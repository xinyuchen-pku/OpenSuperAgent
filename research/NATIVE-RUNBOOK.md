# Native benchmark handoff

The controlled Pro runner and the native AsynCodeBench runner are different
execution paths. Preserve that distinction in result tables and protocol IDs.
The first Pro experiment used a custom OCI backend, one task, one seed, a
600-second horizon and a 500,000-token system budget. Its resource contract
does not qualify for an official aggregate. The planned matrix in
`configs/pilot-matrix.json` has not been executed.

The active M2 scope is recorded in `configs/m2-matrix.json`; larger loads in
the historical matrix remain deferred. Use the M2 configuration templates and
the exact source manifest attached to each run. A working resource limit and
a passing reference patch are separate environment admission requirements.

## Required host

Use Linux x86_64, Python 3.12, Node.js 24, Git, uv and an accessible Docker
daemon. Docker must actually enforce each selected Pro task's CPU and memory
settings. `osa-eval pro-gates` checks the running container's resource controls,
network boundary, hidden files, Git history and evaluator behavior. A successful
image download or a configured Docker flag alone does not satisfy this gate.

The inspected Baidu gateway and CPU allocation lacked a Docker daemon and
writable/delegated cgroups. The Podman backend supports exploratory runs and
records `cgroup_limits_enforced=false`. Preserve the existing platform jobs,
their processes, and access points while arranging a compliant runtime.

## Pinned inputs

| Input | Git revision |
|---|---|
| DeepSeek prototype | `6337fc823ce20251c8de8085948165c81aaa701e` |
| SWE-bench Pro V2 | `66f92766bba642462d4bbe5479e83f91f9211862` |
| AsynCodeBench | `2a639b049f249e79eb2031876bc06a110be9ac3a` |
| OpenHands SDK | `944284310d9a5f1ccad0ef8c2d7c4c38342b9952` |

Use separate clean checkouts. The AsynCodeBench setup script verifies its
locked SDK revision, package versions and event round trip. Its native runner
requires Python 3.12 and OpenHands packages 1.29.2. Keep LF/raw Git bytes when
materializing release files; their content hashes are part of the contract.

## Pro preparation and execution

1. Install this research package and prepare the selection manifests with
   `osa-eval prepare --upstream-root PATH --output MANIFEST_DIRECTORY`.
2. Resolve each selected official image to its registry manifest digest and
   local config/image ID. Save both in the image map. Verify all downloaded
   objects before loading them into the task-specific store.
3. Copy `configs/controlled-pro.template.json` to an execution configuration.
   Set its clean checkout paths, fixed model settings and Docker backend.
   Load the key through the named environment variable outside task containers.
4. Run `osa-eval pro-gates --config CONFIG --images IMAGE_MAP --task-ids ID ...
   --output NEW_GATE_DIRECTORY`. Every selected task needs a valid empty-patch
   failure and reference-patch success with original tests, plus history and
   network checks. Preserve failed gate directories.
5. Freeze identical workloads, common limits and balanced arm order before
   inspecting model outcomes. Run each arm with `osa-eval pro-run --config
   CONFIG --workload WORKLOAD --gates GATES --output NEW_RUN_DIRECTORY`.
6. Use `osa-eval check-comparison` for capacity and budget comparisons
   separately. Recompute metrics with `osa-eval analyze`. A single task/seed
   supplies descriptive observations; repeated paired tasks supply the units
   for task-cluster uncertainty estimates.

## AsynCodeBench native wiring

Follow the pinned benchmark's `docs/QUICKSTART.md` and run its unchanged
`scripts/setup_evaluation.sh`. Install this research package into the resulting
native runner environment. Complete `doctor`, native dry runs and a diagnostic
adapter run before using the model-enabled adapter. A wiring diagnostic is
expected to fail coding while still producing an independently valid bundle.

The import path for the common worker is
`osa_eval.asyncodebench_adapter:SharedWorkerAdapter`. Supply the same adapter
configuration to every native protocol. Configuration keys include:

```json
{
  "architecture": "native",
  "provider_model": "osa-qwen3-coder-30b",
  "temperature": 0.7,
  "max_output_tokens": 8192,
  "seed": 20261102,
  "request_token_reservation": 262144,
  "reservation_policy": "exact_prompt_plus_max_output",
  "token_budget": 32000000,
  "allow_private_http": true,
  "tokenizer_preflight": true,
  "context_policy": "shorten_old_tool_observations"
}
```

The example is incomplete until an explicit input/output pricing convention
is supplied: the native response requires numeric cost. For an unpriced
self-hosted service, publish token counts and GPU residence and explicitly
identify any zero-cost reporting convention. Configure the native manager's
model, decoding, tool parser and pricing consistently as well; the custom
worker configuration does not configure its manager.

Load `LLM_API_KEY` securely in the actual runner environment and set
`LLM_BASE_URL` to the reachable endpoint. The native manager uses a
provider-prefixed `LLM_MODEL`, such as `openai/osa-qwen3-coder-30b`. Do not put
credentials in adapter JSON or task files. Keep endpoint credentials outside
collected artifacts. Native OpenHands workspace-to-model reachability needs
its own check; the controlled runner's host-side transport check covers a
different path.

Use the pinned wrapper's `ASYNCODEBENCH_AGENT_IMPORT_PATH` and
`ASYNCODEBENCH_AGENT_CONFIG_JSON` variables to select the adapter for all five
native protocols. Finish each run with the benchmark's `validate-run` and
retain `run_bundle.json`, evaluator output, dependency probes, scope checks,
integration records and adapter journals.

For the M2 admission case, copy `configs/native-worker.m2.template.json` to a
host configuration file and run from the pinned native runner directory:

```console
python -m asyncodebench_harness.cli run --task asyncodebench:cachetools --protocol async_private --model openai/osa-qwen3-coder-30b --agent-import-path osa_eval.asyncodebench_adapter:SharedWorkerAdapter --agent-config-json "$(cat /absolute/path/native-worker.json)" --output-dir /absolute/path/new-run
python -m asyncodebench_harness.cli validate-run /absolute/path/new-run
```

The configuration JSON contains public parameters, never credentials. Keep the
native 100-response execution profile and its original two-agent scenario.
For the configured 262,144-token service, set `LLM_MAX_INPUT_TOKENS=253952`,
`LLM_MAX_OUTPUT_TOKENS=8192` and `LLM_TEMPERATURE=0.7` consistently in the
native runner. Record serving defaults for top-p, top-k, repetition penalty,
tensor parallelism and cache policy alongside the weight/tokenizer manifest.
The [model card](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct)
defines the native context and recommended sampling settings. The 8,192-token
per-response output cap is this study's declared resource setting.

The native protocols (`single`, `serial_specialists`, `async_private`,
`caid_manager`, `async_manager`) are a separate axis from the five controlled
architectures. The adapter owns one assignment; the native harness retains
orchestration and private worktrees. Its token limit currently applies per
assignment. A protocol-wide token guard covering manager and worker calls,
and a validated custom orchestration extension with its own protocol ID,
remain implementation and acceptance work. Do not label native adapter runs
as a completed five-architecture Track C comparison.

## Completion criteria

Track A needs the selected repeated paired tasks and independently verified
grades. Track B additionally needs replayed open-loop arrivals and measured
offered/admitted concurrency. Track C needs native bundle validity and any
custom coordination extension accepted separately. All tracks need exact
source/model/task/image identities, full-system usage, raw failures, analysis
and a rendered technical report. Publishing requires review of the exact
branch and content under the user's GitHub authorization rule.
