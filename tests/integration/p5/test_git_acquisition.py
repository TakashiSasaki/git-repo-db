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
        select_object_oids=(
            oids["commit1"],
            oids["commit2"],
            oids["tree"],
            oids["tag"],
        ),
        retain_bytes=False,
        include_refs=True,
    )
    acq_meta = GitAcquisition(cat_meta, operational=cat_meta)
    report_meta = acq_meta.acquire_from_native(source, req_meta, new_request=True)

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
            [0, git_format, oids["commit1"].object_oid]
        ]
    finally:
        core_meta.close()

    # 2. Hybrid mode (retain_object_oids={commit2, tag}) + P4 Notes discovery/inventory/note body
    cat_hybrid = tmp_path / "cat_hybrid"
    init_catalog_stores(
        cat_hybrid,
        repository_uuidv4=repo_uuid,
        stores=("core", "operational"),
    )
    notes_spec = NotesAcquisitionSpec(
        discover_notes=True,
        acquire_inventories=True,
        target_object_oids=(oids["commit2"],),
        retain_note_bodies=True,
    )
    req_hybrid = GitNativeAcquisitionRequest(
        repository_uuidv4=repo_uuid,
        capture_origin_uuidv4=origin_uuid,
        capture_uuidv4=str(uuid4()),
        source_attribution="local-git-test",
        observed_at_us=1_700_000_600_000_000,
        select_object_oids=(
            oids["commit1"],
            oids["commit2"],
            oids["tree"],
            oids["tag"],
        ),
        retain_bytes=False,
        retain_object_oids=frozenset({oids["commit2"], oids["tag"]}),
        notes=notes_spec,
    )
    acq_hybrid = GitAcquisition(cat_hybrid, operational=cat_hybrid)
    report_hybrid = acq_hybrid.acquire_from_native(source, req_hybrid, new_request=True)

    assert set(report_hybrid.retained_objects) == {oids["commit2"], oids["tag"]}
    assert oids["commit1"] in report_hybrid.metadata_only_objects
    assert oids["tree"] in report_hybrid.metadata_only_objects
    assert len(report_hybrid.notes_discoveries) == 1
    assert not hasattr(report_hybrid, "notes_inventories")
    assert not hasattr(report_hybrid, "note_acquisitions")
    assert len(report_hybrid.ref_note_acquisitions) == 2
    assert all(
        item.role_verified and item.body_retained
        for item in report_hybrid.ref_note_acquisitions
    )
    assert len(report_hybrid.ref_notes_inventories) == 2
    assert all(
        item.group.status == "complete" for item in report_hybrid.ref_notes_inventories
    )

    core_hybrid = GitCore(cat_hybrid / "core.sqlite3")
    try:
        assert core_hybrid.read_metadata(oids["commit2"]).startswith(b"tree ")
        with pytest.raises(CoreFailure) as exc_info:
            core_hybrid.read_metadata(oids["commit1"])
        assert exc_info.value.code == "BYTES_UNAVAILABLE"

        from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget

        claim = report_hybrid.ref_note_acquisitions[0].claim
        work = UnlimitedWorkBudget()
        mapping = (
            core_hybrid.notes_mapping_projection(
                claim, oids["commit2"], "git-notes", "1", "native-notes-tree", work
            )
            .evidence[0]
            .mapping
        )
        assert core_hybrid.read_ref_note(claim, mapping, work) == b"Reviewed-by: CI\n"
        assert not core_hybrid.sql(
            "SELECT 1 FROM sqlite_schema WHERE type='table' AND name='captures'"
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
        select_object_oids=(oids["blob"],),
        include_refs=False,
    )
    with pytest.raises(CoreFailure) as exc_info:
        acq.acquire_from_native(source, bad_req, new_request=True)
    assert exc_info.value.code == "RETENTION_PURPOSE"

    # Unavailable / shallow parent OID is recorded as nominal object with partial status
    missing_oid = OID(git_format, "f" * (40 if git_format == "sha1" else 64))
    partial_req = GitNativeAcquisitionRequest(
        repository_uuidv4=repo_uuid,
        capture_origin_uuidv4=str(uuid4()),
        capture_uuidv4=str(uuid4()),
        source_attribution="local-git",
        observed_at_us=1_700_000_100_000_000,
        select_object_oids=(oids["commit1"], missing_oid),
        include_refs=False,
    )
    report = acq.acquire_from_native(source, partial_req, new_request=True)
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
    report = acq.acquire_metadata_only(unit, new_request=True)
    assert report.status == "complete"
    assert subject in report.admitted_objects

    # Operational ledger tracks retry_state, cache_locators, and continuations
    op_path = cat_dir / "operational.sqlite3"
    req_id = RequestIdentity(str(uuid4()), str(uuid4()))
    with OperationalAcquisitionLedger(op_path) as ledger:
        ledger.ensure_request(
            req_id, scope=["p5-test", *req_id.values()], new_request=True
        )
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


def test_native_ref_reads_pin_exact_result_and_preserve_symbolic_and_peeled(
    tmp_path, git_format
):
    from dataclasses import replace

    from tests.integration.p5.conftest import git

    repo_path = tmp_path / "repo-i2"
    oids = build_sample_git_repo(repo_path, git_format)
    git(repo_path, "symbolic-ref", "refs/heads/alias", "refs/heads/main")
    catalog = tmp_path / "catalog-i2"
    repository, _ = init_catalog_stores(catalog, stores=("core", "operational"))
    request = GitNativeAcquisitionRequest(
        repository_uuidv4=repository,
        capture_origin_uuidv4=str(uuid4()),
        capture_uuidv4=str(uuid4()),
        source_attribution="local-i2",
        observed_at_us=1_700_000_500_000_000,
        select_object_oids=(),
        retain_bytes=False,
        include_refs=True,
    )
    source = GitNativeSource(repo_path)
    app = GitAcquisition(catalog, operational=catalog)
    first = app.acquire_from_native(source, request, new_request=True)
    event = first.ref_enumerations[0]
    by_name = {link.observation.ref_name_bytes: link.claim for link in event.links}
    symbolic = by_name[b"refs/heads/alias"]
    assert symbolic.ref_form == "symbolic"
    assert symbolic.symbolic_target_ref_name == b"refs/heads/main"
    assert symbolic.resolved_target_object_oid == oids["commit2"]
    assert symbolic.direct_target_object_oid is None
    assert by_name[b"refs/tags/v1.0.0"].peeled_target_object_oid == oids["commit2"]
    git(repo_path, "update-ref", "refs/heads/main", oids["commit1"].object_oid)
    replay = app.acquire_from_native(source, request)
    assert replay.ref_enumerations == first.ref_enumerations
    fresh_request = replace(request, capture_uuidv4=str(uuid4()))
    fresh = app.acquire_from_native(source, fresh_request, new_request=True)
    newer = {
        link.observation.ref_name_bytes: link.claim
        for link in fresh.ref_enumerations[0].links
    }
    assert newer[b"refs/heads/main"].root_object_oid == oids["commit1"]
    assert (
        newer[b"refs/heads/main"].ref_observation_key
        != by_name[b"refs/heads/main"].ref_observation_key
    )


def test_nominated_ref_lookup_confirms_only_named_local_absence(tmp_path, git_format):
    repo_path = tmp_path / "repo-named"
    build_sample_git_repo(repo_path, git_format)
    catalog = tmp_path / "catalog-named"
    repository, _ = init_catalog_stores(catalog, stores=("core", "operational"))
    request = GitNativeAcquisitionRequest(
        repository_uuidv4=repository,
        capture_origin_uuidv4=str(uuid4()),
        capture_uuidv4=str(uuid4()),
        source_attribution="local-named",
        observed_at_us=1_700_000_500_000_000,
        include_refs=False,
        nominated_ref_names=(b"refs/heads/missing",),
        retain_bytes=False,
    )
    report = GitAcquisition(catalog, operational=catalog).acquire_from_native(
        GitNativeSource(repo_path), request, new_request=True
    )
    assert len(report.ref_enumerations) == 1
    result = report.ref_enumerations[0]
    assert result.links[0].claim.presence_state == "absent"
    assert result.links[0].claim.absence_evidence.method == "lookup"
    assert result.event.nominated == (b"refs/heads/missing",)
    assert not result.event.prefixes


def test_invalid_nominated_name_does_not_become_absence(tmp_path, git_format):
    repo_path = tmp_path / "repo-invalid-ref"
    build_sample_git_repo(repo_path, git_format)
    catalog = tmp_path / "catalog-invalid-ref"
    repository, _ = init_catalog_stores(catalog, stores=("core", "operational"))
    request = GitNativeAcquisitionRequest(
        repository,
        str(uuid4()),
        str(uuid4()),
        "local-invalid-ref",
        1_700_000_500_000_000,
        include_refs=False,
        nominated_ref_names=(b"refs/heads/bad name",),
        retain_bytes=False,
    )
    report = GitAcquisition(catalog, operational=catalog).acquire_from_native(
        GitNativeSource(repo_path), request, new_request=True
    )
    assert report.failure_code == "REF"
    assert not report.ref_enumerations


def test_native_ref_lossless_non_utf8_and_failed_lookup_no_absence(
    tmp_path, git_format, monkeypatch
):
    import subprocess

    repo_path = tmp_path / "repo-lossless"
    oids = build_sample_git_repo(repo_path, git_format)
    raw_name = b"refs/heads/branch-\xff"
    subprocess.run(
        [
            b"git",
            b"-C",
            bytes(repo_path),
            b"update-ref",
            raw_name,
            oids["commit1"].object_oid.encode(),
        ],
        check=True,
        capture_output=True,
    )
    catalog = tmp_path / "catalog-lossless"
    repository, _ = init_catalog_stores(catalog, stores=("core", "operational"))
    source = GitNativeSource(repo_path)
    request = GitNativeAcquisitionRequest(
        repository,
        str(uuid4()),
        str(uuid4()),
        "local",
        1_700_000_500_000_000,
        select_object_oids=(),
        retain_bytes=False,
        nominated_ref_names=(b"refs/heads/missing",),
    )

    def fail(*_):
        raise CoreFailure("GIT_INPUT", "lookup", "injected failure")

    monkeypatch.setattr(source, "lookup_ref_presence", fail)
    report = GitAcquisition(catalog, operational=catalog).acquire_from_native(
        source, request, new_request=True
    )
    assert report.failure_code == "GIT_INPUT"
    assert any(
        link.observation.ref_name_bytes == raw_name
        for event in report.ref_enumerations
        for link in event.links
    )
    assert all(
        link.claim.presence_state != "absent"
        for event in report.ref_enumerations
        for link in event.links
    )
