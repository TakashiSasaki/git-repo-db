"""A trusted immutable-root walk derives metadata selection inside actual work."""

from uuid import uuid4

import pytest

from repo_catalog.adapters.git.metadata_walk import NativeMetadataWalk
from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.application.git_acquisition import GitAcquisition
from repo_catalog.domain.git_acquisition import GitNativeAcquisitionRequest
from repo_catalog.domain.p1_coordination import RequestIdentity
from repo_catalog.domain.p1_core import CoreFailure, encode
from tests.integration.p5.conftest import build_sample_git_repo, init_catalog_stores


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_trusted_native_walk_retains_full_metadata_closure_once_without_blob_reads(
    tmp_path, monkeypatch, fmt
):
    catalog, path = tmp_path / "catalog", tmp_path / "native"
    repository, _ = init_catalog_stores(catalog, stores=("core", "operational"))
    objects = build_sample_git_repo(path, fmt)
    source, source_id = GitNativeSource(path), str(uuid4())
    parent = RequestIdentity(str(uuid4()), str(uuid4()))
    request = GitNativeAcquisitionRequest(
        repository,
        parent.request_origin_uuidv4,
        str(uuid4()),
        "explicit-native-source",
        1_700_000_500_000_000,
        select_object_oids=(objects["commit2"],),
        include_refs=True,
        ref_prefixes=("refs/heads/",),
    )
    reads, ref_events = [], []
    original = GitNativeSource.metadata

    def measured(instance, oid, work=None):
        assert oid not in {objects["blob"], objects["note_blob"]}
        reads.append(oid)
        return original(instance, oid, work)

    monkeypatch.setattr(GitNativeSource, "metadata", measured)
    with OperationalAcquisitionLedger(catalog) as ledger:
        _, _, work, progress = ledger.create_budget(
            scope=["actual-git-role-walk", 1], request=parent, new_request=True
        )
        app = GitAcquisition(catalog, operational=ledger)
        report = app.acquire_from_native_with_budget(
            source,
            request,
            source_registration_uuidv4=source_id,
            ledger=ledger,
            work=work,
            progress=progress,
            request_identity=parent,
            unit_scope=("actual-role-unit",),
            metadata_walk=NativeMetadataWalk(source, request.select_object_oids),
            after_ref_scan=lambda events: ref_events.extend(events),
        )
        assert report.status == "complete"
        expected = {objects[name] for name in ("commit1", "commit2", "tree")}
        assert set(report.retained_objects) == expected
        assert set(reads) == expected and len(reads) == len(expected)
        assert ref_events and ref_events[0].links
        intent = progress.load(
            encode(
                [
                    "frozen-native-source",
                    source_id,
                    "operation",
                    ["actual-role-unit"],
                    "intent",
                ]
            )
        )
        assert intent["selected"] == [list(objects["commit2"].key)]
        assert intent["metadata_walk"] == ["native-metadata-closure", 1, 100_000]
        assert objects["commit1"].object_oid not in encode(intent)
        assert objects["tree"].object_oid not in encode(intent)
        before = len(reads)
        with pytest.raises(CoreFailure) as changed:
            app.acquire_from_native_with_budget(
                source,
                request,
                source_registration_uuidv4=source_id,
                ledger=ledger,
                work=work,
                progress=progress,
                request_identity=parent,
                unit_scope=("actual-role-unit",),
                metadata_walk=NativeMetadataWalk(
                    source, request.select_object_oids, 10
                ),
            )
        assert changed.value.code == "INCOMPATIBLE_REPLAY" and len(reads) == before
    assert not (catalog / "context.sqlite3").exists()
