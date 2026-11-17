"""GC authorization belongs to the registered object and complete inventory."""

import pytest

from repo_catalog.adapters.sqlite import managed_git_cache as cache_module
from repo_catalog.adapters.sqlite.managed_git_cache import ManagedGitCache
from repo_catalog.adapters.sqlite.operations_admin import OperationsAdmin
from tests.integration.auxiliary_rows.test_managed_git_cache_and_plans import (
    catalog as catalog,
)
from tests.integration.auxiliary_rows.test_managed_git_cache_and_plans import (
    create_request,
    git_cache,
    rows,
)


def files(root):
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize(
    "change", ["replacement-root", "changed-file", "replacement-child-directory"]
)
def test_changed_or_replaced_registered_cache_is_retained_and_touch_cannot_adopt(
    catalog, change
):
    request, attempt = create_request(catalog)
    managed = git_cache(catalog)
    policy = ManagedGitCache(catalog, max_bytes=100000, ttl_seconds=0)
    entry = policy.register(request, attempt, "repository.git", 1)
    original_progress = rows(catalog)
    if change == "replacement-root":
        managed.rename(managed.with_name("original-managed-aside.git"))
        managed.mkdir()
        (managed / "HEAD").write_bytes(b"unmanaged replacement input")
        (managed / "unmanaged-source.txt").write_bytes(b"source sentinel must survive")
    elif change == "changed-file":
        (managed / "objects" / "metadata.pack").write_bytes(
            b"changed input must be retained"
        )
    else:
        (managed / "objects").rename(managed / "original-objects")
        (managed / "objects").mkdir()
        (managed / "objects" / "unmanaged-source.txt").write_bytes(
            b"new directory is not registered"
        )
    before = files(catalog / "cache")
    assert policy.reuse("repository.git")["availability"] == "reuse_unavailable"
    with pytest.raises(ValueError, match="registered cache changed"):
        policy.touch(request, attempt, "repository.git", 2)
    with pytest.raises(ValueError, match="registered cache changed"):
        policy.register(request, attempt, "repository.git", 2)
    assert rows(catalog) == original_progress
    OperationsAdmin(catalog).transition(request, complete=True)
    result = policy.collect(apply=True, now_us=3)
    assert not result["removed"]
    assert entry["path_hex"] in result["retained"]
    assert files(catalog / "cache") == before
    if change == "replacement-root":
        assert (
            managed / "unmanaged-source.txt"
        ).read_bytes() == b"source sentinel must survive"


def test_all_targets_preflight_before_any_unlink(catalog, monkeypatch):
    request, attempt = create_request(catalog)
    managed = git_cache(catalog)
    policy = ManagedGitCache(catalog, max_bytes=100000, ttl_seconds=0)
    policy.register(request, attempt, "repository.git", 1)
    OperationsAdmin(catalog).transition(request, complete=True)
    before = rows(catalog)
    original = cache_module._preflight

    def change_last_target(root, parts, identity, nodes):
        # HEAD sorts first; the changed object is later in the inventory. A
        # per-target check/unlink loop would already have destroyed HEAD.
        (managed / "objects" / "metadata.pack").write_bytes(
            b"concurrent changed source"
        )
        return original(root, parts, identity, nodes)

    monkeypatch.setattr(cache_module, "_preflight", change_last_target)
    with pytest.raises(ValueError, match="target changed"):
        policy.collect(apply=True, now_us=2)
    assert (managed / "HEAD").read_bytes() == b"ref: refs/heads/main\n"
    assert (
        managed / "objects" / "metadata.pack"
    ).read_bytes() == b"concurrent changed source"
    assert rows(catalog) == before
