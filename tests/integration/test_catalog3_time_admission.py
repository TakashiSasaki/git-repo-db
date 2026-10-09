"""Guarded salvage retains unsupported timestamp evidence without a false instant."""

import hashlib
import json
import sqlite3

from repo_catalog.adapters.import_v2 import engine
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.finalization import finalize_catalog
from repo_catalog.application.import_service import import_catalog
from tests.support.integrated_fixture import make_integrated_source


def test_guarded_import_keeps_fractional_hour_raw_and_diagnoses_unknown_time(tmp_path):
    source, cache = make_integrated_source(tmp_path / "source")
    raw_time = "1970-01-01T01.5Z"
    with sqlite3.connect(source) as db:
        observation_id = db.execute(
            "SELECT id FROM resource_observations ORDER BY id LIMIT 1"
        ).fetchone()[0]
        db.execute(
            "UPDATE resource_observations SET observed_at=? WHERE id=?",
            (raw_time, observation_id),
        )
    source_hash = hashlib.sha256(source.read_bytes()).digest()
    state = tmp_path / "target"
    assert import_catalog(source, state, source_caches=[cache])["complete"]
    with engine.connect(state / "catalog.sqlite3") as db:
        row = db.execute(
            "SELECT observed_at_us FROM document_observations WHERE document_observation_id=?",
            (observation_id,),
        ).fetchone()
        assert row is not None and row[0] is None
        archived = db.execute(
            "SELECT r.legacy_record_id,v.storage_type,v.value_bytes FROM legacy_values v "
            "JOIN legacy_records r USING(legacy_record_id) "
            "WHERE r.source_table='resource_observations' AND v.column_name='observed_at' "
            "AND v.value_bytes=?",
            (raw_time.encode(),),
        ).fetchone()
        assert tuple(archived)[1:] == ("text", raw_time.encode())
        diagnostics = [
            json.loads(row[0])
            for row in db.execute(
                "SELECT details FROM validation_results WHERE code='PR_INVALID_TIME'"
            )
        ]
        assert any(item["legacy_record_id"] == archived[0] for item in diagnostics)
    with Store(state, allow_building=True) as store:
        assert finalize_catalog(store)["lifecycle"] == "validated"
        assert (
            store.one(
                "SELECT observed_at_us FROM document_observations WHERE document_observation_id=?",
                (observation_id,),
            )[0]
            is None
        )
    assert hashlib.sha256(source.read_bytes()).digest() == source_hash
