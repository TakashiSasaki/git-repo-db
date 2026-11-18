"""Each actual body producer keeps its own reported response permission scopes."""

import httpx

from tests.e2e.test_separated_cli_provider_regressions import (
    GraphQLFixture,
    _network_cli,
)
from tests.e2e.test_separated_cli_provider_regressions import (
    provider_case as provider_case,
)


def test_actual_http_body_producers_preserve_reported_permissions_without_authority(
    provider_case, tmp_path, capsys, monkeypatch
):
    case, api, header, failed = provider_case, GraphQLFixture(), [None], [False]

    def handle(request):
        if failed[0] and request.method == "POST":
            return httpx.Response(401, json={"message": "No new body was observed"})
        response = api.response(request)
        if header[0] is not None:
            response.headers["X-OAuth-Scopes"] = header[0]
        return response

    originals = []
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        request = None
        for value, expected in (
            (" repo, read:org, repo ", ["read:org", "repo"]),
            ("", []),
            (None, None),
            ("admin:org", ["admin:org"]),
        ):
            header[0] = value
            if request is not None:
                request["new_request"] = False
            report, request = _network_cli(
                case, tmp_path, capsys, monkeypatch, client, request
            )
            assert report["status"] == "complete"
            view = case.view(capsys, case.keys["comment"])
            current = [
                candidate
                for candidate in view["fields"]["text_body_sha256"]
                if candidate not in originals
            ]
            assert len(current) == 1
            assert (
                current[0]["provenance"]["evidence"]["read_origin"][
                    "reported_oauth_scopes"
                ]
                == expected
            )
            assert (
                current[0]["provenance"]["evidence"]["request_identity"]
                == request["request_identity"]
            )
            assert all(
                original in view["fields"]["text_body_sha256"] for original in originals
            )
            assert list(view["resolved_texts"].values()) == ["comment-10"]
            originals.extend(current)
        before = case.view(capsys, case.keys["thread"])["collections"]
        failed[0] = True
        result, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
    assert (
        result["status"] == "partial"
        and result["failure_code"] == "CREDENTIALS_MISSING"
    )
    retained = case.view(capsys, case.keys["comment"])["fields"]["text_body_sha256"]
    assert len(retained) == len(originals) and all(
        original in retained for original in originals
    )
    assert case.view(capsys, case.keys["thread"])["collections"] == before
    assert not (case.directory / "access.sqlite3").exists()
    assert not (case.directory / "repository.sqlite3").exists()
