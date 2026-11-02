"""Actual OP-04 installations with optional concrete owners physically absent."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.acquisition import ProviderIntakeBatch
from repo_catalog.domain.p1_context import (
    FieldClock,
    MappingDisposition,
    MappingOperationEvidence,
    ResourceKey,
    canonical,
)
from tests.integration.p6.conftest import (
    INSTANCE,
    REPOSITORY,
    SERVICE,
    init_catalog,
    populate_rich_catalog,
)
from tests.support.context_admission import AuthorizedProviderAcquisition
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
def paired_query_distributions(tmp_path_factory):
    base = tmp_path_factory.getbasetemp()
    while base.name.startswith("popen-gw"):
        base = base.parent
    env = package_build_environment()
    project = ROOT / "packages/paired-query"
    products = build_once(
        base / "paired-query-distributions",
        lambda work: make_package_distributions(work, project, env),
        inputs=lambda: package_build_inputs(project, env),
    )
    return env, products


@pytest.mark.parametrize("variant", ["wheel", "sdist_wheel"])
def test_paired_query_without_optional_implementations(
    paired_query_distributions, tmp_path, variant
):
    env, products = paired_query_distributions
    artifacts = (products[variant], *dependency_wheels(products, variant=variant))
    assert len(artifacts) == 5
    owners = {}
    for artifact in artifacts:
        with zipfile.ZipFile(artifact) as archive:
            for name in archive.namelist():
                if name.startswith("repo_catalog/") and not name.endswith("/"):
                    assert name not in owners, name
                    owners[name] = artifact.name
    assert "repo_catalog/adapters/sqlite/paired_coordination.py" in owners
    assert "repo_catalog/application/paired_query.py" in owners
    for module in (
        "adapters/sqlite/p1_coordination.py",
        "adapters/sqlite/production_search.py",
        "adapters/sqlite/access_schema.py",
        "application/production_query.py",
        "application/acquisition.py",
        "application/exchange.py",
        "application/recovery.py",
        "domain/production_query.py",
        "cli/query_features.py",
        "cli/main.py",
    ):
        assert "repo_catalog/" + module not in owners, module

    producer = tmp_path / "producer"
    data = populate_rich_catalog(producer, include_core=True, include_context=True)
    plain = ProductionQueryService(producer)
    provider = ResourceKey.from_native(SERVICE, "repository", "1001")
    claim = plain.get_context_resource(provider).repository_relations[0].claim_key
    disposition = MappingDisposition(
        claim,
        "withdraw",
        FieldClock("operation", 200),
        canonical({"source": "synthetic", "evidence": "observed-operation-200"}),
        201,
    )
    AuthorizedProviderAcquisition(producer).admit_batch(
        ProviderIntakeBatch(SERVICE, mapping_dispositions=(disposition,))
    )
    evidence = MappingOperationEvidence(frozenset({disposition.disposition_key}))
    qualified = ProductionQueryService(producer, mapping_evidence=evidence)
    key = data["pr_key"]
    outside = tmp_path / "consumer"
    fixture = outside / "fixture"
    fixture.mkdir(parents=True)
    for role in ("core", "context"):
        for suffix in ("", "-wal", "-shm"):
            name = role + ".sqlite3" + suffix
            if (producer / name).exists():
                shutil.copy2(producer / name, fixture / name)
    # Mix separately initialized valid authorities, rather than bypassing an
    # immutable identity trigger to create a mismatch fixture.
    alternate = "55555555-5555-4555-8555-555555555555"
    for field in ("repository_uuidv4", "catalog_instance_uuidv4"):
        init_catalog(
            outside / "mismatch-fixtures" / field,
            roles=("context",),
            repository_uuidv4=alternate if field == "repository_uuidv4" else REPOSITORY,
            catalog_instance_uuidv4=alternate
            if field == "catalog_instance_uuidv4"
            else INSTANCE,
        )
    manifest = {
        "key": key.coordinates(),
        "repository": REPOSITORY,
        "oid": data["commit_obj"].object_oid.key,
        "body_hex": data["commit_obj"].body.hex(),
        "paired": plain.get_paired_resource(key, include_core_bytes=True).to_dict(),
        "context_only": ProductionQueryService(producer, mode="context_only")
        .get_context_resource(key)
        .to_dict(),
        "listing": [v.to_dict() for v in plain.list_paired_resources().items],
        "qualified": [v.to_dict() for v in qualified.list_paired_resources().items],
        "disposition_key": disposition.disposition_key.coordinates(),
        "files": {
            role: hashlib.sha256(
                (fixture / (role + ".sqlite3")).read_bytes()
            ).hexdigest()
            for role in ("core", "context")
        },
    }
    (outside / "fixture.json").write_text(json.dumps(manifest))
    links = tmp_path / "allowed-artifacts"
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
            "repo-catalog-paired-query==0.2.0",
        ],
        outside,
        env,
    )
    assert (
        sorted(p.relative_to(outside).as_posix() for p in outside.rglob("*")) == before
    )
    driver = outside / "paired_query_probe.py"
    shutil.copy2(ROOT / "tests/support/paired_query_probe.py", driver)
    shutil.copy2(
        ROOT / "tests/support/network_guard/sitecustomize.py",
        outside / "sitecustomize.py",
    )
    receipt = outside / "result.json"
    run([python, "-I", driver, receipt], outside, env)
    result = json.loads(receipt.read_text())
    assert result["result"] == "passed" and len(result["checks"]) == 17
    result["artifacts"] = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts
    }
    receipt.write_text(json.dumps(result, indent=2) + "\n")

    # A separate resolver-created C+T installation has no paired integration.
    missing = tmp_path / "without-integration"
    run(["uv", "venv", missing, "--python", sys.executable, "--offline"], outside, env)
    missing_python = missing / "bin/python"
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            missing_python,
            "--offline",
            "--no-index",
            "--find-links",
            links,
            "repo-catalog-core==0.2.0",
            "repo-catalog-context==0.2.0",
        ],
        outside,
        env,
    )
    program = """
import importlib.metadata, importlib.util, json, subprocess, sys
from pathlib import Path
from repo_catalog.application.core_query import CoreQueryService
from repo_catalog.application.context_query import ContextQueryService
from repo_catalog.domain.p1_context import ResourceKey
assert importlib.util.find_spec("repo_catalog.application.paired_query") is None
assert importlib.util.find_spec("repo_catalog.cli.paired_query_features") is None
products={d.metadata["Name"] for d in importlib.metadata.distributions() if d.metadata["Name"].startswith("repo-catalog")}
assert products=={"repo-catalog-core","repo-catalog-context","repo-catalog-runtime","repo-catalog-contracts"}
fixture=json.loads(Path("fixture.json").read_text()); catalog=Path("fixture")
for cls in (CoreQueryService,ContextQueryService):
 try: cls(catalog,mode="paired").snapshot_token()
 except Exception as error: assert error.code=="MISSING_CAPABILITY"
 else: raise AssertionError("paired silently downgraded")
try: ContextQueryService(catalog).get_context_resource(ResourceKey(*fixture["key"]))
except Exception as error: assert error.code=="MISSING_CAPABILITY"
else: raise AssertionError("auto silently downgraded")
response=subprocess.run([sys.executable,"-I","-m","repo_catalog.cli.production_query","--help"],capture_output=True,text=True,timeout=30)
assert response.returncode==0 and "paired-resource" not in response.stdout and "context-resources" in response.stdout
assert not (catalog/"p1-recovery-stop.json").exists()
print(json.dumps({"result":"passed","installed_distributions":sorted(products),"scope":"missing integration refuses paired"}))
"""
    no_pair = json.loads(run([missing_python, "-I", "-c", program], outside, env))
    (outside / "missing-integration-result.json").write_text(
        json.dumps(no_pair, indent=2) + "\n"
    )
