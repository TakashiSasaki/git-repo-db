"""Current cache mutations require exact requests and the actual catalog gate."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.catalog_runtime import catalog_gate
from repo_catalog.adapters.sqlite.managed_git_cache import ManagedGitCache
from repo_catalog.adapters.sqlite.operations_admin import OperationsAdmin
from repo_catalog.domain.p1_coordination import CoordinationError, RequestIdentity
from tests.integration.auxiliary_rows.test_managed_git_cache_and_plans import (
    catalog as catalog,
)
from tests.integration.auxiliary_rows.test_managed_git_cache_and_plans import (
    create_request,
    git_cache,
    rows,
)


def test_cache_requires_exact_registered_request_and_attempt_without_mutation(catalog):
    request, attempt = create_request(catalog)
    path = git_cache(catalog)
    policy = ManagedGitCache(catalog, max_bytes=100000, ttl_seconds=0)
    before = rows(catalog)
    for wrong_request, wrong_attempt in (
        (request, str(uuid4())),
        (RequestIdentity(str(uuid4()), str(uuid4())), attempt),
    ):
        with pytest.raises(CoordinationError):
            policy.reserve(wrong_request, wrong_attempt, 1)
        with pytest.raises(CoordinationError):
            policy.register(wrong_request, wrong_attempt, "repository.git", 1)
    assert rows(catalog) == before
    assert (path / "HEAD").read_bytes() == b"ref: refs/heads/main\n"


def test_gc_cannot_cross_actual_catalog_gate_before_inventory_or_deletion(catalog):
    request, attempt = create_request(catalog)
    path = git_cache(catalog)
    policy = ManagedGitCache(catalog, max_bytes=100000, ttl_seconds=0)
    policy.register(request, attempt, "repository.git", 1)
    OperationsAdmin(catalog).transition(request, complete=True)
    before = rows(catalog)
    started = Event()

    def collect():
        started.set()
        return policy.collect(apply=True, now_us=2)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with catalog_gate(catalog, exclusive=True):
            pending = pool.submit(collect)
            assert started.wait(5)
            with pytest.raises(TimeoutError):
                pending.result(timeout=0.1)
            assert (path / "HEAD").exists()
            assert rows(catalog) == before
        result = pending.result(timeout=10)
    assert result["removed"] == [b"repository.git".hex()]
    assert not path.exists()
