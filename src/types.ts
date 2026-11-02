export type Status =
  | "observed"
  | "queued"
  | "running"
  | "review"
  | "blocked"
  | "done"
  | "stopped";
export type Task = {
  id: string;
  title: string;
  prompt: string;
  status: Status;
  source: string;
  actor: string;
  created: string;
  updated: string;
  mandate: { basis: string; scope: string; actor: string; policy: string };
  workspace: string;
  result: string;
  diff: string;
  attempts: number;
};
export type Event = {
  seq: number;
  task_id: string | null;
  kind: string;
  message: string;
  created: string;
};
export type State = {
  tasks: Task[];
  events: Event[];
  paused: boolean;
  observe: boolean;
  mode: "demo" | "live";
  repository: string;
  model: string;
  ready: boolean;
  max_steps: number;
};
export const statusLabels: Record<Status, string> = {
  observed: "Observed",
  queued: "Queued",
  running: "Working",
  review: "Awaiting review",
  blocked: "Blocked",
  done: "Completed",
  stopped: "Stopped",
};
