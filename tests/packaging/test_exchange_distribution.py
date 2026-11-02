"""Actual resolved export/reception minima, with optional implementations absent."""

import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.application.git_acquisition import GitAcquisition
from repo_catalog.domain.git_acquisition import (
    GitNativeAcquisitionRequest,
    NotesAcquisitionSpec,
)
from tests.integration.p5.conftest import build_sample_git_repo
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
def exchange_distributions(tmp_path_factory):
    env = package_build_environment()
    products = {}
    for name in ("exchange", "operational"):
        project = ROOT / "packages" / name
        products[name] = build_once(
            tmp_path_factory.getbasetemp() / (name + "-distributions"),
            lambda work, project=project: make_package_distributions(
                work, project, env
            ),
            inputs=lambda project=project: package_build_inputs(project, env),
        )
    return env, products


def source_fixture(outside):
    """A producer may use G; its closed Core alone enters the independent consumer."""
    producer = outside / "producer"
    producer.mkdir()
    repository, instance = str(uuid4()), str(uuid4())
    for role in ("core", "operational"):
        initialize(producer / (role + ".sqlite3"), role, repository, instance)
    source = outside / "source.git"
    objects = build_sample_git_repo(source, "sha1")
    request = GitNativeAcquisitionRequest(
        repository,
        str(uuid4()),
        str(uuid4()),
        "synthetic-exchange-producer",
        1700000000000000,
        select_object_oids=(objects["commit2"],),
        include_refs=True,
        notes=NotesAcquisitionSpec(
            discover_notes=True,
            acquire_inventories=True,
            target_object_oids=(objects["commit2"],),
        ),
    )
    GitAcquisition(producer / "core.sqlite3", operational=producer).acquire_from_native(
        GitNativeSource(source), request, new_request=True
    )
    assert not (producer / "core.sqlite3-wal").exists()
    destination = outside / "source"
    destination.mkdir()
    shutil.copy2(producer / "core.sqlite3", destination / "core.sqlite3")
    return repository


@pytest.mark.parametrize("receive", [False, True], ids=["export", "receive"])
@pytest.mark.parametrize("variant", ["wheel", "sdist_wheel"])
def test_exchange_minimum(exchange_distributions, tmp_path, receive, variant):
    env, products = exchange_distributions
    artifacts = [
        products["exchange"][variant],
        *dependency_wheels(products["exchange"], variant=variant),
    ]
    if receive:
        artifacts.append(products["operational"][variant])
    assert len(artifacts) == (5 if receive else 4)
    owners = {}
    for artifact in artifacts:
        with zipfile.ZipFile(artifact) as archive:
            for name in archive.namelist():
                if name.startswith("repo_catalog/") and not name.endswith("/"):
                    assert name not in owners, name
                    owners[name] = artifact.name
    assert owners["repo_catalog/application/exchange.py"].startswith(
        "repo_catalog_exchange-"
    )
    for relative in (
        "domain/p1_context.py",
        "adapters/sqlite/p1_coordination.py",
        "adapters/sqlite/paired_admission.py",
        "application/git_acquisition.py",
        "application/acquisition.py",
        "application/search_query.py",
        "application/exchange_service.py",
        "adapters/sqlite/exchange.py",
        "adapters/sqlite/p1_ddl/context.sql",
        "adapters/sqlite/p1_ddl/search.sql",
    ):
        assert "repo_catalog/" + relative not in owners, relative
    if not receive:
        assert "repo_catalog/adapters/sqlite/acquisition.py" not in owners
        assert "repo_catalog/adapters/sqlite/p1_ddl/operational.sql" not in owners
    outside = tmp_path / "consumer"
    outside.mkdir()
    repository = source_fixture(outside)
    (outside / "fixture.json").write_text(
        json.dumps({"repository": repository, "receive": receive})
    )
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
            "repo-catalog-exchange==0.2.0",
            *(("repo-catalog-operational==0.2.0",) if receive else ()),
        ],
        outside,
        env,
    )
    assert (
        sorted(p.relative_to(outside).as_posix() for p in outside.rglob("*")) == before
    )
    for name in ("exchange_probe.py",):
        shutil.copy2(ROOT / "tests/support" / name, outside / name)
    shutil.copy2(
        ROOT / "tests/support/network_guard/sitecustomize.py",
        outside / "sitecustomize.py",
    )
    receipt = outside / "result.json"
    run([python, "-I", outside / "exchange_probe.py", receipt], outside, env)
    result = json.loads(receipt.read_text())
    assert result["result"] == "passed"
    result["artifacts"] = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts
    }
    receipt.write_text(json.dumps(result, indent=2) + "\n")
