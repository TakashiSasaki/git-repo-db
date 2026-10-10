"""Scoped completeness depends on normalized boundaries and exact child facts."""

import copy
import json
import sqlite3

import pytest

from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.current_collections import (
    TREE_PROOF_KIND,
    CurrentCollectionProof,
)
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.domain.current_state import fingerprint_candidate
from tests.integration.test_catalog3_exchange import (
    candidate,
    catalog,
    complete_collection,
    fixture,
    receive,
    uid,
)


def new_collection(db, expected, kind="comments", context=None):
    collection = uid()
    db.execute(
        "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,source_id,kind,observed_at_us,scope_json) VALUES(?,?,?,?,?,100,?)",
        (
            collection,
            expected["repository"],
            expected["cr"],
            "source",
            kind,
            json.dumps(
                {
                    "repository_uuidv4": expected["repository"],
                    "change_request_id": expected["cr"],
                    "repository_binding_id": expected["binding"],
                    "service_instance_uuidv4": expected["service"],
                    "source_registration_uuidv4": expected["source"],
                    "endpoint": "synthetic",
                    "request_context": context or {},
                }
            ),
        ),
    )
    return collection


def page(db, collection, ordinal=0, cursor=None, timestamp=100, *, members=None):
    CurrentCollectionProof(db).page(
        collection,
        ordinal,
        timestamp,
        cursor,
        members or [],
        parser_module="synthetic.current",
        parser_version="1",
    )


def marker(db, collection, **extra):
    proof = CurrentCollectionProof(db)
    return {
        "fetch_collection_id": collection,
        "asserted_state": "complete",
        "observed_at_us": proof.observed_at_us(collection),
        "evidence": json.dumps(
            proof.evidence(collection)
            or {
                "kind": "current-resource-pages-v1",
                "page_ordinals": [],
                "terminal": True,
            }
        ),
        **extra,
    }


@pytest.mark.parametrize(
    "pages",
    [
        [(2, None)],
        [(0, "next"), (2, None)],
        [(0, "next"), (0, None)],
        [(0, None), (1, None)],
        [(0, "next")],
    ],
    ids=["missing-initial", "skipped", "duplicate", "early-terminal", "nonterminal"],
)
def test_incomplete_normalized_page_sequence_cannot_prove_complete(pages):
    db = catalog()
    try:
        expected = fixture(db)
        collection = new_collection(db, expected)
        for ordinal, cursor in pages:
            try:
                page(db, collection, ordinal, cursor)
            except sqlite3.IntegrityError:
                assert [ordinal for ordinal, _ in pages] == [0, 0]
                break
        proof = CurrentCollectionProof(db)
        assert proof.evidence(collection) is None
        assert not proof.is_complete_marker(marker(db, collection))
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        db.close()


def test_unrelated_terminal_receipt_cannot_hide_scope_continuation():
    db = catalog()
    try:
        expected = fixture(db)
        pending, other = new_collection(db, expected), new_collection(db, expected)
        page(db, pending, cursor="next")
        page(db, other)
        assert CurrentCollectionProof(db).evidence(other)
        assert not CurrentCollectionProof(db).is_complete_marker(
            marker(db, pending, evidence=marker(db, other)["evidence"])
        )
    finally:
        db.close()


@pytest.mark.parametrize("kind", ["comments", "threads", "thread-comments"])
def test_empty_terminal_enumeration_is_valid_without_raw_api_bytes(kind):
    db = catalog()
    try:
        expected = fixture(db)
        collection = new_collection(db, expected, kind)
        page(db, collection)
        proof = CurrentCollectionProof(db)
        value = marker(db, collection)
        if kind == "threads":
            # A root thread enumeration requires tree evidence even when the
            # actual terminal roster and required-child set are both empty.
            assert not proof.is_complete_marker(value)
            value = marker(
                db,
                collection,
                evidence=json.dumps(
                    {
                        **proof.evidence(collection),
                        "kind": TREE_PROOF_KIND,
                        "fetch_collection_ids": [],
                    }
                ),
            )
            assert db.execute(
                "SELECT count(*) FROM thread_collection_requirements "
                "WHERE fetch_collection_id=?",
                (collection,),
            ).fetchone() == (0,)
        assert proof.is_complete_marker(value)
        assert db.execute("SELECT count(*) FROM stored_bytes").fetchone() == (0,)
    finally:
        db.close()


def thread_requirement(db, expected, *, timestamp=100):
    root = new_collection(db, expected, "threads")
    thread = "THREAD-1"
    db.execute(
        "INSERT INTO review_threads(provider_resource_id,change_request_id) VALUES(?,?)",
        (thread, expected["cr"]),
    )
    context = {
        "parent_fetch_collection_id": root,
        "provider_resource_id": thread,
        "parent_observed_at_us": timestamp,
        "object_format": None,
        "head_oid": None,
        "base_oid": None,
    }
    child = new_collection(db, expected, "thread-comments", context)
    db.execute(
        "INSERT INTO thread_collection_requirements(fetch_collection_id,provider_resource_id,child_fetch_collection_id,required_observed_at_us) VALUES(?,?,?,?)",
        (root, thread, child, timestamp),
    )
    observed_thread = {
        "kind": "review-thread",
        "change_request_id": expected["cr"],
        "provider_resource_id": thread,
    }
    page(
        db,
        root,
        timestamp=timestamp,
        members=[
            {
                "family": "thread",
                "change_request_id": expected["cr"],
                "provider_resource_id": thread,
                "state_digest": fingerprint_candidate(observed_thread),
            }
        ],
    )
    return root, child


@pytest.mark.parametrize("child_receipts", [False, True])
def test_normalized_thread_child_requires_its_own_terminal_evidence(child_receipts):
    db = catalog()
    try:
        expected = fixture(db)
        root, child = thread_requirement(db, expected)
        if child_receipts:
            page(db, child, timestamp=200)
            complete_collection(db, child)
        proof = CurrentCollectionProof(db)
        evidence = {
            **proof.evidence(root),
            "kind": TREE_PROOF_KIND,
            "fetch_collection_ids": [child],
        }
        value = marker(
            db,
            root,
            evidence=json.dumps(evidence),
            observed_at_us=200 if child_receipts else 100,
        )
        assert proof.is_complete_marker(value) is child_receipts
    finally:
        db.close()


@pytest.mark.parametrize("damage", ["parent", "thread", "capture", "head", "base"])
def test_thread_child_cannot_discharge_a_different_scope_or_target(damage):
    db = catalog()
    try:
        expected = fixture(db)
        root, child = thread_requirement(db, expected)
        row = json.loads(
            db.execute(
                "SELECT scope_json FROM fetch_collections WHERE fetch_collection_id=?",
                (child,),
            ).fetchone()[0]
        )
        keys = {
            "parent": "parent_fetch_collection_id",
            "thread": "provider_resource_id",
            "capture": "parent_observed_at_us",
            "head": "head_oid",
            "base": "base_oid",
        }
        row["request_context"][keys[damage]] = (
            999
            if damage == "capture"
            else uid()
            if damage == "parent"
            else "different"
            if damage == "thread"
            else "aa" * 20
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "UPDATE fetch_collections SET scope_json=? WHERE fetch_collection_id=?",
                (json.dumps(row), child),
            )
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        db.close()


@pytest.mark.parametrize("pages", [[(0, None)], [(0, "next"), (1, None)]])
def test_valid_normalized_sequence_including_empty_members_proves_complete(pages):
    db = catalog()
    try:
        expected = fixture(db)
        collection = new_collection(db, expected)
        for ordinal, cursor in pages:
            page(db, collection, ordinal, cursor, timestamp=100 + ordinal)
        complete_collection(db, collection)
        assert CurrentCollectionProof(db).is_complete_marker(marker(db, collection))
    finally:
        db.close()


@pytest.mark.parametrize("order", ["ordinary", "reversed"])
@pytest.mark.parametrize("damage", ["ordinal", "terminal"])
def test_receiver_and_late_promotion_reject_incomplete_proof_keep_domain_facts(
    order, damage
):
    source, target = catalog(), catalog()
    try:
        expected = fixture(source)
        complete_collection(source, expected["collection"])
        unit = Graph(source).export(expected["repository"])
        forged = copy.deepcopy(unit)
        receipt = next(
            record
            for record in forged["records"]
            if record["table"] == "current_collection_pages"
        )
        receipt["values"]["ordinal" if damage == "ordinal" else "has_next"] = (
            2 if damage == "ordinal" else 1
        )
        if damage == "ordinal":
            receipt["key"] = receipt["key"].replace('"ordinal":0', '"ordinal":2')
        completion = next(
            record
            for record in forged["records"]
            if record["table"] == "completion_markers"
        )
        assert receive(target, {**forged, "records": [completion]})["staged_records"]
        if order == "reversed":
            forged["records"].reverse()
        receive(target, forged)
        receive(target, forged)
        assert target.execute("SELECT count(*) FROM completion_markers").fetchone() == (
            0,
        )
        assert target.execute(
            "SELECT count(*) FROM eligible_document_state"
        ).fetchone() == (1,)
        assert target.execute("SELECT count(*) FROM coverage_claims").fetchone() == (0,)
        assert target.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        source.close()
        target.close()


def test_earlier_complete_receipt_remains_valid_after_document_edit():
    db = catalog()
    try:
        expected = fixture(db)
        complete_collection(db, expected["collection"])
        value = dict(
            zip(
                [
                    column[1]
                    for column in db.execute("PRAGMA table_info(completion_markers)")
                ],
                db.execute("SELECT * FROM completion_markers").fetchone(),
                strict=True,
            )
        )
        assert (
            CurrentApiState(db)
            .admit(
                "document_state",
                candidate(expected, "pr-body", "newer domain body", updated=200),
            )
            .status
            == "accepted"
        )
        assert CurrentCollectionProof(db).is_complete_marker(value)
        assert db.execute(
            "SELECT body FROM eligible_document_state s JOIN text_bodies b ON b.sha256=s.text_body_sha256"
        ).fetchone() == ("newer domain body",)
    finally:
        db.close()
