"""Prepare pinned canonical inputs without adding product files to the web tree."""

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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command, cwd, *, env=None):
    subprocess.run([str(x) for x in command], cwd=cwd, env=env, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--product-root",
        type=Path,
        help="Reuse a checkout already at the selected commit",
    )
    args = parser.parse_args()
    pin = json.loads((ROOT / "product-source.json").read_text())
    if pin.get(
        "repository"
    ) != "https://github.com/TakashiSasaki/resource-atlas.git" or not re.fullmatch(
        r"[0-9a-f]{40}", pin.get("commit", "")
    ):
        raise ValueError("Explicit canonical repository/full product commit required")
    product = (
        args.product_root
        or Path(tempfile.gettempdir()) / "resource-atlas-web-products" / pin["commit"]
    ).absolute()
    if (
        product == ROOT
        or ROOT in product.parents
        or any(p.is_symlink() for p in (product, *product.parents))
    ):
        raise ValueError("Product checkout must be outside the web tree and unlinked")
    if not product.exists():
        if args.product_root:
            raise ValueError("Requested existing product checkout is missing")
        product.parent.mkdir(parents=True, exist_ok=True)
        # Full history is needed for the site's explicitly pinned older citations.
        clone_env = dict(os.environ)
        if clone_env.get("GH_TOKEN"):
            index = int(clone_env.get("GIT_CONFIG_COUNT", "0"))
            credential = base64.b64encode(
                ("x-access-token:" + clone_env["GH_TOKEN"]).encode()
            ).decode()
            clone_env.update(
                {
                    "GIT_CONFIG_COUNT": str(index + 1),
                    f"GIT_CONFIG_KEY_{index}": "http.https://github.com/.extraheader",
                    f"GIT_CONFIG_VALUE_{index}": "AUTHORIZATION: basic " + credential,
                }
            )
        run(
            ["git", "clone", "--no-checkout", pin["repository"], product],
            ROOT,
            env=clone_env,
        )
        run(["git", "checkout", "--detach", pin["commit"]], product)
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=product, text=True
    ).strip()
    if actual != pin["commit"]:
        raise ValueError("Existing checkout differs from pin; it was left untouched")
    integrity_spec = importlib.util.spec_from_file_location(
        "web_source_integrity", ROOT / "website/tools/source_integrity.py"
    )
    integrity = importlib.util.module_from_spec(integrity_spec)
    integrity_spec.loader.exec_module(integrity)
    integrity.verify_checkout(product, pin["commit"])
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
            pin["commit"],
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
    target = ROOT / "website/.build/inputs"
    for name in ("inventory.json", "producer.json", "source-manifest.json"):
        private.write_private(ROOT, target / name, (output / name).read_bytes())
    private.write_private_json(
        ROOT,
        target / "product-location.json",
        {"path": str(product), "commit": pin["commit"]},
    )
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
    integrity.verify_checkout(product, pin["commit"])
    print(
        "Prepared pinned product inputs and isolated website Python environment:",
        pin["commit"],
    )


if __name__ == "__main__":
    main()
