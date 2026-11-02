import type { State, Task } from "./types";
const ago = (minutes: number) =>
  new Date(Date.now() - minutes * 60000).toISOString();
const patch = `diff --git a/src/utils/retry.ts b/src/utils/retry.ts
index a18f297..bf96e02 100644
--- a/src/utils/retry.ts
+++ b/src/utils/retry.ts
@@ -1,5 +1,9 @@
 export async function retry<T>(fn: () => Promise<T>) {
-  return fn();
+  for (let attempt = 0; attempt < 3; attempt++) {
+    try { return await fn(); }
+    catch (error) {
+      if (attempt === 2) throw error;
+      await new Promise(r => setTimeout(r, 250 * 2 ** attempt));
+    }
+  }
 }
`;
export function seed(): State {
  const base = (
    id: string,
    title: string,
    status: Task["status"],
    minutes: number,
    source = "github",
    basis = "explicit",
  ): Task => ({
    id,
    title,
    status,
    source,
    actor: "demo-maintainer",
    created: ago(minutes),
    updated: ago(Math.max(0, minutes - 4)),
    prompt:
      title +
      ". Keep the existing public interface and explain the changes and validation.",
    mandate: {
      basis,
      scope:
        "Local file changes for this task. Human review before publication.",
      actor: "demo-maintainer",
      policy: "v1",
    },
    workspace: status === "observed" ? "" : `.superagent/work/${id}`,
    result: "",
    diff: "",
    attempts: status === "observed" || status === "queued" ? 0 : 1,
  });
  const tasks = [
    {
      ...base(
        "OSA-7A12C9F0",
        "Add exponential backoff to API retries",
        "review",
        24,
      ),
      result:
        "Prepared a bounded retry helper with exponential backoff. Existing function signatures are preserved.\n\nIllustrative demo result: no repository was modified and no tests were executed. Open the Changes tab to inspect the example patch.",
      diff: patch,
    },
    {
      ...base(
        "OSA-53B8D421",
        "Document the local development workflow",
        "review",
        42,
        "local",
      ),
      result:
        "Prepared setup instructions covering installation, environment configuration, and the local console.\n\nThis is an illustrative demo artifact. No real files were changed.",
      diff: "--- /dev/null\n+++ b/docs/development.md\n@@ -0,0 +1,5 @@\n+# Local development\n+\n+Run `pnpm install` to install dependencies.\n+Run `pnpm build` to build the console.\n+Run `python3 -m server.app` to start the local runtime.\n",
    },
    base(
      "OSA-A91E03B2",
      "Improve empty states in the task panel",
      "queued",
      8,
      "local",
    ),
    {
      ...base(
        "OSA-9DF480A1",
        "Investigate a flaky integration check",
        "blocked",
        61,
      ),
      result:
        "A representative failure log is required to reproduce the timeout. Attach the failing test output to the task instructions before retrying. This is an example of a task requiring human input.",
    },
    base(
      "OSA-2E94B10D",
      "Refresh dependencies after the weekly scan",
      "observed",
      12,
      "rule",
      "candidate",
    ),
    {
      ...base(
        "OSA-C028A7E6",
        "Clarify webhook configuration in the README",
        "done",
        96,
      ),
      result:
        "Illustrative completed task. The configuration guide explains event signatures, repository scope, and allowed actors.",
    },
  ];
  return {
    tasks,
    events: [
      {
        seq: 6,
        task_id: tasks[4].id,
        kind: "admission",
        message:
          "Dependency candidate recorded. Observe mode keeps it from executing.",
        created: ago(3),
      },
      {
        seq: 5,
        task_id: tasks[0].id,
        kind: "review",
        message: "Retry helper is ready for human review.",
        created: ago(5),
      },
      {
        seq: 4,
        task_id: tasks[2].id,
        kind: "admission",
        message: "Explicit request added to the queue.",
        created: ago(8),
      },
      {
        seq: 3,
        task_id: tasks[1].id,
        kind: "review",
        message: "Development guide is ready for human review.",
        created: ago(14),
      },
      {
        seq: 2,
        task_id: tasks[3].id,
        kind: "blocked",
        message: "Worker needs a failure log to continue.",
        created: ago(20),
      },
      {
        seq: 1,
        task_id: tasks[5].id,
        kind: "complete",
        message: "Maintainer reviewed the webhook documentation.",
        created: ago(40),
      },
    ],
    paused: false,
    observe: true,
    mode: "demo",
    repository: "example / platform",
    model: "Simulated executor",
    ready: true,
    max_steps: 20,
  };
}
export function loadDemo(): State {
  try {
    const saved = JSON.parse(localStorage.getItem("osa-demo-v1") || "null");
    if (
      saved?.mode === "demo" &&
      Array.isArray(saved.tasks) &&
      Array.isArray(saved.events)
    )
      return saved;
  } catch {
    /* Fresh state if local storage is unavailable or corrupt. */
  }
  return seed();
}
export function saveDemo(state: State) {
  try {
    localStorage.setItem("osa-demo-v1", JSON.stringify(state));
  } catch {
    /* The session remains usable without persistence. */
  }
}
