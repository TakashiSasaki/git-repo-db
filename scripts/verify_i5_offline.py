"""Audit all pytest nodes and execute disjoint offline cohorts with bounded output.

This is an I5 evidence helper, not a release receipt or an approval. Install the
locked dev AND docs groups before use. The docs group supplies PyYAML needed by
ordinary documentation tests. Before --execute, run scripts/prepare_wheelhouse.py
(online dependency preparation only); execution stays network-guarded. Use the
environment Python and its SQLite library; record the actual runtime without
installing or replacing SQLite or requiring a particular release.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import platform
import shlex
import sqlite3
import subprocess
import sys
import time
import tomllib
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def runtime_metadata(db):
    """Measure the current invocation before any product capability refusal."""
    version, source = db.execute(
        "SELECT sqlite_version(),sqlite_source_id()"
    ).fetchone()
    return {
        "python": platform.python_version(),
        "executable": sys.executable,
        "sqlite_version": version,
        "sqlite_source_id": source,
        "compile_options": db.execute("PRAGMA compile_options").fetchall(),
        "pragmas": {
            name: db.execute(f"PRAGMA {name}").fetchall()
            for name in (
                "foreign_keys",
                "recursive_triggers",
                "journal_mode",
                "synchronous",
            )
        },
    }


def verified_wheelhouse(directory=None):
    """Reject altered/unlocked wheels before network-free distribution installs."""
    directory = Path(
        directory
        or os.environ.get("REPO_CATALOG_WHEELHOUSE", ROOT / "artifacts/wheelhouse")
    ).resolve()
    lock = (ROOT / "uv.lock").read_bytes()
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest["lock_sha256"] != hashlib.sha256(lock).hexdigest():
        raise ValueError("wheelhouse is not bound to current uv.lock")
    locked = {
        (Path(wheel["url"]).name, wheel["hash"].removeprefix("sha256:"))
        for package in tomllib.loads(lock.decode())["package"]
        for wheel in package.get("wheels", [])
    }
    files = set()
    for wheel in manifest["wheels"]:
        name, digest = wheel["file"], wheel["sha256"]
        if Path(name).name != name or (name, digest) not in locked or name in files:
            raise ValueError("unlocked or duplicate wheelhouse member: " + name)
        files.add(name)
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise ValueError("wheelhouse SHA-256 mismatch: " + name)
    if {path.name for path in directory.glob("*.whl")} != files:
        raise ValueError("unindexed wheelhouse files")
    return directory, manifest


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def nodes(path):
    return [
        line.strip()
        for line in path.read_text().splitlines()
        if line.startswith("tests/") and "::" in line
    ]


def ci_targets():
    """Read the actual focused collection command; fail if its shape changes."""
    workflow = (ROOT / ".github/workflows/access-registry.yml").read_text()
    joined = workflow.replace("\\\n", " ")
    lines = [
        line.strip()
        for line in joined.splitlines()
        if "uv run --no-sync pytest " in line and "--collect-only" in line
    ]
    if len(lines) != 1:
        raise ValueError("expected one focused CI collection command")
    words = shlex.split(lines[0])
    targets = words[words.index("pytest") + 1 : words.index("--collect-only")]
    result = []
    for word in targets:
        if word == "-q":
            continue
        if not word.startswith("tests/"):
            raise ValueError(f"unexpected CI collection argument: {word}")
        matches = sorted(glob.glob(str(ROOT / word)))
        if not matches:
            raise ValueError(f"missing CI target: {word}")
        result.extend(str(Path(value).relative_to(ROOT)) for value in matches)
    return result


def execute(out, name, arguments):
    command = [sys.executable, "-m", "pytest", *arguments]
    started = time.time()
    with (out / f"{name}.log").open("w") as output:
        process = subprocess.run(
            command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=False
        )
    result = {
        "command": command,
        "cwd": str(ROOT),
        "started_epoch": started,
        "elapsed_seconds": round(time.time() - started, 3),
        "exit_code": process.returncode,
    }
    write_json(out / f"{name}.execution.json", result)
    return result


def collect(out, name, targets, marker=None):
    arguments = ["-q", "--collect-only", "-o", "addopts=", *targets]
    if marker:
        arguments += ["-m", marker]
    result = execute(out, name, arguments)
    selected = nodes(out / f"{name}.log")
    result.update(
        collected=len(selected), duplicates=len(selected) - len(set(selected))
    )
    (out / f"{name}.nodes.txt").write_text("".join(n + "\n" for n in selected))
    write_json(out / f"{name}.execution.json", result)
    return selected, result


def input_hashes():
    paths = [
        path
        for directory in ("src", "tests", "scripts", ".github/workflows")
        for path in (ROOT / directory).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    ]
    paths += [ROOT / "pyproject.toml", ROOT / "uv.lock"]
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
    }


def reconciliation(selected, xml_path, journal_path):
    expected = Counter(selected)
    actual_xml = Counter()
    results = Counter()
    for case in ET.parse(xml_path).findall(".//testcase"):
        actual_xml[(case.get("classname"), case.get("name"))] += 1
    expected_xml = Counter()
    for node in selected:
        prefix, bracket, parameter = node.partition("[")
        parts = prefix.split("::")
        expected_xml[
            (
                ".".join([parts[0][:-3].replace("/", "."), *parts[1:-1]]),
                parts[-1] + bracket + parameter,
            )
        ] += 1
    starts = Counter()
    phases = Counter()
    finishes = []
    setup_outcomes = {}
    for line in journal_path.read_text().splitlines():
        event = json.loads(line)
        if event["event"] == "start":
            starts[event["nodeid"]] += 1
        elif event["event"] == "phase":
            phases[(event["nodeid"], event["phase"])] += 1
            results[event["outcome"]] += 1
            if event["phase"] == "setup":
                setup_outcomes[event["nodeid"]] = event["outcome"]
        elif event["event"] == "finish":
            finishes.append(event)
    checks = {
        "selected_unique": all(count == 1 for count in expected.values()),
        "selected_equals_junit": expected_xml == actual_xml,
        "selected_equals_journal_starts": expected == starts,
        "setup_and_teardown_once": all(
            phases[(node, phase)] == 1
            for node in expected
            for phase in ("setup", "teardown")
        ),
        "no_duplicate_phases": all(count == 1 for count in phases.values()),
        "phase_nodes_equal_selected": {node for node, _ in phases} == set(expected),
        "call_once_after_successful_setup": all(
            phases[(node, "call")] == int(setup_outcomes.get(node) == "passed")
            for node in expected
        ),
        "one_finish": len(finishes) == 1,
    }
    return {
        "checks": checks,
        "consistent_node_execution": all(checks.values()),
        "journal_phase_outcomes": dict(results),
        "finishes": finishes,
    }


def outcomes(xml_path):
    result = Counter(passed=0, failed=0, error=0, skipped=0, xfail=0, xpass=0)
    for case in ET.parse(xml_path).findall(".//testcase"):
        if case.find("failure") is not None:
            result["failed"] += 1
        elif case.find("error") is not None:
            result["error"] += 1
        elif (skipped := case.find("skipped")) is not None:
            key = "xfail" if skipped.get("type") == "pytest.xfail" else "skipped"
            result[key] += 1
        else:
            result["passed"] += 1
    result["executed"] = sum(result.values())
    return dict(result)


def cohort_succeeded(result):
    """A successful process alone cannot hide skipped or unreconciled tests."""
    return (
        result["exit_code"] == 0
        and result.get("reconciliation", {}).get("consistent_node_execution", False)
        and all(
            result.get(name, 0) == 0
            for name in ("failed", "error", "skipped", "xfail", "xpass")
        )
    )


def run_cohort(out, name, selected, workers):
    selection = out / f"{name}.selected.txt"
    selection.write_text("".join(n + "\n" for n in selected))
    arguments = [
        "-q",
        "-o",
        "addopts=--strict-markers",
        "-o",
        "junit_family=xunit1",
        f"@{selection}",
        f"--junitxml={out / (name + '.xml')}",
        f"--journal={out / (name + '.jsonl')}",
    ]
    if workers:
        arguments += ["-n", str(workers), "--dist", "worksteal"]
    result = execute(out, name, arguments)
    result["collected"] = len(selected)
    xml = out / f"{name}.xml"
    if xml.exists():
        result.update(outcomes(xml))
        result["reconciliation"] = reconciliation(selected, xml, out / f"{name}.jsonl")
    else:
        result["execution_evidence_missing"] = True
    write_json(out / f"{name}.execution.json", result)
    print(json.dumps({name: result}), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    os.environ["PATH"] = (
        str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
    )
    if args.workers < 0:
        parser.error("workers must be nonnegative")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        parser.error("output must be empty (preserve earlier evidence)")
    with sqlite3.connect(":memory:") as db:
        runtime = runtime_metadata(db)
    write_json(out / "runtime-before-checks.json", runtime)
    import repo_catalog

    binding = {
        "head": git("rev-parse", "HEAD"),
        "tree": git("rev-parse", "HEAD^{tree}"),
        "dirty": git("status", "--porcelain"),
        **runtime,
        "package_paths": list(repo_catalog.__path__),
        "files": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ("pyproject.toml", "uv.lock", __file__)
        },
        "note": "Concurrent timings are not sequential benchmark measurements.",
    }
    write_json(out / "binding.json", binding)
    before = input_hashes()
    write_json(out / "inputs-before.json", before)
    inventory = {}
    all_nodes, inventory["all"] = collect(out, "all", ["tests"])
    ordinary, inventory["ordinary"] = collect(
        out, "ordinary", ["tests"], "not live and not benchmark"
    )
    offline, inventory["offline"] = collect(out, "offline", ["tests"], "not live")
    ci, inventory["ci"] = collect(out, "ci", ci_targets(), "not live and not benchmark")
    if any(value["exit_code"] or value["duplicates"] for value in inventory.values()):
        write_json(out / "summary.json", {"collection": inventory})
        return 2
    if not set(ci) <= set(ordinary) <= set(offline) <= set(all_nodes):
        raise ValueError("test cohort inclusion differs")
    omitted = sorted(set(ordinary) - set(ci))
    benchmarks = sorted(set(offline) - set(ordinary))
    live = sorted(set(all_nodes) - set(offline))
    write_json(
        out / "selection.json",
        {
            "all": len(all_nodes),
            "ordinary": len(ordinary),
            "ci": len(ci),
            "additional_ordinary": omitted,
            "benchmarks": benchmarks,
            "live_not_run": live,
            "live_reason": "Requires real GitHub network and explicitly selected real repository; prohibited by I5 scope.",
        },
    )
    runs = {}
    if args.execute:
        verified_wheelhouse()
        for name, selected, workers in (
            ("ci-run", ci, args.workers),
            ("additional-run", omitted, args.workers),
            ("benchmark-run", benchmarks, 0),
        ):
            if selected:
                runs[name] = run_cohort(out, name, selected, workers)
    after = input_hashes()
    write_json(out / "inputs-after.json", after)
    changed = sorted(
        key for key in before.keys() | after.keys() if before.get(key) != after.get(key)
    )
    summary = {
        "collection": inventory,
        "runs": runs,
        "changed_inputs": changed,
        "inputs_unchanged": not changed,
    }
    write_json(out / "summary.json", summary)
    print(json.dumps(summary), flush=True)
    return int(
        bool(changed) or any(not cohort_succeeded(value) for value in runs.values())
    )


if __name__ == "__main__":
    raise SystemExit(main())
