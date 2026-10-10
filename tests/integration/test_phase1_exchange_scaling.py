"""Measure real indexed selected closures, independently of wall-clock speed."""

import copy
import hashlib
import json

from repo_catalog.adapters.git.parsing import install_git_object
from repo_catalog.adapters.sqlite.coverage import admit_claim
from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.exchange import Graph, canonical, encode
from repo_catalog.domain.current_state import fingerprint_candidate
from tests.integration.test_catalog3_exchange import (
    candidate,
    catalog,
    complete_collection,
    fixture,
    uid,
)
from tests.integration.test_catalog3_exchange_integrity_audit import git_fixture


def _measure_vm_steps(db, operation):
    callbacks = 0

    def progress():
        nonlocal callbacks
        callbacks += 1
        return 0

    db.set_progress_handler(progress, 1)
    try:
        value = operation()
    finally:
        db.set_progress_handler(None, 0)
    return callbacks, value


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


def test_selected_terminal_claim_work_ignores_same_scope_later_partials():
    db = catalog()
    try:
        expected = fixture(db)
        complete_collection(db, expected["collection"])
        scope = uid()
        db.execute(
            "INSERT INTO coverage_scopes VALUES(?,?,?,'pr-body')",
            (scope, expected["repository"], expected["cr"]),
        )
        marker = db.execute(
            "SELECT completion_marker_uuidv4 FROM completion_markers WHERE fetch_collection_id=?",
            (expected["collection"],),
        ).fetchone()[0]
        admit_claim(
            db,
            scope,
            "complete",
            1,
            json.dumps({"completion_marker_uuidv4s": [marker]}),
        )

        def export():
            return Graph(db, persist_identities=False).export(
                expected["repository"], fetch_collection_id=expected["collection"]
            )

        baseline, original = _measure_vm_steps(db, export)
        assert any(
            record["table"] == "coverage_claims" for record in original["records"]
        )
        for start, stop in ((0, 1000), (1000, 5000)):
            with db:
                for index in range(start, stop):
                    admit_claim(db, scope, "partial", index + 2, "{}")
            steps, unit = _measure_vm_steps(db, export)
            assert unit["records"] == original["records"]
            assert steps <= baseline * 1.1 + 500, (baseline, steps)
        plan = db.execute(
            "EXPLAIN QUERY PLAN SELECT coverage_claim_id FROM coverage_claim_markers WHERE completion_marker_uuidv4=?",
            (marker,),
        ).fetchall()
        assert any("coverage_claim_markers_marker" in row[-1] for row in plan)
        assert db.execute("SELECT count(*) FROM coverage_claim_markers").fetchone() == (
            1,
        )
    finally:
        db.close()


def test_selected_git_work_ignores_unrelated_same_repository_pending_roots():
    from tests.integration.test_catalog3_exchange import receive

    db = catalog()
    try:
        expected = git_fixture(db)
        root = db.execute(
            "SELECT acquisition_root_id FROM acquisition_roots"
        ).fetchone()[0]
        db.execute(
            "INSERT INTO root_origins(acquisition_root_id,repository_uuidv4,origin_kind,raw_ref_name,source_ordinal,snapshot_id) VALUES(?,?,'ref',?,0,?)",
            (root, expected["repository"], b"refs/heads/main", expected["snapshot"]),
        )
        initial = Graph(db).export(
            expected["repository"], git_acquisition_id=expected["acquisition"]
        )
        template = next(
            record for record in initial["records"] if record["table"] == "root_origins"
        )
        root_identity = json.loads(
            template["values"]["acquisition_root_id"]["$ref"].split(":", 1)[1]
        )
        origin_identity = json.loads(template["key"].split(":", 1)[1])

        def export():
            return Graph(db).export(
                expected["repository"], git_acquisition_id=expected["acquisition"]
            )

        baseline, original = _measure_vm_steps(db, export)
        for start, stop in ((0, 1000), (1000, 5000)):
            records = []
            for _ in range(start, stop):
                record = copy.deepcopy(template)
                record["key"] = "root_origins:" + json.dumps(
                    {key: uid() for key in origin_identity},
                    sort_keys=True,
                    separators=(",", ":"),
                )
                record["values"]["acquisition_root_id"]["$ref"] = (
                    "acquisition_roots:"
                    + json.dumps(
                        {key: uid() for key in root_identity},
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
                records.append(record)
            assert (
                receive(db, {**initial, "records": records})["staged_records"] == stop
            )
            steps, unit = _measure_vm_steps(db, export)
            assert unit == original
            assert steps <= baseline * 1.1 + 1000, (baseline, steps)
        assert db.execute(
            "SELECT count(*) FROM exchange_staging WHERE reason='missing_dependency'"
        ).fetchone() == (5000,)
    finally:
        db.close()


def test_git_byte_authorization_visits_selected_records_linearly():
    db = catalog()
    try:
        expected = git_fixture(db)
        graph = Graph(db)
        repo_key = graph.key(
            "repositories",
            graph.lookup(
                "repositories", ("repository_uuidv4",), (expected["repository"],)
            ),
        )
        acquisition_key = graph.key(
            "git_acquisitions",
            graph.lookup(
                "git_acquisitions", ("git_acquisition_id",), (expected["acquisition"],)
            ),
        )
        visits = 0

        class CountedRecord(dict):
            def __getitem__(self, key):
                nonlocal visits
                if key == "table":
                    visits += 1
                return super().__getitem__(key)

        def record(table, values, identities):
            return CountedRecord(
                table=table,
                values=values,
                key=table + ":" + canonical({key: values[key] for key in identities}),
            )

        def ref(key, column):
            return {"$ref": key, "column": column}

        for count in (32, 128, 512, 1024):
            records = []
            for index in range(count):
                raw = f"actual selected blob {index}".encode()
                digest = hashlib.sha256(raw).digest()
                oid = hashlib.sha1(f"blob {len(raw)}".encode() + b"\0" + raw).digest()
                obj = record(
                    "git_objects",
                    {
                        "object_format": "sha1",
                        "oid": encode(oid),
                        "type": "blob",
                        "size": len(raw),
                        "verified": 1,
                    },
                    ("object_format", "oid"),
                )
                stored = record(
                    "stored_bytes",
                    {
                        "sha256": encode(digest, "sha256"),
                        "body": encode(raw),
                        "byte_length": len(raw),
                    },
                    ("sha256",),
                )
                payload = record(
                    "payloads",
                    {
                        "representation": "git-object-raw-v1",
                        "sha256": ref(stored["key"], "sha256"),
                    },
                    ("representation", "sha256"),
                )
                mapping = record(
                    "git_object_payloads",
                    {
                        "git_object_id": ref(obj["key"], "git_object_id"),
                        "payload_representation": ref(payload["key"], "representation"),
                        "payload_sha256": ref(payload["key"], "sha256"),
                    },
                    ("git_object_id",),
                )
                association = record(
                    "repository_object_sources",
                    {
                        "repository_uuidv4": ref(repo_key, "repository_uuidv4"),
                        "git_object_id": ref(obj["key"], "git_object_id"),
                        "git_acquisition_id": ref(
                            acquisition_key, "git_acquisition_id"
                        ),
                    },
                    ("repository_uuidv4", "git_object_id", "git_acquisition_id"),
                )
                records.extend((obj, stored, payload, mapping, association))
            for item in records:
                graph.validate_record(item)
            visits = 0
            assert (
                len(graph._git_authorizations(records, include_staging=False))
                == 4 * count
            )
            assert visits <= 3 * len(records), (count, visits)
    finally:
        db.close()
