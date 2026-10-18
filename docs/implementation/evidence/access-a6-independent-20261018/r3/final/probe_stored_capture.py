"""Independent touched-Capture corruption/immutable-mismatch stop boundaries."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import repo_catalog
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import initialize, register_functions
from repo_catalog.application.acquisition import GitAcquisition, PairedAcquisitionCoordinator
from repo_catalog.domain.acquisition import GitMetadataInput, NotesAcquisitionSpec
from repo_catalog.domain.p1_core import Capture, OID

ROOT = Path(sys.argv[1]).absolute()
ROOT.mkdir(mode=0o700, exist_ok=False)
EXPECT_FIXED = "--expect-fixed" in sys.argv[2:]
results = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], text=True).strip(), "module": repo_catalog.__file__, "sqlite": sqlite3.sqlite_version, "sqlite_source_id": sqlite3.connect(":memory:").execute("SELECT sqlite_source_id()").fetchone()[0], "expect_fixed": EXPECT_FIXED, "checks": []}


def content(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observe(kind, paired):
    cat = ROOT / f"{kind}-{paired}"
    cat.mkdir(mode=0o700)
    seed, target, instance = [str(uuid4()) for _ in range(3)]
    for role in ("core", "context", "operational"):
        initialize(cat / f"{role}.sqlite3", role, seed, instance)
    original = Capture(str(uuid4()), str(uuid4()), target, "valid-original", "refs/notes/test", OID("sha1", "1" * 40))
    with closing(GitCore(cat / "core.sqlite3")) as core:
        core.admit_repository(target)
        core.admit_capture(original)
    incoming = original
    if kind == "incoming-conflict":
        incoming = replace(original, source="another-valid-original")
    else:
        db = sqlite3.connect(cat / "core.sqlite3")
        register_functions(db)
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("PRAGMA foreign_keys=OFF")
        if kind in ("missing-repository", "missing-root"):
            table = "repositories" if kind == "missing-repository" else "git_objects"
            name = f"p1_immutable_{table}_delete"
            trigger = db.execute("SELECT sql FROM sqlite_schema WHERE name=?", (name,)).fetchone()[0]
            db.execute(f"DROP TRIGGER {name}")
            if kind == "missing-repository":
                db.execute("DELETE FROM repositories WHERE repository_uuidv4=?", (target,))
            else:
                db.execute("DELETE FROM git_objects WHERE object_format=? AND full_oid=?", original.root.key)
        else:
            name = "p1_immutable_captures_update"
            trigger = db.execute("SELECT sql FROM sqlite_schema WHERE name=?", (name,)).fetchone()[0]
            db.execute(f"DROP TRIGGER {name}")
            if kind == "empty-source": db.execute("UPDATE captures SET source=''")
            elif kind == "invalid-utf8": db.execute("UPDATE captures SET source=CAST(X'ff' AS TEXT)")
            elif kind == "invalid-ref": db.execute("UPDATE captures SET ref='[\"wrong-tag\",\"726566732f6e6f7465732f74657374\"]'")
            elif kind == "invalid-root": db.execute("UPDATE captures SET root='not-a-full-oid'")
        db.execute(trigger)
        db.commit()
        db.close()
    before = content(cat / "core.sqlite3")
    value = GitMetadataInput(target, str(uuid4()), str(uuid4()), "external", 123, notes=NotesAcquisitionSpec(explicit_captures=(incoming,)))
    try:
        if paired:
            PairedAcquisitionCoordinator(cat).admit_paired(git_input=value, new_request=True)
        else:
            GitAcquisition(cat, operational=cat).acquire_metadata_only(value, new_request=True)
    except Exception as error:
        result = {"kind": kind, "paired": paired, "accepted": False, "error_type": type(error).__name__, "code": getattr(error, "code", None), "error": str(error)}
    else:
        result = {"kind": kind, "paired": paired, "accepted": True}
    result["persistent_stop"] = (cat / "p1-recovery-stop.json").exists()
    result["authoritative_file_unchanged"] = content(cat / "core.sqlite3") == before
    results["checks"].append(result)
    print(json.dumps(result, sort_keys=True), flush=True)
    if EXPECT_FIXED:
        assert not result["accepted"] and result["authoritative_file_unchanged"]
        if kind == "incoming-conflict":
            assert result["code"] == "INCOMPATIBLE_REPLAY" and not result["persistent_stop"]
        else:
            assert result["code"] == "AUTHORITATIVE_CORRUPTION" and result["persistent_stop"]


for kind in ("empty-source", "invalid-utf8", "invalid-ref", "invalid-root", "missing-repository", "missing-root", "incoming-conflict"):
    for paired in (False, True):
        observe(kind, paired)
results["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
(ROOT / "results.json").write_text(json.dumps(results, sort_keys=True, indent=2))
