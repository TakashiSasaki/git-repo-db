"""Execute independent documentation obligations and retain private receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "documentation"))
from tools.build_docs_site import verify_documentation_checkout  # noqa: E402
from tools.provenance import input_record  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-source", required=True)
    parser.add_argument("--documentation-source", required=True)
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Placeholder diagrams; never complete release evidence",
    )
    args = parser.parse_args()
    verify_documentation_checkout(args.documentation_source)
    inputs = ROOT / "documentation/.build/inputs"
    record = input_record(
        ROOT,
        args.documentation_source,
        args.product_source,
        inputs / "producer.json",
        inputs / "inventory.json",
    )
    base = ROOT / "documentation/.build/verification"
    output = base
    if any(p.is_symlink() for p in (output, *output.parents)):
        raise ValueError("Linked evidence directory refused")
    output.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="attempt-", dir=base))
    receipt = output / "documentation-receipt.json"
    # Invalidate a previous success before any new command; do not leave stale evidence.
    receipt.unlink(missing_ok=True)
    commands = [
        [
            sys.executable,
            "documentation/tools/build_docs_site.py",
            "--product-source",
            args.product_source,
            "--documentation-source",
            args.documentation_source,
            *(["--no-mermaid"] if args.preview else []),
        ],
        [sys.executable, "-m", "pytest", "-q", "documentation/tests", "--collect-only"],
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "documentation/tests",
            "--junitxml=" + str(output / "tests.xml"),
        ],
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "documentation/tools",
            "documentation/tests",
        ],
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--check",
            "documentation/tools",
            "documentation/tests",
        ],
    ]
    for i, command in enumerate(commands):
        with (output / f"command-{i}.log").open("w") as stream:
            result = subprocess.run(
                command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT
            )
        if result.returncode:
            print(
                f"Documentation command{i} failed; see private evidence log",
                file=sys.stderr,
            )
            return result.returncode
    nodes = [
        x.strip()
        for x in (output / "command-1.log").read_text().splitlines()
        if x.startswith("documentation/tests/") and "::" in x
    ]
    cases = ET.parse(output / "tests.xml").findall(".//testcase")
    executed = [
        c.attrib["classname"].replace(".", "/") + ".py::" + c.attrib["name"]
        for c in cases
    ]
    if (
        not nodes
        or len(nodes) != len(set(nodes))
        or Counter(nodes) != Counter(executed)
        or any(
            c.find(x) is not None
            for c in cases
            for x in ("failure", "error", "skipped")
        )
    ):
        raise ValueError("Documentation collection/execution reconciliation failed")
    for name in ("inventory.json", "producer.json"):
        shutil.copyfile(inputs / name, output / name)
    paths = [
        "tests.xml",
        "inventory.json",
        "producer.json",
        *[f"command-{i}.log" for i in range(len(commands))],
    ]

    def digest(p):
        return hashlib.sha256(p.read_bytes()).hexdigest()

    hosted = os.environ.get("GITHUB_ACTIONS") == "true"
    result = {
        "schema_version": 1,
        "scope": "documentation",
        "status": "passed",
        "build_mode": "preview" if args.preview else "complete",
        "execution_context": "hosted" if hosted else "local",
        "run_id": os.environ.get("GITHUB_RUN_ID") if hosted else None,
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT") if hosted else None,
        "repository": os.environ.get("GITHUB_REPOSITORY") if hosted else None,
        "feature_sha": os.environ.get("CI_FEATURE_SHA", os.environ.get("GITHUB_SHA"))
        if hosted
        else None,
        "inputs": record,
        "test_ids": sorted(nodes),
        "commands": commands,
        "command_exit_codes": [0] * len(commands),
        "artifact_sha256": {p: digest(output / p) for p in paths},
        "documentation_lock_sha256": digest(ROOT / "documentation/uv.lock"),
        "full_acceptance": False,
    }
    receipt.write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"Documentation {result['build_mode']}: {len(nodes)} nodes, exact collection/JUnit; not complete product+docs release acceptance"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
