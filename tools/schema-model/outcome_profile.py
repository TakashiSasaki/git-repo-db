"""Fixed F1-A witnesses, not a general catalog loader or SQL proof."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from unittest.mock import patch

PROFILE = "filesystem-outcomes-v1"
EXPECTED_FS_COUNTS = {
    "catalog_metadata": 5,
    "scans": 6,
    "entries": 8,
    "scan_outcomes": 4,
}
EXPECTED_STATUSES = {
    "complete": "complete",
    "partial": "partial",
    "interrupted": "interrupted",
    "empty_partial": "partial",
    "incomplete": None,
}


def populate(catalog, root, api, unfinished_scan):
    """Use real scan(), with a bounded interruption and explicit SQL witnesses."""
    from repo_catalog.filesystem import FilesystemCatalog, FilesystemError, store
    from repo_catalog.filesystem.models import occurrence_uuid

    complete_root = root / "complete-root"
    complete_root.mkdir()
    (complete_root / "empty").write_bytes(b"")
    complete = catalog.scan(complete_root)
    partial = catalog.scan(root / "missing-root")
    interrupted_root = root / "interrupted-root"
    interrupted_root.mkdir()
    (interrupted_root / "file").write_bytes(b"bounded witness")
    original = store.walk

    def interrupted_walk(*args):
        with closing(original(*args)) as iterator:
            yield next(iterator)
            raise KeyboardInterrupt("controlled F1-A interruption")

    old_scans = {s.scan_uuid for s in catalog.list_scans()}
    with patch.object(store, "walk", interrupted_walk):
        try:
            catalog.scan(interrupted_root)
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("scan swallowed the controlled interruption")
    new_scans = [s for s in catalog.list_scans() if s.scan_uuid not in old_scans]
    if len(new_scans) != 1:
        raise AssertionError("interruption did not preserve exactly one scan")
    interrupted = new_scans[0]
    assert complete.status == "complete" and complete.entries == 2
    assert partial.status == "partial" and partial.errors == 1
    assert interrupted.status == "interrupted" and interrupted.entries == 1
    assert complete.enumeration_complete and complete.hashing_complete
    assert not partial.enumeration_complete and not partial.hashing_complete
    assert not interrupted.enumeration_complete and not interrupted.hashing_complete

    # SQL/API permits an empty partial observation. This is NOT a scanner trace.
    empty_scan = occurrence_uuid()
    with catalog._db:
        catalog._db.execute(
            "INSERT INTO scans VALUES (?,?,?,?,?)",
            (catalog.namespace_uuid, empty_scan, os.fsencode(root), 1, "[]"),
        )
        catalog._db.execute(
            "INSERT INTO scan_outcomes VALUES (?,?,?,?,?,?)",
            (catalog.namespace_uuid, empty_scan, 1, "partial", 0, 0),
        )
    catalog.verify()
    cases = {
        "complete": complete.scan_uuid,
        "partial": partial.scan_uuid,
        "interrupted": interrupted.scan_uuid,
        "empty_partial": empty_scan,
        "incomplete": unfinished_scan,
    }
    api["outcome_statuses"] = {
        name: catalog.get_scan(scan).status for name, scan in cases.items()
    }
    api["outcome_completeness"] = {
        name: [
            catalog.get_scan(scan).enumeration_complete,
            catalog.get_scan(scan).hashing_complete,
        ]
        for name, scan in cases.items()
    }
    api["outcome_verify"] = catalog.verify()["integrity"]

    # Guards remain enabled. DDL rejects status; API adds cross-row checks.
    controls = {}
    for label, status, count, errors, rejected_by in (
        ("invalid_status", "incomplete", 1, 1, "sqlite"),
        ("entry_count", "partial", 2, 1, "api"),
        ("error_count", "partial", 1, 0, "api"),
        ("complete_with_error", "complete", 1, 1, "api"),
        ("empty_error_is_present", "partial", 1, 1, None),
    ):
        with FilesystemCatalog.initialize(root / (label + ".db")) as bad:
            scan = occurrence_uuid()
            with bad._db:
                bad._db.execute(
                    "INSERT INTO scans VALUES (?,?,?,?,?)",
                    (bad.namespace_uuid, scan, os.fsencode(root), 1, "[]"),
                )
                bad._db.execute(
                    "INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        bad.namespace_uuid,
                        scan,
                        b"",
                        "directory",
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        "not-applicable",
                        "",
                        None,
                        None,
                    ),
                )
            try:
                with bad._db:
                    bad._db.execute(
                        "INSERT INTO scan_outcomes VALUES (?,?,?,?,?,?)",
                        (bad.namespace_uuid, scan, 1, status, count, errors),
                    )
            except sqlite3.IntegrityError as exc:
                if rejected_by != "sqlite":
                    raise
                controls[label] = {"stage": "sqlite", "reason": str(exc)}
                continue
            if rejected_by == "sqlite":
                raise AssertionError("DDL accepted an invalid terminal status")
            try:
                bad.verify()
            except FilesystemError as exc:
                if rejected_by != "api":
                    raise
                controls[label] = {"stage": "api", "reason": str(exc)}
            else:
                if rejected_by is not None:
                    raise AssertionError("API accepted inconsistent outcome: " + label)
                controls[label] = {
                    "stage": "accepted",
                    "reason": "empty text is non-NULL",
                }
    api["outcome_controls"] = controls
    return {name: [catalog.namespace_uuid, scan] for name, scan in cases.items()}


def check_coverage(
    data, decoded, *, profile=PROFILE, expected_counts=EXPECTED_FS_COUNTS
):
    """Admit declared construction coverage independently of generated RDF."""
    supplied_profile = data.get("profile", "values")
    if supplied_profile == "values":
        return
    if supplied_profile != profile:
        raise ValueError("unsupported instance fixture profile")
    if data["expected_counts"]["filesystem"] != expected_counts:
        raise ValueError("F1-A fixed construction counts missing")
    cases = data["outcome_cases"]
    if not isinstance(cases, dict) or set(cases) != set(EXPECTED_STATUSES):
        raise ValueError("F1-A required scenario declarations missing")
    scans = {
        (r["namespace_uuid"], r["scan_uuid"])
        for (store, table, _), r in decoded.items()
        if store == "filesystem" and table == "scans"
    }
    outcomes = [
        r
        for (store, table, _), r in decoded.items()
        if store == "filesystem" and table == "scan_outcomes"
    ]
    seen = set()
    for name, expected in EXPECTED_STATUSES.items():
        key = cases[name]
        if (
            not isinstance(key, list)
            or len(key) != 2
            or any(type(v) is not str for v in key)
        ):
            raise ValueError("malformed F1-A qualified scenario key")
        key = tuple(key)
        if key in seen or key not in scans:
            raise ValueError("F1-A scenario scan missing or repeated")
        seen.add(key)
        rows = [r for r in outcomes if (r["namespace_uuid"], r["scan_uuid"]) == key]
        if len(rows) != (0 if expected is None else 1):
            raise ValueError("F1-A required outcome occurrence missing or repeated")
        # A valid but different state no longer covers this positive scenario.
        # An invalid enum remains admitted to the SHACL negative control.
        if rows and rows[0]["status"] in ("complete", "partial", "interrupted"):
            if rows[0]["status"] != expected:
                raise ValueError("F1-A declared terminal scenario not covered")
