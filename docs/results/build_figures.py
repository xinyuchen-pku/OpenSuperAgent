"""Regenerate README figures from the repository's published experiment tables."""
from pathlib import Path
import csv
import hashlib
import json
import statistics

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.ticker import PercentFormatter

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
ARMS = ["single", "single_subagent", "eager_delegation", "router_worker", "superagent"]
LABELS = ["Single", "Single + Subagent", "Eager Delegation", "Router–Worker", "Super-agent"]
COLORS = ["#6b7280", "#16856f", "#3275c6", "#b77b22", "#7050df"]
SOURCES = {
    "m2_batches": "research/tables/batches.csv",
    "m2_cases": "research/tables/cases.csv",
    "capability": "research/studies/m3-a3/CAPABILITY-RESULTS.csv",
    "capacity": "research/studies/m3-a3/system-capacity.csv",
    "events": "research/studies/m3-a3/system-events.csv",
}


def read(key):
    with (ROOT / SOURCES[key]).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def truth(value):
    assert value in {"True", "False"}, value
    return value == "True"


def style(ax, direction="x"):
    ax.set_axisbelow(True)
    ax.grid(axis=direction, color="#e9eaf1", linewidth=.8)
    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#d1d5db")
    ax.tick_params(axis="both", length=0, pad=8)


def save(fig, stem):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for text in fig.texts:
        bounds = text.get_window_extent(renderer)
        assert bounds.x0 >= 0 and bounds.x1 <= fig.bbox.width, (stem, text.get_text())
    fig.savefig(OUT / (stem + ".png"), dpi=170, facecolor="white", metadata={"Software": "Matplotlib " + matplotlib.__version__})
    svg = OUT / (stem + ".svg")
    fig.savefig(svg, facecolor="white", metadata={"Date": None})
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines()).rstrip() + "\n", encoding="utf-8")
    plt.close(fig)


def main():
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 14,
        "axes.labelcolor": "#374151", "text.color": "#202534",
        "xtick.color": "#4b5563", "ytick.color": "#202534",
        "svg.fonttype": "path", "svg.hashsalt": "OpenSuperAgent-results-001"})
    batches = [r for r in read("m2_batches") if r["section"] == "primary"]
    cases = [r for r in read("m2_cases") if r["section"] == "primary"]
    assert len(batches) == 15 and len(cases) == 60
    task_ids = sorted({r["task_id"] for r in cases})
    successful_ids = sorted({r["task_id"] for r in cases if truth(r["success"])})
    assert len(task_ids) == 4 and len(successful_ids) == 1
    pilot = []
    for arm, label in zip(ARMS, LABELS):
        rows = [r for r in batches if r["architecture"] == arm]
        task_rows = [r for r in cases if r["architecture"] == arm]
        assert len(rows) == 3 and len(task_rows) == 12
        successes = sum(int(r["successes"]) for r in rows)
        assert successes == sum(truth(r["success"]) for r in task_rows)
        pilot.append({"architecture": arm, "label": label, "runs": 12,
            "unique_tasks": 4, "seeds": sorted({int(r["seed"]) for r in rows}),
            "successes": successes, "success_rate_pct": successes / 12 * 100,
            "mean_batch_minutes": statistics.mean(float(r["agent_wall_s"]) for r in rows) / 60,
            "total_API_tokens": sum(int(r["actual_api_tokens"]) for r in rows)})
    fig, axes = plt.subplots(1, 3, figsize=(15.6, 5.8), sharey=True)
    fig.subplots_adjust(left=.19, right=.975, top=.74, bottom=.20, wspace=.33)
    fig.text(.035, .93, "Benchmark pilot: success, time and token use", fontsize=22, weight="bold")
    fig.text(.035, .865, "4 simultaneous tasks · 3 paired seeds · Qwen3-Coder-30B-A3B-Instruct · source022", fontsize=13.5, color="#5b6472")
    definitions = [("success_rate_pct", "Task success", "Success rate (%)", 38),
        ("mean_batch_minutes", "Completion time", "Mean batch time (min)", 49),
        ("total_API_tokens", "Token use", "Total API tokens (M)", 26)]
    for ax, (key, title, xlabel, limit) in zip(axes, definitions):
        values = [r[key] / 1_000_000 if key == "total_API_tokens" else r[key] for r in pilot]
        ax.barh(range(5), values, height=.58, color=COLORS)
        ax.set(xlim=(0, limit), xlabel=xlabel, title=title)
        ax.set_title(title, fontsize=17, weight="bold", pad=18)
        if key == "success_rate_pct":
            ax.set_xticks([0, 10, 20, 30]); ax.xaxis.set_major_formatter(PercentFormatter(100, decimals=0))
        for y, (value, row) in enumerate(zip(values, pilot)):
            label = str(row["successes"]) + "/12" if key == "success_rate_pct" else (f"{value:.2f}" if key == "total_API_tokens" else f"{value:.1f}")
            ax.text(value + limit * .025, y, label, va="center", fontsize=14)
        style(ax)
    axes[0].set_yticks(range(5), LABELS); axes[0].invert_yaxis()
    fig.text(.035, .075, "Descriptive pilot: 4 independent tasks. All successes came from OpenLibrary.", fontsize=12.5, color="#5b6472")
    fig.text(.035, .027, "Time excludes official grading. Tokens include Worker and coordination calls, summed over the 12 runs.", fontsize=12.5, color="#5b6472")
    save(fig, "benchmark-pilot")

    raw = read("capability")
    cohorts = ["qwen-source025", "next-source025", "next-mini"]
    cohort_labels = ["Qwen30B + shared Worker", "Next + shared Worker", "Next + mini-swe-agent"]
    cohort_colors = ["#6b7280", "#7050df", "#16856f"]
    capability = []
    for cohort, label in zip(cohorts, cohort_labels):
        rows = sorted([r for r in raw if r["cohort"] == cohort], key=lambda r: int(r["index"]))
        assert len(rows) == 3 and all(truth(r["official_protocol_valid"]) for r in rows)
        capability.append({"cohort": cohort, "label": label,
            "full_task_successes": sum(truth(r["success"]) for r in rows),
            "tasks": [{"task_id": r["task_id"], "passed": int(r["required_tests_passed"]),
                "required": int(r["required_tests"]), "success": truth(r["success"])} for r in rows]})
    assert [r["full_task_successes"] for r in capability] == [0, 1, 0]
    fig, ax = plt.subplots(figsize=(15.6, 6.4))
    fig.subplots_adjust(left=.08, right=.97, bottom=.23, top=.69)
    fig.text(.035, .94, "Model capability pilot", fontsize=22, weight="bold")
    fig.text(.035, .88, "Required tests passing · 3 tasks · 1 seed · 2M-token budget per task · source025", fontsize=14, color="#5b6472")
    for index, (group, color) in enumerate(zip(capability, cohort_colors)):
        xs = [x + (index - 1) * .24 for x in range(3)]
        values = [x["passed"] / x["required"] * 100 for x in group["tasks"]]
        ax.bar(xs, values, width=.215, color=color,
            label=group["label"] + f" ({group['full_task_successes']}/3 tasks)")
        for x, value, task in zip(xs, values, group["tasks"]):
            ax.text(x, value + 2, f"{task['passed']}/{task['required']}", ha="center", fontsize=14)
    ax.set(ylim=(0, 114), ylabel="Required tests passing (%)")
    ax.set_yticks([0, 25, 50, 75, 100]); ax.yaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    ax.set_xticks(range(3), ["Teleport", "qutebrowser", "OpenLibrary"])
    ax.legend(loc="lower center", bbox_to_anchor=(.5, 1.04), ncol=3, frameon=False, fontsize=13)
    style(ax, "y")
    fig.text(.035, .09, "Full-task success requires every required test to pass. Bars report the exact passed/required counts.", fontsize=12.5, color="#5b6472")
    fig.text(.035, .035, "These nine admitted runs support a small model/kernel calibration; they do not establish a general framework ranking.", fontsize=12.5, color="#5b6472")
    save(fig, "model-capability")

    raw_capacity, raw_events = read("capacity"), read("events")
    capacity, events = [], []
    for arm, label in zip(ARMS, LABELS):
        rows = [r for r in raw_capacity if r["architecture"] == arm and r["count"] == "16" and r["slots"] == "4"]
        assert len(rows) == 3 and all(int(r["actual_api_calls"]) == 0 for r in rows)
        capacity.append({"architecture": arm, "label": label, "wall_seconds": [float(r["wall_s"]) for r in rows],
            "mean_wall_seconds": statistics.mean(float(r["wall_s"]) for r in rows)})
    variants = ["fresh", "persistent", "persistent_subscription"]
    for variant in variants:
        for followups in [0, 1, 8]:
            rows = [r for r in raw_events if r["context_variant"] == variant and int(r["followups_per_task"]) == followups]
            assert len(rows) == 3 and all(int(r["actual_api_calls"]) == 0 and int(r["work_units"]) == 4 * (1 + followups) for r in rows)
            events.append({"variant": variant, "followups_per_task": followups,
                "mean_router_fixture_turns": statistics.mean(int(r["router_fixture_calls"]) for r in rows)})
    fig = plt.figure(figsize=(15.6, 6.4))
    left, right = fig.add_axes([.19, .23, .30, .47]), fig.add_axes([.62, .23, .35, .47])
    fig.text(.035, .94, "System mechanisms: deterministic Workers", fontsize=22, weight="bold")
    fig.text(.035, .88, "0 real model API calls · means of 3 repetitions · source025", fontsize=14, color="#5b6472")
    values = [r["mean_wall_seconds"] for r in capacity]
    left.barh(range(5), values, height=.58, color=COLORS)
    left.set(yticks=range(5), yticklabels=LABELS, xlim=(0, 2.35), xlabel="Batch time (seconds)")
    left.invert_yaxis(); left.set_title("Fixed work: 16 tasks, 4 slots", fontsize=16, pad=20, weight="bold")
    for y, value in enumerate(values):left.text(value + .045, y, f"{value:.3f}", va="center", fontsize=14)
    style(left)
    for index, (variant, label, color) in enumerate(zip(variants, ["Fresh", "Persistent", "Persistent + subscription"], ["#b77b22", "#7050df", "#16856f"])):
        ys = [next(r["mean_router_fixture_turns"] for r in events if r["variant"] == variant and r["followups_per_task"] == f) for f in [0, 1, 8]]
        xs = [x + (index - 1) * .24 for x in range(3)]
        right.bar(xs, ys, width=.215, color=color, label=label)
        for x, y in zip(xs, ys):right.text(x, y + .8, str(int(y)), ha="center", fontsize=13)
    right.set(ylim=(0, 44), ylabel="Router fixture turns", xlabel="Follow-up events per task")
    right.set_xticks(range(3), ["0", "1", "8"]); right.set_yticks([0, 10, 20, 30, 40])
    right.set_title("Event workload: 4 tasks, 4 slots", fontsize=16, pad=20, weight="bold")
    right.legend(loc="lower center", bbox_to_anchor=(.5, 1.15), ncol=3, fontsize=11.5, frameon=False, columnspacing=.9)
    style(right, "y")
    fig.text(.035, .09, "Preset work units isolate scheduling and event-delivery behavior. Real coding scores are reported in separate experiments.", fontsize=12.5, color="#5b6472")
    fig.text(.035, .035, "The event workload performs the same amount of Worker work in every condition; fixture turns are not API calls or tokens.", fontsize=12.5, color="#5b6472")
    save(fig, "system-mechanisms")

    data = {"matplotlib": matplotlib.__version__, "sources": {key: {"path": name,
        "sha256": hashlib.sha256((ROOT / name).read_bytes()).hexdigest()} for key, name in SOURCES.items()},
        "m2_primary": pilot, "m2_successful_task_ids": successful_ids,
        "model_capability": capability, "system_capacity": capacity, "system_events": events,
        "notes": ["M2, capability and system tracks retain separate models, code versions and evidence scopes.",
            "No inference, new benchmark runs, confidence intervals or causal architecture rankings are produced by this script.",
            "System fixture turns are not actual model calls. All plotted quantitative axes include zero."]}
    (OUT / "plotted-values.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"figures": 3, "m2_primary_grades": 60, "independent_m2_tasks": 4,
        "capability_runs": 9, "new_model_API_calls": 0, "frozen_inputs_modified": False}))


if __name__ == "__main__":main()
