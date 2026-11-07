"""Backends receive benchmark-owned workspace handles; no host shell fallback."""
from __future__ import annotations

import asyncio
import shlex
import subprocess
import json


class DockerWorkspace:
    cleanup_grace_s = 6.0

    def __init__(self, container: str, cwd: str, *, image_digest: str, command_prefix=None):
        if not container or not image_digest.startswith("sha256:"):
            raise ValueError("An existing container and its immutable image digest are required")
        self.container, self.cwd = container, cwd
        self.prefix = list(command_prefix if command_prefix is not None else ["docker"])
        if not self.prefix or any(not isinstance(part, str) or not part for part in self.prefix):
            raise ValueError("Docker command prefix must contain nonempty arguments")
        self.identity = {"backend": "docker-exec", "container": container, "cwd": cwd, "image_digest": image_digest}
        self.identity["command_prefix"] = self.prefix

    @classmethod
    def create(cls, *, image, name, purpose, cpus, memory_mb, cwd="/app", command_prefix=None):
        if purpose not in {"agent", "verifier"} or cpus <= 0 or memory_mb <= 0:
            raise ValueError("Explicit purpose and positive CPU/RAM limits are required")
        prefix = list(command_prefix if command_prefix is not None else ["docker"])
        if not prefix or any(not isinstance(part, str) or not part for part in prefix):
            raise ValueError("Docker command prefix must contain nonempty arguments")
        result = subprocess.run([*prefix, "run", "--detach", "--name", name, "--pull", "never",
            "--network", "none" if purpose == "agent" else "bridge", "--cpus", str(cpus), "--memory", str(int(memory_mb * 1024 * 1024)),
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", image, "sh", "-c", "exec sleep infinity"],
            capture_output=True, text=True, timeout=300)
        if result.returncode:
            raise RuntimeError("Docker workspace creation failed: " + result.stderr[-2000:])
        info = json.loads(subprocess.check_output([*prefix, "inspect", result.stdout.strip()], text=True))[0]
        workspace = cls(info["Id"], cwd, image_digest=info["Image"], command_prefix=prefix)
        probe_code = "from pathlib import Path;import json;p=Path('/sys/fs/cgroup');names=['memory.max','cpu.max','memory/memory.limit_in_bytes','cpu/cpu.cfs_quota_us','cpu/cpu.cfs_period_us'];print(json.dumps({n:(p/n).read_text(encoding='utf-8').strip()for n in names if(p/n).exists()}))"
        try:
            probe = json.loads(subprocess.check_output([*prefix, "exec", info["Id"], "python3", "-c", probe_code], text=True))
            memory = probe.get("memory.max", probe.get("memory/memory.limit_in_bytes", "max"))
            quota = probe.get("cpu.max", (probe.get("cpu/cpu.cfs_quota_us", "max") + " " + probe.get("cpu/cpu.cfs_period_us", "100000"))).split()
            enforced = (memory != "max" and int(memory) == int(memory_mb * 1024 * 1024)
                        and quota[0] != "max" and abs(int(quota[0]) / int(quota[1]) - cpus) < 1e-9)
            if not enforced:
                raise RuntimeError("CPU/RAM limits were not confirmed in the container's actual cgroup")
        except BaseException:
            workspace.stop()
            raise
        workspace.identity.update(image_id=info["Image"], purpose=purpose, cgroup_limits_enforced=True,
                                  cpus=cpus, memory_mb=memory_mb, resource_probe=probe, network=info["HostConfig"]["NetworkMode"])
        return workspace

    def stop(self):
        subprocess.run([*self.prefix, "stop", "--time", "15", self.container], check=True, capture_output=True)

    async def resource_usage(self):
        result = await self.execute("python3 -c " + shlex.quote(
            "from pathlib import Path;import json;p=Path('/sys/fs/cgroup');"
            "print(json.dumps({n:(p/n).read_text().strip() for n in "
            "['cpu.stat','memory.current','memory.peak','memory.events'] if (p/n).exists()}))"), 15)
        if result["returncode"]:
            raise RuntimeError("Container resource accounting failed")
        return json.loads(result["stdout"])

    async def execute(self, command, timeout_s):
        # The timeout lives INSIDE the container; terminating the client alone leaves shell work running.
        process = await asyncio.create_subprocess_exec(*self.prefix, "exec", "-w", self.cwd, self.container,
            "timeout", "--signal=TERM", "--kill-after=5", str(timeout_s), "bash", "-c", command,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout_s + 15)
        except BaseException:
            if process.returncode is None:
                process.kill()  # Only this verified client process; container allocation is retained.
                await process.wait()
            raise
        return {"stdout": stdout.decode("utf-8", errors="replace"), "stderr": stderr.decode("utf-8", errors="replace"), "returncode": process.returncode}


class AsynWorkspace:
    def __init__(self, workspace, path, identity):
        self.workspace, self.path, self.identity = workspace, path, identity

    async def execute(self, command, timeout_s):
        result = await asyncio.to_thread(self.workspace.execute_command,
            "cd " + shlex.quote(self.path) + " && " + command, timeout=timeout_s)
        return {"stdout": result.stdout or "", "stderr": result.stderr or "", "returncode": result.exit_code}
