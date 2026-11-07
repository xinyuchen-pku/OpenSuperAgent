"""Outcome-blind, deterministic stratified sampling from PUBLIC instructions only.

Complexity and parallelizability are declared text proxies, not gold-patch
properties. Freeze annotations before any new outcome; report proxy limitations.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict


def rank(seed, value):
    return hashlib.sha256(f'{seed}:{value}'.encode()).hexdigest()


def annotate(rows):
    sizes = sorted(len(r['instruction'].split()) for r in rows)
    cuts = (sizes[len(sizes) // 3], sizes[2 * len(sizes) // 3])
    result = []
    for row in rows:
        text = row['instruction']
        size = len(text.split())
        # Paths are from public requirements, never solution or hidden tests.
        paths = sorted(set(re.findall(r'\b[\w.-]+(?:/[\w.-]+)+\.(?:go|py|js|jsx|ts|tsx)\b', text)))
        coupled = bool(re.search(r'\b(depend(?:s|ency|encies)|backward.compatib\w*|migration|shared.state|ordering|synchroni[sz]\w*)\b', text, re.I))
        parallel = 'dependency_coupled_text' if coupled else ('multi_path_text' if len(paths) >= 2 else 'unspecified_text')
        result.append({k: row[k] for k in ('task_id', 'repository', 'language', 'instruction_sha256', 'task_toml_sha256')} |
                      dict(complexity_proxy='short' if size <= cuts[0] else 'medium' if size <= cuts[1] else 'long',
                           parallelizability_proxy=parallel, instruction_words=size, public_source_paths=paths))
    return result, dict(complexity_word_thresholds=list(cuts), proxy_version='public-instruction-v1')


def select(rows, *, excluded, count, seed):
    if type(count) is not int or count <= 0:
        raise ValueError('Positive sample count required')
    if len({r['task_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate task IDs')
    eligible = [r for r in rows if r['task_id'] not in set(excluded)]
    if count > len(eligible):
        raise ValueError('Sample exceeds unseen population')
    cells = defaultdict(list)
    for row in eligible:
        cells[tuple(row[k] for k in ('repository', 'language', 'complexity_proxy', 'parallelizability_proxy'))].append(row)
    if len(cells) > count:
        raise ValueError('Sample too small for one task per non-empty stratum')
    # Give every non-empty stratum one; allocate remaining proportionally to
    # remaining capacity by largest remainder. This oversamples rare strata.
    quotas = {k: 1 for k in cells}
    remaining = count - len(cells)
    capacity = sum(len(v) - 1 for v in cells.values())
    if capacity and remaining:
        exact = {k: remaining * (len(v) - 1) / capacity for k, v in cells.items()}
        for k in quotas:
            quotas[k] += math.floor(exact[k])
        left = count - sum(quotas.values())
        for k in sorted(cells, key=lambda k: (-(exact[k] - math.floor(exact[k])), rank(seed, repr(k))))[:left]:
            quotas[k] += 1
    selected = []
    for key, values in cells.items():
        for row in sorted(values, key=lambda r: rank(seed, r['task_id']))[:quotas[key]]:
            selected.append(row | dict(stratum=list(key), population_in_stratum=len(values),
                                       selected_in_stratum=quotas[key], inclusion_probability=quotas[key] / len(values)))
    selected.sort(key=lambda r: rank(seed, 'order:' + r['task_id']))
    return selected, [dict(stratum=list(k), population=len(cells[k]), selected=quotas[k]) for k in sorted(cells)]
