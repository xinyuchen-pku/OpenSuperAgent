"""Live, hash-bound admission. Fails before model spend on missing environment.

Image derivation and workload-guard receipts come from the trusted host, outside
agent workspaces. This command validates their identities; it does not start GPU
jobs, edit platform allocations, or silently manufacture missing receipts.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path

from osa_eval.kernel import function_tool
from osa_eval.model import ChatModel

from .budget import BudgetLedger
from .manifest import read, file_hash, verify_lock, verify_installed_suite, write
from .native_workspace import PR_HARD_CPU_LIMIT


def environment(site):
    for name, value in site.get('environment', {}).items():
        if any(k in name.upper() for k in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'CREDENTIAL')):
            raise ValueError('Credentials belong in the secure existing environment')
        os.environ[name] = value


def pid_identity(record):
    pid = record['pid']
    if type(pid) is not int or pid <= 1:
        raise ValueError('Guard PID invalid')
    stat = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    if stat != str(record['start_ticks']):
        raise ValueError('Resource guard identity changed')
    import hashlib
    if hashlib.sha256(Path(f'/proc/{pid}/cmdline').read_bytes()).hexdigest() != record['argv_sha256']:
        raise ValueError('Resource guard command identity changed')


def campaign_identity(args, site, source):
    return dict(manifest_sha256=file_hash(args.manifest), benchmark=args.benchmark,
                suite_lock_sha256=file_hash(args.lock), site_sha256=file_hash(args.site),
                campaign_id=site['campaign_id'], worker_tree=source['tree_sha256'])


def admit(args, manifest, cfg, tasks, source):
    if cfg['readiness'] != 'implementation_ready':
        raise ValueError('Implementation readiness gate has not passed')
    site = read(args.site)
    environment(site)
    lock = verify_lock(Path(args.manifest).resolve().parent.parent, args.lock)
    verify_installed_suite(lock)
    if str(Path(args.output).resolve()) != str(Path(site['admission_file']).resolve()):
        raise ValueError('Admission output differs from frozen site path')
    if Path(args.output).exists():
        raise FileExistsError('Preserve prior admission; use a new versioned site')
    identity = campaign_identity(args, site, source)
    prefix = site['docker_prefix']
    info = json.loads(subprocess.check_output([*prefix, 'info', '--format', '{{json .}}'], text=True, timeout=30))
    if info['NCPU'] < 4 or info['MemTotal'] < 15 * 1024**3 or info.get('CgroupVersion') != '2':
        raise ValueError('Four CPU / 16GiB VM with cgroup v2 required; account for guest kernel memory')
    if (args.benchmark == 'asyncodebench_native' and info['NCPU'] < PR_HARD_CPU_LIMIT
            and any(t['task_id'].startswith('asyncodebench:apache-tvm-') for t in tasks['tasks'])):
        raise ValueError('Native PR-hard tasks require Docker with the original 28-CPU quota')
    guard = read(site['resource_guard_receipt'])
    pid_identity(guard['process'])
    if (guard['campaign_id'] != site['campaign_id'] or guard['gpu_count'] != 4 or
        guard['restores_original_holders'] is not True or
        guard['maximum_service_gpu_hours'] > cfg['maximum_service_gpu_hours'] or
        guard['remaining_service_gpu_hours'] <= 0):
        raise ValueError('Active guard does not cover this campaign compute/restoration contract')
    serving = guard['serving']
    if any(serving.get(k) != manifest['model'][k] for k in
           ['revision', 'precision', 'tensor_parallel', 'maximum_context', 'max_sequences', 'prefix_cache']):
        raise ValueError('Guard serving identity differs from frozen model configuration')
    if serving.get('weights_verified') is not True or serving.get('provider_contract_verified') is not True:
        raise ValueError('Actual weight hashes and provider parser contract require verification')
    image_receipts = []
    if args.benchmark == 'asyncodebench_native':
        root = Path(site['native_runner_root']).parent.parent
        head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
        if head != tasks['source_commit'] or subprocess.run(['git', '-C', str(root), 'diff', '--quiet', 'HEAD', '--']).returncode:
            raise ValueError('Native checkout differs from frozen official source')
        check = ('import sys,json; from osa_suite.manifest import verify_installed_suite; '
                 'from osa_suite.cli import worker_identity; '
                 'assert sys.version_info[:2] == (3,12); '
                 'verify_installed_suite(json.load(open(sys.argv[1]))); worker_identity(sys.argv[2])')
        subprocess.run([str(Path(site['native_executable']).parent / 'python'), '-c', check,
                        str(Path(args.lock).resolve()), site['research_root']],
                       cwd=site['native_runner_root'], check=True, timeout=30)
        for task in tasks['tasks']:
            tid = task['task_id']
            for item in task['artifacts'].values():
                p = (root / item['path']).resolve()
                if not p.is_relative_to(root.resolve()) or file_hash(p) != item['sha256']:
                    raise ValueError('Official task/scenario artifact mismatch: ' + tid)
            proof = read(site['native_image_receipts'][tid])
            if (proof.get('passed') is not True or proof['task_id'] != tid or
                proof['official_base_digest'] != task['image']['digest'] or
                proof['base_image_config_digest'] != task['image']['linux_amd64_config_digest'] or
                proof['sdk_commit'] != '944284310d9a5f1ccad0ef8c2d7c4c38342b9952' or
                proof['derived_image_id'] != site['native_image_ids'][tid]):
                raise ValueError('Missing official-base/SDK image derivation proof: ' + tid)
            observed = json.loads(subprocess.check_output([*prefix, 'image', 'inspect', proof['derived_image_id']], text=True, timeout=30))[0]
            if observed['Id'] != proof['derived_image_id']:
                raise ValueError('Native SDK image identity changed')
            image_receipts.append(dict(task_id=tid, image_id=observed['Id'], proof_sha256=file_hash(site['native_image_receipts'][tid])))
    else:
        gates = read(site['pro_gates'])
        if not all(gates.get(t['task_id'], {}).get('passed') is True for t in tasks['tasks']):
            raise ValueError('Every Pro task requires complete reference/empty environment gates')
    ledger = BudgetLedger(site['campaign_ledger'], campaign_limit=cfg['maximum_api_tokens'] + cfg['admission_token_allowance'],
                          task_limit=cfg['task_tokens'], identity=identity)
    if not ledger.summary()['accounting_valid']:
        raise RuntimeError('Existing campaign has unresolved usage')
    rates = manifest['model']['transport']
    calls = []

    async def controls():
        for maximum in (16, 256):
            model = ChatModel(api_key=os.environ[site.get('api_key_env', 'LLM_API_KEY')],
                  **dict(rates, base_url=site['model_base_url'], model=manifest['model']['served_name'],
                         seed=cfg['seeds'][0], max_output_tokens=maximum))
            model.parameters.update(manifest['model']['extra_sampling'])
            messages = [{'role': 'user', 'content': 'Call contract_probe with value="ready". Do not write prose.'}]
            tools = [function_tool('contract_probe', 'Provider tool-call contract probe.', {'value': {'type': 'string'}})]
            context = await model.prepare(messages, tools)
            if context['max_model_len'] != manifest['model']['maximum_context']:
                raise ValueError('Serving context differs from frozen model')
            key = ledger.reserve('__provider_admission__', 'admission', str(maximum), context['reservation_tokens'])
            try:
                reply = await model.complete(messages, tools, role='admission')
                ledger.finish(key, reply.usage)
            except BaseException:
                ledger.uncertain(key)
                raise
            calls.append(dict(max_output=maximum, context=context, usage=reply.usage.__dict__,
                              finish_reason=reply.finish_reason, message=reply.message))
            if sum(r['usage']['input_tokens'] + r['usage']['output_tokens'] for r in calls) > cfg['admission_token_allowance']:
                raise ValueError('Provider admission spending exceeded its separate allowance')
            if maximum == 256 and (reply.finish_reason != 'tool_calls' or not reply.message.get('tool_calls')):
                raise ValueError('Provider did not produce valid tool calls')
    try:
        asyncio.run(controls())
    except BaseException:
        write(Path(args.output).with_suffix('.failed.json'), dict(passed=False, identity=identity,
              completed_control_calls=calls, budget=ledger.summary()))
        raise
    proof = dict(passed=True, benchmark=args.benchmark, created_unix=time.time(),
                 suite_lock_sha256=file_hash(args.lock), manifest_sha256=file_hash(args.manifest),
                 site_sha256=file_hash(args.site), source025_tree_sha256=source['tree_sha256'],
                 identity=identity, docker_host_id=info['ID'], native_images=image_receipts,
                 guard_receipt_sha256=file_hash(site['resource_guard_receipt']),
                 provider_controls=calls, accounting=ledger.summary())
    write(args.output, proof)
