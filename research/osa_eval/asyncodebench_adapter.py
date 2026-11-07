"""Native assignment adapter. This intentionally preserves the benchmark's own protocols."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from agents import AgentAdapter, AgentRunResponse  # Supplied by the pinned AsynCodeBench runner.

from .contracts import Limits, digest
from .journal import Journal
from .kernel import Kernel, WORKER_PROMPT
from .model import ChatModel
from .workspace import AsynWorkspace
from .scoped_workspace import ScopedAsynWorkspace


class SharedWorkerAdapter(AgentAdapter):
    name = "osa-shared-worker"

    def execute(self, request):
        config = self.config
        if config.get("architecture") not in (None, "native"):
            raise ValueError("The native assignment adapter cannot replace benchmark orchestration")
        identity = {"task": request.benchmark_task_id, "protocol": request.protocol,
                    "assignment": request.assignment_id, "round": request.round_num,
                    "model": request.model, "worker_prompt_sha256": digest(WORKER_PROMPT),
                    "request_sha256": digest(request.public_metadata()),
                    "worker_policy_sha256": digest(config.get("worker_policy", {}))}
        if config.get("input_usd_per_million") is None or config.get("output_usd_per_million") is None:
            raise ValueError("Native harness needs numeric cost: configure an explicit pricing convention before running")
        model = ChatModel(os.environ["LLM_BASE_URL"], os.environ["LLM_API_KEY"], config.get("provider_model", request.model),
                          temperature=config.get("temperature", 0), max_output_tokens=config.get("max_output_tokens", 4096),
                          input_usd_per_million=config["input_usd_per_million"], output_usd_per_million=config["output_usd_per_million"],
                          seed=config.get("seed"), timeout_s=config.get("timeout_s", 300),
                          allow_private_http=config.get("allow_private_http", False),
                          tokenizer_preflight=config.get("tokenizer_preflight", False), context_policy=config.get("context_policy", "stop"))
        limits = Limits(slots=1, model_concurrency=1, max_steps=request.max_iterations,
                        token_budget=config.get("token_budget", 2_000_000),
                        request_token_reservation=config.get("request_token_reservation", 131_072),
                        reservation_policy=config.get("reservation_policy", "context_window"))
        # The benchmark creates separate output directories; include assignment identity for thread-safe journals.
        journal = Journal(Path(request.output_dir) / ("osa-" + digest(identity)[:20] + ".sqlite3"), token_budget=limits.token_budget,
                          identity={**identity, "provider": model.identity, "limits": limits.public()})
        workspace = AsynWorkspace(request.workspace, request.workspace_path, {"backend": "asyncodebench", "workspace_path": request.workspace_path})
        scope = config.get("worker_policy", {}).get("native_scope")
        if scope:
            workspace = ScopedAsynWorkspace(workspace, container_id=request.workspace._container_id,
                allowed_paths=request.writable_paths, docker_prefix=scope["docker_prefix"],
                output=Path(request.output_dir)/"scope-runtime"/request.assignment_id,
                assignment=request.assignment_id, expected_image=scope["expected_image"])
        error = None
        termination = "adapter_completed"
        async def run():
            nonlocal error, termination
            prepared = False
            try:
                if scope:
                    await workspace.prepare()
                    prepared = True
                    journal.trace("native_scope_runtime", task_id=request.assignment_id,
                                  identity=workspace.identity, tools_sha256=digest(workspace.model_tools))
                instruction = request.instruction
                if not scope:
                    instruction += "\nArtifact requirement: create a local git commit of the intended changes inside this disposable assigned worktree. The native harness reads that commit. Do not push."
                try:
                    await Kernel(model, journal, limits).work(request.assignment_id, instruction, workspace)
                except Exception as failure:
                    error = type(failure).__name__ + ": " + str(failure)
                    termination = "budget_exhausted" if type(failure).__name__ == "BudgetExhausted" else "worker_error"
                if scope and journal.usage()["accounting_valid"]:
                    handoff = await workspace.finalize()
                    journal.trace("native_scope_handoff", task_id=request.assignment_id, result=handoff)
                    if handoff["returncode"]:
                        error = error or "ArtifactHandoffError: " + handoff["stdout"]
            finally:
                if scope and prepared:
                    await workspace.close()
        try:
            asyncio.run(run())
        except Exception as failure:
            error = type(failure).__name__ + ": " + str(failure)
            termination = "scope_runtime_error"
        telemetry = journal.usage()
        journal.export(Path(request.output_dir) / ("osa-" + digest(identity)[:20]))
        # The upstream response uses a numeric cost field; unknown cost is explicit in metadata.
        return AgentRunResponse(error=error, prompt_tokens=telemetry["input_tokens"], completion_tokens=telemetry["output_tokens"],
            iterations=len(telemetry["calls"]), cost=telemetry["cost_usd"] or 0.0,
            metadata={"cost_known": telemetry["cost_usd"] is not None, "accounting_valid": telemetry["accounting_valid"],
                      "scope": "native assignment worker; coordination remains benchmark-controlled", "identity": identity,
                      "termination_reason": termination, "scope_enforced": bool(scope)})
