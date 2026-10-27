"""Protect the documentation ownership inventory and current-guide links."""

import re
from urllib.parse import unquote, urlsplit

import pytest

from tools.inventory_content import ROOT, classify, inventory


def test_inventory_has_one_owner_for_every_tracked_file():
    items = inventory()
    paths = [item["path"] for item in items]
    assert len(paths) == len(set(paths))
    assert all(item["role"] and item["owner"] for item in items)
    for path, role in {
        "docs/adr/0035-independent-documentation-workspace.md": "canonical-adr-and-governance",
        "docs/current-runtime-reference.md": "historical-link-pointer",
        "documentation/current-runtime-reference.md": "derived-current-guide",
        "documentation/tests/test_content_ownership.py": "documentation-test",
        "documentation/tools/inventory_content.py": "documentation-tool",
        "docs/phase2/field-contract.json": "machine-structured-artifact",
    }.items():
        assert next(item for item in items if item["path"] == path)["role"] == role
    with pytest.raises(ValueError, match="Unclassified"):
        classify("docs/not-reviewed-new-root.md")
    with pytest.raises(ValueError, match="Unclassified"):
        classify("documentation/new-section/example.md")


def test_current_guide_local_links_resolve():
    guide = ROOT / "documentation/current-runtime-reference.md"
    text = guide.read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)]+)\)", text):
        parsed = urlsplit(target)
        if parsed.scheme or not parsed.path:
            continue
        path = (guide.parent / unquote(parsed.path)).resolve()
        assert path.exists(), f"{target} does not resolve"
    assert (
        "../documentation/current-runtime-reference.md"
        in (ROOT / "docs/current-runtime-reference.md").read_text()
    )
