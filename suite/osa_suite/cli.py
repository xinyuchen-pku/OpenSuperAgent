"""One manifest-driven entry point. Plan is free; run requires admitted evidence."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import time
from pathlib import Path

from .budget import BudgetLedger
from .manifest import read, write, file_hash, load_experiment, schedule, verify_lock, verify_installed_suite, freeze
from .admission import environment, campaign_identity, pid_identity


def worker_identity(research_root):
    root = Path(research_root)
    manifest = read(root / 'SOURCE_MANIFEST.json')
    import osa_eval
    installed = Path(osa_eval.__file__).parent
    for name, expected in manifest['files'].items():
        if name.startswith('osa_eval/') and file_hash(installed / name.removeprefix('osa_eval/')) != expected:
            raise ValueError('Installed Worker differs from source025: ' + name)
        if file_hash(root / name) != expected:
            raise ValueError('Delivered source025 file differs: ' + name)
    from osa_eval.contracts import digest
    if (digest(manifest['files']) != manifest['tree_sha256'] or
        manifest['tree_sha256'] != '5594a771aca46709ae4837aecc2b477dec15138510167842c8083f9bf484112f'):
        raise ValueError('Wrong Worker version')
    return manifest


def prepare(args):
    manifest, cfg, tasks = load_experiment(args.manifest, args.benchmark)
    if args.model != manifest['model']['id']:
        raise ValueError('Model differs from frozen selection')
    if args.agent and args.agent not in cfg['agents']:
        raise ValueError('Agent is outside this experiment track')
    ids = [t['task_id'] for t in tasks['tasks']]
    jobs = schedule(ids, cfg['agents'], cfg['seeds'], order_seed=manifest['order_seed'],
                    batch_size=cfg['slots'] if cfg['track'] == 'controlled_architecture' else len(ids))
    # Selecting one arm is a shard of the frozen plan. Never regenerate arm order.
    if args.agent:
        jobs = [j for j in jobs if j['agent'] == args.agent]
    return manifest, cfg, tasks, dict(schema='osa-plan-v1', benchmark=args.benchmark,
            model=args.model, manifest_sha256=file_hash(args.manifest), task_count=len(ids),
            stage_maximum_api_tokens=cfg['maximum_api_tokens'],
            selected_maximum_api_tokens=cfg['task_tokens'] * sum(len(j['tasks']) for j in jobs),
            jobs=jobs, actual_model_calls=0, status='planned', readiness=cfg['readiness'])


def native_config(manifest, cfg, site, task, seed, ledger_path, identity):
    model = dict(manifest['model']['transport'], base_url=site['model_base_url'], seed=seed)
    model['model'] = manifest['model']['served_name']
    return dict(architecture='native', seed=seed, api_key_env=site.get('api_key_env', 'LLM_API_KEY'), model=model,
        extra_sampling=manifest['model']['extra_sampling'],
        limits=dict(slots=1, model_concurrency=1, max_steps=100, token_budget=cfg['task_tokens'],
                    request_token_reservation=262144, reservation_policy='exact_prompt_plus_max_output',
                    tool_timeout_s=120, task_timeout_s=cfg['task_timeout_s']),
        budget=dict(path=str(ledger_path), campaign_tokens=cfg['maximum_api_tokens'] + cfg['admission_token_allowance'],
                    task_tokens=cfg['task_tokens'], identity=identity),
        worker_policy=dict(native_scope=dict(docker_prefix=site['docker_prefix'],
                    expected_image=site['native_image_ids'][task])))


def run(args):
    manifest, cfg, tasks, plan = prepare(args)
    root = Path(args.manifest).resolve().parent.parent
    verify_installed_suite(verify_lock(root, args.lock))
    if cfg['readiness'] != 'implementation_ready':
        raise ValueError('Experiment has unmet implementation dependencies: ' + cfg['readiness'])
    site = read(args.site)
    environment(site)
    source = worker_identity(site['research_root'])
    # Admission file is separately content-bound to config, model service,
    # resource probes and official runner. It contains no provider credentials.
    gate = read(site['admission_file'])
    if (gate.get('passed') is not True or gate.get('benchmark') != args.benchmark or
        gate.get('suite_lock_sha256') != file_hash(args.lock) or
        gate.get('manifest_sha256') != file_hash(args.manifest) or
        gate.get('site_sha256') != file_hash(args.site) or
        gate.get('source025_tree_sha256') != source['tree_sha256']):
        raise ValueError('Campaign requires identity-matching live admission receipt')
    guard = read(site['resource_guard_receipt'])
    pid_identity(guard['process'])
    if gate['guard_receipt_sha256'] != file_hash(site['resource_guard_receipt']):
        raise ValueError('Active guard receipt differs from admitted identity')
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    identity = campaign_identity(args, site, source)
    write(output / 'plan.json', plan)
    write(output / 'identity.json', dict(identity, attempt=str(output)))
    # Shared across shards, processes AND retry attempts. Never place this
    # ledger under a disposable attempt directory or silently reset its identity.
    ledger_path = Path(site['campaign_ledger']).resolve()
    ledger = BudgetLedger(ledger_path, campaign_limit=cfg['maximum_api_tokens'] + cfg['admission_token_allowance'],
                          task_limit=cfg['task_tokens'], identity=identity)
    if not ledger.summary()['accounting_valid']:
        raise RuntimeError('Existing campaign has outstanding/unknown receipts; preserve and reconcile')
    env = dict(os.environ)
    for name, value in site.get('environment', {}).items():
        if any(k in name.upper() for k in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'CREDENTIAL')):
            raise ValueError('Use existing secure environment for credentials, never a site manifest')
        env[name] = value
    start = time.monotonic()
    state = dict(status='running', completed=[], started_unix=time.time(), benchmark=args.benchmark)
    write(output / 'status.json', state)
    try:
        for job in plan['jobs']:
            if args.benchmark.startswith('asyncodebench'):
                if cfg['protocol'] != 'async_private':
                    raise ValueError('Only scoped async_private native campaign is admitted in this version')
                for task in job['tasks']:
                    if time.monotonic() - start > cfg['maximum_wall_s']:
                        raise TimeoutError('Campaign compute ceiling; preserve attempt')
                    name = task.split(':', 1)[1] + '-' + str(job['seed'])
                    dest = output / name
                    state['active'] = dict(agent='native', seed=job['seed'], tasks=[task])
                    write(output / 'status.json', state)
                    case_started = time.monotonic()
                    adapter = native_config(manifest, cfg, site, task, job['seed'], ledger_path, identity)
                    command = [site['native_executable'], 'run', '--task', task, '--protocol', cfg['protocol'],
                        '--model', 'openai/' + manifest['model']['served_name'], '--max-iterations', '100',
                        '--sub-iterations', '100', '--rounds-of-chat', '2', '--output-dir', str(dest),
                        '--run-id', name, '--agent-import-path', 'osa_suite.native:NativeWorker',
                        '--agent-config-json', json.dumps(adapter, separators=(',', ':'))]
                    write(output / (name + '-command.json'), command)
                    with (output / (name + '.log')).open('wb') as log:
                        # No forced timeout here: the dedicated workload guard owns
                        # PID/start-time verification, model shutdown and GPU restore.
                        process = subprocess.Popen(command, env=env, cwd=site['native_runner_root'],
                                                   stdout=log, stderr=subprocess.STDOUT)
                        write(output / (name + '-process.json'), dict(pid=process.pid, argv=command,
                              start_ticks=Path(f'/proc/{process.pid}/stat').read_text().rsplit(')', 1)[1].split()[19]))
                        code = process.wait()
                    usage = ledger.summary()
                    write(output / 'budget.json', usage)
                    if code or not usage['accounting_valid']:
                        raise RuntimeError('Native command or API accounting invalid; preserve all artifacts')
                    bundles = list(dest.rglob('run_bundle.json'))
                    if len(bundles) != 1:
                        raise RuntimeError('Expected exactly one official run bundle')
                    with (output / (name + '-validate.log')).open('wb') as log:
                        validation = subprocess.run([site['native_executable'], 'validate-run', str(bundles[0].parent)],
                              env=env, cwd=site['native_runner_root'], stdout=log, stderr=subprocess.STDOUT)
                    if validation.returncode:
                        raise RuntimeError('Official run bundle validation failed')
                    state['completed'].append(dict(task_id=task, seed=job['seed'], protocol=cfg['protocol'],
                         bundle=str(bundles[0]), official_bundle_valid=True,
                         independent_regrade_valid=None, architecture_comparison=False,
                         completion_s=time.monotonic() - case_started))
                    state.pop('active', None)
                    write(output / 'status.json', state)
            elif args.benchmark in {'swebench_pro_v2_precheck', 'swebench_pro_v2'}:
                from .pro import run_batch
                model = dict(manifest['model']['transport'], base_url=site['model_base_url'],
                             model=manifest['model']['served_name'], seed=job['seed'])
                pro_site = dict(site, extra_sampling=manifest['model']['extra_sampling'])
                for index in range(0, len(job['tasks']), cfg['slots']):
                    if time.monotonic() - start > cfg['maximum_wall_s']:
                        raise TimeoutError('Campaign compute ceiling; preserve attempt')
                    chosen = job['tasks'][index:index + cfg['slots']]
                    state['active'] = dict(agent=job['agent'], seed=job['seed'], tasks=chosen)
                    write(output / 'status.json', state)
                    batch = output / f"{job['seed']}-block{job['block']:03d}-{job['agent']}-{index:03d}"
                    result = asyncio.run(run_batch(task_ids=chosen, arm=job['agent'], seed=job['seed'],
                        output=batch, model_config=model,
                        cfg=cfg, site=pro_site, ledger=ledger, source_manifest=source))
                    state['completed'].append(dict(agent=job['agent'], seed=job['seed'], tasks=chosen,
                         successes=sum(r['success'] for r in result['official_replays']), official_protocol_valid=result['official_protocol_valid'],
                         result=str(batch / 'result.json')))
                    state.pop('active', None)
                    write(output / 'status.json', state)
            else:
                raise ValueError('Benchmark adapter is not admitted')
        state['status'] = 'completed'
    except BaseException as exc:
        state.update(status='stopped', error=type(exc).__name__ + ': ' + str(exc))
        raise
    finally:
        state.update(elapsed_s=time.monotonic() - start, ended_unix=time.time())
        write(output / 'status.json', state)
        write(output / 'budget.json', ledger.summary())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('plan', 'run', 'admit'):
        p = sub.add_parser(name)
        for key in ('benchmark', 'model', 'manifest', 'output'):
            p.add_argument('--' + key, required=True)
        p.add_argument('--agent')
        if name in {'run', 'admit'}:
            for key in ('site', 'lock'):
                p.add_argument('--' + key, required=True)
    p = sub.add_parser('freeze')
    p.add_argument('--root', required=True)
    p.add_argument('--output', required=True)
    p = sub.add_parser('report')
    p.add_argument('--results', required=True, help='Normalized JSON list; see result-schema.json')
    p.add_argument('--output', required=True)
    p.add_argument('--compare', nargs=2)
    p = sub.add_parser('collect')
    for key in ('manifest', 'run', 'output'):
        p.add_argument('--' + key, required=True)
    args = parser.parse_args(argv)
    if args.command == 'plan':
        _, _, _, plan = prepare(args)
        write(args.output, plan)
        print(json.dumps({k: v for k, v in plan.items() if k != 'jobs'}))
    elif args.command == 'freeze':
        lock = freeze(args.root, args.output)
        print(json.dumps(dict(files=len(lock['files']), tree_sha256=lock['tree_sha256'])))
    elif args.command == 'run':
        run(args)
    elif args.command == 'admit':
        from .admission import admit
        manifest, cfg, tasks, _ = prepare(args)
        source = worker_identity(read(args.site)['research_root'])
        admit(args, manifest, cfg, tasks, source)
    elif args.command == 'collect':
        from .collect import collect
        write(args.output, collect(args.manifest, args.run))
    else:
        from .report import build
        build(read(args.results), Path(args.output), compare=args.compare)


if __name__ == '__main__':
    main()
