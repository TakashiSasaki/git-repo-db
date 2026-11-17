"""Completion cannot strand allocations that need an open ledger to release."""

import pytest

from repo_catalog.adapters.sqlite.managed_git_cache import ManagedGitCache
from repo_catalog.adapters.sqlite.operations_admin import OperationsAdmin
from repo_catalog.domain.p1_coordination import CoordinationError
from tests.integration.auxiliary_rows.test_managed_git_cache_and_plans import (
    catalog as catalog,
)
from tests.integration.auxiliary_rows.test_managed_git_cache_and_plans import (
    create_request,
    rows,
)


@pytest.mark.parametrize("stopped", [False, True])
def test_completion_refuses_disk_allocation_until_explicit_release(catalog, stopped):
    request, attempt = create_request(catalog)
    other, other_attempt = create_request(catalog)
    policy = ManagedGitCache(catalog, max_bytes=100, ttl_seconds=0)
    admin = OperationsAdmin(catalog)
    policy.reserve(request, attempt, 100)
    if stopped:
        admin.transition(request)
    before = admin.show(request)
    progress = rows(catalog)
    with pytest.raises(CoordinationError) as error:
        admin.transition(request, complete=True)
    assert error.value.code == "CAPACITY_RESERVATION_ACTIVE"
    assert admin.show(request) == before
    assert rows(catalog) == progress
    with pytest.raises(CoordinationError) as error:
        policy.reserve(other, other_attempt, 1)
    assert error.value.code == "CAPACITY_WAIT"
    if stopped:
        admin.transition(request, resume=True)
    policy.release(request, attempt)
    released = rows(catalog)
    usage = admin.show(request)["budgets"]
    assert admin.transition(request, complete=True)["state"] == "complete"
    assert rows(catalog) == released
    assert admin.show(request)["budgets"] == usage
    assert policy.reserve(other, other_attempt, 100)["reserved_bytes"] == 100


def test_zero_byte_allocation_does_not_prevent_completion(catalog):
    request, attempt = create_request(catalog)
    policy = ManagedGitCache(catalog, max_bytes=0, ttl_seconds=0)
    policy.reserve(request, attempt, 0)
    assert (
        OperationsAdmin(catalog).transition(request, complete=True)["state"]
        == "complete"
    )
