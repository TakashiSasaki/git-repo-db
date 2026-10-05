from tests.e2e.test_github_sync import configure
from tests.support.cli import run
from tests.support.github_fixture import GitHubFixture


def test_compressed_api_response(catalog):
    state, fixture, repos = catalog
    with GitHubFixture(fixture) as api:
        api.gzip = True
        _, repo, env = configure(state, api, fixture)
        result = run(state, "sync", "pr", "--repo", repo, env=env)
        assert result["data"]["results"][0]["state"] == "complete"
