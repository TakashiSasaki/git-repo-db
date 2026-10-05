"""Characterize v2 defects; these assertions intentionally describe unfixed v2.

The production collector/DDL are not changed by this design investigation.
After implementing the redesign, replace these with the specified invariants.
"""

import json
import sqlite3

from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.job_service import JobService
from repo_catalog.domain.models import CancellationToken
from scripts.schema_audit import diagnose, readonly
from tests.e2e.test_github_sync import configure
from tests.support.cli import run
from tests.support.github_fixture import GitHubFixture


def test_v2_two_head_refs_same_oid_abort_capture(catalog):
    state, fixture, repos = catalog
    fixture.alpha.ref("refs/heads/alias", "N")
    result = run(state, "sync", "git", "--repo", repos["alpha"], expected=5)
    assert result["error"]["code"] == "DATABASE_ERROR"
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        # Capturing refs and roots is one transaction; both observations roll back.
        assert db.execute("SELECT count(*) FROM ref_observations").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM acquisition_roots").fetchone()[0] == 0
        assert (
            db.execute("SELECT state FROM collection_runs").fetchone()[0] == "fetching"
        )
        assert (
            db.execute(
                "SELECT state FROM jobs ORDER BY created_at DESC LIMIT 1"
            ).fetchone()[0]
            == "failed"
        )


def test_v2_partial_commit_and_file_pages_split_code_observations(catalog):
    state, fixture, _ = catalog
    with GitHubFixture(fixture) as api:
        source, repo, env = configure(state, api, fixture)
        original = api.route

        def route(method, path, params, body):
            if method == "GET" and path in (
                "/repos/fixture/alpha/pulls/41/commits",
                "/repos/fixture/alpha/pulls/41/files",
            ):
                second = params.get("page") == ["2"]
                value = (
                    {"sha": fixture.alpha.commits["N" if second else "P"]}
                    if path.endswith("commits")
                    else {
                        "filename": "second.txt" if second else "first.txt",
                        "status": "added",
                    }
                )
                headers = (
                    {}
                    if second
                    else {"Link": f'<{api.url}{path}?per_page=100&page=2>; rel="next"'}
                )
                return [value], headers
            return original(method, path, params, body)

        api.route = route
        api.prs[41].update(commits=2, changed_files=2)

        # Page 1 commits, then page 2 reaches a retry boundary. Other PRs finish.
        # Handler failures are path-only, so inject once after observing page 1.
        def failing_route(method, path, params, body):
            result = route(method, path, params, body)
            if (
                method == "GET"
                and path.endswith(("/41/commits", "/41/files"))
                and not params.get("page")
            ):
                api.failures[path] = [503] * 5
            return result

        api.route = failing_route
        first = run(state, "sync", "pr", "--repo", repo, env=env, expected=3)
        api.route = route
        api.failures.clear()
        run(state, "jobs", "resume", first["data"]["job_id"], env=env)
        with sqlite3.connect(state / "catalog.sqlite3") as db:
            latest = db.execute(
                "SELECT id,state FROM pr_code_observations WHERE pr_id=? ORDER BY id DESC LIMIT 1",
                (repo + ":41",),
            ).fetchone()
            assert latest[1] == "complete"
            for table in ("pr_commits", "pr_file_changes"):
                # Complete is asserted even though the latest code observation
                # contains only page 2. Page 1 remains on the older observation.
                assert db.execute(
                    f"SELECT ordinal FROM {table} WHERE code_observation=?",
                    (latest[0],),
                ).fetchall() == [(10000,)]
                assert (
                    db.execute(
                        f"SELECT count(DISTINCT code_observation) FROM {table} WHERE code_observation IN (SELECT id FROM pr_code_observations WHERE pr_id=?)",
                        (repo + ":41",),
                    ).fetchone()[0]
                    == 2
                )
            saved = db.execute(
                "SELECT count(*) FROM collection_pages WHERE collection_id IN (SELECT id FROM collections WHERE pr_id=? AND kind IN ('pr-commits','pr-files'))",
                (repo + ":41",),
            ).fetchone()[0]
            assert saved == 4
        assert not api.errors
        with readonly(state / "catalog.sqlite3") as db:
            violations = diagnose(db)["violations"]
        assert violations["complete_commit_listing_fragment"] == 1
        assert violations["complete_file_listing_fragment"] == 1


def test_v2_reusing_collection_advances_watermark_without_request(catalog, monkeypatch):
    state, fixture, _ = catalog
    with GitHubFixture(fixture) as api:
        _, repo_id, env = configure(state, api, fixture)
        monkeypatch.setenv("GH_TOKEN", env["GH_TOKEN"])
        with Store(state) as store:
            repo = dict(store.one("SELECT * FROM repositories WHERE id=?", (repo_id,)))
            job = JobService(store).create("sync", {"kind": "pr"})
            collector = GitHubCollector(store, CancellationToken())
            collector.principal = "fixture"
            endpoint = api.url + "/repos/fixture/alpha/issues/comments"
            monkeypatch.setattr(
                "repo_catalog.adapters.github.collector.now",
                lambda: "2026-01-01T00:00:00+00:00",
            )
            collector.incremental_comments(
                repo, job, "issue-comment", endpoint, "issue_url"
            )
            before = len(api.requests)
            monkeypatch.setattr(
                "repo_catalog.adapters.github.collector.now",
                lambda: "2026-01-02T00:00:00+00:00",
            )
            collector.incremental_comments(
                repo, job, "issue-comment", endpoint, "issue_url"
            )
            assert len(api.requests) == before
            value = store.one(
                "SELECT value FROM sync_checkpoints WHERE scope LIKE 'watermark:%'"
            )[0]
            assert json.loads(value)["watermark"] == "2026-01-02T00:00:00+00:00"
            assert store.one("SELECT count(*) FROM collection_pages")[0] == 1
            collector.http.close()
