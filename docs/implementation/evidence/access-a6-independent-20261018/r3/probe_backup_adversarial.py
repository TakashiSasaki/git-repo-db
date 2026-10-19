"""Independent backup snapshot and publication probes on synthetic artifacts only."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from repo_catalog.adapters.sqlite import access_backup as module
from repo_catalog.adapters.sqlite import access_schema as schema
from repo_catalog.adapters.sqlite.access_backup import AccessBackup
from repo_catalog.domain.access_registry import ScopeLocatorRegistration

BASE = Path(sys.argv[1]).absolute()
ROOT = Path(sys.argv[2]).absolute()
ROOT.mkdir(mode=0o700, exist_ok=False)
input_source = BASE / "access/live.sqlite3"
source = ROOT / "live.sqlite3"
copy_source = sqlite3.connect(input_source.as_uri() + "?mode=ro", uri=True)
copy_target = sqlite3.connect(source)
copy_source.backup(copy_target)
copy_target.close()
copy_source.close()
os.chmod(source, 0o600)
valid_bundle = BASE / "access/bundle"
results = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "sqlite": sqlite3.sqlite_version, "sqlite_source_id": sqlite3.connect(":memory:").execute("SELECT sqlite_source_id()").fetchone()[0], "steps": []}


def record(name, **facts):
    item = {"step": name, **facts}
    results["steps"].append(item)
    print(json.dumps(item, sort_keys=True), flush=True)


def attempt(name, callback):
    try:
        value = callback()
        record(name, outcome="accepted", value=str(value))
    except Exception as error:
        record(name, outcome="rejected", code=getattr(error, "code", None), error_type=type(error).__name__, message=str(error))


def raw(path):
    db = sqlite3.connect(path, isolation_level=None)
    schema.register_functions(db)
    return db


def content(path):
    return {item.name: hashlib.sha256(item.read_bytes()).hexdigest() for item in path.iterdir()}


def reseal(path):
    manifest = json.loads((path / "manifest.json").read_bytes())
    payload = (path / "access.sqlite3").read_bytes()
    manifest["store"]["bytes"] = len(payload)
    manifest["store"]["sha256"] = hashlib.sha256(payload).hexdigest()
    encoded = module._encoded(manifest)
    (path / "manifest.json").write_bytes(encoded)
    (path / "manifest.sha256").write_bytes(hashlib.sha256(encoded).hexdigest().encode() + b"\n")


# Hold genuine committed WAL, then add a later row after _live has yielded its
# actual checked/pinned read transaction. Unlike the baseline's existing test,
# injection does not intercept row counting or manipulate a result value.
writer = raw(source)
writer.execute("PRAGMA wal_autocheckpoint=0")
scope = "20000000-0000-4000-8000-000000000001"
latest_time = writer.execute("SELECT max(registered_at_us) FROM scope_locators").fetchone()[0]
before_reg = ScopeLocatorRegistration(scope, latest_time + 11, "file:///before-snapshot")
after_reg = ScopeLocatorRegistration(scope, latest_time + 22, "file:///after-snapshot")
writer.execute("INSERT INTO scope_locators VALUES(?,?,?)", before_reg.key)
original_live = module._live


@contextmanager
def live_with_later_commit(*args, **kwargs):
    with original_live(*args, **kwargs) as result:
        writer.execute("INSERT INTO scope_locators VALUES(?,?,?)", after_reg.key)
        yield result


snapshot_dir = ROOT / "snapshot"
with patch.object(module, "_live", live_with_later_commit):
    AccessBackup().backup(source, snapshot_dir)
writer.close()
db = raw(snapshot_dir / "access.sqlite3")
snapshot_rows = db.execute("SELECT * FROM scope_locators ORDER BY registered_at_us,scope_locator_uri").fetchall()
db.close()
db = raw(source)
live_rows = db.execute("SELECT * FROM scope_locators ORDER BY registered_at_us,scope_locator_uri").fetchall()
db.close()
record("concurrent_wal_cut", before_in_snapshot=before_reg.key in snapshot_rows, later_in_snapshot=after_reg.key in snapshot_rows, later_in_source=after_reg.key in live_rows, snapshot_rows=snapshot_rows, source_rows=live_rows)

for mutation in ("extra-member", "invalid-check", "invalid-fk", "hash-mismatch", "extra-manifest-key"):
    bundle = ROOT / mutation
    shutil.copytree(valid_bundle, bundle)
    if mutation == "extra-member":
        (bundle / "access.sqlite3-wal").write_bytes(b"untrusted sidecar")
        os.chmod(bundle / "access.sqlite3-wal", 0o600)
    elif mutation == "invalid-check":
        db = raw(bundle / "access.sqlite3")
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("UPDATE access_scopes SET display_name=char(0)")
        db.close()
        reseal(bundle)
    elif mutation == "invalid-fk":
        db = raw(bundle / "access.sqlite3")
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("DELETE FROM connection_configurations")
        db.close()
        reseal(bundle)
    elif mutation == "hash-mismatch":
        payload = bytearray((bundle / "access.sqlite3").read_bytes())
        payload[-1] ^= 1
        (bundle / "access.sqlite3").write_bytes(payload)
    else:
        manifest = json.loads((bundle / "manifest.json").read_bytes())
        manifest["activate"] = True
        encoded = module._encoded(manifest)
        (bundle / "manifest.json").write_bytes(encoded)
        (bundle / "manifest.sha256").write_bytes(hashlib.sha256(encoded).hexdigest().encode() + b"\n")
    before = content(bundle)
    destination = ROOT / f"restore-{mutation}"
    attempt(mutation, lambda: AccessBackup().restore(bundle, destination))
    record(mutation + "-aftermath", destination_absent=not destination.exists(), input_unchanged=content(bundle) == before)

destination = ROOT / "raced-empty-target"
original_publish = module._publish


def publish_after_empty_target(fd, stage, target):
    destination.mkdir(mode=0o700)
    original_publish(fd, stage, target)


with patch.object(module, "_publish", publish_after_empty_target):
    attempt("raced_empty_directory", lambda: AccessBackup().restore(valid_bundle, destination))
record("raced_empty_directory-aftermath", target_still_empty=destination.is_dir() and list(destination.iterdir()) == [], stage_paths=[item.name for item in ROOT.glob(".access-stage-*")])

published = False
original_fsync = os.fsync


def mark_publish(*args):
    global published
    original_publish(*args)
    published = True


def fail_postpublication_sync(fd):
    if published:
        raise OSError("independent injected fsync after rename")
    original_fsync(fd)


uncertain = ROOT / "uncertain-target"
with patch.object(module, "_publish", mark_publish), patch.object(module.os, "fsync", fail_postpublication_sync):
    attempt("postpublication_fsync_failure", lambda: AccessBackup().restore(valid_bundle, uncertain))
record("postpublication_fsync_failure-aftermath", target_preserved=uncertain.is_dir(), exact_members=sorted(item.name for item in uncertain.iterdir()))
db = raw(uncertain / "access.sqlite3")
record("uncertain_target_valid_but_inactive", integrity=db.execute("PRAGMA integrity_check").fetchall(), grants=db.execute("SELECT count(*) FROM local_access_grants").fetchone()[0], enabled_routes=db.execute("SELECT count(*) FROM scope_locator_controls WHERE enabled=1").fetchone()[0])
db.close()
results["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
(ROOT / "results.json").write_text(json.dumps(results, sort_keys=True, indent=2))
