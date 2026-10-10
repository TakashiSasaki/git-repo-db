"""Requested PR coverage is independent of result pagination and code-only gaps."""

import json
import sqlite3

import pytest

from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.current_resources import CurrentResources
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application import pr_queries
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.query_service import QueryService
from repo_catalog.application.repository_identity import add_instance, bind
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.support.cli import run

REPOSITORY = "00000000-0000-4000-8000-000000000401"


def add_fact(store, table, **values):
    """Insert explicit direct domain rows, never synthetic parser results."""
    return store.execute(
        f"INSERT INTO {table}({','.join(values)}) VALUES({','.join('?' for _ in values)})",
        tuple(values.values()),
    ).lastrowid


def candidate(store, pr, kind, **fields):
    owner = store.one(
        "SELECT c.*,b.service_instance_uuidv4 FROM change_requests c JOIN repository_bindings b USING(repository_binding_id) WHERE c.change_request_id=?",
        (pr,),
    )
    scope = {
        key: owner[key]
        for key in (
            "change_request_id",
            "repository_uuidv4",
            "repository_binding_id",
            "service_instance_uuidv4",
        )
    }
    return {
        **scope,
        "kind": kind,
        "observed_at_us": 0,
        "parsed_at_us": 0,
        "provider_updated_at_us": 0 if kind != "review-thread" else None,
        "provider_clock_scope": "github-pr-updated-at"
        if kind in ("change-request", "pr-body", "pr-title")
        else None,
        "parser_module": __name__,
        "parser_version": "1",
        "acquisition_scope": {**scope, "endpoint": "synthetic-pr-query"},
        **fields,
    }


def admit_pr_state(store, pr, **fields):
    result = CurrentApiState(store).admit(
        "change_request_state",
        candidate(store, pr, "change-request", **fields),
        source="import",
    )
    assert result.status in ("accepted", "identical")
    return pr


def add_document(store, pr, document_id, body, *, kind="pr-body", thread=None):
    fields = {
        "provider_change_request_document_id": document_id,
        "body": body,
        "body_status": "present" if body is not None else "missing",
    }
    if kind == "review-comment":
        fields["review_thread_provider_resource_id"] = thread
    row = candidate(store, pr, kind, **fields)
    existing = store.one(
        "SELECT provider_updated_at_us FROM document_state WHERE change_request_id=? AND kind=? AND provider_change_request_document_id=?",
        (pr, kind, document_id),
    )
    if existing:
        row["provider_updated_at_us"] = existing[0] + 1
    result = (
        CurrentResources(store).admit(row, source="import")
        if kind in ("review", "review-comment")
        else CurrentApiState(store).admit("document_state", row, source="import")
    )
    assert result.status in ("accepted", "identical")
    return pr, kind, document_id


def add_pr(store, repository, binding, number, *, kind="pull_request"):
    pr = f"repo:{number}:{kind}"
    store.execute(
        "INSERT INTO change_requests VALUES(?,?,?,?,?)",
        (pr, repository, binding, kind, number),
    )
    admit_pr_state(store, pr, state="open", merged=False)
    add_document(store, pr, str(number), f"needle body for {pr}")
    for coverage_kind in ("pr-documents", "pr-code"):
        store.coverage(
            repository,
            coverage_kind,
            "complete",
            change_request_id=pr,
            observed_at_us=0,
        )
    return pr


@pytest.fixture
def pr_catalog(tmp_path):
    state = tmp_path / "catalog"
    MaintenanceService(state).init("catalog-text-v1", 67_108_864, 0)
    with Store(state) as store:
        with store.transaction():
            namespace = add_instance(store, "github", "synthetic")
            store.execute(
                "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES('00000000-0000-4000-8000-000000000401','synthetic/repo','{}')"
            )
            bind(store, "00000000-0000-4000-8000-000000000401", namespace, "1")
            binding = store.one(
                "SELECT repository_binding_id FROM repository_bindings WHERE repository_uuidv4='00000000-0000-4000-8000-000000000401'"
            )[0]
            for number in (1, 2, 3):
                add_pr(store, "00000000-0000-4000-8000-000000000401", binding, number)
            for kind in ("pr", "pr-documents"):
                store.coverage(
                    "00000000-0000-4000-8000-000000000401",
                    kind,
                    "complete",
                    observed_at_us=0,
                )
            store.advance_local_revision()
        yield state, store
        assert not store.all("PRAGMA foreign_key_check")
        assert store.one("PRAGMA integrity_check")[0] == "ok"


def add_gap(store, kind, source, *, number=1, coverage_state="partial"):
    pr = f"repo:{number}:pull_request"
    if source == "claim":
        store.coverage(
            "00000000-0000-4000-8000-000000000401",
            kind,
            coverage_state,
            change_request_id=pr,
            observed_at_us=1,
        )
        return
    store.execute(
        "INSERT INTO jobs(job_id,kind,request,current_attempt,created_at_us) VALUES('query-job','sync','{}',1,0)"
    )
    store.execute(
        "INSERT INTO job_attempts(job_id,attempt,state,created_at_us,checkpoint) VALUES('query-job',1,'failed',0,'{}')"
    )
    store.execute(
        "INSERT INTO resume_scopes(resume_scope_id,repository_uuidv4,request_context,parser_version,confidence) VALUES('query-resume','00000000-0000-4000-8000-000000000401','{}','test','proven')"
    )
    store.execute(
        "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,kind,resume_scope_id,scope_json,observed_at_us) VALUES('query-collection','00000000-0000-4000-8000-000000000401',?,?,'query-resume',?,1)",
        (
            pr,
            kind,
            json.dumps(
                {
                    "repository_uuidv4": REPOSITORY,
                    "change_request_id": pr,
                    "endpoint": "query-test",
                }
            ),
        ),
    )
    store.execute(
        "INSERT INTO collection_progress(fetch_collection_id,job_id,attempt,state) VALUES('query-collection','query-job',1,'partial')"
    )
    store.execute(
        "INSERT INTO completion_markers(fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES('query-collection','partial','{}',1)"
    )


@pytest.mark.parametrize("kind", ["pr-commits", "pr-files", "commits", "files"])
@pytest.mark.parametrize("source", ["claim", "collection"])
def test_document_queries_ignore_code_listing_gaps(pr_catalog, kind, source):
    state, store = pr_catalog
    with store.transaction():
        add_gap(store, kind, source)
        store.advance_local_revision()
    for command in (
        (
            "pr",
            "documents",
            "--repo",
            "00000000-0000-4000-8000-000000000401",
            "--provider-change-request-number",
            1,
        ),
        (
            "search",
            "pr",
            "--repo",
            "00000000-0000-4000-8000-000000000401",
            "--literal",
            "needle",
        ),
    ):
        result = run(state, *command)
        assert result["coverage"]["complete_for_requested_scope"] is True
        assert result["coverage"]["missing"] == []
        assert result["data"]["items"]
    # The same saved gap is still relevant to the combined PR/code scope.
    result = run(
        state,
        "pr",
        "list",
        "--repo",
        "00000000-0000-4000-8000-000000000401",
        "--limit",
        1,
        expected=3,
    )
    assert result["coverage"]["complete_for_requested_scope"] is False


@pytest.mark.parametrize("kind", ["issue-comment", "threads", "pr-documents"])
@pytest.mark.parametrize("source", ["claim", "collection"])
def test_document_queries_retain_document_gaps(pr_catalog, kind, source):
    state, store = pr_catalog
    with store.transaction():
        add_gap(store, kind, source)
        store.advance_local_revision()
    for command in (
        (
            "pr",
            "documents",
            "--repo",
            "00000000-0000-4000-8000-000000000401",
            "--provider-change-request-number",
            1,
        ),
        (
            "search",
            "pr",
            "--repo",
            "00000000-0000-4000-8000-000000000401",
            "--literal",
            "needle",
        ),
    ):
        result = run(state, *command, expected=3)
        assert result["coverage"]["complete_for_requested_scope"] is False
        assert result["data"]["items"]


@pytest.mark.parametrize(
    "selector",
    [("--commit", "sha1:" + "01" * 20), ("--path", "file"), ("--path-b64", "ZmlsZQ==")],
)
def test_code_filter_requires_code_coverage_even_without_results(pr_catalog, selector):
    state, store = pr_catalog
    with store.transaction():
        add_gap(store, "pr-commits", "claim")
        store.advance_local_revision()
    result = run(
        state,
        "search",
        "pr",
        "--repo",
        "00000000-0000-4000-8000-000000000401",
        "--literal",
        "needle",
        *selector,
        expected=3,
    )
    assert result["data"]["items"] == []
    assert any(
        gap["reason"] == "saved_scope_incomplete"
        for gap in result["coverage"]["missing"]
    )


@pytest.mark.parametrize(
    "command",
    [
        ("pr", "list", "--repo", "00000000-0000-4000-8000-000000000401"),
        (
            "search",
            "pr",
            "--repo",
            "00000000-0000-4000-8000-000000000401",
            "--literal",
            "needle",
        ),
    ],
)
def test_full_requested_scope_coverage_is_identical_on_every_page(pr_catalog, command):
    state, store = pr_catalog
    with store.transaction():
        add_gap(store, "pr-documents", "claim", number=3, coverage_state="unknown")
        store.advance_local_revision()
    full = run(state, *command, "--limit", 100, expected=3)
    assert [
        item["provider_change_request_number"] for item in full["data"]["items"]
    ] == [1, 2, 3]
    assert len(full["coverage"]["missing"]) == 1
    first = None
    for limit in (1, 2, 100):
        result = run(state, *command, "--limit", limit, expected=3)
        assert result["catalog"] == full["catalog"]
        assert result["coverage"] == full["coverage"]
        assert result["data"]["items"] == full["data"]["items"][:limit]
        assert result["data"]["page"]["has_more"] is (limit < 3)
        if limit == 1:
            first = result
    cursor = first["data"]["page"]["next_cursor"]
    for number in (2, 3):
        result = run(state, *command, "--limit", 1, "--cursor", cursor, expected=3)
        assert result["catalog"] == full["catalog"]
        assert result["coverage"] == full["coverage"]
        assert result["data"]["items"] == full["data"]["items"][number - 1 : number]
        cursor = result["data"]["page"]["next_cursor"]
    assert cursor is None


def test_code_observation_gap_beyond_page_is_reported(pr_catalog):
    state, store = pr_catalog
    with store.transaction():
        add_fact(
            store,
            "code_assessments",
            code_assessment_id="partial-target",
            repository_uuidv4=REPOSITORY,
            change_request_id="repo:3:pull_request",
            state="partial",
            observed_at_us=0,
            parser_module=__name__,
            parser_version="1",
            details_json="{}",
        )
        store.advance_local_revision()
    first = run(
        state,
        "pr",
        "list",
        "--repo",
        "00000000-0000-4000-8000-000000000401",
        "--limit",
        1,
        expected=3,
    )
    full = run(
        state,
        "pr",
        "list",
        "--repo",
        "00000000-0000-4000-8000-000000000401",
        "--limit",
        100,
        expected=3,
    )
    assert first["coverage"] == full["coverage"]
    assert [gap["reason"] for gap in first["coverage"]["missing"]] == [
        "code_assessment_incomplete"
    ]


@pytest.mark.parametrize("role", ["head", "base"])
def test_new_current_api_observation_requires_its_own_code_observation(
    pr_catalog, role
):
    state, store = pr_catalog
    with store.transaction():
        admit_pr_state(
            store,
            "repo:3:pull_request",
            provider_updated_at_us=1,
            observed_at_us=1,
            object_format="sha1",
            **{role + "_oid": "01" * 20},
        )
        store.advance_local_revision()
    assert (
        store.one(
            "SELECT coverage_state FROM current_coverage WHERE change_request_id='repo:3:pull_request' AND kind='pr-code'"
        )[0]
        == "complete"
    )
    first = run(
        state,
        "pr",
        "list",
        "--repo",
        "00000000-0000-4000-8000-000000000401",
        "--limit",
        1,
        expected=3,
    )
    selected = run(
        state,
        "pr",
        "show",
        "--repo",
        "00000000-0000-4000-8000-000000000401",
        "--provider-change-request-number",
        3,
        expected=3,
    )
    assert first["coverage"] == selected["coverage"]
    assert any(
        gap["reason"] == "code_assessment_missing"
        and gap["change_request_id"] == "repo:3:pull_request"
        for gap in selected["coverage"]["missing"]
    )
    docs = run(
        state,
        "pr",
        "documents",
        "--repo",
        "00000000-0000-4000-8000-000000000401",
        "--provider-change-request-number",
        3,
    )
    assert docs["coverage"]["missing"] == []
    assert (
        store.one(
            "SELECT coverage_state FROM current_coverage WHERE change_request_id='repo:3:pull_request' AND kind='pr-code'"
        )[0]
        == "complete"
    )  # Read-side structural diagnostics do not fabricate claims.


def test_identity_selection_excludes_other_pr_gaps_but_empty_search_retains_them(
    pr_catalog,
):
    state, store = pr_catalog
    with store.transaction():
        add_gap(store, "pr-documents", "claim", number=3, coverage_state="unknown")
        store.advance_local_revision()
    for action in ("show", "documents"):
        result = run(
            state,
            "pr",
            action,
            "--repo",
            "00000000-0000-4000-8000-000000000401",
            "--provider-change-request-number",
            1,
        )
        assert result["coverage"]["missing"] == []
    excluded_kind = run(
        state,
        "pr",
        "list",
        "--repo",
        "00000000-0000-4000-8000-000000000401",
        "--change-request-kind",
        "merge_request",
    )
    assert excluded_kind["data"]["items"] == []
    assert excluded_kind["coverage"]["missing"] == []
    result = run(
        state,
        "search",
        "pr",
        "--repo",
        "00000000-0000-4000-8000-000000000401",
        "--literal",
        "absent",
        expected=3,
    )
    assert result["data"]["items"] == []
    assert result["data"]["page"]["has_more"] is False
    assert result["data"]["page"]["next_cursor"] is None
    assert [gap["reason"] for gap in result["coverage"]["missing"]] == [
        "saved_scope_incomplete"
    ]


def test_thread_body_gap_after_page_is_reported(pr_catalog):
    state, store = pr_catalog
    with store.transaction():
        assert (
            CurrentApiState(store)
            .admit(
                "review_thread_state",
                candidate(
                    store,
                    "repo:1:pull_request",
                    "review-thread",
                    provider_resource_id="thread",
                    resolved=False,
                ),
                source="import",
            )
            .status
            == "accepted"
        )
        for number in (1, 2, 3):
            add_document(
                store,
                "repo:1:pull_request",
                str(number),
                f"comment {number}" if number != 3 else None,
                kind="review-comment",
                thread="thread",
            )
        store.advance_local_revision()
    command = (
        "pr",
        "thread",
        "--repo",
        "00000000-0000-4000-8000-000000000401",
        "--provider-change-request-number",
        1,
        "--provider-resource-id",
        "thread",
    )
    first = run(state, *command, "--limit", 1, expected=3)
    full = run(state, *command, "--limit", 100, expected=3)
    assert first["coverage"] == full["coverage"]
    assert first["coverage"]["missing"] == [
        {
            "kind": "pr",
            "reason": "thread_listing_incomplete",
            "change_request_id": "repo:1:pull_request",
            "provider_resource_id": "thread",
        },
        {
            "kind": "pr",
            "reason": "document_body_missing",
            "change_request_id": "repo:1:pull_request",
            "document_kind": "review-comment",
            "provider_change_request_document_id": "3",
        },
    ]
    assert full["data"]["items"][2]["body"] is None


def test_byte_page_boundary_keeps_later_pr_coverage(pr_catalog):
    state, store = pr_catalog
    with store.transaction():
        add_document(store, "repo:1:pull_request", "1", "needle " + "x" * 8_388_608)
        add_gap(store, "pr-documents", "claim", number=3, coverage_state="unknown")
        store.advance_local_revision()
    result = run(
        state,
        "search",
        "pr",
        "--repo",
        "00000000-0000-4000-8000-000000000401",
        "--literal",
        "needle",
        "--limit",
        100,
        expected=3,
    )
    assert result["data"]["page"]["returned"] == 1
    assert result["data"]["page"]["has_more"] is True
    assert result["data"]["page"]["next_cursor"] is not None
    assert [gap["reason"] for gap in result["coverage"]["missing"]] == [
        "saved_scope_incomplete"
    ]


def test_preflight_does_not_materialize_later_document_results(pr_catalog, monkeypatch):
    state, store = pr_catalog
    with store.transaction():
        add_gap(store, "pr-documents", "claim", number=3, coverage_state="unknown")
        store.advance_local_revision()
    query = QueryService(state)
    matches = []
    original = query.literal_match

    def record_match(kind, key, body, literal):
        matches.append(body)
        return original(kind, key, body, literal)

    monkeypatch.setattr(query, "literal_match", record_match)
    result = query.query(
        "search pr",
        {
            "repo": "00000000-0000-4000-8000-000000000401",
            "literal": "needle",
        },
        limit=1,
    )
    assert result.status == "partial"
    assert len(result.coverage.missing) == 1
    assert matches == [
        "needle body for repo:1:pull_request",
        "needle body for repo:2:pull_request",
    ]


def test_preflight_timeout_discards_page_and_issues_no_cursor(pr_catalog, monkeypatch):
    state, _ = pr_catalog
    original = pr_queries.prepare_pr_coverage

    def expire(query, command, options):
        original(query, command, options)
        query.deadline = -1

    monkeypatch.setattr(pr_queries, "prepare_pr_coverage", expire)
    result = QueryService(state).query(
        "pr list",
        {"repo": "00000000-0000-4000-8000-000000000401"},
        limit=1,
    )
    assert result.status == "partial"
    assert result.execution["completed"] is False
    assert result.execution["timed_out"] is True
    assert result.data["items"] == []
    assert result.data["page"]["has_more"] is None
    assert result.data["page"]["next_cursor"] is None
    assert result.coverage.missing == [{"kind": "execution", "reason": "timeout"}]


def test_preflight_cancellation_remains_an_interruption(pr_catalog, monkeypatch):
    state, _ = pr_catalog
    token = CancellationToken()
    original = pr_queries.prepare_pr_coverage

    def cancel(query, command, options):
        original(query, command, options)
        token.cancelled = True

    monkeypatch.setattr(pr_queries, "prepare_pr_coverage", cancel)
    with pytest.raises(CatalogError) as caught:
        QueryService(state, token).query(
            "pr list",
            {"repo": "00000000-0000-4000-8000-000000000401"},
            limit=1,
        )
    assert caught.value.code == "CANCELLED"


def test_pr_cursor_scope_and_revision_guards_survive_preflight(pr_catalog):
    state, store = pr_catalog
    first = run(
        state,
        "search",
        "pr",
        "--repo",
        "00000000-0000-4000-8000-000000000401",
        "--literal",
        "needle",
        "--limit",
        1,
    )
    cursor = first["data"]["page"]["next_cursor"]
    result = run(
        state,
        "search",
        "pr",
        "--repo",
        "00000000-0000-4000-8000-000000000401",
        "--literal",
        "different",
        "--cursor",
        cursor,
        expected=2,
    )
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    with store.transaction():
        add_gap(store, "pr-documents", "claim", number=3)
        store.advance_local_revision()
    result = run(
        state,
        "search",
        "pr",
        "--repo",
        "00000000-0000-4000-8000-000000000401",
        "--literal",
        "needle",
        "--cursor",
        cursor,
        expected=4,
    )
    assert result["error"]["code"] == "STALE_CURSOR"


def add_complete_code(
    store, unavailable_role=None, link_state="complete", *, declared=None
):
    """Exact typed code anchors with actual independently verified Git bytes."""
    import hashlib

    from repo_catalog.adapters.git.parsing import GitParsing

    acquisition = "code-acquisition"
    add_fact(
        store,
        "git_acquisitions",
        git_acquisition_id=acquisition,
        repository_uuidv4=REPOSITORY,
        object_format="sha1",
        kind="pr",
        observed_at_us=0,
        request="{}",
        roots_manifest="[]",
    )
    parser = GitParsing(store, REPOSITORY)
    tree_raw = b""
    tree_oid = hashlib.sha1(b"tree 0\0").digest()
    parser.install_object("sha1", tree_oid, "tree", tree_raw, acquisition=acquisition)
    targets = {}
    raws = {}
    for role in ("head", "base", "merge"):
        raw = (
            f"tree {tree_oid.hex()}\nauthor Fixture <fixture@example.invalid> 0 +0000\ncommitter Fixture <fixture@example.invalid> 0 +0000\n\n{role}\n"
        ).encode()
        oid = hashlib.sha1(f"commit {len(raw)}\0".encode() + raw).digest()
        targets[role] = oid
        raws[role] = raw
        if not (role == unavailable_role and link_state == "object_missing"):
            parser.install_object("sha1", oid, "commit", raw, acquisition=acquisition)
    admit_pr_state(
        store,
        "repo:1:pull_request",
        provider_updated_at_us=1,
        object_format="sha1",
        head_oid=targets["head"].hex(),
        base_oid=targets["base"].hex(),
        merge_oid=targets["merge"].hex(),
    )
    from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof

    for kind in ("commits", "files"):
        scope = {
            "repository_uuidv4": REPOSITORY,
            "change_request_id": "repo:1:pull_request",
            "endpoint": "code-" + kind,
            "request_context": {
                "object_format": "sha1",
                "head_oid": targets["head"].hex(),
                "base_oid": targets["base"].hex(),
            },
        }
        add_fact(
            store,
            "fetch_collections",
            fetch_collection_id=kind,
            repository_uuidv4=REPOSITORY,
            change_request_id="repo:1:pull_request",
            kind="pr-" + kind,
            scope_json=json.dumps(scope),
        )
        proof = CurrentCollectionProof(store.connection)
        proof.page(kind, 0, 0, None, [], parser_module=__name__, parser_version="1")
        add_fact(
            store,
            "completion_markers",
            fetch_collection_id=kind,
            asserted_state="complete",
            evidence=json.dumps(proof.evidence(kind)),
            observed_at_us=0,
        )
        add_fact(
            store,
            "code_listings",
            code_listing_id=kind,
            change_request_id="repo:1:pull_request",
            fetch_collection_id=kind,
            kind=kind,
            object_format="sha1",
            head_oid=targets["head"],
            base_oid=targets["base"],
        )
        add_fact(
            store,
            "code_listing_progress",
            code_listing_id=kind,
            state="complete",
            terminal=1,
            page_count=1,
            context_proven=1,
        )
    assessment = "exact-target-assessment"
    add_fact(
        store,
        "code_assessments",
        code_assessment_id=assessment,
        repository_uuidv4=REPOSITORY,
        change_request_id="repo:1:pull_request",
        commit_code_listing_id="commits",
        file_code_listing_id="files",
        state="complete",
        object_format="sha1",
        head_oid=targets["head"],
        base_oid=targets["base"],
        observed_at_us=0,
        parser_module=__name__,
        parser_version="1",
        details_json=json.dumps(
            {
                "expected_roles": {"merge": targets["merge"].hex()}
                if declared is None
                else declared
            }
        ),
    )
    for role, oid in targets.items():
        mode = link_state if role == unavailable_role else "complete"
        if mode == "absent":
            continue
        actual = targets["merge"] if mode == "wrong_oid" else oid
        root = None
        if mode != "null_root":
            role_acquisition = acquisition + "-" + role
            add_fact(
                store,
                "git_acquisitions",
                git_acquisition_id=role_acquisition,
                repository_uuidv4=REPOSITORY,
                object_format="sha1",
                kind="pr",
                observed_at_us=0,
                request="{}",
                roots_manifest="[]",
            )
            parser.install_object(
                "sha1", tree_oid, "tree", tree_raw, acquisition=role_acquisition
            )
            if mode != "object_missing":
                actual_role = "merge" if mode == "wrong_oid" else role
                parser.install_object(
                    "sha1",
                    actual,
                    "commit",
                    raws[actual_role],
                    acquisition=role_acquisition,
                )
            root = add_fact(
                store,
                "acquisition_roots",
                git_acquisition_id=role_acquisition,
                repository_uuidv4=REPOSITORY,
                object_format="sha1",
                oid=actual,
                role=role,
                expected_oid=actual,
                complete=0,
            )
            if mode not in {"incomplete", "object_missing"}:
                assert parser.validate_acquisition(role_acquisition)
                store.execute(
                    "UPDATE acquisition_roots SET complete=1 WHERE acquisition_root_id=?",
                    (root,),
                )
        add_fact(
            store,
            "code_acquisitions",
            code_assessment_id=assessment,
            role=role,
            object_format="sha1",
            oid=actual,
            acquisition_root_id=root,
        )
    return assessment, targets


@pytest.mark.parametrize(
    "unavailable_role,link_state",
    [
        ("head", "absent"),
        ("base", "null_root"),
        ("merge", "incomplete"),
        ("head", "wrong_oid"),
        ("base", "object_missing"),
        (None, "complete"),
    ],
)
def test_complete_code_requires_saved_complete_matching_role_roots(
    pr_catalog, unavailable_role, link_state
):
    state, store = pr_catalog
    with store.transaction():
        code, targets = add_complete_code(store, unavailable_role, link_state)
        store.advance_local_revision()
    result = run(
        state,
        "pr",
        "show",
        "--repo",
        "00000000-0000-4000-8000-000000000401",
        "--provider-change-request-number",
        1,
        expected=3 if unavailable_role else 0,
    )
    assert result["coverage"]["missing"] == (
        [
            {
                "kind": "pr",
                "reason": "code_role_target_conflict",
                "change_request_id": "repo:1:pull_request",
                "role": unavailable_role,
            }
        ]
        if link_state == "wrong_oid"
        else [
            {
                "kind": "pr",
                "reason": "code_role_acquisition_missing",
                "change_request_id": "repo:1:pull_request",
                "code_assessment_id": code,
                "role": unavailable_role,
                "expected_oid": "sha1:" + targets[unavailable_role].hex(),
            }
        ]
        if unavailable_role
        else []
    )
    docs = run(
        state,
        "pr",
        "documents",
        "--repo",
        "00000000-0000-4000-8000-000000000401",
        "--provider-change-request-number",
        1,
    )
    assert docs["coverage"]["missing"] == []


@pytest.mark.parametrize("declared", [["head"], {"merge": {"oid": "unparsed"}}])
def test_imported_role_target_shapes_are_rejected_before_admission(
    pr_catalog, declared
):
    state, store = pr_catalog
    with (
        pytest.raises(sqlite3.IntegrityError, match="JSON contract"),
        store.transaction(),
    ):
        add_complete_code(store, declared=declared)
    assert (
        store.one(
            "SELECT count(*) FROM code_assessments WHERE json_type(details_json,'$.expected_roles') IS NOT NULL AND json_type(details_json,'$.expected_roles')<>'object'"
        )[0]
        == 0
    )
