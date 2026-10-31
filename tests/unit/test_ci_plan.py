import json
import re

import pytest

from scripts import ci_plan
from tests.support.ci_fixture import command, commit, context, repository, write


@pytest.fixture
def history(tmp_path):
    root = tmp_path / "repo"
    base, head = repository(root)
    return root, base, head


def followup(history, path, text="changed\n", event="push", mode="development"):
    root, _, head = history
    write(root, path, text)
    current = context(root, head, commit(root), event=event, mode=mode)
    return ci_plan.make_plan(current, root=root)


def access_workflow_steps():
    workflow = (ci_plan.ROOT / ".github/workflows/access-registry.yml").read_text()
    # Inspect named steps without adding documentation's YAML dependency to
    # the product environment. Workflow syntax is validated separately.
    return {
        chunk.splitlines()[0]: chunk for chunk in workflow.split("      - name: ")[1:]
    }


@pytest.mark.parametrize("mode", ["development", "release"])
def test_access_runtime_and_packaging_follow_common_validation_mode(history, mode):
    plan = followup(history, "src/repo_catalog/adapters/sqlite/git_core.py", mode=mode)
    steps = access_workflow_steps()
    cohorts = {
        "tests": (
            "Execute broad regression suite and record receipts",
            "Reconcile regression manifest against baseline evidence",
            "Reconcile Access acceptance ledger and exact test nodes",
        ),
        "packaging": (
            "Installed I2 I3 I4 I5 on both distribution artifacts offline",
            "Verify wheel and sdist-derived wheel outside checkout",
        ),
    }
    for lane, names in cohorts.items():
        assert (plan["lanes"][lane]["disposition"] == "selected") is (mode == "release")
        for name in names:
            condition = re.search(r"^        if: (.+)$", steps[name], re.M)[1]
            assert condition == (
                "${{ !cancelled() && steps.plan.outputs." + lane + " == 'true' }}"
            )
    assert (
        "if: steps.plan.outputs.tests == 'true'"
        in steps["Verify scoped Access acceptance suite"]
    )
    assert plan["lanes"]["static"]["disposition"] == "selected"
    assert plan["lanes"]["smoke"]["disposition"] == "selected"
    if mode == "development":
        assert plan["unexecuted_files"] == plan["acceptance_files"]


def test_access_workflow_plans_before_preparation_and_retains_deferred_evidence():
    workflow = (ci_plan.ROOT / ".github/workflows/access-registry.yml").read_text()
    steps = access_workflow_steps()
    planning = steps["Plan checks with the common validation policy"]
    assert "id: plan" in planning
    assert (
        "run: python scripts/ci_plan.py --output artifacts/access-registry/ci-plan"
        in planning
    )
    assert workflow.index("id: plan") < workflow.index("uv sync --locked")
    assert "fetch-depth: 0" in workflow
    assert "  workflow_dispatch:\n" in workflow
    assert "        default: development" in workflow
    assert "CI_VALIDATION_MODE: ${{ github.event.inputs.mode || '' }}" in workflow
    for name, flag in (
        ("Install locked development dependencies", "dependencies"),
        ("Prepare locked wheels before offline installed acceptance", "wheelhouse"),
        ("Verify runtime environment preflight", "smoke"),
    ):
        assert f"if: steps.plan.outputs.{flag} == 'true'" in steps[name]
    assert "if: always()" in steps["Save focused verification evidence"]
    assert "artifacts/access-registry/" in steps["Save focused verification evidence"]


@pytest.mark.parametrize(
    "path",
    [
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
    # In development mode, leaf tests require local validation without hosted duplicate execution
    assert plan["required_files"] == [path]
    assert plan["selected_files"] == []
    assert plan["lanes"]["tests"]["test_files"] == []
    assert not plan["full"]
    assert plan["lanes"]["static"]["disposition"] == "selected"
    assert plan["lanes"]["packaging"]["disposition"] == "not_applicable"
    assert plan["preparation"]["wheelhouse"]["disposition"] == "not_applicable"
    assert path in plan["unexecuted_files"]

    # When explicit release mode is chosen, all acceptance files are selected
    rel_plan = followup(history, path, mode="release")
    assert rel_plan["full"]
    assert path in rel_plan["lanes"]["tests"]["test_files"]


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
        mode = "release" if full else "development"
        plan = ci_plan.make_plan(dict(ctx, full=full, mode=mode), root=root)
        lane = "packaging" if directory == "tests/packaging" else "tests"
        if full:
            assert path in plan["lanes"][lane]["test_files"]
        else:
            assert path in plan["required_files"]
            assert not plan["lanes"][lane]["test_files"]
        assert not plan["excluded_files"]
        assert path in ci_plan.current_acceptance_files(root)


def test_live_tests_remain_outside_ordinary_full_acceptance(history):
    plan = followup(
        history,
        "tests/live/test_opt_in.py",
        "def test_live(): assert False\n",
        mode="release",
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
    after = commit(root)
    dev_plan = ci_plan.make_plan(
        context(root, before, after, event="push", mode="development"), root=root
    )
    assert not dev_plan["full"]
    assert dev_plan["required_files"] == dev_plan["acceptance_files"]
    assert "Imported test helper: " + helper in dev_plan["fallback_reasons"]
    rel_plan = ci_plan.make_plan(
        context(root, before, after, event="push", mode="release"), root=root
    )
    assert rel_plan["full"]
    assert consumer in rel_plan["lanes"]["tests"]["test_files"]


def test_explicit_shared_test_rule_takes_precedence_over_leaf_selection(history):
    root, _, _ = history
    path = "tests/unit/test_contracts.py"
    rules = ci_plan.policy(root)
    rules["shared_inputs"].append(path)
    write(root, "scripts/ci_dependencies.json", json.dumps(rules))
    before = commit(root)
    write(root, path, "def test_synthetic(): pass\n# shared helper changed\n")
    after = commit(root)
    dev_plan = ci_plan.make_plan(
        context(root, before, after, event="push", mode="development"), root=root
    )
    assert not dev_plan["full"]
    assert dev_plan["required_files"] == dev_plan["acceptance_files"]
    rel_plan = ci_plan.make_plan(
        context(root, before, after, event="push", mode="release"), root=root
    )
    assert rel_plan["full"]


@pytest.mark.parametrize(
    "source",
    [
        "invalid python source\n",
        "import importlib\nhelper = importlib.import_module('tests.unit.test_contracts')\n",
        "from importlib import import_module as load\nhelper = load('tests.unit.test_contracts')\n",
    ],
)
def test_unresolved_test_dependencies_expand_conservatively(history, source):
    root, _, head = history
    write(root, "tests/unit/test_contracts.py", source)
    after = commit(root)
    plan = ci_plan.make_plan(
        context(root, head, after, event="push", mode="development"), root=root
    )
    assert not plan["full"]
    assert plan["required_files"] == plan["acceptance_files"]
    assert plan["fallback_reasons"]
    rel_plan = ci_plan.make_plan(
        context(root, head, after, event="push", mode="release"), root=root
    )
    assert rel_plan["full"]


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
    write(
        root,
        "tests/unit/test_contracts.py",
        "def test_synthetic(): pass\n# changed helper\n",
    )
    after = commit(root)
    plan = ci_plan.make_plan(
        context(root, before, after, event="push", mode="development"), root=root
    )
    assert not plan["full"]
    assert plan["required_files"] == plan["acceptance_files"]
    assert any(
        "Dynamic test dependency" in reason for reason in plan["fallback_reasons"]
    )
    rel_plan = ci_plan.make_plan(
        context(root, before, after, event="push", mode="release"), root=root
    )
    assert rel_plan["full"]


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
    write(root, contract, '{"contract":2}\n')
    after = commit(root)
    plan = ci_plan.make_plan(
        context(root, before, after, event="push", mode="development"), root=root
    )
    assert not plan["full"]
    assert plan["required_files"] == plan["acceptance_files"]
    assert plan["acceptance_input_hash"] != prior["acceptance_input_hash"]
    rel_plan = ci_plan.make_plan(
        context(root, before, after, event="push", mode="release"), root=root
    )
    assert rel_plan["full"]


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
    root, _, head = history
    write(root, path, "changed\n")
    after = commit(root)
    dev = ci_plan.make_plan(
        context(root, head, after, event="push", mode="development"), root=root
    )
    assert not dev["full"]
    assert dev["required_files"] == dev["acceptance_files"]
    assert dev["unexecuted_files"] == dev["acceptance_files"]
    assert dev["lanes"]["tests"]["disposition"] == "not_applicable"
    assert dev["lanes"]["static"]["disposition"] == "selected"
    assert dev["fallback_reasons"]
    rel = ci_plan.make_plan(
        context(root, head, after, event="push", mode="release"), root=root
    )
    assert rel["full"]
    assert not rel["unexecuted_files"]
    assert rel["fallback_reasons"]


def test_fresh_branch_without_comparison_is_conservative(history):
    root, base, head = history
    dev = ci_plan.make_plan(
        context(root, base, head, event="local", mode="development"), root=root
    )
    assert not dev["full"]
    assert dev["required_files"] == dev["acceptance_files"]
    rel = ci_plan.make_plan(
        context(root, base, head, event="local", mode="release"), root=root
    )
    assert rel["full"]


def test_manual_full_and_truncated_diff_expand(history):
    root, _, head = history
    write(root, "README.md", "# Changed\n")
    ctx = context(root, head, commit(root), event="push")
    assert ci_plan.make_plan(dict(ctx, full=True), root=root)["full"]
    trunc = ci_plan.make_plan(dict(ctx, diff_complete=False), root=root)
    assert trunc["required_files"] == trunc["acceptance_files"]
    assert not trunc["full"]


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
    assert not plan["full"]
    assert plan["required_files"] == plan["acceptance_files"]
    assert ci_plan.make_plan(dict(ctx, mode="release"), root=root)["full"]


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
    assert not plan["full"]
    assert plan["required_files"] == plan["acceptance_files"]
    assert "tests/unit/test_contracts.py" not in plan["acceptance_files"]
    assert not plan["excluded_files"]
    assert ci_plan.make_plan(dict(ctx, mode="release"), root=root)["full"]


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
    assert not plan["full"]
    assert plan["required_files"] == plan["acceptance_files"]
    assert plan["comparison_sha"] is None
    assert plan["fallback_reasons"]
    assert ci_plan.make_plan(dict(ctx, mode="release"), root=root)["full"]


def test_pr_synchronize_nonancestor_before_requires_full(history):
    root, base, old_head = history
    command(root, "checkout", "--detach", base)
    write(root, "README.md", "# Force-pushed prose\n")
    head = commit(root)
    ctx = dict(context(root, base, head), action="synchronize", before_sha=old_head)
    plan = ci_plan.make_plan(ctx, root=root)
    assert not plan["full"]
    assert plan["required_files"] == plan["acceptance_files"]
    assert any("not an ancestor" in reason for reason in plan["fallback_reasons"])
    assert ci_plan.make_plan(dict(ctx, mode="release"), root=root)["full"]


def test_pr_synchronize_wrong_effective_merge_parents_require_full(history):
    root, _, _ = history
    ctx = synchronize_context(history)
    ctx["tested_sha"] = ctx["feature_sha"]
    plan = ci_plan.make_plan(ctx, root=root)
    assert not plan["full"]
    assert plan["required_files"] == plan["acceptance_files"]
    assert any("merge parents" in reason for reason in plan["fallback_reasons"])
    assert ci_plan.make_plan(dict(ctx, mode="release"), root=root)["full"]


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
    assert not plan["full"]
    assert plan["required_files"] == plan["acceptance_files"]
    assert {path for change in plan["changed"] for path in change["paths"]} == {
        "docs/schema-hardening/runtime-handoff.md",
        "src/repo_catalog/base_only.py",
    }
    assert ci_plan.make_plan(dict(ctx, mode="release"), root=root)["full"]


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
    assert not plan["full"]
    assert plan["required_files"] == plan["acceptance_files"]
    assert any("not an ancestor" in reason for reason in plan["fallback_reasons"])
    assert ci_plan.make_plan(dict(ctx, mode="release"), root=root)["full"]


@pytest.mark.parametrize("action", [None, "opened", "reopened"])
def test_other_pr_actions_keep_cumulative_merge_base_selection(history, action):
    root, base, _ = history
    ctx = dict(synchronize_context(history), action=action)
    plan = ci_plan.make_plan(ctx, root=root)
    assert plan["comparison_sha"] == base
    assert not plan["full"]
    assert plan["required_files"] == plan["acceptance_files"]
    assert ci_plan.make_plan(dict(ctx, mode="release"), root=root)["full"]


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


@pytest.mark.parametrize("event_name", ["pull_request", "push"])
def test_normal_events_default_to_development_mode(tmp_path, monkeypatch, event_name):
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps({}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
    monkeypatch.setenv("GITHUB_EVENT_NAME", event_name)
    monkeypatch.delenv("CI_VALIDATION_MODE", raising=False)
    monkeypatch.setattr(ci_plan, "git", lambda *args: ("0" * 40 + "\n").encode())
    ctx = ci_plan.context_from_environment()
    assert ctx["mode"] == "development"
    assert ctx["full"] is False


def test_explicit_release_remains_release(tmp_path, monkeypatch):
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps({"inputs": {"mode": "release"}}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.delenv("CI_VALIDATION_MODE", raising=False)
    monkeypatch.setattr(ci_plan, "git", lambda *args: ("0" * 40 + "\n").encode())
    ctx = ci_plan.context_from_environment()
    assert ctx["mode"] == "release"
    assert ctx["full"] is True


@pytest.mark.parametrize(
    "invalid_mode", ["staging", "production", "invalid", "dev", "rel"]
)
def test_invalid_modes_are_rejected(tmp_path, monkeypatch, invalid_mode):
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps({"inputs": {"mode": invalid_mode}}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
    monkeypatch.delenv("CI_VALIDATION_MODE", raising=False)
    monkeypatch.setattr(ci_plan, "git", lambda *args: ("0" * 40 + "\n").encode())
    with pytest.raises(ValueError, match="Unsupported validation mode"):
        ci_plan.context_from_environment()


@pytest.mark.parametrize(
    "mode_val,full_val",
    [
        ("development", True),
        ("development", "true"),
        ("release", False),
    ],
)
def test_conflicting_mode_and_legacy_inputs_are_rejected(
    tmp_path, monkeypatch, mode_val, full_val
):
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps({"inputs": {"mode": mode_val, "full": full_val}}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
    monkeypatch.delenv("CI_VALIDATION_MODE", raising=False)
    monkeypatch.setattr(ci_plan, "git", lambda *args: ("0" * 40 + "\n").encode())
    with pytest.raises(ValueError, match="Contradictory inputs"):
        ci_plan.context_from_environment()


def test_workflow_dispatch_explicit_development_mode(tmp_path, monkeypatch):
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps({"inputs": {"mode": "development"}}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.delenv("CI_VALIDATION_MODE", raising=False)
    monkeypatch.setattr(ci_plan, "git", lambda *args: ("0" * 40 + "\n").encode())
    ctx = ci_plan.context_from_environment()
    assert ctx["mode"] == "development"
    assert ctx["full"] is False


def test_cli_rejects_conflicting_mode_and_full(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "argv", ["ci_plan.py", "--mode", "development", "--full"])
    with pytest.raises(ValueError, match="Contradictory options"):
        ci_plan.main()


def test_cli_accepts_consistent_mode_release_and_full(tmp_path, monkeypatch):
    import sys

    ctx_file = tmp_path / "context.json"
    ctx_file.write_text(
        json.dumps(
            {
                "tested_sha": "0" * 40,
                "base_sha": "0" * 40,
                "feature_sha": "0" * 40,
                "event": "push",
            }
        )
    )
    out_dir = tmp_path / "out"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ci_plan.py",
            "--context",
            str(ctx_file),
            "--output",
            str(out_dir),
            "--mode",
            "release",
            "--full",
        ],
    )
    called = []
    monkeypatch.setattr(
        ci_plan,
        "make_plan",
        lambda c, **kw: (
            called.append(c)
            or {
                "context": c,
                "full": True,
                "mode": "release",
                "lanes": {},
                "preparation": {},
                "unexecuted_files": [],
                "excluded_files": [],
                "fallback_reasons": [],
                "acceptance_input_hash": "h",
                "selection_wall_seconds": 0.1,
            }
        ),
    )
    monkeypatch.setattr(ci_plan, "write_plan", lambda p, o: None)
    ci_plan.main()
    assert called[0]["mode"] == "release"
    assert called[0]["full"] is True


def test_unknown_changed_input_does_not_trigger_full_hosted_testing_during_development(
    history,
):
    root, _, head = history
    write(root, "unknown_dir/unknown_file.txt", "unknown dependency\n")
    ctx = context(root, head, commit(root), event="push", mode="development")
    plan = ci_plan.make_plan(ctx, root=root)
    assert not plan["full"]
    # Unknown dependency path requires full local validation...
    assert plan["required_files"] == plan["acceptance_files"]
    assert any("Unknown dependency path" in r for r in plan["fallback_reasons"])
    # ...but DOES NOT escalate to full hosted testing during Development
    assert plan["selected_files"] == []
    assert plan["lanes"]["tests"]["test_files"] == []
    assert plan["lanes"]["tests"]["disposition"] == "not_applicable"
    assert plan["unexecuted_files"] == plan["acceptance_files"]
    assert plan["lanes"]["smoke"]["disposition"] == "selected"
    assert plan["lanes"]["static"]["disposition"] == "selected"


@pytest.mark.parametrize(
    "path,scope",
    [
        ("README.md", "prose"),
        ("pyproject.toml", "shared"),
        ("src/repo_catalog/new.json", "shared"),
        ("packages/core/src/repo_catalog/domain/core_query.py", "shared"),
        ("packages/contracts/src/repo_catalog/domain/shared_values.py", "shared"),
        ("packages/core/pyproject.toml", "shared"),
        ("packages/contracts/pyproject.toml", "shared"),
        ("tests/packaging/test_distribution.py", "leaf"),
        ("tests/packaging/test_sdist_hardening.py", "leaf"),
        ("scripts/check_sdist_contract.py", "shared"),
        ("scripts/verify_access_distribution.py", "shared"),
        ("scripts/verify_i4_distribution.py", "shared"),
        ("scripts/verify_i5_distribution.py", "shared"),
        ("tests/support/distributions.py", "shared"),
        (".github/workflows/tests.yml", "shared"),
        (".github/workflows/access-registry.yml", "shared"),
    ],
)
def test_distribution_inputs_select_lightweight_contract_without_pytest(
    history, path, scope
):
    root, _, head = history
    prior = ci_plan.make_plan(context(root, head, head, event="push"), root=root)
    plan = followup(history, path, "def test_synthetic(): pass\n# changed input\n")
    assert plan["preparation"]["sdist_contract"]["disposition"] == "selected"
    assert plan["preparation"]["dependencies"]["disposition"] == "selected"
    assert plan["preparation"]["wheelhouse"]["disposition"] == "not_applicable"
    assert not plan["selected_files"]
    assert not plan["full"]
    assert plan["lanes"]["tests"]["disposition"] == "not_applicable"
    assert plan["lanes"]["packaging"]["disposition"] == "not_applicable"
    assert plan["unexecuted_files"] == plan["acceptance_files"]
    if scope == "prose":
        # README belongs to the sdist source inventory, while the runtime
        # fingerprint and runtime-check selection still treat it as prose.
        assert plan["acceptance_input_hash"] == prior["acceptance_input_hash"]
        assert plan["required_files"] == []
        assert all(
            lane["disposition"] == "not_applicable" for lane in plan["lanes"].values()
        )
    else:
        assert plan["acceptance_input_hash"] != prior["acceptance_input_hash"]
        assert plan["lanes"]["static"]["disposition"] == "selected"
        if scope == "leaf":
            assert plan["required_files"] == [path]
            assert path in ci_plan.current_acceptance_files(root)
            release = ci_plan.make_plan(
                dict(plan["context"], mode="release", full=True), root=root
            )
            assert release["full"]
            assert path in release["lanes"]["packaging"]["test_files"]
        else:
            assert plan["required_files"] == plan["acceptance_files"]
            assert plan["lanes"]["smoke"]["disposition"] == "selected"
