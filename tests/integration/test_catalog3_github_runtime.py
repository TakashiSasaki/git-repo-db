"""Synthetic HTTP acceptance of catalog3 history, listings and restart boundaries."""

import copy
import json

import pytest

from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.job_service import JobService
from repo_catalog.config import DEFAULTS, serialize
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.support.git_fixture import GitFixture
from tests.support.github_fixture import GitHubFixture


@pytest.fixture
def github_runtime(tmp_path, monkeypatch):
    fixture = GitFixture(tmp_path / "remotes")
    with GitHubFixture(fixture) as api:
        state = tmp_path / "state"
        state.mkdir()
        (state / "work").mkdir()
        (state / "locks").mkdir()
        (state / "cache").mkdir()
        config = copy.deepcopy(DEFAULTS)
        config["github"].update(rest_base_url=api.url, graphql_url=api.url + "/graphql")
        config["cache"].update(max_bytes=67108864, min_free_bytes=0)
        (state / "catalog.toml").write_text(serialize(config))
        monkeypatch.setenv("GH_TOKEN", "fixture-dummy")
        with Store(state, initialize=True) as store:
            with store.transaction():
                store.execute(
                    "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,web_base_url,api_base_url,metadata,created_at) VALUES('00000000-0000-4000-8000-000000000101','github','fixture',?,?, '{}',NULL)",
                    (api.url, api.url),
                )
                store.execute(
                    "INSERT INTO sources(source_id,service_instance_uuidv4,discovery_kind,name,settings) VALUES('source','00000000-0000-4000-8000-000000000101','github_inventory','fixture',?)",
                    (json.dumps({"owner": "fixture"}),),
                )
                store.execute(
                    "INSERT INTO repositories(repository_id,name,preferred_repository_endpoint_id,current_snapshot_id,metadata) VALUES('repo','fixture/alpha','endpoint',NULL,'{}')"
                )
                store.execute(
                    "INSERT INTO repository_endpoints(repository_endpoint_id,repository_id,url,transport,label,metadata,created_at) VALUES('endpoint','repo',?,'file',NULL,'{}',NULL)",
                    (fixture.alpha.url,),
                )
                store.execute(
                    "INSERT INTO repository_bindings(repository_binding_id,repository_id,service_instance_uuidv4,provider_repository_id,metadata,created_at) VALUES('binding','repo','00000000-0000-4000-8000-000000000101','101','{}',NULL)"
                )
                store.execute(
                    "INSERT INTO source_repositories(source_id,repository_id,first_seen,last_seen) VALUES('source','repo',NULL,NULL)"
                )
            repo = {
                "repository_id": "repo",
                "name": "fixture/alpha",
                "source_id": "source",
                "provider_repository_id": "101",
                "preferred_repository_endpoint_id": "endpoint",
            }
            yield store, repo, fixture, api
            assert not api.errors


def sync(store, repo, *, job=None):
    if job is None:
        job = JobService(store).create(
            "sync", {"kind": "pr", "repositories": [repo["repository_id"]]}
        )
    else:
        JobService(store).resume(job)
    store.expected_attempt = store.one(
        "SELECT current_attempt FROM jobs WHERE job_id=?", (job,)
    )[0]
    try:
        result = GitHubCollector(store, CancellationToken()).sync(repo, job)
        JobService(store).update(job, "complete")
        return job, result
    except CatalogError as error:
        JobService(store).update(job, "waiting", error.code)
        error.details["job_id"] = job
        raise


def test_fresh_history_and_sealed_listing_reuse(github_runtime):
    store, repo, fixture, api = github_runtime
    api.etag = True
    sync(store, repo)
    assert store.one("SELECT count(*) FROM change_requests")[0] == 3
    assert store.one("SELECT count(*) FROM review_threads")[0] == 3
    assert store.one("SELECT count(*) FROM reviews")[0] == 3
    assert store.one("SELECT count(*) FROM change_request_events")[0] == 9
    assert (
        store.one("SELECT count(*) FROM code_listing_progress WHERE state='complete'")[
            0
        ]
        == 6
    )
    assert (
        store.one("SELECT count(*) FROM root_origins WHERE origin_kind='pr_role'")[0]
        >= 6
    )
    api.stage = "B"
    sync(store, repo)
    old_page = store.one(
        "SELECT f.*,o.fetch_occurrence_id fetch_occurrence_id,o.observed_at page_observed_at,p.body FROM fetch_collections f JOIN fetch_occurrences o ON o.fetch_collection_id=f.fetch_collection_id JOIN payloads p ON p.payload_id=o.payload_id WHERE f.change_request_id='repo:41' AND f.kind='issue-comment' ORDER BY o.observed_at LIMIT 1"
    )
    current_version = store.one(
        "SELECT current_document_observation_id FROM documents WHERE change_request_id='repo:41' AND kind='issue-comment' AND provider_change_request_document_id='241'"
    )[0]
    observation_count = store.one("SELECT count(*) FROM document_observations")[0]
    from repo_catalog.adapters.github.persistence import ApiFacts

    # Replaying a committed old A page while current B is selected must be a
    # no-op; it cannot invent a return-to-A observation or move the projection.
    with store.transaction():
        old_value = json.loads(old_page["body"])[0]
        ApiFacts(store, store.config["github"]).document(
            "repo:41",
            "issue-comment",
            "241",
            old_value["body"],
            old_value,
            dict(old_page),
            old_page["fetch_occurrence_id"],
            0,
            old_page["page_observed_at"],
        )
    assert (
        store.one(
            "SELECT current_document_observation_id FROM documents WHERE change_request_id='repo:41' AND kind='issue-comment' AND provider_change_request_document_id='241'"
        )[0]
        == current_version
    )
    assert (
        store.one("SELECT count(*) FROM document_observations")[0] == observation_count
    )
    first = len(api.requests)
    api.stage = "A"
    sync(store, repo)
    assert not any(
        path.endswith(("/commits", "/files")) for _, path, _ in api.requests[first:]
    )
    versions = store.all(
        "SELECT b.body,1 observations FROM document_observations o JOIN text_bodies b ON b.sha256=o.text_body_sha256 WHERE o.kind='issue-comment' AND o.change_request_id='repo:41' ORDER BY o.document_observation_id"
    )
    assert {r["body"] for r in versions} == {"comment-marker A", "comment-marker B"}
    assert sum(r["observations"] for r in versions if r["body"].endswith("A")) == 2
    assert len(versions) == 3
    assert (
        store.one(
            "SELECT count(DISTINCT o.text_body_sha256) FROM document_observations o WHERE o.kind='issue-comment' AND o.change_request_id='repo:41'"
        )[0]
        == 2
    )
    assert store.all("PRAGMA foreign_key_check") == []
    assert b"fixture-dummy" not in store.db_path.read_bytes()


def test_partial_listing_resumes_same_items_and_no_completed_pages(github_runtime):
    store, repo, fixture, api = github_runtime
    original = api.route
    commit_path = "/repos/fixture/alpha/pulls/41/commits"
    failed = False
    api.prs[41]["commits"] = 2

    def route(method, path, params, body):
        nonlocal failed
        if path == commit_path:
            if params.get("page") == ["2"]:
                return [{"sha": fixture.alpha.commits["N"]}], {}
            if not failed:
                api.failures[path] = [500] * 5
                failed = True
            return [{"sha": fixture.alpha.commits["P"]}], {
                "Link": f'<{api.url}{path}?per_page=100&page=2>; rel="next"'
            }
        return original(method, path, params, body)

    api.route = route
    with pytest.raises(CatalogError) as partial:
        sync(store, repo)
    listing = store.one(
        "SELECT l.code_listing_id,l.fetch_collection_id,p.state,p.page_count FROM code_listings l JOIN code_listing_progress p ON p.code_listing_id=l.code_listing_id WHERE l.change_request_id='repo:41' AND l.kind='commits'"
    )
    assert listing["state"] == "partial" and listing["page_count"] == 1
    assert (
        store.one(
            "SELECT count(*) FROM code_commits WHERE code_listing_id=?",
            (listing["code_listing_id"],),
        )[0]
        == 1
    )
    first = len(api.requests)
    sync(store, repo, job=partial.value.details["job_id"])
    requests = api.requests[first:]
    assert [
        params.get("page") for _, path, params in requests if path == commit_path
    ] == [["2"]]
    assert not any(
        path.startswith(
            ("/repos/fixture/alpha/pulls/42", "/repos/fixture/alpha/pulls/43")
        )
        for _, path, _ in requests
    )
    assert (
        store.one(
            "SELECT count(*) FROM code_listings WHERE change_request_id='repo:41' AND kind='commits'"
        )[0]
        == 1
    )
    assert (
        store.one(
            "SELECT count(*) FROM code_commits WHERE code_listing_id=?",
            (listing["code_listing_id"],),
        )[0]
        == 2
    )
    assert (
        store.one(
            "SELECT count(*) FROM fetch_occurrences WHERE fetch_collection_id=?",
            (listing["fetch_collection_id"],),
        )[0]
        == 2
    )
    assert (
        store.one(
            "SELECT state FROM code_listing_progress WHERE code_listing_id=?",
            (listing["code_listing_id"],),
        )[0]
        == "complete"
    )


def test_watermarks_failed_child_and_resume_keep_successful_boundary(github_runtime):
    store, repo, fixture, api = github_runtime
    api.incremental = True
    sync(store, repo)
    old = store.all(
        "SELECT i.safe_watermark,f.kind FROM incremental_scans i JOIN fetch_collections f ON f.fetch_collection_id=i.fetch_collection_id ORDER BY i.scan_started_at"
    )
    api.stage = "B"
    api.failures["/repos/fixture/alpha/issues/comments"] = [503] * 5
    with pytest.raises(CatalogError) as partial:
        sync(store, repo)
    assert (
        store.one(
            "SELECT count(*) FROM incremental_scans i JOIN fetch_collections f ON f.fetch_collection_id=i.fetch_collection_id WHERE f.kind='issue-comment-incremental'"
        )[0]
        == 1
    )
    review = store.one(
        "SELECT i.safe_watermark,i.fetch_collection_id FROM incremental_scans i JOIN fetch_collections f ON f.fetch_collection_id=i.fetch_collection_id WHERE f.kind='review-comment-incremental' ORDER BY i.scan_started_at DESC LIMIT 1"
    )
    assert review["safe_watermark"] != next(
        r["safe_watermark"] for r in old if r["kind"] == "review-comment-incremental"
    )
    before = len(api.requests)
    sync(store, repo, job=partial.value.details["job_id"])
    assert not any(
        path.endswith("/pulls/comments") for _, path, _ in api.requests[before:]
    )
    assert (
        store.one(
            "SELECT safe_watermark FROM incremental_scans WHERE fetch_collection_id=?",
            (review["fetch_collection_id"],),
        )[0]
        == review["safe_watermark"]
    )
    assert any(
        params.get("since")
        for _, path, params in api.requests
        if path.endswith("/issues/comments")
    )


def test_graphql_nested_pagination_and_partial_payload_preservation(github_runtime):
    store, repo, fixture, api = github_runtime
    api.thread_count = 2
    api.reply_count = 101
    api.graphql_partial = True
    with pytest.raises(CatalogError):
        sync(store, repo)
    assert (
        store.one(
            "SELECT count(*) FROM fetch_occurrences o JOIN fetch_collections f ON f.fetch_collection_id=o.fetch_collection_id WHERE f.kind='threads'"
        )[0]
        == 3
    )
    assert (
        store.one(
            "SELECT count(*) FROM documents WHERE kind='review-comment' AND change_request_id='repo:41'"
        )[0]
        == 200
    )
    api.graphql_partial = False
    sync(store, repo)
    assert (
        store.one(
            "SELECT count(*) FROM documents WHERE kind='review-comment' AND change_request_id='repo:41'"
        )[0]
        == 202
    )
    assert (
        store.one(
            "SELECT count(*) FROM collection_progress p JOIN fetch_collections f ON f.fetch_collection_id=p.fetch_collection_id WHERE f.kind='thread-comments' AND p.state='complete'"
        )[0]
        == 2
    )
    assert store.all("PRAGMA foreign_key_check") == []


def legacy_github_source(path, fixture, api):
    """Build v2 evidence directly; the current app never writes a v2 catalog."""
    import hashlib
    import sqlite3
    import uuid

    from tests.support.legacy_v2 import initialize

    source, cache = initialize(path)
    ids = {
        name: str(uuid.uuid5(uuid.NAMESPACE_URL, "catalog3-first-sync:" + name))
        for name in (
            "repo",
            "source",
            "instance",
            "endpoint",
            "job",
            "commits",
            "files",
            "comment-a",
            "comment-b",
            "comment-return-a",
        )
    }
    ids["instance"] = (
        "00000000-0000-4000-8000-000000000101"  # fixed synthetic UUIDv4 namespace
    )
    root = api.url + "/repos/fixture/alpha"
    version = DEFAULTS["github"]["rest_api_version"]
    stamp = "2026-01-01T00:00:00Z"
    detail, _ = api.route("GET", root.removeprefix(api.url) + "/pulls/41", {}, None)
    pr = ids["repo"] + ":41"
    with sqlite3.connect(source) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute(
            "INSERT INTO service_instances VALUES(?,'github','fixture',?,?,?,?)",
            (
                ids["instance"],
                api.url,
                api.url,
                json.dumps({"graphql_url": api.url + "/graphql"}),
                stamp,
            ),
        )
        db.execute(
            "INSERT INTO sources VALUES(?,'github','fixture',?,?)",
            (
                ids["source"],
                json.dumps({"owner": "fixture"}),
                ids["instance"],
            ),
        )
        db.execute(
            "INSERT INTO repositories VALUES(?,?,'127.0.0.1','101','fixture/alpha',?,'{}',NULL)",
            (ids["repo"], ids["source"], fixture.alpha.url),
        )
        db.execute(
            "INSERT INTO repository_bindings VALUES(?,?,'101','{}',?)",
            (ids["repo"], ids["instance"], stamp),
        )
        db.execute(
            "INSERT INTO repository_endpoints VALUES(?,?,?,'file',NULL,1,'{}',?)",
            (ids["endpoint"], ids["repo"], fixture.alpha.url, stamp),
        )
        db.execute(
            "INSERT INTO source_repositories VALUES(?,?,?,?)",
            (ids["source"], ids["repo"], stamp, stamp),
        )
        db.execute(
            "INSERT INTO jobs VALUES(?,'sync','{}','complete',1,NULL,'{}',NULL,?,?)",
            (ids["job"], stamp, stamp),
        )
        db.execute(
            "INSERT INTO pull_requests VALUES(?,?,41,'PR41',1)", (pr, ids["repo"])
        )
        db.execute(
            "INSERT INTO pr_observations VALUES(1,?,?,?,?,1)",
            (pr, ids["job"], stamp, json.dumps(detail)),
        )
        db.execute(
            "INSERT INTO pr_code_observations VALUES(1,?,1,?,?,'complete',?)",
            (
                pr,
                detail["head"]["sha"],
                detail["base"]["sha"],
                json.dumps({"api_head_base_stable": True}),
            ),
        )

        def payload(value):
            raw = json.dumps(value).encode()
            saved = db.execute(
                "SELECT id FROM api_responses WHERE payload_sha256=? AND body=?",
                (hashlib.sha256(raw).digest(), raw),
            ).fetchone()
            if saved:
                return saved[0]
            return db.execute(
                "INSERT INTO api_responses(payload_sha256,body) VALUES(?,?)",
                (hashlib.sha256(raw).digest(), raw),
            ).lastrowid

        for kind in ("commits", "files"):
            url = root + "/pulls/41/" + kind + "?per_page=100"
            values, _ = api.route("GET", url.split(api.url)[1].split("?")[0], {}, None)
            cid, response_id = ids[kind], payload(values)
            db.execute(
                "INSERT INTO collections VALUES(?,?,?, ?,?,'complete',?,NULL,?,NULL)",
                (
                    cid,
                    pr,
                    ids["repo"],
                    "pr-" + kind,
                    ids["job"],
                    json.dumps(
                        {
                            "repo_id": ids["repo"],
                            "api_version": version,
                            "principal": "fixture",
                        }
                    ),
                    stamp,
                ),
            )
            db.execute(
                "INSERT INTO collection_pages VALUES(?,0,?,?,NULL,?)",
                (
                    cid,
                    response_id,
                    json.dumps(
                        {"url": url, "api_version": version, "parser_version": "v1"}
                    ),
                    stamp,
                ),
            )
            if kind == "commits":
                db.execute(
                    "INSERT INTO pr_commits VALUES(1,0,?,?)",
                    (values[0]["sha"], json.dumps(values[0])),
                )
            else:
                db.execute(
                    "INSERT INTO pr_file_changes VALUES(1,0,?,?)",
                    (values[0]["filename"], json.dumps(values[0])),
                )
        response_id = payload(detail)
        key = "etag:" + json.dumps(
            {
                "repo": "101",
                "source": ids["source"],
                "principal": "fixture",
                "version": version,
                "accept": "application/vnd.github+json",
                "url": root + "/pulls/41",
            },
            sort_keys=True,
        )
        db.execute(
            "INSERT INTO sync_checkpoints VALUES(?,?,?)",
            (key, json.dumps({"etag": '"A"', "response_id": response_id}), stamp),
        )
        document = pr + ":issue-comment:241"
        db.execute(
            "INSERT INTO pr_documents VALUES(?,?,'issue-comment','241','IC41','commenter',NULL,1,0,'{}')",
            (document, pr),
        )
        for bid, body in ((1, "comment-marker A"), (2, "comment-marker B")):
            db.execute(
                "INSERT INTO document_versions VALUES(?,?,?,?)",
                (bid, document, body, hashlib.sha256(body.encode()).digest()),
            )
        for ordinal, (name, stage) in enumerate(
            (("comment-a", "A"), ("comment-b", "B"), ("comment-return-a", "A")), 1
        ):
            timestamp = f"2026-01-0{ordinal}T00:00:00Z"
            cid = ids[name]
            value = {
                "id": 241,
                "node_id": "IC41",
                "body": "comment-marker " + stage,
                "user": {"login": "commenter"},
            }
            response_id = payload([value])
            db.execute(
                "INSERT INTO collections VALUES(?,?,?,'issue-comment',?,'complete',?,NULL,?,NULL)",
                (
                    cid,
                    pr,
                    ids["repo"],
                    ids["job"],
                    json.dumps({"repo_id": ids["repo"], "api_version": version}),
                    timestamp,
                ),
            )
            db.execute(
                "INSERT INTO collection_pages VALUES(?,0,?,?,NULL,?)",
                (
                    cid,
                    response_id,
                    json.dumps(
                        {
                            "url": root + "/issues/41/comments?per_page=100",
                            "parser_version": "v1",
                        }
                    ),
                    timestamp,
                ),
            )
            db.execute(
                "INSERT INTO resource_observations VALUES(?,?,?,?,?,'{}')",
                (ordinal, document, 1 if stage == "A" else 2, cid, timestamp),
            )
            db.execute(
                "INSERT INTO collection_memberships VALUES(?,?,0)", (cid, document)
            )
        # Unknown historical cursor must never be used by current online requests.
        db.execute(
            "INSERT INTO sync_checkpoints VALUES('watermark:unsupported',?,?)",
            (json.dumps({"watermark": "2099-01-01T00:00:00Z"}), stamp),
        )
    return source, cache, ids, pr


def test_import_first_sync_conditional_detail_and_saved_complete_listings(
    tmp_path, monkeypatch
):
    import hashlib

    from repo_catalog.application.finalization import finalize_catalog
    from repo_catalog.application.import_service import import_catalog
    from repo_catalog.config import load

    fixture = GitFixture(tmp_path / "remotes")
    with GitHubFixture(fixture) as api:
        source, cache, ids, pr = legacy_github_source(tmp_path / "legacy", fixture, api)
        before = hashlib.sha256(source.read_bytes()).digest()
        state = tmp_path / "catalog3"
        import_catalog(source, state, source_caches=[cache], batch_size=10)
        config = load(state)
        config["github"].update(rest_base_url=api.url, graphql_url=api.url + "/graphql")
        config["cache"].update(max_bytes=67108864, min_free_bytes=0)
        (state / "catalog.toml").write_text(serialize(config))
        (state / "work").mkdir(exist_ok=True)
        monkeypatch.setenv("GH_TOKEN", "fixture-dummy")
        api.etag = True
        with Store(state, allow_building=True) as store:
            finalize_catalog(store)
            historical_observations = {
                r[0]
                for r in store.all(
                    "SELECT document_observation_id FROM document_observations"
                )
            }
            assert (
                store.one(
                    "SELECT count(*) FROM code_listing_progress WHERE state='complete'"
                )[0]
                == 2
            )
            assert (
                store.one(
                    "SELECT current_change_request_observation_id FROM change_requests WHERE change_request_id=?",
                    (pr,),
                )[0]
                == 1
            )
            repo = {
                "repository_id": ids["repo"],
                "name": "fixture/alpha",
                "source_id": ids["source"],
                "provider_repository_id": "101",
                "preferred_repository_endpoint_id": ids["endpoint"],
            }
            sync(store, repo)
            assert not any(
                path
                in (
                    "/repos/fixture/alpha/pulls/41/commits",
                    "/repos/fixture/alpha/pulls/41/files",
                )
                for _, path, _ in api.requests
            )
            # New PRs get their own lists; imported unchanged deterministic lists
            # remain sealed and are linked to the newly authorized observation.
            assert any(
                path.endswith("/pulls/42/commits") for _, path, _ in api.requests
            )
            assert historical_observations <= {
                r[0]
                for r in store.all(
                    "SELECT document_observation_id FROM document_observations"
                )
            }
            assert (
                store.one(
                    "SELECT count(*) FROM incremental_scans WHERE safe_watermark LIKE '2099%'"
                )[0]
                == 0
            )
            reused = store.all(
                "SELECT evidence FROM completion_markers WHERE json_extract(evidence,'$.boundary')='authenticated-current-head-base'"
            )
            assert len(reused) == 2
            assert (
                store.one(
                    "SELECT count(*) FROM completion_markers WHERE json_extract(evidence,'$.status')=304"
                )[0]
                >= 1
            )
            count = store.one(
                "SELECT count(*) FROM code_listings WHERE change_request_id=?", (pr,)
            )[0]
            assert count == 2
            old_listings = {
                row[0]
                for row in store.all(
                    "SELECT code_listing_id FROM code_listings WHERE change_request_id=?",
                    (pr,),
                )
            }
            fixture.alpha.commit(
                "Q", {**fixture.m, b"pr-only.txt": b"pr-marker changed"}, ("P",)
            )
            fixture.alpha.ref("refs/pull/41/head", "Q")
            api.prs[41]["head"]["sha"] = fixture.alpha.commits["Q"]
            api.stage = "B"
            original_route = api.route

            def changed_route(method, path, params, body):
                if path == "/repos/fixture/alpha/pulls/41/commits":
                    return [{"sha": fixture.alpha.commits["Q"]}], {}
                return original_route(method, path, params, body)

            api.route = changed_route
            changed_start = len(api.requests)
            sync(store, repo)
            changed_requests = api.requests[changed_start:]
            assert {
                path
                for _, path, _ in changed_requests
                if path.endswith(("/commits", "/files"))
            } == {
                "/repos/fixture/alpha/pulls/41/commits",
                "/repos/fixture/alpha/pulls/41/files",
            }
            assert (
                store.one(
                    "SELECT count(*) FROM code_listings WHERE change_request_id=?",
                    (pr,),
                )[0]
                == 4
            )
            assert old_listings <= {
                row[0]
                for row in store.all(
                    "SELECT code_listing_id FROM code_listings WHERE change_request_id=?",
                    (pr,),
                )
            }
            assert (
                store.one(
                    "SELECT count(*) FROM code_listing_progress p JOIN code_listings l ON l.code_listing_id=p.code_listing_id WHERE l.change_request_id=? AND p.state='complete'",
                    (pr,),
                )[0]
                == 4
            )
        assert hashlib.sha256(source.read_bytes()).digest() == before
        assert not api.errors


def test_304_never_attaches_cached_head_to_newer_race_observation(github_runtime):
    store, repo, fixture, api = github_runtime
    api.etag = True
    original = api.route
    detail_requests = 0

    def route(method, path, params, body):
        nonlocal detail_requests
        value, headers = original(method, path, params, body)
        if path == "/repos/fixture/alpha/pulls/41":
            detail_requests += 1
            if detail_requests == 2:
                value["head"] = {**value["head"], "sha": fixture.alpha.commits["N"]}
                api.stage = "B"
        return value, headers

    api.route = route
    with pytest.raises(CatalogError):
        sync(store, repo)
    current = store.one(
        "SELECT o.payload FROM change_requests p JOIN change_request_observations o ON o.change_request_observation_id=p.current_change_request_observation_id WHERE p.change_request_id='repo:41'"
    )
    assert json.loads(current[0])["head"]["sha"] == fixture.alpha.commits["N"]
    api.stage = "A"
    first = len(api.requests)
    sync(store, repo)
    assert (
        len(
            [
                path
                for _, path, _ in api.requests[first:]
                if path == "/repos/fixture/alpha/pulls/41"
            ]
        )
        == 3
    )
    # Every complete code observation is backed by exactly its admitted head/base,
    # including after A -> code-race B -> cached conditional A.
    for row in store.all(
        "SELECT c.head_oid,c.base_oid,o.payload FROM code_observations c JOIN change_request_observations o ON o.change_request_observation_id=c.change_request_observation_id WHERE c.state='complete'"
    ):
        value = json.loads(row["payload"])
        assert row["head_oid"].hex() == value["head"]["sha"]
        assert row["base_oid"].hex() == value["base"]["sha"]
    for row in store.all(
        "SELECT p.current_change_request_observation_id FROM change_requests p"
    ):
        assert (
            store.one(
                "SELECT count(*) FROM root_origins WHERE change_request_observation_id=?",
                (row[0],),
            )[0]
            > 0
        )


def test_review_target_failure_is_retried_on_resume(github_runtime, monkeypatch):
    from repo_catalog.adapters.git.importer import GitImporter

    store, repo, fixture, api = github_runtime
    original = GitImporter.sync
    attempts = []
    failed = False

    def acquire(self, repo, job, **kwargs):
        nonlocal failed
        root = kwargs["pr_roots"][0]
        if root["number"] == 41 and root["role"].startswith("review-target:"):
            attempts.append(root["role"])
            if not failed:
                failed = True
                raise CatalogError("API_ACCESS", "synthetic review target failure")
        return original(self, repo, job, **kwargs)

    monkeypatch.setattr(GitImporter, "sync", acquire)
    with pytest.raises(CatalogError) as partial:
        sync(store, repo)
    first = len(api.requests)
    sync(store, repo, job=partial.value.details["job_id"])
    assert len(attempts) == 2
    assert not any(
        path.endswith(("/reviews", "/comments", "/timeline", "/commits", "/files"))
        for _, path, _ in api.requests[first:]
    )
    code = store.one(
        "SELECT code_observation_id FROM code_observations WHERE change_request_id='repo:41' ORDER BY code_observation_id DESC LIMIT 1"
    )[0]
    assert (
        store.one(
            "SELECT count(*) FROM code_acquisitions WHERE code_observation_id=? AND role LIKE 'review-target:%'",
            (code,),
        )[0]
        == 1
    )


def test_malformed_nested_cursor_retries_saved_boundary(github_runtime):
    store, repo, fixture, api = github_runtime
    api.reply_count = 101
    original = api.route
    child_requests = []

    def route(method, path, params, body):
        value, headers = original(method, path, params, body)
        if method == "POST" and body["variables"].get("thread") == "THREAD41-0":
            child_requests.append(body["variables"]["commentCursor"])
            if len(child_requests) == 1:
                value["data"]["node"]["comments"].pop("pageInfo")
        return value, headers

    api.route = route
    with pytest.raises(CatalogError) as partial:
        sync(store, repo)
    child = store.one(
        "SELECT p.state,p.cursor,f.fetch_collection_id FROM collection_progress p JOIN fetch_collections f ON f.fetch_collection_id=p.fetch_collection_id WHERE f.kind='thread-comments' AND f.change_request_id='repo:41'"
    )
    assert child["state"] == "partial" and child["cursor"] == "100"
    root_pages = store.one(
        "SELECT count(*) FROM fetch_occurrences o JOIN fetch_collections f ON f.fetch_collection_id=o.fetch_collection_id WHERE f.kind='threads'"
    )[0]
    sync(store, repo, job=partial.value.details["job_id"])
    assert child_requests == ["100", "100"]
    assert (
        store.one(
            "SELECT state FROM collection_progress WHERE fetch_collection_id=?",
            (child["fetch_collection_id"],),
        )[0]
        == "complete"
    )
    assert (
        store.one(
            "SELECT count(*) FROM fetch_occurrences o JOIN fetch_collections f ON f.fetch_collection_id=o.fetch_collection_id WHERE f.kind='threads'"
        )[0]
        == root_pages
    )


def test_malformed_rest_page_keeps_payload_and_retries_without_skipping(github_runtime):
    store, repo, fixture, api = github_runtime
    original = api.route
    requests = 0
    path = "/repos/fixture/alpha/pulls/41/reviews"
    rejected = {"malformed": "original synthetic response"}

    def route(method, requested, params, body):
        nonlocal requests
        if requested == path:
            requests += 1
            if requests == 1:
                return rejected, {}
        return original(method, requested, params, body)

    api.route = route
    with pytest.raises(CatalogError) as partial:
        sync(store, repo)
    row = store.one(
        "SELECT f.fetch_collection_id,p.cursor,p.state,a.body FROM fetch_collections f JOIN collection_progress p ON p.fetch_collection_id=f.fetch_collection_id JOIN fetch_occurrences o ON o.fetch_collection_id=f.fetch_collection_id JOIN payloads a ON a.payload_id=o.payload_id WHERE f.change_request_id='repo:41' AND f.kind='review'"
    )
    assert row["state"] == "partial"
    assert json.loads(row["body"]) == rejected
    assert store.one("SELECT count(*) FROM unresolved_payloads")[0] == 1
    sync(store, repo, job=partial.value.details["job_id"])
    assert requests == 2
    assert (
        store.one(
            "SELECT count(*) FROM fetch_occurrences WHERE fetch_collection_id=?",
            (row["fetch_collection_id"],),
        )[0]
        == 2
    )
    assert (
        store.one(
            "SELECT state FROM collection_progress WHERE fetch_collection_id=?",
            (row["fetch_collection_id"],),
        )[0]
        == "complete"
    )


def test_changed_observed_permission_scope_refreshes_complete_listings(github_runtime):
    store, repo, fixture, api = github_runtime
    original = api.route
    permission = "repo"

    def route(method, path, params, body):
        value, headers = original(method, path, params, body)
        if path == "/user":
            headers["X-OAuth-Scopes"] = permission
        return value, headers

    api.route = route
    sync(store, repo)
    first = len(api.requests)
    permission = "read:org,repo"
    sync(store, repo)
    assert (
        len(
            [
                path
                for _, path, _ in api.requests[first:]
                if path.endswith(("/commits", "/files"))
            ]
        )
        == 6
    )
    scopes = {
        tuple(json.loads(row[0])["permissions"])
        for row in store.all("SELECT request_context FROM resume_scopes")
    }
    assert scopes == {("repo",), ("read:org", "repo")}
    assert (
        store.one("SELECT count(*) FROM code_listing_progress WHERE state='complete'")[
            0
        ]
        == 12
    )


@pytest.mark.parametrize("child_page", [False, True], ids=["root-page", "child-page"])
def test_missing_graphql_database_id_retains_page_and_resumes_without_node_alias(
    github_runtime, child_page
):
    store, repo, fixture, api = github_runtime
    api.reply_count = 101 if child_page else 1
    original = api.route
    enabled = True
    rejected_nodes = []

    def route(method, path, params, body):
        result, headers = original(method, path, params, body)
        if enabled and method == "POST":
            variables = body["variables"]
            if (
                child_page
                and "thread" in variables
                and variables["thread"].startswith("THREAD41-")
            ):
                comment = result["data"]["node"]["comments"]["nodes"][0]
            elif not child_page and variables.get("number") == 41:
                comment = result["data"]["repository"]["pullRequest"]["reviewThreads"][
                    "nodes"
                ][0]["comments"]["nodes"][0]
            else:
                return result, headers
            rejected_nodes.append(comment["id"])
            comment["fullDatabaseId"] = None
        return result, headers

    api.route = route
    with pytest.raises(CatalogError) as partial:
        sync(store, repo)
    assert rejected_nodes
    assert (
        store.one(
            "SELECT count(*) FROM unresolved_payloads WHERE reason LIKE '%CANONICAL_DOCUMENT_ID_MISSING%'"
        )[0]
        > 0
    )
    for node in rejected_nodes:
        assert not store.one(
            "SELECT 1 FROM documents WHERE provider_change_request_document_id=?",
            (node,),
        )
        assert any(
            node.encode() in row[0] for row in store.all("SELECT body FROM payloads")
        )
    enabled = False
    sync(store, repo, job=partial.value.details["job_id"])
    assert (
        store.one(
            "SELECT count(*) FROM review_comments WHERE change_request_id='repo:41' AND review_thread_provider_resource_id='THREAD41-0'"
        )[0]
        == api.reply_count
    )
    assert not store.all("PRAGMA foreign_key_check")
