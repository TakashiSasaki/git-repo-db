"""Adversarial and transactional security tests for ADR 0031 I7 Recovery.

Covers:
1. Unauthorized / forged service or credential supplied to merge_salvage.
2. Commit-time lease revocation during merge_salvage.
3. G-R1: Context.candidates facade halts authority on corrupted resource identification.
4. G3=A: validate_stored_context_relations rejects TransferEventReport with ineligible parent_issue.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from repo_catalog.adapters.sqlite.core_recovery import is_catalog_stopped
from repo_catalog.adapters.sqlite.p1_schema import (
    connect as p1_connect,
)
from repo_catalog.adapters.sqlite.production_context import Context, ContextError
from repo_catalog.adapters.sqlite.recovery_validation import (
    validate_stored_context_relations,
)
from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.context_admission import (
    AdmissionBudget,
    AdmissionRefused,
    AdmissionSelection,
    ContextAdmissionService,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.p1_context import (
    FieldCandidate,
    FieldClock,
    ProviderEndpointDeclaration,
    ResourceKey,
    TransferEventReport,
    canonical,
)
from repo_catalog.domain.recovery import (
    BackupScope,
    BackupValidationError,
    CandidateType,
    ExtractionStatus,
)
from repo_catalog.domain.resource_identification import ResourceIdentification as RI
from tests.integration.context_originals import synthetic_parent
from tests.support.i6a import isolated_context_db


def test_recovery_merge_salvage_unauthorized_service_refused(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Providing an unauthorized or forged admission service to merge_salvage fails closed."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "unauth_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )

    fresh_dest = tmp_path / "fresh_unauth"
    restore_receipt = service.restore_backup(backup_path, fresh_dest, repo_uuid)
    assert restore_receipt.revalidated_clean

    salvage_file = tmp_path / "salvage_unauth.jsonl"
    cand_sha = hashlib.sha256(b"unauth text").hexdigest()
    record = {
        "candidate_id": cand_sha,
        "candidate_type": CandidateType.CONTEXT_DOCUMENT.value,
        "extraction_provenance": {"store": "context", "table": "text_bodies"},
        "payload": {"sha256": cand_sha, "text_value": "unauth text"},
        "extraction_status": ExtractionStatus.CLEAN.value,
    }
    salvage_file.write_text(json.dumps(record) + "\n", encoding="utf-8")

    # Construct an invalid service that always raises PERMISSION_DENIED
    class ForgedPolicy:
        def lease(self, principal, operation, dependencies):
            raise AdmissionRefused("PERMISSION_DENIED")

    forged_service = ContextAdmissionService(ForgedPolicy(), lambda cred: "attacker")
    forged_adm = forged_service.context(
        "any",
        "salvage_merge",
        AdmissionSelection(all_selected=True),
        AdmissionBudget(),
    )

    # Calling merge_salvage with forged admission rejects candidate under PERMISSION_DENIED
    receipt = service.merge_salvage(
        fresh_dest, salvage_file, authorization=forged_service, admission=forged_adm
    )
    assert receipt.admitted_units == 0
    assert receipt.rejected_units == 1
    assert any("PERMISSION_DENIED" in r["reason"] for r in receipt.rejections)


def test_recovery_merge_salvage_policy_revocation_during_merge(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Commit-time lease revocation rejects candidate without advancing state."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "revocation_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )

    fresh_dest = tmp_path / "fresh_revocation"
    restore_receipt = service.restore_backup(backup_path, fresh_dest, repo_uuid)
    assert restore_receipt.revalidated_clean

    salvage_file = tmp_path / "salvage_revocation.jsonl"
    cand_sha = hashlib.sha256(b"revoked text").hexdigest()
    record = {
        "candidate_id": cand_sha,
        "candidate_type": CandidateType.CONTEXT_DOCUMENT.value,
        "extraction_provenance": {"store": "context", "table": "text_bodies"},
        "payload": {"sha256": cand_sha, "text_value": "revoked text"},
        "extraction_status": ExtractionStatus.CLEAN.value,
    }
    salvage_file.write_text(json.dumps(record) + "\n", encoding="utf-8")

    auth_service, adm_ctx, policy = create_local_admission_service(
        operation="salvage_merge",
        grants=DependencySet(),
        permitted_repositories=frozenset(),
        selection=AdmissionSelection(all_selected=True),
        principal="test-principal",
        credential="test-principal",
    )

    # Revoke policy authority explicitly
    policy.revoke()

    receipt = service.merge_salvage(
        fresh_dest, salvage_file, authorization=auth_service, admission=adm_ctx
    )
    assert receipt.admitted_units == 0
    assert receipt.rejected_units == 1
    assert any("PERMISSION_DENIED" in r["reason"] for r in receipt.rejections)


def test_gr1_candidates_facade_stops_on_corrupted_resource_identification(
    synthetic_catalog, repo_uuid
):
    """G-R1: Context.candidates stops authority when stored Resource identification is corrupted."""
    cat_dir = synthetic_catalog

    res_key = ResourceKey.from_native(
        "11111111-1111-4111-8111-111111111111",
        "document",
        "doc-1",
    )
    ident = RI.global_document(res_key)

    auth_service, adm_ctx, _ = create_local_admission_service(
        operation="provider_intake",
        grants=DependencySet(
            resources={res_key},
            repositories={repo_uuid},
            provider_registrations={res_key.service_instance_uuidv4},
        ),
        permitted_repositories=frozenset({repo_uuid}),
        selection=AdmissionSelection(all_selected=True),
    )

    with Context.transaction(cat_dir, authorization=auth_service) as ctx:
        ctx.provider(res_key.service_instance_uuidv4, "github", admission=adm_ctx)
        ctx.resource(res_key, identification=ident, admission=adm_ctx)
        cand = FieldCandidate(
            resource=res_key,
            field_name="title",
            value_json=canonical("Healthy Title"),
            clock=FieldClock("github", 100),
            provenance_json=canonical({"source": "gh", "evidence": "e1"}),
            observed_at_us=100,
        )
        ctx.admit_field(cand, admission=adm_ctx)

    # Tamper with non-key declaration in SQLite directly
    ctx_db = cat_dir / "context.sqlite3"
    conn = p1_connect(ctx_db, "context")
    trigger_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='trigger' AND name='resources_no_update'"
    ).fetchone()
    assert trigger_row is not None
    trigger_sql = trigger_row[0]

    conn.execute("DROP TRIGGER resources_no_update")
    conn.execute("PRAGMA ignore_check_constraints=ON")
    conn.execute(
        "UPDATE resources SET provider_document_id='\"WRONG\"' WHERE provider_resource_id='\"doc-1\"'"
    )
    conn.execute("PRAGMA ignore_check_constraints=OFF")
    conn.execute(trigger_sql)
    conn.commit()
    conn.close()

    # Calling candidates() on corrupted resource must raise AUTHORITATIVE_CORRUPTION and stop catalog
    with pytest.raises(ContextError) as exc_info:
        with Context.snapshot(cat_dir) as snap:
            snap.candidates(res_key, "title")

    assert "AUTHORITATIVE_CORRUPTION" in str(exc_info.value)
    assert is_catalog_stopped(cat_dir)


def test_g3a_recovery_validation_rejects_ineligible_parent_issue():
    """G3=A: validate_stored_context_relations rejects TransferEventReport with mismatched parent_issue."""
    SERVICE = "aad25448-03eb-4f83-a578-ceec84375b5a"
    KEY_ISSUE = ResourceKey.from_native(SERVICE, "issue", "7")
    KEY_OTHER = ResourceKey.from_native(SERVICE, "issue", "8")
    KEY_REPO = ResourceKey.from_native(SERVICE, "repository", "octocat/Hello-World")
    KEY_EVENT = ResourceKey.timeline_event(KEY_ISSUE, "event-99")
    REPO_1 = "9ebbe38a-f937-40e6-a99c-701835ebcf10"

    parent_obs = synthetic_parent(KEY_EVENT, KEY_OTHER)

    report = TransferEventReport.from_targets(
        KEY_EVENT,
        clock=FieldClock("event", 1),
        provenance_json=canonical(
            {"source": "provider.example", "evidence": "event-1"}
        ),
        from_target_json=canonical(REPO_1),
        observed_at_us=1,
        parent_report=parent_obs,
        endpoint_declaration=ProviderEndpointDeclaration(KEY_REPO, "not_reported"),
        endpoints=(("transfer_from_repository", canonical(REPO_1)),),
    )

    with isolated_context_db() as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("PRAGMA ignore_check_constraints=ON")
        conn.execute('INSERT INTO providers VALUES(?, "github", "{}")', (SERVICE,))
        conn.execute(
            'INSERT INTO repository_context(repository_uuidv4, configuration_json) VALUES(?, "{}")',
            (REPO_1,),
        )
        for k, decl in [
            (KEY_ISSUE, RI.unscoped(KEY_ISSUE)),
            (KEY_OTHER, RI.unscoped(KEY_OTHER)),
            (KEY_REPO, RI.unscoped(KEY_REPO)),
            (KEY_EVENT, RI.scoped(KEY_EVENT, KEY_ISSUE, "timeline_event", "event-99")),
        ]:
            conn.execute(
                "INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id) "
                "VALUES(?,?,?,?,?,?,?)",
                (*k.coordinates(), *decl.columns),
            )

        # Insert parent relation for parent_obs
        conn.execute(
            "INSERT INTO resource_relations VALUES(?,?,?,?,?,?,?,?)",
            (
                *parent_obs.report_key.resource.coordinates(),
                "parent",
                parent_obs.report_key.members_json,
                parent_obs.report_key.provenance_json,
                parent_obs.report_key.scope_json,
                parent_obs.observed_at_us,
            ),
        )

        # Insert transfer_event_report
        conn.execute(
            "INSERT INTO resource_relations VALUES(?,?,?,?,?,?,?,?)",
            (
                *KEY_EVENT.coordinates(),
                "transfer_event_report",
                report.members_json,
                report.report_key.provenance_json,
                report.scope_json,
                1,
            ),
        )

        # Insert endpoint
        endpoint = report.from_relations[0]
        conn.execute(
            "INSERT INTO resource_repository_relations("
            "service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,"
            "clock_json,target_json,provenance_json,observed_at_us,event_report_members_json,event_report_scope_json) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                *endpoint.claim_key.coordinates(),
                endpoint.observed_at_us,
                report.members_json,
                report.scope_json,
            ),
        )
        conn.commit()

        with pytest.raises(BackupValidationError) as exc:
            validate_stored_context_relations(conn)

        assert "G3=A Q-S10 violation" in str(exc.value)
