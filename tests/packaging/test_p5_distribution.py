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
from repo_catalog.adapters.github.production_intake import make_document_key
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
from repo_catalog.domain.context_admission import (
    AdmissionSelection,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.exchange import (
    ExchangeError,
    ExchangePackage,
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
from repo_catalog.domain.p1_core import OID

assert "site-packages" in str(Path(__import__("repo_catalog.application.acquisition", fromlist=["x"]).__file__))
assert "site-packages" in str(Path(__import__("repo_catalog.application.exchange", fromlist=["x"]).__file__))
verify_declared()

class FalseTuple(tuple):
    def __bool__(self):
        return False

try:
    ExchangeSelectionScope(all_selected=True, include_context=False, resource_keys=FalseTuple(("invalid",)))
except ExchangeError as error:
    assert error.code == "INVALID_SELECTION"
else:
    raise AssertionError("falsey nonempty selection was accepted")
key = ResourceKey.from_native(str(uuid4()), "opaque", "valid")
assert ExchangeSelectionScope(resource_keys=FalseTuple((key,))).to_dict()["resource_keys"] == [list(key.coordinates())]
assert ExchangeSelectionScope(resource_keys=FalseTuple()).to_dict()["resource_keys"] == []
assert ExchangeSelectionScope(resource_keys=None).to_dict()["resource_keys"] is None

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
    include_refs=False,
)
git_acq = GitAcquisition(cat_a, operational=cat_a)
git_report = git_acq.acquire_from_native(git_source, git_req, new_request=True)
assert git_report.status == "complete"
assert len(git_report.admitted_objects) >= 1

# Exercise installed I2 acquisition and the I3 rootless ref exchange in a
# separate disposable Core, retaining the object/Context roundtrip below.
cat_i2 = Path("catalog_i2")
cat_i2.mkdir()
instance_i2 = str(uuid4())
for role in ("core", "operational"):
    initialize(cat_i2 / f"{role}.sqlite3", role, repo_uuid, instance_i2)
request_i2 = GitNativeAcquisitionRequest(
    repository_uuidv4=repo_uuid,
    capture_origin_uuidv4=str(uuid4()),
    capture_uuidv4=str(uuid4()),
    source_attribution="installed-i2",
    observed_at_us=1_700_000_000_000_000,
    include_refs=True,
    nominated_ref_names=(b"refs/heads/not-present",),
    retain_bytes=False,
)
observed_i2 = GitAcquisition(cat_i2, operational=cat_i2).acquire_from_native(
    git_source, request_i2, new_request=True
)
assert any(link.claim.presence_state == "present" for event in observed_i2.ref_enumerations for link in event.links)
assert any(link.claim.presence_state == "absent" for event in observed_i2.ref_enumerations for link in event.links)
absent = next(link for event in observed_i2.ref_enumerations for link in event.links if link.claim.presence_state == "absent")
selection_i3 = ExchangeSelectionScope(
    all_selected=True, include_context=False, include_retained_bytes=False,
    object_oids=(), ref_observation_keys=(absent.observation.ref_observation_key,),
)
package_i3 = ExchangeService(cat_i2).export_package(selection=selection_i3)
assert not package_i3.core["git_objects"]
assert len(package_i3.core["ref_enumeration_links"]) == 1
cat_i3 = Path("catalog_i3")
cat_i3.mkdir()
instance_i3 = str(uuid4())
for role in ("core", "operational"):
    initialize(cat_i3 / f"{role}.sqlite3", role, repo_uuid, instance_i3)
ExchangeService(cat_i3, operational=cat_i3).import_package(
    package_i3, new_request=True, permitted_repository_uuidv4s=(repo_uuid,)
)
from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
core_i3 = GitCore(cat_i3 / "core.sqlite3")
try:
    assert core_i3.ref_observation(absent.observation.ref_observation_key, UnlimitedWorkBudget()).claims == (absent.claim,)
finally:
    core_i3.close()

# Exercise automatic whole-inventory receiver checks from the installed artifact.
subprocess.run(["git", "-C", str(git_dir), "update-ref", "refs/notes/empty", tree1], check=True)
cat_inventory = Path("catalog_inventory")
cat_inventory.mkdir()
inventory_instance = str(uuid4())
for role in ("core", "operational"):
    initialize(cat_inventory / f"{role}.sqlite3", role, repo_uuid, inventory_instance)
inventory_request = GitNativeAcquisitionRequest(
    repository_uuidv4=repo_uuid,
    capture_origin_uuidv4=str(uuid4()),
    capture_uuidv4=str(uuid4()),
    source_attribution="installed-inventory",
    observed_at_us=1_700_000_000_000_000,
    include_refs=False,
    notes=NotesAcquisitionSpec(discover_notes=True, acquire_inventories=True),
)
inventory_report = GitAcquisition(cat_inventory, operational=cat_inventory).acquire_from_native(
    git_source, inventory_request, new_request=True
)
assert inventory_report.ref_inventory_verifications
assert all(item.verified and item.group.status == "known_empty" for item in inventory_report.ref_inventory_verifications)
assert all(item.coverage.state == "complete" and item.coverage.known_empty for item in inventory_report.ref_inventory_projections)
from repo_catalog.application.production_query import ProductionQueryService
inventory_query = ProductionQueryService(cat_inventory, mode="core_only")
for item in inventory_report.ref_inventory_verifications:
    projection = inventory_query.list_ref_notes_inventories(item.group.ref_claim, UnlimitedWorkBudget())
    assert projection.coverage.known_empty
    assert any(group.current_verified for group in projection.groups)

# 2. Exercise ProviderAcquisition
service_uuid = str(uuid4())
pr_payload = {
    "id": 2001,
    "number": 43,
    "title": "Installed PR",
    "state": "open",
    "body": "Body text",
    "created_at": "2026-10-10T12:10:00Z",
    "updated_at": "2026-10-10T12:15:00Z",
    "head": {"sha": commit1, "ref": "feature", "repo": {"id": 1}},
    "base": {"sha": commit1, "ref": "main", "repo": {"id": 1}},
}
mapping = ResourceRepositoryRelation(
    ResourceKey.from_native(service_uuid, "repository", "1"),
    "represents_repository",
    FieldClock("installed:mapping", 1_700_000_000_000_000),
    canonical(repo_uuid),
    make_provenance("installed", {"binding": "explicit-test-report"}),
    1_700_000_000_000_000,
)
batch = ProviderIntakeBatch(
    service_instance_uuidv4=service_uuid,
    providers=(ProviderRegistration(service_uuid, "github"),),
    repositories=(RepositoryRegistration(repo_uuid),),
    mapping_claims=(mapping,),
    pull_requests=(
        ProviderPullRequestIntake(
            payload=pr_payload,
            observed_at_us=1_700_000_000_000_000,
            provenance_json=make_provenance("github.rest", "pr-1"),
        ),
    ),
)
pr_key = ResourceKey.from_native(service_uuid, "pull_request", "2001")
title_key = make_document_key(pr_key, "pull_request_document", "pr_title", "2001")
body_key = make_document_key(pr_key, "pull_request_document", "pr_body", "2001")
repo_res = ResourceKey.from_native(service_uuid, "repository", "1")
grants = DependencySet(
    resources=frozenset({pr_key, repo_res, title_key, body_key}),
    repositories=frozenset({repo_uuid}),
    provider_registrations=frozenset({service_uuid}),
    mapping_claims=frozenset({mapping.claim_key}),
    object_oids=frozenset({OID("FORMAT", commit1)}),
)
auth, adm, _ = create_local_admission_service(
    "provider_intake",
    grants=grants,
    selection=AdmissionSelection(all_selected=True),
)
prov_acq = ProviderAcquisition(cat_a, authorization=auth, admission=adm)
prov_report = prov_acq.admit_batch(batch)
assert len(prov_report.admitted_resources) >= 1
with Context.snapshot(cat_a) as context:
    original_roles = context.provider_repository_roles(pr_key)
    assert {role.scope.relation_kind for role in original_roles} == {
        "base_repository", "head_repository",
    }
    for role in original_roles:
        assert role.scope.provider_repository_id == mapping.resource.provider_resource_id
        assert role.supports[0].supporting_claims == (mapping.claim_key,)
        assert role.supports[0].target_repository_uuidv4 == repo_uuid
    original_relations = context.repository_relations(pr_key)
    assert {relation.relation_kind for relation in original_relations} == {
        "base_repository", "head_repository",
    }

# 3. Exercise Exchange export from A and import into B
svc_a = ExchangeService(cat_a)
pkg = svc_a.export_package(
    selection=ExchangeSelectionScope(all_selected=True),
    exported_at_us=1_700_000_100_000_000,
)
assert pkg.core is not None
assert pkg.context is not None

wire = encode_package(pkg)
decoded = decode_package(wire)

svc_b = ExchangeService(cat_b)
rep_b = svc_b.import_package(
    decoded,
    request=RequestIdentity(pkg.sender_catalog_instance_uuidv4, pkg.package_id),
    new_request=True,
    permitted_repository_uuidv4s=(repo_uuid,),
    grants=grants,
)
assert rep_b.admitted_core_objects >= 1
assert rep_b.admitted_context_resources >= 1
with Context.snapshot(cat_b) as context:
    assert context.provider_repository_roles(pr_key) == original_roles
    assert context.repository_relations(pr_key) == original_relations
    assert tuple(
        relation.relation for relation in context.repository_relations(mapping.resource)
    ) == (mapping,)

# Verify catalog B received commit1 in Core
core_b = GitCore(cat_b / "core.sqlite3")
try:
    assert core_b.read_metadata(OID("FORMAT", commit1)) is not None
finally:
    core_b.close()
""".replace("FORMAT", fmt)
    run([python, "-c", script], outside, env)
