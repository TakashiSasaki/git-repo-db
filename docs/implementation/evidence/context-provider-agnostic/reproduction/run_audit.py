#!/usr/bin/env python3
"""Run fixed-source audit probes and preserve non-overwriting execution receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BASE = "efb55af84ccbf1183d47547d22bb6c57d8fbc8f9"
ROOT = Path(__file__).resolve().parents[5]
PROBES = Path(__file__).resolve().parent
EXISTING = (
    "tests/integration/i3/test_selective_exchange.py",
    "tests/integration/i23/test_provider_exchange.py",
    "tests/integration/i4/test_query_search_backup.py",
)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--existing", action="store_true")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if list(out.iterdir()):
        parser.error("output must be empty; preserve earlier attempts")
    if sqlite3.sqlite_version_info < (3, 51, 3):
        parser.error("actual SQLite >=3.51.3 required")
    # This audit verifies the named product revision, not a silently changed tree.
    unchanged = subprocess.run(
        [
            "git",
            "diff",
            "--exit-code",
            BASE,
            "--",
            "src",
            "tests",
            "pyproject.toml",
            "uv.lock",
        ],
        cwd=ROOT,
        capture_output=True,
    )
    if unchanged.returncode:
        parser.error("product/test/dependency inputs differ from the frozen audit base")
    tracked = git(
        "ls-files", "src", "tests", "scripts", "pyproject.toml", "uv.lock"
    ).splitlines()
    input_paths = [ROOT / p for p in tracked] + sorted(PROBES.glob("*.py"))
    input_hashes = {str(p.relative_to(ROOT)): digest(p) for p in input_paths}
    (out / "input-hashes.json").write_text(json.dumps(input_hashes, indent=2) + "\n")
    targets = (
        list(EXISTING)
        if args.existing
        else [str(p.relative_to(ROOT)) for p in sorted(PROBES.glob("test_*.py"))]
    )
    if not targets:
        parser.error("no audit probes found")
    import repo_catalog
    from repo_catalog.adapters.sqlite import p1_schema

    p1_schema.verify_declared()
    environment = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": BASE,
        "source_tree": git("rev-parse", BASE + "^{tree}"),
        "audit_head": git("rev-parse", "HEAD"),
        "audit_head_tree": git("rev-parse", "HEAD^{tree}"),
        "python": sys.version,
        "executable": sys.executable,
        "sqlite_version": sqlite3.sqlite_version,
        "sqlite_source_id": sqlite3.connect(":memory:")
        .execute("select sqlite_source_id()")
        .fetchone()[0],
        "module_path": repo_catalog.__file__,
        "schema_fingerprint_check": "pass",
        "targets": targets,
        "input_hashes_sha256": digest(out / "input-hashes.json"),
        "scope": "focused development audit, not full release or live-provider acceptance",
    }
    (out / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
    env = dict(os.environ)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    common = [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        str(ROOT / "pyproject.toml"),
        *targets,
        "-q",
    ]
    with (out / "collection.log").open("w") as log:
        collect = subprocess.run(
            common + ["--collect-only"],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    collected = [
        line.strip()
        for line in (out / "collection.log").read_text().splitlines()
        if "::" in line and not line.startswith(" ")
    ]
    run = common + ["-o", "junit_family=xunit1", "--junitxml", str(out / "junit.xml")]
    with (out / "pytest.log").open("w") as log:
        proc = (
            subprocess.run(run, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            if collect.returncode == 0
            else None
        )
    cases = []
    if (out / "junit.xml").exists():
        for case in ET.parse(out / "junit.xml").iter("testcase"):
            cases.append(
                {
                    "node": case.attrib["classname"].replace(".", "/")
                    + ".py::"
                    + case.attrib["name"],
                    "status": next(
                        (
                            s
                            for s in ("failure", "error", "skipped")
                            if case.find(s) is not None
                        ),
                        "passed",
                    ),
                }
            )
    after = {str(p.relative_to(ROOT)): digest(p) for p in input_paths}
    receipt = {
        "command": run,
        "collection_exit_code": collect.returncode,
        "execution_exit_code": None if proc is None else proc.returncode,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "collected_nodes": collected,
        "cases": cases,
        "collected_equals_executed": Counter(collected)
        == Counter(c["node"] for c in cases),
        "unique_collected": len(collected) == len(set(collected)),
        "input_hashes_unchanged": input_hashes == after,
        "counts": dict(Counter(c["status"] for c in cases)),
    }
    receipt["pass"] = (
        bool(collected)
        and collect.returncode == 0
        and proc is not None
        and proc.returncode == 0
        and receipt["collected_equals_executed"]
        and receipt["unique_collected"]
        and receipt["input_hashes_unchanged"]
        and all(c["status"] == "passed" for c in cases)
    )
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: receipt[k]
                for k in (
                    "pass",
                    "counts",
                    "collected_equals_executed",
                    "input_hashes_unchanged",
                )
            }
        )
    )
    return 0 if receipt["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
