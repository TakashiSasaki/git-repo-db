"""Independent counterexamples at production current-state and exchange boundaries.

These tests use the complete packaged DDL, actual admission and Graph.receive.
They deliberately combine sparse knowledge, conflict alternatives and captures.
"""

import copy
import json
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.sqlite.current_resources import CurrentResources
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.json_contracts import JsonContractError
from repo_catalog.domain.models import CatalogError
from tests.integration.test_catalog3_current_exchange import receiver
from tests.integration.test_catalog3_current_queries import (
    current_catalog as current_catalog,
)
from tests.integration.test_catalog3_exchange import receive
from tests.integration.test_current_resources import current, issue
from tests.integration.test_current_resources import resources as _resources_fixture
from tests.integration.test_issue_transfer_followup import _transfer
from tests.support.sqlite_contracts import assert_absent_tables


@pytest.fixture(name="resources")
def _resources(tmp_path):
    yield from _resources_fixture.__wrapped__(tmp_path)


def path(*parts):
    return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))


def proof(candidate, **changes):
    names = (
        "provider_updated_at_us",
        "provider_clock_scope",
        "observed_at_us",
        "parsed_at_us",
        "parser_module",
        "parser_version",
        "acquisition_scope",
    )
    return {**{name: candidate.get(name) for name in names}, **changes}


def partial(candidate, *fields):
    return {key: value for key, value in candidate.items() if key not in fields}


def assert_public(resources, expected):
    adapter = resources[0]
    assert current(adapter)["body"] == expected
    assert (
        adapter.c.execute(
            "SELECT count(*) FROM eligible_issue_resources WHERE kind='issue'"
        ).fetchone()[0]
        == 1
    )
    assert adapter.c.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("reverse", [False, True])
def test_sparse_full_permutation_preserves_each_fields_capture(resources, reverse):
    adapter = resources[0]
    initial = issue(resources, title="old title", body="old body", metadata={})
    adapter.admit(initial, source="import")
    full = issue(
        resources,
        title="new title",
        body="new body",
        metadata={},
        provider_updated_at_us=20,
        observed_at_us=21,
        parsed_at_us=22,
    )
    sparse = partial({**full, "observed_at_us": 23, "parsed_at_us": 24}, "body")
    for candidate in (full, sparse) if reverse else (sparse, full):
        assert adapter.admit(candidate, source="import").status in {
            "accepted",
            "identical",
        }
    assert_public(resources, "new body")
    evidence = current(adapter)["field_evidence"]
    assert evidence[path("body")]["provider_updated_at_us"] == 20
    assert evidence[path("body")]["observed_at_us"] == 21
    assert evidence[path("title")]["provider_updated_at_us"] == 20


@pytest.mark.parametrize("reverse", [False, True])
def test_older_body_fills_newer_title_and_clock_does_not_roll_back(resources, reverse):
    adapter = resources[0]
    older = issue(
        resources,
        title="older title",
        body="older observed body",
        metadata={"nested": {"older": True}},
        provider_updated_at_us=10,
        observed_at_us=11,
    )
    newer = partial(
        issue(
            resources,
            title="newer title",
            metadata={"nested": {"newer": True}},
            provider_updated_at_us=20,
            observed_at_us=21,
        ),
        "body",
    )
    for candidate in (newer, older) if reverse else (older, newer):
        assert adapter.admit(candidate, source="import").status == "accepted"
    row = current(adapter)
    assert_public(resources, "older observed body")
    assert row["title"] == "newer title"
    assert row["provider_updated_at_us"] == 20
    assert row["field_evidence"][path("body")]["provider_updated_at_us"] == 10
    assert row["metadata"] == {"nested": {"older": True, "newer": True}}


@pytest.mark.parametrize("reverse", [False, True])
def test_same_clock_nested_contradictions_remain_hidden(resources, reverse):
    adapter = resources[0]
    states = [
        issue(resources, metadata={"nested": {"value": value}})
        for value in ("one", "two")
    ]
    if reverse:
        states.reverse()
    assert adapter.admit(states[0], source="import").status == "accepted"
    assert adapter.admit(states[1], source="import").status == "conflict"
    assert (
        adapter.c.execute("SELECT count(*) FROM eligible_issue_resources").fetchone()[0]
        == 0
    )


def test_newer_scalar_resolves_tied_nested_object_alternatives(resources):
    adapter = resources[0]
    adapter.admit(
        issue(resources, metadata={"nested": {"value": "one"}}), source="import"
    )
    assert (
        adapter.admit(
            issue(resources, metadata={"nested": {"value": "two"}}), source="import"
        ).status
        == "conflict"
    )
    assert (
        adapter.admit(
            issue(resources, metadata={"nested": None}, provider_updated_at_us=20),
            source="import",
        ).status
        == "accepted"
    )
    row = current(adapter)
    assert row["metadata"] == {"nested": None}
    assert path("metadata", "nested", "value") not in row["field_evidence"]
    assert (
        adapter.c.execute(
            "SELECT count(*) FROM current_resource_diagnostics"
        ).fetchone()[0]
        == 0
    )


def test_sparse_live_title_cannot_certify_unseen_disputed_body(resources):
    adapter = resources[0]
    first = issue(resources, body="A", provider_updated_at_us=None, metadata={})
    adapter.admit(first, source="import")
    assert adapter.admit({**first, "body": "B"}, source="import").status == "conflict"
    sparse = partial(
        {**first, "title": "observed live title", "observed_at_us": 500}, "body"
    )
    revision, scope = adapter.capture_context(sparse["acquisition_scope"])
    assert (
        adapter.admit(
            sparse, source="live", base_revision=revision, scope_context=scope
        ).status
        == "conflict"
    )
    assert (
        adapter.c.execute("SELECT count(*) FROM eligible_issue_resources").fetchone()[0]
        == 0
    )
    assert current(adapter)["last_checked_at_us"] is None
    # A full serialized capture can now resolve the body it actually observes.
    full = {**first, "body": "B", "title": "observed live title", "observed_at_us": 501}
    revision, scope = adapter.capture_context(full["acquisition_scope"])
    assert (
        adapter.admit(
            full, source="live", base_revision=revision, scope_context=scope
        ).status
        == "accepted"
    )
    assert_public(resources, "B")
    assert current(adapter)["last_checked_at_us"] == 501


@pytest.mark.parametrize("reverse", [False, True])
def test_mixed_field_evidence_survives_full_graph_exchange(current_catalog, reverse):
    catalog = current_catalog
    older = catalog.candidate(
        "issue",
        "10",
        "old body",
        title="old title",
        provider_updated_at_us=10,
        parser_module="tests.synthetic.body_parser",
        parser_version="9",
    )
    catalog.admit(older)
    sparse = partial(
        {
            **older,
            "title": "new title",
            "provider_updated_at_us": 20,
            "parser_module": "tests.synthetic.title_parser",
            "parser_version": "0",
        },
        "body",
    )
    catalog.admit(sparse)
    unit = Graph(catalog.store.connection).export(catalog.repository)
    if reverse:
        unit["records"].reverse()
    db = receiver()
    db.row_factory = sqlite3.Row
    try:
        assert receive(db, unit)["staged_records"] == 0
        adapter = CurrentResources(db)
        row = current(adapter)
        assert row["field_evidence"][path("body")]["provider_updated_at_us"] == 10
        assert row["field_evidence"][path("title")]["provider_updated_at_us"] == 20
        assert (
            row["field_evidence"][path("body")]["parser_module"]
            == "tests.synthetic.body_parser"
        )
        assert row["field_evidence"][path("body")]["parser_version"] == "9"
        assert (
            row["field_evidence"][path("title")]["parser_module"]
            == "tests.synthetic.title_parser"
        )
        assert row["field_evidence"][path("title")]["parser_version"] == "0"
        complete = {**sparse, "body": "new body"}
        assert adapter.admit(complete, source="import").status == "accepted"
        assert current(adapter)["body"] == "new body"
        assert (
            db.execute("SELECT count(*) FROM eligible_issue_resources").fetchone()[0]
            == 1
        )
        onward = Graph(db).export(catalog.repository)
        receive(db, onward)
        assert receive(db, onward)["received_records"] == 0
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        db.close()


def test_same_content_field_evidence_refresh_with_another_unordered_variant(resources):
    adapter = resources[0]
    initial = issue(
        resources, body="A", title="title", metadata={}, provider_updated_at_us=10
    )
    adapter.admit(initial, source="import")
    for body in ("B", "C"):
        alternative = {**initial, "body": body, "provider_updated_at_us": 30}
        alternative["field_evidence"] = {
            path("body"): proof(alternative, provider_updated_at_us=None),
            path("title"): proof(alternative),
        }
        assert adapter.admit(alternative, source="import").status == "conflict"
    stronger = {**initial, "body": "B", "provider_updated_at_us": 30}
    stronger["field_evidence"] = {
        path("body"): proof(stronger, provider_updated_at_us=20),
        path("title"): proof(stronger),
    }
    assert adapter.admit(stronger, source="import").status == "conflict"
    staged = {
        candidate["body"]: candidate
        for (record,) in adapter.c.execute(
            "SELECT record_json FROM current_resource_diagnostics"
        )
        for candidate in [json.loads(record)]
    }
    assert staged["B"]["field_evidence"][path("body")]["provider_updated_at_us"] == 20
    assert staged["C"]["field_evidence"][path("body")]["provider_updated_at_us"] is None


def test_graph_same_content_field_refresh_with_other_unordered_variant(current_catalog):
    catalog = current_catalog
    initial = catalog.candidate(
        "issue", "10", "A", title="title", provider_updated_at_us=10
    )
    catalog.admit(initial)
    first_unit = Graph(catalog.store.connection).export(catalog.repository)
    states = {}
    for body in ("B", "C"):
        candidate = {**initial, "body": body, "provider_updated_at_us": 30}
        candidate["field_evidence"] = {
            path("body"): proof(candidate, provider_updated_at_us=None),
            path("title"): proof(candidate),
        }
        states[body] = candidate
        assert catalog.admit(candidate).status == "conflict"
    unordered = Graph(catalog.store.connection).export(catalog.repository)
    db = receiver()
    try:
        receive(db, first_unit)
        assert receive(db, unordered)["staged_records"] == 2
        stronger = copy.deepcopy(states["B"])
        stronger["field_evidence"][path("body")]["provider_updated_at_us"] = 20
        assert catalog.admit(stronger).status == "conflict"
        unit = Graph(catalog.store.connection).export(catalog.repository)
        assert receive(db, unit)["staged_records"] == 2
        staged = {
            candidate["body"]: candidate
            for (record,) in db.execute(
                "SELECT record_json FROM current_resource_diagnostics"
            )
            for candidate in [json.loads(record)]
        }
        assert (
            staged["B"]["field_evidence"][path("body")]["provider_updated_at_us"] == 20
        )
        assert (
            staged["C"]["field_evidence"][path("body")]["provider_updated_at_us"]
            is None
        )
        assert receive(db, unit)["received_records"] == 0
        assert (
            catalog.admit({**initial, "body": "C", "provider_updated_at_us": 40}).status
            == "accepted"
        )
        resolved = Graph(catalog.store.connection).export(catalog.repository)
        assert receive(db, resolved)["staged_records"] == 0
        assert db.execute(
            "SELECT body FROM text_bodies JOIN issue_resources ON sha256=text_body_sha256"
        ).fetchone() == ("C",)
    finally:
        db.close()


@pytest.mark.parametrize(
    "attack",
    [
        "unknown-field",
        "structural-field",
        "nested-body",
        "absent-metadata",
        "noncanonical-path",
        "nonstring-part",
        "extra-proof-key",
        "bool-time",
        "wrong-clock",
        "null-capture-time",
        "missing-proof-key",
        "endpoint-nul",
    ],
)
@pytest.mark.parametrize("boundary", ["admission", "sql"])
def test_malformed_knowledge_is_rejected_at_both_boundaries(
    resources, attack, boundary
):
    adapter = resources[0]
    value = issue(resources)
    adapter.admit(value, source="import")
    encoded = path("body")
    entry = proof(value)
    if attack == "unknown-field":
        encoded = path("unregistered")
    elif attack == "structural-field":
        encoded = path("repository_uuidv4")
    elif attack == "nested-body":
        encoded = path("body", "value")
    elif attack == "absent-metadata":
        encoded = path("metadata", "absent")
    elif attack == "noncanonical-path":
        encoded = '[ "body" ]'
    elif attack == "nonstring-part":
        encoded = '["metadata",1]'
    elif attack == "extra-proof-key":
        entry["authoritative"] = True
    elif attack == "bool-time":
        entry["provider_updated_at_us"] = True
    elif attack == "wrong-clock":
        entry["provider_clock_scope"] = "invented-clock"
    elif attack == "null-capture-time":
        entry["observed_at_us"] = None
    elif attack == "missing-proof-key":
        del entry["parsed_at_us"]
    else:
        entry["acquisition_scope"] = {
            **entry["acquisition_scope"],
            "endpoint": "issues\x00hidden",
        }
    evidence = {encoded: entry}
    if boundary == "sql":
        with pytest.raises(sqlite3.IntegrityError):
            adapter.c.execute(
                "UPDATE issue_resources SET field_evidence_json=?",
                (json.dumps(evidence),),
            )
    else:
        with pytest.raises((CatalogError, JsonContractError, ValueError, TypeError)):
            adapter.admit({**value, "field_evidence": evidence}, source="import")


def test_transferred_child_inherits_new_body_without_rewriting_old_title_capture(
    resources,
):
    adapter = resources[0]
    before, child, destination, source, _ = _transfer(resources)
    refresh = {
        **child,
        **destination,
        "provider_issue_number": 7,
        "body": "updated in destination",
        "provider_updated_at_us": 40,
        "observed_at_us": 41,
        "parsed_at_us": 42,
        "acquisition_scope": {
            **destination,
            "source_registration_uuidv4": source,
            "endpoint": "https://synthetic.invalid/repos/b/issues/7/comments",
        },
    }
    refresh.pop("metadata")
    refresh.pop("title")
    revision, scope = adapter.capture_context(refresh["acquisition_scope"])
    assert (
        adapter.admit(
            refresh, source="live", base_revision=revision, scope_context=scope
        ).status
        == "accepted"
    )
    row = adapter.candidate_from_row(
        "issue_resources",
        adapter.c.execute(
            "SELECT * FROM issue_resources WHERE kind='issue-comment'"
        ).fetchone(),
    )
    assert (
        row["field_evidence"][path("body")]["acquisition_scope"]
        == refresh["acquisition_scope"]
    )
    assert row["field_evidence"][path("metadata")]["acquisition_scope"] == json.loads(
        before["acquisition_scope_json"]
    )
    target = receiver()
    try:
        assert (
            receive(target, Graph(adapter.c).export(destination["repository_uuidv4"]))[
                "staged_records"
            ]
            == 0
        )
        outgoing = Graph(target).export(destination["repository_uuidv4"])
        state = next(
            record["values"]
            for record in outgoing["records"]
            if record["table"] == "issue_resources"
            and record["values"]["kind"] == "issue-comment"
        )
        assert json.loads(state["field_evidence_json"])[path("metadata")][
            "acquisition_scope"
        ] == json.loads(before["acquisition_scope_json"])
    finally:
        target.close()


def test_sender_last_check_does_not_advance_receiver_local_live_check(current_catalog):
    catalog = current_catalog
    first = catalog.candidate("issue", "10", "body")
    catalog.admit(first)
    initial = Graph(catalog.store.connection).export(catalog.repository)
    db = receiver()
    db.row_factory = sqlite3.Row
    try:
        receive(db, initial)
        adapter = CurrentResources(db)
        local = {**first, "observed_at_us": 100}
        revision, scope = adapter.capture_context(local["acquisition_scope"])
        adapter.admit(local, source="live", base_revision=revision, scope_context=scope)
        assert current(adapter)["last_checked_at_us"] == 100
        advanced = copy.deepcopy(initial)
        state = next(
            record["values"]
            for record in advanced["records"]
            if record["table"] == "issue_resources"
        )
        assert "last_checked_at_us" not in state
        assert receive(db, initial)["staged_records"] == 0
        state["last_checked_at_us"] = 999999
        with pytest.raises(CatalogError) as failure:
            receive(db, advanced)
        assert failure.value.code == "INVALID_EXCHANGE"
        assert current(adapter)["last_checked_at_us"] == 100
    finally:
        db.close()


@pytest.mark.parametrize("attack", ["other-pr", "other-repository", "missing-pr"])
@pytest.mark.parametrize("boundary", ["admission", "sql"])
def test_review_field_proof_cannot_claim_another_change_request(
    current_catalog, boundary, attack
):
    catalog = current_catalog
    adapter = CurrentResources(catalog.store)
    candidate = catalog.candidate("review-comment", "10", "belongs to this PR")
    catalog.admit(candidate)
    other_request = str(uuid.uuid4())
    scope = {**candidate["acquisition_scope"], "change_request_id": other_request}
    with catalog.store.transaction():
        repository, binding = catalog.repository, catalog.binding
        if attack == "other-repository":
            repository, binding = str(uuid.uuid4()), str(uuid.uuid4())
            catalog.store.execute(
                "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'other','{}')",
                (repository,),
            )
            catalog.store.execute(
                "INSERT INTO repository_bindings(repository_binding_id,repository_uuidv4,service_instance_uuidv4,provider_repository_id,metadata) VALUES(?,?,?,'22','{}')",
                (binding, repository, catalog.service),
            )
            scope.update(repository_uuidv4=repository, repository_binding_id=binding)
        catalog.store.execute(
            "INSERT INTO change_requests VALUES(?,?,?,'pull_request',2)",
            (other_request, repository, binding),
        )
    if attack == "missing-pr":
        del scope["change_request_id"]
    evidence = {
        path("body"): proof(
            candidate,
            acquisition_scope=scope,
        )
    }
    if boundary == "sql":
        with pytest.raises(sqlite3.IntegrityError):
            catalog.store.execute(
                "UPDATE review_resources SET field_evidence_json=?",
                (json.dumps(evidence),),
            )
    else:
        with pytest.raises((CatalogError, JsonContractError)):
            adapter.admit({**candidate, "field_evidence": evidence}, source="import")


@pytest.mark.parametrize("clock", [None, 20, 30])
def test_leaf_only_evidence_cannot_replace_a_newer_or_unordered_scalar(
    resources, clock
):
    adapter = resources[0]
    initial = issue(
        resources, metadata={"nested": "known scalar"}, provider_updated_at_us=30
    )
    adapter.admit(initial, source="import")
    incoming = issue(
        resources,
        metadata={"nested": {"child": "replacement"}},
        provider_updated_at_us=clock,
    )
    incoming["field_evidence"] = {path("metadata", "nested", "child"): proof(incoming)}
    try:
        admitted = adapter.admit(incoming, source="import")
    except (CatalogError, JsonContractError):
        return
    assert admitted.status in {"conflict", "stale", "identical"}
    assert current(adapter)["metadata"] == {"nested": "known scalar"}


def test_graph_leaf_only_evidence_cannot_replace_newer_scalar(current_catalog):
    catalog = current_catalog
    initial = catalog.candidate(
        "issue",
        "10",
        "body",
        metadata={"nested": "known scalar"},
        provider_updated_at_us=30,
    )
    catalog.admit(initial)
    original = Graph(catalog.store.connection).export(catalog.repository)
    db = receiver()
    db.row_factory = sqlite3.Row
    try:
        receive(db, original)
        attack = copy.deepcopy(original)
        state = next(
            record["values"]
            for record in attack["records"]
            if record["table"] == "issue_resources"
        )
        state["metadata"] = json.dumps({"nested": {"child": "replacement"}})
        state["provider_updated_at_us"] = 20
        state["field_evidence_json"] = json.dumps(
            {
                path("metadata", "nested", "child"): proof(
                    initial, provider_updated_at_us=20
                )
            }
        )
        receive(db, attack)
        assert current(CurrentResources(db))["metadata"] == {"nested": "known scalar"}
    finally:
        db.close()


@pytest.mark.parametrize("bad_time", [True, 1.5, 2**63, -(2**63) - 1])
def test_graph_invalid_field_time_retains_valid_sibling_and_invalid_diagnostic(
    current_catalog, bad_time
):
    catalog = current_catalog
    catalog.admit(
        catalog.candidate(
            "issue", "10", "invalid resource body", provider_issue_number=1
        )
    )
    catalog.admit(
        catalog.candidate(
            "issue", "11", "independent valid body", provider_issue_number=2
        )
    )
    unit = Graph(catalog.store.connection).export(catalog.repository)
    state = next(
        record["values"]
        for record in unit["records"]
        if record["table"] == "issue_resources"
        and record["values"]["provider_resource_id"] == "10"
    )
    evidence = json.loads(state["field_evidence_json"])
    evidence[path("body")]["provider_updated_at_us"] = bad_time
    state["field_evidence_json"] = json.dumps(evidence)
    target = receiver()
    try:
        outcome = receive(target, unit)
        assert outcome["staged_records"] == 1
        assert target.execute(
            "SELECT provider_resource_id FROM issue_resources"
        ).fetchall() == [("11",)]
        assert target.execute(
            "SELECT b.body FROM issue_resources r JOIN text_bodies b ON b.sha256=r.text_body_sha256"
        ).fetchone() == ("independent valid body",)
        staged = target.execute(
            "SELECT table_name,reason,record_json FROM exchange_staging"
        ).fetchone()
        assert staged[0] == "issue_resources"
        assert staged[1] == "invalid:domain_json"
        assert json.loads(staged[2])["values"]["provider_resource_id"] == "10"
        assert target.execute("PRAGMA foreign_key_check").fetchall() == []
        assert target.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        target.close()


def test_sql_field_evidence_requires_known_metadata_object_ancestors(resources):
    adapter = resources[0]
    candidate = issue(resources, metadata={"nested": {"child": "value"}})
    adapter.admit(candidate, source="import")
    incomplete = {path("metadata", "nested", "child"): proof(candidate)}
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "UPDATE issue_resources SET field_evidence_json=?",
            (json.dumps(incomplete),),
        )


@pytest.mark.parametrize(
    "field", ["provider_updated_at_us", "observed_at_us", "parsed_at_us"]
)
@pytest.mark.parametrize("value", [2**63, -(2**63) - 1])
def test_sql_field_evidence_rejects_times_outside_signed_int64(resources, field, value):
    adapter = resources[0]
    candidate = issue(resources)
    adapter.admit(candidate, source="import")
    evidence = {path("body"): proof(candidate, **{field: value})}
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "UPDATE issue_resources SET field_evidence_json=?", (json.dumps(evidence),)
        )


@pytest.mark.parametrize(
    "field", ["provider_updated_at_us", "observed_at_us", "parsed_at_us"]
)
def test_sql_field_evidence_preserves_signed_int64_limits_zero_and_negative(
    resources, field
):
    adapter = resources[0]
    candidate = issue(resources)
    adapter.admit(candidate, source="import")
    for value in (-(2**63), -1, 0, 2**63 - 1):
        evidence = {path("body"): proof(candidate, **{field: value})}
        adapter.c.execute(
            "UPDATE issue_resources SET field_evidence_json=?", (json.dumps(evidence),)
        )
        saved = json.loads(
            adapter.c.execute(
                "SELECT field_evidence_json FROM issue_resources"
            ).fetchone()[0]
        )
        assert saved[path("body")][field] == value


@pytest.mark.parametrize("boundary", ["admission", "sql"])
@pytest.mark.parametrize("field", ["parser_module", "parser_version"])
@pytest.mark.parametrize("value", [None, "", "module\x00hidden"])
def test_field_proof_requires_actual_nonempty_parser_attribution(
    resources, boundary, field, value
):
    adapter = resources[0]
    candidate = issue(resources)
    adapter.admit(candidate, source="import")
    evidence = {path("body"): proof(candidate, **{field: value})}
    if boundary == "sql":
        with pytest.raises(sqlite3.IntegrityError):
            adapter.c.execute(
                "UPDATE issue_resources SET field_evidence_json=?",
                (json.dumps(evidence),),
            )
    else:
        with pytest.raises((CatalogError, JsonContractError)):
            adapter.admit({**candidate, "field_evidence": evidence}, source="import")


def test_field_proof_accepts_a_distinct_actual_module_without_profile_authority(
    resources,
):
    adapter = resources[0]
    candidate = issue(resources)
    candidate["field_evidence"] = {
        path("body"): proof(
            candidate, parser_module="tests.synthetic.body_parser", parser_version="7"
        )
    }
    assert adapter.admit(candidate, source="import").status == "accepted"
    body = current(adapter)["field_evidence"][path("body")]
    assert (body["parser_module"], body["parser_version"]) == (
        "tests.synthetic.body_parser",
        "7",
    )
    assert_absent_tables(adapter.c, "parser_profiles")
