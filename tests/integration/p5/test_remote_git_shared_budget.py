"""Real remote sources share parent transport/Git/Notes accounting and replay."""

from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.remote import _OVERHEAD
from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.application.git_acquisition import GitAcquisition
from repo_catalog.application.remote_git_acquisition import (
    acquire_remote_git_with_budget,
)
from repo_catalog.domain.p1_coordination import CoordinationError, RequestIdentity
from repo_catalog.domain.p1_core import CoreFailure
from tests.integration.p5.conftest import build_sample_git_repo, init_catalog_stores
from tests.integration.p5.test_separated_remote_git import git_http, request


def test_real_remote_sources_share_parent_work_and_original_capture_across_temporary_caches(
    tmp_path,
):
    objects = build_sample_git_repo(tmp_path / "repository.git")
    catalog = tmp_path / "catalog"
    repository, _ = init_catalog_stores(catalog, stores=("core", "operational"))
    parent = RequestIdentity(str(uuid4()), str(uuid4()))
    sources = [str(uuid4()), str(uuid4())]
    native = [request(repository, objects), request(repository, objects)]
    with (
        git_http(tmp_path) as (base, events),
        OperationalAcquisitionLedger(catalog) as ledger,
    ):
        _, attempt, work, progress = ledger.create_budget(
            scope=["frozen-mixed-source-parent", 1], request=parent, new_request=True
        )
        document = {
            "locator": base + "/repository.git",
            "object_format": "sha1",
            "transfer_bytes": 1024 * 1024,
            "request_identity": parent,
            "new_request": False,
        }

        def execute(index, **changes):
            return acquire_remote_git_with_budget(
                catalog,
                {**document, "request": native[index], **changes},
                source_registration_uuidv4=sources[index],
                ledger=ledger,
                work=work,
                progress=progress,
                request_identity=parent,
            )

        first = execute(0)
        first_bytes = sum(event["bytes"] for event in events)
        middle = ledger.work_ledger.usage(parent)
        second = execute(1)
        after = ledger.work_ledger.usage(parent)
        assert first.transfer_body_bytes == first_bytes > 0
        assert (
            second.transfer_body_bytes
            == sum(event["bytes"] for event in events) - first_bytes
        )
        assert first.git_report.status == second.git_report.status == "complete"
        assert (
            first.git_report.ref_note_acquisitions
            and second.git_report.ref_note_acquisitions
        )
        assert (
            first.git_report.ref_enumerations[0].event.identity
            != second.git_report.ref_enumerations[0].event.identity
        )
        for unit in ("input_bytes", "verification_bytes", "metadata_units"):
            assert 0 < middle[unit] < after[unit]
        assert after["proof_steps"] >= middle["proof_steps"] > 0
        assert work.attempt_uuidv4 == attempt
        replay = execute(0)
        assert replay.git_report.capture_uuidv4 == native[0].capture_uuidv4
        assert (
            replay.git_report.ref_enumerations[0].event.identity
            == first.git_report.ref_enumerations[0].event.identity
        )
        assert ledger.work_ledger.usage(parent)["input_bytes"] > after["input_bytes"]
        boundary = len(events)
        for changes in (
            {"username": "different-principal"},
            {"refspecs": ["+refs/heads/main:refs/heads/main"]},
            {
                "request": replace(
                    native[0], observed_at_us=native[0].observed_at_us + 1
                )
            },
        ):
            with pytest.raises(CoreFailure) as error:
                execute(0, **changes)
            assert error.value.code == "INCOMPATIBLE_REPLAY"
        assert len(events) == boundary
        assert (
            ledger.db.execute("SELECT count(*) FROM acquisition_requests").fetchone()[0]
            == 1
        )
    assert not (catalog / "context.sqlite3").exists()


def test_parent_cumulative_transfer_bound_cannot_be_reset_for_next_remote_source(
    tmp_path,
):
    objects = build_sample_git_repo(tmp_path / "repository.git")
    catalog = tmp_path / "catalog"
    repository, _ = init_catalog_stores(catalog, stores=("core", "operational"))
    parent = RequestIdentity(str(uuid4()), str(uuid4()))
    with (
        git_http(tmp_path) as (base, events),
        OperationalAcquisitionLedger(catalog) as ledger,
    ):
        _, _, work, progress = ledger.create_budget(
            scope=["finite-mixed-parent"],
            request=parent,
            new_request=True,
            work_limits={"input_bytes": 1024 * 1024 + _OVERHEAD},
        )
        document = {
            "locator": base + "/repository.git",
            "object_format": "sha1",
            "transfer_bytes": 1024 * 1024,
            "request": request(repository, objects, notes=False),
        }
        result = acquire_remote_git_with_budget(
            catalog,
            document,
            source_registration_uuidv4=str(uuid4()),
            ledger=ledger,
            work=work,
            progress=progress,
            request_identity=parent,
        )
        assert result.git_report.status == "complete"
        before = ledger.work_ledger.usage(parent)
        boundary = len(events)
        with pytest.raises(CoreFailure) as error:
            acquire_remote_git_with_budget(
                catalog,
                {**document, "request": request(repository, objects, notes=False)},
                source_registration_uuidv4=str(uuid4()),
                ledger=ledger,
                work=work,
                progress=progress,
                request_identity=parent,
            )
        assert error.value.code == "BUDGET" and len(events) == boundary
        assert (
            ledger.work_ledger.usage(parent)["input_bytes"]
            >= before["input_bytes"]
            > result.transfer_body_bytes
        )
        assert (
            ledger.db.execute("SELECT count(*) FROM acquisition_requests").fetchone()[0]
            == 1
        )
    assert not (catalog / "p1-recovery-stop.json").exists()


def test_remote_shared_hook_refuses_foreign_parent_capabilities_and_child_accounting_before_network(
    tmp_path,
):
    objects = build_sample_git_repo(tmp_path / "repository.git")
    catalog, other = tmp_path / "catalog", tmp_path / "other"
    repository, _ = init_catalog_stores(catalog, stores=("core", "operational"))
    init_catalog_stores(other, stores=("core", "operational"))
    parent = RequestIdentity(str(uuid4()), str(uuid4()))
    source = str(uuid4())
    with (
        git_http(tmp_path) as (base, events),
        OperationalAcquisitionLedger(catalog) as ledger,
        OperationalAcquisitionLedger(other) as foreign,
    ):
        _, _, work, progress = ledger.create_budget(
            scope=["checked-parent"], request=parent, new_request=True
        )
        document = {
            "locator": base + "/repository.git",
            "object_format": "sha1",
            "request": request(repository, objects),
        }

        def execute(doc=document, **overrides):
            return acquire_remote_git_with_budget(
                catalog,
                doc,
                **{
                    "source_registration_uuidv4": source,
                    "ledger": ledger,
                    "work": work,
                    "progress": progress,
                    "request_identity": parent,
                    **overrides,
                },
            )

        with pytest.raises(CoordinationError):
            execute(ledger=foreign)
        with pytest.raises(CoordinationError):
            execute(request_identity=RequestIdentity(str(uuid4()), str(uuid4())))
        with pytest.raises(CoordinationError):
            execute(progress=object())
        for changes in (
            {"new_request": True},
            {"work_limits": {"input_bytes": 100000000}},
            {"request_identity": [str(uuid4()), str(uuid4())]},
        ):
            with pytest.raises((CoreFailure, CoordinationError)):
                execute({**document, **changes})
        assert events == []
        assert (
            ledger.db.execute("SELECT count(*) FROM acquisition_requests").fetchone()[0]
            == 1
        )


def test_remote_units_share_frozen_transport_and_trusted_handler_uses_live_cache_without_child_budgets(
    tmp_path,
):
    objects = build_sample_git_repo(tmp_path / "repository.git")
    catalog = tmp_path / "catalog"
    repository, _ = init_catalog_stores(catalog, stores=("core", "operational"))
    parent = RequestIdentity(str(uuid4()), str(uuid4()))
    source, service, traversal = str(uuid4()), str(uuid4()), str(uuid4())
    requests = [
        request(repository, objects, notes=False),
        request(repository, objects, notes=False),
    ]
    paths = []
    with (
        git_http(tmp_path) as (base, events),
        OperationalAcquisitionLedger(catalog) as ledger,
    ):
        _, _, work, progress = ledger.create_budget(
            scope=["actual-paired-parent"], request=parent, new_request=True
        )

        def execute(index, **changes):
            unit = ("github-pr", service, '"' + str(100 + index) + '"', traversal)

            def handle(actual):
                assert actual.path.is_dir()
                paths.append(actual.path)
                return GitAcquisition(
                    catalog, operational=ledger
                ).acquire_from_native_with_budget(
                    actual,
                    requests[index],
                    source_registration_uuidv4=source,
                    ledger=ledger,
                    work=work,
                    progress=progress,
                    request_identity=parent,
                    unit_scope=unit + ("metadata",),
                )

            return acquire_remote_git_with_budget(
                catalog,
                {
                    "locator": base + "/repository.git",
                    "object_format": "sha1",
                    "request": requests[index],
                    "transfer_bytes": 1024 * 1024,
                    **changes,
                },
                source_registration_uuidv4=source,
                ledger=ledger,
                work=work,
                progress=progress,
                request_identity=parent,
                unit_scope=unit,
                source_handler=handle,
            )

        first, second = execute(0), execute(1)
        assert first.git_report.status == second.git_report.status == "complete"
        assert first.git_report.capture_uuidv4 != second.git_report.capture_uuidv4
        before = ledger.work_ledger.usage(parent)
        replay = execute(0)
        assert replay.git_report.capture_uuidv4 == first.git_report.capture_uuidv4
        assert ledger.work_ledger.usage(parent)["input_bytes"] > before["input_bytes"]
        boundary = len(events)
        with pytest.raises(CoreFailure) as error:
            execute(1, username="changed-source-principal")
        assert error.value.code == "INCOMPATIBLE_REPLAY" and len(events) == boundary
        assert (
            ledger.db.execute("SELECT count(*) FROM acquisition_requests").fetchone()[0]
            == 1
        )
    assert len(paths) == len(set(paths)) == 3
    assert all(not path.exists() for path in paths)
