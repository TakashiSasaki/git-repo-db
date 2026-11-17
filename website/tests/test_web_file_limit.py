"""Keep the actual tracked import tree within the editor's stated limit."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(("count", "valid"), [(1000, True), (1001, False)])
def test_tracked_tree_import_limit(tmp_path, count, valid):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "product-source.json").write_text("{}")
    for index in range(count - 1):
        (tmp_path / f"asset-{index}.txt").touch()
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    result = subprocess.run(
        ["node", str(ROOT / "scripts/check_web_tree.mjs")],
        cwd=tmp_path,
        capture_output=True,
    )
    assert (result.returncode == 0) == valid


def test_canonical_product_sources_are_not_imported(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "product-source.json").write_text("{}")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/adr.md").write_text("second authority")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    result = subprocess.run(
        ["node", str(ROOT / "scripts/check_web_tree.mjs")],
        cwd=tmp_path,
        capture_output=True,
    )
    assert result.returncode != 0
