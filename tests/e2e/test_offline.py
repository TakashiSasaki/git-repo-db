import shutil

from repo_catalog.config import load, serialize
from tests.e2e.test_cache import expire
from tests.e2e.test_github_sync import configure
from tests.support.cli import pages, run
from tests.support.github_fixture import GitHubFixture


def test_evicted_queries(catalog):
    state, fixture, repos = catalog
    with GitHubFixture(fixture) as api:
        _, repo, env = configure(state, api, fixture)
        run(state, "sync", "all", env=env)
        before_pr = pages(state, "search", "pr", "--literal", "review-marker")
    before_code = pages(state, "search", "code", "--literal", "認証")
    before_tree = pages(
        state, "tree", "list", "--repo", repos["alpha"], "--ref", "refs/heads/main"
    )
    expire(state)
    run(state, "cache", "gc", "--apply")
    shutil.rmtree(fixture.alpha.path.parent)
    assert not list((state / "cache").rglob("HEAD"))
    env = {"PATH": "/nonexistent"}
    # CLI absolute executable still imports installed Python but cannot find Git.
    import json
    import os
    import subprocess

    executable = shutil.which("repo-catalog")
    result = subprocess.run(
        [
            executable,
            "--state-dir",
            str(state),
            "--format",
            "json",
            "search",
            "code",
            "--literal",
            "認証",
        ],
        env={**os.environ, **env, "GH_TOKEN": "", "GITHUB_TOKEN": ""},
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["data"]["items"]
    assert pages(state, "search", "code", "--literal", "認証") == before_code
    assert pages(state, "search", "pr", "--literal", "review-marker") == before_pr
    assert (
        pages(
            state, "tree", "list", "--repo", repos["alpha"], "--ref", "refs/heads/main"
        )
        == before_tree
    )


def test_offline_reindex(catalog):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    before = pages(state, "search", "code", "--literal", "observed_in")
    expire(state)
    run(state, "cache", "gc", "--apply")
    shutil.rmtree(fixture.alpha.path.parent)
    result = run(state, "index", "rebuild", "--kind", "all")
    assert {r["kind"] for r in result["data"]["generations"]} == {
        "code",
        "pr",
        "issue",
        "commits",
    }
    assert pages(state, "search", "code", "--literal", "observed_in") == before
    cfg = load(state)
    cfg["search"]["backend"] = "scan"
    (state / "catalog.toml").write_text(serialize(cfg))
    assert (
        run(state, "index", "rebuild", expected=4)["error"]["code"]
        == "INDEX_UNAVAILABLE"
    )
    assert pages(state, "search", "code", "--literal", "observed_in") == before
