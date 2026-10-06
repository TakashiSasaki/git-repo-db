"""Authentic reviewed P3A -> guarded source-proven P3B identity flows."""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.conversion import archive, source, target
from scripts.conversion.common import ROOT
from scripts.schema_contract import tagged_key
from tests.support.p3b_fixture import (
    IDS,
    LATER,
    REVIEWED_P3A,
    SHARED_NAME,
    SHARED_URL,
    STAMP,
    assert_exact_archive,
    authentic_p3a,
    cli,
    export_reviewed,
    make_identity_source,
    parent_snapshot,
)


def worker(workspace, *arguments, expected=0):
    env = dict(os.environ)
    if sqlite3.sqlite_version_info < (3, 46, 1):
        env["TEST_SQLITE_MINIMUM"] = "3.46.1"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.support.p3b_worker",
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
    if expected == 77:
        return None
    return json.loads(result.stdout if expected == 0 else result.stderr)


def identity_cli(action, workspace, *arguments, expected=0):
    options = () if action == "verify-identity" else ("--batch-size", 2)
    return cli(action, workspace, *options, *arguments, expected=expected)


@pytest.fixture(scope="session")
def reviewed_root(tmp_path_factory):
    return export_reviewed(tmp_path_factory.mktemp("p3b-reviewed") / "source")


@pytest.fixture
def prepared(tmp_path, reviewed_root):
    database, cache = make_identity_source(tmp_path / "source")
    workspace = tmp_path / "conversion"
    before = source.file_fingerprint(database), source.cache_inventory([cache])
    authentic_p3a(reviewed_root, database, cache, workspace)
    return database, cache, workspace, before, parent_snapshot(workspace)


def assert_inputs_unchanged(database, cache, before):
    assert before == (
        source.file_fingerprint(database),
        source.cache_inventory([cache]),
    )


def assert_graph(database, workspace):
    """Compare identity bytes, keys, edges, bounds and nullable assertions."""
    with (
        source.readonly(database) as src,
        source.readonly(workspace / "target.sqlite3") as db,
    ):
        assert [
            tuple(row)
            for row in db.execute("SELECT * FROM service_instances ORDER BY id")
        ] == [
            tuple(row)
            for row in src.execute("SELECT * FROM service_instances ORDER BY id")
        ]
        assert [
            tuple(row) for row in db.execute("SELECT * FROM sources ORDER BY id")
        ] == [
            (
                row[0],
                row[4],
                {"github": "github_inventory", "local-git": "manual_git"}[row[1]],
                row[2],
                row[3],
            )
            for row in src.execute("SELECT * FROM sources ORDER BY id")
        ]
        preferred = {
            IDS["repo"]: IDS["endpoint"],
            IDS["mirror"]: IDS["mirror_endpoint"],
        }
        assert [
            tuple(row) for row in db.execute("SELECT * FROM repositories ORDER BY id")
        ] == [
            (row[0], row[4], preferred.get(row[0]), None, row[6])
            for row in src.execute("SELECT * FROM repositories ORDER BY id")
        ]
        assert [
            tuple(row)
            for row in db.execute("SELECT * FROM repository_endpoints ORDER BY id")
        ] == [
            tuple(row[:5]) + tuple(row[6:])
            for row in src.execute("SELECT * FROM repository_endpoints ORDER BY id")
        ]
        assert [
            tuple(row)
            for row in db.execute(
                "SELECT repo_id,instance_id,provider_repo_id,metadata,created_at FROM repository_bindings ORDER BY repo_id,instance_id"
            )
        ] == [
            tuple(row)
            for row in src.execute(
                "SELECT * FROM repository_bindings ORDER BY repo_id,instance_id"
            )
        ]
        assert [
            tuple(row)
            for row in db.execute(
                "SELECT * FROM source_repositories ORDER BY source_id,repo_id"
            )
        ] == [
            tuple(row)
            for row in src.execute(
                "SELECT * FROM source_repositories ORDER BY source_id,repo_id"
            )
        ]
        names = {
            tuple(row) for row in db.execute("SELECT * FROM repository_name_assertions")
        }
        assert names == {
            tuple(row) for row in src.execute("SELECT * FROM repository_names")
        }
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert tuple(
            db.execute(
                "SELECT lifecycle,publication_seq FROM database_identity"
            ).fetchone()
        ) == ("building", 0)
        assert (
            db.execute(
                "SELECT 1 FROM repositories WHERE current_snapshot_id IS NOT NULL"
            ).fetchone()
            is None
        )
        assert (
            db.execute(
                "SELECT count(*) FROM repositories WHERE name=?", (SHARED_NAME,)
            ).fetchone()[0]
            == 2
        )
        assert (
            db.execute(
                "SELECT count(*) FROM repository_endpoints WHERE url=?", (SHARED_URL,)
            ).fetchone()[0]
            == 2
        )
        assert {row[0] for row in db.execute("SELECT id FROM repositories")} == {
            IDS[name] for name in ("repo", "mirror", "local_repo")
        }
        assert (
            db.execute(
                "SELECT provider_repo_id FROM repository_bindings WHERE repo_id=?",
                (IDS["local_repo"],),
            ).fetchone()[0]
            is None
        )
        assert tuple(
            db.execute(
                "SELECT first_seen,last_seen FROM source_repositories WHERE source_id=? AND repo_id=?",
                (IDS["source"], IDS["repo"]),
            ).fetchone()
        ) == (STAMP, LATER)
        assert all(
            row[0] not in {STAMP, LATER}
            for row in db.execute("SELECT started_at FROM conversion_runs")
        )
        # Deferred Git facts remain in their exact archive, with neither shared
        # OID-based identity merging nor premature runtime publication.
        assert db.execute("SELECT count(*) FROM git_objects").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 0
        for record in archive.rows(src, "repository_bindings"):
            archived = db.execute(
                "SELECT id FROM legacy_records WHERE source_table=? AND source_key=?",
                (record.table, record.key),
            ).fetchone()[0]
            mapped = db.execute(
                "SELECT target_key FROM id_mappings WHERE record_id=? AND target_table='repository_bindings' AND relation='identity'",
                (archived,),
            ).fetchall()
            assert len(mapped) == 1
            decoded = archive.decode_key(mapped[0][0])
            assert len(decoded) == 1 and decoded[0][0] == "text"
            binding = db.execute(
                "SELECT repo_id,instance_id FROM repository_bindings WHERE id=?",
                (decoded[0][1].decode(),),
            ).fetchone()
            assert tuple(binding) == tuple(
                raw.decode() for _, raw in archive.decode_key(record.key)
            )


@pytest.mark.parametrize("representative", [False, True])
@pytest.mark.parametrize("derived", [False, True])
def test_authentic_p3a_identity_graph_pause_resume_preserves_exact_evidence(
    tmp_path, reviewed_root, representative, derived
):
    database, cache = make_identity_source(tmp_path / "source", derived=derived)
    workspace = tmp_path / "conversion"
    before = source.file_fingerprint(database), source.cache_inventory([cache])
    authentic_p3a(
        reviewed_root, database, cache, workspace, representative=representative
    )
    parents = parent_snapshot(workspace)
    init = identity_cli("identity-init", workspace)
    assert init["phase"] == "p3b-identity/1" and init["new_phase"]
    assert init["lifecycle"] == "building" and not init["activation_permitted"]
    assert identity_cli("identity-init", workspace) == {**init, "new_phase": False}
    with source.readonly(workspace / "target.sqlite3") as db:
        receipt = json.loads(
            db.execute(
                "SELECT manifest FROM conversion_runs WHERE parser_version='p3b-identity/1'"
            ).fetchone()[0]
        )
        assert receipt["parent"]["reviewed_predecessor_revision"] == REVIEWED_P3A
        assert db.execute("SELECT count(*) FROM repository_bindings").fetchone()[0] == 0
        assert (
            db.execute("SELECT count(*) FROM repository_endpoints").fetchone()[0] == 0
        )
        assert db.execute("SELECT count(*) FROM repositories").fetchone()[0] == (
            3 if representative else 0
        )
    paused = identity_cli("identity", workspace, "--max-batches", 1)
    assert paused["new_batches"] == 1 and not paused["complete"]
    finished = identity_cli("identity", workspace)
    assert finished["complete"] and not finished["activation_permitted"]
    assert finished["transition_id"] == init["transition_id"]
    assert identity_cli("verify-identity", workspace) == {
        **finished,
        "new_phase": False,
        "new_batches": 0,
    }
    assert identity_cli("identity", workspace) == {
        **finished,
        "new_phase": False,
        "new_batches": 0,
    }
    assert parent_snapshot(workspace) == parents
    assert_graph(database, workspace)
    assert_exact_archive(database, workspace)
    assert_inputs_unchanged(database, cache, before)
    with source.readonly(workspace / "target.sqlite3") as db:
        all_rows = {
            name: [
                tuple(row) for row in db.execute(f"SELECT * FROM {name} ORDER BY 1,2")
            ]
            for name in (
                "repository_bindings",
                "id_mappings",
                "validation_results",
                "conversion_batches",
                "conversion_runs",
            )
        }
    identity_cli("identity", workspace)
    with source.readonly(workspace / "target.sqlite3") as db:
        assert all_rows == {
            name: [
                tuple(row) for row in db.execute(f"SELECT * FROM {name} ORDER BY 1,2")
            ]
            for name in all_rows
        }


@pytest.mark.parametrize(
    "probe", ["source-write", "copy-write", "cache-write", "network", "child"]
)
def test_p3b_fresh_worker_enforces_input_and_acquisition_guards(prepared, probe):
    database, cache, workspace, before, parents = prepared
    assert worker(workspace, "--probe", probe)["denied"] == probe
    assert parent_snapshot(workspace) == parents
    assert_inputs_unchanged(database, cache, before)


def test_competing_writer_and_old_phase_write_refusal_preserve_all_evidence(prepared):
    database, cache, workspace, before, parents = prepared
    target_before = source.file_fingerprint(workspace / "target.sqlite3")
    with target.writer_lock(workspace):
        assert (
            worker(workspace, "--action", "identity-init", expected=2)["code"]
            == "CONVERTER_ALREADY_RUNNING"
        )
    assert source.file_fingerprint(workspace / "target.sqlite3") == target_before
    identity_cli("identity", workspace)
    for action in ("archive", "handoff"):
        target_before = source.file_fingerprint(workspace / "target.sqlite3")
        assert cli(action, workspace, expected=2)["code"] == "PHASE_OWNERSHIP_MISMATCH"
        assert source.file_fingerprint(workspace / "target.sqlite3") == target_before
    assert parent_snapshot(workspace) == parents
    assert_inputs_unchanged(database, cache, before)


@pytest.mark.parametrize(
    "point", ["before_identity_init_commit", "after_identity_init_commit"]
)
@pytest.mark.parametrize("hard_exit", [False, True])
def test_owner_commit_interruption_and_restart(prepared, point, hard_exit):
    database, cache, workspace, before, parents = prepared
    args = ["--action", "identity-init", "--fault", point]
    if hard_exit:
        args.append("--hard-exit")
    worker(workspace, *args, expected=77 if hard_exit else 2)
    receipt = identity_cli("identity-init", workspace)
    assert receipt["new_phase"] == (point == "before_identity_init_commit")
    finished = identity_cli("identity", workspace)
    assert finished["complete"]
    assert parent_snapshot(workspace) == parents
    assert_graph(database, workspace)
    assert_inputs_unchanged(database, cache, before)


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
@pytest.mark.parametrize("alias", ["symlink", "hardlink"])
def test_identity_sidecar_alias_is_rejected_before_sqlite_open(prepared, suffix, alias):
    database, cache, workspace, before, parents = prepared
    victim = workspace / "synthetic-sidecar-original"
    victim.write_bytes(b"private synthetic sidecar bytes")
    sidecar = Path(str(workspace / "target.sqlite3") + suffix)
    if alias == "symlink":
        sidecar.symlink_to(victim)
    else:
        os.link(victim, sidecar)
    target_before = source.file_fingerprint(workspace / "target.sqlite3")
    assert (
        identity_cli("identity-init", workspace, expected=2)["code"]
        == "TARGET_SIDECAR_ALIAS_UNSUPPORTED"
    )
    assert victim.read_bytes() == b"private synthetic sidecar bytes"
    assert source.file_fingerprint(workspace / "target.sqlite3") == target_before
    assert sidecar.exists()
    sidecar.unlink()
    assert parent_snapshot(workspace) == parents
    assert_inputs_unchanged(database, cache, before)


@pytest.mark.parametrize(
    "mutation,unsafe_table,unsafe_key",
    [
        ("UPDATE sources SET settings='{broken' WHERE id=?", "sources", IDS["source"]),
        (
            "UPDATE sources SET instance_id='missing-instance' WHERE id=?",
            "sources",
            IDS["source"],
        ),
        (
            "UPDATE sources SET kind='unknown-provider' WHERE id=?",
            "sources",
            IDS["source"],
        ),
        (
            "UPDATE repository_endpoints SET id='' WHERE id=?",
            "repository_endpoints",
            IDS["endpoint"],
        ),
        (
            "UPDATE repository_endpoints SET repo_id='missing-repo' WHERE id=?",
            "repository_endpoints",
            IDS["endpoint"],
        ),
        (
            "UPDATE service_instances SET metadata='{broken' WHERE id=?",
            "service_instances",
            IDS["instance"],
        ),
    ],
    ids=[
        "malformed-json",
        "missing-instance",
        "unknown-kind",
        "invalid-key",
        "missing-owner",
        "invalid-service",
    ],
)
def test_malformed_identity_rows_keep_archive_and_omit_unsafe_projection(
    tmp_path, reviewed_root, mutation, unsafe_table, unsafe_key
):
    database, cache = make_identity_source(tmp_path / "source")
    with sqlite3.connect(database) as db:
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute(mutation, (unsafe_key,))
    workspace = tmp_path / "conversion"
    before = source.file_fingerprint(database), source.cache_inventory([cache])
    authentic_p3a(reviewed_root, database, cache, workspace)
    parents = parent_snapshot(workspace)
    result = identity_cli("identity", workspace)
    assert result["complete"] and not result["activation_permitted"]
    assert identity_cli("verify-identity", workspace) == {
        **result,
        "new_phase": False,
        "new_batches": 0,
    }
    with source.readonly(workspace / "target.sqlite3") as db:
        assert (
            db.execute(
                f"SELECT 1 FROM {unsafe_table} WHERE id=?", (unsafe_key,)
            ).fetchone()
            is None
        )
        if unsafe_table == "repository_endpoints":
            assert (
                db.execute("SELECT 1 FROM repository_endpoints WHERE id=''").fetchone()
                is None
            )
        decisions = db.execute(
            "SELECT severity,details FROM validation_results WHERE run_id IN "
            "(SELECT id FROM conversion_runs WHERE parser_version='p3b-identity/1')"
        ).fetchall()
        assert any(row[0] == "blocking" for row in decisions)
        assert all(json.loads(row[1]).get("record_id") for row in decisions)
    assert parent_snapshot(workspace) == parents
    assert_exact_archive(database, workspace)
    assert_inputs_unchanged(database, cache, before)


@pytest.mark.parametrize(
    "bad_time",
    [
        "not-an-observation-time",
        "2027-01-01T00:00:00Z",
        "2025-01-02T03:04:05+00:60",
        "2025-01-02T03:04:05+00:99",
    ],
)
def test_invalid_or_reversed_membership_bounds_are_not_conversion_times(
    tmp_path, reviewed_root, bad_time
):
    database, cache = make_identity_source(tmp_path / "source")
    with sqlite3.connect(database) as db:
        db.execute(
            "UPDATE source_repositories SET first_seen=? WHERE source_id=? AND repo_id=?",
            (bad_time, IDS["source"], IDS["repo"]),
        )
    workspace = tmp_path / "conversion"
    before = source.file_fingerprint(database), source.cache_inventory([cache])
    authentic_p3a(reviewed_root, database, cache, workspace)
    parents = parent_snapshot(workspace)
    result = identity_cli("identity", workspace)
    assert result["complete"]
    with source.readonly(workspace / "target.sqlite3") as db:
        assert (
            db.execute(
                "SELECT 1 FROM source_repositories WHERE source_id=? AND repo_id=?",
                (IDS["source"], IDS["repo"]),
            ).fetchone()
            is None
        )
        assert (
            db.execute(
                "SELECT 1 FROM validation_results WHERE run_id=? AND severity='blocking'",
                (result["transition_id"],),
            ).fetchone()
            is not None
        )
    assert parent_snapshot(workspace) == parents
    assert_exact_archive(database, workspace)
    assert_inputs_unchanged(database, cache, before)


@pytest.mark.parametrize("missing_binding", [False, True])
def test_conflicting_legacy_native_assertion_does_not_fabricate_binding(
    tmp_path, reviewed_root, missing_binding
):
    database, cache = make_identity_source(tmp_path / "source")
    with sqlite3.connect(database) as db:
        if missing_binding:
            db.execute(
                "DELETE FROM repository_bindings WHERE repo_id=?", (IDS["repo"],)
            )
        else:
            db.execute(
                "UPDATE repositories SET provider_repo_id='401' WHERE id=?",
                (IDS["mirror"],),
            )
    workspace = tmp_path / "conversion"
    before = source.file_fingerprint(database), source.cache_inventory([cache])
    authentic_p3a(reviewed_root, database, cache, workspace)
    parents = parent_snapshot(workspace)
    result = identity_cli("identity", workspace)
    assert result["complete"]
    with source.readonly(workspace / "target.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM repositories").fetchone()[0] == 3
        bindings = {
            tuple(row)
            for row in db.execute(
                "SELECT repo_id,provider_repo_id FROM repository_bindings"
            )
        }
        if missing_binding:
            assert not any(repo == IDS["repo"] for repo, _ in bindings)
        else:
            assert (IDS["mirror"], "402") in bindings
            assert (IDS["mirror"], "401") not in bindings
        assert (
            db.execute(
                "SELECT 1 FROM validation_results WHERE run_id=? AND severity IN ('partial','blocking')",
                (result["transition_id"],),
            ).fetchone()
            is not None
        )
    assert parent_snapshot(workspace) == parents
    assert_exact_archive(database, workspace)
    assert_inputs_unchanged(database, cache, before)


@pytest.mark.parametrize("changed", ["source", "sealed-copy", "cache"])
def test_changed_input_refuses_identity_before_target_mutation(prepared, changed):
    database, cache, workspace, before, parents = prepared
    if changed == "cache":
        (cache / "synthetic-evidence").write_bytes(b"synthetic tampering")
    else:
        path = database if changed == "source" else workspace / "source.sqlite3"
        if changed == "sealed-copy":
            path.chmod(0o600)
        with sqlite3.connect(path) as db:
            db.execute("UPDATE sources SET name='changed evidence'")
    target_before = source.file_fingerprint(workspace / "target.sqlite3")
    result = identity_cli("identity-init", workspace, expected=2)
    assert (
        result["code"]
        == {
            "source": "SOURCE_REPLACED_OR_CHANGED",
            "sealed-copy": "SOURCE_FINGERPRINT_MISMATCH",
            "cache": "CACHE_FINGERPRINT_MISMATCH",
        }[changed]
    )
    assert source.file_fingerprint(workspace / "target.sqlite3") == target_before
    assert parent_snapshot(workspace) == parents


@pytest.mark.parametrize("point", ["before_commit", "after_commit"])
@pytest.mark.parametrize("hard_exit", [False, True])
def test_binding_batch_commit_fault_preserves_committed_allocations(
    prepared, point, hard_exit
):
    database, cache, workspace, before, parents = prepared
    identity_cli("identity-init", workspace)
    args = ["--fault", point, "--fault-table", "repository_bindings"]
    if hard_exit:
        args.append("--hard-exit")
    worker(workspace, *args, expected=77 if hard_exit else 2)
    with target.readonly_destination(workspace / "target.sqlite3") as db:
        committed = {
            tuple(row)
            for row in db.execute(
                "SELECT id,repo_id,instance_id,provider_repo_id FROM repository_bindings"
            )
        }
        assert len(committed) == (0 if point == "before_commit" else 2)
    finished = identity_cli("identity", workspace)
    assert finished["complete"]
    with source.readonly(workspace / "target.sqlite3") as db:
        assert committed <= {
            tuple(row)
            for row in db.execute(
                "SELECT id,repo_id,instance_id,provider_repo_id FROM repository_bindings"
            )
        }
        assert (
            db.execute(
                "SELECT count(*) FROM conversion_runs WHERE parser_version='p3b-identity/1'"
            ).fetchone()[0]
            == 1
        )
    assert identity_cli("verify-identity", workspace) == {
        **finished,
        "new_phase": False,
        "new_batches": 0,
    }
    assert parent_snapshot(workspace) == parents
    assert_graph(database, workspace)
    assert_exact_archive(database, workspace)
    assert_inputs_unchanged(database, cache, before)


@pytest.mark.parametrize("initialization", [False, True])
def test_real_hot_journal_recovery_restores_exact_parent_and_identity_prefix(
    prepared, initialization
):
    database, cache, workspace, before, parents = prepared
    if initialization:
        args = ["--action", "identity-init", "--fault", "before_identity_init_commit"]
    else:
        identity_cli("identity-init", workspace)
        args = ["--fault", "before_commit", "--fault-table", "repository_bindings"]
    worker(workspace, *args, "--spill", "--hard-exit", expected=77)
    journal = workspace / "target.sqlite3-journal"
    assert journal.stat().st_size > 512
    assert journal.read_bytes()[:8] == bytes.fromhex("d9d505f920a163d7")
    # A read-only command must leave the native recovery boundary untouched.
    target_before = source.file_fingerprint(workspace / "target.sqlite3")
    journal_before = source.file_fingerprint(journal)
    assert (
        identity_cli("verify-identity", workspace, expected=2)["code"]
        == "SOURCE_NOT_SEALED"
    )
    assert source.file_fingerprint(workspace / "target.sqlite3") == target_before
    assert source.file_fingerprint(journal) == journal_before
    result = identity_cli("identity", workspace)
    assert result["complete"]
    assert identity_cli("verify-identity", workspace) == {
        **result,
        "new_phase": False,
        "new_batches": 0,
    }
    assert parent_snapshot(workspace) == parents
    assert_graph(database, workspace)
    assert_exact_archive(database, workspace)
    assert_inputs_unchanged(database, cache, before)


@pytest.mark.parametrize("coherent_rehash", [False, True])
def test_domain_value_and_coherently_rehashed_proof_still_require_source_evidence(
    prepared, coherent_rehash
):
    from scripts.conversion import batch
    from scripts.conversion.common import canonical

    database, cache, workspace, before, parents = prepared
    identity_cli("identity", workspace)
    with sqlite3.connect(workspace / "target.sqlite3") as db:
        db.execute(
            "UPDATE repository_endpoints SET label='invented synthetic label' WHERE id=?",
            (IDS["endpoint"],),
        )
        if coherent_rehash:
            # Model corruption outside the converter, restoring the exact
            # target trigger before commit. A changed DDL would only exercise
            # schema refusal, not independent source-derived verification.
            trigger = db.execute(
                "SELECT sql FROM sqlite_schema WHERE name='conversion_batches_immutable'"
            ).fetchone()[0]
            db.execute("DROP TRIGGER conversion_batches_immutable")
            for saved in db.execute(
                "SELECT id,output_manifest FROM conversion_batches WHERE source_table='repository_endpoints'"
                " AND run_id IN (SELECT id FROM conversion_runs WHERE parser_version='p3b-identity/1')"
            ).fetchall():
                manifest = json.loads(saved[1])
                for operation in manifest["output"]["operations"]:
                    if operation["row"][0] == IDS["endpoint"]:
                        operation["row"][4] = "invented synthetic label"
                manifest["output_sha256"] = batch.proof_digest(manifest["output"])
                db.execute(
                    "UPDATE conversion_batches SET output_manifest=? WHERE id=?",
                    (canonical(manifest), saved[0]),
                )
            db.execute(trigger)
    target_before = source.file_fingerprint(workspace / "target.sqlite3")
    for action in ("verify-identity", "identity"):
        assert (
            identity_cli(action, workspace, expected=2)["code"]
            == "IDENTITY_SOURCE_MISMATCH"
        )
        assert source.file_fingerprint(workspace / "target.sqlite3") == target_before
    assert parent_snapshot(workspace) == parents
    assert_inputs_unchanged(database, cache, before)


def test_target_same_owner_pointer_and_immutable_identity_constraints(prepared):
    database, cache, workspace, before, parents = prepared
    identity_cli("identity", workspace)
    with target.connect(workspace / "target.sqlite3") as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "UPDATE repositories SET preferred_endpoint_id=? WHERE id=?",
            (IDS["mirror_endpoint"], IDS["repo"]),
        )
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            db.execute("COMMIT")
        db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="Immutable"):
            db.execute(
                "UPDATE repository_bindings SET repo_id=? WHERE repo_id=?",
                (IDS["mirror"], IDS["repo"]),
            )
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            db.execute(
                "INSERT INTO source_repositories VALUES('missing-source',?,?,?)",
                (IDS["repo"], STAMP, LATER),
            )
    assert_graph(database, workspace)
    assert parent_snapshot(workspace) == parents
    assert_inputs_unchanged(database, cache, before)


@pytest.mark.parametrize(
    "changed", ["receipt", "predecessor", "mapping", "archive", "ddl"]
)
def test_altered_predecessor_refused_before_owner_receipt_or_domain_write(
    prepared, changed
):
    from scripts.conversion.common import canonical

    database, cache, workspace, before, parents = prepared
    with sqlite3.connect(workspace / "target.sqlite3") as db:
        # Corruption is prepared in the test parent. Restore all exact trigger
        # definitions, so value/map/receipt tests do not merely fail a DDL check.
        triggers = list(
            db.execute("SELECT name,sql FROM sqlite_schema WHERE type='trigger'")
        )
        for name, _ in triggers:
            db.execute(f'DROP TRIGGER "{name}"')
        if changed in {"receipt", "predecessor"}:
            row = db.execute(
                "SELECT id,manifest FROM conversion_runs WHERE parser_version='p3a-handoff/1'"
            ).fetchone()
            manifest = json.loads(row[1])
            if changed == "predecessor":
                manifest["signatures"]["converter_sha256"] = "0" * 64
            else:
                manifest["write_ownership"]["normalized_writes"] = ["repositories"]
            db.execute(
                "UPDATE conversion_runs SET manifest=? WHERE id=?",
                (canonical(manifest), row[0]),
            )
        elif changed == "mapping":
            db.execute(
                "UPDATE id_mappings SET target_key=? WHERE id=(SELECT min(id) FROM id_mappings)",
                (tagged_key([("text", IDS["mirror"].encode())]),),
            )
        elif changed == "archive":
            db.execute(
                "UPDATE legacy_values SET value_bytes=x'74616d7065726564' WHERE record_id=(SELECT id FROM legacy_records WHERE source_table='sources' LIMIT 1) AND column_name='name'"
            )
        else:
            db.execute(
                "CREATE TABLE unowned_synthetic_domain(id TEXT PRIMARY KEY) STRICT"
            )
        for _, definition in triggers:
            db.execute(definition)
    target_before = source.file_fingerprint(workspace / "target.sqlite3")
    result = identity_cli("identity-init", workspace, expected=2)
    assert (
        result["code"]
        == {
            "receipt": "PHASE_RECEIPT_MISMATCH",
            "predecessor": "UNSUPPORTED_P3A_PREDECESSOR",
            "mapping": "COMMITTED_OUTPUT_MISMATCH",
            "archive": "COMMITTED_OUTPUT_MISMATCH",
            "ddl": "TARGET_SCHEMA_MISMATCH",
        }[changed]
    )
    assert source.file_fingerprint(workspace / "target.sqlite3") == target_before
    with source.readonly(workspace / "target.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM conversion_runs").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM repository_bindings").fetchone()[0] == 0
    assert_inputs_unchanged(database, cache, before)


@pytest.mark.parametrize(
    "changed",
    [
        "mapping-key",
        "mapping-relation",
        "mapping-reason",
        "batch-input",
        "output-digest",
        "source-decision",
    ],
)
def test_p3b_maps_and_batch_proofs_cannot_be_relabelled_after_commit(prepared, changed):
    from scripts.conversion import batch
    from scripts.conversion.common import canonical

    database, cache, workspace, before, parents = prepared
    result = identity_cli("identity", workspace)
    with sqlite3.connect(workspace / "target.sqlite3") as db:
        triggers = list(
            db.execute("SELECT name,sql FROM sqlite_schema WHERE type='trigger'")
        )
        for name, _ in triggers:
            db.execute(f'DROP TRIGGER "{name}"')
        if changed.startswith("mapping-"):
            mapping_id = db.execute(
                "SELECT id FROM id_mappings WHERE target_table='repository_bindings' ORDER BY id LIMIT 1"
            ).fetchone()[0]
            if changed == "mapping-key":
                db.execute(
                    "UPDATE id_mappings SET target_key=? WHERE id=?",
                    (tagged_key([("integer", 1)]), mapping_id),
                )
            elif changed == "mapping-relation":
                db.execute(
                    "UPDATE id_mappings SET relation='derived' WHERE id=?",
                    (mapping_id,),
                )
            else:
                db.execute(
                    "UPDATE id_mappings SET reason='unattributed synthetic allocation' WHERE id=?",
                    (mapping_id,),
                )
        else:
            saved = db.execute(
                "SELECT id,output_manifest FROM conversion_batches WHERE run_id=? ORDER BY id LIMIT 1",
                (result["transition_id"],),
            ).fetchone()
            if changed == "batch-input":
                db.execute(
                    "UPDATE conversion_batches SET input_sha256=? WHERE id=?",
                    (b"\0" * 32, saved[0]),
                )
            else:
                manifest = json.loads(saved[1])
                if changed == "output-digest":
                    manifest["output_sha256"] = "0" * 64
                else:
                    manifest["output"]["decisions"][0]["disposition"] = "archive_only"
                    manifest["output_sha256"] = batch.proof_digest(manifest["output"])
                db.execute(
                    "UPDATE conversion_batches SET output_manifest=? WHERE id=?",
                    (canonical(manifest), saved[0]),
                )
        for _, definition in triggers:
            db.execute(definition)
    target_before = source.file_fingerprint(workspace / "target.sqlite3")
    expected = {
        "mapping-key": "IDENTITY_MAPPING_MISMATCH",
        "mapping-relation": "IDENTITY_MAPPING_MISSING",
        "mapping-reason": "IDENTITY_MAPPING_MISMATCH",
        "batch-input": "IDENTITY_BATCH_PROOF_MISMATCH",
        "output-digest": "IDENTITY_BATCH_PROOF_MISMATCH",
        "source-decision": "IDENTITY_SOURCE_MISMATCH",
    }[changed]
    for action in ("verify-identity", "identity"):
        assert identity_cli(action, workspace, expected=2)["code"] == expected
        assert source.file_fingerprint(workspace / "target.sqlite3") == target_before
    assert parent_snapshot(workspace) == parents
    assert_inputs_unchanged(database, cache, before)


def test_grammar_valid_but_contradictory_contract_is_refused_before_owner_initialization(
    prepared,
):
    from scripts.conversion.common import DESIGN
    from scripts.schema_contract import validate

    database, cache, workspace, before, parents = prepared
    spec = json.loads((DESIGN / "conversion-contract.json").read_bytes())
    production = next(
        row for row in spec["productions"] if row["id"] == "service_instances"
    )
    production["outputs"]["name"]["inputs"] = ["source.service_instances.kind"]
    for column in spec["source_columns"]:
        if column["table"] == "service_instances":
            if column["column"] == "kind":
                column["outputs"].append(
                    {"production": "service_instances", "column": "name"}
                )
            elif column["column"] == "name":
                column["outputs"] = []
    validate(spec, (DESIGN / "target-schema.sql").read_text())
    contract = workspace / "synthetic-contradictory-contract.json"
    contract.write_text(json.dumps(spec))
    target_before = source.file_fingerprint(workspace / "target.sqlite3")
    assert (
        worker(
            workspace, "--action", "identity-init", "--contract", contract, expected=2
        )["code"]
        == "INVALID_P3B_IDENTITY_CONTRACT"
    )
    assert source.file_fingerprint(workspace / "target.sqlite3") == target_before
    assert parent_snapshot(workspace) == parents
    assert_inputs_unchanged(database, cache, before)


def test_legacy_native_and_host_assertions_remain_unknown_without_normalized_evidence(
    tmp_path, reviewed_root
):
    database, cache = make_identity_source(tmp_path / "source")
    with sqlite3.connect(database) as db:
        db.execute(
            "UPDATE repository_bindings SET provider_repo_id=NULL WHERE repo_id=?",
            (IDS["repo"],),
        )
        db.execute(
            "UPDATE service_instances SET web_base_url=NULL,api_base_url=NULL WHERE id=?",
            (IDS["instance"],),
        )
    workspace = tmp_path / "conversion"
    before = source.file_fingerprint(database), source.cache_inventory([cache])
    authentic_p3a(reviewed_root, database, cache, workspace)
    parents = parent_snapshot(workspace)
    result = identity_cli("identity", workspace)
    assert result["complete"] and not result["activation_permitted"]
    with source.readonly(workspace / "target.sqlite3") as db:
        assert (
            db.execute(
                "SELECT provider_repo_id FROM repository_bindings WHERE repo_id=?",
                (IDS["repo"],),
            ).fetchone()[0]
            is None
        )
        assert tuple(
            db.execute(
                "SELECT web_base_url,api_base_url FROM service_instances WHERE id=?",
                (IDS["instance"],),
            ).fetchone()
        ) == (None, None)
        codes = {
            row[0]
            for row in db.execute(
                "SELECT code FROM validation_results WHERE run_id=? AND severity='partial'",
                (result["transition_id"],),
            )
        }
        assert {
            "IDENTITY_LEGACY_NATIVE_UNRESOLVED",
            "IDENTITY_LEGACY_HOST_UNRESOLVED",
        } <= codes
    assert parent_snapshot(workspace) == parents
    assert_graph(database, workspace)
    assert_exact_archive(database, workspace)
    assert_inputs_unchanged(database, cache, before)
