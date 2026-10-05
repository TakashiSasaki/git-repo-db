import json

import pytest

from scripts import ci_execute, ci_plan
from tests.support.ci_fixture import (
    commit,
    context,
    envelope,
    profile,
    repository,
    write,
    write_results,
)


@pytest.fixture
def acceptance(tmp_path):
    root = tmp_path / "repo"
    base, head = repository(root)
    result = ci_plan.make_plan(context(root, base, head), root=root)
    result["fixture_root"] = str(root)
    output = tmp_path / "result"
    write_results(output, result)
    return root, output


def test_full_gate_requires_exact_full_and_minimum_collection(acceptance):
    root, output = acceptance
    result = ci_execute.gate(output / "plan.json", root)
    assert result["full_acceptance"]
    assert result["coverage"]["fresh"] == result["coverage"]["required"]
    assert result["coverage"]["reused"] == 0
    assert result["coverage"]["minimum_fresh"] > 0
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
def test_final_gate_rejects_missing_failed_skipped_and_tampered_selected_outputs(
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
        (output / "sqlite-preparation.json").unlink()
    elif mutation == "changed-plan":
        plan = json.loads((output / "plan.json").read_bytes())
        plan["lanes"]["p2"]["disposition"] = "reused"
        (output / "plan.json").write_text(json.dumps(plan))
    elif mutation == "empty-collection":
        (output / "required-tests.txt").write_text("0 tests collected")
    elif mutation == "remove-selected-test":
        plan = json.loads((output / "plan.json").read_bytes())
        plan["lanes"]["p2"]["test_ids"].pop()
        (output / "plan.json").write_text(json.dumps(plan))
    else:
        (output / "reports.json").write_text("{}")
    if mutation in ("failed", "skipped", "duplicate", "extra", "wrong-runtime"):
        path.write_text(json.dumps(record))
    with pytest.raises((ValueError, FileNotFoundError)):
        ci_execute.gate(output / "plan.json", root)
    assert not (output / "validation-manifest.json").exists()


def test_report_followup_gate_proves_reuse_without_any_test_or_preparation(acceptance):
    root, full_output = acceptance
    full = ci_execute.gate(full_output / "plan.json", root)
    evidence = envelope(full)
    write(
        root, "docs/schema-hardening/p2-foundation.md", "# Meaningful report update\n"
    )
    current = context(root, full["context"]["base_sha"], commit(root), "11")
    plan = ci_plan.make_plan(current, evidence, root=root)
    output = full_output.parent / "report-only"
    output.mkdir()
    (output / "plan.json").write_text(json.dumps(plan))
    (output / "evidence.json").write_text(json.dumps(evidence))
    (output / "reports.json").write_text(json.dumps(ci_execute.reports(root)))
    for name in ("evidence-lookup", "planning", "report-validation"):
        (output / (name + ".json")).write_text(
            json.dumps(profile(current, plan["runtime"]))
        )
    result = ci_execute.gate(output / "plan.json", root)
    assert not result["full_acceptance"]
    assert result["coverage"]["fresh"] == 0
    assert result["coverage"]["reused"] == full["coverage"]["required"]
    assert result["coverage"]["minimum_reused"] == full["coverage"]["minimum_fresh"]
    assert set(result["command_wall_seconds"]) == {
        "evidence-lookup",
        "planning",
        "report-validation",
    }
    # A cache/evidence artifact cannot masquerade as fresh test output.
    (output / "tests.json").write_text(json.dumps({"exit_code": 0}))
    with pytest.raises(ValueError, match="Unexpected"):
        ci_execute.gate(output / "plan.json", root)


@pytest.mark.parametrize("count,workers", [(4, 1), (24, 4)])
def test_small_selections_are_sequential_and_larger_fixed_four(
    acceptance, monkeypatch, count, workers
):
    _, output = acceptance
    path = output / "plan.json"
    plan = json.loads(path.read_bytes())
    for item in plan["lanes"].values():
        item["disposition"] = "reused"
    plan["lanes"]["ci"].update(
        disposition="selected", test_ids=[f"synthetic::{i}" for i in range(count)]
    )
    path.write_text(json.dumps(plan))
    seen = []
    monkeypatch.setattr(
        ci_execute.ci_profile, "run", lambda args: seen.append(args) or 0
    )
    assert ci_execute.run_selection(path, "tests") == 0
    assert seen[0].workers == workers
    assert ("-n" in seen[0].command) == (workers == 4)
    assert seen[0].mode == ("xdist" if workers == 4 else "sequential")


def test_collection_rejects_duplicates_empty_missing_ids():
    for text in ("", "0 tests collected", "tests/unit/a.py::a\ntests/unit/a.py::a"):
        with pytest.raises(ValueError):
            ci_execute.collection_ids(text)


def test_reuse_requires_full_acceptance_not_an_unbounded_cache_chain(acceptance):
    root, output = acceptance
    full = ci_execute.gate(output / "plan.json", root)
    full["full_acceptance"] = False
    current = dict(full["context"], run_id="11")
    assert ci_plan.make_plan(current, envelope(full), root=root)["full"]


def test_workflow_preserves_check_and_conditions_every_expensive_step():
    workflow = (ci_plan.ROOT / ".github/workflows/tests.yml").read_text()
    assert "  offline:" in workflow and "pull_request_target" not in workflow
    assert "paths-ignore" not in workflow and "cancel-in-progress: true" in workflow
    assert "branches: [main]" in workflow and "fetch-depth: 0" in workflow
    assert "actions: read" in workflow and "contents: read" in workflow
    assert (
        "- name: Validate plan and all required outcomes\n        if: always()"
        in workflow
    )
    for name in (
        "dependencies",
        "wheelhouse",
        "normal",
        "packaging",
        "minimum",
        "demo",
        "build",
        "smoke",
        "static",
    ):
        assert f"steps.plan.outputs.{name} == 'true'" in workflow
    assert "steps.plan.outputs['sqlite-binding'] == 'true'" in workflow
    driver = (ci_plan.ROOT / "scripts/run_sqlite_minimum_tests.py").read_text()
    for path in ci_plan.policy()["minimum_schema"] + ci_plan.policy()["groups"]["p2"]:
        assert f'"{path}"' in driver


def test_report_json_rejects_nonfinite_values_and_nonobject(tmp_path):
    root = tmp_path / "repo"
    repository(root)
    for value in ('{"seconds":NaN}', "[]", "{}"):
        write(root, "docs/ci-performance-results.json", value)
        with pytest.raises(ValueError):
            ci_execute.reports(root)


@pytest.mark.parametrize("field", ["run_id", "run_attempt", "feature_sha"])
def test_stale_profile_from_another_execution_cannot_satisfy_selected_lane(
    acceptance, field
):
    root, output = acceptance
    path = output / "tests.json"
    record = json.loads(path.read_bytes())
    record["runtime"][field] = "wrong-execution"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="another run"):
        ci_execute.gate(output / "plan.json", root)


def test_binary_cache_claim_cannot_skip_cold_preparation(acceptance):
    root, output = acceptance
    path = output / "plan.json"
    plan = json.loads(path.read_bytes())
    plan["preparation"]["sqlite-binding"]["cache"] = "hit"
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="Plan changed"):
        ci_execute.gate(path, root)
