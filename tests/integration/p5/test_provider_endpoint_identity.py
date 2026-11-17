"""Injected endpoints are local execution inputs; Service UUIDs own facts."""

import json
from uuid import uuid4

import httpx

from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.application.provider_acquisition import ProviderAcquisition
from repo_catalog.application.provider_fetch import acquire_github
from repo_catalog.domain.context_admission import (
    AdmissionSelection,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.exchange import ExchangeSelectionScope, encode_package
from repo_catalog.domain.p1_context import ResourceKey, canonical
from repo_catalog.domain.provider_acquisition import (
    ProviderIntakeBatch,
    ProviderRegistration,
    SourceRegistration,
)
from tests.integration.p5.conftest import init_catalog_stores


class Endpoints:
    def __init__(self, path):
        self.path = path
        init_catalog_stores(path, stores=("context", "operational"))
        self.services = [str(uuid4()), str(uuid4())]
        self.sources = [str(uuid4()), str(uuid4())]
        self.grants = DependencySet(
            resources={
                ResourceKey.from_native(service, kind, str(native))
                for service in self.services
                for kind, native in (("repository", 10), ("issue", 20))
            },
            sources=set(self.sources),
            provider_registrations=set(self.services),
        )
        self.auth, self.admission, _ = create_local_admission_service(
            "provider_intake",
            grants=self.grants,
            selection=AdmissionSelection(all_selected=True),
        )
        self.api = ProviderAcquisition(
            path, authorization=self.auth, admission=self.admission
        )
        for service, source in zip(self.services, self.sources, strict=True):
            self.api.admit_batch(
                ProviderIntakeBatch(
                    service,
                    providers=(
                        ProviderRegistration(
                            service,
                            configuration_json=canonical(
                                {
                                    "name": "duplicate",
                                    "description": "authored provider",
                                }
                            ),
                        ),
                    ),
                    sources=(
                        SourceRegistration(
                            source,
                            service,
                            configuration_json=canonical(
                                {
                                    "name": "source name",
                                    "description": "authored source",
                                }
                            ),
                        ),
                    ),
                )
            )

    def document(self, index, *, base=None):
        result = {
            "operation": "sync",
            "service_instance_uuidv4": self.services[index],
            "source_registration_uuidv4": self.sources[index],
            "request_identity": [str(uuid4()), str(uuid4())],
            "new_request": True,
            "owner": "owner",
            "repository": "repo",
            "sections": ["issues"],
            "token_env_var": "RESOURCE_ATLAS_TEST_UNUSED_TOKEN",
        }
        if base is not None:
            result.update(
                rest_base_url=base + "/api/v3", graphql_url=base + "/api/graphql"
            )
        return result

    def acquire(self, document, client):
        result = acquire_github(
            self.path,
            document,
            authorization=self.auth,
            admission=self.admission,
            client=client,
        )
        assert result.status == "complete"
        return result


def response(request):
    payload = (
        {"id": 10, "full_name": "owner/repo"}
        if request.url.path.endswith("/repos/owner/repo")
        else [{"id": 20, "number": 1, "state": "open"}]
    )
    return httpx.Response(200, json=payload, request=request)


def test_duplicate_display_names_and_explicit_rename_do_not_change_injected_service_routes_or_fact_owners(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("RESOURCE_ATLAS_TEST_UNUSED_TOKEN", raising=False)
    fixture = Endpoints(tmp_path)
    documents = [
        fixture.document(index, base="https://" + host + ".example")
        for index, host in enumerate(("alpha", "beta"))
    ]
    calls = []

    def handle(request):
        calls.append((request.url.host, request.url.path))
        return response(request)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        for document in documents:
            fixture.acquire(document, client)
        fixture.api.admit_batch(
            ProviderIntakeBatch(
                fixture.services[0],
                providers=(
                    ProviderRegistration(
                        fixture.services[0],
                        configuration_json=canonical(
                            {"name": "renamed", "description": "retained rename"}
                        ),
                    ),
                ),
            )
        )
        documents[0]["new_request"] = False
        fixture.acquire(documents[0], client)
    assert [host for host, _ in calls] == [
        "alpha.example",
        "alpha.example",
        "beta.example",
        "beta.example",
        "alpha.example",
        "alpha.example",
    ]
    assert all(path.startswith("/api/v3/") for _, path in calls)
    with Context.snapshot(tmp_path) as context:
        providers = {
            row[0]: json.loads(row[1])
            for row in context.db.execute(
                "SELECT service_instance_uuidv4,configuration_json FROM providers"
            )
        }
        assert providers[fixture.services[0]] == {
            "name": "renamed",
            "description": "retained rename",
        }
        assert providers[fixture.services[1]] == {
            "name": "duplicate",
            "description": "authored provider",
        }
        assert all(
            json.loads(row[0])
            == {"name": "source name", "description": "authored source"}
            for row in context.db.execute("SELECT configuration_json FROM sources")
        )
        for service in fixture.services:
            assert (
                context.identification(
                    ResourceKey.from_native(service, "issue", "20")
                ).resource.service_instance_uuidv4
                == service
            )


def test_endpoint_override_and_credential_reference_are_per_request_never_context_or_exchange_defaults(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("RESOURCE_ATLAS_TEST_UNUSED_TOKEN", raising=False)
    fixture = Endpoints(tmp_path)
    original = fixture.document(0, base="https://alpha.example")
    original["token_env_var"] = "SYNTHETIC_ROUTE_TOKEN"
    monkeypatch.setenv("SYNTHETIC_ROUTE_TOKEN", "synthetic-secret-value")
    override = fixture.document(0, base="https://mirror.example")
    calls = []

    def handle(request):
        calls.append((request.url.host, request.headers.get("authorization")))
        return response(request)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        fixture.acquire(original, client)
        fixture.acquire(override, client)
        original["new_request"] = False
        fixture.acquire(original, client)
    assert [host for host, _ in calls] == [
        "alpha.example",
        "alpha.example",
        "mirror.example",
        "mirror.example",
        "alpha.example",
        "alpha.example",
    ]
    assert all(secret is None for host, secret in calls if host == "mirror.example")
    assert all(
        secret == "Bearer synthetic-secret-value"
        for host, secret in calls
        if host == "alpha.example"
    )
    package = ExchangeService(tmp_path).export_package(
        selection=ExchangeSelectionScope(all_selected=True, include_core=False)
    )
    encoded = encode_package(package)
    stored = (tmp_path / "context.sqlite3").read_bytes()
    for marker in (
        "alpha.example",
        "mirror.example",
        "SYNTHETIC_ROUTE_TOKEN",
        "synthetic-secret-value",
    ):
        assert marker not in encoded and marker.encode() not in stored


def test_public_github_profile_defaults_are_independent_from_registry_display_names_and_prior_overrides(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("RESOURCE_ATLAS_TEST_UNUSED_TOKEN", raising=False)
    fixture = Endpoints(tmp_path)
    explicit = fixture.document(0, base="https://enterprise.example")
    public = fixture.document(1)
    calls = []

    def handle(request):
        calls.append(request.url.host)
        return response(request)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        fixture.acquire(explicit, client)
        fixture.acquire(public, client)
    assert calls == [
        "enterprise.example",
        "enterprise.example",
        "api.github.com",
        "api.github.com",
    ]
    assert "rest_base_url" not in public and "graphql_url" not in public


def test_same_native_pull_request_number_under_two_services_never_merges_owners(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("RESOURCE_ATLAS_TEST_UNUSED_TOKEN", raising=False)
    fixture = Endpoints(tmp_path)
    parents = [
        ResourceKey.from_native(service, "pull_request", "20")
        for service in fixture.services
    ]
    grants = DependencySet(
        resources=fixture.grants.resources | set(parents),
        sources=fixture.grants.sources,
        provider_registrations=fixture.grants.provider_registrations,
    )
    fixture.auth, fixture.admission, _ = create_local_admission_service(
        "provider_intake",
        grants=grants,
        selection=AdmissionSelection(all_selected=True),
    )

    def handle(request):
        if request.url.path.endswith("/repos/owner/repo"):
            value = {"id": 10, "full_name": "owner/repo"}
        elif request.url.path.endswith("/pulls"):
            value = [{"id": 20, "number": 1}]
        else:
            value = {"id": 20, "number": 1, "state": "open"}
        return httpx.Response(200, request=request, json=value)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        for index, host in enumerate(("alpha", "beta")):
            document = fixture.document(index, base="https://" + host + ".example")
            document["sections"] = ["pull_requests"]
            fixture.acquire(document, client)
    views = [
        ProductionQueryService(tmp_path).get_context_resource(parent)
        for parent in parents
    ]
    assert [view.resource.service_instance_uuidv4 for view in views] == fixture.services
    assert [json.loads(view.fields["number"][0].value_json) for view in views] == [1, 1]
    assert parents[0] != parents[1]
    with Context.snapshot(tmp_path) as context:
        assert (
            context.db.execute(
                "SELECT count(*) FROM resources WHERE resource_kind='pull_request'"
            ).fetchone()[0]
            == 2
        )
