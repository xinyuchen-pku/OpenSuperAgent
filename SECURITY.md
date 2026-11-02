# Security boundaries

OpenSuperAgent v0.1 is intended for one operator on a trusted local machine and a trusted repository. It is an engineering preview, not a multi-tenant security boundary.

## Enforced controls

- The HTTP server binds to loopback. Console API requests check the Host and Origin and require JSON for mutations. No permissive CORS response is provided.
- GitHub webhook requests require an HMAC-SHA256 signature, an explicit delivery ID, the configured repository, an allowed human actor, and the agent mention.
- Observed candidates do not execute without operator approval. Model instructions cannot edit admission policy.
- File tools operate in a task worktree, reject path traversal and symlinks, protect Git metadata and common secret/weight paths, and bound text operations to 64 KiB.
- No model tool runs shell commands, deletes files, commits, pushes, or merges.
- Provider transport requires HTTPS except on loopback and refuses redirects. Provider HTTP response bodies are omitted from console errors.
- Stopped tasks are not resurrected by late results. Workspaces and task history are retained; there is no automatic cleanup.

## Operator responsibilities

A Git worktree shares repository metadata and is not an OS sandbox. Git checkout can use repository-configured filters; choose a trusted repository and inspect its configuration. Other processes with the operator’s privileges can access the same files. A hostile process could race path checks.

File tools do not recognize every possible secret or recovery-state filename. Keep secrets, training artifacts, credentials, private documents and unrelated data outside the selected repository. Files read by a worker are transmitted to the configured model provider. Check that provider’s data handling before use.

The runtime itself has no outbound firewall, cost accounting, monetary budget, test runner or model-output correctness guarantee. Step and file limits bound operations; provider token billing still depends on context and responses. Review generated code and run your own checks.

Do not expose the console on a public network. Webhooks require a separate HTTPS ingress forwarding only the webhook path. Narrow the allowed-actor list and use least-privilege read-only GitHub credentials for polling. An optional `OSA_UI_TOKEN` bearer guard is available for API-only operation; the browser console does not provide token login in this release.

## Reporting

Report a vulnerability through the repository’s private vulnerability reporting feature if it is enabled. Otherwise contact the maintainer using their public GitHub profile and request a private channel before sharing exploit details or sensitive data. Do not include credentials in public issues.
