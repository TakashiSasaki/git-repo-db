import json

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


def test_prose_followup_reports_unexecuted_files_without_claiming_full_acceptance(
    acceptance,
):
    root, full_output = acceptance
    full = ci_execute.gate(full_output / "plan.json", root)
    head = full["context"]["feature_sha"]
    write(root, "README.md", "# Updated prose\n")
    current = context(root, head, commit(root), event="push")
    output = full_output.parent / "prose"
    write_results(output, ci_plan.make_plan(current, root=root), root)
    result = ci_execute.gate(output / "plan.json", root)
    assert not result["full_acceptance"]
    assert result["coverage"]["executed"] == 0
    assert len(result["coverage"]["unexecuted_files"]) == 3
    (output / "tests.json").write_text(json.dumps({"exit_code": 0}))
    with pytest.raises(ValueError, match="Unexpected"):
        ci_execute.gate(output / "plan.json", root)


@pytest.mark.parametrize("count,workers", [(4, 1), (24, 4)])
def test_small_selections_sequential_and_larger_fixed_four(
    acceptance, monkeypatch, count, workers
):
    _, output = acceptance
    path = output / "plan.json"
    plan = json.loads(path.read_bytes())
    plan["lanes"]["tests"]["test_ids"] = [f"synthetic::{i}" for i in range(count)]
    path.write_text(json.dumps(plan))
    seen = []
    monkeypatch.setattr(
        ci_execute.ci_profile, "run", lambda args: seen.append(args) or 0
    )
    assert ci_execute.run_selection(path, "tests") == 0
    assert seen[0].workers == workers
    assert ("-n" in seen[0].command) == (workers == 4)


def test_empty_and_duplicate_collection_are_rejected():
    for raw in ("", "0 tests collected", "tests/unit/a.py::a\ntests/unit/a.py::a"):
        with pytest.raises(ValueError):
            ci_execute.collection_ids(raw)


@pytest.mark.parametrize("value", ['{"seconds":NaN}', "[]", "{}"])
def test_historical_report_json_is_still_validated(tmp_path, value):
    root = tmp_path / "repo"
    repository(root)
    write(root, "docs/ci-performance-results.json", value)
    with pytest.raises(ValueError):
        ci_execute.reports(root)


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
