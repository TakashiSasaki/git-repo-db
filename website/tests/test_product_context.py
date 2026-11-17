"""Independent repositories retain source and handoff integrity."""

import json
import shutil
import subprocess

import pytest

from tools import product_context as context
from tools.provenance import source_identity


def test_web_and_product_histories_are_distinct():
    web = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=context.WEB_ROOT, text=True
    ).strip()
    product = context.selected_product()["commit"]
    assert web != product
    assert source_identity(context.PRODUCT_ROOT, product)["commit"] == product
    assert not (context.WEB_ROOT / "src").exists()
    assert not (context.WEB_ROOT / "docs").exists()


def test_product_checkout_cannot_be_the_web_tree(monkeypatch):
    monkeypatch.setenv("RESOURCE_ATLAS_PRODUCT_ROOT", str(context.WEB_ROOT))
    with pytest.raises(ValueError, match="separate"):
        context.product_root()


def test_wrong_selected_product_is_refused(monkeypatch):
    snapshot = context.selected_product()
    monkeypatch.setattr(
        context, "selected_product", lambda: {**snapshot, "commit": "0" * 40}
    )
    with pytest.raises(ValueError, match="does not match"):
        context.product_root()


def test_another_preparation_does_not_retarget_loaded_product(tmp_path, monkeypatch):
    original = context.selected_product()
    location = tmp_path / "website/.build/inputs/product-location.json"
    location.parent.mkdir(parents=True)
    location.write_text(json.dumps({**original, "commit": "0" * 40}))
    monkeypatch.setattr(context, "WEB_ROOT", tmp_path)
    assert context.selected_product() == original


def test_wrong_recorded_tree_is_refused_without_checking_remote(monkeypatch):
    snapshot = context.selected_product()
    monkeypatch.setattr(
        context, "selected_product", lambda: {**snapshot, "tree": "0" * 40}
    )
    with pytest.raises(ValueError, match="tree differs"):
        context.product_root()
    with pytest.raises(ValueError, match="tree differs"):
        context.verify_inputs()


def test_tampered_private_handoff_is_refused(tmp_path, monkeypatch):
    (tmp_path / "website/.build").mkdir(parents=True)
    shutil.copytree(
        context.WEB_ROOT / "website/.build/inputs", tmp_path / "website/.build/inputs"
    )
    shutil.copy2(
        context.WEB_ROOT / "product-source.json", tmp_path / "product-source.json"
    )
    monkeypatch.setattr(context, "WEB_ROOT", tmp_path)
    assert context.verify_inputs()
    handoff = tmp_path / "website/.build/inputs/source-manifest.json"
    value = json.loads(handoff.read_text())
    value["canonical_sources"].pop(next(iter(value["canonical_sources"])))
    handoff.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="incomplete or unapproved"):
        context.verify_inputs()


@pytest.mark.parametrize("hidden", [False, True])
def test_modified_product_control_is_refused_before_execution(tmp_path, hidden):
    from tools.source_integrity import verify_checkout

    clone = tmp_path / "product"
    subprocess.run(
        ["git", "clone", "--quiet", "--shared", str(context.PRODUCT_ROOT), str(clone)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "checkout",
            "--quiet",
            "--detach",
            context.selected_product()["commit"],
        ],
        cwd=clone,
        check=True,
    )
    name = "scripts/check_sqlite_validation_policy.py"
    if hidden:
        subprocess.run(
            ["git", "update-index", "--assume-unchanged", name], cwd=clone, check=True
        )
    (clone / name).write_text("raise SystemExit('unexpected modified control')")
    with pytest.raises(
        ValueError, match="uncommitted inputs|differs from selected commit"
    ):
        verify_checkout(clone, context.selected_product()["commit"])
