"""Both rejected bypasses and admitted lifecycles on the complete P1 DDL."""

import hashlib
import json
import sqlite3

import pytest

from tests.integration.test_target_schema import TIME, B, H, put
from tests.integration.test_target_schema import target as target
from tests.support.p1_admission import (
    hydrate_text,
    prepare_git_verification,
    prepare_text_completion,
    record_rediscovery,
    verify_git_object,
)


def append(db, kind, occurrence_id=None, position=99, listing=None, oid=H):
    values = dict(
        listing_id=listing or "listing-a-" + kind,
        occurrence_id=occurrence_id or (1 if kind == "commits" else 2),
        position=position,
        payload="{}",
    )
    if kind == "commits":
        put(db, "code_commits", **values, object_format="sha1", oid=oid)
    else:
        put(db, "code_file_changes", **values, raw_path=b"synthetic.txt")


def code_observation(db, id, state, prefix="listing-a-"):
    put(
        db,
        "code_observations",
        id=id,
        change_request_id="cr-a",
        observation_id=1,
        commit_listing_id=prefix + "commits",
        file_listing_id=prefix + "files",
        state=state,
        object_format="sha1",
        head_oid=H,
        base_oid=B,
        details="{}",
    )


@pytest.mark.parametrize("kind", ["commits", "files"])
@pytest.mark.parametrize("referenced", [False, True])
@pytest.mark.parametrize("mode", ["autocommit", "transaction", "savepoint"])
@pytest.mark.parametrize("attack", ["delete-recreate", "replace-on", "replace-off"])
def test_completed_listing_cannot_reopen(target, kind, referenced, mode, attack):
    db = target
    listing = "listing-a-" + kind
    for item_kind in ("commits", "files"):
        append(db, item_kind, position=0)
    db.execute(
        "UPDATE code_listing_progress SET state='complete',terminal=1,"
        "context_proven=1,page_count=1 WHERE listing_id LIKE 'listing-a-%'"
    )
    if referenced:
        code_observation(db, 1, "complete")
    db.execute(
        "PRAGMA recursive_triggers=" + ("OFF" if attack == "replace-off" else "ON")
    )
    if mode != "autocommit":
        db.execute("BEGIN")
    if mode == "savepoint":
        db.execute("SAVEPOINT attack")
    with pytest.raises(sqlite3.IntegrityError):
        if attack == "delete-recreate":
            db.execute(
                "DELETE FROM code_listing_progress WHERE listing_id=?", (listing,)
            )
            db.execute(
                "INSERT INTO code_listing_progress VALUES(?,'partial',0,0,0)",
                (listing,),
            )
        else:
            db.execute(
                "INSERT OR REPLACE INTO code_listing_progress VALUES(?,'partial',0,0,0)",
                (listing,),
            )
    # A statement abort does not itself roll back an outer transaction. The
    # surviving marker must still seal the collection before a successful COMMIT.
    with pytest.raises(sqlite3.IntegrityError):
        append(db, kind)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "UPDATE code_listing_progress SET state='partial',terminal=0,"
            "context_proven=0,page_count=0 WHERE listing_id=?",
            (listing,),
        )
    if mode == "savepoint":
        db.execute("RELEASE attack")
    if mode != "autocommit":
        db.execute("COMMIT")
    assert db.execute(
        "SELECT state,page_count FROM code_listing_progress WHERE listing_id=?",
        (listing,),
    ).fetchone() == ("complete", 1)
    table = "code_commits" if kind == "commits" else "code_file_changes"
    assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1
    assert db.execute("SELECT state FROM code_observations").fetchall() == (
        [("complete",)] if referenced else []
    )


@pytest.mark.parametrize("kind", ["commits", "files"])
@pytest.mark.parametrize("state", [None, "unknown"])
def test_listing_initialization_requires_partial_marker(target, kind, state):
    db = target
    listing = "listing-a-" + kind
    db.execute("DELETE FROM code_listing_progress WHERE listing_id=?", (listing,))
    if state is not None:
        db.execute(
            "INSERT INTO code_listing_progress VALUES(?,'unknown',0,0,0)", (listing,)
        )
    with pytest.raises(sqlite3.IntegrityError):
        append(db, kind, position=0)
    if state is None:
        db.execute(
            "INSERT INTO code_listing_progress VALUES(?,'partial',0,0,0)", (listing,)
        )
    else:
        db.execute(
            "UPDATE code_listing_progress SET state='partial' WHERE listing_id=?",
            (listing,),
        )
    append(db, kind, position=0)


def content_claim(db, raw, *, state="eligible", anchors=("md5", "sha1", "sha256")):
    put(
        db,
        "contents",
        id=1,
        byte_length=len(raw),
        raw_text=None,
        text_state=state,
        created_at=TIME,
    )
    for algorithm in anchors:
        put(
            db,
            "content_digests",
            content_id=1,
            representation="raw-content-v1",
            algorithm=algorithm,
            digest=hashlib.new(algorithm, raw).digest(),
            verified_at=TIME,
            pipeline_version="synthetic-p1",
        )


def git_claim(db, raw, *, algorithm="sha1", kind="blob", oid=None, size=None):
    put(
        db,
        "git_objects",
        id=1,
        object_format=algorithm,
        oid=oid
        or hashlib.new(algorithm, f"{kind} {len(raw)}\0".encode() + raw).digest(),
        type=kind,
        size=len(raw) if size is None else size,
        verified=0,
    )


def test_local_text_completion_reaches_query_and_search(target, tmp_path):
    db = target
    raw = "synthetic 日本語\n".encode("utf-8")
    local = tmp_path / "blob.raw"
    local.write_bytes(raw)
    content_claim(db, raw)
    git_claim(db, raw)
    put(db, "blob_content_map", object_id=1, content_id=1, acquisition_id="run-a")
    put(
        db,
        "cache_locators",
        id="local-raw",
        repo_id="a",
        path=str(tmp_path),
        access="source_readonly",
        state="available",
    )
    put(
        db,
        "content_locations",
        content_id=1,
        kind="cache",
        locator=local.as_uri(),
        cache_id="local-raw",
        state="available",
    )
    assert db.execute("SELECT raw_text FROM contents").fetchone() == (None,)
    supplied = local.read_bytes()  # no network/Git; before any write transaction
    assert hydrate_text(db, 1, supplied) == raw.decode("utf-8")
    verify_git_object(db, 1, supplied)
    result = db.execute(
        "SELECT CAST(c.raw_text AS BLOB),l.locator FROM blob_content_map m "
        "JOIN contents c ON c.id=m.content_id JOIN content_locations l ON l.content_id=c.id "
        "WHERE m.object_id=1 AND l.kind='durable-content' AND l.state='available'"
    ).fetchone()
    assert result == (raw, "contents:1")
    db.execute(
        "INSERT INTO search_documents(id,kind,source_key,body,metadata) "
        "SELECT 1,'code','content:1',c.raw_text,'{}' FROM contents c "
        "JOIN content_locations l ON l.content_id=c.id WHERE c.id=1 "
        "AND l.kind='durable-content' AND l.locator='contents:1' "
        "AND l.state='available' AND c.raw_text IS NOT NULL"
    )
    assert db.execute("SELECT body FROM search_documents WHERE id=1").fetchone() == (
        raw.decode("utf-8"),
    )
    hydrate_text(db, 1, supplied)
    verify_git_object(db, 1, supplied)
    assert db.execute("SELECT count(*) FROM content_locations").fetchone()[0] == 2
    assert db.execute("SELECT created_at FROM contents").fetchone()[0] == TIME
    assert db.execute(
        "SELECT DISTINCT verified_at FROM content_digests"
    ).fetchall() == [(TIME,)]
    for sql, args in (
        ("UPDATE contents SET raw_text=? WHERE id=1", ("x" * len(raw),)),
        ("UPDATE contents SET raw_text=NULL WHERE id=1", ()),
        ("UPDATE contents SET text_state='unknown' WHERE id=1", ()),
        ("UPDATE git_objects SET verified=0 WHERE id=1", ()),
    ):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(sql, args)


@pytest.mark.parametrize(
    "case", ["digest", "length", "nul", "non-utf8", "no-sha256", "noneligible"]
)
def test_text_admission_rejects_unproven_completion(target, case):
    db = target
    stored = b"abc"
    supplied = {
        "digest": b"def",  # identical length must still fail the digest check
        "length": b"abcd",
        "nul": b"a\0c",
        "non-utf8": b"a\xffc",
    }.get(case, stored)
    content_claim(
        db,
        stored,
        anchors=("sha1",) if case == "no-sha256" else ("sha256",),
        state="unknown" if case == "noneligible" else "eligible",
    )
    with pytest.raises(ValueError):
        hydrate_text(db, 1, supplied)
    assert db.execute("SELECT raw_text,created_at FROM contents").fetchone() == (
        None,
        TIME,
    )
    assert db.execute("SELECT count(*) FROM content_locations").fetchone()[0] == 0


def test_sql_text_completion_shape_and_length_guards(target):
    db = target
    content_claim(db, b"abc", anchors=())
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE contents SET raw_text='abc' WHERE id=1")
    put(
        db,
        "content_digests",
        content_id=1,
        representation="raw-content-v1",
        algorithm="sha256",
        digest=hashlib.sha256(b"abc").digest(),
        pipeline_version="synthetic-p1",
    )
    for text in ("too-long", "a\0c"):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE contents SET raw_text=? WHERE id=1", (text,))
    db.execute("UPDATE contents SET raw_text='abc' WHERE id=1")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE contents SET raw_text='def' WHERE id=1")


@pytest.mark.parametrize("algorithm", ["sha1", "sha256"])
def test_git_verification_is_monotonic_and_checks_bytes(target, algorithm):
    db = target
    raw = b"abc"
    git_claim(db, raw, algorithm=algorithm)
    for wrong in (b"def", b"abcd"):
        with pytest.raises(ValueError, match="size/type/OID"):
            verify_git_object(db, 1, wrong)
        assert db.execute("SELECT verified FROM git_objects").fetchone()[0] == 0
    verify_git_object(db, 1, raw)
    verify_git_object(db, 1, raw)
    assert db.execute("SELECT verified FROM git_objects").fetchone()[0] == 1
    for assignment in ("verified=0", "size=4", "type='tree'", "oid=zeroblob(20)"):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(f"UPDATE git_objects SET {assignment} WHERE id=1")


def test_git_verification_rejects_wrong_typed_header(target):
    raw = b"abc"
    git_claim(target, raw, kind="commit", oid=hashlib.sha1(b"blob 3\0" + raw).digest())
    with pytest.raises(ValueError, match="size/type/OID"):
        verify_git_object(target, 1, raw)
    assert target.execute("SELECT verified FROM git_objects").fetchone()[0] == 0


def test_source_pair_rediscovery_aggregates_without_rewriting_events(target):
    db = target
    times = [TIME, "2026-10-05T13:00:00Z", "2026-10-05T11:00:00Z", TIME]
    for index, observed_at in enumerate(times, 1):
        put(
            db,
            "inventory_observations",
            id=f"discovery-{index}",
            source_id="source",
            asserted_state="partial",
            scope='{"repo_ids":["a"]}',
            observed_at=observed_at,
        )
        record_rediscovery(db, "source", "a", observed_at)
    assert db.execute(
        "SELECT first_seen,last_seen FROM source_repositories"
    ).fetchall() == [(times[2], times[1])]
    assert db.execute(
        "SELECT observed_at FROM inventory_observations ORDER BY id"
    ).fetchall() == [(time,) for time in times]
    for assignment in (
        "last_seen=NULL",
        "last_seen='2026-10-05T10:00:00Z'",
        "first_seen=NULL",
        "first_seen='2026-10-05T12:00:00Z'",
        "last_seen='invalid'",
        "repo_id='b'",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(f"UPDATE source_repositories SET {assignment}")
    with pytest.raises(ValueError, match="timezone"):
        record_rediscovery(db, "source", "a", "2026-10-05T14:00:00")
    for invalid in ("2026-10-05T14:00:00.1234567Z", "2026-02-30T14:00:00Z"):
        with pytest.raises(ValueError):
            record_rediscovery(db, "source", "a", invalid)


def test_source_unknown_times_and_submillisecond_replay(target):
    db = target
    put(db, "source_repositories", source_id="source", repo_id="a")
    later = "2026-10-05T12:00:00.000200Z"
    earlier = "2026-10-05T12:00:00.000100Z"
    record_rediscovery(db, "source", "a", later)
    record_rediscovery(db, "source", "a", earlier)
    record_rediscovery(db, "source", "a", "2026-10-05T12:00:00.000100+00:00")
    assert db.execute(
        "SELECT first_seen,last_seen FROM source_repositories"
    ).fetchone() == (
        earlier,
        later,
    )


def test_monotonic_completions_can_rollback_and_restart(target):
    db = target
    raw = b"abc"
    content_claim(db, raw)
    git_claim(db, raw)
    record_rediscovery(db, "source", "a", TIME)
    later = "2026-10-05T13:00:00Z"
    save_text = prepare_text_completion(db, 1, raw)
    save_verification = prepare_git_verification(db, 1, raw)
    db.execute("BEGIN")
    with pytest.raises(ValueError, match="before the writer transaction"):
        hydrate_text(db, 1, raw)
    with pytest.raises(ValueError, match="before the writer transaction"):
        verify_git_object(db, 1, raw)
    save_text()
    save_verification()
    record_rediscovery(db, "source", "a", later)
    db.execute("ROLLBACK")
    assert db.execute("SELECT raw_text,created_at FROM contents").fetchone() == (
        None,
        TIME,
    )
    assert db.execute("SELECT verified FROM git_objects").fetchone()[0] == 0
    assert db.execute(
        "SELECT first_seen,last_seen FROM source_repositories"
    ).fetchone() == (TIME, TIME)
    assert db.execute("SELECT count(*) FROM content_locations").fetchone()[0] == 0
    db.execute("BEGIN")
    save_text()
    save_verification()
    record_rediscovery(db, "source", "a", later)
    db.execute("COMMIT")
    assert db.execute("SELECT raw_text,created_at FROM contents").fetchone() == (
        "abc",
        TIME,
    )
    assert db.execute("SELECT verified FROM git_objects").fetchone()[0] == 1
    assert db.execute(
        "SELECT first_seen,last_seen FROM source_repositories"
    ).fetchone() == (TIME, later)


def test_partial_pages_rollback_restart_complete_and_seal(target):
    db = target
    prefix = "lifecycle-"
    for kind in ("commits", "files"):
        put(
            db,
            "fetch_collections",
            id=prefix + kind,
            repo_id="a",
            change_request_id="cr-a",
            source_id="source",
            kind=kind,
            scope_id="scope-a",
            observed_at=TIME,
        )
        put(
            db,
            "code_listings",
            id=prefix + kind,
            change_request_id="cr-a",
            collection_id=prefix + kind,
            kind=kind,
            scope_id="scope-a",
            object_format="sha1",
            head_oid=H,
            base_oid=B,
        )
        db.execute(
            "INSERT INTO code_listing_progress VALUES(?,'partial',0,0,0)",
            (prefix + kind,),
        )
    code_observation(db, 10, "partial", prefix)
    # Admission inputs, including original observed times and exact page bytes,
    # are prepared before write transactions. No conversion wall clock replaces them.
    pages = []
    for page in range(2):
        for kind in ("commits", "files"):
            id = 10 + page * 2 + (kind == "files")
            body = json.dumps(
                [{"oid": (H if page == 0 else B).hex()}]
                if kind == "commits"
                else [{"path": f"file-{page}.txt"}]
            ).encode()
            pages.append((page, kind, id, body, hashlib.sha256(body).digest()))

    def save_page(page, kind, id, body, digest):
        put(
            db,
            "payloads",
            id=id,
            sha256=digest,
            body=body,
            byte_length=len(body),
            representation="decoded_api",
        )
        put(
            db,
            "fetch_occurrences",
            id=id,
            collection_id=prefix + kind,
            ordinal=page,
            payload_id=id,
            request=json.dumps({"page": page, "head": H.hex(), "base": B.hex()}),
            observed_at=TIME,
            parsed_at="2026-10-06T00:00:00Z",
        )
        item = json.loads(body)[0]
        values = dict(
            listing_id=prefix + kind,
            occurrence_id=id,
            position=0,
            payload=json.dumps(item),
        )
        if kind == "commits":
            put(
                db,
                "code_commits",
                **values,
                object_format="sha1",
                oid=bytes.fromhex(item["oid"]),
            )
        else:
            put(db, "code_file_changes", **values, raw_path=item["path"].encode())
        db.execute(
            "UPDATE code_listing_progress SET page_count=? WHERE listing_id=?",
            (page + 1, prefix + kind),
        )

    db.execute("BEGIN")
    for page in pages[:2]:
        save_page(*page)
    db.execute("COMMIT")
    saved = db.execute(
        "SELECT id,ordinal,observed_at,parsed_at FROM fetch_occurrences WHERE id>=10 ORDER BY id"
    ).fetchall()
    db.execute("BEGIN")
    db.execute("SAVEPOINT incomplete")
    for page in pages[2:]:
        save_page(*page)
    db.execute(
        "UPDATE code_listing_progress SET state='complete',terminal=1,context_proven=1 "
        "WHERE listing_id LIKE 'lifecycle-%'"
    )
    code_observation(db, 11, "complete", prefix)
    db.execute("ROLLBACK TO incomplete")
    db.execute("RELEASE incomplete")
    db.execute("COMMIT")
    assert (
        db.execute(
            "SELECT id,ordinal,observed_at,parsed_at FROM fetch_occurrences WHERE id>=10 ORDER BY id"
        ).fetchall()
        == saved
    )
    assert db.execute(
        "SELECT state,page_count FROM code_listing_progress WHERE listing_id LIKE 'lifecycle-%'"
    ).fetchall() == [("partial", 1), ("partial", 1)]
    assert db.execute("SELECT id,state FROM code_observations").fetchall() == [
        (10, "partial")
    ]
    # Restart uses the unchanged page inputs/IDs. Rolled-back rows are absent;
    # replay of already committed inputs compares saved facts instead of UPSERT.
    db.execute("BEGIN")
    for page in pages[2:]:
        save_page(*page)
    db.execute(
        "UPDATE code_listing_progress SET state='complete',terminal=1,context_proven=1 "
        "WHERE listing_id LIKE 'lifecycle-%'"
    )
    code_observation(db, 11, "complete", prefix)
    db.execute("COMMIT")
    for _, _, id, body, digest in pages:
        assert db.execute(
            "SELECT body,sha256 FROM payloads WHERE id=?", (id,)
        ).fetchone() == (
            body,
            digest,
        )
        assert db.execute(
            "SELECT observed_at,parsed_at FROM fetch_occurrences WHERE id=?", (id,)
        ).fetchone() == (TIME, "2026-10-06T00:00:00Z")
    assert db.execute("SELECT id,state FROM code_observations").fetchall() == [
        (10, "partial"),
        (11, "complete"),
    ]
    for kind in ("commits", "files"):
        table = "code_commits" if kind == "commits" else "code_file_changes"
        assert (
            db.execute(
                f"SELECT count(*) FROM {table} WHERE listing_id=?", (prefix + kind,)
            ).fetchone()[0]
            == 2
        )
        with pytest.raises(sqlite3.IntegrityError):
            append(
                db,
                kind,
                occurrence_id=pages[0 if kind == "commits" else 1][2],
                listing=prefix + kind,
            )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "DELETE FROM code_listing_progress WHERE listing_id=?", (prefix + kind,)
            )
