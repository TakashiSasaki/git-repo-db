"""Render the shared browser UI for MkDocs without a second UI implementation.

Vite bundles main.js for npm users. MkDocs inlines the same dependency-free
app.js, stylesheet and curated model. Neither path runs product/RDF extraction.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "website/content/design/semantic-model.json"
WEB = ROOT / "website/web"
ENTRY = '<script type="module" src="/website/web/main.js"></script>'
DOMAINS = {
    "core",
    "context",
    "access",
    "operational",
    "search",
    "filesystem",
    "worktrees",
}


def load_model(path: Path = MODEL) -> dict:
    """Check relationships, scope labels and citations at the pinned revision."""
    model = json.loads(path.read_text(encoding="utf-8"))
    revision = model["source_revision"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Unpinned semantic source")

    def git(*args: str) -> bytes:
        return subprocess.check_output(["git", *args], cwd=ROOT)

    if git("rev-parse", revision + "^{tree}").decode().strip() != model["source_tree"]:
        raise ValueError("Semantic source tree mismatch")
    if {d["id"] for d in model["domains"]} != DOMAINS or len(model["domains"]) != 7:
        raise ValueError("Expected seven responsibility domains")
    concepts = {c["id"]: c for c in model["concepts"]}
    if len(concepts) != len(model["concepts"]):
        raise ValueError("Duplicate semantic concept")
    for concept in concepts.values():
        if concept["domain"] not in DOMAINS or concept["rdf_scope"] not in {
            "structural-only",
            "instance-pilot",
            "unmapped",
        }:
            raise ValueError("Unknown domain or RDF scope")
    for relation in model["relations"]:
        if relation["source"] not in concepts or relation["target"] not in concepts:
            raise ValueError("Unknown semantic relation endpoint")
        if relation["kind"] not in {
            "domain-reference",
            "observation",
            "claim",
            "derivation",
            "execution",
        }:
            raise ValueError("Unknown semantic relation kind")
    for stream in model["workstreams"]:
        if stream["status"] not in {"implemented", "partial", "not-implemented"}:
            raise ValueError("Unknown RDF workstream status")
    if {f["id"] for f in model["result_families"]} != {
        "data_conformance",
        "spec_satisfiability",
        "operation_invariants",
        "implementation_conformance",
    } or any(f["status"] != "not_run" for f in model["result_families"]):
        raise ValueError("This code audit must not claim new model execution")

    # Cite committed code/decisions, not generated output or live catalog data.
    cited = {}
    for item in [
        *model["domains"],
        *concepts.values(),
        *model["layers"],
        *model["workstreams"],
        *model["result_families"],
    ]:
        if not item.get("citations"):
            raise ValueError("Uncited semantic assertion")
        for citation in item["citations"]:
            filename, line = citation["path"], citation["line"]
            source = Path(filename)
            if (
                source.is_absolute()
                or ".." in source.parts
                or "\\" in filename
                or source.parts[0]
                not in {
                    "src",
                    "packages",
                    "docs",
                    "documentation",
                    "website",
                    "tools",
                    "scripts",
                }
                or type(line) is not int
                or line < 1
            ):
                raise ValueError("Invalid semantic citation")
            if filename not in cited:
                pinned = git("show", f"{revision}:{filename}")
                cited[filename] = len(pinned.splitlines())
            if line > cited[filename]:
                raise ValueError("Semantic citation line outside source")
    return model


def generate_html() -> str:
    for source in (ROOT / "index.html", WEB):
        if source.is_symlink() or any(p.is_symlink() for p in source.rglob("*")):
            raise ValueError("Symlink frontend source refused")
    model = load_model()
    entry = (ROOT / "index.html").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")
    style = (WEB / "style.css").read_text(encoding="utf-8")
    if entry.count(ENTRY) != 1 or re.search(r"^\s*import\b", app, re.M):
        raise ValueError(
            "Shared frontend entry contract changed; update both render paths"
        )
    # JSON cannot terminate its own HTML script element.
    data = json.dumps(model, ensure_ascii=False).replace("<", "\\u003c")
    scripts = (
        '<script type="application/json" id="semantic-model">' + data + "</script>\n"
        '<script type="module">\n'
        + app
        + '\nrenderApp(JSON.parse(document.getElementById("semantic-model").textContent));\n</script>'
    )
    return entry.replace("</head>", f"<style>\n{style}\n</style>\n</head>").replace(
        ENTRY, scripts
    )
