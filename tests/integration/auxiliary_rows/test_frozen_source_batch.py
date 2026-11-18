"""Real mixed acquisition, frozen resume and one cumulative batch budget."""

import copy
import json
import os
from uuid import uuid4

import httpx
import pytest

from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application import frozen_source_batch as batch_module
from repo_catalog.application.frozen_source_batch import acquire_batch
from repo_catalog.domain.context_admission import (
    AdmissionSelection,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.p1_coordination import RequestIdentity
from tests.integration.p5.conftest import build_sample_git_repo, init_catalog_stores


def native_source(path, repository, objects, *, notes=True):
    request = {
        "repository_uuidv4": repository,
        "capture_origin_uuidv4": str(uuid4()),
        "capture_uuidv4": str(uuid4()),
        "source_attribution": "explicit-frozen-native-input",
        "observed_at_us": 1_700_000_500_000_000,
        "select_object_oids": [
            [objects["commit2"].object_format, objects["commit2"].object_oid]
        ],
        "retain_bytes": False,
        "include_refs": True,
    }
    if notes:
        request["notes"] = {
            "discover_notes": True,
            "acquire_inventories": True,
            "target_object_oids": request["select_object_oids"],
            "retain_note_bodies": True,
        }
    return {
        "source_registration_uuidv4": str(uuid4()),
        "kind": "local_git",
        "settings": {"path_hex": os.fsencode(path).hex(), "request": request},
    }


def document(sources):
    return {
        "request_identity": [str(uuid4()), str(uuid4())],
        "new_request": True,
        "sources": sources,
        "credential_refs": {},
    }


def operational_state(catalog):
    with OperationalAcquisitionLedger(catalog) as ledger:
        return {
            table: [
                tuple(row)
                for row in ledger.db.execute(f"SELECT * FROM {table} ORDER BY 1,2,3")
            ]
            for table in (
                "acquisition_requests",
                "acquisition_attempts",
                "request_continuations",
            )
        }


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_two_native_sources_execute_same_parent_and_frozen_resume_skips_successes(
    tmp_path, monkeypatch, fmt
):
    catalog = tmp_path / "catalog"
    repository, _ = init_catalog_stores(catalog, stores=("repository", "operational"))
    paths = [tmp_path / "first.git", tmp_path / "second.git"]
    sources = [
        native_source(path, repository, build_sample_git_repo(path, fmt))
        for path in paths
    ]
    original = document(sources)
    observed = []
    execute = batch_module._execute

    def record(*args, **kwargs):
        ledger, work, progress = kwargs["ledger"], kwargs["work"], kwargs["progress"]
        result = execute(*args, **kwargs)
        observed.append(
            (
                id(ledger),
                id(work),
                id(progress),
                work.attempt_uuidv4,
                ledger.work_ledger.usage(work.request),
            )
        )
        return result

    monkeypatch.setattr(batch_module, "_execute", record)
    report = acquire_batch(catalog, original)
    assert report.status == "complete"
    assert len(observed) == 2 and observed[0][:4] == observed[1][:4]
    assert observed[0][3] == report.attempt_uuidv4
    for unit in ("input_bytes", "verification_bytes", "metadata_units"):
        assert 0 < observed[0][4][unit] < observed[1][4][unit] == report.usage[unit]
    assert all(item["result"].ref_note_acquisitions for item in report.source_results)
    changed = copy.deepcopy(original)
    changed["new_request"] = False
    changed["sources"].reverse()
    changed["sources"][0]["settings"]["path_hex"] = os.fsencode(
        tmp_path / "changed.git"
    ).hex()
    resumed = acquire_batch(catalog, changed)
    assert resumed.status == "complete" and len(observed) == 2
    assert [item["source_registration_uuidv4"] for item in resumed.source_results] == [
        item["source_registration_uuidv4"] for item in sources
    ]
    assert all(
        item["replayed"] and item["result"] is None for item in resumed.source_results
    )
    assert resumed.usage == report.usage
    state = operational_state(catalog)
    assert (
        len(state["acquisition_requests"]) == 1
        and len(state["acquisition_attempts"]) == 2
    )
    assert not (catalog / "context.sqlite3").exists()


def test_real_native_then_http_share_counters_and_preserve_explicit_credential_reference(
    tmp_path, monkeypatch
):
    catalog = tmp_path / "catalog"
    repository, _ = init_catalog_stores(catalog)
    path = tmp_path / "native.git"
    native = native_source(path, repository, build_sample_git_repo(path), notes=False)
    service, source = str(uuid4()), str(uuid4())
    member = ResourceKey.from_native(service, "repository", "10")
    provider = {
        "source_registration_uuidv4": source,
        "kind": "github_inventory",
        "settings": {
            "service_instance_uuidv4": service,
            "owner": "original-owner",
            "include_repositories": ["repo"],
            "rest_base_url": "https://api.example.test",
            "graphql_url": "https://api.example.test/graphql",
            "max_pages": 3,
            "response_bytes": 8192,
        },
    }
    auth, admission, _ = create_local_admission_service(
        grants=DependencySet(
            resources={member}, sources={source}, provider_registrations={service}
        ),
        selection=AdmissionSelection(all_selected=True),
    )
    value = document([native, provider])
    value["credential_refs"] = {
        source: {"kind": "environment", "name": "FROZEN_BATCH_TEST_TOKEN"}
    }
    monkeypatch.setenv("FROZEN_BATCH_TEST_TOKEN", "synthetic-secret-not-persisted")
    calls = []

    def handle(request):
        calls.append(request.url.path)
        data = (
            {"login": "original-owner"}
            if request.url.path == "/user"
            else {"id": 10, "full_name": "original-owner/repo", "private": True}
        )
        return httpx.Response(
            200, request=request, stream=httpx.ByteStream(json.dumps(data).encode())
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        report = acquire_batch(
            catalog,
            value,
            authorization=auth,
            admission=admission,
            client=client,
            clock_us=lambda: 1_000_000,
        )
    assert report.status == "complete" and len(calls) == 2
    native_report, http_report = [item["result"] for item in report.source_results]
    assert native_report.admitted_objects and http_report.http_attempts == 2
    assert http_report.request_identity == RequestIdentity(*value["request_identity"])
    assert report.usage["input_bytes"] > http_report.network_bytes > 0
    state = operational_state(catalog)
    assert len(state["acquisition_requests"]) == len(state["acquisition_attempts"]) == 1
    assert "FROZEN_BATCH_TEST_TOKEN" in json.dumps(state)
    assert "synthetic-secret-not-persisted" not in json.dumps(state)
    with Context.snapshot(catalog) as context:
        assert context.resources(kind="repository") == (member,)
        assert (
            context.db.execute(
                "SELECT count(*) FROM resource_repository_relations"
            ).fetchone()[0]
            == 0
        )


def test_cumulative_cap_halts_unstarted_sources_and_never_creates_child_requests(
    tmp_path,
):
    catalog = tmp_path / "catalog"
    repository, _ = init_catalog_stores(catalog, stores=("repository", "operational"))
    path = tmp_path / "native.git"
    objects = build_sample_git_repo(path)
    value = document(
        [
            native_source(path, repository, objects),
            native_source(path, repository, objects),
        ]
    )
    value["work_limits"] = {"metadata_units": 1}
    report = acquire_batch(catalog, value)
    assert report.status == "partial"
    assert report.source_results[0]["failure_code"] == "BUDGET"
    assert report.source_results[1]["status"] == "not_started"
    assert report.usage["metadata_units"] == 1
    state = operational_state(catalog)
    assert len(state["acquisition_requests"]) == len(state["acquisition_attempts"]) == 1


def test_remote_and_local_dispatch_execute_real_transport_in_one_parent(tmp_path):
    from tests.integration.p5.test_separated_remote_git import git_http

    catalog = tmp_path / "catalog"
    repository, _ = init_catalog_stores(catalog, stores=("repository", "operational"))
    path = tmp_path / "repository.git"
    objects = build_sample_git_repo(path)
    local = native_source(path, repository, objects)
    remote = native_source(path, repository, objects)
    remote["kind"] = "remote_git"
    with git_http(tmp_path) as (base, events):
        remote["settings"] = {
            "request": remote["settings"]["request"],
            "locator": base + "/repository.git",
            "object_format": "sha1",
            "transfer_bytes": 1024 * 1024,
        }
        value = document([remote, local])
        report = acquire_batch(catalog, value)
        assert report.status == "complete"
        transferred = report.source_results[0]["result"]
        assert (
            transferred.transfer_body_bytes
            == sum(event["bytes"] for event in events)
            > 0
        )
        assert transferred.git_report.ref_note_acquisitions
        assert report.source_results[1]["result"].ref_note_acquisitions
        assert report.usage["input_bytes"] > transferred.transfer_body_bytes
        boundary = len(events)
        value["new_request"] = False
        resumed = acquire_batch(catalog, value)
        assert resumed.status == "complete" and len(events) == boundary
        assert resumed.usage == report.usage
    state = operational_state(catalog)
    assert len(state["acquisition_requests"]) == 1


def test_missing_then_lost_credentials_preserve_frozen_partial_batch_without_http_evidence(
    tmp_path, monkeypatch
):
    catalog = tmp_path / "catalog"
    repository, _ = init_catalog_stores(catalog)
    path = tmp_path / "repository.git"
    local = native_source(path, repository, build_sample_git_repo(path), notes=False)
    service, source = str(uuid4()), str(uuid4())
    member = ResourceKey.from_native(service, "repository", "10")
    provider = {
        "source_registration_uuidv4": source,
        "kind": "github_inventory",
        "settings": {
            "service_instance_uuidv4": service,
            "owner": "original-owner",
            "include_repositories": ["repo"],
            "rest_base_url": "https://api.example.test",
            "graphql_url": "https://api.example.test/graphql",
            "max_pages": 3,
            "response_bytes": 8192,
        },
    }
    auth, admission, _ = create_local_admission_service(
        grants=DependencySet(
            resources={member}, sources={source}, provider_registrations={service}
        ),
        selection=AdmissionSelection(all_selected=True),
    )
    value = document([provider])
    name = "FROZEN_BATCH_MISSING_TOKEN"
    value["credential_refs"] = {source: {"kind": "environment", "name": name}}
    monkeypatch.delenv(name, raising=False)
    before = operational_state(catalog)
    with pytest.raises(CatalogError) as error:
        acquire_batch(catalog, value, authorization=auth, admission=admission)
    assert error.value.code == "SOURCE_CREDENTIAL_UNAVAILABLE"
    assert operational_state(catalog) == before
    monkeypatch.setenv(name, "synthetic-secret-never-saved")
    value["sources"].append(local)
    interrupted = acquire_batch(
        catalog, value, authorization=auth, admission=admission, cancelled=lambda: True
    )
    assert interrupted.status == "partial"
    assert all(item["status"] == "not_started" for item in interrupted.source_results)
    monkeypatch.delenv(name)
    value["new_request"] = False
    calls = []

    def handle(request):
        calls.append(request.url.path)
        data = (
            {"login": "original-owner"}
            if request.url.path == "/user"
            else {"id": 10, "full_name": "original-owner/repo", "private": True}
        )
        return httpx.Response(
            200, request=request, stream=httpx.ByteStream(json.dumps(data).encode())
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        partial = acquire_batch(
            catalog,
            value,
            authorization=auth,
            admission=admission,
            client=client,
            clock_us=lambda: 1_000_000,
        )
        assert partial.status == "partial"
        assert (
            partial.source_results[0]["failure_code"] == "SOURCE_CREDENTIAL_UNAVAILABLE"
        )
        assert partial.source_results[1]["status"] == "complete"
        assert not calls
        with Context.snapshot(catalog) as context:
            assert (
                context.db.execute(
                    "SELECT count(*) FROM source_inventory_evidence"
                ).fetchone()[0]
                == 0
            )
        monkeypatch.setenv(name, "synthetic-secret-never-saved")
        complete = acquire_batch(
            catalog,
            value,
            authorization=auth,
            admission=admission,
            client=client,
            clock_us=lambda: 1_000_000,
        )
        assert complete.status == "complete" and len(calls) == 2
        assert complete.source_results[1]["replayed"]
    state = operational_state(catalog)
    assert len(state["acquisition_requests"]) == 1
    assert "synthetic-secret-never-saved" not in json.dumps(state)


@pytest.mark.parametrize(
    "problem", ["secret", "unsupported", "authority", "zero-sources", "unconfigured"]
)
def test_invalid_frozen_batch_is_refused_before_request_or_progress_write(
    tmp_path, problem
):
    catalog = tmp_path / "catalog"
    init_catalog_stores(catalog, stores=("repository", "operational"))
    source = str(uuid4())
    value = document(
        [
            {
                "source_registration_uuidv4": source,
                "kind": "github_inventory",
                "settings": {
                    "service_instance_uuidv4": str(uuid4()),
                    "owner": "original",
                },
            }
        ]
    )
    value["credential_refs"] = {source: {"kind": "environment", "name": "FROZEN_TOKEN"}}
    if problem == "secret":
        value["sources"][0]["settings"]["git_config"] = {
            "http.extraHeader": "Authorization: Bearer synthetic-secret"
        }
    elif problem == "unsupported":
        value["sources"][0]["kind"] = "arbitrary_transport"
    elif problem == "zero-sources":
        value["sources"] = []
        value["credential_refs"] = {}
    elif problem == "unconfigured":
        value["sources"][0] = {
            "source_registration_uuidv4": source,
            "kind": "local_git",
            "settings": {},
        }
        value["credential_refs"] = {}
    before = operational_state(catalog)
    with pytest.raises(ValueError):
        acquire_batch(catalog, value)
    assert operational_state(catalog) == before
