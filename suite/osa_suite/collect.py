"""Normalize the suite's native/Pro evidence without rewriting scorer metrics."""
from __future__ import annotations

from pathlib import Path

from .manifest import read, load_experiment, file_hash


def collect(manifest_path, run):
    run = Path(run)
    plan, status = read(run / 'plan.json'), read(run / 'status.json')
    if plan['manifest_sha256'] != file_hash(manifest_path):
        raise ValueError('Run belongs to a different experiment manifest')
    _, cfg, tasks = load_experiment(manifest_path, plan['benchmark'])
    task_info = {r['task_id']: r for r in tasks['tasks']}
    ledger = read(run / 'budget.json')

    def counts(task_key):
        calls = [r for r in ledger['calls'] if r['task'] == task_key and r['state'] != 'cancelled']
        charged = [r for r in calls if r['state'] == 'complete']
        def tokens(rows):
            return sum(r['input_tokens'] + r['output_tokens'] for r in rows)
        known = tokens(charged)
        pending = sum(r['reserved'] for r in calls if r['state'] != 'complete')
        valid = bool(calls) and len(calls) == len(charged) and not any(
            r['input_tokens'] + r['output_tokens'] > r['reserved'] for r in charged)
        return dict(accounting_valid=valid, actual_api_tokens=known if valid else None,
                    observed_api_tokens=known, total_token_upper_bound=known + pending,
                    router_tokens=tokens([r for r in charged if r['role'] == 'router']),
                    worker_tokens=tokens([r for r in charged if r['role'] != 'router']),
                    router_calls=sum(r['role'] == 'router' for r in calls),
                    worker_calls=sum(r['role'] != 'router' for r in calls),
                    reserved_tokens_sum=sum(r['reserved'] for r in calls),
                    reservation_denials=sum(e['kind'] == 'reservation_denied' and e['payload']['task'] == task_key
                                            for e in ledger['events']))

    def base(tid, arm, seed):
        return dict(track=cfg['track'], benchmark=plan['benchmark'], protocol=cfg['protocol'],
                    agent=arm, task_id=tid, repository=task_info[tid]['repository'], seed=seed)

    rows = []
    for item in status['completed']:
        if cfg['track'] == 'native_capability':
            tid, seed = item['task_id'], item['seed']
            path = Path(item['bundle'])
            bundle = read(path)
            dependency = read(path.parent / 'strict_dependency_metrics.json')
            valid = bool(item['official_bundle_valid'] and bundle['status'] == 'valid' and
                         bundle['instrumentation']['valid'] and bundle['eligibility']['official_profile'])
            usage = counts('|'.join([tid, cfg['protocol'], str(seed)]))
            final = bundle['final_test']
            rows.append(base(tid, 'native', seed) | usage | dict(
                protocol_valid=valid, scoring_valid=valid, success=final['success'],
                completion_s=item['completion_s'], batch_wall_s=item['completion_s'],
                batch_id=str(path), batch_task_count=1, final_test=final,
                official_final_integrated_ADPR=dependency['final_integrated_ADPR'],
                official_strict_DRS=dependency['strict_DRS'],
                official_dependency_cases=dependency['dependency_metrics'],
                independent_regrade_valid=item['independent_regrade_valid'],
                failure_class='accounting' if not usage['accounting_valid'] else 'scoring' if not valid else None,
                source_bundle=str(path)))
        else:
            path = Path(item['result'])
            result = read(path)
            scores = {r['task_id']: r for r in result['official_replays']}
            for row in result['rows']:
                tid, seed, arm = row['task_id'], item['seed'], item['agent']
                receipt = scores[tid]
                valid = bool(result['official_protocol_valid'] and receipt['official_protocol_valid'])
                usage = counts('|'.join([tid, arm, str(seed)]))
                rows.append(base(tid, arm, seed) | usage | dict(protocol_valid=valid, scoring_valid=valid,
                    success=receipt['success'], completion_s=row['submitted_s'],
                    batch_wall_s=result['agent_wall_s'], batch_id=str(path), batch_task_count=len(result['rows']),
                    independent_original_grade_valid=receipt['independent_original_valid'],
                    test_outcomes_equal=receipt['test_outcomes_equal'],
                    failure_class='accounting' if not usage['accounting_valid'] else 'scoring' if not valid else None,
                    source_grade=str(path), source_original_grade=receipt['trial']))
    if status['status'] == 'stopped' and status.get('active'):
        active = status['active']
        for tid in active['tasks']:
            arm, seed = active['agent'], active['seed']
            key = '|'.join([tid, cfg['protocol'] if cfg['track'] == 'native_capability' else arm, str(seed)])
            usage = counts(key)
            rows.append(base(tid, arm, seed) | usage | dict(protocol_valid=False, scoring_valid=False,
                success=None, completion_s=None, failure_class='accounting' if not usage['accounting_valid'] and usage['total_token_upper_bound'] else 'infrastructure',
                diagnostic=status.get('error'), source_attempt=str(run)))
    return rows
