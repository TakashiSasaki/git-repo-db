"""Real HTTP transport -> normalized Context, with no legacy Store composition."""

import gzip
import json
from contextlib import closing
from uuid import uuid4

import httpx
import pytest

from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.application.provider_fetch import acquire_github
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.p1_context import ResourceKey
from tests.integration.p5.conftest import init_catalog_stores
from tests.support.context_admission import fixture_context, fixture_service


def setup(tmp_path):
    init_catalog_stores(tmp_path, stores=("context", "operational"))
    service, source = str(uuid4()), str(uuid4())
    grants = DependencySet(
        resources=frozenset(
            ResourceKey.from_native(service, kind, str(identifier))
            for kind, identifier in (("repository", 10), ("issue", 20), ("issue", 21))
        )
        | frozenset(
            {
                ResourceKey.document(
                    ResourceKey.from_native(service, "issue", "20"),
                    "comment",
                    "timeline_event",
                    "30",
                )
            }
        ),
        sources=frozenset({source}),
        provider_registrations=frozenset({service}),
    )
    authorization, _ = fixture_service(grants)
    admission = fixture_context(authorization)
    document = {
        "operation": "sync",
        "service_instance_uuidv4": service,
        "source_registration_uuidv4": source,
        "request_identity": [str(uuid4()), str(uuid4())],
        "new_request": True,
        "owner": "owner",
        "repository": "repo",
        "sections": ["issues"],
        "response_bytes": 4096,
        "rest_base_url": "https://api.example.test",
        "graphql_url": "https://api.example.test/graphql",
    }
    return document, authorization, admission


def response(request, value, **headers):
    raw = json.dumps(value).encode()
    return httpx.Response(
        200, request=request, headers=headers, stream=httpx.ByteStream(raw)
    )


def test_http_pagination_admits_pages_and_complete_exact_scope(tmp_path):
    document, authorization, admission = setup(tmp_path)
    calls, byte_counts = [], []

    def handle(request):
        calls.append(str(request.url))
        if request.url.path == "/repos/owner/repo":
            result = response(
                request, {"id": 10, "full_name": "owner/repo", "private": False}
            )
        elif request.url.params.get("page") == "2":
            result = response(request, [{"id": 21, "number": 2, "title": "second"}])
        else:
            result = response(
                request,
                [{"id": 20, "number": 1, "title": "first", "body": "context text"}],
                link='<https://api.example.test/repos/owner/repo/issues?page=2>; rel="next"',
            )
        byte_counts.append(sum(map(len, result.stream)))
        return result

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        report = acquire_github(
            tmp_path,
            document,
            authorization=authorization,
            admission=admission,
            client=client,
        )
    assert report.status == "complete"
    assert report.network_bytes == sum(byte_counts)
    assert report.http_attempts == len(calls) == 3
    assert report.batches[-1].collection_proofs[0][0].state == "complete"
    assert len(report.batches[-1].collection_proofs[0][1].members) == 2
    assert not (tmp_path / "core.sqlite3").exists()
    with closing(connect(tmp_path / "context.sqlite3", "context")) as context:
        assert len(context.execute("SELECT * FROM text_bodies").fetchall()) == 1


def test_budget_stop_retains_page_prefix_and_reports_partial(tmp_path):
    document, authorization, admission = setup(tmp_path)
    document["max_pages"] = 2

    calls = []

    def handle(request):
        calls.append(request)
        if request.url.path == "/repos/owner/repo":
            return response(request, {"id": 10, "full_name": "owner/repo"})
        return response(
            request,
            [{"id": 20, "number": 1}],
            link='<https://api.example.test/repos/owner/repo/issues?page=2>; rel="next"',
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        report = acquire_github(
            tmp_path,
            document,
            authorization=authorization,
            admission=admission,
            client=client,
        )
        document["new_request"] = False
        resumed = acquire_github(
            tmp_path,
            document,
            authorization=authorization,
            admission=admission,
            client=client,
        )
        assert resumed.failure_code == "PAGE_LIMIT"
        assert resumed.http_attempts == 0
        assert len(calls) == 2
    assert report.failure_code == "PAGE_LIMIT"
    assert report.status == "partial"
    assert report.batches[-1].collection_proofs[0][0].state == "partial"
    assert not (tmp_path / "p1-recovery-stop.json").exists()
    with closing(connect(tmp_path / "context.sqlite3", "context")) as context:
        assert (
            context.execute(
                "SELECT count(*) FROM resources WHERE resource_kind='issue'"
            ).fetchone()[0]
            == 1
        )


def test_retry_and_compressed_response_charge_actual_wire_body_bytes(tmp_path):
    document, authorization, admission = setup(tmp_path)
    document.update(operation="discover", include_repositories=["repo"])
    attempts = []
    principal = gzip.compress(json.dumps({"id": 1, "login": "owner"}).encode())
    raw = json.dumps({"id": 10, "full_name": "owner/repo"}).encode()
    compressed = gzip.compress(raw)

    def handle(request):
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(503, stream=httpx.ByteStream(b"retry"))
        return httpx.Response(
            200,
            headers={"content-encoding": "gzip"},
            stream=httpx.ByteStream(
                principal if request.url.path == "/user" else compressed
            ),
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        first = acquire_github(
            tmp_path,
            document,
            authorization=authorization,
            admission=admission,
            client=client,
        )
        document["new_request"] = False
        second = acquire_github(
            tmp_path,
            document,
            authorization=authorization,
            admission=admission,
            client=client,
        )
    assert first.status == second.status == "complete"
    assert [r.url.path for r in attempts] == [
        "/user",
        "/user",
        "/repos/owner/repo",
        "/user",
        "/repos/owner/repo",
    ]
    assert first.network_bytes == 5 + len(principal) + len(compressed)
    assert second.network_bytes == len(principal) + len(compressed)
    from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger

    with OperationalAcquisitionLedger(tmp_path) as ledger:
        # Distinct attempts share one request identity and cumulative actual work.
        rows = ledger.db.execute(
            "SELECT count(*) FROM acquisition_requests"
        ).fetchone()[0]
        assert rows == 1


def test_cross_origin_next_page_does_not_receive_credentials(tmp_path):
    document, authorization, admission = setup(tmp_path)
    sent = []

    class Credential:
        def get(self):
            return "secret-test-token"

    def handle(request):
        sent.append(request)
        if request.url.path == "/repos/owner/repo":
            return response(request, {"id": 10, "full_name": "owner/repo"})
        return response(
            request,
            [{"id": 20, "number": 1}],
            link='<https://other.invalid/stolen>; rel="next"',
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        report = acquire_github(
            tmp_path,
            document,
            authorization=authorization,
            admission=admission,
            credentials=Credential(),
            client=client,
        )
    assert report.failure_code == "UNSAFE_API_URL"
    assert all(r.url.host == "api.example.test" for r in sent)
    assert "secret-test-token" not in repr(report)


@pytest.mark.parametrize("extra_identity", [{}, {"node_id": "actual-provider-node"}])
def test_idless_rest_timeline_preserves_current_page_prefix_without_fabricated_id(
    tmp_path, extra_identity
):
    document, authorization, admission = setup(tmp_path)
    document["sections"] = ["timeline"]

    def handle(request):
        if request.url.path == "/repos/owner/repo":
            return response(request, {"id": 10, "full_name": "owner/repo"})
        if request.url.path.endswith("/timeline"):
            return response(
                request,
                [
                    {"id": 30, "event": "closed"},
                    {"event": "committed", "sha": "a" * 40, **extra_identity},
                ],
            )
        if request.url.path.endswith("/pulls"):
            return response(request, [])
        return response(request, [{"id": 20, "number": 1, "title": "admissible issue"}])

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        report = acquire_github(
            tmp_path,
            document,
            authorization=authorization,
            admission=admission,
            client=client,
        )
    assert report.status == "partial"
    assert report.failure_code == "CANONICAL_ID_REQUIRED"
    assert report.batches[-1].collection_proofs[0][0].state == "partial"
    assert len(report.batches[-1].collection_proofs[0][1].members) == 1
    with closing(connect(tmp_path / "context.sqlite3", "context")) as context:
        # The Issue and preceding actual event survive the unsupported row.
        assert (
            context.execute(
                "SELECT count(*) FROM resources WHERE resource_kind='issue'"
            ).fetchone()[0]
            == 1
        )
        assert (
            context.execute(
                "SELECT count(*) FROM resources WHERE resource_kind='comment'"
            ).fetchone()[0]
            == 1
        )
