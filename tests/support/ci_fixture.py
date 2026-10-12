"""Disposable Git histories and command records for current CI selection tests."""

import json
import subprocess

from scripts import ci_execute, ci_plan


def command(root, *args, input=None):
    return (
        subprocess.check_output(["git", "-C", str(root), *args], input=input)
        .decode()
        .strip()
    )


def write(root, name, value="synthetic\n"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)


def commit(root, message="synthetic"):
    command(root, "add", "--all")
    command(root, "commit", "-qm", message)
    return command(root, "rev-parse", "HEAD")


def repository(root):
    root.mkdir()
    command(root, "init", "-q")
    command(root, "config", "user.name", "Synthetic Fixture")
    command(root, "config", "user.email", "fixture@example.invalid")
    rules = ci_plan.policy()
    files = [
        "tests/unit/test_contracts.py",
        "tests/integration/test_runtime_flow.py",
        "tests/packaging/test_distribution.py",
    ]
    for path in rules["policy_inputs"]:
        write(root, path)
    write(root, "scripts/ci_dependencies.json", json.dumps(rules))
    for path in files:
        write(root, path, "def test_synthetic(): pass\n")
    write(root, "README.md", "# Synthetic fixture\n")
    write(root, "src/repo_catalog/example.py", "# Synthetic source\n")
    base = commit(root, "base")
    write(root, "src/repo_catalog/example.py", "# Changed source\n")
    return base, commit(root, "feature")


def context(root, base, head, run_id="10", event="pull_request", mode="development"):
    merge = command(
        root,
        "commit-tree",
        command(root, "rev-parse", head + "^{tree}"),
        "-p",
        base,
        "-p",
        head,
        input=b"synthetic merge\n",
    )
    is_release = mode == "release"
    return {
        "event": event,
        "base_sha": base,
        "before_sha": base,
        "feature_sha": head,
        "tested_sha": merge if event == "pull_request" else head,
        "run_id": run_id,
        "run_attempt": "1",
        "mode": mode,
        "full": is_release,
    }


def profile(ctx, meta, nodes=()):
    return {
        "exit_code": 0,
        "wall_seconds": 0.01,
        "runtime": {
            **meta,
            "commit_sha": ctx["tested_sha"],
            "tracked_changes": False,
            "run_id": ctx.get("run_id"),
            "run_attempt": ctx.get("run_attempt"),
            "feature_sha": ctx["feature_sha"],
        },
        "junit": {"tests": [{"nodeid": node, "status": "passed"} for node in nodes]},
    }


def make_junit_xml(nodes):
    cases = []
    for node in nodes:
        file_part, name_part = node.split("::")
        classname = file_part.removesuffix(".py").replace("/", ".")
        cases.append(
            f'<testcase classname="{classname}" file="{file_part}" name="{name_part}" time="0.01"/>'
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<testsuites><testsuite name="pytest" tests="{len(nodes)}" errors="0" failures="0" skipped="0">'
        f"{''.join(cases)}"
        "</testsuite></testsuites>\n"
    )


def make_journal(nodes):
    lines = []
    for node in nodes:
        lines.append(
            json.dumps(
                {
                    "event": "start",
                    "nodeid": node,
                    "worker_id": "master",
                    "timestamp": 1000.0,
                }
            )
        )
        lines.append(
            json.dumps(
                {
                    "event": "phase",
                    "nodeid": node,
                    "phase": "setup",
                    "outcome": "passed",
                    "duration": 0.001,
                    "worker_id": "master",
                    "timestamp": 1000.001,
                }
            )
        )
        lines.append(
            json.dumps(
                {
                    "event": "phase",
                    "nodeid": node,
                    "phase": "call",
                    "outcome": "passed",
                    "duration": 0.008,
                    "worker_id": "master",
                    "timestamp": 1000.009,
                }
            )
        )
        lines.append(
            json.dumps(
                {
                    "event": "phase",
                    "nodeid": node,
                    "phase": "teardown",
                    "outcome": "passed",
                    "duration": 0.001,
                    "worker_id": "master",
                    "timestamp": 1000.010,
                }
            )
        )
    lines.append(
        json.dumps(
            {
                "event": "finish",
                "status": "completed",
                "exitstatus": 0,
                "timestamp": 1000.020,
            }
        )
    )
    return "\n".join(lines) + "\n"


def write_results(output, plan, root):
    output.mkdir()
    tree_sha = command(root, "rev-parse", "HEAD^{tree}")
    selected = []
    for name in ci_plan.TEST_LANES:
        item = plan["lanes"][name]
        nodes = sorted(p + "::test_synthetic" for p in item["test_files"])
        if nodes:
            item.update(
                test_ids=nodes,
                selection_kind="nodeids",
                selection_digest=ci_plan.digest(nodes),
            )
            write(
                output,
                name + ".json",
                json.dumps(
                    profile(
                        plan["context"],
                        {**plan["runtime"], "tree_sha": tree_sha},
                        nodes,
                    )
                ),
            )
            write(output, name + ".xml", make_junit_xml(nodes))
            write(output, name + "-journal.jsonl", make_journal(nodes))
            selected.extend(nodes)
    if selected:
        plan["selected_ids"] = sorted(selected)
        write(output, "selected-tests.txt", "\n".join(sorted(selected)) + "\n")
    write(output, "plan.json", json.dumps(plan))
    write(output, "reports.json", json.dumps(ci_execute.reports(root)))
    names = ["planning", "report-validation"]
    if plan["lanes"]["static"]["disposition"] == "selected":
        names += ["lint", "format"]
    if plan["lanes"]["smoke"]["disposition"] == "selected":
        names += ["fts", "doctor"]
    for name, item in plan["preparation"].items():
        if item["disposition"] == "selected":
            names.append("dependency-setup" if name == "dependencies" else name)
    for name in names:
        write(
            output,
            name + ".json",
            json.dumps(
                profile(
                    plan["context"],
                    {**plan["runtime"], "tree_sha": tree_sha},
                )
            ),
        )
    binding = {
        "head": plan["context"]["tested_sha"],
        "tree": tree_sha,
        "feature_sha": plan["context"]["feature_sha"],
        "run_id": plan["context"].get("run_id", "10"),
        "run_attempt": plan["context"].get("run_attempt", "1"),
    }
    write(output, "receipt-binding.json", json.dumps(binding))
    write(
        output,
        "run-verification.json",
        json.dumps(
            {
                "status": "completed",
                "conclusion": "success",
                "run_id": plan["context"].get("run_id", "10"),
                "head_sha": plan["context"]["tested_sha"],
                "source": "github_actions",
            }
        ),
    )
