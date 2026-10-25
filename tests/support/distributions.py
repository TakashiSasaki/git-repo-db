"""Build immutable package inputs once per pytest invocation, across workers."""

import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from scripts.check_sdist_contract import check_sdist, compare_wheels, save

KEYS = {"wheel", "sdist_wheel", "requirements", "sdist", "sdist_contract"}


def make_package_distributions(work, root=None, env=None, wheelhouse=None):
    """Build wheel, sdist, requirements and sdist-wheel into work directory."""
    if root is None:
        root = Path(__file__).resolve().parents[2]
    if env is None:
        env = {
            **os.environ,
            "UV_PYTHON": sys.executable,
            "UV_CACHE_DIR": os.environ.get("UV_CACHE_DIR", "/workspace/.cache/uv"),
        }
        for name in (
            "PYTHONPATH",
            "PYTHONHOME",
            "REPO_CATALOG_TEST_BOOTSTRAP",
            "GH_TOKEN",
            "GITHUB_TOKEN",
        ):
            env.pop(name, None)
    if wheelhouse is None:
        wheelhouse = Path(
            os.environ.get("REPO_CATALOG_WHEELHOUSE", root / "artifacts/wheelhouse")
        ).resolve()

    offline_sources = []
    if (wheelhouse / "manifest.json").is_file():
        env["REPO_CATALOG_WHEELHOUSE"] = str(wheelhouse)
        offline_sources = ["--offline", "--no-index", "--find-links", str(wheelhouse)]
    else:
        offline_sources = ["--offline"]

    def checked(args, cwd):
        res = subprocess.run(
            list(map(str, args)),
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
        )
        if res.returncode != 0:
            raise RuntimeError(
                f"Command failed ({res.returncode}): {args}\n{res.stdout}\n{res.stderr}"
            )
        return res.stdout

    checked(
        ["uv", "build", "--sdist", *offline_sources, "--out-dir", work / "dist"],
        cwd=root,
    )
    checked(
        ["uv", "build", "--wheel", *offline_sources, "--out-dir", work / "dist"],
        cwd=root,
    )
    checked(
        [
            "uv",
            "export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--format",
            "requirements-txt",
            "--output-file",
            work / "requirements.txt",
        ],
        cwd=root,
    )
    sdist = next((work / "dist").glob("*.tar.gz"))
    contract = check_sdist(sdist, root)
    with tarfile.open(sdist) as archive:
        archive.extractall(work / "sdist", filter="data")
    source = next((work / "sdist").iterdir())
    checked(
        [
            "uv",
            "build",
            *offline_sources,
            "--wheel",
            "--out-dir",
            work / "sdist-wheel",
        ],
        cwd=source,
    )
    direct = next((work / "dist").glob("*.whl"))
    derived = next((work / "sdist-wheel").glob("*.whl"))
    contract["wheel_equivalence"] = compare_wheels(
        direct, derived, sdist_metadata=contract["members"]["PKG-INFO"]["sha256"]
    )
    save(work / "sdist-contract.json", contract)
    return {
        "sdist": sdist,
        "sdist_contract": work / "sdist-contract.json",
        "wheel": direct,
        "sdist_wheel": derived,
        "requirements": work / "requirements.txt",
    }


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
