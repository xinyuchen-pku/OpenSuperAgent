# Validation scope

## Local acceptance — 2026-11-02

Environment: macOS; Node.js 24.22.1; pnpm 11.25.0; Python 3.9.6; installed dependency versions are fixed by `pnpm-lock.yaml`.

| Check | Result | Evidence and limits |
| --- | --- | --- |
| TypeScript and production build | Passed | `pnpm build`; frontend compiled to a static artifact |
| Runtime suite | 26 tests passed | `python3 -m unittest discover -s tests -v` |
| HTTP provider → file tool → Git worktree | Passed | A local scripted Chat Completions HTTP service produced a real text file; the original checkout remained unchanged |
| Admission and source identity | Passed | Allowed actor, exact mention, repository scope, observed candidates, signed webhooks, replay idempotence |
| Recovery and control | Passed | Atomic concurrent claims, dispatch pause, stop during an in-flight response, blocked restart recovery, context-follow-up retries |
| File and retention boundaries | Passed | Traversal, symlinks, case variants of protected paths, common weight extensions, oversized files, binary overwrite protection, preservation after the model-step budget |
| Desktop console | Passed | 1440 × 1000 layout; create/search tasks, inspect diff, mark reviewed, approve a candidate, settings and demo reset |
| Narrow console | Passed | 390 × 844 layout; navigation, task dialog, status controls; document width remained within the viewport |
| Real local runtime console | Passed | The browser created a task in SQLite; the scheduler reported missing model/repository configuration as a blocked task with an actionable message |
| Personal-homepage entry | Prepared separately | Bilingual news and project links are maintained in the personal homepage repository, not copied into this application |

The test suite uses only synthetic repositories, temporary files and a scripted model service. It does not run commercial-provider inference, modify a user repository, open pull requests, or delete real training artifacts.

## What this establishes

The checks cover the local state contract, authority boundaries, HTTP interface, tool protocol and independent worktree execution. The console’s static demo uses sample tasks and simulated progression, explicitly labeled in its banner and task results.

No commercial-provider credentials were configured during this acceptance. Real model answer quality, provider quota and provider-specific context behavior require testing against the operator’s chosen account. The built-in worker has no shell/test runner, so a task reaching review does not include repository test execution. Production hosting, external webhook ingress and multi-user operation are outside this validation.

GitHub CI and Pages deployment are defined in the repository workflows; their actual run results belong to the publication record after the first push. Workflow actions are pinned to full commit identities from their official repositories.
