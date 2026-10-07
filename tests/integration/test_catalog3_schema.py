"""Ordinary packaged catalog3 constraints on the working SQLite binding."""

import copy
import hashlib
import sqlite3

import pytest

from repo_catalog.adapters.sqlite.schema import schema_sql
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.config import DEFAULTS, serialize

TIME_US = 1_791_244_800_000_000


def put(db, table, **values):
    db.execute(
        f"INSERT INTO {table}({','.join(values)}) VALUES({','.join('?' for _ in values)})",
        tuple(values.values()),
    )


@pytest.fixture
def facts():
    db = sqlite3.connect(":memory:", autocommit=True)
    db.executescript(schema_sql())
    put(
        db,
        "service_instances",
        service_instance_uuidv4="00000000-0000-4000-8000-000000000101",
        service_kind="github",
        name="synthetic",
        metadata="{}",
    )
    for owner, observation in (("a", 1), ("b", 2)):
        put(db, "repositories", repository_id=owner, name=owner, metadata="{}")
        put(
            db,
            "repository_bindings",
            repository_binding_id="binding-" + owner,
            repository_id=owner,
            service_instance_uuidv4="00000000-0000-4000-8000-000000000101",
            provider_repository_id=owner,
            metadata="{}",
        )
        put(
            db,
            "change_requests",
            change_request_id="pr-" + owner,
            repository_id=owner,
            repository_binding_id="binding-" + owner,
            change_request_kind="pull_request",
            provider_change_request_number=1,
        )
        put(
            db,
            "change_request_observations",
            change_request_observation_id=observation,
            change_request_id="pr-" + owner,
            published=1,
            payload="{}",
            parsed_at_us=TIME_US,
        )
        put(
            db,
            "resume_scopes",
            resume_scope_id="scope-" + owner,
            repository_id=owner,
            repository_binding_id="binding-" + owner,
            request_context="{}",
            parser_version="synthetic",
            profile_version="synthetic",
            confidence="proven",
        )
        put(
            db,
            "fetch_collections",
            fetch_collection_id="collection-" + owner,
            repository_id=owner,
            change_request_id="pr-" + owner,
            kind="files",
            resume_scope_id="scope-" + owner,
        )
        put(
            db,
            "payloads",
            payload_id=observation,
            sha256=hashlib.sha256(owner.encode()).digest(),
            body=owner.encode(),
            byte_length=1,
            representation="decoded_api",
        )
        put(
            db,
            "fetch_occurrences",
            fetch_occurrence_id=observation,
            fetch_collection_id="collection-" + owner,
            ordinal=0,
            payload_id=observation,
            request="{}",
            parsed_at_us=TIME_US,
        )
    put(
        db,
        "code_listings",
        code_listing_id="files",
        change_request_id="pr-a",
        fetch_collection_id="collection-a",
        kind="files",
        resume_scope_id="scope-a",
    )
    put(
        db,
        "code_listing_progress",
        code_listing_id="files",
        state="partial",
        terminal=0,
        page_count=0,
        context_proven=1,
    )
    put(
        db,
        "code_file_changes",
        code_listing_id="files",
        fetch_occurrence_id=1,
        position=0,
        raw_path=b"raw/\xff\tname",
        payload="{}",
    )
    yield db
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    db.close()


@pytest.mark.parametrize("owner,observation", [("pr-a", 1), ("pr-a", 2)])
def test_current_pointer_requires_same_owner_completed_observation(
    facts, owner, observation
):
    if observation == 1:
        facts.execute(
            "UPDATE change_requests SET current_change_request_observation_id=? WHERE change_request_id=?",
            (observation, owner),
        )
        assert (
            facts.execute(
                "SELECT current_change_request_observation_id FROM change_requests WHERE change_request_id=?",
                (owner,),
            ).fetchone()[0]
            == 1
        )
    else:
        with pytest.raises(sqlite3.IntegrityError):
            facts.execute(
                "UPDATE change_requests SET current_change_request_observation_id=? WHERE change_request_id=?",
                (observation, owner),
            )
        assert (
            facts.execute(
                "SELECT current_change_request_observation_id FROM change_requests WHERE change_request_id=?",
                (owner,),
            ).fetchone()[0]
            is None
        )


def test_listing_and_page_must_share_scope_and_owner(facts):
    with pytest.raises(sqlite3.IntegrityError):
        put(
            facts,
            "code_listings",
            code_listing_id="wrong",
            change_request_id="pr-a",
            fetch_collection_id="collection-a",
            kind="commits",
            resume_scope_id="scope-b",
        )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            facts,
            "code_file_changes",
            code_listing_id="files",
            fetch_occurrence_id=2,
            position=1,
            raw_path=b"cross-owner",
            payload="{}",
        )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            facts,
            "code_observations",
            change_request_id="pr-a",
            change_request_observation_id=2,
            file_code_listing_id="files",
            state="partial",
            details="{}",
        )
    assert facts.execute("SELECT raw_path FROM code_file_changes").fetchall() == [
        (b"raw/\xff\tname",)
    ]


@pytest.mark.parametrize(
    "attack", ["append", "edit", "delete", "reopen", "remove-marker", "replace-marker"]
)
def test_completed_listing_seals_content_and_completion_marker(facts, attack):
    facts.execute(
        "UPDATE code_listing_progress SET state='complete',terminal=1,page_count=1 WHERE code_listing_id='files'"
    )
    statements = {
        "append": "INSERT INTO code_file_changes(code_listing_id,fetch_occurrence_id,position,raw_path,payload) VALUES('files',1,1,x'61','{}')",
        "edit": "UPDATE code_file_changes SET raw_path=x'61' WHERE code_listing_id='files'",
        "delete": "DELETE FROM code_file_changes WHERE code_listing_id='files'",
        "reopen": "UPDATE code_listing_progress SET state='partial' WHERE code_listing_id='files'",
        "remove-marker": "DELETE FROM code_listing_progress WHERE code_listing_id='files'",
        "replace-marker": "INSERT OR REPLACE INTO code_listing_progress(code_listing_id,state,terminal,page_count,context_proven) VALUES('files','partial',0,0,1)",
    }
    with pytest.raises(sqlite3.IntegrityError):
        facts.execute(statements[attack])
    assert (
        facts.execute("SELECT state FROM code_listing_progress").fetchone()[0]
        == "complete"
    )
    assert (
        facts.execute("SELECT raw_path FROM code_file_changes").fetchone()[0]
        == b"raw/\xff\tname"
    )


def test_pending_observation_cannot_become_current(facts):
    put(
        facts,
        "change_request_observations",
        change_request_observation_id=3,
        change_request_id="pr-a",
        published=0,
        payload="{}",
        parsed_at_us=TIME_US,
    )
    with pytest.raises(sqlite3.IntegrityError):
        facts.execute(
            "UPDATE change_requests SET current_change_request_observation_id=3 WHERE change_request_id='pr-a'"
        )


def test_source_seen_range_preserves_order_at_single_microsecond_precision(facts):
    put(
        facts,
        "sources",
        source_id="source",
        discovery_kind="manual_git",
        name="synthetic",
        settings="{}",
    )
    put(
        facts,
        "source_repositories",
        source_id="source",
        repository_id="a",
        first_seen_us=TIME_US,
        last_seen_us=TIME_US + 1,
    )
    for first_seen_us, last_seen_us in ((TIME_US + 1, TIME_US + 1), (TIME_US, TIME_US)):
        with pytest.raises(sqlite3.IntegrityError, match="aggregate time regression"):
            facts.execute(
                "UPDATE source_repositories SET first_seen_us=?,last_seen_us=?",
                (first_seen_us, last_seen_us),
            )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            facts,
            "source_repositories",
            source_id="source",
            repository_id="b",
            first_seen_us=TIME_US + 1,
            last_seen_us=TIME_US,
        )
    facts.execute(
        "UPDATE source_repositories SET first_seen_us=?,last_seen_us=?",
        (TIME_US - 1, TIME_US + 2),
    )
    assert facts.execute(
        "SELECT first_seen_us,last_seen_us FROM source_repositories"
    ).fetchone() == (TIME_US - 1, TIME_US + 2)


def test_derived_fts_and_analyze_do_not_change_catalog_identity(tmp_path):
    config = copy.deepcopy(DEFAULTS)
    config["cache"].update(max_bytes=64 * 1024 * 1024, min_free_bytes=0)
    (tmp_path / "catalog.toml").write_text(serialize(config))
    with Store(tmp_path, initialize=True) as store:
        before = tuple(
            store.one(
                "SELECT format_id,schema_version,ddl_sha256 FROM database_identity"
            )
        )
        with store.transaction():
            store.execute(
                "CREATE VIRTUAL TABLE catalog_fts_999 USING fts5(body, tokenize='trigram case_sensitive 1')"
            )
            store.execute(
                "INSERT INTO catalog_fts_999(body) VALUES('searchable original')"
            )
            store.execute("ANALYZE")
        store.verify_format()
        assert (
            store.one(
                "SELECT count(*) FROM catalog_fts_999 WHERE body MATCH 'original'"
            )[0]
            == 1
        )
        store.execute("DROP TABLE catalog_fts_999")
        store.verify_format()
        assert (
            tuple(
                store.one(
                    "SELECT format_id,schema_version,ddl_sha256 FROM database_identity"
                )
            )
            == before
        )
    with Store(tmp_path, readonly=True) as reader:
        assert reader.one("PRAGMA foreign_keys")[0] == 1
        assert reader.one("PRAGMA recursive_triggers")[0] == 1
        assert reader.one("PRAGMA query_only")[0] == 1


def test_runtime_identifiers_make_fk_domains_and_roles_explicit():
    with sqlite3.connect(":memory:") as db:
        db.executescript(schema_sql())
        tables = db.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for (table,) in tables:
            columns = db.execute(f"PRAGMA table_info({table})").fetchall()
            assert "id" not in {column[1] for column in columns}, table
            for fk in db.execute(f"PRAGMA foreign_key_list({table})"):
                local, referenced = fk[3], fk[4]
                if referenced.endswith("_id"):
                    assert local == referenced or local.endswith("_" + referenced), (
                        table,
                        local,
                        fk[2],
                        referenced,
                    )
