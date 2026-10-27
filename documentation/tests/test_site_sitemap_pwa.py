"""Regression checks against the staged and rendered public site."""

import gzip
import json
import struct
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urljoin, urlparse

from tools.build_docs_site import (
    DOCS_ROOT,
    MKDOCS_CONFIG_FILE,
    run_mkdocs_build,
    stage_documentation,
    validate_publication_safety,
)


def test_rendered_sitemap_and_pwa():
    staging_root = DOCS_ROOT / ".build/staging"
    output_root = DOCS_ROOT / ".build/output"
    staging_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (
        tempfile.TemporaryDirectory(dir=staging_root) as stage,
        tempfile.TemporaryDirectory(dir=output_root) as out,
    ):
        stage, out = Path(stage), Path(out)
        stage_documentation(stage, skip_mermaid_render=True)
        run_mkdocs_build(MKDOCS_CONFIG_FILE, staging_dir=stage, output_dir=out)
        assert not validate_publication_safety(out)
        xml = (out / "sitemap.xml").read_bytes()
        assert gzip.decompress((out / "sitemap.xml.gz").read_bytes()) == xml
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = [e.text for e in ET.fromstring(xml).findall("s:url/s:loc", ns)]
        base = "https://git-repo-db.moukaeritai.work/"
        expected = {
            urljoin(
                base,
                "" if p.parent == out else p.parent.relative_to(out).as_posix() + "/",
            )
            for p in out.rglob("index.html")
        }
        assert len(urls) == len(set(urls))
        assert set(urls) == expected
        assert base + "schema/viewer/" in urls
        assert all(
            (out / urlparse(url).path.lstrip("/") / "index.html").is_file()
            for url in urls
        )

        manifest = json.loads((out / "manifest.webmanifest").read_text())
        assert (
            manifest["id"],
            manifest["start_url"],
            manifest["scope"],
            manifest["display"],
        ) == ("/", "/", "/", "standalone")
        for html in (out / "index.html", out / "schema/viewer/index.html"):
            content = html.read_text()
            assert "manifest.webmanifest" in content and "pwa.js" in content
        for icon in manifest["icons"]:
            path = out / icon["src"]
            assert path.is_file()
            if icon["type"] == "image/png":
                data = path.read_bytes()
                assert data[:8] == b"\x89PNG\r\n\x1a\n"
                width, height = struct.unpack(">II", data[16:24])
                assert icon["sizes"] == f"{width}x{height}"
        assert ".register('/sw.js', { scope: '/' })" in (out / "pwa.js").read_text()
        assert (out / "sw.js").is_file()
