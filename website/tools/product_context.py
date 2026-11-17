"""Separate immutable product inputs from editable web sources."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


def selected_product() -> dict:
    value = json.loads((WEB_ROOT / "product-source.json").read_text())
    if value.get(
        "repository"
    ) != "https://github.com/TakashiSasaki/resource-atlas.git" or not re.fullmatch(
        r"[0-9a-f]{40}", value.get("commit", "")
    ):
        raise ValueError("A canonical repository and full product commit are required")
    return value


def product_root() -> Path:
    pin = selected_product()
    location = WEB_ROOT / "website/.build/inputs/product-location.json"
    configured = os.environ.get("RESOURCE_ATLAS_PRODUCT_ROOT")
    if configured is None and location.is_file():
        configured = json.loads(location.read_text())["path"]
    if not configured:
        raise ValueError(
            "Product inputs are not prepared; run python scripts/prepare_product.py"
        )
    root = Path(configured).absolute()
    if (
        root == WEB_ROOT
        or WEB_ROOT in root.parents
        or any(p.is_symlink() for p in (root, *root.parents))
    ):
        raise ValueError("Product checkout must be a separate, unlinked tree")
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    if actual != pin["commit"]:
        raise ValueError("Product checkout does not match product-source.json")
    from tools.source_integrity import verify_checkout

    verify_checkout(root, pin["commit"])
    return root


PRODUCT_ROOT = product_root()


def verify_inputs() -> str:
    """Bind the transferred canonical-source selection to committed product bytes."""
    base = WEB_ROOT / "website/.build/inputs"
    source = base / "source-manifest.json"
    raw = source.read_bytes()
    handoff = json.loads(raw)
    pin = selected_product()["commit"]
    tree = subprocess.check_output(
        ["git", "rev-parse", pin + "^{tree}"], cwd=PRODUCT_ROOT, text=True
    ).strip()
    if handoff.get("product_source") != {"commit": pin, "tree": tree}:
        raise ValueError("Canonical-source handoff differs from product pin")
    policy_path = "docs/web-source-policy.json"
    policy = json.loads(
        subprocess.check_output(
            ["git", "show", pin + ":" + policy_path], cwd=PRODUCT_ROOT
        )
    )
    expected = {
        policy_path,
        policy["canonical_index"],
        *policy["public_adrs"],
        *policy["support"],
    }
    if set(handoff.get("canonical_sources", {})) != expected:
        raise ValueError("Canonical-source selection is incomplete or unapproved")
    for name, digest in handoff["canonical_sources"].items():
        path = PRODUCT_ROOT / name
        if (
            not name.startswith("docs/")
            or ".." in Path(name).parts
            or any(p.is_symlink() for p in (path, *path.parents))
        ):
            raise ValueError("Unsafe canonical-source path")
        committed = subprocess.check_output(
            ["git", "show", pin + ":" + name], cwd=PRODUCT_ROOT
        )
        if (
            hashlib.sha256(committed).hexdigest() != digest
            or path.read_bytes() != committed
        ):
            raise ValueError("Canonical source differs from selected commit: " + name)
    if hashlib.sha256(
        (base / "inventory.json").read_bytes()
    ).hexdigest() != handoff.get("ir_sha256"):
        raise ValueError("Canonical handoff/IR mismatch")
    return hashlib.sha256(raw).hexdigest()
