"""Deterministic framework checks. No benchmark quality or commercial-model claims."""
import asyncio
from pathlib import Path

from .contracts import Event, Limits, Reply, Usage, canonical
from .journal import Journal
from .kernel import Kernel
from .runtime import ARCHITECTURES, Runtime


class DiagnosticModel:
    identity = {"model": "diagnostic-scripted", "real_model": False}

    async def complete(self, messages, tools, *, role):
        await asyncio.sleep(.002)
        if tools[0]["function"]["name"] == "route":
            message = {"role": "assistant", "content": None, "tool_calls": [{"id": "route-call", "type": "function", "function": {"name": "route", "arguments": '{"action":"delegate"}'}}]}
        else:
            message = {"role": "assistant", "content": "Diagnostic completion; benchmark success is ungraded."}
        return Reply(message, Usage(20, 5, 0.0), "diagnostic-scripted")


class DiagnosticWorkspace:
    identity = {"backend": "diagnostic-no-shell", "benchmark": False}
    async def execute(self, command, timeout_s):
        raise AssertionError("Diagnostic model should not invoke a shell")


async def run_smoke(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    reports = []
    for architecture in ARCHITECTURES:
        folder = output / architecture
        limits = Limits(token_budget=100_000, request_token_reservation=1000, slots=2, max_steps=5)
        journal = Journal(folder / "run.sqlite3", token_budget=limits.token_budget,
                          identity={"architecture": architecture, "purpose": "diagnostic", "limits": limits.public(), "model": DiagnosticModel.identity})
        events = [Event("request:a", "thread:a", "Diagnostic task A", task_id="a"),
                  Event("request:b", "thread:b", "Diagnostic task B", task_id="b"),
                  Event("update:a", "thread:a", "Diagnostic followup", arrival_s=.02, task_id="a", kind="followup")]
        result = await Runtime(architecture, Kernel(DiagnosticModel(), journal, limits)).run(events, {"a": DiagnosticWorkspace(), "b": DiagnosticWorkspace()})
        journal.export(folder)
        report = {"architecture": architecture, "purpose": "framework smoke only", "real_model": False, "official_benchmark": False,
                  "tasks": result, "accounting": journal.usage(), "passed": all(t["state"] == "completed" for t in result)}
        (folder / "diagnostic.json").write_text(canonical(report) + "\n", encoding="utf-8")
        reports.append({"architecture": architecture, "passed": report["passed"], "model_calls": len(report["accounting"]["calls"])})
    (output / "summary.json").write_text(canonical({"purpose": "framework smoke only", "results": reports}) + "\n", encoding="utf-8")
    return reports
