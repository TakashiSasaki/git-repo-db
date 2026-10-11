"""Historical completeness uses real page boundaries, not a terminal assertion."""

import copy
import json

import pytest

from repo_catalog.adapters.sqlite.cas_integrity import (
    diagnose_corruption,
    is_quarantined,
)
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.domain.models import CatalogError
from tests.integration.test_catalog3_cas_integrity import corrupt
from tests.integration.test_catalog3_exchange import (
    catalog,
    complete_collection,
    fixture,
    receive,
    uid,
)
from tests.integration.test_catalog3_review_coverage import (
    collect_threads,
    start_threads,
)
from tests.support.github_runtime import github_runtime as github_runtime


def page_marker(
    db,
    pages,
    *,
    current_receipts=False,
    current_boundaries=None,
    current_time=100,
    kind="comments",
    raw_body=b"[]",
):
    expected = fixture(db, body=raw_body)
    original = db.execute(
        "SELECT fetch_collection_id FROM fetch_occurrences"
    ).fetchone()[0]
    collection = uid()
    db.execute(
        "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,source_id,kind,resume_scope_id) "
        "SELECT ?,repository_uuidv4,change_request_id,source_id,?,resume_scope_id FROM fetch_collections WHERE fetch_collection_id=?",
        (collection, kind, original),
    )
    fetches = []
    for ordinal, cursor in pages:
        fetch = uid()
        fetches.append(fetch)
        db.execute(
            "INSERT INTO fetch_occurrences(fetch_occurrence_uuidv4,repository_uuidv4,fetch_collection_id,ordinal,"
            "payload_representation,payload_sha256,request,next_cursor,observed_at_us,parsed_at_us) "
            "SELECT ?,repository_uuidv4,?,?,payload_representation,payload_sha256,'{}',?,100,100 "
            "FROM fetch_occurrences WHERE fetch_occurrence_uuidv4=?",
            (fetch, collection, ordinal, cursor, expected["fetch"]),
        )
    evidence = {"terminal": True, "fetch_occurrence_uuidv4s": fetches}
    if current_receipts:
        proof = CurrentCollectionProof(db)
        boundaries = current_boundaries or [(0, None)]
        for ordinal, cursor in boundaries:
            proof.page(
                collection,
                ordinal,
                current_time,
                cursor,
                [],
                parser_module="synthetic.current",
                parser_version="1",
            )
        evidence["current_page_collections"] = [
            {
                "fetch_collection_id": collection,
                "page_ordinals": [ordinal for ordinal, _ in boundaries],
            }
        ]
    db.execute(
        "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,asserted_state,evidence,observed_at_us) "
        "SELECT resume_scope_id,fetch_collection_id,'complete',?,? FROM fetch_collections WHERE fetch_collection_id=?",
        (
            json.dumps(evidence),
            max(100, current_time) if current_receipts else 100,
            collection,
        ),
    )
    graph = Graph(db)
    return graph, graph.matching(
        "completion_markers", ("fetch_collection_id",), (collection,)
    )[0]


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
def test_incomplete_historical_page_sequence_cannot_prove_complete(pages):
    db = catalog()
    try:
        graph, marker = page_marker(db, pages)
        assert graph.proof_requirements("completion_markers", marker) is None
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        db.close()


def test_unrelated_current_receipt_cannot_hide_flat_historical_continuation():
    db = catalog()
    try:
        graph, marker = page_marker(db, [(0, "next")], current_receipts=True)
        assert graph.proof_requirements("completion_markers", marker) is None
    finally:
        db.close()


@pytest.mark.parametrize("kind", ["comments", "threads", "thread-comments"])
def test_current_receipt_cannot_invent_rawless_historical_root(kind):
    db = catalog()
    try:
        graph, marker = page_marker(db, [], current_receipts=True, kind=kind)
        assert graph.proof_requirements("completion_markers", marker) is None
    finally:
        db.close()


@pytest.mark.parametrize("child_receipts", [False, True])
def test_current_only_thread_child_requires_its_own_receipts(child_receipts):
    db = catalog()
    try:
        graph, root = page_marker(db, [(0, None)], kind="threads")
        child, scope = uid(), uid()
        db.execute(
            "INSERT INTO resume_scopes(resume_scope_id,repository_uuidv4,source_id,request_context,"
            "parser_version,profile_version,confidence) "
            "SELECT ?,repository_uuidv4,source_id,?,parser_version,profile_version,confidence "
            "FROM resume_scopes WHERE resume_scope_id=?",
            (
                scope,
                json.dumps({"parent_fetch_collection_id": root["fetch_collection_id"]}),
                root["resume_scope_id"],
            ),
        )
        db.execute(
            "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,"
            "source_id,kind,resume_scope_id) "
            "SELECT ?,repository_uuidv4,change_request_id,source_id,'thread-comments',? "
            "FROM fetch_collections WHERE fetch_collection_id=?",
            (child, scope, root["fetch_collection_id"]),
        )
        evidence = json.loads(root["evidence"])
        evidence["fetch_collection_ids"] = [root["fetch_collection_id"], child]
        if child_receipts:
            CurrentCollectionProof(db).page(
                child,
                0,
                100,
                None,
                [],
                parser_module="synthetic.current",
                parser_version="1",
            )
            evidence["current_page_collections"] = [
                {"fetch_collection_id": child, "page_ordinals": [0]}
            ]
        marker_id = db.execute(
            "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,asserted_state,evidence,"
            "observed_at_us) VALUES(?,?,'complete',?,100)",
            (
                root["resume_scope_id"],
                root["fetch_collection_id"],
                json.dumps(evidence),
            ),
        ).lastrowid
        marker = graph.lookup(
            "completion_markers", ("completion_marker_id",), (marker_id,)
        )
        assert (
            bool(graph.proof_requirements("completion_markers", marker))
            is child_receipts
        )
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        db.close()


def test_mixed_thread_receipts_must_pair_exact_raw_ordinals():
    db = catalog()
    try:
        graph, marker = page_marker(
            db, [(0, None), (1, None)], current_receipts=True, kind="threads"
        )
        assert graph.proof_requirements("completion_markers", marker) is None
    finally:
        db.close()


@pytest.mark.parametrize(
    "pages,boundaries,current_time",
    [
        ([(0, "next")], [(0, None)], 100),
        ([(0, None)], [(0, None)], 101),
        ([(0, None), (1, None)], [(0, "retry"), (1, None)], 100),
    ],
    ids=["contradictory-terminal", "different-observation", "unobserved-errors"],
)
def test_mixed_thread_receipt_cannot_invent_a_boundary_or_capture_time(
    pages, boundaries, current_time
):
    db = catalog()
    try:
        graph, marker = page_marker(
            db,
            pages,
            current_receipts=True,
            current_boundaries=boundaries,
            current_time=current_time,
            kind="threads",
        )
        assert graph.proof_requirements("completion_markers", marker) is None
    finally:
        db.close()


def test_corrupt_body_cannot_invent_partial_graphql_retry():
    db = catalog()
    try:
        graph, marker = page_marker(
            db,
            [(0, None), (1, None)],
            current_receipts=True,
            current_boundaries=[(0, "retry"), (1, None)],
            kind="threads",
        )
        assert graph.proof_requirements("completion_markers", marker) is None
        digest = db.execute("SELECT payload_sha256 FROM fetch_occurrences").fetchone()[
            0
        ]
        corrupt(db, digest, b'{"errors":[{"message":"invented retry"}]}')
        assert graph.proof_requirements("completion_markers", marker) is None
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        db.close()


@pytest.mark.parametrize("unavailable", ["missing", "quarantined"])
def test_partial_root_retry_requires_available_unquarantined_bytes(
    unavailable, monkeypatch
):
    db = catalog()
    body = b'{"errors":[{"message":"admitted partial root"}]}'
    try:
        graph, marker = page_marker(
            db,
            [(0, None), (1, None)],
            current_receipts=True,
            current_boundaries=[(0, "retry"), (1, None)],
            kind="threads",
            raw_body=body,
        )
        assert graph.proof_requirements("completion_markers", marker)
        if unavailable == "missing":
            original_lookup = graph.lookup

            def lookup(table, columns, values):
                return (
                    None
                    if table == "stored_bytes"
                    else original_lookup(table, columns, values)
                )

            monkeypatch.setattr(graph, "lookup", lookup)
        else:
            digest = db.execute(
                "SELECT payload_sha256 FROM fetch_occurrences"
            ).fetchone()[0]
            corrupt(db, digest, b"damaged")
            diagnose_corruption(db, digest)
            # Restored bytes alone do not clear an existing physical quarantine.
            corrupt(db, digest, body)
            assert is_quarantined(db, digest)
        assert graph.proof_requirements("completion_markers", marker) is None
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        db.close()


@pytest.mark.parametrize("pages", [[(0, None)], [(0, "next"), (1, None)]])
def test_valid_historical_sequence_including_empty_members_proves_complete(pages):
    db = catalog()
    try:
        graph, marker = page_marker(db, pages)
        assert graph.proof_requirements("completion_markers", marker)
    finally:
        db.close()


def complete_unit(db):
    expected = fixture(db)
    collection = complete_collection(db, expected["fetch"])
    db.execute(
        "INSERT INTO coverage_scopes VALUES('coverage',?,?,'comment')",
        (expected["repository"], expected["cr"]),
    )
    from repo_catalog.adapters.sqlite.coverage import freeze_complete_proof

    db.execute(
        "INSERT INTO coverage_claims(coverage_scope_id,coverage_state,observed_at_us,details_json) VALUES('coverage','complete',-1,?)",
        (
            freeze_complete_proof(
                db, -1, json.dumps({"fetch_collection_ids": [collection]})
            ),
        ),
    )
    return expected, Graph(db).export(expected["repository"])


@pytest.mark.parametrize("order", ["ordinary", "reversed"])
@pytest.mark.parametrize("damage", ["ordinal", "terminal"])
def test_receiver_and_late_promotion_reject_incomplete_proof_keep_domain_facts(
    order, damage
):
    source, target = catalog(), catalog()
    try:
        expected, unit = complete_unit(source)
        forged = copy.deepcopy(unit)
        fetch = next(
            record
            for record in forged["records"]
            if record["table"] == "fetch_occurrences"
        )
        if damage == "ordinal":
            fetch["values"]["ordinal"] = 2
        else:
            fetch["values"]["next_cursor"] = "next"
        marker = next(
            record
            for record in forged["records"]
            if record["table"] == "completion_markers"
        )
        # Initial selective subset has missing marker dependencies. Later exact
        # (but intrinsically incomplete) fetch facts must not promote it.
        early = {**forged, "records": [marker]}
        assert receive(target, early)["staged_records"]
        if order == "reversed":
            forged["records"].reverse()
        receive(target, forged)
        receive(target, forged)
        assert target.execute("SELECT count(*) FROM completion_markers").fetchone() == (
            0,
        )
        assert target.execute("SELECT count(*) FROM coverage_claims").fetchone() == (0,)
        assert target.execute(
            "SELECT count(*) FROM document_observations"
        ).fetchone() == (1,)
        assert target.execute(
            "SELECT count(*) FROM parsed_result_publications"
        ).fetchone() == (1,)
        assert target.execute(
            "SELECT ordinal,next_cursor FROM fetch_occurrences WHERE fetch_occurrence_uuidv4=?",
            (expected["fetch"],),
        ).fetchone() == (
            2 if damage == "ordinal" else 0,
            "next" if damage == "terminal" else None,
        )
        assert target.execute(
            "SELECT reason FROM exchange_staging WHERE table_name='completion_markers'"
        ).fetchone() == ("missing_completeness_proof",)
        assert target.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        source.close()
        target.close()


@pytest.mark.parametrize("advertised_nonterminal", [False, True])
def test_accepted_partial_graphql_root_retry_retains_valid_complete_proof(
    github_runtime,
    advertised_nonterminal,
):
    store, repo, _, api = github_runtime
    api.reply_count = 1
    api.graphql_partial = True
    original = api.route

    def route(method, path, params, body):
        payload, headers = original(method, path, params, body)
        if method == "POST" and advertised_nonterminal:
            variables = body["variables"]
            if "thread" not in variables and variables.get("cursor") is None:
                payload["data"]["repository"]["pullRequest"]["reviewThreads"][
                    "pageInfo"
                ] = {
                    "hasNextPage": True,
                    "endCursor": "100",
                }
        return payload, headers

    api.route = route
    job = start_threads(store)
    with pytest.raises(CatalogError, match="partial"):
        collect_threads(store, repo, job)
    # Raw pageInfo may advertise terminal or continuation despite errors. Its
    # interpreted receipt retains a retry, followed by a corrected occurrence.
    assert store.one("SELECT next_cursor FROM fetch_occurrences")[0] == (
        "100" if advertised_nonterminal else None
    )
    assert store.one("SELECT next_cursor FROM current_collection_pages")[0] is not None
    api.graphql_partial = False
    collect_threads(store, repo, job)
    graph = Graph(store.connection)
    marker = next(
        row
        for row in graph.rows("completion_markers")
        if row["asserted_state"] == "complete"
    )
    assert graph.proof_requirements("completion_markers", marker)
    root = marker["fetch_collection_id"]
    assert [
        row[0]
        for row in store.all(
            "SELECT ordinal FROM fetch_occurrences WHERE fetch_collection_id=? ORDER BY ordinal",
            (root,),
        )
    ] == ([0, 1, 2] if advertised_nonterminal else [0, 1])
    assert (
        store.one("SELECT coverage_state FROM current_coverage WHERE kind='threads'")[0]
        == "complete"
    )
    target = catalog()
    try:
        unit = graph.export(repo["repository_uuidv4"], fetch_collection_id=root)
        receive(target, unit)
        assert target.execute(
            "SELECT count(*) FROM completion_markers WHERE asserted_state='complete'"
        ).fetchone() == (1,)
    finally:
        target.close()
