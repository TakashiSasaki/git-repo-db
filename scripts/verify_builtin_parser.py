"""Create packaged parser verification from an executed synthetic JUnit suite.

Run the full runtime/contract suite using test-only bootstrap first. This tool
requires successful cases in every capability's relevant end-to-end module;
failed/skipped cases never count as passed evidence. Final acceptance is then
rerun without bootstrap against the packaged manifest.

Development regeneration (ordinary suite; packaging runs separately afterward)::

    uv run --no-sync python scripts/verify_builtin_parser.py --capture artifacts/parser-definition.json
    REPO_CATALOG_TEST_BOOTSTRAP=1 uv run --no-sync pytest tests --ignore=tests/packaging -m "not live and not benchmark" --junitxml=artifacts/bootstrap.xml
    uv run --no-sync python scripts/verify_builtin_parser.py --snapshot artifacts/parser-definition.json --junit artifacts/bootstrap.xml

Final CI and installed wheel/sdist checks must run without the bootstrap variable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from repo_catalog.adapters.sqlite.parser_model import builtin_definition

REQUIRED_MODULES = {
    "change-request": ("test_catalog3_github_runtime", "test_catalog3_parsing_runtime"),
    "pr-title": ("test_catalog3_github_runtime", "test_catalog3_parsing_runtime"),
    "pr-body": ("test_catalog3_github_runtime", "test_catalog3_parsing_runtime"),
    "issue-comment": ("test_catalog3_github_runtime",),
    "review-thread": ("test_catalog3_github_runtime", "test_catalog3_review_coverage"),
    "events": ("test_catalog3_parsing_runtime",),
    "code": ("test_catalog3_github_runtime", "test_catalog3_parsing_runtime"),
    "git": ("test_catalog3_git_runtime",),
    "inventory": ("test_catalog3_parsing_runtime", "test_catalog3_job_plans"),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", action="append", type=Path)
    parser.add_argument("--capture", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("src/repo_catalog/resources/builtin_parser_verification.json"),
    )
    args = parser.parse_args()
    if args.capture:
        args.capture.write_text(json.dumps(builtin_definition(), sort_keys=True) + "\n")
        print(f"Captured parser and schema definition in {args.capture}")
        return
    if not args.junit or not args.snapshot:
        parser.error("generation requires --junit and the pre-run --snapshot")
    captured = json.loads(args.snapshot.read_text())
    if captured != builtin_definition():
        raise SystemExit(
            "Implementation/schema changed since the pre-run definition capture"
        )
    passed = []
    reports = []
    for path in args.junit:
        root = ET.fromstring(path.read_bytes())
        cases = list(root.iter("testcase"))
        failures = [
            c
            for c in cases
            if c.find("failure") is not None or c.find("error") is not None
        ]
        if failures:
            raise SystemExit(f"Verification report has failing cases: {path}")
        passed.extend(
            f"{c.attrib.get('classname', '')}::{c.attrib.get('name', '')}"
            for c in cases
            if c.find("skipped") is None
        )
        reports.append(
            {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "executed_passed": len(cases)
                - sum(c.find("skipped") is not None for c in cases),
                "skipped": sum(c.find("skipped") is not None for c in cases),
            }
        )
    definition = builtin_definition()
    evidence = []
    for capability in definition["capabilities"]:
        modules = REQUIRED_MODULES[capability["fact_kind"]]
        checks = []
        for module in modules:
            matches = [name for name in passed if module in name]
            if not matches:
                raise SystemExit(f"Missing executed tests for {capability}: {module}")
            checks.extend(matches)
        evidence.append(
            {**capability, "outcome": "passed", "checks": sorted(set(checks))}
        )
    manifest = {
        "definition": definition,
        "criteria": {
            "policy": "whole-profile-v1",
            "execution": "synthetic offline runtime and adversarial contracts",
            "reports": reports,
        },
        "capabilities": evidence,
    }
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(
        f"Wrote {args.output}: {len(evidence)} verified capabilities, {len(passed)} passed cases"
    )


if __name__ == "__main__":
    main()
