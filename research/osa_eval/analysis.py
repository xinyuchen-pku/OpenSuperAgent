"""Recompute summaries and scientific plots from measured campaign artifacts only."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .contracts import canonical, digest
from .metrics import summarize
from .swebench_pro import file_sha


def active_admission_mean(trace, wall_s):
    active, previous, area = set(), None, 0.0
    for row in trace:
        if previous is not None:
            area += len(active) * (row["at"] - previous)
        if row["kind"] == "worker_started":
            active.add(row["task_id"])
        elif row["kind"] == "worker_slot_released":
            active.discard(row["task_id"])
        previous = row["at"]
    return area / wall_s if wall_s > 0 and not active else None


def analyze(root, output, *, plots=False, reclassifications=None):
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    table, failures = [], []
    overrides = json.loads(Path(reclassifications).read_text(encoding="utf-8"))["annotations"] if reclassifications else []
    for result_path in sorted(Path(root).rglob("result.json")):
        run = json.loads(result_path.read_text(encoding="utf-8"))
        if run.get("evidence_tier") != "official-task-custom-backend":
            continue
        identity = json.loads((result_path.parent / "identity.json").read_text(encoding="utf-8"))
        if run.get("status") != "completed":
            failures.append({"path": str(result_path), "error": run.get("error"), "usage": run.get("usage")})
            continue
        for annotation in overrides:
            if annotation["result_sha256"] == file_sha(result_path):
                for row in run["rows"]:
                    if (row["task_id"], row["seed"]) == (annotation["task_id"], annotation["seed"]):
                        row.update({k: annotation[k] for k in ["valid", "success", "grade_source_sha256", "failure_category"]})
        summary = summarize(run["rows"], horizon_s=run["horizon_s"])
        trace = [json.loads(line) for line in (result_path.parent / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
        usage = run["usage"]
        roles = {}
        for call in usage["calls"]:
            role = roles.setdefault(call["role"], {"calls": 0, "input_tokens": 0, "output_tokens": 0})
            role["calls"] += 1
            role["input_tokens"] += call["input_tokens"] or 0
            role["output_tokens"] += call["output_tokens"] or 0
        row = {"run": str(result_path.parent), "architecture": identity["architecture"], "seed": identity["seed"],
               "workload_sha256": digest(identity["events"]),
               "slots": identity["limits"]["slots"], "offered_tasks": len(identity["events"]),
               "mean_active_admitted_slots": active_admission_mean(trace, run["agent_wall_s"]),
               "input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"],
               "known_total_tokens": usage["input_tokens"] + usage["output_tokens"],
               "token_upper_bound": usage["total_token_upper_bound"], "accounting_valid": usage["accounting_valid"],
               "cost_usd": usage["cost_usd"], "role_usage": roles, **summary}
        table.append(row)
    (output / "analysis.json").write_text(canonical({"runs": table, "failed_runs": failures,
        "interpretation": "Measured points only; compare matched workloads/configurations before drawing architectural conclusions. Active slots include admitted sessions waiting for model/session locks. Fixed-horizon throughput includes idle time until the declared horizon."}), encoding="utf-8")
    if table:
        columns = [k for k in table[0] if k != "role_usage"]
        with (output / "runs.csv").open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, columns, extrasaction="ignore");writer.writeheader();writer.writerows(table)
    if plots and table:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import pyplot as plt
        definitions = [("known_total_tokens", "success_rate", "Success versus measured token use", "Known input + output tokens", "Resolved fraction", "success-tokens"),
                       ("slots", "resolved_throughput_per_hour", "Throughput versus execution ceiling", "Execution slots (workload must be matched)", "Resolved tasks / hour at fixed horizon", "throughput-slots"),
                       ("mean_active_admitted_slots", "mean_capped_time_in_system_s_all_valid", "Completion time versus active admissions", "Mean active admitted slots (includes waits)", "Mean capped time in system, seconds", "time-active")]
        for x, y, title, xlabel, ylabel, filename in definitions:
            fig, ax = plt.subplots(figsize=(7.2, 4.6), constrained_layout=True)
            for architecture in sorted({r["architecture"] for r in table}):
                points = [r for r in table if r["architecture"] == architecture and r[x] is not None and r[y] is not None and (x != "known_total_tokens" or r["accounting_valid"])]
                if points:ax.scatter([r[x] for r in points], [r[y] for r in points], label=architecture, alpha=.8)
            ax.set(title=title + "\nMeasured runs; descriptive points", xlabel=xlabel, ylabel=ylabel)
            ax.grid(alpha=.2);ax.legend(fontsize=8)
            fig.savefig(output / (filename + ".pdf"));fig.savefig(output / (filename + ".png"), dpi=180);plt.close(fig)
    return {"completed_runs": len(table), "failed_runs": len(failures), "output": str(output)}
