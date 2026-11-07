# OpenSuperAgent research evaluation

This is an independent Stage 1 research module for reproducing and evaluating
Super-agent architectures. It has its own runtime and imports no code from the
repository's local-workspace application in `server/` or `src/`.

The current implementation supports five **task-level** controlled schedulers,
a common model/tool loop, transactional event/session/subscription storage,
global token reservations, traces, reproducible workload generation, comparison
checks, and grade-based metrics. Its upstream adapter executes DeepSeek's
pinned domain Engine directly. The DSH host scheduler and intra-task recursive
delegation remain integration work. See [the protocol](PROTOCOL.md) for the
precise scope and acceptance requirements.
See [the native execution runbook](NATIVE-RUNBOOK.md) for the required host,
pinned dependencies, actual remaining gates and separate native protocol axis.

## Local checks

Version0.1.1 adds two execution corrections: fully charged but truncated replies
and requests rejected before admission return the session to idle; unknown
provider outcomes remain pending for reconciliation. Truncated tool payloads
are rejected before execution. Recognized Python syntax/indentation failures
with zero collected tests receive a failed grade; unexplained empty results and
toolchain crashes remain invalid.

The optional `osa_eval/vllm_length_priority.py` launcher backports the length
priority portion of upstream vLLM PR59324 to one SHA-pinned vLLM0.20 serving
module. It changes the running service in memory and preserves installed files.
It fails closed on any other source hash. Run its `--contract-check PATH` before
launch and record live capped-response checks before benchmark requests.
All compared architectures must use the same corrected serving profile.

Python 3.11 or later is required. The core uses the Python standard library.
Run these commands from this `research` directory:

```console
python -m unittest discover -s tests -v
python -m osa_eval.cli smoke --output ./results/diagnostic-001
```

The smoke command uses a scripted model and no real shell. It checks runtime
wiring. It produces no official benchmark scores. Live integration must also
verify actual provider usage, sandbox execution, network isolation, and fresh
evaluation environments.

## Pin and prepare public benchmark inputs

Clone each repository identified by `osa_eval.benchmarks.PINS`, check out its
exact commit, and materialize its original file bytes with line-ending
conversion disabled. Place the checkouts under one upstream directory:

```console
python -m osa_eval.cli prepare --upstream-root /path/to/upstream --output ./manifests/pilot
```

This selects 24 of the 642 SWE-bench Pro V2 tasks by a seeded hash ranking and
records file checksums. It also records the official AsynCodeBench task index
and the separately selected v2/v4 runtime profiles. It leaves formal readiness
false until the environment and evaluator gates pass. Public test/gold files
are referenced by checksum and remain outside the agent's environment.

## Run an exploratory controlled workload

`osa_eval.cli run` accepts a model configuration, a frozen event workload,
and a map from task IDs to existing Docker containers. The command verifies
each running container's image identity and disabled network before work.
The model key is read from the named host environment variable.

```console
python -m osa_eval.cli run --config config.json --workload workload.json --workspaces workspaces.json --output results/run-001
```

`Limits` defines the configuration fields. The legacy `context_window` policy
reserves the configured context bound. M2 uses `exact_prompt_plus_max_output`:
the serving tokenizer counts the actual next request and its maximum output
allowance is added before admission. Missing or inconsistent tokenizer receipts
stop execution. Actual usage releases unused reservations. Unknown billed
requests retain their reservation and are
flagged; truncated responses retain their reported token charges. A provider
exceeding its reservation invalidates accounting. A token allowance smaller
than one reservation cannot admit a call.

## M2 execution scope

M2 selects the first four tasks from the existing frozen 24-task manifest,
uses three paired seeds and all five controlled architectures, and offers all
four requests simultaneously. This is 15 workload batches and 60 task grades.
The first seed's 20 grades form a diagnostic stopping point: if all fail,
investigate capability, inputs and budgets before running more seeds. Keep the
selected tasks and every failed attempt. The larger 24-task and 8/16-load matrix
is deferred.

`configs/controlled-pro.m2.template.json` records the common M2 limits. Queue
wait contributes to batch latency; each task's active allowance starts when
its session lock is acquired. `session_acquired` / `session_released` trace
intervals establish actual execution overlap. Report API tokens, accepted
reservation totals, outstanding reservations, denied admissions, context
limits, execution states and independent grades separately. Compiler crashes
invalidate a grade even when another test package has collected real tests.

The native assignment configuration is
`configs/native-worker.m2.template.json`. Its zero USD rates are an explicit
self-hosted API transport convention; GPU residence and hardware pricing are
reported separately. Use the native release's unchanged execution profile,
including its 100-response limits. Native protocols retain their own task
decomposition, permissions, integration and scoring.

At this source freeze, M2 environment qualification is pending. Actual CPU/RAM
enforcement has been measured; the selected Pro reference patch has not passed
the tested nested environments. The raw controlled runner retains
`official_protocol_valid=false`. A formal result requires successful reference
gates and matching native Harbor patch-replay evidence. Execution receipts and
source manifests in the evidence bundle record subsequent measured status.

The legacy `IsolatedPodmanWorkspace` provides an exploratory Linux backend.
Its container inherits a fresh kernel network namespace from
`unshare --net`; the backend verifies that namespace differs from the host.
Its cgroup limits are currently unenforced and must be disclosed in results.
The container's Podman `host` mode refers to that private parent namespace.

## Official evaluators and asynchronous tasks

For SWE-bench Pro V2, use the pinned task evaluator on a fresh image for every
captured patch. Validate both empty and reference patches first and retain
their raw logs. Report the fresh-image grade. The toolkit's worker completion
claim is a separate artifact.

`osa_eval.campaign.ProCampaign` ties intake, patch submission, independent
grading and evidence export together. It requires matching task-file hashes,
image identity, and successful empty/reference gates before model execution.
The global horizon stops new work; artifacts submitted after the deadline,
including bounded cleanup grace, receive no pre-deadline credit. Scoring runs
after the agent phase and its duration is reported separately. A completed
result is immutable; a failed attempt needs a new output directory.

```console
python -m osa_eval.cli pro-run --config configs/controlled-pro.template.json --workload workload.json --gates evaluator-gates.json --output results/pro-001
python -m osa_eval.cli analyze --root results --output results/analysis-001 --plots
```

Adapt the configuration paths and verified model/serving identity first.
`evaluator-gates.json` maps each official task ID to `task_files`, `image_id`,
`empty` and `reference` records produced by `ProTask.grade`. Every gate is
bound to the same immutable image and original task files. The optional
`analysis` package extra supplies Matplotlib. Analysis draws measured points
and exports role totals and invalid runs; matched configurations and repeated
task clusters are required for architectural conclusions.

The initial five-arm real coding fixture used source snapshot002. The original
core/model restart fixture used snapshot003. Later snapshots add reports,
safe-state recovery, context preflight, official patch replay and campaign
analysis. Keep these identities distinct. The first actual Pro pilot uses
snapshot007, a 10-minute horizon and 500,000 total tokens per arm; its shared
host CPU/RAM contract differs from the official50-minute Harbor deployment.

The first image exposed two environment integration defects before model
evaluation: its mode0555 root needs controller-provisioned log directories,
and a login shell overwrites its Go PATH. The adapter now provisions log
directories through the container copy API and preserves the image environment
with a non-login shell. Both empty and reference gates then passed on fresh
images. The official test files remained byte-identical.

`osa_eval.asyncodebench_adapter:SharedWorkerAdapter` implements the native
AsynCodeBench assignment interface. Run it inside the pinned benchmark runner.
Its key comes from `LLM_API_KEY`; `LLM_BASE_URL` identifies the endpoint.
Provide a native provider model name and an explicit numeric pricing convention
in adapter configuration. The native harness retains orchestration, writable
scope checks, integration, dependency probes, and scoring. This adapter alone
does not replace a native protocol with a Super-agent architecture. An extended
coordination study needs its own protocol identity and validated integration.
The adapter's local token guard is per assignment; the native harness owns
protocol-wide coordination and cost aggregation. A common total token quota
across all native manager/worker calls remains a separate integration gate.

## Upstream domain adapter

Node.js 24 supports the required TypeScript transformation:

```console
node --experimental-transform-types adapters/upstream_core.mjs /path/to/dsh-superagent-prototype state.json
```

Send one JSON command per line, for example:

```json
{"method":"snapshot","args":[]}
```

The bridge validates the upstream commit, imports its original core, records
the emitted port effects, and persists domain snapshots. It sends no GitHub or
chat messages and does not start the DSH host. Snapshot writes use atomic
replacement. Consumers must reconcile a lost effect response rather than
blindly replaying outside actions.

`osa_eval.upstream_runtime.UpstreamRuntime` supplies benchmark model ports and
uses the same worker kernel. Its live two-round coding fixture retained one
ticket after a Node-process restart and delivered the subscribed update without
a second admission call. The unmodified upstream core test file also passed
all113 tests under its pinned Vitest4.1.8; this covers the core rather than the
full DSH host.

## Evidence and publication

Keep source manifests, workloads, provider/hardware identities, journals,
trajectories, patches, grades, failures, and derived reports together. Results
must identify whether they are diagnostic fixtures, exploratory runs, or
official-harness results. Frozen runs are immutable; derived reports use
separate output directories. Review traces for repository secrets before
publication. The root repository's MIT license applies to this module;
third-party benchmark/model licenses retain their own terms.
