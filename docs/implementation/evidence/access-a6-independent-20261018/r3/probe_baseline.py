"""Independent R3 synthetic API/SQL probes. Never edits the reviewed checkout."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.sqlite import access_schema, p1_schema
from repo_catalog.adapters.sqlite.access_backup import AccessBackup
from repo_catalog.adapters.sqlite.access_connections import AccessConnections
from repo_catalog.adapters.sqlite.acquisition import (
    InMemoryNotesProgress,
    UnlimitedWorkBudget,
)
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.application.acquisition import GitAcquisition
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.access_connections import (
    AssignmentKey,
    ConnectionConfiguration,
    LocatorConnection,
    RepositoryBinding,
    ScopeExecutionContext,
    canonical,
)
from repo_catalog.domain.access_registry import AccessScope, ScopeLocatorRegistration
from repo_catalog.domain.acquisition import GitMetadataInput, GitNativeAcquisitionRequest
from repo_catalog.domain.exchange import ExchangeSelectionScope, empty_context_section
from repo_catalog.domain.p1_core import OID, Provenance, RepositoryClaim

ROOT = Path(sys.argv[1]).absolute()
ROOT.mkdir(mode=0o700, parents=True, exist_ok=False)
RESULTS = {
    "started_at_utc": datetime.now(timezone.utc).isoformat(),
    "python": sys.version,
    "sqlite": sqlite3.sqlite_version,
    "sqlite_source_id": sqlite3.connect(":memory:").execute("SELECT sqlite_source_id()").fetchone()[0],
    "steps": [],
}
R0 = "10000000-0000-4000-8000-000000000000"
R1 = "10000000-0000-4000-8000-000000000001"
R2 = "10000000-0000-4000-8000-000000000002"
PROV = Provenance("r3-independent", "original-event", "endpoint", "external", "1")


def record(name, **facts):
    item = {"step": name, **facts}
    RESULTS["steps"].append(item)
    print(json.dumps(item, ensure_ascii=False, sort_keys=True), flush=True)


def capture(name, callback):
    try:
        result = callback()
        record(name, outcome="accepted", result=str(result))
        return result
    except Exception as error:
        record(name, outcome="rejected", error_type=type(error).__name__, code=getattr(error, "code", None), message=str(error))
        return None


def catalog(name, seed, roles=("core", "operational")):
    directory = ROOT / name
    directory.mkdir(mode=0o700)
    instance = str(uuid4())
    for role in roles:
        p1_schema.initialize(directory / f"{role}.sqlite3", role, seed, instance)
    return directory


def query(directory, sql):
    with closing(GitCore(directory / "core.sqlite3")) as core:
        return [tuple(row) for row in core.sql(sql)]


def seal(data):
    payload = {key: value for key, value in data.items() if key != "digest_sha256"}
    data["digest_sha256"] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return data


def git(directory, *args, data=None):
    return subprocess.run(["git", "-C", str(directory), *args], input=data, capture_output=True, check=True).stdout.strip()


source = catalog("source-r0", R0)
with closing(GitCore(source / "core.sqlite3")) as core:
    core.admit_repository(R1)
unit = GitMetadataInput(R1, str(uuid4()), str(uuid4()), "original-r1-source", 17, repository_claims=(RepositoryClaim(R1, "endpoint", "ssh://source.example/R1", PROV),), nominal_objects=(OID("sha1", "1" * 40),))
capture("registered_nonseed_external_metadata", lambda: GitAcquisition(source, operational=source).acquire_metadata_only(unit, new_request=True))
record("external_metadata_after_rejection", repositories=query(source, "SELECT * FROM repositories ORDER BY repository_uuidv4"), claims=query(source, "SELECT * FROM repository_claims"), objects=query(source, "SELECT * FROM git_objects"))

# Independent native path, actual Git objects, same additional Repository R1.
repo = ROOT / "native-r1.git"
repo.mkdir(mode=0o700)
git(repo, "init", "--bare", "--object-format=sha1")
tree = git(repo, "hash-object", "-w", "-t", "tree", "--stdin", data=b"").decode()
body = f"tree {tree}\nauthor Reviewer <reviewer@example.invalid> 1 +0000\ncommitter Reviewer <reviewer@example.invalid> 1 +0000\n\nR3 independent\n".encode()
commit = git(repo, "hash-object", "-w", "-t", "commit", "--stdin", data=body).decode()
git(repo, "update-ref", "refs/heads/main", commit)
native_request = GitNativeAcquisitionRequest(R1, str(uuid4()), str(uuid4()), "original-r1-source", 19, select_oids=(OID("sha1", commit),), repository_claims=(RepositoryClaim(R1, "endpoint", "ssh://source.example/R1", PROV),))
capture("nonseed_native_actual_git", lambda: GitAcquisition(source, operational=source).acquire_from_native(GitNativeSource(repo), native_request, new_request=True))
record("native_sql", identity=query(source, "SELECT repository_uuidv4,catalog_instance_uuidv4 FROM store_identity"), repositories=query(source, "SELECT * FROM repositories ORDER BY repository_uuidv4"), claims=query(source, "SELECT * FROM repository_claims"), observations=query(source, "SELECT repository_uuidv4,kind,value FROM git_observations ORDER BY repository_uuidv4,kind"))

package = ExchangeService(source).export_package(selection=ExchangeSelectionScope(include_context=False))
(ROOT / "r0-envelope-r1-payload.json").write_text(json.dumps(package.to_dict(), ensure_ascii=False, sort_keys=True, indent=2))
record("native_export", envelope_repository=package.repository_uuidv4, payload_repositories=package.core["repositories"], payload_claims=package.core["repository_claims"], payload_observation_repositories=sorted({row["repository_uuidv4"] for row in package.core["git_observations"]}))
receiver = catalog("receiver-r2", R2)
capture("r1_payload_into_receiver_seed_r2", lambda: ExchangeService(receiver).import_package(package, new_request=True))
record("receiver_r2_after_rejection", repositories=query(receiver, "SELECT * FROM repositories"), objects=query(receiver, "SELECT * FROM git_objects"))
same_seed = catalog("receiver-r0", R0)
capture("same_seed_import_control", lambda: ExchangeService(same_seed).import_package(package, new_request=True))
again = ExchangeService(same_seed).export_package(selection=ExchangeSelectionScope(include_context=False))
record("same_seed_reexport", repository_claims_unchanged=again.core["repository_claims"] == package.core["repository_claims"], observations_unchanged=again.core["git_observations"] == package.core["git_observations"], envelope_repository=again.repository_uuidv4)

# Existing seed guard does not validate nested input's target selection.
mixed = GitMetadataInput(R0, str(uuid4()), str(uuid4()), "declared-r0-source", 23, repository_claims=(RepositoryClaim(R1, "name", "foreign-to-unit-r0", PROV),))
capture("seed_unit_with_registered_foreign_claim", lambda: GitAcquisition(source, operational=source).acquire_metadata_only(mixed, new_request=True))
record("mixed_claim_sql", claims=query(source, "SELECT repository_uuidv4,field,value FROM repository_claims ORDER BY repository_uuidv4,field,value"))

# Direct JSON RepositoryClaim codec, receiver independent typed admission.
direct = catalog("direct-values-source", R0)
values = [("name", ""), ("name", "a"), ("git_path", "/srv/日本語/repo"), ("endpoint", "https://origin.example/R0"), ("object_format", "sha256"), ("observation_us", None), ("observation_us", 17), ("identity_assertion", R1), ("identity_cancellation", R1)]
with closing(GitCore(direct / "core.sqlite3")) as core:
    for index, (field, value) in enumerate(values):
        distinct_provenance = Provenance("r3-independent", f"original-event-{index}", field, "external", "1")
        core.admit_repository_claim(RepositoryClaim(R0, field, value, distinct_provenance))
direct_package = ExchangeService(direct).export_package()
direct_receiver = catalog("direct-values-receiver", R0)
ExchangeService(direct_receiver).import_package(direct_package, new_request=True)
ExchangeService(direct_receiver).import_package(direct_package, new_request=True)
record("direct_claim_roundtrip", exact_sql=query(direct, "SELECT * FROM repository_claims ORDER BY repository_uuidv4,field,value,provenance") == query(direct_receiver, "SELECT * FROM repository_claims ORDER BY repository_uuidv4,field,value,provenance"), exact_reexport=ExchangeService(direct_receiver).export_package().core["repository_claims"] == direct_package.core["repository_claims"], count=len(values))

# A malicious but correctly rechecksummed unselected Context registration must
# fail before even one otherwise valid nominal Core object is admitted.
unselected = catalog("unselected-context-receiver", R0)
data = ExchangeService(direct).export_package().to_dict()
data["core"]["git_objects"].append({"object_format": "sha1", "full_oid": "f" * 40})
data["selection_scope"]["include_context"] = False
data["context"] = empty_context_section()
data["context"]["providers"] = [{"service_instance_uuidv4": str(uuid4()), "provider_kind": "github", "configuration_json": canonical({"credential_ref": "synthetic-ref"})}]
capture("unselected_context_registration", lambda: ExchangeService(unselected).import_package(seal(data), new_request=True))
record("unselected_context_after_rejection", objects=query(unselected, "SELECT * FROM git_objects"), access_created=(unselected / "access.sqlite3").exists(), recovery_stop=(unselected / "p1-recovery-stop.json").exists())

# Access snapshot from committed WAL using actual APIs; live input unchanged,
# all history kept, grants removed, restore disabled, bundle bytes untouched.
access_dir = ROOT / "access"
access_dir.mkdir(mode=0o700)
live = access_dir / "live.sqlite3"
access_schema.initialize(live)
scope = "20000000-0000-4000-8000-000000000001"
key = AssignmentKey(scope, "/repos/r1", "local")
registrations = [ScopeLocatorRegistration(scope, t, uri) for t, uri in [(11, "file:///old"), (22, "file:///new"), (33, "file:///old"), (33, "file:///tie")]]
with AccessConnections(live, writable=True) as store:
    store.register_scope(AccessScope(scope, "R3 synthetic Scope"))
    for reg in registrations:
        store.register_locator(reg)
        store.set_locator_enabled(reg, True)
    store.configure_scope(ScopeExecutionContext(scope, canonical({"version": 1, "executor_kind": "local", "executor_ref": "reviewer", "identity_view": "owner", "path_dialect": "posix"}), True))
    store.bind_repository(RepositoryBinding(scope, key.locator_text, R1, True))
    store.configure_connection(ConnectionConfiguration(scope, key.configuration_name, canonical({"version": 1, "transport": "file", "path_dialect": "posix"}), True))
    store.assign_connection(LocatorConnection(key, True))
    store.record_local_approval(store.review_plan(R1, scope, registration=registrations[-1]), 44)


def access_rows(path):
    db = sqlite3.connect(path)
    try:
        access_schema.register_functions(db)
        return {table: [tuple(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY 1")] for table in access_schema.TABLES}
    finally:
        db.close()


writer = sqlite3.connect(live, isolation_level=None)
access_schema.register_functions(writer)
writer.execute("PRAGMA foreign_keys=ON")
writer.execute("PRAGMA wal_autocheckpoint=0")
wal_reg = ScopeLocatorRegistration(scope, 55, "file:///committed-wal")
writer.execute("INSERT INTO scope_locators VALUES(?,?,?)", wal_reg.key)
before = access_rows(live)
wal_length = Path(str(live) + "-wal").stat().st_size
bundle = access_dir / "bundle"
AccessBackup().backup(live, bundle)
writer.close()
bundle_bytes = {item.name: item.read_bytes() for item in bundle.iterdir()}
snapshot = access_rows(bundle / "access.sqlite3")
restore = access_dir / "restore"
AccessBackup().restore(bundle, restore)
restored = access_rows(restore / "access.sqlite3")
record("backup_restore_independent", committed_wal_bytes=wal_length, source_rows_unchanged=access_rows(live) == before, all_history=snapshot["scope_locators"] == before["scope_locators"] == restored["scope_locators"], source_grants=len(before["local_access_grants"]), backup_grants=len(snapshot["local_access_grants"]), restored_grants=len(restored["local_access_grants"]), restored_enabled_routes=sum(row[-1] for row in restored["scope_locator_controls"]), input_bundle_bytes_unchanged={item.name: item.read_bytes() for item in bundle.iterdir()} == bundle_bytes)
capture("restore_existing_destination", lambda: AccessBackup().restore(bundle, restore))
record("existing_destination_preserved", history_unchanged=access_rows(restore / "access.sqlite3")["scope_locators"] == restored["scope_locators"])
RESULTS["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
(ROOT / "results.json").write_text(json.dumps(RESULTS, ensure_ascii=False, sort_keys=True, indent=2))
