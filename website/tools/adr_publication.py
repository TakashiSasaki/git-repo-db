"""Explicit current-decision publication set; no recursive ADR publishing."""

from __future__ import annotations

import json
import posixpath
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from tools.product_context import PRODUCT_ROOT, WEB_ROOT

ROOT = PRODUCT_ROOT
# The product branch owns selection; the web branch does not duplicate it.

_POLICY = json.loads((ROOT / "docs/web-source-policy.json").read_text())
PUBLIC_ADRS = tuple(_POLICY["public_adrs"])
SUPPORT = tuple(_POLICY["support"])


def destinations() -> dict[str, str]:
    return {p: "adr/" + Path(p).name for p in (*PUBLIC_ADRS, *SUPPORT)}


def rewrite_links(text: str, source: str, revision: str) -> str:
    published = destinations()
    published["docs/adr/README.md"] = "adr/index.md"

    def replace(match):
        target = match.group(2)
        legacy = "https://github.com/TakashiSasaki/git-repo-db"
        if target == legacy or target.startswith(
            (legacy + "/", legacy + "?", legacy + "#")
        ):
            return (
                match.group(1)
                + "https://github.com/TakashiSasaki/resource-atlas"
                + target[len(legacy) :]
                + ")"
            )
        parsed = urlsplit(target)
        if (
            parsed.scheme
            or parsed.netloc
            or not parsed.path
            or parsed.path.startswith("/")
        ):
            return match.group(0)
        resolved = posixpath.normpath(
            posixpath.join(posixpath.dirname(source), parsed.path)
        )
        suffix = ("?" + parsed.query if parsed.query else "") + (
            "#" + parsed.fragment if parsed.fragment else ""
        )
        relocated = {
            "website/current-runtime-reference.md": "docs/current-runtime-reference.md",
            "website/content-inventory.json": "docs/content-inventory.json",
            "website/tools/inventory_content.py": "scripts/content_inventory.py",
            "website/tests/test_content_ownership.py": "tests/unit/test_content_ownership.py",
        }
        resolved = relocated.get(resolved, resolved)
        if resolved.startswith("website/") or resolved in {
            "index.html",
            "package.json",
            "package-lock.json",
            "vite.config.mjs",
        }:
            web_revision = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=WEB_ROOT, text=True
            ).strip()
            return (
                match.group(1)
                + f"https://github.com/TakashiSasaki/resource-atlas/blob/{web_revision}/{resolved}"
                + suffix
                + ")"
            )
        if resolved in published:
            url = posixpath.relpath(published[resolved], "adr") + suffix
        else:
            # External repository links do not copy additional documents/scripts.
            url = (
                f"https://github.com/TakashiSasaki/resource-atlas/blob/{revision}/{resolved}"
                + suffix
            )
        return match.group(1) + url + ")"

    return re.sub(r"(!?\[[^\]]*\]\()([^\s)]+)\)", replace, text)


def accepted_rows() -> dict[str, str]:
    body = (
        (ROOT / "docs/adr/README.md")
        .read_text()
        .split("## Accepted Records\n", 1)[1]
        .split("## Proposed Records", 1)[0]
    )
    result = {}
    for row in body.splitlines():
        match = re.match(r"\| \[[^\]]+\]\(([^)]+)\)", row)
        if match:
            path = posixpath.normpath("docs/adr/" + match.group(1))
            result[path] = row
    if set(result) != set(PUBLIC_ADRS):
        raise ValueError(
            "Accepted ADR index differs from explicit publication allowlist; review selection"
        )
    return result


def stage_adrs(staging: Path, revision: str) -> None:
    rows = accepted_rows()
    target = staging / "adr"
    target.mkdir(parents=True, exist_ok=True)
    intro = (
        (WEB_ROOT / "website/content/adr/index.md")
        .read_text()
        .replace(
            "/blob/main/docs/adr/README.md", f"/blob/{revision}/docs/adr/README.md"
        )
    )
    table = (
        "| ADR | Decision | Date | Current applicability |\n| --- | --- | --- | --- |\n"
        + "\n".join(rows.values())
        + "\n"
    )
    (target / "index.md").write_text(
        intro + "\n" + rewrite_links(table, "docs/adr/README.md", revision)
    )
    for source, dest in destinations().items():
        path = ROOT / source
        if path.is_symlink():
            raise ValueError("Symlink ADR source refused")
        raw = path.read_text()
        if source in rows:
            # Applicability is copied from the canonical index, outside ADR body.
            scope = rows[source].split("|")[-2].strip()
            banner = (
                "> **現在の適用範囲（正本索引）:** "
                + scope
                + "\n> 全文には過去の用語や未採択の実装提案も含まれます。後継 ADR と部分置換の範囲を併読してください。\n\n"
            )
            if raw.startswith("---\n"):
                end = raw.index("\n---", 4) + 5
                raw = raw[:end] + banner + raw[end:]
            else:
                raw = banner + raw
        (staging / dest).write_text(rewrite_links(raw, source, revision))
