# Benchmark design and reproducibility

## Task capability and efficiency

| Benchmark | Scope | State |
| --- | --- | --- |
| SWE-bench Pro V2 | 24-task diagnostic, then 120-task independent candidate subset of the 642-task release | Frozen model and Worker selected. Live Stage 2 results pending |
| Terminal-Bench 2.0 | 89 terminal tasks | Adapter and environment validation pending |
| SWE-bench Verified | 500 tasks, subject to budget | Deferred |

The primary Pro comparison pairs five architectures and two seeds over the
120-task candidate subset. Its 1,200 task–seed–architecture runs have a theoretical
2.4B token ceiling. The exclusion audit and admission gates precede execution.
A third seed remains a prospective independent replication. Report the selection
and seed plan before seeing its results. Task length and keyword strata are
selection proxies. Claims about decomposability or dependency depth require
independent annotation or an executable task graph.
[Frozen Pro manifest](../suite/manifests/pro120.json) ·
[Official Pro V2](https://labs.scale.com/leaderboard/swe_bench_pro_public_v2) ·
[Terminal-Bench 2.0](https://github.com/laude-institute/terminal-bench-2/tree/2fd12b88aafdd04a52c298e3940bcb189f9766d6)

## Asynchronous collaboration

**B1, native evaluation.** Start with the official `async_private` protocol on
all 19 tasks. Preserve released roles, worktrees, permissions, dependency
checkers, integration order and scoring. Report final success, test pass rate,
asynchronous dependency pass rate, dependency resolution step and resources.
Coverage of the remaining official protocols is a separate extension.

**B2, controlled coordination.** The released assignment hook replaces a
specialist Worker while the harness controls coordination. A coordinator hook
must demonstrate that dispatch decisions genuinely vary by architecture and
that task, access, communication and integration semantics remain fixed. The
five official protocols and the five OpenSuperAgent arms are separate axes.

**Async-RBench.** A paired Linear/Async comparison depends on the official Judge
Bundle and its certification. Keep replanning, response, recovery and repeated
work separate. Official scores are pending external Judge access.
[AsynCodeBench pin and adapter contract](https://github.com/KaituoZhang/AsynCodeBench/blob/2a639b049f249e79eb2031876bc06a110be9ac3a/docs/AGENT_ADAPTER.md) ·
[Async-RBench Judge Bundle](https://github.com/pope8zdt/Async-RBench/blob/main/docs/judge-bundle.md)

## Real-model mechanism tests

Cross fresh and persistent Router history with subscriptions off and on.
The task registry persists in all four conditions. Pair the same Worker's
inputs, tools, events and complete-task token allowance. Planned event cases
include no follow-up, low and high frequencies, a dependency update and a
Worker failure/recovery. Report success, coordination tokens and latency by
event condition. The existing deterministic fixture results describe mechanisms.
[C0–C3 protocol](../suite/PROTOCOL.md) · [Measured system fixtures](results.md#deterministic-system-measurements)

## Baselines and reporting

**Controlled Architecture Comparison** uses Single, Single + Subagent, Eager
Delegation, Router–Worker and Super-agent with a shared Worker. The budget covers
the whole task, including Router and specialist requests and retries.

**End-to-End System Comparison** preserves each external agent's native prompts,
tools and stopping rules. The common model, tasks, permissions and resource
ceilings must be verified before a system enters the matched comparison.

| External baseline | Evidence |
| --- | --- |
| [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) | Three-task model-selection pilot, full comparison pending |
| [SWE-agent](https://github.com/SWE-agent/SWE-agent) | Planned adapter and equal-resource verification |
| [OpenHands](https://github.com/OpenHands/OpenHands) | Planned end-to-end comparison. The native SDK integration serves a different role |
| [LangGraph Supervisor](https://github.com/langchain-ai/langgraph-supervisor-py) | Planned alternative coordinator comparison |

Separate result tables by benchmark, protocol and experimental track. Use task
and repository clustered intervals for paired comparisons, with repeat seeds
nested inside tasks. Include paired success counts, tokens, p50/p95 completion
latency, invalid attempts, and runnable provenance. Analyze differences in
Success–Cost–Latency with the same denominator and resource definitions.
[Stage 2 preregistration](../suite/PROTOCOL.md) · [Results and reproduction](results.md)
