import React, { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Bell,
  BookOpen,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  Circle,
  CircleCheck,
  CircleDot,
  Clock3,
  Code2,
  Copy,
  FileCode2,
  FolderGit2,
  GitBranch,
  Github,
  GitPullRequest,
  LayoutDashboard,
  ListTodo,
  Loader2,
  Menu,
  Pause,
  Play,
  Plus,
  Radio,
  RotateCcw,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Square,
  Terminal,
  Workflow,
  X,
} from "lucide-react";
import type { Event, State, Status, Task } from "./types";
import { statusLabels } from "./types";
import { loadDemo, saveDemo, seed } from "./demo";

const github = "https://github.com/xinyuchen-pku/OpenSuperAgent";
const attention = (t: Task) => t.status === "review" || t.status === "blocked";
const relative = (date: string) => {
  const m = Math.max(
    0,
    Math.floor((Date.now() - new Date(date).getTime()) / 60000),
  );
  return m < 1
    ? "just now"
    : m < 60
      ? `${m}m ago`
      : m < 1440
        ? `${Math.floor(m / 60)}h ago`
        : `${Math.floor(m / 1440)}d ago`;
};
const iconFor = (status: Status) =>
  status === "running"
    ? Loader2
    : status === "review"
      ? GitPullRequest
      : status === "done"
        ? CircleCheck
        : status === "blocked"
          ? CircleDot
          : status === "stopped"
            ? Square
            : status === "observed"
              ? Radio
              : Clock3;
function Badge({ status }: { status: Status }) {
  const Icon = iconFor(status);
  return (
    <span className={`badge status-${status}`}>
      <Icon size={12} className={status === "running" ? "spin" : ""} />
      {statusLabels[status]}
    </span>
  );
}
function Source({ source }: { source: string }) {
  const Icon =
    source === "github" ? Github : source === "rule" ? Radio : Terminal;
  return (
    <span className="source">
      <Icon size={12} />
      {source === "github" ? "GitHub" : source === "rule" ? "Rule" : "Console"}
    </span>
  );
}
export default function App() {
  const [state, setState] = useState<State | null>(null),
    [page, setPage] = useState("Overview"),
    [search, setSearch] = useState(""),
    [filter, setFilter] = useState("all"),
    [selected, setSelected] = useState<string | null>(null),
    [tab, setTab] = useState("Overview"),
    [newTask, setNewTask] = useState(false),
    [mobile, setMobile] = useState(false),
    [toast, setToast] = useState(""),
    [guide, setGuide] = useState(false),
    [busy, setBusy] = useState(false),
    [demoNotice, setDemoNotice] = useState(true);
  const searchRef = useRef<HTMLInputElement>(null),
    modalRef = useRef<HTMLDivElement>(null),
    lastFocus = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!["localhost", "127.0.0.1", "[::1]"].includes(location.hostname)) {
      setState(loadDemo());
      return;
    }
    const abort = new AbortController();
    const timer = setTimeout(() => abort.abort(), 1600);
    fetch("/api/state", { signal: abort.signal })
      .then((r) => {
        if (!r.ok) throw Error();
        return r.json();
      })
      .then((s) => {
        if (s.mode !== "live") throw Error();
        setState(s);
      })
      .catch(() => setState(loadDemo()))
      .finally(() => clearTimeout(timer));
    return () => abort.abort();
  }, []);
  useEffect(() => {
    if (state?.mode === "demo") saveDemo(state);
  }, [state]);
  useEffect(() => {
    if (state?.mode !== "live") return;
    const timer = setInterval(
      () =>
        fetch("/api/state")
          .then((r) => {
            if (!r.ok) throw Error();
            return r.json();
          })
          .then(setState)
          .catch(() =>
            notify(
              "Connection interrupted. The last received state is displayed.",
            ),
          ),
      2000,
    );
    return () => clearInterval(timer);
  }, [state?.mode]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 4200);
    return () => clearTimeout(timer);
  }, [toast]);
  useEffect(() => {
    const fn = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        searchRef.current?.focus();
      }
      if (e.key === "Escape") {
        setSelected(null);
        setNewTask(false);
        setGuide(false);
        setMobile(false);
      }
    };
    document.addEventListener("keydown", fn);
    return () => document.removeEventListener("keydown", fn);
  }, []);
  const dialogOpen = !!selected || newTask || guide;
  useEffect(() => {
    if (!dialogOpen) return;
    lastFocus.current = document.activeElement as HTMLElement;
    const bodyOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    requestAnimationFrame(() =>
      modalRef.current
        ?.querySelector<HTMLElement>("button,input,textarea,a[href]")
        ?.focus(),
    );
    const trap = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const items = modalRef.current?.querySelectorAll<HTMLElement>(
        "button:not([disabled]),a[href],input,textarea,select",
      );
      if (!items?.length) return;
      const first = items[0],
        last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", trap);
    return () => {
      document.body.style.overflow = bodyOverflow;
      document.removeEventListener("keydown", trap);
      lastFocus.current?.focus();
    };
  }, [dialogOpen]);
  // Demo transitions are explicitly simulated; the static site never calls a model or writes GitHub.
  useEffect(() => {
    if (state?.mode !== "demo") return;
    const timer = setInterval(
      () =>
        setState((s) => {
          if (!s) return s;
          const active = s.tasks.find((t) => t.status === "running");
          const queued = s.tasks.find((t) => t.status === "queued");
          const target = active || (!s.paused ? queued : undefined);
          if (!target) return s;
          const status = active ? "review" : "running";
          const stamp = new Date().toISOString();
          const changed = {
            ...target,
            status: status as Status,
            updated: stamp,
            attempts: active ? target.attempts : target.attempts + 1,
            workspace: `.superagent/work/${target.id}`,
            result: active
              ? "Demo execution finished. This simulated result shows where a real worker summary would appear. No repository files were modified and no tests were run."
              : "",
            diff: active
              ? "# This demo task has no file changes.\n# Connect a local runtime to create and review real changes.\n"
              : "",
          };
          return {
            ...s,
            tasks: s.tasks.map((t) => (t.id === target.id ? changed : t)),
            events: [
              {
                seq: (s.events[0]?.seq || 0) + 1,
                task_id: target.id,
                kind: active ? "review" : "execution",
                message: active
                  ? "Simulated execution complete; ready for review."
                  : "Demo worker started a simulated task.",
                created: stamp,
              },
              ...s.events,
            ].slice(0, 250),
          };
        }),
      6500,
    );
    return () => clearInterval(timer);
  }, [state?.mode, state?.paused]);
  function notify(message: string) {
    setToast(message);
  }
  function openTask(id: string) {
    setTab("Overview");
    setSelected(id);
  }
  function navigate(name: string) {
    setPage(name);
    setFilter("all");
    setSearch("");
    setMobile(false);
  }
  async function post(path: string, body: unknown) {
    const r = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await r.json();
    if (!r.ok) throw Error(data.error || "Request failed.");
    const fresh = await fetch("/api/state");
    if (!fresh.ok) throw Error("Unable to refresh runtime state.");
    setState(await fresh.json());
    return data;
  }
  function event(
    s: State,
    task_id: string | null,
    kind: string,
    message: string,
  ): Event {
    return {
      seq: (s.events[0]?.seq || 0) + 1,
      task_id,
      kind,
      message,
      created: new Date().toISOString(),
    };
  }
  async function action(id: string, kind: string, context?: string) {
    if (!state || busy) return;
    setBusy(true);
    try {
      if (state.mode === "live")
        await post("/api/tasks/" + id, { action: kind, content: context });
      else
        setState((s) => {
          if (!s) return s;
          const status: Status =
            kind === "complete"
              ? "done"
              : kind === "stop"
                ? "stopped"
                : "queued";
          return {
            ...s,
            tasks: s.tasks.map((t) =>
              t.id === id
                ? {
                    ...t,
                    status,
                    prompt: context
                      ? t.prompt + "\n\nOperator follow-up:\n" + context
                      : t.prompt,
                    updated: new Date().toISOString(),
                    mandate:
                      kind === "approve"
                        ? { ...t.mandate, basis: "explicit" }
                        : t.mandate,
                  }
                : t,
            ),
            events: [
              event(
                s,
                id,
                kind,
                `Demo operator ${kind === "complete" ? "completed" : kind === "approve" ? "approved" : kind === "retry" ? "retried" : kind === "followup" ? "provided context for" : "stopped"} the task.`,
              ),
              ...s.events,
            ],
          };
        });
      notify(
        kind === "complete"
          ? "Marked complete. No changes were published."
          : kind === "stop"
            ? "Task stopped. Existing files are retained."
            : kind === "approve"
              ? "Candidate approved and queued."
              : "Task queued for retry.",
      );
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function togglePause() {
    if (!state) return;
    try {
      if (state.mode === "live")
        await post("/api/scheduler", { paused: !state.paused });
      else
        setState((s) =>
          s
            ? {
                ...s,
                paused: !s.paused,
                events: [
                  event(
                    s,
                    null,
                    "scheduler",
                    s.paused
                      ? "Demo dispatch resumed."
                      : "Demo dispatch paused.",
                  ),
                  ...s.events,
                ],
              }
            : s,
        );
    } catch (e) {
      notify((e as Error).message);
    }
  }
  async function createTask(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!state || busy) return;
    const data = new FormData(e.currentTarget);
    const title = String(data.get("title") || "").trim(),
      prompt = String(data.get("prompt") || "").trim();
    if (!title || !prompt) return;
    setBusy(true);
    try {
      if (state.mode === "live") await post("/api/tasks", { title, prompt });
      else {
        const id = "OSA-" + crypto.randomUUID().slice(0, 8).toUpperCase();
        setState((s) => {
          if (!s) return s;
          const stamp = new Date().toISOString();
          const task: Task = {
            id,
            title,
            prompt,
            status: "queued",
            source: "local",
            actor: "demo-operator",
            created: stamp,
            updated: stamp,
            mandate: {
              basis: "explicit",
              scope:
                "Local file changes for this task. Human review before publication.",
              actor: "demo-operator",
              policy: "v1",
            },
            workspace: "",
            result: "",
            diff: "",
            attempts: 0,
          };
          return {
            ...s,
            tasks: [task, ...s.tasks],
            events: [
              event(s, id, "admission", "Explicit demo request admitted."),
              ...s.events,
            ],
          };
        });
      }
      setNewTask(false);
      notify(
        state.mode === "demo"
          ? "Demo task created. Execution is simulated."
          : "Task created and queued.",
      );
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      notify("Copied to clipboard.");
    } catch {
      notify("Clipboard is unavailable. Select and copy the text manually.");
    }
  }
  function exportState() {
    if (!state) return;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(
      new Blob([JSON.stringify(state, null, 2)], { type: "application/json" }),
    );
    a.download = "opensuperagent-" + state.mode + "-export.json";
    a.click();
    URL.revokeObjectURL(a.href);
    notify("Task history exported.");
  }
  if (!state)
    return (
      <div className="loading">
        <Logo />
        <Loader2 className="spin" size={20} />
        <span>Opening workspace…</span>
      </div>
    );
  const needs = state.tasks.filter(attention),
    working = state.tasks.filter((t) => t.status === "running"),
    queued = state.tasks.filter((t) => t.status === "queued"),
    completed = state.tasks.filter((t) => t.status === "done"),
    observed = state.tasks.filter((t) => t.status === "observed");
  const tasks = state.tasks.filter(
    (t) =>
      (filter === "all" ||
        (filter === "attention" && attention(t)) ||
        t.status === filter) &&
      (t.title + " " + t.id + " " + t.prompt)
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const task = state.tasks.find((t) => t.id === selected);
  const navs = [
    { name: "Overview", icon: LayoutDashboard },
    {
      name: "Tasks",
      icon: ListTodo,
      count: state.tasks.filter((t) => !["done", "stopped"].includes(t.status))
        .length,
    },
    { name: "Activity", icon: Activity },
    { name: "Rules & permissions", icon: ShieldCheck },
  ];
  const TaskTable = ({ items }: { items: Task[] }) => (
    <div className="task-table">
      {items.length === 0 ? (
        <div className="empty">
          <ListTodo size={24} />
          <h3>No tasks here</h3>
          <p>
            {search
              ? "Try a different search or status filter."
              : "Create a task to start a reviewable workflow."}
          </p>
          <button
            className="btn small"
            onClick={() => {
              setSearch("");
              setFilter("all");
              setNewTask(true);
            }}
          >
            <Plus size={14} />
            New task
          </button>
        </div>
      ) : (
        items.map((t) => (
          <button
            className="task-row"
            key={t.id}
            onClick={() => openTask(t.id)}
          >
            <span className={"task-symbol status-" + t.status}>
              {React.createElement(iconFor(t.status), {
                size: 17,
                className: t.status === "running" ? "spin" : "",
              })}
            </span>
            <span className="task-name">
              <strong>{t.title}</strong>
              <span>
                <code>{t.id}</code>
                <i>·</i>
                <Source source={t.source} />
                <i>·</i>
                {relative(t.updated)}
              </span>
            </span>
            <Badge status={t.status} />
            <ChevronRight size={15} className="row-chevron" />
          </button>
        ))
      )}
    </div>
  );
  return (
    <div className="app-shell">
      {mobile && (
        <div className="sidebar-shade" onClick={() => setMobile(false)} />
      )}
      <aside className={"sidebar " + (mobile ? "open" : "")}>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("Overview");
          }}
        >
          <Logo />
          <span>
            OpenSuperAgent<small>Agent workspace</small>
          </span>
        </a>
        <button className="workspace-switch" onClick={() => setGuide(true)}>
          <span className="workspace-avatar">O</span>
          <span>
            Personal workspace
            <small>
              {state.mode === "demo" ? "Interactive demo" : "Local runtime"}
            </small>
          </span>
          <ChevronDown size={13} />
        </button>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {navs.map((n) => (
            <button
              key={n.name}
              className={"nav-item " + (page === n.name ? "active" : "")}
              onClick={() => navigate(n.name)}
            >
              <n.icon size={17} />
              <span>{n.name}</span>
              {n.count !== undefined && <small>{n.count}</small>}
            </button>
          ))}
        </nav>
        <div className="nav-label repository-label">REPOSITORY</div>
        <button className="repo-nav" onClick={() => navigate("Settings")}>
          <FolderGit2 size={16} />
          <span>
            {state.mode === "demo" ? "example / platform" : state.repository}
          </span>
          <span className={"dot " + (state.ready ? "green" : "amber")} />
        </button>
        <div className="sidebar-bottom">
          <div className="local-card">
            <ShieldCheck size={18} />
            <strong>
              {state.mode === "demo"
                ? "Explore the workflow"
                : "Changes stay local"}
            </strong>
            <p>
              {state.mode === "demo"
                ? "Try tasks, inspect changes, and review permissions. No API key needed."
                : "Isolated workspaces. Review changes before you publish."}
            </p>
            <button onClick={() => setGuide(true)}>
              {state.mode === "demo" ? "Run your own agent" : "Runtime setup"}
              <ArrowUpRight size={14} />
            </button>
          </div>
          <a
            className="nav-item"
            href={github + "/tree/main/docs"}
            target="_blank"
            rel="noreferrer"
          >
            <BookOpen size={16} />
            <span>Documentation</span>
            <ArrowUpRight size={13} />
          </a>
          <button
            className={"nav-item " + (page === "Settings" ? "active" : "")}
            onClick={() => navigate("Settings")}
          >
            <Settings2 size={16} />
            <span>Settings</span>
          </button>
          <div className="sidebar-footer">
            <span className="user-avatar">
              {state.mode === "demo" ? "D" : "L"}
            </span>
            <span>
              {state.mode === "demo" ? "Demo workspace" : "Local operator"}
              <small>OpenSuperAgent v0.1</small>
            </span>
            <a
              aria-label="View source on GitHub"
              href={github}
              target="_blank"
              rel="noreferrer"
            >
              <Github size={17} />
            </a>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-btn mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMobile(true)}
            >
              <Menu size={20} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>{page}</strong>
          </div>
          <div className="topbar-right">
            <label className="global-search">
              <Search size={15} />
              <input
                ref={searchRef}
                aria-label="Search tasks"
                placeholder="Search tasks…"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  if (page !== "Overview" && page !== "Tasks") setPage("Tasks");
                }}
              />
              <kbd>⌘ K</kbd>
            </label>
            <button
              className="icon-btn notification"
              aria-label={`Show ${needs.length} tasks needing attention`}
              onClick={() => {
                navigate("Tasks");
                setFilter("attention");
              }}
            >
              <Bell size={18} />
              {needs.length > 0 && <i />}
            </button>
            <a
              className="source-link"
              href={github}
              target="_blank"
              rel="noreferrer"
            >
              <Github size={16} />
              Source
              <ArrowUpRight size={13} />
            </a>
          </div>
        </header>
        <main>
          {state.mode === "demo" && demoNotice && (
            <div className="demo-banner">
              <span>
                <span className="demo-tag">
                  <CircleDot size={12} />
                  Interactive demo
                </span>
                <span>
                  Sample repository. Simulated execution. Your changes stay in
                  this browser.
                </span>
              </span>
              <button onClick={() => setGuide(true)}>
                Connect a real repository
                <ArrowRight size={13} />
              </button>
              <button
                className="icon-btn"
                aria-label="Dismiss demo notice"
                onClick={() => setDemoNotice(false)}
              >
                <X size={14} />
              </button>
            </div>
          )}
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                <span className={"dot " + (state.paused ? "amber" : "green")} />
                {state.paused
                  ? "DISPATCH PAUSED"
                  : state.mode === "demo"
                    ? "DEMO WORKSPACE"
                    : state.ready
                      ? "RUNTIME CONNECTED"
                      : "SETUP REQUIRED"}
              </div>
              <h1>
                {page === "Overview"
                  ? "Workspace overview"
                  : page === "Rules & permissions"
                    ? "Rules & permissions"
                    : page === "Tasks"
                      ? "Tasks"
                      : page === "Activity"
                        ? "Activity log"
                        : "Runtime settings"}
              </h1>
              <p>
                {page === "Overview"
                  ? "Manage repository tasks, review results, and decide what happens next."
                  : page === "Tasks"
                    ? "Every task has a clear request, an execution history, and a reviewable result."
                    : page === "Activity"
                      ? "Follow admissions, execution, and operator decisions in one place."
                      : page === "Rules & permissions"
                        ? "Explicit requests execute. Proactive candidates wait for your decision."
                        : "Configure the local runtime and understand its execution limits."}
              </p>
            </div>
            <div className="heading-actions">
              {(page === "Overview" || page === "Tasks") && (
                <>
                  <button
                    className="btn"
                    aria-label={
                      state.paused ? "Resume dispatch" : "Pause dispatch"
                    }
                    onClick={togglePause}
                  >
                    {state.paused ? <Play size={14} /> : <Pause size={14} />}
                    <span>
                      {state.paused ? "Resume dispatch" : "Pause dispatch"}
                    </span>
                  </button>
                  <button
                    className="btn primary"
                    onClick={() => setNewTask(true)}
                  >
                    <Plus size={16} />
                    New task
                  </button>
                </>
              )}
              {page === "Activity" && (
                <button className="btn" onClick={exportState}>
                  <ArrowDownToLine size={15} />
                  Export history
                </button>
              )}
            </div>
          </div>
          {(page === "Overview" || page === "Tasks") && (
            <>
              {page === "Overview" && (
                <>
                  <div className="stats-grid">
                    {[
                      {
                        label: "Needs your attention",
                        value: needs.length,
                        icon: GitPullRequest,
                        desc: `${state.tasks.filter((t) => t.status === "review").length} ready for review`,
                        cls: "purple",
                        target: "attention",
                      },
                      {
                        label: "Working",
                        value: working.length,
                        icon: Workflow,
                        desc: `${queued.length} task${queued.length === 1 ? "" : "s"} in queue`,
                        cls: "blue",
                        target: "running",
                      },
                      {
                        label: "Completed",
                        value: completed.length,
                        icon: CheckCheck,
                        desc: "Reviewed by an operator",
                        cls: "green",
                        target: "done",
                      },
                      {
                        label: "Observed candidates",
                        value: observed.length,
                        icon: Radio,
                        desc: "Waiting for explicit approval",
                        cls: "orange",
                        target: "observed",
                      },
                    ].map((s) => (
                      <button
                        key={s.label}
                        className="stat-card"
                        onClick={() => {
                          setPage("Tasks");
                          setFilter(s.target);
                        }}
                      >
                        <span className="stat-label">
                          {s.label}
                          <s.icon size={17} className={s.cls} />
                        </span>
                        <strong>{s.value}</strong>
                        <span className="stat-description">{s.desc}</span>
                      </button>
                    ))}
                  </div>
                </>
              )}
              <div
                className={"content-grid " + (page === "Tasks" ? "full" : "")}
              >
                <div className="main-column">
                  {page === "Overview" && needs.length > 0 && !search && (
                    <section className="attention-section">
                      <div className="section-heading">
                        <h2>
                          <span className="attention-dot" />
                          Needs your attention
                          <span className="count-chip">{needs.length}</span>
                        </h2>
                        <button
                          className="text-btn"
                          onClick={() => {
                            setPage("Tasks");
                            setFilter("attention");
                          }}
                        >
                          View all
                          <ArrowRight size={13} />
                        </button>
                      </div>
                      <div className="attention-cards">
                        {needs.slice(0, 2).map((t) => (
                          <button
                            key={t.id}
                            className="attention-card"
                            onClick={() => openTask(t.id)}
                          >
                            <span
                              className={
                                "attention-icon " +
                                (t.status === "blocked" ? "orange" : "purple")
                              }
                            >
                              {t.status === "blocked" ? (
                                <CircleDot size={19} />
                              ) : (
                                <GitPullRequest size={19} />
                              )}
                            </span>
                            <span className="attention-card-content">
                              <span>
                                <code>{t.id}</code>
                                <span>
                                  {t.status === "blocked"
                                    ? "Input needed"
                                    : "Review requested"}
                                </span>
                              </span>
                              <strong>{t.title}</strong>
                              <p>
                                {t.status === "blocked"
                                  ? "Provide context to unblock this task."
                                  : "Inspect the result and proposed changes."}
                              </p>
                              <span className="attention-cta">
                                {t.status === "blocked"
                                  ? "View blocker"
                                  : "Review changes"}
                                <ArrowUpRight size={13} />
                              </span>
                            </span>
                          </button>
                        ))}
                      </div>
                    </section>
                  )}
                  <section className="panel tasks-panel">
                    <div className="panel-heading">
                      <h2>
                        {page === "Tasks" ? "Repository tasks" : "All tasks"}
                        <span className="count-chip">{state.tasks.length}</span>
                      </h2>
                      <button
                        className="icon-btn"
                        aria-label="Open task filters"
                        onClick={() => {
                          setPage("Tasks");
                          setFilter(filter === "all" ? "attention" : "all");
                        }}
                      >
                        <SlidersHorizontal size={16} />
                      </button>
                    </div>
                    <div className="table-toolbar">
                      <div
                        className="tabs compact"
                        aria-label="Task status filter"
                      >
                        {[
                          { id: "all", name: "All tasks" },
                          { id: "running", name: "Working" },
                          { id: "review", name: "Review" },
                          { id: "done", name: "Completed" },
                          ...(page === "Tasks"
                            ? [
                                { id: "queued", name: "Queued" },
                                { id: "observed", name: "Observed" },
                                { id: "blocked", name: "Blocked" },
                              ]
                            : []),
                        ].map((f) => (
                          <button
                            aria-pressed={filter === f.id}
                            className={filter === f.id ? "active" : ""}
                            key={f.id}
                            onClick={() => setFilter(f.id)}
                          >
                            {f.name}
                          </button>
                        ))}
                      </div>
                      {filter === "attention" && (
                        <button
                          className="filter-chip"
                          onClick={() => setFilter("all")}
                        >
                          Needs attention
                          <X size={12} />
                        </button>
                      )}
                    </div>
                    <TaskTable items={tasks} />
                    <div className="table-footer">
                      <span>
                        {tasks.length} of {state.tasks.length} tasks
                      </span>
                      <span>
                        <ShieldCheck size={12} />
                        Human review before publication
                      </span>
                    </div>
                  </section>
                  {page === "Overview" && (
                    <section className="workflow-panel">
                      <div>
                        <h2>A reviewable path from request to result</h2>
                        <p>
                          Each stage keeps the task within its authorized scope.
                        </p>
                      </div>
                      <div className="flow">
                        {[
                          {
                            icon: Github,
                            label: "Receive",
                            desc: "Task or event",
                          },
                          {
                            icon: ShieldCheck,
                            label: "Authorize",
                            desc: "Explicit scope",
                          },
                          {
                            icon: FolderGit2,
                            label: "Execute",
                            desc: "Isolated worktree",
                          },
                          {
                            icon: GitPullRequest,
                            label: "Review",
                            desc: "Human decision",
                          },
                        ].map((f, i) => (
                          <React.Fragment key={f.label}>
                            <div className="flow-step">
                              <span>
                                <f.icon size={17} />
                              </span>
                              <strong>{f.label}</strong>
                              <small>{f.desc}</small>
                            </div>
                            {i < 3 && (
                              <div className="flow-line">
                                <ArrowRight size={13} />
                              </div>
                            )}
                          </React.Fragment>
                        ))}
                      </div>
                    </section>
                  )}
                </div>
                {page === "Overview" && (
                  <aside className="right-column">
                    <section className="panel repo-panel">
                      <div className="panel-heading">
                        <h2>Repository</h2>
                        <FolderGit2 size={16} />
                      </div>
                      <div className="repo-details">
                        <span className="repo-icon">
                          <Code2 size={23} />
                        </span>
                        <strong>{state.repository}</strong>
                        <span className="repo-branch">
                          <GitBranch size={12} />
                          {state.mode === "demo"
                            ? "main · sample repository"
                            : "Tasks start from committed HEAD"}
                        </span>
                        <dl>
                          <div>
                            <dt>Runtime</dt>
                            <dd>
                              <span
                                className={
                                  "dot " + (state.ready ? "green" : "amber")
                                }
                              />
                              {state.mode === "demo"
                                ? "Simulated"
                                : state.ready
                                  ? "Ready"
                                  : "Needs setup"}
                            </dd>
                          </div>
                          <div>
                            <dt>Proactive mode</dt>
                            <dd>Observe only</dd>
                          </div>
                          <div>
                            <dt>Publication</dt>
                            <dd>Manual review</dd>
                          </div>
                        </dl>
                        <button
                          className="btn full-width"
                          onClick={() => navigate("Settings")}
                        >
                          View configuration
                          <ArrowUpRight size={13} />
                        </button>
                      </div>
                    </section>
                    <section className="panel activity-panel">
                      <div className="panel-heading">
                        <h2>Recent activity</h2>
                        <button
                          className="text-btn"
                          onClick={() => navigate("Activity")}
                        >
                          View all
                          <ArrowRight size={12} />
                        </button>
                      </div>
                      <div className="timeline">
                        {state.events.slice(0, 5).map((e, i) => (
                          <button
                            key={e.seq}
                            className="timeline-item"
                            onClick={() =>
                              e.task_id
                                ? openTask(e.task_id)
                                : navigate("Activity")
                            }
                          >
                            <span
                              className={
                                "timeline-dot " + (i === 0 ? "purple" : "")
                              }
                            >
                              {e.kind === "review" ? (
                                <GitPullRequest size={11} />
                              ) : e.kind === "complete" ? (
                                <Check size={11} />
                              ) : (
                                <Circle size={8} />
                              )}
                            </span>
                            <span>
                              <p>{e.message}</p>
                              <small>{relative(e.created)}</small>
                            </span>
                          </button>
                        ))}
                        {state.events.length === 0 && (
                          <p className="muted">
                            New activity will appear here.
                          </p>
                        )}
                      </div>
                    </section>
                    <div className="version-note">
                      <span className="dot green" />
                      Open source · Local first
                      <a
                        href={github + "/blob/main/LICENSE"}
                        target="_blank"
                        rel="noreferrer"
                      >
                        MIT license
                        <ArrowUpRight size={11} />
                      </a>
                    </div>
                  </aside>
                )}
              </div>
            </>
          )}
          {page === "Activity" && (
            <section className="panel event-panel">
              <div className="panel-heading">
                <h2>
                  Execution history
                  <span className="count-chip">{state.events.length}</span>
                </h2>
                <span className="muted">Latest 250 events</span>
              </div>
              {state.events.length === 0 ? (
                <div className="empty">
                  <Activity size={24} />
                  <h3>No activity yet</h3>
                  <p>Task admission and execution events will appear here.</p>
                </div>
              ) : (
                state.events.map((e) => (
                  <button
                    key={e.seq}
                    className="event-row"
                    onClick={() => e.task_id && openTask(e.task_id)}
                  >
                    <span className="event-icon">
                      <Activity size={16} />
                    </span>
                    <span>
                      <strong>{e.message}</strong>
                      <small>
                        {e.task_id || "Workspace"}
                        <i>·</i>
                        {e.kind}
                      </small>
                    </span>
                    <time dateTime={e.created}>
                      {new Date(e.created).toLocaleString()}
                    </time>
                    {e.task_id && <ChevronRight size={14} />}
                  </button>
                ))
              )}
            </section>
          )}
          {page === "Rules & permissions" && (
            <>
              <div className="policy-banner">
                <ShieldCheck size={24} />
                <div>
                  <h2>Permissions are enforced by the runtime</h2>
                  <p>
                    Task instructions provide context. They cannot expand the
                    configured tools, repository, or allowed actors.
                  </p>
                </div>
                <span className="badge status-done">Policy v1</span>
              </div>
              <div className="rules-grid">
                {[
                  {
                    icon: Terminal,
                    name: "Explicit requests",
                    tag: "Enabled",
                    text: "Tasks created by the local operator are authorized for local code changes. GitHub requests require a valid signature, an allowed actor, the configured repository, and an agent mention.",
                    list: [
                      "A mandate is recorded with every task",
                      "Only the configured repository is selected",
                      "The task receives its own Git worktree",
                    ],
                  },
                  {
                    icon: Radio,
                    name: "Proactive candidates",
                    tag: "Observe only",
                    text: "Candidate work stays visible without starting a worker. The optional GitHub watcher records issues labeled agent-candidate as observed work. Candidates stay idle until a person approves them.",
                    list: [
                      "Candidates start in the Observed state",
                      "A person explicitly approves execution",
                      "External text cannot change this rule",
                    ],
                  },
                  {
                    icon: GitPullRequest,
                    name: "Review & delivery",
                    tag: "Human controlled",
                    text: "The agent produces a local summary and a diff for inspection. Publication remains an operator action outside the runtime.",
                    list: [
                      "No model-controlled shell commands",
                      "No file deletion, commit, push or merge tools",
                      "Interrupted workspaces are preserved",
                    ],
                  },
                ].map((r) => (
                  <section className="panel rule-card" key={r.name}>
                    <span className="rule-icon">
                      <r.icon size={22} />
                    </span>
                    <div className="rule-card-title">
                      <h2>{r.name}</h2>
                      <span>{r.tag}</span>
                    </div>
                    <p>{r.text}</p>
                    <ul>
                      {r.list.map((l) => (
                        <li key={l}>
                          <Check size={14} />
                          {l}
                        </li>
                      ))}
                    </ul>
                  </section>
                ))}
              </div>
              <section className="panel permission-table">
                <div className="panel-heading">
                  <h2>Tool permissions</h2>
                  <span className="muted">Enforced in code</span>
                </div>
                {[
                  [
                    "Read & list files",
                    "Allowed",
                    "Task workspace; secret paths and symlinks are blocked.",
                  ],
                  [
                    "Create & edit text files",
                    "Allowed",
                    "Up to 64 KiB per file; changes stay in the worktree.",
                  ],
                  [
                    "Inspect Git changes",
                    "Allowed",
                    "Diff preview only; external diff tools are disabled.",
                  ],
                  [
                    "Shell, deletion & GitHub writes",
                    "Unavailable",
                    "No model tools exist for these operations.",
                  ],
                ].map(([a, b, c]) => (
                  <div key={a}>
                    <strong>{a}</strong>
                    <span
                      className={
                        "permission-state " +
                        (b === "Allowed" ? "green" : "muted")
                      }
                    >
                      {b}
                    </span>
                    <p>{c}</p>
                  </div>
                ))}
              </section>
            </>
          )}
          {page === "Settings" && (
            <div className="settings-grid">
              <section className="panel settings-panel">
                <div className="panel-heading">
                  <h2>
                    <Settings2 size={17} />
                    Runtime configuration
                  </h2>
                  <span className="badge status-observed">
                    {state.mode === "demo" ? "Demo" : "Local"}
                  </span>
                </div>
                <dl>
                  {[
                    ["Repository", state.repository],
                    ["Model", state.model],
                    ["Workers", "2 concurrent workers"],
                    [
                      "Attempt budget",
                      `${state.max_steps} model steps · 8 tools per step`,
                    ],
                    ["File limit", "64 KiB per read or write"],
                    ["API binding", "127.0.0.1 only"],
                    [
                      "State storage",
                      state.mode === "demo"
                        ? "This browser’s local storage"
                        : "Local SQLite database + Git worktrees",
                    ],
                    [
                      "Publication",
                      "Operator controlled; no automatic GitHub writes",
                    ],
                  ].map(([k, v]) => (
                    <div key={k}>
                      <dt>{k}</dt>
                      <dd>{v}</dd>
                    </div>
                  ))}
                </dl>
                <div className="settings-bottom">
                  <p>
                    Credentials are configured in the server environment and
                    never entered in this console.
                  </p>
                  <button
                    className="btn primary"
                    onClick={() => setGuide(true)}
                  >
                    View setup guide
                    <ArrowUpRight size={14} />
                  </button>
                </div>
              </section>
              <div>
                <section className="panel settings-panel">
                  <div className="panel-heading">
                    <h2>Workspace data</h2>
                  </div>
                  <div className="settings-body">
                    <p>
                      Download the visible tasks and activity history as JSON.
                    </p>
                    <button className="btn full-width" onClick={exportState}>
                      <ArrowDownToLine size={15} />
                      Export task history
                    </button>
                    {state.mode === "demo" && (
                      <>
                        <hr />
                        <h3>Reset the demo</h3>
                        <p>
                          Restore the example tasks in this browser. Real
                          repository data is never affected.
                        </p>
                        <button
                          className="btn full-width"
                          onClick={() => {
                            if (
                              window.confirm(
                                "Replace this browser’s demo tasks with the original examples?",
                              )
                            ) {
                              setState(seed());
                              notify("Demo restored.");
                            }
                          }}
                        >
                          <RotateCcw size={14} />
                          Reset sample tasks
                        </button>
                      </>
                    )}
                  </div>
                </section>
                <div className="about-card">
                  <Logo />
                  <h3>OpenSuperAgent</h3>
                  <p>
                    An independent, local-first implementation inspired by
                    DeepSeek’s SuperAgent research prototype.
                  </p>
                  <a
                    href={github + "/blob/main/docs/research.md"}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Read the design notes
                    <ArrowUpRight size={13} />
                  </a>
                </div>
              </div>
            </div>
          )}
          <footer className="main-footer">
            <span>
              OpenSuperAgent<span> / </span>
              {state.mode === "demo"
                ? "Interactive demonstration"
                : "Local agent workspace"}
            </span>
            <a
              href="https://github.com/deepseek-ai/dsh-superagent-prototype"
              target="_blank"
              rel="noreferrer"
            >
              Inspired by DeepSeek’s SuperAgent research
              <ArrowUpRight size={11} />
            </a>
          </footer>
        </main>
      </div>
      {dialogOpen && (
        <div
          className="modal-backdrop"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) {
              setNewTask(false);
              setSelected(null);
              setGuide(false);
            }
          }}
        >
          <div
            className={
              "modal " + (task ? "task-modal" : guide ? "guide-modal" : "")
            }
            role="dialog"
            aria-modal="true"
            aria-labelledby="dialog-title"
            ref={modalRef}
          >
            <button
              className="icon-btn close-modal"
              aria-label="Close dialog"
              onClick={() => {
                setNewTask(false);
                setSelected(null);
                setGuide(false);
              }}
            >
              <X size={19} />
            </button>
            {newTask && (
              <form onSubmit={createTask}>
                <span className="modal-kicker">
                  <Plus size={15} />
                  NEW TASK
                </span>
                <h2 id="dialog-title">What should the agent work on?</h2>
                <p className="modal-description">
                  Describe a concrete change. The agent works within this
                  request and prepares a result for review.
                </p>
                {state.mode === "demo" && (
                  <div className="inline-notice">
                    This demo simulates execution. No model or repository is
                    connected.
                  </div>
                )}
                <label className="field">
                  Task title
                  <input
                    name="title"
                    required
                    maxLength={160}
                    placeholder="e.g. Improve validation for webhook events"
                    autoComplete="off"
                  />
                </label>
                <label className="field">
                  Instructions
                  <textarea
                    name="prompt"
                    required
                    maxLength={20000}
                    rows={6}
                    placeholder="Explain the desired behavior, relevant files, and acceptance criteria…"
                  />
                </label>
                <div className="scope-note">
                  <ShieldCheck size={16} />
                  <span>
                    Local file changes only. You review the result before
                    publication.
                  </span>
                </div>
                <div className="modal-actions">
                  <button
                    type="button"
                    className="btn"
                    onClick={() => setNewTask(false)}
                  >
                    Cancel
                  </button>
                  <button disabled={busy} className="btn primary" type="submit">
                    {busy ? (
                      <Loader2 className="spin" size={15} />
                    ) : (
                      <Plus size={15} />
                    )}
                    Create task
                  </button>
                </div>
              </form>
            )}
            {task && (
              <>
                <div className="task-detail-heading">
                  <code>{task.id}</code>
                  <Badge status={task.status} />
                  <h2 id="dialog-title">{task.title}</h2>
                  <span>
                    <Source source={task.source} />
                    <i>·</i>Created {relative(task.created)}
                    <i>·</i>
                    {task.attempts} attempt{task.attempts === 1 ? "" : "s"}
                  </span>
                </div>
                <div className="tabs detail-tabs">
                  {["Overview", "Changes", "Activity"].map((t) => (
                    <button
                      key={t}
                      className={tab === t ? "active" : ""}
                      onClick={() => setTab(t)}
                    >
                      {t === "Overview" ? (
                        <ListTodo size={14} />
                      ) : t === "Changes" ? (
                        <FileCode2 size={14} />
                      ) : (
                        <Activity size={14} />
                      )}{" "}
                      {t}
                    </button>
                  ))}
                </div>
                <div className="task-detail-body">
                  {tab === "Overview" && (
                    <>
                      <h3>Request</h3>
                      <p className="preserve">{task.prompt}</p>
                      <div className="mandate-card">
                        <ShieldCheck size={18} />
                        <div>
                          <strong>
                            {task.mandate.basis === "explicit"
                              ? "Explicit authorization"
                              : "Observed candidate"}
                          </strong>
                          <p>{task.mandate.scope}</p>
                          <small>
                            {task.mandate.actor} · Policy {task.mandate.policy}
                          </small>
                        </div>
                      </div>
                      {task.result && (
                        <>
                          <h3>
                            {task.status === "blocked"
                              ? "What the agent needs"
                              : "Worker result"}
                          </h3>
                          <p className="preserve result-text">{task.result}</p>
                        </>
                      )}
                      {!task.result && (
                        <div className="detail-state">
                          <Clock3 size={20} />
                          <p>
                            {task.status === "observed"
                              ? "This candidate is waiting for your explicit approval."
                              : task.status === "running"
                                ? "The worker is processing this request. New activity appears in the Activity tab."
                                : task.status === "stopped"
                                  ? "This task was stopped. Existing workspace files are retained."
                                  : "This task is waiting for an available worker."}
                          </p>
                        </div>
                      )}
                      {["blocked", "review"].includes(task.status) && (
                        <form
                          className="followup-form"
                          onSubmit={(e) => {
                            e.preventDefault();
                            const form = e.currentTarget;
                            const content = String(
                              new FormData(form).get("context") || "",
                            ).trim();
                            if (content)
                              void action(task.id, "followup", content).then(
                                () => form.reset(),
                              );
                          }}
                        >
                          <label className="field">
                            Additional context
                            <textarea
                              name="context"
                              required
                              maxLength={10000}
                              rows={3}
                              placeholder="Provide a failure log, clarify the expected result, or request a revision within this task’s scope…"
                            />
                          </label>
                          <button
                            className="btn small"
                            disabled={busy}
                            type="submit"
                          >
                            <ArrowRight size={13} />
                            Send context & retry
                          </button>
                        </form>
                      )}
                      {task.workspace && (
                        <>
                          <h3>Workspace</h3>
                          <code className="workspace-path">
                            {task.workspace}
                          </code>
                        </>
                      )}
                    </>
                  )}
                  {tab === "Changes" && (
                    <>
                      <div className="diff-title">
                        <h3>Local changes</h3>
                        {task.diff && (
                          <button
                            className="btn small"
                            onClick={() => copy(task.diff)}
                          >
                            <Copy size={12} />
                            Copy diff
                          </button>
                        )}
                      </div>
                      {task.diff ? (
                        <pre className="diff-view">
                          {task.diff.split("\n").map((line, i) => (
                            <div
                              key={i}
                              className={
                                line.startsWith("+")
                                  ? "addition"
                                  : line.startsWith("-")
                                    ? "deletion"
                                    : line.startsWith("@@")
                                      ? "diff-meta"
                                      : ""
                              }
                            >
                              <span className="line-number">{i + 1}</span>
                              <code>{line || " "}</code>
                            </div>
                          ))}
                        </pre>
                      ) : (
                        <div className="empty">
                          <FileCode2 size={25} />
                          <h3>No changes to display</h3>
                          <p>
                            File changes appear here when the worker finishes a
                            task.
                          </p>
                        </div>
                      )}
                      <p className="diff-footnote">
                        {state.mode === "demo"
                          ? "Illustrative sample patch. No repository was modified."
                          : "Diffs are previews. Inspect the full worktree and run your checks before publishing."}
                      </p>
                    </>
                  )}
                  {tab === "Activity" && (
                    <div className="task-events">
                      {state.events
                        .filter((e) => e.task_id === task.id)
                        .map((e) => (
                          <div key={e.seq}>
                            <span className="dot purple" />
                            <span>
                              <p>{e.message}</p>
                              <small>
                                {new Date(e.created).toLocaleString()}
                              </small>
                            </span>
                          </div>
                        ))}
                    </div>
                  )}
                </div>
                <div className="task-detail-footer">
                  <span>
                    <ShieldCheck size={13} />
                    {task.workspace ? "Workspace retained" : "Request retained"}
                  </span>
                  <div>
                    {!["done", "stopped"].includes(task.status) && (
                      <button
                        className="btn small"
                        disabled={busy}
                        onClick={() => action(task.id, "stop")}
                      >
                        <Square size={12} />
                        Stop task
                      </button>
                    )}
                    {task.status === "review" && (
                      <button
                        className="btn primary"
                        disabled={busy}
                        onClick={() => action(task.id, "complete")}
                      >
                        <Check size={15} />
                        Mark reviewed
                      </button>
                    )}
                    {task.status === "observed" && (
                      <button
                        className="btn primary"
                        disabled={busy}
                        onClick={() => action(task.id, "approve")}
                      >
                        <Play size={14} />
                        Approve & queue
                      </button>
                    )}
                    {task.status === "blocked" && (
                      <button
                        className="btn primary"
                        disabled={busy}
                        onClick={() => action(task.id, "retry")}
                      >
                        <RotateCcw size={14} />
                        Retry task
                      </button>
                    )}
                  </div>
                </div>
              </>
            )}
            {guide && (
              <>
                <span className="modal-kicker">
                  <Terminal size={16} />
                  LOCAL RUNTIME
                </span>
                <h2 id="dialog-title">Connect your own repository</h2>
                <p className="modal-description">
                  Run the console locally to process real tasks. The public demo
                  never requests credentials.
                </p>
                <ol className="setup-steps">
                  <li>
                    <span>1</span>
                    <div>
                      <h3>Install and build</h3>
                      <pre>
                        git clone {github}.git{"\n"}cd OpenSuperAgent{"\n"}pnpm
                        install --frozen-lockfile{"\n"}pnpm build
                      </pre>
                    </div>
                  </li>
                  <li>
                    <span>2</span>
                    <div>
                      <h3>Configure the server environment</h3>
                      <p>
                        Use your own repository path and provider credentials.
                        Keep keys outside source control.
                      </p>
                      <pre>
                        export OSA_REPO=/absolute/path/to/repo{"\n"}export
                        OSA_BASE_URL=https://api.deepseek.com{"\n"}export
                        OSA_MODEL=deepseek-flash{"\n"}# Set OSA_API_KEY securely
                        in your environment.
                      </pre>
                    </div>
                  </li>
                  <li>
                    <span>3</span>
                    <div>
                      <h3>Start the local console</h3>
                      <pre>python3 -m server.app</pre>
                      <p>
                        Open <code>http://127.0.0.1:8765</code>. Create a task,
                        inspect its local diff, and run your own checks before
                        publishing.
                      </p>
                    </div>
                  </li>
                </ol>
                <div className="scope-note">
                  <ShieldCheck size={17} />
                  <span>
                    The built-in worker uses bounded file tools. Repository
                    contents are sent to your configured model provider when a
                    task executes.
                  </span>
                </div>
                <div className="modal-actions">
                  <a
                    className="btn"
                    href={github + "/blob/main/docs/getting-started.md"}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Full setup guide
                    <ArrowUpRight size={14} />
                  </a>
                  <button
                    className="btn primary"
                    onClick={() => setGuide(false)}
                  >
                    Got it
                    <Check size={14} />
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
      {toast && (
        <div className="toast" role="status">
          <CircleCheck size={16} />
          {toast}
          <button
            aria-label="Dismiss notification"
            onClick={() => setToast("")}
          >
            <X size={13} />
          </button>
        </div>
      )}
    </div>
  );
}
function Logo() {
  return (
    <span className="logo" aria-hidden="true">
      <svg viewBox="0 0 32 32">
        <path
          d="M8 8.5h10l6 7.5-6 7.5H8l6-7.5z"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}
