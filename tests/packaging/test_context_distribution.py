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
from repo_catalog.domain.p1_context import CoverageScope
from repo_catalog.domain.search_query import SearchQuery
from tests.integration.p6.conftest import init_catalog, populate_rich_catalog
from tests.support.context_metadata_fixture import prepare_metadata_fixture
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
    metadata = prepare_metadata_fixture(producer, data)
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
    fixture = outside / "fixture"
    fixture.mkdir()
    # Producer construction has richer optional DBs. Transfer only the closed
    # Context authority and any necessary SQLite sidecars, never their code/DBs.
    for name in ("context.sqlite3", "context.sqlite3-wal", "context.sqlite3-shm"):
        path = producer / name
        if path.exists():
            shutil.copy2(path, fixture / name)
    manifest = {
        "metadata": metadata,
        "resource": list(key.coordinates()),
        "expected": expected,
        "digest": digest,
        "text": text,
        "listing": [v.to_dict() for v in service.list_context_resources().items],
        "repository": expected["repository_uuidv4"],
        "context_sha256": hashlib.sha256(
            (producer / "context.sqlite3").read_bytes()
        ).hexdigest(),
    }
    init_catalog(outside / "empty", roles=("context",))
    (outside / "fixture.json").write_text(json.dumps(manifest))
    # Independently modeled Provider intake produces missing/null/unresolved and
    # competing mappings, then attributed disposition reports. Only closed T is
    # copied; no producer acquisition/Core implementation enters the consumer.
    from repo_catalog.domain.acquisition import ProviderIntakeBatch
    from repo_catalog.domain.p1_context import (
        FieldClock,
        MappingDisposition,
        MappingOperationEvidence,
    )
    from tests.integration.i23.test_provider_exchange import (
        producer as mapping_producer,
    )
    from tests.integration.i23.test_provider_exchange import provenance
    from tests.support.context_admission import AuthorizedProviderAcquisition

    mapping_path = tmp_path / "mapping-producer"
    mapping_service, r1, r2, claims = mapping_producer(mapping_path)
    dispositions = tuple(
        MappingDisposition(
            target.claim_key,
            kind,
            FieldClock("operation", 20),
            provenance(kind),
            21,
            claims[3].claim_key if kind == "correct" else None,
        )
        for target, kind in (
            (claims[0], "withdraw"),
            (claims[1], "dispute"),
            (claims[2], "correct"),
        )
    )
    AuthorizedProviderAcquisition(mapping_path).admit_batch(
        ProviderIntakeBatch(mapping_service, mapping_dispositions=dispositions)
    )
    mapping_dest = outside / "mapping"
    mapping_dest.mkdir()
    for name in ("context.sqlite3", "context.sqlite3-wal", "context.sqlite3-shm"):
        if (mapping_path / name).exists():
            shutil.copy2(mapping_path / name, mapping_dest / name)
    confirmed = MappingOperationEvidence(
        frozenset(d.disposition_key for d in dispositions)
    )
    plain = ProductionQueryService(mapping_path, mode="context_only")
    qualified = ProductionQueryService(
        mapping_path, mode="context_only", mapping_evidence=confirmed
    )
    (outside / "mapping.json").write_text(
        json.dumps(
            {
                "service": mapping_service,
                "repositories": [r1, r2],
                "dispositions": [d.disposition_key.coordinates() for d in dispositions],
                "plain": [v.to_dict() for v in plain.list_context_resources().items],
                "qualified": [
                    v.to_dict() for v in qualified.list_context_resources().items
                ],
            }
        )
    )
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
    shutil.copy2(
        ROOT / "tests/support/context_metadata_probe.py",
        outside / "context_metadata_probe.py",
    )
    receipt = outside / "result.json"
    run([python, "-I", driver, receipt], outside, env)
    evidence = json.loads(receipt.read_text())
    assert evidence["result"] == "passed"
    assert len(evidence["checks"]) == 31
    evidence["artifacts"] = {
        artifact.name: hashlib.sha256(artifact.read_bytes()).hexdigest()
        for artifact in artifacts
    }
    receipt.write_text(json.dumps(evidence, indent=2) + "\n")


@pytest.fixture(scope="module")
def composed_distributions(tmp_path_factory):
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
def test_composed_context_reader_artifact_parity(
    composed_distributions, tmp_path, variant
):
    """Changed root dependency metadata must compose the same Resource API/CLI."""
    env, products = composed_distributions
    outside = tmp_path / "outside"
    outside.mkdir()
    catalog = outside / "catalog"
    fixture = populate_rich_catalog(catalog, include_core=True, include_context=True)
    key = fixture["pr_key"]
    expected = {
        mode: ProductionQueryService(catalog, mode=mode)
        .get_context_resource(key)
        .to_dict()
        for mode in ("context_only", "paired")
    }
    assert any(d["available"] for d in expected["paired"]["core_dependencies"])
    assert not any(
        d["available"] for d in expected["context_only"]["core_dependencies"]
    )
    (outside / "expected.json").write_text(
        json.dumps(
            {
                "key": key.coordinates(),
                "paired": ProductionQueryService(catalog, mode="paired")
                .get_paired_resource(key, include_core_bytes=True)
                .to_dict(),
                "views": expected,
                "search": {
                    mode: ProductionQueryService(catalog, mode=mode)
                    .search(SearchQuery("e", limit=1000))
                    .to_dict()
                    for mode in ("core_only", "context_only", "paired")
                },
                "metadata": {
                    mode: {
                        "providers": [
                            v.to_dict()
                            for v in ProductionQueryService(
                                catalog, mode=mode
                            ).list_providers()
                        ],
                        "sources": [
                            v.to_dict()
                            for v in ProductionQueryService(
                                catalog, mode=mode
                            ).list_source_views()
                        ],
                        "coverage": ProductionQueryService(catalog, mode=mode)
                        .get_context_coverage(
                            CoverageScope.collection(
                                fixture["issue_key"],
                                "comments",
                                fixture["ctx_prov_2"],
                                "comments",
                            )
                        )
                        .to_dict(),
                    }
                    for mode in expected
                },
                "listings": {
                    mode: [
                        v.to_dict()
                        for v in ProductionQueryService(catalog, mode=mode)
                        .list_context_resources()
                        .items
                    ]
                    for mode in expected
                },
            }
        )
    )
    venv = tmp_path / "venv"
    run = package_build_runner
    run(["uv", "venv", venv, "--python", sys.executable, "--offline"], outside, env)
    python = venv / "bin/python"
    # Ordinary offline dependency resolution uses the prepared, hash-bound local
    # sibling requirements and locked third-party artifacts already in uv cache.
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
            ROOT / "artifacts/wheelhouse",
            "--requirements",
            products["requirements"],
            products[variant],
        ],
        outside,
        env,
    )
    program = """
import importlib.metadata, json, subprocess, sys, sysconfig
from pathlib import Path
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.p1_context import CoverageScope, ResourceKey
from repo_catalog.domain.search_query import SearchQuery
installed = Path(sysconfig.get_path("purelib")).resolve()
products = {d.metadata["Name"]: d for d in importlib.metadata.distributions() if d.metadata["Name"].startswith("repo-catalog")}
assert set(products) == {"repo-catalog", "repo-catalog-search", "repo-catalog-paired-query", "repo-catalog-access", "repo-catalog-core", "repo-catalog-context", "repo-catalog-runtime", "repo-catalog-contracts"}
owners = {}
for name, distribution in products.items():
    for member in distribution.files:
        if str(member).startswith("repo_catalog/"):
            assert str(member) not in owners, str(member)
            owners[str(member)] = name
fixture = json.loads(Path("expected.json").read_text())
key = ResourceKey(*fixture["key"])
for mode, expected_search in fixture["search"].items():
    reader = ProductionQueryService(Path("catalog"), mode=mode)
    result = reader.search(SearchQuery("e", limit=1000))
    assert json.loads(json.dumps(result.to_dict())) == expected_search
    command = [sys.executable,"-I","-m","repo_catalog.cli.production_query","search","--catalog","catalog","--mode",mode,"--query","e","--limit","1000"]
    searched = subprocess.run(command,capture_output=True,text=True,timeout=30)
    assert searched.returncode == 0, searched.stderr
    assert json.loads(searched.stdout) == expected_search
    reader.rebuild_search()
    assert reader.search(SearchQuery("e", limit=1000)).hits == result.hits
for mode, expected in fixture["views"].items():
    view = ProductionQueryService(Path("catalog"), mode=mode).get_context_resource(key)
    assert json.loads(json.dumps(view.to_dict())) == expected
    reader = ProductionQueryService(Path("catalog"), mode=mode)
    if mode == "paired":
        assert json.loads(json.dumps(reader.get_paired_resource(key, include_core_bytes=True).to_dict())) == fixture["paired"]
        paired = subprocess.run([sys.executable, "-I", "-m", "repo_catalog.cli.production_query", "paired-resource", "--catalog", "catalog", "--mode", mode, "--service", key.service_instance_uuidv4, "--kind", key.resource_kind, "--id", key.provider_resource_id, "--include-core-bytes"], capture_output=True, text=True, timeout=30)
        assert paired.returncode == 0, paired.stderr
        assert json.loads(paired.stdout) == fixture["paired"]
    assert [v.to_dict() for v in reader.list_providers()] == fixture["metadata"][mode]["providers"]
    assert [v.to_dict() for v in reader.list_source_views()] == fixture["metadata"][mode]["sources"]
    coverage = fixture["metadata"][mode]["coverage"]
    assert reader.get_context_coverage(CoverageScope(coverage["owner_kind"], tuple(coverage["owner_coordinates"]))).to_dict() == coverage
    listing = reader.list_context_resources()
    assert json.loads(json.dumps([v.to_dict() for v in listing.items])) == fixture["listings"][mode]
    assert listing.total_count == len(listing.items)
    enumerated = subprocess.run([sys.executable, "-I", "-m", "repo_catalog.cli.production_query", "context-resources", "--catalog", "catalog", "--mode", mode, "--limit", "1"], capture_output=True, text=True, timeout=30)
    assert enumerated.returncode == 0, enumerated.stderr
    assert json.loads(enumerated.stdout)["items"] == fixture["listings"][mode][:1]
    response = subprocess.run([sys.executable, "-I", "-m", "repo_catalog.cli.production_query", "context-resource", "--catalog", "catalog", "--mode", mode, "--service", key.service_instance_uuidv4, "--kind", key.resource_kind, "--id", key.provider_resource_id], capture_output=True, text=True, timeout=30)
    assert response.returncode == 0, response.stderr
    assert json.loads(response.stdout) == expected
for name, module in tuple(sys.modules.items()):
    if name.startswith("repo_catalog.") and getattr(module, "__file__", None):
        assert Path(module.__file__).resolve().is_relative_to(installed), name
print(json.dumps({"result": "passed", "modes": list(fixture["views"]), "installed_distributions": sorted(products), "unique_product_files": len(owners)}))
"""
    evidence = json.loads(run([python, "-I", "-c", program], outside, env))
    assert evidence["result"] == "passed"
    evidence["artifacts"] = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (products[variant], *dependency_wheels(products, variant=variant))
    }
    (outside / "composed-result.json").write_text(json.dumps(evidence, indent=2) + "\n")
