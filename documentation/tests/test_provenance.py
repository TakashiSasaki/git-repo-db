"""Consistency controls using synthetic committed inputs, never live catalogs."""

from __future__ import annotations

import json
import subprocess

import pytest

from tools.provenance import EvidenceError, digest, input_record, source_identity


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args]).decode().strip()


@pytest.fixture
def inputs(tmp_path):
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Synthetic documentation test")
    git(root, "config", "user.email", "fixture@example.invalid")
    (root / "schema.sql").write_text("CREATE TABLE example(id INTEGER PRIMARY KEY);")
    git(root, "add", "schema.sql")
    git(root, "commit", "-qm", "synthetic product")
    product = git(root, "rev-parse", "HEAD")
    (root / "documentation.txt").write_text("Synthetic derived document")
    (root / "link").symlink_to("schema.sql")
    git(root, "add", "documentation.txt", "link")
    git(root, "commit", "-qm", "synthetic documentation")
    documentation = git(root, "rev-parse", "HEAD")
    ir = tmp_path / "inventory.json"
    ir.write_text(json.dumps({"stores": {"fixture": {"sql": "complete SQL"}}}))
    manifest = tmp_path / "producer.json"
    value = {
        "schema_version": 1,
        "product_source": source_identity(root, product),
        "ir_sha256": digest(ir.read_bytes()),
        "input_sha256": {"schema.sql": digest((root / "schema.sql").read_bytes())},
    }
    manifest.write_text(json.dumps(value))
    return root, documentation, product, manifest, ir


def test_distinct_sources_and_checkout_mutation_do_not_change_selected_inputs(inputs):
    root, documentation, product, manifest, ir = inputs
    original = input_record(*inputs)
    (root / "schema.sql").write_text("uncommitted changed source")
    assert input_record(*inputs) == original
    assert original["documentation_source"]["commit"] == documentation
    assert original["selected_product_source"]["commit"] == product
    assert documentation != product
    assert original["neutral_ir_sha256"] == digest(ir.read_bytes())
    assert "full_acceptance" not in original


@pytest.mark.parametrize("missing", ["manifest", "ir"])
def test_missing_evidence_refused(inputs, missing):
    inputs[3 if missing == "manifest" else 4].unlink()
    with pytest.raises(EvidenceError):
        input_record(*inputs)


@pytest.mark.parametrize(
    "field", ["schema_version", "product_source", "ir_sha256", "input_sha256"]
)
def test_missing_manifest_field_refused(inputs, field):
    value = json.loads(inputs[3].read_text())
    del value[field]
    inputs[3].write_text(json.dumps(value))
    with pytest.raises(EvidenceError):
        input_record(*inputs)


@pytest.mark.parametrize(
    "change", ["product-tree", "ir", "input", "empty-inputs", "malformed-ir"]
)
def test_changed_evidence_refused(inputs, change):
    value = json.loads(inputs[3].read_text())
    if change == "product-tree":
        value["product_source"]["tree"] = "0" * 40
    elif change == "ir":
        inputs[4].write_text('{"altered": true}')
    elif change == "input":
        value["input_sha256"]["schema.sql"] = "0" * 64
    elif change == "empty-inputs":
        value["input_sha256"] = {}
    else:
        inputs[4].write_text("not JSON")
        value["ir_sha256"] = digest(inputs[4].read_bytes())
    inputs[3].write_text(json.dumps(value))
    with pytest.raises(EvidenceError):
        input_record(*inputs)


@pytest.mark.parametrize(
    "path", ["../schema.sql", "/schema.sql", "./schema.sql", "missing", "link"]
)
def test_unsafe_or_nonregular_committed_input_refused(inputs, path):
    root, documentation, product, manifest, ir = inputs
    value = json.loads(manifest.read_text())
    # Select the documentation commit only for this synthetic link-input control.
    value["product_source"] = source_identity(root, documentation)
    value["input_sha256"] = {path: digest((root / "schema.sql").read_bytes())}
    manifest.write_text(json.dumps(value))
    with pytest.raises(EvidenceError):
        input_record(root, documentation, documentation, manifest, ir)


@pytest.mark.parametrize("source", ["HEAD", "main", "abc", "0" * 40])
def test_moving_or_missing_source_refused(inputs, source):
    with pytest.raises(EvidenceError):
        input_record(inputs[0], source, inputs[2], inputs[3], inputs[4])


def test_manifest_contains_only_hashes_not_input_or_ir_contents(inputs):
    record = json.dumps(input_record(*inputs))
    assert "CREATE TABLE" not in record
    assert "complete SQL" not in record


def test_manifest_digest_binds_the_same_bytes_that_were_checked(inputs, monkeypatch):
    manifest = inputs[3]
    original_read = type(manifest).read_bytes
    count = 0

    def read_once(path):
        nonlocal count
        if path == manifest:
            count += 1
            if count > 1:
                return b"changed after validation"
        return original_read(path)

    expected = digest(manifest.read_bytes())
    monkeypatch.setattr(type(manifest), "read_bytes", read_once)
    record = input_record(*inputs)
    assert record["producer_manifest_sha256"] == expected
    assert count == 1
