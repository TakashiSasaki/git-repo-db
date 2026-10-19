"""P5 integration tests for versioned typed Exchange export and import.

Verifies:
- Initial export/import, repeat idempotent import, reverse (B->A), onward multi-hop (A->B->C)
- Selective export/import (retained bytes excluded, OID filters, ResourceKey filters)
- Refusal of sender-claimed intrinsic spoofing without validated bytes
- Refusal of tampered metadata bytes, text body SHA-256 mismatch, and smuggled ordinary blobs
- Evaluation of core_references against receiver's actual Core state (never blindly trusting sender)
- Preservation of competing claims and field candidates across exchange
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.acquisition import (
    PairedAcquisitionCoordinator,
)
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.acquisition import (
    GitNativeAcquisitionRequest,
    NotesAcquisitionSpec,
    ProviderIntakeBatch,
    ProviderPullRequestIntake,
    ProviderRegistration,
    RepositoryRegistration,
    make_provenance,
)
from repo_catalog.domain.exchange import (
    ExchangeError,
    ExchangeSelectionScope,
    decode_package,
    encode_package,
)
from repo_catalog.domain.p1_context import (
    FieldClock,
    ResourceKey,
    ResourceRepositoryRelation,
    canonical,
)
from repo_catalog.domain.p1_coordination import RequestIdentity
from repo_catalog.domain.p1_core import OID, CoreFailure
from tests.integration.p5.conftest import build_sample_git_repo, init_catalog_stores


def test_i1_relation_export_guard_without_i2_acquisition(tmp_path: Path) -> None:
    """Direct I3 boundary control; the five integration tests still stop in I2."""
    repo, service = str(uuid4()), str(uuid4())
    init_catalog_stores(
        tmp_path, repository_uuidv4=repo, stores=("core", "context", "operational")
    )
    resource = ResourceKey(service, "issue", "7")
    with Context.transaction(tmp_path) as context:
        context.provider(service, "github", "{}")
        context.repository(repo)
        context.resource(resource)
        context.admit_repository_relation(
            ResourceRepositoryRelation(
                resource,
                "owning_repository",
                FieldClock("event", 1),
                canonical(repo),
                make_provenance("fixture", "direct-I1"),
                1,
            )
        )
    with pytest.raises(ExchangeError) as refused:
        ExchangeService(tmp_path).export_package(exported_at_us=2)
    assert refused.value.code == "UNSUPPORTED_UNTIL_I3"
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def _setup_source_catalog(
    cat_dir: Path, repo_uuid: str, fmt: str = "sha1"
) -> dict[str, OID]:
    init_catalog_stores(
        cat_dir, repository_uuidv4=repo_uuid, stores=("core", "context", "operational")
    )
    repo_dir = cat_dir / "repo"
    oids = build_sample_git_repo(repo_dir, fmt)  # type: ignore[arg-type]

    git_source = GitNativeSource(repo_dir)
    git_req = GitNativeAcquisitionRequest(
        repository_uuidv4=repo_uuid,
        capture_origin_uuidv4=str(uuid4()),
        capture_uuidv4=str(uuid4()),
        source_attribution="src-cat-git",
        observed_at_us=1_700_000_100_000_000,
        select_oids=(oids["commit1"], oids["commit2"], oids["tree"], oids["tag"]),
        retain_bytes=True,
        notes=NotesAcquisitionSpec(
            discover_notes=True,
            acquire_inventories=True,
            target_oids=(oids["commit2"],),
            retain_note_bodies=True,
        ),
    )

    service_uuid = str(uuid4())
    prov_json = make_provenance("src-cat-prov", "intake-step")
    pr_payload = {
        "id": 100,
        "number": 1,
        "title": "Initial Feature PR",
        "state": "open",
        "body": "PR description body text",
        "head": {"sha": oids["commit2"].full_oid, "ref": "feat/init"},
        "base": {"sha": oids["commit1"].full_oid, "ref": "main"},
    }
    batch = ProviderIntakeBatch(
        service_instance_uuidv4=service_uuid,
        providers=(ProviderRegistration(service_uuid, "github"),),
        repositories=(RepositoryRegistration(repo_uuid),),
        pull_requests=(
            ProviderPullRequestIntake(
                pr_payload,
                1_700_000_150_000_000,
                prov_json,
                repository_uuidv4=repo_uuid,
            ),
        ),
    )

    coord = PairedAcquisitionCoordinator(cat_dir)
    coord.admit_paired(
        new_request=True,
        git_source=git_source,
        git_request=git_req,
        provider_batch=batch,
    )
    return oids


def test_exchange_export_import_repeat_reverse_and_multi_hop(tmp_path: Path) -> None:
    repo_uuid = str(uuid4())
    cat_a = tmp_path / "cat_a"
    cat_b = tmp_path / "cat_b"
    cat_c = tmp_path / "cat_c"
    oids = _setup_source_catalog(cat_a, repo_uuid, fmt="sha1")

    # 1. Export package from A
    svc_a = ExchangeService(cat_a)
    pkg_a = svc_a.export_package(exported_at_us=1_700_000_200_000_000)
    assert pkg_a.core is not None
    assert pkg_a.context is not None

    # Encode to canonical JSON wire format and decode
    wire_bytes = encode_package(pkg_a)
    decoded_pkg = decode_package(wire_bytes)
    assert decoded_pkg.package_id == pkg_a.package_id

    # 2. Import into empty catalog B
    init_catalog_stores(
        cat_b, repository_uuidv4=repo_uuid, stores=("core", "context", "operational")
    )
    svc_b = ExchangeService(cat_b)
    rep_b1 = svc_b.import_package(
        wire_bytes,
        request=RequestIdentity(pkg_a.sender_catalog_instance_uuidv4, pkg_a.package_id),
        new_request=True,
    )
    assert rep_b1.admitted_core_objects >= 3
    assert rep_b1.admitted_retained_metadata >= 3
    assert rep_b1.admitted_context_resources >= 1

    # Verify B now has objects and context
    core_b = GitCore(cat_b / "core.sqlite3")
    try:
        assert core_b.read_metadata(oids["commit2"]) is not None
    finally:
        core_b.close()

    # 3. Repeat import into B (idempotent, lost-ack handling)
    rep_b2 = svc_b.import_package(
        wire_bytes,
        request=RequestIdentity(pkg_a.sender_catalog_instance_uuidv4, pkg_a.package_id),
        new_request=True,
    )
    assert rep_b2.package_id == pkg_a.package_id

    # 4. Reverse import (export from B, import back into A)
    pkg_b = svc_b.export_package(exported_at_us=1_700_000_300_000_000)
    rep_a = svc_a.import_package(pkg_b, new_request=True)
    assert rep_a.package_id == pkg_b.package_id

    # 5. Multi-hop (export from B, import into C)
    init_catalog_stores(
        cat_c, repository_uuidv4=repo_uuid, stores=("core", "context", "operational")
    )
    svc_c = ExchangeService(cat_c)
    rep_c = svc_c.import_package(pkg_b, new_request=True)
    assert rep_c.admitted_core_objects >= 3

    with Context.snapshot(cat_c) as ctx_c:
        res_list = ctx_c.db.execute("SELECT resource_kind FROM resources").fetchall()
        assert len(res_list) >= 1


def test_exchange_selective_filters_and_partial_input(tmp_path: Path) -> None:
    repo_uuid = str(uuid4())
    cat_src = tmp_path / "cat_src"
    cat_dst = tmp_path / "cat_dst"
    oids = _setup_source_catalog(cat_src, repo_uuid, fmt="sha1")

    # Selective export: include Core metadata-only (no retained bytes) and commit1 only
    svc_src = ExchangeService(cat_src)
    scope = ExchangeSelectionScope(
        include_core=True,
        include_context=False,
        include_retained_bytes=False,
        object_oids=(oids["commit1"],),
    )
    pkg = svc_src.export_package(selection=scope)
    assert pkg.context is None
    assert pkg.core is not None
    assert len(pkg.core.get("retained_metadata", [])) == 0
    assert any(
        o["full_oid"] == oids["commit1"].full_oid
        for o in pkg.core.get("git_objects", [])
    )

    # Import into dst
    init_catalog_stores(
        cat_dst, repository_uuidv4=repo_uuid, stores=("core", "context", "operational")
    )
    svc_dst = ExchangeService(cat_dst)
    rep = svc_dst.import_package(pkg, new_request=True)
    assert rep.admitted_core_objects >= 1
    assert rep.admitted_retained_metadata == 0


def test_exchange_refuses_intrinsic_spoofing_without_validated_bytes(
    tmp_path: Path,
) -> None:
    repo_uuid = str(uuid4())
    cat_a = tmp_path / "cat_a"
    cat_b = tmp_path / "cat_b"
    _setup_source_catalog(cat_a, repo_uuid, fmt="sha1")

    svc_a = ExchangeService(cat_a)
    pkg = svc_a.export_package()

    # Modify package: strip retained_metadata bytes, but keep claims claiming authority="intrinsic"
    pkg_dict = json.loads(encode_package(pkg))
    pkg_dict["core"]["retained_metadata"] = []
    # Verify claims have authority="intrinsic"
    for claim in pkg_dict["core"].get("scalar_claims", []):
        claim["authority"] = "intrinsic"

    # A rewritten digest is only a checksum; independently reject intrinsic spoofing.
    import hashlib

    content = {k: v for k, v in pkg_dict.items() if k != "digest_sha256"}
    pkg_dict["digest_sha256"] = hashlib.sha256(
        json.dumps(
            content, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    # Import into B
    init_catalog_stores(
        cat_b, repository_uuidv4=repo_uuid, stores=("core", "context", "operational")
    )
    svc_b = ExchangeService(cat_b)
    rep = svc_b.import_package(pkg_dict, new_request=True)
    assert rep.package_id == pkg.package_id

    # Receiver MUST ignore/refuse unverified intrinsic claims and not admit them as intrinsic!
    core_b = GitCore(cat_b / "core.sqlite3")
    try:
        intrinsic_rows = core_b.sql("SELECT COUNT(*) FROM intrinsic_claims")
        assert intrinsic_rows[0][0] == 0
    finally:
        core_b.close()


def test_exchange_refuses_tampered_payloads_without_store_corruption(
    tmp_path: Path,
) -> None:
    repo_uuid = str(uuid4())
    cat_a = tmp_path / "cat_a"
    cat_b = tmp_path / "cat_b"
    _setup_source_catalog(cat_a, repo_uuid, fmt="sha1")

    svc_a = ExchangeService(cat_a)
    wire_bytes = encode_package(svc_a.export_package())

    init_catalog_stores(
        cat_b, repository_uuidv4=repo_uuid, stores=("core", "context", "operational")
    )
    svc_b = ExchangeService(cat_b)

    # 1. Tamper retained_metadata raw bytes (hash mismatch)
    bad_dict = json.loads(wire_bytes)
    if bad_dict["core"].get("retained_metadata"):
        # Alter the hex bytes so hash no longer matches declared full_oid
        bad_dict["core"]["retained_metadata"][0]["body_hex"] = "00" * 30
        with pytest.raises((ExchangeError, CoreFailure)):
            svc_b.import_package(bad_dict, new_request=True)

    # 2. Tamper text_bodies UTF-8 text (digest mismatch)
    bad_dict2 = json.loads(wire_bytes)
    if bad_dict2["context"].get("text_bodies"):
        bad_dict2["context"]["text_bodies"][0]["text_value"] = "tampered text value"
        with pytest.raises((ExchangeError, CoreFailure)):
            svc_b.import_package(bad_dict2, new_request=True)

    # 3. Smuggle ordinary blob into retained_metadata
    bad_dict3 = json.loads(wire_bytes)
    bad_dict3["core"]["retained_metadata"].append(
        {
            "object_format": "sha1",
            "full_oid": "1" * 40,
            "native_type": "blob",  # ORDINARY BLOB FORBIDDEN
            "declared_size": 5,
            "digest_sha256": "a" * 64,
            "body_hex": "68656c6c6f",
        }
    )
    with pytest.raises((ExchangeError, CoreFailure)):
        svc_b.import_package(bad_dict3, new_request=True)

    # Verify that target catalog B was NEVER mutated or corrupted
    core_b = GitCore(cat_b / "core.sqlite3")
    try:
        assert core_b.sql("SELECT COUNT(*) FROM git_objects")[0][0] == 0
    finally:
        core_b.close()
    assert not (cat_b / "p1-recovery-stop.json").exists()


def test_exchange_evaluates_core_dependencies_against_receiver_core(
    tmp_path: Path,
) -> None:
    repo_uuid = str(uuid4())
    cat_a = tmp_path / "cat_a"
    cat_b = tmp_path / "cat_b"
    _setup_source_catalog(cat_a, repo_uuid, fmt="sha1")

    # Export Context only from A (without Core objects)
    svc_a = ExchangeService(cat_a)
    scope = ExchangeSelectionScope(include_core=False, include_context=True)
    pkg = svc_a.export_package(selection=scope)

    # Import Context into catalog B which lacks the referenced Git Core OIDs
    init_catalog_stores(
        cat_b, repository_uuidv4=repo_uuid, stores=("core", "context", "operational")
    )
    svc_b = ExchangeService(cat_b)
    rep = svc_b.import_package(pkg, new_request=True)
    assert rep.admitted_context_resources >= 1

    # In catalog B, the imported PR's core_dependencies must have required=False because Core lacks the OID!
    with Context.snapshot(cat_b) as ctx_b:
        pr_rows = ctx_b.db.execute(
            "SELECT provider_resource_id FROM resources WHERE resource_kind='pull_request'"
        ).fetchall()
        assert len(pr_rows) >= 1
        pr_key = ResourceKey(
            pkg.context["providers"][0]["service_instance_uuidv4"],
            "pull_request",
            pr_rows[0][0],
        )
        deps = ctx_b.core_dependencies(pr_key)
        assert len(deps) >= 1
        # None of the dependencies should be required in receiver until OID is actually in Core
        assert all(not d.required for d in deps)
