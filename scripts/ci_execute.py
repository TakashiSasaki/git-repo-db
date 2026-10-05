"""Execute pre-collected selections and fail-closed reconciliation for CI plans."""

import argparse
import json
import math
import os
import re
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
    output = path.parent
    command = [
        "uv",
        "run",
        "--no-sync",
        "pytest",
        *ci_plan.REQUIRED_DIRS,
        "--strict-markers",
        "-m",
        MARKER,
        "--collect-only",
        "-q",
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    nodes = collection_ids(result.stdout)
    (output / "required-tests.txt").write_text(result.stdout)
    for name in ci_plan.TEST_LANES:
        item = plan["lanes"][name]
        expected = sorted(n for n in nodes if n.split("::")[0] in item["test_files"])
        if not expected or {n.split("::")[0] for n in expected} != set(
            item["test_files"]
        ):
            raise ValueError("Collection is missing an expected test file")
        if item["disposition"] == "reused" and expected != item["test_ids"]:
            raise ValueError("Reused selection differs from current collection")
        item.update(
            test_ids=expected,
            selection_digest=ci_plan.digest(expected),
            selection_kind="nodeids",
        )
    plan["required_ids"] = nodes
    save(path, plan)


def run_selection(path, name):
    plan, output = read(path), path.parent
    lanes = (
        ci_plan.NORMAL
        if name == "tests"
        else ("minimum-schema", "minimum-p2")
        if name == "sqlite-minimum"
        else ("packaging",)
    )
    selected = [
        plan["lanes"][k] for k in lanes if plan["lanes"][k]["disposition"] == "selected"
    ]
    if not selected or any(
        i["selection_kind"] != "nodeids" or not i["test_ids"] for i in selected
    ):
        raise ValueError("Lane was not selected/collected before execution")
    files = sorted({p for i in selected for p in i["test_files"]})
    count = sum(len(i["test_ids"]) for i in selected)
    workers = 4 if name != "packaging" and count >= 20 else 1
    xml = output / (name + ".xml")
    if name == "sqlite-minimum":
        files_path = output / "minimum-selected-files.json"
        save(files_path, files)
        command = [
            "uv",
            "run",
            "--no-sync",
            "python",
            "scripts/run_sqlite_minimum_tests.py",
            "--files-from",
            str(files_path),
        ]
    else:
        command = ["uv", "run", "--no-sync", "pytest", *files]
    command += [
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
            sqlite="3.46.1" if name == "sqlite-minimum" else None,
        )
    )


def reports(root=ROOT):
    """Cheap explicit report/prose validation; no application/dependency imports."""
    rules = ci_plan.policy(root)
    checked = []
    for name in rules["prose"]:
        path = root / name
        if not path.exists():
            continue  # A deletion is recorded by Git; no executable dependency here.
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

            def check(item):
                if isinstance(item, float) and not math.isfinite(item):
                    raise ValueError("Nonfinite report value")
                if isinstance(item, dict):
                    for v in item.values():
                        check(v)
                if isinstance(item, list):
                    for v in item:
                        check(v)

            check(value)
        else:
            for target in re.findall(r"\]\(([^\s()]+)\)", raw):
                if "://" in target or target.startswith("#"):
                    continue
                relative = target.split("#", 1)[0]
                if relative and not (path.parent / relative).exists():
                    raise ValueError("Broken local documentation link")
        checked.append(name)
    return {"checked": checked, "outcome": "passed"}


def successful_profile(path, context, expected_runtime):
    record = read(path)
    if record["exit_code"] != 0 or record.get("measurement_error"):
        raise ValueError("Selected command failed or output is invalid")
    meta = record["runtime"]
    if (
        meta["commit_sha"] != context["tested_sha"]
        or meta["tracked_changes"]
        or meta["python"] != expected_runtime["python"]
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
    (path.parent / "validation-manifest.json").unlink(missing_ok=True)
    plan, output = read(path), path.parent
    envelope_path = output / "evidence.json"
    envelope = ci_plan.load_evidence(envelope_path)
    rebuilt = ci_plan.make_plan(plan["context"], envelope, root=root)
    for key in (
        "policy_hash",
        "runtime",
        "full",
        "preparation",
        "fallback_reasons",
        "changed",
        "comparison_sha",
        "always_checks",
    ):
        if rebuilt[key] != plan[key]:
            raise ValueError("Plan changed after selection: " + key)
    for name in ci_plan.LANES:
        for key in (
            "disposition",
            "input_fingerprint",
            "input_paths",
            "test_files",
            "prior_run",
        ):
            if rebuilt["lanes"][name][key] != plan["lanes"][name][key]:
                raise ValueError("Lane selection was modified")
    report = read(output / "reports.json")
    if report != reports(root):
        raise ValueError("Missing/changed report validation")
    context, meta = plan["context"], plan["runtime"]
    has_tests = any(
        plan["lanes"][k]["disposition"] == "selected" for k in ci_plan.TEST_LANES
    )
    required_path = output / "required-tests.txt"
    if has_tests:
        required = collection_ids(required_path.read_text())
        if plan.get("required_ids") != required:
            raise ValueError("Required collection differs from recorded plan")
    else:
        required = plan["prior_manifest"]["required_ids"]
    for name in ci_plan.TEST_LANES:
        item = plan["lanes"][name]
        expected = sorted(n for n in required if n.split("::")[0] in item["test_files"])
        if (
            not expected
            or item["test_ids"] != expected
            or item["selection_digest"] != ci_plan.digest(expected)
            or item["selection_kind"] != "nodeids"
        ):
            raise ValueError("Expected selection does not match required collection")
    # Independently partition the full collection, even in affected-only mode.
    normal_ids = sum(
        (plan["lanes"][k]["test_ids"] for k in (*ci_plan.NORMAL, "packaging")), []
    )
    if len(normal_ids) != len(set(normal_ids)) or sorted(normal_ids) != required:
        raise ValueError("Plan omitted or duplicated required tests")
    ci_plan.check_baseline(
        required,
        plan["lanes"]["minimum-schema"]["test_ids"]
        + plan["lanes"]["minimum-p2"]["test_ids"],
        root,
    )
    profiles = {}
    selected_groups = {
        "tests": ci_plan.NORMAL,
        "packaging": ("packaging",),
        "sqlite-minimum": ("minimum-schema", "minimum-p2"),
    }
    for profile_name, names in selected_groups.items():
        expected = sorted(
            n
            for k in names
            if plan["lanes"][k]["disposition"] == "selected"
            for n in plan["lanes"][k]["test_ids"]
        )
        if not expected:
            if (output / (profile_name + ".json")).exists():
                raise ValueError("Unexpected result for an unselected lane")
            continue
        record = successful_profile(output / (profile_name + ".json"), context, meta)
        actual = record["junit"]["tests"]
        if (
            any(n["status"] != "passed" for n in actual)
            or sorted(n["nodeid"] for n in actual) != expected
        ):
            raise ValueError("Selected tests failed/skipped/missing/duplicated/extra")
        if record["runtime"]["sqlite"] != (
            "3.46.1" if profile_name == "sqlite-minimum" else meta["sqlite"]
        ):
            raise ValueError("Selected test SQLite runtime differs")
        profiles[profile_name] = record
    command_names = {
        "static": ["lint", "format"],
        "smoke": ["fts", "doctor"],
        "build": ["build", "export"],
        "demo": ["offline-recovery"],
    }
    command_names.update(
        {
            k: [v]
            for k, v in {
                "dependencies": "dependency-setup",
                "wheelhouse": "wheelhouse",
                "sqlite-binding": "sqlite-preparation",
            }.items()
        }
    )
    if plan["preparation"]["dependencies"]["disposition"] == "selected":
        if (
            subprocess.check_output(["uv", "--version"], text=True).split()[1]
            != meta["uv"]
        ):
            raise ValueError(
                "Actual uv runtime differs from declared dependency preparation"
            )
    for name, commands in command_names.items():
        item = plan["lanes"].get(name) or plan["preparation"][name]
        for command in commands:
            if item["disposition"] == "selected":
                profiles[command] = successful_profile(
                    output / (command + ".json"), context, meta
                )
            elif (output / (command + ".json")).exists():
                raise ValueError("Unexpected unselected command output")
    for name in ("evidence-lookup", "planning", "report-validation"):
        profiles[name] = successful_profile(output / (name + ".json"), context, meta)
    # Keep the existing independent required-ID reconciler. The expected set was
    # collected before execution; it cannot shrink to whatever happened to pass.
    for profile_names, groups, filename in (
        (("tests", "packaging"), (*ci_plan.NORMAL, "packaging"), "selected-tests.txt"),
        (
            ("sqlite-minimum",),
            ("minimum-schema", "minimum-p2"),
            "selected-minimum-tests.txt",
        ),
    ):
        expected = sorted(
            n
            for name in groups
            if plan["lanes"][name]["disposition"] == "selected"
            for n in plan["lanes"][name]["test_ids"]
        )
        if expected:
            (output / filename).write_text("\n".join(expected) + "\n")
            ci_profile.coverage(
                output / filename,
                [
                    output / (name + ".json")
                    for name in profile_names
                    if name in profiles
                ],
            )
    lanes = {}
    for name, item in plan["lanes"].items():
        reused = item["disposition"] == "reused"
        lanes[name] = {
            "state": "passed",
            "provenance": "reused" if reused else "fresh",
            "prior_run": item["prior_run"],
            "input_fingerprint": item["input_fingerprint"],
            "selection_digest": ci_plan.digest(item["test_ids"]),
            "test_ids": item["test_ids"],
        }
    result = {
        "version": 1,
        "outcome": "passed",
        "context": context,
        "policy_hash": plan["policy_hash"],
        "runtime": meta,
        "full_acceptance": plan["full"],
        "required_ids": required,
        "lanes": lanes,
        "coverage": {
            "required": len(required),
            "fresh": sum(
                len(lanes[k]["test_ids"])
                for k in (*ci_plan.NORMAL, "packaging")
                if lanes[k]["provenance"] == "fresh"
            ),
            "reused": sum(
                len(lanes[k]["test_ids"])
                for k in (*ci_plan.NORMAL, "packaging")
                if lanes[k]["provenance"] == "reused"
            ),
            "minimum_fresh": sum(
                len(lanes[k]["test_ids"])
                for k in ("minimum-schema", "minimum-p2")
                if lanes[k]["provenance"] == "fresh"
            ),
            "minimum_reused": sum(
                len(lanes[k]["test_ids"])
                for k in ("minimum-schema", "minimum-p2")
                if lanes[k]["provenance"] == "reused"
            ),
        },
        "preparation": plan["preparation"],
        "selection_wall_seconds": plan["selection_wall_seconds"],
        "command_wall_seconds": {k: p["wall_seconds"] for k, p in profiles.items()},
        "always_checks": plan["always_checks"],
    }
    save(output / "validation-manifest.json", result)
    summary = (
        "## Validation outcome\n\n"
        + json.dumps(result["coverage"])
        + "\n\nFresh execution and reused earlier acceptance are reported separately. Binding cache: not enabled.\n"
    )
    (output / "validation-summary.md").write_text(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as handle:
            handle.write(summary)
    if not required_path.exists():
        required_path.write_text("\n".join(required) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("collect", "run", "reports", "gate"))
    parser.add_argument(
        "--plan", type=Path, default=Path("artifacts/ci-profile/plan.json")
    )
    parser.add_argument("--lane", choices=("tests", "packaging", "sqlite-minimum"))
    args = parser.parse_args()
    if args.action == "reports":
        args.plan.parent.mkdir(parents=True, exist_ok=True)
        save(args.plan.parent / "reports.json", reports())
    elif args.action == "collect":
        collect(args.plan)
    elif args.action == "run":
        return run_selection(args.plan, args.lane)
    else:
        print(json.dumps(gate(args.plan)["coverage"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
