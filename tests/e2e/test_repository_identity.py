import sqlite3
import uuid

import pytest

from tests.e2e.test_recovery import interrupted_job
from tests.support.cli import pages, run
from tests.support.github_fixture import GitHubFixture
from tests.support.process import start_hooked


def test_remounted_paths_share_explicit_repo_identity(catalog, tmp_path):
    state, fixture, repos = catalog
    repo = repos["alpha"]
    local = tmp_path / "local-mount.git"
    network = tmp_path / "network-mount.git"
    local.symlink_to(fixture.alpha.path, target_is_directory=True)
    network.symlink_to(fixture.alpha.path, target_is_directory=True)
    endpoint = run(
        state, "endpoints", "add", "--repo", repo, "--url", local, "--preferred"
    )["data"]["endpoint_id"]
    assert uuid.UUID(endpoint).version == 4
    first = run(state, "sync", "git", "--repo", repo)["data"]["results"][0]
    assert first["endpoint_id"] == endpoint and first["endpoint_url"] == local.as_uri()
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        before = [
            db.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in ["git_objects", "contents", "content_digests"]
        ]
    source = run(
        state,
        "sources",
        "add",
        "git-url",
        "--name",
        "network-view",
        "--url",
        network,
        "--repo",
        repo,
    )["data"]["source_id"]
    discovered = run(state, "discover", "--source", source)["data"]["repositories"]
    assert discovered[0]["repo_id"] == repo
    assert [r["id"] for r in pages(state, "repos", "list", "--source", source)] == [
        repo
    ]
    eps = pages(state, "endpoints", "list", "--repo", repo)
    net = next(e for e in eps if e["url"] == network.as_uri())
    run(state, "endpoints", "prefer", "--repo", repo, "--endpoint", net["id"])
    local.unlink()
    second = run(state, "sync", "git", "--source", source)["data"]["results"][0]
    assert second["endpoint_id"] == net["id"] and second["repo_id"] == repo
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        after = [
            db.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in ["git_objects", "contents", "content_digests"]
        ]
        assert after == before
        assert (
            db.execute(
                "SELECT count(*) FROM source_repositories WHERE repo_id=?", (repo,)
            ).fetchone()[0]
            == 2
        )
    assert len(pages(state, "repos", "list")) == 3
    assert (
        run(state, "repos", "show", "--repo", repo)["data"]["items"][0]["url"]
        == network.as_uri()
    )
    run(state, "db", "check", "--full")
    # An identical URL in a separate registration is not proof of identity.
    unrelated = run(
        state,
        "sources",
        "add",
        "git-url",
        "--name",
        "unrelated-registration",
        "--url",
        network,
    )["data"]["source_id"]
    other = run(state, "discover", "--source", unrelated)["data"]["repositories"][0][
        "repo_id"
    ]
    assert other != repo


def test_github_instances_and_sources_keep_api_identity_separate(catalog):
    state, fixture, _ = catalog
    with GitHubFixture(fixture) as api_a, GitHubFixture(fixture) as api_b:
        registered = []
        for name, api, token_env in (
            ("gh-a", api_a, "FIXTURE_A_TOKEN"),
            ("gh-b", api_b, "FIXTURE_B_TOKEN"),
        ):
            run(
                state,
                "instances",
                "add",
                "github",
                "--name",
                name,
                "--web-base-url",
                api.url,
                "--api-base-url",
                api.url,
            )
            source = run(
                state,
                "sources",
                "add",
                "github",
                "--owner",
                "fixture",
                "--instance",
                name,
                "--token-env-var",
                token_env,
                "--clone-url-override",
                "101=" + fixture.alpha.url,
            )["data"]["source_id"]
            env = {token_env: "fixture-dummy"}
            repo = run(state, "discover", "--source", source, env=env)["data"][
                "repositories"
            ][0]["repo_id"]
            registered.append((repo, source))
            run(state, "sync", "pr", "--source", source, env=env)
        a, b = registered[0][0], registered[1][0]
        assert a != b
        run(state, "repos", "show", "--repo", "fixture/alpha", expected=2)
        assert (
            run(state, "repos", "show", "--repo", "gh-a/fixture/alpha")["data"][
                "items"
            ][0]["id"]
            == a
        )
        # A second API source uses its own token reference but the same Repo ID.
        second = run(
            state,
            "sources",
            "add",
            "github",
            "--owner",
            "fixture",
            "--instance",
            "gh-a",
            "--token-env-var",
            "FIXTURE_SECOND_TOKEN",
            "--clone-url-override",
            "101=" + fixture.alpha.url,
        )["data"]["source_id"]
        env = {"FIXTURE_SECOND_TOKEN": "fixture-dummy"}
        assert (
            run(state, "discover", "--source", second, env=env)["data"]["repositories"][
                0
            ]["repo_id"]
            == a
        )
        run(state, "sync", "pr", "--source", second, env=env)
        assert not api_a.errors and not api_b.errors
        # Multiple service bindings can share Git identity, but PR numbers
        # require a separate namespace model before collecting both services.
        run(
            state,
            "repos",
            "bind",
            "--repo",
            a,
            "--instance",
            "gh-b",
            "--provider-repo-id",
            "102",
        )
        request_count = len(api_a.requests) + len(api_b.requests)
        unsupported = run(
            state, "sync", "pr", "--repo", a, "--source", second, env=env, expected=3
        )
        assert unsupported["data"]["results"][0]["error"] == "PROVIDER_UNSUPPORTED"
        assert len(api_a.requests) + len(api_b.requests) == request_count
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM review_threads").fetchone()[0] == 6
        assert (
            db.execute(
                "SELECT count(*) FROM review_comments c JOIN pr_documents d ON d.id=c.document_id JOIN review_threads t ON t.id=c.thread_id WHERE d.pr_id!=t.pr_id"
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT count(*) FROM source_repositories WHERE repo_id=?", (a,)
            ).fetchone()[0]
            == 2
        )
        assert (
            db.execute(
                "SELECT count(*) FROM repository_bindings WHERE provider_repo_id='101'"
            ).fetchone()[0]
            == 2
        )
    run(state, "db", "check", "--full")


def test_instance_scoped_native_ids_and_conflicts(catalog):
    state, fixture, repos = catalog
    a = run(
        state,
        "instances",
        "add",
        "gitlab",
        "--name",
        "gl-a",
        "--web-base-url",
        "https://code.example.net:8443",
        "--api-base-url",
        "https://code.example.net:8443/api/v4",
    )["data"]["instance_id"]
    b = run(
        state,
        "instances",
        "add",
        "gitlab",
        "--name",
        "gl-b",
        "--web-base-url",
        "https://code.example.net:9443",
        "--api-base-url",
        "https://code.example.net:9443/api/v4",
    )["data"]["instance_id"]
    assert uuid.UUID(a).version == uuid.UUID(b).version == 4
    run(
        state,
        "repos",
        "bind",
        "--repo",
        repos["alpha"],
        "--instance",
        a,
        "--provider-repo-id",
        "42",
    )
    run(
        state,
        "repos",
        "bind",
        "--repo",
        repos["beta"],
        "--instance",
        b,
        "--provider-repo-id",
        "42",
    )
    assert (
        run(state, "repos", "show", "--repo", "gl-a/alpha")["data"]["items"][0]["id"]
        == repos["alpha"]
    )
    assert (
        run(
            state,
            "repos",
            "bind",
            "--repo",
            repos["beta"],
            "--instance",
            a,
            "--provider-repo-id",
            "42",
            expected=4,
        )["error"]["code"]
        == "IDENTITY_CONFLICT"
    )
    assert len(pages(state, "instances", "list")) == 2
    assert run(state, "instances", "show", "--instance", "gl-b")["data"]["items"][0][
        "api_base_url"
    ].endswith(":9443/api/v4")
    source = run(
        state,
        "sources",
        "add",
        "git-url",
        "--name",
        "native-identity-view",
        "--url",
        fixture.alpha.url,
        "--instance",
        "gl-a",
        "--provider-repo-id",
        "42",
    )["data"]["source_id"]
    assert (
        run(state, "discover", "--source", source)["data"]["repositories"][0]["repo_id"]
        == repos["alpha"]
    )
    # GitLab metadata does not imply its API adapter is implemented.
    result = run(state, "sync", "pr", "--repo", repos["alpha"], expected=3)
    assert result["data"]["results"][0]["error"] == "PROVIDER_UNSUPPORTED"
    bad = run(
        state,
        "sources",
        "add",
        "git-url",
        "--name",
        "conflicting-view",
        "--url",
        fixture.beta.url,
        "--repo",
        repos["beta"],
        "--instance",
        "gl-a",
        "--provider-repo-id",
        "42",
    )["data"]["source_id"]
    assert (
        run(state, "discover", "--source", bad, expected=3)["coverage"]["missing"][0][
            "reason"
        ]
        == "IDENTITY_CONFLICT"
    )


def test_endpoint_scope_and_resume_keep_original_url(catalog, tmp_path):
    state, fixture, repos = catalog
    alt = tmp_path / "alternative.git"
    alt.symlink_to(fixture.alpha.path, target_is_directory=True)
    ep = run(state, "endpoints", "add", "--repo", repos["alpha"], "--url", alt)["data"][
        "endpoint_id"
    ]
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM collection_runs").fetchone()[0] == 0
    assert (
        run(
            state, "sync", "git", "--repo", repos["beta"], "--endpoint", ep, expected=3
        )["data"]["results"][0]["error"]
        == "NOT_FOUND"
    )
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM collection_runs").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM cache_entries").fetchone()[0] == 0
    run(state, "sync", "git", "--endpoint", ep, expected=2)
    p, hooks = start_hooked(
        state,
        "before_publish",
        tmp_path,
        "sync",
        "git",
        "--repo",
        repos["alpha"],
        "--endpoint",
        ep,
    )
    p.kill()
    p.communicate(timeout=10)
    job = interrupted_job(state)
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        original = db.execute(
            "SELECT id FROM repository_endpoints WHERE repo_id=? AND is_preferred=1",
            (repos["alpha"],),
        ).fetchone()[0]
    run(state, "endpoints", "prefer", "--repo", repos["alpha"], "--endpoint", original)
    resumed = run(state, "jobs", "resume", job)["data"]["results"][0]
    assert resumed["endpoint_id"] == ep and resumed["endpoint_url"] == alt.as_uri()
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        assert db.execute(
            "SELECT endpoint_id,endpoint_url FROM collection_runs WHERE job_id=?",
            (job,),
        ).fetchone() == (ep, alt.as_uri())
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "UPDATE collection_runs SET repo_id=? WHERE job_id=?",
                (repos["beta"], job),
            )
    run(state, "db", "check", "--full")
