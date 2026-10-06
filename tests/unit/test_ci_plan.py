import copy
import json
import subprocess

import pytest

from scripts import ci_plan
from tests.support.ci_fixture import (
    commit,
    context,
    envelope,
    manifest,
    repository,
    write,
)


@pytest.fixture
def history(tmp_path):
    root = tmp_path / "repo"
    base, head = repository(root)
    prior_context = context(root, base, head)
    full = ci_plan.make_plan(prior_context, root=root)
    evidence = envelope(manifest(full))
    write(root, "docs/schema-hardening/p2-foundation.md", "# Updated report\n")
    current = context(root, base, commit(root, "report only"), "11")
    return root, current, evidence


def plan(history):
    root, current, evidence = history
    return ci_plan.make_plan(current, evidence, root=root)


def test_report_only_followup_reuses_cumulative_feature_inputs(history):
    result = plan(history)
    assert not result["full"] and not result["fallback_reasons"]
    assert {v["disposition"] for v in result["lanes"].values()} == {"reused"}
    assert {v["disposition"] for v in result["preparation"].values()} == {
        "not_applicable"
    }
    assert result["comparison_sha"] == history[1]["base_sha"]
    assert any("scripts/conversion/engine.py" in c["paths"] for c in result["changed"])
    assert result["lanes"]["p2"]["prior_run"] == "10"
    assert "reused" in ci_plan.explain(result)


def test_report_after_untested_code_is_not_a_shortcut(history):
    root, current, evidence = history
    write(root, "scripts/conversion/engine.py", "# Untested code\n")
    commit(root, "untested code")
    write(root, "docs/schema-hardening/p2-foundation.md", "# Report after code\n")
    current = context(root, current["base_sha"], commit(root, "report"), "12")
    result = ci_plan.make_plan(current, evidence, root=root)
    assert result["lanes"]["p2"]["disposition"] == "selected"
    assert result["lanes"]["minimum-p2"]["disposition"] == "selected"
    assert result["lanes"]["legacy"]["disposition"] == "reused"
    evidence["run"]["conclusion"] = "failure"
    assert ci_plan.make_plan(current, evidence, root=root)["full"]


@pytest.mark.parametrize(
    "path",
    [
        "docs/schema-hardening/target-schema.sql",
        "docs/schema-hardening/conversion-contract.json",
        "docs/schema-hardening/column-conversion.csv",
        "docs/schema-hardening/table-conversion.md",
        "scripts/conversion/engine.py",
        "scripts/conversion/source.py",
        "scripts/conversion/admission.py",
        "scripts/conversion/phase.py",
        "scripts/offline_convert.py",
    ],
)
def test_schema_and_p2_dependencies_select_constraints_on_both_runtimes(history, path):
    root, current, evidence = history
    write(root, path, "changed synthetic input\n")
    current = context(root, current["base_sha"], commit(root), "12")
    result = ci_plan.make_plan(current, evidence, root=root)
    for name in ("schema", "p2", "minimum-schema", "minimum-p2"):
        assert result["lanes"][name]["disposition"] == "selected"
    assert result["preparation"]["sqlite-binding"]["disposition"] == "selected"
    assert result["lanes"]["legacy"]["disposition"] == "reused"
    assert result["lanes"]["packaging"]["disposition"] == "reused"


@pytest.mark.parametrize(
    "path",
    [
        "tests/integration/test_conversion_source_admission.py",
        "tests/unit/test_conversion_phase.py",
        "tests/integration/test_p3a_operational_flow.py",
    ],
)
def test_p3a_test_collections_run_in_native_and_minimum_conversion_lanes(history, path):
    root, current, evidence = history
    write(root, path, "def test_synthetic(): pass\n# Changed P3A test\n")
    current = context(root, current["base_sha"], commit(root), "12")
    result = ci_plan.make_plan(current, evidence, root=root)
    for lane in ("p2", "minimum-p2"):
        assert path in result["lanes"][lane]["test_files"]
        assert result["lanes"][lane]["disposition"] == "selected"
        assert path in result["lanes"][lane]["triggering_paths"]
    assert result["lanes"]["schema"]["disposition"] == "selected"
    assert result["lanes"]["minimum-schema"]["disposition"] == "selected"
    assert result["lanes"]["legacy"]["disposition"] == "reused"
    assert path not in result["lanes"]["legacy"]["test_files"]
    assert result["preparation"]["sqlite-binding"]["disposition"] == "selected"


def test_p3a_handoff_prose_reuses_verified_effective_inputs(history):
    root, current, evidence = history
    write(root, "docs/schema-hardening/p3a-handoff.md", "# P3B handoff\n")
    current = context(root, current["base_sha"], commit(root), "12")
    result = ci_plan.make_plan(current, evidence, root=root)
    assert not result["full"] and not result["fallback_reasons"]
    assert {lane["disposition"] for lane in result["lanes"].values()} == {"reused"}
    assert result["always_checks"]["reports"]["disposition"] == "selected"


@pytest.mark.parametrize(
    "path",
    [
        "tests/conftest.py",
        "tests/support/cli.py",
        "tests/support/operational_source.py",
        "tests/support/conversion_worker.py",
        "uv.lock",
        "src/repo_catalog/example.py",
        ".github/workflows/tests.yml",
        "scripts/ci_dependencies.json",
        "scripts/ci_plan.py",
        "unrecognized.txt",
        "tests/integration/p3a_fixture.py",
        "scripts/p3a_unclassified.py",
    ],
)
def test_shared_runtime_lock_policy_and_unknown_inputs_widen_conservatively(
    history, path
):
    root, current, evidence = history
    if path == "scripts/ci_dependencies.json":
        rules = ci_plan.policy(root)
        rules["notes"]["common"] += " changed policy"
        write(root, path, json.dumps(rules))
    else:
        write(root, path, "changed input\n")
    current = context(root, current["base_sha"], commit(root), "12")
    result = ci_plan.make_plan(current, evidence, root=root)
    assert result["full"]


def test_leaf_ci_test_change_is_sequential_sized_and_not_legacy(history):
    root, current, evidence = history
    write(root, "tests/unit/test_ci_plan.py", "def test_changed(): pass\n")
    current = context(root, current["base_sha"], commit(root), "12")
    result = ci_plan.make_plan(current, evidence, root=root)
    assert result["lanes"]["ci"]["disposition"] == "selected"
    assert result["lanes"]["legacy"]["disposition"] == "reused"
    assert result["preparation"]["sqlite-binding"]["disposition"] == "not_applicable"
    assert result["preparation"]["wheelhouse"]["disposition"] == "not_applicable"


@pytest.mark.parametrize(
    "mutation",
    [
        "no-evidence",
        "truncated",
        "missing-base",
        "different-base",
        "force-push",
        "fork",
        "push",
        "manual",
        "full",
    ],
)
def test_unknown_history_context_and_full_override_never_reuse(history, mutation):
    root, current, evidence = history
    if mutation == "no-evidence":
        evidence = None
    elif mutation == "truncated":
        current["diff_complete"] = False
    elif mutation == "missing-base":
        current["base_sha"] = "f" * 40
    elif mutation == "different-base":
        current["base_sha"] = current["feature_sha"]
        current = context(root, current["base_sha"], current["feature_sha"], "12")
    elif mutation == "force-push":
        tree = (
            ci_plan.git(root, "rev-parse", current["feature_sha"] + "^{tree}")
            .decode()
            .strip()
        )
        head = (
            subprocess.check_output(
                [
                    "git",
                    "-C",
                    str(root),
                    "commit-tree",
                    tree,
                    "-p",
                    current["base_sha"],
                ],
                input=b"force push\n",
            )
            .decode()
            .strip()
        )
        current = context(root, current["base_sha"], head, "12")
    elif mutation == "fork":
        current["head_repository"] = "untrusted/fork"
    elif mutation == "push":
        current.update(event="push", before_sha=current["base_sha"])
    elif mutation == "manual":
        current["event"] = "workflow_dispatch"
    else:
        current["full"] = True
    assert ci_plan.make_plan(current, evidence, root=root)["full"]


@pytest.mark.parametrize(
    "mutation",
    ["runtime", "policy", "partial", "skipped", "nodeids", "input", "required"],
)
def test_mismatched_or_incomplete_acceptance_is_rejected(history, mutation):
    root, current, evidence = history
    record = copy.deepcopy(evidence["manifest"])
    if mutation == "runtime":
        record["runtime"]["abi"] = "wrong ABI"
    elif mutation == "policy":
        record["policy_hash"] = "f" * 64
    elif mutation == "partial":
        record["full_acceptance"] = False
    elif mutation == "skipped":
        record["lanes"]["p2"]["state"] = "skipped"
    elif mutation == "nodeids":
        record["lanes"]["p2"]["test_ids"] += record["lanes"]["p2"]["test_ids"]
    elif mutation == "input":
        record["lanes"]["p2"]["input_fingerprint"] = "f" * 64
    else:
        record["required_ids"].pop()
    assert ci_plan.make_plan(current, envelope(record), root=root)["full"]


def test_empty_changes_can_reuse_another_successful_run(history):
    root, _, evidence = history
    current = dict(evidence["manifest"]["context"], run_id="12")
    subprocess.run(
        ["git", "-C", str(root), "checkout", "--detach", current["tested_sha"]],
        check=True,
        capture_output=True,
    )
    assert not ci_plan.make_plan(current, evidence, root=root)["full"]


def test_nul_diff_rename_delete_unicode_and_shell_metacharacters():
    changed = ci_plan.parse_diff(
        b"R100\0old path\0new\n$(secret);name\0D\0deleted\0A\0\xe6\x96\xb0\0"
    )
    assert changed[0]["paths"] == ["old path", "new\n$(secret);name"]
    assert changed[1] == {"status": "D", "paths": ["deleted"]}
    assert changed[2]["paths"] == ["新"]
    for truncated in (b"M\0file", b"R100\0old\0", b"Q\0path\0"):
        with pytest.raises(ValueError):
            ci_plan.parse_diff(truncated)


def test_real_renames_and_deletions_do_not_disappear(history):
    root, current, evidence = history
    (root / "scripts/conversion/engine.py").rename(root / "scripts/conversion/new.py")
    (root / "docs/schema-hardening/target-schema.sql").unlink()
    current = context(root, current["base_sha"], commit(root), "12")
    result = ci_plan.make_plan(current, evidence, root=root)
    paths = {p for change in result["changed"] for p in change["paths"]}
    assert (
        "scripts/conversion/new.py" in paths and "scripts/conversion/engine.py" in paths
    )
    assert result["lanes"]["p2"]["disposition"] == "selected"


def test_policy_cannot_duplicate_groups_or_remove_minimum_members(history):
    root, _, _ = history
    rules = ci_plan.policy(root)
    rules["groups"]["ci"].append(rules["groups"]["p2"][0])
    write(root, "scripts/ci_dependencies.json", json.dumps(rules))
    with pytest.raises(ValueError, match="Duplicate"):
        ci_plan.policy(root)


@pytest.mark.parametrize(
    "path", ["tests/e2e/conftest.py", "tests/e2e/__init__.py", "tests/e2e/helper.py"]
)
def test_nested_configuration_and_unrecognized_helpers_never_look_like_leaf_tests(
    history, path
):
    root, current, evidence = history
    write(root, path, "# new shared setup\n")
    current = context(root, current["base_sha"], commit(root), "12")
    assert ci_plan.make_plan(current, evidence, root=root)["full"]


def test_policy_cannot_drop_fixed_minimum_lane(history):
    root, _, _ = history
    rules = ci_plan.policy(root)
    rules["minimum_schema"].pop()
    write(root, "scripts/ci_dependencies.json", json.dumps(rules))
    with pytest.raises(ValueError, match="may not disappear"):
        ci_plan.policy(root)


@pytest.mark.parametrize("path", sorted(ci_plan.MINIMUM_P2))
def test_policy_cannot_drop_preexisting_conversion_files(history, path):
    root, _, _ = history
    rules = ci_plan.policy(root)
    rules["groups"]["p2"].remove(path)
    write(root, "scripts/ci_dependencies.json", json.dumps(rules))
    with pytest.raises(ValueError, match="may not disappear"):
        ci_plan.policy(root)


def test_policy_accepts_additional_conversion_tests_without_shrinking_floor(history):
    root, _, _ = history
    rules = ci_plan.policy(root)
    rules["groups"]["p2"].append("tests/unit/test_future_conversion_phase.py")
    write(root, "scripts/ci_dependencies.json", json.dumps(rules))
    assert ci_plan.MINIMUM_P2 <= set(ci_plan.policy(root)["groups"]["p2"])


def test_required_baseline_prevents_removal_of_preexisting_coverage():
    baseline = json.loads(
        (ci_plan.ROOT / "scripts/ci_required_baseline.json").read_bytes()
    )
    assert len(baseline["required_ids"]) == 321 and len(baseline["minimum_ids"]) == 228
    with pytest.raises(ValueError, match="disappeared"):
        ci_plan.check_baseline(baseline["required_ids"][:-1], baseline["minimum_ids"])
    with pytest.raises(ValueError, match="disappeared"):
        ci_plan.check_baseline(baseline["required_ids"], baseline["minimum_ids"][:-1])


def test_deleted_mandatory_test_file_is_not_silently_deselected(history):
    root, current, evidence = history
    (root / "tests/integration/test_conversion_foundation.py").unlink()
    current = context(root, current["base_sha"], commit(root), "12")
    with pytest.raises(ValueError, match="missing"):
        ci_plan.make_plan(current, evidence, root=root)


@pytest.mark.parametrize("value", ["{", "[]", "null"])
def test_malformed_local_evidence_falls_back_to_execution(history, tmp_path, value):
    root, current, _ = history
    path = tmp_path / "bad-evidence.json"
    path.write_text(value)
    assert ci_plan.load_evidence(path) is None
    assert ci_plan.make_plan(current, ci_plan.load_evidence(path), root=root)["full"]


def test_dirty_or_mismatched_checkout_cannot_record_validation_evidence(history):
    root, current, evidence = history
    write(root, "src/repo_catalog/example.py", "# uncommitted\n")
    with pytest.raises(ValueError, match="Commit"):
        ci_plan.make_plan(current, evidence, root=root)
