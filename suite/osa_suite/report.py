"""Export normalized tables, paired CIs and separate Success/Cost/Latency plots."""
from __future__ import annotations

import csv
from collections import defaultdict

from .analysis import summarize, paired, pareto
from .manifest import write

REQUIRED = {'track', 'benchmark', 'protocol', 'agent', 'task_id', 'repository', 'seed',
            'protocol_valid', 'accounting_valid', 'scoring_valid', 'success',
            'actual_api_tokens', 'completion_s'}
PRIMARY_CONTRASTS = [('single', 'eager_delegation'), ('eager_delegation', 'router_worker'),
                     ('router_worker', 'superagent'), ('single_subagent', 'superagent'),
                     ('eager_delegation', 'superagent')]


def validate(rows):
    seen = set()
    for row in rows:
        if not REQUIRED <= set(row):
            raise ValueError('Missing result fields: ' + ','.join(sorted(REQUIRED - set(row))))
        for key in ('protocol_valid', 'accounting_valid', 'scoring_valid'):
            if type(row[key]) is not bool:
                raise ValueError('Validity fields must be booleans')
        valid = all(row[k] for k in ('protocol_valid', 'accounting_valid', 'scoring_valid'))
        if valid:
            if type(row['success']) is not bool or type(row['actual_api_tokens']) is not int or row['actual_api_tokens'] < 0:
                raise ValueError('Valid results require observed integer usage and binary success')
            import math
            if not isinstance(row['completion_s'], (int, float)) or not math.isfinite(row['completion_s']) or row['completion_s'] < 0:
                raise ValueError('Valid results require observed nonnegative finite latency')
            key = tuple(row[k] for k in ('track', 'benchmark', 'protocol', 'agent', 'task_id', 'seed'))
            if key in seen:
                raise ValueError('Duplicate valid task/seed/arm; select the preregistered attempt')
            seen.add(key)
        elif row.get('failure_class') not in {'infrastructure', 'scoring', 'protocol', 'accounting'}:
            raise ValueError('Invalid results need an explicit failure class')


def build(rows, output, *, compare=None):
    validate(rows)
    output.mkdir(parents=True, exist_ok=False)
    groups = summarize(rows)
    write(output / 'summary.json', groups)
    # Per-seed tables remain separate; seeds never multiply independent task N.
    by_seed = {str(seed): summarize([r for r in rows if r['seed'] == seed]) for seed in sorted({r['seed'] for r in rows})}
    write(output / 'per-seed.json', by_seed)
    with (output / 'summary.csv').open('w', encoding='utf-8', newline='') as stream:
        fieldnames = ['condition', *next(iter(groups.values())).keys()] if groups else ['condition']
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for key, row in groups.items():
            writer.writerow(dict(condition=key, **row))
    if compare:
        # Caller must select one benchmark/protocol/track; paired() rejects mixes.
        write(output / 'paired.json', paired(rows, *compare))
    contexts = defaultdict(list)
    for row in rows:
        contexts[(row['track'], row['benchmark'], row['protocol'])].append(row)
    frontiers = {}
    contrasts = {}
    for context, values in contexts.items():
        points = []
        arms = sorted({r['agent'] for r in values})
        keys = {arm: {(r['task_id'], r['seed']) for r in values if r['agent'] == arm and
                      all(r[k] for k in ('protocol_valid', 'accounting_valid', 'scoring_valid'))} for arm in arms}
        balanced = set.intersection(*keys.values()) if keys else set()
        for arm in arms:
            arm_rows = [r for r in values if r['agent'] == arm and (r['task_id'], r['seed']) in balanced
                        and all(r[k] for k in ('protocol_valid', 'accounting_valid', 'scoring_valid'))]
            if arm_rows:
                points.append(dict(agent=arm, success_rate=sum(r['success'] for r in arm_rows) / len(arm_rows),
                     tokens=sum(r['actual_api_tokens'] for r in arm_rows) / len(arm_rows),
                     latency_s=sum(r['completion_s'] for r in arm_rows) / len(arm_rows)))
        label = '|'.join(str(x) for x in context)
        frontiers[label] = dict(points=points, non_dominated=pareto(points),
             balanced_task_seed_count=len(balanced), arms=arms,
             scope='Intersection of valid task/seed pairs across present arms; stage completeness remains a separate gate')
        contrasts[label] = [paired(values, a, b) for a, b in PRIMARY_CONTRASTS if a in keys and b in keys and keys[a] & keys[b]]
    write(output / 'pareto.json', frontiers)
    write(output / 'primary-contrasts.json', contrasts)
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        raise RuntimeError('Tables were saved; install matplotlib>=3.8,<4 to generate figures') from None
    for index, (context, data) in enumerate(frontiers.items()):
        fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout='constrained')
        for point in data['points']:
            for ax, field in zip(axes, ['tokens', 'latency_s']):
                ax.scatter(point[field], 100 * point['success_rate'])
                ax.annotate(point['agent'], (point[field], 100 * point['success_rate']), xytext=(5, 4), textcoords='offset points', fontsize=8)
                ax.set_ylabel('Success (%)')
                ax.set_ylim(-2, 105)
        axes[0].set_xlabel('Mean actual API tokens / task')
        axes[1].set_xlabel('Mean observed completion time (s)')
        fig.suptitle(context + '\nObserved sample; separate benchmark/protocol/track')
        fig.savefig(output / f'pareto-{index:02d}.png', dpi=180)
        plt.close(fig)
    (output / 'README.md').write_text(
        '# Evaluation report\n\nTables include validity and unique task counts. Paired intervals resample tasks or repositories, keeping seeds together. '
        'Pareto coordinates use observed sample means; no full-benchmark extrapolation. '
        'Throughput uses only complete batch clock receipts. '
        'Native dependency metrics remain in original scorer artifacts; ADPR/DRS are not redefined here.\n', encoding='utf-8')
