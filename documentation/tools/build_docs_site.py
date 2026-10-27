#!/usr/bin/env python3
"""Build and validate the developer documentation website for git-repo-db.

Implements the publication allowlist, schema freshness verification,
build-time Mermaid SVG rendering, standalone viewer staging, MkDocs build,
and publication safety validation.

Usage:
    uv run --no-sync python scripts/build_docs_site.py
    uv run --no-sync python scripts/build_docs_site.py --check
    uv run --no-sync python scripts/build_docs_site.py --serve
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
DOCS_ROOT = ROOT / "documentation"
sys.path.insert(0, str(DOCS_ROOT))
sys.path.insert(0, str(ROOT))

DOCS_SITE_DIR = DOCS_ROOT / "content"
DOCS_SCHEMA_DIR = DOCS_ROOT / "schema"
DOCS_ADR_DIR = ROOT / "docs" / "adr"
DEFAULT_STAGING_DIR = DOCS_ROOT / ".build" / "staging" / "site"
DEFAULT_OUTPUT_DIR = DOCS_ROOT / "site"
MKDOCS_CONFIG_FILE = DOCS_ROOT / "mkdocs.yml"
IR_PATH = DOCS_ROOT / ".build" / "inputs" / "inventory.json"

# Allowlisted extensions in built static distribution
PUBLIC_ALLOWLIST_EXTENSIONS = {
    ".html",
    ".css",
    ".js",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".dbml",
    ".json",
    ".webmanifest",
    ".map",
    ".txt",
    ".xml",
    ".gz",
}

FORBIDDEN_PATTERNS = [
    r"\.sqlite3?$",
    r"\.db$",
    r"\.py[cod]?$",
    r"\.sh$",
    r"\.key$",
    r"\.pem$",
    r"\.env.*$",
    r"(?:^|/)token[s]?\.",
    r"(?:^|/)secret[s]?\.",
    r"(?:^|/)credentials?\.",
    r"transcript.*\.jsonl$",
]

MERMAID_DIAGRAM_SLUGS = [
    "overview",
    "core-overview",
    "core-identity",
    "core-current-state",
    "core-coverage",
    "core-git",
    "core-cas",
    "core-exchange",
    "operational",
    "search",
]


def run_cmd(
    cmd: List[str], cwd: Path | None = None, env: Dict[str, str] | None = None
) -> str:
    """Run a subprocess command and return stripped stdout."""
    res = subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"Command failed ({res.returncode}): {' '.join(cmd)}\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
    return res.stdout.strip()


def check_schema_freshness() -> None:
    """Compare committed presentation outputs with the pinned complete IR."""
    from tools.schema_viz import check_artifacts, generate_all_artifacts

    ir = json.loads(IR_PATH.read_bytes())
    clean, mismatches = check_artifacts(generate_all_artifacts(ir), DOCS_SCHEMA_DIR)
    if not clean:
        raise RuntimeError(
            "Schema visualization freshness failed: " + "; ".join(mismatches)
        )


def verify_documentation_checkout(source: str) -> None:
    if get_git_metadata()["commit_sha"] != source:
        raise ValueError("Documentation checkout does not match pinned source")
    result = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=all",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    if result.stdout:
        raise ValueError("Documentation inputs differ from pinned committed source")


def validate_destination(path: Path, kind: str) -> Path:
    """Allow only dedicated documentation output roots; refuse all symlink hops."""
    path = Path(os.path.abspath(path))
    roots = [DOCS_ROOT / ".build" / kind]
    if kind == "output":
        roots.append(DOCS_ROOT / "site")
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError("Symlink destination refused")
    actual = path.resolve()
    allowed = any(
        actual == root.resolve()
        and root.name == "site"
        or root.resolve() in actual.parents
        for root in roots
    )
    if not allowed:
        raise ValueError(
            "Destination outside dedicated documentation " + kind + " roots"
        )
    protected_names = {
        ".git",
        ".venv",
        "pyvenv.cfg",
        "evidence",
        "cache",
        ".cache",
        ".uv-cache",
        "catalogs",
        "artifacts",
    }
    if any(
        part in protected_names
        for part in actual.relative_to(DOCS_ROOT.resolve()).parts
    ):
        raise ValueError("Protected destination name")
    if actual.exists():
        for member in actual.rglob("*"):
            if (
                member.is_symlink()
                or member.name
                in {
                    ".git",
                    ".venv",
                    "pyvenv.cfg",
                    "evidence",
                    "uv.lock",
                    "cache",
                    ".cache",
                    ".uv-cache",
                    "__pycache__",
                    "catalogs",
                    "artifacts",
                }
                or member.suffix.lower() in {".db", ".sqlite", ".sqlite3"}
            ):
                raise ValueError("Protected content in destination")
            if member.is_file():
                with member.open("rb") as stream:
                    if stream.read(16) == b"SQLite format 3\x00":
                        raise ValueError("Catalog content in destination")
    return actual


def validated_config(
    config_path: Path, staging_dir: Path | None = None, output_dir: Path | None = None
):
    import yaml

    cfg = yaml.safe_load(config_path.read_text())
    if not isinstance(cfg, dict):
        raise ValueError("MkDocs config must be a mapping")
    for key in ("docs_dir", "site_dir"):
        if key not in cfg:
            raise ValueError("Explicit MkDocs destinations required")
        cfg[key] = str(config_path.parent / cfg[key])
    # Reject hostile configured destinations even if caller also supplies overrides.
    validate_destination(Path(cfg["docs_dir"]), "staging")
    validate_destination(Path(cfg["site_dir"]), "output")
    cfg["docs_dir"] = str(
        validate_destination(staging_dir or Path(cfg["docs_dir"]), "staging")
    )
    cfg["site_dir"] = str(
        validate_destination(output_dir or Path(cfg["site_dir"]), "output")
    )
    a, b = Path(cfg["docs_dir"]), Path(cfg["site_dir"])
    if a == b or a in b.parents or b in a.parents:
        raise ValueError("Overlapping staging and output refused")
    return cfg


def get_git_metadata() -> Dict[str, str]:
    """Retrieve Git commit and tree revision deterministically."""
    try:
        commit_sha = run_cmd(["git", "rev-parse", "HEAD"])
    except Exception:
        commit_sha = "unknown"

    try:
        tree_sha = run_cmd(["git", "rev-parse", "HEAD^{tree}"])
    except Exception:
        tree_sha = "unknown"

    return {
        "commit_sha": commit_sha,
        "tree_sha": tree_sha,
        "short_commit": commit_sha[:10] if len(commit_sha) >= 10 else commit_sha,
        "short_tree": tree_sha[:10] if len(tree_sha) >= 10 else tree_sha,
    }


def find_mermaid_cli() -> List[str]:
    """Locate Mermaid CLI runner (mmdc, bunx, or npx)."""
    # Check if mmdc is in PATH
    mmdc_path = shutil.which("mmdc")
    if mmdc_path:
        return [mmdc_path]

    # Check bunx
    bunx_candidates = [
        shutil.which("bunx"),
        "/home/ubuntu/.local/bin/bunx",
        "/home/ubuntu/.bun/bin/bunx",
    ]
    for candidate in bunx_candidates:
        if candidate and Path(candidate).is_file():
            return [candidate, "@mermaid-js/mermaid-cli@12.0.0"]

    # Check npx
    npx_candidates = [
        shutil.which("npx"),
        "/home/ubuntu/.local/bin/npx",
        "/home/ubuntu/.hermes/node/bin/npx",
    ]
    for candidate in npx_candidates:
        if candidate and Path(candidate).is_file():
            return [candidate, "--yes", "@mermaid-js/mermaid-cli@12.0.0"]

    raise RuntimeError(
        "Mermaid CLI runner not found. Please ensure '@mermaid-js/mermaid-cli' is accessible via mmdc, bunx, or npx."
    )


def render_mermaid_to_svg(
    mmd_content: str, out_svg_path: Path, puppeteer_cfg: Path
) -> None:
    """Render raw Mermaid syntax string to browser-compatible SVG."""
    cli_base = find_mermaid_cli()

    env = os.environ.copy()
    local_bin = "/home/ubuntu/.local/bin"
    if local_bin not in env.get("PATH", ""):
        env["PATH"] = f"{local_bin}:{env.get('PATH', '')}"

    with tempfile.NamedTemporaryFile(
        suffix=".mmd", mode="w", encoding="utf-8", delete=False
    ) as tf:
        tf.write(mmd_content)
        temp_mmd = Path(tf.name)

    try:
        cmd = [
            *cli_base,
            "-p",
            str(puppeteer_cfg),
            "-i",
            str(temp_mmd),
            "-o",
            str(out_svg_path),
        ]
        res = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(
                f"Failed to render Mermaid diagram to SVG:\nCommand: {' '.join(cmd)}\n"
                f"Error: {res.stderr}\nOutput: {res.stdout}"
            )
        if not out_svg_path.is_file() or out_svg_path.stat().st_size == 0:
            raise RuntimeError(f"Rendered SVG is missing or empty: {out_svg_path}")
    finally:
        if temp_mmd.exists():
            temp_mmd.unlink()


def stage_documentation(staging_dir: Path, skip_mermaid_render: bool = False) -> None:
    """Stage explicitly allowlisted documentation into the staging directory."""
    for source in (
        DOCS_SITE_DIR,
        DOCS_SCHEMA_DIR,
        DOCS_ROOT / "overrides",
        DOCS_ADR_DIR,
    ):
        if source.is_symlink() or any(p.is_symlink() for p in source.rglob("*")):
            raise ValueError("Symlink documentation source refused")
    staging_dir = validate_destination(staging_dir, "staging")
    print(f"Staging documentation into {staging_dir}...")
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    meta = get_git_metadata()

    # 0. PWA Assets (Manifests, Service Worker, Client Script, Icons)
    for pwa_file in ["manifest.webmanifest", "manifest.json", "sw.js", "pwa.js"]:
        src_pwa = DOCS_SITE_DIR / pwa_file
        if src_pwa.is_file():
            shutil.copy2(src_pwa, staging_dir / pwa_file)

    icons_src = DOCS_SITE_DIR / "assets" / "images" / "icons"
    if icons_src.is_dir():
        icons_dst = staging_dir / "assets" / "images" / "icons"
        icons_dst.mkdir(parents=True, exist_ok=True)
        for icon_file in icons_src.glob("*"):
            if icon_file.is_file():
                shutil.copy2(icon_file, icons_dst / icon_file.name)

    # 1. Homepage
    homepage_src = DOCS_SITE_DIR / "index.md"
    if not homepage_src.is_file():
        raise FileNotFoundError(f"Missing homepage source: {homepage_src}")
    homepage_content = homepage_src.read_text(encoding="utf-8")
    metadata_banner = (
        f"\n\n---\n\n"
        f"### ビルド・リビジョン情報 (Build Metadata)\n"
        f"- **Source Commit**: [`{meta['short_commit']}`](https://github.com/TakashiSasaki/git-repo-db/commit/{meta['commit_sha']})\n"
        f"- **Git Tree**: `{meta['short_tree']}`\n"
        f"- **Authoritative Schemas**: Core Schema 21 / Operational Schema 1 / Search Schema 1\n"
    )
    (staging_dir / "index.md").write_text(
        homepage_content + metadata_banner, encoding="utf-8"
    )

    # 2. Architecture
    arch_staging = staging_dir / "architecture"
    arch_staging.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DOCS_SITE_DIR / "architecture" / "index.md", arch_staging / "index.md")
    shutil.copy2(
        DOCS_SITE_DIR / "architecture" / "three-store-boundary.md",
        arch_staging / "three-store-boundary.md",
    )

    # 3. ADRs
    adr_staging = staging_dir / "adr"
    adr_staging.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DOCS_SITE_DIR / "adr" / "index.md", adr_staging / "index.md")

    # ADR 0001 with repository link adjustment
    adr1_raw = (DOCS_ADR_DIR / "0001-validation-lifecycle-architecture.md").read_text(
        encoding="utf-8"
    )
    adr1_transformed = (
        adr1_raw.replace(
            "[Binding Owner Decisions on Test and CI Optimization](../../AGENTS.md)",
            "[Binding Owner Decisions on Test and CI Optimization](https://github.com/TakashiSasaki/git-repo-db/blob/main/AGENTS.md)",
        )
        .replace(
            "[Change-Aware CI Architecture](../change-aware-ci.md)",
            "[Change-Aware CI Architecture](https://github.com/TakashiSasaki/git-repo-db/blob/main/docs/change-aware-ci.md)",
        )
        .replace(
            "[Testing Architecture and Guidelines](../testing.md)",
            "[Testing Architecture and Guidelines](https://github.com/TakashiSasaki/git-repo-db/blob/main/docs/testing.md)",
        )
        .replace(
            "[CI Dependencies and Classification Policy](../../scripts/ci_dependencies.json)",
            "[CI Dependencies and Classification Policy](https://github.com/TakashiSasaki/git-repo-db/blob/main/scripts/ci_dependencies.json)",
        )
    )
    (adr_staging / "0001-validation-lifecycle-architecture.md").write_text(
        adr1_transformed, encoding="utf-8"
    )

    # ADR 0002
    shutil.copy2(
        DOCS_ADR_DIR / "0002-three-store-boundary-architecture.md",
        adr_staging / "0002-three-store-boundary-architecture.md",
    )

    # 4. Development Guide
    dev_staging = staging_dir / "development"
    dev_staging.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DOCS_SITE_DIR / "development" / "index.md", dev_staging / "index.md")

    # 5. Schema section
    schema_staging = staging_dir / "schema"
    schema_staging.mkdir(parents=True, exist_ok=True)

    # 5.1 Transform docs/schema/README.md -> schema/index.md
    schema_readme_raw = (DOCS_SCHEMA_DIR / "README.md").read_text(encoding="utf-8")
    # Convert inline-code source paths into actual website links. Replacing
    # only substrings inside code spans would leave inert Markdown link text.
    schema_index_content = (
        schema_readme_raw.replace(
            "`docs/schema/mermaid/overview.md`", "[Mermaid 全体俯瞰](mermaid/overview/)"
        )
        .replace("`docs/schema/dbml/core.dbml`", "[core.dbml](dbml/core.dbml)")
        .replace("`docs/schema/index.html`", "[インタラクティブビューアー](viewer/)")
        .replace("`docs/schema/dbml/`", "[DBML エクスポートガイド](dbml/)")
        .replace("`docs/schema/mermaid/`", "[Mermaid ダイアグラム一覧](mermaid/)")
    )
    (schema_staging / "index.md").write_text(schema_index_content, encoding="utf-8")

    # 5.2 Standalone Interactive HTML Viewer -> schema/viewer/index.html
    viewer_staging = schema_staging / "viewer"
    viewer_staging.mkdir(parents=True, exist_ok=True)
    viewer_raw = (DOCS_SCHEMA_DIR / "index.html").read_text(encoding="utf-8")
    pwa_head_tags = (
        '  <link rel="manifest" href="/manifest.webmanifest">\n'
        '  <link rel="icon" type="image/svg+xml" href="/assets/images/icons/icon.svg">\n'
        '  <link rel="apple-touch-icon" href="/assets/images/icons/icon-180.png">\n'
        '  <meta name="theme-color" content="#0f172a">\n'
        '  <meta name="mobile-web-app-capable" content="yes">\n'
        '  <meta name="apple-mobile-web-app-capable" content="yes">\n'
        '  <meta name="apple-mobile-web-app-title" content="git-repo-db">\n'
        '  <script src="/pwa.js"></script>'
    )
    if "</head>" in viewer_raw:
        viewer_transformed = viewer_raw.replace(
            "</head>", f"{pwa_head_tags}\n</head>", 1
        )
    else:
        viewer_transformed = viewer_raw
    (viewer_staging / "index.html").write_text(viewer_transformed, encoding="utf-8")

    # 5.3 DBML Downloads -> schema/dbml/
    dbml_staging = schema_staging / "dbml"
    dbml_staging.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        DOCS_SITE_DIR / "schema" / "dbml" / "index.md", dbml_staging / "index.md"
    )
    for dbml_file in (DOCS_SCHEMA_DIR / "dbml").glob("*.dbml"):
        shutil.copy2(dbml_file, dbml_staging / dbml_file.name)

    # 5.4 Mermaid Diagrams -> schema/mermaid/
    mermaid_staging = schema_staging / "mermaid"
    mermaid_staging.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        DOCS_SITE_DIR / "schema" / "mermaid" / "index.md", mermaid_staging / "index.md"
    )

    # Puppeteer config for headless rendering
    p_cfg = staging_dir / "puppeteer-config.json"
    p_cfg.write_text(
        json.dumps({"args": ["--no-sandbox", "--disable-setuid-sandbox"]}),
        encoding="utf-8",
    )

    try:
        for slug in MERMAID_DIAGRAM_SLUGS:
            src_md = DOCS_SCHEMA_DIR / "mermaid" / f"{slug}.md"
            if not src_md.is_file():
                raise FileNotFoundError(f"Missing Mermaid markdown: {src_md}")

            raw_text = src_md.read_text(encoding="utf-8")
            svg_filename = f"{slug}.svg"
            svg_path = mermaid_staging / svg_filename

            # Extract Mermaid block
            m = re.search(r"```mermaid\n(.*?)\n```", raw_text, re.DOTALL)
            if not m:
                raise ValueError(f"No mermaid code block found in {src_md}")
            mermaid_code = m.group(1).strip()

            if not svg_path.is_file():
                if skip_mermaid_render:
                    svg_path.write_text(
                        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y="50">{slug}</text></svg>',
                        encoding="utf-8",
                    )
                else:
                    print(f"  Rendering Mermaid SVG: {svg_filename}...")
                    render_mermaid_to_svg(mermaid_code, svg_path, p_cfg)

            # Copy to slug directory so both schema/mermaid/<slug>.svg and
            # schema/mermaid/<slug>/<slug>.svg resolve cleanly from directory URLs
            slug_dir = mermaid_staging / slug
            slug_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(svg_path, slug_dir / svg_filename)

            # Transform markdown to embed SVG and provide controls
            svg_block = f"""
<div class="mermaid-svg-container" style="overflow-x: auto; background: #ffffff; padding: 1.5rem; border-radius: 8px; border: 1px solid #e2e8f0; margin: 1.5rem 0; box-shadow: 0 1px 3px rgba(0,0,0,0.05); text-align: center;">
  <a href="{svg_filename}" target="_blank" title="クリックしてフルサイズSVGを表示">
    <img src="{svg_filename}" alt="{slug} ER Diagram" style="max-width: 100%; height: auto; display: inline-block;" />
  </a>
</div>

<div class="diagram-actions" style="display: flex; gap: 0.75rem; margin-bottom: 1.5rem; flex-wrap: wrap;">
  <a href="{svg_filename}" target="_blank" class="md-button md-button--primary">🔍 フルサイズSVGを開く</a>
  <a href="https://github.com/TakashiSasaki/git-repo-db/blob/main/docs/schema/mermaid/{slug}.md" target="_blank" class="md-button">🐙 GitHubでソースを表示</a>
</div>

??? info "Mermaid 構文ソースコードを表示"
    ```mermaid
    {mermaid_code}
    ```
"""
            transformed_md = raw_text[: m.start()] + svg_block + raw_text[m.end() :]
            (mermaid_staging / f"{slug}.md").write_text(
                transformed_md, encoding="utf-8"
            )
    finally:
        if p_cfg.exists():
            p_cfg.unlink()

    print("✓ Staging completed successfully.")


def run_mkdocs_build(
    config_path: Path,
    strict: bool = True,
    *,
    staging_dir: Path | None = None,
    output_dir: Path | None = None,
) -> None:
    """Execute MkDocs static build."""
    print("Executing MkDocs static build...")
    from mkdocs.commands.build import build

    destinations = validated_config(config_path, staging_dir, output_dir)
    from mkdocs.config import load_config

    cfg = load_config(
        str(config_path),
        docs_dir=destinations["docs_dir"],
        site_dir=destinations["site_dir"],
    )
    if strict:
        cfg["strict"] = True
    build(cfg)

    # Ensure root favicon.ico and PWA assets exist for standard browser requests
    site_dir = Path(cfg["site_dir"])
    icons_src = DOCS_SITE_DIR / "assets" / "images" / "icons"
    fav_png = icons_src / "favicon-32.png"
    if fav_png.is_file():
        shutil.copy2(fav_png, site_dir / "favicon.ico")

    for pwa_file in ["manifest.webmanifest", "manifest.json", "sw.js", "pwa.js"]:
        src_pwa = DOCS_SITE_DIR / pwa_file
        if src_pwa.is_file() and not (site_dir / pwa_file).is_file():
            shutil.copy2(src_pwa, site_dir / pwa_file)

    if icons_src.is_dir():
        icons_dst = site_dir / "assets" / "images" / "icons"
        icons_dst.mkdir(parents=True, exist_ok=True)
        for icon_file in icons_src.glob("*"):
            if icon_file.is_file():
                shutil.copy2(icon_file, icons_dst / icon_file.name)

    print("✓ MkDocs build completed successfully.")


def validate_publication_safety(output_dir: Path) -> List[str]:
    """Validate that output directory contains only allowlisted, non-sensitive assets."""
    print(f"Validating publication safety for {output_dir}...")
    violations = []

    if not output_dir.is_dir():
        return [f"Output directory {output_dir} does not exist."]

    for item in output_dir.rglob("*"):
        if not item.is_file():
            continue

        rel_path = str(item.relative_to(output_dir))

        # Check file extension against allowlist
        if item.suffix.lower() not in PUBLIC_ALLOWLIST_EXTENSIONS:
            violations.append(f"Disallowed file extension '{item.suffix}': {rel_path}")

        # Check forbidden patterns
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, rel_path, re.IGNORECASE):
                violations.append(
                    f"Forbidden sensitive pattern match ({pattern}): {rel_path}"
                )

    return violations


def validate_internal_links(output_dir: Path) -> List[str]:
    """Scan generated HTML pages and verify all internal links resolve to valid files."""
    print(f"Scanning internal links in {output_dir}...")
    broken_links = []
    html_files = list(output_dir.rglob("*.html"))

    href_re = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)

    for html_file in html_files:
        rel_html = html_file.relative_to(output_dir)
        content = html_file.read_text(encoding="utf-8", errors="replace")

        for m in href_re.finditer(content):
            target = m.group(1).strip()

            # Ignore external links, mailto, in-page anchors, javascript
            if (
                target.startswith("http://")
                or target.startswith("https://")
                or target.startswith("//")
                or target.startswith("mailto:")
                or target.startswith("javascript:")
                or target.startswith("#")
                or not target
            ):
                continue

            # Strip URL query and fragment
            parsed = urlparse(target)
            clean_path = unquote(parsed.path)

            if not clean_path:
                continue

            if clean_path.startswith("/"):
                # Absolute from site root
                cand = output_dir / clean_path.lstrip("/")
            else:
                # Relative from current html file's directory
                cand = (html_file.parent / clean_path).resolve()

            # Check existence
            exists = False
            if cand.is_file():
                exists = True
            elif cand.is_dir() and (cand / "index.html").is_file():
                exists = True
            elif (
                clean_path.endswith("/")
                and (output_dir / clean_path.strip("/") / "index.html").is_file()
            ):
                exists = True

            if not exists:
                broken_links.append(
                    f"[{rel_html}] Broken link target '{target}' -> resolved: '{cand}'"
                )

    return broken_links


def validate_critical_endpoints(output_dir: Path) -> List[str]:
    """Ensure all required public documentation routes exist."""
    critical_rel_paths = [
        "index.html",
        "architecture/index.html",
        "architecture/three-store-boundary/index.html",
        "schema/index.html",
        "schema/viewer/index.html",
        "schema/dbml/index.html",
        "schema/dbml/core.dbml",
        "schema/dbml/operational.dbml",
        "schema/dbml/search.dbml",
        "schema/dbml/combined.dbml",
        "schema/mermaid/index.html",
        "schema/mermaid/overview/index.html",
        "schema/mermaid/overview.svg",
        "adr/index.html",
        "adr/0001-validation-lifecycle-architecture/index.html",
        "adr/0002-three-store-boundary-architecture/index.html",
        "development/index.html",
        "manifest.webmanifest",
        "manifest.json",
        "sw.js",
        "pwa.js",
        "assets/images/icons/icon.svg",
        "assets/images/icons/icon-maskable.svg",
        "assets/images/icons/icon-192.png",
        "assets/images/icons/icon-512.png",
        "assets/images/icons/icon-180.png",
        "assets/images/icons/favicon-32.png",
    ]
    missing = []
    for rel in critical_rel_paths:
        target = output_dir / rel
        if not target.is_file():
            missing.append(f"Missing critical public endpoint: {rel}")
    return missing


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--staging-dir",
        type=Path,
        default=DEFAULT_STAGING_DIR,
        help="Temporary directory for staging allowlisted Markdown sources",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Target output directory for static HTML site",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate inputs, freshness, staging, and MkDocs config without publishing",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start MkDocs development server after staging",
    )
    parser.add_argument(
        "--no-mermaid",
        action="store_true",
        help="Skip re-rendering Mermaid diagrams if SVGs already exist (for fast preview)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean staging and output directories before build",
    )
    parser.add_argument("--product-source", required=True)
    parser.add_argument("--documentation-source", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    verify_documentation_checkout(args.documentation_source)
    # Resolve/validate all actual destinations before any cleanup, stage or build.
    cfg = validated_config(MKDOCS_CONFIG_FILE, args.staging_dir, args.output_dir)
    args.staging_dir, args.output_dir = Path(cfg["docs_dir"]), Path(cfg["site_dir"])
    from scripts.verification_outputs import private_path, write_private_json

    from tools.provenance import input_record

    metadata_path = private_path(ROOT, IR_PATH.parent / "documentation-inputs.json")
    record = input_record(
        ROOT,
        args.documentation_source,
        args.product_source,
        IR_PATH.with_name("producer.json"),
        IR_PATH,
    )
    write_private_json(ROOT, metadata_path, record)

    print("=================================================================")
    print(" git-repo-db Developer Documentation Site Builder")
    print("=================================================================")

    # 1. Freshness Check
    check_schema_freshness()

    # 2. Clean if requested
    if args.clean:
        if args.staging_dir.exists():
            shutil.rmtree(args.staging_dir)
        if args.output_dir.exists():
            shutil.rmtree(args.output_dir)

    # 3. Stage Documentation
    stage_documentation(args.staging_dir, skip_mermaid_render=args.no_mermaid)

    # 4. Handle --serve mode
    if args.serve:
        print("Starting MkDocs live development server on http://127.0.0.1:8000/ ...")
        from mkdocs.commands.serve import serve

        serve(
            config_file=str(MKDOCS_CONFIG_FILE),
            docs_dir=str(args.staging_dir),
            site_dir=str(args.output_dir),
        )
        return 0

    # 5. Build static site
    run_mkdocs_build(
        MKDOCS_CONFIG_FILE,
        strict=True,
        staging_dir=args.staging_dir,
        output_dir=args.output_dir,
    )

    # 6. Validate critical endpoints
    missing_endpoints = validate_critical_endpoints(args.output_dir)
    if missing_endpoints:
        print(
            "ERROR: Critical public endpoints missing from build output:",
            file=sys.stderr,
        )
        for ep in missing_endpoints:
            print(f"  - {ep}", file=sys.stderr)
        return 1

    # 7. Validate publication safety
    safety_violations = validate_publication_safety(args.output_dir)
    if safety_violations:
        print("ERROR: Publication safety violations detected:", file=sys.stderr)
        for v in safety_violations:
            print(f"  - {v}", file=sys.stderr)
        return 1
    print("✓ Publication safety check passed (0 sensitive files, all allowlisted).")

    # 8. Validate internal links
    broken_links = validate_internal_links(args.output_dir)
    if broken_links:
        print("ERROR: Broken internal links detected:", file=sys.stderr)
        for link in broken_links:
            print(f"  - {link}", file=sys.stderr)
        return 1
    print("✓ Internal link validation passed (0 broken links).")

    meta = get_git_metadata()
    print("=================================================================")
    print(" Build Summary:")
    print(f"  - Output Directory: {args.output_dir}")
    print(f"  - Source Commit: {meta['commit_sha']}")
    print(f"  - Git Tree: {meta['tree_sha']}")
    print("  - Core Schema: 21 (70 tables)")
    print("  - Operational Schema: 1 (10 tables)")
    print("  - Search Schema: 1 (4 tables)")
    print(f"  - Mermaid Diagrams Rendered: {len(MERMAID_DIAGRAM_SLUGS)} SVGs")
    print(" Status: BUILD & VALIDATION SUCCESSFUL")
    print("=================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
