"""Stage 2 Pro campaign. Task preparation, patch capture and scoring reuse pins.

The official Harbor replay is a required second grade. Its helper is the
published, unchanged reproduction module, loaded from the supplied package tree.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

from osa_eval.benchmarks import verify_checkout
from osa_eval.contracts import Event, Limits, digest
from osa_eval.model import ChatModel
from osa_eval.swebench_pro import ProTask
from osa_eval.workspace import DockerWorkspace

from .budget import BudgetLedger, SharedBudgetJournal, CURRENT_TASK
from .manifest import read, write
from .runtime import ArchitectureRuntime, RoutingChargedKernel


async def run_batch(*, task_ids, arm, seed, output, model_config, cfg, site, ledger, source_manifest):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    checkout = Path(site['pro_checkout'])
    verify_checkout(checkout, 'swebench_pro')
    gates = read(site['pro_gates'])
    tasks = {tid: ProTask(checkout / 'v2/tasks' / tid) for tid in task_ids}
    for tid, task in tasks.items():
        gate = gates.get(tid, {})
        if (gate.get('task_files') != task.files or gate.get('empty', {}).get('valid') is not True or
            gate['empty'].get('success') is not False or gate.get('reference', {}).get('valid') is not True or
            gate['reference'].get('success') is not True or not gate.get('image_id')):
            raise ValueError('Task lacks pristine, identity-matching reference/empty gates: ' + tid)
        if task.config['agent']['timeout_sec'] != cfg['task_timeout_s']:
            raise ValueError('Agent active limit must retain the official task timeout')
    limits = Limits(slots=cfg['slots'], model_concurrency=cfg['model_concurrency'],
                    max_steps=100, token_budget=cfg['task_tokens'] * len(tasks),
                    task_timeout_s=cfg['task_timeout_s'], tool_timeout_s=120,
                    request_token_reservation=262144, reservation_policy='exact_prompt_plus_max_output')
    model = ChatModel(api_key=os.environ[site.get('api_key_env', 'LLM_API_KEY')], **model_config)
    model.parameters.update(site['extra_sampling'])
    identity = dict(architecture=arm, seed=seed, source=dict(frozen_manifest=source_manifest),
                    controller='stage2-task-level-v1', model=model.identity, limits=limits.public(),
                    task_order=task_ids, task_budget=cfg['task_tokens'])
    write(output / 'identity.json', identity)
    journal = SharedBudgetJournal(output / 'run.sqlite3', token_budget=limits.token_budget,
                  identity=identity, ledger=ledger,
                  task_key=lambda: '|'.join([CURRENT_TASK.get() or '', arm, str(seed)]))
    kernel = RoutingChargedKernel(model, journal, limits)
    workspaces, captures, results = {}, {}, []
    started = time.monotonic()

    def factory(tid, purpose):
        index = task_ids.index(tid)
        prefix = site['docker_command_prefix_by_cpu'][str(index)]
        return DockerWorkspace.create(image=gates[tid]['image_id'],
            name='osa-s2-' + digest([str(output), tid, purpose])[:20], purpose=purpose,
            cpus=1, memory_mb=4096, command_prefix=prefix)

    async def capture(tid):
        folder = output / digest(tid)[:20]
        folder.mkdir(exist_ok=True)
        receipt = await tasks[tid].capture_patch(workspaces[tid], folder / 'model.patch')
        captures[tid] = dict(submitted_s=time.monotonic() - clock_start, **receipt)
        journal.trace('patch_submitted', task_id=tid, **captures[tid])

    result = dict(status='failed', rows=[], official_protocol_valid=False)
    try:
        for tid in tasks:
            workspaces[tid] = factory(tid, 'agent')
            if workspaces[tid].identity['image_id'] != gates[tid]['image_id'] or any(workspaces[tid].identity.get(k) != gates[tid]['reference']['workspace'].get(k)
                   for k in ['backend', 'cgroup_limits_enforced', 'cpus', 'memory_mb']):
                raise ValueError('Actual resource contract differs from admitted reference')
            await tasks[tid].prepare_agent(workspaces[tid])
        clock_start = time.monotonic()
        events = [Event(tid, tid, task.instruction, task_id=tid) for tid, task in tasks.items()]
        runtime = ArchitectureRuntime(arm, kernel, on_task_update=capture)
        await asyncio.wait_for(runtime.run(events, workspaces), cfg['batch_horizon_s'])
        for tid in tasks:
            if tid not in captures:
                await capture(tid)
        agent_wall = time.monotonic() - clock_start
        receipt_drain_started = time.monotonic()
        await kernel.settle_model_receipts()
        result['model_receipt_drain_wall_s'] = time.monotonic() - receipt_drain_started
        if not journal.usage()['accounting_valid'] or not ledger.summary()['accounting_valid']:
            raise RuntimeError('Unknown provider usage; preserve artifacts and stop campaign')
        for workspace in workspaces.values():
            workspace.stop()
        workspaces.clear()
        for tid, task in tasks.items():
            grade = await task.grade(lambda tid=tid: factory(tid, 'verifier'),
                    output / digest(tid)[:20] / 'model.patch', output / digest(tid)[:20] / 'pristine-grade')
            results.append(dict(task_id=tid, seed=seed, architecture=arm, success=grade['success'],
                                valid=grade['valid'], grade=grade, submitted_s=captures[tid]['submitted_s']))
        result.update(status='completed', rows=results, captures=captures, agent_wall_s=agent_wall,
                      environment_and_scoring_wall_s=time.monotonic() - started - agent_wall,
                      usage=journal.usage())
        # Preserve the independent result before the second official scorer reads it.
        write(output / 'result.json', result)
        helpers = str(Path(site['research_root']) / 'reproduction')
        sys.path.insert(0, helpers)
        try:
            from official_regrade import configure, replay
            configure(checkout, site['harbor'], site['docker_prefix'])
            official = []
            for cpu, tid in enumerate(task_ids):
                official.append(await asyncio.to_thread(replay, tid, output,
                                output / 'official-harbor' / digest(tid)[:20], cpu))
        finally:
            sys.path.remove(helpers)
        result['official_replays'] = official
        # replay itself checks raw outputs and validity; retain those receipts.
        result['official_protocol_valid'] = all(r.get('official_protocol_valid') is True for r in official)
        if not result['official_protocol_valid']:
            raise RuntimeError('Original Harbor replay protocol invalid')
        return result
    except BaseException as exc:
        result.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
        raise
    finally:
        await kernel.settle_model_receipts()
        for workspace in workspaces.values():
            workspace.stop()
        result['usage'] = journal.usage()
        journal.export(output)
        write(output / 'result.json', result)
