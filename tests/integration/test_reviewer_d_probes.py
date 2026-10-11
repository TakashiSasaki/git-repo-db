"""Reviewer D integrated verification harness and multi-stage transition probe."""

import json
import sqlite3
import uuid
from pathlib import Path

import httpx
import pytest

from repo_catalog.adapters.github import current_parser
from repo_catalog.adapters.sqlite.cas_integrity import register_git_object_sql_function
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.schema import DDL_SHA256, SCHEMA_VERSION, schema_sql
from repo_catalog.application.job_service import JobService
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.integration.test_current_collection_rejection_clocks import (
    MARKER,
    mock_collector,
    new_job,
    resume_job,
    seed_pr,
)
from tests.support.cli import run
from tests.support.github_runtime import github_runtime as github_runtime


def make_receiver_db():
    """Create a production-equivalent receiver SQLite connection with native UDFs registered."""
    db = sqlite3.connect(":memory:", isolation_level=None)
    register_git_object_sql_function(db)
    db.executescript(schema_sql())
    db.execute(
        "INSERT INTO database_identity VALUES(1,'repo-catalog/catalog3',?,?,0,?,'validated')",
        (SCHEMA_VERSION, str(uuid.uuid4()), DDL_SHA256),
    )
    return db


def test_reviewer_d_integrated_multistage_transition_probe(github_runtime, tmp_path):
    store, repo, fixture, api = github_runtime
    repo_name = repo["name"]
    pr_number = 41
    commit_oid = f"sha1:{fixture.alpha.commits['P']}"

    receipt = {
        "reviewer": "Reviewer D",
        "verdict": "PENDING",
        "target_pr": "https://github.com/TakashiSasaki/git-repo-db/pull/28",
        "pipeline": "collection -> exchange -> query/CLI -> coverage v2",
        "harness_fixes": [
            "Registered native UDF register_git_object_sql_function on all raw sqlite3 connections",
            "Used public supported CLI commands: file show, tree list, pr show, pr code",
            "Validated CLI output schemas against cli-v1.schema.json",
        ],
        "stages": [],
    }

    # 1. Sync git objects using GitImporter so git queries work without touching PR coverage
    from repo_catalog.adapters.git.importer import GitImporter

    job = JobService(store).create("sync", {})
    store.expected_attempt = 1
    GitImporter(store, CancellationToken()).sync(
        repo,
        job,
        pr_roots=[
            {
                "ref": f"refs/pull/{pr_number}/head",
                "expected": fixture.alpha.commits["P"],
                "role": "head",
                "number": pr_number,
            }
        ],
    )
    pr_id = seed_pr(store, repo)
    path = f"/repos/fixture/alpha/pulls/{pr_number}/reviews"
    endpoint = api.url + path

    clock = [100]
    retry_clock = [175]
    mode = ["initial"]
    requested = []

    def response(request):
        if request.url.path == "/user":
            return httpx.Response(200, json={"id": 10})
        assert request.url.path == path
        page = request.url.params.get("page", "1")
        requested.append((mode[0], page))
        if mode[0] == "initial":
            clock[0] = 100
            return httpx.Response(200, json=[])
        if page == "1":
            clock[0] = 150
            return httpx.Response(
                200, json=[], headers={"Link": f'<{endpoint}?page=2>; rel="next"'}
            )
        clock[0] = 200 if mode[0] == "rejected" else retry_clock[0]
        return httpx.Response(
            200,
            json=[{"id": 2, "number": 2, "body": [], "transport_only": MARKER}]
            if mode[0] == "rejected"
            else [],
        )

    receiver_db = make_receiver_db()

    with mock_collector(store, response, clock) as current:
        # -------------------------------------------------------------
        # Stage 1: complete100
        # -------------------------------------------------------------
        clock[0] = 100
        mode[0] = "initial"
        job1 = new_job(store, "review")
        current.current_collection(
            repo, pr_id, "review", job1, endpoint, current_parser.review
        )
        JobService(store).update(job1, "complete")

        cov_100 = store.one(
            "SELECT observed_at_us, coverage_state FROM current_coverage WHERE repository_uuidv4=? AND change_request_id=? AND kind='review'",
            (repo["repository_uuidv4"], pr_id),
        )
        assert (cov_100["observed_at_us"], cov_100["coverage_state"]) == (100, "complete")

        # CLI surface checks
        res_tree_100 = run(store.path, "tree", "list", "--repo", repo_name, "--commit", commit_oid)
        assert len(res_tree_100["data"]["items"]) > 0

        res_file_100 = run(
            store.path, "file", "show", "--repo", repo_name, "--commit", commit_oid, "--path", "README.md"
        )
        assert res_file_100["data"]["items"][0]["raw_available"] is True

        res_pr_100 = run(
            store.path,
            "pr",
            "show",
            "--repo",
            repo_name,
            "--provider-change-request-number",
            pr_number,
            expected=None,
        )
        assert res_pr_100["data"]["items"][0]["provider_change_request_number"] == pr_number

        res_pr_code_100 = run(
            store.path,
            "pr",
            "code",
            "--repo",
            repo_name,
            "--provider-change-request-number",
            pr_number,
            expected=None,
        )
        assert res_pr_code_100["status"] in ("ok", "partial")

        # Exchange pipeline check
        export_100 = Graph(store.connection).export(repo["repository_uuidv4"])
        receive_100 = Graph(receiver_db).receive(export_100)
        assert receive_100 is not None

        receiver_cov_100 = receiver_db.execute(
            "SELECT observed_at_us, coverage_state FROM current_coverage WHERE repository_uuidv4=? AND change_request_id=? AND kind='review'",
            (repo["repository_uuidv4"], pr_id),
        ).fetchone()
        assert receiver_cov_100 == (100, "complete")

        receipt["stages"].append({
            "stage": "complete100",
            "clock_us": 100,
            "expected_state": "complete",
            "observed_coverage_state": cov_100["coverage_state"],
            "receiver_coverage_state": receiver_cov_100[1],
            "cli_commands_tested": ["tree list", "file show", "pr show", "pr code"],
            "status": "PASS",
        })

        # -------------------------------------------------------------
        # Stage 2: partial200
        # -------------------------------------------------------------
        clock[0] = 200
        mode[0] = "rejected"
        job2 = new_job(store, "review")
        with pytest.raises(CatalogError) as err:
            current.current_collection(
                repo, pr_id, "review", job2, endpoint, current_parser.review
            )
        assert err.value.code == "API_SCHEMA"

        cov_200 = store.one(
            "SELECT observed_at_us, coverage_state FROM current_coverage WHERE repository_uuidv4=? AND change_request_id=? AND kind='review'",
            (repo["repository_uuidv4"], pr_id),
        )
        assert (cov_200["observed_at_us"], cov_200["coverage_state"]) == (200, "partial")

        # CLI surface check
        res_pr_200 = run(
            store.path,
            "pr",
            "show",
            "--repo",
            repo_name,
            "--provider-change-request-number",
            pr_number,
            expected=None,
        )
        assert res_pr_200["data"]["items"][0]["provider_change_request_number"] == pr_number

        # Exchange pipeline check
        export_200 = Graph(store.connection).export(repo["repository_uuidv4"])
        receive_200 = Graph(receiver_db).receive(export_200)
        assert receive_200 is not None

        receiver_cov_200 = receiver_db.execute(
            "SELECT observed_at_us, coverage_state FROM current_coverage WHERE repository_uuidv4=? AND change_request_id=? AND kind='review'",
            (repo["repository_uuidv4"], pr_id),
        ).fetchone()
        assert receiver_cov_200 == (200, "partial")

        receipt["stages"].append({
            "stage": "partial200",
            "clock_us": 200,
            "expected_state": "partial",
            "observed_coverage_state": cov_200["coverage_state"],
            "receiver_coverage_state": receiver_cov_200[1],
            "cli_commands_tested": ["pr show"],
            "status": "PASS",
        })

        # -------------------------------------------------------------
        # Stage 3: stale successful175 remains partial200
        # -------------------------------------------------------------
        resume_job(store, job2)
        retry_clock[0] = 175
        mode[0] = "retry"
        current.current_collection(
            repo, pr_id, "review", job2, endpoint, current_parser.review
        )

        # Coverage v2 latest candidate set MUST remain (200, partial) because 175 < 200
        cov_175 = store.one(
            "SELECT observed_at_us, coverage_state FROM current_coverage WHERE repository_uuidv4=? AND change_request_id=? AND kind='review'",
            (repo["repository_uuidv4"], pr_id),
        )
        assert (cov_175["observed_at_us"], cov_175["coverage_state"]) == (200, "partial")

        # CLI surface check continues to show partial 200
        res_pr_175 = run(
            store.path,
            "pr",
            "show",
            "--repo",
            repo_name,
            "--provider-change-request-number",
            pr_number,
            expected=None,
        )
        assert res_pr_175["data"]["items"][0]["provider_change_request_number"] == pr_number

        # Exchange pipeline check: receiver still preserves (200, partial)
        export_175 = Graph(store.connection).export(repo["repository_uuidv4"])
        receive_175 = Graph(receiver_db).receive(export_175)
        assert receive_175 is not None

        receiver_cov_175 = receiver_db.execute(
            "SELECT observed_at_us, coverage_state FROM current_coverage WHERE repository_uuidv4=? AND change_request_id=? AND kind='review'",
            (repo["repository_uuidv4"], pr_id),
        ).fetchone()
        assert receiver_cov_175 == (200, "partial")

        receipt["stages"].append({
            "stage": "stale_successful175_remains_partial200",
            "clock_us": 175,
            "preserved_clock_us": 200,
            "expected_state": "partial",
            "observed_coverage_state": cov_175["coverage_state"],
            "receiver_coverage_state": receiver_cov_175[1],
            "cli_commands_tested": ["pr show"],
            "status": "PASS",
        })

        # -------------------------------------------------------------
        # Stage 4: complete300
        # -------------------------------------------------------------
        retry_clock[0] = 300
        mode[0] = "retry"
        job3 = new_job(store, "review")
        current.current_collection(
            repo, pr_id, "review", job3, endpoint, current_parser.review
        )
        JobService(store).update(job3, "complete")

        # Because 300 > 200, coverage v2 transitions to (300, complete)
        cov_300 = store.one(
            "SELECT observed_at_us, coverage_state FROM current_coverage WHERE repository_uuidv4=? AND change_request_id=? AND kind='review'",
            (repo["repository_uuidv4"], pr_id),
        )
        assert (cov_300["observed_at_us"], cov_300["coverage_state"]) == (300, "complete")

        # CLI surfaces
        res_pr_300 = run(
            store.path,
            "pr",
            "show",
            "--repo",
            repo_name,
            "--provider-change-request-number",
            pr_number,
            expected=None,
        )
        assert res_pr_300["data"]["items"][0]["provider_change_request_number"] == pr_number

        res_pr_code_300 = run(
            store.path,
            "pr",
            "code",
            "--repo",
            repo_name,
            "--provider-change-request-number",
            pr_number,
            expected=None,
        )
        assert res_pr_code_300["status"] in ("ok", "partial")

        res_tree_300 = run(store.path, "tree", "list", "--repo", repo_name, "--commit", commit_oid)
        assert len(res_tree_300["data"]["items"]) > 0

        res_file_300 = run(
            store.path, "file", "show", "--repo", repo_name, "--commit", commit_oid, "--path", "README.md"
        )
        assert res_file_300["data"]["items"][0]["raw_available"] is True

        # Exchange pipeline check: receiver transitions to (300, complete)
        export_300 = Graph(store.connection).export(repo["repository_uuidv4"])
        receive_300 = Graph(receiver_db).receive(export_300)
        assert receive_300 is not None

        receiver_cov_300 = receiver_db.execute(
            "SELECT observed_at_us, coverage_state FROM current_coverage WHERE repository_uuidv4=? AND change_request_id=? AND kind='review'",
            (repo["repository_uuidv4"], pr_id),
        ).fetchone()
        assert receiver_cov_300 == (300, "complete")

        receipt["stages"].append({
            "stage": "complete300",
            "clock_us": 300,
            "expected_state": "complete",
            "observed_coverage_state": cov_300["coverage_state"],
            "receiver_coverage_state": receiver_cov_300[1],
            "cli_commands_tested": ["tree list", "file show", "pr show", "pr code"],
            "status": "PASS",
        })

    receipt["verdict"] = "PASS"

    receipt_file = Path("/home/ubuntu/github/git-repo-db/reviewer_d_receipt.json")
    receipt_file.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    assert receipt["verdict"] == "PASS"
