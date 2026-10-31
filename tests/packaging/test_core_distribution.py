"""Dependency-resolved OP-01 installations from both hardened build paths."""

from __future__ import annotations

import json
import shutil
import sys
import zipfile
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


@pytest.fixture(scope="module")
def core_distributions(tmp_path_factory):
    base = tmp_path_factory.getbasetemp()
    while base.name.startswith("popen-gw"):
        base = base.parent
    env = package_build_environment()
    project = ROOT / "packages/core"
    products = build_once(
        base / "core-package-distributions",
        lambda work: make_package_distributions(work, project, env),
        inputs=lambda: package_build_inputs(project, env),
    )
    return env, products


@pytest.mark.parametrize("variant", ["wheel", "sdist_wheel"])
def test_minimal_core_dependency_resolved_op01(core_distributions, tmp_path, variant):
    env, products = core_distributions
    wheel = products[variant]
    dependencies = dependency_wheels(products, variant=variant)
    assert len(dependencies) == 1
    artifact_members = {}
    for artifact in (wheel, *dependencies):
        with zipfile.ZipFile(artifact) as archive:
            for name in archive.namelist():
                if name.startswith("repo_catalog/") and not name.endswith("/"):
                    assert name not in artifact_members, name
                    artifact_members[name] = artifact.name
    assert "repo_catalog/adapters/sqlite/git_core.py" in artifact_members
    assert "repo_catalog/domain/shared_values.py" in artifact_members
    forbidden = (
        "production_context",
        "p1_context",
        "access_",
        "acquisition",
        "search",
        "exchange",
        "production_query.py",
    )
    for name in artifact_members:
        if name == "repo_catalog/cli/production_query.py":
            continue
        assert not any(part in name for part in forbidden), name

    outside = tmp_path / "outside"
    outside.mkdir()
    links = tmp_path / "allowed-artifacts"
    links.mkdir()
    for artifact in (wheel, *dependencies):
        shutil.copy2(artifact, links / artifact.name)
    venv = tmp_path / "venv"
    run = package_build_runner
    run(["uv", "venv", venv, "--python", sys.executable, "--offline"], outside, env)
    python = venv / "bin/python"
    before = sorted(p.relative_to(outside).as_posix() for p in outside.rglob("*"))
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
            "repo-catalog-core==0.2.0",
        ],
        outside,
        env,
    )
    assert (
        sorted(p.relative_to(outside).as_posix() for p in outside.rglob("*")) == before
    )
    driver = outside / "core_op01_probe.py"
    shutil.copy2(ROOT / "tests/support/core_op01_probe.py", driver)
    shutil.copy2(
        ROOT / "tests/support/network_guard/sitecustomize.py",
        outside / "sitecustomize.py",
    )
    receipt = outside / "op01.json"
    run([python, "-I", driver, receipt], outside, env)
    evidence = json.loads(receipt.read_text())
    assert evidence["result"] == "passed"
    assert evidence["installed_distributions"] == [
        "repo-catalog-contracts",
        "repo-catalog-core",
    ]
    assert len(evidence["checks"]) >= 19
