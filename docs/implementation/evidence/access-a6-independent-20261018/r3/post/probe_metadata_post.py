"""Independent selected-metadata counterexamples; no test fixture imports."""

from __future__ import annotations

import hashlib
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
from repo_catalog.adapters.sqlite.acquisition import InMemoryNotesProgress, UnlimitedWorkBudget
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.application.acquisition import GitAcquisition, PairedAcquisitionCoordinator
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.acquisition import GitMetadataInput, NotesAcquisitionSpec
from repo_catalog.domain.p1_coordination import RequestIdentity
from repo_catalog.domain.p1_core import OID, Capture, CoreCoverageScope, GitObservation, NativeObject, NotesClaim, NotesGroup, Provenance, RepositoryClaim
from repo_catalog.domain.p1_coverage import CoverageClaim

ROOT = Path(sys.argv[1]).absolute()
ROOT.mkdir(mode=0o700, exist_ok=False)
R0, R1, R2 = [f"10000000-0000-4000-8000-{n:012d}" for n in range(3)]
PROV = Provenance("external-r3", "original-r3", "field", "parser", "1")
results = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "cwd": os.getcwd(), "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], text=True).strip(), "module": repo_catalog.__file__, "python": sys.version, "sqlite": sqlite3.sqlite_version, "sqlite_source_id": sqlite3.connect(":memory:").execute("SELECT sqlite_source_id()").fetchone()[0], "checks": []}


def record(name, **facts):
    row = {"check": name, **facts}
    results["checks"].append(row)
    print(json.dumps(row, sort_keys=True), flush=True)


def catalog(name, seed=R0):
    cat = ROOT / name
    cat.mkdir(mode=0o700)
    instance = str(uuid4())
    for role in ("core", "context", "operational"):
        initialize(cat / f"{role}.sqlite3", role, seed, instance)
    return cat, instance


def rows(cat):
    with closing(connect(cat / "core.sqlite3", "core")) as db:
        return {name: [tuple(row) for row in db.execute(f'SELECT * FROM "{name}" ORDER BY 1')] for (name,) in db.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name")}


def budget(cat):
    with closing(connect(cat / "operational.sqlite3", "operational")) as db:
        return {kind: spent for kind, spent in db.execute("SELECT work_kind,sum(spent_or_reserved) FROM request_budgets GROUP BY work_kind")}


def unit(repo=R1, fmt="sha1"):
    origin, capture = str(uuid4()), str(uuid4())
    return GitMetadataInput(repo, origin, capture, "external-original", 123, object_format=fmt, nominal_objects=(OID(fmt, "1" * (40 if fmt == "sha1" else 64)),), repository_claims=(RepositoryClaim(repo, "endpoint", "https://original.example/R1", PROV),), observations=(GitObservation(origin, capture, repo, "acquisition", ("external-original",), {"source": "external-original", "observed_at_us": 123, "endpoint": "https://original.example/R1"}, PROV),))


def acquire(cat, value, paired=False, **kwargs):
    if paired:
        return PairedAcquisitionCoordinator(cat).admit_paired(git_input=value, **kwargs).git_report
    return GitAcquisition(cat, operational=cat).acquire_metadata_only(value, **kwargs)


def refuse(name, callback, cat, codes):
    before = rows(cat)
    try:
        callback()
    except Exception as error:
        unchanged = rows(cat) == before
        record(name, rejected=True, error_type=type(error).__name__, code=getattr(error, "code", None), authoritative_rows_unchanged=unchanged)
        assert getattr(error, "code", None) in codes and unchanged
    else:
        record(name, rejected=False)
        raise AssertionError(f"{name} was unexpectedly accepted")


# Standalone + prepared paired APIs, both actual Git object formats.
for paired in (False, True):
    for fmt in ("sha1", "sha256"):
        cat, instance = catalog(f"positive-{paired}-{fmt}")
        value = unit(fmt=fmt)
        report = acquire(cat, value, paired, new_request=True)
        before, spent = rows(cat), budget(cat)
        again = acquire(cat, value, paired)
        with closing(GitCore(cat / "core.sqlite3")) as core:
            identity = core.catalog_identity()
        after_spent = budget(cat)
        assert report.repository_uuidv4 == R1 and identity == (R0, instance)
        assert report.ref_observations == value.observations and rows(cat) == before
        assert after_spent["metadata_units"] > spent["metadata_units"]
        record(f"nonseed-{paired}-{fmt}", target=report.repository_uuidv4, physical_identity=identity, replay_same_rows=True, original_observations=True, metadata_work_before=spent["metadata_units"], metadata_work_after=after_spent["metadata_units"])

# Reproduce the exact baseline shape: outer seed R0, registered foreign R1.
# All nested repository-owned paths must reject before any ordinary Core row.
for paired in (False, True):
    for kind in ("claim", "observation", "notes", "notes_claim", "notes_group", "scope", "coverage", "proof"):
        cat, _ = catalog(f"foreign-{paired}-{kind}")
        with closing(GitCore(cat / "core.sqlite3")) as core:
            core.admit_repository(R1)
        value = unit(R0)
        capture = Capture(str(uuid4()), str(uuid4()), R1, "original-notes", "refs/notes/external", value.nominal_objects[0])
        scope = CoreCoverageScope("repository", (R1, "git_metadata"))
        claim = CoverageClaim(scope, 123, "partial")
        if kind == "claim": value = replace(value, repository_claims=(RepositoryClaim(R1, "name", "foreign", PROV),))
        elif kind == "observation": value = replace(value, observations=unit(R1).observations)
        elif kind == "notes": value = replace(value, notes=NotesAcquisitionSpec(explicit_captures=(capture,)))
        elif kind == "notes_claim": value = replace(value, notes=NotesAcquisitionSpec(external_claims=(NotesClaim(capture, value.nominal_objects[0], value.nominal_objects[0], PROV),)))
        elif kind == "notes_group": value = replace(value, notes=NotesAcquisitionSpec(external_groups=(NotesGroup(capture, "all", "known_empty", (), PROV),)))
        elif kind == "scope": value = replace(value, coverage_scopes=(scope,))
        elif kind == "coverage": value = replace(value, coverage_claims=(claim,))
        else: value = replace(value, coverage_proofs=((claim, (), PROV),))
        refuse(f"foreign-{paired}-{kind}", lambda: acquire(cat, value, paired, new_request=True), cat, {"REPOSITORY_SCOPE"})

# Test capture ownership through every containing field, both prepared paths;
# global OID/field Coverage stays legal without fabricated repository membership.
for paired in (False, True):
    for kind in ("scope", "claim", "proof"):
        for owner in ("selected", "foreign", "absent", "incoming"):
            cat, _ = catalog(f"capture-{paired}-{kind}-{owner}")
            value = unit()
            capture = Capture(str(uuid4()), str(uuid4()), R1 if owner in ("selected", "incoming") else R2, "capture-original", "refs/notes/external", value.nominal_objects[0])
            if owner in ("selected", "foreign"):
                with closing(GitCore(cat / "core.sqlite3")) as core:
                    core.admit_repository(capture.repository_uuidv4)
                    core.admit_capture(capture)
            if owner == "incoming": value = replace(value, notes=NotesAcquisitionSpec(explicit_captures=(capture,)))
            scope = CoreCoverageScope("capture", (*capture.pair, "inventory"))
            claim = CoverageClaim(scope, 123, "partial")
            if kind == "scope": value = replace(value, coverage_scopes=(scope,))
            elif kind == "claim": value = replace(value, coverage_claims=(claim,))
            else: value = replace(value, coverage_proofs=((claim, (), PROV),))
            if owner in ("selected", "incoming"):
                acquire(cat, value, paired, new_request=True)
                assert rows(cat)["captures"] == [capture.key]
                record(f"capture-{paired}-{kind}-{owner}", accepted=True, exact_capture_preserved=True)
            else:
                refuse(f"capture-{paired}-{kind}-{owner}", lambda: acquire(cat, value, paired, new_request=True), cat, {"REPOSITORY_SCOPE"})
    cat, _ = catalog(f"global-{paired}")
    value = unit()
    oid = value.nominal_objects[0]
    value = replace(value, coverage_scopes=(CoreCoverageScope("object", (*oid.key, "metadata")), CoreCoverageScope("field", (*oid.key, "message", "metadata"))))
    acquire(cat, value, paired, new_request=True)
    record(f"global-object-field-{paired}", accepted=True, coverage_owner_kinds=[row[0] for row in rows(cat)["coverage_scopes"]])

# Physical pair mismatch still fails with zero authoritative changes.
cat, _ = catalog("physical-pair")
foreign, _ = catalog("foreign-physical-pair", R2)
refuse("foreign-operational-identity", lambda: GitAcquisition(cat, operational=foreign).acquire_metadata_only(unit(), new_request=True), cat, {"STORE_IDENTITY"})

# Fixed original request inputs plus measured work. A new explicit request may
# add compatible facts while retaining the actual original Capture UUID pair.
for paired in (False, True):
    cat, _ = catalog(f"intent-{paired}")
    value = unit()
    acquire(cat, value, paired, new_request=True)
    for field, changed in (("source", replace(value, source_attribution="new-source")), ("time", replace(value, observed_at_us=124)), ("objects", replace(value, nominal_objects=(*value.nominal_objects, OID("sha1", "2" * 40))))):
        refuse(f"intent-{paired}-{field}", lambda: acquire(cat, changed, paired), cat, {"INCOMPATIBLE_REPLAY"})
    extra = replace(value, nominal_objects=(*value.nominal_objects, OID("sha1", "3" * 40)))
    report = acquire(cat, extra, paired, new_request=True, request_identity=RequestIdentity(str(uuid4()), str(uuid4())))
    assert (report.capture_origin_uuidv4, report.capture_uuidv4) == (value.capture_origin_uuidv4, value.capture_uuidv4)
    record(f"new-request-same-capture-{paired}", exact_original_pair=True, added_objects=[list(oid.key) for oid in report.admitted_objects])

# Retained native bytes are rechecked/charged; Operational saves coordinates only.
cat, _ = catalog("no-raw-body")
body = b"tree 4b825dc642cb6eb9a060e54bf8d69288fbee4904\nauthor R3 <r3@example.invalid> 1 +0000\ncommitter R3 <r3@example.invalid> 1 +0000\n\nunique-body-canary-28ef\n"
oid = OID("sha1", hashlib.sha1(f"commit {len(body)}\0".encode() + body).hexdigest())
native = NativeObject(oid, "commit", body, len(body), hashlib.sha256(body).hexdigest())
value = replace(unit(), native_objects=(native,))
acquire(cat, value, new_request=True)
prior = budget(cat)
acquire(cat, value)
after = budget(cat)
with closing(connect(cat / "operational.sqlite3", "operational")) as db:
    cursors = [row[0] for row in db.execute("SELECT cursor_json FROM request_continuations")]
assert all(body.decode() not in encoded and body.hex() not in encoded and "unique-body-canary-28ef" not in encoded for encoded in cursors)
assert after["input_bytes"] > prior["input_bytes"] and after["verification_bytes"] > prior["verification_bytes"]
record("no-raw-native-staging", body_text_or_hex_in_progress=False, budgets_before=prior, budgets_after=after)

# Same-seed onward preservation and mutation-free cross-seed refusal unchanged.
source = cat
package = ExchangeService(source).export_package()
same_seed, _ = catalog("exchange-same-seed")
ExchangeService(same_seed).import_package(package, new_request=True)
again = ExchangeService(same_seed).export_package()
assert again.core["repository_claims"] == package.core["repository_claims"]
assert again.core["git_observations"] == package.core["git_observations"]
record("exchange-same-seed-onward", exact_claims=True, exact_observations=True)
different, _ = catalog("exchange-different-seed", R2)
refuse("exchange-cross-seed-fence", lambda: ExchangeService(different).import_package(package, new_request=True), different, {"REPOSITORY_MISMATCH"})
results["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
(ROOT / "results.json").write_text(json.dumps(results, sort_keys=True, indent=2))
