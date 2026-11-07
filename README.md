<p align="center">
  <img src="docs/images/opensuperagent-logo-tile.png" alt="OpenSuperAgent logo" width="96" height="96">
</p>
<h1 align="center">OpenSuperAgent</h1>
<p align="center"><strong>Reproducible experiments on multi-agent coding systems.</strong></p>
<p align="center">
  English · <a href="README.zh-CN.md">简体中文</a> ·
  <a href="research/reproduction/INSTALL.txt">Reproduce</a> ·
  <a href="research/START-HERE.md">Research overview</a>
</p>

OpenSuperAgent studies whether persistent, event-driven coding agents improve on ordinary delegation. We publish benchmark scores, execution traces, and token accounting for five controlled schedulers sharing a coding kernel.

## Benchmark results

Click a chart for its full-size SVG.

[![Five-architecture benchmark pilot: success rate, mean batch time and total API tokens](docs/results/benchmark-pilot.png)](docs/results/benchmark-pilot.svg)

**The pilot has not established a Super-agent advantage.** Eager Delegation and Single + Subagent each resolved 3/12 runs; Super-agent resolved 2/12. This is a descriptive comparison of **4 independent tasks × 3 paired seeds**, using Qwen3-Coder-30B-A3B-Instruct and frozen source022. All successes came from one task, OpenLibrary.

[Full report and scoring evidence](research/M2-REPORT-003.md) · [Figure data and definitions](docs/results/README.md)

## Model capability

[![Required-test pass counts for Qwen30B with the shared Worker, Next with the shared Worker, and Next with mini-swe-agent](docs/results/model-capability.png)](docs/results/model-capability.svg)

With the same shared Worker, Qwen3-Coder-Next resolved **1/3 tasks**, versus **0/3** for Qwen30B. Next + mini-swe-agent also resolved 0/3, while passing more qutebrowser tests. These **three tasks and one seed** support a model-selection pilot; broader model and framework comparisons remain open.

[M3-A3 results, trajectories and budgets](research/studies/m3-a3/README.md)

## System measurements

[![Deterministic system measurements: batch time for 16 tasks and Router fixture turns under follow-up events](docs/results/system-mechanisms.png)](docs/results/system-mechanisms.svg)

At 16 tasks and 4 slots, Eager Delegation took **0.540 s** and Super-agent **0.542 s**. In the 36-event workload, subscriptions reduced Router fixture turns from **36 to 4**. These measurements use deterministic Workers, three repetitions, and **zero real model API calls**; real coding outcomes are reported above.

[System Track report](research/studies/m3-a3/SYSTEM-REPORT.md) · [Raw tables and figure-generation script](docs/results/README.md)

## Reproduce and explore

- **Get started:** [installation and zero-key checks](research/reproduction/INSTALL.txt).
- **Reproduce experiments:** [historical five-architecture benchmark](research/reproduction/INSTALL-M2-source022.txt) · [current Worker and patch replay](research/reproduction/RUN-CAPABILITY.md) · [native benchmark runbook](research/NATIVE-RUNBOOK.md).
- **Read the methods:** [research scope](research/START-HERE.md) · [architecture comparison protocol](research/PROTOCOL.md) · [figure sources and regeneration](docs/results/README.md).

**Current status:** Worker calibration is closed; Next + source025 is the candidate for the larger fixed-task comparison. The first M3-B1 attempt stopped after a model-request timeout left usage uncertain. A completed new five-architecture comparison is not yet published. [Study plan](research/studies/m3-b1/README.md).

Research preview. This is an independent task-level implementation inspired by [DeepSeek's public prototype](https://github.com/deepseek-ai/dsh-superagent-prototype), with no affiliation. Full DSH hosting, full Watchdog behavior, and recursive within-task delegation remain documented integration work. The earlier [workspace UI](docs/getting-started.md) has its own executor.

[MIT License](LICENSE) · [Third-party notices](research/reproduction/THIRD-PARTY-NOTICES.md) · [Contributing](CONTRIBUTING.md) · [Logo](docs/BRANDING.md)
