"""Prepare provenance manifests from official checkouts; never expose gold/test payloads to agents."""
from __future__ import annotations

import hashlib
import json
import subprocess
import tomllib
from pathlib import Path

from .contracts import digest
from .workload import select_tasks

PINS = {
    "deepseek": {"url": "https://github.com/deepseek-ai/dsh-superagent-prototype.git", "commit": "6337fc823ce20251c8de8085948165c81aaa701e"},
    "swebench_pro": {"url": "https://github.com/scaleapi/SWE-bench_Pro-os.git", "commit": "66f92766bba642462d4bbe5479e83f91f9211862", "tag": "v2.0.0"},
    "asyncodebench": {"url": "https://github.com/KaituoZhang/AsynCodeBench.git", "commit": "2a639b049f249e79eb2031876bc06a110be9ac3a"},
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_checkout(root, name):
    root = Path(root).resolve()
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if head != PINS[name]["commit"]:
        raise ValueError(name + " checkout does not match the pinned commit")
    if subprocess.run(["git", "-C", str(root), "diff", "--no-ext-diff", "--no-textconv", "--quiet", "HEAD", "--"], check=False).returncode:
        raise ValueError(name + " checkout has modified tracked files")
    return {**PINS[name], "observed_head": head}


def prepare_pro(root, *, count=24, seed=20261102):
    root = Path(root)
    provenance = verify_checkout(root, "swebench_pro")
    task_root = root / "v2/tasks"
    task_ids = sorted(p.name for p in task_root.iterdir() if p.is_dir())
    if len(task_ids) != 642:
        raise ValueError("Expected exactly 642 official Pro V2 tasks")
    selected = select_tasks(task_ids, count, seed)
    rows = []
    for task_id in selected:
        task = task_root / task_id
        config = tomllib.loads((task / "task.toml").read_text(encoding="utf-8"))
        if config.get("agent", {}).get("network_mode") != "no-network":
            raise ValueError("Official no-network agent policy is missing")
        hashes = {p.relative_to(task).as_posix(): sha256(p) for p in sorted(task.rglob("*")) if p.is_file()}
        rows.append({"id": task_id, "task_files_sha256": hashes,
                     "instruction_path": "v2/tasks/" + task_id + "/instruction.md",
                     "image_reference": config["environment"]["docker_image"],
                     "resolved_image_digest": None})
    return {"schema_version": 1, "benchmark": "swebench_pro_v2", "provenance": provenance, "seed": seed,
            "selection": "SHA256-ranked sample of sorted public task ids, without model outcomes", "official_task_count": 642,
            "tasks": rows, "formal_ready": False,
            "remaining_gates": ["Resolve and verify image digests", "Run network/history probes", "Validate oracle and empty patch on selected tasks", "Grade each patch on a pristine image"]}


def prepare_asyn(root):
    root = Path(root)
    provenance = verify_checkout(root, "asyncodebench")
    release_path = root / "manifests/release/v0.4/official_tasks.json"
    release = json.loads(release_path.read_text(encoding="utf-8"))
    if not release["stable_release_ready"] or release["task_count"] != 19:
        raise ValueError("Expected the stable 19-task release")
    profile = root / release["execution_profile"]["path"]
    if sha256(profile) != release["execution_profile"]["sha256"]:
        raise ValueError("Execution profile checksum mismatch")
    return {"schema_version": 1, "benchmark": "asyncodebench", "provenance": provenance,
            "release_manifest_sha256": sha256(release_path), "release": release["release_version"],
            "release_index_execution_profile": release["execution_profile"],
            "runtime_profiles": {"single_serial_async_private_caid": {"path": "configs/evaluation/official_execution_profile.v2.json", "sha256": sha256(profile)},
                                 "async_manager": {"path": "configs/evaluation/official_execution_profile.v4.json", "sha256": sha256(root / "configs/evaluation/official_execution_profile.v4.json")}},
            "tasks": release["official_task_ids"],
            "native_protocols": ["single", "serial_specialists", "async_private", "caid_manager", "async_manager"],
            "custom_agent_contract": "One assignment execution only; native harness retains orchestration and evaluation",
            "formal_ready": False, "remaining_gates": ["Native custom-agent wiring smoke", "Model-enabled native runs and validate-run", "Separate and validate any custom orchestration extension"]}
