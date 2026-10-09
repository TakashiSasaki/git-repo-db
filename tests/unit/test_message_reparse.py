"""Supplementary archive inspection cannot publish or reobserve domain state."""

import json

import pytest

from repo_catalog.adapters.recording import LocalFileRecorder
from repo_catalog.application.parser_service import ParserService
from repo_catalog.domain.models import CatalogError


def recorded(tmp_path, value, *, status=200):
    state = tmp_path / "explicit-synthetic-state"
    reference = LocalFileRecorder(state / "transport-archive").record_exchange(
        {
            "method": "GET",
            "url": "https://api.github.com/repos/fixture/alpha/issues",
            "observed_at_us": -123,
            "attempt": 1,
            "response_status": status,
        },
        json.dumps(value).encode(),
    )
    return state, reference


def test_reparse_message_uses_provider_parser_and_original_observation(tmp_path):
    state, reference = recorded(
        tmp_path,
        [
            {
                "id": 17,
                "number": 4,
                "title": "Original title",
                "body": "exact\r\n本文",
                "state": "closed",
                "updated_at": "2026-10-09T10:00:00Z",
            }
        ],
    )
    context = tmp_path / "context.json"
    context.write_text(
        json.dumps(
            {
                "resource_kind": "issue",
                "context": {"acquisition_scope": {"endpoint": "synthetic"}},
            }
        )
    )
    before = set(state.rglob("*"))
    result = ParserService(state).execute(
        "reparse-message",
        {"archive_reference": reference, "max_bytes": 65536, "context": str(context)},
    )
    assert result.data["admitted"] is False
    assert result.data["source"] == "replay"
    projection = result.data["projections"][0]
    assert projection["provider_resource_id"] == "17"
    assert projection["body"] == "exact\r\n本文"
    assert projection["observed_at_us"] == -123
    assert projection["provider_updated_at_us"] == 1791540000000000
    assert projection["parsed_at_us"] != -123
    assert set(state.rglob("*")) == before
    assert not (state / "catalog.sqlite3").exists()


def test_inspection_and_bounded_failure_do_not_create_catalog(tmp_path):
    state, reference = recorded(tmp_path, {"id": 1, "body": "x" * 100})
    result = ParserService(state).execute(
        "inspect-message", {"archive_reference": reference, "max_bytes": 1000}
    )
    assert result.data["body_bytes"] > 100
    assert result.data["admitted"] is False
    with pytest.raises(CatalogError) as exc:
        ParserService(state).execute(
            "inspect-message", {"archive_reference": reference, "max_bytes": 20}
        )
    assert exc.value.code == "ARCHIVE_LIMIT"
    assert not (state / "catalog.sqlite3").exists()


def test_reparse_message_does_not_treat_http_failure_as_resource(tmp_path):
    state, reference = recorded(tmp_path, {"message": "not accessible"}, status=404)
    context = tmp_path / "context.json"
    context.write_text(
        json.dumps({"resource_kind": "issue", "context": {"acquisition_scope": {}}})
    )
    with pytest.raises(CatalogError, match="saved successful JSON body"):
        ParserService(state).execute(
            "reparse-message",
            {
                "archive_reference": reference,
                "max_bytes": 65536,
                "context": str(context),
            },
        )
