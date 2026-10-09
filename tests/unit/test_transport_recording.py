import copy
import gzip
import json
import os

import httpx
import pytest

from repo_catalog.adapters.github.transport import GitHubTransport
from repo_catalog.adapters.recording import (
    BODY_REPRESENTATION,
    DisabledRecorder,
    LocalArchiveReader,
    LocalFileRecorder,
    RecordingError,
    recorder_from_config,
)
from repo_catalog.config import DEFAULTS, validate
from repo_catalog.domain.models import CancellationToken, CatalogError, Waiting


class Credentials:
    def get(self):
        return "synthetic-private-token"


def references(path):
    return sorted(entry.stem for entry in path.glob("*.json"))


def transport(client, recorder=None, *, max_attempts=3):
    return GitHubTransport(
        {**DEFAULTS["github"], "max_attempts": max_attempts},
        CancellationToken(),
        client=client,
        credentials=Credentials(),
        clock_us=lambda: 1_234_567,
        recorder=recorder,
    )


def test_capture_preserves_decoded_bytes_and_redacts_metadata_before_recorder(tmp_path):
    body = b'{"body":"exact\\r\\ntext", "original":"synthetic-private-token"}\n'
    path = tmp_path / "transport-archive"
    seen = []
    persistent = LocalFileRecorder(path)

    class SpyRecorder:
        def record_exchange(self, context, raw):
            seen.append(context)
            return persistent.record_exchange(context, raw)

    def respond(request):
        assert request.headers["authorization"] == "Bearer synthetic-private-token"
        return httpx.Response(
            200,
            headers={
                "content-encoding": "gzip",
                "content-type": "application/json",
                "set-cookie": "session=synthetic-cookie-secret",
                "x-unsafe": "synthetic-header-secret",
                "etag": '"synthetic-validator"',
            },
            content=gzip.compress(body),
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        response = transport(client, SpyRecorder()).request(
            "GET",
            "https://api.github.com/repos/example/project/issues",
            params={
                "state": "closed",
                "access_token": "synthetic-query-secret",
                "page": 2,
                "api_key": "synthetic-other-secret",
            },
            headers={"Cookie": "session=synthetic-request-cookie"},
            record_context={
                "provider_request_kind": "issue-list",
                "owner": "example",
                "repository": "project",
                "pr_number": 5,
                "authorization": "synthetic-context-secret",
            },
        )
    assert response.content == body
    assert "content-encoding" not in response.headers
    assert response.extensions["catalog_observed_at_us"] == 1_234_567
    reference = response.extensions["repo_catalog_archive_ref"]
    message = LocalArchiveReader(path).read(reference)
    assert message.body == body
    assert message.body_representation == BODY_REPRESENTATION
    assert message.context == seen[0]
    assert message.context["metadata_redacted"] is True
    assert message.context["response_headers"]["content-encoding"] == "gzip"
    assert message.context["provider_context"] == {
        "provider_request_kind": "issue-list",
        "owner": "example",
        "repository": "project",
        "pr_number": 5,
    }
    metadata = (path / (reference + ".json")).read_text()
    for secret in (
        "synthetic-private-token",
        "synthetic-cookie-secret",
        "synthetic-header-secret",
        "synthetic-query-secret",
        "synthetic-other-secret",
        "synthetic-request-cookie",
        "synthetic-context-secret",
    ):
        assert secret not in metadata
    assert "state=closed" in message.context["url"]
    assert "page=2" in message.context["url"]
    # Metadata is intentionally redacted; source body evidence remains exact.
    assert b"synthetic-private-token" in message.body
    assert os.stat(path / (reference + ".body")).st_mode & 0o777 == 0o600


def test_disabled_recorder_does_not_create_any_archive(tmp_path):
    recorder = recorder_from_config(DEFAULTS["github"], tmp_path)
    assert isinstance(recorder, DisabledRecorder)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"id": 1})
        )
    ) as client:
        response = transport(client, recorder).request(
            "GET", "https://api.github.com/user"
        )
    assert response.extensions["repo_catalog_archive_ref"] is None
    assert response.extensions["repo_catalog_recording_diagnostics"] == []
    assert not (tmp_path / "transport-archive").exists()
    enabled = recorder_from_config({"record_messages": True}, tmp_path)
    assert isinstance(enabled, LocalFileRecorder)
    assert (
        not enabled.path.exists()
    )  # Initialization itself never requires archive access.


def test_capture_failure_is_visible_and_preserves_valid_http_response(tmp_path):
    blocked = tmp_path / "transport-archive"
    blocked.write_bytes(b"synthetic unavailable archive")
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"id": 1})
        )
    ) as client:
        http = transport(client, LocalFileRecorder(blocked))
        with pytest.warns(RuntimeWarning, match="ARCHIVE_IO"):
            response = http.request("GET", "https://api.github.com/user")
    assert response.json() == {"id": 1}
    assert response.extensions["repo_catalog_archive_ref"] is None
    assert response.extensions["repo_catalog_recording_diagnostics"] == [
        {"code": "ARCHIVE_IO", "observed_at_us": 1_234_567, "attempt": 1}
    ]
    assert (
        http.recording_diagnostics
        == response.extensions["repo_catalog_recording_diagnostics"]
    )


@pytest.mark.parametrize(
    "error", [ValueError("synthetic bug"), httpx.ConnectError("recorder bug")]
)
def test_unexpected_recorder_errors_do_not_become_transport_retries(error):
    requests = []

    class BrokenRecorder:
        def record_exchange(self, context, body):
            raise error

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        http = transport(client, BrokenRecorder())
        with pytest.warns(RuntimeWarning, match="ARCHIVE_FAILURE") as warnings:
            response = http.request("GET", "https://api.github.com/user")
    assert response.json() == {}
    assert str(error) not in str(warnings[0].message)
    assert http.recording_diagnostics == [
        {"code": "ARCHIVE_FAILURE", "observed_at_us": 1_234_567, "attempt": 1}
    ]
    assert len(requests) == 1


def test_each_network_retry_and_server_response_has_separate_capture(tmp_path):
    count = 0

    def respond(request):
        nonlocal count
        count += 1
        if count == 1:
            raise httpx.ConnectError(
                "synthetic-token-must-not-be-recorded", request=request
            )
        if count == 2:
            return httpx.Response(503, json={"message": "synthetic server failure"})
        return httpx.Response(200, json={"id": 3})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        response = transport(client, LocalFileRecorder(tmp_path)).request(
            "GET", "https://api.github.com/user?token=synthetic-url-secret"
        )
    assert response.json() == {"id": 3}
    reader = LocalArchiveReader(tmp_path)
    messages = sorted(
        (reader.read(ref) for ref in references(tmp_path)),
        key=lambda m: m.context["attempt"],
    )
    assert len(messages) == 3
    assert messages[0].body is None
    assert messages[0].context["failure_code"] == "API_NETWORK"
    assert messages[1].context["response_status"] == 503
    assert messages[2].context["response_status"] == 200
    for reference in references(tmp_path):
        assert (
            "synthetic-token-must-not-be-recorded"
            not in (tmp_path / (reference + ".json")).read_text()
        )


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
def test_http_failure_capture_does_not_change_failure_semantics(tmp_path, status, code):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json={"synthetic": "failure"})
        )
    ) as client:
        with pytest.raises(CatalogError) as raised:
            transport(client, LocalFileRecorder(tmp_path), max_attempts=1).request(
                "GET", "https://api.github.com/user"
            )
    assert raised.value.code == code
    if status == 429:
        assert isinstance(raised.value, Waiting)
    message = LocalArchiveReader(tmp_path).read(references(tmp_path)[0])
    assert message.context["response_status"] == status
    assert json.loads(message.body) == {"synthetic": "failure"}


def test_recording_failure_does_not_suppress_network_failure():
    class BrokenRecorder:
        def record_exchange(self, context, body):
            raise RecordingError("ARCHIVE_IO", "synthetic archive failure")

    def fail(request):
        raise httpx.ConnectError("synthetic network failure", request=request)

    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        with (
            pytest.warns(RuntimeWarning, match="ARCHIVE_IO"),
            pytest.raises(CatalogError) as raised,
        ):
            transport(client, BrokenRecorder(), max_attempts=1).request(
                "GET", "https://api.github.com/user"
            )
    assert raised.value.code == "API_NETWORK"


def test_capture_never_labels_partial_stream_as_complete_body(tmp_path):
    class FailingStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"partial source text"
            raise httpx.ReadError("synthetic interrupted body")

    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, stream=FailingStream())
        )
    ) as client:
        with pytest.raises(CatalogError) as raised:
            transport(client, LocalFileRecorder(tmp_path), max_attempts=1).request(
                "GET", "https://api.github.com/user"
            )
    assert raised.value.code == "API_NETWORK"
    message = LocalArchiveReader(tmp_path).read(references(tmp_path)[0])
    assert message.body is None
    assert message.context["failure_code"] == "API_NETWORK"
    assert message.context["response_status"] == 200


def archive_body(path, body=b"synthetic body"):
    return LocalFileRecorder(path).record_exchange(
        {
            "method": "GET",
            "url": "https://api.github.com/user",
            "observed_at_us": -1,
            "attempt": 1,
            "response_status": 200,
        },
        body,
    )


def test_reader_is_bounded_and_does_not_mutate_original_observation(tmp_path):
    reference = archive_body(tmp_path)
    reader = LocalArchiveReader(tmp_path)
    with pytest.raises(RecordingError) as raised:
        reader.read(reference, max_body_bytes=4)
    assert raised.value.code == "ARCHIVE_LIMIT"
    assert reader.read(reference).context["observed_at_us"] == -1
    assert reader.read(reference).body == b"synthetic body"
    assert len(references(tmp_path)) == 1


@pytest.mark.parametrize("entry_type", ["symlink", "fifo"])
def test_reader_rejects_special_files_without_following_or_blocking(
    tmp_path, entry_type
):
    reference = archive_body(tmp_path)
    body_path = tmp_path / (reference + ".body")
    body_path.unlink()
    if entry_type == "symlink":
        target = tmp_path / "synthetic-external-body"
        target.write_bytes(b"synthetic body")
        body_path.symlink_to(target)
    else:
        os.mkfifo(body_path)
    with pytest.raises(RecordingError) as raised:
        LocalArchiveReader(tmp_path).read(reference)
    assert raised.value.code in ("ARCHIVE_IO", "ARCHIVE_CORRUPT")


def test_reader_rejects_duplicate_metadata_keys(tmp_path):
    reference = archive_body(tmp_path)
    metadata_path = tmp_path / (reference + ".json")
    metadata = metadata_path.read_text()
    metadata_path.write_text(
        metadata.replace(
            '"archive_version":1', '"archive_version":0,"archive_version":1'
        )
    )
    with pytest.raises(RecordingError) as raised:
        LocalArchiveReader(tmp_path).read(reference)
    assert raised.value.code == "ARCHIVE_CORRUPT"


@pytest.mark.parametrize(
    "change",
    [
        "missing-body",
        "changed-body",
        "wrong-length",
        "wrong-representation",
        "missing-context",
        "boolean-time",
        "unsafe-header",
        "unsafe-context",
    ],
)
def test_missing_or_corrupt_archive_is_investigation_failure_only(tmp_path, change):
    reference = archive_body(tmp_path)
    metadata_path = tmp_path / (reference + ".json")
    body_path = tmp_path / (reference + ".body")
    envelope = json.loads(metadata_path.read_text())
    if change == "missing-body":
        body_path.unlink()
    elif change == "changed-body":
        body_path.write_bytes(b"different body")
    elif change == "wrong-length":
        envelope["body_length"] = 0
    elif change == "wrong-representation":
        envelope["body_representation"] = "raw-wire-v1"
    elif change == "missing-context":
        del envelope["context"]
    elif change == "boolean-time":
        envelope["context"]["observed_at_us"] = True
    elif change == "unsafe-header":
        envelope["context"]["request_headers"]["authorization"] = "synthetic secret"
    else:
        envelope["context"]["provider_context"] = {"credentials": "synthetic secret"}
    metadata_path.write_text(json.dumps(envelope))
    with pytest.raises(RecordingError) as raised:
        LocalArchiveReader(tmp_path).read(reference)
    assert raised.value.code in ("ARCHIVE_MISSING", "ARCHIVE_CORRUPT")
    # The reader has no store/transport and cannot retract previously admitted state.


@pytest.mark.parametrize(
    "reference",
    ["../secret", "a" * 1000, "", "00000000-0000-5000-8000-000000000001", None],
)
def test_reader_rejects_noncanonical_references(tmp_path, reference):
    with pytest.raises(RecordingError) as raised:
        LocalArchiveReader(tmp_path).read(reference)
    assert raised.value.code == "ARCHIVE_ARGUMENT"


@pytest.mark.parametrize("value", ["false", 0, 1, None, []])
def test_recording_configuration_requires_boolean(value):
    config = copy.deepcopy(DEFAULTS)
    config["cache"].update(max_bytes=1000, min_free_bytes=0)
    config["github"]["record_messages"] = value
    with pytest.raises(CatalogError) as raised:
        validate(config)
    assert raised.value.code == "CONFIG_ERROR"
