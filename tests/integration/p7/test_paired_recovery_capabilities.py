"""Missing installed capabilities refuse before creating a paired destination."""

from importlib.util import find_spec

import pytest

from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.context_admission import (
    AdmissionRefused,
    AdmissionSelection,
)
from repo_catalog.domain.recovery import BackupScope, RecoveryCapabilityError


def test_context_own_selection_needs_no_exchange(monkeypatch):
    selection = AdmissionSelection(all_selected=True)
    imports = []

    def unavailable(name):
        imports.append(name)
        return None

    monkeypatch.setattr("importlib.util.find_spec", unavailable)
    assert AdmissionSelection.from_scope(selection) is selection
    assert not imports
    with pytest.raises(AdmissionRefused, match="INVALID_SELECTION"):
        AdmissionSelection.from_scope(object())
    assert imports == ["repo_catalog.domain.exchange"]
    assert find_spec("repo_catalog.domain.context_admission") is not None


@pytest.mark.parametrize("missing", ["operational", "search"])
def test_paired_capability_preflight_creates_no_output(
    synthetic_catalog, tmp_path, monkeypatch, missing
):
    original = p1_schema._resource

    def resource(name):
        if name == missing + ".sql":
            raise FileNotFoundError("synthetic unavailable schema capability")
        return original(name)

    monkeypatch.setattr(p1_schema, "_resource", resource)
    destination = tmp_path / "backup"
    service = RecoveryService()
    with pytest.raises(RecoveryCapabilityError, match=missing):
        service.create_consistent_backup(
            synthetic_catalog, destination, scope=BackupScope.PAIRED
        )
    assert not destination.exists()
    assert not service.is_stopped(synthetic_catalog)
    # The Git-only exemption still applies to the same installed integration.
    service.create_consistent_backup(
        synthetic_catalog, destination, scope=BackupScope.GIT_ONLY
    )
    assert destination.is_dir()
