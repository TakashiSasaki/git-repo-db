"""Integration counterexamples use only disposable, actually pinned inputs."""

import hashlib
import json
import subprocess
from types import SimpleNamespace

import pytest

from tools import build_docs_site as builder
from tools.provenance import input_record


@pytest.mark.parametrize("attack", ["symlink", "hardlink", "catalog"])
def test_builder_refuses_unsafe_private_manifest_before_any_write(
    tmp_path, monkeypatch, attack
):
    root = tmp_path / "repository"
    docs = root / "documentation"
    docs.mkdir(parents=True)
    (root / ".gitignore").write_text("documentation/.build/\ndocumentation/site/\n")
    config = docs / "mkdocs.yml"
    config.write_text(
        "site_name: fixture\ndocs_dir: .build/staging/site\nsite_dir: site\n"
    )
    product = root / "schema.sql"
    product.write_text("synthetic committed schema")

    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args]).decode().strip()

    git("init", "-q")
    git("config", "user.name", "Synthetic output fixture")
    git("config", "user.email", "fixture@example.invalid")
    git("add", ".")
    git("commit", "-qm", "pinned synthetic inputs")
    source = git("rev-parse", "HEAD")
    tree = git("rev-parse", "HEAD^{tree}")
    inputs = docs / ".build/inputs"
    inputs.mkdir(parents=True)
    ir = inputs / "inventory.json"
    ir.write_text('{"complete":"synthetic IR"}')
    producer = inputs / "producer.json"
    producer.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "product_source": {"commit": source, "tree": tree},
                "ir_sha256": hashlib.sha256(ir.read_bytes()).hexdigest(),
                "input_sha256": {
                    "schema.sql": hashlib.sha256(product.read_bytes()).hexdigest()
                },
            }
        )
    )
    assert (
        input_record(root, source, source, producer, ir)["selected_product_source"][
            "commit"
        ]
        == source
    )
    outside = tmp_path / "product-state"
    outside.write_text("unchanged sentinel")
    target = inputs / "documentation-inputs.json"
    if attack == "symlink":
        target.symlink_to(outside)
    elif attack == "hardlink":
        __import__("os").link(outside, target)
    else:
        target.write_bytes(b"SQLite format 3\x00" + b"synthetic catalog")
    before = target.read_bytes()
    for name, value in {
        "ROOT": root,
        "DOCS_ROOT": docs,
        "MKDOCS_CONFIG_FILE": config,
        "IR_PATH": ir,
    }.items():
        monkeypatch.setattr(builder, name, value)
    args = SimpleNamespace(
        staging_dir=docs / ".build/staging/site",
        output_dir=docs / "site",
        product_source=source,
        documentation_source=source,
        clean=True,
        no_mermaid=True,
        serve=False,
    )
    monkeypatch.setattr(builder, "parse_args", lambda: args)
    monkeypatch.setattr(
        builder,
        "check_schema_freshness",
        lambda: pytest.fail(
            "freshness must not run before private destination refusal"
        ),
    )
    try:
        with pytest.raises(ValueError):
            builder.main()
    finally:
        assert outside.read_text() == "unchanged sentinel"
        assert target.read_bytes() == before
    assert not args.staging_dir.exists() and not args.output_dir.exists()
