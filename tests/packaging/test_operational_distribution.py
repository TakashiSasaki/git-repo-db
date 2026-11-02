"""Operational accounting installs without concrete authority/acquisition code."""

import hashlib
import json
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


@pytest.fixture(scope="module")
def operational_distributions(tmp_path_factory):
    project = ROOT / "packages/operational"
    env = package_build_environment()
    products = build_once(
        tmp_path_factory.getbasetemp() / "operational-distributions",
        lambda work: make_package_distributions(work, project, env),
        inputs=lambda: package_build_inputs(project, env),
    )
    return env, products


@pytest.mark.parametrize("variant", ["wheel", "sdist_wheel"])
def test_operational_only(operational_distributions, tmp_path, variant):
    env, products = operational_distributions
    artifacts = (products[variant], *dependency_wheels(products, variant=variant))
    assert len(artifacts) == 3
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
            "repo-catalog-operational==0.2.0",
        ],
        outside,
        env,
    )
    assert (
        sorted(p.relative_to(outside).as_posix() for p in outside.rglob("*")) == before
    )
    driver = outside / "operational_probe.py"
    shutil.copy2(ROOT / "tests/support/operational_probe.py", driver)
    shutil.copy2(
        ROOT / "tests/support/network_guard/sitecustomize.py",
        outside / "sitecustomize.py",
    )
    result = outside / "result.json"
    run([python, "-I", driver, result], outside, env)
    receipt = json.loads(result.read_text())
    assert receipt["result"] == "passed"
    receipt["artifacts"] = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts
    }
    result.write_text(json.dumps(receipt, indent=2) + "\n")
