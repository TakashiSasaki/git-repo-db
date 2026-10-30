"""Read-only, cited semantic design projection; never a product/DDL inventory."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "documentation/content/design/model.json"
STATUSES = {"A", "I", "P", "U"}


def load_model(path: Path = MODEL) -> dict:
    model = json.loads(path.read_text())
    if model["id"] != "accepted-design" or not re.fullmatch(
        r"[0-9a-f]{40}", model["source_revision"]
    ):
        raise ValueError("Unpinned design source")
    tree = (
        subprocess.check_output(
            ["git", "rev-parse", model["source_revision"] + "^{tree}"], cwd=ROOT
        )
        .decode()
        .strip()
    )
    if tree != model["source_tree"]:
        raise ValueError("Design source tree mismatch")
    stores = {s["id"] for s in model["stores"]}
    if stores != {"core", "context", "access", "operational", "search"}:
        raise ValueError("Expected five responsibility stores")
    entities = {e["id"]: e for e in model["entities"]}
    if len(entities) != len(model["entities"]):
        raise ValueError("Duplicate qualified identity")
    facts = [s["meaning"] for s in model["stores"]]
    for e in entities.values():
        if e["store"] not in stores or e["id"] != f"design/{e['store']}/{e['name']}":
            raise ValueError("Unqualified entity identity")
        facts.extend([e["meaning"], *e["keys"], *e["constraints"]])
    for rel in model["relations"]:
        if (
            rel["source"] not in entities
            or rel["target"] not in entities
            or rel["kind"] != "semantic"
        ):
            raise ValueError("Invalid semantic relation endpoint")
        facts.append(rel["meaning"])
    paths = set()
    for f in facts:
        if f["status"] not in STATUSES or not f["text"] or not f["sources"]:
            raise ValueError("Uncited design assertion")
        for source in f["sources"]:
            p = Path(source["path"])
            if (
                p.is_absolute()
                or ".." in p.parts
                or p.parts[0] != "docs"
                or p.suffix != ".md"
                or not source["anchor"]
            ):
                raise ValueError("Invalid design citation")
            paths.add(source["path"])
    for p in sorted(paths):
        pinned = subprocess.check_output(
            ["git", "show", f"{model['source_revision']}:{p}"], cwd=ROOT
        )
        if (ROOT / p).is_symlink() or (ROOT / p).read_bytes() != pinned:
            raise ValueError(f"Design citation differs from selected source: {p}")
    return model


def generate_html() -> str:
    model = load_model()
    data = json.dumps(model, ensure_ascii=False, separators=(",", ":")).replace(
        "<", "\\u003c"
    )
    return (
        Path(__file__)
        .with_name("design_viewer.html")
        .read_text()
        .replace("__DESIGN_MODEL__", data)
    )
