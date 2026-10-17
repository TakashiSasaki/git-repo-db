"""Maintenance inputs reject ambiguous identities and unbounded resources."""

from dataclasses import replace

import pytest

from repo_catalog.domain.access_backup import AccessBackupLimits, ScopeFork
from repo_catalog.domain.access_registry import (
    AccessRegistryError,
    AccessScope,
    ScopeLocatorRegistration,
)

S1 = "550e8400-e29b-41d4-a716-446655440000"
S2 = "650e8400-e29b-41d4-a716-446655440000"


@pytest.mark.parametrize("field", ["max_bytes", "max_rows", "timeout_seconds"])
@pytest.mark.parametrize("bad", [0, -1, None, True, 1.5, "10", 2**63])
def test_limits(field, bad):
    with pytest.raises(AccessRegistryError):
        replace(AccessBackupLimits(), **{field: bad})


def test_limits_positive_edges():
    assert AccessBackupLimits(1, 1, 1).max_rows == 1
    assert AccessBackupLimits(2**63 - 1, 2**63 - 1, 2**63 - 1).max_rows == 2**63 - 1


@pytest.mark.parametrize(
    "kind",
    [
        "same",
        "other-registration",
        "bad-source",
        "untyped-target",
        "untyped-registration",
    ],
)
def test_fork_identity(kind):
    source, target, reg = (
        S1,
        AccessScope(S2),
        ScopeLocatorRegistration(S2, 10, "file:///fork"),
    )
    if kind == "same":
        source = S2
    if kind == "other-registration":
        reg = ScopeLocatorRegistration(S1, 10, "file:///fork")
    if kind == "bad-source":
        source = "host"
    if kind == "untyped-target":
        target = S2
    if kind == "untyped-registration":
        reg = reg.key
    with pytest.raises(AccessRegistryError):
        ScopeFork(source, target, reg)
