"""Canonical JSON types and duplicate-key guards on current Context originals."""

import json
import sqlite3
from dataclasses import replace

import pytest

from repo_catalog.application.context_query import ContextQueryService
from repo_catalog.domain.p1_context import canonical
from tests.integration.p3.test_context_retirement_semantics import (
    KEY,
    directory,
    field,
    writable,
)

__all__ = ["directory"]


@pytest.mark.parametrize(
    "first_value,other_value",
    [(True, 1), ([True], [1]), ({}, []), ([], {})],
    ids=["boolean", "array", "object-to-array", "array-to-object"],
)
def test_equal_clock_json_types_remain_distinct_in_real_store_and_query(
    directory, first_value, other_value
):
    first = field("typed-value", first_value, 10, "first")
    other = field("typed-value", other_value, 10, "second")
    unclocked = field("body-proof", "independent body", None, "body", observed=11)
    with writable(directory) as context:
        for original in (first, other, unclocked):
            assert context.admit_field(original) == "insert"
        assert context.admit_field(first) == "duplicate"
    reader = ContextQueryService(directory, mode="context_only")
    view = reader.get_context_resource(KEY)
    assert {item.value_json for item in view.fields["typed-value"]} == {
        canonical(first_value),
        canonical(other_value),
    }
    assert set(view.fields["typed-value"]) == {first, other}
    fresh = field("typed-value", other_value, 20, "actual-new-observation")
    with writable(directory) as context:
        assert context.admit_field(fresh) == "insert"
    final = reader.get_context_resource(KEY)
    assert final.fields["typed-value"] == (fresh,)
    assert final.fields["body-proof"] == (unclocked,)


@pytest.mark.parametrize("column", ["value_json", "clock_json", "provenance_json"])
@pytest.mark.parametrize(
    "raw",
    [
        '{"same":1,"same":2}',
        '{"nested":{"same":1,"same":2}}',
        r'{"name":1,"\u006eame":2}',
    ],
    ids=["same-container", "nested", "escaped-name"],
)
def test_duplicate_json_names_cannot_enter_current_field_originals(
    directory, column, raw
):
    original = field("title", "healthy", 10, "original")
    with writable(directory) as context:
        context.admit_field(original)
        before = context.candidates(KEY, "title")
        if column == "clock_json":
            from repo_catalog.domain.p1_context import FieldClock

            with pytest.raises(ValueError):
                FieldClock.from_json(raw)
        else:
            with pytest.raises(ValueError):
                replace(original, **{column: raw})
        columns = {
            "value_json": original.value_json,
            "clock_json": original.clock.encode(),
            "provenance_json": original.provenance_json,
        }
        columns[column] = raw
        with pytest.raises(sqlite3.IntegrityError):
            context.db.execute(
                "INSERT INTO field_candidates(service_instance_uuidv4,resource_kind,"
                "provider_resource_id,field_name,value_json,clock_json,provenance_json,"
                "observed_at_us) VALUES(?,?,?,?,?,?,?,?)",
                (
                    *KEY.coordinates(),
                    "title",
                    columns["value_json"],
                    columns["clock_json"],
                    columns["provenance_json"],
                    10,
                ),
            )
        assert context.candidates(KEY, "title") == before
        assert not context.db.execute("PRAGMA foreign_key_check").fetchall()


def test_equal_key_names_in_separate_containers_are_valid_current_field_data(directory):
    value = {"a": {"name": "A"}, "b": {"name": "B"}, "c": [{"name": "C"}]}
    original = field("structured-value", value, 10, "valid-nested-value")
    with writable(directory) as context:
        assert context.admit_field(original) == "insert"
    view = ContextQueryService(directory, mode="context_only").get_context_resource(KEY)
    assert json.loads(view.fields["structured-value"][0].value_json) == value
