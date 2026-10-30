"""Focused tests for Developer Documentation Site Builder and Publication Safety."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from tools.build_docs_site import (
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
    with tempfile.TemporaryDirectory(dir=staging_parent()) as td:
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
        assert "github.com/TakashiSasaki/git-repo-db/blob/" in adr1_text

        # 4. Development Guide
        assert not (staging_dir / "development").exists()
        assert (staging_dir / "design" / "index.html").is_file()

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
            commit = get_git_metadata()["commit_sha"]
            expected = f"https://github.com/TakashiSasaki/git-repo-db/blob/{commit}/documentation/schema/mermaid/{slug}.md"
            assert expected in slug_text
            subprocess.run(
                [
                    "git",
                    "cat-file",
                    "-e",
                    f"{commit}:documentation/schema/mermaid/{slug}.md",
                ],
                check=True,
                capture_output=True,
            )


def test_publication_safety_validator():
    """Publication safety validator permits allowed files and rejects dangerous/sensitive files."""
    with tempfile.TemporaryDirectory(dir=staging_parent()) as td:
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
    with tempfile.TemporaryDirectory(dir=staging_parent()) as td:
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
    with tempfile.TemporaryDirectory(dir=staging_parent()) as td:
        empty_dir = Path(td)
        missing = validate_critical_endpoints(empty_dir)
        assert len(missing) > 0
        assert any("index.html" in m for m in missing)
        assert any("schema/viewer/index.html" in m for m in missing)
        assert any("manifest.webmanifest" in m for m in missing)
        assert any("sw.js" in m for m in missing)


def _github_actions_glob_to_regex(pattern: str) -> re.Pattern:
    """Convert GitHub Actions path filter pattern to an equivalent compiled regex."""
    res = []
    i = 0
    n = len(pattern)
    while i < n:
        if pattern[i : i + 3] == "/**":
            res.append("(?:/.*)?")
            i += 3
        elif pattern[i : i + 2] == "**":
            res.append(".*")
            i += 2
        elif pattern[i] == "*":
            res.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            res.append("[^/]")
            i += 1
        elif pattern[i] in r"\.[]{}()+-^$|#":
            res.append("\\" + pattern[i])
            i += 1
        else:
            res.append(pattern[i])
            i += 1
    return re.compile("^" + "".join(res) + "$")


def _eval_github_workflow_trigger(
    patterns: list[str], changed_files: list[str]
) -> bool:
    """Evaluate whether changed files trigger a GitHub Actions workflow with path filtering."""
    compiled = [_github_actions_glob_to_regex(p) for p in patterns]
    for cf in changed_files:
        for c in compiled:
            if c.match(cf):
                return True
    return False


def test_pages_trigger_paths_decision_matrix():
    """Verify GitHub Pages workflow trigger path filter decision matrix against actual pages.yml."""
    pages_yml_path = (
        Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pages.yml"
    )
    assert pages_yml_path.is_file()
    cfg = yaml.safe_load(pages_yml_path.read_text(encoding="utf-8"))
    on_triggers = cfg.get("on") or cfg.get(True)
    assert on_triggers, "Missing 'on' section in pages.yml"

    push_paths = on_triggers["push"]["paths"]
    pr_paths = on_triggers["pull_request"]["paths"]
    assert push_paths == pr_paths, "push and pull_request paths should match"

    matrix_cases = [
        # (changed_files, expected_pages_build, description)
        (["documentation/content/index.md"], True, "Published site homepage"),
        (
            ["documentation/schema/mermaid/overview.md"],
            True,
            "Published schema Mermaid diagram",
        ),
        (
            ["docs/adr/0001-validation-lifecycle-architecture.md"],
            True,
            "Published ADR 0001",
        ),
        (
            ["docs/adr/0002-three-store-boundary-architecture.md"],
            True,
            "Published ADR 0002",
        ),
        (["documentation/overrides/main.html"], True, "MkDocs theme override"),
        (["documentation/mkdocs.yml"], True, "MkDocs config"),
        (["documentation/tools/build_docs_site.py"], True, "Docs build script"),
        (
            ["src/repo_catalog/resources/catalog3.sql"],
            True,
            "Relevant schema-generation input (Schema 21 DDL affecting site)",
        ),
        (
            ["docs/implementation/evidence/example.json"],
            False,
            "Internal implementation evidence",
        ),
        (
            ["docs/adr/0028-classified-times-and-sha256-exchange.md"],
            True,
            "Published accepted ADR 0028",
        ),
        (
            ["artifacts/ci-profile/journal.jsonl"],
            False,
            "Internal execution log only",
        ),
        (
            [
                "documentation/content/index.md",
                "docs/implementation/evidence/example.json",
            ],
            True,
            "Mixed site and internal-documentation changes",
        ),
        (
            ["src/repo_catalog/adapters/sqlite/p1_ddl/core.sql"],
            True,
            "Selected producer source includes opt-in P1-P7 target schema DDL not yet visualized on site",
        ),
        (
            ["src/repo_catalog/adapters/sqlite/p1_schema.py"],
            True,
            "Selected producer source includes opt-in P1-P7 target schema code not yet visualized on site",
        ),
    ]

    for changed_files, expected, desc in matrix_cases:
        actual = _eval_github_workflow_trigger(push_paths, changed_files)
        assert actual == expected, (
            f"Decision matrix mismatch for '{desc}': files={changed_files}, expected={expected}, actual={actual}"
        )


def test_pages_trigger_covers_executed_schema_dependencies():
    """A schema-check dependency change must trigger the complete Pages build."""
    root = Path(__file__).resolve().parents[2]
    probe = """
import json, runpy, sys
from pathlib import Path
root = Path.cwd()
sys.argv = ['scripts/schema_inventory.py', '--check']
try:
    runpy.run_path('scripts/schema_inventory.py', run_name='__main__')
except SystemExit as error:
    assert error.code in (None, 0)
loaded = sorted({
    Path(module.__file__).relative_to(root).as_posix()
    for module in tuple(sys.modules.values())
    if getattr(module, '__file__', None)
    and str(root / 'src/repo_catalog') in module.__file__
})
print('DEPENDENCIES=' + json.dumps(loaded))
"""
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    loaded = json.loads(result.stdout.split("DEPENDENCIES=", 1)[1])
    assert "src/repo_catalog/adapters/sqlite/git_intrinsic.py" in loaded
    cfg = yaml.safe_load((root / ".github/workflows/pages.yml").read_text())
    triggers = cfg.get("on") or cfg[True]
    for event in ("push", "pull_request"):
        missing = [
            path
            for path in loaded
            if not _eval_github_workflow_trigger(triggers[event]["paths"], [path])
        ]
        assert not missing, f"{event} misses executed schema dependencies: {missing}"


def staging_parent():
    from tools.build_docs_site import DOCS_ROOT

    parent = DOCS_ROOT / ".build" / "staging"
    parent.mkdir(parents=True, exist_ok=True)
    return parent


def test_link_scanner_ignores_script_text_but_checks_html_attributes(tmp_path):
    (tmp_path / "index.html").write_text("""<script>
      const template = `<a href="${route()}">dynamic link</a>`;
    </script><a href="missing.html">real missing link</a>""")
    errors = validate_internal_links(tmp_path)
    assert len(errors) == 1
    assert "missing.html" in errors[0]
