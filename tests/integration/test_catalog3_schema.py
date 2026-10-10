"""Fresh typed ownership and domain completeness constraints."""

import copy
import json
import sqlite3

import pytest

from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.schema import schema_sql
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.config import DEFAULTS, serialize
from tests.support.domain_facts import (
    TIME_US,
    admit_pr,
    candidate,
    collection,
    fresh_domain_db,
    repository_uuid,
)
from tests.support.domain_facts import (
    insert as put,
)


@pytest.fixture
def facts():
    db = fresh_domain_db()
    for number in (1, 2):
        admit_pr(db, number, state="open")
        scope = collection(db, number, identity=f"collection-{number}")
        put(
            db,
            "code_listings",
            code_listing_id=f"files-{number}",
            change_request_id=f"pr{number}",
            fetch_collection_id=f"collection-{number}",
            kind="files",
            resume_scope_id=scope,
            object_format="sha1",
            head_oid=b"h" * 20,
            base_oid=b"b" * 20,
        )
        put(
            db,
            "code_listing_progress",
            code_listing_id=f"files-{number}",
            state="partial",
            terminal=0,
            page_count=0,
            context_proven=1,
        )
    put(
        db,
        "code_file_changes",
        code_listing_id="files-1",
        position=0,
        repository_uuidv4=repository_uuid(1),
        raw_path=b"raw/\xff\tname",
        metadata="{}",
    )
    yield db
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    db.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("repository_uuidv4", repository_uuid(2)),
        ("repository_binding_id", "binding-2"),
        ("change_request_id", "pr2"),
    ],
)
def test_current_state_requires_same_typed_owner(facts, field, value):
    with pytest.raises(sqlite3.IntegrityError):
        facts.execute(
            f"UPDATE change_request_state SET {field}=? WHERE change_request_id='pr1'",
            (value,),
        )
    assert facts.execute(
        "SELECT state FROM eligible_change_request_state WHERE change_request_id='pr1'"
    ).fetchone() == ("open",)


def test_listing_and_members_must_share_scope_and_owner(facts):
    with pytest.raises(sqlite3.IntegrityError):
        put(
            facts,
            "code_listings",
            code_listing_id="wrong",
            change_request_id="pr1",
            fetch_collection_id="collection-2",
            kind="commits",
            resume_scope_id="scope-collection-2",
        )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            facts,
            "code_file_changes",
            code_listing_id="files-1",
            position=1,
            repository_uuidv4=repository_uuid(2),
            raw_path=b"cross-owner",
            metadata="{}",
        )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            facts,
            "code_assessments",
            code_assessment_id="foreign",
            change_request_id="pr1",
            repository_uuidv4=repository_uuid(1),
            file_code_listing_id="files-2",
            state="partial",
            object_format="sha1",
            head_oid=b"h" * 20,
            base_oid=b"b" * 20,
            parser_module=__name__,
            parser_version="1",
            details_json="{}",
        )
    assert facts.execute("SELECT raw_path FROM code_file_changes").fetchall() == [
        (b"raw/\xff\tname",)
    ]


@pytest.mark.parametrize(
    "attack", ["append", "edit", "delete", "reopen", "remove-marker", "replace-marker"]
)
def test_completed_listing_preserves_exact_target_content(facts, attack):
    facts.execute(
        "UPDATE code_listing_progress SET state='complete',terminal=1,page_count=1 WHERE code_listing_id='files-1'"
    )
    statements = {
        "append": (
            "INSERT INTO code_file_changes(code_listing_id,position,repository_uuidv4,raw_path,metadata) VALUES('files-1',1,?,x'61','{}')",
            (repository_uuid(1),),
        ),
        "edit": (
            "UPDATE code_file_changes SET raw_path=x'61' WHERE code_listing_id='files-1'",
            (),
        ),
        "delete": ("DELETE FROM code_file_changes WHERE code_listing_id='files-1'", ()),
        "reopen": (
            "UPDATE code_listing_progress SET state='partial' WHERE code_listing_id='files-1'",
            (),
        ),
        "remove-marker": (
            "DELETE FROM code_listing_progress WHERE code_listing_id='files-1'",
            (),
        ),
        "replace-marker": (
            "INSERT OR REPLACE INTO code_listing_progress(code_listing_id,state,terminal,page_count,context_proven) VALUES('files-1','partial',0,0,1)",
            (),
        ),
    }
    sql, args = statements[attack]
    with pytest.raises(sqlite3.IntegrityError):
        facts.execute(sql, args)
    assert (
        facts.execute(
            "SELECT state FROM code_listing_progress WHERE code_listing_id='files-1'"
        ).fetchone()[0]
        == "complete"
    )
    assert (
        facts.execute("SELECT raw_path FROM code_file_changes").fetchone()[0]
        == b"raw/\xff\tname"
    )


def test_missing_parent_stages_current_candidate_until_parent_exists(facts):
    data = candidate(
        change_request_id="late-parent",
        acquisition_scope={
            **candidate()["acquisition_scope"],
            "change_request_id": "late-parent",
        },
        state="open",
    )
    api = CurrentApiState(facts)
    assert (
        api.admit("change_request_state", data, source="import").status
        == "missing_dependency"
    )
    assert not facts.execute(
        "SELECT 1 FROM change_request_state WHERE change_request_id='late-parent'"
    ).fetchall()
    put(
        facts,
        "change_requests",
        change_request_id="late-parent",
        repository_uuidv4=repository_uuid(1),
        repository_binding_id="binding-1",
        change_request_kind="pull_request",
        provider_change_request_number=2,
    )
    assert api._promote_staging() == 1
    assert facts.execute(
        "SELECT state FROM eligible_change_request_state WHERE change_request_id='late-parent'"
    ).fetchone() == ("open",)


def test_source_seen_range_preserves_order_at_single_microsecond_precision(facts):
    put(
        facts,
        "source_repositories",
        source_id="source",
        repository_uuidv4=repository_uuid(1),
        first_seen_us=TIME_US,
        last_seen_us=TIME_US + 1,
    )
    for first, last in ((TIME_US + 1, TIME_US + 1), (TIME_US, TIME_US)):
        with pytest.raises(sqlite3.IntegrityError, match="aggregate time regression"):
            facts.execute(
                "UPDATE source_repositories SET first_seen_us=?,last_seen_us=?",
                (first, last),
            )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            facts,
            "source_repositories",
            source_id="source",
            repository_uuidv4=repository_uuid(2),
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


def test_committed_resource_does_not_need_collection_or_operation_success(facts):
    facts.execute("DELETE FROM code_listing_progress WHERE code_listing_id='files-1'")
    assert facts.execute(
        "SELECT state FROM eligible_change_request_state WHERE change_request_id='pr1'"
    ).fetchone() == ("open",)
    assert facts.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
    assert facts.execute("SELECT count(*) FROM completion_markers").fetchone()[0] == 0
    assert not facts.execute(
        "SELECT 1 FROM sqlite_schema WHERE name='parsed_results'"
    ).fetchall()


def test_latest_api_states_have_no_normalized_accepted_history(facts):
    api = CurrentApiState(facts)
    for clock in range(TIME_US + 1, TIME_US + 101):
        result = api.admit(
            "change_request_state",
            candidate(
                clock=clock,
                observed_at_us=clock,
                state="open" if clock % 2 else "closed",
            ),
            source="import",
        )
        assert result.status in {"accepted", "identical"}
    assert facts.execute("SELECT count(*) FROM change_request_state").fetchone()[0] == 2
    assert facts.execute("SELECT count(*) FROM exchange_staging").fetchone()[0] == 0
    evidence = json.loads(
        facts.execute(
            "SELECT field_evidence_json FROM change_request_state WHERE change_request_id='pr1'"
        ).fetchone()[0]
    )
    assert evidence['["state"]']["provider_updated_at_us"] == TIME_US + 100


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
    # Current review associations name their provider role explicitly. Each is
    # a typed natural-key reference, scoped by its owning change request.
    natural_associations = {
        ("review_resources", "review_provider_resource_id"): "parent_review_kind",
        ("review_resources", "in_reply_to_provider_resource_id"): "reply_kind",
    }
    seen = set()
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
                    if (table, local) in natural_associations:
                        assert fk[2] == "review_resources"
                        assert referenced == "provider_change_request_document_id"
                        parts = {
                            (part[3], part[4])
                            for part in db.execute(f"PRAGMA foreign_key_list({table})")
                            if part[0] == fk[0]
                        }
                        assert parts == {
                            ("change_request_id", "change_request_id"),
                            (natural_associations[(table, local)], "kind"),
                            (local, referenced),
                        }
                        seen.add((table, local))
                        continue
                    assert local == referenced or local.endswith("_" + referenced), (
                        table,
                        local,
                        fk[2],
                        referenced,
                    )
    assert seen == natural_associations.keys()
