"""Transactional event intake, session checkpoints, and global usage reservations."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .contracts import Event, Usage, canonical, digest


class BudgetExhausted(RuntimeError):
    pass


class Journal:
    def __init__(self, path, *, token_budget: int, identity: dict):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.db() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, messages TEXT NOT NULL, state TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS subscriptions(thread TEXT NOT NULL, task TEXT NOT NULL, PRIMARY KEY(thread,task));
            CREATE TABLE IF NOT EXISTS inputs(event TEXT NOT NULL,task TEXT NOT NULL,payload TEXT NOT NULL,read INTEGER DEFAULT 0,PRIMARY KEY(event,task));
            CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY,role TEXT NOT NULL,session TEXT NOT NULL,reserved INTEGER NOT NULL,state TEXT NOT NULL,input_tokens INTEGER,output_tokens INTEGER,cost REAL);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,instruction TEXT NOT NULL,session TEXT NOT NULL,role TEXT NOT NULL,state TEXT NOT NULL,result TEXT);
            CREATE TABLE IF NOT EXISTS trace(seq INTEGER PRIMARY KEY AUTOINCREMENT,at REAL NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL);
            """)
            expected = {"identity": identity, "token_budget": token_budget}
            row = db.execute("SELECT value FROM metadata WHERE key='run'").fetchone()
            if row and json.loads(row[0]) != expected:
                raise ValueError("Resume identity or budget differs from the frozen run")
            db.execute("INSERT OR IGNORE INTO metadata VALUES('run',?)", (canonical(expected),))
            db.execute("INSERT OR IGNORE INTO metadata VALUES('invalid','false')")
        self.token_budget = token_budget

    @contextmanager
    def db(self):
        with self.lock:
            db = sqlite3.connect(str(self.path), timeout=30)
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
    def _trace(db, kind, payload):
        db.execute("INSERT INTO trace(at,kind,payload) VALUES(?,?,?)", (time.time(), kind, canonical(payload)))

    def trace(self, kind, **payload):
        with self.db() as db:
            self._trace(db, kind, payload)

    def intake(self, event: Event):
        payload = canonical(event.__dict__)
        with self.db() as db:
            row = db.execute("SELECT payload FROM events WHERE id=?", (event.id,)).fetchone()
            if row:
                if row[0] != payload:
                    raise ValueError("An event id was reused with a different payload")
                return False
            db.execute("INSERT INTO events VALUES(?,?,'pending')", (event.id, payload))
            self._trace(db, "event_received", event.__dict__)
            return True

    def pending(self):
        with self.db() as db:
            return [Event(**json.loads(r[0])) for r in db.execute("SELECT payload FROM events WHERE state='pending' ORDER BY rowid")]

    def event_records(self):
        with self.db() as db:
            return {r["id"]: Event(**json.loads(r["payload"])) for r in db.execute("SELECT id,payload FROM events ORDER BY rowid")}

    def unread_input_ids(self, task):
        with self.db() as db:
            return [r[0] for r in db.execute("SELECT event FROM inputs WHERE task=? AND read=0 ORDER BY rowid", (task,))]

    def event_done(self, event_id):
        with self.db() as db:
            db.execute("UPDATE events SET state='routed' WHERE id=?", (event_id,))

    def assign(self, event, task, session, role, *, subscribe=False):
        with self.db() as db:
            row = db.execute("SELECT id FROM tasks WHERE id=?", (task,)).fetchone()
            if row:
                db.execute("INSERT OR IGNORE INTO inputs(event,task,payload) VALUES(?,?,?)", (event.id, task, event.text))
                db.execute("UPDATE tasks SET state='pending' WHERE id=? AND state='completed'", (task,))
            else:
                db.execute("INSERT INTO tasks(id,instruction,session,role,state) VALUES(?,?,?,?,'pending')", (task, event.text, session, role))
            if subscribe:
                db.execute("INSERT OR IGNORE INTO subscriptions VALUES(?,?)", (event.thread, task))
            db.execute("UPDATE events SET state='routed' WHERE id=?", (event.id,))
            self._trace(db, "task_assigned", {"task_id": task, "event_id": event.id, "session": session, "role": role})

    def tasks(self):
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM tasks ORDER BY rowid")]

    def task_state(self, task, state, result=None):
        with self.db() as db:
            db.execute("UPDATE tasks SET state=?,result=? WHERE id=?", (state, result, task))
            self._trace(db, "task_state", {"task_id": task, "state": state, "result": result})

    def complete_task(self, task, result=None):
        with self.db() as db:
            unread = db.execute("SELECT 1 FROM inputs WHERE task=? AND read=0 LIMIT 1", (task,)).fetchone()
            state = "pending" if unread else "completed"
            db.execute("UPDATE tasks SET state=?,result=? WHERE id=?", (state, result, task))
            self._trace(db, "task_state", {"task_id": task, "state": state})

    def subscribe(self, thread, task):
        with self.db() as db:
            db.execute("INSERT OR IGNORE INTO subscriptions VALUES(?,?)", (thread, task))

    def subscribers(self, thread):
        with self.db() as db:
            return [r[0] for r in db.execute("SELECT task FROM subscriptions WHERE thread=? ORDER BY task", (thread,))]

    def deliver(self, event: Event, task):
        with self.db() as db:
            db.execute("INSERT OR IGNORE INTO inputs(event,task,payload) VALUES(?,?,?)", (event.id, task, event.text))

    def take_inputs(self, task, session, messages):
        # Taking an input and checkpointing its appearance in history is one transaction.
        with self.db() as db:
            rows = db.execute("SELECT event,payload FROM inputs WHERE task=? AND read=0 ORDER BY rowid", (task,)).fetchall()
            messages = list(messages) + [{"role": "user", "content": "Event update: " + r["payload"]} for r in rows]
            db.executemany("UPDATE inputs SET read=1 WHERE event=? AND task=?", [(r["event"], task) for r in rows])
            db.execute("INSERT OR REPLACE INTO sessions VALUES(?,?,'idle')", (session, canonical(messages)))
            return messages

    def session(self, session):
        with self.db() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (session,)).fetchone()
            return (json.loads(row["messages"]), row["state"]) if row else ([], "new")

    def save(self, session, messages, state="idle"):
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO sessions VALUES(?,?,?)", (session, canonical(messages), state))

    def reserve(self, role, session, amount, *, details=None):
        if type(amount) is not int or amount <= 0:
            raise ValueError("Reservation must be a positive integer")
        key = None
        with self.db() as db:
            used = db.execute("SELECT COALESCE(SUM(CASE WHEN state='complete' THEN input_tokens+output_tokens ELSE reserved END),0) FROM calls").fetchone()[0]
            if used + amount > self.token_budget:
                self._trace(db, "budget_reservation_denied", {"role": role, "session": session,
                    "requested_tokens": amount, "used_or_reserved_tokens": used,
                    "budget_tokens": self.token_budget, "details": details})
            else:
                key = uuid.uuid4().hex
                db.execute("INSERT INTO calls(id,role,session,reserved,state) VALUES(?,?,?,?,'pending')", (key, role, session, amount))
                self._trace(db, "budget_reservation_accepted", {"call_id": key, "role": role,
                    "session": session, "reserved_tokens": amount, "details": details})
        # Commit denial telemetry even though admission raises; no API call was issued.
        if key is None:
            raise BudgetExhausted("Global token budget cannot cover another reserved model call")
        return key

    def finish(self, call_id, usage: Usage):
        overflow = False
        with self.db() as db:
            row = db.execute("SELECT reserved,state FROM calls WHERE id=?", (call_id,)).fetchone()
            if not row or row["state"] != "pending":
                raise ValueError("Call is missing or was already charged")
            overflow = usage.tokens > row["reserved"]
            db.execute("UPDATE calls SET state='complete',input_tokens=?,output_tokens=?,cost=? WHERE id=?", (usage.input_tokens, usage.output_tokens, usage.cost_usd, call_id))
            if overflow:
                db.execute("UPDATE metadata SET value='true' WHERE key='invalid'")
            self._trace(db, "model_usage", {"call_id": call_id, **usage.__dict__, "reservation_overrun": overflow})
        if overflow:
            raise ValueError("Provider usage exceeded the reserved context bound; run is invalid")

    def uncertain(self, call_id):
        # Transport failures can still be billed. Retain the full reservation and exclude formal aggregation.
        with self.db() as db:
            db.execute("UPDATE calls SET state='uncertain' WHERE id=? AND state='pending'", (call_id,))
            db.execute("UPDATE metadata SET value='true' WHERE key='invalid'")

    def usage(self):
        with self.db() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM calls ORDER BY rowid")]
            invalid = json.loads(db.execute("SELECT value FROM metadata WHERE key='invalid'").fetchone()[0])
            denials = [{"at": r["at"], **json.loads(r["payload"])} for r in db.execute(
                "SELECT at,payload FROM trace WHERE kind='budget_reservation_denied' ORDER BY seq")]
            return {"calls": rows, "input_tokens": sum(r["input_tokens"] or 0 for r in rows),
                    "output_tokens": sum(r["output_tokens"] or 0 for r in rows),
                    "observed_api_tokens": sum((r["input_tokens"] or 0) + (r["output_tokens"] or 0) for r in rows),
                    "actual_api_tokens": (sum((r["input_tokens"] or 0) + (r["output_tokens"] or 0) for r in rows)
                                          if all(r["state"] == "complete" for r in rows) else None),
                    "accepted_reservation_tokens_sum": sum(r["reserved"] for r in rows),
                    "outstanding_reserved_tokens": sum(r["reserved"] for r in rows if r["state"] != "complete"),
                    "reservation_denied_count": len(denials), "reservation_denials": denials,
                    "cost_usd": None if any(r["cost"] is None for r in rows) else sum(r["cost"] for r in rows),
                    "uncertain_or_pending_call_count": sum(r["state"] != "complete" for r in rows),
                    "total_token_upper_bound": sum((r["input_tokens"] + r["output_tokens"]) if r["state"] == "complete" else r["reserved"] for r in rows),
                    "accounting_valid": not invalid and all(r["state"] == "complete" for r in rows)}

    def export(self, target):
        target = Path(target)
        target.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            rows = [{"seq": r["seq"], "at": r["at"], "kind": r["kind"], **json.loads(r["payload"])} for r in db.execute("SELECT * FROM trace ORDER BY seq")]
        (target / "trace.jsonl").write_text("".join(canonical(r) + "\n" for r in rows), encoding="utf-8")
        (target / "usage.json").write_text(canonical(self.usage()) + "\n", encoding="utf-8")
