"""Permitted metadata and Context documents remain usable without source/cache/Git."""

import shutil
import subprocess
from uuid import uuid4

import httpx

from repo_catalog.domain.provider_acquisition import (
    ProviderPullRequestIntake,
    make_provenance,
)
from tests.e2e.test_separated_cli import init, run
from tests.e2e.test_separated_cli_github_git_roles import setup
from tests.e2e.test_separated_cli_pr_assessment import query
from tests.e2e.test_separated_cli_provider_regressions import (
    _http_response,
    _network_cli,
)
from tests.e2e.test_separated_cli_provider_regressions import (
    provider_case as provider_case,
)


def search(capsys, case, *options, expected=0):
    return run(
        capsys,
        "query",
        "search",
        "--catalog",
        case.directory,
        "--kinds",
        "git_metadata,context_text",
        "--query",
        "offline-marker",
        *options,
        expected=expected,
    )


def test_normal_cli_offline_metadata_documents_reindex_fallback_and_cursor_fence(
    provider_case, tmp_path, capsys, monkeypatch
):
    case = provider_case
    native, objects, request, rest, calls = setup(case, tmp_path, capsys)
    request["sections"].append("reviews")

    def handle(http):
        if http.url.path.endswith("/reviews"):
            return _http_response(http, [{"id": 10, "body": "offline-marker review"}])
        response = rest(http)
        if http.url.path.endswith("/pulls/1"):
            response.read()
            value = response.json()
            value.update(title="offline-marker title", body="offline-marker body")
            return _http_response(http, value)
        return response

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        acquired, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
    assert acquired["status"] == "complete"
    before = search(capsys, case)
    # Initial and final actual detail reads keep distinct equal-clock originals:
    # two parent titles, two title documents, two body documents, one review.
    assert before["total_count"] == 7 and before["backend"] == "authority_scan"
    assert {hit["matched_text"] for hit in before["hits"]} == {
        "offline-marker title",
        "offline-marker body",
        "offline-marker review",
    }
    assert calls == [
        "/repos/owner/repo",
        "/repos/owner/repo/pulls",
        "/repos/owner/repo/pulls/1",
        "/repos/owner/repo/pulls/1/commits",
        "/repos/owner/repo/pulls/1/files",
        "/repos/owner/repo/pulls/1",
    ]
    before_tree = run(
        capsys,
        "query",
        "tree",
        "--catalog",
        case.directory,
        "--object-oid",
        objects["commit2"].object_oid,
        "--recursive",
    )
    shutil.rmtree(native)

    def forbidden(*args, **kwargs):
        raise AssertionError("ordinary offline query attempted source hydration")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    after = search(capsys, case)
    assert after["hits"] == before["hits"]
    assert (
        run(
            capsys,
            "query",
            "tree",
            "--catalog",
            case.directory,
            "--object-oid",
            objects["commit2"].object_oid,
            "--recursive",
        )
        == before_tree
    )
    assert (
        query(capsys, case, "pr-documents", "--kind", "reviews")["state"] == "complete"
    )
    init(capsys, case.directory, "search")
    run(
        capsys,
        "query",
        "search-rebuild",
        "--catalog",
        case.directory,
        "--kinds",
        "git_metadata,context_text",
    )
    first = search(capsys, case, "--limit", 1)
    assert first["backend"] == "verified_projection_scan" and first["has_more"]
    run(
        capsys,
        "query",
        "search-rebuild",
        "--catalog",
        case.directory,
        "--kinds",
        "git_metadata,context_text",
    )
    following = search(capsys, case, "--limit", 1, "--cursor", first["next_cursor"])
    assert following["hits"] != first["hits"]
    assert following["snapshot_token"] == first["snapshot_token"]
    # A corrupt disposable index must fall back to unchanged authority, offline.
    index = case.directory / "search.sqlite3"
    index.write_bytes(b"untrusted disposable derivative")
    fallback = search(capsys, case)
    assert (
        fallback["backend"] == "authority_scan" and fallback["hits"] == before["hits"]
    )
    assert not (case.directory / "p1-recovery-stop.json").exists()
    case.admit(
        tmp_path,
        capsys,
        pull_requests=(
            ProviderPullRequestIntake(
                {
                    "id": 20,
                    "title": "offline-marker changed",
                    "updated_at": "2026-03-01T00:00:00Z",
                },
                600,
                make_provenance("explicit-offline-report", str(uuid4())),
            ),
        ),
    )
    refused = search(
        capsys, case, "--limit", 1, "--cursor", first["next_cursor"], expected=2
    )
    assert refused["code"] == "SNAPSHOT_MISMATCH"


def test_normal_cli_explicit_tree_roots_and_raw_paths_never_union_other_recorded_roots(
    tmp_path, capsys
):
    import base64
    import hashlib
    from dataclasses import replace

    from repo_catalog.domain.p1_core import OID, NativeObject, native_object_oid
    from tests.e2e.test_separated_cli import document
    from tests.e2e.test_separated_cli_literal_bytes import setup as metadata

    catalog, original, tree, commits, _ = metadata(tmp_path, capsys, "sha1")
    raw = b"\xff\tline\n.txt"
    raw64 = base64.b64encode(raw).decode()
    path = run(
        capsys,
        "query",
        "path",
        "--catalog",
        catalog,
        "--object-oid",
        commits[0].object_oid,
        "--path-b64",
        raw64,
    )
    assert len(path["items"]) == 1
    assert base64.b64decode(path["items"][0]["path"]["$bytes"]) == raw
    assert path["items"][0]["object_oid"] == "1" * 40
    # An independently captured PR/rewrite root has a different exact tree. Its
    # nominal blob is metadata only, and never contributes to another root.
    body = b"100644 pr-only.txt\0" + bytes.fromhex("2" * 40)
    alternate = OID("sha1", native_object_oid("sha1", "tree", body))
    unit = replace(
        original,
        capture_uuidv4=str(uuid4()),
        native_objects=(
            NativeObject(
                alternate, "tree", body, len(body), hashlib.sha256(body).hexdigest()
            ),
        ),
    )
    run(
        capsys,
        "acquire",
        "git-metadata",
        "--catalog",
        catalog,
        "--input",
        document(tmp_path, "other-root.json", unit),
        "--new-request",
    )
    for root in (tree, commits[0], commits[1]):
        selected = run(
            capsys,
            "query",
            "path",
            "--catalog",
            catalog,
            "--object-oid",
            root.object_oid,
            "--path-b64",
            base64.b64encode(b"pr-only.txt").decode(),
        )
        assert selected["items"] == []
    chosen = run(
        capsys,
        "query",
        "tree",
        "--catalog",
        catalog,
        "--object-oid",
        alternate.object_oid,
    )
    assert [base64.b64decode(row["path"]["$bytes"]) for row in chosen["items"]] == [
        b"pr-only.txt"
    ]
    assert chosen["items"][0]["object_oid"] == "2" * 40
    assert (
        run(
            capsys,
            "query",
            "path",
            "--catalog",
            catalog,
            "--object-oid",
            alternate.object_oid,
            "--path-b64",
            raw64,
        )["items"]
        == []
    )
    from contextlib import closing

    from repo_catalog.adapters.sqlite.git_core import GitCore

    with closing(GitCore(catalog / "core.sqlite3")) as core:
        assert (
            core.sql(
                "SELECT 1 FROM retained_metadata WHERE object_format=? AND object_oid=?",
                ("sha1", "2" * 40),
            )
            == []
        )
    assert not (catalog / "p1-recovery-stop.json").exists()
