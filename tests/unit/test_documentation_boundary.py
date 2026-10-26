"""ADR0035 product isolation, policy coverage and conservative selection."""

import json
from pathlib import Path

import pytest

from scripts import check_sqlite_validation_policy as sqlite_policy
from scripts import ci_plan
from tests.support.ci_fixture import commit, context, repository, write


@pytest.mark.parametrize(
    "path",
    [
        "documentation/content/index.md",
        "documentation/mkdocs.yml",
        "documentation/uv.lock",
        "documentation/tools/schema_viz.py",
        ".github/workflows/pages.yml",
    ],
)
def test_classified_docs_changes_preserve_product_input_hash(tmp_path, path):
    root = tmp_path / "repo"
    _, head = repository(root)
    initial = ci_plan.make_plan(context(root, head, head, event="push"), root=root)
    write(root, path, "broken documentation fixture\n")
    current = commit(root)
    plan = ci_plan.make_plan(context(root, head, current, event="push"), root=root)
    assert plan["acceptance_input_hash"] == initial["acceptance_input_hash"]
    assert all(
        x["disposition"] == "not_applicable" for x in plan["preparation"].values()
    )
    assert all(x["disposition"] == "not_applicable" for x in plan["lanes"].values())


@pytest.mark.parametrize(
    "path",
    [
        "documentation/unknown-contract.json",
        "docs/implementation/machine-contract.json",
        "src/changed.sql",
        "uv.lock",
        "unknown.json",
    ],
)
def test_unknown_root_and_machine_inputs_remain_product_inputs(tmp_path, path):
    root = tmp_path / "repo"
    _, head = repository(root)
    write(root, path, "changed\n")
    current = commit(root)
    plan = ci_plan.make_plan(context(root, head, current, event="push"), root=root)
    assert plan["lanes"]["static"]["disposition"] == "selected"
    assert plan["fallback_reasons"]


def test_relocated_sqlite_policy_page_still_rejects_forbidden_instructions(tmp_path):
    path = "documentation/content/development/index.md"
    write(tmp_path, path, "```sh\nuv pip install pysqlite3\n```\n")
    assert sqlite_policy.scan(tmp_path, [path])
    (tmp_path / path).unlink()
    assert sqlite_policy.scan(tmp_path, [path])[0].rule == "missing-live-policy-input"


def test_product_configuration_has_no_docs_dependencies():
    import tomllib

    root = Path(__file__).resolve().parents[2]
    project = tomllib.loads((root / "pyproject.toml").read_text())
    assert "docs" not in project["dependency-groups"]
    assert not any("mkdocs" in x.lower() for x in project["project"]["dependencies"])
    assert "documentation" not in json.dumps(project.get("tool", {}).get("uv", {}))
