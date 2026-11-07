"""Versioned interpretation of preserved verifier artifacts; never rewrites a run."""
from __future__ import annotations

import json
from pathlib import Path

from .contracts import canonical
from .swebench_pro import compilation_diagnostics, file_sha


def reclassify(root, output):
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    annotations = []
    for result_path in sorted(Path(root).rglob("result.json")):
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("evidence_tier") != "official-task-custom-backend" or result.get("status") != "completed":
            continue
        identity = json.loads((result_path.parent / "identity.json").read_text(encoding="utf-8"))
        for row in result["rows"]:
            grade = row["grade"]
            if row["valid"] is not False:
                continue
            reference = identity["evaluator_gates"][row["task_id"]]["reference"]
            if reference.get("valid") is not True or reference.get("success") is not True:
                continue
            if reference["task_files"] != grade["task_files"] or reference["workspace"]["image_id"] != grade["workspace"]["image_id"]:
                continue
            # Locate by independent raw output identity; do not trust a stale absolute host path.
            folders = []
            for path in result_path.parent.rglob("grade.json"):
                candidate = json.loads(path.read_text(encoding='utf-8'))
                if candidate.get("task_id") == row["task_id"] and candidate.get("patch_sha256") == grade["patch_sha256"]:
                    folders.append(path.parent)
            for folder in folders:
                reward = folder / "reward.txt"
                raw = folder / "output.json"
                if not reward.exists() or not raw.exists() or reward.read_text(encoding='utf-8').strip() != "0":
                    continue
                log_paths = [folder / name for name in ["run-script-stdout.txt", "run-script-stderr.txt"] if (folder / name).exists()]
                diagnostics = compilation_diagnostics("\n".join(p.read_text(encoding='utf-8', errors="replace") for p in log_paths))
                if not diagnostics:
                    continue
                annotations.append({"result_sha256": file_sha(result_path), "task_id": row["task_id"], "seed": row["seed"],
                    "valid": True, "success": False, "failure_category": "code_compilation_failure",
                    "reason": "Official reward is0 and compiler diagnostics identify a coding failure; retain this attempt in the denominator.",
                    "diagnostics": diagnostics, "grade_source_sha256": file_sha(raw),
                    "evidence": {p.name: file_sha(p) for p in [reward, raw, *log_paths, folder / "grade.json"]},
                    "reference_grade_source_sha256": reference["grade_source_sha256"],
                    "rule_source_sha256": file_sha(Path(__file__).with_name("swebench_pro.py"))})
                break
    record = {"schema_version": 1, "original_runs_modified": False, "annotations": annotations}
    (output / "reclassifications.json").write_text(canonical(record), encoding="utf-8")
    return record
