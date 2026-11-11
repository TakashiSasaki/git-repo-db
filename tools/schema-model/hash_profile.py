"""Bounded hash witnesses; graph conformance does not establish byte equality."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from collections import Counter
from unittest.mock import patch

PROFILE = "filesystem-hash-v1"
EXPECTED_FS_COUNTS = {
    "catalog_metadata": 5,
    "scans": 9,
    "entries": 15,
    "scan_outcomes": 7,
}
EXPECTED_HASH_COUNTS = {"complete": 3, "changed": 1, "error": 1, "not-applicable": 10}
EXPECTED_KIND_COUNTS = {
    "file": 5,
    "directory": 7,
    "unknown": 1,
    "symlink": 1,
    "special": 1,
}
CASE_NAMES = {
    "complete",
    "changed",
    "error",
    "symlink",
    "special",
    "complete_with_error",
    "unknown",
    "directory",
}


def populate(catalog, root, api, outcome_cases):
    """Exercise scan() plus precisely labeled SQL-only DDL boundary witnesses."""
    from repo_catalog.filesystem import FilesystemCatalog, scanner
    from repo_catalog.filesystem.models import occurrence_uuid

    results = {}
    cases = {}
    for state in ("changed", "error"):
        folder = root / (state + "-root")
        folder.mkdir()
        target = folder / "file"
        target.write_bytes(b"a" * 1024)
        original = scanner.os.read
        mutated = False

        def controlled_read(fd, count):
            nonlocal mutated
            if state == "error":
                raise PermissionError(13, "controlled read failure")
            block = original(fd, count)
            if block and not mutated:
                mutated = True
                target.write_bytes(b"different")
            return block

        with patch.object(scanner.os, "read", controlled_read):
            scan = catalog.scan(folder)
        row = next(
            e
            for e in catalog.iter_entries(scan.scan_uuid)
            if e.relative_path == b"file"
        )
        assert scan.status == "partial" and scan.errors == 1
        assert scan.enumeration_complete and not scan.hashing_complete
        assert row.hash_status == state and row.sha256 is None and row.error is not None
        if state == "changed":
            assert mutated
        results[state] = {
            "status": row.hash_status,
            "digest": row.sha256,
            "error": row.error,
            "scan_status": scan.status,
            "enumeration_complete": scan.enumeration_complete,
            "hashing_complete": scan.hashing_complete,
        }
        cases[state] = [catalog.namespace_uuid, scan.scan_uuid, b"file".hex()]

    # No symlink/device is opened: these are explicitly SQL-only boundary rows.
    # DDL permits non-file size, and complete entry with an error. Do not invent
    # stronger universal rules; the scan itself must not claim complete on errors.
    boundary_scan = occurrence_uuid()
    empty_digest = hashlib.sha256(b"").hexdigest()
    with catalog._db:
        catalog._db.execute(
            "INSERT INTO scans VALUES (?,?,?,?,?)",
            (catalog.namespace_uuid, boundary_scan, os.fsencode(root), 1, "[]"),
        )
        for name, kind, size, digest, status, error in (
            ("symlink", "symlink", None, None, "not-applicable", None),
            ("special", "special", 0, None, "not-applicable", None),
            ("complete_with_error", "file", 0, empty_digest, "complete", ""),
        ):
            path = name.encode("ascii")
            catalog._db.execute(
                "INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    catalog.namespace_uuid,
                    boundary_scan,
                    path,
                    kind,
                    size,
                    None,
                    None,
                    None,
                    None,
                    None,
                    digest,
                    status,
                    error,
                    None,
                    None,
                ),
            )
            cases[name] = [catalog.namespace_uuid, boundary_scan, path.hex()]
        catalog._db.execute(
            "INSERT INTO scan_outcomes VALUES (?,?,?,?,?,?)",
            (catalog.namespace_uuid, boundary_scan, 1, "partial", 3, 1),
        )
    cases["complete"] = [*outcome_cases["complete"], b"empty".hex()]
    cases["directory"] = [*outcome_cases["complete"], ""]
    cases["unknown"] = [*outcome_cases["partial"], ""]
    complete = next(
        e
        for e in catalog.iter_entries(outcome_cases["complete"][1])
        if e.relative_path == b"empty"
    )
    assert complete.sha256 == empty_digest and complete.hash_status == "complete"
    api["hash_scanner_controls"] = results
    api["empty_file_sha256"] = complete.sha256
    api["hash_profile_verify"] = catalog.verify()["integrity"]

    bad_variants = {
        "missing_digest": {"sha256": None},
        "malformed_digest": {"sha256": "g" * 64},
        "uppercase_digest": {"sha256": "A" * 64},
        "short_digest": {"sha256": "a" * 63},
        "digest_on_error": {"hash_status": "error", "error": "read"},
        "changed_without_reason": {"hash_status": "changed", "sha256": None},
        "error_without_reason": {"hash_status": "error", "sha256": None},
        "directory_digest": {"kind": "directory"},
        "missing_file_size": {"size": None},
        "negative_size": {"size": -1},
        "nonfile_error_state": {
            "kind": "special",
            "hash_status": "error",
            "sha256": None,
            "error": "read",
        },
        "pending_persisted": {"hash_status": "pending", "sha256": None},
        "unknown_hash_state": {"hash_status": "unknown", "sha256": None},
    }
    controls = {}
    with FilesystemCatalog.initialize(root / "hash-rejections.db") as bad:
        scan = occurrence_uuid()
        with bad._db:
            bad._db.execute(
                "INSERT INTO scans VALUES (?,?,?,?,?)",
                (bad.namespace_uuid, scan, os.fsencode(root), 1, "[]"),
            )
        for label, delta in bad_variants.items():
            row = dict(
                namespace_uuid=bad.namespace_uuid,
                scan_uuid=scan,
                relative_path=label.encode("ascii"),
                kind="file",
                size=0,
                mtime_ns=None,
                birthtime_ns=None,
                ctime_ns=None,
                attributes=None,
                mode=None,
                sha256=empty_digest,
                hash_status="complete",
                error=None,
                link_target=None,
                observed_us=None,
            )
            row.update(delta)
            try:
                with bad._db:
                    bad._db.execute(
                        "INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        tuple(row.values()),
                    )
            except sqlite3.IntegrityError as exc:
                controls[label] = str(exc)
            else:
                raise AssertionError("SQLite accepted invalid hash tuple: " + label)
        assert bad._db.execute("SELECT count(*) FROM entries").fetchone()[0] == 0
        bad.verify()
    api["hash_sqlite_rejections"] = controls
    return cases


def check_coverage(data, decoded):
    """Positive profile coverage is independent of RDF; negatives use values."""
    cases = data["hash_cases"]
    if not isinstance(cases, dict) or set(cases) != CASE_NAMES:
        raise ValueError("F1-B required case declarations missing")
    entries = [
        r
        for (store, table, _), r in decoded.items()
        if store == "filesystem" and table == "entries"
    ]
    if Counter(r["hash_status"] for r in entries) != EXPECTED_HASH_COUNTS:
        raise ValueError("F1-B declared hash-state coverage missing")
    if Counter(r["kind"] for r in entries) != EXPECTED_KIND_COUNTS:
        raise ValueError("F1-B declared file-kind coverage missing")
    seen = set()
    for key in cases.values():
        if (
            not isinstance(key, list)
            or len(key) != 3
            or any(type(v) is not str for v in key)
        ):
            raise ValueError("malformed F1-B qualified entry key")
        path = bytes.fromhex(key[2])
        if path.hex() != key[2]:
            raise ValueError("noncanonical F1-B path encoding")
        key = (key[0], key[1], path)
        if key in seen:
            raise ValueError("repeated F1-B case identity")
        seen.add(key)
        if (
            sum(
                (r["namespace_uuid"], r["scan_uuid"], r["relative_path"]) == key
                for r in entries
            )
            != 1
        ):
            raise ValueError("F1-B case occurrence missing or repeated")
