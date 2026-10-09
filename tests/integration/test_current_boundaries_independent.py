"""Independent combined-case checks of mutable conflict boundaries."""

import copy
import json
import uuid

import pytest

from repo_catalog.adapters.sqlite.current_resources import CurrentResources
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.json_contracts import (
    JsonContractError,
    validate_catalog,
)
from repo_catalog.domain.models import CatalogError
from tests.integration.test_catalog3_current_exchange import receiver as _receiver
from tests.integration.test_catalog3_current_queries import (
    current_catalog as current_catalog,
)
from tests.integration.test_catalog3_exchange import receive
from tests.integration.test_current_exchange_followup import candidate, table_for
from tests.integration.test_current_resources import issue
from tests.integration.test_current_resources import resources as resources
from tests.integration.test_issue_transfer_followup import _source


def _visible(db, kind):
    return db.execute(
        f"SELECT count(*) FROM eligible_{table_for(kind)} WHERE kind=?", (kind,)
    ).fetchone()[0]


def _state(db, kind):
    adapter = CurrentResources(db)
    row = adapter._one(f"SELECT * FROM {table_for(kind)} WHERE kind=?", (kind,))
    return adapter.candidate_from_row(table_for(kind), row)


@pytest.mark.parametrize("kind", ["issue", "issue-comment", "review-comment"])
def test_fresh_incumbent_proof_survives_two_unordered_alternatives(
    current_catalog, kind
):
    catalog = current_catalog
    first = candidate(catalog, kind, "10", "A", provider_updated_at_us=10)
    catalog.admit(first)
    for body in ("B", "C"):
        assert (
            catalog.admit(
                {**first, "body": body, "provider_updated_at_us": None}
            ).status
            == "conflict"
        )
    assert catalog.admit({**first, "provider_updated_at_us": 20}).status == "conflict"
    assert (
        _state(catalog.store.connection, kind)["field_evidence"]['["body"]'][
            "provider_updated_at_us"
        ]
        == 20
    )
    assert (
        catalog.admit({**first, "body": "B", "provider_updated_at_us": 15}).status
        == "conflict"
    )
    assert _visible(catalog.store.connection, kind) == 0
    catalog.admit({**first, "body": "C", "provider_updated_at_us": 18})
    assert _state(catalog.store.connection, kind)["body"] == "A"
    assert _visible(catalog.store.connection, kind) == 1
    assert (
        catalog.store.one("SELECT count(*) FROM current_resource_diagnostics")[0] == 0
    )


@pytest.mark.parametrize(
    ("stored", "incoming"),
    [(True, 1), ([True], [1]), ({}, []), ([], {})],
    ids=["boolean", "array", "object-to-array", "array-to-object"],
)
def test_equal_proof_retention_preserves_distinct_json_types(
    resources, stored, incoming
):
    adapter, *_ = resources
    first = issue(resources, body="A", metadata={"value": stored})
    adapter.admit(first, source="import")
    assert (
        adapter.admit(
            {**first, "body": "B", "provider_updated_at_us": None}, source="import"
        ).status
        == "conflict"
    )
    assert (
        adapter.admit(
            {**first, "metadata": {"value": incoming}, "provider_updated_at_us": 20},
            source="import",
        ).status
        == "conflict"
    )
    state = _state(adapter.c, "issue")
    assert json.dumps(state["metadata"]["value"]) == json.dumps(stored)
    assert state["field_evidence"]['["body"]']["provider_updated_at_us"] == 20
    assert (
        state["field_evidence"]['["metadata","value"]']["provider_updated_at_us"] == 10
    )
    assert _visible(adapter.c, "issue") == 0
    adapter.admit({**first, "body": "B", "provider_updated_at_us": 15}, source="import")
    # Body dating disproves B, but the different JSON value observed at 20
    # remains unresolved against the retained value's weaker proof at 15.
    assert _visible(adapter.c, "issue") == 0
    adapter.admit(
        {**first, "metadata": {"value": incoming}, "provider_updated_at_us": 20},
        source="import",
    )
    assert json.dumps(_state(adapter.c, "issue")["metadata"]["value"]) == json.dumps(
        incoming
    )
    assert _visible(adapter.c, "issue") == 1


@pytest.mark.parametrize(
    ("stored", "incoming"),
    [(True, 1), ([True], [1]), ({}, []), ([], {})],
    ids=["boolean", "array", "object-to-array", "array-to-object"],
)
def test_equal_clock_distinct_json_values_remain_conflicted(
    resources, stored, incoming
):
    adapter, *_ = resources
    first = issue(resources, body="A", metadata={"value": stored})
    adapter.admit(first, source="import")
    assert (
        adapter.admit(
            {**first, "metadata": {"value": incoming}}, source="import"
        ).status
        == "conflict"
    )
    assert _visible(adapter.c, "issue") == 0


@pytest.mark.parametrize("deleted", [False, True])
def test_equivalent_typed_deleted_flag_does_not_create_json_conflict(
    resources, deleted
):
    adapter, *_ = resources
    first = issue(resources, deleted=int(deleted))
    assert adapter.admit(first, source="import").status == "accepted"
    assert (
        adapter.admit({**first, "deleted": deleted}, source="import").status
        == "identical"
    )
    assert (
        adapter.c.execute(
            "SELECT count(*) FROM current_resource_diagnostics"
        ).fetchone()[0]
        == 0
    )


def _comment_setup(resources, *, alternatives=(), transfer=True):
    adapter, context, profile, _, _ = resources
    source = _source(
        adapter.c, context["service_instance_uuidv4"], context["repository_uuidv4"]
    )
    capture = {**context, "source_registration_uuidv4": source, "endpoint": "A"}
    parent = issue(resources, body="parent", acquisition_scope=capture)
    child = issue(
        resources,
        kind="issue-comment",
        provider_resource_id="23",
        parent_provider_resource_id="12",
        body="A",
        title=None,
        state=None,
        provider_clock_scope="github-issue-comment-updated-at",
        acquisition_scope=capture,
    )
    assert adapter.admit(parent, source="import").status == "accepted"
    assert adapter.admit(child, source="import").status == "accepted"
    for body in alternatives:
        assert (
            adapter.admit(
                {**child, "body": body, "provider_updated_at_us": None}, source="import"
            ).status
            == "conflict"
        )
    if not transfer:
        return child, parent, context, context, source
    destination = _move_parent(adapter, context, profile, parent)
    return child, parent, context, destination, source


def _move_parent(adapter, context, profile, parent):
    destination = {
        **context,
        "repository_uuidv4": str(uuid.uuid4()),
        "repository_binding_id": str(uuid.uuid4()),
    }
    adapter.c.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'B','{}')",
        (destination["repository_uuidv4"],),
    )
    adapter.c.execute(
        "INSERT INTO repository_bindings(repository_binding_id,repository_uuidv4,service_instance_uuidv4,provider_repository_id,metadata) VALUES(?,?,?,'22','{}')",
        (
            destination["repository_binding_id"],
            destination["repository_uuidv4"],
            destination["service_instance_uuidv4"],
        ),
    )
    moved = {
        **parent,
        **destination,
        "provider_issue_number": 7,
        "provider_updated_at_us": 30,
        "acquisition_scope": {**destination, "endpoint": "B parent"},
    }
    assert adapter.admit(moved, source="import").status == "accepted"
    return destination


def _observation(child, destination, body, clock, transfer):
    return {
        **child,
        **destination,
        "provider_issue_number": 7 if transfer else 2,
        "body": body,
        "provider_updated_at_us": clock,
        "acquisition_scope": {**destination, "endpoint": "actual child refresh"},
    }


@pytest.mark.parametrize("transfer", [False, True], ids=["same-owner", "transferred"])
@pytest.mark.parametrize("refresh_first", [False, True], ids=["B15-first", "A20-first"])
def test_transferred_alternative_dating_uses_projected_semantics(
    resources, transfer, refresh_first
):
    adapter, *_ = resources
    child, _, _, destination, _ = _comment_setup(
        resources, alternatives=("B", "C"), transfer=transfer
    )
    steps = [("A", 20), ("B", 15)] if refresh_first else [("B", 15), ("A", 20)]
    for body, clock in steps:
        assert (
            adapter.admit(
                _observation(child, destination, body, clock, transfer), source="import"
            ).status
            == "conflict"
        )
    assert _visible(adapter.c, "issue-comment") == 0
    assert (
        _state(adapter.c, "issue-comment")["field_evidence"]['["body"]'][
            "provider_updated_at_us"
        ]
        == 20
    )
    adapter.admit(_observation(child, destination, "C", 18, transfer), source="import")
    assert _state(adapter.c, "issue-comment")["body"] == "A"
    assert _visible(adapter.c, "issue-comment") == 1
    assert (
        adapter.c.execute(
            "SELECT count(*) FROM current_resource_diagnostics"
        ).fetchone()[0]
        == 0
    )
    validate_catalog(adapter.c)


@pytest.mark.parametrize("repository", ["old", "current"])
def test_unrepresentable_parent_ownership_fork_refuses_either_repository(
    resources, repository
):
    adapter, *_ = resources
    _, parent, original, destination, _ = _comment_setup(resources)
    assert (
        adapter.admit(
            {**parent, "provider_updated_at_us": None}, source="import"
        ).status
        == "conflict"
    )
    assert _visible(adapter.c, "issue") == 0
    owner = original if repository == "old" else destination
    with pytest.raises(CatalogError) as failure:
        Graph(adapter.c).export(owner["repository_uuidv4"])
    assert failure.value.code == "CURRENT_STATE_CROSS_REPOSITORY_CONFLICT"


@pytest.mark.parametrize("reverse", [False, True])
def test_transfer_fork_repeated_exchange_preserves_capture_and_child_clock(
    resources, reverse
):
    adapter, _, profile, _, _ = resources
    child, _, original, destination, source = _comment_setup(
        resources, alternatives=("B", "C")
    )
    unit = Graph(adapter.c).export(destination["repository_uuidv4"])
    if reverse:
        unit["records"].reverse()
    target, onward = _receiver(), _receiver()
    try:
        for _ in range(2):
            receive(target, unit)
        assert _visible(target, "issue-comment") == 0
        assert _state(target, "issue-comment")["field_evidence"]['["body"]'][
            "provider_updated_at_us"
        ] in (None, 10)
        for _, record, _ in CurrentResources(target).export_candidates(
            destination["repository_uuidv4"]
        ):
            if record["kind"] == "issue-comment":
                assert record["acquisition_scope"] == child["acquisition_scope"]
                assert record["repository_uuidv4"] == destination["repository_uuidv4"]
                assert record["parent_provider_resource_id"] == "12"
                assert all(
                    proof["provider_updated_at_us"] in (None, 10)
                    for proof in record["field_evidence"].values()
                )
        receive(onward, Graph(target).export(destination["repository_uuidv4"]))
        for db in (target, onward):
            assert _visible(db, "issue-comment") == 0
            assert (
                db.execute(
                    "SELECT count(*) FROM current_resource_diagnostics"
                ).fetchone()[0]
                == 2
            )
            assert not db.execute(
                "SELECT 1 FROM repositories WHERE repository_uuidv4=?",
                (original["repository_uuidv4"],),
            ).fetchone()
            assert not db.execute(
                "SELECT 1 FROM sources WHERE source_registration_uuidv4=?", (source,)
            ).fetchone()
            validate_catalog(db)
            assert db.execute("PRAGMA foreign_key_check").fetchall() == []
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        target.close()
        onward.close()


@pytest.mark.parametrize("reverse", [False, True])
def test_different_comment_parent_claim_survives_exchange(resources, reverse):
    adapter, context, profile, *_ = resources
    child, _, _, _, _ = _comment_setup(resources, transfer=False)
    adapter.admit(
        issue(resources, provider_resource_id="13", provider_issue_number=3),
        source="import",
    )
    different_parent = {
        **child,
        "parent_provider_resource_id": "13",
        "provider_issue_number": 3,
        "provider_updated_at_us": None,
    }
    assert adapter.admit(different_parent, source="import").status == "conflict"
    unit = Graph(adapter.c).export(context["repository_uuidv4"])
    if reverse:
        unit["records"].reverse()
    target = _receiver()
    try:
        receive(target, unit)
        assert _visible(target, "issue-comment") == 0
        variants = CurrentResources(target).export_candidates(
            context["repository_uuidv4"]
        )
        assert {
            record["parent_provider_resource_id"]
            for _, record, _ in variants
            if record["kind"] == "issue-comment"
        } == {"12", "13"}
        validate_catalog(target)
    finally:
        target.close()


@pytest.mark.parametrize("repository", ["old", "current"])
def test_transfer_does_not_erase_distinct_comment_parent_ownership_claim(
    resources, repository
):
    adapter, context, profile, *_ = resources
    child, parent, _, _, _ = _comment_setup(resources, transfer=False)
    adapter.admit(
        issue(resources, provider_resource_id="13", provider_issue_number=3),
        source="import",
    )
    different_parent = {
        **child,
        "parent_provider_resource_id": "13",
        "provider_issue_number": 3,
        "provider_updated_at_us": None,
    }
    assert adapter.admit(different_parent, source="import").status == "conflict"
    destination = _move_parent(adapter, context, profile, parent)
    owner = context if repository == "old" else destination
    with pytest.raises(CatalogError) as failure:
        Graph(adapter.c).export(owner["repository_uuidv4"])
    assert failure.value.code == "CURRENT_STATE_CROSS_REPOSITORY_CONFLICT"
    staged = json.loads(
        adapter.c.execute(
            "SELECT record_json FROM current_resource_diagnostics"
        ).fetchone()[0]
    )
    assert staged["parent_provider_resource_id"] == "13"
    assert staged["repository_uuidv4"] == context["repository_uuidv4"]
    assert _state(adapter.c, "issue-comment")["parent_provider_resource_id"] == "12"


@pytest.mark.parametrize("scope_case", ["owner", "source"])
def test_malformed_detached_field_capture_cannot_enter_conflict_intake(
    resources, scope_case
):
    adapter, context, *_ = resources
    first = issue(resources, body="A")
    adapter.admit(first, source="import")
    alternative = {**first, "body": "B", "provider_updated_at_us": None}
    scope = {**context, "endpoint": "forged historical capture"}
    if scope_case == "owner":
        scope.update(
            repository_uuidv4="invalid-repository",
            repository_binding_id="invalid-binding",
        )
    else:
        scope["source_registration_uuidv4"] = "invalid-source"
    alternative["field_evidence"] = adapter._observation_evidence(alternative)
    for proof in alternative["field_evidence"].values():
        proof["acquisition_scope"] = scope
    with pytest.raises(JsonContractError):
        adapter.admit(alternative, source="import")
    assert _visible(adapter.c, "issue") == 1
    assert (
        adapter.c.execute(
            "SELECT count(*) FROM current_resource_diagnostics"
        ).fetchone()[0]
        == 0
    )


@pytest.mark.parametrize("scope_case", ["owner", "source"])
def test_graph_malformed_field_capture_is_invalid_and_keeps_valid_sibling(
    resources, scope_case
):
    adapter, context, profile, *_ = resources
    first = issue(resources, body="A")
    adapter.admit(first, source="import")
    initial = Graph(adapter.c).export(context["repository_uuidv4"])
    adapter.admit(
        {**first, "body": "B", "provider_updated_at_us": None}, source="import"
    )
    adapter.admit(
        issue(
            resources,
            provider_resource_id="34",
            provider_issue_number=3,
            body="independent",
        ),
        source="import",
    )
    malformed = copy.deepcopy(Graph(adapter.c).export(context["repository_uuidv4"]))
    scope = {**context, "endpoint": "forged historical capture"}
    if scope_case == "owner":
        scope.update(
            repository_uuidv4="invalid-repository",
            repository_binding_id="invalid-binding",
        )
    else:
        scope["source_registration_uuidv4"] = "invalid-source"
    mutated = 0
    for record in malformed["records"]:
        if (
            record["table"] == "issue_resources"
            and record["values"]["provider_resource_id"] == "12"
            and record["values"]["provider_updated_at_us"] is None
        ):
            evidence = json.loads(record["values"]["field_evidence_json"])
            for proof in evidence.values():
                proof["acquisition_scope"] = scope
            record["values"]["field_evidence_json"] = json.dumps(evidence)
            mutated += 1
    assert mutated == 1
    target = _receiver()
    try:
        receive(target, initial)
        receive(target, malformed)
        assert target.execute("SELECT count(*) FROM issue_resources").fetchone()[0] == 2
        assert _visible(target, "issue") == 2
        reasons = [
            row[0] for row in target.execute("SELECT reason FROM exchange_staging")
        ]
        assert len(reasons) == 1
        assert "invalid" in reasons[0]
        assert (
            target.execute(
                "SELECT count(*) FROM current_resource_diagnostics"
            ).fetchone()[0]
            == 0
        )
        validate_catalog(target)
    finally:
        target.close()
