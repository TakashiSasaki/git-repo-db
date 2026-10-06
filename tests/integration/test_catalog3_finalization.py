"""Finalization is a decision over saved evidence, not an observation heuristic."""

import json

import pytest

from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.finalization import check_catalog, finalize_catalog
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.domain.models import CatalogError


def pending(tmp_path, *, complete=True):
    state = tmp_path / "state"
    MaintenanceService(state).init("catalog-text-v1", 67108864, 0)
    s = Store(state)
    s.execute("UPDATE database_identity SET lifecycle='building'")
    s.execute(
        "INSERT INTO conversion_sources(conversion_source_id,source_sha256,schema_sha256,format_id,source_db_instance_id,source_catalog,source_migrations) VALUES('src',?,?,'v2','source-instance',?,?)",
        (b"x" * 32, b"y" * 32, b"{}", b"{}"),
    )
    s.execute(
        "INSERT INTO conversion_runs(conversion_run_id,conversion_source_id,started_at,ended_at,parser_version,state,manifest) VALUES('run','src','2026-01-01',NULL,'offline-v2/1','paused',?)",
        (json.dumps({"complete": complete}),),
    )
    s.execute(
        "INSERT INTO repositories(repository_id,name,metadata) VALUES('repo','repo','{}')"
    )
    s.execute(
        "INSERT INTO git_acquisitions(git_acquisition_id,repository_id,object_format,refs_observed_at,kind,request) VALUES('acq','repo','sha1','2026-01-01','legacy','{}')"
    )
    return s


def archived(store, table, values, encoding="utf-8"):
    rid = store.execute(
        "INSERT INTO legacy_records(conversion_source_id,source_table,source_key,row_sha256) VALUES('src',?,?,?)",
        (table, values["id"].encode(), b"r" * 32),
    ).lastrowid
    for key, value in values.items():
        kind, raw = (
            ("null", b"")
            if value is None
            else ("integer", str(value).encode())
            if isinstance(value, int)
            else ("text", value.encode(encoding))
        )
        store.execute(
            "INSERT INTO legacy_values(legacy_record_id,column_name,storage_type,value_bytes) VALUES(?,?,?,?)",
            (rid, key, kind, raw),
        )
    return rid


def test_saved_pointer_beats_largest_id_or_newest_timestamp_and_is_idempotent(tmp_path):
    with pending(tmp_path) as store:
        store.execute(
            "INSERT INTO snapshots(snapshot_id,git_acquisition_id,repository_id,published,generation,created_at) VALUES('saved','acq','repo',1,1,'2026-01-01')"
        )
        store.execute(
            "INSERT INTO git_acquisitions(git_acquisition_id,repository_id,object_format,refs_observed_at,kind,request) VALUES('later-acq','repo','sha1','2026-02-01','legacy','{}')"
        )
        store.execute(
            "INSERT INTO snapshots(snapshot_id,git_acquisition_id,repository_id,published,generation,created_at) VALUES('zz-largest','later-acq','repo',1,100,'2026-02-01')"
        )
        archived(store, "repositories", {"id": "repo", "current_snapshot": "saved"})
        result = finalize_catalog(store)
        assert store.one("SELECT current_snapshot_id FROM repositories")[0] == "saved"
        assert result["restored"][0]["candidate_id"] == "saved"
        revision = store.revision()
        assert finalize_catalog(store)["catalog"] == revision
        assert (
            store.one(
                "SELECT count(*) FROM validation_results WHERE code='RUNTIME_FINALIZATION'"
            )[0]
            == 1
        )
    with Store(tmp_path / "state", readonly=True) as store:
        assert store.one("SELECT lifecycle FROM database_identity")[0] == "validated"


def test_missing_selection_or_unpublished_fact_stays_unset_without_blocking_catalog(
    tmp_path,
):
    with pending(tmp_path) as store:
        store.execute(
            "INSERT INTO snapshots(snapshot_id,git_acquisition_id,repository_id,published,generation,created_at) VALUES('incomplete','acq','repo',0,1,'2026-01-01')"
        )
        archived(
            store, "repositories", {"id": "repo", "current_snapshot": "incomplete"}
        )
        result = finalize_catalog(store)
        assert store.one("SELECT current_snapshot_id FROM repositories")[0] is None
        assert (
            result["unresolved_current"][0]["reason"] == "saved_selection_not_suitable"
        )
        assert store.one("SELECT lifecycle FROM database_identity")[0] == "validated"


def test_partial_content_diagnostics_do_not_block_but_identity_corruption_does(
    tmp_path,
):
    with pending(tmp_path) as store:
        record = archived(store, "contents", {"id": "1", "raw_text": None})
        store.execute(
            "INSERT INTO validation_results(conversion_run_id,invariant_id,code,severity,observed_at,details) VALUES('run','content','ORIGINAL_BYTES_MISSING','blocking','2026-01-01',?)",
            (json.dumps({"legacy_record_id": record}),),
        )
        assert check_catalog(store) == []
        identity_record = archived(
            store, "repositories", {"id": "malformed", "name": "bad"}
        )
        store.execute(
            "INSERT INTO validation_results(conversion_run_id,invariant_id,code,severity,observed_at,details) VALUES('run','identity','MALFORMED_TEXT','blocking','2026-01-01',?)",
            (json.dumps({"legacy_record_id": identity_record}),),
        )
        with pytest.raises(CatalogError, match="Critical import"):
            finalize_catalog(store)
        assert store.one("SELECT lifecycle FROM database_identity")[0] == "building"
    with pytest.raises(CatalogError, match="Complete import"):
        Store(tmp_path / "state", readonly=True)


def test_incomplete_import_cannot_be_finalized(tmp_path):
    with pending(tmp_path, complete=False) as store:
        with pytest.raises(CatalogError) as cause:
            finalize_catalog(store)
        assert cause.value.details["issues"][0]["code"] == "IMPORT_INCOMPLETE"
        assert store.revision()["publication_seq"] == 0


def test_saved_selection_decodes_retained_source_text_encoding(tmp_path):
    with pending(tmp_path) as store:
        store.execute(
            "UPDATE conversion_runs SET manifest=?",
            (json.dumps({"complete": True, "encoding": "UTF-16le"}),),
        )
        store.execute(
            "INSERT INTO snapshots(snapshot_id,git_acquisition_id,repository_id,published,generation,created_at) VALUES('選択','acq','repo',1,1,'2026-01-01')"
        )
        archived(
            store,
            "repositories",
            {"id": "repo", "current_snapshot": "選択"},
            encoding="UTF-16le",
        )
        assert finalize_catalog(store)["restored"][0]["candidate_id"] == "選択"
        assert store.one("SELECT current_snapshot_id FROM repositories")[0] == "選択"


@pytest.mark.parametrize(
    "code",
    [
        "OBJECT_HASH_MISMATCH",
        "EXPECTED_OID_MISMATCH",
        "THREAD_IDENTITY_CONFLICT",
        "GIT_OWNER_MISMATCH",
    ],
)
def test_domain_identity_corruption_prevents_finalization(tmp_path, code):
    with pending(tmp_path) as store:
        store.execute(
            "INSERT INTO validation_results(conversion_run_id,invariant_id,code,severity,observed_at,details) VALUES('run','identity',?,'blocking','2026-01-01','{}')",
            (code,),
        )
        with pytest.raises(CatalogError):
            finalize_catalog(store)
        assert store.one("SELECT lifecycle FROM database_identity")[0] == "building"
