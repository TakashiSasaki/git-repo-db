"""Producer strings attribute current fields without ordinary-read authority."""

import pytest

from tests.integration.test_catalog3_current_queries import (
    current_catalog as current_catalog,
)
from tests.integration.test_current_resources import current, issue
from tests.integration.test_current_resources import resources as resources


@pytest.mark.parametrize(
    "module,version",
    [("tests.decoder", "1"), ("third_party.decoder", "999"), ("other.decoder", "0")],
)
def test_actual_module_and_version_are_sufficient_for_current_admission(
    resources, module, version
):
    adapter, *_ = resources
    candidate = issue(resources, parser_module=module, parser_version=version)
    assert adapter.admit(candidate, source="import").status == "accepted"
    row = current(adapter)
    assert row["body"] == candidate["body"]
    evidence = row["field_evidence"]['["body"]']
    assert evidence["parser_module"] == module
    assert evidence["parser_version"] == version
    assert (
        adapter.c.execute("SELECT count(*) FROM eligible_issue_resources").fetchone()[0]
        == 1
    )
    tables = {
        row[0]
        for row in adapter.c.execute(
            "SELECT name FROM sqlite_schema WHERE type='table'"
        )
    }
    assert not tables.intersection(
        {
            "parser_profiles",
            "parser_profile_capabilities",
            "parser_profile_verifications",
            "parsed_results",
            "parsed_result_inputs",
            "parsed_result_publications",
            "fact_selection_decisions",
            "parser_profile_selection_decisions",
        }
    )


def test_greatest_parser_version_and_capture_time_do_not_resolve_domain_conflict(
    resources,
):
    adapter, *_ = resources
    first = issue(resources, parser_module="tests.first", parser_version="1")
    assert adapter.admit(first, source="import").status == "accepted"
    other = issue(
        resources,
        body="different equal-clock value",
        parser_module="tests.other",
        parser_version="999",
        observed_at_us=2**62,
    )
    assert adapter.admit(other, source="import").status == "conflict"
    assert (
        adapter.c.execute("SELECT count(*) FROM eligible_issue_resources").fetchone()[0]
        == 0
    )
    assert current(adapter)["body"] == first["body"]
    assert adapter.c.execute("SELECT count(*) FROM exchange_staging").fetchone()[0] == 1


def test_sparse_update_retains_actual_prior_field_producer(resources):
    adapter, *_ = resources
    first = issue(resources, parser_module="tests.original", parser_version="1")
    assert adapter.admit(first, source="import").status == "accepted"
    later = issue(
        resources,
        title="new title",
        provider_updated_at_us=20,
        parser_module="tests.new",
        parser_version="2",
    )
    later.pop("body")
    assert adapter.admit(later, source="import").status == "accepted"
    row = current(adapter)
    assert row["body"] == first["body"]
    assert row["title"] == "new title"
    assert row["field_evidence"]['["body"]']["parser_module"] == "tests.original"
    assert row["field_evidence"]['["title"]']["parser_module"] == "tests.new"


def test_repository_exchange_preserves_capture_without_changing_local_source_settings(
    current_catalog,
):
    """Source settings are local; scoped identity and observed origin remain portable."""
    import json
    import sqlite3
    import uuid

    from repo_catalog.adapters.sqlite.exchange import Graph
    from repo_catalog.adapters.sqlite.schema import schema_sql

    catalog = current_catalog
    registration = str(uuid.uuid4())
    with catalog.store.transaction():
        catalog.store.execute(
            "INSERT INTO sources(source_id,source_registration_uuidv4,service_instance_uuidv4,discovery_kind,name,settings) VALUES('source',?,?,'github_inventory','sender-label','{\"owner\":\"sender-owner\"}')",
            (registration, catalog.service),
        )
        catalog.store.execute(
            "INSERT INTO source_repositories(source_id,repository_uuidv4) VALUES('source',?)",
            (catalog.repository,),
        )
    value = catalog.candidate("issue", "10", "source-captured current body")
    value["acquisition_scope"]["source_registration_uuidv4"] = registration
    assert catalog.admit(value).status == "accepted"
    unit = Graph(catalog.store.connection).export(catalog.repository)
    assert "source_inventory_assessments" not in {
        record["table"] for record in unit["records"]
    }
    assert all(
        record["values"]["settings"] is None
        for record in unit["records"]
        if record["table"] == "sources"
    )
    receiver = sqlite3.connect(":memory:", isolation_level=None)
    receiver.executescript(schema_sql())
    try:
        assert Graph(receiver).receive(unit)["staged_records"] == 0
        receiver.execute(
            "UPDATE sources SET name='receiver-label',settings='{\"owner\":\"receiver-owner\"}'"
        )
        catalog.store.execute(
            "UPDATE sources SET name='sender-renamed',settings='{\"owner\":\"new-sender-owner\"}' WHERE source_id='source'"
        )
        later = Graph(catalog.store.connection).export(catalog.repository)
        assert Graph(receiver).receive(later)["staged_records"] == 0
        assert receiver.execute("SELECT name,settings FROM sources").fetchall() == [
            ("receiver-label", '{"owner":"receiver-owner"}')
        ]
        evidence = json.loads(
            receiver.execute(
                "SELECT field_evidence_json FROM issue_resources"
            ).fetchone()[0]
        )
        assert (
            evidence['["body"]']["acquisition_scope"]["source_registration_uuidv4"]
            == registration
        )
        assert receiver.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        receiver.close()
