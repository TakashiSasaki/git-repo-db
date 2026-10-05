"""Reproducible CLI-only demonstration with independent synthetic fixtures."""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.e2e.test_cache import expire
from tests.e2e.test_github_sync import configure
from tests.support.cli import pages, run
from tests.support.git_fixture import GitFixture
from tests.support.github_fixture import GitHubFixture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--scenario", choices=["offline-recovery"], required=True)
    args = parser.parse_args()
    work = args.work_dir.resolve()
    if work.exists() and any(work.iterdir()):
        parser.error("Work directory must be new or empty")
    work.mkdir(parents=True, exist_ok=True)
    os.chmod(work, 0o700)
    evidence = []
    state = work / "state"

    def execute(*argv, **kwargs):
        value = run(state, *argv, **kwargs)
        evidence.append(
            {
                "argv": [
                    "repo-catalog",
                    "--state-dir",
                    str(state),
                    "--format",
                    "json",
                    *map(str, argv),
                ],
                "result": value,
            }
        )
        return value

    fixture = GitFixture(work / "remotes")
    execute(
        "init",
        "--profile",
        "catalog-text-v1",
        "--cache-max-bytes",
        134217728,
        "--min-free-bytes",
        0,
    )
    for name in ("alpha", "beta", "empty"):
        source = execute(
            "sources",
            "add",
            "local-git",
            "--name",
            name,
            "--url",
            getattr(fixture, name).url,
        )["data"]["source_id"]
        execute("discover", "--source", source)
    with GitHubFixture(fixture) as api:
        _, repo, env = configure(state, api, fixture)
        execute("sync", "all", env=env)
        execute("search", "code", "--literal", "認証")
        execute("search", "pr", "--literal", "review-marker")
        execute("sync", "all", env=env)
        fixture.advance()
        api.stage = "B"
        execute("sync", "all", env=env)
        before_code = pages(state, "search", "code", "--literal", "認証")
        before_pr = pages(state, "search", "pr", "--literal", "review-marker")
        execute("doctor")
        expire(state)
        execute("cache", "gc", "--apply")
    shutil.rmtree(work / "remotes")
    assert pages(state, "search", "code", "--literal", "認証") == before_code
    assert pages(state, "search", "pr", "--literal", "review-marker") == before_pr
    execute("search", "code", "--literal", "認証")
    execute("search", "pr", "--literal", "review-marker")
    execute("index", "rebuild", "--kind", "all")
    assert pages(state, "search", "code", "--literal", "認証") == before_code
    backup = work / "backup.sqlite3"
    execute("db", "backup", "--output", backup)
    restored = work / "restored"
    restore = run(restored, "db", "restore", "--input", backup)
    assert pages(restored, "search", "code", "--literal", "認証") == before_code
    assert pages(restored, "search", "pr", "--literal", "review-marker") == before_pr
    execute("db", "check", "--full")
    evidence.append({"operation": "restore", "result": restore})
    current = execute("status")["catalog"]
    (work / "evidence.json").write_text(
        json.dumps(
            {
                "scenario": args.scenario,
                "checks": {
                    "code_queries_equal": True,
                    "pr_queries_equal": True,
                    "clones_evicted": not list((state / "cache").rglob("HEAD")),
                    "new_db_instance": restore["catalog"]["db_instance_id"]
                    != current["db_instance_id"],
                },
                "commands": evidence,
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    print(
        json.dumps(
            {
                "work_dir": str(work),
                "scenario": args.scenario,
                "evidence": str(work / "evidence.json"),
                "status": "complete",
            }
        )
    )


if __name__ == "__main__":
    main()
