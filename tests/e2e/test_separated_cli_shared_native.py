"""Two genuine native Sources share parent work and retain original capture scope."""

from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.application.git_acquisition import GitAcquisition
from repo_catalog.domain.git_acquisition import (
    GitNativeAcquisitionRequest,
    NotesAcquisitionSpec,
)
from repo_catalog.domain.p1_coordination import CoordinationError, RequestIdentity
from repo_catalog.domain.p1_core import CoreFailure
from tests.e2e.test_separated_cli import run
from tests.integration.p5.conftest import build_sample_git_repo, init_catalog_stores


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_shared_native_sources_keep_one_parent_budget_and_source_scoped_notes_captures(
    tmp_path, capsys, monkeypatch, fmt
):
    catalog = tmp_path / "catalog"
    repository, _ = init_catalog_stores(catalog, stores=("core", "operational"))
    paths = [tmp_path / "source-a", tmp_path / "source-b"]
    oids = [build_sample_git_repo(path, fmt) for path in paths]
    sources = [GitNativeSource(path) for path in paths]
    source_ids = [str(uuid4()), str(uuid4())]
    requests = [
        GitNativeAcquisitionRequest(
            repository,
            str(uuid4()),
            str(uuid4()),
            "explicit-local-source-" + str(index),
            1_700_000_500_000_000,
            select_object_oids=(objects["commit2"], objects["tag"]),
            retain_bytes=False,
            include_refs=True,
            notes=NotesAcquisitionSpec(
                discover_notes=True,
                acquire_inventories=True,
                target_object_oids=(objects["commit2"],),
                retain_note_bodies=True,
            ),
        )
        for index, objects in enumerate(oids)
    ]
    actual_metadata_reads = []
    original = GitNativeSource.metadata

    def measured(source, object_oid, work=None):
        actual_metadata_reads.append((source.path, object_oid))
        return original(source, object_oid, work)

    monkeypatch.setattr(GitNativeSource, "metadata", measured)
    parent = RequestIdentity(str(uuid4()), str(uuid4()))
    with OperationalAcquisitionLedger(catalog) as ledger:
        _, attempt, work, progress = ledger.create_budget(
            scope=["frozen-native-source-parent", 1], request=parent, new_request=True
        )
        app = GitAcquisition(catalog, operational=ledger)
        before = ledger.work_ledger.usage(parent)

        def execute(index, request=None, owner=None):
            return app.acquire_from_native_with_budget(
                sources[index],
                request or requests[index],
                source_registration_uuidv4=source_ids[index],
                ledger=owner or ledger,
                work=work,
                progress=progress,
                request_identity=parent,
            )

        first = execute(0)
        middle = ledger.work_ledger.usage(parent)
        second = execute(1)
        after = ledger.work_ledger.usage(parent)
        assert first.status == second.status == "complete"
        assert first.ref_note_acquisitions and second.ref_note_acquisitions
        assert all(
            item.role_verified and item.body_retained
            for report in (first, second)
            for item in report.ref_note_acquisitions
        )
        assert work.attempt_uuidv4 == attempt
        for unit in ("input_bytes", "verification_bytes", "metadata_units"):
            assert before[unit] < middle[unit] < after[unit]
        assert after["proof_steps"] >= middle["proof_steps"] > 0
        assert {path for path, _ in actual_metadata_reads} == set(paths)
        assert (
            first.ref_enumerations[0].event.identity
            != second.ref_enumerations[0].event.identity
        )
        replay = execute(0)
        assert (
            replay.ref_enumerations[0].event.identity
            == first.ref_enumerations[0].event.identity
        )
        assert replay.capture_uuidv4 == first.capture_uuidv4
        assert (
            ledger.work_ledger.usage(parent)["metadata_units"] > after["metadata_units"]
        )
        boundary = len(actual_metadata_reads)
        with pytest.raises(CoreFailure) as changed:
            execute(
                0, replace(requests[0], observed_at_us=requests[0].observed_at_us + 1)
            )
        assert changed.value.code == "INCOMPATIBLE_REPLAY"
        assert len(actual_metadata_reads) == boundary
        other = tmp_path / "unrelated-parent"
        init_catalog_stores(other, stores=("core", "operational"))
        with OperationalAcquisitionLedger(other) as foreign:
            with pytest.raises(CoordinationError):
                execute(0, owner=foreign)
        assert len(actual_metadata_reads) == boundary
    listed = run(capsys, "operations", "list", "--catalog", catalog)
    assert len(listed["requests"]) == 1
    assert listed["requests"][0]["request_uuidv4"] == parent.request_uuidv4
    assert not (catalog / "context.sqlite3").exists()
    assert not (catalog / "access.sqlite3").exists()


def test_one_native_source_supports_distinct_frozen_pr_units_without_child_budgets(
    tmp_path, capsys
):
    catalog = tmp_path / "catalog"
    repository, _ = init_catalog_stores(catalog, stores=("core", "operational"))
    objects = build_sample_git_repo(tmp_path / "native", "sha1")
    source = GitNativeSource(tmp_path / "native")
    source_id, parent = str(uuid4()), RequestIdentity(str(uuid4()), str(uuid4()))
    requests = [
        GitNativeAcquisitionRequest(
            repository,
            parent.request_origin_uuidv4,
            str(uuid4()),
            "explicit-shared-source",
            1_700_000_500_000_000 + index,
            select_object_oids=(objects["commit2"],),
        )
        for index in range(2)
    ]
    with OperationalAcquisitionLedger(catalog) as ledger:
        _, attempt, work, progress = ledger.create_budget(
            scope=["github-native-units", 1], request=parent, new_request=True
        )
        app = GitAcquisition(catalog, operational=ledger)

        def execute(index, *, request=None, unit_scope=None):
            return app.acquire_from_native_with_budget(
                source,
                request or requests[index],
                source_registration_uuidv4=source_id,
                ledger=ledger,
                work=work,
                progress=progress,
                request_identity=parent,
                unit_scope=unit_scope
                or ("pull-request", str(20 + index), "actual-pass"),
            )

        first = execute(0)
        middle = ledger.work_ledger.usage(parent)
        second = execute(1)
        after = ledger.work_ledger.usage(parent)
        assert first.status == second.status == "complete"
        assert first.capture_uuidv4 != second.capture_uuidv4
        assert (
            first.ref_enumerations[0].event.identity
            != second.ref_enumerations[0].event.identity
        )
        assert work.attempt_uuidv4 == attempt
        assert after["input_bytes"] > middle["input_bytes"] > 0
        assert after["metadata_units"] > middle["metadata_units"] > 0
        assert (
            execute(0).ref_enumerations[0].event.identity
            == first.ref_enumerations[0].event.identity
        )
        with pytest.raises(CoreFailure) as changed:
            execute(0, request=replace(requests[0], observed_at_us=123))
        assert changed.value.code == "INCOMPATIBLE_REPLAY"
        with pytest.raises(CoordinationError):
            execute(0, unit_scope=("x" * 4097,))
    assert len(run(capsys, "operations", "list", "--catalog", catalog)["requests"]) == 1
    assert not (catalog / "context.sqlite3").exists()
