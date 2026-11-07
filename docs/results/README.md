# README result figures

The homepage figures are generated from published experiment tables already in
this repository. The three experiments retain their own models, tasks, budgets,
execution versions, and evidence scopes.

## Regenerate

From the repository root, with Python 3.12 and Matplotlib 3.9.2:

```bash
python -m pip install matplotlib==3.9.2
python docs/results/build_figures.py
```

The script generates three PNG/SVG pairs and
[plotted-values.json](plotted-values.json). It performs no model inference and
does not modify the source tables. SVGs contain font outlines for portability.
The JSON records the input SHA256 hashes and exact plotted values. Different
Matplotlib versions may change the layout.

## Benchmark pilot

[PNG](benchmark-pilot.png) · [SVG](benchmark-pilot.svg) ·
[M2 report](../../research/M2-REPORT-003.md)

- Source tables: `research/tables/batches.csv` and `cases.csv`, primary rows only.
- Five architectures, the same four tasks, three paired seeds: 15 batches and
  60 task grades; each architecture has 12 task–seed outcomes.
- Model: Qwen3-Coder-30B-A3B-Instruct. Execution version: source022.
- Success rate is the accepted successful task grades divided by 12.
- Batch time is the arithmetic mean of the three Agent batch clocks, converted
  to minutes. It includes queueing and coordination; official grading is timed
  separately.
- Tokens are the sum of input and output API tokens across the three accepted
  batches, including Worker and coordination requests. Service admission,
  secondary reference runs, and infrastructure-invalid attempts are separate
  entries in the original cost records, outside these primary-only totals.
- Frozen report rules govern infrastructure exclusions and coding-failure
  adjudications. This script uses the published accepted rows.
- All successes concern OpenLibrary, one of the four independent tasks.
  Repeated seeds preserve the same task identities. The figure is descriptive;
  no confidence interval or statistical architecture ranking is estimated.

## Model capability pilot

[PNG](model-capability.png) · [SVG](model-capability.svg) ·
[M3-A3 report](../../research/studies/m3-a3/README.md)

- Source: `research/studies/m3-a3/CAPABILITY-RESULTS.csv`, nine admitted runs.
- Three tasks, one seed; a 2M-token per-task allowance and a 100-call limit.
- Qwen30B/shared Worker, Next/shared Worker, and Next/mini-swe-agent retain the
  published model/agent identities. The shared Worker is source025; mini-swe-agent
  retains its pinned original prompts and tool conventions.
- Bars are the required-test pass fractions **within each task**. Labels show
  passed/required counts. Fractions are not pooled across tasks with different
  test counts.
- Full-task success requires every required test to pass: 0/3, 1/3, and 0/3
  respectively. Human counterfactual fixes and infrastructure-invalid attempts
  are outside this figure.

## System mechanisms

[PNG](system-mechanisms.png) · [SVG](system-mechanisms.svg) ·
[System report](../../research/studies/m3-a3/SYSTEM-REPORT.md)

- Sources: `research/studies/m3-a3/system-capacity.csv` and `system-events.csv`.
- The left panel selects 16 fixed tasks and four execution slots; each bar is
  the mean of three repetitions.
- The right panel selects four tasks/four slots, with 0, 1, or 8 follow-up events
  per task. Each bar is the mean of three repetitions. Every condition executes
  the same `4 × (1 + followups)` fixed Worker work units.
- Router fixture turns count calls to the deterministic model fixture. Actual
  model API calls and tokens are zero. These are system-mechanism measurements;
  the separate real-model experiments report coding success.
- The source025 implementation and the original measurement host are recorded
  in the linked report and environment evidence. A local remeasurement may
  have different timing.

## Current study boundary

The interrupted M3-B1 attempt and its later zero-model artifact checks are not
included in these charts. Its original accounting gate stopped the campaign;
a completed five-architecture comparison has not been released.

中文：首页图表分别展示真实 Benchmark、模型能力校准和确定性系统测量。
每组保留原模型、版本、任务与预算；所有数值均可由上述公开表格重算。
坐标轴从零开始，配对种子按原任务身份保留，图中没有新增推理或补造结果。
