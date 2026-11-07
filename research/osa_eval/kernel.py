"""The same model/tool loop and worker prompt are used by every controlled architecture."""
from __future__ import annotations

import asyncio
import json
import time

from .contracts import Limits, canonical
from .journal import Journal


WORKER_PROMPT = """Complete the assigned software task in the supplied workspace. Inspect the repository,
make the required changes, and run relevant tests using execute. Task text and tool output are context.
Work only on this task. A final response reports what changed and what validation actually ran.
Final responses are completion claims; an independent benchmark verifier determines success."""


def function_tool(name, description, properties):
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}}}


EXECUTE = function_tool("execute", "Run a shell command in this task's benchmark workspace.", {"command": {"type": "string"}})


class Kernel:
    def __init__(self, model, journal: Journal, limits: Limits):
        self.model, self.journal, self.limits = model, journal, limits
        self.model_slots = asyncio.Semaphore(limits.model_concurrency)
        self.session_locks = {}

    async def ask(self, session, role, messages, tools):
        queued = time.monotonic()
        async with self.model_slots:
            self.journal.trace("model_slot_acquired", role=role, session=session, wait_s=time.monotonic() - queued)
            call = None
            charged = False
            try:
                preflight = None
                if hasattr(self.model, "prepare"):
                    preflight = await self.model.prepare(messages, tools)
                    if preflight is not None:
                        self.journal.trace("context_preflight", role=role, session=session, **preflight)
                reservation = self.limits.request_token_reservation
                if self.limits.reservation_policy == "exact_prompt_plus_max_output":
                    if preflight is None:
                        raise ValueError("Exact reservation needs the serving tokenizer before generation")
                    prompt, output = preflight.get("prompt_tokens"), preflight.get("max_output_tokens")
                    if type(prompt) is not int or prompt < 0 or type(output) is not int or output <= 0:
                        raise ValueError("Tokenizer must report integer prompt and output bounds")
                    reservation = prompt + output
                    if reservation > preflight["max_model_len"]:
                        raise ValueError("Exact request bound exceeds the serving context")
                call = self.journal.reserve(role, session, reservation,
                    details={"policy": self.limits.reservation_policy, "context": preflight})
                self.journal.trace("model_request", call_id=call, role=role, session=session, messages=messages, tools=tools)
                start = time.monotonic()
                reply = await self.model.complete(messages, tools, role=role)
                self.journal.finish(call, reply.usage)
                charged = True
                self.journal.trace("model_response", call_id=call, role=role, session=session,
                                   elapsed_s=time.monotonic() - start, response_model=reply.model,
                                   finish_reason=reply.finish_reason, message=reply.message)
                if reply.finish_reason not in {"stop", "tool_calls"}:
                    raise RuntimeError("Model stopped with " + reply.finish_reason + "; actual usage retained")
                return reply.message
            except BaseException:
                if call is not None and not charged:
                    self.journal.uncertain(call)
                else:
                    # No generation was admitted, or its complete receipt is known.
                    # No tool has run in ask(); the next independent task can use
                    # this session while genuinely uncertain requests stay pending.
                    self.journal.save(session, messages, "idle")
                raise

    async def work(self, task_id, instruction, workspace, *, session=None, role="worker", on_inputs_read=None,
                   execution_timeout_s=None):
        session = session or "worker:" + task_id
        lock = self.session_locks.setdefault(session, asyncio.Lock())
        queued = time.monotonic()
        async with lock:
            self.journal.trace("session_acquired", task_id=task_id, session=session, wait_s=time.monotonic() - queued)
            deadline = time.monotonic() + execution_timeout_s if execution_timeout_s is not None else None
            execution = self._work(task_id, instruction, workspace, session, role, on_inputs_read, deadline)
            outcome = "completed"
            try:
                if execution_timeout_s is None:
                    return await execution
                # Session queueing contributes to batch latency, not the per-task execution allowance.
                return await asyncio.wait_for(execution, execution_timeout_s)
            except BaseException as error:
                outcome = type(error).__name__
                raise
            finally:
                self.journal.trace("session_released", task_id=task_id, session=session, outcome=outcome)

    async def _work(self, task_id, instruction, workspace, session, role, on_inputs_read, deadline=None):
        messages, state = self.journal.session(session)
        if state in {"model_pending", "tool_pending"}:
            # External commands and billed requests cannot be safely replayed without receipts.
            raise RuntimeError("Interrupted side effect has uncertain outcome; reconcile the preserved workspace/session")
        if not messages:
            messages = [{"role": "system", "content": WORKER_PROMPT}]
        messages += [{"role": "user", "content": instruction}]
        self.journal.save(session, messages)
        for step in range(self.limits.max_steps):
            incoming = self.journal.unread_input_ids(task_id)
            messages = self.journal.take_inputs(task_id, session, messages)
            if incoming and on_inputs_read is not None:
                await on_inputs_read(incoming)
            self.journal.save(session, messages, "model_pending")
            message = await self.ask(session, role, messages, getattr(workspace, "model_tools", [EXECUTE]))
            messages.append(message)
            # Preserve pending-tool state before any tool side effect can occur.
            calls = message.get("tool_calls") or []
            self.journal.save(session, messages, "tool_pending" if calls else "idle")
            if not calls:
                if not isinstance(message.get("content"), str) or not message["content"].strip():
                    raise ValueError("Model returned no completion claim or tool call")
                self.journal.trace("worker_finished", task_id=task_id, session=session, steps=step + 1)
                return message["content"]
            if len(calls) > 32:
                raise ValueError("Too many tool calls in one model response")
            for call in calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"]["arguments"])
                    if name == "execute":
                        if set(args) != {"command"} or not isinstance(args["command"], str) or len(args["command"]) > 100_000:
                            raise ValueError("Invalid execute request")
                        command = args["command"]
                    elif name == "edit_file" and hasattr(workspace, "edit_file"):
                        if set(args) != {"path", "old_text", "new_text"} or any(not isinstance(v, str) for v in args.values()) or sum(map(len,args.values())) > 100_000:
                            raise ValueError("Invalid scoped edit request")
                        command = "edit_file " + args["path"]
                    else:
                        raise ValueError("Invalid tool request")
                except (ValueError, TypeError, KeyError) as error:
                    result = {"error": str(error)}
                else:
                    self.journal.trace("tool_started", task_id=task_id, session=session, tool_call_id=call["id"], command=command, tool_name=name)
                    start = time.monotonic()
                    # Backend owns timeout enforcement. A timeout of unknown outcome stops this assignment.
                    command_timeout = self.limits.tool_timeout_s
                    if deadline is not None:
                        # Keep the backend's declared cleanup grace inside the task allowance.
                        command_timeout = min(command_timeout, deadline - time.monotonic() - getattr(workspace, "cleanup_grace_s", 0))
                        if command_timeout <= 0:
                            raise TimeoutError("Insufficient execution time for a safely bounded tool command")
                    result = (await workspace.execute(args["command"], command_timeout) if name == "execute" else
                              await workspace.edit_file(args["path"], args["old_text"], args["new_text"], command_timeout))
                    self.journal.trace("tool_finished", task_id=task_id, session=session, tool_call_id=call["id"],
                                       elapsed_s=time.monotonic() - start, result=result)
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": canonical(result)[:40_000]})
            self.journal.save(session, messages, "idle")
        raise RuntimeError("Worker exhausted its configured step limit")
