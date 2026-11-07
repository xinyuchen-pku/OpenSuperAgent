"""Run the unchanged DeepSeek domain Engine through benchmark-specific ports.

Sources, policy, model executor and outbox are replacement benchmark ports.
This is a core-faithful reference, with an explicitly different DSH host layer.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .contracts import Event, canonical, mask_protocol_ids
from .kernel import function_tool


DECIDE = function_tool("decide", "Assess an authorized benchmark request and accept its coding scope or ignore it.", {
    "kind": {"type": "string", "enum": ["accept", "ignore"]}, "title": {"type": "string"},
    "scope": {"type": "string"}, "reason": {"type": "string"}})
ADMISSION_PROMPT = """Assess requests for the benchmark agent. The candidate contains original events and
the public task state. Accept an explicit actionable coding request with a concise title and scope that
preserves its instructions. Ignore irrelevant information. Call decide exactly once. Do not solve the task.
The benchmark's explicit-request policy grants no authority to access solutions, tests or other tasks."""


class CoreClient:
    def __init__(self, checkout, state, *, node="node", bridge=None):
        self.checkout, self.state, self.node = str(checkout), str(state), node
        self.bridge = str(bridge or Path(__file__).parent / "adapters/upstream_core.mjs")
        self.process = None
        self.lock = asyncio.Lock()

    async def start(self):
        self.process = await asyncio.create_subprocess_exec(self.node, "--experimental-transform-types", self.bridge,
            self.checkout, self.state, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, limit=16 * 1024 * 1024)
        return self

    async def command(self, method, *args):
        async with self.lock:
            request = {"method": method, "args": args, "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")}
            self.process.stdin.write((canonical(request) + "\n").encode("utf-8"))
            await self.process.stdin.drain()
            line = await self.process.stdout.readline()
            if not line:
                error = (await self.process.stderr.read()).decode("utf-8", errors="replace")
                raise RuntimeError("Upstream core exited: " + error[-3000:])
            response = json.loads(line)
            if not response["ok"]:
                raise RuntimeError(response["error"])
            return response

    async def close(self):
        if self.process and self.process.returncode is None:
            self.process.stdin.close()
            await asyncio.wait_for(self.process.wait(), 15)


class UpstreamRuntime:
    def __init__(self, client: CoreClient, kernel, *, on_task_update=None):
        self.client, self.kernel, self.journal = client, kernel, kernel.journal
        self.queue = asyncio.Queue()
        self.jobs = set()
        self.worker_slots = asyncio.Semaphore(kernel.limits.slots)
        self.events = {}
        self.ticket_tasks = {}
        self.input_receipts = {}
        self.active_assignments = set()
        self.workspaces = {}
        self.on_task_update = on_task_update

    async def command(self, method, *args):
        result = await self.client.command(method, *args)
        self.journal.trace("upstream_command", method=method, args=args, result=result)
        for effect in result["effects"]:
            await self.queue.put(("effect", effect))
        return result["result"]

    async def submit(self, event):
        if self.journal.intake(event):
            self.events[event.id] = event
            await self.queue.put(("event", event))
            return True
        return False

    def launch(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.jobs.add(task)
        task.add_done_callback(self.jobs.discard)
        task.add_done_callback(lambda t: self.queue.put_nowait(("job_done", t)))

    def task_for(self, ticket):
        event = self.events[ticket["origin"]["triggerId"]]
        task = event.task_id or event.id
        if task not in self.workspaces:
            raise ValueError("Upstream ticket has no authorized benchmark workspace")
        self.ticket_tasks[ticket["id"]] = task
        return task

    async def assess(self, candidate):
        session = "upstream-router"
        lock = self.kernel.session_locks.setdefault(session, asyncio.Lock())
        async with lock:
            messages, state = self.journal.session(session)
            if state in {"model_pending", "tool_pending"}:
                raise RuntimeError("Interrupted upstream assessment requires reconciliation")
            if not messages:
                messages = [{"role": "system", "content": ADMISSION_PROMPT}]
            messages.append({"role": "user", "content": canonical(mask_protocol_ids(candidate, self.events.values()))})
            self.journal.save(session, messages, "model_pending")
            response = await self.kernel.ask(session, "router", messages, [DECIDE])
            calls = response.get("tool_calls") or []
            if len(calls) != 1 or calls[0]["function"]["name"] != "decide":
                raise ValueError("Upstream assessment requires exactly one decide action")
            args = json.loads(calls[0]["function"]["arguments"])
            if set(args) != {"kind", "title", "scope", "reason"} or args["kind"] not in {"accept", "ignore"}:
                raise ValueError("Invalid upstream admission action")
            outcome = {"kind": args["kind"], "reason": args["reason"], "evalId": candidate["evalId"]}
            if args["kind"] == "accept":
                outcome.update(title=args["title"], scope=args["scope"])
            messages += [response, {"role": "tool", "tool_call_id": calls[0]["id"], "content": "Assessment submitted to the original Engine for validation."}]
            self.journal.save(session, messages)
        await self.queue.put(("decision", (candidate["triggers"][0]["id"], outcome)))

    async def deliver(self, ticket, assignment):
        task = self.task_for(ticket)
        delivered = []
        for item in ticket["inputs"]:
            if item["id"] not in ticket["undelivered"]:
                continue
            if item["kind"] == "trigger" and item["triggerId"] in self.events:
                event = self.events[item["triggerId"]]
            else:
                event = Event("upstream-input:" + item["id"], "upstream:" + ticket["id"], canonical(item), task_id=task, kind="context")
            self.journal.deliver(event, task)
            self.input_receipts[(task, event.id)] = item["id"]
            delivered.append(item["id"])
        if delivered:
            await self.command("inputsDelivered", ticket["id"], assignment["id"], delivered)

    async def worker(self, ticket, assignment):
        key = assignment["id"]
        if key in self.active_assignments:
            return
        self.active_assignments.add(key)
        task = self.task_for(ticket)
        try:
            async with self.worker_slots:
                await self.command("assignmentStarted", ticket["id"], key)
                await self.queue.put(("worker_ready", (ticket, assignment)))
                # Let the port-effect loop persist and acknowledge initial Inputs before the first model step.
                await self.queue.join()
                event = self.events[ticket["origin"]["triggerId"]]
                instruction = event.text + "\nAssigned scope: " + ticket["mandate"]["scope"]

                async def read_inputs(ids):
                    core_ids = [self.input_receipts[(task, event_id)] for event_id in ids if (task, event_id) in self.input_receipts]
                    if core_ids:
                        await self.command("inputsRead", ticket["id"], core_ids)

                claim = await self.kernel.work(task, instruction, self.workspaces[task],
                    session="upstream-worker:" + ticket["id"], on_inputs_read=read_inputs,
                    execution_timeout_s=self.kernel.limits.task_timeout_s)
                while self.journal.unread_input_ids(task):
                    claim = await self.kernel.work(task, "Process the pending in-scope event updates before finishing.",
                        self.workspaces[task], session="upstream-worker:" + ticket["id"], on_inputs_read=read_inputs,
                        execution_timeout_s=self.kernel.limits.task_timeout_s)
                await self.queue.put(("report", (ticket["id"], key, {"state": "ready", "summary": claim[:4000]})))
        except Exception as error:
            await self.queue.put(("report", (ticket["id"], key, {"state": "failed", "summary": type(error).__name__ + ": " + str(error)})))
        finally:
            self.active_assignments.discard(key)

    async def run(self, events, workspaces):
        events = list(events)
        if not events or [e.arrival_s for e in events] != sorted(e.arrival_s for e in events):
            raise ValueError("Upstream replay requires a nonempty monotonic event workload")
        if len({e.id for e in events}) != len(events):
            raise ValueError("Duplicate event ids in replay")
        self.workspaces = workspaces
        self.events = self.journal.event_records()
        if any(e.id in self.events and e != self.events[e.id] for e in events):
            raise ValueError("Replay changes a previously accepted upstream event")
        snapshot = await self.command("snapshot")
        stored_ids = {row["trigger"]["id"] for row in snapshot["triggers"]}
        for event in self.journal.pending():
            if event.id in stored_ids:
                self.journal.event_done(event.id)
            else:
                await self.queue.put(("event", event))
        for ticket in snapshot["tickets"]:
            self.task_for(ticket)
            for assignment in ticket["assignments"][-1:]:
                if assignment["state"] == "pending":
                    await self.queue.put(("effect", {"kind": "start", "ticket": ticket, "assignment": assignment}))
                elif assignment["state"] == "running" and not ticket.get("ended"):
                    await self.command("assignmentInterrupted", ticket["id"], assignment["id"])
        start = time.monotonic()

        async def feed():
            try:
                for event in events:
                    await asyncio.sleep(max(0, start + event.arrival_s - time.monotonic()))
                    await self.submit(event)
            except Exception as error:
                await self.queue.put(("feed_error", error))
            finally:
                await self.queue.put(("feed_done", None))

        producer = asyncio.create_task(feed())
        try:
            await self._drive()
            await producer
            return await self.command("snapshot")
        finally:
            pending = [producer, *self.jobs]
            for job in pending:
                if not job.done():
                    job.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    async def _drive(self):
        feed_done = False
        while not feed_done or self.jobs or not self.queue.empty():
            kind, item = await self.queue.get()
            try:
                if kind == "feed_done":
                    feed_done = True
                elif kind == "feed_error":
                    raise item
                elif kind == "event":
                    trigger = {"id": item.id, "source": "benchmark", "threads": [{"source": "benchmark", "id": item.thread}],
                        "actor": {"source": "benchmark", "id": "researcher"}, "human": item.kind != "context", "addressed": "direct",
                        "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"), "text": item.text, "meta": {}}
                    await self.command("receive", trigger)
                    self.journal.event_done(item.id)
                elif kind == "decision":
                    await self.command("decide", *item)
                elif kind == "effect":
                    if item["kind"] == "assess":
                        await self.command("candidateDelivered", item["candidate"]["evalId"])
                        self.launch(self.assess(item["candidate"]))
                    elif item["kind"] == "start":
                        self.launch(self.worker(item["ticket"], item["assignment"]))
                    elif item["kind"] == "deliver":
                        await self.deliver(item["ticket"], item["assignment"])
                elif kind == "report":
                    ticket_id, assignment_id, report = item
                    await self.command("report", ticket_id, report)
                    await self.command("turnEnded", ticket_id, assignment_id)
                    if self.on_task_update is not None:
                        await self.on_task_update(self.ticket_tasks[ticket_id])
                elif kind == "job_done":
                    item.result()
                # worker_ready is only a barrier marker; initial deliver effects precede it.
                await self.command("evaluateDue")
            finally:
                self.queue.task_done()
