import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import ci_execute, ci_plan
from tests.support.ci_fixture import commit, context, repository, write, write_results

ROOT = ci_execute.ROOT


@pytest.fixture
def acceptance(tmp_path):
    root = tmp_path / "repo"
    base, head = repository(root)
    plan = ci_plan.make_plan(context(root, base, head, mode="release"), root=root)
    output = tmp_path / "result"
    write_results(output, plan, root)
    return root, output


def test_full_current_acceptance_reports_exact_execution(acceptance):
    root, output = acceptance
    result = ci_execute.gate(output / "plan.json", root)
    assert result["product_full_acceptance"]
    assert not result["full_acceptance"]
    assert result["documentation_status"] == "not_verified"
    assert result["acceptance_status"] == "hosted_product_release_passed"
    assert result["coverage"]["executed"] == 3
    assert not result["coverage"]["unexecuted_files"]
    assert json.loads((output / "validation-manifest.json").read_bytes()) == result


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "failed",
        "skipped",
        "duplicate",
        "extra",
        "wrong-runtime",
        "missing-preparation",
        "changed-plan",
        "empty-collection",
        "remove-selected-test",
        "changed-report",
    ],
)
def test_reconciliation_rejects_failed_missing_skipped_or_tampered_outputs(
    acceptance, mutation
):
    root, output = acceptance
    path = output / "tests.json"
    record = json.loads(path.read_bytes())
    if mutation == "missing":
        path.unlink()
    elif mutation == "failed":
        record["exit_code"] = 1
    elif mutation == "skipped":
        record["junit"]["tests"][0]["status"] = "skipped"
    elif mutation == "duplicate":
        record["junit"]["tests"].append(record["junit"]["tests"][0])
    elif mutation == "extra":
        record["junit"]["tests"].append(
            {"nodeid": "tests/unit/extra.py::test_extra", "status": "passed"}
        )
    elif mutation == "wrong-runtime":
        record["runtime"]["sqlite"] = "0.0.0"
    elif mutation == "missing-preparation":
        (output / "wheelhouse.json").unlink()
    elif mutation == "changed-plan":
        plan = json.loads((output / "plan.json").read_bytes())
        plan["lanes"]["tests"]["disposition"] = "not_applicable"
        (output / "plan.json").write_text(json.dumps(plan))
    elif mutation == "empty-collection":
        (output / "selected-tests.txt").write_text("0 tests collected")
    elif mutation == "remove-selected-test":
        plan = json.loads((output / "plan.json").read_bytes())
        plan["lanes"]["tests"]["test_ids"].pop()
        (output / "plan.json").write_text(json.dumps(plan))
    else:
        (output / "reports.json").write_text("{}")
    if mutation in ("failed", "skipped", "duplicate", "extra", "wrong-runtime"):
        path.write_text(json.dumps(record))
    with pytest.raises((ValueError, FileNotFoundError)):
        ci_execute.gate(output / "plan.json", root)
    assert not (output / "validation-manifest.json").exists()


@pytest.mark.parametrize("event", ["push", "pull_request"])
def test_prose_followup_reports_unexecuted_files_without_claiming_full_acceptance(
    acceptance,
    event,
):
    root, full_output = acceptance
    full = ci_execute.gate(full_output / "plan.json", root)
    head = full["context"]["feature_sha"]
    write(root, "README.md", "# Updated prose\n")
    base = full["context"]["base_sha"] if event == "pull_request" else head
    current = context(root, base, commit(root), event=event)
    if event == "pull_request":
        current.update(action="synchronize", before_sha=head)
    output = full_output.parent / "prose"
    write_results(output, ci_plan.make_plan(current, root=root), root)
    result = ci_execute.gate(output / "plan.json", root)
    assert not result["full_acceptance"]
    assert result["acceptance_status"] == "development_checks_passed"
    assert result["acceptance_input_hash"] == full["acceptance_input_hash"]
    assert result["coverage"]["executed"] == 0
    assert len(result["coverage"]["unexecuted_files"]) == 3
    (output / "tests.json").write_text(json.dumps({"exit_code": 0}))
    with pytest.raises(ValueError, match="Unexpected"):
        ci_execute.gate(output / "plan.json", root)


@pytest.mark.parametrize(
    "lane,count,requested,workers",
    [
        ("tests", 4, None, 1),
        ("tests", 24, None, 2),
        ("packaging", 1, None, 1),
        ("packaging", 2, None, 2),
        ("tests", 24, 2, 2),
        ("tests", 4, 2, 2),
        ("packaging", 2, 1, 1),
        ("tests", 1, 8, 1),
    ],
)
def test_selection_parallelism_keeps_small_defaults_and_bounds_overrides(
    acceptance, monkeypatch, lane, count, requested, workers
):
    # This orchestration fixture checks selection defaults, not host resource
    # availability; scheduler resource caps have independent controls.
    monkeypatch.setattr(ci_execute.resource_scheduler, "available_cpu_count", lambda: 8)
    monkeypatch.setattr(
        ci_execute.resource_scheduler, "available_memory_mb", lambda: 8192
    )
    _, output = acceptance
    path = output / "plan.json"
    plan = json.loads(path.read_bytes())
    plan["lanes"][lane]["test_ids"] = [f"synthetic::{i}" for i in range(count)]
    path.write_text(json.dumps(plan))
    seen = []
    monkeypatch.setattr(
        ci_execute.ci_profile, "run", lambda args: seen.append(args) or 0
    )
    assert ci_execute.run_selection(path, lane, requested) == 0
    assert seen[0].workers == workers
    assert ("-n" in seen[0].command) == (workers > 1)
    assert ("--dist" in seen[0].command) == (workers > 1)
    if workers > 1:
        assert seen[0].command[-2:] == ["--dist", "worksteal"]


@pytest.mark.parametrize("workers", [0, -1])
def test_invalid_worker_count_is_rejected_before_test_execution(workers):
    with pytest.raises(
        argparse.ArgumentTypeError, match="Workers must be at least one"
    ):
        ci_execute.positive_workers(workers)


def test_empty_and_duplicate_collection_are_rejected():
    for raw in ("", "0 tests collected", "tests/unit/a.py::a\ntests/unit/a.py::a"):
        with pytest.raises(ValueError):
            ci_execute.collection_ids(raw)


@pytest.mark.parametrize(
    "path",
    [
        "docs/ci-performance-results.json",
        "docs/validation/synthetic/corrective-acceptance.json",
        "docs/validation/synthetic/nested/corrective-acceptance.json",
    ],
)
@pytest.mark.parametrize("value", ['{"seconds":NaN}', "[]", "{}", "", "{broken"])
def test_historical_and_synthetic_report_json_is_validated(tmp_path, path, value):
    root = tmp_path / "repo"
    repository(root)
    write(root, path, value)
    with pytest.raises(ValueError):
        ci_execute.reports(root)


@pytest.mark.parametrize(
    "directory", ["docs/validation/synthetic", "docs/validation/synthetic/nested"]
)
def test_synthetic_evidence_only_changes_validate_json_without_runtime_lanes(
    tmp_path, directory
):
    root = tmp_path / "repo"
    _, before = repository(root)
    path = directory + "/corrective-acceptance.json"
    write(root, path, '{"outcome":"passed","full_acceptance":false}\n')
    plan = ci_plan.make_plan(
        context(root, before, commit(root), event="push"), root=root
    )
    assert not plan["full"]
    assert all(
        item["disposition"] == "not_applicable" for item in plan["lanes"].values()
    )
    output = tmp_path / "reports-only"
    write_results(output, plan, root)
    assert path in ci_execute.reports(root)["checked"]
    assert ci_execute.gate(output / "plan.json", root)["coverage"]["executed"] == 0


def synthetic_pytest(root, files):
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *files],
        cwd=root,
        env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize("directory", ci_plan.REQUIRED_DIRS)
@pytest.mark.parametrize(
    "filename", ["test_added_regression.py", "added_regression_test.py"]
)
def test_new_failing_test_cannot_disappear_from_full_acceptance(
    tmp_path, directory, filename
):
    root = tmp_path / "repo"
    _, before = repository(root)
    path = directory + "/" + filename
    write(root, path, "def test_new_regression(): assert False\n")
    ctx = dict(context(root, before, commit(root), event="push"), full=True)
    plan = ci_plan.make_plan(ctx, root=root)
    files = [
        p for lane in ci_plan.TEST_LANES for p in plan["lanes"][lane]["test_files"]
    ]
    result = synthetic_pytest(root, files)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "test_new_regression" in result.stdout
    assert not plan["excluded_files"]


def test_shared_test_change_runs_consumer_with_broken_import(tmp_path):
    root = tmp_path / "repo"
    repository(root)
    for path in ("tests/__init__.py", "tests/unit/__init__.py"):
        write(root, path, "")
    helper = "tests/unit/test_contracts.py"
    consumer = "tests/unit/test_consumer.py"
    write(root, helper, "shared = 1\ndef test_synthetic(): pass\n")
    write(
        root,
        consumer,
        "from .test_contracts import shared\ndef test_consumer(): assert shared == 1\n",
    )
    before = commit(root)
    write(root, helper, "renamed = 1\ndef test_synthetic(): pass\n")
    ctx = context(root, before, commit(root), event="push", mode="release")
    plan = ci_plan.make_plan(ctx, root=root)
    assert synthetic_pytest(root, [helper]).returncode == 0
    result = synthetic_pytest(root, plan["lanes"]["tests"]["test_files"])
    assert result.returncode == 2, result.stdout + result.stderr
    assert "cannot import name 'shared'" in result.stdout


@pytest.mark.parametrize(
    "previous_state", ["failed", "cancelled", "in_progress", "never_run"]
)
def test_prose_after_unfinished_source_acceptance_does_not_establish_merge_readiness(
    acceptance, previous_state
):
    root, full_output = acceptance
    prior = json.loads((full_output / "plan.json").read_bytes())
    result_path = full_output / "tests.json"
    if previous_state == "failed":
        record = json.loads(result_path.read_bytes())
        record["exit_code"] = 1
        result_path.write_text(json.dumps(record))
    else:
        # Interrupted/absent source execution has no completed lane profile.
        result_path.unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        ci_execute.gate(full_output / "plan.json", root)
    before = prior["context"]["feature_sha"]
    write(root, "README.md", "# Prose pushed before source acceptance completes\n")
    ctx = dict(
        context(root, prior["context"]["base_sha"], commit(root)),
        action="synchronize",
        before_sha=before,
    )
    output = full_output.parent / "prose-followup"
    plan = ci_plan.make_plan(ctx, root=root)
    write_results(output, plan, root)
    result = ci_execute.gate(output / "plan.json", root)
    assert result["acceptance_status"] == "development_checks_passed"
    assert result["acceptance_input_hash"] == prior["acceptance_input_hash"]
    assert result["coverage"]["unexecuted_files"] == prior["acceptance_files"]
    assert (
        "Full runtime acceptance is not established"
        in (output / "validation-summary.md").read_text()
    )


def test_runtime_changes_invalidate_prior_acceptance_input_fingerprint(acceptance):
    root, output = acceptance
    prior = ci_execute.gate(output / "plan.json", root)
    write(root, "src/repo_catalog/example.py", "# Changed after completed acceptance\n")
    ctx = context(root, prior["context"]["feature_sha"], commit(root), event="push")
    assert (
        ci_plan.make_plan(ctx, root=root)["acceptance_input_hash"]
        != prior["acceptance_input_hash"]
    )


@pytest.mark.parametrize("field", ["run_id", "run_attempt", "feature_sha"])
def test_stale_profiles_cannot_satisfy_current_execution(acceptance, field):
    root, output = acceptance
    path = output / "tests.json"
    record = json.loads(path.read_bytes())
    record["runtime"][field] = "wrong-execution"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="another run"):
        ci_execute.gate(output / "plan.json", root)


def test_workflow_keeps_one_environment_and_conditions_expensive_checks():
    workflow = (ci_plan.ROOT / ".github/workflows/tests.yml").read_text()
    assert "  offline:" in workflow and "pull_request_target" not in workflow
    assert "cancel-in-progress: true" in workflow
    assert "branches: [main]" in workflow and "fetch-depth: 0" in workflow
    assert "sqlite-minimum" not in workflow and "evidence-lookup" not in workflow
    for lane in ("dependencies", "wheelhouse", "tests", "packaging", "smoke", "static"):
        assert f"steps.plan.outputs.{lane} == 'true'" in workflow


def make_valid_receipt(plan, output=None, root=None):
    ordinary_nodes = [
        "tests/integration/test_runtime_flow.py::test_synthetic",
        "tests/unit/test_contracts.py::test_synthetic",
    ]
    packaging_nodes = [
        "tests/packaging/test_distribution.py::test_synthetic",
    ]
    all_nodes = sorted(ordinary_nodes + packaging_nodes)
    tests_xml_sha = "0" * 64
    tests_journal_sha = "0" * 64
    pkg_xml_sha = "0" * 64
    pkg_journal_sha = "0" * 64
    tree_sha = "0" * 40

    if output is not None:
        t_xml = output / "tests.xml"
        if t_xml.is_file():
            tests_xml_sha = hashlib.sha256(t_xml.read_bytes()).hexdigest()
        t_j = output / "tests-journal.jsonl"
        if t_j.is_file():
            tests_journal_sha = hashlib.sha256(t_j.read_bytes()).hexdigest()
        p_xml = output / "packaging.xml"
        if p_xml.is_file():
            pkg_xml_sha = hashlib.sha256(p_xml.read_bytes()).hexdigest()
        p_j = output / "packaging-journal.jsonl"
        if p_j.is_file():
            pkg_journal_sha = hashlib.sha256(p_j.read_bytes()).hexdigest()
        b_file = output / "receipt-binding.json"
        if b_file.is_file():
            tree_sha = json.loads(b_file.read_bytes()).get("tree", tree_sha)

    if root is not None and (root / ".git").is_dir():
        try:
            tree_sha = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD^{tree}"], text=True
            ).strip()
        except Exception:
            pass

    return {
        "schema_version": 1,
        "kind": "local_release_receipt",
        "commit_sha": plan["context"]["tested_sha"],
        "tree_sha": tree_sha,
        "acceptance_input_hash": plan["acceptance_input_hash"],
        "exit_code": 0,
        "status": "passed",
        "dirty": False,
        "tracked_changes": False,
        "passed_nodes": all_nodes,
        "passed_count": len(all_nodes),
        "failed_nodes": [],
        "failed_count": 0,
        "skipped_nodes": [],
        "skipped_count": 0,
        "lanes": {
            "tests": {
                "exit_code": 0,
                "status": "passed",
                "passed_nodes": ordinary_nodes,
                "passed_count": len(ordinary_nodes),
                "failed_nodes": [],
                "skipped_nodes": [],
                "junit_file": "tests.xml",
                "junit_sha256": tests_xml_sha,
                "journal_file": "tests-journal.jsonl",
                "journal_sha256": tests_journal_sha,
            },
            "packaging": {
                "exit_code": 0,
                "status": "passed",
                "passed_nodes": packaging_nodes,
                "passed_count": len(packaging_nodes),
                "failed_nodes": [],
                "skipped_nodes": [],
                "junit_file": "packaging.xml",
                "junit_sha256": pkg_xml_sha,
                "journal_file": "packaging-journal.jsonl",
                "journal_sha256": pkg_journal_sha,
            },
        },
    }


def test_complete_release_reconciliation_with_valid_local_receipt(acceptance):
    root, output = acceptance
    plan = json.loads((output / "plan.json").read_bytes())
    receipt = make_valid_receipt(plan, output=output, root=root)
    (output / "local-receipt.json").write_text(json.dumps(receipt))
    result = ci_execute.gate(output / "plan.json", root)
    assert result["product_full_acceptance"]
    assert not result["full_acceptance"]
    assert result["documentation_status"] == "not_verified"
    assert result["acceptance_status"] == "product_release_passed"
    assert result["evidence_status"] == "local_evidence_verified"


@pytest.mark.parametrize(
    "tamper,expected_reason_substr",
    [
        (
            lambda r: r.update(
                passed_nodes=[
                    "tests/unit/test_contracts.py::test_synthetic",
                    "synthetic::1",
                    "synthetic::2",
                ]
            ),
            "outside required acceptance directories",
        ),
        (
            lambda r: r.update(
                passed_nodes=[
                    "tests/unit/test_contracts.py::test_synthetic",
                    "not_a_valid_node_id",
                    "tests/packaging/test_distribution.py::test_synthetic",
                ]
            ),
            "Malformed node identifier",
        ),
        (
            lambda r: (
                r.update(
                    passed_nodes=[
                        "tests/unit/test_contracts.py::test_synthetic",
                        "tests/packaging/test_distribution.py::test_synthetic",
                    ],
                    passed_count=2,
                ),
                r["lanes"]["tests"].update(
                    passed_nodes=[
                        "tests/unit/test_contracts.py::test_synthetic",
                    ],
                    passed_count=1,
                ),
            ),
            "Node reconciliation mismatch",
        ),
        (
            lambda r: (
                r.update(
                    passed_nodes=[
                        "tests/unit/test_contracts.py::test_synthetic",
                        "tests/unit/test_contracts.py::test_other",
                        "tests/packaging/test_distribution.py::test_synthetic",
                    ],
                    passed_count=3,
                ),
                r["lanes"]["tests"].update(
                    passed_nodes=[
                        "tests/unit/test_contracts.py::test_synthetic",
                        "tests/unit/test_contracts.py::test_other",
                    ],
                    passed_count=2,
                ),
            ),
            "Node reconciliation mismatch",
        ),
        (
            lambda r: r.update(
                passed_nodes=[
                    "tests/unit/test_contracts.py::test_synthetic",
                    "tests/unit/test_contracts.py::test_synthetic",
                    "tests/packaging/test_distribution.py::test_synthetic",
                ],
                passed_count=3,
            ),
            "duplicate",
        ),
        (
            lambda r: r.pop("exit_code"),
            "exit_code",
        ),
        (
            lambda r: r.update(exit_code=1),
            "exit_code",
        ),
        (
            lambda r: r.update(status="failed"),
            "status",
        ),
        (
            lambda r: r.update(
                passed_nodes=[
                    "tests/unit/test_contracts.py::test_synthetic",
                    "tests/integration/test_runtime_flow.py::test_synthetic",
                ],
                passed_count=2,
            ),
            "Packaging validation is missing",
        ),
        (
            lambda r: r.update(
                passed_nodes=[
                    "tests/packaging/test_distribution.py::test_synthetic",
                ],
                passed_count=1,
            ),
            "Ordinary test validation is missing",
        ),
        (
            lambda r: r.update(dirty=True),
            "dirty",
        ),
        (
            lambda r: r.update(tracked_changes=True),
            "uncommitted changes",
        ),
        (
            lambda r: r.update(
                acceptance_input_hash="0000000000000000000000000000000000000000000000000000000000000000"
            ),
            "Acceptance input hash mismatch",
        ),
        (
            lambda r: r.update(commit_sha="0000000000000000000000000000000000000000"),
            "Commit SHA mismatch",
        ),
        (
            lambda r: r.update(
                failed_nodes=["tests/unit/test_contracts.py::test_synthetic"],
                failed_count=1,
            ),
            "failures",
        ),
        (
            lambda r: r.update(
                skipped_nodes=["tests/unit/test_contracts.py::test_synthetic"],
                skipped_count=1,
            ),
            "skips",
        ),
        (
            lambda r: r.pop("commit_sha"),
            "Missing commit_sha",
        ),
        (
            lambda r: r.pop("lanes"),
            "Lanes mapping is missing",
        ),
        (
            lambda r: r["lanes"].pop("packaging"),
            "Lanes mapping is missing or must contain",
        ),
        (
            lambda r: r.update(interrupted=True),
            "interrupted",
        ),
        (
            lambda r: r.update(
                error_nodes=["tests/unit/test_contracts.py::test_synthetic"],
                error_count=1,
            ),
            "errors",
        ),
        (
            lambda r: r["lanes"]["tests"].update(
                failed_nodes=["tests/unit/test_contracts.py::test_synthetic"],
                failed_count=1,
            ),
            "records non-empty failed_nodes",
        ),
        (
            lambda r: r["lanes"]["tests"].update(
                passed_nodes=[
                    "tests/packaging/test_distribution.py::test_synthetic",
                    "tests/unit/test_contracts.py::test_synthetic",
                ]
            ),
            "Tests lane contains packaging node",
        ),
        (
            lambda r: r["lanes"]["tests"].update(junit_sha256="invalid_sha"),
            "invalid junit_sha256",
        ),
        (
            lambda r: r.update(passed_count=999),
            "Contradictory passed_count",
        ),
    ],
)
def test_adversarial_receipt_tampering_is_rejected(
    acceptance, tamper, expected_reason_substr
):
    root, output = acceptance
    plan = json.loads((output / "plan.json").read_bytes())
    receipt = make_valid_receipt(plan, output=output, root=root)
    tamper(receipt)

    valid, reason = ci_execute.verify_local_receipt(
        receipt,
        plan,
        required_nodes=set(
            plan["lanes"]["tests"]["test_ids"] + plan["lanes"]["packaging"]["test_ids"]
        ),
        root=root,
        receipt_path=output / "local-receipt.json",
    )
    assert not valid
    assert expected_reason_substr.lower() in reason.lower()

    (output / "local-receipt.json").write_text(json.dumps(receipt))
    result = ci_execute.gate(output / "plan.json", root)
    assert result["acceptance_status"] == "release_rejected"
    assert result["outcome"] == "failed"
    assert result["evidence_status"] == "local_evidence_failed"


def test_create_receipt_and_reconcile_release_workflow(acceptance):
    root, output = acceptance
    plan = json.loads((output / "plan.json").read_bytes())

    receipt = ci_execute.create_receipt(output, root=root)
    assert receipt["exit_code"] == 0
    assert receipt["passed_count"] == 3
    assert receipt["acceptance_input_hash"] == plan["acceptance_input_hash"]

    gate_res = ci_execute.gate(output / "plan.json", root)
    assert gate_res["acceptance_status"] == "product_release_passed"
    assert gate_res["evidence_status"] == "local_evidence_verified"

    manifest_path = output / "validation-manifest.json"
    local_rec_path = output / "local-receipt.json"

    # Authoritative Tier 3 verified hosted run
    reconciled = ci_execute.reconcile_release(
        local_rec_path,
        manifest_path,
        root=root,
        run_verifier=lambda rid, b, h: (True, None),
    )
    assert reconciled["verdict"] == "product_release_passed"
    assert reconciled["acceptance_status"] == "product_release_passed"

    # Unverified hosted run without gh verification yields validation_gap_reported
    unverified = ci_execute.reconcile_release(local_rec_path, manifest_path, root=root)
    assert unverified["verdict"] == "validation_gap_reported"
    assert unverified["acceptance_status"] == "validation_gap_reported"

    # Invalid receipt must yield release_rejected for both verdict and acceptance_status
    bad_rec_path = output / "bad-receipt.json"
    bad_rec_path.write_text(json.dumps({"exit_code": 1}))
    rejected = ci_execute.reconcile_release(
        bad_rec_path,
        manifest_path,
        root=root,
        run_verifier=lambda rid, b, h: (True, None),
    )
    assert rejected["verdict"] == "release_rejected"
    assert rejected["acceptance_status"] == "release_rejected"


def test_corrupted_local_receipt_fails_closed(acceptance):
    root, output = acceptance
    (output / "local-receipt.json").write_text("{corrupt json")
    result = ci_execute.gate(output / "plan.json", root)
    assert result["acceptance_status"] == "release_rejected"
    assert result["outcome"] == "failed"
    assert result["evidence_status"] == "local_evidence_failed"


def test_contradictory_candidate_receipts_fail_closed(acceptance):
    root, output = acceptance
    plan = json.loads((output / "plan.json").read_bytes())
    valid_rec = make_valid_receipt(plan, output=output, root=root)
    receipts_dir = output / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    (receipts_dir / "valid.json").write_text(json.dumps(valid_rec))

    failed_rec = make_valid_receipt(plan, output=output, root=root)
    failed_rec["exit_code"] = 1
    (output / "local-receipt.json").write_text(json.dumps(failed_rec))

    result = ci_execute.gate(output / "plan.json", root)
    assert result["acceptance_status"] == "release_rejected"
    assert result["outcome"] == "failed"
    assert result["evidence_status"] == "local_evidence_failed"


def test_create_receipt_rejects_dirty_worktree(acceptance):
    root, output = acceptance
    write(root, "untracked.txt", "dirty\n")
    with pytest.raises(ValueError, match="dirty working tree"):
        ci_execute.create_receipt(output, root=root)


def test_development_mode_gate_records_development_checks_passed(tmp_path):
    root = tmp_path / "repo"
    base, head = repository(root)
    plan = ci_plan.make_plan(context(root, base, head, mode="development"), root=root)
    output = tmp_path / "dev-result"
    write_results(output, plan, root)
    result = ci_execute.gate(output / "plan.json", root)
    assert not result["full_acceptance"]
    assert result["validation_mode"] == "development"
    assert result["acceptance_status"] == "development_checks_passed"
    assert (
        "Development infrastructure checks passed"
        in (output / "validation-summary.md").read_text()
    )


# ==============================================================================
# Section 6: Explicit Adversarial Regressions (Cases 1 to 15)
# ==============================================================================


def test_adversarial_01_missing_required_junit_hash(acceptance):
    root, output = acceptance
    plan = json.loads((output / "plan.json").read_bytes())
    receipt = make_valid_receipt(plan, output=output, root=root)
    receipt["lanes"]["tests"].pop("junit_sha256", None)
    valid, reason = ci_execute.verify_local_receipt(
        receipt,
        plan,
        required_nodes=set(receipt["passed_nodes"]),
        root=root,
        receipt_path=output / "local-receipt.json",
    )
    assert not valid
    assert "invalid junit_sha256" in reason.lower()


def test_adversarial_02_missing_required_junit_file(acceptance):
    root, output = acceptance
    plan = json.loads((output / "plan.json").read_bytes())
    receipt = make_valid_receipt(plan, output=output, root=root)
    (output / "tests.xml").unlink(missing_ok=True)
    valid, reason = ci_execute.verify_local_receipt(
        receipt,
        plan,
        required_nodes=set(receipt["passed_nodes"]),
        root=root,
        receipt_path=output / "local-receipt.json",
    )
    assert not valid
    assert "does not exist or is unreadable" in reason.lower()


def test_adversarial_03_valid_syntax_incorrect_hash_value(acceptance):
    root, output = acceptance
    plan = json.loads((output / "plan.json").read_bytes())
    receipt = make_valid_receipt(plan, output=output, root=root)
    receipt["lanes"]["tests"]["junit_sha256"] = "0" * 64
    valid, reason = ci_execute.verify_local_receipt(
        receipt,
        plan,
        required_nodes=set(receipt["passed_nodes"]),
        root=root,
        receipt_path=output / "local-receipt.json",
    )
    assert not valid
    assert "digest mismatch" in reason.lower()


def test_adversarial_04_receipt_claims_nodes_absent_from_junit(acceptance):
    root, output = acceptance
    plan = json.loads((output / "plan.json").read_bytes())
    receipt = make_valid_receipt(plan, output=output, root=root)
    extra_node = "tests/unit/test_contracts.py::test_synthetic_extra"
    receipt["passed_nodes"].append(extra_node)
    receipt["passed_count"] = len(receipt["passed_nodes"])
    receipt["lanes"]["tests"]["passed_nodes"].append(extra_node)
    receipt["lanes"]["tests"]["passed_count"] = len(
        receipt["lanes"]["tests"]["passed_nodes"]
    )
    valid, reason = ci_execute.verify_local_receipt(
        receipt,
        plan,
        required_nodes=set(receipt["passed_nodes"]),
        root=root,
        receipt_path=output / "local-receipt.json",
    )
    assert not valid
    assert "does not match claimed passed_nodes" in reason.lower()


def test_adversarial_05_profile_and_junit_report_different_node_sets(acceptance):
    root, output = acceptance
    profile_path = output / "tests.json"
    profile = json.loads(profile_path.read_bytes())
    profile["junit"]["tests"][0]["nodeid"] = (
        "tests/unit/test_contracts.py::test_tampered"
    )
    profile_path.write_text(json.dumps(profile))
    with pytest.raises(
        ValueError, match="Profile JUnit tests do not match raw JUnit XML"
    ):
        ci_execute.create_receipt(output, root=root)


def test_adversarial_06_empty_hosted_test_ids(acceptance):
    root, output = acceptance
    receipt = ci_execute.create_receipt(output, root=root)
    (output / "local-receipt.json").write_text(json.dumps(receipt))
    ci_execute.gate(output / "plan.json", root)
    manifest_path = output / "validation-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["test_ids"] = []
    manifest_path.write_text(json.dumps(manifest))
    reconciled = ci_execute.reconcile_release(
        output / "local-receipt.json", manifest_path, root=root
    )
    assert reconciled["verdict"] == "release_rejected"
    assert "test_ids is empty or missing" in reconciled["reason"].lower()


def test_adversarial_07_hosted_manifest_duplicate_node_ids(acceptance):
    root, output = acceptance
    receipt = ci_execute.create_receipt(output, root=root)
    (output / "local-receipt.json").write_text(json.dumps(receipt))
    ci_execute.gate(output / "plan.json", root)
    manifest_path = output / "validation-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["test_ids"].append(manifest["test_ids"][0])
    manifest_path.write_text(json.dumps(manifest))
    reconciled = ci_execute.reconcile_release(
        output / "local-receipt.json", manifest_path, root=root
    )
    assert reconciled["verdict"] == "release_rejected"
    assert "duplicate node ids" in reconciled["reason"].lower()


def test_adversarial_08_hosted_manifest_missing_packaging_completion(acceptance):
    root, output = acceptance
    receipt = ci_execute.create_receipt(output, root=root)
    (output / "local-receipt.json").write_text(json.dumps(receipt))
    ci_execute.gate(output / "plan.json", root)
    manifest_path = output / "validation-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["test_ids"] = [
        t for t in manifest["test_ids"] if not t.startswith("tests/packaging/")
    ]
    manifest_path.write_text(json.dumps(manifest))
    reconciled = ci_execute.reconcile_release(
        output / "local-receipt.json", manifest_path, root=root
    )
    assert reconciled["verdict"] == "release_rejected"
    assert "without packaging completion" in reconciled["reason"].lower()


def test_adversarial_09_arbitrary_json_without_run_provenance(acceptance):
    root, output = acceptance
    receipt = ci_execute.create_receipt(output, root=root)
    (output / "local-receipt.json").write_text(json.dumps(receipt))
    ci_execute.gate(output / "plan.json", root)
    (output / "receipt-binding.json").unlink(missing_ok=True)
    (output / "run-verification.json").unlink(missing_ok=True)
    manifest_path = output / "validation-manifest.json"
    reconciled = ci_execute.reconcile_release(
        output / "local-receipt.json", manifest_path, root=root
    )
    assert reconciled["verdict"] == "release_rejected"
    assert "verifiable run provenance" in reconciled["reason"].lower()


def test_adversarial_10_receipt_refers_to_different_tree(acceptance):
    root, output = acceptance
    plan = json.loads((output / "plan.json").read_bytes())
    receipt = make_valid_receipt(plan, output=output, root=root)
    receipt["tree_sha"] = "0" * 40
    valid, reason = ci_execute.verify_local_receipt(
        receipt,
        plan,
        required_nodes=set(receipt["passed_nodes"]),
        root=root,
        receipt_path=output / "local-receipt.json",
    )
    assert not valid
    assert "tree sha mismatch" in reason.lower()


def test_adversarial_11_receipt_creator_rejects_development_plan(tmp_path):
    root = tmp_path / "repo"
    base, head = repository(root)
    plan = ci_plan.make_plan(context(root, base, head, mode="development"), root=root)
    output = tmp_path / "dev-result"
    write_results(output, plan, root)
    with pytest.raises(
        ValueError,
        match="create_receipt requires a completed Release mode plan with full acceptance",
    ):
        ci_execute.create_receipt(output, root=root)


def test_adversarial_12_incomplete_journal_rejected(acceptance):
    root, output = acceptance
    plan = json.loads((output / "plan.json").read_bytes())
    receipt = make_valid_receipt(plan, output=output, root=root)
    journal_path = output / "tests-journal.jsonl"
    journal_lines = [
        line for line in journal_path.read_text().splitlines() if '"finish"' not in line
    ]
    journal_path.write_text("\n".join(journal_lines) + "\n")
    receipt["lanes"]["tests"]["journal_sha256"] = hashlib.sha256(
        journal_path.read_bytes()
    ).hexdigest()
    valid, reason = ci_execute.verify_local_receipt(
        receipt,
        plan,
        required_nodes=set(receipt["passed_nodes"]),
        root=root,
        receipt_path=output / "local-receipt.json",
    )
    assert not valid
    assert "missing successful finish event" in reason.lower()


def test_adversarial_13_hidden_failure_or_skip_in_supporting_artifact(acceptance):
    root, output = acceptance
    plan = json.loads((output / "plan.json").read_bytes())
    receipt = make_valid_receipt(plan, output=output, root=root)
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="2" failures="1" errors="0" skipped="0">
    <testcase classname="tests.unit.test_contracts" name="test_synthetic" file="tests/unit/test_contracts.py" line="10"/>
    <testcase classname="tests.unit.test_contracts" name="test_hidden_fail" file="tests/unit/test_contracts.py" line="20">
      <failure message="assertion error">failed</failure>
    </testcase>
  </testsuite>
</testsuites>
"""
    xml_path = output / "tests.xml"
    xml_path.write_text(xml_content)
    receipt["lanes"]["tests"]["junit_sha256"] = hashlib.sha256(
        xml_path.read_bytes()
    ).hexdigest()
    valid, reason = ci_execute.verify_local_receipt(
        receipt,
        plan,
        required_nodes=set(receipt["passed_nodes"]),
        root=root,
        receipt_path=output / "local-receipt.json",
    )
    assert not valid
    assert "failed/error/skipped tests" in reason.lower()


def test_adversarial_14_successive_invocations_retain_independent_bundles(tmp_path):
    from scripts import ci_profile

    out_dir = tmp_path / "profiling"
    xml_tmp = tmp_path / "lane.xml"
    journal_tmp = tmp_path / "lane-journal.jsonl"

    cmd1 = [
        sys.executable,
        "-c",
        f'open({repr(str(xml_tmp))}, \'w\').write(\'<testsuites><testsuite name="t" tests="1"><testcase classname="c" name="t1"/></testsuite></testsuites>\'); open({repr(str(journal_tmp))}, \'w\').write(\'{{"event": "finish", "status": "completed", "exitstatus": 0}}\\n\')',
    ]
    args1 = argparse.Namespace(
        name="unit-tests",
        command=cmd1,
        output=out_dir,
        junit=xml_tmp,
        journal=journal_tmp,
        mode="release",
        workers=1,
        invocation_id="inv-001",
    )
    ci_profile.run(args1)

    cmd2 = [
        sys.executable,
        "-c",
        f'open({repr(str(xml_tmp))}, \'w\').write(\'<testsuites><testsuite name="t" tests="2"><testcase classname="c" name="t1"/><testcase classname="c" name="t2"/></testsuite></testsuites>\'); open({repr(str(journal_tmp))}, \'w\').write(\'{{"event": "finish", "status": "completed", "exitstatus": 0}}\\n\')',
    ]
    args2 = argparse.Namespace(
        name="unit-tests",
        command=cmd2,
        output=out_dir,
        junit=xml_tmp,
        journal=journal_tmp,
        mode="release",
        workers=1,
        invocation_id="inv-002",
    )
    ci_profile.run(args2)

    inv_dir = out_dir / "invocations"
    assert (inv_dir / "unit-tests-inv-001.json").is_file()
    assert (inv_dir / "unit-tests-inv-001.xml").is_file()
    assert (inv_dir / "unit-tests-inv-001-journal.jsonl").is_file()
    assert (inv_dir / "unit-tests-inv-002.json").is_file()
    assert (inv_dir / "unit-tests-inv-002.xml").is_file()
    assert (inv_dir / "unit-tests-inv-002-journal.jsonl").is_file()

    assert (inv_dir / "unit-tests-inv-001.xml").read_text() != (
        inv_dir / "unit-tests-inv-002.xml"
    ).read_text()


def test_adversarial_15_valid_complete_local_and_hosted_evidence_yields_positive_verdict(
    acceptance,
):
    root, output = acceptance
    plan = json.loads((output / "plan.json").read_bytes())
    ci_execute.create_receipt(output, root=root)
    ci_execute.gate(output / "plan.json", root)
    manifest_path = output / "validation-manifest.json"
    local_rec_path = output / "local-receipt.json"
    reconciled = ci_execute.reconcile_release(
        local_rec_path,
        manifest_path,
        root=root,
        run_verifier=lambda rid, b, h: (True, None),
    )
    assert reconciled["verdict"] == "product_release_passed"
    assert reconciled["acceptance_status"] == "product_release_passed"
    assert reconciled["acceptance_input_hash"] == plan["acceptance_input_hash"]


def test_adversarial_16_unauthenticated_run_verification_json_does_not_grant_tier3(
    acceptance,
):
    root, output = acceptance
    ci_execute.create_receipt(output, root=root)
    ci_execute.gate(output / "plan.json", root)
    # Write plaintext run-verification.json
    (output / "run-verification.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "conclusion": "success",
                "run_id": "10",
                "source": "unauthenticated",
            }
        )
    )
    manifest_path = output / "validation-manifest.json"
    local_rec_path = output / "local-receipt.json"
    # Without authoritative gh / run_verifier, plaintext file cannot grant Tier 3 attestation
    reconciled = ci_execute.reconcile_release(local_rec_path, manifest_path, root=root)
    assert reconciled["verdict"] == "validation_gap_reported"
    assert reconciled["acceptance_status"] == "validation_gap_reported"
    assert (
        "authoritative hosted run verification unavailable"
        in reconciled["reason"].lower()
    )


def test_adversarial_17_hosted_development_run_rejected_for_release(acceptance):
    root, output = acceptance
    ci_execute.create_receipt(output, root=root)
    ci_execute.gate(output / "plan.json", root)
    manifest_path = output / "validation-manifest.json"
    local_rec_path = output / "local-receipt.json"
    # Verifier reports run was triggered by development pull_request event
    reconciled = ci_execute.reconcile_release(
        local_rec_path,
        manifest_path,
        root=root,
        run_verifier=lambda rid, b, h: (
            False,
            "GitHub Actions run was triggered by pull_request, which does not execute full release qualification",
        ),
    )
    assert reconciled["verdict"] == "release_rejected"
    assert "does not execute full release qualification" in reconciled["reason"].lower()


def test_adversarial_18_stale_commit_or_input_hash_in_hosted_manifest_rejected(
    acceptance,
):
    root, output = acceptance
    ci_execute.create_receipt(output, root=root)
    ci_execute.gate(output / "plan.json", root)
    manifest_path = output / "validation-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["context"]["tested_sha"] = "0" * 40
    manifest["context"]["feature_sha"] = "0" * 40
    manifest_path.write_text(json.dumps(manifest))
    binding_path = output / "receipt-binding.json"
    binding = json.loads(binding_path.read_bytes())
    binding["head"] = "0" * 40
    binding["feature_sha"] = "0" * 40
    binding_path.write_text(json.dumps(binding))
    local_rec_path = output / "local-receipt.json"
    reconciled = ci_execute.reconcile_release(
        local_rec_path,
        manifest_path,
        root=root,
        run_verifier=lambda rid, b, h: (True, None),
    )
    assert reconciled["verdict"] == "release_rejected"
    assert "does not match active repository head" in reconciled["reason"].lower()


def test_adversarial_19_hosted_manifest_missing_acceptance_files_rejected(
    acceptance,
):
    root, output = acceptance
    ci_execute.create_receipt(output, root=root)
    ci_execute.gate(output / "plan.json", root)
    manifest_path = output / "validation-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["coverage"]["unexecuted_files"] = ["tests/unit/test_contracts.py"]
    manifest_path.write_text(json.dumps(manifest))
    local_rec_path = output / "local-receipt.json"
    reconciled = ci_execute.reconcile_release(
        local_rec_path,
        manifest_path,
        root=root,
        run_verifier=lambda rid, b, h: (True, None),
    )
    assert reconciled["verdict"] == "release_rejected"
    assert "unexecuted acceptance files" in reconciled["reason"].lower()


def test_adversarial_20_find_artifact_rejects_absolute_path_and_runner_artifacts(
    tmp_path,
):
    root = tmp_path / "repo"
    root.mkdir()
    artifacts_dir = root / "artifacts" / "ci-profile"
    artifacts_dir.mkdir(parents=True)
    runner_xml = artifacts_dir / "tests.xml"
    runner_xml.write_text("<testsuites/>")

    # Absolute path must be rejected
    res_abs = ci_execute.find_artifact(
        {"junit_file": str(runner_xml.resolve())},
        "junit_file",
        "junit_path",
        "tests.xml",
        tmp_path / "receipt.json",
        root,
    )
    assert res_abs is None

    # Reference attempting to resolve to artifacts/ci-profile must be rejected
    res_art = ci_execute.find_artifact(
        {"junit_file": "tests.xml"},
        "junit_file",
        "junit_path",
        "tests.xml",
        tmp_path / "receipt.json",
        root,
    )
    assert res_art is None


# ==============================================================================
# Section 7: Provider-Backed Evidence Boundary and CLI Exit Propagation
# ==============================================================================


def make_mock_provider_bundle(manifest, binding, output_dir):
    """Create a dictionary of artifact files representing provider-retrieved evidence."""
    files = {}
    manifest_bytes = json.dumps(manifest, indent=2).encode() + b"\n"
    binding_bytes = json.dumps(binding, indent=2).encode() + b"\n"
    files["validation-manifest.json"] = manifest_bytes
    files["receipt-binding.json"] = binding_bytes

    # Copy lane files from output_dir if present
    for fname in (
        "tests.json",
        "tests.xml",
        "tests-journal.jsonl",
        "packaging.json",
        "packaging.xml",
        "packaging-journal.jsonl",
    ):
        p = output_dir / fname
        if p.is_file():
            files[fname] = p.read_bytes()

    index = {
        fname: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for fname, data in files.items()
    }
    files["receipt-index.json"] = json.dumps(index, indent=2).encode() + b"\n"
    return files


def mock_gh_runner(
    run_view_data=None, download_files=None, log_text=None, fail_gh=False
):
    """Mock subprocess runner simulating the gh CLI."""

    def runner(cmd, capture_output=True, text=True, check=False):
        if fail_gh:
            return subprocess.CompletedProcess(
                cmd,
                returncode=1,
                stdout="",
                stderr="error: authentication token invalid",
            )
        if "view" in cmd and "--log" not in cmd:
            stdout = json.dumps(run_view_data or {})
            return subprocess.CompletedProcess(
                cmd, returncode=0, stdout=stdout, stderr=""
            )
        elif "download" in cmd:
            if download_files is not None:
                dest = Path(cmd[cmd.index("-D") + 1])
                for fname, fdata in download_files.items():
                    (dest / fname).write_bytes(
                        fdata if isinstance(fdata, bytes) else fdata.encode()
                    )
                return subprocess.CompletedProcess(
                    cmd, returncode=0, stdout="", stderr=""
                )
            return subprocess.CompletedProcess(
                cmd, returncode=1, stdout="", stderr="artifact not found"
            )
        elif "view" in cmd and "--log" in cmd:
            if log_text is not None:
                return subprocess.CompletedProcess(
                    cmd, returncode=0, stdout=log_text, stderr=""
                )
            return subprocess.CompletedProcess(
                cmd, returncode=1, stdout="", stderr="logs unavailable"
            )
        return subprocess.CompletedProcess(
            cmd, returncode=1, stdout="", stderr="unknown gh subcommand"
        )

    return runner


def test_adversarial_21_development_run_presented_as_release(acceptance):
    root, output = acceptance
    ci_execute.create_receipt(output, root=root)
    ci_execute.gate(output / "plan.json", root)
    manifest_path = output / "validation-manifest.json"
    local_rec_path = output / "local-receipt.json"

    # Case A: run was triggered by pull_request
    pr_view = {
        "status": "completed",
        "conclusion": "success",
        "workflowName": "tests",
        "headSha": json.loads(manifest_path.read_bytes())["context"]["tested_sha"],
        "event": "pull_request",
    }
    res_pr = ci_execute.reconcile_release(
        local_rec_path,
        manifest_path,
        root=root,
        gh_runner=mock_gh_runner(run_view_data=pr_view),
    )
    assert res_pr["verdict"] == "release_rejected"
    assert "does not execute full release qualification" in res_pr["reason"]

    # Case B: run was triggered by workflow_dispatch, but in development mode (test lanes skipped)
    wf_dev_view = {
        "status": "completed",
        "conclusion": "success",
        "workflowName": "tests",
        "headSha": json.loads(manifest_path.read_bytes())["context"]["tested_sha"],
        "event": "workflow_dispatch",
        "jobs": [
            {
                "name": "offline",
                "steps": [
                    {
                        "name": "Current catalog3 checks (offline)",
                        "conclusion": "skipped",
                    },
                    {
                        "name": "Installed wheel and sdist checks (offline, isolated parallel workers)",
                        "conclusion": "skipped",
                    },
                ],
            }
        ],
    }
    res_wf_dev = ci_execute.reconcile_release(
        local_rec_path,
        manifest_path,
        root=root,
        gh_runner=mock_gh_runner(run_view_data=wf_dev_view),
    )
    assert res_wf_dev["verdict"] == "release_rejected"
    assert "development mode" in res_wf_dev["reason"]


def test_adversarial_22_correct_run_id_with_substituted_local_manifest(acceptance):
    root, output = acceptance
    ci_execute.create_receipt(output, root=root)
    ci_execute.gate(output / "plan.json", root)
    manifest_path = output / "validation-manifest.json"
    local_rec_path = output / "local-receipt.json"

    manifest = json.loads(manifest_path.read_bytes())
    binding = json.loads((output / "receipt-binding.json").read_bytes())
    prov_bundle = make_mock_provider_bundle(manifest, binding, output)

    # Operator substitutes local manifest with different content / extra tests
    tampered_manifest = dict(manifest)
    tampered_manifest["test_ids"] = list(manifest["test_ids"]) + [
        "tests/unit/test_tampered.py::test_fake"
    ]
    manifest_path.write_text(json.dumps(tampered_manifest))

    view_data = {
        "status": "completed",
        "conclusion": "success",
        "workflowName": "tests",
        "headSha": manifest["context"]["tested_sha"],
        "event": "workflow_dispatch",
        "jobs": [
            {
                "name": "offline",
                "steps": [
                    {
                        "name": "Current catalog3 checks (offline)",
                        "conclusion": "success",
                    },
                    {
                        "name": "Installed wheel and sdist checks (offline, isolated parallel workers)",
                        "conclusion": "success",
                    },
                ],
            }
        ],
    }
    res = ci_execute.reconcile_release(
        local_rec_path,
        manifest_path,
        root=root,
        gh_runner=mock_gh_runner(run_view_data=view_data, download_files=prov_bundle),
    )
    assert res["verdict"] == "release_rejected"
    assert "does not match provider-retrieved artifact" in res["reason"]


def test_adversarial_23_correct_commit_wrong_workflow(acceptance):
    root, output = acceptance
    ci_execute.create_receipt(output, root=root)
    ci_execute.gate(output / "plan.json", root)
    manifest_path = output / "validation-manifest.json"
    local_rec_path = output / "local-receipt.json"
    manifest = json.loads(manifest_path.read_bytes())

    wrong_wf_view = {
        "status": "completed",
        "conclusion": "success",
        "workflowName": "lint",
        "headSha": manifest["context"]["tested_sha"],
        "event": "workflow_dispatch",
    }
    res = ci_execute.reconcile_release(
        local_rec_path,
        manifest_path,
        root=root,
        gh_runner=mock_gh_runner(run_view_data=wrong_wf_view),
    )
    assert res["verdict"] == "release_rejected"
    assert "belongs to unexpected workflow" in res["reason"]


def test_adversarial_24_wrong_run_attempt(acceptance):
    root, output = acceptance
    ci_execute.create_receipt(output, root=root)
    ci_execute.gate(output / "plan.json", root)
    manifest_path = output / "validation-manifest.json"
    local_rec_path = output / "local-receipt.json"

    manifest = json.loads(manifest_path.read_bytes())
    binding = json.loads((output / "receipt-binding.json").read_bytes())
    # Binding claims attempt 2
    binding["run_attempt"] = 2
    (output / "receipt-binding.json").write_text(json.dumps(binding))

    # Provider artifact bundle has attempt 1
    prov_binding = dict(binding)
    prov_binding["run_attempt"] = 1
    prov_bundle = make_mock_provider_bundle(manifest, prov_binding, output)

    view_data = {
        "status": "completed",
        "conclusion": "success",
        "workflowName": "tests",
        "headSha": manifest["context"]["tested_sha"],
        "event": "workflow_dispatch",
        "jobs": [
            {
                "name": "offline",
                "steps": [
                    {
                        "name": "Current catalog3 checks (offline)",
                        "conclusion": "success",
                    },
                    {
                        "name": "Installed wheel and sdist checks (offline, isolated parallel workers)",
                        "conclusion": "success",
                    },
                ],
            }
        ],
    }
    res = ci_execute.reconcile_release(
        local_rec_path,
        manifest_path,
        root=root,
        gh_runner=mock_gh_runner(run_view_data=view_data, download_files=prov_bundle),
    )
    assert res["verdict"] == "release_rejected"
    assert "run attempt mismatch" in res["reason"].lower()


def test_adversarial_25_missing_or_substituted_artifact(acceptance):
    root, output = acceptance
    ci_execute.create_receipt(output, root=root)
    ci_execute.gate(output / "plan.json", root)
    manifest_path = output / "validation-manifest.json"
    local_rec_path = output / "local-receipt.json"
    manifest = json.loads(manifest_path.read_bytes())

    view_data = {
        "status": "completed",
        "conclusion": "success",
        "workflowName": "tests",
        "headSha": manifest["context"]["tested_sha"],
        "event": "workflow_dispatch",
        "jobs": [
            {
                "name": "offline",
                "steps": [
                    {
                        "name": "Current catalog3 checks (offline)",
                        "conclusion": "success",
                    },
                    {
                        "name": "Installed wheel and sdist checks (offline, isolated parallel workers)",
                        "conclusion": "success",
                    },
                ],
            }
        ],
    }
    # download_files is None -> artifact download fails, no log text -> missing artifact
    res = ci_execute.reconcile_release(
        local_rec_path,
        manifest_path,
        root=root,
        gh_runner=mock_gh_runner(
            run_view_data=view_data, download_files=None, log_text=None
        ),
    )
    assert res["verdict"] == "release_rejected"
    assert (
        "missing or unretrievable provider validation artifact" in res["reason"].lower()
    )


def test_adversarial_26_self_generated_receipt_index_rejected_without_provider(
    acceptance,
):
    root, output = acceptance
    ci_execute.create_receipt(output, root=root)
    ci_execute.gate(output / "plan.json", root)
    manifest_path = output / "validation-manifest.json"
    local_rec_path = output / "local-receipt.json"
    manifest = json.loads(manifest_path.read_bytes())

    # Create synthetic self-generated receipt index locally
    index = {
        "validation-manifest.json": {
            "bytes": len(manifest_path.read_bytes()),
            "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        }
    }
    (output / "receipt-index.json").write_text(json.dumps(index))

    view_data = {
        "status": "completed",
        "conclusion": "success",
        "workflowName": "tests",
        "headSha": manifest["context"]["tested_sha"],
        "event": "workflow_dispatch",
        "jobs": [
            {
                "name": "offline",
                "steps": [
                    {
                        "name": "Current catalog3 checks (offline)",
                        "conclusion": "success",
                    },
                    {
                        "name": "Installed wheel and sdist checks (offline, isolated parallel workers)",
                        "conclusion": "success",
                    },
                ],
            }
        ],
    }
    # Provider has different artifact content
    prov_manifest = dict(manifest)
    prov_manifest["outcome"] = "passed"
    prov_binding = json.loads((output / "receipt-binding.json").read_bytes())
    prov_bundle = make_mock_provider_bundle(prov_manifest, prov_binding, output)
    prov_bundle["other.json"] = b"content"
    prov_bundle["receipt-index.json"] = json.dumps(
        {
            "other.json": {
                "bytes": len(b"content"),
                "sha256": hashlib.sha256(b"content").hexdigest(),
            }
        }
    ).encode()

    res = ci_execute.reconcile_release(
        local_rec_path,
        manifest_path,
        root=root,
        gh_runner=mock_gh_runner(run_view_data=view_data, download_files=prov_bundle),
    )
    assert res["verdict"] == "release_rejected"
    assert "does not match provider-retrieved artifact" in res["reason"]


def test_adversarial_27_mismatched_artifact_and_hosted_manifest(acceptance):
    root, output = acceptance
    ci_execute.create_receipt(output, root=root)
    ci_execute.gate(output / "plan.json", root)
    manifest_path = output / "validation-manifest.json"
    local_rec_path = output / "local-receipt.json"

    manifest = json.loads(manifest_path.read_bytes())
    binding = json.loads((output / "receipt-binding.json").read_bytes())

    # Provider artifact has different acceptance input hash
    prov_manifest = dict(manifest)
    prov_manifest["acceptance_input_hash"] = "0" * 64
    prov_bundle = make_mock_provider_bundle(prov_manifest, binding, output)

    view_data = {
        "status": "completed",
        "conclusion": "success",
        "workflowName": "tests",
        "headSha": manifest["context"]["tested_sha"],
        "event": "workflow_dispatch",
        "jobs": [
            {
                "name": "offline",
                "steps": [
                    {
                        "name": "Current catalog3 checks (offline)",
                        "conclusion": "success",
                    },
                    {
                        "name": "Installed wheel and sdist checks (offline, isolated parallel workers)",
                        "conclusion": "success",
                    },
                ],
            }
        ],
    }
    res = ci_execute.reconcile_release(
        local_rec_path,
        manifest_path,
        root=root,
        gh_runner=mock_gh_runner(run_view_data=view_data, download_files=prov_bundle),
    )
    assert res["verdict"] == "release_rejected"
    assert "does not match provider-retrieved artifact" in res["reason"]


def test_adversarial_28_missing_provider_backed_verification(acceptance):
    root, output = acceptance
    ci_execute.create_receipt(output, root=root)
    ci_execute.gate(output / "plan.json", root)
    manifest_path = output / "validation-manifest.json"
    local_rec_path = output / "local-receipt.json"

    # gh command fails
    res = ci_execute.reconcile_release(
        local_rec_path, manifest_path, root=root, gh_runner=mock_gh_runner(fail_gh=True)
    )
    assert res["verdict"] == "validation_gap_reported"
    assert res["acceptance_status"] == "validation_gap_reported"
    assert "authoritative hosted run verification unavailable" in res["reason"].lower()


def test_adversarial_29_genuine_provider_backed_release_artifact_passes(acceptance):
    root, output = acceptance
    ci_execute.create_receipt(output, root=root)
    ci_execute.gate(output / "plan.json", root)
    manifest_path = output / "validation-manifest.json"
    local_rec_path = output / "local-receipt.json"

    manifest = json.loads(manifest_path.read_bytes())
    binding = json.loads((output / "receipt-binding.json").read_bytes())
    prov_bundle = make_mock_provider_bundle(manifest, binding, output)

    view_data = {
        "status": "completed",
        "conclusion": "success",
        "workflowName": "tests",
        "headSha": manifest["context"]["tested_sha"],
        "event": "workflow_dispatch",
        "jobs": [
            {
                "name": "offline",
                "steps": [
                    {
                        "name": "Current catalog3 checks (offline)",
                        "conclusion": "success",
                    },
                    {
                        "name": "Installed wheel and sdist checks (offline, isolated parallel workers)",
                        "conclusion": "success",
                    },
                ],
            }
        ],
    }
    res = ci_execute.reconcile_release(
        local_rec_path,
        manifest_path,
        root=root,
        gh_runner=mock_gh_runner(run_view_data=view_data, download_files=prov_bundle),
    )
    assert res["verdict"] == "product_release_passed"
    assert res["acceptance_status"] == "product_release_passed"


def test_adversarial_30_job_log_receipt_bundle_fallback_and_extraction(acceptance):
    root, output = acceptance
    ci_execute.create_receipt(output, root=root)
    ci_execute.gate(output / "plan.json", root)
    manifest_path = output / "validation-manifest.json"
    local_rec_path = output / "local-receipt.json"

    manifest = json.loads(manifest_path.read_bytes())
    binding = json.loads((output / "receipt-binding.json").read_bytes())
    prov_bundle = make_mock_provider_bundle(manifest, binding, output)

    # Package files into zip for job log
    import base64
    import io
    import textwrap
    import zipfile

    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname, fdata in prov_bundle.items():
            zf.writestr(fname, fdata)
    zip_bytes = bio.getvalue()
    zip_digest = hashlib.sha256(zip_bytes).hexdigest()
    b64_data = base64.b64encode(zip_bytes).decode("ascii")

    log_lines = [
        "2026-10-12T07:32:12Z info: test step starting",
        f"2026-10-12T07:32:12Z CI_RECEIPTS_BEGIN_V1 {zip_digest} {len(zip_bytes)}",
    ]
    for chunk in textwrap.wrap(b64_data, 120):
        log_lines.append(f"2026-10-12T07:32:12Z CI_RECEIPTS_DATA_V1 {chunk}")
    log_lines.append(f"2026-10-12T07:32:12Z CI_RECEIPTS_END_V1 {zip_digest}")
    log_lines.append("2026-10-12T07:32:12Z info: complete")
    synthetic_log = "\n".join(log_lines) + "\n"

    view_data = {
        "status": "completed",
        "conclusion": "success",
        "workflowName": "tests",
        "headSha": manifest["context"]["tested_sha"],
        "event": "workflow_dispatch",
        "jobs": [
            {
                "name": "offline",
                "steps": [
                    {
                        "name": "Current catalog3 checks (offline)",
                        "conclusion": "success",
                    },
                    {
                        "name": "Installed wheel and sdist checks (offline, isolated parallel workers)",
                        "conclusion": "success",
                    },
                ],
            }
        ],
    }
    # download_files is None (simulating unavailable artifact), but log_text is provided
    res = ci_execute.reconcile_release(
        local_rec_path,
        manifest_path,
        root=root,
        gh_runner=mock_gh_runner(
            run_view_data=view_data, download_files=None, log_text=synthetic_log
        ),
    )
    assert res["verdict"] == "product_release_passed"
    assert res["acceptance_status"] == "product_release_passed"


def test_cli_exit_status_development_gate_zero(tmp_path):
    root = tmp_path / "repo"
    base, head = repository(root)
    plan = ci_plan.make_plan(context(root, base, head, mode="development"), root=root)
    output = tmp_path / "dev-result"
    write_results(output, plan, root)

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/ci_execute.py",
            "gate",
            "--plan",
            str(output / "plan.json"),
            "--root",
            str(root),
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0
    coverage = json.loads(proc.stdout)
    assert "executed" in coverage
    manifest = json.loads((output / "validation-manifest.json").read_bytes())
    assert manifest["outcome"] == "passed"
    assert manifest["acceptance_status"] == "development_checks_passed"


def test_cli_exit_status_rejected_release_gate_nonzero(acceptance):
    root, output = acceptance
    # Write corrupt local receipt to trigger release_rejected
    (output / "local-receipt.json").write_text(
        '{"schema_version": 1, "status": "failed", "exit_code": 1}\n'
    )

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/ci_execute.py",
            "gate",
            "--plan",
            str(output / "plan.json"),
            "--root",
            str(root),
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert proc.returncode == 1
    coverage = json.loads(proc.stdout)
    assert "executed" in coverage
    manifest = json.loads((output / "validation-manifest.json").read_bytes())
    assert manifest["outcome"] == "failed"
    assert manifest["acceptance_status"] == "release_rejected"


def test_cli_exit_status_reconcile_release(acceptance):
    root, output = acceptance
    ci_execute.create_receipt(output, root=root)
    ci_execute.gate(output / "plan.json", root)
    manifest_path = output / "validation-manifest.json"

    # Corrupt local receipt -> reconcile returns 1
    corrupt_rec = output / "corrupt-rec.json"
    corrupt_rec.write_text('{"schema_version": 1, "status": "failed"}\n')
    proc_rej = subprocess.run(
        [
            sys.executable,
            "scripts/ci_execute.py",
            "reconcile-release",
            "--local-receipt",
            str(corrupt_rec),
            "--hosted-manifest",
            str(manifest_path),
            "--root",
            str(root),
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert proc_rej.returncode == 1
    res_rej = json.loads(proc_rej.stdout)
    assert res_rej["verdict"] in ("release_rejected", "validation_gap_reported")


@pytest.mark.parametrize("documentation_status", ["verified", "not_verified"])
def test_complete_release_requires_documentation_conjunction_after_product_proofs(
    acceptance, monkeypatch, documentation_status
):
    from scripts import documentation_receipts, schema_inventory

    root, output = acceptance
    plan = json.loads((output / "plan.json").read_bytes())
    ci_execute.create_receipt(output, root=root)
    ci_execute.gate(output / "plan.json", root)
    actual_git = ci_plan.git

    def selected_checkout(repository, *args):
        if args == ("rev-parse", "HEAD"):
            return plan["context"]["tested_sha"].encode() + b"\n"
        return actual_git(repository, *args)

    # Synthetic product proof fixture; validate only the conjunction connection.
    # Real documentation tamper/provider controls are tested independently.
    monkeypatch.setattr(ci_plan, "git", selected_checkout)
    monkeypatch.setattr(schema_inventory, "introspect_all", lambda: {"synthetic": "IR"})
    seen = []

    def documentation_proof(*args, **kwargs):
        seen.append(args)
        return {"status": documentation_status}

    monkeypatch.setattr(
        documentation_receipts, "complete_documentation", documentation_proof
    )
    result = ci_execute.reconcile_release(
        output / "local-receipt.json",
        output / "validation-manifest.json",
        root=root,
        run_verifier=lambda *args: (True, None),
        documentation_local="synthetic-local",
        documentation_hosted="synthetic-hosted",
    )
    assert len(seen) == 1
    assert seen[0][2]["commit"] == plan["context"]["tested_sha"]
    assert result["full_acceptance"] == (documentation_status == "verified")
    assert result["verdict"] == (
        "complete_release_passed"
        if documentation_status == "verified"
        else "product_release_passed"
    )
