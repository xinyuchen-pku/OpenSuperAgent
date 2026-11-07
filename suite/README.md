# OpenSuperAgent Evaluation Suite

Manifest-driven evaluation with a shared, frozen Coding Worker. The new suite
keeps source025 intact and separates architecture experiments from native
benchmark execution. **Status: local Stage 2 candidate; no new real-model results.**

[Protocol, budgets and implementation boundaries](PROTOCOL.md) ·
[Frozen task manifests](manifests) · [Historical measured results](../docs/results/README.md)

## Install

Python 3.11+ for suite tools; Python 3.12 and the pinned official Linux/Docker
environment for native AsynCodeBench. From the repository root:

```console
python -m pip install ./research ./suite
python -m unittest discover -s suite/tests -v
```

Install plotting dependencies when generating figures:

```console
python -m pip install "./suite[analysis]"
```

`osa-suite` is the Stage 2 entry point; `osa-eval` remains the immutable Stage 1
entry point. Both packages install separate commands. Experiment manifests are
JSON. Endpoint credentials remain in the named environment.

## Inspect a complete run plan without a model or Docker

```console
osa-suite plan --benchmark asyncodebench_native --model qwen3-coder-next \
  --manifest suite/configs/stage2.json --output native-plan.json

osa-suite plan --benchmark swebench_pro_v2 --model qwen3-coder-next \
  --manifest suite/configs/stage2.json --output pro120-plan.json
```

The first plan covers all19 original native tasks under `async_private`, one
seed, 38M total upper tokens. It preserves official coordination. The Pro120
plan covers five architecture arms and two seeds, 2.4B theoretical upper tokens;
its final development-inventory and environment gates are still pending.
Plans never call a model or manufacture a score.

## Execute after live admission

Copy `configs/site.template.json` outside the repository, resolve paths, attach
task-specific SDK image IDs and provenance receipts, and load the secure environment.
The site file names a shared campaign ledger **outside attempt directories**;
all retries and arm shards use that same path. The live admission file must bind
the exact experiment, site, Worker and suite lock and include original environment
and resource evidence. Template placeholders deliberately fail admission.
The guard process receipt must identify the live supervisor on the same Linux
host as the suite; the supervisor may manage a separately verified remote model.
Use `osa-suite admit` with the same benchmark/model/manifest/site/lock flags and
set `--output` to the site's immutable admission file. It verifies code, images,
resources and capped provider controls. The two controls share the campaign
ledger, with a separate 10K-token admission allowance.

```console
osa-suite run --benchmark asyncodebench_native --agent native \
  --model qwen3-coder-next --manifest suite/configs/stage2.json \
  --site /private/stage2-site.json --lock suite/FREEZE.json \
  --output /evidence/stage2/native-attempt-001
```

The native runner executes official commands and automatically validates each
original run bundle. Git identity preflight and exact-path edits reuse the accepted
source025 policy. Each role sees only its own live, read-only worktree and an
isolated shallow Git baseline; a read/Git probe must pass before inference.
Manager protocols are explicitly refused
until their model traffic also participates in full-task accounting.

Pro execution uses pristine reference/empty gates, actual 1CPU/4GiB containers,
and independent plus original Harbor grading. All five task-level arms use the
same Worker. See the protocol for the new, fresh-context baseline definitions.

Platform-specific resource-guard integration, complete native independent
regrading, native coordinator injection, real-model event runner and the queued
Terminal/Async-RBench adapters remain work in progress. Those readiness gaps are
listed in the protocol; a local unit test pass is narrower than benchmark acceptance.

## Tables and paired confidence intervals

Normalized result rows follow `result-schema.json`; official native metrics retain
their original scorer artifacts and metric names. Collect suite artifacts, then
generate tables and separate
Success–Cost and Success–Latency plots with:

```console
osa-suite collect --manifest suite/configs/stage2.json --run /evidence/run --output normalized-results.json
osa-suite report --results normalized-results.json --output report
```

For one selected track/benchmark/protocol, add `--compare eager_delegation superagent`.
The report retains per-seed results and resamples tasks/repositories with seeds
together. Unknown usage is explicit; no fake zero-cost successful run is admitted.
Throughput uses complete, observed batch clock receipts. Historical results and
deterministic fixtures stay separately labeled.
