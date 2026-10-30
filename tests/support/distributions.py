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
    # Inherit an explicit cache setting; otherwise let uv use the same default
    # as dependency setup rather than selecting a machine-specific empty cache.
    env = {
        **os.environ,
        "UV_PYTHON": sys.executable,
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


def uv_configuration_files(env):
    """Conservative Linux uv 0.12.19 discovery inputs, in search order.

    See uv-dirs::system_config_file / locate_system_config_xdg and etcetera
    0.11's XDG strategy. Snapshot absent candidates too: an earlier config may
    appear without an environment change. We also bind lower-priority candidates
    conservatively; parsing/priority and rejection remain uv's responsibility.
    No configuration contents or values are emitted by this helper.
    """
    if not sys.platform.startswith("linux"):
        raise ValueError("Build configuration discovery is verified on Linux only")
    home = Path(env.get("HOME") or str(Path.home()))
    if not home.is_absolute():
        raise ValueError("Relative HOME cannot bind all build subprocess contexts")
    config_home = Path(env.get("XDG_CONFIG_HOME") or home / ".config")
    # etcetera ignores nonabsolute XDG_CONFIG_HOME and falls back to HOME.
    if not config_home.is_absolute():
        config_home = home / ".config"
    result = {"user": config_home / "uv/uv.toml"}
    directories = env.get("XDG_CONFIG_DIRS") or "/etc/xdg"
    for index, directory in enumerate(directories.split(":")):
        # The pinned uv implementation stops at the first empty component.
        if not directory:
            break
        path = Path(directory)
        if not path.is_absolute():
            # uv allows these, but source and sdist builds have different cwd.
            # Refuse reuse rather than guess another subprocess's input path.
            raise ValueError("Relative XDG_CONFIG_DIRS cannot bind all build contexts")
        result[f"system-xdg/{index}"] = path / "uv/uv.toml"
    result["system-fallback"] = Path("/etc/uv/uv.toml")
    if env.get("UV_CONFIG_FILE"):
        explicit = Path(env["UV_CONFIG_FILE"])
        if not explicit.is_absolute():
            raise ValueError("Relative UV_CONFIG_FILE cannot bind all build contexts")
        result["explicit"] = explicit
    # These redirect uv's project/cwd and require a different multi-cwd recipe.
    if env.get("UV_PROJECT") or env.get("UV_WORKING_DIR"):
        raise ValueError(
            "Redirected uv project/cwd needs an explicit build input contract"
        )
    return result


def backend_control_inputs(root, env):
    """Conservatively bind backend auto-inclusions and discovered configuration.

    Hatchling auto-includes root controls such as hatch.toml, hatch_build.py and
    VCS ignores independently of our product inventory. Hash every root file,
    not a guessed filename allowlist. Also bind inherited VCS exclusions and
    uv's ancestor/user/system or explicitly selected configuration contents.
    Non-file VCS markers matter only as search boundaries, not as Git identity.
    """
    root = Path(root).resolve()
    result = {}

    def record(key, path):
        if path.is_symlink():
            raise ValueError("Linked backend control input: " + str(path))
        if path.exists() and not path.is_file():
            raise ValueError("Non-file backend control input: " + str(path))
        result[key] = (
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        )

    for path in sorted(root.iterdir()):
        if path.name in {".git", ".hg"}:
            continue
        if path.is_symlink() and not path.is_dir():
            raise ValueError("Linked backend root input")
        if path.is_file():
            record("root/" + path.name, path)
    for name, boundary in ((".gitignore", ".git"), (".hgignore", ".hg")):
        for level, directory in enumerate((root, *root.parents)):
            candidate = directory / name
            if candidate.is_file() or candidate.is_symlink():
                record(f"vcs/{name}/{level}", candidate)
                break
            if (directory / boundary).exists():
                break
    for level, directory in enumerate(root.parents):
        for name in ("uv.toml", "pyproject.toml", "hatch.toml", ".python-version"):
            record(f"ancestor/{level}/{name}", directory / name)
    for label, path in uv_configuration_files(env).items():
        record("uv-config/" + label, path)
    return result


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
        "backend_controls": backend_control_inputs(root, env),
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


def build_context_inputs(directory):
    """Bind configuration inherited by generated sdist/build working directories.

    Generated children are controlled by the checked builder and source archive;
    this captures their otherwise ambient cache-directory/ancestor settings.
    """
    result = {}
    root = Path(directory).resolve()
    for level, parent in enumerate((root, *root.parents)):
        for name in (
            "uv.toml",
            "pyproject.toml",
            "hatch.toml",
            ".python-version",
            ".gitignore",
            ".hgignore",
        ):
            path = parent / name
            if path.is_symlink() or (path.exists() and not path.is_file()):
                raise ValueError(
                    "Unsupported linked/non-file build-context configuration"
                )
            result[f"{level}/{name}"] = (
                hashlib.sha256(path.read_bytes()).hexdigest()
                if path.is_file()
                else None
            )
        for boundary in (".git", ".hg"):
            result[f"{level}/{boundary}-boundary"] = (parent / boundary).exists()
    return result


def prepared_build_context_inputs(root):
    """Seal config in generated children as well as the key-specific ancestry."""
    root = Path(root)
    result = {"ancestors": build_context_inputs(root), "generated": {}}
    names = {
        "uv.toml",
        "pyproject.toml",
        "hatch.toml",
        "hatch_build.py",
        ".python-version",
        ".gitignore",
        ".hgignore",
        ".git",
        ".hg",
    }
    for path in sorted(root.rglob("*")):
        if path.name not in names:
            continue
        if path.is_symlink():
            raise ValueError("Linked generated build configuration")
        key = path.relative_to(root).as_posix()
        if path.name in {".git", ".hg"}:
            result["generated"][key] = "boundary"
        elif not path.is_file():
            raise ValueError("Non-file generated build configuration")
        else:
            result["generated"][key] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def build_cache_key(directory, source_fingerprint):
    return hashlib.sha256(
        json.dumps(
            {
                "source": source_fingerprint,
                "build_context": build_context_inputs(directory),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


def build_once(directory, build, *, inputs):
    source_fingerprint = inputs()
    if (
        not isinstance(source_fingerprint, str)
        or len(source_fingerprint) != 64
        or any(char not in "0123456789abcdef" for char in source_fingerprint)
    ):
        raise ValueError("Missing/invalid package build input fingerprint")
    cache_directory = Path(directory)
    fingerprint = build_cache_key(cache_directory, source_fingerprint)
    directory = cache_directory / fingerprint
    directory.mkdir(parents=True, exist_ok=True)
    root = directory / "build"
    receipt = directory / "ready.json"
    with (directory / "build.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (
            inputs() != source_fingerprint
            or build_cache_key(cache_directory, source_fingerprint) != fingerprint
        ):
            raise ValueError("Package build inputs changed before build")
        if not receipt.exists():
            # No receipt authorizes no reuse. Discard only this cache key's
            # incomplete workspace, then execute the complete checked builder.
            if root.exists():
                shutil.rmtree(root)
            root.mkdir()
            ambient_context = build_context_inputs(root)
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
            if (
                inputs() != source_fingerprint
                or build_cache_key(cache_directory, source_fingerprint) != fingerprint
                or build_context_inputs(root) != ambient_context
            ):
                raise ValueError("Package build inputs changed during build")
            temporary = receipt.with_suffix(".tmp")
            with temporary.open("w") as stream:
                json.dump(
                    {
                        "schema": 2,
                        "inputs": fingerprint,
                        "files": files,
                        "build_context": prepared_build_context_inputs(root),
                    },
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
            set(data) != {"schema", "inputs", "files", "build_context"}
            or data["schema"] != 2
            or data["inputs"] != fingerprint
            or set(data["files"]) != KEYS
        ):
            raise ValueError("Invalid package build receipt")
        if prepared_build_context_inputs(root) != data["build_context"]:
            raise ValueError("Prepared build configuration changed after publication")
        products = {}
        for key, item in data["files"].items():
            path = root / item["path"]
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("Package build product escaped its invocation")
            if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError("Package build product changed after publication")
            products[key] = path
        if (
            inputs() != source_fingerprint
            or build_cache_key(cache_directory, source_fingerprint) != fingerprint
            or prepared_build_context_inputs(root) != data["build_context"]
        ):
            raise ValueError("Package build inputs changed during verification")
        return products
