"""Sparse observations retain their own clocks, including portable projections."""

import pytest

from tests.integration.test_current_resources import (  # noqa: F401
    current,
    issue,
)
from tests.integration.test_current_resources import (
    resources as _resources_fixture,
)


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
