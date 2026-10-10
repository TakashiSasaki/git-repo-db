"""Current coverage reaches offline CLI projections without historical fallback."""

import sqlite3

import pytest

from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.query_service import QueryService
from repo_catalog.application.repository_identity import add_instance, bind
from repo_catalog.domain.models import CatalogError
from tests.integration.test_catalog3_pr_scope_coverage import (
    add_complete_code,
    add_document,
    add_fact,
    admit_pr_state,
)
from tests.integration.test_catalog3_pr_scope_coverage import (
    pr_catalog as pr_catalog,
)
from tests.support.cli import run


@pytest.fixture
def coverage_catalog(tmp_path):
    """A saved synthetic repository, snapshot and PR; no acquisition is needed."""
    state = tmp_path / "catalog"
    MaintenanceService(state).init("catalog-text-v1", 67_108_864, 0)
    with Store(state) as store:
        with store.transaction():
            namespace = add_instance(store, "github", "synthetic")
            store.execute(
                "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES('00000000-0000-4000-8000-000000000401','synthetic/repo','{}')"
            )
            bind(store, "00000000-0000-4000-8000-000000000401", namespace, "1")
            binding = store.one(
                "SELECT repository_binding_id FROM repository_bindings WHERE repository_uuidv4='00000000-0000-4000-8000-000000000401'"
            )[0]
            store.execute(
                "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,object_format,refs_observed_at_us,kind,observed_at_us,request,roots_manifest) VALUES('acquisition','00000000-0000-4000-8000-000000000401','sha1',0,'git',0,'{}','[]')"
            )
            add_fact(
                store,
                "snapshots",
                snapshot_id="snapshot",
                git_acquisition_id="acquisition",
                repository_uuidv4="00000000-0000-4000-8000-000000000401",
                complete=0,
                generation=1,
                created_at_us=0,
            )
            store.execute(
                "UPDATE snapshots SET complete=1 WHERE snapshot_id='snapshot'"
            )
            store.execute(
                "INSERT INTO change_requests(change_request_id,repository_uuidv4,repository_binding_id,change_request_kind,provider_change_request_number) VALUES('pr','00000000-0000-4000-8000-000000000401',?,'pull_request',1)",
                (binding,),
            )
            admit_pr_state(store, "pr", state="open", merged=False)
            add_document(store, "pr", "1", "needle")
            for kind in ("pr", "pr-documents"):
                store.coverage(
                    "00000000-0000-4000-8000-000000000401",
                    kind,
                    "complete",
                    observed_at_us=-1,
                )
        yield state, store
        assert not store.all("PRAGMA foreign_key_check")


@pytest.mark.parametrize(
    "command",
    [
        ("coverage", "--repo", "00000000-0000-4000-8000-000000000401", "--kind", "git"),
        ("status", "--repo", "00000000-0000-4000-8000-000000000401", "--kind", "git"),
        ("snapshots", "show", "--snapshot", "snapshot"),
        ("snapshots", "list", "--repo", "00000000-0000-4000-8000-000000000401"),
    ],
)
def test_cli_current_conflict_preserves_separate_latest_claim_details(
    coverage_catalog, command
):
    state, store = coverage_catalog
    complete_details = '{"producer":"first","complete_only":true}'
    partial_details = '{"producer":"second","partial_only":true}'
    with store.transaction():
        store.coverage(
            "00000000-0000-4000-8000-000000000401", "git", "complete", observed_at_us=0
        )
        store.coverage(
            "00000000-0000-4000-8000-000000000401",
            "git",
            "complete",
            complete_details,
            observed_at_us=1,
        )
        store.coverage(
            "00000000-0000-4000-8000-000000000401",
            "git",
            "partial",
            partial_details,
            observed_at_us=1,
        )
        store.coverage(
            "00000000-0000-4000-8000-000000000401", "git", "unknown", observed_at_us=1
        )
    result = run(state, *command)
    item = result["data"]["items"][0]
    components = item["coverage" if command[0] == "snapshots" else "components"]
    current = next(component for component in components if component["kind"] == "git")
    assert current["coverage_state"] == "conflict"
    assert current["observed_at_us"] == 1
    assert current["claim_count"] == 3
    assert "details" not in current and "details_json" not in current
    assert {
        claim["coverage_state"]: claim["details_json"] for claim in current["claims"]
    } == {
        "complete": complete_details,
        "partial": partial_details,
        "unknown": None,
    }
    assert {claim["observed_at_us"] for claim in current["claims"]} == {1}
    assert (
        store.one(
            "SELECT count(*) FROM coverage_claims WHERE coverage_scope_id=?",
            (current["coverage_scope_id"],),
        )[0]
        == 4
    )


def test_cli_latest_unknown_does_not_fall_back_to_saved_complete(coverage_catalog):
    state, store = coverage_catalog
    with store.transaction():
        store.coverage(
            "00000000-0000-4000-8000-000000000401",
            "git",
            "complete",
            {"old": True},
            observed_at_us=-1,
        )
        store.coverage(
            "00000000-0000-4000-8000-000000000401", "git", "unknown", observed_at_us=0
        )
    result = run(
        state,
        "coverage",
        "--repo",
        "00000000-0000-4000-8000-000000000401",
        "--kind",
        "git",
    )
    current = result["data"]["items"][0]["components"][0]
    assert current["coverage_state"] == "unknown"
    assert current["observed_at_us"] == 0
    assert current["claim_count"] == 1
    assert len(current["claims"]) == 1
    assert current["claims"][0]["coverage_state"] == "unknown"
    assert current["claims"][0]["details_json"] is None


def test_cli_empty_scope_has_no_fabricated_claim_time_or_details(coverage_catalog):
    state, store = coverage_catalog
    with store.transaction():
        store.execute(
            "INSERT INTO coverage_scopes(coverage_scope_id,repository_uuidv4,kind) VALUES('empty-scope','00000000-0000-4000-8000-000000000401','empty')"
        )
    result = run(
        state,
        "status",
        "--repo",
        "00000000-0000-4000-8000-000000000401",
        "--kind",
        "empty",
    )
    current = result["data"]["items"][0]["components"][0]
    assert current["coverage_state"] == "unknown"
    assert current["observed_at_us"] is None
    assert current["claim_count"] == 0
    assert current["claims"] == []
    assert "details" not in current and "details_json" not in current


@pytest.mark.parametrize(
    "old_states,latest_states,complete",
    [
        (("partial",), ("complete",), True),
        (("complete",), ("complete", "partial"), False),
        (("complete",), ("unknown",), False),
        (("complete", "partial"), ("complete",), True),
    ],
)
def test_ordinary_and_diagnostic_pr_queries_use_only_current_coverage(
    coverage_catalog, old_states, latest_states, complete
):
    state, store = coverage_catalog
    with store.transaction():
        for coverage_state in old_states:
            store.coverage(
                "00000000-0000-4000-8000-000000000401",
                "pr-documents",
                coverage_state,
                observed_at_us=0,
                change_request_id="pr",
            )
        for coverage_state in latest_states:
            store.coverage(
                "00000000-0000-4000-8000-000000000401",
                "pr-documents",
                coverage_state,
                observed_at_us=1,
                change_request_id="pr",
            )
    scope = store.one(
        "SELECT coverage_scope_id FROM coverage_scopes WHERE change_request_id='pr' AND kind='pr-documents'"
    )[0]
    commands = [
        (
            "pr",
            "show",
            "--repo",
            "00000000-0000-4000-8000-000000000401",
            "--provider-change-request-number",
            1,
        ),
        (
            "pr",
            "documents",
            "--repo",
            "00000000-0000-4000-8000-000000000401",
            "--provider-change-request-number",
            1,
        ),
        (
            "target",
            "--database",
            state / "catalog.sqlite3",
            "pr",
            "--repo",
            "00000000-0000-4000-8000-000000000401",
            "--provider-change-request-number",
            1,
        ),
        (
            "target",
            "--database",
            state / "catalog.sqlite3",
            "search",
            "--repo",
            "00000000-0000-4000-8000-000000000401",
            "--kind",
            "pr",
            "--literal",
            "needle",
        ),
    ]
    for command in commands:
        result = run(state, *command, expected=0 if complete else 3)
        missing = [
            item
            for item in result["coverage"]["missing"]
            if item["reason"] == "saved_scope_incomplete"
        ]
        assert [item["coverage_scope_id"] for item in missing] == (
            [] if complete else [scope]
        ), command
        assert result["coverage"]["complete_for_requested_scope"] is complete, command
        assert result["status"] == ("complete" if complete else "partial"), command


def test_document_only_queries_ignore_code_only_coverage(coverage_catalog):
    state, store = coverage_catalog
    with store.transaction():
        for kind in ("pr-commits", "pr-files", "pr-code"):
            store.coverage(
                "00000000-0000-4000-8000-000000000401",
                kind,
                "partial",
                {"code_only": True},
                observed_at_us=1,
                change_request_id="pr",
            )
    for command in (
        (
            "pr",
            "documents",
            "--repo",
            "00000000-0000-4000-8000-000000000401",
            "--provider-change-request-number",
            1,
        ),
        (
            "search",
            "pr",
            "--repo",
            "00000000-0000-4000-8000-000000000401",
            "--literal",
            "needle",
        ),
    ):
        result = run(state, *command)
        assert result["status"] == "complete", command
        assert result["coverage"]["complete_for_requested_scope"], command
        assert not [
            item
            for item in result["coverage"]["missing"]
            if item["reason"] == "saved_scope_incomplete"
        ], command


def test_pr_query_coverage_is_independent_of_page_limit(coverage_catalog):
    state, store = coverage_catalog
    binding = store.one(
        "SELECT repository_binding_id FROM repository_bindings WHERE repository_uuidv4='00000000-0000-4000-8000-000000000401'"
    )[0]
    with store.transaction():
        for number in (2, 3):
            change_request_id = f"pr-{number}"
            store.execute(
                "INSERT INTO change_requests(change_request_id,repository_uuidv4,repository_binding_id,change_request_kind,provider_change_request_number) VALUES(?,?,?,'pull_request',?)",
                (
                    change_request_id,
                    "00000000-0000-4000-8000-000000000401",
                    binding,
                    number,
                ),
            )
            admit_pr_state(store, change_request_id, state="open", merged=False)
            add_document(store, change_request_id, str(number), f"pr {number}")
        store.coverage(
            "00000000-0000-4000-8000-000000000401",
            "pr-documents",
            "unknown",
            observed_at_us=1,
            change_request_id="pr-3",
        )

    for limit in (1, 2, 100):
        result = run(
            state,
            "pr",
            "list",
            "--repo",
            "00000000-0000-4000-8000-000000000401",
            "--limit",
            limit,
            expected=3,
        )
        assert result["status"] == "partial", limit
        assert not result["coverage"]["complete_for_requested_scope"], limit


def test_coverage_owner_namespaces_are_explicit(coverage_catalog):
    _state, store = coverage_catalog
    with store.transaction():
        store.execute(
            "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES('00000000-0000-4000-8000-000000000402','collision-repository','{}')"
        )
        repository_claim = store.coverage(
            "00000000-0000-4000-8000-000000000402",
            "collision",
            "complete",
            observed_at_us=1,
        )
        request_claim = store.coverage(
            "00000000-0000-4000-8000-000000000401",
            "collision",
            "partial",
            observed_at_us=1,
            change_request_id="pr",
        )
        with pytest.raises(CatalogError) as error:
            store.coverage(
                "00000000-0000-4000-8000-000000000402",
                "wrong-owner",
                "complete",
                observed_at_us=1,
                change_request_id="pr",
            )
        assert error.value.code == "INVALID_COVERAGE_OWNER"

    assert repository_claim is not None and request_claim is not None
    rows = store.all(
        "SELECT repository_uuidv4,change_request_id,kind FROM coverage_scopes WHERE kind='collision' ORDER BY repository_uuidv4"
    )
    assert [tuple(row) for row in rows] == [
        ("00000000-0000-4000-8000-000000000401", "pr", "collision"),
        ("00000000-0000-4000-8000-000000000402", None, "collision"),
    ]


@pytest.mark.parametrize(
    "role,link_state",
    [
        ("head", "absent"),
        ("base", "null_root"),
        ("merge", "incomplete"),
        ("head", "wrong_oid"),
        ("base", "object_missing"),
        (None, "complete"),
    ],
)
def test_diagnostic_queries_preserve_complete_label_role_gap_checks(
    pr_catalog, role, link_state
):
    state, store = pr_catalog
    with store.transaction():
        add_complete_code(store, role, link_state)
        store.advance_local_revision()
    commands = (
        (
            "pr",
            "show",
            "--repo",
            "00000000-0000-4000-8000-000000000401",
            "--provider-change-request-number",
            1,
        ),
        (
            "target",
            "--database",
            state / "catalog.sqlite3",
            "pr",
            "--repo",
            "00000000-0000-4000-8000-000000000401",
            "--provider-change-request-number",
            1,
        ),
        (
            "target",
            "--database",
            state / "catalog.sqlite3",
            "search",
            "--repo",
            "00000000-0000-4000-8000-000000000401",
            "--kind",
            "pr",
            "--literal",
            "needle",
        ),
    )
    results = [run(state, *command, expected=3 if role else 0) for command in commands]
    assert all(result["coverage"] == results[0]["coverage"] for result in results)
    missing = results[0]["coverage"]["missing"]
    assert [gap["reason"] for gap in missing] == (
        ["code_role_target_conflict"]
        if link_state == "wrong_oid"
        else ["code_role_acquisition_missing"]
        if role
        else []
    )
    assert [gap["role"] for gap in missing] == ([role] if role else [])


@pytest.mark.parametrize("declared", [["head"], {"merge": {"oid": "unparsed"}}])
def test_diagnostic_role_target_shapes_are_rejected_before_admission(
    pr_catalog, declared
):
    _, store = pr_catalog
    with pytest.raises(sqlite3.IntegrityError, match="JSON contract"):
        with store.transaction():
            add_complete_code(store, declared=declared)
    assert store.one("SELECT count(*) FROM code_assessments")[0] == 0


def test_retained_exact_code_assessment_does_not_recreate_api_edit_history(pr_catalog):
    state, store = pr_catalog
    with store.transaction():
        old_code, targets = add_complete_code(store, "head", "absent")
        admit_pr_state(
            store, "repo:1:pull_request", provider_updated_at_us=2, head_oid="ab" * 20
        )
        store.advance_local_revision()
    assert (
        store.one(
            "SELECT head_oid FROM code_assessments WHERE code_assessment_id=?",
            (old_code,),
        )[0]
        == targets["head"]
    )
    assert (
        store.one(
            "SELECT count(*) FROM change_request_state WHERE change_request_id='repo:1:pull_request'"
        )[0]
        == 1
    )
    from repo_catalog.application.target_queries import TargetQueryService

    with pytest.raises(CatalogError, match="history"):
        TargetQueryService(state / "catalog.sqlite3").query(
            "pr",
            {
                "repo": "00000000-0000-4000-8000-000000000401",
                "provider_change_request_number": 1,
                "observations": "all",
            },
        )
    result = QueryService(state).query(
        "pr code",
        {
            "repo": "00000000-0000-4000-8000-000000000401",
            "provider_change_request_number": 1,
        },
    )
    assert result.status == "partial"
    assert result.data["items"] == []
    assert any(
        gap["reason"] == "code_assessment_missing"
        and gap["change_request_id"] == "repo:1:pull_request"
        for gap in result.coverage.missing
    )


def test_metadata_filters_do_not_hide_code_gaps_from_requested_identity_scope(
    pr_catalog,
):
    state, store = pr_catalog
    with store.transaction():
        add_complete_code(store, "head", "absent")
        store.advance_local_revision()
    result = run(
        state,
        "search",
        "pr",
        "--repo",
        "00000000-0000-4000-8000-000000000401",
        "--literal",
        "needle",
        "--path",
        "not-saved",
        "--author",
        "nonmatching",
        expected=3,
    )
    assert result["data"]["items"] == []
    assert [gap["reason"] for gap in result["coverage"]["missing"]] == [
        "code_role_acquisition_missing"
    ]
