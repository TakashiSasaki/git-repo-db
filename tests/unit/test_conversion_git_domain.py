"""Exact stored Git bytes, edges and admitted verification recipe regressions."""

import hashlib
import sqlite3

import pytest

from repo_catalog.adapters.import_v2 import archive, git_domain
from repo_catalog.adapters.import_v2.common import DESIGN
from repo_catalog.adapters.sqlite.schema import schema_sql
from repo_catalog.domain.time import parse_iso8601_us
from tests.support.import_workspace import memory_workspace

STAMP = "2026-01-02T03:04:05Z"
STAMP_US = parse_iso8601_us(STAMP)


def git_payload(kind, raw):
    return hashlib.sha1(f"{kind} {len(raw)}\0".encode() + raw).digest()


@pytest.fixture
def graph(request):
    src, db = sqlite3.connect(":memory:"), sqlite3.connect(":memory:")
    src.row_factory = db.row_factory = sqlite3.Row
    src.execute(f"PRAGMA encoding='{getattr(request, 'param', 'UTF-8')}'")
    for path in sorted((DESIGN / "migrations").glob("*.sql")):
        src.executescript(path.read_text())
    db.executescript(schema_sql())
    memory_workspace(db)
    src.execute("INSERT INTO sources VALUES('source','local-git','source','{}',NULL)")
    src.execute(
        "INSERT INTO repositories VALUES('repo','source','local','repo','name','/synthetic','{}',NULL)"
    )
    src.execute(
        "INSERT INTO jobs(id,kind,request,state,created_at,updated_at) VALUES('job','sync','{}','complete',?,?)",
        (STAMP, STAMP),
    )
    src.execute(
        "INSERT INTO collection_runs(id,job_id,repo_id,generation,attempt,state,started_at,refs_at,ended_at,object_format,kind,roots_manifest,request) VALUES('run','job','repo',1,1,'published',?,?,?,'sha1','git','[]','{}')",
        (STAMP, STAMP, STAMP),
    )
    db.execute(
        "INSERT INTO sources(source_id,service_instance_uuidv4,discovery_kind,name,settings) VALUES('source',NULL,'manual_git','source','{}')"
    )
    db.execute(
        "INSERT INTO repositories(repository_id,name,preferred_repository_endpoint_id,current_snapshot_id,metadata) VALUES('repo','name',NULL,NULL,'{}')"
    )
    body, missing_oid = b"hello\n", git_payload("blob", b"binary\xff")
    blob_oid = git_payload("blob", body)
    tree = b"100644 lost.bin\0" + missing_oid + b"100644 raw-\xff.py\0" + blob_oid
    tree_oid = git_payload("tree", tree)
    header = b"tree " + tree_oid.hex().encode()
    parent_a, parent_b = header + b"\n\nparent a\n", header + b"\n\nparent b\n"
    a_oid, b_oid = git_payload("commit", parent_a), git_payload("commit", parent_b)
    merge_header = (
        header
        + b"\nparent "
        + a_oid.hex().encode()
        + b"\nparent "
        + b_oid.hex().encode()
    )
    merge = merge_header + b"\n\nmerge \xff\n"
    merge_oid = git_payload("commit", merge)
    tag = (
        b"object " + merge_oid.hex().encode() + b"\ntype commit\ntag v1\n\nannotated\n"
    )
    tag_oid = git_payload("tag", tag)
    for ident, oid, kind, size in (
        (1, merge_oid, "commit", len(merge)),
        (2, blob_oid, "blob", len(body)),
        (3, missing_oid, "blob", 7),
        (4, tree_oid, "tree", len(tree)),
        (5, a_oid, "commit", len(parent_a)),
        (6, b_oid, "commit", len(parent_b)),
        (7, tag_oid, "tag", len(tag)),
    ):
        src.execute(
            "INSERT INTO git_objects VALUES(?,'sha1',?,?,?,1)", (ident, oid, kind, size)
        )
        src.execute(
            "INSERT INTO repository_object_sources VALUES('repo',?,'run')", (ident,)
        )
    src.executemany(
        "INSERT INTO commits VALUES(?,4,?,?,?)",
        [
            (1, merge_header, b"merge \xff\n", '{ "exact": 1 }'),
            (5, header, b"parent a\n", "{}"),
            (6, header, b"parent b\n", "{}"),
        ],
    )
    src.executemany("INSERT INTO commit_parents VALUES(1,?,?)", [(0, 5), (1, 6)])
    src.executemany(
        "INSERT INTO tree_entries VALUES(4,?,33188,'sha1',?,?)",
        [(b"lost.bin", missing_oid, 3), (b"raw-\xff.py", blob_oid, 2)],
    )
    src.execute("INSERT INTO tag_objects VALUES(7,1,?)", (tag,))
    src.execute("INSERT INTO contents VALUES(11,6,'hello\n','eligible',?)", (STAMP,))
    src.execute("INSERT INTO contents VALUES(12,7,NULL,'non_utf8',?)", (STAMP,))
    src.executemany(
        "INSERT INTO blob_content_map VALUES(?,?,'run')", [(2, 11), (3, 12)]
    )
    for algorithm in ("md5", "sha1", "sha256"):
        src.execute(
            "INSERT INTO content_digests VALUES(11,'raw-content-v1',?,?,?,'v1')",
            (algorithm, hashlib.new(algorithm, body).digest(), STAMP),
        )
    src.execute("INSERT INTO snapshots VALUES('snap','run','repo',1,1,?)", (STAMP,))
    for name in (b"refs/heads/main", b"refs/heads/raw-\xff"):
        src.execute(
            "INSERT INTO ref_observations VALUES('snap',?,'head','sha1',?,NULL,'commit')",
            (name, merge_oid),
        )
    src.execute(
        "INSERT INTO ref_observations VALUES('snap',?,'tag','sha1',?,?,'tag')",
        (b"refs/tags/v1", tag_oid, merge_oid),
    )
    src.execute(
        "INSERT INTO acquisition_roots VALUES(21,'run','repo','sha1',?,'head',NULL,NULL,NULL,1)",
        (merge_oid,),
    )
    src.execute("INSERT INTO root_manifests VALUES(4,1)")
    src.executemany(
        "INSERT INTO root_manifest_entries VALUES(4,?,33188,?,'sha1',?)",
        [(b"lost.bin", 3, missing_oid), (b"raw-\xff.py", 2, blob_oid)],
    )
    db.execute(
        "INSERT INTO conversion_sources(conversion_source_id,source_sha256,schema_sha256,format_id,source_db_instance_id,source_catalog,source_migrations) VALUES('sealed',?,?, 'v2','synthetic',x'',x'')",
        (b"s" * 32, b"d" * 32),
    )
    db.commit()
    yield src, db, {"conversion_source_id": "sealed"}
    src.close()
    db.close()


def normalize(graph, *, through=None):
    src, db, run = graph
    for table in sorted(
        {git_domain.SOURCE_TABLES.get(recipe, recipe) for recipe in git_domain.RECIPES}
    ):
        for record in archive.rows(src, table):
            db.execute(
                "INSERT INTO legacy_records(conversion_source_id,source_table,source_key,row_sha256) VALUES('sealed',?,?,?)",
                (table, record.key, record.row_sha256),
            )
    db.commit()
    outputs = {}
    for recipe in git_domain.RECIPES:
        records = tuple(archive.rows(src, git_domain.SOURCE_TABLES.get(recipe, recipe)))
        output = git_domain.prepare(
            db,
            src,
            run,
            recipe,
            0,
            records,
            encoding=src.execute("PRAGMA encoding").fetchone()[0],
        )
        outputs[recipe] = output
        for operation in output["operations"]:
            table, row = operation["table"], operation["row"]
            if operation["operation"] == "manifest_completion":
                db.execute(
                    "UPDATE root_manifests SET complete=? WHERE tree_git_object_id=?",
                    (row[1], row[0]),
                )
            else:
                columns = ",".join(git_domain.COLUMNS[table])
                db.execute(
                    f"INSERT INTO {table}({columns}) VALUES({','.join('?' for _ in row)})",
                    row,
                )
        db.commit()
        if recipe == through:
            break
    return outputs


def codes(output):
    return {row[1] for row in output["diagnostics"]}


@pytest.mark.parametrize("graph", ["UTF-8", "UTF-16le", "UTF-16be"], indirect=True)
def test_stored_git_recipes_preserve_raw_bytes_ids_order_and_all_ref_origins(graph):
    src, db, _ = graph
    before = tuple(src.iterdump())
    outputs = normalize(graph)
    assert tuple(src.iterdump()) == before
    assert [
        tuple(row)
        for row in db.execute("SELECT * FROM commit_parents ORDER BY parent_ordinal")
    ] == [(1, 0, 5), (1, 1, 6)]
    assert db.execute(
        "SELECT raw_message,metadata FROM commits WHERE git_object_id=1"
    ).fetchone()[:] == (b"merge \xff\n", '{ "exact": 1 }')
    assert (
        db.execute(
            "SELECT raw_name FROM tree_entries WHERE child_git_object_id=2"
        ).fetchone()[0]
        == b"raw-\xff.py"
    )
    assert (
        db.execute(
            "SELECT raw_path FROM root_manifest_entries WHERE git_object_id=2"
        ).fetchone()[0]
        == b"raw-\xff.py"
    )
    assert (
        db.execute("SELECT raw_payload FROM tag_objects").fetchone()[0]
        == src.execute("SELECT raw_payload FROM tag_objects").fetchone()[0]
    )
    assert (
        db.execute(
            "SELECT count(*) FROM root_origins WHERE acquisition_root_id=21 AND origin_kind='ref'"
        ).fetchone()[0]
        == 3
    )
    assert (
        db.execute(
            "SELECT count(*) FROM root_origins WHERE origin_kind='legacy_unknown'"
        ).fetchone()[0]
        == 0
    )
    assert db.execute("SELECT complete FROM root_manifests").fetchone()[0] == 1
    assert (
        db.execute("SELECT git_object_id FROM git_objects WHERE verified=0").fetchone()[
            0
        ]
        == 3
    )
    assert codes(outputs["git_objects"]) == {"GIT_ORIGINAL_BYTES_MISSING"}
    assert (
        db.execute("SELECT raw_text FROM contents WHERE content_id=12").fetchone()[0]
        is None
    )
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert db.execute(
        "SELECT source_id,observed_at_us,refs_observed_at_us FROM git_acquisitions"
    ).fetchone()[:] == (None, None, STAMP_US)


def test_missing_original_is_not_empty_and_old_verified_is_not_proof(graph):
    src, db, _ = graph
    normalize(graph, through="git_objects")
    source = src.execute("SELECT verified,size FROM git_objects WHERE id=3").fetchone()
    assert source[:] == (1, 7)
    assert db.execute(
        "SELECT verified,size FROM git_objects WHERE git_object_id=3"
    ).fetchone()[:] == (0, 7)
    assert (
        db.execute("SELECT verified FROM git_objects WHERE git_object_id=2").fetchone()[
            0
        ]
        == 1
    )


@pytest.mark.parametrize(
    "source_stamp,expected_us,diagnostic",
    [
        ("1970-01-01T09:00:00+09:00", 0, None),
        ("1969-12-31T23:59:59.999999Z", -1, None),
        ("2026-01-02T03:04:05.000001Z", STAMP_US + 1, None),
        (None, None, "GIT_OBSERVATION_TIME_MISSING"),
        ("2026-01-02T03:04:05", None, "GIT_INVALID_TIME"),
        ("2026-01-02T03:04:05.0000001Z", None, "GIT_INVALID_TIME"),
        ("invalid-source-time", None, "GIT_INVALID_TIME"),
    ],
)
def test_source_git_observation_time_is_exact_or_unknown_with_evidence(
    graph, source_stamp, expected_us, diagnostic
):
    src, db, _ = graph
    src.execute("UPDATE collection_runs SET refs_at=?", (source_stamp,))
    before = tuple(src.iterdump())
    output = normalize(graph, through="git_acquisitions")["git_acquisitions"]
    assert tuple(src.iterdump()) == before
    row = db.execute(
        "SELECT refs_observed_at_us,typeof(refs_observed_at_us),started_at_us,observed_at_us FROM git_acquisitions"
    ).fetchone()
    assert tuple(row) == (
        expected_us,
        "null" if expected_us is None else "integer",
        STAMP_US,
        None,
    )
    assert codes(output) == ({diagnostic} if diagnostic else set())
    assert output["decisions"][0]["disposition"] == "normalized"


@pytest.mark.parametrize(
    "mutation,recipe,code",
    [
        (
            "UPDATE commit_parents SET parent_id=6 WHERE parent_ordinal=0",
            "commit_parents",
            "GIT_PARENT_ORDER_MISMATCH",
        ),
        (
            "UPDATE tree_entries SET child_oid=zeroblob(20) WHERE child_id=2",
            "tree_entries",
            "GIT_OBJECT_RELATION_MISMATCH",
        ),
        (
            "UPDATE contents SET byte_length=5 WHERE id=11",
            "contents",
            "GIT_CONTENT_LENGTH_MISMATCH",
        ),
        (
            "UPDATE content_digests SET digest=zeroblob(32) WHERE algorithm='sha256'",
            "content_digests",
            "GIT_CONTENT_DIGEST_MISMATCH",
        ),
        (
            "UPDATE root_manifest_entries SET raw_path=x'77726f6e67' WHERE object_id=2",
            "root_manifest_entries",
            "GIT_MISSING_REFERENCE",
        ),
    ],
)
def test_malformed_relation_is_archived_with_attributed_diagnostic(
    graph, mutation, recipe, code
):
    src, db, _ = graph
    src.execute(mutation)
    output = normalize(graph, through=recipe)[recipe]
    assert code in codes(output)
    assert any(
        decision["disposition"] == "archive_only" for decision in output["decisions"]
    )
    assert all(
        '"legacy_record_id":' in row[3] and '"column":' in row[3]
        for row in output["diagnostics"]
    )


def test_completed_manifest_with_missing_path_remains_explicitly_partial(graph):
    src, db, _ = graph
    src.execute("DELETE FROM root_manifest_entries WHERE object_id=2")
    outputs = normalize(graph, through="root_manifests")
    assert db.execute("SELECT complete FROM root_manifests").fetchone()[0] == 0
    assert "GIT_MANIFEST_COVERAGE_MISMATCH" in codes(outputs["root_manifests"])
    assert src.execute("SELECT complete FROM root_manifests").fetchone()[0] == 1


def test_malformed_tree_text_is_diagnosed_without_sqlite_decoder_failure(graph):
    src, db, _ = graph
    src.execute(
        "UPDATE tree_entries SET child_format=CAST(x'ff' AS TEXT) WHERE child_id=2"
    )
    outputs = normalize(graph, through="root_manifests")
    assert "GIT_MALFORMED_TEXT" in codes(outputs["tree_entries"])
    assert "GIT_MANIFEST_COVERAGE_MISMATCH" in codes(outputs["root_manifests"])
    assert (
        db.execute(
            "SELECT complete FROM root_manifests WHERE tree_git_object_id=4"
        ).fetchone()[0]
        == 0
    )


@pytest.mark.parametrize("name,parsed", [(b"sub", False), (b".", True)])
def test_completed_manifest_requires_safe_parsed_empty_subtree(graph, name, parsed):
    src, db, _ = graph
    payload = b"" if parsed else b"100644 hidden\0" + b"x" * 20
    oid = git_payload("tree", payload)
    src.execute(
        "INSERT INTO git_objects VALUES(8,'sha1',?,'tree',?,1)", (oid, len(payload))
    )
    src.execute("INSERT INTO tree_entries VALUES(4,?,16384,'sha1',?,8)", (name, oid))
    if parsed:
        src.execute("INSERT INTO root_manifests VALUES(8,1)")
    outputs = normalize(graph, through="root_manifests")
    assert (
        db.execute(
            "SELECT complete FROM root_manifests WHERE tree_git_object_id=4"
        ).fetchone()[0]
        == 0
    )
    assert "GIT_MANIFEST_COVERAGE_MISMATCH" in codes(outputs["root_manifests"])
    if parsed:
        assert "GIT_INVALID_TREE_ENTRY" in codes(outputs["tree_entries"])


def test_complete_manifest_cannot_hide_same_missing_tree_and_manifest_rows(graph):
    src, db, _ = graph
    src.execute("DELETE FROM tree_entries")
    src.execute("DELETE FROM root_manifest_entries")
    outputs = normalize(graph, through="root_manifests")
    assert (
        db.execute("SELECT verified FROM git_objects WHERE git_object_id=4").fetchone()[
            0
        ]
        == 0
    )
    assert (
        db.execute(
            "SELECT complete FROM root_manifests WHERE tree_git_object_id=4"
        ).fetchone()[0]
        == 0
    )
    assert "GIT_MANIFEST_COVERAGE_MISMATCH" in codes(outputs["root_manifests"])


def test_complete_manifest_requires_demonstrated_subtree_bytes(graph):
    src, db, _ = graph
    child_oid = src.execute("SELECT oid FROM git_objects WHERE id=2").fetchone()[0]
    subtree = b"100644 hidden\0" + child_oid
    subtree_oid = git_payload("tree", subtree)
    src.execute(
        "INSERT INTO git_objects VALUES(8,'sha1',?,'tree',?,1)",
        (subtree_oid, len(subtree)),
    )
    src.execute("INSERT INTO root_manifests VALUES(8,1)")
    src.execute(
        "INSERT INTO tree_entries VALUES(4,x'737562',16384,'sha1',?,8)", (subtree_oid,)
    )
    root = b"".join(
        f"{mode:o} ".encode() + name + b"\0" + oid
        for name, mode, oid in src.execute(
            "SELECT raw_name,mode,child_oid FROM tree_entries WHERE tree_id=4 ORDER BY raw_name"
        )
    )
    src.execute(
        "UPDATE git_objects SET oid=?,size=? WHERE id=4",
        (git_payload("tree", root), len(root)),
    )
    outputs = normalize(graph, through="root_manifests")
    assert db.execute(
        "SELECT git_object_id,verified FROM git_objects WHERE git_object_id IN (4,8) ORDER BY git_object_id"
    ).fetchall()[0][:] == (4, 1)
    assert (
        db.execute("SELECT verified FROM git_objects WHERE git_object_id=8").fetchone()[
            0
        ]
        == 0
    )
    assert (
        db.execute(
            "SELECT complete FROM root_manifests WHERE tree_git_object_id=4"
        ).fetchone()[0]
        == 0
    )
    assert "GIT_MANIFEST_COVERAGE_MISMATCH" in codes(outputs["root_manifests"])


def test_tag_message_does_not_satisfy_conflicting_target_type_header(graph):
    src, db, _ = graph
    raw = src.execute("SELECT raw_payload FROM tag_objects").fetchone()[0]
    raw = raw.replace(b"type commit\n", b"type blob\n", 1) + b"type commit\n"
    src.execute("UPDATE tag_objects SET raw_payload=?", (raw,))
    src.execute(
        "UPDATE git_objects SET oid=?,size=? WHERE id=7",
        (git_payload("tag", raw), len(raw)),
    )
    outputs = normalize(graph, through="tag_objects")
    assert (
        db.execute("SELECT verified FROM git_objects WHERE git_object_id=7").fetchone()[
            0
        ]
        == 1
    )
    assert db.execute("SELECT count(*) FROM tag_objects").fetchone()[0] == 0
    assert "GIT_TAG_TARGET_MISMATCH" in codes(outputs["tag_objects"])


def test_origin_ids_and_typed_maps_are_repeatable_with_raw_refs(graph):
    src, db, run = graph
    normalize(graph, through="root_manifest_entries")
    records = tuple(archive.rows(src, "ref_observations"))
    first = git_domain.prepare(db, src, run, "ref_root_origins", 0, records)
    second = git_domain.prepare(
        db, src, run, "ref_root_origins", 0, records, verifying=True
    )
    assert first == second
    ids = [op["row"][0] for op in first["operations"]]
    assert len(set(ids)) == 3 and all(0 <= ident < 2**63 for ident in ids)
    assert all(mapped[3] == "split" for mapped in first["mappings"])
    for op in first["operations"]:
        assert archive.decode_key(git_domain.target_key(op["table"], op["row"])) == [
            ("integer", op["row"][0])
        ]


def test_unknown_origin_preserves_root_with_partial_provenance(graph):
    src, db, _ = graph
    src.execute("DELETE FROM ref_observations")
    outputs = normalize(graph)
    assert db.execute(
        "SELECT origin_kind,raw_ref_name,snapshot_id,change_request_id,change_request_observation_id FROM root_origins"
    ).fetchone()[:] == ("legacy_unknown", None, None, None, None)
    assert "GIT_ROOT_ORIGIN_UNKNOWN" in codes(outputs["unknown_root_origins"])


def test_unknown_origin_skips_exactly_archived_malformed_pr_role(graph):
    src, db, _ = graph
    src.execute("DELETE FROM ref_observations")
    oid = src.execute("SELECT oid FROM acquisition_roots WHERE id=21").fetchone()[0]
    src.execute(
        "INSERT INTO pr_git_links VALUES(501,CAST(x'ff' AS TEXT),'sha1',?,21)", (oid,)
    )
    outputs = normalize(graph)
    assert "GIT_MALFORMED_TEXT" in codes(outputs["pr_root_origins"])
    assert (
        db.execute("SELECT origin_kind FROM root_origins").fetchone()[0]
        == "legacy_unknown"
    )
    assert (
        src.execute("SELECT CAST(role AS BLOB) FROM pr_git_links").fetchone()[0]
        == b"\xff"
    )


def test_unknown_origin_skips_exactly_archived_malformed_snapshot_key(graph):
    src, db, _ = graph
    src.execute("UPDATE snapshots SET id=CAST(x'ff' AS TEXT)")
    src.execute("UPDATE ref_observations SET snapshot_id=CAST(x'ff' AS TEXT)")
    outputs = normalize(graph)
    assert "GIT_MALFORMED_TEXT" in codes(outputs["ref_observations"])
    assert (
        db.execute("SELECT origin_kind FROM root_origins").fetchone()[0]
        == "legacy_unknown"
    )


def test_unknown_content_state_keeps_safe_identity_and_missing_bytes(graph):
    src, db, _ = graph
    src.execute("UPDATE contents SET text_state='legacy-binary' WHERE id=12")
    outputs = normalize(graph)
    assert db.execute(
        "SELECT byte_length,raw_text,text_state FROM contents WHERE content_id=12"
    ).fetchone()[:] == (7, None, "unknown")
    assert "GIT_UNKNOWN_TEXT_STATE" in codes(outputs["contents"])
    assert (
        db.execute(
            "SELECT content_id FROM blob_content_map WHERE git_object_id=3"
        ).fetchone()[0]
        == 12
    )
    assert all(row[2] != "blocking" for row in outputs["contents"]["diagnostics"])


def test_bad_legacy_verified_assertion_keeps_hash_demonstrated_identity(graph):
    src, db, _ = graph
    src.execute("UPDATE git_objects SET verified=9 WHERE id=2")
    outputs = normalize(graph, through="git_objects")
    assert db.execute(
        "SELECT git_object_id,verified FROM git_objects WHERE git_object_id=2"
    ).fetchone()[:] == (2, 1)
    assert "GIT_INVALID_VERIFICATION_ASSERTION" in codes(outputs["git_objects"])
    assert src.execute("SELECT verified FROM git_objects WHERE id=2").fetchone()[0] == 9


@pytest.mark.parametrize("claimed_observation", [501, 999])
def test_pr_origin_requires_exact_saved_observation_and_code_acquisition(
    graph, claimed_observation
):
    src, db, run = graph
    oid = src.execute("SELECT oid FROM git_objects WHERE id=5").fetchone()[0]
    src.execute("INSERT INTO pull_requests VALUES('pr','repo',7,NULL,NULL)")
    src.execute("INSERT INTO pr_observations VALUES(501,'pr','job',?,'{}',1)", (STAMP,))
    src.execute(
        "INSERT INTO pr_code_observations VALUES(501,'pr',501,?,NULL,'partial','{}')",
        (oid.hex(),),
    )
    src.execute(
        "INSERT INTO acquisition_roots VALUES(22,'run','repo','sha1',?,'head',7,?,NULL,1)",
        (oid, claimed_observation),
    )
    src.execute("INSERT INTO pr_git_links VALUES(501,'head','sha1',?,22)", (oid,))
    normalize(graph, through="root_manifest_entries")
    db.execute(
        "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,web_base_url,api_base_url,metadata,created_at_us) VALUES('00000000-0000-4000-8000-000000000101','git','00000000-0000-4000-8000-000000000101',NULL,NULL,'{}',NULL)"
    )
    db.execute(
        "INSERT INTO repository_bindings(repository_binding_id,repository_id,service_instance_uuidv4,provider_repository_id,metadata,created_at_us) VALUES('binding','repo','00000000-0000-4000-8000-000000000101',NULL,'{}',NULL)"
    )
    db.execute(
        "INSERT INTO change_requests(change_request_id,repository_id,repository_binding_id,change_request_kind,provider_change_request_number,current_change_request_observation_id) VALUES('pr','repo','binding','pull_request',7,NULL)"
    )
    db.execute(
        "INSERT INTO change_request_observations(change_request_observation_id,change_request_id,observed_at_us,published,payload,origin_key,parsed_at_us,origin_fetch_occurrence_id) VALUES(501,'pr',?,1,'{}','saved',?,NULL)",
        (STAMP_US, STAMP_US),
    )
    db.execute(
        "INSERT INTO code_observations(code_observation_id,change_request_id,change_request_observation_id,commit_code_listing_id,file_code_listing_id,state,object_format,head_oid,base_oid,details) VALUES(501,'pr',501,NULL,NULL,'partial','sha1',?,NULL,'{}')",
        (oid,),
    )
    db.execute(
        "INSERT INTO code_acquisitions(code_observation_id,role,object_format,oid,acquisition_root_id) VALUES(501,'head','sha1',?,22)",
        (oid,),
    )
    records = tuple(archive.rows(src, "pr_git_links"))
    output = git_domain.prepare(db, src, run, "pr_root_origins", 0, records)
    if claimed_observation == 501:
        row = output["operations"][0]["row"]
        assert row[1:] == (22, "pr_role", None, 501, None, "pr", 501, "repo")
        db.execute(
            "INSERT INTO root_origins(root_origin_id,acquisition_root_id,origin_kind,raw_ref_name,source_ordinal,snapshot_id,change_request_id,change_request_observation_id,repository_id) VALUES(?,?,?,?,?,?,?,?,?)",
            row,
        )
        assert codes(output) == set()
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    else:
        assert output["operations"] == []
        assert "GIT_PR_ROOT_MISMATCH" in codes(output)
        assert output["decisions"][0]["disposition"] == "archive_only"
