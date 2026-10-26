"""Build immutable package inputs once per pytest invocation, across workers."""

import fcntl
import hashlib
import inspect
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from scripts.check_sdist_contract import (
    check_sdist,
    compare_wheels,
    save,
    source_inventory,
)

KEYS = {"wheel", "sdist_wheel", "requirements", "sdist", "sdist_contract"}


def package_build_environment():
    """Use one sanitized environment for the ordinary packaging fixtures."""
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
    return env


def package_build_runner(args, cwd, env):
    """The shared checked subprocess contract; tests may supply a hostile runner."""
    result = subprocess.run(
        list(map(str, args)),
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {args}\n{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def make_package_distributions(work, root=None, env=None, wheelhouse=None, runner=None):
    """Build wheel, sdist, requirements and sdist-wheel into work directory."""
    if root is None:
        root = Path(__file__).resolve().parents[2]
    if env is None:
        env = package_build_environment()
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
        if runner is not None:
            return runner(args, cwd, env)
        return package_build_runner(args, cwd, env)

    checked(
        ["uv", "build", "--sdist", *offline_sources, "--out-dir", work / "dist"],
        cwd=root,
    )
    checked(
        ["uv", "build", "--wheel", *offline_sources, "--out-dir", work / "dist"],
        cwd=root,
    )
    sdist = next((work / "dist").glob("*.tar.gz"))
    contract = check_sdist(sdist, root)
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


def package_build_inputs(root, env, wheelhouse=None, runner=None):
    """Bind reuse to bytes, build contract, runtime and effective build settings.

    Paths are not identities. Read working bytes (including untracked product
    files), not HEAD, so edits in the same checkout invalidate reuse. Missing
    required inputs and linked inputs fail before any cached artifact is returned.
    """
    root = Path(root).resolve()
    inventory = source_inventory(root)
    for path in sorted((root / "src/repo_catalog").rglob("*")):
        if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
            continue
        if path.is_symlink():
            raise ValueError("Linked build input")
        if path.is_file():
            inventory[path.relative_to(root).as_posix()] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()
            }
    lock = root / "uv.lock"
    if lock.is_symlink():
        raise ValueError("Linked dependency lock")
    # Archive attack specimens need not contain a lock, but absence is part of
    # their identity and must never match a locked checkout.
    inventory["uv.lock"] = (
        hashlib.sha256(lock.read_bytes()).hexdigest() if lock.is_file() else None
    )
    if wheelhouse is None:
        wheelhouse = Path(
            env.get("REPO_CATALOG_WHEELHOUSE", root / "artifacts/wheelhouse")
        )
    wheelhouse = Path(wheelhouse)
    wheels = {}
    if wheelhouse.exists():
        for path in sorted(wheelhouse.iterdir()):
            if path.is_symlink():
                raise ValueError("Linked wheelhouse input")
            if path.is_file():
                wheels[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    effective_env = dict(env)
    if (wheelhouse / "manifest.json").is_file():
        effective_env["REPO_CATALOG_WHEELHOUSE"] = str(wheelhouse.resolve())
    contract = {
        "schema": 1,
        "source": inventory,
        "wheelhouse": wheels,
        "builder": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "sdist_checker": hashlib.sha256(
            Path(inspect.getfile(check_sdist)).read_bytes()
        ).hexdigest(),
        "runner": inspect.getsource(runner or package_build_runner),
        "python": hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
        "uv": hashlib.sha256(Path(shutil.which("uv")).read_bytes()).hexdigest(),
        # Hash the full environment, never publish values or credentials. This
        # conservatively includes custom backend knobs and reproducibility flags.
        "environment": {
            key: value
            for key, value in effective_env.items()
            if key
            not in {
                "PYTEST_CURRENT_TEST",
                "PYTEST_XDIST_WORKER",
                "PYTEST_XDIST_WORKER_COUNT",
                "PYTEST_XDIST_TESTRUNUID",
            }
        },
    }
    return hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()


def build_once(directory, build, *, inputs):
    fingerprint = inputs()
    if (
        not isinstance(fingerprint, str)
        or len(fingerprint) != 64
        or any(char not in "0123456789abcdef" for char in fingerprint)
    ):
        raise ValueError("Missing/invalid package build input fingerprint")
    directory = Path(directory) / fingerprint
    directory.mkdir(parents=True, exist_ok=True)
    root = directory / "build"
    receipt = directory / "ready.json"
    with (directory / "build.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if inputs() != fingerprint:
            raise ValueError("Package build inputs changed before build")
        if not receipt.exists():
            # No receipt authorizes no reuse. Discard only this cache key's
            # incomplete workspace, then execute the complete checked builder.
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
            if inputs() != fingerprint:
                raise ValueError("Package build inputs changed during build")
            temporary = receipt.with_suffix(".tmp")
            with temporary.open("w") as stream:
                json.dump(
                    {"schema": 1, "inputs": fingerprint, "files": files},
                    stream,
                    sort_keys=True,
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(receipt)
            descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        data = json.loads(receipt.read_text())
        if (
            set(data) != {"schema", "inputs", "files"}
            or data["schema"] != 1
            or data["inputs"] != fingerprint
            or set(data["files"]) != KEYS
        ):
            raise ValueError("Invalid package build receipt")
        products = {}
        for key, item in data["files"].items():
            path = root / item["path"]
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("Package build product escaped its invocation")
            if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError("Package build product changed after publication")
            products[key] = path
        if inputs() != fingerprint:
            raise ValueError("Package build inputs changed during verification")
        return products
