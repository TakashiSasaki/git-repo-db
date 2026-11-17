"""The ordinary CLI selects exact current or captured Provider code scopes."""

import json
from pathlib import Path

import pytest

from repo_catalog.cli.main import main
from repo_catalog.domain.provider_acquisition import (
    ProviderPullRequestIntake,
    make_provenance,
)
from tests.e2e.test_separated_cli import document, run
from tests.integration.p5.test_pr_assessment import Fixture


def query(capsys, fixture, command, *options, expected=0):
    return run(
        capsys,
        "query",
        command,
        "--catalog",
        fixture.path,
        "--service-instance",
        fixture.service,
        "--provider-resource-id",
        fixture.parent.provider_resource_id,
        *options,
        expected=expected,
    )


def test_normal_cli_selects_listing_and_exact_original_capture_without_current_borrowing(
    tmp_path, capsys
):
    fixture = Fixture(tmp_path)
    fixture.code()
    original = fixture.query()
    files = next(row for row in original.collections if row["kind"] == "pr_files")
    provenance = files["alternatives"][0]["provenance_json"]
    fixture.observation(
        fixture.parent,
        "pr_files",
        make_provenance("cli-scope", "failed-files"),
        files["alternatives"][0]["scope_json"],
        400,
        "partial",
        (),
    )
    whole = query(capsys, fixture, "pr-code")
    assert whole["state"] == "partial"
    selected = query(capsys, fixture, "pr-code", "--listing-kind", "pr_commits")
    assert selected["state"] == "complete"
    assert [row["kind"] for row in selected["collections"]] == ["pr_commits"]
    assert selected["total_count"] == 1
    fixture.admit(
        pull_requests=(
            ProviderPullRequestIntake(
                {
                    **fixture.payload,
                    "head": {"sha": fixture.base.object_oid},
                    "updated_at": "2026-02-01T00:00:00Z",
                },
                500,
                make_provenance("cli-scope", "new-head"),
            ),
        )
    )
    assert query(capsys, fixture, "pr-code")["state"] != "complete"
    path = document(tmp_path, "original-provenance.json", provenance)
    first = query(
        capsys,
        fixture,
        "pr-code-capture",
        "--kind",
        "pr_files",
        "--provenance-file",
        path,
        "--require-git",
        "--limit",
        1,
    )
    assert first["state"] == "complete"
    assert first["coverage"]["scope_kind"] == "captured_listing"
    assert first["coverage"]["current_provider_state_asserted"] is False
    assert first["anchors"] == {k: original.anchors[k] for k in ("head", "base")}
    assert first["total_count"] == 2 and first["has_more"]
    second = query(
        capsys,
        fixture,
        "pr-code-capture",
        "--kind",
        "pr_files",
        "--provenance-file",
        path,
        "--require-git",
        "--limit",
        1,
        "--cursor",
        first["next_cursor"],
    )
    assert second["state"] == "complete" and not second["has_more"]
    assert first["items"] != second["items"]
    assert second["snapshot_token"] == first["snapshot_token"]
    wrong = query(
        capsys,
        fixture,
        "pr-code-capture",
        "--kind",
        "pr_commits",
        "--provenance-file",
        path,
        expected=2,
    )
    assert wrong["code"] == "CAPTURE_NOT_FOUND"
    # Reordered JSON may identify a different original; the CLI must preserve strings.
    assert json.loads(Path(path).read_text()) == provenance


@pytest.mark.parametrize(
    "options",
    [
        ("pr-code-capture", "--kind", "pr_files"),
        ("pr-code-capture", "--kind", "reviews", "--provenance-file", "unused"),
        ("pr-documents", "--listing-kind", "pr_commits"),
        ("pr-code", "--provenance-file", "unused"),
    ],
)
def test_invalid_code_scope_cli_options_do_not_open_catalog(tmp_path, capsys, options):
    with pytest.raises(SystemExit) as failure:
        main(
            [
                "query",
                options[0],
                "--catalog",
                str(tmp_path / "absent"),
                "--service-instance",
                "unused",
                "--provider-resource-id",
                "unused",
                *options[1:],
            ]
        )
    assert failure.value.code == 2
    capsys.readouterr()
    assert not (tmp_path / "absent").exists()
