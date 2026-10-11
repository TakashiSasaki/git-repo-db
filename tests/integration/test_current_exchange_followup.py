"""Production exchange regressions for mutable variants and freshness evidence."""

import copy
import json
import sqlite3

import pytest

from repo_catalog.adapters.sqlite.current_resources import CurrentResources
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.exchange_service import ExchangeService
from repo_catalog.application.maintenance_service import MaintenanceService
from tests.integration.test_catalog3_current_exchange import receiver
from tests.integration.test_catalog3_current_queries import (
    current_catalog as current_catalog,
)
from tests.integration.test_catalog3_exchange import receive
from tests.support.sqlite_contracts import assert_absent_tables


def reopen(db, path):
    """Reopen the complete production schema with its required connection flags."""
    disk = sqlite3.connect(path, isolation_level=None)
    db.backup(disk)
    db.close()
    disk.close()
    disk = sqlite3.connect(path, isolation_level=None)
    disk.execute("PRAGMA foreign_keys=ON")
    disk.execute("PRAGMA recursive_triggers=ON")
    return disk


def table_for(kind):
    return "issue_resources" if kind.startswith("issue") else "review_resources"


def candidate(catalog, kind, ident, body, **fields):
    if kind == "issue-comment":
        parent = catalog.candidate("issue", "1", "Issue parent")
        catalog.admit(parent)
        fields["parent_provider_resource_id"] = "1"
    return catalog.candidate(kind, ident, body, **fields)


def body_for(db, kind):
    table = table_for(kind)
    return db.execute(
        f"SELECT b.body FROM {table} r JOIN text_bodies b ON b.sha256=r.text_body_sha256 WHERE r.kind=?",
        (kind,),
    ).fetchone()[0]


@pytest.mark.parametrize("kind", ["issue", "issue-comment", "review", "review-comment"])
@pytest.mark.parametrize("reverse", [False, True])
def test_competing_current_variants_keep_typed_staging_on_later_receipt(
    current_catalog, tmp_path, kind, reverse
):
    catalog = current_catalog
    first = candidate(catalog, kind, "10", "incumbent", provider_updated_at_us=None)
    assert catalog.admit(first).status == "accepted"
    initial = Graph(catalog.store.connection).export(catalog.repository)
    for body in ("alternative B", "alternative C", "alternative D"):
        assert catalog.admit({**first, "body": body}).status == "conflict"
    conflicted = Graph(catalog.store.connection).export(catalog.repository)
    if reverse:
        conflicted["records"].reverse()
    db = receiver()
    try:
        receive(db, initial)
        assert receive(db, conflicted)["staged_records"] == 3
        db = reopen(db, tmp_path / "competing-current.sqlite3")
        # A repeat used to relabel plain candidates as immutable envelopes and
        # raise KeyError('key') while refreshing immutable conflict barriers.
        assert receive(db, conflicted)["staged_records"] == 3
        assert (
            db.execute("SELECT table_name,reason FROM exchange_staging").fetchall()
            == [(table_for(kind), "current_state:conflict")] * 3
        )
        assert db.execute(
            "SELECT count(*) FROM current_resource_diagnostics"
        ).fetchone() == (3,)
        assert db.execute(
            f"SELECT count(*) FROM eligible_{table_for(kind)} WHERE kind=?", (kind,)
        ).fetchone() == (0,)
        independent = candidate(
            catalog, kind, "11", "independent", provider_updated_at_us=None
        )
        if kind == "issue":
            independent["provider_issue_number"] = 2
        assert catalog.admit(independent).status == "accepted"
        onward = Graph(catalog.store.connection).export(catalog.repository)
        assert receive(db, onward)["staged_records"] == 3
        assert db.execute(
            f"SELECT count(*) FROM eligible_{table_for(kind)} WHERE kind=?", (kind,)
        ).fetchone() == (1,)
        forwarded = Graph(db).export(catalog.repository)
        states = [
            record
            for record in forwarded["records"]
            if record["table"] == table_for(kind) and record["values"]["kind"] == kind
        ]
        assert len(states) == 5  # Incumbent, three unresolved values, independent.
        assert {
            row[0]
            for row in db.execute(
                f"SELECT b.body FROM {table_for(kind)} r JOIN text_bodies b ON b.sha256=r.text_body_sha256 WHERE r.kind=?",
                (kind,),
            )
        } == {"incumbent", "independent"}
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        db.close()


@pytest.mark.parametrize("kind", ["issue", "issue-comment", "review-comment"])
def test_semantically_duplicate_candidate_admits_stronger_provider_evidence(
    current_catalog, tmp_path, kind
):
    catalog = current_catalog
    first = candidate(catalog, kind, "10", "A", provider_updated_at_us=10)
    catalog.admit(first)
    initial = Graph(catalog.store.connection).export(catalog.repository)
    alternative = {**first, "body": "B", "provider_updated_at_us": None}
    assert catalog.admit(alternative).status == "conflict"
    unordered = Graph(catalog.store.connection).export(catalog.repository)
    db = receiver()
    try:
        receive(db, initial)
        assert receive(db, unordered)["staged_records"] == 1
        assert receive(db, unordered)["received_records"] == 0
        db = reopen(db, tmp_path / "freshness-current.sqlite3")
        assert (
            catalog.admit({**alternative, "provider_updated_at_us": 20}).status
            == "accepted"
        )
        strengthened = Graph(catalog.store.connection).export(catalog.repository)
        assert receive(db, strengthened)["staged_records"] == 0
        assert body_for(db, kind) == "B"
        assert db.execute(
            f"SELECT provider_updated_at_us,last_checked_at_us FROM {table_for(kind)} WHERE kind=?",
            (kind,),
        ).fetchone() == (20, None)
        assert db.execute(
            f"SELECT count(*) FROM eligible_{table_for(kind)} WHERE kind=?", (kind,)
        ).fetchone() == (1,)
        assert receive(db, strengthened)["received_records"] == 0
        assert receive(db, unordered)["staged_records"] == 0
        assert body_for(db, kind) == "B"
        assert db.execute(
            f"SELECT count(*) FROM {table_for(kind)} WHERE kind=?", (kind,)
        ).fetchone() == (1,)
        assert_absent_tables(db, "parsed_results")
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        db.close()


@pytest.mark.parametrize("kind", ["issue", "issue-comment", "review-comment"])
def test_staged_same_value_refresh_retains_new_clock_with_other_conflict(
    current_catalog, tmp_path, kind
):
    catalog = current_catalog
    first = candidate(catalog, kind, "10", "A", provider_updated_at_us=10)
    catalog.admit(first)
    initial = Graph(catalog.store.connection).export(catalog.repository)
    for body in ("B", "C"):
        assert (
            catalog.admit(
                {**first, "body": body, "provider_updated_at_us": None}
            ).status
            == "conflict"
        )
    unordered = Graph(catalog.store.connection).export(catalog.repository)
    db = receiver()
    try:
        receive(db, initial)
        assert receive(db, unordered)["staged_records"] == 2
        db = reopen(db, tmp_path / "staged-clock-current.sqlite3")
        # Send exactly the B state with a newly known comparable clock. C is
        # still unordered, so B must remain staged while retaining that clock.
        assert (
            catalog.admit({**first, "body": "B", "provider_updated_at_us": 20}).status
            == "conflict"
        )
        strengthened = Graph(catalog.store.connection).export(catalog.repository)
        assert receive(db, strengthened)["staged_records"] == 2
        staged = {
            candidate["body"]: candidate
            for (serialized,) in db.execute(
                "SELECT record_json FROM current_resource_diagnostics"
            )
            for candidate in [json.loads(serialized)]
        }
        assert staged["B"]["provider_updated_at_us"] == 20
        assert staged["C"]["provider_updated_at_us"] is None
        assert body_for(db, kind) == "A"
        assert receive(db, strengthened)["received_records"] == 0
    finally:
        db.close()


@pytest.mark.parametrize("kind", ["issue", "issue-comment", "review-comment"])
def test_application_import_reopens_conflicts_and_exports_every_variant(
    current_catalog, tmp_path, kind
):
    catalog = current_catalog
    first = candidate(catalog, kind, "10", "A", provider_updated_at_us=None)
    catalog.admit(first)
    sender = ExchangeService(catalog.state)
    initial = tmp_path / "initial.json"
    sender.export_repository(catalog.repository, initial)
    for body in ("B", "C"):
        catalog.admit({**first, "body": body})
    conflicted = tmp_path / "conflicted.json"
    sender.export_repository(catalog.repository, conflicted)
    target = tmp_path / "receiver-state"
    MaintenanceService(target).init("catalog-text-v1", 67_108_864, 0)
    service = ExchangeService(target)
    assert service.import_file(initial).status == "complete"
    assert service.import_file(conflicted).status == "partial"
    # import_file opens/closes Store and owns the production writer transaction.
    assert service.import_file(conflicted).status == "partial"
    assert [row["reason"] for row in service.staging().data] == [
        "current_state:conflict",
        "current_state:conflict",
    ]
    forwarded = tmp_path / "forwarded.json"
    service.export_repository(catalog.repository, forwarded)
    unit = json.loads(forwarded.read_text())
    assert (
        sum(
            record["table"] == table_for(kind) and record["values"]["kind"] == kind
            for record in unit["records"]
        )
        == 3
    )
    with Store(target) as store:
        assert store.one("SELECT count(*) FROM current_resource_diagnostics")[0] == 2
        assert (
            store.one(
                f"SELECT count(*) FROM eligible_{table_for(kind)} WHERE kind=?", (kind,)
            )[0]
            == 0
        )
        assert not store.all("PRAGMA foreign_key_check")
        assert store.one("PRAGMA integrity_check")[0] == "ok"


@pytest.mark.parametrize("kind", ["issue", "issue-comment", "review-comment"])
def test_new_clock_proves_previously_unordered_alternative_is_stale(
    current_catalog, tmp_path, kind
):
    catalog = current_catalog
    first = candidate(catalog, kind, "10", "A", provider_updated_at_us=30)
    catalog.admit(first)
    initial = Graph(catalog.store.connection).export(catalog.repository)
    assert (
        catalog.admit({**first, "body": "B", "provider_updated_at_us": None}).status
        == "conflict"
    )
    unordered = Graph(catalog.store.connection).export(catalog.repository)
    db = receiver()
    try:
        receive(db, initial)
        assert receive(db, unordered)["staged_records"] == 1
        db = reopen(db, tmp_path / "stale-evidence-current.sqlite3")
        assert (
            catalog.admit({**first, "body": "B", "provider_updated_at_us": 20}).status
            == "stale"
        )
        # Preserve the actual newly received B observation on the wire. The
        # source's current-only projection has already disproved its local fork,
        # so exporting that source now would send only the unchanged winner A.
        strengthened = copy.deepcopy(unordered)
        b_key = next(
            record["key"]
            for record in strengthened["records"]
            if record["table"] == "text_bodies" and record["values"]["body"] == "B"
        )
        strengthened["records"] = [
            record
            for record in strengthened["records"]
            if record["table"] != table_for(kind)
            or record["values"]["kind"] != kind
            or record["values"]["text_body_sha256"]["$ref"] == b_key
        ]
        for record in strengthened["records"]:
            if record["table"] != table_for(kind) or record["values"]["kind"] != kind:
                continue
            record["values"]["provider_updated_at_us"] = 20
            evidence = json.loads(record["values"]["field_evidence_json"])
            for proof in evidence.values():
                proof["provider_updated_at_us"] = 20
            record["values"]["field_evidence_json"] = json.dumps(evidence)
        assert receive(db, strengthened)["staged_records"] == 0
        assert body_for(db, kind) == "A"
        assert db.execute(
            f"SELECT count(*) FROM eligible_{table_for(kind)} WHERE kind=?", (kind,)
        ).fetchone() == (1,)
        # Stale input is re-evaluated without storing a per-message receipt.
        assert receive(db, strengthened)["staged_records"] == 0
        assert body_for(db, kind) == "A"
        assert db.execute(
            f"SELECT count(*) FROM {table_for(kind)} WHERE kind=?", (kind,)
        ).fetchone() == (1,)
    finally:
        db.close()


@pytest.mark.parametrize("kind", ["issue", "issue-comment", "review", "review-comment"])
def test_each_family_exports_inherited_body_parser_independently_of_row_parser(
    current_catalog, kind
):
    catalog = current_catalog
    first = candidate(
        catalog, kind, "10", "inherited body", provider_updated_at_us=None
    )
    first.update(parser_module="tests.synthetic.body_parser", parser_version="9")
    assert catalog.admit(first).status == "accepted"
    resources = CurrentResources(catalog.store)
    sparse = {
        **first,
        "author": "new author",
        "observed_at_us": 50,
        "parser_module": "tests.synthetic.author_parser",
        "parser_version": "0",
    }
    sparse.pop("body")
    revision, scope = resources.capture_context(sparse["acquisition_scope"])
    assert (
        resources.admit(
            sparse, source="live", base_revision=revision, scope_context=scope
        ).status
        == "accepted"
    )
    unit = Graph(catalog.store.connection).export(catalog.repository)
    assert not any(
        record["table"].startswith("parser_profile") for record in unit["records"]
    )
    db = receiver()
    try:
        assert receive(db, unit)["staged_records"] == 0
        target = CurrentResources(db)
        raw = target._one(f"SELECT * FROM {table_for(kind)} WHERE kind=?", (kind,))
        row = target.candidate_from_row(table_for(kind), raw)
        assert row["body"] == "inherited body"
        assert (
            row["field_evidence"]['["body"]']["parser_module"]
            == "tests.synthetic.body_parser"
        )
        assert row["field_evidence"]['["body"]']["parser_version"] == "9"
        assert (
            row["field_evidence"]['["author"]']["parser_module"]
            == "tests.synthetic.author_parser"
        )
        assert row["field_evidence"]['["author"]']["parser_version"] == "0"
        assert (
            db.execute(
                f"SELECT count(*) FROM eligible_{table_for(kind)} WHERE kind=?", (kind,)
            ).fetchone()[0]
            == 1
        )
    finally:
        db.close()
