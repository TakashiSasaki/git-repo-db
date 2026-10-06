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


def document_source(store, observations):
    """Saved version assertions stay evidence, not a recreated version entity."""
    from repo_catalog.adapters.import_v2.types import tagged_key
    from repo_catalog.adapters.sqlite.text_bodies import intern_text_body
    from repo_catalog.application.repository_identity import add_instance, bind

    service = add_instance(store, "github", "fixture")
    bind(store, "repo", service, "42")
    binding = store.one("SELECT repository_binding_id FROM repository_bindings")[0]
    store.execute(
        "INSERT INTO change_requests(change_request_id,repository_id,repository_binding_id,request_kind,number) VALUES('pr','repo',?,'pull_request',1)",
        (binding,),
    )
    key = ("pr", "pr-body", "123")
    store.execute(
        "INSERT INTO documents(change_request_id,kind,provider_change_request_document_id,deleted,metadata) VALUES(?,?,?,0,'{}')",
        key,
    )
    digest = intern_text_body(store.connection, "retained text")

    def mapped(table, source_values, target_table, target_values):
        record = archived(store, table, source_values)
        target_key = tagged_key(
            [
                ("integer", value)
                if isinstance(value, int)
                else ("text", value.encode())
                for value in target_values
            ]
        )
        store.execute(
            "INSERT INTO id_mappings(legacy_record_id,target_table,target_key,relation,reason) VALUES(?,?,?,'identity','test')",
            (record, target_table, target_key),
        )

    mapped("pr_documents", {"id": "old-doc", "current_version": 7}, "documents", key)
    # This orphan source version itself is NOT an observation and has no target
    # version mapping. Its original value remains in the typed archive.
    archived(store, "document_versions", {"id": "7", "body": "retained text"})
    for ident, version, stamp in observations:
        store.execute(
            "INSERT INTO document_observations(document_observation_id,change_request_id,kind,provider_change_request_document_id,text_body_sha256,observed_at,parsed_at,metadata) VALUES(?,?,?,?,?,?,'2026-10-06','{}')",
            (ident, *key, digest, stamp),
        )
        mapped(
            "resource_observations",
            {"id": str(ident), "document_id": "old-doc", "version_id": version},
            "document_observations",
            (ident,),
        )
    return key


def test_saved_version_selects_real_observation_not_largest_id_or_other_version(
    tmp_path,
):
    with pending(tmp_path) as store:
        document_source(
            store,
            [(900, 7, "2026-01-01"), (12, 7, "2026-01-02"), (999, 8, "2026-01-03")],
        )
        result = finalize_catalog(store)
        assert (
            store.one("SELECT current_document_observation_id FROM documents")[0] == 12
        )
        assert any(row.get("candidate_id") == 12 for row in result["restored"])
        assert store.one("SELECT count(*) FROM document_observations")[0] == 3
        assert not store.one(
            "SELECT 1 FROM sqlite_schema WHERE name='document_versions'"
        )


@pytest.mark.parametrize(
    "observations,reason",
    [
        ([], "saved_selection_not_suitable"),
        ([(1, 7, "2026-01-01"), (2, 7, "2026-01-01")], "saved_selection_ambiguous"),
        ([(1, 7, None)], "saved_selection_not_suitable"),
    ],
)
def test_orphan_or_ambiguous_saved_version_does_not_invent_current(
    tmp_path, observations, reason
):
    with pending(tmp_path) as store:
        document_source(store, observations)
        result = finalize_catalog(store)
        assert (
            store.one("SELECT current_document_observation_id FROM documents")[0]
            is None
        )
        assert store.one("SELECT count(*) FROM document_observations")[0] == len(
            observations
        )
        assert any(
            row.get("table") == "documents" and row["reason"] == reason
            for row in result["unresolved_current"]
        )
        assert (
            store.one(
                "SELECT count(*) FROM legacy_records WHERE source_table='document_versions'"
            )[0]
            == 1
        )
