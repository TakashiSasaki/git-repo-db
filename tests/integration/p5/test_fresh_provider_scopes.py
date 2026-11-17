"""Explicit fresh HTTP scopes never use an old validator or silently adopt a route."""

import json
from uuid import uuid4

import httpx

from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.context_query import ContextQueryService
from repo_catalog.application.provider_fetch import acquire_github
from repo_catalog.domain.p1_context import ResourceKey
from tests.integration.p5.test_separated_github_fetch import response, setup


def test_repeated_fresh_reads_ignore_etag_and_304_never_creates_a_new_body_original(
    tmp_path,
):
    document, authorization, admission = setup(tmp_path)
    service = document["service_instance_uuidv4"]
    key = ResourceKey.from_native(service, "issue", "20")
    stamp, mode, requests = [100], ["body"], []
    opaque = '"unmodeled-etag-must-not-enter-domain"'

    def handle(request):
        requests.append(request)
        if request.url.path == "/repos/owner/repo":
            result = response(request, {"id": 10, "full_name": "owner/repo"})
        elif mode[0] == "304":
            return httpx.Response(304, headers={"ETag": opaque})
        else:
            result = response(
                request,
                [{"id": 20, "number": 1, "body": "genuine body", "updated_at": 10}],
            )
        result.headers["ETag"] = opaque
        return result

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        for stamp[0] in (100, 200):
            document["request_identity"] = [str(uuid4()), str(uuid4())]
            result = acquire_github(
                tmp_path,
                document,
                authorization=authorization,
                admission=admission,
                client=client,
                clock_us=lambda: stamp[0],
            )
            assert result.status == "complete"
        with Context.snapshot(tmp_path) as context:
            originals = context.candidates(key, "text_body_sha256")
        assert len(originals) == 2
        assert {candidate.observed_at_us for candidate in originals} == {100, 200}
        assert len({candidate.provenance_json for candidate in originals}) == 2
        mode[0], stamp[0] = "304", 300
        document["request_identity"] = [str(uuid4()), str(uuid4())]
        failed = acquire_github(
            tmp_path,
            document,
            authorization=authorization,
            admission=admission,
            client=client,
            clock_us=lambda: stamp[0],
        )
    assert failed.status == "partial"
    assert all(
        "if-none-match" not in request.headers
        and "if-modified-since" not in request.headers
        for request in requests
    )
    with Context.snapshot(tmp_path) as context:
        assert context.candidates(key, "text_body_sha256") == originals
    view = ContextQueryService(tmp_path, mode="context_only").get_context_resource(
        key, include_text=True
    )
    assert list(view.resolved_texts.values()) == ["genuine body"]
    assert opaque not in json.dumps(view.to_dict())
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def test_redirect_does_not_adopt_another_scope_but_explicit_new_name_keeps_native_identity(
    tmp_path,
):
    document, authorization, admission = setup(tmp_path)
    key = ResourceKey.from_native(document["service_instance_uuidv4"], "issue", "20")
    phase, calls = ["original"], []

    def handle(request):
        calls.append(request.url.path)
        if phase[0] == "redirect":
            return httpx.Response(
                301,
                headers={"Location": "https://api.example.test/repos/owner/renamed"},
            )
        repository = "renamed" if phase[0] == "renamed" else "repo"
        if request.url.path == f"/repos/owner/{repository}":
            return response(request, {"id": 10, "full_name": f"owner/{repository}"})
        assert request.url.path == f"/repos/owner/{repository}/issues"
        return response(
            request,
            [
                {
                    "id": 20,
                    "number": 1,
                    "body": "new explicit scope"
                    if repository == "renamed"
                    else "original scope",
                    "updated_at": 20 if repository == "renamed" else 10,
                }
            ],
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        first = acquire_github(
            tmp_path,
            document,
            authorization=authorization,
            admission=admission,
            client=client,
        )
        assert first.status == "complete"
        with Context.snapshot(tmp_path) as context:
            original = context.candidates(key, "text_body_sha256")
        phase[0] = "redirect"
        document["request_identity"] = [str(uuid4()), str(uuid4())]
        before = len(calls)
        refused = acquire_github(
            tmp_path,
            document,
            authorization=authorization,
            admission=admission,
            client=client,
        )
        assert refused.status == "partial"
        assert calls[before:] == ["/repos/owner/repo"]
        with Context.snapshot(tmp_path) as context:
            assert context.candidates(key, "text_body_sha256") == original
        phase[0] = "renamed"
        document.update(
            repository="renamed", request_identity=[str(uuid4()), str(uuid4())]
        )
        actual = acquire_github(
            tmp_path,
            document,
            authorization=authorization,
            admission=admission,
            client=client,
        )
        assert actual.status == "complete"
    with Context.snapshot(tmp_path) as context:
        (current,) = context.candidates(key, "text_body_sha256")
        assert context.read_text(json.loads(current.value_json)) == "new explicit scope"
        assert (
            json.loads(current.provenance_json)["evidence"]["resource_path"]
            == "/repos/owner/renamed/issues"
        )
        assert current.provenance_json != original[0].provenance_json
    assert not (tmp_path / "p1-recovery-stop.json").exists()
