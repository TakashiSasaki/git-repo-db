"""Independent metadata live-Notes and immutable incoming Capture checks."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import repo_catalog
from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.git.notes import GitNotesSource
from repo_catalog.adapters.sqlite.acquisition import InMemoryNotesProgress, UnlimitedWorkBudget
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.application.acquisition import GitAcquisition, PairedAcquisitionCoordinator
from repo_catalog.domain.acquisition import GitMetadataInput, NotesAcquisitionSpec
from repo_catalog.domain.p1_core import OID, Capture, NotesClaim, NotesGroup, Provenance, RepositoryClaim

ROOT = Path(sys.argv[1]).absolute()
ROOT.mkdir(mode=0o700, exist_ok=False)
EXPECT_FIXED = "--expect-fixed" in sys.argv[2:]
R0, R1, R2 = [f"10000000-0000-4000-8000-{n:012d}" for n in range(3)]
PROV = Provenance("outside-issuer", "original-observation", "name", "parser", "1")
results = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], text=True).strip(), "python": sys.version, "module": repo_catalog.__file__, "sqlite": sqlite3.sqlite_version, "sqlite_source_id": sqlite3.connect(":memory:").execute("SELECT sqlite_source_id()").fetchone()[0], "expect_fixed": EXPECT_FIXED, "checks": []}


def record(name, **facts):
    row = {"check": name, **facts}
    results["checks"].append(row)
    print(json.dumps(row, sort_keys=True), flush=True)


def catalog(name):
    cat = ROOT / name
    cat.mkdir(mode=0o700)
    instance = str(uuid4())
    for role in ("core", "context", "operational"):
        initialize(cat / f"{role}.sqlite3", role, R0, instance)
    return cat


def rows(cat):
    with closing(connect(cat / "core.sqlite3", "core")) as db:
        return {name: [tuple(row) for row in db.execute(f'SELECT * FROM "{name}" ORDER BY 1')] for (name,) in db.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name")}


def git(path, *args, data=None):
    return subprocess.run(["git", "-C", str(path), *args], input=data, capture_output=True, check=True).stdout.strip()


def source(name, fmt="sha1", with_note=False):
    repo = ROOT / (name + ".git")
    repo.mkdir(mode=0o700)
    git(repo, "init", "--bare", f"--object-format={fmt}")
    tree = git(repo, "hash-object", "-w", "-t", "tree", "--stdin", data=b"").decode()
    commit_body = f"tree {tree}\nauthor R3 <r3@example.invalid> 1 +0000\ncommitter R3 <r3@example.invalid> 1 +0000\n\nOriginal target\n".encode()
    commit = git(repo, "hash-object", "-w", "-t", "commit", "--stdin", data=commit_body).decode()
    git(repo, "update-ref", "refs/heads/main", commit)
    note_body = b"R3 independently verified note\n"
    if with_note:
        note = git(repo, "hash-object", "-w", "-t", "blob", "--stdin", data=note_body).decode()
        mapping = b"100644 " + commit.encode() + b"\0" + bytes.fromhex(note)
        notes_tree = git(repo, "hash-object", "-w", "-t", "tree", "--stdin", data=mapping).decode()
        git(repo, "update-ref", "refs/notes/review", notes_tree)
    return GitNotesSource(GitNativeSource(repo)), OID(fmt, commit), note_body


def unit(fmt="sha1", notes=None, target=None):
    return GitMetadataInput(R1, str(uuid4()), str(uuid4()), "same-original-attribution", 123, object_format=fmt, nominal_objects=(() if target is None else (target,)), repository_claims=(RepositoryClaim(R1, "name", "selected", PROV),), notes=notes)


def acquire(cat, value, paired=False, **kwargs):
    if paired:
        return PairedAcquisitionCoordinator(cat).admit_paired(git_input=value, **kwargs).git_report
    return GitAcquisition(cat, operational=cat).acquire_metadata_only(value, **kwargs)


# Durably scoped, actual non-seed live Notes acquisition; direct-tree ref avoids
# inventing a commit for a genuine direct-tree root.
for paired in (False, True):
    for fmt in ("sha1", "sha256"):
        cat = catalog(f"live-{paired}-{fmt}")
        notes_source, target, note_body = source(f"input-{paired}-{fmt}", fmt, True)
        value = unit(fmt, NotesAcquisitionSpec(discover_notes=True, acquire_inventories=True, target_oids=(target,), retain_note_bodies=True), target)
        try:
            report = acquire(cat, value, paired, notes_source=notes_source, new_request=True)
            before = rows(cat)
            retry = acquire(cat, value, paired, notes_source=notes_source)
            cap = report.notes_discoveries[0].captures[0]
            with closing(GitCore(cat / "core.sqlite3")) as core:
                body = core.read_note(cap, target, report.note_acquisitions[0].note)
            assert body == note_body and rows(cat) == before
            assert retry.notes_discoveries[0].captures == report.notes_discoveries[0].captures
            record(f"live-{paired}-{fmt}", accepted=True, actual_note_bytes=True, replay_rows_unchanged=True, original_capture_pair_preserved=True, discovery_count=len(report.notes_discoveries), inventory_count=len(report.notes_inventories))
        except Exception as error:
            record(f"live-{paired}-{fmt}", accepted=False, error_type=type(error).__name__, code=getattr(error, "code", None), error=str(error))
            if EXPECT_FIXED:
                raise

# A/B use identical Git objects but different actual source paths. Source identity
# must remain fixed even when caller explicitly owns cumulative work/progress.
cat = catalog("memory-switch")
source_a, _, _ = source("A")
source_b, _, _ = source("B")
value = unit(notes=NotesAcquisitionSpec(discover_notes=True))
work, progress = UnlimitedWorkBudget(), InMemoryNotesProgress()
service = GitAcquisition(cat)
service.acquire_metadata_only(value, notes_source=source_a, work=work, progress=progress)
before = rows(cat)
try:
    service.acquire_metadata_only(value, notes_source=source_b, work=work, progress=progress)
except Exception as error:
    unchanged = rows(cat) == before
    record("memory-source-A-to-B", rejected=True, code=getattr(error, "code", None), authoritative_rows_unchanged=unchanged)
    assert getattr(error, "code", None) == "INCOMPATIBLE_REPLAY" and unchanged
else:
    record("memory-source-A-to-B", rejected=False, different_source_scopes=source_a.scope != source_b.scope)
    if EXPECT_FIXED:
        raise AssertionError("same request switched live Notes source")

# Existing foreign owner can be hidden in a supplied selected-looking Capture.
# Test all incoming Notes paths even without a capture-owned Coverage record.
for paired in (False, True):
    for kind in ("explicit", "claim", "group"):
        cat = catalog(f"existing-foreign-{paired}-{kind}")
        original = Capture(str(uuid4()), str(uuid4()), R2, "genuine-issuer", "refs/notes/report", OID("sha1", "1" * 40))
        with closing(GitCore(cat / "core.sqlite3")) as core:
            core.admit_repository(R2)
            core.admit_capture(original)
        incoming = replace(original, repository_uuidv4=R1)
        if kind == "explicit": spec = NotesAcquisitionSpec(explicit_captures=(incoming,))
        elif kind == "claim": spec = NotesAcquisitionSpec(external_claims=(NotesClaim(incoming, original.root, original.root, PROV),))
        else: spec = NotesAcquisitionSpec(external_groups=(NotesGroup(incoming, "all", "known_empty", (), PROV),))
        value = unit(notes=spec)
        before = rows(cat)
        try:
            acquire(cat, value, paired, new_request=True)
        except Exception as error:
            unchanged = rows(cat) == before
            record(f"existing-foreign-{paired}-{kind}", rejected=True, code=getattr(error, "code", None), authoritative_rows_unchanged=unchanged, original_capture_preserved=rows(cat)["captures"] == before["captures"])
            if EXPECT_FIXED:
                assert unchanged and getattr(error, "code", None) == "REPOSITORY_SCOPE"
        else:
            raise AssertionError("foreign existing Capture was rebound")

# External attributed Capture.source is independent of outer intake attribution.
# Preserve it exactly; do not enforce source equality or relabel the issuer.
cat = catalog("external-source-preserved")
capture = Capture(str(uuid4()), str(uuid4()), R1, "genuine-different-external-issuer", "refs/notes/report", OID("sha1", "2" * 40))
value = unit(notes=NotesAcquisitionSpec(explicit_captures=(capture,)))
acquire(cat, value, new_request=True)
assert rows(cat)["captures"] == [capture.key]
record("external-attributed-source-preserved", exact_original_capture_key=True, outer_source_differs=True)
results["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
(ROOT / "results.json").write_text(json.dumps(results, sort_keys=True, indent=2))
