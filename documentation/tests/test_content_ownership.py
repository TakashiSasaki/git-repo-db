"""Protect explicit documentation classification, frozen evidence and guide links."""

import os
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

import pytest

from tools import inventory_content
from tools.inventory_content import ROOT, classify, inventory


def test_inventory_has_exact_roles_and_rejects_unreviewed_paths():
    items = inventory()
    paths = [item["path"] for item in items]
    assert len(paths) == len(set(paths))
    assert all(item["status"] and item["owner"] for item in items)
    for path, status in {
        "docs/transport-independent-core-adr.md": "accepted-decision",
        "docs/phase2/no-independent-publication-adr.md": "accepted-decision",
        "docs/implementation/p1-schema-contracts.md": "active-scoped-contract",
        "docs/phase2/decision-register-before-no-publication.md": "superseded-decision-or-proposal-snapshot",
        "docs/phase2/field-contract.json": "machine-input-with-scoped-provenance",
        "documentation/schema/README.md": "generated-presentation",
        "documentation/current-runtime-reference.md": "derived-milestone-guide",
    }.items():
        assert classify(path)["status"] == status
    assert "schema_viz.py" in classify("documentation/schema/README.md")["producer"]
    assert not (ROOT / "docs/current-runtime-reference.md").exists()
    for path in (
        "docs/implementation/unreviewed-current-contract.md",
        "docs/phase2/unknown-decision.md",
        "documentation/content/unpublished-prose.md",
        "documentation/content/private.env",
        "documentation/schema/handwritten-policy.md",
        "docs/implementation/evidence/unreviewed.json",
    ):
        with pytest.raises(ValueError, match="Unclassified"):
            classify(path)


def test_historical_body_unchanged_and_navigation_retargeted():
    baseline = "5d28bb33bf62d7b0eff7e6547a4fda84c1815a9d"
    for path in (
        "docs/cli.md",
        "docs/data-model.md",
        "docs/implementation-status.md",
        "docs/model-integration-status.md",
    ):
        original = subprocess.check_output(
            ["git", "show", f"{baseline}:{path}"], cwd=ROOT
        )
        expected = original.replace(
            b"](current-runtime-reference.md)",
            b"](../documentation/current-runtime-reference.md)",
            1,
        )
        assert (ROOT / path).read_bytes() == expected


def test_current_guide_local_links_resolve():
    guide = ROOT / "documentation/current-runtime-reference.md"
    text = guide.read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)]+)\)", text):
        parsed = urlsplit(target)
        if parsed.scheme or not parsed.path:
            continue
        assert (guide.parent / unquote(parsed.path)).resolve().exists(), target


@pytest.mark.parametrize(
    "candidate",
    [
        "docs/implementation/unreviewed-current-contract.md",
        "documentation/content/unpublished-prose.md",
        "documentation/content/private.env",
        "documentation/schema/handwritten-policy.md",
        "docs/implementation/evidence/unreviewed.json",
    ],
)
def test_alternate_index_additions_are_not_silently_classified(tmp_path, candidate):
    env = dict(os.environ, GIT_INDEX_FILE=str(tmp_path / "index"))
    subprocess.run(["git", "read-tree", "HEAD"], cwd=ROOT, env=env, check=True)
    blob = subprocess.check_output(
        ["git", "rev-parse", "HEAD:README.md"], cwd=ROOT, text=True
    ).strip()
    subprocess.run(
        ["git", "update-index", "--add", "--cacheinfo", f"100644,{blob},{candidate}"],
        cwd=ROOT,
        env=env,
        check=True,
    )
    result = subprocess.run(
        [sys.executable, "documentation/tools/inventory_content.py"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "Unclassified tracked paths" in result.stderr


def test_unresolved_metadata_is_not_accepted(monkeypatch):
    data = inventory_content._manifest()
    data["records"]["docs/implementation/p1-schema-contracts.md"]["status"] = (
        "needs_assessment"
    )
    monkeypatch.setattr(inventory_content, "_manifest", lambda: data)
    with pytest.raises(ValueError, match="Unresolved inventory entry"):
        inventory_content.inventory()


def test_adr_status_evidence_must_match_source(monkeypatch):
    data = inventory_content._manifest()
    data["records"]["docs/adr/0001-validation-lifecycle-architecture.md"][
        "status_in_source"
    ] = "not declared in YAML; inspect the record"
    monkeypatch.setattr(inventory_content, "_manifest", lambda: data)
    with pytest.raises(ValueError, match="ADR status evidence mismatch"):
        inventory_content.inventory()
