"""API transport originals and accepted edit history have no domain owner."""

import json

import pytest

from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.domain.models import CatalogError
from tests.integration.test_catalog3_exchange import candidate, fixture, receive
from tests.integration.test_catalog3_exchange import databases as databases


def test_retired_transport_tables_and_original_representation_absent(databases):
    source, target = databases
    expected = fixture(source)
    names = {r[0] for r in source.execute("SELECT name FROM sqlite_schema")}
    assert (
        not {
            "fetch_occurrences",
            "parsed_results",
            "parser_profiles",
            "fact_selection_scopes",
            "publication_inputs",
        }
        & names
    )
    with pytest.raises(Exception, match="CHECK constraint"):
        source.execute("INSERT INTO payloads VALUES('decoded_api',?)", (b"x" * 32,))
    unit = Graph(source).export(expected["repository"])
    assert receive(target, unit)["staged_records"] == 0
    assert not {"payloads", "stored_bytes"} & {r["table"] for r in unit["records"]}


def test_accepted_api_edit_not_archived_in_admission_envelope(databases):
    source, target = databases
    expected = fixture(source, body=b"old body")
    assert (
        receive(target, Graph(source).export(expected["repository"]))["staged_records"]
        == 0
    )
    api = CurrentApiState(source)
    assert (
        api.admit(
            "document_state", candidate(expected, "pr-body", "new body", updated=2)
        ).status
        == "accepted"
    )
    current = Graph(source).export(expected["repository"])
    assert receive(target, current)["staged_records"] == 0
    assert "record_json" not in {
        r[1] for r in target.execute("PRAGMA table_info(exchange_admissions)")
    }
    assert target.execute("SELECT count(*) FROM exchange_staging").fetchone() == (0,)
    assert "old body" not in json.dumps(Graph(target).export(expected["repository"]))
    assert target.execute("SELECT count(*) FROM document_state").fetchone() == (1,)


def test_opaque_original_field_is_rejected_before_any_admission(databases):
    source, target = databases
    expected = fixture(source)
    unit = Graph(source).export(expected["repository"])
    record = next(r for r in unit["records"] if r["table"] == "document_state")
    record["values"]["original_response"] = {"secret": "provider response"}
    with pytest.raises(CatalogError, match="Unexpected domain"):
        receive(target, unit)
    assert target.execute("SELECT count(*) FROM exchange_admissions").fetchone() == (0,)
    assert target.execute("SELECT count(*) FROM exchange_staging").fetchone() == (0,)
