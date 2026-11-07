<p align="center">
  <img src="docs/images/opensuperagent-logo-tile.png" alt="OpenSuperAgent logo" width="88" height="88">
</p>
<h1 align="center">OpenSuperAgent</h1>
<p align="center"><strong>An open framework and benchmark suite for persistent, event-driven multi-agent systems</strong></p>
<p align="center">
  English · <a href="README.zh-CN.md">简体中文</a> ·
  <a href="docs/getting-started.md">Quick start</a> ·
  <a href="docs/results.md">Results</a>
</p>

OpenSuperAgent implements a task-level Router–Worker architecture inspired by DeepSeek's public Super-agent prototype. A persistent Router assigns requests to Workers with independent sessions and workspaces. Thread subscriptions carry relevant follow-up events to the Workers already handling the tasks. The **Framework** runs this design. The **Evaluation Suite** measures how it compares with ordinary delegation under the same model and budget.

[![Super-agent architecture showing a persistent Router, task journal, separate Workers and the subscription path for follow-up events](docs/architecture/overview.png)](docs/architecture/overview.svg)

## Why persistent coordination?

Parallel delegation is useful when tasks arrive together. A persistent Router retains context across arrivals, and a subscribed Worker can receive a later update directly. We measure when these mechanisms improve completion, latency or token use. The five task-level schedulers share a coding Worker so their coordination choices can be compared.

[![Comparison of Single, Single with Subagent, Eager Delegation, Router–Worker and Super-agent](docs/architecture/comparison.png)](docs/architecture/comparison.svg)

[Architecture and upstream design mapping](docs/architecture/README.md)

## Watch a run

[![Recorded mechanism demo. Two Workers run in parallel, a second process restores the journal, and subscriptions deliver two follow-ups.](docs/architecture/event-demo.gif)](docs/architecture/event-timeline.svg)

**32-second replay of a deterministic run.** Two Workers execute concurrently, save their state, and receive follow-ups in a second process. The animation uses recorded timestamps and has zero model API calls. [Trace, static timeline and replay instructions](docs/architecture/README.md#recorded-demo)

**Real coding case.** A Qwen Worker fixed OpenLibrary's table-of-contents handling in an Eager Delegation run. The captured patch passed 13/13 required tests and scored 1 in the original Harbor evaluator. [Instruction, actual actions, patch and replay](docs/case-studies/openlibrary.md)

## What ships

| Directory | What it runs |
| --- | --- |
| [`research/`](research/START-HERE.md) | **Framework.** Task-level Router–Worker runtime, common Worker, and archived experiment evidence |
| [`suite/`](suite/README.md) | **Evaluation Suite.** Frozen manifests, five controlled arms, native benchmark adapter and reports |
| [`src/`, `server/`, `public/`](docs/getting-started.md#web-workspace) | **Web Workspace.** Browser UI with a separate local executor |
| [`docs/`](docs/architecture/README.md) | Architecture figures, runnable demo and user guides |

## Quick start

From the checkout root with Python 3.11+, run the deterministic demo with the standard library. Use a new output directory each time.

```bash
python docs/architecture/run_demo.py --output osa-demo
```

The run records two separate process receipts, Worker activity and subscription delivery. [Install the evaluation CLI and inspect a benchmark plan](docs/getting-started.md)

## Benchmark results

[![Historical SWE-bench Pro pilot showing success rate, mean batch time and API tokens](docs/results/benchmark-pilot.png)](docs/results/benchmark-pilot.svg)

The controlled pilot used Qwen3-Coder-30B-A3B-Instruct with source022 on **4 tasks × 3 paired seeds**. Eager Delegation and Single + Subagent each resolved 3/12 task–seed runs, and Super-agent resolved 2/12. All successes came from OpenLibrary. [Result tables, paired outcomes and the other measured studies](docs/results.md)

Stage 2 has a 120-task independent Pro V2 candidate subset and a 19-task AsynCodeBench native plan. Live scores are pending environment admission. [Benchmark design, baselines and protocol boundaries](docs/benchmarks.md)

## Reproduce the results

- [Replay the captured OpenLibrary patch with the official evaluator](research/public-example/README.md)
- [Regenerate published charts from the frozen result tables](docs/results/README.md)
- [Plan and run Stage 2 with the Evaluation Suite](suite/README.md)

## Implementation status

| Capability | Evidence |
| --- | --- |
| Task dispatch and parallel Workers | Implemented at task level and exercised in benchmark runs and system tests |
| Persistent Router and subscriptions | Implemented, with deterministic tests and limited model-run evidence |
| Native role workspace boundaries | Exact-path editing and private reads checked in Docker fixtures. Live Stage 2 acceptance is pending |
| Process recovery | Demonstrated from a safe persisted checkpoint |
| Full Watchdog, recursive delegation, DSH host integration | Planned |

[Detailed implementation status and evidence](docs/implementation-status.md)

[Research archive](research/START-HERE.md) · [Citation and upstream references](docs/architecture/README.md#citation) · [MIT license](LICENSE) · [Third-party notices](research/reproduction/THIRD-PARTY-NOTICES.md) · [Contributing](CONTRIBUTING.md)
