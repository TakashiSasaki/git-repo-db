"""Disposable output-path counterexamples; never use destructive real targets."""

from pathlib import Path

import pytest

from tools import build_docs_site as builder


@pytest.fixture
def layout(tmp_path, monkeypatch):
    root = tmp_path / "repository"
    docs = root / "documentation"
    docs.mkdir(parents=True)
    for name in ("content", "schema", "overrides"):
        (docs / name).mkdir()
    adr = root / "docs/adr"
    adr.mkdir(parents=True)
    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(builder, "DOCS_ROOT", docs)
    monkeypatch.setattr(builder, "DOCS_SITE_DIR", docs / "content")
    monkeypatch.setattr(builder, "DOCS_SCHEMA_DIR", docs / "schema")
    monkeypatch.setattr(builder, "DOCS_ADR_DIR", adr)
    return root, docs


@pytest.mark.parametrize(
    "relative",
    [
        ".",
        ".git",
        "docs/adr",
        "src",
        "documentation/content",
        "documentation/.venv",
        "cache",
        "catalogs",
        "docs/implementation/evidence",
    ],
)
def test_unsafe_staging_refused_before_deletion(layout, relative):
    root, docs = layout
    target = root / relative
    target.mkdir(parents=True, exist_ok=True)
    sentinel = target / "unchanged.txt"
    sentinel.write_text("retain me")
    with pytest.raises(ValueError):
        builder.stage_documentation(target)
    assert sentinel.read_text() == "retain me"


def test_symlink_escape_refused_with_unchanged_sentinel(layout, tmp_path):
    root, docs = layout
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "unchanged.txt"
    sentinel.write_text("retain me")
    (docs / ".build").mkdir()
    (docs / ".build/staging").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        builder.stage_documentation(docs / ".build/staging/child")
    assert sentinel.read_text() == "retain me"


@pytest.mark.parametrize(
    "name", ["state.sqlite3", "state.db", "pyvenv.cfg", "uv.lock", "evidence"]
)
def test_protected_content_refused_in_otherwise_allowed_destination(layout, name):
    root, docs = layout
    target = docs / ".build/staging/preview"
    target.mkdir(parents=True)
    sentinel = target / name
    sentinel.write_text("retain me")
    with pytest.raises(ValueError):
        builder.stage_documentation(target)
    assert sentinel.read_text() == "retain me"


def test_symlink_source_refused_before_destination_cleanup(layout, tmp_path):
    root, docs = layout
    source = tmp_path / "private.txt"
    source.write_text("private sentinel")
    (docs / "content/exposed.txt").symlink_to(source)
    target = docs / ".build/staging/preview"
    target.mkdir(parents=True)
    marker = target / "keep.txt"
    marker.write_text("unchanged")
    with pytest.raises(ValueError):
        builder.stage_documentation(target)
    assert marker.read_text() == "unchanged"
    assert source.read_text() == "private sentinel"


def test_configured_and_cli_actual_output_paths_are_checked(layout):
    root, docs = layout
    config = docs / "mkdocs.yml"
    config.write_text(
        "site_name: fixture\ndocs_dir: .build/staging/site\nsite_dir: ../src\n"
    )
    with pytest.raises(ValueError):
        builder.validated_config(config, output_dir=docs / "site")
    config.write_text(
        "site_name: fixture\ndocs_dir: .build/staging/site\nsite_dir: site\n"
    )
    with pytest.raises(ValueError):
        builder.validated_config(config, output_dir=root / ".git")
    valid = builder.validated_config(config, output_dir=docs / ".build/output/preview")
    assert Path(valid["site_dir"]) == docs / ".build/output/preview"
    assert Path(valid["docs_dir"]) == docs / ".build/staging/site"


def test_catalog_header_refused_even_without_database_extension(layout):
    _, docs = layout
    target = docs / ".build/staging/preview"
    target.mkdir(parents=True)
    marker = target / "opaque-state"
    marker.write_bytes(b"SQLite format 3\x00" + b"synthetic sentinel")
    with pytest.raises(ValueError):
        builder.stage_documentation(target)
    assert marker.read_bytes().endswith(b"synthetic sentinel")


def test_documentation_pin_rejects_dirty_inputs_and_ignores_event_sha(
    layout, monkeypatch
):
    import subprocess

    root, docs = layout

    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args]).decode().strip()

    git("init", "-q")
    git("config", "user.name", "Synthetic documentation fixture")
    git("config", "user.email", "fixture@example.invalid")
    content = docs / "content/index.md"
    content.write_text("synthetic source")
    git("add", ".")
    git("commit", "-qm", "synthetic source")
    source = git("rev-parse", "HEAD")
    monkeypatch.setenv("GITHUB_SHA", "0" * 40)
    builder.verify_documentation_checkout(source)
    content.write_text("uncommitted edit")
    with pytest.raises(ValueError, match="differ from pinned"):
        builder.verify_documentation_checkout(source)
    assert content.read_text() == "uncommitted edit"
