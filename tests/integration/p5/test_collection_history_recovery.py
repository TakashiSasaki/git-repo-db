"""Actual paired backup/restore retains historical Collection originals."""

from contextlib import closing
from dataclasses import replace

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.pr_assessment import PRQueryService
from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.p1_context import CoverageScope, canonical
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.production_context import CollectionObservation
from repo_catalog.domain.query_work import UnlimitedWorkBudget
from repo_catalog.domain.recovery import BackupScope
from tests.integration.p5.test_selected_collection_exchange import setup
from tests.support.context_admission import fixture_transaction


def history_snapshot(directory):
    with Context.snapshot(directory) as context:
        result = {}
        for table in (
            "resources",
            "field_candidates",
            "text_bodies",
            "collections",
            "collection_terminals",
            "coverage_scopes",
            "coverage_claims",
            "coverage_proofs",
        ):
            rows = context.db.execute(f'SELECT * FROM "{table}"').fetchall()
            result[table] = sorted(rows, key=lambda row: canonical(list(row)))
        result["pair_identity"] = context.db.execute(
            "SELECT repository_uuidv4,catalog_instance_uuidv4 FROM store_identity"
        ).fetchone()
        return result


def test_paired_backup_restore_retains_old_collection_proof_and_newer_partial_originals(
    tmp_path,
):
    fixture, _, key = setup(tmp_path / "source", core=True)
    scope = CoverageScope.collection(fixture.parent, "pr_files", key[4], "pr_files")
    with Context.snapshot(fixture.path) as context:
        original_scope = context.db.execute(
            "SELECT scope_json FROM collections WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND collection_kind=? AND provenance_json=?",
            key,
        ).fetchone()[0]
        terminal = context.db.execute(
            "SELECT observed_at_us,terminal_state,members_json FROM collection_terminals WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND collection_kind=? AND provenance_json=?",
            key,
        ).fetchone()
    old = CollectionObservation(
        fixture.parent,
        "pr_files",
        key[4],
        original_scope,
        600,
        "complete",
        tuple(fixture.files[:2]),
    )
    assert terminal == (old.observed_at_us, old.state, old.members_json)
    assert isinstance(old, CollectionObservation) and old.observed_at_us == 600
    with fixture_transaction(fixture.path, fixture.grants) as context:
        context.collection(
            replace(
                old,
                observed_at_us=700,
                state="partial",
                members=tuple(fixture.files[:1]),
            )
        )
        context.admit_coverage(CoverageClaim(scope, 700, "partial"))
    before = history_snapshot(fixture.path)
    with closing(GitCore(fixture.path / "core.sqlite3")) as core:
        copy = core.sql(
            "SELECT physical_copy_uuidv4 FROM retained_metadata WHERE object_format=? AND object_oid=? ORDER BY physical_copy_uuidv4 LIMIT 1",
            fixture.head.key,
        )[0][0]
        body = core.read_metadata_copy(fixture.head, copy, UnlimitedWorkBudget())[
            "body"
        ]
        assert core.catalog_identity() == before["pair_identity"]
    backup, target = tmp_path / "backup", tmp_path / "restored"
    recovery = RecoveryService()
    recovery.create_consistent_backup(fixture.path, backup, BackupScope.PAIRED)
    receipt = recovery.restore_backup(backup, target, fixture.repository)
    assert receipt.revalidated_clean
    after = history_snapshot(target)
    for table in before.keys() - {"pair_identity"}:
        assert after[table] == before[table]
    with Context.snapshot(target) as context:
        assert context.coverage(scope).state == "partial"
        proof = context.db.execute(
            "SELECT terminal_observed_at_us,terminal_state FROM coverage_proofs WHERE owner_kind=? AND owner_coordinates_json=?",
            (scope.owner_kind, scope.encoded),
        ).fetchone()
        assert proof == (600, "complete")
    captured = PRQueryService(target).get_pr_code_capture(
        fixture.parent, "pr_files", key[4]
    )
    assert captured.state == "partial" and captured.page.total_count == 1
    with closing(GitCore(target / "core.sqlite3")) as core:
        assert core.catalog_identity() == after["pair_identity"]
        assert (
            core.read_metadata_copy(fixture.head, copy, UnlimitedWorkBudget())["body"]
            == body
        )
    assert not (target / "p1-recovery-stop.json").exists()
