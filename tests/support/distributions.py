"""Build immutable package inputs once per pytest invocation, across workers."""

import fcntl
import hashlib
import json
import shutil
from pathlib import Path

KEYS = {"wheel", "sdist_wheel", "requirements"}


def build_once(directory, build):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    root = directory / "build"
    receipt = directory / "ready.json"
    with (directory / "build.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not receipt.exists():
            # A crashed/failed builder has no success receipt. Do not reuse its
            # partial wheel or partially extracted sdist on the next attempt.
            if root.exists():
                shutil.rmtree(root)
            root.mkdir()
            products = build(root)
            if set(products) != KEYS:
                raise ValueError("Missing package build products")
            files = {}
            for key, path in products.items():
                path = Path(path)
                relative = path.resolve().relative_to(root.resolve())
                files[key] = {
                    "path": str(relative),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            temporary = receipt.with_suffix(".tmp")
            temporary.write_text(json.dumps(files, sort_keys=True) + "\n")
            temporary.replace(receipt)
        files = json.loads(receipt.read_text())
        if set(files) != KEYS:
            raise ValueError("Invalid package build receipt")
        products = {}
        for key, item in files.items():
            path = root / item["path"]
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("Package build product escaped its invocation")
            if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError("Package build product changed after publication")
            products[key] = path
        return products
