"""Content-bound experiment manifests and deterministic paired arm order."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from osa_eval.contracts import canonical

ARCHITECTURES = ('single', 'single_subagent', 'eager_delegation', 'router_worker', 'superagent')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_files(root, destination):
    return {p.relative_to(root).as_posix(): file_hash(p) for p in sorted(root.rglob('*'))
            if p.is_file() and p.resolve() != destination and '__pycache__' not in p.parts
            and not any(x.endswith('.egg-info') for x in p.parts)
            and not {'build', 'dist', 'runs'} & set(p.relative_to(root).parts)
            and p.suffix in {'.py', '.json', '.toml', '.md', '.txt'}}


def freeze(root, destination):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if destination.exists():
        raise FileExistsError('A frozen lock is immutable; choose a new version')
    files = source_files(root, destination)
    lock = dict(schema='osa-suite-lock-v1', files=files,
                tree_sha256=hashlib.sha256(canonical(files).encode()).hexdigest())
    write(destination, lock)
    return lock


def verify_lock(root, path):
    root, lock = Path(root).resolve(), read(path)
    if hashlib.sha256(canonical(lock['files']).encode()).hexdigest() != lock['tree_sha256']:
        raise ValueError('Lock content digest mismatch')
    mismatches = [name for name, value in lock['files'].items()
                  if not (root / name).is_file() or file_hash(root / name) != value]
    if mismatches:
        raise ValueError('Frozen files changed: ' + ', '.join(mismatches))
    extra = set(source_files(root, Path(path).resolve())) - set(lock['files'])
    if extra:
        raise ValueError('Unfrozen source files added: ' + ', '.join(sorted(extra)))
    return lock


def verify_installed_suite(lock):
    installed = Path(__file__).resolve().parent
    expected = {name.removeprefix('osa_suite/'): sha for name, sha in lock['files'].items()
                if name.startswith('osa_suite/') and name.endswith('.py')}
    actual = {p.relative_to(installed).as_posix(): file_hash(p) for p in installed.rglob('*.py')}
    if actual != expected:
        raise ValueError('Installed Stage 2 package differs from the frozen source lock')


def schedule(tasks, architectures, seeds, *, order_seed, batch_size=None):
    tasks = list(tasks)
    if len(set(tasks)) != len(tasks) or len(set(seeds)) != len(seeds):
        raise ValueError('Duplicate tasks or seeds')
    if not architectures or len(set(architectures)) != len(architectures):
        raise ValueError('Unique non-empty architecture list required')
    batch_size = batch_size or len(tasks)
    if batch_size <= 0:
        raise ValueError('Non-empty tasks and a positive batch size required')
    result = []
    for seed in seeds:
        for start in range(0, len(tasks), batch_size):
            block = start // batch_size
            arms = sorted(architectures, key=lambda arm: hashlib.sha256(f'{order_seed}:{seed}:{block}:{arm}'.encode()).hexdigest())
            for order, arm in enumerate(arms):
                result.append(dict(seed=seed, agent=arm, arm_order=order, block=block,
                                   tasks=tasks[start:start + batch_size]))
    return result


def load_experiment(path, benchmark):
    path = Path(path).resolve()
    manifest = read(path)
    if manifest['schema'] != 'osa-stage2-v1':
        raise ValueError('Unsupported experiment schema')
    if benchmark not in manifest['benchmarks']:
        raise ValueError('Unknown benchmark')
    cfg = manifest['benchmarks'][benchmark]
    tasks_path = path.parent / cfg['tasks_path']
    if file_hash(tasks_path) != cfg['tasks_sha256']:
        raise ValueError('Task manifest hash mismatch')
    tasks = read(tasks_path)
    ids = [r['task_id'] for r in tasks['tasks']]
    if len(ids) != len(set(ids)) or len(ids) != cfg['task_count']:
        raise ValueError('Task count or identity mismatch')
    if cfg['task_tokens'] * len(ids) * len(cfg['seeds']) * len(cfg['agents']) != cfg['maximum_api_tokens']:
        raise ValueError('Theoretical stage token ceiling is inconsistent')
    return manifest, cfg, tasks
