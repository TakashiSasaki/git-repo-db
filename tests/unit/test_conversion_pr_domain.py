"""Independent stored-page/PR recipes against the executable target DDL."""

import hashlib
import json
import sqlite3

import pytest

from repo_catalog.adapters.import_v2 import archive, git_domain, identity, pr_domain
from repo_catalog.adapters.sqlite.schema import schema_sql
from repo_catalog.domain.time import parse_iso8601_us
from tests.support.import_workspace import memory_workspace
from tests.support.integrated_fixture import (
    IDS,
    SAVED_EARLY_BODY,
    STAMPS,
    make_integrated_source,
)

STAMPS_US = tuple(parse_iso8601_us(stamp) for stamp in STAMPS)


def source_document_key(source, source_id):
    return tuple(
        source.execute(
            "SELECT pr_id,kind,provider_id FROM pr_documents WHERE id=?", (source_id,)
        ).fetchone()
    )


def apply(db, output, module):
    for operation in output["operations"]:
        table, row = operation["table"], operation["row"]
        columns, keys = module.COLUMNS[table], module.KEYS[table]
        predicate = " AND ".join(f'"{key}"=?' for key in keys)
        key_values = [row[columns.index(key)] for key in keys]
        actual = db.execute(
            f'SELECT * FROM "{table}" WHERE {predicate}', key_values
        ).fetchone()
        if operation["operation"] == "update":
            assert tuple(actual) == operation["before"]
            db.execute(
                f'UPDATE "{table}" SET '
                + ",".join(f'"{column}"=?' for column in columns[1:])
                + " WHERE code_listing_id=?",
                [*row[1:], row[0]],
            )
        elif operation["operation"] == "preference":
            db.execute(
                "UPDATE repositories SET preferred_repository_endpoint_id=? WHERE repository_id=?",
                (row[2], row[0]),
            )
        elif operation["operation"] == "manifest_completion":
            db.execute(
                "UPDATE root_manifests SET complete=? WHERE tree_git_object_id=?",
                (row[1], row[0]),
            )
        elif actual is None:
            db.execute(
                f'INSERT INTO "{table}"({",".join(columns)}) VALUES({",".join("?" for _ in row)})',
                row,
            )
        else:
            assert tuple(actual) == tuple(row), (table, tuple(actual), row)
    for mapped in output["mappings"]:
        db.execute(
            "INSERT INTO id_mappings(legacy_record_id,target_table,target_key,relation,reason) VALUES(?,?,?,?,?)",
            (mapped[0], mapped[1], bytes.fromhex(mapped[2]), *mapped[3:]),
        )
    db.commit()


def components(tmp_path, *, mutate=None, encoding="UTF-8", scale=1):
    original, _ = make_integrated_source(tmp_path / "source", scale=scale)
    if encoding != "UTF-8":
        with sqlite3.connect(original) as initial:
            schema_and_rows = "\n".join(initial.iterdump())
        rewritten = tmp_path / "source" / "utf16.sqlite3"
        with sqlite3.connect(rewritten) as rebuilt:
            assert encoding in ("UTF-16le", "UTF-16be")
            rebuilt.execute(f"PRAGMA encoding='{encoding}'")
            rebuilt.executescript(schema_and_rows)
        original = rewritten
    src = sqlite3.connect(original)
    src.row_factory = sqlite3.Row
    if mutate:
        mutate(src)
        src.commit()
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(schema_sql())
    memory_workspace(db)
    db.execute(
        "INSERT INTO conversion_sources(conversion_source_id,source_sha256,schema_sha256,format_id,source_db_instance_id,source_catalog,source_migrations) VALUES('source',?,?,'v2','synthetic',?,?)",
        (b"s" * 32, b"c" * 32, b"{}", b"[]"),
    )
    db.execute(
        "INSERT INTO conversion_runs(conversion_run_id,conversion_source_id,started_at_us,ended_at_us,parser_version,state,manifest) VALUES('run','source',?,NULL,'p3-integrated/1','building','{}')",
        (STAMPS_US[0],),
    )
    run = dict(db.execute("SELECT * FROM conversion_runs").fetchone())
    for table in src.execute(
        "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall():
        for record in archive.rows(src, table[0]):
            saved = db.execute(
                "INSERT INTO legacy_records(conversion_source_id,source_table,source_key,row_sha256) VALUES('source',?,?,?)",
                (record.table, record.key, record.row_sha256),
            ).lastrowid
            db.executemany(
                "INSERT INTO legacy_values(legacy_record_id,column_name,storage_type,value_bytes) VALUES(?,?,?,?)",
                [(saved, *value) for value in record.values],
            )
    db.commit()
    for recipe in identity.RECIPES:
        records = tuple(archive.rows(src, identity.SOURCE_TABLES.get(recipe, recipe)))
        apply(
            db,
            identity.prepare(db, src, run, recipe, 0, records, encoding=encoding),
            identity,
        )
    for recipe in git_domain.RECIPES:
        if recipe.endswith("root_origins"):
            continue
        records = tuple(archive.rows(src, git_domain.SOURCE_TABLES.get(recipe, recipe)))
        apply(
            db,
            git_domain.prepare(db, src, run, recipe, 0, records, encoding=encoding),
            git_domain,
        )
    return db, src, run


def convert(db, src, run):
    encoding = src.execute("PRAGMA encoding").fetchone()[0]
    prepared = {}
    for recipe in pr_domain.RECIPES:
        records = tuple(archive.rows(src, pr_domain.SOURCE_TABLES.get(recipe, recipe)))
        output = pr_domain.prepare(db, src, run, recipe, 0, records, encoding=encoding)
        apply(db, output, pr_domain)
        prepared[recipe] = output
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
    return prepared


@pytest.mark.parametrize(
    "source_stamp,expected_us,diagnostic",
    [
        ("1970-01-01T09:00:00+09:00", 0, None),
        ("1969-12-31T23:59:59.999999Z", -1, None),
        ("2026-01-02T03:04:05.123456Z", 1767323045123456, None),
        ("2026-01-02T03:04:05", None, "PR_INVALID_TIME"),
        ("2026-01-02T03:04:05.1234567Z", None, "PR_INVALID_TIME"),
        ("1970-01-01T00:00:00-00:00:00.000001", None, "PR_INVALID_TIME"),
        ("1970-01-01T00:00:00+00,000001", None, "PR_INVALID_TIME"),
        ("1970-01-01T00:00:00-00:00:00.000001\x00", None, "PR_INVALID_TIME"),
        ("invalid-source-time", None, "PR_INVALID_TIME"),
    ],
)
def test_source_pr_time_normalization_retains_raw_time_and_unknown_observations(
    tmp_path, source_stamp, expected_us, diagnostic
):
    def mutate(src):
        src.execute(
            "UPDATE pr_observations SET observed_at=? WHERE id=301", (source_stamp,)
        )

    db, src, run = components(tmp_path, mutate=mutate)
    try:
        outputs = convert(db, src, run)
        row = db.execute(
            "SELECT observed_at_us,parsed_at_us,published FROM change_request_observations WHERE change_request_observation_id=301"
        ).fetchone()
        assert tuple(row) == (expected_us, STAMPS_US[0], 0)
        assert (
            src.execute(
                "SELECT observed_at FROM pr_observations WHERE id=301"
            ).fetchone()[0]
            == source_stamp
        )
        assert db.execute(
            "SELECT v.storage_type,v.value_bytes FROM legacy_values v JOIN legacy_records r USING(legacy_record_id) WHERE r.source_table='pr_observations' AND v.column_name='observed_at' AND v.value_bytes=?",
            (source_stamp.encode(),),
        ).fetchone()[:] == ("text", source_stamp.encode())
        found = {
            row[1] for row in outputs["change_request_observations"]["diagnostics"]
        }
        assert found == ({diagnostic} if diagnostic else set())
    finally:
        db.close()
        src.close()


@pytest.mark.parametrize(
    "source_seconds,expected_us",
    [
        (0, 0),
        (-0.000001, -1),
        (1.123456, 1123456),
        (1767323045.123456, 1767323045123456),
        (float("inf"), None),
        (1e20, None),
    ],
)
def test_source_job_deadline_translates_unix_seconds_without_clock_substitution(
    tmp_path, source_seconds, expected_us
):
    def mutate(src):
        src.execute("UPDATE jobs SET not_before=?", (source_seconds,))

    db, src, run = components(tmp_path, mutate=mutate)
    try:
        records = tuple(archive.rows(src, "jobs"))
        output = pr_domain.prepare(db, src, run, "jobs", 0, records)
        apply(db, output, pr_domain)
        assert all(
            row[0] == expected_us
            for row in db.execute("SELECT not_before_us FROM job_attempts")
        )
        found = {row[1] for row in output["diagnostics"]}
        assert ("PR_INVALID_TIME" in found) == (expected_us is None)
    finally:
        db.close()
        src.close()


@pytest.mark.parametrize("malformed_first", (False, True))
def test_page_attribution_keeps_valid_prefix_exact_bodies_and_earliest_position(
    tmp_path, malformed_first
):
    def mutate(src):
        malformed = {"id": 999}
        values = [
            [{"id": 901, "body": "A"}, {"id": 901, "body": None}],
            [
                {"id": 902, "body": ""},
                {"id": 902, "body": "A"},
                {"id": 902, "body": "B"},
                {"id": 902, "body": "A"},
            ],
            [{"id": 901, "body": "A"}, {"id": 901, "body": None}],
        ]
        values[0].insert(0 if malformed_first else 2, malformed)
        values[0].append({"id": 901, "body": "unvisited after malformed"})
        for ordinal, items in enumerate(values):
            response = src.execute(
                "SELECT response_id FROM collection_pages WHERE collection_id=? AND ordinal=?",
                (IDS["comments_partial"], ordinal),
            ).fetchone()[0]
            raw = json.dumps(items).encode()
            src.execute(
                "UPDATE api_responses SET body=?,payload_sha256=? WHERE id=?",
                (raw, hashlib.sha256(raw).digest(), response),
            )

    db, src, run = components(tmp_path, mutate=mutate)
    context = pr_domain.Context(db, src, run)
    cid, document = IDS["comments_partial"], IDS["document_a"]
    earliest = 2 if malformed_first else 0
    assert context.first_source_page(cid, document, "A") == earliest
    assert context.first_source_page(cid, document, None) == earliest
    assert context.first_document_position(cid, document) == (earliest, 0)
    assert context.first_source_page(cid, document, "") is None
    assert context.first_source_page(cid, document, "unvisited after malformed") is None
    repaired = f"{IDS['pr']}:issue-comment:902"
    for body in ("", "A", "B"):
        assert context.first_source_page(cid, repaired, body) == 1
    assert context.first_source_page(cid, repaired, None) is None
    assert context.first_document_position(cid, repaired) == (1, 0)
    db.close()
    src.close()


def test_scaled_attribution_validates_each_saved_item_once_per_current_page(
    tmp_path, monkeypatch
):
    scale, calls = 200, 0
    original = pr_domain.Context.saved_document

    def counted(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pr_domain.Context, "saved_document", counted)
    db, src, run = components(tmp_path, scale=scale)
    prepared = convert(db, src, run)
    assert (
        db.execute(
            "SELECT count(*) FROM document_observations WHERE document_observation_id BETWEEN 5001 AND ? AND fetch_occurrence_id IS NOT NULL",
            (5000 + scale - 1,),
        ).fetchone()[0]
        == scale - 1
    )
    # The 199 scaled documents share one saved page. Attribution must not
    # revalidate every preceding item separately for each source observation.
    assert calls < scale * 12
    previous = calls
    for recipe in ("document_observations", "saved_document_repair"):
        records = tuple(archive.rows(src, pr_domain.SOURCE_TABLES[recipe]))
        assert prepared[recipe] == pr_domain.prepare(
            db, src, run, recipe, 0, records, verifying=True
        )
    # Verification rebuilds the source proof rather than retaining the earlier
    # page index or accepting rows from the now-populated target database.
    assert previous < calls < previous + scale * 12
    db.close()
    src.close()


@pytest.mark.parametrize(
    ("malformed", "error"),
    ((7, AttributeError), ({"id": "THREAD_bad", "comments": {"nodes": 7}}, TypeError)),
)
def test_attribution_defers_malformed_graphql_tail_until_no_prefix_match(
    tmp_path, malformed, error
):
    def mutate(src):
        payload = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "id": "THREAD_synthetic",
                                    "comments": {
                                        "nodes": [
                                            {
                                                "id": 1002,
                                                "body": "Inline original 日本語",
                                            }
                                        ]
                                    },
                                },
                                malformed,
                            ]
                        }
                    }
                }
            }
        }
        response = src.execute(
            "SELECT response_id FROM collection_pages WHERE collection_id=? AND ordinal=0",
            (IDS["threads"],),
        ).fetchone()[0]
        raw = json.dumps(payload, ensure_ascii=False).encode()
        src.execute(
            "UPDATE api_responses SET body=?,payload_sha256=? WHERE id=?",
            (raw, hashlib.sha256(raw).digest(), response),
        )

    db, src, run = components(tmp_path, mutate=mutate)
    context = pr_domain.Context(db, src, run)
    assert (
        context.first_source_page(
            IDS["threads"], IDS["document_line"], "Inline original 日本語"
        )
        == 0
    )
    assert context.first_document_position(IDS["threads"], IDS["document_line"]) == (
        0,
        0,
    )
    with pytest.raises(error):
        context.first_source_page(IDS["threads"], IDS["document_line"], "unmatched")
    with pytest.raises(error):
        context.first_document_position(IDS["threads"], "unmatched")
    # Advancing to another source page evicts both the prefix and deferred
    # failure; a malformed old tail cannot affect a valid unrelated origin.
    assert context.first_source_page(IDS["comments_a"], IDS["document_a"], "A") == 0
    db.close()
    src.close()


def test_pr_history_exact_payload_ids_distinct_observations_shared_body_and_repair(
    tmp_path,
):
    db, src, run = components(tmp_path)
    before = src.execute("SELECT id,body FROM api_responses ORDER BY id").fetchall()
    output = convert(db, src, run)
    assert [(r["id"], r["body"]) for r in before] == [
        (r["payload_id"], r["body"])
        for r in db.execute("SELECT payload_id,body FROM payloads ORDER BY payload_id")
    ]
    assert [
        tuple(r)
        for r in db.execute(
            "SELECT change_request_observation_id,observed_at_us,payload,published FROM change_request_observations ORDER BY change_request_observation_id"
        )
    ] == [
        (row["id"], parse_iso8601_us(row["observed_at"]), row["payload"], 0)
        for row in src.execute("SELECT * FROM pr_observations ORDER BY id")
    ]
    history = list(
        db.execute(
            "SELECT o.document_observation_id,b.body,o.observed_at_us FROM document_observations o JOIN text_bodies b ON b.sha256=o.text_body_sha256 WHERE o.change_request_id=? AND o.kind=? AND o.provider_change_request_document_id=? AND o.document_observation_id<1000 ORDER BY o.document_observation_id",
            source_document_key(src, IDS["document_a"]),
        )
    )
    assert [tuple(row) for row in history] == [
        (301, "A", STAMPS_US[0]),
        (302, "B", STAMPS_US[1]),
        (303, "A", STAMPS_US[2]),
    ]
    bodies = [
        row[0]
        for row in db.execute(
            "SELECT text_body_sha256 FROM document_observations WHERE document_observation_id IN (301,303) ORDER BY document_observation_id"
        )
    ]
    assert len(set(bodies)) == 1
    repaired = db.execute(
        "SELECT b.body,o.observed_at_us,o.parsed_at_us,f.next_cursor FROM document_observations o JOIN text_bodies b ON b.sha256=o.text_body_sha256 JOIN fetch_occurrences f ON f.fetch_occurrence_id=o.fetch_occurrence_id WHERE b.body=? ORDER BY o.observed_at_us",
        (SAVED_EARLY_BODY,),
    ).fetchone()
    assert tuple(repaired)[:3] == (SAVED_EARLY_BODY, STAMPS_US[3], STAMPS_US[0])
    assert repaired[3] is not None
    assert all(
        row[0] is None
        for row in db.execute("SELECT current_document_observation_id FROM documents")
    )
    assert all(
        row[0] is None
        for row in db.execute(
            "SELECT current_change_request_observation_id FROM change_requests"
        )
    )
    for recipe, expected in output.items():
        records = tuple(archive.rows(src, pr_domain.SOURCE_TABLES.get(recipe, recipe)))
        assert expected == pr_domain.prepare(
            db, src, run, recipe, 0, records, verifying=True
        )
    db.close()
    src.close()


def test_full_listings_seal_after_items_partial_pages_keep_cursor(tmp_path):
    db, src, run = components(tmp_path)
    convert(db, src, run)
    assert [
        tuple(r)
        for r in db.execute(
            "SELECT state,terminal,page_count,context_proven FROM code_listing_progress ORDER BY state"
        )
    ] == [
        ("complete", 1, 1, 1),
        ("complete", 1, 1, 1),
        ("partial", 0, 1, 1),
        ("partial", 0, 1, 1),
    ]
    assert [
        tuple(r)
        for r in db.execute(
            "SELECT code_observation_id,state FROM code_observations ORDER BY code_observation_id"
        )
    ] == [(301, "complete"), (302, "partial")]
    listing = db.execute(
        "SELECT code_listing_id FROM code_listing_progress WHERE state='complete'"
    ).fetchone()[0]
    with pytest.raises(
        sqlite3.IntegrityError,
        match="Listing items require initialized partial progress",
    ):
        db.execute(
            "INSERT INTO code_commits(code_listing_id,fetch_occurrence_id,position,object_format,oid,payload) SELECT code_listing_id,fetch_occurrence_id,position+10,object_format,oid,payload FROM code_commits WHERE code_listing_id=?",
            (listing,),
        )
    assert [
        tuple(r)
        for r in db.execute(
            "SELECT code_observation_id,role,acquisition_root_id FROM code_acquisitions ORDER BY code_observation_id,role"
        )
    ] == [
        (301, "base", 404),
        (301, "head", 403),
        (302, "base", None),
        (302, "head", None),
    ]
    db.close()
    src.close()


def test_saved_page_replay_restores_same_collection_a_b_a_without_body_merge(tmp_path):
    def mutate(src):
        source_collection = IDS["comments_a"]
        document = IDS["document_a"]
        src.execute("DELETE FROM resource_observations WHERE id IN (302,303)")
        src.execute(
            "UPDATE resource_observations SET collection_run=? WHERE id=301",
            (source_collection,),
        )
        first = json.loads(
            src.execute(
                "SELECT body FROM api_responses WHERE id=(SELECT response_id FROM collection_pages WHERE collection_id=? AND ordinal=0)",
                (source_collection,),
            ).fetchone()[0]
        )[0]
        for ordinal, body in ((1, "B"), (2, "A")):
            value = {**first, "body": body}
            raw = json.dumps([value]).encode()
            response = src.execute(
                "INSERT INTO api_responses(payload_sha256,body) VALUES(?,?)",
                (hashlib.sha256(raw).digest(), raw),
            ).lastrowid
            src.execute(
                "INSERT INTO collection_pages VALUES(?,?,?,?,NULL,?)",
                (
                    source_collection,
                    ordinal,
                    response,
                    json.dumps({"url": f"page-{ordinal}", "parser_version": "v1"}),
                    STAMPS[ordinal],
                ),
            )
        assert (
            src.execute(
                "SELECT count(*) FROM resource_observations WHERE document_id=?",
                (document,),
            ).fetchone()[0]
            == 1
        )

    db, src, run = components(tmp_path, mutate=mutate)
    convert(db, src, run)
    history = list(
        db.execute(
            "SELECT o.document_observation_id,b.body,o.observed_at_us FROM document_observations o JOIN text_bodies b ON b.sha256=o.text_body_sha256 WHERE o.change_request_id=? AND o.kind=? AND o.provider_change_request_document_id=? AND o.origin_key=? ORDER BY o.observed_at_us",
            (*source_document_key(src, IDS["document_a"]), IDS["comments_a"]),
        )
    )
    assert [r[1] for r in history] == ["A", "B", "A"]
    assert len({r[0] for r in history}) == 3
    assert [r[2] for r in history] == list(STAMPS_US[:3])
    db.close()
    src.close()


def test_malformed_saved_page_is_preserved_and_cannot_seal_listing(tmp_path):
    def mutate(src):
        page = src.execute(
            "SELECT response_id FROM collection_pages WHERE collection_id=?",
            (IDS["commits_complete"],),
        ).fetchone()[0]
        raw = b'{"not":"a-list"}'
        src.execute(
            "UPDATE api_responses SET body=?,payload_sha256=? WHERE id=?",
            (raw, hashlib.sha256(raw).digest(), page),
        )

    db, src, run = components(tmp_path, mutate=mutate)
    output = convert(db, src, run)
    assert (
        db.execute(
            "SELECT count(*) FROM payloads WHERE body=?", (b'{"not":"a-list"}',)
        ).fetchone()[0]
        == 1
    )
    assert (
        db.execute(
            "SELECT state FROM code_observations WHERE code_observation_id=301"
        ).fetchone()[0]
        == "partial"
    )
    assert any(
        diag[1] == "PR_MALFORMED_PAYLOAD"
        for diag in output["saved_listing_repair"]["diagnostics"]
    )
    db.close()
    src.close()


def test_saved_pr_title_body_reconstruct_history_and_original_metadata(tmp_path):
    def mutate(src):
        for ident, title in ((301, "title A"), (302, "title B"), (303, "title A")):
            payload = json.loads(
                src.execute(
                    "SELECT payload FROM pr_observations WHERE id=?", (ident,)
                ).fetchone()[0]
            )
            payload["title"] = title
            src.execute(
                "UPDATE pr_observations SET payload=? WHERE id=?",
                (json.dumps(payload), ident),
            )

    db, src, run = components(tmp_path, mutate=mutate)
    convert(db, src, run)
    history = list(
        db.execute(
            "SELECT o.document_observation_id,b.body,o.observed_at_us,o.metadata FROM documents d JOIN document_observations o ON o.change_request_id=d.change_request_id AND o.kind=d.kind AND o.provider_change_request_document_id=d.provider_change_request_document_id JOIN text_bodies b ON b.sha256=o.text_body_sha256 WHERE d.kind='pr-title' ORDER BY o.observed_at_us"
        )
    )
    assert [r[1] for r in history] == ["title A", "title B", "title A"]
    assert len({r[0] for r in history}) == 3
    assert [r[2] for r in history] == list(STAMPS_US[:3])
    assert [json.loads(r[3])["state"] for r in history] == ["open", "closed", "open"]
    assert (
        db.execute("SELECT count(*) FROM documents WHERE kind='pr-body'").fetchone()[0]
        == 1
    )
    db.close()
    src.close()


def test_repeated_saved_document_metadata_has_stable_identity_and_distinct_observations(
    tmp_path,
):
    def mutate(src):
        pages = src.execute(
            "SELECT ordinal,response_id FROM collection_pages WHERE collection_id=? ORDER BY ordinal",
            (IDS["comments_partial"],),
        ).fetchall()
        for ordinal, response in pages:
            values = json.loads(
                src.execute(
                    "SELECT body FROM api_responses WHERE id=?", (response,)
                ).fetchone()[0]
            )
            for item in values:
                if item["id"] == 902:
                    item["updated_at"] = f"source-update-{ordinal}"
            raw = json.dumps(values).encode()
            src.execute(
                "UPDATE api_responses SET body=?,payload_sha256=? WHERE id=?",
                (raw, hashlib.sha256(raw).digest(), response),
            )

    db, src, run = components(tmp_path, mutate=mutate)
    convert(db, src, run)
    document = db.execute(
        "SELECT change_request_id,kind,provider_change_request_document_id,metadata FROM documents WHERE provider_change_request_document_id='902'"
    ).fetchone()
    assert json.loads(document[3])["updated_at"] == "source-update-0"
    rows = list(
        db.execute(
            "SELECT metadata FROM document_observations WHERE change_request_id=? AND kind=? AND provider_change_request_document_id=? ORDER BY observed_at_us",
            tuple(document[:3]),
        )
    )
    assert [json.loads(r[0])["updated_at"] for r in rows] == [
        "source-update-0",
        "source-update-1",
        "source-update-2",
    ]
    db.close()
    src.close()


def test_pending_parent_and_etag_preserve_scope_payload_and_observation_time(tmp_path):
    def mutate(src):
        for number, provider in ((7, 907), (99, 908)):
            value = {
                "repo_id": IDS["repo"],
                "number": number,
                "kind": "issue-comment",
                "payload": {"id": provider, "body": "pending original"},
                "collection": IDS["comments_partial"],
            }
            src.execute(
                "INSERT INTO sync_checkpoints VALUES(?,?,?)",
                (
                    f"pending-comment:{IDS['repo']}:issue-comment:{provider}",
                    json.dumps(value),
                    STAMPS[3],
                ),
            )
        scope = {
            "repo": "401",
            "source": IDS["source"],
            "principal": "synthetic-user",
            "version": "2022-11-28",
            "url": "https://synthetic.invalid/api/repos/same/repo/pulls/7",
        }
        response = src.execute(
            "SELECT response_id FROM collection_pages WHERE collection_id=? AND ordinal=0",
            (IDS["comments_a"],),
        ).fetchone()[0]
        src.execute(
            "INSERT INTO sync_checkpoints VALUES(?,?,?)",
            (
                "etag:" + json.dumps(scope, sort_keys=True),
                json.dumps({"etag": 'W/"saved"', "response_id": response}),
                STAMPS[2],
            ),
        )

    db, src, run = components(tmp_path, mutate=mutate)
    output = convert(db, src, run)
    assert (
        db.execute(
            "SELECT count(*) FROM documents WHERE provider_change_request_document_id='907'"
        ).fetchone()[0]
        == 1
    )
    assert (
        db.execute(
            "SELECT count(*) FROM documents WHERE provider_change_request_document_id='908'"
        ).fetchone()[0]
        == 0
    )
    assert (
        db.execute(
            "SELECT observed_at_us FROM document_observations WHERE origin_key LIKE 'pending-comment:%'"
        ).fetchone()[0]
        == STAMPS_US[3]
    )
    validator = db.execute(
        "SELECT v.etag,v.validated_at_us,s.principal_ref,s.api_version,s.confidence FROM validators v JOIN resume_scopes s ON s.resume_scope_id=v.resume_scope_id"
    ).fetchone()
    assert tuple(validator) == (
        'W/"saved"',
        STAMPS_US[2],
        "synthetic-user",
        "2022-11-28",
        "legacy_unknown",
    )
    assert any(
        d[1] == "PR_PENDING_PARENT_UNRESOLVED"
        for d in output["sync_checkpoints"]["diagnostics"]
    )
    assert (
        db.execute(
            "SELECT count(*) FROM unresolved_payloads WHERE reason='pending resource parent unresolved'"
        ).fetchone()[0]
        == 1
    )
    db.close()
    src.close()


def test_graphql_repeated_missing_thread_retains_initial_snapshot_and_later_facts(
    tmp_path,
):
    def mutate(src):
        thread = {
            "id": "THREAD_new",
            "isResolved": False,
            "comments": {
                "nodes": [
                    {
                        "id": "COMMENT_new",
                        "fullDatabaseId": 910,
                        "body": "GraphQL A",
                        "author": {"login": "original"},
                    }
                ]
            },
        }
        payload = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [thread],
                            "pageInfo": {"hasNextPage": True, "endCursor": "next"},
                        }
                    }
                }
            }
        }
        page = src.execute(
            "SELECT response_id FROM collection_pages WHERE collection_id=? AND ordinal=0",
            (IDS["threads"],),
        ).fetchone()[0]
        raw = json.dumps(payload).encode()
        src.execute(
            "UPDATE api_responses SET body=?,payload_sha256=? WHERE id=?",
            (raw, hashlib.sha256(raw).digest(), page),
        )
        thread["isResolved"] = True
        thread["comments"]["nodes"][0]["body"] = "GraphQL B"
        payload["data"]["repository"]["pullRequest"]["reviewThreads"]["pageInfo"] = {
            "hasNextPage": False,
            "endCursor": None,
        }
        raw = json.dumps(payload).encode()
        response = src.execute(
            "INSERT INTO api_responses(payload_sha256,body) VALUES(?,?)",
            (hashlib.sha256(raw).digest(), raw),
        ).lastrowid
        request = json.dumps(
            {
                "url": "https://synthetic.invalid/graphql",
                "parser_version": "v1",
                "variables": {"cursor": "next"},
            }
        )
        src.execute(
            "INSERT INTO collection_pages VALUES(?,1,?,?,NULL,?)",
            (IDS["threads"], response, request, STAMPS[1]),
        )

    db, src, run = components(tmp_path, mutate=mutate)
    output = convert(db, src, run)
    thread = db.execute(
        "SELECT provider_resource_id,payload,observed_at_us FROM review_threads WHERE provider_resource_id='THREAD_new'"
    ).fetchone()
    assert json.loads(thread[1])["isResolved"] is False
    assert thread[2] == STAMPS_US[0]
    rows = list(
        db.execute(
            "SELECT b.body,o.observed_at_us,o.metadata FROM documents d JOIN document_observations o ON o.change_request_id=d.change_request_id AND o.kind=d.kind AND o.provider_change_request_document_id=d.provider_change_request_document_id JOIN text_bodies b ON b.sha256=o.text_body_sha256 WHERE d.provider_change_request_document_id='910' ORDER BY o.observed_at_us"
        )
    )
    assert [(r[0], r[1]) for r in rows] == [
        ("GraphQL A", STAMPS_US[0]),
        ("GraphQL B", STAMPS_US[1]),
    ]
    assert [json.loads(r[2])["thread_payload"]["isResolved"] for r in rows] == [
        False,
        True,
    ]
    assert (
        db.execute(
            "SELECT review_thread_provider_resource_id FROM review_comments WHERE provider_change_request_document_id='910'"
        ).fetchone()[0]
        == thread[0]
    )
    records = tuple(archive.rows(src, "collection_pages"))
    assert output["saved_document_repair"] == pr_domain.prepare(
        db, src, run, "saved_document_repair", 0, records, verifying=True
    )
    db.close()
    src.close()


def test_saved_null_body_keeps_identity_each_occurrence_without_inventing_empty_text(
    tmp_path,
):
    def mutate(src):
        for ident in (301, 302, 303):
            payload = json.loads(
                src.execute(
                    "SELECT payload FROM pr_observations WHERE id=?", (ident,)
                ).fetchone()[0]
            )
            payload["body"] = None
            src.execute(
                "UPDATE pr_observations SET payload=? WHERE id=?",
                (json.dumps(payload), ident),
            )
        for ordinal, response in src.execute(
            "SELECT ordinal,response_id FROM collection_pages WHERE collection_id=?",
            (IDS["comments_partial"],),
        ).fetchall():
            values = json.loads(
                src.execute(
                    "SELECT body FROM api_responses WHERE id=?", (response,)
                ).fetchone()[0]
            )
            for value in values:
                if value["id"] == 902:
                    value["body"] = None
            raw = json.dumps(values).encode()
            src.execute(
                "INSERT OR IGNORE INTO api_responses(payload_sha256,body) VALUES(?,?)",
                (hashlib.sha256(raw).digest(), raw),
            )
            saved_response = src.execute(
                "SELECT id FROM api_responses WHERE body=? AND payload_sha256=?",
                (raw, hashlib.sha256(raw).digest()),
            ).fetchone()[0]
            src.execute(
                "UPDATE collection_pages SET response_id=? WHERE collection_id=? AND ordinal=?",
                (saved_response, IDS["comments_partial"], ordinal),
            )
        document = IDS["document_same"]
        src.execute(
            "UPDATE document_versions SET body='',body_sha256=? WHERE id=303",
            (hashlib.sha256(b"").digest(),),
        )
        assert (
            src.execute(
                "SELECT document_id FROM document_versions WHERE id=303"
            ).fetchone()[0]
            == document
        )

    db, src, run = components(tmp_path, mutate=mutate)
    output = convert(db, src, run)
    assert (
        db.execute("SELECT count(*) FROM documents WHERE kind='pr-body'").fetchone()[0]
        == 1
    )
    assert (
        db.execute(
            "SELECT count(*) FROM documents WHERE provider_change_request_document_id='902'"
        ).fetchone()[0]
        == 1
    )
    assert (
        db.execute(
            "SELECT count(*) FROM document_observations WHERE kind='pr-body' OR provider_change_request_document_id='902'"
        ).fetchone()[0]
        == 0
    )
    assert (
        db.execute(
            "SELECT count(*) FROM unresolved_payloads WHERE reason LIKE '%body is NULL%'"
        ).fetchone()[0]
        == 6
    )
    assert (
        db.execute("SELECT count(*) FROM text_bodies WHERE body=''").fetchone()[0] == 1
    )
    assert (
        sum(
            d[1] == "PR_NULL_SAVED_BODY"
            for d in output["saved_pr_document_repair"]["diagnostics"]
        )
        == 3
    )
    assert (
        db.execute(
            "SELECT count(*) FROM fetch_occurrences WHERE fetch_collection_id=?",
            (IDS["comments_partial"],),
        ).fetchone()[0]
        == 3
    )
    db.close()
    src.close()


def test_oversized_saved_page_defers_replay_preserves_payload_occurrence_and_direct_rows(
    tmp_path,
):
    assert pr_domain.MAX_SAVED_REPLAY_BYTES == 32 * 1024 * 1024
    saved = {}

    def mutate(src):
        response = src.execute(
            "SELECT response_id FROM collection_pages WHERE collection_id=? AND ordinal=0",
            (IDS["commits_complete"],),
        ).fetchone()[0]
        value = json.loads(
            src.execute(
                "SELECT body FROM api_responses WHERE id=?", (response,)
            ).fetchone()[0]
        )[0]
        value["padding"] = "x" * pr_domain.MAX_SAVED_REPLAY_BYTES
        raw = json.dumps([value]).encode()
        assert len(raw) > pr_domain.MAX_SAVED_REPLAY_BYTES
        src.execute(
            "UPDATE api_responses SET body=?,payload_sha256=? WHERE id=?",
            (raw, hashlib.sha256(raw).digest(), response),
        )
        saved["response"] = response
        saved["sha256"] = hashlib.sha256(raw).digest()
        saved["bytes"] = len(raw)

    db, src, run = components(tmp_path, mutate=mutate)
    output = convert(db, src, run)
    payload = db.execute(
        "SELECT body,sha256,byte_length FROM payloads WHERE payload_id=?",
        (saved["response"],),
    ).fetchone()
    assert len(payload[0]) == saved["bytes"]
    assert hashlib.sha256(payload[0]).digest() == payload[1] == saved["sha256"]
    assert payload[2] == saved["bytes"]
    occurrence = db.execute(
        "SELECT observed_at_us,payload_id FROM fetch_occurrences WHERE fetch_collection_id=?",
        (IDS["commits_complete"],),
    ).fetchone()
    assert tuple(occurrence) == (STAMPS_US[0], saved["response"])
    # The already acquired normalized item survives even though its page cannot
    # be replayed/proved complete within the decoder budget.
    assert db.execute("SELECT count(*) FROM code_commits").fetchone()[0] == 2
    assert (
        db.execute(
            "SELECT state FROM code_observations WHERE code_observation_id=301"
        ).fetchone()[0]
        == "partial"
    )
    diagnostics = output["saved_listing_repair"]["diagnostics"]
    assert any(d[1:3] == ["PR_REPLAY_BUDGET_EXCEEDED", "partial"] for d in diagnostics)
    attributed = json.loads(
        next(d[3] for d in diagnostics if d[1] == "PR_REPLAY_BUDGET_EXCEEDED")
    )
    assert attributed["column"] == "response_id"
    assert (
        db.execute(
            "SELECT source_table FROM legacy_records WHERE legacy_record_id=?",
            (attributed["legacy_record_id"],),
        ).fetchone()[0]
        == "collection_pages"
    )
    assert (
        db.execute(
            "SELECT count(*) FROM document_observations WHERE change_request_id=? AND kind=? AND provider_change_request_document_id=? AND document_observation_id<1000",
            source_document_key(src, IDS["document_a"]),
        ).fetchone()[0]
        == 3
    )
    db.close()
    src.close()


def test_oversized_normalized_pr_metadata_retains_direct_fact_defers_only_reanalysis(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(pr_domain, "MAX_SAVED_REPLAY_BYTES", 1024)
    saved = {}

    def mutate(src):
        payload = json.loads(
            src.execute("SELECT payload FROM pr_observations WHERE id=301").fetchone()[
                0
            ]
        )
        payload["padding"] = "x" * 1024
        raw = json.dumps(payload)
        assert len(raw.encode()) > pr_domain.MAX_SAVED_REPLAY_BYTES
        src.execute("UPDATE pr_observations SET payload=? WHERE id=301", (raw,))
        saved["payload"] = raw

    db, src, run = components(tmp_path, mutate=mutate)
    output = convert(db, src, run)
    assert tuple(
        db.execute(
            "SELECT payload,observed_at_us FROM change_request_observations WHERE change_request_observation_id=301"
        ).fetchone()
    ) == (saved["payload"], STAMPS_US[0])
    assert (
        db.execute("SELECT count(*) FROM change_request_observations").fetchone()[0]
        == 3
    )
    assert db.execute("SELECT count(*) FROM code_observations").fetchone()[0] == 2
    assert (
        db.execute(
            "SELECT count(*) FROM document_observations WHERE origin_key='pr-observation:301'"
        ).fetchone()[0]
        == 0
    )
    assert (
        db.execute(
            "SELECT count(*) FROM document_observations WHERE origin_key='pr-observation:302'"
        ).fetchone()[0]
        == 2
    )
    assert any(
        d[1:3] == ["PR_REPLAY_BUDGET_EXCEEDED", "partial"]
        for d in output["saved_pr_document_repair"]["diagnostics"]
    )
    assert not output["change_request_observations"]["diagnostics"]
    records = tuple(archive.rows(src, "pr_observations"))
    assert output["saved_pr_document_repair"] == pr_domain.prepare(
        db, src, run, "saved_pr_document_repair", 0, records, verifying=True
    )
    db.close()
    src.close()


def test_small_deep_saved_json_is_attributed_without_decoder_crash(tmp_path):
    saved = {}

    def mutate(src):
        response = src.execute(
            "SELECT response_id FROM collection_pages WHERE collection_id=? AND ordinal=0",
            (IDS["commits_complete"],),
        ).fetchone()[0]
        raw = b"[" * 10000 + b"0" + b"]" * 10000
        assert len(raw) < pr_domain.MAX_SAVED_REPLAY_BYTES
        src.execute(
            "UPDATE api_responses SET body=?,payload_sha256=? WHERE id=?",
            (raw, hashlib.sha256(raw).digest(), response),
        )
        saved["response"] = response
        saved["body"] = raw

    db, src, run = components(tmp_path, mutate=mutate)
    output = convert(db, src, run)
    assert (
        db.execute(
            "SELECT body FROM payloads WHERE payload_id=?", (saved["response"],)
        ).fetchone()[0]
        == saved["body"]
    )
    assert any(
        d[1:3] == ["PR_JSON_DEPTH_UNSUPPORTED", "partial"]
        for d in output["saved_listing_repair"]["diagnostics"]
    )
    assert db.execute("SELECT count(*) FROM code_commits").fetchone()[0] == 2
    assert (
        db.execute(
            "SELECT state FROM code_observations WHERE code_observation_id=301"
        ).fetchone()[0]
        == "partial"
    )
    db.close()
    src.close()


def test_large_scope_request_details_preserve_direct_rows_edges_and_completion(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(pr_domain, "MAX_SAVED_REPLAY_BYTES", 1024)
    saved = {}

    def mutate(src):
        for collection in (
            IDS["commits_complete"],
            IDS["files_complete"],
            IDS["commits_partial"],
            IDS["files_partial"],
        ):
            scope = json.loads(
                src.execute(
                    "SELECT scope FROM collections WHERE id=?", (collection,)
                ).fetchone()[0]
            )
            scope["padding"] = "x" * 1024
            raw_scope = json.dumps(scope)
            src.execute(
                "UPDATE collections SET scope=? WHERE id=?", (raw_scope, collection)
            )
            saved[collection] = raw_scope
            for ordinal, request in src.execute(
                "SELECT ordinal,request FROM collection_pages WHERE collection_id=?",
                (collection,),
            ).fetchall():
                parsed = json.loads(request)
                parsed["padding"] = {"large": "y" * 1024}
                raw_request = json.dumps(parsed)
                src.execute(
                    "UPDATE collection_pages SET request=? WHERE collection_id=? AND ordinal=?",
                    (raw_request, collection, ordinal),
                )
                saved[(collection, ordinal)] = raw_request
        for ident, details in src.execute(
            "SELECT id,details FROM pr_code_observations"
        ).fetchall():
            parsed = json.loads(details)
            parsed["padding"] = ["z" * 1024]
            raw_details = json.dumps(parsed)
            src.execute(
                "UPDATE pr_code_observations SET details=? WHERE id=?",
                (raw_details, ident),
            )
            saved[ident] = raw_details

    db, src, run = components(tmp_path, mutate=mutate)
    output = convert(db, src, run)
    assert (
        db.execute("SELECT count(*) FROM code_commits").fetchone()[0]
        == src.execute("SELECT count(*) FROM pr_commits").fetchone()[0]
        == 2
    )
    assert (
        db.execute("SELECT count(*) FROM code_file_changes").fetchone()[0]
        == src.execute("SELECT count(*) FROM pr_file_changes").fetchone()[0]
        == 2
    )
    code = list(
        db.execute(
            "SELECT code_observation_id,state,commit_code_listing_id,file_code_listing_id,details FROM code_observations ORDER BY code_observation_id"
        )
    )
    assert [(r[0], r[1]) for r in code] == [(301, "complete"), (302, "partial")]
    assert all(r[2] and r[3] and r[4] == saved[r[0]] for r in code)
    for collection in (
        IDS["commits_complete"],
        IDS["files_complete"],
        IDS["commits_partial"],
        IDS["files_partial"],
    ):
        context = db.execute(
            "SELECT request_context FROM resume_scopes WHERE resume_scope_id=(SELECT resume_scope_id FROM fetch_collections WHERE fetch_collection_id=?)",
            (collection,),
        ).fetchone()[0]
        expected = json.loads(saved[collection])
        expected["repository_id"] = expected.pop("repo_id")
        assert json.loads(context) == expected
        archived = db.execute(
            "SELECT v.value_bytes FROM legacy_values v JOIN legacy_records r ON r.legacy_record_id=v.legacy_record_id WHERE r.source_table='collections' AND r.source_key=? AND v.column_name='scope'",
            (
                next(
                    r.key
                    for r in archive.rows(src, "collections")
                    if r.key.endswith(collection.encode())
                ),
            ),
        ).fetchone()[0]
        assert bytes(archived).decode() == saved[collection]
        assert (
            db.execute(
                "SELECT request FROM fetch_occurrences WHERE fetch_collection_id=?",
                (collection,),
            ).fetchone()[0]
            == saved[(collection, 0)]
        )
    assert not output["code_commits"]["diagnostics"]
    assert not output["code_file_changes"]["diagnostics"]
    records = tuple(archive.rows(src, "pr_code_observations"))
    assert output["code_observations"] == pr_domain.prepare(
        db, src, run, "code_observations", 0, records, verifying=True
    )
    db.close()
    src.close()


def test_scope_scalar_extraction_preserves_last_duplicate_key_semantics(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(pr_domain, "MAX_SAVED_REPLAY_BYTES", 1024)

    def mutate(src):
        scope = (
            '{"repo_id":"wrong","repo_id":'
            + json.dumps(IDS["repo"])
            + ',"principal":{"invalid":"first"},"principal":null,"api_version":3,"api_version":"last-version","padding":'
            + json.dumps("x" * 1024)
            + "}"
        )
        src.execute(
            "UPDATE collections SET scope=? WHERE id=?",
            (scope, IDS["commits_complete"]),
        )
        request = (
            '{"url":false,"url":"https://synthetic.invalid/last","parser_version":3,"parser_version":"last-parser","padding":'
            + json.dumps("y" * 1024)
            + "}"
        )
        src.execute(
            "UPDATE collection_pages SET request=? WHERE collection_id=?",
            (request, IDS["commits_complete"]),
        )
        details = (
            '{"api_head_base_stable":false,"api_head_base_stable":true,"padding":'
            + json.dumps("z" * 1024)
            + "}"
        )
        src.execute(
            "UPDATE pr_code_observations SET details=? WHERE id=301", (details,)
        )

    db, src, run = components(tmp_path, mutate=mutate)
    convert(db, src, run)
    scope = db.execute(
        "SELECT principal_ref,api_version,endpoint,parser_version FROM resume_scopes WHERE resume_scope_id=(SELECT resume_scope_id FROM fetch_collections WHERE fetch_collection_id=?)",
        (IDS["commits_complete"],),
    ).fetchone()
    assert tuple(scope) == (
        None,
        "last-version",
        "https://synthetic.invalid/last",
        "last-parser",
    )
    assert (
        db.execute(
            "SELECT state FROM code_observations WHERE code_observation_id=301"
        ).fetchone()[0]
        == "complete"
    )
    assert db.execute("SELECT count(*) FROM code_commits").fetchone()[0] == 2
    db.close()
    src.close()


@pytest.mark.parametrize("encoding", ["UTF-8", "UTF-16le", "UTF-16be"])
@pytest.mark.parametrize(
    "original",
    [
        r'{"principal":"\ud800","api_version":"original"}',
        r'{"principal":"valid","principal":"\ud800","api_version":"original"}',
    ],
)
def test_selected_unpaired_surrogate_is_attributed_without_replacement_or_crash(
    tmp_path, encoding, original
):

    def mutate(src):
        src.execute(
            "UPDATE collections SET scope=? WHERE id=?",
            (original, IDS["commits_complete"]),
        )

    db, src, run = components(tmp_path, mutate=mutate, encoding=encoding)
    output = convert(db, src, run)
    assert (
        src.execute(
            "SELECT scope FROM collections WHERE id=?", (IDS["commits_complete"],)
        ).fetchone()[0]
        == original
    )
    assert any(
        d[1:3] == ["PR_MALFORMED_TEXT", "blocking"]
        for d in output["resume_scopes"]["diagnostics"]
    )
    assert (
        db.execute(
            "SELECT count(*) FROM fetch_collections WHERE fetch_collection_id=?",
            (IDS["commits_complete"],),
        ).fetchone()[0]
        == 0
    )
    assert not db.execute(
        "SELECT 1 FROM resume_scopes WHERE principal_ref=?", ("\ufffd",)
    ).fetchone()
    archived = db.execute(
        "SELECT v.value_bytes FROM legacy_values v JOIN legacy_records r ON r.legacy_record_id=v.legacy_record_id WHERE r.source_table='collections' AND v.column_name='scope' AND v.value_bytes=?",
        (original.encode(encoding),),
    ).fetchone()
    assert archived is not None
    db.close()
    src.close()


@pytest.mark.parametrize("encoding", ["UTF-8", "UTF-16le", "UTF-16be"])
def test_selected_paired_escaped_surrogates_backslashes_and_last_duplicate_survive(
    tmp_path, encoding
):
    original = r'{"principal":"\ud800","principal":"\ud83d\ude00","api_version":"\\ud800","padding":"\ud800"}'

    def mutate(src):
        src.execute(
            "UPDATE collections SET scope=? WHERE id=?",
            (original, IDS["commits_complete"]),
        )

    db, src, run = components(tmp_path, mutate=mutate, encoding=encoding)
    output = convert(db, src, run)
    row = db.execute(
        "SELECT principal_ref,api_version,request_context FROM resume_scopes WHERE resume_scope_id=(SELECT resume_scope_id FROM fetch_collections WHERE fetch_collection_id=?)",
        (IDS["commits_complete"],),
    ).fetchone()
    assert tuple(row) == ("😀", r"\ud800", original)
    assert not any(
        d[1] == "PR_MALFORMED_TEXT" for d in output["resume_scopes"]["diagnostics"]
    )
    assert db.execute("SELECT count(*) FROM code_commits").fetchone()[0] == 2
    db.close()
    src.close()


def test_node_only_source_document_stays_archived_not_canonical(tmp_path):
    def mutate(src):
        src.execute(
            "UPDATE pr_documents SET provider_id='NODE_only' WHERE id=?",
            (IDS["document_a"],),
        )

    db, src, run = components(tmp_path, mutate=mutate)
    output = convert(db, src, run)
    assert not db.execute(
        "SELECT 1 FROM documents WHERE provider_change_request_document_id='NODE_only'"
    ).fetchone()
    assert any(
        item[1] == "PR_CANONICAL_DOCUMENT_ID_MISSING" and item[2] == "partial"
        for batch in output.values()
        for item in batch.get("diagnostics", [])
    )
    assert db.execute(
        "SELECT 1 FROM legacy_values WHERE column_name='provider_id' AND value_bytes=?",
        (b"NODE_only",),
    ).fetchone()
    db.close()
    src.close()


def test_source_thread_local_id_is_not_used_when_provider_id_missing(tmp_path):
    def mutate(src):
        src.execute(
            "UPDATE review_threads SET payload='{}' WHERE id=?", (IDS["thread"],)
        )

    db, src, run = components(tmp_path, mutate=mutate)
    output = convert(db, src, run)
    assert not db.execute(
        "SELECT 1 FROM review_threads WHERE provider_resource_id=?", (IDS["thread"],)
    ).fetchone()
    assert any(
        item[1] == "PR_INVALID_SAVED_IDENTITY"
        for batch in output.values()
        for item in batch.get("diagnostics", [])
    )
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
    db.close()
    src.close()
