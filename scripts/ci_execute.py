"""Execute current selections and report exactly what ran, failed or remained untested."""

import argparse
import glob
import json
import math
import os
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ci_plan, ci_profile  # noqa: E402

MARKER = "not live and not benchmark"


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def collection_ids(text):
    nodes = [
        line.strip()
        for line in text.splitlines()
        if line.startswith("tests/") and "::" in line
    ]
    if not nodes or len(nodes) != len(set(nodes)):
        raise ValueError("Missing/duplicate collection IDs")
    return sorted(nodes)


def collect(path):
    plan = read(path)
    files = sorted(
        p for name in ci_plan.TEST_LANES for p in plan["lanes"][name]["test_files"]
    )
    if not files:
        raise ValueError("No tests were selected")
    command = [
        "uv",
        "run",
        "--no-sync",
        "pytest",
        *files,
        "--strict-markers",
        "-m",
        MARKER,
        "--collect-only",
        "-q",
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    nodes = collection_ids(result.stdout)
    (path.parent / "selected-tests.txt").write_text("\n".join(nodes) + "\n")
    for name in ci_plan.TEST_LANES:
        item = plan["lanes"][name]
        expected = sorted(n for n in nodes if n.split("::")[0] in item["test_files"])
        if {n.split("::")[0] for n in expected} != set(item["test_files"]):
            raise ValueError("Collection is missing an expected test file")
        item.update(
            test_ids=expected,
            selection_digest=ci_plan.digest(expected),
            selection_kind="nodeids",
        )
    plan["selected_ids"] = nodes
    save(path, plan)


def run_selection(path, name):
    plan, output = read(path), path.parent
    item = plan["lanes"][name]
    if (
        item["disposition"] != "selected"
        or item["selection_kind"] != "nodeids"
        or not item["test_ids"]
    ):
        raise ValueError("Lane was not selected/collected before execution")
    workers = 4 if name != "packaging" and len(item["test_ids"]) >= 20 else 1
    xml = output / (name + ".xml")
    command = [
        "uv",
        "run",
        "--no-sync",
        "pytest",
        *item["test_files"],
        "--strict-markers",
        "-m",
        MARKER,
        "--junitxml",
        str(xml),
        "--durations=20",
    ]
    if workers > 1:
        command += ["-n", str(workers)]
    return ci_profile.run(
        Namespace(
            command=command,
            output=output,
            name=name,
            junit=xml,
            mode="xdist" if workers > 1 else "sequential",
            workers=workers,
        )
    )


def run_current(output, name):
    """Run the current manifest during edits; raw profiles retain dirty-tree status."""
    files = [
        path
        for path in ci_plan.current_acceptance_files()
        if path.startswith("tests/packaging/") == (name == "packaging")
    ]
    workers = 1 if name == "packaging" else 4
    xml = output / (name + ".xml")
    command = [
        "uv",
        "run",
        "--no-sync",
        "pytest",
        *files,
        "--strict-markers",
        "-m",
        MARKER,
        "--junitxml",
        str(xml),
        "--durations=20",
    ]
    if workers > 1:
        command += ["-n", str(workers)]
    return ci_profile.run(
        Namespace(
            command=command,
            output=output,
            name=name,
            junit=xml,
            mode="xdist" if workers > 1 else "sequential",
            workers=workers,
        )
    )


def reports(root=ROOT):
    """Check readable, nonempty reports and JSON objects without application imports."""
    checked = set()
    rules = ci_plan.policy(root)
    for pattern in rules["prose"] + rules.get("report_inputs", []):
        # Use the planner's matcher, where '*' can span directories, to avoid
        # classifying nested evidence as report-only without validating it.
        search = root
        for part in Path(pattern).parts:
            if glob.has_magic(part):
                break
            search /= part
        candidates = search.rglob("*") if search.is_dir() else [search]
        for path in sorted(candidates):
            if not path.is_file():
                continue
            relative = str(path.relative_to(root))
            if relative in checked or not ci_plan.matches(relative, [pattern]):
                continue
            if path.is_symlink() or root.resolve() not in path.resolve().parents:
                raise ValueError("Report/prose must be a regular repository file")
            raw = path.read_text(encoding="utf-8")
            if not raw.strip():
                raise ValueError("Empty report/prose file")
            if path.suffix == ".json":
                value = json.loads(
                    raw,
                    parse_constant=lambda _: (_ for _ in ()).throw(
                        ValueError("Nonfinite report JSON")
                    ),
                )
                if not isinstance(value, dict) or not value:
                    raise ValueError("Report must be a nonempty JSON object")
            checked.add(relative)
    return {"checked": sorted(checked), "outcome": "passed"}


def successful_profile(path, context, expected_runtime):
    record = read(path)
    if record["exit_code"] != 0 or record.get("measurement_error"):
        raise ValueError("Selected command failed or output is invalid")
    meta = record["runtime"]
    if (
        meta["commit_sha"] != context["tested_sha"]
        or meta["tracked_changes"]
        or meta["python"] != expected_runtime["python"]
        or meta["sqlite"] != expected_runtime["sqlite"]
    ):
        raise ValueError("Selected command revision/runtime differs")
    if context.get("run_id") and (
        str(meta.get("run_id")) != str(context["run_id"])
        or str(meta.get("run_attempt")) != str(context["run_attempt"])
        or meta.get("feature_sha") != context["feature_sha"]
    ):
        raise ValueError("Selected command belongs to another run/attempt/feature")
    if not math.isfinite(record["wall_seconds"]) or record["wall_seconds"] < 0:
        raise ValueError("Invalid command wall time")
    return record


def gate(path, root=ROOT):
    manifest_path = path.parent / "validation-manifest.json"
    manifest_path.unlink(missing_ok=True)
    plan, output = read(path), path.parent
    rebuilt = ci_plan.make_plan(plan["context"], root=root)
    for key in (
        "version",
        "policy_hash",
        "tree_hash",
        "acceptance_input_hash",
        "runtime",
        "full",
        "acceptance_files",
        "excluded_files",
        "unexecuted_files",
        "preparation",
        "fallback_reasons",
        "changed",
        "comparison_sha",
    ):
        if rebuilt[key] != plan[key]:
            raise ValueError("Plan changed after selection: " + key)
    for name in ci_plan.LANES:
        for key in ("disposition", "test_files"):
            if rebuilt["lanes"][name][key] != plan["lanes"][name][key]:
                raise ValueError("Lane selection was modified")
    if read(output / "reports.json") != reports(root):
        raise ValueError("Missing/changed report validation")
    profiles, selected = {}, []
    for name in ci_plan.TEST_LANES:
        item = plan["lanes"][name]
        result_path = output / (name + ".json")
        if item["disposition"] != "selected":
            if result_path.exists():
                raise ValueError("Unexpected result for an unselected lane")
            continue
        nodes = item["test_ids"]
        if (
            not nodes
            or len(nodes) != len(set(nodes))
            or {n.split("::")[0] for n in nodes} != set(item["test_files"])
            or item["selection_kind"] != "nodeids"
            or item["selection_digest"] != ci_plan.digest(nodes)
        ):
            raise ValueError("Expected selection does not match selected files")
        record = successful_profile(result_path, plan["context"], plan["runtime"])
        actual = record["junit"]["tests"]
        if any(n["status"] != "passed" for n in actual) or sorted(
            n["nodeid"] for n in actual
        ) != sorted(nodes):
            raise ValueError("Selected tests failed/skipped/missing/duplicated/extra")
        selected.extend(nodes)
        profiles[name] = record
    if selected:
        collected = collection_ids((output / "selected-tests.txt").read_text())
        if (
            len(selected) != len(set(selected))
            or sorted(selected) != collected
            or plan.get("selected_ids") != collected
        ):
            raise ValueError("Selected collection differs from recorded execution")
        ci_profile.coverage(
            output / "selected-tests.txt",
            [
                output / (name + ".json")
                for name in ci_plan.TEST_LANES
                if name in profiles
            ],
        )
    command_names = {
        "static": ["lint", "format"],
        "smoke": ["fts", "doctor"],
        "dependencies": ["dependency-setup"],
        "wheelhouse": ["wheelhouse"],
    }
    for name, commands in command_names.items():
        item = plan["lanes"].get(name) or plan["preparation"][name]
        for command in commands:
            result_path = output / (command + ".json")
            if item["disposition"] == "selected":
                profiles[command] = successful_profile(
                    result_path, plan["context"], plan["runtime"]
                )
            elif result_path.exists():
                raise ValueError("Unexpected unselected command output")
    for name in ("planning", "report-validation"):
        profiles[name] = successful_profile(
            output / (name + ".json"), plan["context"], plan["runtime"]
        )
    result = {
        "version": 2,
        "outcome": "passed",
        "context": plan["context"],
        "runtime": plan["runtime"],
        "full_acceptance": plan["full"],
        "acceptance_status": "full_acceptance_passed"
        if plan["full"]
        else "selected_checks_only",
        "acceptance_input_hash": plan["acceptance_input_hash"],
        "coverage": {
            "executed": len(selected),
            "selected_files": sum(
                len(plan["lanes"][k]["test_files"]) for k in ci_plan.TEST_LANES
            ),
            "unexecuted_files": plan["unexecuted_files"],
            "excluded_files": plan["excluded_files"],
        },
        "test_ids": sorted(selected),
        "selection_wall_seconds": plan["selection_wall_seconds"],
        "command_wall_seconds": {
            name: record["wall_seconds"] for name, record in profiles.items()
        },
    }
    save(manifest_path, result)
    status = (
        "Full acceptance passed for the tested inputs."
        if result["full_acceptance"]
        else "Selected checks only; merge acceptance is not established by this run."
    )
    summary = (
        f"## Validation outcome\n\n**{status}**\n\n"
        f"Executed tests: {len(selected)}. Unexecuted acceptance files: {len(plan['unexecuted_files'])}.\n\n"
        f"Acceptance input hash: `{result['acceptance_input_hash']}`. "
        "Final integration requires a completed full acceptance with matching inputs; "
        "an earlier failed, cancelled or in-progress run is insufficient.\n"
    )
    (output / "validation-summary.md").write_text(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as handle:
            handle.write(summary)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("collect", "run", "current", "reports", "gate")
    )
    parser.add_argument(
        "--plan", type=Path, default=Path("artifacts/ci-profile/plan.json")
    )
    parser.add_argument("--lane", choices=ci_plan.TEST_LANES, default="tests")
    args = parser.parse_args()
    if args.action == "reports":
        args.plan.parent.mkdir(parents=True, exist_ok=True)
        save(args.plan.parent / "reports.json", reports())
    elif args.action == "collect":
        collect(args.plan)
    elif args.action == "run":
        return run_selection(args.plan, args.lane)
    elif args.action == "current":
        return run_current(args.plan.parent, args.lane)
    else:
        print(json.dumps(gate(args.plan)["coverage"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
