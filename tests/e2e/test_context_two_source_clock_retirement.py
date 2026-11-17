"""Earlier Source A reads cannot borrow later Source B original evidence."""

import json
from uuid import uuid4

import httpx

from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.context_query import ContextQueryService
from repo_catalog.domain.context_admission import AdmissionSelection, DependencySet
from repo_catalog.domain.p1_context import CoverageScope
from tests.e2e.test_context_response_boundary_retirement import request_document
from tests.e2e.test_separated_cli import document
from tests.e2e.test_separated_cli_provider_regressions import (
    _http_response,
    _network_cli,
)
from tests.e2e.test_separated_cli_provider_regressions import (
    provider_case as provider_case,
)


def test_same_service_source_b_900_then_a_100_keeps_actual_independent_scopes_and_producers(
    provider_case, tmp_path, capsys, monkeypatch
):
    case, source_b = provider_case, str(uuid4())
    source_a = case.source
    case.authority = document(
        tmp_path,
        "two-source-authority.json",
        {
            "grants": DependencySet(
                resources=frozenset(case.keys.values()),
                sources={source_a, source_b},
                provider_registrations={case.service},
            ),
            "selection": AdmissionSelection(all_selected=True),
        },
    )
    active, stamp, received = [source_b], [900], []
    text = "same exact\x00issue body\r\n"

    def handle(http):
        received.append((active[0], stamp[0], http.url.path))
        if http.url.path == "/user":
            value = {"login": "owner", "public_repos": 0, "owned_private_repos": 1}
        elif http.url.path == "/user/repos":
            value = [
                {"id": 10, "full_name": "owner/repo", "private": True, "updated_at": 10}
            ]
        elif http.url.path == "/repos/owner/repo":
            value = {
                "id": 10,
                "full_name": "owner/repo",
                "private": True,
                "updated_at": 10,
            }
        else:
            assert http.url.path == "/repos/owner/repo/issues"
            value = [
                {
                    "id": 100,
                    "number": 1,
                    "title": "same issue",
                    "body": text,
                    "updated_at": 10,
                }
            ]
        return _http_response(http, value)

    query = ContextQueryService(case.directory, mode="context_only")
    snapshots = {}
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        for source_id, observed in ((source_b, 900), (source_a, 100)):
            active[0], stamp[0] = source_id, observed
            discover = {
                "operation": "discover",
                "service_instance_uuidv4": case.service,
                "source_registration_uuidv4": source_id,
                "request_identity": [str(uuid4()), str(uuid4())],
                "new_request": True,
                "owner": "owner",
                "rest_base_url": "https://api.example.test",
                "graphql_url": "https://api.example.test/graphql",
            }
            inventory_report, _ = _network_cli(
                case,
                tmp_path,
                capsys,
                monkeypatch,
                client,
                discover,
                clock_us=lambda: stamp[0],
            )
            request = request_document(case)
            request.update(source_registration_uuidv4=source_id, sections=["issues"])
            issue_report, _ = _network_cli(
                case,
                tmp_path,
                capsys,
                monkeypatch,
                client,
                request,
                clock_us=lambda: stamp[0],
            )
            assert inventory_report["status"] == issue_report["status"] == "complete"
            sources = {
                item.source_registration_uuidv4: item
                for item in query.list_source_views(case.service)
            }
            source = sources[source_id]
            assert source.service_instance_uuidv4 == case.service
            (inventory,) = source.inventories
            assert inventory.terminal and inventory.state == "complete"
            assert inventory.observed_at_us == observed
            assert inventory.provider_repositories == (case.keys["repository"],)
            inventory_scope = json.loads(inventory.scope_json)
            assert inventory_scope["source_registration_uuidv4"] == source_id
            assert inventory_scope["service_instance_uuidv4"] == case.service
            inventory_coverage = query.get_context_coverage(
                CoverageScope.source_inventory(
                    source_id, inventory.scope_json, "provider_repositories"
                )
            )
            assert inventory_coverage.state == "complete"
            assert inventory_coverage.latest_observed_at_us == observed
            assert {claim.observed_at_us for claim in inventory_coverage.claims} == {
                observed
            }
            repository = query.get_context_resource(case.keys["repository"])
            (collection,) = (
                item
                for item in repository.collections
                if item.collection_kind == "issues"
                and json.loads(item.scope_json)["source_registration_uuidv4"]
                == source_id
            )
            assert (
                collection.state == "complete" and collection.observed_at_us == observed
            )
            assert collection.members == (case.keys["issue"],)
            original = json.loads(collection.provenance_json)["evidence"]
            assert original["source_registration_uuidv4"] == source_id
            assert original["service_instance_uuidv4"] == case.service
            assert original["resource_path"] == "/repos/owner/repo/issues"
            collection_coverage = query.get_context_coverage(
                CoverageScope.collection(
                    case.keys["repository"],
                    "issues",
                    collection.provenance_json,
                    "issues",
                )
            )
            assert collection_coverage.state == "complete"
            assert collection_coverage.latest_observed_at_us == observed
            assert {claim.observed_at_us for claim in collection_coverage.claims} == {
                observed
            }
            snapshots[source_id] = (
                source,
                inventory_coverage,
                collection,
                collection_coverage,
            )
            if source_id == source_a:
                assert sources[source_b] == snapshots[source_b][0]
                assert snapshots[source_b][2] in repository.collections
                assert (
                    query.get_context_coverage(snapshots[source_b][1].scope)
                    == snapshots[source_b][1]
                )
                assert (
                    query.get_context_coverage(snapshots[source_b][3].scope)
                    == snapshots[source_b][3]
                )
    assert received == [
        (source_id, observed, path)
        for source_id, observed in ((source_b, 900), (source_a, 100))
        for path in (
            "/user",
            "/user/repos",
            "/repos/owner/repo",
            "/repos/owner/repo/issues",
        )
    ]
    with Context.snapshot(case.directory) as context:
        candidates = context.candidates(case.keys["issue"], "text_body_sha256")
        assert len(candidates) == 2
        assert {
            (
                json.loads(item.provenance_json)["evidence"][
                    "source_registration_uuidv4"
                ],
                item.observed_at_us,
            )
            for item in candidates
        } == {(source_b, 900), (source_a, 100)}
        # These are the actual unchanged Provider clocks, not either receiver's
        # later/earlier observation time copied onto an original field.
        assert {item.clock.at_us for item in candidates} == {10}
        assert {
            context.read_text(json.loads(item.value_json)) for item in candidates
        } == {text}
    aggregate = query.get_context_coverage(
        CoverageScope.resource(case.keys["repository"], "issues")
    )
    assert aggregate.state == "unknown" and aggregate.claims == ()
    assert aggregate.latest_observed_at_us is None
    assert not (case.directory / "core.sqlite3").exists()
    assert not (case.directory / "p1-recovery-stop.json").exists()
