"""Metrics require independent grades; completion claims are never sufficient."""
from __future__ import annotations

import math
import random
import statistics


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    x = (len(values) - 1) * p
    lo, hi = math.floor(x), math.ceil(x)
    return values[lo] + (values[hi] - values[lo]) * (x - lo)


def summarize(rows, *, horizon_s):
    if not math.isfinite(horizon_s) or horizon_s <= 0 or not rows:
        raise ValueError("A nonempty cohort and positive observation horizon are required")
    keys = [(r["task_id"], r["seed"]) for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate task/seed rows")
    valid, invalid = [], []
    for row in rows:
        if not 0 <= row["arrival_s"] <= horizon_s:
            raise ValueError("Task arrival lies outside the observation window")
        end = row.get("submitted_s")
        if end is not None and (not math.isfinite(end) or end < row["arrival_s"]):
            raise ValueError("Submission precedes arrival or is nonfinite")
        if row.get("success") is not None and type(row["success"]) is not bool:
            raise ValueError("Grade must be boolean or absent")
        if row.get("success") is not None and not row.get("grade_source_sha256"):
            raise ValueError("Grades need independent evaluator artifact provenance")
        (valid if row.get("valid") is True else invalid).append(row)
    done = [r for r in valid if r.get("submitted_s") is not None and r["submitted_s"] <= horizon_s]
    graded = [r for r in done if r.get("success") is not None]
    success = [r for r in graded if r["success"] is True]
    latency = [r["submitted_s"] - r["arrival_s"] for r in done]
    capped = [min(r.get("submitted_s") if r.get("submitted_s") is not None else horizon_s, horizon_s) - r["arrival_s"] for r in valid]
    return {"cohort_count": len(rows), "valid_count": len(valid), "infrastructure_invalid_count": len(invalid),
            "official_aggregate_eligible": not invalid and len(done) == len(graded) and all(r.get("official_protocol_valid") is True for r in rows),
            "submitted_count": len(done), "graded_count": len(graded), "resolved_at_time_budget": len(success),
            "success_rate": len(success) / len(valid) if valid else None,
            "completion_fraction": len(done) / len(valid) if valid else None,
            "resolved_throughput_per_hour": len(success) * 3600 / horizon_s,
            "submission_throughput_per_hour": len(done) * 3600 / horizon_s,
            "p50_submission_latency_s_completed_only": percentile(latency, .50),
            "p95_submission_latency_s_completed_only": percentile(latency, .95),
            "mean_capped_time_in_system_s_all_valid": statistics.mean(capped) if capped else None,
            "right_censored_count": len(valid) - len(done), "ungraded_submissions": len(done) - len(graded)}


def paired_bootstrap(a, b, *, seed=0, samples=10_000):
    """Each mapping is task -> outcomes across the SAME repeated seed set; cluster by task."""
    if not a or set(a) != set(b) or type(samples) is not int or samples <= 0:
        raise ValueError("Paired task sets and a positive bootstrap sample count are required")
    differences = []
    for task in sorted(a):
        if not a[task] or set(a[task]) != set(b[task]):
            raise ValueError("Each task needs the same nonempty paired seed set")
        values = list(a[task].values()) + list(b[task].values())
        if any(not math.isfinite(v) for v in values):
            raise ValueError("Bootstrap outcomes must be finite")
        differences.append(statistics.mean(b[task][s] - a[task][s] for s in a[task]))
    rng = random.Random(seed)
    distribution = [statistics.mean(rng.choices(differences, k=len(differences))) for _ in range(samples)]
    return {"mean_difference_b_minus_a": statistics.mean(differences), "ci95": [percentile(distribution, .025), percentile(distribution, .975)],
            "task_clusters": len(differences), "bootstrap_samples": samples, "seed": seed}


COMMON_FIELDS = ("model", "generation", "worker_prompt_sha256", "tools_sha256", "workload_sha256", "benchmark_sha256", "image_manifest_sha256")


def validate_comparison(configs, mode):
    if len(configs) < 2 or mode not in {"capacity", "budget"}:
        raise ValueError("Compare at least two configurations in capacity or budget mode")
    if mode == "capacity":
        controls = ("slots", "model_concurrency", "model_rate_limit", "horizon_s")
    else:
        units = {c.get("budget_unit") for c in configs}
        if len(units) != 1 or not units <= {"tokens", "usd"}:
            raise ValueError("Freeze one common budget_unit: tokens or usd")
        controls = ("budget_unit", "token_budget" if "tokens" in units else "cost_budget_usd")
    fields = COMMON_FIELDS + controls
    for field in fields:
        if any(field not in c or c[field] is None or c[field] == "" for c in configs):
            raise ValueError("Unfrozen comparison field: " + field)
        if any(c[field] != configs[0][field] for c in configs[1:]):
            raise ValueError("Comparison differs on " + field)
    return {"mode": mode, "matched_fields": list(fields), "configuration_count": len(configs)}
