"""Physical deduplication must preserve logical and acquisition identities."""

import hashlib
import sqlite3

import pytest

from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.adapters.sqlite.schema import schema_sql
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.payload import PayloadRef


@pytest.fixture
def db():
    connection = sqlite3.connect(":memory:", isolation_level=None)
    connection.executescript(schema_sql())
    yield connection
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    connection.close()


def test_same_bytes_across_representations_share_one_physical_object(db):
    first = intern_payload(db, b"\x00{}\xff")
    assert intern_payload(db, b"\x00{}\xff") == first
    second = intern_payload(db, b"\x00{}\xff", representation="legacy_normalized")
    assert first != second
    assert first.sha256 == second.sha256
    assert db.execute("SELECT count(*) FROM stored_bytes").fetchone() == (1,)
    assert db.execute("SELECT count(*) FROM payloads").fetchone() == (2,)
    assert [r[1] for r in db.execute("PRAGMA table_info(payloads)")] == [
        "representation",
        "sha256",
    ]


def test_distinct_byte_encodings_remain_distinct(db):
    refs = [intern_payload(db, value) for value in (b"", b"{}", b"{ }", b"{}\n")]
    assert len(set(refs)) == 4
    assert db.execute("SELECT count(*) FROM stored_bytes").fetchone() == (4,)


def test_independent_fetches_keep_separate_occurrences_for_shared_bytes(db):
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES('repo','repo','{}')"
    )
    db.execute(
        "INSERT INTO resume_scopes(resume_scope_id,repository_uuidv4,request_context,parser_version,profile_version,confidence) VALUES('scope','repo','{}','parser','profile','proven')"
    )
    db.execute(
        "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,kind,resume_scope_id) VALUES('collection','repo','fixture','scope')"
    )
    for ordinal, timestamp in enumerate((-1, 0)):
        ref = intern_payload(db, b"same response")
        db.execute(
            "INSERT INTO fetch_occurrences(fetch_collection_id,ordinal,payload_representation,payload_sha256,request,observed_at_us,parsed_at_us) VALUES('collection',?,?,?,'{}',?,1)",
            (ordinal, *ref.parameters(), timestamp),
        )
    assert db.execute(
        "SELECT count(DISTINCT fetch_occurrence_id),count(DISTINCT payload_sha256) FROM fetch_occurrences"
    ).fetchone() == (2, 1)
    assert db.execute(
        "SELECT observed_at_us FROM fetch_occurrences ORDER BY ordinal"
    ).fetchall() == [(-1,), (0,)]


def test_declared_hash_mismatch_is_rejected_before_any_admission(db):
    with pytest.raises(CatalogError) as error:
        intern_payload(
            db, b"invalid", expected_sha256=hashlib.sha256(b"valid").digest()
        )
    assert error.value.code == "PAYLOAD_DIGEST_MISMATCH"
    assert db.execute("SELECT count(*) FROM stored_bytes").fetchone() == (0,)
    assert db.execute("SELECT count(*) FROM payloads").fetchone() == (0,)


def test_physical_and_logical_admission_is_atomic_inside_caller_transaction(db):
    db.execute(
        "CREATE TRIGGER reject_payload BEFORE INSERT ON payloads BEGIN SELECT RAISE(ABORT,'injected failure'); END"
    )
    db.execute("BEGIN IMMEDIATE")
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES('unrelated','unrelated','{}')"
    )
    with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
        intern_payload(db, b"response")
    assert db.in_transaction
    assert db.execute("SELECT count(*) FROM stored_bytes").fetchone() == (0,)
    db.commit()
    assert db.execute("SELECT count(*) FROM repositories").fetchone() == (1,)


def test_corrupt_existing_bytes_are_preserved_and_never_silently_repaired(db):
    digest = hashlib.sha256(b"good").digest()
    # Simulate corrupt storage, bypassing only application admission.
    db.execute("INSERT INTO stored_bytes VALUES(?,?,?)", (digest, b"bad!", 4))
    with pytest.raises(CatalogError) as error:
        intern_payload(db, b"good")
    assert error.value.code == "PAYLOAD_CORRUPTION"
    assert db.execute("SELECT body FROM stored_bytes").fetchone() == (b"bad!",)
    assert db.execute("SELECT count(*) FROM payloads").fetchone() == (0,)


def test_real_collision_is_distinguished_from_bad_declared_hash(db, monkeypatch):
    from repo_catalog.adapters.sqlite import payloads

    digest = b"h" * 32

    class CollisionHash:
        def digest(self):
            return digest

    monkeypatch.setattr(payloads.hashlib, "sha256", lambda body: CollisionHash())
    intern_payload(db, b"first")
    with pytest.raises(CatalogError) as error:
        intern_payload(db, b"other", representation="legacy_normalized")
    assert error.value.code == "PAYLOAD_HASH_COLLISION"
    assert db.execute("SELECT body FROM stored_bytes").fetchone() == (b"first",)
    assert db.execute("SELECT count(*) FROM payloads").fetchone() == (1,)


@pytest.mark.parametrize("table", ["stored_bytes", "payloads"])
def test_replace_update_delete_cannot_mutate_admitted_identity(db, table):
    reference = intern_payload(db, b"response")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(f"DELETE FROM {table}")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(f"UPDATE {table} SET sha256=?", (b"x" * 32,))
    with pytest.raises(sqlite3.IntegrityError):
        if table == "stored_bytes":
            db.execute(
                "INSERT OR REPLACE INTO stored_bytes VALUES(?,?,?)",
                (reference.sha256, b"tampered", 8),
            )
        else:
            db.execute(
                "INSERT OR REPLACE INTO payloads VALUES(?,?)", reference.parameters()
            )
    assert db.execute("SELECT body FROM stored_bytes").fetchone() == (b"response",)


def test_logical_reference_requires_both_components(db):
    reference = intern_payload(db, b"response")
    for representation, digest in (
        (None, reference.sha256),
        (reference.representation, None),
        ("legacy_normalized", reference.sha256),
    ):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO unresolved_payloads(payload_representation,payload_sha256,reason) VALUES(?,?,'gap')",
                (representation, digest),
            )
    db.execute(
        "INSERT INTO unresolved_payloads(payload_representation,payload_sha256,reason) VALUES(?,?,'gap')",
        reference.parameters(),
    )


def test_portable_json_reference_is_exact_lowercase_hex():
    ref = PayloadRef("decoded_api", bytes(range(32)))
    assert PayloadRef.from_json(ref.as_json()) == ref
    assert len(ref.as_json()["sha256"]) == 64


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"representation": "decoded_api", "sha256": "A" * 64},
        {"representation": "decoded_api", "sha256": "0" * 63},
        {"representation": "other", "sha256": "0" * 64},
        {"representation": "decoded_api", "sha256": "0" * 64, "payload_id": 1},
    ],
)
def test_noncanonical_json_reference_is_rejected(value):
    with pytest.raises(CatalogError) as error:
        PayloadRef.from_json(value)
    assert error.value.code == "INVALID_PAYLOAD_REFERENCE"
