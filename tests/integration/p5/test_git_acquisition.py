"""P5 integration tests for metadata-first and selective native Git + Notes acquisition."""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.application.acquisition import GitAcquisition
from repo_catalog.domain.acquisition import (
    GitMetadataInput,
    GitNativeAcquisitionRequest,
    NotesAcquisitionSpec,
)
from repo_catalog.domain.p1_coordination import CoordinationError, RequestIdentity
from repo_catalog.domain.p1_core import (
    OID,
    CoreCoverageScope,
    CoreFailure,
    Provenance,
    RepositoryClaim,
    ScalarClaim,
    encode,
)
from tests.integration.p5.conftest import build_sample_git_repo, init_catalog_stores


def test_git_acquisition_metadata_only_and_retained_modes(
    tmp_path: Path,
    git_format: Literal["sha1", "sha256"],
) -> None:
    repo_dir = tmp_path / "repo"
    oids = build_sample_git_repo(repo_dir, git_format)
    source = GitNativeSource(repo_dir)

    # 1. Metadata-only acquisition (retain_bytes=False)
    cat_meta = tmp_path / "cat_meta"
    repo_uuid, _ = init_catalog_stores(cat_meta, stores=("core", "operational"))
    origin_uuid = str(uuid4())
    cap_uuid = str(uuid4())

    req_meta = GitNativeAcquisitionRequest(
        repository_uuidv4=repo_uuid,
        capture_origin_uuidv4=origin_uuid,
        capture_uuidv4=cap_uuid,
        source_attribution="local-git-test",
        observed_at_us=1_700_000_500_000_000,
        select_oids=(oids["commit1"], oids["commit2"], oids["tree"], oids["tag"]),
        retain_bytes=False,
        include_refs=True,
    )
    acq_meta = GitAcquisition(cat_meta, operational=cat_meta)
    report_meta = acq_meta.acquire_from_native(source, req_meta)

    assert report_meta.status == "complete"
    assert report_meta.object_format == git_format
    assert report_meta.retained_objects == ()
    assert oids["commit2"] in report_meta.metadata_only_objects
    assert oids["blob"] in report_meta.admitted_objects
    assert len(report_meta.ref_observations) == 1

    core_meta = GitCore(cat_meta / "core.sqlite3")
    try:
        # Zero retained_metadata rows in metadata-only mode
        assert core_meta.sql("SELECT COUNT(*) FROM retained_metadata")[0][0] == 0
        with pytest.raises(CoreFailure) as exc_info:
            core_meta.read_metadata(oids["commit2"])
        assert exc_info.value.code == "BYTES_UNAVAILABLE"

        # Scalar claims and relations are present as reported facts
        msg_proj = core_meta.scalar(oids["commit2"], "message")
        assert msg_proj.canonical is None  # no receiver_intrinsic copy
        assert len(msg_proj.alternatives) == 1
        assert msg_proj.alternatives[0]["value"] == ["known", "Second commit\n"]
        assert msg_proj.alternatives[0]["checked"] is False

        parents_proj = core_meta.relations(oids["commit2"], "commit_parents")
        assert len(parents_proj.alternatives) == 1
        assert parents_proj.alternatives[0]["membership"] == [
            [0, git_format, oids["commit1"].full_oid]
        ]
    finally:
        core_meta.close()

    # 2. Hybrid mode (retain_oids={commit2, tag}) + P4 Notes discovery/inventory/note body
    cat_hybrid = tmp_path / "cat_hybrid"
    init_catalog_stores(
        cat_hybrid,
        repository_uuidv4=repo_uuid,
        stores=("core", "operational"),
    )
    notes_spec = NotesAcquisitionSpec(
        discover_notes=True,
        acquire_inventories=True,
        target_oids=(oids["commit2"],),
        retain_note_bodies=True,
    )
    req_hybrid = GitNativeAcquisitionRequest(
        repository_uuidv4=repo_uuid,
        capture_origin_uuidv4=origin_uuid,
        capture_uuidv4=str(uuid4()),
        source_attribution="local-git-test",
        observed_at_us=1_700_000_600_000_000,
        select_oids=(oids["commit1"], oids["commit2"], oids["tree"], oids["tag"]),
        retain_bytes=False,
        retain_oids=frozenset({oids["commit2"], oids["tag"]}),
        notes=notes_spec,
    )
    acq_hybrid = GitAcquisition(cat_hybrid, operational=cat_hybrid)
    report_hybrid = acq_hybrid.acquire_from_native(source, req_hybrid)

    assert set(report_hybrid.retained_objects) == {oids["commit2"], oids["tag"]}
    assert oids["commit1"] in report_hybrid.metadata_only_objects
    assert oids["tree"] in report_hybrid.metadata_only_objects
    assert len(report_hybrid.notes_discoveries) == 1
    assert len(report_hybrid.notes_inventories) == 1
    assert len(report_hybrid.note_acquisitions) == 1
    assert report_hybrid.note_acquisitions[0].role_verified is True
    assert report_hybrid.note_acquisitions[0].body_retained is True

    core_hybrid = GitCore(cat_hybrid / "core.sqlite3")
    try:
        assert core_hybrid.read_metadata(oids["commit2"]).startswith(b"tree ")
        with pytest.raises(CoreFailure) as exc_info:
            core_hybrid.read_metadata(oids["commit1"])
        assert exc_info.value.code == "BYTES_UNAVAILABLE"

        cap = report_hybrid.notes_discoveries[0].captures[0]
        assert (
            core_hybrid.read_note(cap, oids["commit2"], oids["note_blob"])
            == b"Reviewed-by: CI\n"
        )
    finally:
        core_hybrid.close()


def test_git_acquisition_rejects_ordinary_file_blob_and_handles_missing_oids(
    tmp_path: Path,
    git_format: Literal["sha1", "sha256"],
) -> None:
    repo_dir = tmp_path / "repo"
    oids = build_sample_git_repo(repo_dir, git_format)
    source = GitNativeSource(repo_dir)

    cat_dir = tmp_path / "cat"
    repo_uuid, _ = init_catalog_stores(cat_dir, stores=("core", "operational"))
    acq = GitAcquisition(cat_dir, operational=cat_dir)

    # Ordinary file blob requested as metadata object is rejected with RETENTION_PURPOSE
    bad_req = GitNativeAcquisitionRequest(
        repository_uuidv4=repo_uuid,
        capture_origin_uuidv4=str(uuid4()),
        capture_uuidv4=str(uuid4()),
        source_attribution="local-git",
        observed_at_us=1_700_000_000_000_000,
        select_oids=(oids["blob"],),
        include_refs=False,
    )
    with pytest.raises(CoreFailure) as exc_info:
        acq.acquire_from_native(source, bad_req)
    assert exc_info.value.code == "RETENTION_PURPOSE"

    # Unavailable / shallow parent OID is recorded as nominal object with partial status
    missing_oid = OID(git_format, "f" * (40 if git_format == "sha1" else 64))
    partial_req = GitNativeAcquisitionRequest(
        repository_uuidv4=repo_uuid,
        capture_origin_uuidv4=str(uuid4()),
        capture_uuidv4=str(uuid4()),
        source_attribution="local-git",
        observed_at_us=1_700_000_100_000_000,
        select_oids=(oids["commit1"], missing_oid),
        include_refs=False,
    )
    report = acq.acquire_from_native(source, partial_req)
    assert report.status == "partial"
    assert report.failure_code == "OBJECT_UNAVAILABLE"
    assert missing_oid in report.nominal_missing_objects
    assert missing_oid in report.admitted_objects

    core = GitCore(cat_dir / "core.sqlite3")
    try:
        cov = core.coverage(
            CoreCoverageScope("repository", (repo_uuid, "git_metadata"))
        )
        assert cov.state == "partial"
    finally:
        core.close()


def test_git_metadata_input_competing_claims_and_operational_rebuild(
    tmp_path: Path,
    git_format: Literal["sha1", "sha256"],
) -> None:
    cat_dir = tmp_path / "cat"
    repo_uuid, inst_uuid = init_catalog_stores(cat_dir, stores=("core", "operational"))
    acq = GitAcquisition(cat_dir, operational=cat_dir)

    subject = OID(git_format, "1" * (40 if git_format == "sha1" else 64))
    prov_a = Provenance("source-a", encode(["ev-a"]), "commit", "ext", "1", "reported")
    prov_b = Provenance("source-b", encode(["ev-b"]), "commit", "ext", "1", "reported")

    unit = GitMetadataInput(
        repository_uuidv4=repo_uuid,
        capture_origin_uuidv4=str(uuid4()),
        capture_uuidv4=str(uuid4()),
        source_attribution="source-a",
        observed_at_us=1_700_000_000_000_000,
        object_format=git_format,
        repository_claims=(RepositoryClaim(repo_uuid, "name", "sample-repo", prov_a),),
        scalar_claims=(
            ScalarClaim(subject, "message", "Message A\n", prov_a),
            ScalarClaim(subject, "message", "Message B\n", prov_b),
        ),
    )
    report = acq.acquire_metadata_only(unit)
    assert report.status == "complete"
    assert subject in report.admitted_objects

    # Operational ledger tracks retry_state, cache_locators, and continuations
    op_path = cat_dir / "operational.sqlite3"
    req_id = RequestIdentity(str(uuid4()), str(uuid4()))
    with OperationalAcquisitionLedger(op_path) as ledger:
        ledger.ensure_request(req_id, scope=["p5-test", *req_id.values()])
        ledger.save_continuation(req_id, ["cursor"], {"page": 2})
        assert ledger.load_continuation(req_id, ["cursor"]) == {"page": 2}
        retry = ledger.record_retry_state(
            ["rate-limit"], not_before_us=1_700_000_999_000_000, reason="http_429"
        )
        assert retry["attempt_count"] == 1
        ledger.record_cache_locator(["etag", "commit"], 'W/"123"', observed_at_us=100)
        assert ledger.get_cache_locator(["etag", "commit"])["locator"] == 'W/"123"'

    # Delete and recreate operational.sqlite3 with a new instance:
    # old continuation fails with CONTINUATION_UNAVAILABLE, while Core facts remain intact!
    op_path.unlink()
    initialize(op_path, "operational", repo_uuid, str(uuid4()))
    with OperationalAcquisitionLedger(op_path) as new_ledger:
        with pytest.raises(CoordinationError) as exc_info:
            new_ledger.load_continuation(req_id, ["cursor"])
        assert exc_info.value.code == "CONTINUATION_UNAVAILABLE"

    core = GitCore(cat_dir / "core.sqlite3")
    try:
        proj = core.scalar(subject, "message")
        assert proj.reported_conflict is True
        assert len(proj.alternatives) == 2
    finally:
        core.close()
