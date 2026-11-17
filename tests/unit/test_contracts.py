import base64

import pytest

from repo_catalog.adapters.sqlite.managed_git_cache import ManagedGitCache
from repo_catalog.domain.models import CatalogError, GitOid, path_fields


def test_oid_lengths_and_raw_path():
    assert len(GitOid.parse("sha256:" + "ab" * 32).value) == 32
    with pytest.raises(CatalogError):
        GitOid.parse("sha1:abc")
    raw = b"odd/\xff\tline\n.txt"
    fields = path_fields(raw)
    assert base64.b64decode(fields["path_b64"]) == raw
    assert fields["path_utf8"] is None
    assert "\n" not in fields["path_display"]


def test_current_cache_budgets_reject_nonfinite_and_negative_settings(tmp_path):
    cache = ManagedGitCache(tmp_path, max_bytes=1000, min_free_bytes=0, ttl_seconds=60)
    assert cache.max_bytes == 1000 and cache.min_free_bytes == 0
    for key in ("max_bytes", "min_free_bytes", "ttl_seconds", "max_entries"):
        for value in (True, 1.5, -1):
            args = {
                "max_bytes": 1000,
                "min_free_bytes": 0,
                "ttl_seconds": 60,
                key: value,
            }
            with pytest.raises(ValueError):
                ManagedGitCache(tmp_path, **args)
    assert list(tmp_path.iterdir()) == []
