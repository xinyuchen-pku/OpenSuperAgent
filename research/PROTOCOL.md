# Super agent reproduction and evaluation protocol

Stage 1 asks where Super-agent architectures help, what resources they consume,
and which architectural mechanisms account for any difference. The study does
not presuppose an advantage, a defective module, or a new method.

This protocol is a working specification. Its source and workload identities
can be frozen before a campaign; environmental gates and implementation scope
must be established by actual runs. A repository skeleton or model completion
message does not provide those measurements.

The current execution milestone is M2: four fixed Pro tasks, three seeds,
five controlled architectures, and simultaneous four-task arrival; at least
one complete native AsynCodeBench task and validated run bundle. Larger loads,
additional benchmarks, new methods and extra agent modules remain deferred.
The first seed's twenty grades are reviewed before further seeds when all fail.

## Implementations and attribution

Maintain two separately identified paths:

1. **Source-faithful reference.** Pin DeepSeek's public prototype at
   `6337fc823ce20251c8de8085948165c81aaa701e`. Preserve its domain rules,
   subscriptions, reports, retry behavior, and resource policy. Record every
   replacement port or disabled integration. The current bridge executes the
   real domain core; DSH host scheduling, model sessions, background jobs, and
   native deployment equivalence still require validation.
2. **Controlled implementations.** Use one model adapter, base worker prompt,
   tool executor, environment contract, and accounting implementation. Change
   the declared orchestration factors. Report controlled results separately
   from native upstream results.

The public prototype differs from DeepSeek's internal system and includes
design ideas whose implementation status differs from the associated article.
Claims about fidelity refer to the inspected public code and explicit contract
tests. [Upstream description](https://github.com/deepseek-ai/dsh-superagent-prototype/tree/6337fc823ce20251c8de8085948165c81aaa701e)

| Condition | Task-level implementation | Additional acceptance work |
|---|---|---|
| A Single | Requests execute serially in one retained main session | Verify multi-task context and queue latency on real tasks |
| B Single plus Subagent | Main session chooses direct execution or a private worker session | Add and test within-task decomposition/delegation before claiming the general baseline |
| C Eager Delegation | Persistent main session must delegate each independent request | Add within-task eager decomposition and result synthesis, under the same information contract |
| D Static Router Worker | Fresh router history for each event, isolated worker session per task | Validate deterministic/fixed-router ablation separately from LLM-router overhead |
| E Super agent | Retained router history, asynchronous workers, durable subscriptions and event delivery | Complete report-driven coordination, recovery, hand-back, cancellation, and host-fidelity tests |

Task-level delegation is a declared implementation scope. Report it as such.
Before making claims about more general multi-agent coding, implement private
subtask workspaces, controlled integration, nested resource accounting, and
equivalent information availability for all applicable conditions.

## Benchmarks and tracks

### Track A Single task capability

Start with SWE-bench Pro V2. The pinned release contains 642 tasks; its agent
phase restricts network access, captures patches, and grades them in fresh
environments. Retain both any in-place result and the authoritative clean-image
result. Validate the chosen environment using empty/reference patches and
network/history probes. [Official V2 protocol](https://github.com/scaleapi/SWE-bench_Pro-os/blob/v2.0.0/v2/README.md)

The initial task manifest uses 24 public task IDs selected by ranking the SHA256
of the seed and ID, without consulting model outcomes. Preserve the selected
order and all attempted tasks. Use the first selected task for integration,
then expand only after the framework and scoring gates pass. Single-task
runs reset sessions; their results are separate from a multi-task retained
session experiment.

Add SWE-bench Verified and Terminal-Bench 2.1 as declared coverage extensions.
Pin their releases, images, evaluators, and task manifests before execution.
They are pending adapters in the current module.

### Track B Multi task load

Reuse the same software tasks and independent official tests. Distinguish
three variables:

| Variable | Suggested frozen levels | Meaning |
|---|---|---|
| Offered requests | 1, 4, 8, 16 simultaneous tasks; fixed and Poisson streams | External demand presented to each architecture |
| Execution slots | 1, 4, 8, 16 where the environment permits | Maximum active execution capacity |
| Model quota | Fixed concurrent calls, context, token/rate quota and serving topology | Shared inference capacity |

For each comparison cell, replay the identical task IDs, arrival timestamps,
follow-ups, seed, deadline and fault schedule. An independent producer records
arrival before the router processes it. Include queue time in end-to-end
latency. Completion-dependent task releases belong to a separately labeled
closed-loop experiment; they change the offered workload between systems.

For sustained load, determine rates from one common reference calibration and
freeze them for every condition. Do not retune rates separately to each
architecture. Record active inference, tool execution, session-lock waits,
queue waits and background work separately.

### Track C Async coordination and persistence

Use AsynCodeBench's 19-task stable release and its native dependency checkers.
Preserve private-worktree boundaries, changed-path validation, integration
checkpoints, test collection, and official run-bundle validation. Record the
actual execution profile chosen by code: the pinned release index names v2,
while the current budgeted `async_manager` entry selects v4.
[Native adapter contract](https://github.com/KaituoZhang/AsynCodeBench/blob/2a639b049f249e79eb2031876bc06a110be9ac3a/docs/AGENT_ADAPTER.md),
[validity rules](https://github.com/KaituoZhang/AsynCodeBench/blob/2a639b049f249e79eb2031876bc06a110be9ac3a/docs/RESULT_VALIDITY.md)

The benchmark's five native protocols and this study's five architectures are
different experimental axes. The native custom-agent interface executes one
assignment while the benchmark owns coordination. Replacing only that worker
does not implement a new manager. A controlled coordination extension needs a
new protocol ID, the same task/checker contracts, and independent validation;
publish its results separately from native official aggregates.

Report final success, ADPR, strict checkpoint-based DRS and unresolved
dependencies using the frozen native metric implementation. Preserve
checkpoint frequency; DRS is a logical checkpoint measure. Keep infrastructure
probe failures distinct from code-induced probe collection failures. Extend
to SWE-EVO after the primary tracks. Async-RBench remains supplementary until
the required complete evaluator/Judge access has been verified.

## Fairness controls

Freeze model weights or provider snapshot, tokenizer/template, precision,
generation parameters, worker prompt, tools, task inputs, evaluator, image
digests, seeds, CPU/RAM limits, model topology, and runtime source hashes.
Record active configuration and uncommitted file identities, not just a Git
commit. Keep model credentials outside task environments.

Run both comparisons:

- **Capacity matched:** identical execution/model quotas, workload, hardware
  assignment, and deadline. A single-session architecture may use less than its
  available ceiling. That utilization difference is measured.
- **Budget matched:** identical total token or monetary allowance, including
  every router, main, worker, subagent, retry, and failed request. Specify any
  additional resource/time ceiling explicitly.

The legacy token policy reserves a provider-context upper bound before each call.
M2's `exact_prompt_plus_max_output` policy instead reserves the next request's
serving-tokenizer input count plus maximum output allowance. Record both the
tokenizer receipt and API usage, including denied admissions and uncertainty.
The token ledger enforces one shared budget, including concurrent calls.
Known usage is charged even when output truncates.
Unknown billed requests retain their reservation and an uncertainty flag.
Report observed token counts and a conservative upper bound. A reservation
overrun invalidates accounting. Monetary cost for self-hosted models remains
unknown unless a declared pricing or measured infrastructure-cost convention
is supplied; report hardware residence and inference utilization separately.

The upstream prototype has an extra priority slot for human input and permits
worker subagents. Preserve and report that behavior in its native reference
run. In controlled comparisons count every active descendant and give every
condition the same global ceiling; disable or equalize priority exceptions.
[Upstream execution semantics](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/docs/003-execution.md)

Control serving caches, background load and arm order. Use paired task/seed
blocks with randomized or balanced arm ordering. Record prefix-cache state and
reset/disable it consistently when isolating architecture costs. Preserve
generation variability; a fixed seed does not guarantee bitwise identical
outputs under asynchronous GPU serving.

## Outcomes and analysis

An agent's final message is a completion claim. Success requires a separately
produced evaluator artifact with its source and content identity. Empty or
missing test collection requires diagnosis from the original compiler and probe
logs. A compiler failure caused by the submitted code remains a coding failure
in the denominator; environment or unresolved collection failures are marked
invalid with their raw evidence. Parser sentinel entries are not counted as tests.

| Family | Required output |
|---|---|
| Quality | Resolved fraction, independent grade, failure category and raw test evidence |
| Budget | Resolved at the frozen time/token/cost cutoff; all attempted work charged |
| Load | Resolved and submitted tasks per unit time, offered/active task count |
| Latency | Arrival-to-submission p50/p95 with completion fraction and censor counts |
| All tasks | Capped time in system including unfinished requests; infrastructure-invalid count |
| Resources | Input/output tokens by role, provider usage validity, model/tool calls, waits, CPU/GPU residence |
| Coordination | Dependency checkpoints, merge conflicts, scope violations, stale inputs, duplicate work and recovery |

Persist failure labels for code/test failure, model output limit, context or
step budget, malformed model action, routing error, integration/scope failure,
provider failure, environment failure and instrumentation failure. Include
valid coding failures in denominators. Preserve invalid runs and reasons;
repair infrastructure failures according to a predeclared retry policy.

Compare success versus cost, throughput versus execution/offered concurrency,
and completion time versus active tasks. Compute paired confidence intervals
by resampling task clusters, retaining paired seeds within each task. Label
small pilots as descriptive. Do not extrapolate a tiny coding fixture to public
benchmark performance or architectural superiority.

Interference has two reported components: observed cross-task artifact/state
violations, and paired changes from isolated task outcomes under matched
settings. A concurrent failure alone establishes an outcome; attributing it
to interference additionally needs trace or paired evidence.

## Ablations

Compare Single to Eager, Eager to Router Worker, and Router Worker to Super
agent under the same frozen controls. These are system contrasts; several
factors may differ simultaneously. For mechanism attribution add orthogonal
toggles for retained router history, subscription bypass, role isolation,
completion notifications, recovery, and priority exceptions. In the
no-subscription condition route the same follow-up payload through the same
model instead of dropping it. Vary slot limits separately from offered demand.

## Evidence gates and release

| Gate | Evidence required |
|---|---|
| G0 Provenance | Exact source/model/data/image/config/workload identities and licenses |
| G1 Runtime | Real model/tool transport, complete accounting and deterministic contract tests |
| G2 Environment | Actual network/history probes, isolated task state, explicit resource enforcement limits |
| G3 Evaluator | Empty patch fails, reference patch passes on selected pristine images; nonempty test evidence |
| G4 Architectures | Required delegation, events, recovery and report behavior demonstrated in real traces |
| G5 Pilot | Paired repeated tasks across five conditions with validated outcomes and all costs |
| G6 Analysis | Recomputed metrics, uncertainty, failure cases and declared limitations |
| G7 Distribution | Source/environment recipes, selection manifests, raw/derived artifacts, technical PDF and license review |

Keep the legacy UI/application and its existing behavior separate from this
research module. Preserve immutable source snapshots and failed attempts.
Publish source, configuration, trajectories and analysis only after the
specific branch/scope has been reviewed under the user's GitHub submission
rule. Publishing, merging and deployment have separate states.

The current Baidu integration uses one prepared Qwen3-Coder-30B-A3B-Instruct
model on a verified A100 GPU, a common 32,768-token context and four-request
serving ceiling. The temporary holder manager restores the original GPU
reservation and verifies 12 memory/utilization samples. Platform allocations
and other workloads remain preserved. Current Podman cgroup enforcement is
absent; any results obtained before that resource gate is resolved must state
the actual shared-host resource contract.
