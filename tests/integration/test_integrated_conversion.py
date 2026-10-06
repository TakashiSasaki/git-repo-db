"""Guarded operational v2 -> normalized Git/PR -> useful offline queries."""

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time

import pytest

from repo_catalog.application.target_queries import TargetQueryService
from scripts.conversion import (
    batch,
    integrated_parent,
    integrated_phase,
    source,
    target,
)
from scripts.conversion.common import ROOT, canonical
from tests.support.integrated_fixture import (
    AVAILABLE_TEXT,
    IDS,
    OBJECT_IDS,
    OIDS,
    RAW_PATHS,
    SAVED_BODY_SEQUENCE,
    SAVED_EARLY_BODY,
    SAVED_PAGE_STAMPS,
    make_integrated_source,
)
from tests.support.p3b_fixture import assert_exact_archive, cli, export_reviewed


def worker(workspace, *arguments, expected=0, module="tests.support.integrated_worker"):
    env = dict(os.environ)
    if sqlite3.sqlite_version_info < (3, 46, 1):
        env["TEST_SQLITE_MINIMUM"] = "3.46.1"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            module,
            str(workspace),
            *map(str, arguments),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == expected, (result.stdout, result.stderr)
    return (
        None
        if expected == 77
        else json.loads(result.stdout if expected == 0 else result.stderr)
    )


def prepared(tmp_path, *, malformed=False, scale=1):
    database, cache = make_integrated_source(
        tmp_path / "source", derived=True, malformed=malformed, scale=scale
    )
    work = tmp_path / "conversion"
    before = source.file_fingerprint(database), source.cache_inventory([cache])
    cli("seal", work, "--source", database, "--source-cache", cache)
    return database, cache, work, before


def unchanged(database, cache, before):
    assert before == (
        source.file_fingerprint(database),
        source.cache_inventory([cache]),
    )


def graph(work):
    with source.readonly(work / "target.sqlite3") as db:
        return {
            table: sorted(
                (tuple(row) for row in db.execute(f'SELECT * FROM "{table}"')), key=repr
            )
            for table in integrated_phase.definitions()[0]
        }


def items(result):
    return result.data["items"]


def test_operational_source_normalized_queries_search_and_saved_history(tmp_path):
    database, cache, work, before = prepared(tmp_path)
    status = cli("integrated", work, "--batch-size", 2)
    assert status["complete"] and not status["activation_permitted"]
    assert status["lifecycle"] == "building"
    assert not status["diagnostics"].get("blocking", 0)
    assert cli("verify-stored", work)["complete"]
    assert_exact_archive(database, work)
    with (
        source.readonly(database) as src,
        source.readonly(work / "target.sqlite3") as db,
    ):
        for table in ("commit_parents", "tree_entries", "root_manifest_entries"):
            assert sorted(
                (tuple(row) for row in db.execute(f'SELECT * FROM "{table}"')), key=repr
            ) == sorted(
                (tuple(row) for row in src.execute(f'SELECT * FROM "{table}"')),
                key=repr,
            )
        assert [
            tuple(row)
            for row in db.execute(
                "SELECT parent_ordinal,parent_id FROM commit_parents WHERE commit_id=? ORDER BY parent_ordinal",
                (OBJECT_IDS["merge"],),
            )
        ] == [(0, OBJECT_IDS["parent_a"]), (1, OBJECT_IDS["parent_b"])]
        origins = db.execute(
            "SELECT root_id,raw_ref_name FROM root_origins WHERE origin_kind='ref' AND raw_ref_name IN (?,?) ORDER BY raw_ref_name",
            (b"refs/heads/main", b"refs/heads/alias"),
        ).fetchall()
        assert len(origins) == 2 and origins[0][0] == origins[1][0]
        assert len({row[1] for row in origins}) == 2
        assert (
            db.execute(
                "SELECT count(*) FROM repositories WHERE current_snapshot_id IS NOT NULL"
            ).fetchone()[0]
            == 0
        )
        history = db.execute(
            "SELECT b.body,o.observed_at FROM document_observations o JOIN document_versions v ON v.id=o.version_id JOIN text_bodies b ON b.id=v.body_id WHERE o.document_id=? ORDER BY o.observed_at,o.id",
            (IDS["document_a"],),
        ).fetchall()
        assert [row[0] for row in history[:3]] == ["A", "B", "A"]
        assert len({row[1] for row in history[:3]}) == 3
        assert (
            db.execute(
                "SELECT count(*) FROM documents WHERE provider_id='902'"
            ).fetchone()[0]
            == 1
        )
        restored = db.execute(
            "SELECT b.body,o.observed_at,v.id FROM document_observations o "
            "JOIN documents d ON d.id=o.document_id "
            "JOIN document_versions v ON v.id=o.version_id "
            "JOIN text_bodies b ON b.id=v.body_id WHERE d.provider_id='902' "
            "ORDER BY o.observed_at,o.id"
        ).fetchall()
        assert tuple(row[0] for row in restored) == SAVED_BODY_SEQUENCE
        assert tuple(row[1] for row in restored) == SAVED_PAGE_STAMPS
        assert len({row[2] for row in restored}) == 3
        assert (
            db.execute(
                "SELECT count(*) FROM text_bodies WHERE body=?", (SAVED_EARLY_BODY,)
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT count(*) FROM code_listing_progress WHERE state='partial'"
            ).fetchone()[0]
            >= 2
        )
        assert (
            db.execute(
                "SELECT count(*) FROM code_listing_progress WHERE state='complete'"
            ).fetchone()[0]
            >= 2
        )
        assert (
            db.execute(
                "SELECT count(*) FROM code_acquisitions WHERE root_id IS NOT NULL"
            ).fetchone()[0]
            >= 2
        )
    target_hash = hashlib.sha256((work / "target.sqlite3").read_bytes()).hexdigest()
    query = TargetQueryService(work / "target.sqlite3", allow_building=True)
    commit = "sha1:" + OIDS["merge"].hex()
    assert len(items(query.query("repos"))) == 3
    details = items(query.query("commit", {"repo": IDS["repo"], "commit": commit}))[0]
    assert [parent["object_id"] for parent in details["parents"]] == [
        OBJECT_IDS["parent_a"],
        OBJECT_IDS["parent_b"],
    ]
    file = items(
        query.query(
            "file",
            {"repo": IDS["repo"], "commit": commit, "path": RAW_PATHS[0].decode()},
        )
    )[0]
    assert file["text"] == AVAILABLE_TEXT and file["digests"]
    missing = query.query(
        "file", {"repo": IDS["repo"], "commit": commit, "path": "lost.txt"}
    )
    assert items(missing)[0]["text"] is None and missing.status == "partial"
    assert items(query.query("pr", {"repo": IDS["repo"], "number": 7}, limit=1000))
    for kind, literal in (
        ("code", "searchable sentinel"),
        ("commits", "merge"),
        ("pr", SAVED_EARLY_BODY),
    ):
        result = query.query(
            "search", {"repo": IDS["repo"], "kind": kind, "literal": literal}
        )
        assert items(result), (kind, result)
        assert result.status == "partial" and result.execution["backend"] == "scan"
    assert (
        target_hash
        == hashlib.sha256((work / "target.sqlite3").read_bytes()).hexdigest()
    )
    unchanged(database, cache, before)


def test_malformed_rows_stay_archived_and_expose_attributed_diagnostics(tmp_path):
    database, cache, work, before = prepared(tmp_path, malformed=True)
    status = cli("integrated", work, "--batch-size", 2)
    assert status["complete"] and not status["normalized_ready"]
    assert status["diagnostics"]["blocking"] > 0
    assert_exact_archive(database, work)
    with source.readonly(work / "target.sqlite3") as db:
        defects = list(
            db.execute(
                "SELECT details FROM validation_results WHERE code LIKE 'GIT_%' OR code LIKE 'PR_%'"
            )
        )
        assert defects and all(json.loads(row[0]).get("record_id") for row in defects)
    unchanged(database, cache, before)


@pytest.mark.parametrize(
    "point,spill", [("before_commit", True), ("after_commit", False)]
)
def test_actual_process_commit_interruption_resumes_identical_domain_graph(
    tmp_path, point, spill
):
    database, cache, work, before = prepared(tmp_path)
    cli("archive", work, "--batch-size", 2)
    cli("handoff", work)
    cli("identity", work, "--batch-size", 2)
    cli("stored", work, "--batch-size", 2, "--max-batches", 0)
    seed = tmp_path / "seed.sqlite3"
    shutil.copyfile(work / "target.sqlite3", seed)
    cli("stored", work, "--batch-size", 2)
    expected = graph(work)
    shutil.copyfile(seed, work / "target.sqlite3")
    args = ["--fault", point, "--fault-table", "payloads"] + (
        ["--spill"] if spill else []
    )
    worker(work, *args, expected=77)
    if spill:
        assert (work / "target.sqlite3-journal").exists()
    worker(work)
    assert cli("verify-stored", work)["complete"]
    assert graph(work) == expected
    with source.readonly(work / "target.sqlite3") as db:
        mappings = [
            tuple(row) for row in db.execute("SELECT * FROM id_mappings ORDER BY id")
        ]
    assert cli("stored", work, "--batch-size", 2)["new_batches"] == 0
    with source.readonly(work / "target.sqlite3") as db:
        assert mappings == [
            tuple(row) for row in db.execute("SELECT * FROM id_mappings ORDER BY id")
        ]
    unchanged(database, cache, before)


def test_guard_denials_and_modest_scaling_without_payload_proof_copies(
    tmp_path, capsys
):
    database, cache, work, before = prepared(tmp_path, scale=200)
    for probe in ("network", "source-write", "cache-write"):
        assert worker(work, "--probe", probe)["denied"] == probe
    started = time.monotonic()
    status = cli("integrated", work, "--batch-size", 50)
    seconds = time.monotonic() - started
    assert (
        status["complete"] and status["normalized_rows"]["document_observations"] >= 200
    )
    with source.readonly(work / "target.sqlite3") as db:
        manifests = list(
            db.execute(
                "SELECT output_manifest FROM conversion_batches WHERE run_id=(SELECT id FROM conversion_runs WHERE parser_version='p3-integrated/1')"
            )
        )
        assert all(
            AVAILABLE_TEXT not in row[0] and SAVED_EARLY_BODY not in row[0]
            for row in manifests
        )
        assert max(len(row[0]) for row in manifests) < 200_000
    print(
        json.dumps(
            {
                "synthetic_scale": 200,
                "conversion_seconds": round(seconds, 3),
                "batches": status["committed_batches"],
            }
        )
    )
    assert seconds < 45
    unchanged(database, cache, before)


def test_locked_invocation_audits_parent_once(tmp_path, monkeypatch):
    _, _, work, _ = prepared(tmp_path)
    cli("integrated", work, "--batch-size", 2, "--max-batches", 1)
    calls = []
    original = integrated_parent.check_parent

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(integrated_parent, "check_parent", counted)
    assert integrated_phase.convert(work, batch_size=2)["complete"]
    assert len(calls) == 1
    comparisons = []
    original_output = integrated_phase.validate_output

    def counted_output(*args, **kwargs):
        comparisons.append(1)
        return original_output(*args, **kwargs)

    monkeypatch.setattr(integrated_phase, "validate_output", counted_output)
    unchanged_status = integrated_phase.convert(work, batch_size=2)
    assert unchanged_status["new_batches"] == 0
    assert unchanged_status["verification"]["exit_comparisons"] == 0
    assert len(comparisons) == 1 and len(calls) == 2


def test_authentic_reviewed_p3b_stored_conversion_and_queries(tmp_path):
    database, cache = make_integrated_source(tmp_path / "source", derived=True)
    work = tmp_path / "conversion"
    before = source.file_fingerprint(database), source.cache_inventory([cache])
    reviewed = export_reviewed(
        tmp_path / "reviewed", revision=integrated_parent.REVIEWED_P3B_REVISION
    )
    cli("seal", work, "--source", database, "--source-cache", cache, root=reviewed)
    cli("archive", work, "--batch-size", 2, root=reviewed)
    cli("handoff", work, root=reviewed)
    assert cli("identity", work, "--batch-size", 2, root=reviewed)["complete"]
    assert cli("stored", work, "--batch-size", 2)["complete"]
    assert cli("verify-stored", work)["complete"]
    query = TargetQueryService(work / "target.sqlite3", allow_building=True)
    assert items(
        query.query(
            "search", {"repo": IDS["repo"], "kind": "pr", "literal": SAVED_EARLY_BODY}
        )
    )
    unchanged(database, cache, before)


def test_coherently_rehashed_domain_corruption_still_fails_source_comparison(tmp_path):
    database, cache, work, before = prepared(tmp_path)
    cli("integrated", work, "--batch-size", 2)
    with sqlite3.connect(work / "target.sqlite3") as db:
        triggers = list(
            db.execute(
                "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name IN ('contents','conversion_batches')"
            )
        )
        for name, _ in triggers:
            db.execute(f'DROP TRIGGER "{name}"')
        db.execute(
            "UPDATE contents SET raw_text=replace(raw_text,'sentinel','sentinex') WHERE raw_text IS NOT NULL"
        )
        actual = db.execute(
            "SELECT * FROM contents WHERE raw_text IS NOT NULL"
        ).fetchone()
        for ident, text in db.execute(
            "SELECT id,output_manifest FROM conversion_batches WHERE source_table='contents' "
            "AND run_id=(SELECT id FROM conversion_runs WHERE parser_version='p3-integrated/1')"
        ).fetchall():
            value = json.loads(text)
            for op in value["output"]["operations"]:
                if op["table"] == "contents" and op["key"] == [actual[0]]:
                    op["sha256"] = integrated_phase.row_hash(actual)
            value["output_sha256"] = batch.proof_digest(value["output"])
            db.execute(
                "UPDATE conversion_batches SET output_manifest=? WHERE id=?",
                (canonical(value), ident),
            )
        for _, sql in triggers:
            db.execute(sql)
    error = cli("verify-stored", work, expected=2)
    assert error["code"] == "INTEGRATED_SOURCE_MISMATCH"
    unchanged(database, cache, before)


@pytest.mark.parametrize("phase", ["archive", "identity"])
def test_guarded_integrated_resumes_partial_upstream_with_saved_options(
    tmp_path, phase
):
    database, cache, work, before = prepared(tmp_path)
    cli(
        "archive",
        work,
        "--batch-size",
        2,
        "--representative-repositories",
        *(["--max-batches", 1] if phase == "archive" else []),
    )
    if phase == "identity":
        cli("handoff", work)
        partial = cli("identity", work, "--batch-size", 1, "--max-batches", 1)
        assert not partial["complete"]
    with source.readonly(work / "target.sqlite3") as db:
        saved_maps = list(db.execute("SELECT * FROM id_mappings ORDER BY id"))
    result = cli("integrated", work, "--batch-size", 3)
    assert result["complete"]
    assert cli("verify-stored", work)["complete"]
    with source.readonly(work / "target.sqlite3") as db:
        for saved in saved_maps:
            assert tuple(saved) == tuple(
                db.execute(
                    "SELECT * FROM id_mappings WHERE id=?", (saved[0],)
                ).fetchone()
            )
    assert_exact_archive(database, work)
    unchanged(database, cache, before)


@pytest.mark.parametrize("phase", ["handoff", "identity-init"])
def test_guarded_integrated_recovers_spilled_upstream_receipt(tmp_path, phase):
    database, cache, work, before = prepared(tmp_path)
    cli("archive", work, "--batch-size", 2)
    if phase == "identity-init":
        cli("handoff", work)
    worker(
        work,
        "--action",
        phase,
        "--fault",
        "before_handoff_commit"
        if phase == "handoff"
        else "before_identity_init_commit",
        "--spill",
        "--hard-exit",
        expected=77,
        module="tests.support.conversion_worker"
        if phase == "handoff"
        else "tests.support.p3b_worker",
    )
    assert (work / "target.sqlite3-journal").is_file()
    # The immutable ownership read actually exposes the uncommitted receipt;
    # orchestration must route recovery through its upstream phase writer.
    with target.readonly_destination(work / "target.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM conversion_runs").fetchone()[0] == (
            2 if phase == "handoff" else 3
        )
    assert cli("integrated", work, "--batch-size", 3)["complete"]
    assert cli("verify-stored", work)["complete"]
    assert_exact_archive(database, work)
    unchanged(database, cache, before)
