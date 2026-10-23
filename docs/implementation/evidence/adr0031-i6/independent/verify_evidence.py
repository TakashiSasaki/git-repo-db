"""Validate this frozen review's evidence; does not run or accept future I6."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
AUTHOR = "418ee68046fdfd03a0e84cc840e5d52fce176b81"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check():
    checks = {}
    # These inputs are unchanged even though evidence publication changes the tree.
    manifest = json.loads((HERE / "input-manifest.json").read_text())
    checks["all_frozen_inputs_unchanged"] = all(
        sha((ROOT / row["path"]).read_bytes()) == row["sha256"]
        for row in manifest["entries"]
    )
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", AUTHOR], cwd=ROOT, text=True
    ).splitlines()
    checks["tracked_diff_only_review_evidence"] = all(
        x.startswith("docs/implementation/evidence/adr0031-i6/independent/")
        for x in changed
    )
    invalid_links = []
    documents = list(HERE.glob("*.md")) + [
        ROOT / "docs/implementation" / name
        for name in (
            "adr0031-i6-wire-admission-exchange.md",
            "adr0031-i6-vectors-and-tests.md",
            "adr0031-i6-change-map-and-handoff.md",
            "context-resource-design-handoff.md",
        )
    ]
    for path in documents:
        content = path.read_text(encoding="utf-8", errors="strict")
        assert len(re.findall(r"^```", content, re.M)) % 2 == 0, path
        for link in re.findall(r"\]\(([^)]+)\)", content):
            if "://" not in link and not link.startswith("#"):
                target = unquote(link.split("#", 1)[0])
                if not (path.parent / target).exists():
                    invalid_links.append([path.name, link])
    checks["strict_utf8_balanced_fences_local_links"] = not invalid_links
    matrix = (HERE / "MATRIX.md").read_text()
    checks["all_19_requirements"] = set(
        re.findall(r"^\| (R\d\d) \|", matrix, re.M)
    ) == {f"R{x:02}" for x in range(1, 20)}
    findings = json.loads((HERE / "findings.json").read_text())
    checks["finding_scope_and_verdict"] = (
        findings["reviewed_head"] == AUTHOR
        and findings["verdict"] == "DESIGN_PASS_I6_A_MAY_START"
        and Counter(x["severity"] for x in findings["new_design_findings"])
        == {"Low": 1}
    )
    summary = json.loads((HERE / "raw/focused-summary.json").read_text())
    checks["246_nodes_738_phases_exact"] = (
        summary["consistent_success"]
        and summary["selected"] == 246
        and summary["phases"] == 738
    )
    probes = json.loads((HERE / "raw/review-probes.json").read_text())
    checks["five_independent_baseline_scenarios"] = len(probes["results"]) == 5 and all(
        x["outcome"] == "PASS" for x in probes["results"]
    )
    wire = json.loads((HERE / "raw/wire-probes.json").read_text())
    checks["15_existing_domain_checks"] = len(wire["checks"]) == 15 and all(
        x["status"] == "pass" for x in wire["checks"]
    )
    sql = json.loads((HERE / "raw/sql-probes.json").read_text())
    checks["sql_diagnostic_scope"] = (
        len(sql["fence_state_probe"]) == 5
        and sql["deferred_commit"]["rows_after_failure"] == [1, 1]
        and sql["deferred_commit"]["rows_after_rollback"] == [0, 0]
        and not sql["deferred_commit"]["transaction_after_rollback"]
    )
    for path in HERE.rglob("*.json"):
        if path != HERE / "raw/validation.json":
            json.loads(path.read_text(encoding="utf-8"))
    index = json.loads((HERE / "artifact-index.json").read_text())
    checks["indexed_artifacts_match"] = all(
        (HERE / row["path"]).stat().st_size == row["bytes"]
        and sha((HERE / row["path"]).read_bytes()) == row["sha256"]
        for row in index["entries"]
    )
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "invalid_links": invalid_links,
        "scope": "Evidence consistency and frozen input equality; not future I6 or full release acceptance",
    }


if __name__ == "__main__":
    result = check()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["passed"] else 1)
