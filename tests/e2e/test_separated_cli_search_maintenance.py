"""Normal Search maintenance reports actual projection checks and optional timing."""

import pytest

from tests.e2e.test_separated_cli import init, run, seed_metadata


def query(capsys, catalog, command):
    return run(
        capsys, "query", command, "--catalog", catalog, "--kinds", "git_metadata"
    )


def test_normal_cli_search_status_and_rebuild_report_actual_counts_and_duration(
    tmp_path, capsys
):
    catalog, _, _, _, _ = seed_metadata(tmp_path, capsys)
    before = query(capsys, catalog, "search-status")
    assert before["status"] == "unavailable_or_stale"
    assert before["estimate"] == {
        "runs": 0,
        "average_duration_ns": None,
        "estimated_duration_ns": None,
    }
    assert not (catalog / "search.sqlite3").exists()
    init(capsys, catalog, "search")
    rebuilt = query(capsys, catalog, "search-rebuild")
    assert rebuilt["indexed_counts"] == rebuilt["counts"]
    assert rebuilt["counts"]["git_metadata"] > 0
    assert type(rebuilt["duration_ns"]) is int and rebuilt["duration_ns"] >= 0
    assert rebuilt["telemetry_status"] == "available"
    assert rebuilt["estimate"] == {
        "runs": 1,
        "average_duration_ns": rebuilt["duration_ns"],
        "estimated_duration_ns": rebuilt["duration_ns"],
    }
    current = query(capsys, catalog, "search-status")
    assert current["status"] == "ready"
    assert current["kinds"]["git_metadata"] == {
        "fresh": True,
        "status": "ready",
        "document_count": rebuilt["counts"]["git_metadata"],
    }
    assert current["snapshot_token"] == rebuilt["snapshot_token"]
    assert current["estimate"] == rebuilt["estimate"]
    found = run(
        capsys,
        "query",
        "search",
        "--catalog",
        catalog,
        "--kinds",
        "git_metadata",
        "--query",
        "message",
    )
    assert found["backend"] == "verified_projection_scan" and found["total_count"] > 0
    assert not (catalog / "context.sqlite3").exists()


@pytest.mark.parametrize("loss", ["absent", "corrupt"])
def test_normal_cli_search_remains_usable_without_optional_operational_telemetry(
    tmp_path, capsys, loss
):
    catalog, _, _, _, _ = seed_metadata(tmp_path, capsys)
    init(capsys, catalog, "search")
    operational = catalog / "operational.sqlite3"
    operational.rename(tmp_path / "preserved-operational.sqlite3")
    if loss == "corrupt":
        operational.write_bytes(b"preserve damaged optional telemetry source")
    original = operational.read_bytes() if operational.exists() else None
    rebuilt = query(capsys, catalog, "search-rebuild")
    assert rebuilt["counts"]["git_metadata"] > 0
    assert rebuilt["telemetry_status"] == (
        "uninitialized" if loss == "absent" else "unavailable"
    )
    assert rebuilt["estimate"] == {
        "runs": 0,
        "average_duration_ns": None,
        "estimated_duration_ns": None,
    }
    assert (operational.read_bytes() if operational.exists() else None) == original
    status = query(capsys, catalog, "search-status")
    assert status["status"] == "ready" and status["kinds"]["git_metadata"]["fresh"]
    found = run(
        capsys,
        "query",
        "search",
        "--catalog",
        catalog,
        "--kinds",
        "git_metadata",
        "--query",
        "message",
    )
    assert found["backend"] == "verified_projection_scan" and found["total_count"] > 0
    assert not (catalog / "p1-recovery-stop.json").exists()
