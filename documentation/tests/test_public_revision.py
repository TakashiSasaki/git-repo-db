"""Public metadata is derived from independently selected, validated sources."""

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from tools import build_docs_site as builder
from tools.provenance import EvidenceError, input_record, source_identity

ROOT = Path(__file__).resolve().parents[2]
PRODUCT_BASE = "f0e3022dd8f6dc7b3793e47522dced3ec8be3e8a"


def test_compatible_older_product_and_public_metadata(tmp_path):
    docs = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    assert docs != PRODUCT_BASE
    inputs = ROOT / "documentation/.build/inputs"
    manifest = json.loads((inputs / "producer.json").read_text())
    manifest["product_source"] = source_identity(ROOT, PRODUCT_BASE)
    synthetic = tmp_path / "producer.json"
    synthetic.write_text(json.dumps(manifest))
    record = input_record(
        ROOT, docs, PRODUCT_BASE, synthetic, inputs / "inventory.json"
    )
    assert (
        record["documentation_source"]["commit"]
        != record["selected_product_source"]["commit"]
    )
    staging_parent = builder.DOCS_ROOT / ".build/staging"
    staging_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=staging_parent) as temp:
        destination = Path(temp)
        builder.stage_documentation(
            destination, skip_mermaid_render=True, provenance=record
        )
        content = (destination / "index.md").read_text()
        assert record["documentation_source"]["commit"] in content
        assert record["documentation_source"]["tree"] in content
        assert record["selected_product_source"]["commit"] in content
        assert record["selected_product_source"]["tree"] in content
        assert record["neutral_ir_sha256"] in content
        assert "input_sha256" not in content
        assert not any(path in content for path in record["producer_input_sha256"])
        sentinel = destination / "unchanged.txt"
        sentinel.write_text("preserve")
        invalid = dict(record, documentation_source=source_identity(ROOT, PRODUCT_BASE))
        with pytest.raises(ValueError, match="does not match"):
            builder.stage_documentation(
                destination, skip_mermaid_render=True, provenance=invalid
            )
        assert sentinel.read_text() == "preserve"
        invalid = dict(record)
        del invalid["selected_product_source"]
        with pytest.raises(ValueError, match="Missing or malformed"):
            builder.stage_documentation(
                destination, skip_mermaid_render=True, provenance=invalid
            )
        assert sentinel.read_text() == "preserve"
    manifest["ir_sha256"] = "0" * 64
    synthetic.write_text(json.dumps(manifest))
    with pytest.raises(EvidenceError):
        input_record(ROOT, docs, PRODUCT_BASE, synthetic, inputs / "inventory.json")
    synthetic.unlink()
    with pytest.raises(EvidenceError):
        input_record(ROOT, docs, PRODUCT_BASE, synthetic, inputs / "inventory.json")
