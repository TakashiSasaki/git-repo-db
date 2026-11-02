"""Native acquisition rejects volatile and unrelated injected accounting."""

from contextlib import ExitStack, closing
from unittest.mock import patch
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.sqlite.acquisition import (
    InMemoryNotesProgress,
    OperationalAcquisitionLedger,
    UnlimitedWorkBudget,
)
from repo_catalog.adapters.sqlite.catalog_runtime import persist_catalog_stop
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.notes import NotesProgress
from repo_catalog.adapters.sqlite.operational_coordination import NotesWorkBudget
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.application.git_acquisition import GitAcquisition
from repo_catalog.domain.git_acquisition import (
    GitMetadataInput,
    GitNativeAcquisitionRequest,
)
from repo_catalog.domain.p1_coordination import (
    CoordinationError,
    RequestIdentity,
)
from tests.integration.p5.conftest import build_sample_git_repo


@pytest.fixture
def native_case(tmp_path):
    objects = build_sample_git_repo(tmp_path / "git", "sha1")
    source = GitNativeSource(tmp_path / "git")
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    repository, instance = str(uuid4()), str(uuid4())
    initialize(catalog / "core.sqlite3", "core", repository, instance)
    request = GitNativeAcquisitionRequest(
        repository,
        str(uuid4()),
        str(uuid4()),
        "synthetic-local",
        1700000000000000,
        select_object_oids=(objects["commit2"],),
        include_refs=False,
    )
    return catalog, source, request, instance


@pytest.mark.parametrize(
    "fault",
    ["volatile", "foreign", "mixed_progress", "constructor_progress", "fake_ledger"],
)
def test_invalid_native_accounting_refuses_before_git_and_admission(
    native_case, tmp_path, fault
):
    catalog, source, request, instance = native_case
    identity = RequestIdentity(request.capture_origin_uuidv4, request.capture_uuidv4)
    scope = ["p5-git-native", request.repository_uuidv4, *identity.values()]
    with ExitStack() as stack:
        if fault == "volatile":
            work, progress = UnlimitedWorkBudget(), InMemoryNotesProgress()
        elif fault == "fake_ledger":

            class Fake:
                def store_identity(self):
                    raise AssertionError("caller claimed durability")

            work = object.__new__(NotesWorkBudget)
            work.ledger = Fake()
            progress = NotesProgress(work)
        else:
            path = (
                tmp_path / "foreign.sqlite3"
                if fault == "foreign"
                else catalog / "operational.sqlite3"
            )
            initialize(
                path,
                "operational",
                str(uuid4()) if fault == "foreign" else request.repository_uuidv4,
                instance,
            )
            ledger = stack.enter_context(OperationalAcquisitionLedger(path))
            _, _, work, progress = ledger.create_budget(
                scope=scope, request=identity, new_request=True
            )
            if fault == "mixed_progress":
                _, _, _, progress = ledger.create_budget(scope=scope, new_request=True)
        with patch(
            "subprocess.Popen",
            side_effect=AssertionError("Git before accounting validation"),
        ):
            with pytest.raises(CoordinationError) as failure:
                if fault == "constructor_progress":
                    GitAcquisition(
                        catalog, operational=catalog, progress=InMemoryNotesProgress()
                    ).acquire_from_native(source, request)
                else:
                    GitAcquisition(catalog).acquire_from_native(
                        source, request, work=work, progress=progress
                    )
        assert failure.value.code == (
            "STORE_IDENTITY" if fault == "foreign" else "CONTINUATION_UNAVAILABLE"
        )
    with closing(GitCore(catalog / "core.sqlite3")) as core:
        assert core.sql("SELECT count(*) FROM git_objects")[0][0] == 0
    assert not (catalog / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("metadata", [False, True])
def test_owned_core_cleanup_stop_prevents_normal_completion(
    native_case, monkeypatch, metadata
):
    catalog, source, request, instance = native_case
    initialize(
        catalog / "operational.sqlite3",
        "operational",
        request.repository_uuidv4,
        instance,
    )
    original = GitCore.close

    def stopped(core):
        original(core)
        persist_catalog_stop(catalog, "synthetic acquisition cleanup stop")

    monkeypatch.setattr(GitCore, "close", stopped)
    service = GitAcquisition(catalog, operational=catalog)
    with pytest.raises(CoordinationError) as failure:
        if metadata:
            unit = GitMetadataInput(
                repository_uuidv4=request.repository_uuidv4,
                object_format="sha1",
                capture_origin_uuidv4=request.capture_origin_uuidv4,
                capture_uuidv4=request.capture_uuidv4,
                source_attribution=request.source_attribution,
                observed_at_us=request.observed_at_us,
            )
            service.acquire_metadata_only(unit, new_request=True)
        else:
            service.acquire_from_native(source, request, new_request=True)
    assert failure.value.code == "RECOVERY_REQUIRED"
    assert (catalog / "p1-recovery-stop.json").exists()


def test_explicit_custom_durable_request_retains_cumulative_expenditure(native_case):
    catalog, source, request, instance = native_case
    initialize(
        catalog / "operational.sqlite3",
        "operational",
        request.repository_uuidv4,
        instance,
    )
    custom = RequestIdentity(str(uuid4()), str(uuid4()))
    scope = [
        "p5-git-native",
        request.repository_uuidv4,
        request.capture_origin_uuidv4,
        request.capture_uuidv4,
    ]
    with OperationalAcquisitionLedger(catalog / "operational.sqlite3") as ledger:
        _, _, work, progress = ledger.create_budget(
            scope=scope, request=custom, new_request=True
        )
        service = GitAcquisition(catalog)
        with pytest.raises(CoordinationError) as failure:
            service.acquire_from_native(source, request, work=work, progress=progress)
        assert failure.value.code == "REQUEST_SCOPE"
        first = service.acquire_from_native(
            source, request, work=work, progress=progress, request_identity=custom
        )
        spent = ledger.work_ledger.usage(custom)["input_bytes"]
        assert first.status == "complete" and spent > 0
        second = service.acquire_from_native(
            source,
            request,
            work=work,
            progress=progress,
            request_identity=custom,
            new_request=True,
        )
        assert (
            second.status == "complete"
            and ledger.work_ledger.usage(custom)["input_bytes"] > spent
        )
    assert not (catalog / "p1-recovery-stop.json").exists()
