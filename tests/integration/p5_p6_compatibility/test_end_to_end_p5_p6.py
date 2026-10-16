"""Combined end-to-end integration tests uniting P5 (acquisition, paired admission, Exchange)
and P6 (authoritative queries, derivative Search, pagination, and byte reads).

Verifies:
1. End-to-end acquisition (native Git Core + GitHub Provider Context) into query and Search.
2. Multi-hop Exchange (A -> B -> C) into authoritative query verification.
3. Deferred / late Core dependency reconciliation into PairedResourceView.
4. Derivative loss and corruption resilience (search.sqlite3 missing or corrupt falls back
   to authority_scan without recovery stop).
5. Authoritative corruption detection halts the store and writes p1-recovery-stop.json.
"""

from __future__ import annotations

import json
import subprocess
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.github.production_intake import make_document_key
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.application.acquisition import (
    GitAcquisition,
    PairedAcquisitionCoordinator,
    ProviderAcquisition,
)
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.acquisition import (
    GitNativeAcquisitionRequest,
    ProviderIntakeBatch,
    ProviderPullRequestIntake,
    ProviderRegistration,
    RepositoryRegistration,
    make_provenance,
)
from repo_catalog.domain.exchange import (
    decode_package,
    encode_package,
)
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.p1_core import OID, CoreFailure
from repo_catalog.domain.production_query import SearchQuery


def _init_catalog(cat_dir: Path, repo_uuid: str, inst_uuid: str) -> None:
    cat_dir.mkdir(parents=True, exist_ok=True)
    for role in ("core", "context", "operational", "search"):
        initialize(cat_dir / f"{role}.sqlite3", role, repo_uuid, inst_uuid)


def _setup_git_repo(git_dir: Path, fmt: str = "sha1") -> dict[str, str]:
    subprocess.run(
        ["git", "init", "--bare", f"--object-format={fmt}", str(git_dir)],
        check=True,
        capture_output=True,
    )

    def write_obj(kind: str, body: bytes) -> str:
        return (
            subprocess.run(
                ["git", "-C", str(git_dir), "hash-object", "-w", "-t", kind, "--stdin"],
                input=body,
                check=True,
                capture_output=True,
            )
            .stdout.strip()
            .decode("utf-8")
        )

    tree_oid = write_obj("tree", b"")
    c1_raw = (
        f"tree {tree_oid}\n"
        f"author Alice <alice@example.com> 1700000000 +0000\n"
        f"committer Alice <alice@example.com> 1700000000 +0000\n\n"
        f"commit 1 needle_kw\n"
    ).encode("utf-8")
    c1_oid = write_obj("commit", c1_raw)
    subprocess.run(
        ["git", "-C", str(git_dir), "update-ref", "refs/heads/main", c1_oid], check=True
    )

    c2_raw = (
        f"tree {tree_oid}\n"
        f"parent {c1_oid}\n"
        f"author Bob <bob@example.com> 1700000100 +0000\n"
        f"committer Bob <bob@example.com> 1700000100 +0000\n\n"
        f"commit 2 needle_kw\n"
    ).encode("utf-8")
    c2_oid = write_obj("commit", c2_raw)
    subprocess.run(
        ["git", "-C", str(git_dir), "update-ref", "refs/heads/feature", c2_oid],
        check=True,
    )

    return {"tree": tree_oid, "commit1": c1_oid, "commit2": c2_oid}


def test_end_to_end_acquisition_into_query_and_search(tmp_path: Path) -> None:
    repo_uuid = str(uuid4())
    inst_uuid = str(uuid4())
    cat_dir = tmp_path / "catalog"
    _init_catalog(cat_dir, repo_uuid, inst_uuid)

    git_dir = tmp_path / "git_repo"
    oids = _setup_git_repo(git_dir, "sha1")

    # 1. P5 Git acquisition
    git_src = GitNativeSource(git_dir)
    git_req = GitNativeAcquisitionRequest(
        repository_uuidv4=repo_uuid,
        capture_origin_uuidv4=str(uuid4()),
        capture_uuidv4=str(uuid4()),
        source_attribution="test-git",
        observed_at_us=1_700_000_000_000_000,
        select_oids=(OID("sha1", oids["commit1"]), OID("sha1", oids["commit2"])),
        retain_bytes=True,
    )
    git_acq = GitAcquisition(cat_dir)
    git_rep = git_acq.acquire_from_native(git_src, git_req)
    assert git_rep.status == "complete"

    # 2. P5 Provider intake
    service_uuid = str(uuid4())
    prov_acq = ProviderAcquisition(cat_dir)
    pr_payload = {
        "id": 501,
        "number": 1,
        "title": "Add feature needle_kw",
        "state": "open",
        "body": "PR description details needle_kw",
        "created_at": "2026-10-10T12:00:00Z",
        "updated_at": "2026-10-10T12:05:00Z",
        "head": {"sha": oids["commit2"], "ref": "feature"},
        "base": {"sha": oids["commit1"], "ref": "main"},
    }
    batch = ProviderIntakeBatch(
        service_instance_uuidv4=service_uuid,
        providers=(ProviderRegistration(service_uuid, "github"),),
        repositories=(RepositoryRegistration(repo_uuid),),
        pull_requests=(
            ProviderPullRequestIntake(
                payload=pr_payload,
                observed_at_us=1_700_000_000_000_000,
                provenance_json=make_provenance("github.rest", "pr-1"),
                repository_uuidv4=repo_uuid,
            ),
        ),
    )
    prov_rep = prov_acq.admit_batch(batch)
    assert len(prov_rep.admitted_resources) >= 1

    # 3. P6 Query Service verification
    qs = ProductionQueryService(cat_dir)
    obj1 = qs.get_git_object(OID("sha1", oids["commit1"]), include_bytes=True)
    assert obj1.oid.full_oid == oids["commit1"]
    assert obj1.native_type == "commit"
    assert obj1.metadata_retained is True

    # P6 Paired Resource query
    pr_key = ResourceKey(service_uuid, "pull_request", "501")
    paired = qs.get_paired_resource(pr_key)
    assert paired.resource.resource_kind == "pull_request"
    assert (
        json.loads(paired.context_resource.fields["title"][0].value_json)
        == "Add feature needle_kw"
    )

    # Query title document resource to verify resolved text body
    title_doc_key = make_document_key(
        pr_key, "pull_request_document", "pr_title", "501"
    )
    title_doc = qs.get_context_resource(title_doc_key, include_text=True)
    assert next(iter(title_doc.resolved_texts.values())) == "Add feature needle_kw"

    # Dependencies to commit1 and commit2 resolved in Core
    assert len(paired.core_resolutions) >= 2
    for res in paired.core_resolutions:
        assert res.available_in_core is True
        assert res.object_view is not None

    # 4. P6 Search integration
    qs.rebuild_search()
    res = qs.search(SearchQuery(query_text="needle_kw"))
    assert res.total_count >= 2
    assert all(hit.snapshot_token == res.snapshot_token for hit in res.hits)


def test_multi_hop_exchange_into_query(tmp_path: Path) -> None:
    repo_uuid = str(uuid4())
    inst_a = str(uuid4())
    inst_b = str(uuid4())
    inst_c = str(uuid4())

    cat_a = tmp_path / "cat_a"
    cat_b = tmp_path / "cat_b"
    cat_c = tmp_path / "cat_c"
    _init_catalog(cat_a, repo_uuid, inst_a)
    _init_catalog(cat_b, repo_uuid, inst_b)
    _init_catalog(cat_c, repo_uuid, inst_c)

    git_dir = tmp_path / "git_repo"
    oids = _setup_git_repo(git_dir, "sha1")

    # Acquire into A
    git_acq = GitAcquisition(cat_a)
    git_acq.acquire_from_native(
        GitNativeSource(git_dir),
        GitNativeAcquisitionRequest(
            repository_uuidv4=repo_uuid,
            capture_origin_uuidv4=str(uuid4()),
            capture_uuidv4=str(uuid4()),
            source_attribution="src-a",
            observed_at_us=1_700_000_000_000_000,
            select_oids=(OID("sha1", oids["commit1"]),),
            retain_bytes=True,
        ),
    )

    # Export A -> Import B
    svc_a = ExchangeService(cat_a)
    pkg_a = svc_a.export_package(exported_at_us=1_700_000_010_000_000)
    wire_a = encode_package(pkg_a)

    svc_b = ExchangeService(cat_b)
    rep_b = svc_b.import_package(decode_package(wire_a))
    assert rep_b.admitted_core_objects >= 1

    # Export B -> Import C
    pkg_b = svc_b.export_package(exported_at_us=1_700_000_020_000_000)
    wire_b = encode_package(pkg_b)

    svc_c = ExchangeService(cat_c)
    rep_c = svc_c.import_package(decode_package(wire_b))
    assert rep_c.admitted_core_objects >= 1

    # Query catalog C with P6 QueryService
    qs_c = ProductionQueryService(cat_c)
    obj = qs_c.get_git_object(OID("sha1", oids["commit1"]), include_bytes=True)
    assert obj.metadata_retained is True
    byte_res = qs_c.read_metadata_bytes(OID("sha1", oids["commit1"]))
    assert byte_res.available is True
    assert byte_res.verified is True
    assert byte_res.body_bytes is not None


def test_deferred_core_dependency_reconciliation_into_paired_queries(
    tmp_path: Path,
) -> None:
    repo_uuid = str(uuid4())
    inst_uuid = str(uuid4())
    cat_dir = tmp_path / "cat_deferred"
    _init_catalog(cat_dir, repo_uuid, inst_uuid)

    git_dir = tmp_path / "git_repo"
    oids = _setup_git_repo(git_dir, "sha1")

    # 1. Admit Context first with PR referencing commit1 (which is NOT in Core yet!)
    service_uuid = str(uuid4())
    prov_acq = ProviderAcquisition(cat_dir)
    pr_payload = {
        "id": 901,
        "number": 10,
        "title": "Deferred PR",
        "state": "open",
        "body": "Referencing not yet present commit",
        "created_at": "2026-10-10T12:00:00Z",
        "head": {"sha": oids["commit1"], "ref": "main"},
        "base": {"sha": oids["commit1"], "ref": "main"},
    }
    batch = ProviderIntakeBatch(
        service_instance_uuidv4=service_uuid,
        providers=(ProviderRegistration(service_uuid, "github"),),
        repositories=(RepositoryRegistration(repo_uuid),),
        pull_requests=(
            ProviderPullRequestIntake(
                payload=pr_payload,
                observed_at_us=1_700_000_000_000_000,
                provenance_json=make_provenance("github.rest", "pr-10"),
                repository_uuidv4=repo_uuid,
            ),
        ),
    )
    prov_acq.admit_batch(batch)

    # Query with P6 before Core arrives: PR dependency available_in_core is False
    qs = ProductionQueryService(cat_dir)
    pr_key = ResourceKey(service_uuid, "pull_request", "901")
    paired_before = qs.get_paired_resource(pr_key)
    assert all(not r.available_in_core for r in paired_before.core_resolutions)
    assert all(r.object_view is None for r in paired_before.core_resolutions)

    # 2. Later, acquire commit1 into Core
    git_acq = GitAcquisition(cat_dir)
    git_acq.acquire_from_native(
        GitNativeSource(git_dir),
        GitNativeAcquisitionRequest(
            repository_uuidv4=repo_uuid,
            capture_origin_uuidv4=str(uuid4()),
            capture_uuidv4=str(uuid4()),
            source_attribution="src-git-late",
            observed_at_us=1_700_000_100_000_000,
            select_oids=(OID("sha1", oids["commit1"]),),
            retain_bytes=True,
        ),
    )

    # 3. Reconcile dependencies via PairedAcquisitionCoordinator
    coord = PairedAcquisitionCoordinator(cat_dir)
    reconciled = coord.reconcile_core_dependencies()
    assert len(reconciled.promoted_references) >= 1

    # 4. Query again: now available_in_core is True and object_view is populated!
    qs_after = ProductionQueryService(cat_dir)
    paired_after = qs_after.get_paired_resource(pr_key)
    assert any(r.available_in_core for r in paired_after.core_resolutions)
    resolved_deps = [r for r in paired_after.core_resolutions if r.available_in_core]
    assert resolved_deps[0].object_view is not None
    assert resolved_deps[0].object_view.oid.full_oid == oids["commit1"]


def test_derivative_loss_resilience_and_transparent_fallback(tmp_path: Path) -> None:
    repo_uuid = str(uuid4())
    inst_uuid = str(uuid4())
    cat_dir = tmp_path / "cat_fallback"
    _init_catalog(cat_dir, repo_uuid, inst_uuid)

    git_dir = tmp_path / "git_repo"
    oids = _setup_git_repo(git_dir, "sha1")

    git_acq = GitAcquisition(cat_dir)
    git_acq.acquire_from_native(
        GitNativeSource(git_dir),
        GitNativeAcquisitionRequest(
            repository_uuidv4=repo_uuid,
            capture_origin_uuidv4=str(uuid4()),
            capture_uuidv4=str(uuid4()),
            source_attribution="src-git",
            observed_at_us=1_700_000_000_000_000,
            select_oids=(OID("sha1", oids["commit1"]),),
            retain_bytes=True,
        ),
    )

    qs = ProductionQueryService(cat_dir)
    qs.rebuild_search()
    res1 = qs.search(SearchQuery(query_text="needle_kw"))
    assert res1.backend == "projection"
    assert res1.total_count >= 1

    # Corrupt search.sqlite3 by writing garbage
    search_path = cat_dir / "search.sqlite3"
    search_path.write_bytes(b"garbage-database-corrupted-bytes")

    # Search query must transparently fall back to authority_scan without crashing
    res2 = qs.search(SearchQuery(query_text="needle_kw"))
    assert res2.backend == "authority_scan"
    assert res2.total_count == res1.total_count
    # NEVER write recovery stop for derivative loss or corruption
    assert not (cat_dir / "p1-recovery-stop.json").exists()


def test_authoritative_corruption_immediate_stop(tmp_path: Path) -> None:
    repo_uuid = str(uuid4())
    inst_uuid = str(uuid4())
    cat_dir = tmp_path / "cat_corrupt"
    _init_catalog(cat_dir, repo_uuid, inst_uuid)

    git_dir = tmp_path / "git_repo"
    oids = _setup_git_repo(git_dir, "sha1")

    git_acq = GitAcquisition(cat_dir)
    git_acq.acquire_from_native(
        GitNativeSource(git_dir),
        GitNativeAcquisitionRequest(
            repository_uuidv4=repo_uuid,
            capture_origin_uuidv4=str(uuid4()),
            capture_uuidv4=str(uuid4()),
            source_attribution="src-git",
            observed_at_us=1_700_000_000_000_000,
            select_oids=(OID("sha1", oids["commit1"]),),
            retain_bytes=True,
        ),
    )

    # Tamper with retained_metadata body in core.sqlite3
    with closing(connect(cat_dir / "core.sqlite3", "core")) as db:
        trigger = db.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND name='p1_immutable_retained_metadata_update'"
        ).fetchone()[0]
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("BEGIN IMMEDIATE")
        db.execute("DROP TRIGGER p1_immutable_retained_metadata_update")
        db.execute(
            "UPDATE retained_metadata SET body=x'636f7272757074' WHERE full_oid=?",
            (oids["commit1"],),
        )
        db.execute(trigger)
        db.commit()

    qs = ProductionQueryService(cat_dir, mode="core_only")
    with pytest.raises(CoreFailure) as exc_info:
        qs.read_metadata_bytes(OID("sha1", oids["commit1"]))
    assert exc_info.value.code == "AUTHORITATIVE_CORRUPTION"

    # Verify stop file was written
    assert (cat_dir / "p1-recovery-stop.json").exists()

    # Subsequent reads fail closed immediately with RECOVERY_STOP
    with pytest.raises(CoreFailure) as fenced:
        qs.get_git_object(OID("sha1", oids["commit1"]))
    assert fenced.value.code == "RECOVERY_STOP"
