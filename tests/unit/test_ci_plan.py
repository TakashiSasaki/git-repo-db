import json

import pytest

from scripts import ci_plan
from tests.support.ci_fixture import command, commit, context, repository, write


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
        "docs/schema-hardening/target-schema.sql",
        "docs/schema-hardening/current-schema.json",
        "docs/schema-hardening/column-conversion.csv",
        "docs/schema-hardening/table-conversion.md",
        "docs/validation/real-world/2026-10-06-public-git.json",
        "docs/validation/synthetic/2026-10-09-payload-cas.json",
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


@pytest.mark.parametrize("directory", ci_plan.REQUIRED_DIRS)
@pytest.mark.parametrize("rename", [False, True], ids=["add", "rename"])
@pytest.mark.parametrize(
    "filename", ["test_added_regression.py", "added_regression_test.py"]
)
def test_new_ordinary_tests_are_discovered_in_every_directory(
    history, directory, rename, filename
):
    root, _, head = history
    path = directory + "/nested/" + filename
    write(root, path, "def test_synthetic(): assert False\n")
    if rename:
        (root / "tests/unit/test_contracts.py").unlink()
    ctx = context(root, head, commit(root), event="push")
    for full in (False, True):
        plan = ci_plan.make_plan(dict(ctx, full=full), root=root)
        lane = "packaging" if directory == "tests/packaging" else "tests"
        assert path in plan["lanes"][lane]["test_files"]
        assert not plan["excluded_files"]
        assert path in ci_plan.current_acceptance_files(root)


def test_live_tests_remain_outside_ordinary_full_acceptance(history):
    plan = followup(
        history, "tests/live/test_opt_in.py", "def test_live(): assert False\n"
    )
    assert plan["full"]
    assert "tests/live/test_opt_in.py" not in plan["acceptance_files"]
    assert not plan["excluded_files"]


@pytest.mark.parametrize(
    "statement",
    [
        "from tests.unit.test_contracts import shared",
        "import tests.unit.test_contracts as helper",
        "from tests.unit import test_contracts",
        "from .test_contracts import shared",
        "from test_contracts import shared",
        "from tests.unit import *",
    ],
)
def test_changed_imported_test_helper_selects_its_consumers(history, statement):
    root, _, _ = history
    helper = "tests/unit/test_contracts.py"
    consumer = "tests/unit/test_consumer.py"
    write(root, helper, "shared = 1\ndef test_synthetic(): pass\n")
    write(root, consumer, statement + "\ndef test_synthetic(): pass\n")
    before = commit(root)
    write(root, helper, "renamed = 1\ndef test_synthetic(): pass\n")
    plan = ci_plan.make_plan(
        context(root, before, commit(root), event="push"), root=root
    )
    assert plan["full"]
    assert consumer in plan["lanes"]["tests"]["test_files"]
    assert "Imported test helper: " + helper in plan["fallback_reasons"]


def test_explicit_shared_test_rule_takes_precedence_over_leaf_selection(history):
    root, _, _ = history
    path = "tests/unit/test_contracts.py"
    rules = ci_plan.policy(root)
    rules["shared_inputs"].append(path)
    write(root, "scripts/ci_dependencies.json", json.dumps(rules))
    before = commit(root)
    write(root, path, "def test_synthetic(): pass\n# shared helper changed\n")
    plan = ci_plan.make_plan(
        context(root, before, commit(root), event="push"), root=root
    )
    assert plan["full"]


@pytest.mark.parametrize(
    "source",
    [
        "invalid python source\n",
        "import importlib\nhelper = importlib.import_module('tests.unit.test_contracts')\n",
        "from importlib import import_module as load\nhelper = load('tests.unit.test_contracts')\n",
    ],
)
def test_unresolved_test_dependencies_expand_conservatively(history, source):
    plan = followup(history, "tests/unit/test_contracts.py", source)
    assert plan["full"]
    assert plan["fallback_reasons"]


@pytest.mark.parametrize(
    "source",
    [
        "pytest_plugins = ['tests.unit.test_contracts']\n",
        "import importlib\nloader = importlib.import_module\nhelper = loader('tests.unit.test_contracts')\n",
        "loader = __import__\nhelper = loader('tests.unit.test_contracts')\n",
        "from builtins import __import__ as load\nhelper = load('tests.unit.test_contracts')\n",
    ],
)
def test_changed_helper_with_plugin_or_aliased_dynamic_consumer_is_not_a_leaf(
    history, source
):
    root, _, _ = history
    write(root, "tests/conftest.py", source)
    before = commit(root)
    plan = followup(
        (root, before, before),
        "tests/unit/test_contracts.py",
        "def test_synthetic(): pass\n# changed helper\n",
    )
    assert plan["full"]
    assert any(
        "Dynamic test dependency" in reason for reason in plan["fallback_reasons"]
    )


@pytest.mark.parametrize(
    "contract",
    ["docs/current-contract.md", "docs/validation/synthetic/current-contract.json"],
)
def test_explicit_executable_contract_wins_over_report_selection_and_fingerprint(
    history, contract
):
    root, _, _ = history
    rules = ci_plan.policy(root)
    rules["executable_inputs"].append(contract)
    write(root, "scripts/ci_dependencies.json", json.dumps(rules))
    write(root, contract, '{"contract":1}\n')
    before = commit(root)
    prior = ci_plan.make_plan(
        dict(context(root, before, before, event="push"), full=True), root=root
    )
    plan = followup((root, before, before), contract, '{"contract":2}\n')
    assert plan["full"]
    assert plan["acceptance_input_hash"] != prior["acceptance_input_hash"]


@pytest.mark.parametrize(
    "path",
    [
        "src/repo_catalog/example.py",
        "tests/support/helper.py",
        "scripts/ci_plan.py",
        "uv.lock",
        "src/repo_catalog/resources/catalog3.sql",
        "src/repo_catalog/resources/schemas/cli-v1.schema.json",
        "docs/schema-hardening/new-current-contract.json",
        "docs/new-runtime-contract.sql",
        "docs/new-runtime-contract.csv",
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


def test_acceptance_file_removal_conservatively_runs_remaining_tests(history):
    root, _, head = history
    (root / "tests/unit/test_contracts.py").unlink()
    ctx = context(root, head, commit(root), event="push")
    plan = ci_plan.make_plan(ctx, root=root)
    assert plan["full"]
    assert "tests/unit/test_contracts.py" not in plan["acceptance_files"]
    assert not plan["excluded_files"]


def test_policy_cannot_silently_omit_an_ordinary_test_directory(history):
    root, _, _ = history
    rules = ci_plan.policy(root)
    rules["acceptance_directories"].remove("tests/unit")
    write(root, "scripts/ci_dependencies.json", json.dumps(rules))
    with pytest.raises(ValueError, match="ordinary test directories"):
        ci_plan.policy(root)


def test_dirty_checkout_cannot_record_validation(history):
    root, base, head = history
    write(root, "README.md", "# Uncommitted\n")
    with pytest.raises(ValueError, match="Commit"):
        ci_plan.make_plan(context(root, base, head), root=root)


def synchronize_context(history):
    root, base, before = history
    write(root, "docs/schema-hardening/runtime-handoff.md", "# Final results\n")
    head = commit(root)
    return dict(context(root, base, head), action="synchronize", before_sha=before)


def test_pr_synchronize_prose_uses_before_to_actual_merge_without_fresh_runtime_claim(
    history,
):
    root, _, before = history
    plan = ci_plan.make_plan(synchronize_context(history), root=root)
    assert plan["comparison_sha"] == before
    assert plan["changed"] == [
        {"status": "A", "paths": ["docs/schema-hardening/runtime-handoff.md"]}
    ]
    assert not plan["full"]
    assert plan["unexecuted_files"] == plan["acceptance_files"]
    assert all(
        item["disposition"] == "not_applicable" for item in plan["lanes"].values()
    )
    assert all(
        item["disposition"] == "not_applicable" for item in plan["preparation"].values()
    )


@pytest.mark.parametrize("before", [None, 1, "short", "0" * 40, "f" * 40])
def test_pr_synchronize_missing_invalid_or_unavailable_before_requires_full(
    history, before
):
    root, _, _ = history
    ctx = dict(synchronize_context(history), before_sha=before)
    plan = ci_plan.make_plan(ctx, root=root)
    assert plan["full"]
    assert plan["comparison_sha"] is None
    assert plan["fallback_reasons"]


def test_pr_synchronize_nonancestor_before_requires_full(history):
    root, base, old_head = history
    command(root, "checkout", "--detach", base)
    write(root, "README.md", "# Force-pushed prose\n")
    head = commit(root)
    ctx = dict(context(root, base, head), action="synchronize", before_sha=old_head)
    plan = ci_plan.make_plan(ctx, root=root)
    assert plan["full"]
    assert any("not an ancestor" in reason for reason in plan["fallback_reasons"])


def test_pr_synchronize_wrong_effective_merge_parents_require_full(history):
    root, _, _ = history
    ctx = synchronize_context(history)
    ctx["tested_sha"] = ctx["feature_sha"]
    plan = ci_plan.make_plan(ctx, root=root)
    assert plan["full"]
    assert any("merge parents" in reason for reason in plan["fallback_reasons"])


def test_pr_synchronize_current_base_code_is_in_actual_merge_diff(history):
    root, base, before = history
    ctx = synchronize_context(history)
    feature = ctx["feature_sha"]
    command(root, "checkout", "--detach", base)
    write(root, "src/repo_catalog/base_only.py", "# Current base code\n")
    current_base = commit(root)
    actual_tree = command(
        root, "merge-tree", "--write-tree", current_base, feature
    ).splitlines()[0]
    tested = command(
        root,
        "commit-tree",
        actual_tree,
        "-p",
        current_base,
        "-p",
        feature,
        input=b"effective merge\n",
    )
    command(root, "checkout", "--detach", tested)
    ctx.update(base_sha=current_base, tested_sha=tested)
    plan = ci_plan.make_plan(ctx, root=root)
    assert plan["comparison_sha"] == before
    assert plan["full"]
    assert {path for change in plan["changed"] for path in change["paths"]} == {
        "docs/schema-hardening/runtime-handoff.md",
        "src/repo_catalog/base_only.py",
    }


def test_force_push_cannot_use_before_present_only_in_current_base(history):
    root, original_base, old_head = history
    command(root, "checkout", "--detach", original_base)
    write(root, "README.md", "# Replacement feature\n")
    feature = commit(root)
    actual_tree = command(
        root, "merge-tree", "--write-tree", old_head, feature
    ).splitlines()[0]
    tested = command(
        root,
        "commit-tree",
        actual_tree,
        "-p",
        old_head,
        "-p",
        feature,
        input=b"effective merge\n",
    )
    command(root, "checkout", "--detach", tested)
    ctx = dict(
        context(root, old_head, feature),
        action="synchronize",
        before_sha=old_head,
        tested_sha=tested,
    )
    plan = ci_plan.make_plan(ctx, root=root)
    assert plan["full"]
    assert any("not an ancestor" in reason for reason in plan["fallback_reasons"])


@pytest.mark.parametrize("action", [None, "opened", "reopened"])
def test_other_pr_actions_keep_cumulative_merge_base_selection(history, action):
    root, base, _ = history
    ctx = dict(synchronize_context(history), action=action)
    plan = ci_plan.make_plan(ctx, root=root)
    assert plan["comparison_sha"] == base
    assert plan["full"]


def test_github_context_retains_synchronize_action_and_before(tmp_path, monkeypatch):
    event_file = tmp_path / "event.json"
    event_file.write_text(
        json.dumps(
            {
                "action": "synchronize",
                "before": "a" * 40,
                "pull_request": {"head": {"sha": "b" * 40}, "base": {"sha": "c" * 40}},
            }
        )
    )
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setattr(ci_plan, "git", lambda *args: ("d" * 40 + "\n").encode())
    ctx = ci_plan.context_from_environment()
    assert ctx["action"] == "synchronize"
    assert ctx["before_sha"] == "a" * 40
    assert ctx["feature_sha"] == "b" * 40
    assert ctx["tested_sha"] == "d" * 40
