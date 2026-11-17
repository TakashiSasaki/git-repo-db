"""Stored Transfer decoding stops authority; caller iteration stays outside it."""

import json

import pytest

from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.p1_context import (
    FieldClock,
    ProviderEndpointDeclaration,
    TransferEventReport,
    canonical,
)
from repo_catalog.domain.production_context import ContextError
from tests.integration.context_originals import synthetic_parent
from tests.integration.p1.test_context_relations import (
    KEY_EVENT,
    KEY_ISSUE,
    KEY_REPO,
    PROVENANCE_1,
    REPO_1,
    reviewed_transfer_report,
    stored_transfer_fault,
    transfer_context_db,
)

__all__ = ["transfer_context_db"]


@pytest.mark.parametrize(
    "missing",
    ["clock", "parent_members_json", "parent_provenance_json", "parent_scope_json"],
)
def test_missing_stored_transfer_scope_key_stops_production_facade(
    transfer_context_db, tmp_path, missing
):
    db, _store, _path = transfer_context_db
    report = reviewed_transfer_report(
        TransferEventReport.from_targets(
            KEY_EVENT,
            clock=FieldClock("event", 1),
            provenance_json=PROVENANCE_1,
            observed_at_us=1,
            from_target_json=canonical(REPO_1),
            parent_report=synthetic_parent(KEY_EVENT, KEY_ISSUE),
            endpoint_declaration=ProviderEndpointDeclaration(KEY_REPO, "not_reported"),
            endpoints=(("transfer_from_repository", canonical(REPO_1)),),
        )
    )
    scope = json.loads(report.scope_json)
    del scope[missing]
    damaged_scope = canonical(scope)
    endpoint = report.from_relations[0]
    with stored_transfer_fault(db):
        db.execute(
            "INSERT INTO resource_relations(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,members_json,provenance_json,scope_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)",
            (
                *KEY_EVENT.coordinates(),
                "transfer_event_report",
                report.members_json,
                report.provenance_json,
                damaged_scope,
                report.observed_at_us,
            ),
        )
        db.execute(
            "INSERT INTO resource_repository_relations(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,clock_json,target_json,provenance_json,observed_at_us,event_report_members_json,event_report_scope_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                *endpoint.claim_key.coordinates(),
                endpoint.observed_at_us,
                report.members_json,
                damaged_scope,
            ),
        )
    before = list(db.iterdump())
    db.execute("BEGIN")
    try:
        with pytest.raises(ContextError) as failure:
            with Context.for_snapshot(db, tmp_path) as context:
                context.transfer_event_reports()
        assert failure.value.code == "AUTHORITATIVE_CORRUPTION"
        assert isinstance(failure.value.__cause__, ValueError)
        assert missing in str(failure.value.__cause__)
        assert (tmp_path / "p1-recovery-stop.json").is_file()
    finally:
        db.rollback()
    assert list(db.iterdump()) == before


def test_caller_transfer_selection_keyerror_does_not_stop_healthy_facade(
    transfer_context_db, tmp_path
):
    db, _store, _path = transfer_context_db

    def invalid_selection():
        raise KeyError("caller selection")
        yield REPO_1

    db.execute("BEGIN")
    try:
        with Context.for_snapshot(db, tmp_path) as context:
            with pytest.raises(KeyError, match="caller selection"):
                context.transfer_event_reports(
                    selected_repositories=invalid_selection()
                )
            assert not (tmp_path / "p1-recovery-stop.json").exists()
            assert KEY_ISSUE in context.resources()
    finally:
        db.rollback()
    assert not (tmp_path / "p1-recovery-stop.json").exists()
