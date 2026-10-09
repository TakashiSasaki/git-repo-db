"""Incumbent freshness and transferred forks through the production schema."""

import json
import uuid

import pytest

from repo_catalog.adapters.sqlite.current_resources import CurrentResources
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.json_contracts import validate_catalog
from repo_catalog.adapters.sqlite.parser_model import ParserModel
from tests.integration.test_catalog3_current_exchange import receiver as _receiver
from tests.integration.test_catalog3_current_queries import (
    current_catalog as current_catalog,
)
from tests.integration.test_catalog3_exchange import receive
from tests.integration.test_current_exchange_followup import candidate as make_candidate
from tests.integration.test_current_exchange_followup import table_for
from tests.integration.test_current_resources import issue
from tests.integration.test_current_resources import resources as resources
from tests.integration.test_issue_transfer_followup import _source


def _state(db, kind):
    resources = CurrentResources(db)
    row = resources._one(f"SELECT * FROM {table_for(kind)} WHERE kind=?", (kind,))
    return resources.candidate_from_row(table_for(kind), row)


def _visible(db, kind):
    return db.execute(
        f"SELECT count(*) FROM eligible_{table_for(kind)} WHERE kind=?", (kind,)
    ).fetchone()[0]


def _observations(catalog, kind, sparse):
    first = make_candidate(catalog, kind, "10", "A", provider_updated_at_us=10)
    unknown = {**first, "body": "B", "provider_updated_at_us": None}
    repeated = {**first, "provider_updated_at_us": 20}
    if sparse:
        repeated.pop("author")
        repeated.pop("metadata")
    dated = {**first, "body": "B", "provider_updated_at_us": 15}
    return first, unknown, repeated, dated


@pytest.mark.parametrize("kind", ["issue", "issue-comment", "review-comment"])
@pytest.mark.parametrize("sparse", [False, True], ids=["full", "body-only"])
@pytest.mark.parametrize("reverse", [False, True], ids=["A20-first", "B15-first"])
def test_incumbent_duplicate_keeps_freshness_during_conflict(
    current_catalog, kind, sparse, reverse
):
    catalog = current_catalog
    first, unknown, repeated, dated = _observations(catalog, kind, sparse)
    assert catalog.admit(first).status == "accepted"
    assert catalog.admit(unknown).status == "conflict"
    if not reverse:
        assert catalog.admit(repeated).status == "conflict"
        assert _visible(catalog.store.connection, kind) == 0
    else:
        catalog.admit(dated)
    catalog.admit(repeated if reverse else dated)
    state = _state(catalog.store.connection, kind)
    assert state["body"] == "A"
    assert state["field_evidence"]['["body"]']["provider_updated_at_us"] == 20
    assert _visible(catalog.store.connection, kind) == 1
    assert (
        catalog.store.one("SELECT count(*) FROM current_resource_diagnostics")[0] == 0
    )


@pytest.mark.parametrize("kind", ["issue", "issue-comment", "review-comment"])
def test_sparse_freshness_does_not_certify_omitted_body(current_catalog, kind):
    catalog = current_catalog
    first, unknown, repeated, dated = _observations(catalog, kind, False)
    catalog.admit(first)
    catalog.admit(unknown)
    repeated.pop("body")
    assert catalog.admit(repeated).status == "conflict"
    assert (
        _state(catalog.store.connection, kind)["field_evidence"]['["body"]'][
            "provider_updated_at_us"
        ]
        == 10
    )
    catalog.admit(dated)
    assert _state(catalog.store.connection, kind)["body"] == "B"
    assert _visible(catalog.store.connection, kind) == 1


@pytest.mark.parametrize("kind", ["issue", "issue-comment", "review-comment"])
@pytest.mark.parametrize("reverse", [False, True])
def test_incumbent_refresh_crosses_actual_exchange(current_catalog, kind, reverse):
    catalog = current_catalog
    first, unknown, repeated, dated = _observations(catalog, kind, False)
    target, other_sender = _receiver(), _receiver()
    try:
        for index, observation in enumerate((first, unknown, repeated, dated)):
            catalog.admit(observation)
            unit = Graph(catalog.store.connection).export(catalog.repository)
            if index == 0:
                receive(other_sender, unit)
            if reverse:
                unit["records"].reverse()
            receive(target, unit)
            if index == 0:
                ParserModel(target).trust_verification(catalog.verification)
            if index in (1, 2):
                assert _visible(target, kind) == 0
        # The resolved sender snapshot contains only A@20. That does not prove
        # an already received unordered B was old; keep it hidden until the
        # receiver actually receives B's dating evidence from another catalog.
        assert _visible(target, kind) == 0
        CurrentResources(other_sender).admit(dated, source="import")
        dated_unit = Graph(other_sender).export(catalog.repository)
        if reverse:
            dated_unit["records"].reverse()
        receive(target, dated_unit)
        assert _state(target, kind)["body"] == "A"
        assert (
            _state(target, kind)["field_evidence"]['["body"]']["provider_updated_at_us"]
            == 20
        )
        assert _visible(target, kind) == 1
        assert (
            target.execute(
                "SELECT count(*) FROM current_resource_diagnostics"
            ).fetchone()[0]
            == 0
        )
        validate_catalog(target)
    finally:
        target.close()
        other_sender.close()


def _transferred_fork(resources):
    adapter, context, profile, _, _ = resources
    db = adapter.c
    original_source = _source(
        db, context["service_instance_uuidv4"], context["repository_uuidv4"]
    )
    scope = {
        **context,
        "source_registration_uuidv4": original_source,
        "endpoint": "capture-in-A",
    }
    parent = issue(resources, body="parent", acquisition_scope=scope)
    child = issue(
        resources,
        kind="issue-comment",
        provider_resource_id="23",
        parent_provider_resource_id="12",
        body="comment A",
        title=None,
        state=None,
        provider_clock_scope="github-issue-comment-updated-at",
        acquisition_scope=scope,
    )
    adapter.admit(parent, source="import")
    adapter.admit(child, source="import")
    assert (
        adapter.admit(
            {**child, "body": "unordered comment B", "provider_updated_at_us": None},
            source="import",
        ).status
        == "conflict"
    )
    captured = db.execute(
        "SELECT record_json FROM current_resource_diagnostics"
    ).fetchone()[0]
    destination, binding = str(uuid.uuid4()), str(uuid.uuid4())
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'B','{}')",
        (destination,),
    )
    db.execute(
        "INSERT INTO repository_bindings(repository_binding_id,repository_uuidv4,service_instance_uuidv4,provider_repository_id,metadata) VALUES(?,?,?,'22','{}')",
        (binding, destination, context["service_instance_uuidv4"]),
    )
    for kind in ("issue", "ordinary-issue-comment"):
        ParserModel(db).ensure_scope_profile(
            profile, repository_uuidv4=destination, fact_kind=kind
        )
    owner = {
        **context,
        "repository_uuidv4": destination,
        "repository_binding_id": binding,
    }
    moved = {
        **parent,
        **owner,
        "provider_issue_number": 7,
        "provider_updated_at_us": 30,
        "acquisition_scope": {**owner, "endpoint": "capture-in-B"},
    }
    assert adapter.admit(moved, source="import").status == "accepted"
    return destination, original_source, json.loads(captured)


def test_transfer_exports_every_child_candidate_under_current_membership(resources):
    adapter, context, _, _, _ = resources
    destination, _, captured = _transferred_fork(resources)
    # Acquisition ownership in intake intentionally remains A.
    assert (
        adapter.c.execute(
            "SELECT repository_uuidv4 FROM current_resource_diagnostics"
        ).fetchone()[0]
        == context["repository_uuidv4"]
    )
    children = [
        candidate
        for _, candidate, _ in adapter.export_candidates(destination)
        if candidate["kind"] == "issue-comment"
    ]
    assert {candidate["body"] for candidate in children} == {
        "comment A",
        "unordered comment B",
    }
    for candidate in children:
        assert candidate["repository_uuidv4"] == destination
        assert candidate["provider_issue_number"] == 7
        assert candidate["acquisition_scope"] == captured["acquisition_scope"]
        assert all(
            proof["acquisition_scope"] == captured["acquisition_scope"]
            for proof in candidate["field_evidence"].values()
        )


@pytest.mark.parametrize("reverse", [False, True])
def test_destination_only_exchange_never_turns_transferred_fork_into_winner(
    resources, reverse
):
    adapter, context, profile, _, _ = resources
    destination, source, captured = _transferred_fork(resources)
    target, onward = _receiver(), _receiver()
    try:
        unit = Graph(adapter.c).export(destination)
        if reverse:
            unit["records"].reverse()
        receive(target, unit)
        verification = target.execute(
            "SELECT parser_profile_verification_uuidv4 FROM parser_profile_verifications WHERE parser_profile_uuidv4=?",
            (profile,),
        ).fetchone()[0]
        ParserModel(target).trust_verification(verification)
        assert _visible(target, "issue-comment") == 0
        assert (
            target.execute(
                "SELECT count(*) FROM current_resource_diagnostics WHERE table_name='issue_resources'"
            ).fetchone()[0]
            == 1
        )
        assert receive(target, unit)["staged_records"] == 1
        forwarded = Graph(target).export(destination)
        assert receive(onward, forwarded)["staged_records"] == 1
        for db in (target, onward):
            assert not db.execute(
                "SELECT 1 FROM repositories WHERE repository_uuidv4=?",
                (context["repository_uuidv4"],),
            ).fetchone()
            assert not db.execute(
                "SELECT 1 FROM sources WHERE source_registration_uuidv4=?", (source,)
            ).fetchone()
            variants = CurrentResources(db).export_candidates(destination)
            for _, candidate, _ in variants:
                if candidate["kind"] == "issue-comment":
                    assert (
                        candidate["acquisition_scope"] == captured["acquisition_scope"]
                    )
            validate_catalog(db)
            assert db.execute("PRAGMA foreign_key_check").fetchall() == []
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        target.close()
        onward.close()


@pytest.mark.parametrize("kind", ["issue", "issue-comment", "review", "review-comment"])
def test_exchange_omits_checks_from_current_and_staged_candidates(
    current_catalog, kind
):
    catalog = current_catalog
    first = make_candidate(catalog, kind, "10", "A", provider_updated_at_us=None)
    resources = CurrentResources(catalog.store)
    revision, scope = resources.capture_context(first["acquisition_scope"])
    assert (
        resources.admit(
            {**first, "last_checked_at_us": 500},
            source="live",
            base_revision=revision,
            scope_context=scope,
        ).status
        == "accepted"
    )
    assert _state(catalog.store.connection, kind)["last_checked_at_us"] == 500
    initial = Graph(catalog.store.connection).export(catalog.repository)
    target = _receiver()
    try:
        receive(target, initial)
        ParserModel(target).trust_verification(catalog.verification)
        receiver = CurrentResources(target)
        checked = {**first, "observed_at_us": 888, "parsed_at_us": 889}
        revision, scope = receiver.capture_context(checked["acquisition_scope"])
        receiver.admit(
            checked, source="live", base_revision=revision, scope_context=scope
        )
        assert (
            catalog.admit({**first, "body": "B", "last_checked_at_us": 999}).status
            == "conflict"
        )
        unit = Graph(catalog.store.connection).export(catalog.repository)
        variants = [
            record
            for record in unit["records"]
            if record["table"] == table_for(kind) and record["values"]["kind"] == kind
        ]
        assert len(variants) == 2
        assert all("last_checked_at_us" not in record["values"] for record in variants)
        assert all(
            "last_checked_at_us" not in json.loads(stage[0])
            for stage in catalog.store.connection.execute(
                "SELECT record_json FROM current_resource_diagnostics"
            )
        )
        receive(target, unit)
        assert _state(target, kind)["last_checked_at_us"] == 888
        assert _visible(target, kind) == 0
        assert receive(target, unit)["staged_records"] == 1
        assert _state(target, kind)["last_checked_at_us"] == 888
    finally:
        target.close()
