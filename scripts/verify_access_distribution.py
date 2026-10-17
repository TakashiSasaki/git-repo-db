"""Build wheel and sdist-derived wheel; smoke each outside checkout on real SQLite.

Uses the locked environment's hatchling. No runtime-version override, no credentials,
no real catalog, no activation. Temporary virtualenvs intentionally contain only
this wheel: the isolated Access registry must not need Provider/HTTP dependencies.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE = r'''
import importlib.util, json, sqlite3, tempfile
from pathlib import Path
from uuid import uuid4
from repo_catalog.adapters.sqlite.access_schema import initialize, require_runtime, fingerprint
from repo_catalog.adapters.sqlite.access_registry import AccessRegistry
from repo_catalog.domain.access_registry import AccessScope, ScopeLocatorRegistration
require_runtime()
assert importlib.util.find_spec("httpx") is None
s = str(uuid4())
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "access.sqlite3"
    initialize(path)
    with AccessRegistry(path, writable=True) as store:
        store.register_scope(AccessScope(s, "installed"))
        a = ScopeLocatorRegistration(s, 1, "file:///a")
        b = ScopeLocatorRegistration(s, 2, "file:///b")
        again = ScopeLocatorRegistration(s, 3, "file:///a")
        for value in (a, b, again):
            store.register_locator(value)
        assert store.first_choices(s) == (again,)
        assert store.history(s).registrations == (again, b, a)
        assert not store.locator_enabled(again)
    assert not (Path(directory) / "core.sqlite3").exists()
print(json.dumps({"sqlite": sqlite3.sqlite_version, "ddl_sha256": fingerprint(), "installed_smoke": "passed"}))
'''


def run(*args: str, cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(args, cwd=cwd, env=env, check=True, text=True, capture_output=True)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.stdout


def main() -> None:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    results = []
    with tempfile.TemporaryDirectory(prefix="access-distribution-") as temporary:
        base = Path(temporary)
        built = base / "built"
        built.mkdir()
        print(run(sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-t", "sdist", "-d", str(built), cwd=ROOT, env=env))
        direct = next(built.glob("*.whl"))
        archive = next(built.glob("*.tar.gz"))
        unpacked = base / "sdist"
        unpacked.mkdir()
        with tarfile.open(archive) as source:
            source.extractall(unpacked, filter="data")
        source_root = next(unpacked.iterdir())
        rebuilt = base / "rebuilt"
        rebuilt.mkdir()
        print(run(sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", str(rebuilt), cwd=source_root, env=env))
        for label, wheel in (("wheel", direct), ("sdist-wheel", next(rebuilt.glob("*.whl")))):
            target = base / label
            venv.EnvBuilder(with_pip=False).create(target)
            python = target / "bin/python"
            # Pure Python wheel only; verify all archive members before extracting.
            with zipfile.ZipFile(wheel) as package:
                assert any(name.endswith("access_ddl/registry.sql") for name in package.namelist())
                for name in package.namelist():
                    parts = Path(name).parts
                    if Path(name).is_absolute() or ".." in parts:
                        raise ValueError("unsafe wheel member")
            print(run("uv", "pip", "install", "--python", str(python), "--no-deps", str(wheel), cwd=base, env=env))
            output = run(str(python), "-I", "-c", SMOKE, cwd=base, env=env)
            result = json.loads(output)
            result["artifact_kind"] = label
            results.append(result)
            print(label, output)
    evidence = ROOT / "artifacts/access-registry"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "distribution.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
