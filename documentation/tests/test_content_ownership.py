"""Protect explicit documentation classification, frozen evidence and guide links."""

import json
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
        "docs/implementation/access-a6-acceptance.json": "authored-live-acceptance-ledger",
        "docs/implementation/callsite-dependencies.json": "generated-callsite-audit-index",
        "docs/implementation/table-disposition.md": "generated-schema-disposition-report",
        "documentation/schema/README.md": "generated-presentation",
        "documentation/current-runtime-reference.md": "derived-milestone-guide",
    }.items():
        assert classify(path)["status"] == status
    assert "schema_viz.py" in classify("documentation/schema/README.md")["producer"]
    assert (
        "audit_access_acceptance.py"
        in classify("docs/implementation/access-a6-acceptance.json")["consumers"]
    )
    assert (
        "audit_callsite_dependencies.py"
        in classify("docs/implementation/callsite-dependencies.json")["producer"]
    )
    assert (
        "audit_implementation_boundary.py"
        in classify("docs/implementation/table-disposition.md")["producer"]
    )
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


@pytest.mark.parametrize("change", ["blob", "mode"])
def test_frozen_index_blob_and_mode_changes_are_refused(tmp_path, change):
    env = dict(os.environ, GIT_INDEX_FILE=str(tmp_path / "index"))
    subprocess.run(["git", "read-tree", "HEAD"], cwd=ROOT, env=env, check=True)
    path = "docs/implementation/evidence/access-a6-independent-20261018/baseline-index.json"
    reference = "HEAD:README.md" if change == "blob" else f"HEAD:{path}"
    blob = subprocess.check_output(
        ["git", "rev-parse", reference], cwd=ROOT, text=True
    ).strip()
    mode = "100644" if change == "blob" else "100755"
    subprocess.run(
        ["git", "update-index", "--cacheinfo", f"{mode},{blob},{path}"],
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
    assert "Frozen evidence changed" in result.stderr


def test_frozen_baseline_cannot_be_replaced(tmp_path, monkeypatch):
    data = inventory_content._manifest()
    data["frozen"]["docs/phase2/reviews/"] = "0" * 40
    manifest = tmp_path / "inventory.json"
    manifest.write_text(json.dumps(data))
    monkeypatch.setattr(inventory_content, "MANIFEST", manifest)
    with pytest.raises(ValueError, match="Frozen evidence baseline mismatch"):
        inventory_content.inventory()


def _temporary_frozen_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    paths = ["docs/implementation/evidence", "docs/phase2/reviews"]
    for directory in paths:
        target = repo / directory
        target.mkdir(parents=True)
        (target / "original.txt").write_text("preserved\n")
    subprocess.run(["git", "add", "docs"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "baseline",
        ],
        cwd=repo,
        check=True,
    )
    baseline = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    trees = {
        f"{directory}/": subprocess.check_output(
            ["git", "rev-parse", f"HEAD:{directory}"], cwd=repo, text=True
        ).strip()
        for directory in paths
    }
    manifest = tmp_path / "inventory.json"
    manifest.write_text(
        json.dumps({"baseline": baseline, "frozen": trees, "records": {}})
    )
    monkeypatch.setattr(inventory_content, "ROOT", repo)
    monkeypatch.setattr(inventory_content, "MANIFEST", manifest)
    monkeypatch.setattr(inventory_content, "FROZEN_BASELINE", baseline)
    monkeypatch.setattr(inventory_content, "FROZEN_TREES", trees)
    return repo, paths


def test_ignored_untracked_addition_to_frozen_evidence_is_refused(
    tmp_path, monkeypatch
):
    repo, paths = _temporary_frozen_repo(tmp_path, monkeypatch)
    exclude = repo / ".git/info/exclude"
    exclude.write_text("hidden.secret\n")
    (repo / paths[0] / "hidden.secret").write_text("not tracked\n")
    with pytest.raises(ValueError, match="Untracked frozen evidence"):
        inventory_content.inventory()


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
def test_hidden_flags_on_modified_frozen_evidence_are_refused(
    tmp_path, monkeypatch, flag
):
    repo, paths = _temporary_frozen_repo(tmp_path, monkeypatch)
    target = f"{paths[0]}/original.txt"
    subprocess.run(["git", "update-index", flag, "--", target], cwd=repo, check=True)
    (repo / target).write_text("modified\n")
    with pytest.raises(ValueError, match="Hidden index flag on frozen evidence"):
        inventory_content.inventory()
    # The checker must not clear either user-controlled flag or alter the bytes.
    tagged = subprocess.check_output(
        ["git", "ls-files", "-v", "--", target], cwd=repo, text=True
    )
    assert not tagged.startswith("H ")
    assert (repo / target).read_text() == "modified\n"
