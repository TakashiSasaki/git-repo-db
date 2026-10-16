"""Installed opt-in P5 acquisition and Exchange from wheel and wheel built from sdist."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.packaging.test_p1_distribution import p1_distributions, run  # noqa: F401


@pytest.mark.parametrize("variant", [0, 1], ids=["wheel", "sdist-wheel"])
@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_p5_installed_acquisition_and_exchange(
    p1_distributions,  # noqa: F811
    tmp_path: Path,
    variant: int,
    fmt: str,
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
            wheels[variant],
        ],
        outside,
        env,
    )
    script = r"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_coordination import PairCoordinator
from repo_catalog.adapters.sqlite.p1_schema import initialize, verify_declared
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.acquisition import (
    GitAcquisition,
    ProviderAcquisition,
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
    ExchangePackage,
    ExchangeSelectionScope,
    decode_package,
    encode_package,
)
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.p1_core import OID

assert "site-packages" in str(Path(__import__("repo_catalog.application.acquisition", fromlist=["x"]).__file__))
assert "site-packages" in str(Path(__import__("repo_catalog.application.exchange", fromlist=["x"]).__file__))
verify_declared()

repo_uuid = str(uuid4())
cat_a = Path("catalog_a")
cat_b = Path("catalog_b")
cat_a.mkdir()
cat_b.mkdir()

inst_a = str(uuid4())
inst_b = str(uuid4())
for role in ("core", "context", "operational"):
    initialize(cat_a / f"{role}.sqlite3", role, repo_uuid, inst_a)
    initialize(cat_b / f"{role}.sqlite3", role, repo_uuid, inst_b)

# Setup disposable git repo
git_dir = Path("disposable_repo")
subprocess.run(["git", "init", "--bare", f"--object-format=FORMAT", str(git_dir)], check=True, capture_output=True)

def write_obj(kind, body):
    return subprocess.run(
        ["git", "-C", str(git_dir), "hash-object", "-w", "-t", kind, "--stdin"],
        input=body,
        check=True,
        capture_output=True,
    ).stdout.strip().decode("utf-8")

tree1 = write_obj("tree", b"")
c1_raw = f"tree {tree1}\nauthor Bob <bob@example.com> 1700000000 +0000\ncommitter Bob <bob@example.com> 1700000000 +0000\n\ncommit 1\n".encode("utf-8")
commit1 = write_obj("commit", c1_raw)
subprocess.run(["git", "-C", str(git_dir), "update-ref", "refs/heads/main", commit1], check=True)

# 1. Exercise GitAcquisition
git_source = GitNativeSource(git_dir)
git_req = GitNativeAcquisitionRequest(
    repository_uuidv4=repo_uuid,
    capture_origin_uuidv4=str(uuid4()),
    capture_uuidv4=str(uuid4()),
    source_attribution="src-installed",
    observed_at_us=1_700_000_000_000_000,
    select_oids=(OID("FORMAT", commit1),),
    retain_bytes=True,
)
git_acq = GitAcquisition(cat_a)
git_report = git_acq.acquire_from_native(git_source, git_req)
assert git_report.status == "complete"
assert len(git_report.admitted_objects) >= 1

# 2. Exercise ProviderAcquisition
service_uuid = str(uuid4())
prov_acq = ProviderAcquisition(cat_a)
pr_payload = {
    "id": 2001,
    "number": 43,
    "title": "Installed PR",
    "state": "open",
    "body": "Body text",
    "created_at": "2026-10-10T12:10:00Z",
    "updated_at": "2026-10-10T12:15:00Z",
    "head": {"sha": commit1, "ref": "feature"},
    "base": {"sha": commit1, "ref": "main"},
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
prov_report = prov_acq.admit_batch(batch)
assert len(prov_report.admitted_resources) >= 1

# 3. Exercise Exchange export from A and import into B
svc_a = ExchangeService(cat_a)
pkg = svc_a.export_package(exported_at_us=1_700_000_100_000_000)
assert pkg.core is not None
assert pkg.context is not None

wire = encode_package(pkg)
decoded = decode_package(wire)

svc_b = ExchangeService(cat_b)
rep_b = svc_b.import_package(decoded)
assert rep_b.admitted_core_objects >= 1
assert rep_b.admitted_context_resources >= 1

# Verify catalog B received commit1 in Core
core_b = GitCore(cat_b / "core.sqlite3")
try:
    assert core_b.read_metadata(OID("FORMAT", commit1)) is not None
finally:
    core_b.close()
""".replace("FORMAT", fmt)
    run([python, "-c", script], outside, env)
