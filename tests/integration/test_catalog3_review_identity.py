"""Selected service registrations, not their display names, own API routing."""

import json

import pytest

from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application import repository_identity as identity
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.domain.models import CatalogError


@pytest.fixture
def store(tmp_path):
    state = tmp_path / "state"
    MaintenanceService(state).init("catalog-text-v1", 32 * 1024 * 1024, 0)
    with Store(state) as value:
        yield value


def source(service, **overrides):
    return {
        "service_instance_uuidv4": service,
        "discovery_kind": "github_inventory",
        "settings": json.dumps({"owner": "fixture", "api_settings": overrides}),
    }


def routes(store, src):
    config = identity.github_config(store, src)
    return config["rest_base_url"], config["graphql_url"]


def test_explicit_service_uuid_keeps_its_endpoints_with_duplicate_names_and_rename(
    store,
):
    services = [
        identity.add_instance(
            store, "github", "github.com", f"https://{host}.example", api
        )
        for host, api in (("first", "https://first.example/api/v3"), ("second", None))
    ]
    for host, service in zip(("first", "second"), services, strict=True):
        expected = (
            f"https://{host}.example/api/v3",
            f"https://{host}.example/api/graphql",
        )
        assert routes(store, source(service)) == expected
        store.execute(
            "UPDATE service_instances SET name='renamed' WHERE service_instance_uuidv4=?",
            (service,),
        )
        assert routes(store, source(service)) == expected


def test_source_endpoint_overrides_are_explicit_and_service_local(store):
    service = identity.add_instance(
        store, "github", "github.com", "https://enterprise.example"
    )
    overrides = {
        "rest_base_url": "http://127.0.0.1:8100/rest",
        "graphql_url": "http://127.0.0.1:8200/query",
        "token_env_var": "SYNTHETIC_TOKEN",
    }
    config = identity.github_config(store, source(service, **overrides))
    assert all(config[key] == value for key, value in overrides.items())
    assert routes(store, source(service)) == (
        "https://enterprise.example/api/v3",
        "https://enterprise.example/api/graphql",
    )


def test_configured_default_routes_are_captured_in_the_service_registration(store):
    expected = ("http://127.0.0.1:8100/rest", "http://127.0.0.1:8200/query")
    store.config["github"].update(rest_base_url=expected[0], graphql_url=expected[1])
    service = identity.default_github_instance(store)
    assert routes(store, source(service)) == expected
    store.execute("UPDATE service_instances SET name='renamed default'")
    store.config["github"].update(
        rest_base_url="https://another.example/rest",
        graphql_url="https://another.example/query",
    )
    assert routes(store, source(service)) == expected


def test_public_github_web_registration_uses_public_api_regardless_of_name(store):
    service = identity.add_instance(store, "github", "renamed", "https://github.com/")
    assert routes(store, source(service)) == (
        "https://api.github.com",
        "https://api.github.com/graphql",
    )


def test_service_name_alone_never_inherits_global_endpoints(store):
    service = identity.add_instance(store, "github", "github.com")
    with pytest.raises(CatalogError, match="instance base URL"):
        routes(store, source(service))
