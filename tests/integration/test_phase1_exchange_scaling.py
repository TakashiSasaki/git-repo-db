"""Measure real indexed selected closures, independently of wall-clock speed."""

import hashlib
import json

from repo_catalog.adapters.git.parsing import install_git_object
from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.domain.current_state import fingerprint_candidate
from tests.integration.test_catalog3_exchange import (
    candidate,
    catalog,
    complete_collection,
    fixture,
    uid,
)


def _measure_vm_steps(db, operation):
    callbacks = 0

    def progress():
        nonlocal callbacks
        callbacks += 1
        return 0

    db.set_progress_handler(progress, 100)
    try:
        value = operation()
    finally:
        db.set_progress_handler(None, 0)
    return callbacks * 100, value


def _add_captures(db, expected, count, start=0):
    """Same-repository collection/code/Git captures with real canonical bodies."""
    scope = json.dumps(candidate(expected)["acquisition_scope"])
    api, proof = CurrentApiState(db), CurrentCollectionProof(db)
    db.execute("BEGIN")
    try:
        for index in range(start, start + count):
            collection, code_collection, listing, acquisition = (
                uid(),
                uid(),
                uid(),
                uid(),
            )
            values = candidate(
                expected, "issue-comment", f"unselected {index}", updated=index + 10
            )
            values["provider_change_request_document_id"] = str(index + 10)
            assert api.admit("document_state", values).status == "accepted"
            db.execute(
                "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,kind,scope_json) VALUES(?,?,?,'comments',?)",
                (collection, expected["repository"], expected["cr"], scope),
            )
            proof.page(
                collection,
                0,
                index + 10,
                None,
                [
                    {
                        "family": "document",
                        "change_request_id": expected["cr"],
                        "kind": "issue-comment",
                        "provider_change_request_document_id": str(index + 10),
                        "state_digest": fingerprint_candidate(values),
                    }
                ],
                parser_module="synthetic",
                parser_version="v1",
            )
            complete_collection(db, collection)
            db.execute(
                "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,kind,scope_json) VALUES(?,?,?,'pr-commits',?)",
                (code_collection, expected["repository"], expected["cr"], scope),
            )
            db.execute(
                "INSERT INTO code_listings(code_listing_id,change_request_id,fetch_collection_id,kind,object_format) VALUES(?,?,?,'commits','sha1')",
                (listing, expected["cr"], code_collection),
            )
            empty_tree_oid = hashlib.sha1(b"tree 0\0").digest()
            body = (
                b"tree "
                + empty_tree_oid.hex().encode()
                + b"\n\n"
                + f"actual Git history {index}".encode()
            )
            oid = hashlib.sha1(f"commit {len(body)}\0".encode() + body).digest()
            db.execute(
                "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,kind,object_format,request,roots_manifest) VALUES(?,?,'git','sha1','{}','[]')",
                (acquisition, expected["repository"]),
            )
            install_git_object(
                db,
                "sha1",
                oid,
                "commit",
                body,
                repository_uuid=expected["repository"],
                acquisition=acquisition,
            )
            db.execute(
                "INSERT INTO code_commits VALUES(?,0,?,'sha1',?,'{}')",
                (listing, expected["repository"], oid),
            )
        db.commit()
    except BaseException:
        db.rollback()
        raise


def test_selected_collection_work_independent_of_same_repository_history():
    db = catalog()
    try:
        expected = fixture(db)
        complete_collection(db, expected["collection"])

        def export():
            return Graph(db, persist_identities=False).export(
                expected["repository"], fetch_collection_id=expected["collection"]
            )

        baseline, original = _measure_vm_steps(db, export)
        measurements = []
        for count, start in ((1000, 0), (4000, 1000)):
            _add_captures(db, expected, count, start)
            steps, unit = _measure_vm_steps(db, export)
            assert unit["records"] == original["records"]
            assert steps <= baseline * 1.3 + 5000, (baseline, steps)
            measurements.append(steps)
        assert db.execute("SELECT count(*) FROM fetch_collections").fetchone() == (
            10001,
        )
        assert db.execute("SELECT count(*) FROM git_acquisitions").fetchone() == (5000,)
        assert db.execute("SELECT count(*) FROM code_commits").fetchone() == (5000,)
        assert measurements[-1] <= measurements[0] * 1.2 + 2000
    finally:
        db.close()


def test_selected_member_volume_has_linear_vm_work():
    db = catalog()
    try:
        expected = fixture(db)
        api = CurrentApiState(db)
        measured = []
        for size in (20, 200, 1000):
            members = []
            for index in range(size):
                values = candidate(
                    expected, "issue-comment", f"selected {index}", updated=index + 20
                )
                values["provider_change_request_document_id"] = str(index + 200000)
                assert api.admit("document_state", values).status in (
                    "accepted",
                    "duplicate",
                    "identical",
                    "stale",
                )
                members.append(
                    {
                        "family": "document",
                        "change_request_id": expected["cr"],
                        "kind": "issue-comment",
                        "provider_change_request_document_id": values[
                            "provider_change_request_document_id"
                        ],
                        "state_digest": fingerprint_candidate(values),
                    }
                )
            collection = uid()
            db.execute(
                "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,kind,scope_json) VALUES(?,?,?,'comments',?)",
                (
                    collection,
                    expected["repository"],
                    expected["cr"],
                    json.dumps(candidate(expected)["acquisition_scope"]),
                ),
            )
            CurrentCollectionProof(db).page(
                collection,
                0,
                size,
                None,
                members,
                parser_module="synthetic",
                parser_version="v1",
            )
            complete_collection(db, collection)
            steps, unit = _measure_vm_steps(
                db,
                lambda: Graph(db, persist_identities=False).export(
                    expected["repository"], fetch_collection_id=collection
                ),
            )
            assert sum(r["table"] == "document_state" for r in unit["records"]) == size
            measured.append((size, steps))
        for (small, small_steps), (large, large_steps) in zip(measured, measured[1:]):
            assert large_steps <= small_steps * (large / small) * 1.3 + 5000, measured
    finally:
        db.close()
