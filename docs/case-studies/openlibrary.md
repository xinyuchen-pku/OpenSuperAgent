# OpenLibrary patch replay

This captured run used Eager Delegation, Qwen3-Coder-30B-A3B-Instruct and
source022 in the four-task Pro pilot at seed `20261102`. The public task concerns
OpenLibrary's table-of-contents parsing and serialization. The run record keeps
the original instruction and full task ID.
[Original instruction and run identity](../../research/public-example/captured-run/identity.json)

| Step | Recorded evidence |
| --- | --- |
| Assignment | The Eager run gave OpenLibrary its own Worker session. The published Worker trace includes its assignment and start |
| Work | The model made 24 requests and executed 23 tool commands. Its patch updates table-of-contents parsing, serialization and related behavior |
| Delivery | The batch recorded the task patch at 526.49 s from start. The Worker consumed 300,747 input plus output tokens. Shared Router and other Workers are recorded separately |
| Validation | Original Harbor score 1, 13/13 required tests. A later clean environment replay reproduced the official result and independent grading agreement |

[Full Worker trace](../../research/public-example/worker-trajectory.jsonl.gz) ·
[Captured patch](../../research/public-example/captured-run/c5e3b484ba4a8302b305/model.patch) ·
[Worker token ledger](../../research/public-example/worker-cost.json) ·
[Official and independent scoring evidence](../../research/public-example/captured-run/accepted-summary.json)

The paired Super-agent row for this seed failed on the same task. This pair
illustrates a result difference and supports closer trajectory review. Task and
seed repetitions provide the evidence for any broader architecture comparison.
[Paired results](../results.md#paired-outcomes-eager-delegation-and-super-agent)

The public replay instructions use a pinned Harbor environment and official
image. They apply this recorded patch and rerun the scorer without model calls.
[Replay the captured patch](../../research/public-example/README.md)
