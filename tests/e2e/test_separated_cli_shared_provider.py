"""Trusted Source composition shares genuine durable work without child budgets."""

import json
from uuid import uuid4

import httpx
import pytest

from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.application.provider_fetch import acquire_github_with_budget
from repo_catalog.cli.separated_io import authority
from repo_catalog.domain.context_admission import AdmissionSelection, DependencySet
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.p1_coordination import RequestIdentity
from tests.e2e.test_separated_cli import document, init, run
from tests.e2e.test_separated_cli_provider_regressions import _http_response
from tests.e2e.test_separated_cli_provider_regressions import (
    provider_case as provider_case,
)


def test_shared_parent_source_namespaces_and_same_attempt_retries_never_reset_http_budget(
    provider_case, tmp_path, capsys
):
    case = provider_case
    second_source = str(uuid4())
    grants = document(
        tmp_path,
        "parent-authority.json",
        {
            "grants": DependencySet(
                resources=frozenset(case.keys.values()),
                sources=frozenset({case.source, second_source}),
                provider_registrations=frozenset({case.service}),
            ),
            "selection": AdmissionSelection(all_selected=True),
        },
    )
    auth, admission, _ = authority(grants, "provider_intake")
    init(capsys, case.directory, "operational")
    parent = RequestIdentity(str(uuid4()), str(uuid4()))
    calls = []

    def handle(http):
        calls.append(http.url.path)
        return _http_response(
            http,
            {"login": "owner"}
            if http.url.path == "/user"
            else {"id": 10, "full_name": "owner/repo", "private": True},
        )

    def value(source):
        return {
            "operation": "discover",
            "service_instance_uuidv4": case.service,
            "source_registration_uuidv4": source,
            "request_identity": list(parent.values()),
            "new_request": False,
            "owner": "owner",
            "include_repositories": ["repo"],
            "max_pages": 3,
            "response_bytes": 8192,
            "rest_base_url": "https://api.example.test",
            "graphql_url": "https://api.example.test/graphql",
        }

    with OperationalAcquisitionLedger(case.directory) as ledger:
        _, attempt, work, progress = ledger.create_budget(
            scope=["explicit-multi-source-parent", str(uuid4())],
            request=parent,
            new_request=True,
        )
        before = ledger.work_ledger.usage(parent)
        with httpx.Client(transport=httpx.MockTransport(handle)) as client:

            def execute(source):
                return acquire_github_with_budget(
                    case.directory,
                    value(source),
                    authorization=auth,
                    admission=admission,
                    work=work,
                    progress=progress,
                    ledger=ledger,
                    client=client,
                    clock_us=lambda: 1_000_000,
                )

            first = execute(case.source)
            middle = ledger.work_ledger.usage(parent)
            second = execute(second_source)
            after_second = ledger.work_ledger.usage(parent)
            third = execute(case.source)
        assert first.status == second.status == "complete"
        assert third.status == "partial" and third.failure_code == "PAGE_LIMIT"
        assert (
            first.http_attempts == second.http_attempts == 2
            and third.http_attempts == 1
        )
        assert len(calls) == 5
        assert all(
            report.request_identity == parent for report in (first, second, third)
        )
        assert work.attempt_uuidv4 == attempt
        after = ledger.work_ledger.usage(parent)
        assert (
            before["input_bytes"]
            < middle["input_bytes"]
            < after_second["input_bytes"]
            < after["input_bytes"]
        )
        assert (
            after["input_bytes"]
            >= first.network_bytes + second.network_bytes + third.network_bytes
        )
        observations = [
            observation
            for report in (first, second, third)
            for batch in report.batches
            for _, observation in batch.source_inventory_proofs
        ]
        evidence = [
            json.loads(observation.provenance_json)["evidence"]
            for observation in observations
        ]
        reads = {
            original["http_attempt_uuidv4"]
            for item in evidence
            for original in item["terminal_report"]["read_origins"]
        }
        assert len(reads) == 5
        assert len({item["traversal_attempt_uuidv4"] for item in evidence}) == 3
        changed = value(case.source)
        changed["owner"] = "different"
        with pytest.raises(CatalogError) as error:
            acquire_github_with_budget(
                case.directory,
                changed,
                authorization=auth,
                admission=admission,
                work=work,
                progress=progress,
                ledger=ledger,
            )
        assert error.value.code == "INCOMPATIBLE_REPLAY"
    listed = run(capsys, "operations", "list", "--catalog", case.directory)
    assert len(listed["requests"]) == 1
    assert listed["requests"][0]["request_uuidv4"] == parent.request_uuidv4
    assert not (case.directory / "repository.sqlite3").exists()
