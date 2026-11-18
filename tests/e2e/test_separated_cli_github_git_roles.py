"""Live API PR inputs are checked against actual explicit Git source observations."""

import os
from uuid import uuid4

import httpx
import pytest

from repo_catalog.adapters.github.production_intake import (
    normalize_pr_commit,
    normalize_pr_file,
)
from repo_catalog.domain.context_admission import AdmissionSelection, DependencySet
from repo_catalog.domain.provider_acquisition import make_provenance
from tests.e2e.test_separated_cli import document, init
from tests.e2e.test_separated_cli_pr_assessment import query
from tests.e2e.test_separated_cli_provider_regressions import (
    _http_response,
    _network_cli,
)
from tests.e2e.test_separated_cli_provider_regressions import (
    provider_case as provider_case,
)
from tests.integration.p5.conftest import build_sample_git_repo, git


def setup(case, tmp_path, capsys):
    identity = init(capsys, case.directory, "repository")
    native = tmp_path / "native.git"
    objects = build_sample_git_repo(native, "sha1")
    git(native, "update-ref", "refs/heads/main", objects["commit1"].object_oid)
    git(native, "update-ref", "refs/pull/1/head", objects["commit2"].object_oid)
    git_source = str(uuid4())
    commit = {"sha": objects["commit2"].object_oid}
    file = {"filename": "README.md", "status": "modified"}
    original = make_provenance("fixture", "finite-grants")
    keys = {
        normalize_pr_commit(case.service, "20", commit, 1, original).primary_resource,
        normalize_pr_file(case.service, "20", file, 1, original).primary_resource,
    }
    case.authority = document(
        tmp_path,
        "role-authority.json",
        {
            "grants": DependencySet(
                resources=frozenset(case.keys.values()) | keys,
                sources=frozenset({case.source, git_source}),
                provider_registrations=frozenset({case.service}),
                object_oids=frozenset(objects.values()),
            ),
            "selection": AdmissionSelection(all_selected=True),
        },
    )
    request = {
        "operation": "sync",
        "service_instance_uuidv4": case.service,
        "source_registration_uuidv4": case.source,
        "request_identity": [str(uuid4()), str(uuid4())],
        "new_request": True,
        "owner": "owner",
        "repository": "repo",
        "sections": ["pr_commits", "pr_files"],
        "response_bytes": 8192,
        "rest_base_url": "https://api.example.test",
        "graphql_url": "https://api.example.test/graphql",
        "git_source": {
            "source_registration_uuidv4": git_source,
            "repository_uuidv4": identity["repository_uuidv4"],
            "path_hex": os.fsencode(native).hex(),
            "ref_templates": {
                "head": "refs/pull/{number}/head",
                "base": "refs/heads/{base_ref}",
            },
        },
    }
    calls = []

    def handle(http):
        calls.append(http.url.path)
        if http.url.path.endswith("/pulls"):
            value = [{"id": 20, "number": 1}]
        elif http.url.path.endswith("/pulls/1"):
            value = {
                "id": 20,
                "head": {"sha": objects["commit2"].object_oid},
                "base": {"sha": objects["commit1"].object_oid, "ref": "main"},
                "commits": 1,
                "changed_files": 1,
                "updated_at": "2026-01-01T00:00:00Z",
            }
        elif http.url.path.endswith("/commits"):
            value = [commit]
        elif http.url.path.endswith("/files"):
            value = [file]
        else:
            value = {"id": 10, "full_name": "owner/repo"}
        return _http_response(http, value)

    return native, objects, request, handle, calls


def test_normal_cli_git_role_request_never_initializes_missing_repository_or_calls_http(
    provider_case, tmp_path, capsys, monkeypatch
):
    from tests.e2e.test_separated_cli import run

    case = provider_case
    before = (case.directory / "context.sqlite3").read_bytes()
    request = {
        "operation": "sync",
        "service_instance_uuidv4": case.service,
        "source_registration_uuidv4": case.source,
        "request_identity": [str(uuid4()), str(uuid4())],
        "new_request": True,
        "owner": "owner",
        "repository": "repo",
        "git_source": {
            "source_registration_uuidv4": case.source,
            "repository_uuidv4": str(uuid4()),
            "path_hex": os.fsencode(tmp_path / "explicit-native").hex(),
            "ref_templates": {
                "head": "refs/pull/{number}/head",
                "base": "refs/heads/{base_ref}",
            },
        },
    }

    def forbidden(*args, **kwargs):
        pytest.fail("Missing explicit Repository must be refused before HTTP")

    monkeypatch.setattr(httpx.Client, "request", forbidden)
    error = run(
        capsys,
        "acquire",
        "github",
        "--catalog",
        case.directory,
        "--input",
        document(tmp_path, "missing-repository-role.json", request),
        "--authority",
        case.authority,
        expected=2,
    )
    assert error["code"] == "STORE_UNAVAILABLE"
    assert (case.directory / "context.sqlite3").read_bytes() == before
    assert not (case.directory / "repository.sqlite3").exists()
    assert not (case.directory / "operational.sqlite3").exists()


@pytest.mark.parametrize("previously_retained", [False, True])
def test_normal_cli_live_git_ref_race_stays_partial_even_with_retained_expected_head(
    provider_case, tmp_path, capsys, monkeypatch, previously_retained
):
    import json
    from contextlib import closing

    from repo_catalog.adapters.sqlite.git_repository import GitRepositoryStore

    case = provider_case
    native, objects, request, handle, calls = setup(case, tmp_path, capsys)
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        if previously_retained:
            initial, request = _network_cli(
                case, tmp_path, capsys, monkeypatch, client, request
            )
            assert initial["status"] == "complete" and initial["git_reports"]
            assert query(capsys, case, "pr-code")["state"] == "complete"
            request["new_request"] = False
        git(native, "update-ref", "refs/pull/1/head", objects["commit1"].object_oid)
        raced, request = _network_cli(
            case, tmp_path, capsys, monkeypatch, client, request
        )
        assert raced["status"] == "partial" and raced["failure_code"] == "PR_CODE_RACE"
        checked = [
            item
            for item in case.view(capsys, case.keys["pull"])["collections"]
            if item["collection_kind"] == "git_role_checks"
        ]
        partial = [item for item in checked if item["state"] == "partial"]
        assert len(partial) == 1
        assert (
            any(item["state"] == "complete" for item in checked) == previously_retained
        )
        assert str(native) not in json.dumps(checked)
        assert "path_hex" not in json.dumps(checked)
        head = next(
            item
            for item in partial[0]["scope"]["role_checks"]
            if item["role"] == "head"
        )
        assert head["expected_oid"] == list(objects["commit2"].key)
        assert head["actual_oid"] == list(objects["commit1"].key)
        assert head["ref_observation_key"]
        result = query(capsys, case, "pr-code")
        assert (
            result["state"] != "complete"
            and not result["coverage"]["complete_for_requested_scope"]
        )
        with closing(
            GitRepositoryStore(case.directory / "repository.sqlite3")
        ) as repository_store:
            present = repository_store.sql(
                "SELECT 1 FROM git_objects WHERE object_format=? AND object_oid=?",
                objects["commit2"].key,
            )
            assert bool(present) == previously_retained
        before = len(calls)
        git(native, "update-ref", "refs/pull/1/head", objects["commit2"].object_oid)
        request["new_request"] = False
        resumed, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
    assert (
        resumed["status"] == "complete"
        and resumed["request_identity"] == raced["request_identity"]
    )
    assert (
        len(calls) > before
    )  # Owner-approved fresh acquisition spends real HTTP work.
    assert query(capsys, case, "pr-code")["state"] == "complete"
    assert not (case.directory / "p1-recovery-stop.json").exists()


def test_normal_cli_interrupted_git_role_walk_keeps_actual_prefix_and_resumes_parent(
    provider_case, tmp_path, capsys, monkeypatch
):
    import json
    import signal
    from contextlib import closing
    from dataclasses import replace

    import repo_catalog.application.provider_fetch as module
    from repo_catalog.adapters.git.native import GitNativeSource
    from repo_catalog.adapters.sqlite.git_repository import GitRepositoryStore
    from repo_catalog.cli.main import main
    from repo_catalog.cli.separated_io import decode, read_document
    from tests.integration.p5.conftest import write_git_object

    case = provider_case
    native, objects, request, handle, _ = setup(case, tmp_path, capsys)
    newer = write_git_object(
        native,
        "sha1",
        "commit",
        (
            f"tree {objects['tree'].object_oid}\nparent {objects['commit2'].object_oid}\n"
            "author New <new@example.test> 1700000400 +0000\n"
            "committer New <new@example.test> 1700000400 +0000\n\nnew captured head\n"
        ).encode(),
    )
    authority = decode(read_document(case.authority))
    newer_member = normalize_pr_commit(
        case.service,
        "20",
        {"sha": newer.object_oid},
        1,
        make_provenance("fixture", "newer-head"),
    ).primary_resource
    authority["grants"] = replace(
        authority["grants"],
        resources=authority["grants"].resources | {newer_member},
        object_oids=authority["grants"].object_oids | {newer},
    )
    case.authority = document(tmp_path, "new-head-authority.json", authority)
    init(capsys, case.directory, "operational")
    original_http, original_metadata = module.acquire_github, GitNativeSource.metadata
    interrupted, advanced = [False], [False]

    def current(http):
        if advanced[0] and http.url.path.endswith("/pulls/1"):
            return _http_response(
                http,
                {
                    "id": 20,
                    "head": {"sha": newer.object_oid},
                    "base": {"sha": objects["commit1"].object_oid, "ref": "main"},
                    "commits": 1,
                    "changed_files": 1,
                    "updated_at": "2026-02-01T00:00:00Z",
                },
            )
        if advanced[0] and http.url.path.endswith("/commits"):
            return _http_response(http, [{"sha": newer.object_oid}])
        return handle(http)

    def metadata(source, oid, work=None):
        if oid == newer and not interrupted[0]:
            interrupted[0] = True
            signal.raise_signal(signal.SIGINT)
        return original_metadata(source, oid, work)

    with httpx.Client(transport=httpx.MockTransport(current)) as client:
        initial, request = _network_cli(
            case, tmp_path, capsys, monkeypatch, client, request
        )
        assert (
            initial["status"] == "complete"
            and query(capsys, case, "pr-code")["state"] == "complete"
        )
        advanced[0] = True
        request["new_request"] = False
        git(native, "update-ref", "refs/pull/1/head", newer.object_oid)
        monkeypatch.setattr(GitNativeSource, "metadata", metadata)

        def invoke(catalog, value, *, authorization, admission):
            return original_http(
                catalog,
                value,
                authorization=authorization,
                admission=admission,
                client=client,
            )

        monkeypatch.setattr(module, "acquire_github", invoke)
        result = main(
            [
                "acquire",
                "github",
                "--catalog",
                str(case.directory),
                "--input",
                document(tmp_path, "cancel-role.json", request),
                "--authority",
                case.authority,
            ]
        )
        captured = capsys.readouterr()
        assert result == 130 and captured.out == ""
        assert json.loads(captured.err)["code"] == "CANCELLED"
        assert interrupted[0]
        with closing(
            GitRepositoryStore(case.directory / "repository.sqlite3")
        ) as repository_store:
            prefix = repository_store.sql(
                "SELECT object_oid,digest_sha256 FROM retained_metadata"
            )
        assert any(row[0] == objects["commit2"].object_oid for row in prefix)
        interrupted_view = query(capsys, case, "pr-code")
        assert interrupted_view["state"] != "complete"
        assert interrupted_view["anchors"]["head"] == list(newer.key)
        monkeypatch.setattr(module, "acquire_github", original_http)
        request["new_request"] = False
        resumed, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
    assert (
        resumed["status"] == "complete"
        and resumed["request_identity"]["request_uuidv4"]
        == request["request_identity"][1]
    )
    with closing(
        GitRepositoryStore(case.directory / "repository.sqlite3")
    ) as repository_store:
        retained = repository_store.sql(
            "SELECT object_oid,digest_sha256 FROM retained_metadata"
        )
    assert all(row in retained for row in prefix)
    assert query(capsys, case, "pr-code")["state"] == "complete"
    assert not (case.directory / "p1-recovery-stop.json").exists()


def test_normal_cli_captured_review_target_is_actually_retried_under_original_budget(
    provider_case, tmp_path, capsys, monkeypatch
):
    from dataclasses import replace

    from repo_catalog.adapters.git.native import GitNativeSource
    from repo_catalog.cli.separated_io import decode, read_document
    from repo_catalog.domain.p1_repository import RepositoryFailure
    from tests.integration.p5.conftest import write_git_object

    case = provider_case
    native, objects, request, handle, calls = setup(case, tmp_path, capsys)
    target = write_git_object(
        native,
        "sha1",
        "commit",
        (
            f"tree {objects['tree'].object_oid}\n"
            "author Review <review@example.test> 1700000300 +0000\n"
            "committer Review <review@example.test> 1700000300 +0000\n\nreview target\n"
        ).encode(),
    )
    authority = decode(read_document(case.authority))
    authority["grants"] = replace(
        authority["grants"], object_oids=authority["grants"].object_oids | {target}
    )
    case.authority = document(tmp_path, "review-role-authority.json", authority)
    request["sections"].append("reviews")
    original, attempts = GitNativeSource.metadata, []

    def metadata(source, oid, work=None):
        if oid == target:
            attempts.append(oid)
            if len(attempts) == 1:
                raise RepositoryFailure(
                    "OBJECT_UNAVAILABLE", oid, "Actual selected target read unavailable"
                )
        return original(source, oid, work)

    def review(http):
        if http.url.path.endswith("/reviews"):
            calls.append(http.url.path)
            return _http_response(
                http,
                [{"id": 10, "commit_id": target.object_oid, "body": "captured review"}],
            )
        return handle(http)

    monkeypatch.setattr(GitNativeSource, "metadata", metadata)
    with httpx.Client(transport=httpx.MockTransport(review)) as client:
        first, request = _network_cli(
            case, tmp_path, capsys, monkeypatch, client, request
        )
        assert (
            first["status"] == "partial"
            and first["failure_code"] == "OBJECT_UNAVAILABLE"
        )
        assert attempts == [target]
        assert query(capsys, case, "pr-code")["state"] != "complete"
        prior_calls = len(calls)
        request["new_request"] = False
        resumed, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
    assert (
        resumed["status"] == "complete"
        and resumed["request_identity"] == first["request_identity"]
    )
    assert attempts == [target, target]
    assert (
        len(calls) > prior_calls
    )  # Fresh HTTP replaces the retired completed-unit cache.
    assert query(capsys, case, "pr-code")["state"] == "complete"
    assert list(case.view(capsys, case.keys["review"])["resolved_texts"].values()) == [
        "captured review"
    ]


def test_normal_cli_remote_git_role_source_uses_real_transfer_and_removes_temporary_cache(
    provider_case, tmp_path, capsys, monkeypatch
):
    from tests.integration.p5.test_separated_remote_git import git_http

    case = provider_case
    _, _, request, handle, _ = setup(case, tmp_path, capsys)
    source = request["git_source"]
    source.pop("path_hex")
    source["kind"] = "remote"
    with git_http(tmp_path) as (base, events):
        source["remote"] = {
            "locator": base + "/native.git",
            "object_format": "sha1",
            "transfer_bytes": 1024 * 1024,
            "disk_bytes": 32 * 1024 * 1024,
            "token_env_var": "SEPARATED_ROLE_TEST_NO_CREDENTIAL",
            "refspecs": ["+refs/heads/*:refs/heads/*", "+refs/pull/*:refs/pull/*"],
        }
        monkeypatch.delenv("SEPARATED_ROLE_TEST_NO_CREDENTIAL", raising=False)
        with httpx.Client(transport=httpx.MockTransport(handle)) as client:
            report, _ = _network_cli(
                case, tmp_path, capsys, monkeypatch, client, request
            )
    assert report["status"] == "complete", {"failure_code": report["failure_code"]}
    assert (
        report["git_reports"]
        and report["git_reports"][0]["transfer_body_bytes"]
        == sum(event["bytes"] for event in events)
        > 0
    )
    assert query(capsys, case, "pr-code")["state"] == "complete"
    assert not list((case.directory / "cache").rglob("HEAD"))


def test_normal_cli_api_wait_never_dispatches_git_work_or_rewrites_saved_role_evidence(
    provider_case, tmp_path, capsys, monkeypatch
):
    from repo_catalog.adapters.git.native import GitNativeSource
    from tests.e2e.test_separated_cli_provider_regressions import (
        GraphQLFixture,
        _request_usage,
    )

    case = provider_case
    _, _, request, handle, _ = setup(case, tmp_path, capsys)
    request["sections"].append("review_threads")
    graphql, limited, probes = GraphQLFixture(), [False], []
    original = GitNativeSource.__init__

    def native_probe(source, *args, **kwargs):
        probes.append(True)
        original(source, *args, **kwargs)

    def response(http):
        if http.method == "POST":
            if limited[0]:
                return _http_response(
                    http,
                    {
                        "errors": [{"type": "RATE_LIMITED", "message": "wait"}],
                        "data": None,
                    },
                )
            return graphql.response(http)
        return handle(http)

    monkeypatch.setattr(GitNativeSource, "__init__", native_probe)
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        initial, request = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request,
            clock_us=lambda: 1_000_000,
        )
        assert initial["status"] == "complete" and probes == [True]
        prior = [
            item
            for item in case.view(capsys, case.keys["pull"])["collections"]
            if item["collection_kind"] == "git_role_checks"
        ]
        request["new_request"] = False
        limited[0] = True
        waiting, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request,
            clock_us=lambda: 1_000_000,
        )
        assert (
            waiting["status"] == "partial" and waiting["failure_code"] == "RATE_LIMIT"
        )
        assert waiting["not_before_us"] == 61_000_000
        assert probes == [True] and waiting["git_reports"] == []
        usage = _request_usage(case.directory, request)
        blocked, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request,
            clock_us=lambda: 1_000_000,
        )
    assert blocked["failure_code"] == "NOT_BEFORE" and blocked["http_attempts"] == 0
    assert probes == [True] and _request_usage(case.directory, request) == usage
    assert [
        item
        for item in case.view(capsys, case.keys["pull"])["collections"]
        if item["collection_kind"] == "git_role_checks"
    ] == prior
    assert query(capsys, case, "pr-code")["state"] == "complete"


@pytest.mark.parametrize("head_changed", [False, True])
def test_normal_cli_unobserved_git_refresh_reuses_only_matching_retained_roles(
    provider_case, tmp_path, capsys, monkeypatch, head_changed
):
    from contextlib import closing
    from dataclasses import replace

    from repo_catalog.adapters.git.native import GitNativeSource
    from repo_catalog.adapters.sqlite.git_repository import GitRepositoryStore
    from repo_catalog.cli.separated_io import decode, read_document
    from repo_catalog.domain.p1_repository import RepositoryFailure
    from tests.integration.p5.conftest import write_git_object

    case = provider_case
    native, objects, request, handle, _ = setup(case, tmp_path, capsys)
    newer = write_git_object(
        native,
        "sha1",
        "commit",
        (
            f"tree {objects['tree'].object_oid}\nparent {objects['commit2'].object_oid}\n"
            "author New <new@example.test> 1700000400 +0000\n"
            "committer New <new@example.test> 1700000400 +0000\n\nnew captured head\n"
        ).encode(),
    )
    authority = decode(read_document(case.authority))
    newer_member = normalize_pr_commit(
        case.service,
        "20",
        {"sha": newer.object_oid},
        1,
        make_provenance("fixture", "new-head"),
    ).primary_resource
    authority["grants"] = replace(
        authority["grants"],
        resources=authority["grants"].resources | {newer_member},
        object_oids=authority["grants"].object_oids | {newer},
    )
    case.authority = document(tmp_path, "refresh-role-authority.json", authority)
    failed = [False]

    def response(http):
        if failed[0] and head_changed and http.url.path.endswith("/pulls/1"):
            return _http_response(
                http,
                {
                    "id": 20,
                    "head": {"sha": newer.object_oid},
                    "base": {"sha": objects["commit1"].object_oid, "ref": "main"},
                    "commits": 1,
                    "changed_files": 1,
                    "updated_at": "2026-02-01T00:00:00Z",
                },
            )
        if failed[0] and head_changed and http.url.path.endswith("/commits"):
            return _http_response(http, [{"sha": newer.object_oid}])
        return handle(http)

    def unavailable(*args, **kwargs):
        raise RepositoryFailure(
            "GIT_INPUT", "explicit-source", "No fresh Git ref was observed"
        )

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        initial, request = _network_cli(
            case, tmp_path, capsys, monkeypatch, client, request
        )
        assert (
            initial["status"] == "complete"
            and query(capsys, case, "pr-code")["state"] == "complete"
        )
        previous = [
            item
            for item in case.view(capsys, case.keys["pull"])["collections"]
            if item["collection_kind"] == "git_role_checks"
        ]
        with closing(
            GitRepositoryStore(case.directory / "repository.sqlite3")
        ) as repository_store:
            retained = repository_store.sql(
                "SELECT object_oid,digest_sha256 FROM retained_metadata ORDER BY object_oid"
            )
        failed[0] = True
        git(
            native,
            "update-ref",
            "refs/pull/1/head",
            (newer if head_changed else objects["commit1"]).object_oid,
        )
        monkeypatch.setattr(GitNativeSource, "__init__", unavailable)
        request["new_request"] = False
        report, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
    assert report["status"] == "partial" and report["failure_code"] == "GIT_INPUT"
    assert report["git_reports"] == []
    assert [
        item
        for item in case.view(capsys, case.keys["pull"])["collections"]
        if item["collection_kind"] == "git_role_checks"
    ] == previous
    with closing(
        GitRepositoryStore(case.directory / "repository.sqlite3")
    ) as repository_store:
        assert (
            repository_store.sql(
                "SELECT object_oid,digest_sha256 FROM retained_metadata ORDER BY object_oid"
            )
            == retained
        )
    result = query(capsys, case, "pr-code")
    assert result["anchors"]["head"] == list(
        (newer if head_changed else objects["commit2"]).key
    )
    assert (result["state"] == "complete") == (not head_changed)


def test_normal_cli_final_provider_check_cannot_borrow_another_captured_head_listing(
    provider_case, tmp_path, capsys, monkeypatch
):
    import hashlib
    from contextlib import closing
    from dataclasses import replace

    from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
    from repo_catalog.adapters.sqlite.git_repository import GitRepositoryStore
    from repo_catalog.cli.separated_io import decode, read_document
    from repo_catalog.domain.p1_repository import NativeObject
    from tests.integration.p5.conftest import write_git_object

    case = provider_case
    native, objects, request, handle, _ = setup(case, tmp_path, capsys)
    body = (
        f"tree {objects['tree'].object_oid}\nparent {objects['commit2'].object_oid}\n"
        "author New <new@example.test> 1700000400 +0000\ncommitter New <new@example.test> 1700000400 +0000\n\npreexisting other head\n"
    ).encode()
    other = write_git_object(native, "sha1", "commit", body)
    with closing(
        GitRepositoryStore(case.directory / "repository.sqlite3")
    ) as repository_store:
        repository_store.admit_metadata(
            NativeObject(
                other, "commit", body, len(body), hashlib.sha256(body).hexdigest()
            ),
            str(uuid4()),
            UnlimitedWorkBudget(),
        )
    authority = decode(read_document(case.authority))
    authority["grants"] = replace(
        authority["grants"], object_oids=authority["grants"].object_oids | {other}
    )
    case.authority = document(tmp_path, "final-check-authority.json", authority)
    details = []

    def response(http):
        if http.url.path.endswith("/pulls/1"):
            details.append(True)
            changed = len(details) == 2
            oid = other if changed else objects["commit2"]
            stamp = (
                "2026-02-01T00:00:00Z"
                if changed
                else "2026-01-01T00:00:00Z"
                if len(details) == 1
                else "2026-03-01T00:00:00Z"
            )
            return _http_response(
                http,
                {
                    "id": 20,
                    "head": {"sha": oid.object_oid},
                    "base": {"sha": objects["commit1"].object_oid, "ref": "main"},
                    "commits": 1,
                    "changed_files": 1,
                    "updated_at": stamp,
                },
            )
        return handle(http)

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        raced, request = _network_cli(
            case, tmp_path, capsys, monkeypatch, client, request
        )
        assert len(details) == 2
        assert raced["status"] == "partial" and raced["failure_code"] == "PR_CODE_RACE"
        view = query(capsys, case, "pr-code")
        assert view["anchors"]["head"] == list(other.key)
        assert (
            view["state"] != "complete"
            and not view["coverage"]["complete_for_requested_scope"]
        )
        request["new_request"] = False
        recovered, _ = _network_cli(
            case, tmp_path, capsys, monkeypatch, client, request
        )
    assert len(details) == 4
    assert (
        recovered["status"] == "complete"
        and recovered["request_identity"] == raced["request_identity"]
    )
    current = query(capsys, case, "pr-code")
    assert current["state"] == "complete" and current["anchors"]["head"] == list(
        objects["commit2"].key
    )
