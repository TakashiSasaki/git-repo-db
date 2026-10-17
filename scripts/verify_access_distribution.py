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
SMOKE = r"""
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
    from repo_catalog.adapters.sqlite.access_connections import AccessConnections
    from repo_catalog.domain.access_connections import (
        ScopeExecutionContext, RepositoryBinding, ConnectionConfiguration,
        AssignmentKey, LocatorConnection, canonical,
    )
    from repo_catalog.domain.access_registry import AccessRegistryError
    from dataclasses import replace
    repo = str(uuid4())
    context = canonical({"version": 1, "executor_kind": "local", "executor_ref": "installed", "identity_view": "owner", "path_dialect": "posix"})
    options = canonical({"version": 1, "transport": "file", "path_dialect": "posix"})
    key = AssignmentKey(s, "/repos/app.git", "local")
    with AccessConnections(path, writable=True) as store:
        store.set_locator_enabled(again, True)
        store.configure_scope(ScopeExecutionContext(s, context, True))
        store.bind_repository(RepositoryBinding(s, key.locator_text, repo, True))
        profile = ConnectionConfiguration(s, "local", options, True)
        store.configure_connection(profile)
        store.assign_connection(LocatorConnection(key, True))
        plan = store.review_plan(repo, s)
        grant = store.record_local_approval(plan, 10)
        assert store.current_grant(repo, s) == grant
        disabled = replace(profile, enabled=False)
        store.configure_connection(disabled, expected=profile)
        store.configure_connection(profile, expected=disabled)
        try:
            store.current_grant(repo, s)
        except AccessRegistryError as error:
            assert error.code == "APPROVAL_REQUIRED"
        else:
            raise AssertionError("ABA grant resurrection")
    from repo_catalog.application.access_workflow import AccessWorkflow
    from repo_catalog.domain.access_workflow import AccessSelection
    from repo_catalog.adapters.filesystem.access_executor import LocalDirectoryExecutor
    import os, subprocess, sys
    root = Path(directory) / "executor"
    root.mkdir(mode=0o700)
    repository = root / "repo.git"
    repository.mkdir(mode=0o700)
    newest = ScopeLocatorRegistration(s, 30, root.as_uri())
    local_key = AssignmentKey(s, str(repository), "local")
    with AccessConnections(path, writable=True) as store:
        store.register_locator(newest)
        store.set_locator_enabled(newest, True)
        store.bind_repository(RepositoryBinding(s, str(repository), repo, True))
        store.assign_connection(LocatorConnection(local_key, True))
        selected = AccessSelection(repo, s, local_key)
        with AccessWorkflow(store) as workflow:
            workflow.approve(workflow.begin_review(selected), lambda shown: True)
            token = workflow.activate(selected, LocalDirectoryExecutor(), lambda shown: True)
            assert workflow.dispatch_once(token, lambda fd: os.fstat(fd).st_ino, guard=lambda: None) == repository.stat().st_ino
    # Installed read-only CLI needs no TTY. Mutating CLI paths are PTY-tested separately.
    output = subprocess.check_output([sys.executable, "-I", "-m", "repo_catalog.cli.access_workflow", "review", "--access-db", str(path), "--repository", repo, "--scope", s, "--locator", str(repository), "--profile", "local"], text=True)
    assert json.loads(output)["status"] == "review-only"
    assert not (Path(directory) / "core.sqlite3").exists()
print(json.dumps({"sqlite": sqlite3.sqlite_version, "ddl_sha256": fingerprint(), "installed_smoke": "passed"}))
"""


def run(*args: str, cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(
        args, cwd=cwd, env=env, check=True, text=True, capture_output=True
    )
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
        print(
            run(
                sys.executable,
                "-m",
                "hatchling",
                "build",
                "-t",
                "wheel",
                "-t",
                "sdist",
                "-d",
                str(built),
                cwd=ROOT,
                env=env,
            )
        )
        direct = next(built.glob("*.whl"))
        archive = next(built.glob("*.tar.gz"))
        unpacked = base / "sdist"
        unpacked.mkdir()
        with tarfile.open(archive) as source:
            source.extractall(unpacked, filter="data")
        source_root = next(unpacked.iterdir())
        rebuilt = base / "rebuilt"
        rebuilt.mkdir()
        print(
            run(
                sys.executable,
                "-m",
                "hatchling",
                "build",
                "-t",
                "wheel",
                "-d",
                str(rebuilt),
                cwd=source_root,
                env=env,
            )
        )
        for label, wheel in (
            ("wheel", direct),
            ("sdist-wheel", next(rebuilt.glob("*.whl"))),
        ):
            target = base / label
            venv.EnvBuilder(with_pip=False).create(target)
            python = target / "bin/python"
            # Pure Python wheel only; verify all archive members before extracting.
            with zipfile.ZipFile(wheel) as package:
                assert any(
                    name.endswith("access_ddl/registry.sql")
                    for name in package.namelist()
                )
                for name in package.namelist():
                    parts = Path(name).parts
                    if Path(name).is_absolute() or ".." in parts:
                        raise ValueError("unsafe wheel member")
            print(
                run(
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    "--no-deps",
                    str(wheel),
                    cwd=base,
                    env=env,
                )
            )
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
