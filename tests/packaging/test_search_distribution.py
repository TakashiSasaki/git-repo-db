"""Resolved OP-05/06 installs, with the other concrete authority absent."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import zipfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.search_query import SearchQuery
from tests.integration.p4.conftest import acquisition
from tests.integration.p5.test_ref_inventory_wiring import run_request
from tests.integration.p5.test_ref_notes_inputs import with_input
from tests.integration.p6.conftest import populate_rich_catalog
from tests.integration.p6.test_ref_search_transition import two_claims
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
def search_distributions(tmp_path_factory):
    base = tmp_path_factory.getbasetemp()
    env = package_build_environment()
    products = {}
    for name in ("search", "core", "context"):
        project = ROOT / "packages" / name
        products[name] = build_once(
            base / (name + "-distributions"),
            lambda work, project=project: make_package_distributions(
                work, project, env
            ),
            inputs=lambda project=project: package_build_inputs(project, env),
        )
    return env, products


def copy_authority(source, destination, role):
    destination.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        path = source / (role + ".sqlite3" + suffix)
        if path.exists():
            shutil.copy2(path, destination / path.name)


@pytest.mark.parametrize("role", ["core", "context"])
@pytest.mark.parametrize("variant", ["wheel", "sdist_wheel"])
def test_search_minimum(search_distributions, tmp_path, role, variant):
    env, products = search_distributions
    artifacts = (
        products["search"][variant],
        *dependency_wheels(products["search"], variant=variant),
        products[role][variant],
    )
    assert len(artifacts) == 4
    owners = {}
    for artifact in artifacts:
        with zipfile.ZipFile(artifact) as archive:
            for name in archive.namelist():
                if name.startswith("repo_catalog/") and not name.endswith("/"):
                    assert name not in owners, name
                    owners[name] = artifact.name
    assert owners["repo_catalog/application/search_query.py"].startswith(
        "repo_catalog_search-"
    )
    other = "context" if role == "core" else "core"
    assert "repo_catalog/domain/p1_" + other + ".py" not in owners
    for name in ("paired_query", "production_query", "acquisition", "exchange"):
        assert "repo_catalog/application/" + name + ".py" not in owners

    producer = tmp_path / "producer"
    data = populate_rich_catalog(
        producer, include_core=role == "core", include_context=role == "context"
    )
    service = ProductionQueryService(producer, mode=role + "_only")
    kinds = ("git_metadata", "notes") if role == "core" else ("context_text",)
    outside = tmp_path / "consumer"
    copy_authority(producer, outside / "fixture", role)
    manifest = {
        "role": role,
        "kinds": kinds,
        "resource": data["pr_key"].coordinates(),
        "expected": service.search(SearchQuery("e", kinds, limit=1000)).to_dict(),
    }
    if role == "core":
        # One representative real local Git producer; only its closed Core
        # enters the consumer. No Operational/acquisition implementation does.
        notes = tmp_path / "notes-producer"
        notes.mkdir()
        generator = acquisition.__wrapped__(
            notes, SimpleNamespace(param=("sha1", True))
        )
        case = next(generator)
        try:
            value, target = two_claims(case)
            run_request(case, with_input(case, value))
            first = replace(
                value,
                claims=(value.claims[0],),
                mapping_groups=(value.mapping_groups[0],),
            )
            run_request(case, with_input(case, first, target_object_oids=(target,)))
            manifest["notes_target"] = target.object_oid
            manifest["notes_coordinate"] = first.claims[0].provenance.coordinate
        finally:
            try:
                next(generator)
            except StopIteration:
                pass
        copy_authority(notes, outside / "exact-notes", role)
    (outside / "fixture.json").write_text(json.dumps(manifest))
    links = tmp_path / "allowed-artifacts"
    links.mkdir()
    for artifact in artifacts:
        shutil.copy2(artifact, links / artifact.name)
    run = package_build_runner
    venv = tmp_path / "venv"
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
            "repo-catalog-search==0.2.0",
            "repo-catalog-" + role + "==0.2.0",
        ],
        outside,
        env,
    )
    driver = outside / "search_probe.py"
    shutil.copy2(ROOT / "tests/support/search_probe.py", driver)
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

    # A distinct resolver-created basic installation proves Search is optional.
    basic = tmp_path / "basic"
    run(["uv", "venv", basic, "--python", sys.executable, "--offline"], outside, env)
    basic_python = basic / "bin/python"
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            basic_python,
            "--offline",
            "--no-index",
            "--find-links",
            links,
            "repo-catalog-" + role + "==0.2.0",
        ],
        outside,
        env,
    )
    run(
        [
            basic_python,
            "-I",
            "-c",
            """
import importlib.util, subprocess, sys
for module in ('application.search_query','domain.search_query','cli.search_query_features','adapters.sqlite.production_search'):
 assert importlib.util.find_spec('repo_catalog.'+module) is None, module
p=subprocess.run([sys.executable,'-I','-m','repo_catalog.cli.production_query','--help'],capture_output=True,text=True,check=True)
assert 'search-rebuild' not in p.stdout
""",
        ],
        outside,
        env,
    )
