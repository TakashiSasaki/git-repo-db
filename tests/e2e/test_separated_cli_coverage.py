"""Ordinary CLI renders qualified Coverage originals without a silent winner."""

import json

from repo_catalog.domain.p1_context import CoverageClaim, CoverageScope, canonical
from tests.e2e.test_separated_cli import document, run
from tests.e2e.test_separated_cli_provider_regressions import issue
from tests.e2e.test_separated_cli_provider_regressions import (
    provider_case as provider_case,
)


def test_cli_coverage_renders_conflicting_original_claims_and_newer_unknown(
    provider_case, tmp_path, capsys
):
    case = provider_case
    case.admit(tmp_path, capsys, issues=(issue({"id": 100}), issue({"id": 101})))
    first = CoverageScope.resource(case.keys["issue"], "review-documents")
    other = CoverageScope.resource(case.keys["other_issue"], "review-documents")

    def invoke(scope):
        payload = document(tmp_path, "coverage-query.json", {"args": [scope]})
        return run(
            capsys,
            "query",
            "context-coverage",
            "--catalog",
            case.directory,
            "--input",
            payload,
        )

    def append(scope, stamp, state, details):
        payload = document(tmp_path, "coverage-scope.json", {"args": [scope]})
        run(
            capsys,
            "context",
            "scope",
            "--catalog",
            case.directory,
            "--authority",
            case.authority,
            "--input",
            payload,
        )
        payload = document(
            tmp_path,
            "coverage-claim.json",
            {"args": [CoverageClaim(scope, stamp, state, canonical(details))]},
        )
        run(
            capsys,
            "context",
            "coverage",
            "--catalog",
            case.directory,
            "--authority",
            case.authority,
            "--input",
            payload,
        )

    empty = invoke(first)
    assert empty["state"] == "unknown" and empty["latest_observed_at_us"] is None
    assert empty["claims"] == [] and not empty["known_empty"]
    append(first, 10, "partial", {"reason": "missing children", "advisory": "first"})
    append(
        first,
        10,
        "not_applicable",
        {"reason": "reported different applicability", "advisory": "second"},
    )
    conflict = invoke(first)
    assert conflict["state"] == "conflict" and conflict["latest_observed_at_us"] == 10
    assert {item["state"] for item in conflict["claims"]} == {
        "partial",
        "not_applicable",
    }
    assert {item["observed_at_us"] for item in conflict["claims"]} == {10}
    assert {
        canonical(json.loads(item["details_json"])) for item in conflict["claims"]
    } == {
        canonical({"reason": "missing children", "advisory": "first"}),
        canonical({"reason": "reported different applicability", "advisory": "second"}),
    }
    assert all(
        item["scope"]["coordinates"] == list(first.coordinates)
        for item in conflict["claims"]
    )
    assert invoke(other)["claims"] == []  # Full ResourceKey owner remains separate.
    append(other, 30, "partial", {"advisory": "other owner"})
    assert invoke(first) == conflict
    append(first, 20, "unknown", {"reason": "new original uncertainty"})
    latest = invoke(first)
    assert latest["state"] == "unknown" and latest["latest_observed_at_us"] == 20
    assert len(latest["claims"]) == 1 and latest["claims"][0]["state"] == "unknown"
    assert latest["claims"][0]["details_json"] == canonical(
        {"reason": "new original uncertainty"}
    )
    assert invoke(other)["latest_observed_at_us"] == 30
    assert not (case.directory / "core.sqlite3").exists()
