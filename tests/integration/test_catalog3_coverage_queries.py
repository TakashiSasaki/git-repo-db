"""Current coverage reaches offline CLI projections without historical fallback."""

import json

import pytest

from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.repository_identity import add_instance, bind
from repo_catalog.domain.models import CatalogError
from tests.integration.test_catalog3_pr_scope_coverage import (
    add_complete_code,
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
                "INSERT INTO repositories(repository_id,name,metadata) VALUES('repo','synthetic/repo','{}')"
            )
            bind(store, "repo", namespace, "1")
            binding = store.one(
                "SELECT repository_binding_id FROM repository_bindings WHERE repository_id='repo'"
            )[0]
            store.execute(
                "INSERT INTO git_acquisitions(git_acquisition_id,repository_id,object_format,refs_observed_at_us,kind,observed_at_us,request,roots_manifest) VALUES('acquisition','repo','sha1',0,'git',0,'{}','[]')"
            )
            store.execute(
                "INSERT INTO snapshots(snapshot_id,git_acquisition_id,repository_id,published,generation,created_at_us) VALUES('snapshot','acquisition','repo',1,1,0)"
            )
            store.execute(
                "UPDATE repositories SET current_snapshot_id='snapshot' WHERE repository_id='repo'"
            )
            store.execute(
                "INSERT INTO change_requests(change_request_id,repository_id,repository_binding_id,change_request_kind,provider_change_request_number) VALUES('pr','repo',?,'pull_request',1)",
                (binding,),
            )
            store.execute(
                "INSERT INTO change_request_observations(change_request_observation_id,change_request_id,observed_at_us,published,payload,parsed_at_us) VALUES(1,'pr',0,1,?,0)",
                (json.dumps({"title": "needle", "state": "open", "merged": False}),),
            )
            store.execute(
                "UPDATE change_requests SET current_change_request_observation_id=1 WHERE change_request_id='pr'"
            )
            for kind in ("pr", "pr-documents"):
                store.coverage("repo", kind, "complete", observed_at_us=-1)
        yield state, store
        assert not store.all("PRAGMA foreign_key_check")


@pytest.mark.parametrize(
    "command",
    [
        ("coverage", "--repo", "repo", "--kind", "git"),
        ("status", "--repo", "repo", "--kind", "git"),
        ("snapshots", "show", "--snapshot", "snapshot"),
        ("snapshots", "list", "--repo", "repo"),
    ],
)
def test_cli_current_conflict_preserves_separate_latest_claim_details(
    coverage_catalog, command
):
    state, store = coverage_catalog
    complete_details = '{"producer":"first","complete_only":true}'
    partial_details = '{"producer":"second","partial_only":true}'
    with store.transaction():
        store.coverage("repo", "git", "complete", observed_at_us=0)
        store.coverage("repo", "git", "complete", complete_details, observed_at_us=1)
        store.coverage("repo", "git", "partial", partial_details, observed_at_us=1)
        store.coverage("repo", "git", "unknown", observed_at_us=1)
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
        store.coverage("repo", "git", "complete", {"old": True}, observed_at_us=-1)
        store.coverage("repo", "git", "unknown", observed_at_us=0)
    result = run(state, "coverage", "--repo", "repo", "--kind", "git")
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
            "INSERT INTO coverage_scopes(coverage_scope_id,repository_id,kind) VALUES('empty-scope','repo','empty')"
        )
    result = run(state, "status", "--repo", "repo", "--kind", "empty")
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
                "repo",
                "pr-documents",
                coverage_state,
                observed_at_us=0,
                change_request_id="pr",
            )
        for coverage_state in latest_states:
            store.coverage(
                "repo",
                "pr-documents",
                coverage_state,
                observed_at_us=1,
                change_request_id="pr",
            )
    scope = store.one(
        "SELECT coverage_scope_id FROM coverage_scopes WHERE change_request_id='pr' AND kind='pr-documents'"
    )[0]
    commands = [
        ("pr", "show", "--repo", "repo", "--provider-change-request-number", 1),
        ("pr", "documents", "--repo", "repo", "--provider-change-request-number", 1),
        (
            "target",
            "--database",
            state / "catalog.sqlite3",
            "pr",
            "--repo",
            "repo",
            "--provider-change-request-number",
            1,
        ),
        (
            "target",
            "--database",
            state / "catalog.sqlite3",
            "search",
            "--repo",
            "repo",
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
                "repo",
                kind,
                "partial",
                {"code_only": True},
                observed_at_us=1,
                change_request_id="pr",
            )
    for command in (
        ("pr", "documents", "--repo", "repo", "--provider-change-request-number", 1),
        ("search", "pr", "--repo", "repo", "--literal", "needle"),
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
        "SELECT repository_binding_id FROM repository_bindings WHERE repository_id='repo'"
    )[0]
    with store.transaction():
        for number in (2, 3):
            change_request_id = f"pr-{number}"
            store.execute(
                "INSERT INTO change_requests(change_request_id,repository_id,repository_binding_id,change_request_kind,provider_change_request_number) VALUES(?,?,?,'pull_request',?)",
                (change_request_id, "repo", binding, number),
            )
            store.execute(
                "INSERT INTO change_request_observations(change_request_observation_id,change_request_id,observed_at_us,published,payload,parsed_at_us) VALUES(?,?,0,1,?,0)",
                (
                    number,
                    change_request_id,
                    json.dumps(
                        {"title": f"pr {number}", "state": "open", "merged": False}
                    ),
                ),
            )
            store.execute(
                "UPDATE change_requests SET current_change_request_observation_id=? WHERE change_request_id=?",
                (number, change_request_id),
            )
        store.coverage(
            "repo",
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
            "repo",
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
            "INSERT INTO repositories(repository_id,name,metadata) VALUES('pr','collision-repository','{}')"
        )
        repository_claim = store.coverage(
            "pr", "collision", "complete", observed_at_us=1
        )
        request_claim = store.coverage(
            "repo",
            "collision",
            "partial",
            observed_at_us=1,
            change_request_id="pr",
        )
        with pytest.raises(CatalogError) as error:
            store.coverage(
                "pr",
                "wrong-owner",
                "complete",
                observed_at_us=1,
                change_request_id="pr",
            )
        assert error.value.code == "INVALID_COVERAGE_OWNER"

    assert repository_claim is not None and request_claim is not None
    rows = store.all(
        "SELECT repository_id,change_request_id,kind FROM coverage_scopes WHERE kind='collision' ORDER BY repository_id"
    )
    assert [tuple(row) for row in rows] == [
        ("pr", None, "collision"),
        ("repo", "pr", "collision"),
    ]


@pytest.mark.parametrize(
    "role,link_state",
    [
        ("head", "absent"),
        ("base", "null_root"),
        ("merge", "unpublished"),
        ("head", "wrong_oid"),
        ("base", "object_missing"),
        (None, "published"),
    ],
)
def test_diagnostic_queries_preserve_complete_label_role_gap_checks(
    pr_catalog, role, link_state
):
    state, store = pr_catalog
    with store.transaction():
        add_complete_code(store, role, link_state)
        store.publish()
    commands = (
        ("pr", "show", "--repo", "repo", "--provider-change-request-number", 1),
        (
            "target",
            "--database",
            state / "catalog.sqlite3",
            "pr",
            "--repo",
            "repo",
            "--provider-change-request-number",
            1,
        ),
        (
            "target",
            "--database",
            state / "catalog.sqlite3",
            "search",
            "--repo",
            "repo",
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
        ["code_role_acquisition_missing"] if role else []
    )
    assert [gap["role"] for gap in missing] == ([role] if role else [])


@pytest.mark.parametrize("declared", [["head"], {"merge": {"oid": "unparsed"}}])
def test_diagnostic_role_metadata_is_validated_without_keys_type_assumptions(
    pr_catalog, declared
):
    state, store = pr_catalog
    with store.transaction():
        add_complete_code(store, declared=declared)
        store.publish()
    result = run(
        state,
        "target",
        "--database",
        state / "catalog.sqlite3",
        "pr",
        "--repo",
        "repo",
        "--provider-change-request-number",
        1,
        expected=3,
    )
    assert [gap["reason"] for gap in result["coverage"]["missing"]] == [
        "code_role_targets_unresolved"
    ]


def test_diagnostic_role_checks_retain_history_while_ordinary_query_selects_current(
    pr_catalog,
):
    state, store = pr_catalog
    with store.transaction():
        old_code, targets = add_complete_code(store, "head", "absent")
        # Preserve a later complete interpretation without modifying the older
        # complete-labelled observation whose acquisition was never saved.
        new_code = store.execute(
            "INSERT INTO code_observations(change_request_id,change_request_observation_id,commit_code_listing_id,file_code_listing_id,state,object_format,head_oid,base_oid,details) SELECT change_request_id,change_request_observation_id,commit_code_listing_id,file_code_listing_id,state,object_format,head_oid,base_oid,details FROM code_observations WHERE code_observation_id=?",
            (old_code,),
        ).lastrowid
        store.execute(
            "INSERT INTO code_acquisitions(code_observation_id,role,object_format,oid,acquisition_root_id) SELECT ?,role,object_format,oid,acquisition_root_id FROM code_acquisitions WHERE code_observation_id=?",
            (new_code, old_code),
        )
        store.execute(
            "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES('sha1',?,'commit',0,1)",
            (targets["head"],),
        )
        root = store.execute(
            "INSERT INTO acquisition_roots(git_acquisition_id,object_format,oid,role,repository_id,expected_oid,published) VALUES('code-acquisition','sha1',?,'head','repo',?,1)",
            (targets["head"], targets["head"]),
        ).lastrowid
        store.execute(
            "INSERT INTO code_acquisitions(code_observation_id,role,object_format,oid,acquisition_root_id) VALUES(?,'head','sha1',?,?)",
            (new_code, targets["head"], root),
        )
        store.publish()
    ordinary = run(
        state, "pr", "show", "--repo", "repo", "--provider-change-request-number", 1
    )
    assert ordinary["coverage"]["missing"] == []
    diagnostic = run(
        state,
        "target",
        "--database",
        state / "catalog.sqlite3",
        "pr",
        "--repo",
        "repo",
        "--provider-change-request-number",
        1,
        "--limit",
        1,
        expected=3,
    )
    assert [
        gap["code_observation_id"] for gap in diagnostic["coverage"]["missing"]
    ] == [old_code]
    assert [gap["reason"] for gap in diagnostic["coverage"]["missing"]] == [
        "code_role_acquisition_missing"
    ]


def test_metadata_filters_do_not_hide_code_gaps_from_requested_identity_scope(
    pr_catalog,
):
    state, store = pr_catalog
    with store.transaction():
        add_complete_code(store, "head", "absent")
        store.publish()
    result = run(
        state,
        "search",
        "pr",
        "--repo",
        "repo",
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
