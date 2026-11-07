"""Frozen, resumable controlled Pro V2 workloads with clean-image grading.

The environment factory is explicit; benchmark tasks never receive host paths,
API credentials or evaluator files. A completed output is immutable. Failed
attempts retain their complete evidence and need a new attempt directory.
"""
from __future__ import annotations

import asyncio
import json
import math
import random
import time
from pathlib import Path

from .contracts import canonical, digest
from .journal import Journal
from .kernel import Kernel, WORKER_PROMPT, EXECUTE
from .runtime import ARCHITECTURES, Runtime
from .upstream_runtime import CoreClient, UpstreamRuntime
from .benchmarks import PINS


def balanced_arm_order(blocks, seed=20261102):
    if type(blocks) is not int or blocks <= 0:
        raise ValueError("A positive number of blocks is required")
    arms = list(ARCHITECTURES)
    random.Random(seed).shuffle(arms)
    # Each complete five-block cycle gives every arm each position once.
    return [arms[i % len(arms):] + arms[:i % len(arms)] for i in range(blocks)]


class ProCampaign:
    def __init__(self, tasks, model, limits, factory, *, source_identity, evaluator_gates, reset_serving=None,
                 upstream_checkout=None, node_binary="node"):
        self.tasks, self.model, self.limits, self.factory = tasks, model, limits, factory
        self.source_identity, self.reset_serving = source_identity, reset_serving
        self.evaluator_gates = evaluator_gates
        self.upstream_checkout, self.node_binary = upstream_checkout, node_binary

    async def run(self, architecture, events, output, *, seed, horizon_s, subscriptions=True):
        events = list(events)
        task_ids = list(dict.fromkeys(e.task_id or e.id for e in events))
        if architecture not in (*ARCHITECTURES, "upstream_core_reference") or not events or any(e.kind != "request" for e in events):
            raise ValueError("Pro workload uses independent requests and one declared controlled architecture")
        if architecture == "upstream_core_reference" and self.upstream_checkout is None:
            raise ValueError("Original-core reference requires the pinned checkout and Node runtime")
        if len(task_ids) != len(events) or any(t not in self.tasks for t in task_ids):
            raise ValueError("Each Pro task must have one request and an available pinned task input")
        if not math.isfinite(horizon_s) or horizon_s <= 0 or any(e.arrival_s >= horizon_s for e in events):
            raise ValueError("All offered arrivals must lie inside a positive frozen horizon")
        for event in events:
            task_id = event.task_id or event.id
            gate = self.evaluator_gates.get(task_id, {})
            if event.text != self.tasks[task_id].instruction:
                raise ValueError("Benchmark request differs from the frozen public instruction")
            if (gate.get("task_files") != self.tasks[task_id].files or not gate.get("image_id") or
                gate.get("empty", {}).get("valid") is not True or gate["empty"].get("success") is not False or
                gate.get("reference", {}).get("valid") is not True or gate["reference"].get("success") is not True):
                raise ValueError("Pristine empty/reference gates are missing or differ from this task")
        output = Path(output)
        identity = {"architecture": architecture, "seed": seed, "subscriptions": subscriptions, "horizon_s": horizon_s,
                    "source": self.source_identity, "model": self.model.identity, "limits": self.limits.public(),
                    "worker_prompt_sha256": digest(WORKER_PROMPT), "tools_sha256": digest([EXECUTE]),
                    "events": [e.__dict__ for e in events], "tasks": {t: self.tasks[t].files for t in task_ids},
                    "evaluator_gates": {t: self.evaluator_gates[t] for t in task_ids}}
        identity_sha = digest(identity)
        if (output / "result.json").exists():
            previous = json.loads((output / "result.json").read_text(encoding='utf-8'))
            if previous["identity_sha256"] != identity_sha:
                raise ValueError("Completed run identity differs; choose a new output directory")
            if previous.get("status") != "completed":
                raise ValueError("Failed run preserved; select a new attempt directory")
            return previous
        output.mkdir(parents=True, exist_ok=False)
        (output / "identity.json").write_text(canonical(identity), encoding='utf-8')
        journal = Journal(output / "run.sqlite3", token_budget=self.limits.token_budget, identity=identity)
        workspaces, captures, probes = {}, {}, {}
        result = {"identity_sha256": identity_sha, "evidence_tier": "official-task-custom-backend", "official_protocol_valid": False}
        try:
            if self.reset_serving is not None:
                result["serving_reset"] = await self.reset_serving()
            for task_id in task_ids:
                workspace = self.factory(self.tasks[task_id], "agent", digest([identity_sha, task_id, "agent"])[:20])
                workspaces[task_id] = workspace
                if workspace.identity["image_id"] != self.evaluator_gates[task_id]["image_id"]:
                    raise ValueError("Agent image differs from the validated evaluator image")
                reference_workspace = self.evaluator_gates[task_id]["reference"]["workspace"]
                if any(workspace.identity.get(k) != reference_workspace.get(k) for k in ["backend", "cgroup_limits_enforced", "cpus", "memory_mb"]):
                    raise ValueError("CPU/RAM/backend contract differs from the reference gate; repeat environment validation")
                probes[task_id] = await self.tasks[task_id].prepare_agent(workspace)
                (output / digest(task_id)[:20]).mkdir()
            start = time.monotonic()
            journal.trace("campaign_clock_start")

            async def capture(task_id):
                patch = output / digest(task_id)[:20] / "model.patch"
                gate = getattr(workspaces[task_id], "artifact_validation", None)
                readiness = None
                if gate is not None:
                    journal.trace("artifact_validation_started", task_id=task_id)
                    readiness = await gate.validate_current()
                    journal.trace("artifact_validation_finished", task_id=task_id, report=readiness)
                    if not readiness["passed"]:
                        journal.task_state(task_id, "blocked", "Current artifact failed its declared public validation")
                receipt = await self.tasks[task_id].capture_patch(workspaces[task_id], patch)
                if readiness is not None:
                    receipt["public_readiness"] = readiness
                captures[task_id] = {"submitted_s": time.monotonic() - start, "patch": str(patch), **receipt}
                if hasattr(workspaces[task_id], "resource_usage"):
                    captures[task_id]["container_resource_usage"] = await workspaces[task_id].resource_usage()
                journal.trace("patch_submitted", task_id=task_id, **captures[task_id])

            try:
                kernel = Kernel(self.model, journal, self.limits)
                async def execute():
                    if architecture == "upstream_core_reference":
                        client = await CoreClient(self.upstream_checkout, output / "upstream-state.json", node=self.node_binary).start()
                        journal.trace("upstream_identity", commit=PINS["deepseek"]["commit"], scope="original core with replacement benchmark ports; DSH host differs")
                        try:
                            return await UpstreamRuntime(client, kernel, on_task_update=capture).run(events, workspaces)
                        finally:
                            await client.close()
                    return await Runtime(architecture, kernel, subscriptions=subscriptions, on_task_update=capture).run(events, workspaces)
                claims = await asyncio.wait_for(execute(), horizon_s)
                result["deadline_hit"] = False
            except TimeoutError:
                result["deadline_hit"] = True
                journal.trace("workload_deadline", horizon_s=horizon_s)
                # An already-issued command is bounded inside its container. Preserve its final
                # artifact after that grace, but grant no pre-cutoff credit for late submission.
                await asyncio.sleep(self.limits.tool_timeout_s + 6)
                claims = journal.tasks()
            for task_id in task_ids:
                if task_id not in captures:
                    await capture(task_id)
            result.update(agent_wall_s=time.monotonic() - start, completion_claims=claims, captures=captures, probes=probes)
            # The agent phase ends before any official test files enter new verifier containers.
            for workspace in workspaces.values():
                workspace.stop()
            workspaces = {}
            rows = []
            for event in events:
                task_id = event.task_id or event.id
                task = self.tasks[task_id]
                factory = lambda task=task, task_id=task_id: self.factory(task, "verifier", digest([identity_sha, task_id, "grade"])[:20])
                grade = await task.grade(factory, captures[task_id]["patch"], output / digest(task_id)[:20] / "pristine-grade")
                rows.append({"task_id": task_id, "seed": seed, "arrival_s": event.arrival_s,
                             "submitted_s": captures[task_id]["submitted_s"], "success": grade["success"], "valid": grade["valid"],
                             "grade_source_sha256": grade.get("grade_source_sha256"), "official_protocol_valid": False,
                             "architecture": architecture, "grade": grade})
            result.update(rows=rows, usage=journal.usage(), status="completed", horizon_s=horizon_s)
        except Exception as error:
            result.update(status="failed", error=type(error).__name__ + ": " + str(error), usage=journal.usage())
            raise
        finally:
            for workspace in workspaces.values():
                workspace.stop()
            journal.export(output)
            (output / "result.json").write_text(canonical(result), encoding="utf-8")
        return result
