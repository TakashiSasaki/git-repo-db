"""Concrete source/collection fences for destructive legacy-code retirement."""

import copy
import subprocess
from collections import Counter

import pytest

from scripts.check_runtime_retirement import check


@pytest.fixture
def case(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    git("init", "-q")
    git("config", "user.name", "retirement fixture")
    git("config", "user.email", "fixture@example.invalid")
    tests = tmp_path / "tests"
    tests.mkdir()
    old = tests / "test_old.py"
    old.write_text("def test_old():\n    assert True\n")
    git("add", "tests")
    git("commit", "-qm", "baseline")
    baseline = git("rev-parse", "HEAD")
    node = "tests/test_old.py::test_old[value]"
    data = {
        "schema_version": 1,
        "baseline_commit": baseline,
        "retired_modules": ["src/obsolete.py"],
        "obligations": [
            {
                "legacy_node": node,
                "legacy_blob": git("rev-parse", "HEAD:tests/test_old.py"),
                "disposition": "pending",
                "replacement_nodes": [],
                "reason": "Preserve the original behavior until its exact replacement is reviewed.",
            }
        ],
    }
    return tmp_path, old, data


def test_pending_source_may_remain_but_cannot_be_removed_or_declared_complete(case):
    root, old, data = case
    assert check(data, root) == []
    assert any("pending" in message for message in check(data, root, complete=True))
    old.write_text("def test_unrelated():\n    assert True\n")
    assert any(
        "pending obligation cannot be retired" in message
        for message in check(data, root)
    )


def test_named_replacement_and_actual_parameter_collection_are_required(case):
    root, old, data = case
    replacement = root / "tests/test_new.py"
    replacement.write_text("def test_new():\n    assert True\n")
    record = data["obligations"][0]
    record.update(
        disposition="replaced", replacement_nodes=["tests/test_new.py::test_new[real]"]
    )
    old.unlink()
    assert check(data, root, complete=True) == []
    assert any(
        "not actually collected" in message
        for message in check(
            data, root, collected=Counter({"tests/test_new.py::test_new[other]": 1})
        )
    )
    assert (
        check(data, root, collected=Counter({"tests/test_new.py::test_new[real]": 1}))
        == []
    )
    replacement.unlink()
    assert any("replacement source missing" in message for message in check(data, root))


def test_baseline_blob_and_unique_original_nodes_are_not_optional(case):
    root, _, data = case
    wrong = copy.deepcopy(data)
    wrong["obligations"][0]["legacy_blob"] = "0" * 40
    assert any("baseline blob mismatch" in message for message in check(wrong, root))
    data["obligations"].append(copy.deepcopy(data["obligations"][0]))
    assert any("duplicate legacy node" in message for message in check(data, root))


def test_exclusion_requires_a_named_new_policy_control(case):
    root, old, data = case
    old.unlink()
    data["obligations"][0].update(
        disposition="excluded-by-adr", reason="ADR replaces this mechanism."
    )
    assert any("named replacement/control" in message for message in check(data, root))


def test_complete_retirement_requires_obsolete_module_removal(case):
    root, _, data = case
    data["obligations"][0].update(
        disposition="retained", replacement_nodes=["tests/test_old.py::test_old[value]"]
    )
    source = root / "src/obsolete.py"
    source.parent.mkdir()
    source.write_text("# old factory\n")
    assert any(
        "retired module remains" in message
        for message in check(data, root, complete=True)
    )
    source.unlink()
    assert check(data, root, complete=True) == []
    del data["retired_modules"]
    assert any(
        "explicit obsolete module" in message
        for message in check(data, root, complete=True)
    )


@pytest.mark.parametrize(
    "node", ["../outside.py::test_old", "::test_old", "/tmp/test_old.py::test_old"]
)
def test_malformed_or_escaping_node_paths_fail_cleanly(case, node):
    root, _, data = case
    data["obligations"][0]["legacy_node"] = node
    assert check(data, root)
