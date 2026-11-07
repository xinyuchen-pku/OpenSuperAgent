# Implementation status

| Capability | Status | Evidence and scope |
| --- | --- | --- |
| Task dispatch and bounded parallel Workers | Implemented | Five-arm task-level runs and measured concurrency fixtures. [Benchmark pilot](../research/M2-REPORT-003.md) · [System Track](../research/studies/m3-a3/SYSTEM-REPORT.md) |
| Persistent Router history | Implemented | Saved sessions and deterministic mechanisms. Quality and cost effects under real event loads are open. [Protocol](../suite/PROTOCOL.md) |
| Thread subscription | Implemented | Deterministic direct delivery and limited real-model follow-up evidence. [Recorded demo](architecture/README.md#recorded-demo) |
| Role-scoped editing and reading | Partial live coverage | Prior native scope checks exercise exact-path editing. Stage 2 adds private role mounts and a shallow isolated Git baseline, checked with Docker/Git fixtures. [Stage 2 validation](../suite/VALIDATION.json) |
| Cross-process recovery | Partial | Safe idle checkpoint and duplicate-event handling demonstrated. Interrupted external side effects require reconciliation. [System Track](../research/studies/m3-a3/SYSTEM-REPORT.md) |
| Native AsynCodeBench integration and grading | Adapter available | Official harness owns tasks and integration. Stage 2 full-19 real-model runs await environment admission. [Native scope](benchmarks.md#asynchronous-collaboration) |
| Replace the native coordinator | Pending | The assignment adapter provides a Worker hook. A separately validated coordinator interface is required for native architecture comparison. [Protocol](../suite/PROTOCOL.md#native-coordination-boundary) |
| Public DeepSeek Engine adapter | Partial | Original core, repositories and lifecycle connected in the pinned reference experiment. [M2 report](../research/M2-REPORT-003.md) |
| Full Watchdog, recursive task decomposition and DSH host | Planned | Current task-level time limits and safe restart are the implemented subset. [Research scope](../research/START-HERE.md) |

The Framework and Evaluation Suite are built around the research runtime. The
Web Workspace is a separate local application with its own runtime, tool set
and usage guide. [Web Workspace](getting-started.md#web-workspace)
