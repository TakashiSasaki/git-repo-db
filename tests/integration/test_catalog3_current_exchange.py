"""Mutable exchange converges with domain data and sealed page receipts only."""

import copy
import json
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.sqlite.coverage import admit_claim, freeze_complete_proof
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.schema import DDL_SHA256, SCHEMA_VERSION, schema_sql
from repo_catalog.application.repository_identity import bind
from repo_catalog.domain.current_state import fingerprint_candidate
from tests.integration.test_catalog3_current_queries import (
    current_catalog as current_catalog,
)
from tests.integration.test_catalog3_exchange import receive


def receiver():
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.executescript(schema_sql())
    db.execute(
        "INSERT INTO database_identity VALUES(1,'repo-catalog/catalog3',?,?,0,?,'validated')",
        (SCHEMA_VERSION, str(uuid.uuid4()), DDL_SHA256),
    )
    return db


def collection(catalog, candidate, *, observed=0, pages=1, context=None):
    db = catalog.store.connection
    scope, ident = str(uuid.uuid4()), str(uuid.uuid4())
    db.execute(
        "INSERT INTO resume_scopes(resume_scope_id,repository_uuidv4,repository_binding_id,endpoint,request_context,parser_version,profile_version,confidence) VALUES(?,?,?,'synthetic',?,'test','test','proven')",
        (scope, catalog.repository, catalog.binding, json.dumps(context or {})),
    )
    db.execute(
        "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,kind,resume_scope_id) VALUES(?,?,'issue',?)",
        (ident, catalog.repository, scope),
    )
    proof = CurrentCollectionProof(db)
    member = {
        "family": "issue",
        "kind": candidate["kind"],
        "service_instance_uuidv4": catalog.service,
        "provider_resource_id": candidate["provider_resource_id"],
        "state_digest": fingerprint_candidate(candidate),
    }
    for ordinal in range(pages):
        proof.page(
            ident,
            ordinal,
            observed + ordinal,
            "next" if ordinal < pages - 1 else None,
            [member] if ordinal == 0 else [],
            parser_module=candidate["parser_module"],
            parser_version=candidate["parser_version"],
        )
    db.execute(
        "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,?,'complete',?,?)",
        (scope, ident, json.dumps(proof.evidence(ident)), observed + pages - 1),
    )
    return ident


@pytest.mark.parametrize("order", [(0, 1), (1, 0)])
def test_current_edits_reversed_repeat_and_archive_free_selection(
    current_catalog, order
):
    source = current_catalog
    first = source.candidate("issue", "10", "first body", title="first title")
    assert source.admit(first).status == "accepted"
    selected = collection(source, first, observed=-1)
    old = Graph(source.store.connection).export(
        source.repository, fetch_collection_id=selected
    )
    newer = {
        **first,
        "body": "new body",
        "provider_updated_at_us": 2,
        "observed_at_us": 3,
    }
    assert source.admit(newer).status == "accepted"
    new = Graph(source.store.connection).export(
        source.repository, fetch_collection_id=selected
    )
    assert not {"fetch_occurrences", "parsed_results", "stored_bytes", "payloads"} & {
        r["table"] for r in new["records"]
    }
    # The old receipt still describes the old observation after the body edit.
    assert next(
        r for r in old["records"] if r["table"] == "current_collection_pages"
    ) == next(r for r in new["records"] if r["table"] == "current_collection_pages")
    target = receiver()
    try:
        units = [old, new]
        for index in order:
            unit = copy.deepcopy(units[index])
            unit["records"].reverse()
            assert receive(target, unit)["staged_records"] == 0
        assert target.execute(
            "SELECT b.body FROM issue_resources r JOIN text_bodies b ON b.sha256=r.text_body_sha256"
        ).fetchall() == [("new body",)]
        assert target.execute("SELECT count(*) FROM issue_resources").fetchone() == (1,)
        assert target.execute("SELECT count(*) FROM parsed_results").fetchone() == (0,)
        assert receive(target, new)["received_records"] == 0
        assert target.execute(
            "SELECT count(*) FROM local_parser_profile_verification_trust"
        ).fetchone() == (0,)
        assert target.execute(
            "SELECT count(*) FROM eligible_issue_resources"
        ).fetchone() == (1,)
        assert target.execute("SELECT count(*) FROM parser_profiles").fetchone() == (0,)
        assert target.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        target.close()


def test_unordered_conflict_survives_reexport_and_newer_resolves(current_catalog):
    source = current_catalog
    first = source.candidate("issue", "10", "incumbent")
    assert source.admit(first).status == "accepted"
    alternative = {**first, "body": "unordered alternative", "observed_at_us": 99}
    assert source.admit(alternative).status == "conflict"
    unit = Graph(source.store.connection).export(source.repository)
    assert sum(r["table"] == "issue_resources" for r in unit["records"]) == 2
    a, b = receiver(), receiver()
    try:
        assert receive(a, unit)["staged_records"] == 1
        reverse = copy.deepcopy(unit)
        reverse["records"].reverse()
        assert receive(b, reverse)["staged_records"] == 1
        assert a.execute(
            "SELECT reason FROM current_resource_diagnostics"
        ).fetchall() == [("current_state:conflict",)]
        assert receive(a, unit)["received_records"] == 0
        onward = Graph(a).export(source.repository)
        assert sum(r["table"] == "issue_resources" for r in onward["records"]) == 2
        newer = {**first, "body": "resolved value", "provider_updated_at_us": 2}
        assert source.admit(newer).status == "accepted"
        resolved = Graph(source.store.connection).export(source.repository)
        assert receive(a, resolved)["staged_records"] == 0
        assert receive(b, resolved)["staged_records"] == 0
        for db in (a, b):
            assert db.execute(
                "SELECT b.body FROM issue_resources r JOIN text_bodies b ON b.sha256=r.text_body_sha256"
            ).fetchone() == ("resolved value",)
    finally:
        a.close()
        b.close()


def test_current_completeness_freezes_terminal_pages_and_max_time(current_catalog):
    catalog = current_catalog
    candidate = catalog.candidate("issue", "10", "page member")
    catalog.admit(candidate)
    ident = collection(catalog, candidate, observed=-1, pages=2)
    # The reader fixture's advisory claim at time 1 has no portable proof.
    # A fresh exchange retains its typed scope without fabricating that claim,
    # so the independently proven negative/zero observation can be admitted.
    db, target = receiver(), receiver()
    try:
        assert (
            receive(db, Graph(catalog.store.connection).export(catalog.repository))[
                "staged_records"
            ]
            == 0
        )
        scope = db.execute(
            "SELECT coverage_scope_id FROM coverage_scopes WHERE repository_uuidv4=? AND change_request_id IS NULL AND kind='issue'",
            (catalog.repository,),
        ).fetchone()[0]
        assert db.execute("SELECT count(*) FROM coverage_claims").fetchone() == (0,)
        details = json.dumps({"fetch_collection_ids": [ident]})
        claim = admit_claim(db, scope, "complete", 0, details)
        assert claim is not None
        assert len(db.execute("PRAGMA table_info(coverage_claims)").fetchall()) == 5
        frozen = freeze_complete_proof(db, 0, details)
        assert json.loads(frozen)["completion_marker_uuidv4s"]
        with pytest.raises(sqlite3.IntegrityError, match="sealed"):
            CurrentCollectionProof(db).page(
                ident,
                2,
                1,
                None,
                [],
                parser_module=catalog.parser_module,
                parser_version=catalog.parser_version,
            )
        unit = Graph(db).export(catalog.repository, fetch_collection_id=ident)
        assert receive(target, unit)["staged_records"] == 0
        assert target.execute(
            "SELECT coverage_state,observed_at_us FROM current_coverage WHERE kind='issue'"
        ).fetchone() == ("complete", 0)
        assert target.execute("SELECT count(*) FROM fetch_occurrences").fetchone() == (
            0,
        )
    finally:
        db.close()
        target.close()


def test_receipt_keeps_actual_parser_after_current_module_version_changes(
    current_catalog,
):
    catalog = current_catalog
    candidate = catalog.candidate("issue", "10", "same body")
    catalog.admit(candidate)
    ident = collection(catalog, candidate)
    assert (
        catalog.admit(
            {
                **candidate,
                "body": "newly parsed body",
                "parser_module": "tests.synthetic.next_issue_parser",
                "parser_version": "2",
                "provider_updated_at_us": 2,
            }
        ).status
        == "accepted"
    )
    assert tuple(
        catalog.store.one(
            "SELECT parser_module,parser_version FROM current_collection_pages "
            "WHERE fetch_collection_id=?",
            (ident,),
        )
    ) == (catalog.parser_module, catalog.parser_version)
    unit = Graph(catalog.store.connection).export(
        catalog.repository, fetch_collection_id=ident
    )
    assert not any(
        record["table"].startswith("parser_profile") for record in unit["records"]
    )
    page = next(
        record
        for record in unit["records"]
        if record["table"] == "current_collection_pages"
    )
    row = next(
        record for record in unit["records"] if record["table"] == "issue_resources"
    )
    assert page["values"]["parser_version"] == "1"
    assert row["values"]["parser_version"] == "2"
    assert row["values"]["parser_module"] == "tests.synthetic.next_issue_parser"


def test_current_comment_parent_arrives_after_restart(current_catalog, tmp_path):
    catalog = current_catalog
    parent = catalog.candidate("issue", "10", "parent")
    child = catalog.candidate(
        "issue-comment", "11", "child", parent_provider_resource_id="10"
    )
    catalog.admit(parent)
    catalog.admit(child)
    ident = collection(catalog, child)
    full = Graph(catalog.store.connection).export(
        catalog.repository, fetch_collection_id=ident
    )
    incomplete = copy.deepcopy(full)
    incomplete["records"] = [
        record
        for record in incomplete["records"]
        if not (
            record["table"] == "issue_resources" and record["values"]["kind"] == "issue"
        )
    ]
    path = tmp_path / "parent-late.sqlite3"
    target = receiver()
    disk = sqlite3.connect(path, isolation_level=None)
    target.backup(disk)
    target.close()
    try:
        result = receive(disk, incomplete)
        assert result["staged_records"] > 0
        assert disk.execute("SELECT count(*) FROM issue_resources").fetchone() == (0,)
        disk.close()
        disk = sqlite3.connect(path, isolation_level=None)
        disk.execute("PRAGMA foreign_keys=ON")
        disk.execute("PRAGMA recursive_triggers=ON")
        assert receive(disk, full)["staged_records"] == 0
        assert disk.execute(
            "SELECT kind FROM issue_resources ORDER BY kind"
        ).fetchall() == [("issue",), ("issue-comment",)]
        assert disk.execute("SELECT count(*) FROM parsed_results").fetchone() == (0,)
        assert disk.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        disk.close()


def test_old_repository_receipt_does_not_export_transferred_issue(current_catalog):
    catalog = current_catalog
    first = catalog.candidate("issue", "10", "old membership body")
    catalog.admit(first)
    ident = collection(catalog, first)
    other_repository = str(uuid.uuid4())
    with catalog.store.transaction():
        catalog.store.execute(
            "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'transfer-target','{}')",
            (other_repository,),
        )
        bind(catalog.store, other_repository, catalog.service, "2")
        other_binding = catalog.store.one(
            "SELECT repository_binding_id FROM repository_bindings WHERE repository_uuidv4=?",
            (other_repository,),
        )[0]
        catalog.store.publish()
    moved = {
        **first,
        "repository_uuidv4": other_repository,
        "repository_binding_id": other_binding,
        "provider_issue_number": 2,
        "body": "new repository only body",
        "provider_updated_at_us": 2,
        "acquisition_scope": {
            **first["acquisition_scope"],
            "repository_uuidv4": other_repository,
            "repository_binding_id": other_binding,
        },
    }
    assert catalog.admit(moved).status == "accepted"
    unit = Graph(catalog.store.connection).export(
        catalog.repository, fetch_collection_id=ident
    )
    assert not any(record["table"] == "issue_resources" for record in unit["records"])
    assert not any(record["table"] == "text_bodies" for record in unit["records"])
    target = receiver()
    try:
        outcome = receive(target, unit)
        assert outcome["staged_records"] > 0
        assert target.execute("SELECT count(*) FROM completion_markers").fetchone() == (
            0,
        )
        assert target.execute("SELECT count(*) FROM issue_resources").fetchone() == (0,)
        assert target.execute("SELECT count(*) FROM coverage_claims").fetchone() == (0,)
        assert not target.execute(
            "SELECT 1 FROM repositories WHERE repository_uuidv4=?", (other_repository,)
        ).fetchone()
    finally:
        target.close()


def test_incremental_selection_requires_same_scope_baseline_receipts(current_catalog):
    catalog = current_catalog
    first = catalog.candidate("issue", "10", "initial body")
    catalog.admit(first)
    context = {"incremental_endpoint": "https://synthetic.invalid/issues?state=all"}
    initial = collection(catalog, first, observed=1, context=context)
    baseline = catalog.store.one(
        "SELECT completion_marker_uuidv4 FROM completion_markers WHERE fetch_collection_id=?",
        (initial,),
    )[0]
    edited = {**first, "body": "new body", "provider_updated_at_us": 2}
    catalog.admit(edited)
    later = collection(
        catalog,
        edited,
        observed=3,
        context={**context, "completion_marker_uuidv4": baseline},
    )
    unit = Graph(catalog.store.connection).export(
        catalog.repository, fetch_collection_id=later
    )
    assert (
        sum(record["table"] == "current_collection_pages" for record in unit["records"])
        == 2
    )
    assert not any(record["table"] == "fetch_occurrences" for record in unit["records"])
    incomplete = copy.deepcopy(unit)
    initial_key = next(
        record["key"]
        for record in unit["records"]
        if record["table"] == "fetch_collections"
        and record["values"]["fetch_collection_id"] == initial
    )
    incomplete["records"] = [
        record
        for record in incomplete["records"]
        if not (
            record["table"] == "current_collection_pages"
            and record["values"]["fetch_collection_id"]["$ref"] == initial_key
        )
    ]
    target = receiver()
    try:
        assert receive(target, incomplete)["staged_records"] > 0
        assert target.execute("SELECT count(*) FROM completion_markers").fetchone() == (
            0,
        )
        assert receive(target, unit)["staged_records"] == 0
        assert target.execute("SELECT count(*) FROM completion_markers").fetchone() == (
            2,
        )
        assert target.execute("SELECT count(*) FROM issue_resources").fetchone() == (1,)
    finally:
        target.close()


@pytest.mark.parametrize(
    "manifest",
    [
        None,
        {},
        [None],
        [{"fetch_collection_id": "bad", "page_ordinals": [False]}],
        [{"fetch_collection_id": "bad", "page_ordinals": []}],
        [{"fetch_collection_id": "bad", "page_ordinals": [0], "extra": 1}],
    ],
)
def test_mixed_receipt_manifest_resists_direct_sql_bypass(current_catalog, manifest):
    catalog = current_catalog
    candidate = catalog.candidate("issue", "10", "body")
    catalog.admit(candidate)
    ident = collection(catalog, candidate)
    scope = catalog.store.one(
        "SELECT resume_scope_id FROM fetch_collections WHERE fetch_collection_id=?",
        (ident,),
    )[0]
    with pytest.raises(sqlite3.IntegrityError):
        catalog.store.execute(
            "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,?,'complete',?,0)",
            (
                scope,
                ident,
                json.dumps({"terminal": True, "current_page_collections": manifest}),
            ),
        )
