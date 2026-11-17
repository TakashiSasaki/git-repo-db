"""A killed HTTP acquisition preserves only committed facts and retries real work."""

import json
import subprocess
import sys
from uuid import uuid4

import httpx

from tests.e2e.test_separated_cli import init
from tests.e2e.test_separated_cli_provider_regressions import (
    _http_response,
    _network_cli,
    _request_usage,
)
from tests.e2e.test_separated_cli_provider_regressions import (
    provider_case as provider_case,
)

# A real child process exits between committed domain admission and any terminal.
CHILD = r"""
import json, os, signal, sys
import httpx
from repo_catalog.cli.separated_io import authority
from repo_catalog.application.provider_fetch import acquire_github
from repo_catalog.application.provider_acquisition import ProviderAcquisition
catalog, authfile, requestfile = sys.argv[1:]
auth, admission, policy = authority(authfile, 'provider_intake')
request = json.load(open(requestfile))
original = ProviderAcquisition.admit_batch
def admit(self, batch):
    result = original(self, batch)
    if batch.reviews:
        os.kill(os.getpid(), signal.SIGKILL)
    return result
ProviderAcquisition.admit_batch = admit
def handle(http):
    path = http.url.path
    if path.endswith('/pulls'): value = [{'id':20,'number':1}]
    elif path.endswith('/pulls/1'): value = {'id':20,'number':1}
    elif path.endswith('/reviews'): value = [{'id':10,'body':'committed-before-kill'}]
    else: value = {'id':10,'full_name':'owner/repo'}
    return httpx.Response(200,request=http,json=value)
with httpx.Client(transport=httpx.MockTransport(handle)) as client:
    acquire_github(catalog, request, authorization=auth, admission=admission,
                   client=client, clock_us=lambda:100)
raise AssertionError('kill injection was not reached')
"""


def test_normal_cli_retry_after_real_process_kill_keeps_committed_http_prefix_and_original_budget(
    provider_case, tmp_path, capsys, monkeypatch
):
    case = provider_case
    init(capsys, case.directory, "operational")
    request = {
        "operation": "sync",
        "service_instance_uuidv4": case.service,
        "source_registration_uuidv4": case.source,
        "request_identity": [str(uuid4()), str(uuid4())],
        "new_request": True,
        "owner": "owner",
        "repository": "repo",
        "sections": ["reviews"],
        "response_bytes": 8192,
        "rest_base_url": "https://api.example.test",
    }
    path = tmp_path / "crash-request.json"
    path.write_text(json.dumps(request))
    process = subprocess.run(
        [sys.executable, "-c", CHILD, str(case.directory), case.authority, str(path)],
        capture_output=True,
        timeout=30,
    )
    assert process.returncode == -9, process.stderr.decode(errors="replace")
    before = case.view(capsys, case.keys["review"])
    assert list(before["resolved_texts"].values()) == ["committed-before-kill"]
    originals = before["fields"]["text_body_sha256"]
    assert {value["observed_at_us"] for value in originals} == {100}
    parent = case.view(capsys, case.keys["pull"])
    assert not any(row["collection_kind"] == "reviews" for row in parent["collections"])
    from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger

    usage_before = _request_usage(case.directory, request)["input_bytes"]
    calls = []

    def handle(http):
        calls.append(http.url.path)
        if http.url.path.endswith("/pulls"):
            value = [{"id": 20, "number": 1}]
        elif http.url.path.endswith("/pulls/1"):
            value = {"id": 20, "number": 1}
        elif http.url.path.endswith("/reviews"):
            value = [{"id": 10, "body": "committed-before-kill"}]
        else:
            value = {"id": 10, "full_name": "owner/repo"}
        return _http_response(http, value)

    request["new_request"] = False
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        resumed, _ = _network_cli(
            case, tmp_path, capsys, monkeypatch, client, request, clock_us=lambda: 300
        )
    assert resumed["status"] == "complete"
    assert "/repos/owner/repo/pulls/1/reviews" in calls
    after = case.view(capsys, case.keys["review"])
    assert all(
        candidate in after["fields"]["text_body_sha256"] for candidate in originals
    )
    assert list(after["resolved_texts"].values()) == ["committed-before-kill"]
    parent = case.view(capsys, case.keys["pull"])
    review = [
        row for row in parent["collections"] if row["collection_kind"] == "reviews"
    ]
    assert len(review) == 1 and review[0]["state"] == "complete"
    with OperationalAcquisitionLedger(case.directory) as ledger:
        assert (
            ledger.db.execute("SELECT count(*) FROM acquisition_requests").fetchone()[0]
            == 1
        )
    assert _request_usage(case.directory, request)["input_bytes"] > usage_before
