"""Use one automatically recorded product snapshot for this process."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


def prepared_snapshot() -> dict:
    value = json.loads((WEB_ROOT / "product-source.json").read_text())
    if value.get(
        "repository"
    ) != "https://github.com/TakashiSasaki/resource-atlas.git" or (
        value.get("schema_version") != 2
        or value.get("ref") != "main"
        or "commit" in value
    ):
        raise ValueError("Product source must follow the canonical main branch")
    location = WEB_ROOT / "website/.build/inputs/product-location.json"
    if not location.is_file():
        raise ValueError("Run python scripts/prepare_product.py to prepare main inputs")
    snapshot = json.loads(location.read_text())
    if (
        snapshot.get("schema_version") != 2
        or snapshot.get("repository") != value["repository"]
        or snapshot.get("requested_ref") != value["ref"]
        or snapshot.get("selection_mode") not in {"remote-ref", "local-override"}
        or not re.fullmatch(r"[0-9a-f]{40}", snapshot.get("commit", ""))
        or not re.fullmatch(r"[0-9a-f]{40}", snapshot.get("tree", ""))
    ):
        raise ValueError(
            "Prepared source is incompatible; run scripts/prepare_product.py"
        )
    return snapshot


# Freeze once: a later preparation must not retarget already imported modules.
SNAPSHOT = prepared_snapshot()


def selected_product() -> dict:
    return dict(SNAPSHOT)


def product_root() -> Path:
    snapshot = selected_product()
    configured = os.environ.get("RESOURCE_ATLAS_PRODUCT_ROOT", snapshot["path"])
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
    if actual != snapshot["commit"]:
        raise ValueError("Product checkout does not match this attempt's snapshot")
    tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True
    ).strip()
    if tree != snapshot["tree"]:
        raise ValueError("Product checkout tree differs from prepared snapshot")
    from tools.source_integrity import verify_checkout

    verify_checkout(root, snapshot["commit"])
    return root


PRODUCT_ROOT = product_root()


def verify_inputs() -> str:
    """Bind the transferred canonical-source selection to committed product bytes."""
    base = WEB_ROOT / "website/.build/inputs"
    source = base / "source-manifest.json"
    raw = source.read_bytes()
    handoff = json.loads(raw)
    snapshot = selected_product()
    pin = snapshot["commit"]
    tree = subprocess.check_output(
        ["git", "rev-parse", pin + "^{tree}"], cwd=PRODUCT_ROOT, text=True
    ).strip()
    if tree != snapshot["tree"]:
        raise ValueError("Product checkout tree differs from prepared snapshot")
    if handoff.get("product_source") != {"commit": pin, "tree": tree}:
        raise ValueError("Canonical-source handoff differs from prepared snapshot")
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
