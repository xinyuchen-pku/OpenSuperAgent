"""Official Pro V2 files, patch capture and fresh-image grading with explicit environment provenance.

This adapter does not claim Harbor/Modal deployment equivalence. Resource and
network gates from the selected backend remain part of the result identity.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import time
import tomllib
from pathlib import Path

from .contracts import canonical
from .image_probe import probe_history


def file_sha(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def compiler_crashes(logs):
    """A crashed toolchain invalidates even a partially collected test run."""
    return re.findall(r"^.*(?:[/\\](?:compile|link): signal: segmentation fault|"
                      r"(?:gcc|g\+\+|cc): internal compiler error:|"
                      r"collect2: fatal error: ld terminated with signal 11|"
                      r"clang: error: unable to execute command: Segmentation fault).*$", logs, re.MULTILINE | re.IGNORECASE)


def compilation_diagnostics(logs):
    """Recognize compiler diagnostics rather than treating parser sentinel rows as tests."""
    infrastructure_terms = ["permission denied", "no space left on device", "no such host", "connection refused", "tls handshake timeout",
                            "/compile: signal: segmentation fault", "/link: signal: segmentation fault"]
    if compiler_crashes(logs) or any(term in logs.lower() for term in infrastructure_terms):
        return []
    matches = re.findall(r"(?m)^\S+\.go:\d+(?::\d+)?: .+$", logs)
    if matches:
        return list(dict.fromkeys(matches))
    return [line for line in logs.splitlines() if re.search(r"\b(?:SyntaxError|IndentationError|TabError):|error TS\d+:", line)]


class ProTask:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.id = self.path.name
        self.config = tomllib.loads((self.path / "task.toml").read_text(encoding="utf-8"))
        self.image = self.config["environment"]["docker_image"]
        self.instruction = (self.path / "instruction.md").read_text(encoding="utf-8")
        self.files = {p.relative_to(self.path).as_posix(): file_sha(p) for p in sorted(self.path.rglob("*")) if p.is_file()}

    def copy(self, workspace, source, destination):
        # Podman copies bytes through its container API; no host directory is mounted into the task.
        subprocess.run([*workspace.prefix, "cp", str(source), workspace.container + ":" + destination],
                       check=True, capture_output=True, timeout=120)

    async def prepare_agent(self, workspace):
        probe = await workspace.execute("if [ -d /app/.git ]; then printf /app; elif [ -d /testbed/.git ]; then printf /testbed; else exit 2; fi", 30)
        if probe["returncode"]:
            raise RuntimeError("Official image has no expected repository")
        workspace.cwd = probe["stdout"].strip()
        workspace.identity["cwd"] = workspace.cwd
        status = await workspace.execute("git status --porcelain; printf '\\nHISTORY\\n'; git log --oneline -5; git show-ref; git stash list", 30)
        no_hidden = await workspace.execute("test ! -e /tests && test ! -e /solution && test ! -e /logs/verifier", 10)
        if no_hidden["returncode"]:
            raise RuntimeError("Evaluator or reference artifacts exposed to agent")
        toolchain = await workspace.execute("if test -f go.mod; then command -v go && go version; else git --version; fi", 30)
        if toolchain["returncode"]:
            raise RuntimeError("Image toolchain is unavailable in the actual tool execution environment")
        detailed = await probe_history(self, workspace)
        return {"repository_probe": probe, "history_probe": status, "history_leak_gate": detailed, "hidden_paths_absent": True, "toolchain_probe": toolchain}

    async def capture_patch(self, workspace, output):
        # Same staging contract as official locked agents; capture stdout without presentation truncation.
        result = await workspace.execute("git add -A && git diff --cached --binary", 120)
        if result["returncode"]:
            raise RuntimeError("Patch capture failed")
        Path(output).write_text(result["stdout"], encoding="utf-8", newline="")
        return {"sha256": file_sha(output), "bytes": Path(output).stat().st_size}

    async def grade(self, factory, patch, output):
        output = Path(output); output.mkdir(parents=True, exist_ok=False)
        workspace = factory()  # Must create a fresh image instance, never the agent's workspace.
        started = time.time()
        record = {"task_id": self.id, "task_files": self.files, "patch_sha256": file_sha(patch),
                  "workspace": workspace.identity, "started": started, "official_verifier_modified": False}
        try:
            # Some official images have mode0555 on /. Harbor supplies log mounts;
            # a capability-restricted OCI backend must provision them via its copy API.
            staging = output / "verifier-staging" / "logs"
            (staging / "verifier").mkdir(parents=True)
            staging.chmod(0o777); (staging / "verifier").chmod(0o777)
            self.copy(workspace, staging, "/")
            self.copy(workspace, str(self.path / "tests") + "/.", "/tests")
            prepared = await workspace.execute("test -r /tests/test.sh && test -w /logs/verifier", 30)
            if prepared["returncode"]:
                raise RuntimeError("Verifier files/log directory preparation failed")
            self.copy(workspace, Path(patch), "/tmp/osa-replay.patch")
            locate = await workspace.execute("if [ -d /app/.git ]; then printf /app; elif [ -d /testbed/.git ]; then printf /testbed; else exit 2; fi", 30)
            if locate["returncode"]:
                raise RuntimeError("Pristine verifier repository missing")
            workspace.cwd = locate["stdout"].strip()
            if Path(patch).stat().st_size:
                record["apply"] = await workspace.execute("git apply --verbose /tmp/osa-replay.patch || git apply --3way /tmp/osa-replay.patch || patch --fuzz=3 -p1 -i /tmp/osa-replay.patch", 300)
            else:
                record["apply"] = {"returncode": 0, "stdout": "Empty patch", "stderr": ""}
            # Preserve official verifier outcome even if patch replay failed; failure is additionally labelled.
            record["execution"] = await workspace.execute("bash /tests/test.sh", float(self.config["verifier"]["timeout_sec"]))
            subprocess.run([*workspace.prefix, "cp", workspace.container + ":/logs/verifier/.", str(output)],
                           check=True, capture_output=True, timeout=120)
            raw = json.loads((output / "output.json").read_text(encoding='utf-8'))
            config = json.loads((self.path / "tests/config.json").read_text(encoding='utf-8'))
            def required(value):
                return ast.literal_eval(value) if isinstance(value, str) else value
            targets = set(required(config.get("fail_to_pass", []))) | set(required(config.get("pass_to_pass", [])))
            reported = raw.get("tests", [])
            collected = {t["name"] for t in reported if not t["name"].startswith("NO_TESTS_")}
            reward = (output / "reward.txt").read_text(encoding='utf-8').strip()
            if not targets or reward not in {"0", "1"}:
                raise RuntimeError("Official verifier produced incomplete instrumentation")
            logs = "\n".join((output / n).read_text(encoding='utf-8', errors="replace") for n in ["run-script-stdout.txt", "run-script-stderr.txt"] if (output / n).exists())
            crashes = compiler_crashes(logs)
            if crashes:
                record["infrastructure_failure"] = {"kind": "compiler_process_crash", "diagnostics": crashes,
                                                    "collected_tests_before_failure": len(collected)}
                raise RuntimeError("Compiler process crashed; partial test collection does not establish a valid grade")
            collection_failure = None
            diagnostics = compilation_diagnostics(logs)
            if not reported and not diagnostics:
                raise RuntimeError("Official verifier produced incomplete instrumentation")
            if not collected:
                if diagnostics:
                    collection_failure = "code_compilation_failure; required tests did not execute"
                else:
                    raise RuntimeError("No real tests collected; environment/compiler cause requires inspection of preserved raw logs")
            # Missing targets are a real coding/test outcome, retained for failure analysis.
            record.update(success=reward == "1" and record["apply"]["returncode"] == 0, collected_tests=len(collected), required_tests=len(targets),
                          missing_required_tests=sorted(targets-collected), valid=True,
                          collection_failure=collection_failure,
                          compilation_diagnostics=diagnostics,
                          grade_source_sha256=file_sha(output / "output.json"),
                          protocol_equivalence="official task and verifier; custom OCI backend, consult workspace resource limits")
        except Exception as error:
            record.update(valid=False, success=None, error=type(error).__name__ + ": " + str(error))
            if isinstance(error, subprocess.CalledProcessError):
                record["controller_error_stdout"] = (error.stdout or b"").decode(errors="replace")[-2000:] if isinstance(error.stdout, bytes) else error.stdout
                record["controller_error_stderr"] = (error.stderr or b"").decode(errors="replace")[-2000:] if isinstance(error.stderr, bytes) else error.stderr
        finally:
            record["elapsed_s"] = time.time() - started
            workspace.stop()
            (output / "grade.json").write_text(canonical(record), encoding="utf-8")
        return record
