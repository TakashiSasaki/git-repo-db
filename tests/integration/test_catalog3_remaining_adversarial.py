"""Retained independent attacks against direct typed domain contracts."""

import hashlib
import json
import sqlite3
import uuid
from types import SimpleNamespace

import pytest

from repo_catalog.adapters.sqlite.cas_integrity import diagnose_corruption
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.json_contracts import reference_dependencies
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.git_query_context import decoded_fact
from repo_catalog.application.pr_queries import _collection_state
from repo_catalog.application.query_service import QueryService
from repo_catalog.domain.models import CatalogError
from tests.integration.test_catalog3_exchange import receive
from tests.support.cli import run
from tests.support.domain_facts import (
    SOURCE,
    TIME_US,
    admit_document,
    admit_pr,
    collection,
    fresh_domain_db,
    insert,
    repository_uuid,
)


@pytest.fixture
def databases():
    dbs = [fresh_domain_db(), fresh_domain_db()]
    yield dbs
    for db in dbs:
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        db.close()


def reader(db):
    def rows(sql, args=()):
        cursor = db.execute(sql, args)
        cursor.row_factory = sqlite3.Row
        return cursor.fetchall()

    return SimpleNamespace(
        connection=db, all=rows, one=lambda sql, args=(): (rows(sql, args) or [None])[0]
    )


def git_acquisition(db, number=1, identity="git"):
    insert(
        db,
        "git_acquisitions",
        git_acquisition_id=identity,
        repository_uuidv4=repository_uuid(number),
        object_format="sha1",
        kind="git",
        request="{}",
    )
    return identity


def git_blob(
    db, body=b"blob", number=1, *, acquisition="git", fmt="sha1", bytes_present=True
):
    oid = hashlib.new(fmt, f"blob {len(body)}\0".encode() + body).digest()
    obj = insert(
        db,
        "git_objects",
        object_format=fmt,
        oid=oid,
        type="blob",
        size=len(body),
        verified=1,
    ).lastrowid
    content = insert(db, "contents", byte_length=len(body)).lastrowid
    insert(db, "blob_content_map", git_object_id=obj, content_id=content)
    insert(
        db,
        "repository_object_sources",
        repository_uuidv4=repository_uuid(number),
        git_object_id=obj,
        git_acquisition_id=acquisition,
    )
    if bytes_present:
        payload = intern_payload(db, body, representation="git-object-raw-v1")
        insert(
            db,
            "git_object_payloads",
            git_object_id=obj,
            payload_representation=payload.representation,
            payload_sha256=payload.sha256,
        )
    return obj, content, oid


def complete_page(
    db, identity, observed=100, *, ordinal=0, next_cursor=None, members=None
):
    proof = CurrentCollectionProof(db)
    proof.page(
        identity,
        ordinal,
        observed,
        next_cursor,
        members or [],
        parser_module=__name__,
        parser_version="1",
    )
    return proof


def marker(db, identity, evidence, *, observed=100, state="complete"):
    return insert(
        db,
        "completion_markers",
        fetch_collection_id=identity,
        asserted_state=state,
        evidence=json.dumps(evidence),
        observed_at_us=observed,
    )


def corrupt(db, digest, body):
    trigger = db.execute(
        "SELECT sql FROM sqlite_schema WHERE name='stored_bytes_immutable'"
    ).fetchone()[0]
    db.execute("DROP TRIGGER stored_bytes_immutable")
    db.execute(
        "UPDATE stored_bytes SET body=?,byte_length=? WHERE sha256=?",
        (body, len(body), digest),
    )
    db.execute(trigger)


def test_unrelated_present_record_cannot_prove_complete_coverage(databases):
    sender, receiver = databases
    admit_pr(sender, state="open")
    insert(
        sender,
        "coverage_scopes",
        coverage_scope_id="scope",
        repository_uuidv4=repository_uuid(1),
        change_request_id="pr1",
        kind="comment",
    )
    insert(
        sender,
        "coverage_claims",
        coverage_scope_id="scope",
        coverage_state="complete",
        observed_at_us=100,
    )
    graph = Graph(sender)
    unit = graph.export(repository_uuid(1))
    claim = graph.record("coverage_claims", graph.rows("coverage_claims")[0])
    claim["requires"] = [
        next(
            record["key"]
            for record in unit["records"]
            if record["table"] == "repositories"
        )
    ]
    unit["records"] = [
        record for record in unit["records"] if record["table"] != "coverage_claims"
    ] + [claim]
    try:
        receive(receiver, unit)
    except CatalogError as error:
        assert error.code == "INVALID_EXCHANGE"
    assert (
        receiver.execute(
            "SELECT count(*) FROM coverage_claims WHERE coverage_state='complete'"
        ).fetchone()[0]
        == 0
    )


def test_git_commit_cannot_bind_tree_from_another_object_format(databases):
    db, _ = databases
    tree = insert(
        db,
        "git_objects",
        object_format="sha256",
        oid=b"t" * 32,
        type="tree",
        size=0,
        verified=1,
    ).lastrowid
    commit = insert(
        db,
        "git_objects",
        object_format="sha1",
        oid=b"c" * 20,
        type="commit",
        size=2,
        verified=1,
    ).lastrowid
    with pytest.raises(sqlite3.IntegrityError):
        insert(
            db,
            "commits",
            git_object_id=commit,
            tree_git_object_id=tree,
            tree_format="sha256",
            tree_oid=b"t" * 32,
            parent_count=0,
            raw_headers=b"",
            raw_message=b"",
        )


@pytest.mark.parametrize(
    "column",
    [
        "git_object_id",
        "tree_format",
        "tree_oid",
        "parent_count",
        "raw_headers",
        "raw_message",
    ],
)
def test_git_intrinsic_fact_rejects_null_required_component(databases, column):
    db, _ = databases
    obj = insert(
        db,
        "git_objects",
        object_format="sha1",
        oid=b"c" * 20,
        type="commit",
        size=2,
        verified=1,
    ).lastrowid
    values = dict(
        git_object_id=obj,
        tree_format="sha1",
        tree_oid=b"t" * 20,
        parent_count=0,
        raw_headers=b"",
        raw_message=b"",
    )
    values[column] = None
    with pytest.raises(sqlite3.IntegrityError):
        insert(db, "commits", **values)


def test_git_acquisition_membership_rejects_foreign_typed_owner(databases):
    db, _ = databases
    git_acquisition(db)
    obj, _, _ = git_blob(db)
    with pytest.raises(sqlite3.IntegrityError):
        insert(
            db,
            "repository_object_sources",
            repository_uuidv4=repository_uuid(2),
            git_object_id=obj,
            git_acquisition_id="git",
        )


def test_collection_subset_manifest_does_not_prove_complete_collection(databases):
    db, _ = databases
    collection(db, identity="pages")
    proof = complete_page(db, "pages", ordinal=0, next_cursor="next")
    proof.page("pages", 1, 100, None, [], parser_module=__name__, parser_version="1")
    with pytest.raises(sqlite3.IntegrityError):
        marker(
            db,
            "pages",
            {
                "kind": "current-resource-pages-v1",
                "terminal": True,
                "page_ordinals": [0],
            },
        )
    assert proof.evidence("pages")["page_ordinals"] == [0, 1]


@pytest.mark.parametrize("as_list", [False, True])
def test_source_capture_rejects_outside_source_membership(databases, as_list):
    db, _ = databases
    admit_pr(db, state="open")
    admit_document(db, body="own")
    data = reader(db).one("SELECT * FROM document_state")
    scope = json.loads(data["acquisition_scope_json"])
    scope["source_registration_uuidv4"] = SOURCE
    if as_list:
        scope["nested"] = [{"source_registration_uuidv4": SOURCE}]
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "UPDATE document_state SET acquisition_scope_json=?", (json.dumps(scope),)
        )


def test_current_origin_cannot_hide_malformed_nested_reference(databases):
    db, _ = databases
    admit_pr(db, state="open")
    admit_document(db, body="own")
    scope = {
        "repository_uuidv4": repository_uuid(1),
        "repository_binding_id": "binding-1",
        "service_instance_uuidv4": "00000000-0000-4000-8000-000000000101",
        "change_request_id": "pr1",
        "endpoint": "synthetic",
        "nested": {"repository_uuidv4": "wrong-type-domain"},
    }
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "UPDATE document_state SET acquisition_scope_json=?", (json.dumps(scope),)
        )


def test_valid_git_prefix_is_available_without_acquisition_wide_seal(databases):
    db, _ = databases
    git_acquisition(db)
    first, _, _ = git_blob(db, b"first")
    assert db.execute("SELECT git_object_id FROM available_git_objects").fetchall() == [
        (first,)
    ]
    second, _, _ = git_blob(db, b"second")
    assert {
        row[0] for row in db.execute("SELECT git_object_id FROM available_git_objects")
    } == {first, second}
    assert db.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 0
    assert not db.execute(
        "SELECT 1 FROM sqlite_schema WHERE name='git_acquisition_publications'"
    ).fetchall()


def test_missing_raw_git_bytes_keeps_only_dependent_object_unavailable(databases):
    db, _ = databases
    git_acquisition(db)
    first, _, _ = git_blob(db, b"first")
    second, _, _ = git_blob(db, b"second", bytes_present=False)
    assert db.execute("SELECT git_object_id FROM available_git_objects").fetchall() == [
        (first,)
    ]
    payload = intern_payload(db, b"second", representation="git-object-raw-v1")
    insert(
        db,
        "git_object_payloads",
        git_object_id=second,
        payload_representation=payload.representation,
        payload_sha256=payload.sha256,
    )
    assert {
        row[0] for row in db.execute("SELECT git_object_id FROM available_git_objects")
    } == {first, second}


def test_quarantined_raw_git_bytes_leave_independent_prefix_available(databases):
    db, _ = databases
    git_acquisition(db)
    first, _, _ = git_blob(db, b"first")
    second, _, _ = git_blob(db, b"second")
    digest = db.execute(
        "SELECT payload_sha256 FROM git_object_payloads WHERE git_object_id=?",
        (second,),
    ).fetchone()[0]
    corrupt(db, digest, b"BROKEN")
    diagnose_corruption(db, digest)
    assert db.execute("SELECT git_object_id FROM available_git_objects").fetchall() == [
        (first,)
    ]
    assert db.execute("SELECT count(*) FROM git_objects").fetchone()[0] == 2


@pytest.mark.parametrize("representation", [[], {}])
def test_nested_original_reference_cannot_become_authored_evidence(
    databases, representation
):
    with pytest.raises(CatalogError) as error:
        reference_dependencies(
            "repository_names",
            {
                "provenance_json": json.dumps(
                    {
                        "nested": {
                            "payload": {
                                "representation": representation,
                                "sha256": "a" * 64,
                            }
                        }
                    }
                )
            },
        )
    assert error.value.code == "INVALID_JSON_REFERENCE"


@pytest.mark.parametrize("reverse", [False, True])
def test_git_decoder_candidates_never_choose_receipt_parser_or_uuid_winner(
    databases, reverse
):
    db, _ = databases
    git_acquisition(db)
    obj, content, _ = git_blob(db, b"caf\xe9")
    choices = [("utf-8", "caf�", "1"), ("latin-1", "café", "999")]
    for encoding, text, version in reversed(choices) if reverse else choices:
        key = hashlib.sha256(encoding.encode()).hexdigest()
        insert(
            db,
            "git_text_facts",
            git_fact_uuidv4=str(uuid.uuid4()),
            git_object_id=obj,
            content_id=content,
            decoder_key=key,
            parser_module=__name__,
            parser_version=version,
            text_encoding=encoding,
            max_text_blob_bytes=1024,
            metadata_encoding=encoding,
            metadata_errors="replace",
            text_state="eligible",
            raw_text=text,
        )
    result = decoded_fact(reader(db), obj, "blob")
    assert result["fact"] is None and result["decoder_conflict"]
    assert len(result["candidates"]) == 2
    for encoding, text, _ in choices:
        explicit = decoded_fact(
            reader(db),
            obj,
            "blob",
            decoder_key=hashlib.sha256(encoding.encode()).hexdigest(),
        )
        assert not explicit["decoder_conflict"] and explicit["fact"]["raw_text"] == text


@pytest.mark.parametrize("kind", ["pr-code", "pr", "pr-documents"])
def test_terminal_pr_detail_cannot_prove_broader_coverage_without_scope_evidence(
    databases, kind
):
    sender, receiver = databases
    admit_pr(sender, state="open")
    collection(sender, identity="detail", kind="pr-detail")
    proof = complete_page(sender, "detail")
    marker(sender, "detail", proof.evidence("detail"))
    insert(
        sender,
        "coverage_scopes",
        coverage_scope_id="scope",
        repository_uuidv4=repository_uuid(1),
        change_request_id="pr1" if kind == "pr-code" else None,
        kind=kind,
    )
    insert(
        sender,
        "coverage_claims",
        coverage_scope_id="scope",
        coverage_state="complete",
        observed_at_us=100,
        details_json=json.dumps({"fetch_collection_ids": ["detail"]}),
    )
    unit = Graph(sender).export(repository_uuid(1))
    assert not any(record["table"] == "coverage_claims" for record in unit["records"])
    receive(receiver, unit)
    assert receiver.execute("SELECT count(*) FROM coverage_claims").fetchone() == (0,)


@pytest.mark.parametrize("member", [None, "sha1:0123", {"oid": "not-an-oid"}])
def test_git_root_declarations_require_structured_reference_members(databases, member):
    db, _ = databases
    roots = json.dumps([member])
    with pytest.raises(CatalogError):
        reference_dependencies("git_acquisitions", {"roots_manifest": roots})
    with pytest.raises(sqlite3.IntegrityError):
        insert(
            db,
            "git_acquisitions",
            git_acquisition_id="bad",
            repository_uuidv4=repository_uuid(1),
            object_format="sha1",
            kind="git",
            request="{}",
            roots_manifest=roots,
        )


@pytest.mark.parametrize(
    "proof",
    [
        "exact",
        "subset",
        "empty",
        "unrelated",
        "duplicate",
        "nonterminal",
        "stale",
        "unknown",
    ],
)
def test_complete_code_requires_exact_terminal_listing_sql_evidence(databases, proof):
    db, _ = databases
    collection(db, identity="pages", kind="commits")
    pages = complete_page(db, "pages", ordinal=0, next_cursor="next")
    pages.page("pages", 1, 100, None, [], parser_module=__name__, parser_version="1")
    evidence = pages.evidence("pages")
    observed = 100
    if proof == "subset":
        evidence["page_ordinals"] = [0]
    elif proof == "empty":
        evidence["page_ordinals"] = []
    elif proof == "unrelated":
        evidence["page_ordinals"] = [2, 3]
    elif proof == "duplicate":
        evidence["page_ordinals"] = [0, 0]
    elif proof == "nonterminal":
        evidence["terminal"] = False
    elif proof == "stale":
        observed = 99
    elif proof == "unknown":
        observed = None
    if proof == "exact":
        marker(db, "pages", evidence, observed=observed)
        assert pages.is_complete_marker(
            reader(db).one("SELECT * FROM completion_markers")
        )
    else:
        with pytest.raises(sqlite3.IntegrityError):
            marker(db, "pages", evidence, observed=observed)
        assert db.execute("SELECT count(*) FROM completion_markers").fetchone()[0] == 0


def test_completion_marker_uuid_cannot_hide_noncanonical_suffix_after_nul(databases):
    db, _ = databases
    collection(db, identity="pages")
    with pytest.raises(sqlite3.IntegrityError):
        insert(
            db,
            "completion_markers",
            completion_marker_uuidv4=str(uuid.uuid4()) + "\0hidden",
            fetch_collection_id="pages",
            asserted_state="partial",
            evidence="{}",
            observed_at_us=0,
        )


@pytest.mark.parametrize(
    "details",
    [
        {"expected_roles": []},
        {"expected_roles": {"head": "not-a-git-oid"}},
        {"api_head_base_stable": "yes"},
        {"code_inputs_complete": {}},
        {"missing_roles": {"head": "missing"}},
    ],
)
def test_code_detail_consumers_reject_malformed_authored_types(databases, details):
    db, _ = databases
    encoded = json.dumps(details)
    with pytest.raises(CatalogError):
        reference_dependencies(
            "code_assessments", {"object_format": "sha1", "details_json": encoded}
        )
    with pytest.raises(sqlite3.IntegrityError):
        insert(
            db,
            "code_assessments",
            code_assessment_id="bad",
            change_request_id="pr1",
            repository_uuidv4=repository_uuid(1),
            state="partial",
            object_format="sha1",
            details_json=encoded,
            parser_module=__name__,
            parser_version="1",
        )


@pytest.mark.parametrize(
    "request_data",
    [{"parent_fetch_collection_id": []}, {"parent_fetch_collection_id": 42}],
)
def test_collection_scope_consumers_reject_malformed_authored_types(
    databases, request_data
):
    db, _ = databases
    scope = {
        "repository_uuidv4": repository_uuid(1),
        "change_request_id": "pr1",
        "endpoint": "synthetic",
        "request_context": request_data,
    }
    with pytest.raises(CatalogError):
        reference_dependencies("fetch_collections", {"scope_json": json.dumps(scope)})
    with pytest.raises(sqlite3.IntegrityError):
        insert(
            db,
            "fetch_collections",
            fetch_collection_id="bad",
            repository_uuidv4=repository_uuid(1),
            change_request_id="pr1",
            kind="thread-comments",
            scope_json=json.dumps(scope),
        )


@pytest.mark.parametrize("object_format,width", [("sha1", 40), ("sha256", 64)])
@pytest.mark.parametrize("field", ["expected_roles", "merge", "missing_roles"])
def test_code_git_oid_cannot_hide_nonhex_suffix_after_nul(
    databases, object_format, width, field
):
    db, _ = databases
    oid = "a" * (width - 2) + "\0a"
    value = {
        "expected_roles": {"head": oid},
        "merge": {"merge": oid},
        "missing_roles": ["review-target:" + oid],
    }[field]
    encoded = json.dumps({field: value})
    with pytest.raises(CatalogError):
        reference_dependencies(
            "code_assessments",
            {"object_format": object_format, "details_json": encoded},
        )
    with pytest.raises(sqlite3.IntegrityError):
        insert(
            db,
            "code_assessments",
            code_assessment_id="bad",
            change_request_id="pr1",
            repository_uuidv4=repository_uuid(1),
            state="partial",
            object_format=object_format,
            details_json=encoded,
            parser_module=__name__,
            parser_version="1",
        )


@pytest.mark.parametrize(
    "later_state,observed", [("partial", 200), ("unknown", 200), ("partial", 100)]
)
def test_immutable_collection_state_never_falls_back_from_newer_or_tied_incomplete(
    databases, later_state, observed
):
    db, _ = databases
    collection(db, identity="pages")
    proof = complete_page(db, "pages")
    marker(db, "pages", proof.evidence("pages"))
    marker(db, "pages", {}, observed=observed, state=later_state)
    query = SimpleNamespace(s=reader(db), check=lambda: None)
    assert _collection_state(query, {"fetch_collection_id": "pages"}) != "complete"


def test_genuine_equal_time_current_conflict_has_no_parser_certificate_fallback(
    databases,
):
    db, _ = databases
    assert admit_pr(db, state="open", clock=100).status == "accepted"
    assert (
        admit_pr(
            db,
            state="closed",
            clock=100,
            parser_version="999",
            observed_at_us=TIME_US + 1,
        ).status
        == "conflict"
    )
    assert (
        db.execute("SELECT count(*) FROM eligible_change_request_state").fetchone()[0]
        == 0
    )
    assert not db.execute(
        "SELECT 1 FROM sqlite_schema WHERE name='parser_profiles'"
    ).fetchall()


def test_git_quarantine_suppresses_only_dependent_repository_readers(catalog):
    state, _, repositories = catalog
    run(state, "sync", "git")
    query = QueryService(state)
    alpha_options = {
        "repo": repositories["alpha"],
        "ref": "refs/heads/main",
        "path": "README.md",
    }
    beta_options = {
        "repo": repositories["beta"],
        "ref": "refs/heads/main",
        "path": "copy.txt",
    }
    assert query.query("file show", alpha_options).data["items"]
    assert query.query("file show", beta_options).data["items"][0]["text"] == "abc"
    with Store(state) as store, store.transaction():
        digest = store.one(
            "SELECT p.payload_sha256 FROM git_object_payloads p JOIN stored_bytes b ON b.sha256=p.payload_sha256 "
            "JOIN repository_object_sources o USING(git_object_id) WHERE o.repository_uuidv4=? AND b.body=X'6D61696E' LIMIT 1",
            (repositories["alpha"],),
        )[0]
        before = store.one("SELECT count(*) FROM commits")[0]
        corrupt(store.connection, digest, b"FAIL")
        diagnose_corruption(store.connection, digest)
        assert store.one("SELECT count(*) FROM commits")[0] == before
    affected = query.query("file show", alpha_options)
    assert affected.data["items"] == []
    assert affected.status == "partial"
    assert query.query("file show", beta_options).data["items"][0]["text"] == "abc"
    assert query.query(
        "search code", {"repo": repositories["beta"], "literal": "abc"}
    ).data["items"]
