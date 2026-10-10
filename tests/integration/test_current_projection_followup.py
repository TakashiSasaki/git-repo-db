"""Sparse observations retain their own clocks, including portable projections."""

import pytest

from tests.integration.test_current_resources import (  # noqa: F401
    current,
    issue,
)
from tests.integration.test_current_resources import (
    resources as _resources_fixture,
)
from tests.support.sqlite_contracts import assert_absent_tables


@pytest.fixture(name="resources")
def _resources(tmp_path):
    yield from _resources_fixture.__wrapped__(tmp_path)


def test_sparse_then_full_same_clock_does_not_invent_body_conflict(resources):
    adapter, *_ = resources
    adapter.admit(issue(resources, title="old", body="old"), source="import")
    partial = issue(resources, title="new", provider_updated_at_us=20)
    partial.pop("body")
    assert adapter.admit(partial, source="import").status == "accepted"
    assert (
        adapter.admit(
            issue(resources, title="new", body="new", provider_updated_at_us=20),
            source="import",
        ).status
        == "accepted"
    )
    assert current(adapter)["body"] == "new"
    assert (
        adapter.c.execute("SELECT count(*) FROM eligible_issue_resources").fetchone()[0]
        == 1
    )


def test_older_full_can_fill_a_field_not_observed_in_newer_partial(resources):
    adapter, *_ = resources
    first = issue(resources, title="new", provider_updated_at_us=20)
    first.pop("body")
    adapter.admit(first, source="import")
    assert (
        adapter.admit(
            issue(
                resources,
                title="old",
                body="known older body",
                provider_updated_at_us=10,
            ),
            source="import",
        ).status
        == "accepted"
    )
    assert current(adapter)["title"] == "new"
    assert current(adapter)["body"] == "known older body"


def test_initial_and_changed_live_checks_advance_local_check_time(resources):
    adapter, *_ = resources
    for observed, body in ((100, "first"), (200, "first"), (300, "changed")):
        value = issue(
            resources,
            body=body,
            observed_at_us=observed,
            provider_updated_at_us=observed,
        )
        revision, scope = adapter.capture_context(value["acquisition_scope"])
        adapter.admit(value, source="live", base_revision=revision, scope_context=scope)
        assert current(adapter)["last_checked_at_us"] == observed


def test_imported_sender_check_is_not_a_receiver_local_check(resources):
    adapter, *_ = resources
    adapter.admit(issue(resources, last_checked_at_us=900), source="import")
    assert current(adapter)["last_checked_at_us"] is None


@pytest.mark.parametrize("reverse", [False, True])
def test_partial_fields_keep_actual_parser_when_another_version_updates_row(
    resources, reverse
):
    adapter, *_ = resources
    older = issue(
        resources,
        body="old body",
        title="old title",
        metadata={},
        parser_module="tests.synthetic.body_parser",
        parser_version="9",
        provider_updated_at_us=10,
    )
    newer = issue(
        resources,
        title="new title",
        metadata={},
        parser_module="tests.synthetic.title_parser",
        parser_version="0",
        provider_updated_at_us=20,
    )
    newer.pop("body")
    for observation in (newer, older) if reverse else (older, newer):
        assert adapter.admit(observation, source="import").status == "accepted"
    row = current(adapter)
    assert row["body"] == "old body"
    assert row["title"] == "new title"
    evidence = row["field_evidence"]
    assert (
        evidence['["body"]']["parser_module"],
        evidence['["body"]']["parser_version"],
    ) == ("tests.synthetic.body_parser", "9")
    assert (
        evidence['["title"]']["parser_module"],
        evidence['["title"]']["parser_version"],
    ) == ("tests.synthetic.title_parser", "0")
    assert_absent_tables(adapter.c, "parser_profiles")
    assert_absent_tables(adapter.c, "fetch_occurrences")
