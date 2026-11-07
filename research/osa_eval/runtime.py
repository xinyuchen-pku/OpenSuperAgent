"""Task-level controlled architecture comparison; upstream fidelity is a separate adapter."""
from __future__ import annotations

import asyncio
import json
import time

from .contracts import Event, canonical, model_event, public_id
from .kernel import WORKER_PROMPT, function_tool


ARCHITECTURES = ("single", "single_subagent", "eager_delegation", "router_worker", "superagent")
ROUTE = function_tool("route", "Choose whether the main session executes this request or delegates a task.", {
    "action": {"type": "string", "enum": ["self", "delegate"]}})
ROUTER_PROMPT = """Route software requests to independent worker sessions. Use the supplied task id.
Keep follow-ups attached to their explicit task. Select route(action='delegate') to delegate;
select route(action='self') to execute in the main session when that option is allowed.
Do not solve the coding task in a routing response. Emit exactly one route tool call."""


class Runtime:
    def __init__(self, architecture, kernel, *, subscriptions=True, on_task_update=None):
        if architecture not in ARCHITECTURES:
            raise ValueError("Unknown architecture")
        self.architecture, self.kernel = architecture, kernel
        self.journal, self.limits = kernel.journal, kernel.limits
        self.subscriptions = subscriptions
        self.on_task_update = on_task_update
        self.slots = asyncio.Semaphore(self.limits.slots)
        self.single_lock = asyncio.Lock()
        self.running = {}

    async def _decision(self, event):
        if self.architecture == "single":
            return "self"
        if self.architecture == "router_worker":
            session = "router:" + event.id  # Stateless router: fresh history per event.
        elif self.architecture == "superagent":
            session = "router"  # Persistent decision history.
        else:
            session = "main"  # Shared with direct execution in the dynamic baseline.
        lock = self.kernel.session_locks.setdefault(session, asyncio.Lock())
        async with lock:
            messages, state = self.journal.session(session)
            if state in {"model_pending", "tool_pending"}:
                raise RuntimeError("Router has an uncertain interrupted turn")
            if not messages:
                messages = [{"role": "system", "content": WORKER_PROMPT if session == "main" else ROUTER_PROMPT}]
            force = self.architecture != "single_subagent"
            messages.append({"role": "user", "content": ROUTER_PROMPT + ("\nThis condition requires delegation." if force else "\nChoose freely; delegation is optional.") + "\nEvent: " + canonical(model_event(event))})
            self.journal.save(session, messages, "model_pending")
            message = await self.kernel.ask(session, "router" if session != "main" else "main", messages, [ROUTE])
            calls = message.get("tool_calls") or []
            if len(calls) != 1 or calls[0]["function"]["name"] != "route":
                raise ValueError("Router must emit exactly one route tool call")
            args = json.loads(calls[0]["function"]["arguments"])
            if set(args) != {"action"} or args["action"] not in {"self", "delegate"}:
                raise ValueError("Invalid routing action")
            if force and args["action"] != "delegate":
                raise ValueError("Router violated the condition's mandatory delegation rule")
            messages += [message, {"role": "tool", "tool_call_id": calls[0]["id"], "content": canonical({"accepted": args["action"]})}]
            self.journal.save(session, messages)
            return args["action"]

    async def _route(self, event):
        task = event.task_id or event.id
        targets = self.journal.subscribers(event.thread) if self.architecture == "superagent" and self.subscriptions else []
        # Explicit task references narrow delivery. Subscription-only events can fan out many-to-many.
        if targets and (event.task_id is None or event.task_id in targets) and event.kind != "request":
            if event.task_id:
                targets = [event.task_id]
            existing = {t["id"]: t for t in self.journal.tasks()}
            for target in targets:
                row = existing[target]
                self.journal.assign(event, target, row["session"], row["role"], subscribe=True)
            self.journal.trace("subscription_fanout", event_id=event.id, tasks=targets)
            return
        action = await self._decision(event)
        session = "main" if action == "self" else "worker:" + task
        self.journal.assign(event, task, session, "main" if action == "self" else "worker",
                            subscribe=self.architecture == "superagent" and self.subscriptions)

    async def _execute(self, row, workspace):
        task = row["id"]
        try:
            async with self.slots:
                self.journal.task_state(task, "running")
                self.journal.trace("worker_started", task_id=task, workspace=workspace.identity)
                instruction = row["instruction"] if not self.journal.session(row["session"])[0] else "Continue assigned task " + public_id(task) + ":\n" + row["instruction"]
                claim = await self.kernel.work(task, instruction, workspace, session=row["session"], role=row["role"],
                                               execution_timeout_s=self.limits.task_timeout_s)
                # Completion claims are distinct from official benchmark grades.
                self.journal.complete_task(task, claim)
                if self.on_task_update is not None:
                    await self.on_task_update(task)
                await self._notify(row)
        except Exception as error:
            self.journal.task_state(task, "blocked", type(error).__name__ + ": " + str(error))
            if self.on_task_update is not None:
                await self.on_task_update(task)
            await self._notify(row)
        finally:
            self.journal.trace("worker_slot_released", task_id=task)

    async def _notify(self, row):
        if row["session"] == "main" or self.architecture in {"single", "router_worker"}:
            return
        session = "router" if self.architecture == "superagent" else "main"
        lock = self.kernel.session_locks.setdefault(session, asyncio.Lock())
        async with lock:
            messages, state = self.journal.session(session)
            if state != "idle":
                self.journal.trace("notification_deferred", task_id=row["id"], session=session, state=state)
                return
            current = next(t for t in self.journal.tasks() if t["id"] == row["id"])
            report = {"id": public_id(current["id"]), "state": current["state"], "role": current["role"], "result": (current["result"] or "")[:4000]}
            messages.append({"role": "user", "content": "Worker status report: " + canonical(report)})
            self.journal.save(session, messages)
            self.journal.trace("completion_notification", task_id=row["id"], session=session, task_state=current["state"])

    def _dispatch(self, workspaces):
        for row in self.journal.tasks():
            if row["state"] != "pending" or (row["id"] in self.running and not self.running[row["id"]].done()):
                continue
            if row["id"] not in workspaces:
                raise ValueError("Missing benchmark workspace for task " + row["id"])
            self.running[row["id"]] = asyncio.create_task(self._execute(row, workspaces[row["id"]]))

    async def run(self, events, workspaces):
        # Validate all inputs before starting a billed request or task-side effect.
        events = list(events)
        ids = [e.id for e in events]
        if len(set(ids)) != len(ids):
            raise ValueError("Workload contains duplicate event ids")
        if [e.arrival_s for e in events] != sorted(e.arrival_s for e in events):
            raise ValueError("Workload arrival times must be monotonic")
        if any((e.task_id or e.id) not in workspaces for e in events if e.kind == "request" or e.task_id):
            raise ValueError("Workload references a missing workspace")
        previous_events = self.journal.event_records()
        if any(e.id in previous_events and e != previous_events[e.id] for e in events):
            raise ValueError("Replay changes a previously accepted event")
        for row in self.journal.tasks():
            if row["state"] == "running":
                _, state = self.journal.session(row["session"])
                if state != "idle":
                    raise RuntimeError("Interrupted side effect requires explicit reconciliation before resume")
                self.journal.task_state(row["id"], "pending")
                self.journal.trace("safe_resume", task_id=row["id"], session=row["session"])
        start = time.monotonic()
        self.journal.trace("run_started", architecture=self.architecture, subscriptions=self.subscriptions)
        for event in self.journal.pending():
            await self._route(event)
        self._dispatch(workspaces)
        queue = asyncio.Queue()

        async def feed():
            # Arrival is measured independently of the router's own processing latency.
            try:
                for event in events:
                    await asyncio.sleep(max(0, start + event.arrival_s - time.monotonic()))
                    if self.journal.intake(event):
                        self.journal.trace("arrival", event_id=event.id, scheduled_s=event.arrival_s, actual_s=time.monotonic() - start)
                        await queue.put(event)
            except Exception as error:
                await queue.put(error)
            finally:
                await queue.put(None)

        producer = asyncio.create_task(feed())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                if isinstance(event, Exception):
                    raise event
                await self._route(event)
                self._dispatch(workspaces)
        except BaseException:
            producer.cancel()
            for job in self.running.values():
                if not job.done():
                    job.cancel()
            await asyncio.gather(producer, *self.running.values(), return_exceptions=True)
            raise
        finally:
            if not producer.cancelled():
                await producer
            if self.running:
                await asyncio.gather(*self.running.values(), return_exceptions=True)
        while self.running:
            active = list(self.running.values())
            await asyncio.gather(*active)
            self.running = {key: job for key, job in self.running.items() if not job.done()}
            self._dispatch(workspaces)
        self.journal.trace("run_finished", wall_s=time.monotonic() - start)
        return self.journal.tasks()
