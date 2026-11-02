# Research notes

Reviewed on **2026-11-02**, against DeepSeek’s published repository at commit [`6337fc823ce20251c8de8085948165c81aaa701e`](https://github.com/deepseek-ai/dsh-superagent-prototype/tree/6337fc823ce20251c8de8085948165c81aaa701e).

## What DeepSeek published

The [upstream README](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/README.md) describes a repository-focused agent bundle for DeepSeek Harness. It explicitly calls the code a research prototype, distinguishes it from an official product, and says the published implementation differs from internal systems and the accompanying article. This project uses the public implementation documents as its reference; it does not claim to reproduce unpublished internals.

Three useful design decisions informed this implementation:

1. **Human attention is a resource.** The [philosophy](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/docs/000-philosophy.md) prioritizes useful results and actionable decisions. OpenSuperAgent places blocked tasks and review requests ahead of the general task list.
2. **Authorization is distinct from context.** The [authorization model](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/docs/002-authorization.md) separates explicit requests, inferred work and information delivered to existing tasks. OpenSuperAgent records a mandate and keeps inferred candidates observed until a local person approves them.
3. **A task outlives an execution attempt.** The [domain model](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/docs/001-domain.md) and [execution guide](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/docs/003-execution.md) separate work from its executor. OpenSuperAgent retains task identity, attempt history and worktree across retries.

These are engineering choices inspired by the documents, not comparative performance findings. No controlled capability benchmark against the upstream runtime was performed.

## Implemented differences

| Area | Public upstream design | OpenSuperAgent v0.1 |
| --- | --- | --- |
| Runtime | Bundle for DeepSeek Harness | Standalone Python/SQLite runtime and React console |
| Worker | Harness sessions with richer execution tools | Small chat-completions loop with bounded file tools |
| Authorization | Rich policy, admission tables and mandates | Explicit local requests; narrow GitHub gate; observed-label rule |
| Context | Thread subscriptions and source-specific follow-ups | Local operator follow-ups on blocked/review tasks |
| Sources | GitHub and optional Feishu | GitHub webhooks, optional read-only issue polling, local console |
| Delivery | Source channels and repository workflows | Local summary/diff; operator performs publication |
| Proactivity | Assessment and rule-based candidate handling | Label-triggered observation, manual approval |
| Isolation | Worker sessions/directories; deployment-specific controls | Git worktree and file-tool checks; no OS sandbox |

The narrower worker is intentional for a first inspectable release. It can make real local code edits while keeping its available operations small. It also limits usefulness: it cannot execute tests, install dependencies, use arbitrary tools, or deliver a pull request itself. A stronger executor should be added behind an explicit isolation and publication contract, rather than silently changing those assumptions.

## Provider reference

The adapter follows DeepSeek’s official [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/) and [Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/) documentation. The default model is `deepseek-flash`, as listed in those documents on the review date. Compatible-provider support is an interface contract; individual provider behavior requires its own integration check.

## Attribution

Application code was written independently. No upstream implementation files, prompts, or tests were copied into this repository. DeepSeek’s research prototype remains the conceptual reference, not a dependency. DM Sans and Manrope are self-hosted with their original SIL OFL notices; Lucide icons retain the package’s ISC license.
