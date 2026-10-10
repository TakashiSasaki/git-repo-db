"""Physical deduplication must preserve logical and acquisition identities."""

import hashlib
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.adapters.sqlite.schema import schema_sql
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.payload import PayloadRef
from tests.support.git_payloads import register_git_blob


@pytest.fixture
def db():
    connection = sqlite3.connect(":memory:", isolation_level=None)
    connection.executescript(schema_sql())
    yield connection
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    connection.close()


def test_payload_registration_requires_an_explicit_representation(db):
    with pytest.raises(TypeError, match="representation"):
        intern_payload(db, b"unclassified bytes")
    assert db.execute("SELECT count(*) FROM stored_bytes").fetchone() == (0,)
    assert db.execute("SELECT count(*) FROM payloads").fetchone() == (0,)


def test_same_raw_bytes_across_git_formats_share_one_physical_object(db):
    body = b'{"content":"also a Git blob"}'
    first = register_git_blob(db, body, object_format="sha1")
    second = register_git_blob(db, body, object_format="sha256")
    assert first == second
    assert db.execute("SELECT count(*) FROM stored_bytes").fetchone() == (1,)
    assert db.execute("SELECT count(*) FROM payloads").fetchone() == (1,)
    assert db.execute("SELECT count(*) FROM git_objects").fetchone() == (2,)
    assert [r[1] for r in db.execute("PRAGMA table_info(payloads)")] == [
        "representation",
        "sha256",
    ]


def test_distinct_byte_encodings_remain_distinct(db):
    refs = [register_git_blob(db, value) for value in (b"", b"{}", b"{ }", b"{}\n")]
    assert len(set(refs)) == 4
    assert db.execute("SELECT count(*) FROM stored_bytes").fetchone() == (4,)


def test_independent_acquisitions_keep_separate_captures_for_shared_bytes(db):
    repository = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'fixture','{}')",
        (repository,),
    )
    register_git_blob(db, b"same canonical Git content")
    object_id = db.execute("SELECT git_object_id FROM git_objects").fetchone()[0]
    for timestamp in (-1, 0):
        acquisition = str(uuid.uuid4())
        db.execute(
            "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,kind,observed_at_us,request) VALUES(?,?,'git',?,'{}')",
            (acquisition, repository, timestamp),
        )
        db.execute(
            "INSERT INTO repository_object_sources VALUES(?,?,?)",
            (repository, object_id, acquisition),
        )
    assert db.execute("SELECT count(*) FROM git_acquisitions").fetchone() == (2,)
    assert db.execute("SELECT count(*) FROM repository_object_sources").fetchone() == (
        2,
    )
    assert db.execute("SELECT count(*) FROM stored_bytes").fetchone() == (1,)
    assert db.execute(
        "SELECT observed_at_us FROM git_acquisitions ORDER BY observed_at_us"
    ).fetchall() == [(-1,), (0,)]


def test_declared_hash_mismatch_is_rejected_before_any_admission(db):
    with pytest.raises(CatalogError) as error:
        intern_payload(
            db,
            b"invalid",
            expected_sha256=hashlib.sha256(b"valid").digest(),
            representation="git-object-raw-v1",
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
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES('dddddddd-dddd-4ddd-8ddd-dddddddddddd','dddddddd-dddd-4ddd-8ddd-dddddddddddd','{}')"
    )
    with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
        intern_payload(db, b"raw blob", representation="git-object-raw-v1")
    assert db.in_transaction
    assert db.execute("SELECT count(*) FROM stored_bytes").fetchone() == (0,)
    db.commit()
    assert db.execute("SELECT count(*) FROM repositories").fetchone() == (1,)


def test_corrupt_existing_bytes_are_preserved_and_never_silently_repaired(db):
    digest = hashlib.sha256(b"good").digest()
    # Simulate corrupt storage, bypassing only application admission.
    db.execute("INSERT INTO stored_bytes VALUES(?,?,?)", (digest, b"bad!", 4))
    with pytest.raises(CatalogError) as error:
        intern_payload(db, b"good", representation="git-object-raw-v1")
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
    intern_payload(db, b"first", representation="git-object-raw-v1")
    with pytest.raises(CatalogError) as error:
        intern_payload(db, b"other", representation="git-object-raw-v1")
    assert error.value.code == "PAYLOAD_HASH_COLLISION"
    assert db.execute("SELECT body FROM stored_bytes").fetchone() == (b"first",)
    assert db.execute("SELECT count(*) FROM payloads").fetchone() == (1,)


@pytest.mark.parametrize("table", ["stored_bytes", "payloads"])
def test_replace_update_delete_cannot_mutate_admitted_identity(db, table):
    reference = register_git_blob(db, b"raw Git content")
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
    assert db.execute("SELECT body FROM stored_bytes").fetchone() == (
        b"raw Git content",
    )


def test_git_object_reference_requires_both_components_and_its_representation(db):
    body = b"raw Git blob content"
    reference = intern_payload(db, body, representation="git-object-raw-v1")
    object_id = db.execute(
        "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES('sha1',?,'blob',?,1)",
        (hashlib.sha1(f"blob {len(body)}\0".encode() + body).digest(), len(body)),
    ).lastrowid
    for representation, digest in (
        (None, reference.sha256),
        (reference.representation, None),
        ("decoded_api", reference.sha256),
        (reference.representation, b"x" * 32),
    ):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO git_object_payloads VALUES(?,?,?)",
                (object_id, representation, digest),
            )
    db.execute(
        "INSERT INTO git_object_payloads VALUES(?,?,?)",
        (object_id, *reference.parameters()),
    )


def test_rejection_diagnostics_have_no_api_payload_reference_or_logical_fk(db):
    assert [
        row[1] for row in db.execute("PRAGMA table_xinfo(unresolved_payloads)")
    ] == [
        "stored_sha256",
        "detected_at_us",
        "diagnostic_json",
        "unresolved_payload_id",
        "reason",
    ]
    foreign_keys = db.execute("PRAGMA foreign_key_list(unresolved_payloads)").fetchall()
    assert len(foreign_keys) == 1
    assert foreign_keys[0][2:5] == ("stored_bytes", "stored_sha256", "sha256")
    assert not db.execute(
        "SELECT 1 FROM sqlite_schema WHERE name='unresolved_payloads_fk_1'"
    ).fetchone()
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO unresolved_payloads(reason) VALUES('API_SCHEMA')")


def test_portable_json_reference_is_exact_lowercase_hex():
    ref = PayloadRef("git-object-raw-v1", bytes(range(32)))
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
