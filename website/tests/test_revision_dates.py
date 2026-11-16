"""Selected source dates are commit facts, distinct from build time."""

import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools import build_docs_site as builder
from tools.provenance import source_identity

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = "f0e3022dd8f6dc7b3793e47522dced3ec8be3e8a"


def test_distinct_source_dates_and_design_links():
    docs = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    record = {
        "documentation_source": source_identity(ROOT, docs),
        "selected_product_source": source_identity(ROOT, PRODUCT),
        "neutral_ir_sha256": "a" * 64,
    }
    assert docs != PRODUCT
    parent = builder.DOCS_ROOT / ".build/staging"
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=parent) as temp:
        destination = Path(temp)
        builder.stage_documentation(
            destination, skip_mermaid_render=True, provenance=record
        )
        text = (destination / "index.md").read_text()
        for commit in (docs, PRODUCT):
            raw = subprocess.check_output(
                ["git", "show", "-s", "--format=%cI", commit], cwd=ROOT, text=True
            ).strip()
            utc = (
                datetime.fromisoformat(raw)
                .astimezone(timezone.utc)
                .isoformat(timespec="seconds")
            )
            assert f'datetime="{utc}"' in text
            assert f"/commit/{commit}" in text
        assert f"/tree/{docs}/docs/adr" in text
        assert "意味的に検証済み" in text
        assert "Build time" in text and "公開時刻ではありません" in text
        builder.stage_documentation(destination, skip_mermaid_render=True)
        text = (destination / "index.md").read_text()
        assert "未検証（staging 単体）" in text
        assert "Selected Product commit time" not in text


def test_missing_commit_never_uses_build_time():
    with pytest.raises((ValueError, RuntimeError)):
        builder.commit_timestamp("0" * 40)
