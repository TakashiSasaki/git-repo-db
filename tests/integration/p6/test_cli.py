"""Integration tests for the opt-in P6 CLI (`repo_catalog.cli.production_query`)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from repo_catalog.adapters.sqlite.p1_coordination import persist_catalog_stop
from repo_catalog.cli.production_query import main
from repo_catalog.domain.resource_identity import encode_identity
from tests.integration.p6.conftest import (
    REPOSITORY,
    SERVICE,
    populate_rich_catalog,
)


def _run_cli(args: list[str], capsys) -> tuple[int, dict]:
    code = main(args)
    captured = capsys.readouterr()
    output = captured.out if code == 0 else captured.err
    return code, json.loads(output.strip())


def test_cli_all_subcommands_pagination_and_error_handling(
    tmp_path: Path, capsys
) -> None:
    catalog_dir = tmp_path / "cli_catalog"
    fixtures = populate_rich_catalog(catalog_dir, fmt="sha1")
    cat_str = str(catalog_dir)

    # 1. status
    code, status_data = _run_cli(["status", "--catalog", cat_str], capsys)
    assert code == 0
    assert status_data["mode"] == "paired"
    assert status_data["repository_uuidv4"] == REPOSITORY
    token_str = status_data["snapshot_token"]

    # 2. git-object
    commit_object_oid = fixtures["commit_obj"].object_oid.object_oid
    code, gobj_data = _run_cli(
        [
            "git-object",
            "--catalog",
            cat_str,
            "--format",
            "sha1",
            "--object-oid",
            commit_object_oid,
            "--include-bytes",
        ],
        capsys,
    )
    assert code == 0
    assert gobj_data["object_oid"] == commit_object_oid
    assert gobj_data["metadata_retained"] is True
    assert gobj_data["retained_bytes"]["verified"] is True

    # 3. git-objects with pagination
    code, gobjs_p1 = _run_cli(
        [
            "git-objects",
            "--catalog",
            cat_str,
            "--format",
            "sha1",
            "--limit",
            "2",
            "--expected-token",
            token_str,
        ],
        capsys,
    )
    assert code == 0
    assert len(gobjs_p1["items"]) == 2
    assert gobjs_p1["has_more"] is True
    code, gobjs_p2 = _run_cli(
        [
            "git-objects",
            "--catalog",
            cat_str,
            "--format",
            "sha1",
            "--limit",
            "2",
            "--cursor",
            gobjs_p1["next_cursor"],
            "--expected-token",
            token_str,
        ],
        capsys,
    )
    assert code == 0
    assert len(gobjs_p2["items"]) >= 1

    # 4. git-observations
    code, gobs_data = _run_cli(
        ["git-observations", "--catalog", cat_str, "--kind", "ref"], capsys
    )
    assert code == 0
    assert gobs_data["total_count"] == 2

    # 5. ref observations (the Capture-based notes command is retired)
    code, notes_data = _run_cli(
        ["ref-observations", "--catalog", cat_str],
        capsys,
    )
    assert code == 0
    assert len(notes_data["items"]) == 1

    # 6. context-resource
    code, cres_data = _run_cli(
        [
            "context-resource",
            "--catalog",
            cat_str,
            "--service",
            SERVICE,
            "--kind",
            "pull_request",
            "--id",
            encode_identity("42"),
        ],
        capsys,
    )
    assert code == 0
    assert cres_data["provider_resource_id"] == encode_identity("42")
    assert cres_data["repository_uuidv4"] == REPOSITORY

    # 7. context-resources
    code, cress_data = _run_cli(
        [
            "context-resources",
            "--catalog",
            cat_str,
            "--service",
            SERVICE,
            "--kind",
            "pull_request",
        ],
        capsys,
    )
    assert code == 0
    assert cress_data["total_count"] == 1

    # 8. paired-resource
    code, pres_data = _run_cli(
        [
            "paired-resource",
            "--catalog",
            cat_str,
            "--service",
            SERVICE,
            "--kind",
            "pull_request",
            "--id",
            encode_identity("42"),
            "--include-core-bytes",
        ],
        capsys,
    )
    assert code == 0
    assert len(pres_data["core_resolutions"]) == 2

    # 9. paired-resources
    code, press_data = _run_cli(
        ["paired-resources", "--catalog", cat_str, "--kind", "pull_request"],
        capsys,
    )
    assert code == 0
    assert press_data["total_count"] == 1

    # 10. search-rebuild & search
    code, sreb_data = _run_cli(
        [
            "search-rebuild",
            "--catalog",
            cat_str,
            "--kinds",
            "git_metadata,notes,context_text",
        ],
        capsys,
    )
    assert code == 0
    assert sreb_data["indexed_counts"]["git_metadata"] > 0

    code, search_data = _run_cli(
        ["search", "--catalog", cat_str, "--query", "p6", "--limit", "10"],
        capsys,
    )
    assert code == 0
    assert search_data["backend"] == "verified_projection_scan"
    assert search_data["total_count"] >= 3

    # 11. Error exit code on SNAPSHOT_MISMATCH
    bad_token = (
        '{"catalog_instance_uuidv4":"'
        + status_data["catalog_instance_uuidv4"]
        + '","context_sha256":"'
        + ("0" * 64)
        + '","core_sha256":"'
        + ("0" * 64)
        + '","repository_uuidv4":"'
        + REPOSITORY
        + '"}'
    )
    code, err_data = _run_cli(
        [
            "git-objects",
            "--catalog",
            cat_str,
            "--expected-token",
            bad_token,
        ],
        capsys,
    )
    assert code != 0
    assert err_data["code"] == "SNAPSHOT_MISMATCH"

    # 12. Error exit code on RECOVERY_STOP
    persist_catalog_stop(catalog_dir, "simulated stop for CLI test")
    code, stop_err = _run_cli(["status", "--catalog", cat_str], capsys)
    assert code != 0
    assert stop_err["code"] in ("RECOVERY_STOP", "RECOVERY_REQUIRED")


def test_cli_module_execution_and_schema21_cli_isolation(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "subproc_catalog"
    populate_rich_catalog(
        catalog_dir, fmt="sha256", include_core=True, include_context=False
    )

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "repo_catalog.cli.production_query",
            "status",
            "--catalog",
            str(catalog_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    parsed = json.loads(proc.stdout.strip())
    assert parsed["mode"] == "core_only"

    # Verify default Schema 21 CLI (`repo_catalog.cli.main`) still works and is untouched
    main_proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "from repo_catalog.cli.main import main; main(['--help'])",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "repo-catalog" in main_proc.stdout
