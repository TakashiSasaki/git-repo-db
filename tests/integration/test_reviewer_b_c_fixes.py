"""Regression and counterexample tests for Reviewer B and Reviewer C findings.

Covers:
- R-B1: Incompatible or cross-PR code-list membership in _assess_code and Exchange.
- R-B2: Explicit code-list scope availability and completeness isolation.
- R-B6: Non-HTTP continuation tokens raising structured CatalogError.
- C01: Captured Ref/tag metadata contradicting available object path vs absent dependency.
- C02: Directory and tree completeness handling of Gitlink (0o160000) boundaries.
- C03: Decoder comparison memoization cache, boolean settings rejection, and safe candidate isolation.
- C04: Marker-free code evidence admission and promotion dependencies.
- C05: Explicit code query target resolution without current-code linkage.
"""

import base64
import hashlib
import json

import pytest

from repo_catalog.adapters.git.importer import GitImporter
from repo_catalog.adapters.git.parsing import GitParsing
from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.adapters.github.transport import GitHubTransport
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.git_query_context import decoded_fact
from repo_catalog.application.job_service import JobService
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.query_service import QueryService
from repo_catalog.application.repository_identity import add_endpoint
from repo_catalog.domain.git_decoding import (
    _DECODER_COMPARISON_CACHE,
    clear_decoder_cache,
    validate_decoded_value,
)
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.support.domain_facts import (
    SERVICE,
    SOURCE,
    repository_uuid,
)
from tests.support.git_fixture import FixtureRepo


def oid(fmt, typ, data):
    return hashlib.new(fmt, f"{typ} {len(data)}\0".encode() + data).digest()


def opened(path):
    MaintenanceService(path).init("catalog-text-v1", 64 * 1024 * 1024, 0)
    return Store(path)


def put(store, table, **values):
    return store.execute(
        f"INSERT INTO {table}({','.join(values)}) VALUES({','.join('?' for _ in values)})",
        tuple(values.values()),
    )


def git_catalog(path, remote, owner):
    store = opened(path)
    with store.transaction():
        put(store, "repositories", repository_uuidv4=owner, name="synthetic", metadata="{}")
        add_endpoint(store, owner, remote.url)
    repo = {"repository_uuidv4": owner, "name": "synthetic"}
    job = JobService(store).create("sync", {"kind": "git"})
    GitImporter(store, CancellationToken()).sync(repo, job)
    JobService(store).update(job, "complete")
    return store


# =====================================================================
# R-B1: Cross-PR / Swapped code listing validation
# =====================================================================


def _setup_collector_db(tmp_path):
    store = opened(tmp_path / "collector_db")
    repo1 = repository_uuid(1)
    repo2 = repository_uuid(2)

    with store.transaction():
        # Insert repositories and bindings
        put(store, "repositories", repository_uuidv4=repo1, name="repo1", metadata="{}")
        put(store, "repositories", repository_uuidv4=repo2, name="repo2", metadata="{}")
        put(store, "service_instances", service_instance_uuidv4=SERVICE, service_kind="github", name="test", metadata="{}")
        put(store, "sources", source_registration_uuidv4=SOURCE, source_id="src", service_instance_uuidv4=SERVICE, discovery_kind="github_inventory", name="test", settings="{}")
        put(store, "repository_bindings", repository_binding_id="b-1", repository_uuidv4=repo1, service_instance_uuidv4=SERVICE, provider_repository_id="1", metadata="{}")
        put(store, "repository_bindings", repository_binding_id="b-2", repository_uuidv4=repo2, service_instance_uuidv4=SERVICE, provider_repository_id="2", metadata="{}")

        # Insert Change Requests
        put(
            store,
            "change_requests",
            change_request_id="cr-1",
            repository_uuidv4=repo1,
            repository_binding_id="b-1",
            change_request_kind="pull_request",
            provider_change_request_number=1,
        )
        put(
            store,
            "change_requests",
            change_request_id="cr-2",
            repository_uuidv4=repo1,
            repository_binding_id="b-1",
            change_request_kind="pull_request",
            provider_change_request_number=2,
        )
        put(
            store,
            "change_requests",
            change_request_id="cr-other",
            repository_uuidv4=repo2,
            repository_binding_id="b-2",
            change_request_kind="pull_request",
            provider_change_request_number=1,
        )

        # Insert Fetch Collections with matching scope_json
        scope1 = json.dumps({"repository_uuidv4": repo1, "change_request_id": "cr-1", "endpoint": "https://api.github.com/commits"})
        scope2 = json.dumps({"repository_uuidv4": repo1, "change_request_id": "cr-2", "endpoint": "https://api.github.com/commits"})
        scope_other = json.dumps({"repository_uuidv4": repo2, "change_request_id": "cr-other", "endpoint": "https://api.github.com/commits"})

        put(
            store,
            "fetch_collections",
            fetch_collection_id="fc-1",
            repository_uuidv4=repo1,
            source_id="src",
            kind="pr-commits",
            change_request_id="cr-1",
            scope_json=scope1,
        )
        put(
            store,
            "fetch_collections",
            fetch_collection_id="fc-2",
            repository_uuidv4=repo1,
            source_id="src",
            kind="pr-commits",
            change_request_id="cr-2",
            scope_json=scope2,
        )
        put(
            store,
            "fetch_collections",
            fetch_collection_id="fc-other-repo",
            repository_uuidv4=repo2,
            source_id="src",
            kind="pr-commits",
            change_request_id="cr-other",
            scope_json=scope_other,
        )

        # Insert Code Listings
        put(
            store,
            "code_listings",
            code_listing_id="list-commits-1",
            fetch_collection_id="fc-1",
            change_request_id="cr-1",
            kind="commits",
            object_format="sha1",
            head_oid=b"\x11" * 20,
            base_oid=b"\x00" * 20,
        )
        put(
            store,
            "code_listings",
            code_listing_id="list-files-1",
            fetch_collection_id="fc-1",
            change_request_id="cr-1",
            kind="files",
            object_format="sha1",
            head_oid=b"\x11" * 20,
            base_oid=b"\x00" * 20,
        )
        put(
            store,
            "code_listings",
            code_listing_id="list-commits-2",
            fetch_collection_id="fc-2",
            change_request_id="cr-2",
            kind="commits",
            object_format="sha1",
            head_oid=b"\x11" * 20,
            base_oid=b"\x00" * 20,
        )
        put(
            store,
            "code_listings",
            code_listing_id="list-commits-other-repo",
            fetch_collection_id="fc-other-repo",
            change_request_id="cr-other",
            kind="commits",
            object_format="sha1",
            head_oid=b"\x11" * 20,
            base_oid=b"\x00" * 20,
        )
    return store, repo1, repo2


def test_assess_code_rejects_cross_pr_and_swapped_listings(tmp_path):
    store, repo1, _ = _setup_collector_db(tmp_path)
    job = JobService(store).create("sync", {"kind": "pr"})
    store.expected_attempt = 1

    collector = GitHubCollector(store, CancellationToken())
    repo_row = {"repository_uuidv4": repo1, "source_id": "src"}
    pr_row = {"change_request_id": "cr-1", "provider_change_request_number": 1}
    pr_payload = {
        "head": {"sha": ("11" * 20)},
        "base": {"sha": ("00" * 20)},
    }

    # 1. Positive case: valid commits listing and files listing
    missing = []
    listings = [("commits", "list-commits-1"), ("files", "list-files-1")]
    res = collector._assess_code(
        repo_row, pr_row, job, pr_payload, pr_payload, listings, True, missing
    )
    assert res is not None
    assert not any(m.get("reason") == "INVALID_CODE_LISTING" for m in missing)
    row = store.one(
        "SELECT commit_code_listing_id, file_code_listing_id FROM code_assessments WHERE code_assessment_id=?",
        (res,),
    )
    assert row["commit_code_listing_id"] == "list-commits-1"
    assert row["file_code_listing_id"] == "list-files-1"

    # 2. Negative case: cross-PR commits listing (list-commits-2 from PR 2)
    missing = []
    listings_cross_pr = [("commits", "list-commits-2"), ("files", "list-files-1")]
    res_cross = collector._assess_code(
        repo_row, pr_row, job, pr_payload, pr_payload, listings_cross_pr, True, missing
    )
    assert any(m.get("reason") == "INVALID_CODE_LISTING" for m in missing)
    row_cross = store.one(
        "SELECT commit_code_listing_id, file_code_listing_id FROM code_assessments WHERE code_assessment_id=?",
        (res_cross,),
    )
    assert row_cross["commit_code_listing_id"] is None

    # 3. Negative case: cross-repo listing
    missing = []
    listings_cross_repo = [
        ("commits", "list-commits-other-repo"),
        ("files", "list-files-1"),
    ]
    res_cross_repo = collector._assess_code(
        repo_row, pr_row, job, pr_payload, pr_payload, listings_cross_repo, True, missing
    )
    assert any(m.get("reason") == "INVALID_CODE_LISTING" for m in missing)
    row_cross_repo = store.one(
        "SELECT commit_code_listing_id, file_code_listing_id FROM code_assessments WHERE code_assessment_id=?",
        (res_cross_repo,),
    )
    assert row_cross_repo["commit_code_listing_id"] is None

    # 4. Negative case: swapped listings (files listing given as commits)
    missing = []
    listings_swapped = [("commits", "list-files-1"), ("files", "list-commits-1")]
    res_swapped = collector._assess_code(
        repo_row, pr_row, job, pr_payload, pr_payload, listings_swapped, True, missing
    )
    assert any(m.get("reason") == "INVALID_CODE_LISTING" for m in missing)
    row_swapped = store.one(
        "SELECT commit_code_listing_id, file_code_listing_id FROM code_assessments WHERE code_assessment_id=?",
        (res_swapped,),
    )
    assert row_swapped["commit_code_listing_id"] is None
    assert row_swapped["file_code_listing_id"] is None


def test_exchange_admit_rejects_cross_pr_and_swapped_code_assessments(tmp_path):
    store, repo1, _ = _setup_collector_db(tmp_path)
    graph = Graph(store.connection)

    # 1. Valid partial code_assessment record
    valid_record = {
        "code_assessment_id": "ca-valid",
        "change_request_id": "cr-1",
        "repository_uuidv4": repo1,
        "commit_code_listing_id": "list-commits-1",
        "file_code_listing_id": "list-files-1",
        "state": "partial",
        "object_format": "sha1",
        "head_oid": {"$bytes": base64.b64encode(b"\x11" * 20).decode("ascii")},
        "base_oid": {"$bytes": base64.b64encode(b"\x00" * 20).decode("ascii")},
        "observed_at_us": 100,
        "parser_module": "repo_catalog.adapters.github.collector",
        "parser_version": "1.0.0",
        "details_json": "{}",
    }
    envelope = {
        "key": "code_assessments:ca-valid",
        "table": "code_assessments",
        "values": valid_record,
    }
    status = graph._admit(envelope, "00000000-0000-4000-8000-000000000301", repo1)
    assert status is None

    # 2. Cross-PR listing: commit listing belongs to cr-2
    cross_pr_record = dict(
        valid_record,
        code_assessment_id="ca-cross-pr",
        commit_code_listing_id="list-commits-2",
    )
    envelope_cross_pr = {
        "key": "code_assessments:ca-cross-pr",
        "table": "code_assessments",
        "values": cross_pr_record,
    }
    status = graph._admit(
        envelope_cross_pr, "00000000-0000-4000-8000-000000000301", repo1
    )
    assert status == "invalid:code_listing_context"

    # 3. Swapped listing: commit listing has kind == 'files'
    swapped_record = dict(
        valid_record,
        code_assessment_id="ca-swapped",
        commit_code_listing_id="list-files-1",
    )
    envelope_swapped = {
        "key": "code_assessments:ca-swapped",
        "table": "code_assessments",
        "values": swapped_record,
    }
    status = graph._admit(
        envelope_swapped, "00000000-0000-4000-8000-000000000301", repo1
    )
    assert status == "invalid:code_listing_context"

    # 4. Cross-repo listing
    cross_repo_record = dict(
        valid_record,
        code_assessment_id="ca-cross-repo",
        commit_code_listing_id="list-commits-other-repo",
    )
    envelope_cross_repo = {
        "key": "code_assessments:ca-cross-repo",
        "table": "code_assessments",
        "values": cross_repo_record,
    }
    status = graph._admit(
        envelope_cross_repo, "00000000-0000-4000-8000-000000000301", repo1
    )
    assert status == "invalid:code_listing_context"


# =====================================================================
# R-B2 & C05: Explicit code-list scope and unlinked target availability
# =====================================================================


def test_explicit_code_list_scope_isolated_completeness(tmp_path):
    store, repo1, _ = _setup_collector_db(tmp_path)
    with store.transaction():
        # Insert code commits under list-commits-1
        put(
            store,
            "code_commits",
            code_listing_id="list-commits-1",
            position=0,
            repository_uuidv4=repo1,
            object_format="sha1",
            oid=b"\x11" * 20,
            metadata="{}",
        )
        put(
            store,
            "code_listing_progress",
            code_listing_id="list-commits-1",
            state="complete",
            terminal=1,
            page_count=1,
            context_proven=1,
        )
        put(
            store,
            "code_assessments",
            code_assessment_id="ca-single",
            change_request_id="cr-1",
            repository_uuidv4=repo1,
            commit_code_listing_id="list-commits-1",
            file_code_listing_id=None,
            state="partial",
            object_format="sha1",
            head_oid=b"\x11" * 20,
            base_oid=b"\x00" * 20,
            observed_at_us=100,
            parser_module="test",
            parser_version="1.0",
            details_json="{}",
        )

    qs = QueryService(store.path)

    # When querying explicit listing_kind='commits':
    res_commits = qs.query(
        "pr code",
        {
            "repo": repo1,
            "provider_change_request_number": 1,
            "listing_kind": "commits",
        },
    )
    gaps_commits = [
        m for m in res_commits.coverage.missing if m.get("reason") == "code_assessment_incomplete"
    ]
    assert not gaps_commits

    # When querying explicit listing_kind='files':
    res_files = qs.query(
        "pr code",
        {
            "repo": repo1,
            "provider_change_request_number": 1,
            "listing_kind": "files",
        },
    )
    gaps_files = [
        m for m in res_files.coverage.missing if m.get("reason") == "code_assessment_incomplete"
    ]
    assert len(gaps_files) > 0


def test_explicit_code_query_without_current_code_linkage(tmp_path):
    store, repo1, _ = _setup_collector_db(tmp_path)
    with store.transaction():
        put(
            store,
            "code_commits",
            code_listing_id="list-commits-1",
            position=0,
            repository_uuidv4=repo1,
            object_format="sha1",
            oid=b"\x11" * 20,
            metadata="{}",
        )

    qs = QueryService(store.path)
    res = qs.query(
        "pr code",
        {
            "repo": repo1,
            "provider_change_request_number": 1,
            "code_listing_id": "list-commits-1",
            "listing_kind": "commits",
        },
    )
    items = res.data["items"]
    assert len(items) == 1
    assert items[0]["kind"] == "commits"


# =====================================================================
# R-B6: Non-HTTP continuation tokens raising CatalogError
# =====================================================================


def test_transport_and_collector_reject_non_http_continuation_tokens():
    cfg = {
        "rest_base_url": "https://api.github.com",
        "graphql_url": "https://api.github.com/graphql",
        "token_env_var": "GITHUB_TOKEN",
        "read_timeout_seconds": 10,
        "connect_timeout_seconds": 5,
        "rest_api_version": "2022-11-28",
        "max_attempts": 3,
    }
    transport = GitHubTransport(cfg, CancellationToken())

    # 1. Non-string URL
    with pytest.raises(CatalogError) as exc_info:
        transport.validate_url(12345)
    assert exc_info.value.code == "UNSAFE_API_URL"

    # 2. git: continuation scheme
    with pytest.raises(CatalogError) as exc_info:
        transport.validate_url("git://api.github.com/repos/test/pulls")
    assert exc_info.value.code == "UNSAFE_API_URL"

    # 3. Opaque git: token
    with pytest.raises(CatalogError) as exc_info:
        transport.validate_url("git:opaque-continuation-cursor")
    assert exc_info.value.code == "UNSAFE_API_URL"

    # 4. Out of range port (urllib ValueError)
    with pytest.raises(CatalogError) as exc_info:
        transport.validate_url("https://api.github.com:99999999/repos/test")
    assert exc_info.value.code == "UNSAFE_API_URL"

    # 5. Invalid path
    with pytest.raises(CatalogError) as exc_info:
        transport.validate_url("https://api.github.com/repos/../secret")
    assert exc_info.value.code == "UNSAFE_API_URL"

    # 6. Mock response with git: next link
    class MockResponse:
        links = {"next": {"url": "git://api.github.com/repos/test?page=2"}}

    with pytest.raises(CatalogError) as exc_info:
        transport.next_url(MockResponse())
    assert exc_info.value.code == "UNSAFE_API_URL"


# =====================================================================
# C01: Captured Ref/tag metadata contradiction vs absent dependency
# =====================================================================


def test_captured_ref_contradiction_versus_absent_dependency(tmp_path):
    store = opened(tmp_path / "c01_store")
    repo = repository_uuid(1)
    parser = GitParsing(store)

    with store.transaction():
        put(store, "repositories", repository_uuidv4=repo, name="repo1", metadata="{}")
        put(
            store,
            "git_acquisitions",
            git_acquisition_id="acq-1",
            repository_uuidv4=repo,
            kind="git",
            request="{}",
        )

    # 1. Lightweight tag claiming target_type='commit' with peeled_oid provided
    with pytest.raises(CatalogError) as exc_info:
        parser.validate_ref("acq-1", "sha1", b"\x11" * 20, "commit", b"\x22" * 20)
    assert exc_info.value.code == "GIT_REF_IDENTITY"

    # 2. Target object exists in database as blob, but ref claims target_type='commit'
    blob_content = b"sample blob bytes"
    blob_oid = oid("sha1", "blob", blob_content)
    with store.transaction():
        put(
            store,
            "git_objects",
            git_object_id=1,
            object_format="sha1",
            oid=blob_oid,
            type="blob",
            size=len(blob_content),
            verified=1,
        )
    with pytest.raises(CatalogError) as exc_info:
        parser.validate_ref("acq-1", "sha1", blob_oid, "commit", None)
    assert exc_info.value.code == "GIT_REF_IDENTITY"

    # 3. Target object genuinely absent from database -> INCOMPLETE_CLOSURE
    absent_oid = b"\x33" * 20
    with pytest.raises(CatalogError) as exc_info:
        parser.validate_ref("acq-1", "sha1", absent_oid, "commit", None)
    assert exc_info.value.code == "INCOMPLETE_CLOSURE"

    # 4. Annotated tag target contradiction:
    # Tag object T points to commit C1, but ref claims peeled_oid=C2
    tag_body = b"object " + (b"1" * 40) + b"\ntype commit\ntag v1\ntagger T <t@t> 0 +0000\n\ntag msg"
    tag_oid = oid("sha1", "tag", tag_body)
    c1_oid = b"\x44" * 20
    c2_oid = b"\x55" * 20
    with store.transaction():
        put(
            store,
            "git_objects",
            git_object_id=2,
            object_format="sha1",
            oid=tag_oid,
            type="tag",
            size=len(tag_body),
            verified=1,
        )
        put(
            store,
            "tag_objects",
            git_object_id=2,
            target_format="sha1",
            target_oid=c1_oid,
            target_type="commit",
            raw_payload=tag_body,
        )
    # Ref claims peeled_oid is c2_oid instead of c1_oid -> contradiction!
    with pytest.raises(CatalogError) as exc_info:
        parser.validate_ref("acq-1", "sha1", tag_oid, "tag", c2_oid)
    assert exc_info.value.code == "GIT_REF_IDENTITY"

    # Ref claims correct peeled_oid c1_oid, but c1_oid is absent from sources -> INCOMPLETE_CLOSURE
    with pytest.raises(CatalogError) as exc_info:
        parser.validate_ref("acq-1", "sha1", tag_oid, "tag", c1_oid)
    assert exc_info.value.code == "INCOMPLETE_CLOSURE"


# =====================================================================
# C02: Gitlink (0o160000) boundary handling in directory / tree queries
# =====================================================================


def test_gitlink_boundary_preservation(tmp_path):
    owner = repository_uuid(1)
    remote = FixtureRepo(tmp_path / "remote.git")
    submodule_commit = "1" * 40
    remote.commit("A", {b"regular.txt": b"hello world", b"submodule": ("160000", submodule_commit)})
    remote.ref("refs/heads/main", "A")
    store = git_catalog(tmp_path / "catalog", remote, owner)

    qs = QueryService(store.path)
    result = qs.query("tree list", {"repo": owner, "ref": "refs/heads/main"})
    items = result.data["items"]
    submodule_item = next(item for item in items if item.get("path_utf8") == "submodule")
    assert submodule_item["mode"] == "160000"
    assert submodule_item["raw_available"] is False
    # No spurious gaps for tree child or body
    gaps = [m for m in result.coverage.missing if m.get("reason") in ("tree_child_unavailable", "body_not_saved")]
    assert not gaps


# =====================================================================
# C03: Decoder memoization cache, settings validation, and malformed row isolation
# =====================================================================


def test_decoder_memoization_cache_and_boolean_rejection():
    clear_decoder_cache()
    raw_body = b"valid text content"
    settings = {
        "parser_module": "repo_catalog",
        "parser_version": "1.0",
        "text_encoding": "utf-8",
        "metadata_encoding": "utf-8",
        "metadata_errors": "strict",
        "max_text_blob_bytes": 1024,
    }
    key = hashlib.sha256(
        json.dumps(settings, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    # 1. Validation succeeds and populates cache
    validate_decoded_value(
        "text", "sha1", raw_body, key, settings, "eligible", "valid text content", "{}"
    )
    assert len(_DECODER_COMPARISON_CACHE) == 1

    # 2. Second validation hits cache
    validate_decoded_value(
        "text", "sha1", raw_body, key, settings, "eligible", "valid text content", "{}"
    )
    assert len(_DECODER_COMPARISON_CACHE) == 1

    # 3. Changed raw bytes causes cache miss
    other_bytes = b"different text"
    validate_decoded_value(
        "text", "sha1", other_bytes, key, settings, "eligible", "different text", "{}"
    )
    assert len(_DECODER_COMPARISON_CACHE) == 2

    # 4. Strict rejection of boolean in max_text_blob_bytes
    bool_settings = dict(settings, max_text_blob_bytes=True)
    bool_key = hashlib.sha256(
        json.dumps(bool_settings, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with pytest.raises(CatalogError) as exc_info:
        validate_decoded_value(
            "text", "sha1", raw_body, bool_key, bool_settings, "eligible", "valid text content", "{}"
        )
    assert exc_info.value.code == "GIT_DECODER_FACT"


def test_malformed_decoder_rows_in_decoded_fact():
    class MockStore:
        def all(self, query, params):
            # Return two candidate rows for commit:
            # Row 1 has malformed metadata JSON
            # Row 2 has valid metadata JSON
            return [
                {
                    "git_fact_uuidv4": "fact-1",
                    "git_object_id": 20,
                    "decoder_key": "commit-def",
                    "message_text": "good commit message",
                    "metadata": "NOT_VALID_JSON{",
                    "parser_module": "test",
                },
                {
                    "git_fact_uuidv4": "fact-2",
                    "git_object_id": 20,
                    "decoder_key": "commit-def",
                    "message_text": "good commit message",
                    "metadata": '{"author": "Test"}',
                    "parser_module": "test",
                },
            ]

    res = decoded_fact(MockStore(), 20, "commit", decoder_key="commit-def")
    # Malformed row was excluded, valid row was used as fact
    assert res["fact"] is not None
    assert res["fact"]["message_text"] == "good commit message"
    assert res["decoder_conflict"] is False
