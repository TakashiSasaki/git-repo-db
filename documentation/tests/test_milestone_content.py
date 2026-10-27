"""Ensure the published milestone's source links resolve at its declared revision."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = "5d28bb33bf62d7b0eff7e6547a4fda84c1815a9d"


def test_published_milestone_source_links_and_categories():
    content = ROOT / "documentation/content"
    homepage = (content / "index.md").read_text(encoding="utf-8")
    for category in ("通常ランタイム", "実装済み opt-in", "採択済み目標", "履歴・証跡"):
        assert category in homepage
    assert "すべてのページがオフラインで利用できる保証はありません" in homepage
    sources = [homepage]
    sources.extend(
        p.read_text(encoding="utf-8") for p in (content / "architecture").glob("*.md")
    )
    sources.append((content / "development/index.md").read_text(encoding="utf-8"))
    pattern = rf"https://github\.com/TakashiSasaki/git-repo-db/blob/{PRODUCT}/([^\s)]+)"
    paths = set(re.findall(pattern, "\n".join(sources)))
    assert {
        "docs/adr/0014-history-and-notes-catalog-without-file-archive.md",
        "docs/adr/0026-stop-salvage-restore-merge-after-corruption.md",
        "docs/adr/0029-independent-access-store.md",
        "src/repo_catalog/adapters/sqlite/p1_schema.py",
        "src/repo_catalog/cli/access_workflow.py",
    } <= paths
    for path in paths:
        subprocess.run(
            ["git", "cat-file", "-e", f"{PRODUCT}:{path}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
