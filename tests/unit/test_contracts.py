import base64
import copy

import pytest

from repo_catalog.config import DEFAULTS, validate
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


def test_config_budgets():
    cfg = copy.deepcopy(DEFAULTS)
    cfg["cache"].update(max_bytes=1000, min_free_bytes=0)
    assert validate(cfg) == cfg
    cfg["cache"]["low_water_ratio"] = 0.9
    with pytest.raises(CatalogError):
        validate(cfg)
