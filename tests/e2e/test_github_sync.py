import json
import sqlite3

from repo_catalog.config import load, serialize
from tests.support.cli import pages, run
from tests.support.github_fixture import GitHubFixture


def configure(state, api, fixture):
    cfg = load(state)
    cfg["github"].update(rest_base_url=api.url, graphql_url=api.url + "/graphql")
    (state / "catalog.toml").write_text(serialize(cfg))
    sid = run(
        state,
        "sources",
        "add",
        "github",
        "--owner",
        "fixture",
        "--clone-url-override",
        "101=" + fixture.alpha.url,
    )["data"]["source_id"]
    env = {"GH_TOKEN": "fixture-dummy"}
    repo = run(state, "discover", "--source", sid, env=env)["data"]["repositories"][0][
        "repository_uuidv4"
    ]
    return sid, repo, env


def test_selected_inventory_scope(catalog):
    state, fixture, repos = catalog
    with GitHubFixture(fixture) as api:
        cfg = load(state)
        cfg["github"].update(rest_base_url=api.url, graphql_url=api.url + "/graphql")
        (state / "catalog.toml").write_text(serialize(cfg))
        run(
            state,
            "sources",
            "add",
            "github",
            "--owner",
            "fixture",
            "--include-repo",
            "outside/alpha",
            expected=2,
        )
        sid = run(
            state,
            "sources",
            "add",
            "github",
            "--owner",
            "fixture",
            "--include-repo",
            "alpha",
        )["data"]["source_id"]
        result = run(
            state, "discover", "--source", sid, env={"GH_TOKEN": "fixture-dummy"}
        )
        assert [r["name"] for r in result["data"]["repositories"]] == ["fixture/alpha"]
        assert {path for _, path, _ in api.requests} == {
            "/user",
            "/repos/fixture/alpha",
        }
        assert not api.errors


def test_document_queries_independent_of_git_availability(catalog):
    state, fixture, repos = catalog
    with GitHubFixture(fixture) as api:
        _, repo, env = configure(state, api, fixture)
        run(
            state,
            "endpoints",
            "add",
            "--repo",
            repo,
            "--url",
            "file:///missing",
            "--preferred",
        )
        run(state, "sync", "pr", "--repo", repo, env=env, expected=3)
        result = run(
            state, "search", "pr", "--repo", repo, "--literal", "comment-marker"
        )
        assert result["coverage"]["complete_for_requested_scope"]
        assert result["data"]["items"]
        run(
            state,
            "search",
            "pr",
            "--repo",
            repo,
            "--literal",
            "comment-marker",
            "--path",
            "pr-only.txt",
            expected=3,
        )


def test_resume_skips_completed_prs(catalog):
    state, fixture, repos = catalog
    with GitHubFixture(fixture) as api:
        _, repo, env = configure(state, api, fixture)
        api.failures["/repos/fixture/alpha/pulls/42/reviews"] = [500] * 5
        result = run(state, "sync", "pr", "--repo", repo, env=env, expected=3)
        previous = len(api.requests)
        run(state, "jobs", "resume", result["data"]["job_id"], env=env)
        for method, path, params in api.requests[previous:]:
            assert not any(
                path.startswith(prefix)
                for prefix in (
                    "/repos/fixture/alpha/pulls/41",
                    "/repos/fixture/alpha/issues/41",
                    "/repos/fixture/alpha/pulls/43",
                    "/repos/fixture/alpha/issues/43",
                )
            )


def test_pr_documents(catalog):
    state, fixture, repos = catalog
    with GitHubFixture(fixture) as api:
        sid, repo, env = configure(state, api, fixture)
        run(state, "sync", "all", "--repo", repo, env=env)
        for marker, kind in [
            ("title-marker", "pr-title"),
            ("body-marker", "pr-body"),
            ("comment-marker", "issue-comment"),
            ("review-marker", "review"),
            ("review-comment-marker", "review-comment"),
        ]:
            result = pages(
                state,
                "search",
                "pr",
                "--repo",
                repo,
                "--literal",
                marker,
                "--document-kind",
                kind,
            )
            assert len(result) == 3 and all(r["document_kind"] == kind for r in result)
        assert {r["state"] for r in pages(state, "pr", "list", "--repo", repo)} == {
            "open",
            "closed",
            "merged",
        }
        shown = run(
            state, "pr", "show", "--repo", repo, "--provider-change-request-number", 43
        )["data"]["items"][0]
        code = shown["code_observation"]
        details = json.loads(code["details"])
        links = {link["role"]: link for link in shown["code_links"]}
        assert code["state"] == "complete"
        assert details["code_inputs_complete"] is True
        assert details["merge"]["test-merge"] is None
        assert "test-merge" not in details["expected_roles"]
        assert "test-merge" not in links
        merge_oid = fixture.alpha.commits["P"]
        assert details["merge"]["merge"] == merge_oid
        assert details["expected_roles"]["merge"] == merge_oid
        assert links["merge"]["oid"] == f"{code['object_format']}:{merge_oid}"
        assert links["merge"]["acquisition_root_id"] is not None
        assert pages(
            state,
            "search",
            "pr",
            "--repo",
            repo,
            "--literal",
            "review-comment-marker",
            "--resolved",
            "true",
            "--outdated",
            "true",
        )
        assert not api.errors
    assert b"fixture-dummy" not in (state / "catalog.sqlite3").read_bytes()


def test_observed_content_and_replay_fencing(catalog):
    state, fixture, repos = catalog
    with GitHubFixture(fixture) as api:
        _, repo, env = configure(state, api, fixture)
        for stage in ("A", "B", "A"):
            api.stage = stage
            run(state, "sync", "pr", "--repo", repo, env=env)
        latest = pages(
            state,
            "search",
            "pr",
            "--repo",
            repo,
            "--literal",
            "comment-marker B",
            "--document-kind",
            "issue-comment",
        )
        assert latest == []
        historical = pages(
            state,
            "search",
            "pr",
            "--repo",
            repo,
            "--literal",
            "comment-marker B",
            "--document-kind",
            "issue-comment",
            "--document-observations",
            "all",
        )
        assert len(historical) == 3
        a = pages(
            state,
            "search",
            "pr",
            "--repo",
            repo,
            "--literal",
            "comment-marker A",
            "--document-kind",
            "issue-comment",
            "--document-observations",
            "all",
        )
        assert len(a) == 6 and all(r["document_observed_at_us"] for r in a)
        assert all(
            len({r["document_observation_id"] for r in a if r["pr_id"] == pr}) == 2
            for pr in {r["pr_id"] for r in a}
        )


def test_private_inventory(catalog):
    state, fixture, repos = catalog
    with GitHubFixture(fixture) as api:
        _, repo, env = configure(state, api, fixture)
        item = run(state, "repos", "show", "--repo", repo)["data"]["items"][0]
        assert item["metadata"] == {}
        observations = item["inventory_observations"]
        assert len(observations) == 1
        assert observations[0]["source_registration_uuidv4"]
        assert observations[0]["parsed_result_uuidv4"]
        assert observations[0]["repository_uuidv4"] == repo
        metadata = observations[0]["metadata"]
        assert metadata["private"] and metadata["archived"] and metadata["fork"]


def test_unknown_inventory_scope_retains_known_repositories(catalog):
    state, fixture, repos = catalog
    with GitHubFixture(fixture) as api:
        sid, repo, env = configure(state, api, fixture)
        api.inventory_verified = False
        partial = run(state, "discover", "--source", sid, env=env, expected=3)
        assert partial["data"]["repositories"] == [
            {"repository_uuidv4": repo, "name": "fixture/alpha"}
        ]
        assert (
            partial["coverage"]["missing"][0]["reason"] == "INVENTORY_SCOPE_UNVERIFIED"
        )
        api.inventory_verified = True
        run(state, "jobs", "resume", partial["data"]["job_id"], env=env)


def test_unobserved_refresh_failure_preserves_saved_coverage_and_waits(catalog):
    state, fixture, repos = catalog
    with GitHubFixture(fixture) as api:
        _, repo, env = configure(state, api, fixture)
        run(state, "sync", "pr", "--repo", repo, env=env)
        api.failures["/user"] = [401]
        failed = run(state, "sync", "pr", "--repo", repo, env=env, expected=3)
        assert failed["data"]["results"][0]["error"] == "CREDENTIALS_MISSING"
        assert not failed["coverage"]["complete_for_requested_scope"]
        job = run(state, "jobs", "show", failed["data"]["job_id"])["data"]["items"][0]
        assert job["state"] == "waiting"
        saved = run(
            state,
            "search",
            "pr",
            "--repo",
            repo,
            "--literal",
            "body-marker",
        )
        assert (
            saved["data"]["items"] and saved["coverage"]["complete_for_requested_scope"]
        )


def test_nested_partial(catalog):
    state, fixture, repos = catalog
    with GitHubFixture(fixture) as api:
        _, repo, env = configure(state, api, fixture)
        api.graphql_partial = True
        result = run(state, "sync", "pr", "--repo", repo, env=env, expected=3)
        assert result["coverage"]["missing"]
        result = run(
            state,
            "search",
            "pr",
            "--repo",
            repo,
            "--literal",
            "body-marker",
            expected=3,
        )
        assert result["data"]["items"] and result["status"] == "partial"


def test_nested_pagination(catalog):
    state, fixture, repos = catalog
    with GitHubFixture(fixture) as api:
        _, repo, env = configure(state, api, fixture)
        api.thread_count = 101
        api.reply_count = 101
        run(state, "sync", "pr", "--repo", repo, env=env)
        with sqlite3.connect(state / "catalog.sqlite3") as db:
            assert (
                db.execute(
                    "SELECT count(*) FROM review_threads WHERE change_request_id=?",
                    (repo + ":41",),
                ).fetchone()[0]
                == 101
            )
            assert (
                db.execute(
                    "SELECT count(*) FROM review_resources WHERE change_request_id=? AND kind='review-comment'",
                    (repo + ":41",),
                ).fetchone()[0]
                == 10201
            )
        assert not api.errors


def test_child_watermarks(catalog):
    state, fixture, repos = catalog
    with GitHubFixture(fixture) as api:
        _, repo, env = configure(state, api, fixture)
        api.incremental = True
        run(state, "sync", "pr", "--repo", repo, env=env)
        with sqlite3.connect(state / "catalog.sqlite3") as db:
            old = dict(
                db.execute(
                    "SELECT f.kind,i.safe_watermark_us FROM incremental_scans i JOIN fetch_collections f ON f.fetch_collection_id=i.fetch_collection_id ORDER BY i.scan_started_at_us"
                )
            )
        api.stage = "B"
        api.failures["/repos/fixture/alpha/issues/comments"] = [503] * 5
        run(state, "sync", "pr", "--repo", repo, env=env, expected=3)
        with sqlite3.connect(state / "catalog.sqlite3") as db:
            new = dict(
                db.execute(
                    "SELECT f.kind,i.safe_watermark_us FROM incremental_scans i JOIN fetch_collections f ON f.fetch_collection_id=i.fetch_collection_id ORDER BY i.scan_started_at_us"
                )
            )
        issue = "issue-comment-incremental"
        review = "review-comment-incremental"
        assert old[issue] == new[issue] and old[review] != new[review]
        assert any(
            params.get("since")
            for method, path, params in api.requests
            if path.endswith("/pulls/comments")
        )


def test_code_races_caps(catalog):
    state, fixture, repos = catalog
    with GitHubFixture(fixture) as api:
        _, repo, env = configure(state, api, fixture)
        api.cap_mode = True
        api.prs[41].update(commits=251, changed_files=3001)
        run(state, "sync", "pr", "--repo", repo, env=env, expected=3)
        shown = run(
            state,
            "pr",
            "show",
            "--repo",
            repo,
            "--provider-change-request-number",
            41,
            expected=3,
        )["data"]["items"][0]
        assert shown["code_observation"]["state"] == "partial"
        assert any(c["reason"] == "API_CAP" for c in shown["collections"])
        assert len(shown["file_changes"]) == 100
        assert shown["nested_collections"]["file_changes"] == {
            "returned": 100,
            "total": 3001,
            "has_more": True,
        }
        with sqlite3.connect(state / "catalog.sqlite3") as db:
            assert (
                db.execute(
                    "SELECT count(*) FROM code_file_changes f JOIN code_observations c ON c.file_code_listing_id=f.code_listing_id WHERE c.code_observation_id=?",
                    (shown["code_observation"]["code_observation_id"],),
                ).fetchone()[0]
                == 3001
            )


def test_rate_etag(catalog):
    state, fixture, repos = catalog
    with GitHubFixture(fixture) as api:
        _, repo, env = configure(state, api, fixture)
        api.etag = True
        api.failures["/repos/fixture/alpha/pulls/41/comments"] = [429]
        result = run(state, "sync", "pr", "--repo", repo, env=env, expected=3)
        job = result["data"]["job_id"]
        requests = len(api.requests)
        run(state, "jobs", "resume", job, env=env, expected=3)
        assert len(api.requests) == requests
        with sqlite3.connect(state / "catalog.sqlite3") as db:
            db.execute("UPDATE job_attempts SET not_before_us=0 WHERE job_id=?", (job,))
        run(state, "jobs", "resume", job, env=env)
        before = pages(
            state, "search", "pr", "--repo", repo, "--literal", "body-marker"
        )
        run(state, "sync", "pr", "--repo", repo, env=env)
        after = pages(state, "search", "pr", "--repo", repo, "--literal", "body-marker")
        assert [r["body"] for r in before] == [r["body"] for r in after]


def test_page_crash(catalog, tmp_path):
    from tests.e2e.test_recovery import interrupted_job
    from tests.support.process import start_hooked

    state, fixture, repos = catalog
    with GitHubFixture(fixture) as api:
        _, repo, env = configure(state, api, fixture)
        process, hooks = start_hooked(
            state, "after_api_page_commit", tmp_path, "sync", "pr", "--repo", repo
        )
        process.kill()
        process.communicate(timeout=10)
        with sqlite3.connect(state / "catalog.sqlite3") as db:
            assert (
                db.execute("SELECT count(*) FROM fetch_occurrences").fetchone()[0] == 1
            )
        run(state, "jobs", "resume", interrupted_job(state), env=env)
        assert len(pages(state, "pr", "list", "--repo", repo)) == 3
