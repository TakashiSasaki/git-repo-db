"""Dependency-resolved minimal Core installations from both hardened build paths."""

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


def _minimal_installation(core_distributions, tmp_path, variant):
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
        "operational",
        "search",
        "production_query.py",
    )
    for name in artifact_members:
        if name == "repo_catalog/cli/production_query.py":
            continue
        assert not any(part in name for part in forbidden), name

    # Pure typed Ref codecs are Core-owned. Excluding high-level Exchange is
    # established by exact ownership plus the probe's runtime closure checks,
    # rather than banning an incidental filename substring.
    for module in (
        "application/exchange.py",
        "application/ref_exchange.py",
        "domain/exchange.py",
        "adapters/sqlite/exchange.py",
    ):
        assert "repo_catalog/" + module not in artifact_members

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
    return outside, python, env


def _run_probe(core_distributions, tmp_path, variant, probe):
    outside, python, env = _minimal_installation(core_distributions, tmp_path, variant)
    driver = outside / (probe + ".py")
    shutil.copy2(ROOT / "tests/support" / (probe + ".py"), driver)
    shutil.copy2(
        ROOT / "tests/support/network_guard/sitecustomize.py",
        outside / "sitecustomize.py",
    )
    receipt = outside / (probe + ".json")
    package_build_runner([python, "-I", driver, receipt], outside, env)
    evidence = json.loads(receipt.read_text())
    assert evidence["result"] == "passed"
    assert evidence["installed_distributions"] == [
        "repo-catalog-contracts",
        "repo-catalog-core",
    ]
    return evidence


@pytest.mark.parametrize("variant", ["wheel", "sdist_wheel"])
def test_minimal_core_dependency_resolved_op01(core_distributions, tmp_path, variant):
    evidence = _run_probe(core_distributions, tmp_path, variant, "core_op01_probe")
    assert len(evidence["checks"]) >= 19


@pytest.mark.parametrize("variant", ["wheel", "sdist_wheel"])
def test_minimal_core_dependency_resolved_op02(core_distributions, tmp_path, variant):
    evidence = _run_probe(core_distributions, tmp_path, variant, "core_op02_probe")
    assert set(evidence["checks"]) == {
        "physical_absence_unique_owners_and_installed_origins",
        "verified_git_only_backup_with_actual_metadata_bytes",
        "paired_declared_artifact_is_not_downgraded_to_git_only",
        "paired_capability_refused_without_false_corruption",
        "persistent_source_stop_fences_normal_backup",
        "opaque_context_and_sidecars_preserved_without_interpretation",
        "source_bound_work_accumulates_across_output_paths_and_scope_refusal",
        "fresh_restore_receiver_validated_typed_notes_merge_and_replay",
        "supplied_paired_salvage_scope_refused_for_git_only_target",
        "receiver_rejects_changed_note_bytes_while_independent_claims_survive",
        "finite_merge_limit_without_authority_corruption",
        "lost_durable_request_state_fails_closed_without_operational",
        "untrusted_fresh_filename_is_not_a_verified_baseline",
        "unvalidated_context_is_not_promoted_in_git_only_activation",
        "final_retained_byte_validation_stops_damaged_target_before_publication",
        "failed_locator_publication_preserves_previous_locator_and_source",
        "safe_git_only_activation_truthful_receipt_without_optional_databases",
        "complete_zero_retained_body_git_only_lifecycle",
        "runtime_dependency_closure_stays_in_minimal_installed_owners",
    }
