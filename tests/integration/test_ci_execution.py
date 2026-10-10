import argparse
import json
import os
import subprocess
import sys

import pytest

from scripts import ci_execute, ci_plan
from tests.support.ci_fixture import commit, context, repository, write, write_results


@pytest.fixture
def acceptance(tmp_path):
    root = tmp_path / "repo"
    base, head = repository(root)
    plan = ci_plan.make_plan(context(root, base, head), root=root)
    output = tmp_path / "result"
    write_results(output, plan, root)
    return root, output


def test_full_current_acceptance_reports_exact_execution(acceptance):
    root, output = acceptance
    result = ci_execute.gate(output / "plan.json", root)
    assert result["full_acceptance"]
    assert result["acceptance_status"] == "full_acceptance_passed"
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
    assert result["acceptance_status"] == "selected_checks_only"
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
        ("tests", 24, None, 4),
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
    ctx = context(root, before, commit(root), event="push")
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
    assert result["acceptance_status"] == "selected_checks_only"
    assert result["acceptance_input_hash"] == prior["acceptance_input_hash"]
    assert result["coverage"]["unexecuted_files"] == prior["acceptance_files"]
    assert (
        "merge acceptance is not established"
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
