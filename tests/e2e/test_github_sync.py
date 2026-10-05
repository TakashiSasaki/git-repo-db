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
        "repo_id"
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
        with sqlite3.connect(state / "catalog.sqlite3") as db:
            db.execute(
                "UPDATE repositories SET url='file:///missing' WHERE id=?", (repo,)
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
        with sqlite3.connect(state / "catalog.sqlite3") as db:
            db.execute("DELETE FROM sync_checkpoints WHERE scope LIKE 'pr-complete:%'")
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
        shown = run(state, "pr", "show", "--repo", repo, "--number", 43)["data"][
            "items"
        ][0]
        assert (
            json.loads(shown["code_observation"]["details"])["merge"]["test-merge"]
            is None
        )
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


def test_versions_fencing(catalog):
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
            "--document-versions",
            "observed",
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
            "--document-versions",
            "observed",
        )
        assert all(len(r["observations"]) == 2 for r in a)


def test_private_inventory(catalog):
    state, fixture, repos = catalog
    with GitHubFixture(fixture) as api:
        _, repo, env = configure(state, api, fixture)
        item = run(state, "repos", "show", "--repo", repo)["data"]["items"][0]
        assert (
            item["metadata"]["private"]
            and item["metadata"]["archived"]
            and item["metadata"]["fork"]
        )


def test_unknown_inventory_scope_retains_known_repositories(catalog):
    state, fixture, repos = catalog
    with GitHubFixture(fixture) as api:
        sid, repo, env = configure(state, api, fixture)
        api.inventory_verified = False
        partial = run(state, "discover", "--source", sid, env=env, expected=3)
        assert partial["data"]["repositories"] == [
            {"repo_id": repo, "name": "fixture/alpha"}
        ]
        assert (
            partial["coverage"]["missing"][0]["reason"] == "INVENTORY_SCOPE_UNVERIFIED"
        )
        api.inventory_verified = True
        run(state, "jobs", "resume", partial["data"]["job_id"], env=env)


def test_refresh_failure_does_not_reuse_complete_coverage(catalog):
    state, fixture, repos = catalog
    with GitHubFixture(fixture) as api:
        _, repo, env = configure(state, api, fixture)
        run(state, "sync", "pr", "--repo", repo, env=env)
        api.failures["/user"] = [401]
        run(state, "sync", "pr", "--repo", repo, env=env, expected=3)
        saved = run(
            state,
            "search",
            "pr",
            "--repo",
            repo,
            "--literal",
            "body-marker",
            expected=3,
        )
        assert (
            saved["data"]["items"]
            and not saved["coverage"]["complete_for_requested_scope"]
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
                    "SELECT count(*) FROM review_threads WHERE pr_id=?", (repo + ":41",)
                ).fetchone()[0]
                == 101
            )
            assert (
                db.execute(
                    "SELECT count(*) FROM pr_documents WHERE pr_id=? AND kind='review-comment'",
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
                    "SELECT scope,value FROM sync_checkpoints WHERE scope LIKE 'watermark:%'"
                )
            )
        api.stage = "B"
        api.failures["/repos/fixture/alpha/issues/comments"] = [503] * 5
        run(state, "sync", "pr", "--repo", repo, env=env, expected=3)
        with sqlite3.connect(state / "catalog.sqlite3") as db:
            new = dict(
                db.execute(
                    "SELECT scope,value FROM sync_checkpoints WHERE scope LIKE 'watermark:%'"
                )
            )
        issue = next(k for k in old if ":issue-comment:" in k)
        review = next(k for k in old if ":review-comment:" in k)
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
        shown = run(state, "pr", "show", "--repo", repo, "--number", 41, expected=3)[
            "data"
        ]["items"][0]
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
                    "SELECT count(*) FROM pr_file_changes WHERE code_observation=?",
                    (shown["code_observation"]["id"],),
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
            db.execute("UPDATE jobs SET not_before=0 WHERE id=?", (job,))
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
                db.execute("SELECT count(*) FROM collection_pages").fetchone()[0] == 1
            )
        run(state, "jobs", "resume", interrupted_job(state), env=env)
        assert len(pages(state, "pr", "list", "--repo", repo)) == 3
