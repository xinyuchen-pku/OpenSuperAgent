# Stage 2 — OpenSuperAgent Comprehensive Evaluation

**Research question:** under equal model, tools and total compute ceilings,
where do task-level Super-agent mechanisms improve quality, cost, or latency?
An unfavorable result is an outcome. Protocol and resource failures are stop gates.

This protocol supersedes Stage 1 planning for new campaigns. Historical M2–M3
snapshots, outcomes and budget rules remain unchanged and separately identified.
The suite implements public-design task-level controllers; full DSH hosting,
Watchdog behavior and recursive within-task decomposition remain open work.

## Tracks and attribution

1. **Controlled architecture:** common source025 Kernel, Worker prompt, tools,
   context policy, model and total task budget. Pro batches have four simultaneous
   public requests and four available execution/model slots for every arm.
2. **Native capability:** official AsynCodeBench orchestration and scoring with
   the common Worker assignment adapter. This answers whether that Worker can
   execute the original collaboration assignments. It does not replace managers.
3. **Native full-Agent comparison:** mini-swe-agent and benchmark reference agents
   retain their own prompts/tools/termination and run as separately named agents.
   Their full-task spending must use the same admission ledger, including every
   condenser and manager request. Existing M3-A3 results are historical pilot data;
   this suite has not admitted a new full-Agent campaign yet.
4. **Mechanism extensions:** C0–C3 and E0–E4 use a separately frozen event stream.
   Additional events never silently enter an official benchmark condition.
   Unit fixtures establish routing contracts; real-model benefits await real runs.

## Frozen common candidate

Qwen3-Coder-Next revision `a7fbcb5c0e12d62a448eaa0e260346bf5dcc0feb`,
BF16 TP4, context 262144, four serving sequences, prefix cache disabled.
Temperature 0.7, top-p 0.8, top-k 20, repetition penalty 1.05,
8192 maximum output tokens. Paired seeds 20261107/20261108 for Pro;
the first native full-19 campaign uses 20261107. Online batching may diverge even
when task input and seed match. Keep first full responses and provider counters.

source025's 43 files and 25 package modules remain byte-identical to tree
`5594a771aca46709ae4837aecc2b477dec15138510167842c8083f9bf484112f`.
The new controller and accounting layer have their own immutable suite lock.
There is no cachetools prompt adjustment or hidden-test-driven Worker repair.

The uniformly applied HTTP timeout is 1800 seconds. The previous 600-second
timeout left one paid B1 request without an individual receipt; its old run and
unknown usage remain preserved. This transport change precedes new outcomes.

## Task-level architecture definitions

| Arm | Routing history | Execution | Subscription |
|---|---|---|---|
| Single | No routing call | One serial main execution; separate history per independent task | Off |
| Single + Subagent | Fresh main routing context per event | Chooses main or delegate; one main at a time; shared slot ceiling | Off |
| Eager Delegation | Fresh main routing context | Mandatory delegation of independent supplied tasks | Off |
| Router–Worker | Fresh Router per event | Mandatory delegation, private Worker histories | Off |
| Super-agent | Persistent Router history | Same asynchronous Workers and slot ceiling | On |

The main routing prompt for Subagent/Eager uses the frozen Worker system prompt;
Router–Worker/Super use the same frozen Router prompt. Record this distinction.
All coding Worker histories start with the same source025 prompt and public
instruction, including main execution. This differs from historical Stage 1,
which retained shared main histories across independent tasks. Do not pool the
two controller versions. Eager here is supplied-task delegation, not an invented
within-task parallel coding planner. Pro evaluates independent-task scheduling.
Dependent collaboration needs the separate native/dynamic track below.

## Full-task budget and time

The task key includes benchmark task, architecture/protocol and seed. **Two million
actual API tokens per complete logical task** includes Router, all assignments,
retries, and output. Shared process-safe SQLite admission uses serving-tokenizer
prompt count plus maximum output. Completed receipts release unused reservation.
Publish actual input/output tokens, cumulative reservations, outstanding bounds,
denied calls, context length, termination and artifact state.

The campaign ledger lives outside attempt directories and survives shards/retries.
An uncertain request retains its bound, invalidates the campaign and stops further
admission. Provider aggregate deltas remain diagnostic; they do not create a
missing per-request receipt. Preserve all invalid attempts and their observed cost.

Pro retains 1 CPU / 4096 MiB per task and its original 3000-second agent and
verifier limits. Router inference/queue time reduces that task's active Worker
allowance. External task queue time contributes to completion latency. The same
four CPU indices and inference capacity are available in every architecture;
Single's unused parallel capacity is reported, not silently reassigned.

At the Pro task deadline the Worker stops and the runner captures the patch.
An already admitted request keeps its model slot until its actual usage arrives.
The runner discards its late response and charges its actual tokens to the
original task before accepting the batch. Cancellation before admission stops
the pending request. A missing usage receipt still invalidates accounting.
The batch reports receipt drain time separately within post-execution overhead.

Native AsynCodeBench keeps released scenario decomposition, writable paths,
communication, integration order, Dependency Checkers and final evaluator.
The assignment layer preserves exact-path editing and isolates each role's
read-only worktree and shallow Git metadata. The legacy read-only mount exposed
sibling worktree paths; the new private-read probe must pass before model calls.
The original harness is still the integrator, and its source is unchanged.
Its standard profile permits 100 responses per model-facing assignment and two
chat rounds. The added 2M total-task token ceiling is a declared experiment
condition. The common specialist active timeout is 3000s. SDK/scope-container
resources and setup time need measured evidence; Pro limits are not presumed
to be native requirements. Zero USD is a self-hosted accounting convention;
tokens and GPU service residence carry the measured resource cost.

## Benchmark versions and schedule

| Stage | Frozen scope | Theoretical task-token ceiling | Execution state |
|---|---|---:|---|
| S2.0 | Protocol, code, model, task and scorer identities | Admission separately charged | Local candidate; live admission pending |
| S2.1 | Original24 × five arms × two seeds | 480M | Diagnostic, paired randomized order |
| S2.2 first | All19 AsynCodeBench, async_private, one seed | 38M | Official dry-run complete; image/runtime gates pending |
| S2.2 comparison | All19, same fixed native protocol across controllers | Unfrozen until coordinator hook is valid | Interface gap documented below |
| S2.3 | Independent stratified120 Pro × five arms × two seeds | 2.4B | Candidate sample; final exclusion/admission gate pending |
| S2.4 | Async-RBench200, eight scenarios | Freeze after Judge certification | External Judge pending |
| S2.5 | Terminal-Bench2.0@89 | Freeze after oracle/empty gates | Adapter and environment pending |
| P2 | SWE-bench Verified500 | Separate preregistration | Deferred |

Native full19 preparation is the first execution priority; Pro preparation proceeds
independently. These are ceilings, not measured spending or a claim of completed
evaluation. Current native service guard ceiling is 24h / 96 GPU·h (TP4), including
startup, admission and shutdown. Pro diagnostic/confirmatory ceilings are 100h /
400h of campaign execution respectively; a resource guard must enforce service
residence independently, including retries. Those stages require renewed live
admission against the frozen site and their own ledger.
Provider controls have a separate maximum of 10K tokens in the same campaign
ledger. Arm order is randomized within each four-task block and seed, before
selecting any execution shard.

Sources: [official Pro V2](https://labs.scale.com/leaderboard/swe_bench_pro_public_v2),
[Pro commit](https://github.com/scaleapi/SWE-bench_Pro-os/tree/66f92766bba642462d4bbe5479e83f91f9211862),
[AsynCodeBench release](https://github.com/KaituoZhang/AsynCodeBench/tree/2a639b049f249e79eb2031876bc06a110be9ac3a),
[Terminal2 dataset](https://github.com/laude-institute/terminal-bench-2/tree/2fd12b88aafdd04a52c298e3940bcb189f9766d6).
Pro/Asyn main heads were rechecked on 2026-11-07; they match the previous pins.

## Native coordination boundary

The official [custom-adapter contract](https://github.com/KaituoZhang/AsynCodeBench/blob/2a639b049f249e79eb2031876bc06a110be9ac3a/docs/AGENT_ADAPTER.md)
assigns decomposition, worktrees, communication, ordering, merge and scoring to
the harness. `AgentAdapter.execute` owns one coding assignment. Repeating this
adapter under five architecture names would still use the same coordinator.
The five official protocols are an independent benchmark axis: four standard
protocols plus online `async_manager`. The latter's current budgeted profile is
v4, distinct from the older v3 online profile; both are retained as source data.

This version admits `async_private` only for the full19 campaign. It refuses
manager protocols while manager/condenser API usage lacks common admission.
The four TVM PR-hard tasks retain the official 28-CPU workspace quota and
offline command policy. The specialist shell can write build outputs in its
own prebuilt cache directory. Its source tree and shallow Git snapshot are
read-only, and other specialists' caches and worktrees are hidden. The
`pr-hard:` request identifier maps to the released `asyncodebench:` task key
in the shared token ledger.
A same-protocol architecture comparison requires a verified orchestration hook
that preserves all released information/authority/checkpoint rules. If a harness
extension is necessary, version it and label it separately from native official
execution. No protocol-to-architecture mapping is allowed.

Async-RBench requires the separately delivered `command-boundaries-v1` runtime
Judge: [official access and compatibility instructions](https://github.com/pope8zdt/Async-RBench/blob/56c25554768a7eeb9b493361f4243ef330dbff8b/docs/judge-bundle.md).
Public cases alone provide no official scores. Runtime boundary scoring differs
from the paper's hidden weighted ERCs; preserve that distinction and the metric
namespace. **AsynCodeBench DRS means Dependency Resolution Step; Async-RBench
DRS means Dynamic Replanning Score.**

## Causal mechanism cells and events

| Cell | Router model history | External durable task/event registry | Subscription |
|---|---|---|---|
| C0 | Fresh | Yes | No |
| C1 | Persistent | Yes | No |
| C2 | Fresh | Yes | Yes |
| C3 | Persistent | Yes | Yes |

Keep Router prompt, async Worker, task/compute caps, event timestamps and
registry implementation fixed. Measure persistence, subscription and interaction
effects on real model cost, latency and task quality. C2 uses the same SQLite
subscription registry as C3, without persistent Router messages.
E0 no follow-ups; E1 sparse follow-ups; E2 frequent follow-ups; E3 changed
dependency state/replanning; E4 failure/restart. Freeze exact events and fault
identities before model outcomes. Safe-point recovery and uncertain-side-effect
reconciliation are distinct; current source025 fails closed on uncertain effects.
Real-model E0–E4 event runner and task-level quality acceptance remain pending.

## Independent sample and inference

The entire original24 is excluded from the confirmatory sample. The inventory
checked 393 admitted-call journals in 3499 operational directories; all eight
observed Pro IDs are among those24. Archived-only attempts and any newly exposed
development task must be reconciled before confirmatory admission.

Sampling uses repository, language and prespecified public-instruction proxies:
word-count thirds for complexity; explicit dependency/coupling terms, multiple
source-path mentions, or unspecified text for parallelizability. Thresholds are
computed on the public population without new outcomes. One task per nonempty
stratum, then proportional largest-remainder allocation, then seeded SHA256 rank.
The candidate has 86 strata, 11 repositories, 47 Go / 39 Python / 31 JavaScript /
3 TypeScript tasks. Rare strata are oversampled. Inclusion probabilities are
recorded. Primary sampled-task estimates describe this preregistered subset;
full-population estimates require design weights and separate analysis.
The proxies describe textual features, not established semantic parallelism.

Report paired success/failure cross tables, per-seed results, task-cluster and
repository-cluster percentile CIs with seeds kept within a task. A task repeated
under two seeds remains one unique task. Show per-task cost/latency differences,
repository exceptions and concrete failure sequences. Main quality is official
success plus required/partial tests; native ADPR/DRS use official definitions.
Efficiency includes observed completion p50/p95, actual tokens and successful
tasks per observed batch hour. Keep Router/Worker calls and tokens, event/message
counts, waits, budget exhaustion, timeouts, duplication/conflicts and recovery.
Success–Cost–Latency Pareto plots require balanced valid task/seed intersections.
Always display invalid attempt counts, observed cost and unresolved upper bounds.

## Acceptance and stop policy

Before inference: verify frozen installed Worker/suite/benchmark/scorer bytes;
resolve official image manifests and SDK derivation; enforce actual resources;
check task/model network and credential separation; pass official dry-run,
scope/Git identity preflight and token-capped provider controls; bind the live
receipt to manifest/site/lock hashes and the verified resource guard.

After each run: retain original native bundle or Pro official Harbor score,
independent replay where implemented, structured model/tool/event envelopes,
complete ledger and provider reconciliation. Grade failure, coding failure and
invalid infrastructure are separate states. Native bundle validation checks
instrumentation and checksums; independent native regrading is still pending in
this version and remains explicitly null. No full19 or five-arm score is claimed
until the corresponding evidence is complete.
