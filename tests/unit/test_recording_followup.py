"""Bounded recorder diagnostics under warning errors and cancellation."""

import asyncio
import itertools
import json
import warnings

import httpx
import pytest

from repo_catalog.adapters.github.transport import GitHubTransport
from repo_catalog.adapters.recording import RecordingError
from repo_catalog.config import DEFAULTS
from repo_catalog.domain.models import CancellationToken, CatalogError

SECRET = "synthetic-private-recorder-secret"


class BrokenRecorder:
    def __init__(self, error=None):
        self.error = error or RecordingError("ARCHIVE_IO", SECRET)

    def record_exchange(self, context, body):
        raise self.error


def transport(client, *, recorder=None, token=None, clock_us=lambda: 10):
    return GitHubTransport(
        {**DEFAULTS["github"], "max_attempts": 1},
        token or CancellationToken(),
        client=client,
        clock_us=clock_us,
        recorder=recorder or BrokenRecorder(),
    )


@pytest.mark.parametrize("code", [SECRET, SECRET * 1000, [SECRET], None])
def test_custom_error_codes_do_not_escape_as_warning_or_diagnostic_text(code):
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    ) as client:
        http = transport(client, recorder=BrokenRecorder(RecordingError(code, SECRET)))
        with pytest.warns(RuntimeWarning, match="ARCHIVE_FAILURE") as emitted:
            response = http.request("GET", "https://api.github.com/user")
    assert SECRET not in str(emitted[0].message)
    assert response.extensions["repo_catalog_recording_diagnostics"] == [
        {"code": "ARCHIVE_FAILURE", "observed_at_us": 10, "attempt": 1}
    ]


def test_mutated_callback_error_code_is_sanitized_at_transport_boundary():
    error = RecordingError("ARCHIVE_IO", SECRET)
    error.code = SECRET * 1000
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    ) as client:
        http = transport(client, recorder=BrokenRecorder(error))
        with pytest.warns(RuntimeWarning, match="ARCHIVE_FAILURE") as emitted:
            response = http.request("GET", "https://api.github.com/user")
    assert SECRET not in str(emitted[0].message)
    assert SECRET not in json.dumps(http.recording_diagnostics)
    assert response.extensions["repo_catalog_recording_diagnostics"][0]["code"] == (
        "ARCHIVE_FAILURE"
    )


def test_warning_output_hook_failure_keeps_response_and_saved_diagnostics(monkeypatch):
    def broken_warning_output(*args, **kwargs):
        raise OSError(SECRET)

    monkeypatch.setattr(warnings, "showwarning", broken_warning_output)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"id": 10})
        )
    ) as client:
        http = transport(client)
        with warnings.catch_warnings():
            warnings.simplefilter("always", RuntimeWarning)
            response = http.request("GET", "https://api.github.com/user")
    assert response.json() == {"id": 10}
    assert http.recording_diagnostics == [
        {"code": "ARCHIVE_IO", "observed_at_us": 10, "attempt": 1}
    ]


def test_warning_error_filter_keeps_transport_diagnostics_bounded():
    timestamps = itertools.count()
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    ) as client:
        http = transport(client, clock_us=lambda: next(timestamps))
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            for _ in range(105):
                response = http.request("GET", "https://api.github.com/user")
    assert len(http.recording_diagnostics) == 100
    assert [item["observed_at_us"] for item in http.recording_diagnostics] == list(
        range(5, 105)
    )
    assert response.extensions["repo_catalog_recording_diagnostics"] == [
        {"code": "ARCHIVE_IO", "observed_at_us": 104, "attempt": 1}
    ]


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "CREDENTIALS_MISSING"),
        (403, "API_ACCESS"),
        (404, "API_ACCESS"),
        (429, "RATE_LIMIT"),
        (503, "API_SERVER"),
    ],
)
def test_warning_error_filter_preserves_http_failure(status, code):
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json={}))
    ) as client:
        http = transport(client)
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            with pytest.raises(CatalogError) as raised:
                http.request("GET", "https://api.github.com/user")
    assert raised.value.code == code
    assert http.recording_diagnostics[0]["code"] == "ARCHIVE_IO"


@pytest.mark.parametrize("failure", ["network", "protocol", "cancelled", "limit"])
def test_warning_error_filter_preserves_interrupted_exchange_failure(failure):
    token = CancellationToken()

    class InterruptedStream(httpx.SyncByteStream):
        def __iter__(self):
            if failure == "cancelled":
                token.cancelled = True
                yield b"interrupted"
            else:
                for _ in range(33):
                    yield b"x" * (1024 * 1024)

    def respond(request):
        if failure == "network":
            raise httpx.ConnectError(SECRET, request=request)
        if failure == "protocol":
            raise httpx.RemoteProtocolError(SECRET, request=request)
        return httpx.Response(200, stream=InterruptedStream())

    expected = httpx.RemoteProtocolError if failure == "protocol" else CatalogError
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        http = transport(client, token=token)
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            with pytest.raises(expected) as raised:
                http.request("GET", "https://api.github.com/user")
    if failure != "protocol":
        assert (
            raised.value.code
            == {
                "network": "API_NETWORK",
                "cancelled": "CANCELLED",
                "limit": "API_RESPONSE_LIMIT",
            }[failure]
        )
    assert http.recording_diagnostics[0]["code"] == "ARCHIVE_IO"


@pytest.mark.parametrize(
    "error",
    [
        CatalogError("CANCELLED", "synthetic cancelled recording"),
        asyncio.CancelledError(),
        KeyboardInterrupt(),
    ],
)
def test_recorder_cancellation_propagates_without_generic_failure_diagnostic(error):
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    ) as client:
        http = transport(client, recorder=BrokenRecorder(error))
        with pytest.raises(type(error)) as raised:
            http.request("GET", "https://api.github.com/user")
    assert raised.value is error
    assert http.recording_diagnostics == []
