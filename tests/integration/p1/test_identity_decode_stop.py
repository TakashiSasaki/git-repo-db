"""A fixed identity reader stops on malformed stored TEXT before ordinary reuse."""

from contextlib import closing
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.p1_repository import RepositoryStore
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize, schema_rows
from repo_catalog.domain.shared_values import RepositoryFailure, encode
from tests.integration.auxiliary_rows.test_identity_assertions import (
    assertion,
    cancellation,
    original,
)


@pytest.mark.parametrize("kind", ["relation", "cancellation"])
@pytest.mark.parametrize("column", ["record_json", "provenance"])
def test_identity_snapshot_invalid_stored_utf8_stops_without_rewriting_authority(
    tmp_path, kind, column
):
    path = tmp_path / "repository.sqlite3"
    left, right = str(uuid4()), str(uuid4())
    initialize(path, "repository", left, str(uuid4()))
    record = assertion("repository", left, right)
    removed = cancellation(record)
    with closing(RepositoryStore(path)) as repository_store:
        repository_store.admit_repository(right)
        repository_store.admit_identity_evidence(
            "relation", encode(record), original(record)
        )
        repository_store.admit_identity_evidence(
            "cancellation", encode(removed), original(removed)
        )
        healthy = repository_store.identity_evidence_snapshot()
        assert healthy["relations"][0]["record_json"] == encode(record)
        assert healthy["cancellations"][0]["record_json"] == encode(removed)
    table = (
        "repository_identity_assertions"
        if kind == "relation"
        else "repository_identity_cancellations"
    )
    with closing(connect(path, "repository")) as raw:
        before = schema_rows(raw)
        guards = raw.execute(
            "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name=? AND name LIKE '%_update'",
            (table,),
        ).fetchall()
        assert guards
        checks = raw.execute("PRAGMA ignore_check_constraints").fetchone()[0]
        raw.execute("PRAGMA ignore_check_constraints=ON")
        try:
            for name, _ in guards:
                raw.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
            assert (
                raw.execute(f"UPDATE {table} SET {column}=CAST(x'80' AS TEXT)").rowcount
                == 1
            )
        finally:
            for _, ddl in guards:
                raw.execute(ddl)
            raw.execute("PRAGMA ignore_check_constraints=" + str(checks))
        assert schema_rows(raw) == before
    preserved = path.read_bytes()
    with closing(RepositoryStore(path)) as repository_store:
        with pytest.raises(RepositoryFailure) as fault:
            repository_store.identity_evidence_snapshot()
        assert fault.value.code == "AUTHORITATIVE_CORRUPTION"
        assert (tmp_path / "p1-recovery-stop.json").is_file()
        with pytest.raises(RepositoryFailure) as blocked:
            repository_store.admit_repository(str(uuid4()))
        assert blocked.value.code == "RECOVERY_STOP"
    assert path.read_bytes() == preserved


def test_identity_snapshot_input_limits_do_not_stop_sound_authority(tmp_path):
    path = tmp_path / "repository.sqlite3"
    initialize(path, "repository", str(uuid4()), str(uuid4()))
    with closing(RepositoryStore(path)) as repository_store:
        for options in (
            {"max_evidence": True},
            {"max_evidence": 0},
            {"max_bytes": False},
        ):
            with pytest.raises(ValueError):
                repository_store.identity_evidence_snapshot(**options)
        assert repository_store.identity_evidence_snapshot()["relations"] == []
    assert not (tmp_path / "p1-recovery-stop.json").exists()
