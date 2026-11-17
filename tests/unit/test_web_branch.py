"""Cross-branch ownership and publication selection regressions."""

import ast
import json
import re
import subprocess
from pathlib import Path

import pytest

from scripts.check_web_boundary import check

ROOT = Path(__file__).resolve().parents[2]


def test_web_tracking_config_needs_no_product_commit():
    from scripts.documentation_receipts import verify_web_tracking_config

    verify_web_tracking_config(
        {
            "schema_version": 2,
            "repository": "https://github.com/TakashiSasaki/resource-atlas.git",
            "ref": "main",
        }
    )


@pytest.mark.parametrize("change", [{"ref": "web"}, {"commit": "0" * 40}])
def test_web_tracking_config_rejects_wrong_branch_or_maintained_pin(change):
    from scripts.documentation_receipts import (
        DocumentationGap,
        verify_web_tracking_config,
    )

    with pytest.raises(DocumentationGap, match="canonical main"):
        verify_web_tracking_config(
            {
                "schema_version": 2,
                "repository": "https://github.com/TakashiSasaki/resource-atlas.git",
                "ref": "main",
                **change,
            }
        )


def test_product_tree_has_no_editable_website():
    assert not check(ROOT)


def test_reintroduced_website_is_detected(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "website").mkdir()
    (tmp_path / "website/page.md").write_text("second authority")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    assert check(tmp_path) == ["website/page.md"]


def test_publication_selection_matches_canonical_index():
    policy = json.loads((ROOT / "docs/web-source-policy.json").read_text())
    body = (
        (ROOT / policy["canonical_index"])
        .read_text()
        .split("## Accepted Records\n", 1)[1]
        .split("## Proposed Records", 1)[0]
    )
    paths = {
        "docs/adr/" + p for p in re.findall(r"^\| \[[^\]]+\]\(([^)]+)\)", body, re.M)
    }
    import posixpath

    assert {posixpath.normpath(p) for p in paths} == set(policy["public_adrs"])
    assert len(policy["public_adrs"]) == len(set(policy["public_adrs"]))
    assert all(
        (ROOT / p).is_file() for p in [*policy["public_adrs"], *policy["support"]]
    )


def test_moved_ownership_obligations_are_explicit_and_retained():
    mapping = json.loads((ROOT / "docs/web-branch-test-map.json").read_text())
    for move in mapping["moves"]:
        tree = ast.parse((ROOT / move["new_path"]).read_text())
        current = {
            n.name
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
        }
        assert current == set(move["functions"])
        assert move["old_path"].startswith("website/tests/")
        assert move["new_path"].startswith("tests/unit/")


def test_moved_negative_controls_cannot_be_omitted_from_release_evidence():
    import pytest

    from scripts.documentation_receipts import (
        DocumentationGap,
        verify_moved_product_obligations,
    )

    mapping = {
        "main_nodes": [
            "tests/unit/test_content_ownership.py::negative[blob]",
            "tests/unit/test_content_ownership.py::negative[mode]",
        ]
    }
    with pytest.raises(DocumentationGap, match="obligations missing"):
        verify_moved_product_obligations(mapping, mapping["main_nodes"][:1])
    verify_moved_product_obligations(mapping, mapping["main_nodes"])


@pytest.mark.parametrize("name", ["README.md", "scripts/prepare_product.py"])
def test_web_root_instructions_are_checked_as_documentation(tmp_path, name):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "product-source.json").write_text("{}")
    page = tmp_path / "website/content/development/index.md"
    page.parent.mkdir(parents=True)
    page.write_text("Use the environment's Python-loaded SQLite.")
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "import subprocess\nsubprocess.run(['uv','pip','install','pysqlite3'])"
        if name.endswith(".py")
        else "```sh\nuv pip install pysqlite3\n```\n"
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    import sys

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/check_sqlite_validation_policy.py"),
            "--root",
            str(tmp_path),
            "--scope",
            "documentation",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert name + ":" in result.stdout and "sqlite-install" in result.stdout
