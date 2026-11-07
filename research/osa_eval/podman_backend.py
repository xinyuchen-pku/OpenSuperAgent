"""Linux Podman backend for a host with mount/PID isolation but no NET_ADMIN capability.

Each agent container inherits a fresh network namespace from unshare. Podman's
host network mode means that isolated parent namespace, never the host namespace.
The actual kernel namespace identity is checked before exposing the workspace.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path


class IsolatedPodmanWorkspace:
    cleanup_grace_s = 6.0

    def __init__(self, prefix, container, cwd, image_id, network_namespace):
        self.prefix, self.container, self.cwd = list(prefix), container, cwd
        self.identity = {"backend": "podman-inherited-private-netns", "container": container, "cwd": cwd,
                         "image_id": image_id, "network_namespace": network_namespace,
                         "network_egress": "private namespace without interfaces/routes", "cgroup_limits_enforced": False}

    @classmethod
    def create(cls, *, image, name, cwd="/app", graph_root=None, run_root=None, purpose="agent"):
        if purpose not in {"agent", "verifier"}:
            raise ValueError("Workspace purpose must be agent or verifier")
        prefix = ["podman"]
        if graph_root:
            prefix += ["--storage-driver", "vfs", "--root", str(graph_root), "--runroot", str(run_root)]
        # Disable a default sysctl that cannot be changed in this outer container.
        config = Path(run_root or "/dev/shm/osa-eval") / "containers.conf"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text("[containers]\ndefault_sysctls=[]\n", encoding="utf-8")
        env = dict(os.environ, CONTAINERS_CONF=str(config))
        command = (["unshare", "--net"] if purpose == "agent" else []) + [*prefix, "run", "--detach", "--name", name, "--cgroups=disabled",
                   "--network", "host", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                   "--pull", "never", image, "sh", "-c", "exec sleep infinity"]
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=300)
        if result.returncode:
            raise RuntimeError("Podman workspace creation failed: " + result.stderr[-2000:])
        container = result.stdout.strip().splitlines()[-1]
        info = json.loads(subprocess.check_output([*prefix, "inspect", container], text=True, env=env))[0]
        pid = int(info["State"]["Pid"])
        actual = os.readlink(f"/proc/{pid}/ns/net")
        if purpose == "agent" and actual == os.readlink("/proc/self/ns/net"):
            subprocess.run([*prefix, "stop", "--time", "5", container], check=False, env=env, capture_output=True)
            raise RuntimeError("Container inherited the host network namespace; workspace refused")
        secret_names = {"LLM_API_KEY", "OPENAI_API_KEY", "VLLM_API_KEY", "BOS_ACCESS_KEY", "BOS_SECRET_KEY", "WANDB_API_KEY"}
        if any(v.split("=", 1)[0] in secret_names for v in info.get("Config", {}).get("Env", [])):
            subprocess.run([*prefix, "stop", "--time", "5", container], check=False, env=env, capture_output=True)
            raise RuntimeError("Model or platform credential environment found in task container")
        workspace = cls(prefix, container, cwd, info["Image"], actual)
        workspace.identity.update(purpose=purpose, network_egress="private namespace without interfaces/routes" if purpose == "agent" else "public verifier network, per official task contract")
        return workspace

    async def execute(self, command, timeout_s):
        process = await asyncio.create_subprocess_exec(*self.prefix, "exec", "-w", self.cwd, self.container,
            "timeout", "--signal=TERM", "--kill-after=5", str(timeout_s), "bash", "-c", command,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout_s + 20)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        return {"stdout": stdout.decode("utf-8", errors="replace"), "stderr": stderr.decode("utf-8", errors="replace"), "returncode": process.returncode}

    @classmethod
    def resume(cls, *, prefix, container, cwd, image_id):
        info = json.loads(subprocess.check_output([*prefix, "inspect", container], text=True))[0]
        if info["Image"] != image_id or info["State"]["Running"] or info["HostConfig"]["NetworkMode"] != "host":
            raise ValueError("Resume requires the exact stopped agent image and inherited-netns configuration")
        subprocess.run(["unshare", "--net", *prefix, "start", info["Id"]], check=True, capture_output=True, timeout=300)
        fresh = json.loads(subprocess.check_output([*prefix, "inspect", info["Id"]], text=True))[0]
        namespace = os.readlink(f"/proc/{fresh['State']['Pid']}/ns/net")
        if namespace == os.readlink("/proc/self/ns/net"):
            subprocess.run([*prefix, "stop", "--time", "5", info["Id"]], check=True, capture_output=True)
            raise RuntimeError("Resumed task entered the host network namespace; refused")
        return cls(prefix, info["Id"], cwd, image_id, namespace)

    def stop(self):
        # Stops this exact local container workload; its filesystem and platform allocation are retained.
        subprocess.run([*self.prefix, "stop", "--time", "15", self.container], check=True, capture_output=True)
