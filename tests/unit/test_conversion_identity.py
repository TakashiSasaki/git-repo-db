"""Identity components supplement the guarded operational flow tests."""

import hashlib
import json
import sqlite3
import uuid

import pytest

from scripts.conversion import (
    archive,
    batch,
    engine,
    identity,
    identity_phase,
    phase,
    source,
    target,
)
from scripts.conversion.common import ROOT, ConversionError, canonical

STAMP = "2026-01-01T00:00:00.000001Z"
LAST = "2026-01-02T01:00:00.000002+01:00"


def make_identity_source(path, *, encoding="UTF-8", mutate=None):
    db = sqlite3.connect(path)
    db.execute(f"PRAGMA encoding='{encoding}'")
    for version, migration in enumerate(
        sorted((ROOT / "src/repo_catalog/resources/migrations").glob("*.sql")), 1
    ):
        db.executescript(migration.read_text())
        db.execute(
            "INSERT INTO schema_migrations VALUES(?,?,?)",
            (version, hashlib.sha256(migration.read_bytes()).hexdigest(), STAMP),
        )
        db.commit()
    db.execute("INSERT INTO catalog_meta VALUES(1,'synthetic-identity-source',0,2)")
    db.execute(
        "INSERT INTO service_instances VALUES('instance','github','example.invalid','https://example.invalid','https://example.invalid/api','{\"kept\": 1}',?)",
        (STAMP,),
    )
    for ident in ("source-a", "source-b"):
        db.execute(
            "INSERT INTO sources VALUES(?,'github',?,'{\"owner\": \"synthetic\"}','instance')",
            (ident, ident),
        )
    for ident, native in (("repo-a", "401"), ("repo-b", "402")):
        db.execute(
            "INSERT INTO repositories VALUES(?,'source-a','example.invalid',?,'same/name','https://example.invalid/shared.git','{\"exact\": 2}',NULL)",
            (ident, native),
        )
        db.execute(
            "INSERT INTO repository_bindings VALUES(?,'instance',?,'{\"native\": true}',?)",
            (ident, native, STAMP),
        )
        db.execute(
            "INSERT INTO repository_endpoints VALUES(?,?,'https://example.invalid/shared.git','https',NULL,1,'{\"endpoint\": 3}',?)",
            (f"endpoint-{ident}", ident, STAMP),
        )
        db.execute(
            "INSERT INTO repository_names VALUES(?,'same/name',?)", (ident, STAMP)
        )
        for discovery in ("source-a", "source-b"):
            db.execute(
                "INSERT INTO source_repositories VALUES(?,?,?,?)",
                (discovery, ident, STAMP, LAST),
            )
    if mutate:
        mutate(db)
    db.commit()
    db.close()


def workspace(tmp_path, *, map_repositories=True, encoding="UTF-8", mutate=None):
    original, destination = tmp_path / "original.sqlite3", tmp_path / "conversion"
    make_identity_source(original, encoding=encoding, mutate=mutate)
    engine.seal_input(original, destination)
    engine.convert(destination, batch_size=2, map_repositories=map_repositories)
    phase.handoff(destination)
    identity_phase.initialize(destination, batch_size=1)
    return original, destination


@pytest.mark.parametrize("maps", [False, True])
def test_identity_preserves_exact_graph_ids_times_and_p2_evidence(tmp_path, maps):
    original, destination = workspace(tmp_path, map_repositories=maps)
    before_source = original.read_bytes()
    with source.readonly(destination / "target.sqlite3") as db:
        before_archive = {
            name: batch.encode([tuple(r) for r in db.execute(f"SELECT * FROM {name}")])
            for name in ("legacy_records", "legacy_values")
        }
        parent_rows = [
            tuple(r)
            for r in db.execute(
                "SELECT * FROM conversion_runs WHERE parser_version!=?",
                (identity_phase.PROTOCOL_VERSION,),
            )
        ]
    first = identity_phase.convert(destination, batch_size=1)
    assert first["complete"]
    assert identity_phase.convert(destination, batch_size=1)["new_batches"] == 0
    assert identity_phase.verify(destination)["complete"]
    assert original.read_bytes() == before_source
    with source.readonly(destination / "target.sqlite3") as db:
        for name, rows in before_archive.items():
            assert rows == batch.encode(
                [tuple(r) for r in db.execute(f"SELECT * FROM {name}")]
            )
        assert parent_rows == [
            tuple(r)
            for r in db.execute(
                "SELECT * FROM conversion_runs WHERE parser_version!=?",
                (identity_phase.PROTOCOL_VERSION,),
            )
        ]
        assert [
            tuple(r)
            for r in db.execute(
                "SELECT id,name,preferred_endpoint_id,current_snapshot_id,metadata FROM repositories ORDER BY id"
            )
        ] == [
            (ident, "same/name", f"endpoint-{ident}", None, '{"exact": 2}')
            for ident in ("repo-a", "repo-b")
        ]
        assert [
            tuple(r)
            for r in db.execute(
                "SELECT source_id,repo_id,first_seen,last_seen FROM source_repositories ORDER BY source_id,repo_id"
            )
        ] == [
            (src, repo, STAMP, LAST)
            for src in ("source-a", "source-b")
            for repo in ("repo-a", "repo-b")
        ]
        bindings = [
            tuple(r)
            for r in db.execute(
                "SELECT id,repo_id,provider_repo_id,created_at FROM repository_bindings ORDER BY repo_id"
            )
        ]
        assert [(r[1], r[2], r[3]) for r in bindings] == [
            ("repo-a", "401", STAMP),
            ("repo-b", "402", STAMP),
        ]
        assert all(uuid.UUID(r[0]).version == 4 for r in bindings)
        assert (
            db.execute(
                "SELECT count(*) FROM validation_results WHERE run_id IN (SELECT id FROM conversion_runs WHERE parser_version=?)",
                (identity_phase.PROTOCOL_VERSION,),
            ).fetchone()[0]
            == 0
        )
        assert db.execute(
            "SELECT lifecycle,publication_seq FROM database_identity"
        ).fetchone()[:] == ("building", 0)


@pytest.mark.parametrize(
    "point",
    ["before_insert", "after_data", "after_mapping", "before_commit", "after_commit"],
)
def test_identity_atomic_batch_fault_recognizes_committed_maps(tmp_path, point):
    _, destination = workspace(tmp_path, map_repositories=False)

    def fault(actual, **context):
        if actual == point:
            raise ConversionError("SYNTHETIC_FAULT")

    with pytest.raises(ConversionError, match="SYNTHETIC_FAULT"):
        identity_phase.convert(destination, batch_size=1, fault=fault)
    with source.readonly(destination / "target.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM service_instances").fetchone()[0] == (
            1 if point == "after_commit" else 0
        )
    assert identity_phase.convert(destination, batch_size=1)["complete"]
    assert identity_phase.verify(destination)["complete"]


@pytest.mark.parametrize(
    "column,value", [("name", "altered"), ("metadata", '{"altered":1}')]
)
def test_zero_batch_p3b_cannot_hide_tampered_p2_representative(tmp_path, column, value):
    _, destination = workspace(tmp_path)
    db = target.connect(destination / "target.sqlite3")
    db.execute(f"UPDATE repositories SET {column}=? WHERE id='repo-a'", (value,))
    db.close()
    with pytest.raises(ConversionError, match="IDENTITY_SOURCE_MISMATCH"):
        identity_phase.verify(destination)


def test_coherent_domain_and_proof_tamper_fails_source_reconstruction(tmp_path):
    _, destination = workspace(tmp_path)
    identity_phase.convert(destination, batch_size=1)
    db = target.connect(destination / "target.sqlite3")
    db.execute(
        "UPDATE repositories SET name=? WHERE id='repo-a'",
        ("coherent-alteration",),
    )
    row = db.execute(
        "SELECT * FROM conversion_batches WHERE source_table='repositories' AND run_id IN (SELECT id FROM conversion_runs WHERE parser_version='p3b-identity/1') ORDER BY id LIMIT 1"
    ).fetchone()
    manifest = json.loads(row["output_manifest"])
    manifest["output"]["operations"][0]["row"][1] = "coherent-alteration"
    manifest["output_sha256"] = batch.proof_digest(manifest["output"])
    triggers = list(
        db.execute(
            "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name='conversion_batches'"
        )
    )
    for name, _ in triggers:
        db.execute(f'DROP TRIGGER "{name}"')
    db.execute(
        "UPDATE conversion_batches SET output_manifest=? WHERE id=?",
        (canonical(manifest), row["id"]),
    )
    for _, sql in triggers:
        db.execute(sql)
    db.close()
    with pytest.raises(ConversionError, match="IDENTITY_SOURCE_MISMATCH"):
        identity_phase.verify(destination)


def test_unattributed_p3a_diagnostic_is_rejected(tmp_path):
    _, destination = workspace(tmp_path)
    db = target.connect(destination / "target.sqlite3")
    parent = db.execute(
        "SELECT id FROM conversion_runs WHERE parser_version=?",
        (phase.PROTOCOL_VERSION,),
    ).fetchone()[0]
    db.execute(
        "INSERT INTO validation_results(run_id,invariant_id,code,severity,observed_at,details) VALUES(?,'I31','UNOWNED','info',?,'{}')",
        (parent, STAMP),
    )
    db.close()
    with pytest.raises(
        ConversionError,
        match="UNLEDGERED_OUTPUT|IDENTITY_UNLEDGERED_DIAGNOSTIC|SOURCE_DIAGNOSTIC_MISMATCH",
    ):
        identity_phase.verify(destination)


@pytest.mark.parametrize("encoding", ["UTF-16le", "UTF-16be"])
def test_identity_decodes_source_encoding_preserves_text_and_archive(
    tmp_path, encoding
):
    original, destination = workspace(
        tmp_path, map_repositories=False, encoding=encoding
    )
    before = original.read_bytes()
    assert identity_phase.convert(destination, batch_size=1)["complete"]
    assert identity_phase.verify(destination)["complete"]
    assert original.read_bytes() == before
    with source.readonly(destination / "target.sqlite3") as db:
        assert db.execute(
            "SELECT name,metadata FROM repositories WHERE id='repo-a'"
        ).fetchone()[:] == ("same/name", '{"exact": 2}')
        with source.readonly(destination / "source.sqlite3") as src:
            record = next(archive.rows(src, "repositories"))
            saved = db.execute(
                "SELECT value_bytes FROM legacy_values WHERE column_name='name' AND record_id=(SELECT id FROM legacy_records WHERE source_table='repositories' AND source_key=?)",
                (record.key,),
            ).fetchone()[0]
            assert saved == "same/name".encode(encoding)


def test_contract_rejects_recipe_drift_before_writes():
    _, spec, _ = target.resources()
    identity.validate_contract(spec)
    spec["p3b_identity"]["preferences"] = "select most convenient URL"
    with pytest.raises(ConversionError, match="INVALID_P3B_IDENTITY_CONTRACT"):
        identity.validate_contract(spec)


@pytest.mark.parametrize("offset", ["+00:60", "+00:99", "+24:00", "-23:60"])
def test_identity_timestamp_does_not_normalize_malformed_offsets(offset):
    with pytest.raises(ValueError):
        identity.instant("2025-01-01T00:00:00" + offset)


def test_identity_unsupported_sqlite_bounds_archived_diagnosed_without_sql_crash(
    tmp_path,
):
    def mutate(db):
        db.execute(
            "UPDATE source_repositories SET first_seen='2025-01-01T00:00:00+15:00'"
        )

    _, destination = workspace(tmp_path, mutate=mutate)
    assert identity_phase.convert(destination, batch_size=1)["complete"]
    with source.readonly(destination / "target.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM source_repositories").fetchone()[0] == 0
        assert (
            db.execute(
                "SELECT count(*) FROM validation_results WHERE code='IDENTITY_INVALID_TIME'"
            ).fetchone()[0]
            == 4
        )
        assert (
            db.execute(
                "SELECT count(*) FROM legacy_values WHERE column_name='first_seen' AND value_bytes=?",
                (b"2025-01-01T00:00:00+15:00",),
            ).fetchone()[0]
            == 4
        )


def test_reviewed_baseline_contract_productions_cannot_disagree_with_recipes():
    _, spec, _ = target.resources()
    production = next(p for p in spec["productions"] if p["id"] == "service_instances")
    production["outputs"]["name"]["inputs"] = ["source.service_instances.kind"]
    with pytest.raises(ConversionError, match="INVALID_P3B_IDENTITY_CONTRACT"):
        identity.validate_contract(spec)


def test_local_configured_binding_keeps_native_and_source_id_assertions_separate(
    tmp_path,
):
    def mutate(db):
        db.execute(
            "INSERT INTO service_instances VALUES('git-instance','git','git-local',NULL,NULL,'{}',?)",
            (STAMP,),
        )
        db.execute(
            "INSERT INTO sources VALUES('local-source','local-git','local-name','{\"repo_id\":\"local-repo\",\"provider_repo_id\":\"native-id\"}','git-instance')"
        )
        db.execute(
            "INSERT INTO repositories VALUES('local-repo','local-source','local','local-source','local-name','/original/mount/repo.git','{}',NULL)"
        )
        db.execute(
            "INSERT INTO repository_bindings VALUES('local-repo','git-instance','native-id','{}',?)",
            (STAMP,),
        )
        db.execute(
            "INSERT INTO repository_endpoints VALUES('local-endpoint','local-repo','/original/mount/repo.git','file',NULL,1,'{}',?)",
            (STAMP,),
        )
        db.execute(
            "INSERT INTO source_repositories VALUES('local-source','local-repo',?,?)",
            (STAMP, LAST),
        )

    _, destination = workspace(tmp_path, mutate=mutate)
    result = identity_phase.convert(destination, batch_size=1)
    assert result["complete"] and result["identity_ready"]
    with source.readonly(destination / "target.sqlite3") as db:
        assert (
            db.execute(
                "SELECT provider_repo_id FROM repository_bindings WHERE repo_id='local-repo'"
            ).fetchone()[0]
            == "native-id"
        )
        assert (
            db.execute(
                "SELECT url FROM repository_endpoints WHERE id='local-endpoint'"
            ).fetchone()[0]
            == "/original/mount/repo.git"
        )


def test_nullable_native_metadata_urls_and_labels_are_preserved(tmp_path):
    def mutate(db):
        db.execute(
            "UPDATE repository_bindings SET provider_repo_id=NULL WHERE repo_id='repo-a'"
        )
        db.execute("UPDATE service_instances SET web_base_url=NULL,api_base_url=NULL")

    _, destination = workspace(tmp_path, mutate=mutate)
    assert identity_phase.convert(destination, batch_size=1)["complete"]
    with source.readonly(destination / "target.sqlite3") as db:
        assert (
            db.execute(
                "SELECT provider_repo_id FROM repository_bindings WHERE repo_id='repo-a'"
            ).fetchone()[0]
            is None
        )
        assert db.execute(
            "SELECT web_base_url,api_base_url FROM service_instances"
        ).fetchone()[:] == (None, None)
        codes = {
            row[0]
            for row in db.execute(
                "SELECT code FROM validation_results WHERE run_id IN (SELECT id FROM conversion_runs WHERE parser_version='p3b-identity/1')"
            )
        }
        assert "IDENTITY_LEGACY_NATIVE_UNRESOLVED" in codes
        assert "IDENTITY_LEGACY_HOST_UNRESOLVED" in codes
        assert (
            db.execute(
                "SELECT count(*) FROM validation_results WHERE severity='blocking'"
            ).fetchone()[0]
            == 0
        )
