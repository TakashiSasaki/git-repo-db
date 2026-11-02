"""Dependency-resolved Access-only direct and sdist-derived installed artifacts."""

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
def access_distributions(tmp_path_factory):
    base = tmp_path_factory.getbasetemp()
    while base.name.startswith("popen-gw"):
        base = base.parent
    env = package_build_environment()
    project = ROOT / "packages/access"
    products = build_once(
        base / "access-package-distributions",
        lambda work: make_package_distributions(work, project, env),
        inputs=lambda: package_build_inputs(project, env),
    )
    return env, products


@pytest.mark.parametrize("variant", ["wheel", "sdist_wheel"])
def test_access_without_other_concrete_stores(access_distributions, tmp_path, variant):
    env, products = access_distributions
    assert not dependency_wheels(products, variant=variant)
    outside = tmp_path / "outside"
    outside.mkdir()
    links = tmp_path / "allowed-artifacts"
    links.mkdir()
    wheel = products[variant]
    shutil.copy2(wheel, links / wheel.name)
    venv = tmp_path / "venv"
    run = package_build_runner
    run(["uv", "venv", venv, "--python", sys.executable, "--offline"], outside, env)
    python = venv / "bin/python"
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
            "repo-catalog-access==0.2.0",
        ],
        outside,
        env,
    )
    assert not list(outside.iterdir()), "installation must not initialize any store"
    driver = outside / "access_distribution_probe.py"
    shutil.copy2(ROOT / "tests/support/access_distribution_probe.py", driver)
    receipt = outside / "result.json"
    run([python, "-I", driver, receipt], outside, env)
    evidence = json.loads(receipt.read_text())
    assert evidence["result"] == "passed"
    evidence["artifacts"] = {
        products[key].name: hashlib.sha256(products[key].read_bytes()).hexdigest()
        for key in (variant, "sdist")
    }
    receipt.write_text(json.dumps(evidence, indent=2) + "\n")


@pytest.fixture(scope="module")
def composed_access_distributions(tmp_path_factory):
    base = tmp_path_factory.getbasetemp()
    while base.name.startswith("popen-gw"):
        base = base.parent
    env = package_build_environment()
    products = build_once(
        base / "composed-package-distributions",
        lambda work: make_package_distributions(work, ROOT, env),
        inputs=lambda: package_build_inputs(ROOT, env),
    )
    return env, products


@pytest.mark.parametrize("variant", ["wheel", "sdist_wheel"])
def test_composed_access_acquisition(composed_access_distributions, tmp_path, variant):
    from scripts.verify_access_distribution import ACCESS_SMOKE

    env, products = composed_access_distributions
    outside = tmp_path / "outside"
    outside.mkdir()
    links = tmp_path / "allowed-artifacts"
    links.mkdir()
    artifacts = (products[variant], *dependency_wheels(products, variant=variant))
    assert len(artifacts) == 6
    for artifact in artifacts:
        shutil.copy2(artifact, links / artifact.name)
    # External locked wheels are prepared separately. Local products come only
    # from this build variant and normal dependency resolution, including Access.
    requirements = outside / "third-party.txt"
    requirements.write_text(
        "".join(
            line
            for line in products["requirements"].read_text().splitlines(keepends=True)
            if not line.startswith("file:")
        )
    )
    venv = tmp_path / "venv"
    run = package_build_runner
    run(["uv", "venv", venv, "--python", sys.executable, "--offline"], outside, env)
    python = venv / "bin/python"
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            python,
            "--offline",
            "--find-links",
            links,
            "--requirements",
            requirements,
            "repo-catalog==0.2.0",
        ],
        outside,
        env,
    )
    # Preserve the existing executable A1/A2/A4/A5 smoke, with the unrelated
    # Context Exchange stage excluded explicitly. Source regressions cover retry
    # intent/accounting, stop fencing and absent/damaged Access separately.
    program = (
        ACCESS_SMOKE
        + """
import importlib.metadata, importlib.util
assert importlib.util.find_spec("httpx") is not None
products = {d.metadata["Name"]: d for d in importlib.metadata.distributions() if d.metadata["Name"].startswith("repo-catalog")}
assert set(products) == {"repo-catalog", "repo-catalog-access", "repo-catalog-core", "repo-catalog-context", "repo-catalog-runtime", "repo-catalog-contracts"}
owners = {}
for name, distribution in products.items():
    for member in distribution.files:
        if str(member).startswith("repo_catalog/"):
            assert str(member) not in owners, str(member)
            owners[str(member)] = name
assert owners["repo_catalog/adapters/sqlite/access_schema.py"] == "repo-catalog-access"
print(json.dumps({"result": "passed", "local_git_acquired": True, "inactive_restore_and_fork": True, "installed_distributions": sorted(products), "unique_product_files": len(owners)}))
"""
    )
    evidence = json.loads(run([python, "-I", "-c", program], outside, env))
    assert evidence["result"] == "passed"
    evidence["artifacts"] = {
        artifact.name: hashlib.sha256(artifact.read_bytes()).hexdigest()
        for artifact in artifacts
    }
    (outside / "composed-result.json").write_text(json.dumps(evidence, indent=2) + "\n")
