"""Installed opt-in P7 recovery capabilities from wheel and wheel built from sdist."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.packaging.test_p1_distribution import p1_distributions, run  # noqa: F401


@pytest.mark.parametrize("variant", [0, 1], ids=["wheel", "sdist-wheel"])
def test_p7_installed_recovery_distribution(
    p1_distributions,  # noqa: F811
    tmp_path: Path,
    variant: int,
) -> None:
    env, wheels = p1_distributions
    outside = tmp_path / "outside"
    outside.mkdir()
    venv = tmp_path / "venv"
    run(["uv", "venv", venv, "--python", sys.executable, "--offline"], outside, env)
    python = venv / "bin/python"
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            python,
            "--offline",
            "--no-deps",
            *wheels[variant],
        ],
        outside,
        env,
    )
    script = r"""
import sys
import hashlib
from pathlib import Path
from uuid import uuid4

from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.recovery import BackupScope
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.p1_core import OID, NativeObject, Provenance, native_object_oid
from repo_catalog.domain.ref_observation import RefObservation, RefObservationClaim, RefObservationKey, new_uuid7

assert "site-packages" in str(Path(__import__("repo_catalog.application.recovery", fromlist=["x"]).__file__))

# 1. Initialize a catalog in site-packages venv
catalog_dir = Path("dist_catalog")
catalog_dir.mkdir(parents=True)
repo_uuid = str(uuid4())
inst_uuid = str(uuid4())
core_path = catalog_dir / "core.sqlite3"
initialize(core_path, "core", repo_uuid, inst_uuid)
initialize(catalog_dir / "context.sqlite3", "context", repo_uuid, inst_uuid)
initialize(catalog_dir / "operational.sqlite3", "operational", repo_uuid, inst_uuid)
initialize(catalog_dir / "search.sqlite3", "search", repo_uuid, inst_uuid)

# 2. Populate commit via GitCore
core = GitCore(core_path)
core.admit_repository(repo_uuid)

tree_body = b"100644 README.md\0" + bytes.fromhex("1" * 40)
tree_object_oid = native_object_oid("sha1", "tree", tree_body)
tree_obj = NativeObject(
    object_oid=OID("sha1", tree_object_oid),
    native_type="tree",
    body=tree_body,
    declared_size=len(tree_body),
    digest_sha256=hashlib.sha256(tree_body).hexdigest(),
)
body = f"tree {tree_object_oid}\nauthor A <a@b> 1700000000 +0000\ncommitter A <a@b> 1700000000 +0000\n\nDist commit\n".encode("utf-8")
oid = native_object_oid("sha1", "commit", body)
commit_obj = NativeObject(
    object_oid=OID("sha1", oid),
    native_type="commit",
    body=body,
    declared_size=len(body),
    digest_sha256=hashlib.sha256(body).hexdigest(),
)
core.admit_metadata(tree_obj, str(uuid4()), UnlimitedWorkBudget())
core.admit_metadata(commit_obj, str(uuid4()), UnlimitedWorkBudget())

# 3. Create consistent backup
service = RecoveryService()
backup_dir = Path("dist_backup")
b_receipt = service.create_consistent_backup(catalog_dir, backup_dir, scope=BackupScope.PAIRED)
assert b_receipt.verified_clean
assert b_receipt.manifest.retained_byte_summary.commit_count == 1

# 4. Salvage a later rootless observation using the installed implementation.
key = RefObservationKey(str(uuid4()), new_uuid7())
subject = RefObservation(key, repo_uuid, b"refs/notes/\xff", "source", "scope", 1)
claim = RefObservationClaim(key, Provenance("source", "scan", "item", "git", "1"), "present")
core.admit_ref_observation(subject)
core.admit_ref_observation_claim(claim)
core.close()
service.stop_suspect_catalog(catalog_dir, "synthetic installed salvage")
salvage = Path("dist-salvage.jsonl")
assert service.extract_salvage(catalog_dir, salvage, request_id="installed").candidate_count

# 5. Restore backup into fresh destination and validate/admit the candidate.
restored_dir = Path("dist_restored")
r_receipt = service.restore_backup(backup_dir, restored_dir, repo_uuid)
assert r_receipt.revalidated_clean
assert "core" in r_receipt.revalidated_stores
assert (restored_dir / "core.sqlite3").exists()
assert service.merge_salvage(restored_dir, salvage).admitted_units >= 1
work = UnlimitedWorkBudget()
assert ProductionQueryService(restored_dir).get_ref_observation(key, work).claims == (claim,)

# 6. Safe activation
active_loc = Path("dist_active")
a_receipt = service.activate_catalog(restored_dir, active_loc)
assert a_receipt.clean_operational
assert "operational" in a_receipt.reconstructed_stores

print("P7 recovery installed and executed meaningful recovery in wheel/sdist venv successfully")
"""
    run([python, "-c", script], outside, env)
