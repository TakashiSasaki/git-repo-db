"""R230-01: post-backup metadata bodies are typed candidates, not generic rows."""

import base64
import json
from contextlib import closing
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
from repo_catalog.adapters.sqlite.core_recovery import stop_catalog
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.adapters.sqlite.recovery import SQLiteRecoveryAdapter
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.p1_core import OID
from repo_catalog.domain.recovery import BackupScope
from tests.integration.p7.conftest import (
    admit_context_text,
    make_commit,
    make_tag,
    make_tree,
)


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("paired", [False, True], ids=["core", "paired"])
def test_post_backup_metadata_copy_recovery_preserves_types_and_source(
    tmp_path, fmt, paired
):
    source = tmp_path / "source"
    source.mkdir()
    repository, instance = str(uuid4()), str(uuid4())
    for role in ("core", "context") if paired else ("core",):
        initialize(source / (role + ".sqlite3"), role, repository, instance)
    adapter = SQLiteRecoveryAdapter()
    backup = tmp_path / "baseline"
    adapter.create_consistent_backup(
        source, backup, BackupScope.PAIRED if paired else BackupScope.GIT_ONLY
    )
    width = 40 if fmt == "sha1" else 64
    nominal = OID(fmt, "a" * width)
    tree = make_tree(fmt, [(b"100644", b"not-archived", nominal.object_oid)])
    commit = make_commit(fmt, tree.object_oid.object_oid, [], message="post-backup\n")
    tag = make_tag(fmt, commit.object_oid.object_oid)
    originals = {obj.object_oid: (obj, str(uuid4())) for obj in (tree, commit, tag)}
    bad_copy = str(uuid4())
    with closing(GitCore(source / "core.sqlite3")) as core:
        core.admit_object(nominal)
        for obj, copy in originals.values():
            core.admit_metadata(obj, copy, UnlimitedWorkBudget())
        core.admit_metadata(tree, bad_copy, UnlimitedWorkBudget())
    text = "post-backup Context document"
    if paired:
        with closing(connect(source / "context.sqlite3", "context")) as context:
            admit_context_text(context, text)
    # Synthetic damage after real admission; keep the WAL live during extraction.
    with closing(connect(source / "core.sqlite3", "core")) as db:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_retained_metadata_update'"
        ).fetchone()[0]
        db.execute("DROP TRIGGER p1_immutable_retained_metadata_update")
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute(
            "UPDATE retained_metadata SET body=zeroblob(size) WHERE physical_copy_uuidv4=?",
            (bad_copy,),
        )
        db.execute(trigger)
        db.commit()
        stop_catalog(source, "synthetic damaged metadata copy")
        preserved = {
            p.name: p.read_bytes() for p in source.glob("*.sqlite3*") if p.is_file()
        }
        assert "core.sqlite3-wal" in preserved
        salvage = tmp_path / "metadata.jsonl"
        extracted = adapter.extract_salvage(
            source,
            salvage,
            scope=BackupScope.PAIRED if paired else BackupScope.GIT_ONLY,
        )
        assert extracted.partial
        assert {
            p.name: p.read_bytes() for p in source.glob("*.sqlite3*") if p.is_file()
        } == preserved
    rows = [json.loads(line) for line in salvage.read_text().splitlines()]
    retained = [
        row
        for row in rows
        if row["candidate_type"] == "retained_body"
        and row["extraction_status"] == "clean"
    ]
    assert {row["payload"]["physical_copy_uuidv4"] for row in retained} == {
        copy for _, copy in originals.values()
    }
    for row in retained:
        payload = row["payload"]
        obj, copy = originals[OID(payload["object_format"], payload["object_oid"])]
        assert payload["native_type"] == obj.native_type
        assert base64.b64decode(payload["body_base64"]) == obj.body
        assert payload["physical_copy_uuidv4"] == copy
    assert any(
        row["candidate_type"] == "git_metadata"
        and row["extraction_provenance"]["table"] == "git_objects"
        for row in rows
    )
    assert sum(row["candidate_type"] == "context_document" for row in rows) == int(
        paired
    )
    bad = next(
        row for row in rows if row["payload"].get("physical_copy_uuidv4") == bad_copy
    )
    assert bad["extraction_status"] == "partial" and "body_base64" not in bad["payload"]
    fresh = tmp_path / "fresh"
    adapter.restore_backup(backup, fresh, repository)
    merged = adapter.merge_salvage(fresh, salvage)
    assert merged.rejected_units == merged.deferred_units == 0, merged.rejections
    assert (
        merged.admitted_units + merged.replayed_units + merged.observation_units
        == merged.candidates_processed
    )
    service = ProductionQueryService(fresh)
    for obj, _ in originals.values():
        read = service.read_metadata_bytes(obj.object_oid)
        assert read.available and read.verified
        assert service.get_git_object(obj.object_oid).native_type == obj.native_type
        assert read.body_bytes == obj.body
    with closing(GitCore(fresh / "core.sqlite3")) as core:
        assert {
            row[0]
            for row in core.sql("SELECT physical_copy_uuidv4 FROM retained_metadata")
        } == {copy for _, copy in originals.values()}
        assert core.sql(
            "SELECT 1 FROM git_objects WHERE object_format=? AND object_oid=?",
            nominal.key,
        )
    if paired:
        with closing(connect(fresh / "context.sqlite3", "context")) as context:
            assert context.execute(
                "SELECT 1 FROM text_bodies WHERE text_value=?", (text,)
            ).fetchone()
    assert not (fresh / "p1-recovery-stop.json").exists()
