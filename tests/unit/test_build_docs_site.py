"""Focused tests for Developer Documentation Site Builder and Publication Safety."""

from __future__ import annotations

import tempfile
from pathlib import Path

from scripts.build_docs_site import (
    DOCS_SCHEMA_DIR,
    MERMAID_DIAGRAM_SLUGS,
    check_schema_freshness,
    get_git_metadata,
    stage_documentation,
    validate_critical_endpoints,
    validate_internal_links,
    validate_publication_safety,
)


def test_schema_freshness():
    """Committed schema visualization artifacts must match authoritative DDL."""
    check_schema_freshness()


def test_git_metadata():
    """Git commit SHA and tree SHA are retrieved and non-empty."""
    meta = get_git_metadata()
    assert "commit_sha" in meta and len(meta["commit_sha"]) >= 7
    assert "tree_sha" in meta and len(meta["tree_sha"]) >= 7
    assert "short_commit" in meta
    assert "short_tree" in meta


def test_staging_allowlist_and_transformation():
    """Staging includes only allowlisted content and resolves required transformations."""
    with tempfile.TemporaryDirectory() as td:
        staging_dir = Path(td)
        stage_documentation(staging_dir, skip_mermaid_render=True)

        # 0. PWA Assets
        assert (staging_dir / "manifest.webmanifest").is_file()
        assert (staging_dir / "manifest.json").is_file()
        assert (staging_dir / "sw.js").is_file()
        assert (staging_dir / "pwa.js").is_file()
        icons_dir = staging_dir / "assets" / "images" / "icons"
        assert (icons_dir / "icon.svg").is_file()
        assert (icons_dir / "icon-maskable.svg").is_file()
        assert (icons_dir / "icon-192.png").is_file()
        assert (icons_dir / "icon-512.png").is_file()
        assert (icons_dir / "icon-180.png").is_file()

        # 1. Homepage
        home_md = staging_dir / "index.md"
        assert home_md.is_file()
        content = home_md.read_text(encoding="utf-8")
        assert "git-repo-db" in content
        assert "Three-Store Boundary" in content
        assert "Schema 21" in content
        assert "ビルド・リビジョン情報" in content

        # 2. Architecture
        arch_dir = staging_dir / "architecture"
        assert (arch_dir / "index.md").is_file()
        assert (arch_dir / "three-store-boundary.md").is_file()
        arch_text = (arch_dir / "index.md").read_text(encoding="utf-8")
        assert "Core Schema 21" in arch_text
        assert "Operational Schema 1" in arch_text
        assert "Search Schema 1" in arch_text

        # 3. ADRs
        adr_dir = staging_dir / "adr"
        assert (adr_dir / "index.md").is_file()
        assert (adr_dir / "0001-validation-lifecycle-architecture.md").is_file()
        assert (adr_dir / "0002-three-store-boundary-architecture.md").is_file()
        # Verify repo links in ADR 0001 were transformed to GitHub links
        adr1_text = (adr_dir / "0001-validation-lifecycle-architecture.md").read_text(
            encoding="utf-8"
        )
        assert "../../AGENTS.md" not in adr1_text
        assert "github.com/TakashiSasaki/git-repo-db/blob/main/AGENTS.md" in adr1_text

        # 4. Development Guide
        assert (staging_dir / "development" / "index.md").is_file()

        # 5. Schema section
        schema_dir = staging_dir / "schema"
        assert (schema_dir / "index.md").is_file()
        schema_index = (schema_dir / "index.md").read_text(encoding="utf-8")
        for target in (
            "[インタラクティブビューアー](viewer/)",
            "[Mermaid ダイアグラム一覧](mermaid/)",
            "[Mermaid 全体俯瞰](mermaid/overview/)",
            "[DBML エクスポートガイド](dbml/)",
            "[core.dbml](dbml/core.dbml)",
        ):
            assert target in schema_index
            assert f"`{target}`" not in schema_index

        # 5.1 Standalone HTML viewer
        viewer_html = schema_dir / "viewer" / "index.html"
        assert viewer_html.is_file()
        viewer_text = viewer_html.read_text(encoding="utf-8")
        assert 'href="/manifest.webmanifest"' in viewer_text
        assert 'href="/assets/images/icons/icon.svg"' in viewer_text
        assert 'src="/pwa.js"' in viewer_text

        # 5.2 DBML files
        dbml_dir = schema_dir / "dbml"
        assert (dbml_dir / "index.md").is_file()
        for df in ["core.dbml", "operational.dbml", "search.dbml", "combined.dbml"]:
            assert (dbml_dir / df).is_file()
            assert (dbml_dir / df).read_bytes() == (
                DOCS_SCHEMA_DIR / "dbml" / df
            ).read_bytes()

        # 5.3 Mermaid Markdown files
        mermaid_dir = schema_dir / "mermaid"
        assert (mermaid_dir / "index.md").is_file()
        for slug in MERMAID_DIAGRAM_SLUGS:
            slug_md = mermaid_dir / f"{slug}.md"
            assert slug_md.is_file()
            slug_text = slug_md.read_text(encoding="utf-8")
            assert "mermaid-svg-container" in slug_text
            assert f"{slug}.svg" in slug_text
            assert "Mermaid 構文ソースコードを表示" in slug_text


def test_publication_safety_validator():
    """Publication safety validator permits allowed files and rejects dangerous/sensitive files."""
    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td)
        # Create valid assets
        (out_dir / "index.html").write_text("<html></html>", encoding="utf-8")
        (out_dir / "style.css").write_text("body {}", encoding="utf-8")
        (out_dir / "bundle.js").write_text("console.log();", encoding="utf-8")
        (out_dir / "diag.svg").write_text("<svg></svg>", encoding="utf-8")
        (out_dir / "schema.dbml").write_text("Table t {}", encoding="utf-8")
        (out_dir / "manifest.webmanifest").write_text(
            '{"name": "test"}', encoding="utf-8"
        )
        (out_dir / "sw.js").write_text(
            "self.addEventListener('fetch', () => {});", encoding="utf-8"
        )

        assert len(validate_publication_safety(out_dir)) == 0

        # Inject sensitive files
        (out_dir / "dump.sqlite3").write_bytes(b"SQLite format 3\0")
        (out_dir / "test.py").write_text("import os", encoding="utf-8")
        (out_dir / "deploy.sh").write_text("#!/bin/bash", encoding="utf-8")
        (out_dir / "server.key").write_text("KEY", encoding="utf-8")
        (out_dir / ".env.local").write_text("SECRET=1", encoding="utf-8")

        violations = validate_publication_safety(out_dir)
        assert len(violations) >= 5
        assert any(".sqlite3" in v for v in violations)
        assert any(".py" in v for v in violations)
        assert any(".sh" in v for v in violations)
        assert any(".key" in v for v in violations)
        assert any(".env" in v for v in violations)


def test_internal_links_validator():
    """Internal links validator correctly flags broken link targets."""
    with tempfile.TemporaryDirectory() as td:
        site_dir = Path(td)
        (site_dir / "index.html").write_text(
            '<a href="missing.html">Link</a>', encoding="utf-8"
        )
        broken = validate_internal_links(site_dir)
        assert len(broken) == 1
        assert "missing.html" in broken[0]

        # Fix link
        (site_dir / "missing.html").write_text("<html></html>", encoding="utf-8")
        broken = validate_internal_links(site_dir)
        assert len(broken) == 0


def test_critical_endpoints_validator():
    """Missing critical endpoint produces actionable violation."""
    with tempfile.TemporaryDirectory() as td:
        empty_dir = Path(td)
        missing = validate_critical_endpoints(empty_dir)
        assert len(missing) > 0
        assert any("index.html" in m for m in missing)
        assert any("schema/viewer/index.html" in m for m in missing)
        assert any("manifest.webmanifest" in m for m in missing)
        assert any("sw.js" in m for m in missing)
