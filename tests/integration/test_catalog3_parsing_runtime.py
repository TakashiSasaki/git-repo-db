"""Remote admission retains typed domain state and actual producer attribution."""

import json
import uuid

import pytest

from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.application.collection_service import CollectionService
from repo_catalog.application.parsing_service import ParsingService
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.support.github_runtime import github_runtime as github_runtime
from tests.support.github_runtime import sync
from tests.support.sqlite_contracts import assert_absent_tables


def test_normal_acquisition_retains_typed_producers_and_exact_code_dependencies(
    github_runtime,
):
    store, repo, _, _ = github_runtime
    sync(store, repo)
    for table in (
        "change_request_state",
        "document_state",
        "review_thread_state",
        "change_request_events",
        "code_assessments",
    ):
        rows = store.all(f"SELECT parser_module,parser_version FROM {table}")
        assert rows and all(
            tuple(row) == ("repo_catalog.adapters.github.current_parser", "3")
            for row in rows
        )
    assert (
        store.one(
            "SELECT count(*) FROM code_acquisitions a JOIN acquisition_roots r USING(acquisition_root_id) WHERE a.role=r.role AND a.oid=r.oid AND r.complete=1"
        )[0]
        >= 6
    )
    assert_absent_tables(
        store.connection,
        "parsed_results",
        "parsed_result_inputs",
        "parsed_result_publications",
        "parser_profiles",
        "fetch_occurrences",
        "source_input_observations",
    )
    assert not store.all("PRAGMA foreign_key_check")
    assert store.one("PRAGMA integrity_check")[0] == "ok"


@pytest.mark.parametrize(
    "kind",
    [
        "pr-detail",
        "pr-list",
        "threads",
        "timeline",
        "pr-commits",
        "pr-files",
        "issue-comment",
    ],
)
@pytest.mark.parametrize("select", [False, True])
def test_core_http_reparse_is_retired_without_reading_original_or_mutating_catalog(
    github_runtime, monkeypatch, kind, select
):
    store, repo, _, api = github_runtime
    sync(store, repo)
    collection = store.one(
        "SELECT fetch_collection_id FROM fetch_collections WHERE kind=?", (kind,)
    )
    assert collection is not None
    before = list(store.connection.iterdump())
    before_requests = len(api.requests)
    original_one = store.one

    def domain_only_query(sql, parameters=()):
        assert all(
            table not in sql
            for table in ("fetch_occurrences", "stored_bytes", "payloads")
        )
        return original_one(sql, parameters)

    monkeypatch.setattr(store, "one", domain_only_query)
    with pytest.raises(CatalogError, match="API response replay is retired") as error:
        ParsingService(store).reparse(
            collection["fetch_collection_id"],
            select=select,
            profile_uuid=str(uuid.uuid4()),
        )
    assert error.value.code == "PARSER_UNSUPPORTED_INPUT"
    assert list(store.connection.iterdump()) == before
    assert len(api.requests) == before_requests


def test_source_inventory_admits_current_scoped_roster_without_originals(
    github_runtime,
):
    store, _, _, _ = github_runtime
    result = CollectionService(store.path).discover("source")
    assert result.status == "complete"
    rows = store.all("SELECT * FROM source_repositories WHERE source_id='source'")
    assert len(rows) == 1
    assert all(
        json.loads(row["scope_json"])["source_registration_uuidv4"]
        == store.one(
            "SELECT source_registration_uuidv4 FROM sources WHERE source_id='source'"
        )[0]
        for row in rows
    )
    assert all(
        row["parser_module"] == "repo_catalog.adapters.github.current_parser"
        for row in rows
    )
    assert_absent_tables(
        store.connection,
        "source_input_observations",
        "parsed_results",
        "fetch_occurrences",
    )
    assert store.one("SELECT count(*) FROM stored_bytes")[0] == 0


def test_http_reparse_lookup_ignores_quarantined_git_content(
    github_runtime, monkeypatch
):
    store, _, _, _ = github_runtime
    before = list(store.connection.iterdump())

    def forbidden(*args):
        raise AssertionError("Replay must not read any payload")

    monkeypatch.setattr("repo_catalog.adapters.git.parsing.reparse_git", forbidden)
    with pytest.raises(CatalogError) as error:
        ParsingService(store).reparse(str(uuid.uuid4()))
    assert error.value.code == "PARSER_UNSUPPORTED_INPUT"
    assert list(store.connection.iterdump()) == before


def test_api_original_has_no_admission_method_or_representation(github_runtime):
    from repo_catalog.adapters.sqlite.payloads import intern_payload

    store, _, _, _ = github_runtime
    facts = GitHubCollector(store, CancellationToken()).facts
    assert not any(
        hasattr(facts, name)
        for name in ("payload", "document", "publish", "inventory_result", "result")
    )
    with pytest.raises(CatalogError) as error:
        intern_payload(
            store.connection,
            b'{"provider_original":true}',
            representation="decoded_api",
        )
    assert error.value.code == "INVALID_PAYLOAD_REFERENCE"
    assert store.one("SELECT count(*) FROM stored_bytes")[0] == 0


def test_parser_labels_cannot_replace_latest_document_clock(github_runtime):
    from repo_catalog.adapters.sqlite.current_api import CurrentApiState

    store, repo, _, _ = github_runtime
    sync(store, repo)
    row = dict(store.one("SELECT * FROM document_state WHERE kind='pr-body' LIMIT 1"))
    before = tuple(
        store.one(
            "SELECT text_body_sha256,provider_updated_at_us,parser_module,parser_version FROM document_state WHERE change_request_id=? AND kind='pr-body'",
            (row["change_request_id"],),
        )
    )
    candidate = CurrentApiState(store).candidate_from_row("document_state", row)
    candidate["body"] = "older interpretation with higher version"
    candidate["observed_at_us"] -= 1
    candidate["parser_version"] = "9999"
    candidate["field_evidence"] = {}
    with store.transaction():
        CurrentApiState(store).admit("document_state", candidate, source="import")
    assert (
        tuple(
            store.one(
                "SELECT text_body_sha256,provider_updated_at_us,parser_module,parser_version FROM document_state WHERE change_request_id=? AND kind='pr-body'",
                (row["change_request_id"],),
            )
        )
        == before
    )


def test_repository_http_etag_is_transient_and_never_a_domain_original(github_runtime):
    store, _, _, api = github_runtime
    api.etag = True
    for _ in range(2):
        assert CollectionService(store.path).discover("source").status == "complete"
    assert_absent_tables(
        store.connection, "source_input_observations", "fetch_occurrences", "validators"
    )
    assert store.one("SELECT count(*) FROM source_repositories")[0] == 1
    assert store.one("SELECT count(*) FROM stored_bytes")[0] == 0
