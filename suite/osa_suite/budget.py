"""Process-safe task AND campaign accounting, shared by all roles and retries.

Outstanding or uncertain receipts stop further admission. A terminated caller
leaves a durable reservation, requiring an actual provider receipt to reconcile.
No inferred usage or automatic replay is supported.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextvars import ContextVar
from contextlib import contextmanager
from pathlib import Path

from osa_eval.contracts import canonical
from osa_eval.journal import BudgetExhausted, Journal

CURRENT_TASK = ContextVar('osa_suite_task', default=None)


class BudgetLedger:
    def __init__(self, path, *, campaign_limit, task_limit, identity):
        if any(type(v) is not int or v <= 0 for v in (campaign_limit, task_limit)):
            raise ValueError("Positive integer token ceilings required")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        schema = sqlite3.connect(self.path, timeout=60)
        try:
            schema.executescript("""
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY,task TEXT NOT NULL,
                    role TEXT NOT NULL,session TEXT NOT NULL,reserved INTEGER NOT NULL,
                    state TEXT NOT NULL,input_tokens INTEGER,output_tokens INTEGER);
                CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY,at REAL NOT NULL,
                    kind TEXT NOT NULL,payload TEXT NOT NULL);
            """)
        finally:
            schema.close()
        with self.db() as db:
            value = canonical(dict(identity=identity, campaign_limit=campaign_limit, task_limit=task_limit))
            old = db.execute("SELECT value FROM metadata WHERE key='identity'").fetchone()
            if old and old[0] != value:
                raise ValueError("Ledger identity/limits differ from frozen campaign")
            db.execute("INSERT OR IGNORE INTO metadata VALUES('identity',?)", (value,))
            db.execute("INSERT OR IGNORE INTO metadata VALUES('invalid','false')")
        self.campaign_limit, self.task_limit = campaign_limit, task_limit

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=60)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def event(db, kind, payload):
        db.execute("INSERT INTO events(at,kind,payload) VALUES(?,?,?)", (time.time(), kind, canonical(payload)))

    def reserve(self, task, role, session, amount):
        if not isinstance(task, str) or not task:
            raise ValueError("Every billed request needs an explicit logical task identity")
        if type(amount) is not int or amount <= 0:
            raise ValueError("Positive integer reservation required")
        denied = None
        key = uuid.uuid4().hex
        with self.db() as db:
            if db.execute("SELECT value FROM metadata WHERE key='invalid'").fetchone()[0] == 'true':
                raise RuntimeError("Campaign accounting invalid; reconcile receipts before admission")
            charge = "CASE WHEN state='complete' THEN input_tokens+output_tokens ELSE reserved END"
            total = db.execute(f"SELECT COALESCE(SUM({charge}),0) FROM calls WHERE state!='cancelled'").fetchone()[0]
            used = db.execute(f"SELECT COALESCE(SUM({charge}),0) FROM calls WHERE task=? AND state!='cancelled'", (task,)).fetchone()[0]
            if total + amount > self.campaign_limit or used + amount > self.task_limit:
                denied = dict(task=task, role=role, reserved=amount, task_used_or_reserved=used,
                              campaign_used_or_reserved=total)
                self.event(db, "reservation_denied", denied)
            else:
                db.execute("INSERT INTO calls VALUES(?,?,?,?,?,'pending',NULL,NULL)", (key, task, role, session, amount))
                self.event(db, "reservation_accepted", dict(call_id=key, task=task, role=role, reserved=amount))
        if denied:
            raise BudgetExhausted("Full-task or campaign ceiling would be exceeded")
        return key

    def cancel_before_api(self, key):
        with self.db() as db:
            row = db.execute("SELECT state FROM calls WHERE id=?", (key,)).fetchone()
            if not row or row[0] != 'pending':
                raise ValueError("Only a not-issued pending reservation can be cancelled")
            db.execute("UPDATE calls SET state='cancelled' WHERE id=?", (key,))
            self.event(db, "cancelled_before_api", dict(call_id=key))

    def finish(self, key, usage):
        overflow = False
        with self.db() as db:
            row = db.execute("SELECT * FROM calls WHERE id=?", (key,)).fetchone()
            if not row or row['state'] != 'pending':
                raise ValueError("Missing call or duplicate receipt")
            overflow = usage.tokens > row['reserved']
            db.execute("UPDATE calls SET state='complete',input_tokens=?,output_tokens=? WHERE id=?",
                       (usage.input_tokens, usage.output_tokens, key))
            self.event(db, "api_receipt", dict(call_id=key, **usage.__dict__, reservation_overrun=overflow))
            if overflow:
                db.execute("UPDATE metadata SET value='true' WHERE key='invalid'")
        if overflow:
            raise ValueError("Provider receipt exceeded reservation; campaign invalid")

    def uncertain(self, key):
        with self.db() as db:
            db.execute("UPDATE calls SET state='uncertain' WHERE id=? AND state='pending'", (key,))
            db.execute("UPDATE metadata SET value='true' WHERE key='invalid'")
            self.event(db, "unknown_receipt", dict(call_id=key))

    def summary(self):
        with self.db() as db:
            calls = [dict(r) for r in db.execute("SELECT * FROM calls ORDER BY rowid")]
            events = [dict(r, payload=json.loads(r['payload'])) for r in db.execute("SELECT * FROM events ORDER BY seq")]
            invalid = db.execute("SELECT value FROM metadata WHERE key='invalid'").fetchone()[0] == 'true'
        active = [r for r in calls if r['state'] != 'cancelled']
        known = sum((r['input_tokens'] or 0) + (r['output_tokens'] or 0) for r in active)
        outstanding = sum(r['reserved'] for r in active if r['state'] != 'complete')
        valid = not invalid and all(r['state'] == 'complete' for r in active)
        return dict(accounting_valid=valid, actual_api_tokens=known if valid else None,
                    observed_api_tokens=known, outstanding_reserved_tokens=outstanding,
                    total_upper_bound=known + outstanding,
                    reservation_tokens_sum=sum(r['reserved'] for r in active),
                    denied_calls=sum(e['kind'] == 'reservation_denied' for e in events),
                    calls=calls, events=events)


class SharedBudgetJournal(Journal):
    """Frozen Kernel API, with additional aggregate admission and trace envelopes.

    Separate DB transactions are deliberately conservative: a crash between them
    retains a reservation and fails campaign validity, rather than allowing spend.
    """
    def __init__(self, *args, ledger, task_key, **kwargs):
        self.ledger, self.task_key = ledger, task_key
        super().__init__(*args, **kwargs)
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS suite_calls(local_id TEXT PRIMARY KEY,shared_id TEXT NOT NULL)")

    def reserve(self, role, session, amount, *, details=None):
        task = self.task_key() if callable(self.task_key) else self.task_key
        shared = self.ledger.reserve(task, role, session, amount)
        try:
            local = super().reserve(role, session, amount, details=details)
        except BaseException:
            self.ledger.cancel_before_api(shared)
            raise
        with self.db() as db:
            db.execute("INSERT INTO suite_calls VALUES(?,?)", (local, shared))
        return local

    def shared_id(self, key):
        with self.db() as db:
            row = db.execute("SELECT shared_id FROM suite_calls WHERE local_id=?", (key,)).fetchone()
        if row is None:
            raise ValueError("Call lacks campaign mapping; reconcile before continuing")
        return row[0]

    def finish(self, key, usage):
        # Charge the shared receipt first. If local recording fails, it remains
        # visible to the campaign and local accounting marks that assignment invalid.
        self.ledger.finish(self.shared_id(key), usage)
        super().finish(key, usage)

    def uncertain(self, key):
        self.ledger.uncertain(self.shared_id(key))
        super().uncertain(key)

    def export(self, target):
        super().export(target)
        with self.db() as db:
            rows = [dict(schema='osa-trace-v2', seq=r['seq'], at=r['at'], event_type=r['kind'],
                         payload=json.loads(r['payload'])) for r in db.execute("SELECT * FROM trace ORDER BY seq")]
        Path(target, 'events.v2.jsonl').write_text(''.join(canonical(r) + '\n' for r in rows), encoding='utf-8')
