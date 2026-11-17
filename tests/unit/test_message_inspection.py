"""Saved message inspection cannot invoke provider parsing or domain admission."""

import json
import sqlite3

import pytest

from repo_catalog.adapters.github import production_intake
from repo_catalog.adapters.github.transport import GitHubTransport
from repo_catalog.adapters.recording import (
    LocalArchiveReader,
    LocalFileRecorder,
    RecordingError,
)
from repo_catalog.application.recording_inspection import inspect_message
from repo_catalog.cli.main import main
from repo_catalog.cli.separated_recording import parser


def recorded(tmp_path, value):
    state = tmp_path / "explicit-synthetic-state"
    reference = LocalFileRecorder(state / "transport-archive").record_exchange(
        {
            "method": "GET",
            "url": "https://api.github.com/repos/fixture/alpha/issues",
            "observed_at_us": -123,
            "attempt": 1,
            "response_status": 200,
        },
        json.dumps(value).encode(),
    )
    return state, reference


@pytest.mark.parametrize(
    "action",
    ["reparse-message", "reparse_message", "replay-message", "extract-message"],
)
def test_saved_message_parsing_is_absent_before_any_application_access(
    tmp_path, monkeypatch, action
):
    state, reference = recorded(
        tmp_path,
        {
            "id": 17,
            "number": 4,
            "title": "Saved title",
            "body": "exact\r\n本文",
            "state": "closed",
            "transport_only_marker": "PHASE1_RETIRED_MESSAGE_PARSING",
        },
    )
    before = {path: path.read_bytes() for path in state.rglob("*") if path.is_file()}

    def forbidden(*args, **kwargs):
        pytest.fail("Unsupported parsing accessed transport, archive or catalog")

    monkeypatch.setattr(LocalArchiveReader, "read", forbidden)
    monkeypatch.setattr(GitHubTransport, "request", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    for name in (
        "normalize_issue",
        "normalize_issue_comment",
        "normalize_review",
        "normalize_review_comment",
    ):
        monkeypatch.setattr(production_intake, name, forbidden)
    with pytest.raises(SystemExit) as error:
        main(
            [
                "recording",
                action,
                reference,
                "--archive-root",
                str(state / "transport-archive"),
            ]
        )
    assert error.value.code == 2
    assert {
        path: path.read_bytes() for path in state.rglob("*") if path.is_file()
    } == before
    assert not (state / "catalog.sqlite3").exists()


@pytest.mark.parametrize(
    "arguments",
    [
        ["reparse-message", "saved-reference", "--context", "context.json"],
        ["reparse_message", "saved-reference"],
        ["replay-message", "saved-reference"],
        ["extract-message", "saved-reference"],
        ["inspect-message", "saved-reference", "--context", "context.json"],
    ],
)
def test_retired_message_cli_routes_and_context_option_have_no_side_effects(
    tmp_path, arguments
):
    state = tmp_path / "absent-catalog-state"
    with pytest.raises(SystemExit) as error:
        main(
            [
                "recording",
                *arguments,
                "--archive-root",
                str(state / "transport-archive"),
            ]
        )
    assert error.value.code == 2
    assert not state.exists()


def test_parser_help_exposes_inspection_without_saved_message_parsing(capsys):
    with pytest.raises(SystemExit) as exit_status:
        parser().parse_args(["--help"])
    assert exit_status.value.code == 0
    help_text = capsys.readouterr().out
    assert "inspect-message" in help_text
    assert "reparse-message" not in help_text
    assert "replay-message" not in help_text
    with pytest.raises(SystemExit) as exit_status:
        parser().parse_args(["inspect-message", "--help"])
    assert exit_status.value.code == 0
    assert "--context" not in capsys.readouterr().out


def test_inspection_and_bounded_failure_do_not_parse_or_create_catalog(
    tmp_path, monkeypatch
):
    state, reference = recorded(tmp_path, {"id": 1, "body": "x" * 100})

    def forbidden(*args, **kwargs):
        pytest.fail("Inspection accessed transport, provider parser or catalog")

    monkeypatch.setattr(GitHubTransport, "request", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    for name in (
        "normalize_issue",
        "normalize_issue_comment",
        "normalize_review",
        "normalize_review_comment",
    ):
        monkeypatch.setattr(production_intake, name, forbidden)
    result = inspect_message(state / "transport-archive", reference, max_bytes=1000)
    assert set(result) == {
        "archive_reference",
        "context",
        "body_bytes",
        "admitted",
    }
    assert result["body_bytes"] > 100
    assert result["context"]["observed_at_us"] == -123
    assert result["admitted"] is False
    with pytest.raises(RecordingError) as exc:
        inspect_message(state / "transport-archive", reference, max_bytes=20)
    assert exc.value.code == "ARCHIVE_LIMIT"
    assert not (state / "catalog.sqlite3").exists()
