"""REST retries keep admitted review units, exact originals and cumulative work."""

import json

import httpx
import pytest

from repo_catalog.adapters.github.production_intake import make_document_key
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.pr_assessment import PRQueryService
from repo_catalog.domain.context_admission import AdmissionSelection, DependencySet
from tests.e2e.test_context_response_boundary_retirement import request_document
from tests.e2e.test_separated_cli import document
from tests.e2e.test_separated_cli_provider_regressions import (
    _http_response,
    _network_cli,
    _request_usage,
)
from tests.e2e.test_separated_cli_provider_regressions import (
    provider_case as provider_case,
)

PREFIX = "committed\x00prefix\r\n"
PENDING = "accepted second-page unit"
CORRECTED = "corrected response 認証 🦉"
REJECTED = "REJECTED-MODELED-BODY-MARKER"
BAD_ITEMS = [
    ("null-item", None),
    ("string-item", "unexpected scalar"),
    ("integer-item", 42),
    ("array-item", []),
    ("user-scalar", {"id": 13, "body": REJECTED, "user": "writer"}),
    ("user-login-array", {"id": 13, "body": REJECTED, "user": {"login": []}}),
    ("author-array", {"id": 13, "body": REJECTED, "author": ["writer"]}),
    ("body-array", {"id": 13, "body": [REJECTED]}),
    ("url-object", {"id": 13, "body": REJECTED, "html_url": {}}),
    ("target-integer", {"id": 13, "body": REJECTED, "commit_id": 5}),
    ("target-nonhex", {"id": 13, "body": REJECTED, "commit_id": "not-an-oid"}),
    ("author-surrogate", {"id": 13, "body": REJECTED, "user": {"login": "\ud800"}}),
    ("url-surrogate", {"id": 13, "body": REJECTED, "html_url": "\udfff"}),
    ("target-whitespace", {"id": 13, "body": REJECTED, "commit_id": "aa" * 19 + "  "}),
]


def prepare(case, tmp_path):
    for value in (10, 11, 12, 13):
        case.keys[f"rest_review_{value}"] = make_document_key(
            case.keys["pull"], "review", "review_summary", str(value)
        )
    case.authority = document(
        tmp_path,
        "rest-prefix-authority.json",
        {
            "grants": DependencySet(
                resources=frozenset(case.keys.values()),
                sources={case.source},
                provider_registrations={case.service},
            ),
            "selection": AdmissionSelection(all_selected=True),
        },
    )


def bodies(case):
    with Context.snapshot(case.directory) as context:
        return {
            row[0] for row in context.db.execute("SELECT text_value FROM text_bodies")
        }


def proof_view(case, capsys):
    return [
        item
        for item in case.view(capsys, case.keys["pull"])["collections"]
        if item["collection_kind"] == "reviews"
    ]


@pytest.mark.parametrize(
    "case_name,bad_item", BAD_ITEMS, ids=[item[0] for item in BAD_ITEMS]
)
def test_actual_rest_review_rejection_keeps_units_and_retries_root_under_original_budget(
    provider_case, tmp_path, capsys, monkeypatch, case_name, bad_item
):
    case, blocked, stamp, pages = provider_case, [True], [100], []
    prepare(case, tmp_path)
    prefix = {"id": 10, "body": PREFIX}
    pending = {"id": 11, "body": PENDING}
    corrected = {"id": 12, "body": CORRECTED, "user": None}

    def handle(http):
        path = http.url.path
        if path.endswith("/reviews"):
            page = http.url.params.get("page")
            pages.append(page)
            assert page in (None, "2"), (
                "A rejected later cursor cannot become a retry target"
            )
            if page is None:
                response = _http_response(http, [prefix])
                next_page = 2
            else:
                response = _http_response(
                    http, [pending, bad_item] if blocked[0] else [pending, corrected]
                )
                next_page = 3 if blocked[0] else None
            if next_page:
                response.headers["link"] = (
                    f'<https://api.example.test/repos/owner/repo/pulls/1/reviews?page={next_page}>; rel="next"'
                )
            return response
        if path.endswith("/pulls"):
            return _http_response(http, [{"id": 20, "number": 1}])
        if path.endswith("/pulls/1"):
            return _http_response(http, {"id": 20, "number": 1})
        assert path == "/repos/owner/repo"
        return _http_response(http, {"id": 10, "full_name": "owner/repo"})

    request = request_document(case)
    request["max_pages"] = 10  # Five actual requests in each of the two traversals.
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        failed, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request,
            clock_us=lambda: stamp[0],
        )
        assert failed["status"] == "partial" and failed["failure_code"]
        assert failed["http_attempts"] == 5 and pages == [None, "2"]
        assert bodies(case) == {PREFIX, PENDING}
        with Context.snapshot(case.directory) as context:
            originals = {
                key: context.candidates(key, "text_body_sha256")
                for key in (case.keys["rest_review_10"], case.keys["rest_review_11"])
            }
            assert all(
                len(values) == 1 and values[0].observed_at_us == 100
                for values in originals.values()
            )
            assert (
                context.db.execute(
                    "SELECT 1 FROM resources WHERE service_instance_uuidv4=? "
                    "AND resource_kind=? AND provider_resource_id=?",
                    case.keys["rest_review_13"].coordinates(),
                ).fetchone()
                is None
            )
        partial = proof_view(case, capsys)
        assert partial and all(item["state"] == "partial" for item in partial)
        assert any(
            item["members"]
            == [
                list(case.keys["rest_review_10"].coordinates()),
                list(case.keys["rest_review_11"].coordinates()),
            ]
            for item in partial
        )
        usage = _request_usage(case.directory, request)
        assert usage["input_bytes"] > 0 and usage["metadata_units"] > 0
        blocked[0], stamp[0], request["new_request"] = False, 200, False
        recovered, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request,
            clock_us=lambda: stamp[0],
        )
        assert recovered["status"] == "complete" and recovered["http_attempts"] == 5
        assert (
            recovered["request_identity"]["request_uuidv4"]
            == request["request_identity"][1]
        )
        assert pages == [None, "2", None, "2"]
        new_usage = _request_usage(case.directory, request)
        assert all(new_usage[unit] >= amount for unit, amount in usage.items())
        assert new_usage["input_bytes"] > usage["input_bytes"]
        assert bodies(case) == {PREFIX, PENDING, CORRECTED}
        with Context.snapshot(case.directory) as context:
            for key, values in originals.items():
                assert set(values) <= set(context.candidates(key, "text_body_sha256"))
            assert (
                context.candidates(case.keys["rest_review_12"], "author")[0].value_json
                == "null"
            )
            assert context.db.execute("PRAGMA foreign_key_check").fetchall() == []
        result = PRQueryService(case.directory).get_pr_documents(
            case.keys["pull"], kinds=("reviews",)
        )
        assert result.state == "complete" and len(result.page.items) == 3
        prior = proof_view(case, capsys)
        assert all(item in prior for item in partial)
        assert any(
            item["state"] == "complete" and len(item["members"]) == 3 for item in prior
        )
        exhausted, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request,
            clock_us=lambda: stamp[0],
        )
    assert (
        exhausted["status"] == "partial" and exhausted["failure_code"] == "PAGE_LIMIT"
    )
    assert exhausted["http_attempts"] == 0 and pages == [None, "2", None, "2"]
    assert proof_view(case, capsys) == prior
    assert not (case.directory / "transport-archive").exists()
    assert not (case.directory / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("unknown_shape", ["value-surrogate", "key-surrogate"])
def test_unknown_rest_metadata_cannot_become_an_opaque_replica_field(
    provider_case, tmp_path, capsys, monkeypatch, unknown_shape
):
    case, pages = provider_case, []
    prepare(case, tmp_path)
    unknown = (
        {"nested": ["UNKNOWN-REPLICA-MARKER", "\ud800"]}
        if unknown_shape == "value-surrogate"
        else {"\ud800": "UNKNOWN-REPLICA-MARKER"}
    )

    def handle(http):
        path = http.url.path
        if path.endswith("/reviews"):
            pages.append(http.url.params.get("page"))
            if len(pages) == 1:
                response = _http_response(http, [{"id": 10, "body": PREFIX}])
                response.headers["link"] = (
                    '<https://api.example.test/repos/owner/repo/pulls/1/reviews?page=2>; rel="next"'
                )
                return response
            return _http_response(
                http,
                [
                    {"id": 11, "body": PENDING},
                    {"id": 13, "body": "legitimate modeled text", "unknown": unknown},
                ],
            )
        if path.endswith("/pulls"):
            return _http_response(http, [{"id": 20, "number": 1}])
        if path.endswith("/pulls/1"):
            return _http_response(http, {"id": 20, "number": 1})
        return _http_response(http, {"id": 10, "full_name": "owner/repo"})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        report, _ = _network_cli(
            case, tmp_path, capsys, monkeypatch, client, request_document(case)
        )
    assert report["status"] == "complete" and pages == [None, "2"]
    assert bodies(case) == {PREFIX, PENDING, "legitimate modeled text"}
    with Context.snapshot(case.directory) as context:
        key = case.keys["rest_review_13"]
        assert context.candidates(key, "unknown") == ()
        rows = context.db.execute(
            "SELECT value_json,provenance_json FROM field_candidates "
            "WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
            key.coordinates(),
        ).fetchall()
        encoded = json.dumps([tuple(row) for row in rows])
        assert "UNKNOWN-REPLICA-MARKER" not in encoded and "\\ud800" not in encoded
        assert context.db.execute("PRAGMA foreign_key_check").fetchall() == []
    result = PRQueryService(case.directory).get_pr_documents(
        case.keys["pull"], kinds=("reviews",)
    )
    assert result.state == "complete" and len(result.page.items) == 3
    assert not (case.directory / "transport-archive").exists()
    assert not (case.directory / "p1-recovery-stop.json").exists()
