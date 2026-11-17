"""The normal batch route executes frozen sources under one cumulative request."""

import copy
import json
import os
from uuid import uuid4

import httpx

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.domain.context_admission import AdmissionSelection, DependencySet
from repo_catalog.domain.p1_context import ResourceKey
from tests.e2e.test_separated_cli import document, init, run
from tests.e2e.test_separated_cli_provider_regressions import _http_response
from tests.integration.p5.conftest import build_sample_git_repo


def native(path, repository):
    objects = build_sample_git_repo(path)
    return {
        "source_registration_uuidv4": str(uuid4()),
        "kind": "local_git",
        "settings": {
            "path_hex": os.fsencode(path).hex(),
            "request": {
                "repository_uuidv4": repository,
                "capture_origin_uuidv4": str(uuid4()),
                "capture_uuidv4": str(uuid4()),
                "source_attribution": "explicit-cli-source",
                "observed_at_us": 1_700_000_500_000_000,
                "select_object_oids": [list(objects["commit2"].key)],
                "retain_bytes": False,
                "include_refs": True,
                "notes": {
                    "discover_notes": True,
                    "acquire_inventories": True,
                    "target_object_oids": [list(objects["commit2"].key)],
                    "retain_note_bodies": True,
                },
            },
        },
    }


def invoke(capsys, tmp_path, catalog, value, authority=None, expected=0):
    payload = document(tmp_path, "batch.json", value)
    return run(
        capsys,
        "acquire",
        "batch",
        "--catalog",
        catalog,
        "--input",
        payload,
        *([] if authority is None else ["--authority", authority]),
        expected=expected,
    )


def test_normal_cli_native_only_batch_needs_no_context_authority_and_replays_frozen_order(
    tmp_path, capsys, monkeypatch
):
    catalog = tmp_path / "catalog"
    identity = init(capsys, catalog, "core")
    init(capsys, catalog, "operational")
    sources = [
        native(tmp_path / label, identity["repository_uuidv4"])
        for label in ("first.git", "second.git")
    ]
    value = {
        "request_identity": [str(uuid4()), str(uuid4())],
        "new_request": True,
        "sources": sources,
        "credential_refs": {},
    }
    calls, original = [], GitNativeSource.metadata

    def count(source, oid, work=None):
        calls.append((source.path, oid))
        return original(source, oid, work)

    monkeypatch.setattr(GitNativeSource, "metadata", count)
    first = invoke(capsys, tmp_path, catalog, value)
    assert first["status"] == "complete"
    assert all(
        result["result"]["ref_note_acquisitions"] for result in first["source_results"]
    )
    before = len(calls)
    changed = copy.deepcopy(value)
    changed["new_request"] = False
    changed["sources"].reverse()
    changed["sources"][0]["settings"]["path_hex"] = os.fsencode(
        tmp_path / "must-not-read"
    ).hex()
    replay = invoke(capsys, tmp_path, catalog, changed)
    assert replay["status"] == "complete" and len(calls) == before
    assert replay["request_identity"] == first["request_identity"]
    assert [
        result["source_registration_uuidv4"] for result in replay["source_results"]
    ] == [source["source_registration_uuidv4"] for source in sources]
    assert all(
        result["replayed"] and result["result"] is None
        for result in replay["source_results"]
    )
    assert replay["usage"] == first["usage"]
    assert len(run(capsys, "operations", "list", "--catalog", catalog)["requests"]) == 1
    assert not (catalog / "context.sqlite3").exists()
    assert not (catalog / "access.sqlite3").exists()


def test_normal_cli_mixed_batch_resumes_only_original_partial_source_with_shared_usage(
    tmp_path, capsys, monkeypatch
):
    import repo_catalog.application.frozen_source_batch as module

    catalog = tmp_path / "catalog"
    identity = init(capsys, catalog, "paired")
    init(capsys, catalog, "operational")
    first_source = native(tmp_path / "native.git", identity["repository_uuidv4"])
    service, source_id = str(uuid4()), str(uuid4())
    second_source = {
        "source_registration_uuidv4": source_id,
        "kind": "github_inventory",
        "settings": {
            "service_instance_uuidv4": service,
            "owner": "owner",
            "include_repositories": ["repo"],
            "rest_base_url": "https://api.example.test",
            "graphql_url": "https://api.example.test/graphql",
            "max_pages": 100,
            "response_bytes": 8192,
        },
    }
    authority = document(
        tmp_path,
        "batch-authority.json",
        {
            "grants": DependencySet(
                resources=frozenset(
                    {ResourceKey.from_native(service, "repository", "10")}
                ),
                sources=frozenset({source_id}),
                provider_registrations=frozenset({service}),
            ),
            "selection": AdmissionSelection(all_selected=True),
        },
    )
    token, name = "synthetic-batch-value-never-persisted", "SEPARATED_BATCH_TOKEN"
    monkeypatch.setenv(name, token)
    value = {
        "request_identity": [str(uuid4()), str(uuid4())],
        "new_request": True,
        "sources": [first_source, second_source],
        "credential_refs": {source_id: {"kind": "environment", "name": name}},
    }
    broken, calls, metadata_calls = [True], [], []
    native_read = GitNativeSource.metadata

    def measured(source, oid, work=None):
        metadata_calls.append((source.path, oid))
        return native_read(source, oid, work)

    monkeypatch.setattr(GitNativeSource, "metadata", measured)

    def handle(http):
        calls.append(http.url.path)
        if http.url.path == "/user":
            return _http_response(http, {"login": "owner"})
        assert http.url.path == "/repos/owner/repo"
        if broken[0]:
            return httpx.Response(
                401, json={"message": "temporary authorization failure"}
            )
        return _http_response(
            http, {"id": 10, "full_name": "owner/repo", "private": True}
        )

    actual = module.acquire_batch
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:

        def execute(catalog, payload, *, authorization, admission):
            return actual(
                catalog,
                payload,
                authorization=authorization,
                admission=admission,
                client=client,
                clock_us=lambda: 1_000_000,
            )

        monkeypatch.setattr(module, "acquire_batch", execute)
        first = invoke(capsys, tmp_path, catalog, value, authority)
        assert first["status"] == "partial"
        assert [result["status"] for result in first["source_results"]] == [
            "complete",
            "partial",
        ]
        assert first["source_results"][1]["failure_code"] == "CREDENTIALS_MISSING"
        before = len(metadata_calls)
        changed = copy.deepcopy(value)
        changed["new_request"] = False
        changed["sources"].reverse()
        changed["sources"][0]["settings"]["owner"] = "must-not-execute"
        changed["credential_refs"][source_id]["name"] = (
            "MUST_NOT_RESOLVE_CHANGED_REFERENCE"
        )
        broken[0] = False
        second = invoke(capsys, tmp_path, catalog, changed, authority)
    assert second["status"] == "complete" and len(metadata_calls) == before
    assert second["request_identity"] == first["request_identity"]
    assert (
        second["source_results"][0]["replayed"]
        and second["source_results"][0]["result"] is None
    )
    assert not second["source_results"][1]["replayed"]
    assert (
        second["source_results"][1]["result"]["request_identity"]
        == second["request_identity"]
    )
    assert second["usage"]["input_bytes"] > first["usage"]["input_bytes"]
    assert calls == ["/user", "/repos/owner/repo", "/user", "/repos/owner/repo"]
    assert len(run(capsys, "operations", "list", "--catalog", catalog)["requests"]) == 1
    assert token not in json.dumps(second)
    for retained in catalog.glob("operational.sqlite3*"):
        if retained.is_file():
            assert token.encode() not in retained.read_bytes()
    assert not (catalog / "access.sqlite3").exists()
