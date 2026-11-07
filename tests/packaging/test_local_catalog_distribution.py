"""Direct/sdist installed absence tests for the three new catalog packages."""

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from tests.support.distributions import (
    build_once,
    dependency_wheels,
    make_package_distributions,
    package_build_environment,
    package_build_inputs,
    package_build_runner,
)

ROOT = Path(__file__).resolve().parents[2]

PROBE = r"""
import csv
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

scope, destination = sys.argv[1:]
base = Path(destination)
source = base / "source"
source.mkdir()
(source / "data.txt").write_bytes(b"installed artifact bytes")

def available(module):
    try:
        return importlib.util.find_spec(module) is not None
    except ModuleNotFoundError:
        return False

for module in (
    "repo_catalog.adapters.sqlite.git_core",
    "repo_catalog.adapters.sqlite.production_context",
    "repo_catalog.adapters.sqlite.access_schema",
    "repo_catalog.adapters.sqlite.acquisition",
    "repo_catalog.adapters.sqlite.production_search",
    "repo_catalog.adapters.sqlite.catalog_runtime",
):
    assert not available(module), module

names = {d.metadata["Name"] for d in importlib.metadata.distributions()
         if d.metadata["Name"].startswith("repo-catalog")}
allowed = {"repo-catalog-contracts", "repo-catalog-" + scope}
if scope == "local":
    allowed.update({"repo-catalog-filesystem", "repo-catalog-worktrees"})
assert names <= allowed, (names, allowed)
assert "repo-catalog-" + scope in names

if scope == "filesystem":
    assert not available("repo_catalog.worktrees")
    assert not available("repo_catalog.local")
    from repo_catalog.filesystem import FilesystemCatalog
    with FilesystemCatalog.initialize(base / "filesystem.sqlite3") as catalog:
        scan = catalog.scan(source)
        assert scan.status == "complete", scan
        shutil.rmtree(source)
        catalog.export_efu(scan.scan_uuid, base / "files.efu")
elif scope == "worktrees":
    assert not available("repo_catalog.filesystem")
    assert not available("repo_catalog.local")
    from repo_catalog.worktrees import WorktreeCatalog
    subprocess.run(["git", "init", "-b", "main", str(source)],
                   check=True, capture_output=True, timeout=30)
    with WorktreeCatalog.initialize(base / "worktrees.sqlite3") as catalog:
        observation = catalog.discover(source)
        assert observation.status == "complete", observation
        assert any(e.root_path == os.fsencode(source) for e in observation.entries)
        shutil.rmtree(source)
        assert catalog.get_discovery(observation.observation_uuid) == observation
else:
    from repo_catalog.local import LocalCatalog
    with LocalCatalog.initialize(base / "filesystem.sqlite3", base / "worktrees.sqlite3") as catalog:
        result = catalog.scan([source])
        assert result.status == "complete", result
        assert len(result.scans) == 1
        shutil.rmtree(source)
        catalog.export_efu([result.scans[0].scan_uuid], base / "files.efu")

console = Path(sys.executable).with_name(
    "repo-catalog-" + scope + (".exe" if os.name == "nt" else "")
)
if scope == "local":
    arguments = [
        "export", "--filesystem-db", str(base / "filesystem.sqlite3"),
        "--worktrees-db", str(base / "worktrees.sqlite3"),
        "--scan", result.scans[0].scan_uuid,
        "--output", str(base / "console.efu"),
    ]
else:
    arguments = ["--database", str(base / (scope + ".sqlite3")), "verify"]
command = subprocess.run([str(console), *arguments], check=True, capture_output=True,
                         text=True, timeout=30)
console_result = json.loads(command.stdout)
if scope == "filesystem":
    assert console_result["integrity"] == "ok", console_result
else:
    assert console_result["status"] == "complete", console_result

if scope != "worktrees":
    with (base / "files.efu").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    data = next(row for row in rows if row["Filename"].endswith("data.txt"))
    assert data["SHA256"] == hashlib.sha256(b"installed artifact bytes").hexdigest()
assert not any(base.glob("core.sqlite3"))
assert not any(base.glob("context.sqlite3"))
assert not any(base.glob("access.sqlite3"))
assert not any(base.glob("operational.sqlite3"))
assert not any(base.glob("search.sqlite3"))
print(json.dumps({"result": "passed", "scope": scope, "distributions": sorted(names),
                  "console_entrypoint": str(console)}))
"""


@pytest.fixture(scope="module")
def local_catalog_distributions(tmp_path_factory):
    base = tmp_path_factory.getbasetemp()
    while base.name.startswith("popen-gw"):
        base = base.parent
    env = package_build_environment()
    project = ROOT / "packages/local"
    products = build_once(
        base / "local-catalog-distributions",
        lambda work: make_package_distributions(work, project, env),
        inputs=lambda: package_build_inputs(project, env),
    )
    return env, products


@pytest.mark.parametrize("scope", ["filesystem", "worktrees", "local"])
@pytest.mark.parametrize("variant", ["wheel", "sdist_wheel"])
def test_standalone_catalog_installation(
    local_catalog_distributions, tmp_path, scope, variant
):
    env, products = local_catalog_distributions
    outside = tmp_path / "outside"
    outside.mkdir()
    links = tmp_path / "allowed-artifacts"
    links.mkdir()
    for wheel in (products[variant], *dependency_wheels(products, variant=variant)):
        shutil.copy2(wheel, links / wheel.name)
    venv = tmp_path / "venv"
    run = package_build_runner
    run(["uv", "venv", venv, "--python", sys.executable, "--offline"], outside, env)
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            python,
            "--offline",
            "--no-index",
            "--find-links",
            links,
            f"repo-catalog-{scope}==0.2.0",
        ],
        outside,
        env,
    )
    assert not list(outside.iterdir()), "installation must not initialize a catalog"
    receipt = json.loads(run([python, "-I", "-c", PROBE, scope, outside], outside, env))
    assert receipt["result"] == "passed"
