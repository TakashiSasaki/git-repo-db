"""Real Context-reader installations; producer and consumer dependencies stay separate."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

from repo_catalog.application.production_query import ProductionQueryService
from tests.integration.p6.conftest import populate_rich_catalog
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
def context_distributions(tmp_path_factory):
    base = tmp_path_factory.getbasetemp()
    while base.name.startswith("popen-gw"):
        base = base.parent
    env = package_build_environment()
    project = ROOT / "packages/context"
    products = build_once(
        base / "context-package-distributions",
        lambda work: make_package_distributions(work, project, env),
        inputs=lambda: package_build_inputs(project, env),
    )
    return env, products


@pytest.mark.parametrize("variant", ["wheel", "sdist_wheel"])
def test_context_resource_reader_without_concrete_core(
    context_distributions, tmp_path, variant
):
    env, products = context_distributions
    artifacts = (products[variant], *dependency_wheels(products, variant=variant))
    assert len(artifacts) == 3
    owners = {}
    for artifact in artifacts:
        with zipfile.ZipFile(artifact) as archive:
            for name in archive.namelist():
                if name.startswith("repo_catalog/") and not name.endswith("/"):
                    assert name not in owners, name
                    owners[name] = artifact.name
    assert "repo_catalog/adapters/sqlite/production_context.py" in owners
    assert "repo_catalog/adapters/sqlite/p1_ddl/context.sql" in owners
    assert "repo_catalog/adapters/sqlite/p1_ddl/core.sql" not in owners
    for name in owners:
        assert (
            not any(
                part in name
                for part in (
                    "git_core",
                    "core_coordination",
                    "core_schema_functions",
                    "core_recovery",
                    "core_query",
                    "p1_core",
                    "p1_coordination.py",
                )
            )
            or name == "repo_catalog/domain/p1_coordination.py"
        ), name

    # Rich producer uses current typed admission, and closes all capabilities.
    producer = tmp_path / "producer"
    data = populate_rich_catalog(producer, include_core=False, include_context=True)
    key = data["pr_key"]
    service = ProductionQueryService(producer, mode="context_only")
    expected = service.get_context_resource(key, include_text=True).to_dict()
    assert (
        expected["relations"] and expected["fields"] and expected["core_dependencies"]
    )
    assert all(not item["available"] for item in expected["core_dependencies"])
    digest, text = next(iter(expected["resolved_texts"].items()))
    assert service.read_context_text(digest).text_value == text

    outside = tmp_path / "consumer"
    outside.mkdir()
    shutil.copytree(producer, outside / "fixture")
    manifest = {
        "resource": list(key.coordinates()),
        "expected": expected,
        "digest": digest,
        "text": text,
        "context_sha256": hashlib.sha256(
            (producer / "context.sqlite3").read_bytes()
        ).hexdigest(),
    }
    (outside / "fixture.json").write_text(json.dumps(manifest))
    links = tmp_path / "allowed-artifacts"
    links.mkdir()
    for artifact in artifacts:
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
            "repo-catalog-context==0.2.0",
        ],
        outside,
        env,
    )
    assert (
        sorted(p.relative_to(outside).as_posix() for p in outside.rglob("*")) == before
    )
    driver = outside / "context_reader_probe.py"
    shutil.copy2(ROOT / "tests/support/context_reader_probe.py", driver)
    shutil.copy2(
        ROOT / "tests/support/network_guard/sitecustomize.py",
        outside / "sitecustomize.py",
    )
    receipt = outside / "result.json"
    run([python, "-I", driver, receipt], outside, env)
    evidence = json.loads(receipt.read_text())
    assert evidence["result"] == "passed"
    assert len(evidence["checks"]) == 12
    evidence["artifacts"] = {
        artifact.name: hashlib.sha256(artifact.read_bytes()).hexdigest()
        for artifact in artifacts
    }
    receipt.write_text(json.dumps(evidence, indent=2) + "\n")
