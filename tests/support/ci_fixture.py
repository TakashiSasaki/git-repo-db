"""Synthetic Git histories and Actions metadata, never hosted test evidence."""

import hashlib
import json
import subprocess
from pathlib import Path

from scripts import ci_plan
from scripts.ci_evidence import GATE_STEP

REPOSITORY = "TakashiSasaki/git-repo-db"


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
    write(root, "README.md", "# Synthetic fixture\n")
    write(root, "scripts/conversion/engine.py", "# Base synthetic engine\n")
    base = commit(root, "base")
    rules = ci_plan.policy()
    for path in rules["policy_inputs"]:
        write(root, path)
    write(root, "scripts/ci_dependencies.json", json.dumps(rules))
    files = sum(rules["groups"].values(), []) + [
        "tests/packaging/test_distribution.py",
        "tests/e2e/test_cli_more.py",
        "tests/integration/test_v2_hardening_reproductions.py",
    ]
    for path in files:
        write(root, path, "def test_synthetic(): pass\n")
    write(
        root,
        "scripts/ci_required_baseline.json",
        json.dumps(
            {
                "version": 1,
                "required_ids": sorted(p + "::test_synthetic" for p in files),
                "minimum_ids": sorted(
                    p + "::test_synthetic"
                    for p in rules["minimum_schema"] + rules["groups"]["p2"]
                ),
            }
        ),
    )
    for path in [
        "src/repo_catalog/example.py",
        "tests/conftest.py",
        "tests/support/cli.py",
        "scripts/conversion/engine.py",
        "pyproject.toml",
        "uv.lock",
        ".gitignore",
        "scripts/demo.py",
        "scripts/prepare_wheelhouse.py",
        "scripts/schema_contract.py",
        "scripts/run_sqlite_minimum_tests.py",
        "scripts/prepare_sqlite_minimum.py",
        "scripts/sqlite_minimum.py",
        "docs/schema-hardening/target-schema.sql",
        "docs/schema-hardening/table-conversion.md",
        "docs/schema-hardening/column-conversion.csv",
    ]:
        write(root, path)
    write(root, "docs/schema-hardening/conversion-contract.json", '{"synthetic":true}')
    write(root, "docs/schema-hardening/p2-foundation.md", "# Synthetic P2 report\n")
    head = commit(root, "feature")
    return base, head


def context(root, base, head, run_id="10"):
    merge = command(
        root,
        "commit-tree",
        command(root, "rev-parse", head + "^{tree}"),
        "-p",
        base,
        "-p",
        head,
        input=b"synthetic tested merge\n",
    )
    return {
        "repository": REPOSITORY,
        "head_repository": REPOSITORY,
        "event": "pull_request",
        "pr": 1,
        "base_sha": base,
        "feature_sha": head,
        "tested_sha": merge,
        "run_id": run_id,
        "run_attempt": "1",
        "full": False,
    }


def materialize(plan):
    for name, item in plan["lanes"].items():
        nodes = sorted(p + "::test_synthetic" for p in item["test_files"])
        item.update(
            test_ids=nodes,
            selection_digest=ci_plan.digest(nodes),
            selection_kind="nodeids",
        )
    plan["required_ids"] = sorted(
        n for k in (*ci_plan.NORMAL, "packaging") for n in plan["lanes"][k]["test_ids"]
    )
    return plan


def manifest(plan):
    materialize(plan)
    return {
        "version": 1,
        "context": plan["context"],
        "policy_hash": plan["policy_hash"],
        "runtime": plan["runtime"],
        "outcome": "passed",
        "full_acceptance": True,
        "required_ids": plan["required_ids"],
        "lanes": {
            k: {
                "state": "passed",
                "provenance": "fresh",
                "input_fingerprint": v["input_fingerprint"],
                "test_ids": v["test_ids"],
                "selection_digest": v["selection_digest"],
            }
            for k, v in plan["lanes"].items()
        },
    }


def envelope(record):
    ctx = record["context"]
    run_id = int(ctx["run_id"])
    checksum = hashlib.sha256(b"synthetic archive").hexdigest()
    raw = json.dumps(record)
    return {
        "manifest": record,
        "manifest_bytes": raw,
        "manifest_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "archive_sha256": checksum,
        "run": {
            "id": run_id,
            "run_attempt": 1,
            "repository": {"id": 42, "full_name": REPOSITORY},
            "head_repository": {"full_name": REPOSITORY},
            "head_sha": ctx["feature_sha"],
            "status": "completed",
            "conclusion": "success",
            "event": "pull_request",
            "path": ".github/workflows/tests.yml",
            "pull_requests": [
                {
                    "number": 1,
                    "head": {"sha": ctx["feature_sha"]},
                    "base": {"sha": ctx["base_sha"]},
                }
            ],
        },
        "artifact": {
            "id": 123,
            "name": f"ci-profile-{run_id}-1",
            "expired": False,
            "expires_at": "2099-01-01T00:00:00Z",
            "digest": "sha256:" + checksum,
            "workflow_run": {
                "id": run_id,
                "head_sha": ctx["feature_sha"],
                "repository_id": 42,
                "head_repository_id": 42,
            },
        },
        "jobs": {
            "total_count": 1,
            "jobs": [
                {
                    "head_sha": ctx["feature_sha"],
                    "name": "offline",
                    "status": "completed",
                    "conclusion": "success",
                    "steps": [
                        {
                            "name": GATE_STEP,
                            "status": "completed",
                            "conclusion": "success",
                        }
                    ],
                }
            ],
        },
    }


def profile(ctx, meta, nodes=()):
    return {
        "exit_code": 0,
        "wall_seconds": 1.0,
        "runtime": {
            "commit_sha": ctx["tested_sha"],
            "python": meta["python"],
            "sqlite": meta["sqlite"],
            "tracked_changes": False,
            "run_id": ctx["run_id"],
            "run_attempt": ctx["run_attempt"],
            "feature_sha": ctx["feature_sha"],
        },
        "junit": {"tests": [{"nodeid": n, "status": "passed"} for n in nodes]},
    }


def write_results(output, plan):
    from scripts import ci_execute

    output.mkdir()
    materialize(plan)
    (output / "plan.json").write_text(json.dumps(plan))
    (output / "required-tests.txt").write_text("\n".join(plan["required_ids"]))
    ctx, meta = plan["context"], plan["runtime"]
    for name, groups in {
        "tests": ci_plan.NORMAL,
        "packaging": ("packaging",),
        "sqlite-minimum": ("minimum-schema", "minimum-p2"),
    }.items():
        nodes = sorted(n for k in groups for n in plan["lanes"][k]["test_ids"])
        record = profile(ctx, meta, nodes)
        if name == "sqlite-minimum":
            record["runtime"]["sqlite"] = "3.46.1"
        (output / (name + ".json")).write_text(json.dumps(record))
    for name in (
        "dependency-setup",
        "wheelhouse",
        "sqlite-preparation",
        "lint",
        "format",
        "fts",
        "doctor",
        "build",
        "export",
        "offline-recovery",
        "evidence-lookup",
        "planning",
        "report-validation",
    ):
        (output / (name + ".json")).write_text(json.dumps(profile(ctx, meta)))
    (output / "reports.json").write_text(
        json.dumps(ci_execute.reports(Path(plan["fixture_root"])))
    )
