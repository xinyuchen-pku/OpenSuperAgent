# Getting started

## Install

Use Node.js 22 or newer, pnpm 11, Python 3.9 or newer, and Git. macOS and Linux are supported. Install pnpm using its [official installation instructions](https://pnpm.io/installation).

```bash
git clone https://github.com/xinyuchen-pku/OpenSuperAgent.git
cd OpenSuperAgent
pnpm install --frozen-lockfile
pnpm build
python3 -m server.app
```

The console is served by Python at `http://127.0.0.1:8765`. Without a repository and model key, tasks can be recorded but attempts become blocked with a setup instruction.

For a frontend-only demonstration, run `pnpm dev` without a runtime on port 8765. The console detects the missing API and opens clearly labeled browser-local demo data. For development with real execution, start Python on 8765, then run `pnpm dev`; Vite proxies same-origin API requests to the loopback runtime.

## Configure real execution

Set environment variables **in the shell starting the Python process**. The runtime does not load `.env` files automatically. `.env.example` lists names without any credentials.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OSA_REPO` | unset | Absolute path to an existing, trusted Git repository with a committed `HEAD` |
| `OSA_API_KEY` | unset | Model provider key; required for execution |
| `OSA_BASE_URL` | `https://api.deepseek.com` | Provider base URL; `/chat/completions` is appended |
| `OSA_MODEL` | `deepseek-flash` | Provider-specific model name |
| `OSA_GITHUB_REPO` | unset | Exact `owner/repository` source scope and display label |
| `OSA_ALLOWED_ACTORS` | unset | Comma-separated GitHub login names permitted to originate work |
| `OSA_BOT_MENTION` | `opensuperagent` | Mention checked in GitHub issue or comment bodies |
| `OSA_WEBHOOK_SECRET` | unset | HMAC secret; webhook intake remains disabled without it |
| `OSA_GITHUB_POLL` | unset | Set to `1` to enable read-only polling every 60 seconds |
| `OSA_GITHUB_TOKEN` | unset | Optional read-only GitHub token for private repositories or higher API limits |
| `OSA_CANDIDATE_LABEL` | `agent-candidate` | GitHub issue label that records an observed candidate |

```bash
export OSA_REPO=/absolute/path/to/repository
export OSA_BASE_URL=https://api.deepseek.com
export OSA_MODEL=deepseek-flash
# Set OSA_API_KEY securely; keep it outside source control and shell history.
python3 -m server.app --port 8765 --state-dir .superagent
```

For another compatible provider, set its base URL and model. A typical base URL ends in `/v1`; DeepSeek uses `https://api.deepseek.com`. HTTPS is required except for localhost. The adapter keeps provider `reasoning_content` in the in-memory continuation when supplied, without displaying it in the console. Actual tool support, context windows, quota, and pricing depend on the provider.

Each task starts from the configured repository’s committed `HEAD`. Uncommitted source-checkout changes are not copied. Retry uses the existing worktree and its modifications. Branches are named `osa/osa-<task id>`. No task workspace is removed automatically.

## GitHub polling

Polling is an optional read-only source. It examines open issues updated after the first polling start and persists its read cursor. It excludes pull requests and bot-created issues.

```bash
export OSA_GITHUB_REPO=your-account/your-repository
export OSA_ALLOWED_ACTORS=your-github-login
export OSA_GITHUB_POLL=1
python3 -m server.app
```

- An issue by an allowed actor containing `@opensuperagent` creates one explicitly authorized task.
- An issue by an allowed actor labeled `agent-candidate`, without that mention, creates an **Observed** candidate. Approve it from the console before execution.
- Issue edits do not create additional tasks. The first accepted issue identity is retained. Use a local follow-up for revisions; polling does not implement conversation subscriptions.
- Polling has a 1,000-update page budget. If exceeded, it keeps the old cursor and records an error rather than skipping updates.
- Polling errors are recorded once per error type and retried every 60 seconds. A recovery event is recorded after success.

## Signed webhooks

`POST /api/webhooks/github` handles `issues.opened` and `issue_comment.created`. Configure a repository webhook with a strong secret matching `OSA_WEBHOOK_SECRET`, the exact repository scope, and a narrow allowed-actor list. The request must include a matching `X-Hub-Signature-256`, a delivery ID, and a body that mentions the configured agent. Bots cannot create explicit work.

The server binds only to loopback. Receiving GitHub webhooks requires a **separately operated HTTPS ingress** forwarding only this route; do not expose the entire local console. Polling avoids that ingress requirement. Webhook setup is optional, and the repository does not create a webhook or network tunnel for you.

Issue webhooks and polling share a stable issue identity. Re-delivered comments share their GitHub delivery identity. Comment requests create separate tasks; they do not resume an existing conversation automatically.

## Review and follow-up

Open a task to view its request, mandate, result, local diff, and event history. For a blocked task or a revision, add context and choose **Send context & retry**. This preserves the original request and worktree, then queues another attempt. Stopped tasks remain stopped; create a new task for new work.

**Pause dispatch** prevents new workers from starting; active workers continue. **Stop task** prevents subsequent tools after the current model request or file operation returns. A model request can take up to 90 seconds to return. Files already changed remain available.

The built-in worker cannot run tests. Inspect the full worktree and run your repository’s normal checks before copying, committing, or publishing changes yourself. **Mark reviewed** only records your local decision.

## Persistence and shutdown

The state directory contains `state.sqlite3`, SQLite journal files, `runtime.lock`, and `work/OSA-*` Git worktrees. Keep the directory and the source repository together; worktrees refer back to the original repository. Back up SQLite using the SQLite backup API while the runtime is running, or stop the runtime and copy its complete state directory and repository.

One runtime owns a state directory. A second process is rejected by an OS lock. Interrupted active tasks become blocked on the next start, with their workspace paths retained. Graceful shutdown stops new dispatch and lets active workers finish. There is no automated retention limit, worktree prune, or cleanup command.

## Troubleshooting

- **Provider HTTP error:** verify base URL, model name, credentials and quota. Error responses do not expose provider response bodies in the console.
- **Execution disabled:** set both `OSA_REPO` and `OSA_API_KEY` before starting the runtime.
- **Git worktree failure:** make sure the target is a trusted Git repository with a committed `HEAD` and writable worktree storage.
- **Browser shows demo:** check that the local runtime is reachable on the same origin, or use the configured Vite proxy during frontend development.
- **Port already used:** choose another `--port` or stop only your own old runtime. Do not stop unrelated workloads.
