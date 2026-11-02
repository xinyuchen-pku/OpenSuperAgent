# Contributing

Start with a focused issue describing the desired behavior and its impact on the existing task, authorization, or executor contract. Keep changes small enough to review.

## Local checks

```bash
pnpm install --frozen-lockfile
python3 -m unittest discover -s tests -v
pnpm build
pnpm exec prettier --check src vite.config.ts
```

Use Python 3.9+ and Node.js 22+ with pnpm 11. The Python backend has no third-party runtime dependencies. Frontend changes should include a desktop and narrow-screen visual check and keyboard navigation through relevant dialogs.

## Invariants

- Text from a repository, issue, or model is context, not permission to alter configured policy.
- Duplicate source events must not create duplicate tasks.
- Observed work requires an explicit operator decision before execution.
- A task stop is durable even when a provider request is in flight.
- Workspaces survive retries, stops and restart recovery. Do not introduce cleanup without an explicit retention contract.
- New model tools require argument checks, a clear resource budget, and tests of their authority and file boundaries.
- Report actual validation. A successful model response does not establish that repository tests passed.

Do not submit keys, `.env` files, `.superagent` state, local worktrees, private prompts, or generated dependency directories. The MIT license applies to contributions.
