"""Runtime contracts: remote acquisition, parser execution and current decisions."""

import json
import uuid

import pytest

from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.application.parsing_service import ParsingService
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.support.github_runtime import github_runtime as github_runtime
from tests.support.github_runtime import sync


def _fetch(store, kind):
    return store.one(
        "SELECT o.* FROM fetch_occurrences o JOIN fetch_collections f "
        "ON f.fetch_collection_id=o.fetch_collection_id WHERE f.kind=? "
        "ORDER BY o.fetch_occurrence_id LIMIT 1",
        (kind,),
    )


def test_normal_acquisition_publishes_owned_results_and_multiple_code_inputs(
    github_runtime,
):
    store, repo, _, _ = github_runtime
    sync(store, repo)
    fetches = store.all(
        "SELECT fetch_occurrence_uuidv4,repository_uuidv4 FROM fetch_occurrences"
    )
    assert fetches and all(
        uuid.UUID(row[0]).version == 4 and row[1] == repo["repository_uuidv4"]
        for row in fetches
    )
    for table in (
        "change_request_observations",
        "document_observations",
        "change_request_events",
        "code_observations",
        "code_commits",
        "code_file_changes",
        "review_thread_observations",
    ):
        assert not store.one(
            f"SELECT 1 FROM {table} f LEFT JOIN parsed_result_publications p USING(parsed_result_uuidv4) WHERE p.parsed_result_uuidv4 IS NULL"
        )
    assert (
        store.one(
            "SELECT count(*) FROM parsed_result_inputs WHERE parsed_result_uuidv4=(SELECT parsed_result_uuidv4 FROM current_code_observations LIMIT 1)"
        )[0]
        > 1
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
    fetch = _fetch(store, kind)
    assert fetch is not None
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
            fetch["fetch_occurrence_uuidv4"],
            select=select,
            profile_uuid=str(uuid.uuid4()),
        )
    assert error.value.code == "PARSER_UNSUPPORTED_INPUT"
    assert list(store.connection.iterdump()) == before
    assert len(api.requests) == before_requests


def test_source_inventory_records_separate_owned_raw_inputs(github_runtime):
    store, _, _, _ = github_runtime
    source = store.one("SELECT * FROM sources WHERE source_id='source'")
    collector = GitHubCollector(store, CancellationToken())
    repositories = collector.inventory(source, "unused-inventory-job")
    assert repositories
    assert collector.inventory_evidence
    with store.transaction():
        result = collector.inventory_result(source)
    inputs = store.all("SELECT * FROM source_input_observations")
    assert len(inputs) == len(collector.inventory_evidence)
    assert all(
        row["source_registration_uuidv4"] == source["source_registration_uuidv4"]
        for row in inputs
    )
    assert all(
        isinstance(json.loads(row["request_context_json"]), dict) for row in inputs
    )
    assert not store.one("SELECT 1 FROM fetch_occurrences")
    assert (
        store.one(
            "SELECT source_registration_uuidv4 FROM parsed_results WHERE parsed_result_uuidv4=?",
            (result,),
        )[0]
        == source["source_registration_uuidv4"]
    )
    assert not store.all("PRAGMA foreign_key_check")


def test_retired_http_reparse_rejects_quarantined_original_without_diagnosis(
    github_runtime,
):
    store, repo, _, _ = github_runtime
    sync(store, repo)
    fetch = _fetch(store, "pr-detail")
    with store.transaction():
        diag = store.execute(
            "INSERT INTO unresolved_payloads(reason,stored_sha256,detected_at_us,diagnostic_json) VALUES('physical_corruption',?,0,'{}')",
            (fetch["payload_sha256"],),
        ).lastrowid
        store.execute(
            "INSERT INTO payload_quarantine(sha256,unresolved_payload_id) VALUES(?,?)",
            (fetch["payload_sha256"], diag),
        )
    before = store.one("SELECT count(*) FROM parsed_results")[0]
    with pytest.raises(CatalogError, match="API response replay is retired"):
        ParsingService(store).reparse(fetch["fetch_occurrence_uuidv4"])
    assert store.one("SELECT count(*) FROM parsed_results")[0] == before


def test_valid_new_fetch_of_corrupt_digest_is_staged_with_original_identity(
    github_runtime,
):
    import httpx

    from repo_catalog.adapters.github.persistence import ApiFacts

    store, repo, _, _ = github_runtime
    sync(store, repo)
    fetch = _fetch(store, "pr-detail")
    body = store.one(
        "SELECT body FROM stored_bytes WHERE sha256=?", (fetch["payload_sha256"],)
    )[0]
    trigger = store.one(
        "SELECT sql FROM sqlite_schema WHERE name='stored_bytes_immutable'"
    )[0]
    with store.transaction():
        store.execute("DROP TRIGGER stored_bytes_immutable")
        corrupted = (b"x" if body[:1] != b"x" else b"y") + body[1:]
        store.execute(
            "UPDATE stored_bytes SET body=? WHERE sha256=?",
            (corrupted, fetch["payload_sha256"]),
        )
        store.execute(trigger)
    collection = dict(
        store.one(
            "SELECT * FROM fetch_collections WHERE fetch_collection_id=?",
            (fetch["fetch_collection_id"],),
        )
    )
    facts = ApiFacts(store, store.config["github"])
    count = store.one("SELECT count(*) FROM fetch_occurrences")[0]
    with pytest.raises(CatalogError) as failure, store.transaction():
        facts.page(
            collection,
            httpx.Response(
                200,
                content=body,
                headers={
                    "ETag": 'W/"opaque,=token"',
                    "Set-Cookie": "synthetic-secret=excluded",
                },
            ),
            {"url": "https://fixture.invalid/detail", "method": "GET"},
            None,
        )
    assert failure.value.code == "PAYLOAD_CORRUPTION"
    received = facts.rejected_fetch[1].copy()
    assert received["request"]["response"] == {
        "status": 200,
        "headers": {"etag": 'W/"opaque,=token"'},
    }
    assert "synthetic-secret" not in json.dumps(received)
    assert facts.stage_rejected(failure.value)
    staged = store.one("SELECT * FROM payload_admission_staging")
    assert staged["body"] == body
    assert json.loads(staged["context_json"]) == received
    assert received["fetch_occurrence_uuidv4"] != fetch["fetch_occurrence_uuidv4"]
    assert uuid.UUID(received["fetch_occurrence_uuidv4"]).version == 4
    assert store.one("SELECT count(*) FROM fetch_occurrences")[0] == count
    assert (
        store.one(
            "SELECT body FROM stored_bytes WHERE sha256=?", (fetch["payload_sha256"],)
        )[0]
        == corrupted
    )
    assert store.one(
        "SELECT 1 FROM payload_quarantine WHERE sha256=?", (fetch["payload_sha256"],)
    )


def test_other_profile_result_retained_without_changing_selected_document(
    github_runtime,
):
    from repo_catalog.adapters.github.persistence import ApiFacts
    from repo_catalog.adapters.sqlite.parser_model import (
        ParserModel,
        builtin_definition,
    )

    store, repo, _, _ = github_runtime
    sync(store, repo)
    fetch = _fetch(store, "pr-detail")
    old = store.one(
        "SELECT * FROM current_document_observations WHERE kind='pr-body' ORDER BY change_request_id LIMIT 1"
    )
    definition = builtin_definition()
    definition["settings"] = {"explicit_test_profile": "alternative"}
    model = ParserModel(store.connection)
    with store.transaction():
        profile = model.register_profile(definition)
        verification = model.verify_profile(
            profile,
            criteria={"synthetic_test_fixture": True},
            evidence={
                "definition": definition,
                "capabilities": [
                    {
                        **capability,
                        "outcome": "passed",
                        "checks": [{"synthetic_test_fixture": True}],
                    }
                    for capability in definition["capabilities"]
                ],
            },
        )
        model.trust_verification(
            verification, rationale={"synthetic_test_fixture": True}
        )
        facts = ApiFacts(store, store.config["github"])
        facts.profile_uuid = profile
        collection = dict(
            store.one(
                "SELECT * FROM fetch_collections WHERE fetch_collection_id=?",
                (fetch["fetch_collection_id"],),
            )
        )
        facts.document(
            old["change_request_id"],
            "pr-body",
            old["provider_change_request_document_id"],
            "alternative normalization",
            {
                "user": {"login": "alternative-parser"},
                "url": "https://fixture.invalid/alternate",
            },
            collection,
            fetch["fetch_occurrence_id"],
            1,
            fetch["observed_at_us"],
        )
        facts.publish()
        result = next(iter(facts.unselected_results))
    assert (
        store.one(
            "SELECT parsed_result_uuidv4 FROM current_document_observations WHERE change_request_id=? AND kind='pr-body'",
            (old["change_request_id"],),
        )[0]
        == old["parsed_result_uuidv4"]
    )
    assert (
        store.one(
            "SELECT author FROM document_observations WHERE parsed_result_uuidv4=?",
            (result,),
        )[0]
        == "alternative-parser"
    )
    assert store.one(
        "SELECT 1 FROM parsed_result_publications WHERE parsed_result_uuidv4=?",
        (result,),
    )
    assert not store.one(
        "SELECT 1 FROM fact_selection_decisions WHERE parsed_result_uuidv4=?", (result,)
    )


def test_repository_response_etag_survives_as_immutable_history_including_304(
    github_runtime,
):
    store, repo, _, api = github_runtime
    api.etag = True
    original = api.route

    def route(method, path, params, body):
        value, headers = original(method, path, params, body)
        return value, {**headers, "Set-Cookie": "synthetic-secret=excluded"}

    api.route = route
    sync(store, repo)
    fetch = _fetch(store, "pr-detail")
    request = json.loads(fetch["request"])
    expected_etag = '"' + api.stage + '"'
    assert request["response"] == {"status": 200, "headers": {"etag": expected_etag}}
    assert "synthetic-secret" not in fetch["request"]
    sync(store, repo)
    validations = store.all(
        "SELECT evidence FROM completion_markers WHERE json_extract(evidence,'$.status')=304"
    )
    assert validations
    for record in validations:
        evidence = json.loads(record[0])
        assert evidence["response"] == {
            "status": 304,
            "headers": {"etag": expected_etag},
        }
        assert evidence["fetch_occurrence_uuidv4"]
        assert evidence["change_request_observation_uuidv4"]
        assert "synthetic-secret" not in record[0]
    assert (
        store.one(
            "SELECT request FROM fetch_occurrences WHERE fetch_occurrence_uuidv4=?",
            (fetch["fetch_occurrence_uuidv4"],),
        )[0]
        == fetch["request"]
    )
