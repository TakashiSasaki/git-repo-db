import json

import pytest

from scripts import ci_plan
from tests.support.ci_fixture import commit, context, repository, write


@pytest.fixture
def history(tmp_path):
    root = tmp_path / "repo"
    base, head = repository(root)
    return root, base, head


def followup(history, path, text="changed\n", event="push"):
    root, _, head = history
    write(root, path, text)
    current = context(root, head, commit(root), event=event)
    return ci_plan.make_plan(current, root=root)


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        "docs/testing.md",
        "docs/schema-hardening/implementation-plan.md",
        "docs/ci-selection-results.json",
    ],
)
def test_main_prose_change_does_not_require_unconditional_acceptance(history, path):
    plan = followup(history, path, "# Updated prose\n")
    assert not plan["full"]
    assert all(
        item["disposition"] == "not_applicable" for item in plan["lanes"].values()
    )
    assert plan["unexecuted_files"] == plan["acceptance_files"]
    assert all(
        item["disposition"] == "not_applicable" for item in plan["preparation"].values()
    )


def test_leaf_test_change_collects_current_selected_file(history):
    path = "tests/integration/test_runtime_flow.py"
    plan = followup(history, path, "def test_synthetic(): pass\n# Changed\n")
    assert plan["lanes"]["tests"]["test_files"] == [path]
    assert not plan["full"]
    assert plan["lanes"]["packaging"]["disposition"] == "not_applicable"
    assert plan["preparation"]["wheelhouse"]["disposition"] == "not_applicable"
    assert len(plan["unexecuted_files"]) == 2


@pytest.mark.parametrize(
    "path",
    [
        "src/repo_catalog/example.py",
        "tests/support/helper.py",
        "scripts/ci_plan.py",
        "uv.lock",
        "docs/schema-hardening/target-schema.sql",
        "docs/schema-hardening/contract.json",
        "docs/schema-hardening/columns.csv",
        "docs/schema-hardening/table-conversion.md",
        "unknown.file",
    ],
)
def test_shared_executable_and_unknown_inputs_expand_to_current_acceptance(
    history, path
):
    result = followup(history, path)
    assert result["full"]
    assert not result["unexecuted_files"]
    assert result["fallback_reasons"]


def test_fresh_branch_without_comparison_is_conservative(history):
    root, base, head = history
    result = ci_plan.make_plan(context(root, base, head, event="local"), root=root)
    assert result["full"]


def test_manual_full_and_truncated_diff_expand(history):
    root, _, head = history
    write(root, "README.md", "# Changed\n")
    ctx = context(root, head, commit(root), event="push")
    for field in ("full", "diff_complete"):
        current = dict(ctx, **{field: field == "full"})
        assert ci_plan.make_plan(current, root=root)["full"]


def test_rename_and_delete_paths_remain_visible(history):
    root, _, head = history
    (root / "src/repo_catalog/example.py").rename(root / "src/repo_catalog/new.py")
    (root / "README.md").unlink()
    ctx = context(root, head, commit(root), event="push")
    plan = ci_plan.make_plan(ctx, root=root)
    paths = {path for row in plan["changed"] for path in row["paths"]}
    assert paths == {
        "src/repo_catalog/example.py",
        "src/repo_catalog/new.py",
        "README.md",
    }
    assert plan["full"]


def test_nul_diff_handles_unicode_shell_metacharacters_and_truncation():
    changed = ci_plan.parse_diff(
        b"R100\0old path\0new\n$(secret);name\0D\0deleted\0A\0\xe6\x96\xb0\0"
    )
    assert changed[0]["paths"] == ["old path", "new\n$(secret);name"]
    assert changed[2]["paths"] == ["新"]
    for truncated in (b"M\0file", b"R100\0old\0", b"Q\0path\0"):
        with pytest.raises(ValueError):
            ci_plan.parse_diff(truncated)


def test_acceptance_file_removal_requires_current_policy_update(history):
    root, _, head = history
    (root / "tests/unit/test_contracts.py").unlink()
    ctx = context(root, head, commit(root), event="push")
    with pytest.raises(ValueError, match="missing"):
        ci_plan.make_plan(ctx, root=root)
    rules = ci_plan.policy(root)
    rules["acceptance_files"].remove("tests/unit/test_contracts.py")
    write(root, "scripts/ci_dependencies.json", json.dumps(rules))
    ctx = context(root, head, commit(root), event="push")
    assert ci_plan.make_plan(ctx, root=root)["full"]


def test_duplicate_policy_members_are_rejected(history):
    root, _, _ = history
    rules = ci_plan.policy(root)
    rules["acceptance_files"].append(rules["acceptance_files"][0])
    write(root, "scripts/ci_dependencies.json", json.dumps(rules))
    with pytest.raises(ValueError, match="Duplicate"):
        ci_plan.policy(root)


def test_dirty_checkout_cannot_record_validation(history):
    root, base, head = history
    write(root, "README.md", "# Uncommitted\n")
    with pytest.raises(ValueError, match="Commit"):
        ci_plan.make_plan(context(root, base, head), root=root)
