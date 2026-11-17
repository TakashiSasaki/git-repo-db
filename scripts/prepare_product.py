"""Follow main once per preparation, without a maintained product commit pin."""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import re
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GITHUB_HTTP_SCOPE = "https://github.com/"


def run(command, cwd, *, env=None):
    subprocess.run([str(x) for x in command], cwd=cwd, env=env, check=True)


def git_environment():
    environment = dict(os.environ)
    if environment.get("GH_TOKEN"):
        index = int(environment.get("GIT_CONFIG_COUNT", "0"))
        credential = base64.b64encode(
            ("x-access-token:" + environment["GH_TOKEN"]).encode()
        ).decode()
        environment.update(
            {
                "GIT_CONFIG_COUNT": str(index + 2),
                # ls-remote inside actions/checkout inherits its existing header.
                # An empty value resets this multivalue before adding our token.
                f"GIT_CONFIG_KEY_{index}": f"http.{GITHUB_HTTP_SCOPE}.extraheader",
                f"GIT_CONFIG_VALUE_{index}": "",
                f"GIT_CONFIG_KEY_{index + 1}": f"http.{GITHUB_HTTP_SCOPE}.extraheader",
                f"GIT_CONFIG_VALUE_{index + 1}": "AUTHORIZATION: basic " + credential,
            }
        )
    return environment


def prepare_checkout(selection, product_root=None, *, cache=None, env=None):
    """Resolve once; an advancing remote never retargets this attempt."""
    commit = None
    if product_root is None:
        ref = "refs/heads/" + selection["ref"]
        listing = subprocess.check_output(
            ["git", "ls-remote", "--exit-code", selection["repository"], ref],
            env=env,
            text=True,
        ).splitlines()
        if len(listing) != 1:
            raise ValueError("Expected one main branch resolution")
        commit, actual_ref = listing[0].split()
        if not re.fullmatch(r"[0-9a-f]{40}", commit) or actual_ref != ref:
            raise ValueError("Invalid main branch resolution")
        cache = cache or Path(tempfile.gettempdir()) / "resource-atlas-web-products"
        product_root = cache / commit
    product = product_root.absolute()
    if (
        product == ROOT
        or ROOT in product.parents
        or any(p.is_symlink() for p in (product, *product.parents))
    ):
        raise ValueError("Product checkout must be outside the web tree and unlinked")
    if not product.exists():
        if commit is None:
            raise ValueError("Requested existing product checkout is missing")
        product.parent.mkdir(parents=True, exist_ok=True)
        # Historical citations need full history, even when main has advanced.
        run(
            ["git", "clone", "--no-checkout", selection["repository"], product],
            ROOT,
            env=env,
        )
        run(["git", "checkout", "--detach", commit], product, env=env)
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=product, text=True
    ).strip()
    if commit is not None and actual != commit:
        raise ValueError("Cached checkout differs from resolved main; left untouched")
    tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=product, text=True
    ).strip()
    return {
        "schema_version": 2,
        "repository": selection["repository"],
        "requested_ref": selection["ref"],
        "selection_mode": "remote-ref" if commit is not None else "local-override",
        "path": str(product),
        "commit": actual,
        "tree": tree,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--product-root",
        type=Path,
        help="Use an existing checkout's HEAD for local/offline work; record the override",
    )
    args = parser.parse_args()
    selection = json.loads((ROOT / "product-source.json").read_text())
    if selection.get(
        "repository"
    ) != "https://github.com/TakashiSasaki/resource-atlas.git" or (
        selection.get("schema_version") != 2
        or selection.get("ref") != "main"
        or "commit" in selection
    ):
        raise ValueError("Product source must follow the canonical main branch")
    snapshot = prepare_checkout(selection, args.product_root, env=git_environment())
    product = Path(snapshot["path"])
    integrity_spec = importlib.util.spec_from_file_location(
        "web_source_integrity", ROOT / "website/tools/source_integrity.py"
    )
    integrity = importlib.util.module_from_spec(integrity_spec)
    integrity_spec.loader.exec_module(integrity)
    integrity.verify_checkout(product, snapshot["commit"])
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("UV_PROJECT_ENVIRONMENT", None)
    env.pop("RESOURCE_ATLAS_PRODUCT_ROOT", None)
    run(["./scripts/setup-local-python.sh"], product, env=env)
    output = product / "website/.build/inputs" / ("web-" + uuid.uuid4().hex)
    run(
        [
            "scripts/local-run.sh",
            "python",
            "scripts/export_web_inputs.py",
            "--source",
            snapshot["commit"],
            "--output",
            output,
        ],
        product,
        env=env,
    )
    spec = importlib.util.spec_from_file_location(
        "verified_private_outputs", product / "scripts/verification_outputs.py"
    )
    private = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(private)
    run(
        [
            "uv",
            "sync",
            "--locked",
            "--project",
            "website",
            "--python",
            product / ".venv/bin/python",
        ],
        ROOT,
        env=env,
    )
    integrity.verify_checkout(product, snapshot["commit"])
    target = ROOT / "website/.build/inputs"
    for name in ("inventory.json", "producer.json", "source-manifest.json"):
        private.write_private(ROOT, target / name, (output / name).read_bytes())
    private.write_private_json(ROOT, target / "product-location.json", snapshot)
    print(
        "Prepared main-tracking inputs and isolated website Python environment:",
        snapshot["commit"],
        "(" + snapshot["selection_mode"] + ")",
    )


if __name__ == "__main__":
    main()
