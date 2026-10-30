"""Adversaries for authored legacy-to-target reconciliation and physical drift."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "audit_p1_schema", ROOT / "scripts/audit_p1_schema.py"
)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


@pytest.fixture(scope="module")
def evidence():
    return json.loads(AUDIT.MANIFEST.read_text()), AUDIT.introspect()


def test_all_84_tables_and_every_physical_column_are_reconciled(evidence):
    manifest, actual = evidence
    AUDIT.validate_routes(manifest, actual)
    assert len(manifest["legacy_tables"]) == 84
    assert manifest["target_schemas"] == actual


def test_audit_command_checks_recorded_constraints():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/audit_p1_schema.py"), "--check"],
        text=True,
        capture_output=True,
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "zero unclassified" in result.stdout


@pytest.mark.parametrize("remove", ["table", "column"])
def test_omitted_baseline_evidence_fails_closed(evidence, remove):
    manifest, actual = copy.deepcopy(evidence)
    if remove == "table":
        manifest["legacy_tables"].pop("repositories")
    else:
        manifest["legacy_tables"]["repositories"]["columns"].pop("repository_uuidv4")
    with pytest.raises(ValueError, match="omitted or unclassified"):
        AUDIT.validate_routes(manifest, actual)


def test_stale_target_column_is_not_accepted_as_a_concrete_successor(evidence):
    manifest, actual = copy.deepcopy(evidence)
    column = manifest["legacy_tables"]["repositories"]["columns"]["repository_uuidv4"]
    column["targets"][0]["columns"] = ["removed_target_column"]
    with pytest.raises(ValueError, match="missing concrete target column"):
        AUDIT.validate_routes(manifest, actual)


def test_new_target_table_requires_ownership_and_retention_contract(evidence):
    manifest, actual = copy.deepcopy(evidence)
    actual["context"]["tables"]["unclassified_new_authority"] = {}
    with pytest.raises(ValueError, match="Unclassified target ownership"):
        AUDIT.validate_routes(manifest, actual)


def test_elimination_cannot_silently_discard_a_mapped_fact(evidence):
    manifest, actual = copy.deepcopy(evidence)
    column = manifest["legacy_tables"]["repositories"]["columns"]["repository_uuidv4"]
    column["targets"] = []
    with pytest.raises(ValueError, match="exactly one concrete route or elimination"):
        AUDIT.validate_routes(manifest, actual)


def test_authoritative_context_cannot_be_reclassified_as_disposable(evidence):
    manifest, actual = copy.deepcopy(evidence)
    contract = next(
        value
        for key, value in manifest["target_contracts"].items()
        if key.startswith("context.")
    )
    contract["durability"] = "reconstructible"
    with pytest.raises(ValueError, match="incorrect durability owner"):
        AUDIT.validate_routes(manifest, actual)


def test_isolated_target_exclusion_does_not_hide_production_runtime_imports():
    spec = importlib.util.spec_from_file_location(
        "callsite_audit", ROOT / "scripts/audit_callsite_dependencies.py"
    )
    assert spec is not None and spec.loader is not None
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    isolated = baseline.ISOLATED_P1_MODULES
    for relative in isolated:
        assert (ROOT / relative).is_file(), relative
    for path in (ROOT / "src/repo_catalog").rglob("*.py"):
        if not baseline.is_baseline_source(path):
            continue
        package = ".".join(path.parent.relative_to(ROOT / "src").parts)
        assert not baseline.isolated_runtime_imports(path.read_text(), package), (
            f"Isolated target imported by public runtime: {path}"
        )


@pytest.mark.parametrize(
    "source",
    [
        "import repo_catalog.domain.p1_core as core",
        "from repo_catalog.domain import ref_observation",
        "from repo_catalog.domain import p1_core",
        "from repo_catalog.adapters.sqlite.git_core import GitCore",
        "from repo_catalog.adapters.sqlite import production_context",
        "from ..domain import git_native",
        "from .sqlite.production_context import Context",
        "from repo_catalog.domain.ports.production_context import ContextPersistence",
        "from repo_catalog.domain.resource_identification import ResourceIdentification",
        "from repo_catalog.domain import resource_stage",
        "from repo_catalog.domain import context_admission",
        "from repo_catalog.domain.ports.context_authorization import AuthorizationPolicy",
        "from repo_catalog.adapters.sqlite import context_admission",
        "from .sqlite.context_admission import AdmissionTransactions",
        "from repo_catalog.application.notes import NotesAcquisition",
        "from repo_catalog.application.acquisition import GitAcquisition",
        "from repo_catalog.application.exchange import ExchangeService",
        "from repo_catalog.application.production_query import ProductionQueryService",
        "from repo_catalog.cli import production_query",
    ],
)
def test_public_runtime_guard_detects_every_isolated_stage(source):
    spec = importlib.util.spec_from_file_location(
        "callsite_audit", ROOT / "scripts/audit_callsite_dependencies.py"
    )
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    assert baseline.isolated_runtime_imports(source, "repo_catalog.adapters")


def test_alias_removal_does_not_erase_semantic_table_successor(evidence):
    manifest, actual = copy.deepcopy(evidence)
    manifest["legacy_tables"]["coverage_claim_markers"].pop("target_tables")
    with pytest.raises(ValueError, match="concrete table successor"):
        AUDIT.validate_routes(manifest, actual)


def test_i6a_admission_modules_are_explicitly_owned_without_prefix_exclusion():
    spec = importlib.util.spec_from_file_location(
        "callsite_audit", ROOT / "scripts/audit_callsite_dependencies.py"
    )
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    for path in (
        "domain/context_admission.py",
        "domain/ports/context_authorization.py",
        "adapters/sqlite/context_admission.py",
    ):
        assert "src/repo_catalog/" + path in baseline.ISOLATED_TARGET_MODULES
        future = ROOT / ("src/repo_catalog/" + path.replace(".py", "_future.py"))
        assert baseline.is_baseline_source(future)
