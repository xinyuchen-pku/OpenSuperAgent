"""Official AsynCodeBench assignment hook, NOT an orchestration replacement.

Reuses source025 Kernel, model, and exact-path workspace. Adds full-task and
campaign admission across assignment threads/processes. Manager protocols are
refused until their upstream LLM traffic shares the same admission ledger.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from agents import AgentAdapter, AgentRunResponse
from osa_eval.contracts import Limits, digest
from osa_eval.kernel import Kernel, WORKER_PROMPT
from osa_eval.model import ChatModel
from osa_eval.workspace import AsynWorkspace

from .budget import BudgetLedger, SharedBudgetJournal
from .environment import prepare_native_identity
from .native_workspace import PrivateReadWorkspace


class NativeWorker(AgentAdapter):
    name = 'osa-source025-shared-task-budget'

    def execute(self, request):
        config = self.config
        if request.protocol not in {'async_private', 'serial_specialists'}:
            raise ValueError('This adapter admits scoped specialists only; manager calls need aggregate admission first')
        if config['architecture'] != 'native':
            raise ValueError('Official assignment API preserves harness orchestration')
        proof = prepare_native_identity(request)
        budget = config['budget']
        ledger = BudgetLedger(budget['path'], campaign_limit=budget['campaign_tokens'],
                              task_limit=budget['task_tokens'], identity=budget['identity'])
        task = '|'.join([request.benchmark_task_id, request.protocol, str(config['seed'])])
        identity = dict(request=request.public_metadata(), worker_prompt_sha256=digest(WORKER_PROMPT),
                        model=config['model'], limits=config['limits'], worker_policy=config['worker_policy'],
                        budget_identity=budget['identity'], seed=config['seed'])
        run_id = digest(identity)[:24]
        output = Path(request.output_dir) / ('osa-suite-' + run_id)
        limits = Limits(**config['limits'])
        if limits.max_steps != request.max_iterations or limits.token_budget != budget['task_tokens']:
            raise ValueError('Common limits must retain official per-assignment iterations and full-task ceiling')
        model = ChatModel(api_key=os.environ[config.get('api_key_env', 'LLM_API_KEY')], **config['model'])
        model.parameters.update(config['extra_sampling'])
        journal = SharedBudgetJournal(output / 'run.sqlite3', token_budget=limits.token_budget,
                                      identity=identity, ledger=ledger, task_key=task)
        inner = AsynWorkspace(request.workspace, request.workspace_path,
                              dict(backend='asyncodebench', workspace_path=request.workspace_path))
        scope = config['worker_policy']['native_scope']
        workspace = PrivateReadWorkspace(inner, container_id=request.workspace._container_id,
                    allowed_paths=request.writable_paths, docker_prefix=scope['docker_prefix'],
                    output=output / 'scope', assignment=request.assignment_id, expected_image=scope['expected_image'])
        error, termination = None, 'completed_claim'

        async def run():
            nonlocal error, termination
            try:
                await workspace.prepare()
                journal.trace('native_scope_runtime', identity=workspace.identity,
                              tools_sha256=digest(workspace.model_tools))
                try:
                    await Kernel(model, journal, limits).work(request.assignment_id, request.instruction,
                          workspace, execution_timeout_s=limits.task_timeout_s)
                except Exception as exc:
                    error = type(exc).__name__ + ': ' + str(exc)
                    termination = 'budget_exhausted' if type(exc).__name__ == 'BudgetExhausted' else 'worker_error'
                if journal.usage()['accounting_valid']:
                    handoff = await workspace.finalize()
                    journal.trace('native_scope_handoff', result=handoff)
                    if handoff['returncode']:
                        error = error or 'ArtifactHandoffError: ' + handoff['stdout']
                        termination = 'artifact_handoff_failed'
            finally:
                if workspace.container is not None:
                    await workspace.close()
        try:
            asyncio.run(run())
        except Exception as exc:
            error, termination = type(exc).__name__ + ': ' + str(exc), 'environment_error'
        finally:
            journal.export(output)
        usage = journal.usage()
        return AgentRunResponse(error=error, prompt_tokens=usage['input_tokens'],
                    completion_tokens=usage['output_tokens'], iterations=len(usage['calls']),
                    cost=usage['cost_usd'] or 0.0,
                    metadata=dict(termination_reason=termination, cost_known=usage['cost_usd'] is not None,
                                  accounting_valid=usage['accounting_valid'], task_key=task,
                                  full_task_budget=True, scope_enforced=True,
                                  private_read_enforced=workspace.identity.get('private_read_preflight', False),
                                  native_environment_preflight=proof,
                                  scope='native assignment only; official harness owns coordination'))
