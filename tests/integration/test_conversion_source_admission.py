import json
import os
import sqlite3
import subprocess
import sys

import pytest

from repo_catalog.adapters.sqlite import index
from repo_catalog.adapters.sqlite.store import Store
from scripts.conversion import admission, engine, source
from scripts.conversion.common import DESIGN, ConversionError, canonical
from tests.support.conversion_fixture import make_source
from tests.support.operational_source import make_operational_source


def evidence(database, cache):
    return source.file_fingerprint(database), source.cache_inventory([cache])


@pytest.mark.parametrize(
    ("kinds", "analyze", "partial"),
    [
        ((), False, False),
        (("code",), False, False),
        (("code", "pr", "commits"), False, False),
        (("code", "code"), False, False),
        ((), True, False),
        (("code", "pr"), True, False),
        (("code",), False, True),
        (("code",), True, True),
    ],
)
def test_real_application_layouts_are_admitted_and_sealed(
    tmp_path, kinds, analyze, partial
):
    database, cache = make_operational_source(
        tmp_path / "state",
        kinds=kinds,
        analyze=analyze,
        documents=450 if partial else 3,
        partial=partial,
    )
    before = evidence(database, cache)
    with source.readonly(database) as db:
        report = source.identify(db)
        expected_objects = [
            tuple(r)
            for r in db.execute(
                "SELECT type,name,tbl_name,rootpage,sql FROM sqlite_schema ORDER BY type,name"
            )
        ]
        assert expected_objects == [
            tuple(i[k] for k in ("type", "name", "tbl_name", "rootpage", "sql"))
            for i in report["source_inventory"]
        ]
        assert len(report["preservation_dispositions"]) == len(expected_objects)
        assert any(i["sql"] is None for i in report["source_inventory"])
    spec = json.loads((DESIGN / "conversion-contract.json").read_bytes())
    assert (
        report["core_schema_sha256"]
        == report["schema_sha256"]
        == spec["source_schema_sha256"]
    )
    assert report["accepted"] and not report["diagnostics"]
    if kinds:
        assert report["capabilities"]["fts5_contentless_trigram_case_sensitive"]
    else:
        assert not report["capabilities"]["fts_required"]
    dispositions = {d["object"]: d for d in report["preservation_dispositions"]}
    for obj in report["source_inventory"]:
        disposition = dispositions[obj["name"]]
        assert {c["name"] for c in obj.get("columns", [])} == {
            c["column"] for c in disposition["columns"]
        }
        if disposition["classification"] == "strict_v2_core" and obj["type"] == "table":
            assert disposition["preservation"] == "exact_typed_archive"
        else:
            assert disposition["preservation"] == "sealed_bytes_rebuild_excluded"
            assert disposition["rebuild_from"]
    if analyze:
        assert dispositions["sqlite_stat1"]["classification"] == "sqlite_statistics"
    if partial:
        assert report["derived_generations"][0]["state"] == "building"
        assert report["derived_generations"][0]["coverage"] == "incomplete"
        assert report["derived_generations"][0]["members"] == 200
    if kinds == ("code", "code"):
        assert [g["state"] for g in report["derived_generations"]] == [
            "removed",
            "ready",
        ]
    workspace = tmp_path / "conversion"
    sealed = engine.seal_input(database, workspace, [cache])
    assert source.verify_seal(workspace) == sealed
    assert (workspace / "source.sqlite3").read_bytes() == database.read_bytes()
    assert before == evidence(database, cache)


def test_retired_generation_is_proven_by_actual_rebuild(tmp_path):
    database, cache = make_operational_source(tmp_path / "state", kinds=("code",))
    with Store(database.parent) as store:
        cursor = store.execute("SELECT rowid FROM catalog_fts_1")
        cursor.fetchone()
        index.rebuild(store, "code")
        cursor.close()
    before = evidence(database, cache)
    with source.readonly(database) as db:
        report = source.identify(db)
    assert [g["state"] for g in report["derived_generations"]] == ["retired", "ready"]
    assert before == evidence(database, cache)


@pytest.mark.parametrize("state", ["ready", "unavailable"])
def test_stale_generation_preserves_fixed_scope_and_requests_rebuild(tmp_path, state):
    database, cache = make_operational_source(tmp_path / "state", kinds=("code",))
    with sqlite3.connect(database) as db:
        db.execute("UPDATE index_generations SET state=?", (state,))
        db.execute(
            "INSERT INTO search_documents(kind,source_key,body) VALUES('code','new','later original')"
        )
    before = evidence(database, cache)
    with source.readonly(database) as db:
        report = source.identify(db)
    assert report["derived_generations"][0]["stale"]
    assert report["derived_generations"][0]["coverage"] == "complete"
    assert report["derived_generations"][0]["rebuild_from"] == "search_documents"
    assert before == evidence(database, cache)


def test_ready_incomplete_and_unavailable_missing_states_are_explicit(tmp_path):
    database, cache = make_operational_source(
        tmp_path / "state", kinds=("code",), documents=450, partial=True
    )
    with sqlite3.connect(database) as db:
        db.execute("UPDATE index_generations SET state='ready'")
    with source.readonly(database) as db:
        report = source.identify(db)
    assert report["derived_generations"][0]["coverage"] == "incomplete"
    with sqlite3.connect(database) as db:
        db.execute("DROP TABLE catalog_fts_1")
        db.execute("UPDATE index_generations SET state='unavailable'")
    before = evidence(database, cache)
    with source.readonly(database) as db:
        report = source.identify(db)
    assert report["derived_generations"][0]["coverage"] == "excluded_missing"
    assert before == evidence(database, cache)


BAD_LAYOUTS = [
    "user_table",
    "lookalike",
    "view",
    "trigger",
    "index",
    "core_column",
    "wrong_options",
    "wrong_columns",
    "orphan_fts",
    "orphan_shadow",
    "missing_shadow",
    "conflicting_registry",
    "bad_membership",
    "extra_fts_row",
    "missing_generation",
    "removed_present",
    "stat_reference",
    "stat_lookalike",
    "internal_lookalike",
    "unknown_virtual_module",
]


def mutate(db, case):
    if case == "user_table":
        db.execute(
            "CREATE TABLE arbitrary_user_data(id INTEGER PRIMARY KEY, body BLOB)"
        )
    elif case == "lookalike":
        db.execute("CREATE TABLE catalog_fts_untrusted(id INTEGER PRIMARY KEY)")
    elif case == "view":
        db.execute("CREATE VIEW custom_view AS SELECT body FROM search_documents")
    elif case == "trigger":
        db.execute(
            "CREATE TRIGGER custom_trigger AFTER INSERT ON search_documents BEGIN SELECT 1; END"
        )
    elif case == "index":
        db.execute("CREATE INDEX custom_index ON search_documents(body)")
    elif case == "core_column":
        db.execute("ALTER TABLE contents ADD COLUMN custom_value TEXT")
    elif case in {"wrong_options", "wrong_columns"}:
        db.execute("DROP TABLE catalog_fts_1")
        arguments = (
            "body,content=''"
            if case == "wrong_options"
            else "body,extra, tokenize='trigram case_sensitive 1',content='',detail=full"
        )
        db.execute(f"CREATE VIRTUAL TABLE catalog_fts_1 USING fts5({arguments})")
    elif case == "orphan_fts":
        db.execute("DELETE FROM index_membership")
        db.execute("DELETE FROM index_generations")
    elif case == "orphan_shadow":
        db.execute("DROP TABLE catalog_fts_1")
        db.execute(
            "CREATE TABLE catalog_fts_2_data(id INTEGER PRIMARY KEY, block BLOB)"
        )
    elif case == "missing_shadow":
        db.execute("DROP TABLE catalog_fts_1_idx")
    elif case == "conflicting_registry":
        db.execute("UPDATE index_generations SET id=9")
    elif case == "bad_membership":
        db.execute("UPDATE index_membership SET input_version='forged'")
    elif case == "extra_fts_row":
        db.execute(
            "INSERT INTO catalog_fts_1(rowid,body) VALUES(900,'unrelated user data')"
        )
    elif case == "missing_generation":
        db.execute("DROP TABLE catalog_fts_1")
    elif case == "removed_present":
        db.execute("UPDATE index_generations SET state='removed'")
    elif case == "stat_reference":
        db.execute("ANALYZE")
        db.execute("UPDATE sqlite_stat1 SET tbl='unrelated_table'")
    elif case in {"stat_lookalike", "internal_lookalike", "unknown_virtual_module"}:
        # Fixture-only corrupt/schema crafting, never performed by admission.
        if case == "stat_lookalike":
            db.execute("ANALYZE")
            db.execute("PRAGMA writable_schema=ON")
            db.execute(
                "UPDATE sqlite_schema SET sql='CREATE TABLE sqlite_stat1(tbl,idx,stat,unexpected)' WHERE name='sqlite_stat1'"
            )
        elif case == "internal_lookalike":
            db.execute("CREATE TABLE crafted_internal(x)")
            db.execute("PRAGMA writable_schema=ON")
            db.execute(
                "UPDATE sqlite_schema SET name='sqlite_untrusted',tbl_name='sqlite_untrusted',sql='CREATE TABLE sqlite_untrusted(x)' WHERE name='crafted_internal'"
            )
        else:
            db.execute("PRAGMA writable_schema=ON")
            db.execute(
                "UPDATE sqlite_schema SET sql='CREATE VIRTUAL TABLE catalog_fts_1 USING unsupported_module(body)' WHERE name='catalog_fts_1'"
            )


@pytest.mark.parametrize("case", BAD_LAYOUTS)
def test_unsupported_objects_fail_closed_with_complete_dispositions(tmp_path, case):
    database, cache = make_operational_source(tmp_path / "state", kinds=("code",))
    with sqlite3.connect(database) as db:
        mutate(db, case)
    before = evidence(database, cache)
    with source.readonly(database) as db:
        report = admission.classify(db)
        with pytest.raises(admission.SourceAdmissionError) as error:
            source.identify(db)
    assert not report["accepted"] and report["diagnostics"]
    assert error.value.report == report
    assert len(report["source_inventory"]) == len(report["preservation_dispositions"])
    assert (
        any(
            d["preservation"] == "blocking_unsupported"
            for d in report["preservation_dispositions"]
        )
        or case == "missing_generation"
    )
    assert before == evidence(database, cache)
    workspace = tmp_path / "conversion"
    with pytest.raises(admission.SourceAdmissionError):
        engine.seal_input(database, workspace, [cache])
    assert not (workspace / "source.sqlite3").exists()
    assert before == evidence(database, cache)


def test_readonly_admission_does_not_run_fts_write_checks(tmp_path):
    database, cache = make_operational_source(
        tmp_path / "state", kinds=("code",), analyze=True
    )
    before = evidence(database, cache)
    with source.readonly(database) as db:
        executed = []
        db.set_trace_callback(executed.append)
        source.identify(db)
        for sql in (
            "INSERT INTO catalog_fts_1(catalog_fts_1) VALUES('integrity-check')",
            "INSERT INTO catalog_fts_1(catalog_fts_1) VALUES('rebuild')",
            "ANALYZE",
        ):
            with pytest.raises(sqlite3.Error):
                db.execute(sql)
    assert all(
        not sql.lstrip().upper().startswith(("INSERT", "CREATE", "DROP", "ANALYZE"))
        for sql in executed
    )
    assert before == evidence(database, cache)


def test_unsupported_runtime_capability_blocks_fts_without_prefix_allowlist(
    tmp_path, monkeypatch
):
    database, cache = make_operational_source(tmp_path / "state", kinds=("code",))
    capability, _, stats = admission.capabilities()
    capability["fts5_contentless_trigram_case_sensitive"] = False
    capability["fts_layout_sha256"] = None
    monkeypatch.setattr(admission, "capabilities", lambda: (capability, [], stats))
    before = evidence(database, cache)
    with source.readonly(database) as db:
        with pytest.raises(admission.SourceAdmissionError):
            source.identify(db)
    assert before == evidence(database, cache)


def test_unproved_stat4_layout_is_rejected_even_when_its_shape_looks_standard(
    tmp_path, monkeypatch
):
    database, cache = make_operational_source(tmp_path / "state", analyze=True)
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE crafted_stat4(tbl,idx,neq,nlt,ndlt,sample)")
        db.execute("PRAGMA writable_schema=ON")
        db.execute(
            "UPDATE sqlite_schema SET name='sqlite_stat4',tbl_name='sqlite_stat4',"
            "sql='CREATE TABLE sqlite_stat4(tbl,idx,neq,nlt,ndlt,sample)' "
            "WHERE name='crafted_stat4'"
        )
    capability, fts, stats = admission.capabilities()
    stats.pop("sqlite_stat4", None)
    capability["statistics_layouts"].pop("sqlite_stat4", None)
    monkeypatch.setattr(admission, "capabilities", lambda: (capability, fts, stats))
    before = evidence(database, cache)
    with source.readonly(database) as db:
        with pytest.raises(admission.SourceAdmissionError) as error:
            source.identify(db)
    assert any(
        d["object"] == "sqlite_stat4" and d["preservation"] == "blocking_unsupported"
        for d in error.value.report["preservation_dispositions"]
    )
    assert before == evidence(database, cache)


def test_unused_runtime_capabilities_do_not_change_baseline_identity(
    tmp_path, monkeypatch
):
    database, _ = make_operational_source(tmp_path / "state")
    with source.readonly(database) as db:
        original = source.identify(db)
    capability, _, _ = admission.capabilities()
    capability["fts5_contentless_trigram_case_sensitive"] = False
    capability["fts_layout_sha256"] = None
    capability["statistics_layouts"] = {}
    monkeypatch.setattr(admission, "capabilities", lambda: (capability, [], {}))
    with source.readonly(database) as db:
        assert source.identify(db) == original


def test_component_capability_does_not_relax_guarded_worker_minimum(tmp_path):
    database, cache = make_operational_source(tmp_path / "state", kinds=("code",))
    before = evidence(database, cache)
    workspace = tmp_path / "conversion"
    # Use the actual lane's binding. In particular, do not upgrade an older
    # native parent here: it may recognize the read profile but cannot convert.
    code = """
import importlib.util, os, runpy, sys
if os.environ.get('TEST_SQLITE_MINIMUM'):
    from scripts.sqlite_minimum import activate
    activate()
elif sys.argv[1]:
    spec = importlib.util.spec_from_file_location('_sqlite3', sys.argv[1])
    binding = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(binding)
    sys.modules['_sqlite3'] = binding
sys.argv = ['scripts/offline_convert.py', *sys.argv[2:]]
runpy.run_path('scripts/offline_convert.py', run_name='__main__')
"""
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            getattr(sys.modules["_sqlite3"], "__file__", ""),
            "seal",
            "--source",
            str(database),
            "--source-cache",
            str(cache),
            "--work-dir",
            str(workspace),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env=dict(os.environ),
    )
    if sqlite3.sqlite_version_info < (3, 46, 1):
        assert child.returncode == 2, child.stderr
        assert json.loads(child.stderr)["code"] == "UNSUPPORTED_SQLITE_RUNTIME"
        assert not (workspace / "source.sqlite3").exists()
    else:
        assert child.returncode == 0, child.stderr
        assert json.loads(child.stdout) == {"sealed": True}
        assert (workspace / "source.sqlite3").is_file()
    assert before == evidence(database, cache)


def test_migration_records_remain_strict(tmp_path):
    database, cache = make_operational_source(tmp_path / "state", kinds=("code",))
    with sqlite3.connect(database) as db:
        db.execute("UPDATE schema_migrations SET checksum='forged' WHERE version=2")
    before = evidence(database, cache)
    with source.readonly(database) as db:
        with pytest.raises(ConversionError, match="SOURCE_MIGRATIONS_MISMATCH"):
            source.identify(db)
    assert before == evidence(database, cache)


def test_bounded_legacy_descriptor_is_only_admitted_for_core_handoff(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    cache = make_source(database)
    workspace = tmp_path / "conversion"
    record = engine.seal_input(database, workspace, [cache])
    old_keys = {
        "format_id",
        "db_instance_id",
        "schema_sha256",
        "catalog",
        "migrations",
        "encoding",
        "original",
        "sealed",
        "caches",
    }
    old = {k: record[k] for k in old_keys}
    descriptor = workspace / "sealed.json"
    descriptor.write_text(canonical(old))
    with pytest.raises(ConversionError, match="SOURCE_SCHEMA_MISMATCH"):
        source.verify_seal(workspace)
    assert source.verify_seal(workspace, allow_legacy=True) == old
    descriptor.write_text(canonical({**old, "unexpected": True}))
    with pytest.raises(ConversionError, match="SOURCE_SCHEMA_MISMATCH"):
        source.verify_seal(workspace, allow_legacy=True)


def test_legacy_descriptor_cannot_hide_operational_derivatives(tmp_path):
    database, cache = make_operational_source(tmp_path / "state", kinds=("code",))
    workspace = tmp_path / "conversion"
    record = engine.seal_input(database, workspace, [cache])
    old_keys = {
        "format_id",
        "db_instance_id",
        "schema_sha256",
        "catalog",
        "migrations",
        "encoding",
        "original",
        "sealed",
        "caches",
    }
    (workspace / "sealed.json").write_text(canonical({k: record[k] for k in old_keys}))
    with pytest.raises(ConversionError, match="LEGACY_SOURCE_LAYOUT_UNSUPPORTED"):
        source.verify_seal(workspace, allow_legacy=True)
