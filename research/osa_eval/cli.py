from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
from pathlib import Path

from .benchmarks import PINS, prepare_asyn, prepare_pro, verify_checkout, sha256
from .contracts import Event, Limits, canonical, digest
from .journal import Journal
from .kernel import Kernel, WORKER_PROMPT, EXECUTE
from .metrics import summarize, validate_comparison
from .model import ChatModel
from .runtime import ARCHITECTURES, Runtime
from .smoke import run_smoke
from .workload import schedule
from .workspace import DockerWorkspace
from .podman_backend import IsolatedPodmanWorkspace
from .upstream_runtime import CoreClient, UpstreamRuntime
from .swebench_pro import ProTask
from .campaign import ProCampaign
from .analysis import analyze
from .reclassification import reclassify
from .gates import validate_tasks
from .artifact_validation import ArtifactValidation


def workspace_factory(backend, image_ids):
    def factory(task, purpose, name):
        image = image_ids[task.id]
        if backend["kind"] == "docker":
            env = task.config["environment"]
            prefix = (backend["command_prefix_by_task"][task.id] if "command_prefix_by_task" in backend
                      else backend.get("command_prefix"))
            return DockerWorkspace.create(image=image, name="osa-" + name, purpose=purpose,
                cpus=env["cpus"], memory_mb=env["memory_mb"], command_prefix=prefix)
        if backend["kind"] == "podman_inherited_netns":
            return IsolatedPodmanWorkspace.create(image=image, name="osa-" + name, purpose=purpose,
                graph_root=backend["graph_root"], run_root=backend["run_root"])
        raise ValueError("Unsupported campaign workspace backend")
    return factory


def run_gates(args):
    config, images = read(args.config), read(args.images)
    root = Path(config["pro_checkout"])
    provenance = verify_checkout(root, "swebench_pro")
    official_ids = set(subprocess.check_output(["git", "-C", str(root), "ls-tree", "--name-only", "HEAD:v2/tasks"], text=True).splitlines())
    if any(task_id not in official_ids or task_id not in images for task_id in args.task_ids):
        raise ValueError("Every requested task needs an official tracked ID and a frozen image record")
    tasks = {task_id: ProTask(root / "v2/tasks" / task_id) for task_id in args.task_ids}
    for record in [images[task_id] for task_id in tasks]:
        if not record.get("manifest_digest", "").startswith("sha256:") or not record.get("image_id"):
            raise ValueError("Image record requires its resolved official manifest digest and config identity")
    factory = workspace_factory(config["workspace_backend"], {task_id: images[task_id]["image_id"] for task_id in tasks})
    return asyncio.run(validate_tasks(tasks, factory, args.output, provenance={"benchmark": provenance, "images": images, "backend": config["workspace_backend"]}))


def run_pro(args):
    config, workload, gates = read(args.config), read(args.workload), read(args.gates)
    root = Path(config["pro_checkout"])
    provenance = verify_checkout(root, "swebench_pro")
    events = [Event(**e) for e in workload["events"]]
    tasks = {e.task_id or e.id: ProTask(root / "v2/tasks" / (e.task_id or e.id)) for e in events}
    model = ChatModel(api_key=os.environ[config.get("api_key_env", "LLM_API_KEY")], **config["model"])
    limits = Limits(**config["limits"])
    base_factory = workspace_factory(config["workspace_backend"], {task_id: gates[task_id]["image_id"] for task_id in tasks})
    policies = config.get("worker_policy", {}).get("final_validation_by_task", {})
    if policies and not set(tasks) <= set(policies):
        raise ValueError("Every selected task requires the same frozen public validation policy")
    def factory(task,purpose,name):
        workspace=base_factory(task,purpose,name)
        if purpose=="agent" and task.id in policies:
            workspace.artifact_validation=ArtifactValidation(workspace,**policies[task.id])
        return workspace
    package = Path(__file__).parent
    source = {p.relative_to(package).as_posix(): sha256(p) for p in sorted(package.rglob("*")) if p.is_file() and p.suffix in {".py", ".mjs"}}
    campaign = ProCampaign(tasks, model, limits, factory, evaluator_gates=gates,
                           source_identity={"modules": source, "benchmark": provenance, "config": config},
                           upstream_checkout=config.get("upstream_checkout"), node_binary=config.get("node_binary", "node"))
    return asyncio.run(campaign.run(config["architecture"], events, args.output, seed=config["seed"], horizon_s=config["horizon_s"], subscriptions=config.get("subscriptions", True)))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def run_live(args):
    config = read(args.config)
    workload = read(args.workload)
    workspace_specs = read(args.workspaces)
    limits = Limits(**config.get("limits", {}))
    architecture = config["architecture"]
    if architecture not in (*ARCHITECTURES, "upstream_core_reference"):
        raise ValueError("Unknown architecture")
    if len({row["container"] for row in workspace_specs.values()}) != len(workspace_specs):
        raise ValueError("Independent benchmark tasks must use distinct containers")
    workspaces = {}
    for task, spec in workspace_specs.items():
        backend = spec.get("backend", "docker")
        if backend == "podman_inherited_netns":
            prefix = ["podman", "--storage-driver", "vfs", "--root", spec["graph_root"], "--runroot", spec["run_root"]]
        elif backend == "docker":
            prefix = ["docker"]
        else:
            raise ValueError("Unknown workspace backend")
        observed = json.loads(subprocess.check_output([*prefix, "inspect", spec["container"]], text=True))[0]
        if observed["Image"] != spec["image_digest"]:
            raise ValueError("Container image digest differs from its manifest: " + task)
        if not observed["State"]["Running"]:
            raise ValueError("Container is not running: " + task)
        if observed["HostConfig"].get("Privileged"):
            raise ValueError("Privileged task containers are refused")
        if backend == "docker":
            if observed["HostConfig"]["NetworkMode"] != "none":
                raise ValueError("Agent container must have network mode none: " + task)
            workspaces[task] = DockerWorkspace(observed["Id"], spec["cwd"], image_digest=spec["image_digest"])
        else:
            namespace = os.readlink(f"/proc/{observed['State']['Pid']}/ns/net")
            if namespace == os.readlink("/proc/self/ns/net"):
                raise ValueError("Podman task shares the actual host network namespace")
            workspaces[task] = IsolatedPodmanWorkspace(prefix, observed["Id"], spec["cwd"], observed["Image"], namespace)
    model_config = dict(config["model"])
    model = ChatModel(api_key=os.environ[config.get("api_key_env", "LLM_API_KEY")], **model_config)
    identity = {"architecture": architecture, "limits": limits.public(), "model": model.identity,
                "workload_sha256": digest(workload), "workspace_manifest_sha256": digest(workspace_specs),
                "worker_prompt_sha256": digest(WORKER_PROMPT), "tools_sha256": digest([EXECUTE]),
                "subscriptions": config.get("subscriptions", True), "evidence_tier": "exploratory-container-run"}
    if architecture == "upstream_core_reference":
        identity["upstream"] = {"commit": PINS["deepseek"]["commit"], "reference_scope": "unchanged domain core, benchmark-specific ports; DSH host replaced"}
    output = Path(args.output)
    journal = Journal(output / "run.sqlite3", token_budget=limits.token_budget, identity=identity)
    write(output / "identity.json", identity)
    try:
        kernel = Kernel(model, journal, limits)
        events = [Event(**e) for e in workload["events"]]
        if architecture == "upstream_core_reference":
            async def reference():
                client = await CoreClient(config["upstream_checkout"], output / "upstream-state.json", node=config.get("node_binary", "node")).start()
                try:
                    return await UpstreamRuntime(client, kernel).run(events, workspaces)
                finally:
                    await client.close()
            results = asyncio.run(reference())
        else:
            results = asyncio.run(Runtime(architecture, kernel, subscriptions=identity["subscriptions"]).run(events, workspaces))
        write(output / "completion_claims.json", {"official_grades": False, "tasks": results})
    finally:
        journal.export(output)


def main():
    parser = argparse.ArgumentParser(description="Independent Super-agent research tools; formal benchmark scores require native evaluators")
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--upstream-root", required=True)
    prepare.add_argument("--output", required=True)
    prepare.add_argument("--sample-count", type=int, default=24)
    prepare.add_argument("--seed", type=int, default=20261102)
    smoke = sub.add_parser("smoke")
    smoke.add_argument("--output", required=True)
    live = sub.add_parser("run")
    for name in ("config", "workload", "workspaces", "output"):
        live.add_argument("--" + name, required=True)
    pro = sub.add_parser("pro-run")
    for name in ("config", "workload", "gates", "output"):
        pro.add_argument("--" + name, required=True)
    gates = sub.add_parser("pro-gates")
    for name in ("config", "images", "output"):
        gates.add_argument("--" + name, required=True)
    gates.add_argument("--task-ids", nargs="+", required=True)
    metrics = sub.add_parser("summarize")
    metrics.add_argument("--rows", required=True)
    metrics.add_argument("--horizon-s", type=float, required=True)
    metrics.add_argument("--output", required=True)
    compare = sub.add_parser("check-comparison")
    compare.add_argument("--configs", required=True)
    compare.add_argument("--mode", choices=("capacity", "budget"), required=True)
    analysis = sub.add_parser("analyze")
    analysis.add_argument("--root", required=True)
    analysis.add_argument("--output", required=True)
    analysis.add_argument("--plots", action="store_true")
    analysis.add_argument("--reclassifications")
    classify = sub.add_parser("reclassify")
    classify.add_argument("--root", required=True)
    classify.add_argument("--output", required=True)
    arrivals = sub.add_parser("schedule")
    arrivals.add_argument("--tasks", required=True)
    arrivals.add_argument("--output", required=True)
    arrivals.add_argument("--mode", choices=("burst", "fixed", "poisson"), default="burst")
    arrivals.add_argument("--burst-size", type=int, default=4)
    arrivals.add_argument("--interval-s", type=float, default=60)
    arrivals.add_argument("--rate-per-s", type=float)
    arrivals.add_argument("--seed", type=int, default=20261102)
    args = parser.parse_args()
    if args.command == "prepare":
        root = Path(args.upstream_root)
        write(Path(args.output) / "swebench_pro_pilot.json", prepare_pro(root / "SWE-bench_Pro-os", count=args.sample_count, seed=args.seed))
        write(Path(args.output) / "asyncodebench.json", prepare_asyn(root / "AsynCodeBench"))
        write(Path(args.output) / "upstream-lock.json", PINS)
    elif args.command == "smoke":
        result = asyncio.run(run_smoke(args.output))
        print(canonical(result))
        if not all(r["passed"] for r in result):
            raise SystemExit(1)
    elif args.command == "run":
        run_live(args)
    elif args.command == "pro-run":
        run_pro(args)
    elif args.command == "pro-gates":
        run_gates(args)
    elif args.command == "summarize":
        write(args.output, summarize(read(args.rows), horizon_s=args.horizon_s))
    elif args.command == "check-comparison":
        print(canonical(validate_comparison(read(args.configs), args.mode)))
    elif args.command == "analyze":
        print(canonical(analyze(args.root, args.output, plots=args.plots, reclassifications=args.reclassifications)))
    elif args.command == "reclassify":
        print(canonical(reclassify(args.root, args.output)))
    elif args.command == "schedule":
        write(args.output, schedule(read(args.tasks), seed=args.seed, mode=args.mode, burst_size=args.burst_size,
                                    interval_s=args.interval_s, rate_per_s=args.rate_per_s))


if __name__ == "__main__":
    main()
