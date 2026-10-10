"""Saved message inspection cannot invoke provider parsing or domain admission."""

import json

import pytest

from repo_catalog.adapters.github import current_parser
from repo_catalog.adapters.github.transport import GitHubTransport
from repo_catalog.adapters.recording import LocalArchiveReader, LocalFileRecorder
from repo_catalog.application import parser_service
from repo_catalog.application.parser_service import ParserService
from repo_catalog.cli.main import parser
from repo_catalog.domain.models import CatalogError
from tests.support.cli import run


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
    monkeypatch.setattr(parser_service, "Store", forbidden)
    monkeypatch.setattr(parser_service, "FileLock", forbidden)
    for name in ("issue", "issue_comment", "review", "review_comment"):
        monkeypatch.setattr(current_parser, name, forbidden)
    with pytest.raises(CatalogError, match="Unknown parser action") as error:
        ParserService(state).execute(
            action,
            {
                "archive_reference": reference,
                "max_bytes": 65536,
                "context": str(tmp_path / "missing-context.json"),
                "input": str(tmp_path / "missing-input.json"),
            },
        )
    assert error.value.code == "INVALID_ARGUMENT"
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
    result = run(state, "parser", *arguments, expected=2)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert not state.exists()


def test_parser_help_exposes_inspection_without_saved_message_parsing(capsys):
    with pytest.raises(SystemExit) as exit_status:
        parser().parse_args(["parser", "--help"])
    assert exit_status.value.code == 0
    help_text = capsys.readouterr().out
    assert "inspect-message" in help_text
    assert "reparse-message" not in help_text
    assert "replay-message" not in help_text
    with pytest.raises(SystemExit) as exit_status:
        parser().parse_args(["parser", "inspect-message", "--help"])
    assert exit_status.value.code == 0
    assert "--context" not in capsys.readouterr().out


def test_inspection_and_bounded_failure_do_not_parse_or_create_catalog(
    tmp_path, monkeypatch
):
    state, reference = recorded(tmp_path, {"id": 1, "body": "x" * 100})

    def forbidden(*args, **kwargs):
        pytest.fail("Inspection accessed transport, provider parser or catalog")

    monkeypatch.setattr(GitHubTransport, "request", forbidden)
    monkeypatch.setattr(parser_service, "Store", forbidden)
    monkeypatch.setattr(parser_service, "FileLock", forbidden)
    for name in ("issue", "issue_comment", "review", "review_comment"):
        monkeypatch.setattr(current_parser, name, forbidden)
    result = ParserService(state).execute(
        "inspect-message", {"archive_reference": reference, "max_bytes": 1000}
    )
    assert set(result.data) == {
        "archive_reference",
        "context",
        "body_bytes",
        "admitted",
    }
    assert result.data["body_bytes"] > 100
    assert result.data["context"]["observed_at_us"] == -123
    assert result.data["admitted"] is False
    with pytest.raises(CatalogError) as exc:
        ParserService(state).execute(
            "inspect-message", {"archive_reference": reference, "max_bytes": 20}
        )
    assert exc.value.code == "ARCHIVE_LIMIT"
    assert not (state / "catalog.sqlite3").exists()
