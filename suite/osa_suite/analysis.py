"""Paired inference uses tasks/repositories as clusters, keeping seeds together."""
from __future__ import annotations

import math
import random
from collections import defaultdict


def quantile(values, q):
    values = sorted(values)
    if not values:
        return None
    pos = (len(values) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def summarize(rows):
    output = {}
    grouped = defaultdict(list)
    for r in rows:
        grouped[(r['track'], r['benchmark'], r.get('protocol'), r['agent'])].append(r)
    for key, group in grouped.items():
        valid = [r for r in group if r['protocol_valid'] and r['accounting_valid'] and r['scoring_valid']]
        success = sum(r['success'] for r in valid)
        batches = defaultdict(list)
        for row in valid:
            if 'batch_id' in row:
                batches[row['batch_id']].append(row)
        complete = all(len(batch) == batch[0]['batch_task_count'] and
                       len({r['batch_wall_s'] for r in batch}) == 1 for batch in batches.values())
        observed_wall = (sum(b[0]['batch_wall_s'] for b in batches.values())
                         if batches and complete and sum(map(len, batches.values())) == len(valid) else None)
        output['|'.join(str(x) for x in key)] = dict(
            attempts=len(group), valid=len(valid), invalid=len(group) - len(valid),
            unique_tasks=len({r['task_id'] for r in valid}), seeds=sorted({r['seed'] for r in valid}),
            successes=success, success_rate=success / len(valid) if valid else None,
            total_tokens=sum(r['actual_api_tokens'] for r in valid),
            invalid_observed_tokens=sum(r.get('observed_api_tokens') or 0 for r in group if r not in valid),
            invalid_upper_bound_tokens=sum(r.get('total_token_upper_bound') or 0 for r in group if r not in valid),
            tokens_per_success=sum(r['actual_api_tokens'] for r in valid) / success if success else None,
            complete_batch_wall_s=observed_wall,
            successful_tasks_per_batch_hour=success * 3600 / observed_wall if observed_wall else None,
            completion_p50_s=quantile([r['completion_s'] for r in valid], .5),
            completion_p95_s=quantile([r['completion_s'] for r in valid], .95))
    return output


def paired(rows, a, b, *, iterations=10000, seed=20261107):
    rows = [r for r in rows if r['protocol_valid'] and r['accounting_valid'] and r['scoring_valid']]
    contexts = {(r['track'], r['benchmark'], r.get('protocol')) for r in rows}
    if len(contexts) != 1:
        raise ValueError('Select exactly one track, benchmark, and protocol before pairing')
    arms = defaultdict(dict)
    for row in rows:
        key = (row['task_id'], row['seed'])
        if row['agent'] in arms[key]:
            raise ValueError('Duplicate arm/task/seed; invalid attempts need distinct attempt records')
        arms[key][row['agent']] = row
    pairs = [(v[a], v[b]) for v in arms.values() if a in v and b in v]
    cross = {'both_success': 0, 'a_only': 0, 'b_only': 0, 'both_fail': 0}
    tasks = defaultdict(list)
    repos = {}
    cases = []
    for left, right in pairs:
        if left['repository'] != right['repository']:
            raise ValueError('Repository mismatch in a paired task')
        label = 'both_success' if left['success'] and right['success'] else ('a_only' if left['success'] else ('b_only' if right['success'] else 'both_fail'))
        cross[label] += 1
        tasks[left['task_id']].append(int(left['success']) - int(right['success']))
        repos[left['task_id']] = left['repository']
        cases.append(dict(task_id=left['task_id'], repository=left['repository'], seed=left['seed'],
                          outcome=label, a_success=left['success'], b_success=right['success'],
                          actual_token_difference_a_minus_b=left['actual_api_tokens'] - right['actual_api_tokens'],
                          completion_difference_a_minus_b_s=left['completion_s'] - right['completion_s']))
    means = {t: sum(v) / len(v) for t, v in tasks.items()}
    def interval(cluster):
        groups = defaultdict(list)
        for t, value in means.items():
            groups[cluster(t)].append(value)
        if len(groups) < 2:
            return dict(low=None, high=None, clusters=len(groups), reason='fewer than two clusters')
        rng = random.Random(seed)
        keys = sorted(groups)
        boot = []
        for _ in range(iterations):
            sample = [v for k in rng.choices(keys, k=len(keys)) for v in groups[k]]
            boot.append(sum(sample) / len(sample))
        return dict(low=quantile(boot, .025), high=quantile(boot, .975), clusters=len(groups))
    return dict(a=a, b=b, paired_task_seeds=len(pairs), unique_tasks=len(tasks), cross_table=cross,
                task_mean_success_difference=sum(means.values()) / len(means) if means else None,
                task_cluster_ci=interval(lambda t: t), repository_cluster_ci=interval(lambda t: repos[t]),
                case_differences=cases,
                estimand='unweighted sampled-task mean; seeds retained together; not full-population weighted')


def pareto(points):
    """Higher success; lower cost and latency. No scalar score is constructed."""
    return [p for p in points if not any(
        q['success_rate'] >= p['success_rate'] and q['tokens'] <= p['tokens'] and q['latency_s'] <= p['latency_s'] and
        (q['success_rate'] > p['success_rate'] or q['tokens'] < p['tokens'] or q['latency_s'] < p['latency_s'])
        for q in points)]
