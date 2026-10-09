"""Requested PR coverage is independent of result pagination and code-only gaps."""

import hashlib
import json
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.sqlite.parser_model import ParserModel
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application import pr_queries
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.query_service import QueryService
from repo_catalog.application.repository_identity import add_instance, bind
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.support.cli import run
from tests.support.parser_facts import enrich


def add_fact(store, table, **values):
    values = enrich(store.connection, table, values)
    result = values["parsed_result_uuidv4"]
    ident = store.execute(
        f"INSERT INTO {table}({','.join(values)}) VALUES({','.join('?' for _ in values)})",
        tuple(values.values()),
    ).lastrowid
    model = ParserModel(store.connection)
    scope = {"change_request_id": values.get("change_request_id")}
    if table == "document_observations":
        scope.update(
            fact_kind=values["kind"],
            kind=values["kind"],
            provider_change_request_document_id=values[
                "provider_change_request_document_id"
            ],
        )
    elif table == "review_thread_observations":
        scope.update(
            fact_kind="review-thread",
            provider_resource_id=values["provider_resource_id"],
        )
    else:
        scope["fact_kind"] = {
            "code_observations": "code",
            "change_request_observations": "change-request",
            "snapshots": "git",
        }[table]
    profile = store.one(
        "SELECT parser_profile_uuidv4 FROM parsed_results WHERE parsed_result_uuidv4=?",
        (result,),
    )[0]
    model.publish_result(result)
    model.ensure_scope_profile(
        profile,
        repository_uuidv4=values["repository_uuidv4"],
        fact_kind=scope["fact_kind"],
    )
    model.select_fact(result, **scope)
    return ident


def add_document(store, pr, document_id, body, *, kind="pr-body", thread=None):
    key = (pr, kind, document_id)
    if kind in ("review", "review-comment"):
        from repo_catalog.adapters.sqlite.current_resources import CurrentResources

        owner = store.one(
            "SELECT * FROM change_requests WHERE change_request_id=?", (pr,)
        )
        binding = store.one(
            "SELECT * FROM repository_bindings WHERE repository_binding_id=?",
            (owner["repository_binding_id"],),
        )
        model = ParserModel(store.connection)
        profile = model.ensure_builtin_profile()
        model.ensure_scope_profile(
            profile, repository_uuidv4=owner["repository_uuidv4"], fact_kind=kind
        )
        scope = {
            "repository_uuidv4": owner["repository_uuidv4"],
            "repository_binding_id": owner["repository_binding_id"],
            "service_instance_uuidv4": binding["service_instance_uuidv4"],
            "change_request_id": pr,
            "endpoint": "synthetic-test",
        }
        candidate = {
            "kind": kind,
            "provider_change_request_document_id": document_id,
            **{k: v for k, v in scope.items() if k != "endpoint"},
            "acquisition_scope": scope,
            "body": body,
            "body_status": "present" if body is not None else "missing",
            "observed_at_us": 0,
            "parsed_at_us": 0,
            "parser_profile_uuidv4": profile,
            "metadata": {},
            "review_thread_provider_resource_id": thread,
        }
        assert (
            CurrentResources(store).admit(candidate, source="import").status
            == "accepted"
        )
        return key
    store.execute("INSERT INTO documents VALUES(?,?,?)", key)
    if body is not None:
        encoded = body.encode("utf8")
        digest = hashlib.sha256(encoded).digest()
        store.execute(
            "INSERT INTO text_bodies(body,byte_length,sha256) VALUES(?,?,?)",
            (body, len(encoded), digest),
        )
        add_fact(
            store,
            "document_observations",
            change_request_id=pr,
            kind=kind,
            provider_change_request_document_id=document_id,
            text_body_sha256=digest,
            observed_at_us=0,
            parsed_at_us=0,
            metadata="{}",
        )
    return key


def add_pr(store, repository, binding, number, *, kind="pull_request"):
    pr = f"repo:{number}:{kind}"
    store.execute(
        "INSERT INTO change_requests(change_request_id,repository_uuidv4,repository_binding_id,change_request_kind,provider_change_request_number) VALUES(?,?,?,?,?)",
        (pr, repository, binding, kind, number),
    )
    add_fact(
        store,
        "change_request_observations",
        change_request_id=pr,
        observed_at_us=0,
        published=1,
        payload=json.dumps({"title": "needle", "state": "open", "merged": False}),
        parsed_at_us=0,
    )
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
            store.publish()
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
        "INSERT INTO resume_scopes(resume_scope_id,repository_uuidv4,request_context,parser_version,profile_version,confidence) VALUES('query-resume','00000000-0000-4000-8000-000000000401','{}','test','test','proven')"
    )
    store.execute(
        "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,kind,resume_scope_id,observed_at_us) VALUES('query-collection','00000000-0000-4000-8000-000000000401',?,?,'query-resume',1)",
        (pr, kind),
    )
    store.execute(
        "INSERT INTO collection_progress(fetch_collection_id,job_id,attempt,state) VALUES('query-collection','query-job',1,'partial')"
    )


@pytest.mark.parametrize("kind", ["pr-commits", "pr-files", "commits", "files"])
@pytest.mark.parametrize("source", ["claim", "collection"])
def test_document_queries_ignore_code_listing_gaps(pr_catalog, kind, source):
    state, store = pr_catalog
    with store.transaction():
        add_gap(store, kind, source)
        store.publish()
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
        store.publish()
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
        store.publish()
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
        store.publish()
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
        current = store.one(
            "SELECT change_request_id,change_request_observation_id FROM current_change_request_observations WHERE change_request_id='repo:3:pull_request'"
        )
        add_fact(
            store,
            "code_observations",
            change_request_id=current[0],
            change_request_observation_id=current[1],
            state="partial",
            details="{}",
        )
        store.publish()
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
        "code_observation_incomplete"
    ]


@pytest.mark.parametrize("role", ["head", "base"])
def test_new_current_api_observation_requires_its_own_code_observation(
    pr_catalog, role
):
    state, store = pr_catalog
    with store.transaction():
        observation = add_fact(
            store,
            "change_request_observations",
            change_request_id="repo:3:pull_request",
            observed_at_us=1,
            published=1,
            payload=json.dumps({"state": "open", role: {"sha": "01" * 20}}),
            parsed_at_us=1,
        )
        store.publish()
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
    assert selected["data"]["items"][0]["code_observation"] is None
    assert selected["coverage"]["missing"] == [
        {
            "kind": "pr",
            "reason": "code_observation_missing",
            "change_request_id": "repo:3:pull_request",
            "change_request_observation_id": observation,
        }
    ]
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
        store.publish()
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
        store.execute(
            "INSERT INTO review_threads VALUES('repo:1:pull_request','thread')"
        )
        from tests.support.parser_facts import new_result

        result = new_result(store.connection, "00000000-0000-4000-8000-000000000401")
        add_fact(
            store,
            "review_thread_observations",
            thread_observation_uuidv4=str(uuid.uuid4()),
            parsed_result_uuidv4=result,
            repository_uuidv4="00000000-0000-4000-8000-000000000401",
            change_request_id="repo:1:pull_request",
            provider_resource_id="thread",
            observed_at_us=0,
            payload=json.dumps(
                {"comments": {"nodes": [{"fullDatabaseId": n} for n in (1, 2, 3)]}}
            ),
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
        store.publish()
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
        add_document(store, "repo:1:pull_request", "large", "needle " + "x" * 8_388_608)
        add_gap(store, "pr-documents", "claim", number=3, coverage_state="unknown")
        store.publish()
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
        store.publish()
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
            "00000000-0000-4000-8000-000000000401": "00000000-0000-4000-8000-000000000401",
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
    original = pr_queries._coverage

    def expire(query, pr, documents_only):
        original(query, pr, documents_only)
        query.deadline = -1

    monkeypatch.setattr(pr_queries, "_coverage", expire)
    result = QueryService(state).query(
        "pr list",
        {
            "00000000-0000-4000-8000-000000000401": "00000000-0000-4000-8000-000000000401"
        },
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
    original = pr_queries._coverage

    def cancel(query, pr, documents_only):
        original(query, pr, documents_only)
        token.cancelled = True

    monkeypatch.setattr(pr_queries, "_coverage", cancel)
    with pytest.raises(CatalogError) as caught:
        QueryService(state, token).query(
            "pr list",
            {
                "00000000-0000-4000-8000-000000000401": "00000000-0000-4000-8000-000000000401"
            },
            limit=1,
        )
    assert caught.value.code == "CANCELLED"


def test_pr_cursor_scope_and_publication_guards_survive_preflight(pr_catalog):
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
        store.publish()
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
    store, unavailable_role=None, link_state="published", *, declared=None
):
    """Valid complete listings with independently preserved role evidence."""
    targets = {
        role: bytes([index]) * 20
        for index, role in enumerate(("head", "base", "merge"), 1)
    }
    store.execute(
        "INSERT INTO jobs(job_id,kind,request,current_attempt,created_at_us) VALUES('code-job','sync','{}',1,0)"
    )
    store.execute(
        "INSERT INTO job_attempts(job_id,attempt,state,created_at_us,checkpoint) VALUES('code-job',1,'complete',0,'{}')"
    )
    store.execute(
        "INSERT INTO resume_scopes(resume_scope_id,repository_uuidv4,request_context,parser_version,profile_version,confidence) VALUES('code-resume','00000000-0000-4000-8000-000000000401','{}','test','test','proven')"
    )
    for kind in ("commits", "files"):
        store.execute(
            "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,kind,resume_scope_id,observed_at_us) VALUES(?,'00000000-0000-4000-8000-000000000401','repo:1:pull_request',?,'code-resume',0)",
            (kind, "pr-" + kind),
        )
        store.execute(
            "INSERT INTO collection_progress(fetch_collection_id,job_id,attempt,state) VALUES(?,'code-job',1,'complete')",
            (kind,),
        )
        store.execute(
            "INSERT INTO code_listings(code_listing_id,change_request_id,fetch_collection_id,kind,resume_scope_id,object_format,head_oid,base_oid) VALUES(?,'repo:1:pull_request',?,?,'code-resume','sha1',?,?)",
            (kind, kind, kind, targets["head"], targets["base"]),
        )
        store.execute(
            "INSERT INTO code_listing_progress(code_listing_id,state,terminal,page_count,context_proven) VALUES(?,'complete',1,0,1)",
            (kind,),
        )
    current = store.one(
        "SELECT change_request_observation_id FROM current_change_request_observations WHERE change_request_id='repo:1:pull_request'"
    )[0]
    code = add_fact(
        store,
        "code_observations",
        change_request_id="repo:1:pull_request",
        change_request_observation_id=current,
        commit_code_listing_id="commits",
        file_code_listing_id="files",
        state="complete",
        object_format="sha1",
        head_oid=targets["head"],
        base_oid=targets["base"],
        details=json.dumps(
            {
                "expected_roles": {"merge": targets["merge"].hex()}
                if declared is None
                else declared
            }
        ),
    )
    store.execute(
        "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,object_format,kind,observed_at_us,request,roots_manifest) VALUES('code-acquisition','00000000-0000-4000-8000-000000000401','sha1','legacy',0,'{}','[]')"
    )
    for role, oid in targets.items():
        mode = link_state if role == unavailable_role else "published"
        if mode == "absent":
            continue
        actual = bytes([4]) * 20 if mode == "wrong_oid" else oid
        root = None
        if mode != "null_root":
            if mode != "object_missing":
                store.execute(
                    "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES('sha1',?,'commit',0,1)",
                    (actual,),
                )
            root = store.execute(
                "INSERT INTO acquisition_roots(git_acquisition_id,object_format,oid,role,repository_uuidv4,expected_oid,published) VALUES('code-acquisition','sha1',?,?,'00000000-0000-4000-8000-000000000401',?,?)",
                (actual, role, actual, 0 if mode == "unpublished" else 1),
            ).lastrowid
        store.execute(
            "INSERT INTO code_acquisitions(code_observation_id,role,object_format,oid,acquisition_root_id) VALUES(?,?,'sha1',?,?)",
            (code, role, actual, root),
        )
    return code, targets


@pytest.mark.parametrize(
    "unavailable_role,link_state",
    [
        ("head", "absent"),
        ("base", "null_root"),
        ("merge", "unpublished"),
        ("head", "wrong_oid"),
        ("base", "object_missing"),
        (None, "published"),
    ],
)
def test_complete_code_requires_saved_published_matching_role_roots(
    pr_catalog, unavailable_role, link_state
):
    state, store = pr_catalog
    with store.transaction():
        code, targets = add_complete_code(store, unavailable_role, link_state)
        store.publish()
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
    assert result["data"]["items"][0]["code_observation"]["state"] == "complete"
    assert result["coverage"]["missing"] == (
        [
            {
                "kind": "pr",
                "reason": "code_role_acquisition_missing",
                "change_request_id": "repo:1:pull_request",
                "code_observation_id": code,
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
        pytest.raises(sqlite3.IntegrityError, match="JSON reference"),
        store.transaction(),
    ):
        add_complete_code(store, declared=declared)
    assert (
        store.one(
            "SELECT count(*) FROM code_observations WHERE json_type(details,'$.expected_roles') IS NOT NULL AND json_type(details,'$.expected_roles')<>'object'"
        )[0]
        == 0
    )
