"""Provider document selection uses exact Provider scope independently of Git bytes."""

from uuid import uuid4

import httpx

from repo_catalog.adapters.github.production_intake import (
    normalize_pr_commit,
    normalize_pr_file,
)
from repo_catalog.domain.context_admission import AdmissionSelection, DependencySet
from repo_catalog.domain.p1_core import OID
from repo_catalog.domain.provider_acquisition import make_provenance
from tests.e2e.test_separated_cli import document
from tests.e2e.test_separated_cli_pr_assessment import query
from tests.e2e.test_separated_cli_provider_regressions import (
    _http_response,
    _network_cli,
)
from tests.e2e.test_separated_cli_provider_regressions import (
    provider_case as provider_case,
)


def test_normal_cli_document_path_and_commit_queries_need_exact_provider_scope_without_git_bytes(
    provider_case, tmp_path, capsys, monkeypatch
):
    case = provider_case
    current = ["1" * 40]
    base, changed, calls = "2" * 40, "3" * 40, []
    original = make_provenance("finite-document-fixture", "grants")
    files = {"filename": "src/item.py", "status": "modified"}
    keys = {normalize_pr_file(case.service, "20", files, 1, original).primary_resource}
    for head in (current[0], changed):
        keys.add(
            normalize_pr_commit(
                case.service, "20", {"sha": head}, 1, original
            ).primary_resource
        )
    case.authority = document(
        tmp_path,
        "selector-authority.json",
        {
            "grants": DependencySet(
                resources=frozenset(case.keys.values()) | keys,
                provider_registrations={case.service},
                sources={case.source},
                object_oids={
                    OID("sha1", value) for value in (current[0], base, changed)
                },
            ),
            "selection": AdmissionSelection(all_selected=True),
        },
    )

    def handle(http):
        path = http.url.path
        calls.append(path)
        if path.endswith("/pulls"):
            value = [{"id": 20, "number": 1}]
        elif path.endswith("/pulls/1"):
            value = {
                "id": 20,
                "head": {"sha": current[0]},
                "base": {"sha": base},
                "commits": 1,
                "changed_files": 1,
                "updated_at": "2026-02-01T00:00:00Z"
                if current[0] == changed
                else "2026-01-01T00:00:00Z",
            }
        elif path.endswith("/commits"):
            value = [{"sha": current[0]}]
        elif path.endswith("/files"):
            value = (
                {"malformed": "no actual current listing"}
                if current[0] == changed
                else [files]
            )
        elif path.endswith("/comments"):
            value = [
                {
                    "id": 10,
                    "path": "src/item.py",
                    "commit_id": "1" * 40,
                    "body": "provider-only comment",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            ]
        else:
            value = {"id": 10, "full_name": "owner/repo"}
        return _http_response(http, value)

    request = {
        "operation": "sync",
        "service_instance_uuidv4": case.service,
        "source_registration_uuidv4": case.source,
        "request_identity": [str(uuid4()), str(uuid4())],
        "new_request": True,
        "owner": "owner",
        "repository": "repo",
        "sections": ["pr_commits", "pr_files", "review_comments"],
        "response_bytes": 8192,
        "rest_base_url": "https://api.example.test",
    }
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        acquired, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
        assert acquired["status"] == "complete"
        for options in ((), ("--path", "src/item.py"), ("--commit", "1" * 40)):
            result = query(
                capsys, case, "pr-documents", "--kind", "review_comments", *options
            )
            assert result["state"] == "complete" and result["total_count"] == 1
            assert list(result["items"][0]["resolved_texts"].values()) == [
                "provider-only comment"
            ]
        absent = query(
            capsys,
            case,
            "pr-documents",
            "--kind",
            "review_comments",
            "--path",
            "not-listed.py",
        )
        assert absent["state"] == "complete" and absent["total_count"] == 0
        current[0] = changed
        request["new_request"] = False
        partial, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
        assert partial["status"] == "partial"
    plain = query(capsys, case, "pr-documents", "--kind", "review_comments")
    assert plain["state"] == "complete" and plain["total_count"] == 1
    scoped = query(
        capsys,
        case,
        "pr-documents",
        "--kind",
        "review_comments",
        "--path",
        "src/item.py",
    )
    assert scoped["state"] == "partial" and scoped["total_count"] == 1
    assert any(gap["kind"] == "code_selector" for gap in scoped["coverage"]["missing"])
    assert not (case.directory / "core.sqlite3").exists()
    assert not (case.directory / "p1-recovery-stop.json").exists()
