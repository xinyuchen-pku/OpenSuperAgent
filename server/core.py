"""Durable task admission and lifecycle. External inputs never set policy."""
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS tasks (
                  id TEXT PRIMARY KEY, title TEXT, prompt TEXT, status TEXT,
                  source TEXT, actor TEXT, created TEXT, updated TEXT,
                  mandate TEXT, workspace TEXT DEFAULT '', result TEXT DEFAULT '',
                  diff TEXT DEFAULT '', attempts INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS events (
                  seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT,
                  kind TEXT, message TEXT, created TEXT);
                CREATE TABLE IF NOT EXISTS triggers (id TEXT PRIMARY KEY, task_id TEXT);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            ''')
            db.execute("INSERT OR IGNORE INTO settings VALUES ('paused', 'false')")
            db.execute("INSERT OR IGNORE INTO settings VALUES ('observe', 'true')")
            rows = db.execute("SELECT id FROM tasks WHERE status='running'").fetchall()
            for row in rows:
                db.execute("UPDATE tasks SET status='blocked',result=?,updated=? WHERE id=?",
                           ('Runtime restarted during execution. Review the preserved workspace before retrying.', now(), row['id']))
                self.event(db, row['id'], 'recovery', 'Interrupted execution; workspace retained. Retry requires a person.')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def event(self, db, task_id, kind, message):
        db.execute('INSERT INTO events(task_id,kind,message,created) VALUES(?,?,?,?)',
                   (task_id, kind, message, now()))

    def state(self):
        with self.connect() as db:
            db.execute('BEGIN')
            tasks = [dict(r) for r in db.execute('SELECT * FROM tasks ORDER BY created DESC')]
            for t in tasks:
                t['mandate'] = json.loads(t['mandate'])
            return {'tasks': tasks,
                    'events': [dict(r) for r in db.execute('SELECT * FROM events ORDER BY seq DESC LIMIT 250')],
                    'paused': json.loads(db.execute("SELECT value FROM settings WHERE key='paused'").fetchone()[0]),
                    'observe': json.loads(db.execute("SELECT value FROM settings WHERE key='observe'").fetchone()[0])}

    def get(self, task_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            if row is None:
                return None
            task = dict(row)
            task['mandate'] = json.loads(task['mandate'])
            return task

    def create(self, title, prompt, source='local', actor='operator', trigger_id=None, inferred=False):
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 160:
            raise ValueError('Task title must contain 1–160 characters.')
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 20000:
            raise ValueError('Task instructions must contain 1–20,000 characters.')
        with self.lock, self.connect() as db:
            if trigger_id:
                old = db.execute('SELECT task_id FROM triggers WHERE id=?', (trigger_id,)).fetchone()
                if old:
                    return old[0]
            task_id = 'OSA-' + uuid.uuid4().hex[:8].upper()
            stamp = now()
            mandate = {'basis': 'candidate' if inferred else 'explicit', 'actor': actor,
                       'scope': 'local file changes for this task; no publish, merge, shell or deletion',
                       'policy': 'v1', 'created': stamp}
            db.execute('INSERT INTO tasks(id,title,prompt,status,source,actor,created,updated,mandate) VALUES(?,?,?,?,?,?,?,?,?)',
                       (task_id, title.strip(), prompt.strip(), 'observed' if inferred else 'queued', source, actor, stamp, stamp, json.dumps(mandate)))
            self.event(db, task_id, 'admission', 'Candidate recorded for human review.' if inferred else 'Explicit request admitted. Changes stay in an isolated workspace.')
            if trigger_id:
                db.execute('INSERT INTO triggers VALUES(?,?)', (trigger_id, task_id))
            return task_id

    def action(self, task_id, action):
        with self.lock, self.connect() as db:
            row = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            if row is None:
                raise ValueError('Task does not exist.')
            allowed = {'approve': (['observed'], 'queued'), 'retry': (['blocked'], 'queued'),
                       'complete': (['review'], 'done'), 'stop': (['observed', 'queued', 'running', 'blocked', 'review'], 'stopped')}
            if action not in allowed or row['status'] not in allowed[action][0]:
                raise ValueError('This action is unavailable in the current task state.')
            target = allowed[action][1]
            if action == 'approve':
                mandate = json.loads(row['mandate'])
                mandate.update(basis='explicit', approved_by='local operator', approved_at=now())
                db.execute('UPDATE tasks SET mandate=? WHERE id=?', (json.dumps(mandate), task_id))
            db.execute('UPDATE tasks SET status=?,updated=? WHERE id=?', (target, now(), task_id))
            self.event(db, task_id, action, {'approve': 'Operator approved this candidate.', 'retry': 'Retry requested; existing files retained.', 'complete': 'Operator marked reviewed work complete. No GitHub changes were submitted.', 'stop': 'Operator stopped this task; request and existing files retained.'}[action])

    def pause(self, paused):
        if not isinstance(paused, bool):
            raise ValueError('paused must be a boolean.')
        with self.lock, self.connect() as db:
            db.execute("UPDATE settings SET value=? WHERE key='paused'", (json.dumps(paused),))
            self.event(db, None, 'scheduler', 'New dispatch paused; active work continues.' if paused else 'New dispatch resumed.')

    def followup(self, task_id, content):
        if not isinstance(content, str) or not 1 <= len(content.strip()) <= 10000:
            raise ValueError('Follow-up must contain 1–10,000 characters.')
        with self.lock, self.connect() as db:
            row = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            if row is None or row['status'] not in ('blocked', 'review'):
                raise ValueError('Add context when a task is blocked or waiting for review.')
            prompt = row['prompt'] + '\n\nOperator follow-up (within the original task scope):\n' + content.strip()
            if len(prompt) > 40000:
                raise ValueError('Task context reached its 40,000-character budget. Create a new task.')
            db.execute("UPDATE tasks SET prompt=?,status='queued',updated=? WHERE id=?", (prompt, now(), task_id))
            self.event(db, task_id, 'followup', 'Operator supplied additional context and queued another attempt. Workspace retained.')

    def claim(self):
        with self.lock, self.connect() as db:
            if db.execute("SELECT value FROM settings WHERE key='paused'").fetchone()[0] == 'true':
                return None
            row = db.execute("SELECT * FROM tasks WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE tasks SET status='running',attempts=attempts+1,updated=? WHERE id=?", (now(), row['id']))
                self.event(db, row['id'], 'execution', 'Worker claimed task.')
                return row['id']

    def update(self, task_id, **fields):
        if not set(fields) <= {'workspace', 'result', 'diff', 'status'}:
            raise ValueError('Unsupported update.')
        with self.lock, self.connect() as db:
            # A late model response may never resurrect a stopped task.
            row = db.execute('SELECT status FROM tasks WHERE id=?', (task_id,)).fetchone()
            if row['status'] == 'stopped' and 'status' in fields:
                del fields['status']
            fields['updated'] = now()
            db.execute('UPDATE tasks SET ' + ','.join(k + '=?' for k in fields) + ' WHERE id=?', (*fields.values(), task_id))

    def log(self, task_id, kind, message):
        with self.lock, self.connect() as db:
            self.event(db, task_id, kind, message)
