"""Resolved paired Recovery minima, with unrelated implementations absent."""

import hashlib
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
def paired_recovery_distributions(tmp_path_factory):
    env = package_build_environment()
    project = ROOT / "packages/paired-recovery"
    products = build_once(
        tmp_path_factory.getbasetemp() / "paired-recovery-distributions",
        lambda work: make_package_distributions(work, project, env),
        inputs=lambda: package_build_inputs(project, env),
    )
    return env, products


@pytest.mark.parametrize("variant", [0, 1], ids=["wheel", "sdist-wheel"])
def test_p7_installed_recovery_distribution(
    paired_recovery_distributions, tmp_path, variant
):
    env, products = paired_recovery_distributions
    selected = ("wheel", "sdist_wheel")[variant]
    artifacts = [products[selected], *dependency_wheels(products, variant=selected)]
    assert len(artifacts) == 7
    owners = {}
    for artifact in artifacts:
        with zipfile.ZipFile(artifact) as archive:
            for name in archive.namelist():
                if name.startswith("repo_catalog/") and not name.endswith("/"):
                    assert name not in owners, name
                    owners[name] = artifact.name
    assert owners["repo_catalog/application/recovery.py"].startswith(
        "repo_catalog_paired_recovery-"
    )
    for relative in (
        "application/acquisition.py",
        "application/git_acquisition.py",
        "application/exchange.py",
        "domain/exchange.py",
        "application/paired_query.py",
        "application/production_query.py",
        "adapters/sqlite/p1_coordination.py",
        "adapters/sqlite/access_connections.py",
    ):
        assert "repo_catalog/" + relative not in owners, relative
    outside = tmp_path / "consumer"
    outside.mkdir()
    links = outside / "allowed-artifacts"
    links.mkdir()
    for artifact in artifacts:
        shutil.copy2(artifact, links / artifact.name)
    run = package_build_runner
    venv = tmp_path / "venv"
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
            "repo-catalog-paired-recovery==0.2.0",
        ],
        outside,
        env,
    )
    assert (
        sorted(p.relative_to(outside).as_posix() for p in outside.rglob("*")) == before
    )
    driver = outside / "paired_recovery_probe.py"
    shutil.copy2(ROOT / "tests/support/paired_recovery_probe.py", driver)
    shutil.copy2(
        ROOT / "tests/support/network_guard/sitecustomize.py",
        outside / "sitecustomize.py",
    )
    receipt = outside / "result.json"
    run([python, "-I", driver, receipt], outside, env)
    result = json.loads(receipt.read_text())
    assert result["result"] == "passed"
    result["artifacts"] = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts
    }
    receipt.write_text(json.dumps(result, indent=2) + "\n")
