"""Shared disposable catalog and local HTTP acquisition helpers."""

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
                    "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,web_base_url,api_base_url,metadata,created_at_us) VALUES('00000000-0000-4000-8000-000000000101','github','fixture',?,?, '{}',NULL)",
                    (api.url, api.url),
                )
                store.execute(
                    "INSERT INTO sources(source_id,source_registration_uuidv4,service_instance_uuidv4,discovery_kind,name,settings) VALUES('source','00000000-0000-4000-8000-000000000201','00000000-0000-4000-8000-000000000101','github_inventory','fixture',?)",
                    (json.dumps({"owner": "fixture"}),),
                )
                store.execute(
                    "INSERT INTO repositories(repository_uuidv4,name,preferred_repository_endpoint_id,current_snapshot_id,metadata) VALUES('repo','fixture/alpha','endpoint',NULL,'{}')"
                )
                store.execute(
                    "INSERT INTO repository_endpoints(repository_endpoint_id,repository_uuidv4,url,transport,label,metadata,created_at_us) VALUES('endpoint','repo',?,'file',NULL,'{}',NULL)",
                    (fixture.alpha.url,),
                )
                store.execute(
                    "INSERT INTO repository_bindings(repository_binding_id,repository_uuidv4,service_instance_uuidv4,provider_repository_id,metadata,created_at_us) VALUES('binding','repo','00000000-0000-4000-8000-000000000101','101','{}',NULL)"
                )
                store.execute(
                    "INSERT INTO source_repositories(source_id,repository_uuidv4,first_seen_us,last_seen_us) VALUES('source','repo',NULL,NULL)"
                )
            repo = {
                "repository_uuidv4": "repo",
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
            "sync", {"kind": "pr", "repositories": [repo["repository_uuidv4"]]}
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
