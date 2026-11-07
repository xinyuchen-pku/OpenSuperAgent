"""Portable environment/evaluator validation before a billed benchmark campaign."""
from __future__ import annotations

import json
from pathlib import Path

from .contracts import canonical, digest


async def validate_tasks(tasks, factory, output, *, provenance):
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    gates = {}
    (output / "identity.json").write_text(canonical(provenance), encoding="utf-8")
    for task_id, task in tasks.items():
        folder = output / task_id; folder.mkdir()
        empty_patch = folder / "empty.patch"; empty_patch.write_bytes(b"")
        workspace = factory(task, "agent", digest([str(output), task_id, "probe"])[:20])
        gate = {"task_files": task.files, "image_id": workspace.identity["image_id"], "workspace_contract": workspace.identity}
        try:
            gate["agent_probes"] = await task.prepare_agent(workspace)
            network = await workspace.execute("python3 -c \"import socket,json; s=socket.socket(); s.settimeout(2); print(json.dumps({'external_connect_errno':s.connect_ex(('1.1.1.1',443))}))\"", 10)
            gate["network_probe"] = network
            if network["returncode"] or json.loads(network["stdout"])["external_connect_errno"] not in {100, 101, 113}:
                raise RuntimeError("Agent network gate did not confirm outbound denial")
        finally:
            workspace.stop()
        for label, patch in [("empty", empty_patch), ("reference", task.path / "solution/gold_patch.diff")]:
            def new_workspace(label=label):
                return factory(task, "verifier", digest([str(output), task_id, label])[:20])
            gate[label] = await task.grade(new_workspace, patch, folder / label)
        gate["passed"] = (gate["empty"].get("valid") is True and gate["empty"].get("success") is False
                          and gate["reference"].get("valid") is True and gate["reference"].get("success") is True)
        gates[task_id] = gate
        (output / "evaluator-gates.json").write_text(canonical(gates), encoding="utf-8")
        if not gate["passed"]:
            raise RuntimeError("Evaluator gate failed for " + task_id + "; preserved all artifacts")
    return gates
