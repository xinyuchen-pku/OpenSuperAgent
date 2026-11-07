"""Run two independent processes against the same zero-model journal."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


RESEARCH = Path(__file__).resolve().parents[2] / 'research'


def run(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    journal = output / 'journal'
    phases = []
    env = dict(os.environ, OSA_SOURCE=str(RESEARCH))
    for phase in ('first', 'resume'):
        command = [sys.executable, str(RESEARCH / 'reproduction/system_track.py'),
                   '--restart-child', str(journal), phase]
        with subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True) as child:
            try:
                stdout, stderr = child.communicate(timeout=45)
            except subprocess.TimeoutExpired:
                child.kill()
                child.communicate()
                raise
            if child.returncode:
                raise RuntimeError(stderr)
            phases.append({'phase': phase, 'pid': child.pid, 'result': json.loads(stdout)})
    trace = output / 'trace.jsonl'
    export = subprocess.run([sys.executable, str(RESEARCH / 'reproduction/export_trace.py'),
                             '--database', str(journal / 'run.sqlite3'), '--output', str(trace)],
                            text=True, capture_output=True, check=True, timeout=30)
    records = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
    kinds = [row['kind'] for row in records]
    first, resumed = (phase['result'] for phase in phases)
    assert phases[0]['pid'] != phases[1]['pid']
    assert kinds.count('run_started') == 2 and kinds.count('subscription_fanout') == 2
    assert first['max_parallel_fixed_work'] == 2
    assert first['work_units'] == 2 and resumed['work_units'] == 4
    assert first['router_fixture_calls'] == resumed['router_fixture_calls'] == 2
    assert all(p['result']['actual_api_calls'] == 0 for p in phases)
    receipt = {'scope': 'deterministic mechanism demo', 'actual_api_calls': 0,
               'source_manifest_sha256': hashlib.sha256((RESEARCH / 'SOURCE_MANIFEST.json').read_bytes()).hexdigest(),
               'trace_sha256': hashlib.sha256(trace.read_bytes()).hexdigest(),
               'journal_export': json.loads(export.stdout), 'phases': phases}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print('2 workers overlapped, 2 follow-ups reached their subscribers, 0 model API calls.')
    print(f'Trace and process receipts: {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)
