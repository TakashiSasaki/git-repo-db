"""Disposable public-API/SQLite pilot producer; never accepts a retained DB path."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import hash_profile
import outcome_profile

from repo_catalog.filesystem import FilesystemCatalog, FilesystemError
from repo_catalog.filesystem.models import occurrence_uuid
from repo_catalog.worktrees import WorktreeCatalog


def encode(value):
    if isinstance(value, bytes):
        return {
            "type": "blob",
            "base64": base64.b64encode(value).decode(),
            "length": len(value),
        }
    return {
        "type": "null"
        if value is None
        else "integer"
        if isinstance(value, int)
        else "text",
        "value": value,
    }


def extract(path, tables):
    """Read one closed, quiescent disposable database in one read transaction."""
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        result = {}
        for table in tables:  # fixed caller-owned names, not SQL supplied by a user
            rows = [
                {k: encode(v) for k, v in dict(r).items()}
                for r in db.execute(f'SELECT * FROM "{table}"')
            ]
            result[table] = sorted(rows, key=lambda r: json.dumps(r, sort_keys=True))
        return result


def produce(profile="values"):
    if profile not in ("values", outcome_profile.PROFILE, hash_profile.PROFILE):
        raise ValueError("unsupported fixture profile")
    outcome_cases = None
    hash_cases = None
    with tempfile.TemporaryDirectory(prefix="schema-instance-pilot-") as temp:
        root = Path(temp)
        fs_path, wt_path = root / "fs.db", root / "wt.db"
        scans = [occurrence_uuid(), occurrence_uuid()]
        huge = "9223372036854775808"
        with FilesystemCatalog.initialize(fs_path) as fs:
            namespace = fs.namespace_uuid
            with fs._db:
                for scan in scans:
                    fs._db.execute(
                        "INSERT INTO scans VALUES(?,?,?,?,?)",
                        (namespace, scan, os.fsencode(root), 1, "[]"),
                    )
                    for path in (b"", b"bad-\xff"):
                        fs._db.execute(
                            "INSERT INTO entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                namespace,
                                scan,
                                path,
                                "directory",
                                None,
                                huge,
                                None,
                                "-1",
                                None,
                                None,
                                None,
                                "not-applicable",
                                None,
                                None,
                                None,
                            ),
                        )
            # Direct SQL setup is deliberate: huge native timestamps cannot be
            # reliably materialized by a real filesystem on every platform.
            api = {
                "filesystem_verify": fs.verify()["integrity"],
                "incomplete_scan": all(
                    s.status == "incomplete" for s in fs.list_scans()
                ),
            }
            entries = list(fs.iter_entries(scans[0]))
            api["blob_and_huge_ns_roundtrip"] = {e.relative_path for e in entries} == {
                b"",
                b"bad-\xff",
            } and all(
                e.mtime_ns == int(huge) and e.birthtime_ns is None for e in entries
            )
            try:
                with fs._db:
                    fs._db.execute(
                        "INSERT INTO entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            namespace,
                            occurrence_uuid(),
                            b"orphan",
                            "directory",
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            "not-applicable",
                            None,
                            None,
                            None,
                        ),
                    )
            except sqlite3.IntegrityError as exc:
                api["sqlite_orphan_rejection"] = str(exc)
            else:
                raise AssertionError("SQLite accepted an orphan entry")
            if profile in (outcome_profile.PROFILE, hash_profile.PROFILE):
                outcome_cases = outcome_profile.populate(fs, root, api, scans[0])
            if profile == hash_profile.PROFILE:
                hash_cases = hash_profile.populate(fs, root, api, outcome_cases)
        with FilesystemCatalog.initialize(root / "invalid-ns.db") as bad:
            scan = occurrence_uuid()
            with bad._db:
                bad._db.execute(
                    "INSERT INTO scans VALUES(?,?,?,?,?)",
                    (bad.namespace_uuid, scan, os.fsencode(root), 1, "[]"),
                )
                bad._db.execute(
                    "INSERT INTO entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        bad.namespace_uuid,
                        scan,
                        b"",
                        "directory",
                        None,
                        "+01",
                        None,
                        None,
                        None,
                        None,
                        None,
                        "not-applicable",
                        None,
                        None,
                        None,
                    ),
                )
            api["sqlite_noncanonical_ns"] = "accepted"
            try:
                bad.verify()
            except FilesystemError as exc:
                api["api_noncanonical_ns"] = str(exc)
            else:
                raise AssertionError("API accepted a noncanonical native timestamp")
        git_root = root / "repo"
        git_root.mkdir()
        subprocess.run(
            ["git", "init", "-q", str(git_root)], check=True, capture_output=True
        )
        with WorktreeCatalog.initialize(wt_path) as wt:
            discovery = wt.discover(git_root, expand=False)
            assert discovery.entries, discovery
            wt.record_scan_reference(
                discovery.observation_uuid,
                discovery.entries[0].root_path,
                str(uuid4()),
                occurrence_uuid(),
            )
            api["worktrees_verify_without_filesystem"] = wt.verify()
        tables = {
            "filesystem": extract(
                fs_path, ("catalog_metadata", "scans", "entries", "scan_outcomes")
            ),
            "worktrees": extract(
                wt_path,
                (
                    "catalog_identity",
                    "observations",
                    "worktrees",
                    "scan_references",
                    "repository_links",
                ),
            ),
        }
        repo = Path(__file__).resolve().parents[2]

        def git(*args):
            return subprocess.check_output(
                ["git", "-C", str(repo), *args], text=True
            ).strip()

        module_sources = {}
        for name, module in sorted(sys.modules.items()):
            if name.startswith(
                ("repo_catalog.filesystem", "repo_catalog.worktrees")
            ) and getattr(module, "__file__", None):
                path = Path(module.__file__).resolve()
                relative = path.relative_to(repo).as_posix()
                actual = path.read_bytes()
                committed = subprocess.check_output(
                    ["git", "-C", str(repo), "show", "HEAD:" + relative]
                )
                if actual != committed:
                    raise ValueError(
                        "imported product source differs from HEAD: " + relative
                    )
                module_sources[name] = {
                    "path": relative,
                    "sha256": hashlib.sha256(actual).hexdigest(),
                }
        producer_inputs = {}
        for module in (outcome_profile, hash_profile):
            helper = Path(module.__file__).resolve()
            helper_relative = helper.relative_to(repo).as_posix()
            if helper.read_bytes() != subprocess.check_output(
                ["git", "-C", str(repo), "show", "HEAD:" + helper_relative]
            ):
                raise ValueError("producer helper differs from HEAD")
            producer_inputs[helper_relative] = hashlib.sha256(
                helper.read_bytes()
            ).hexdigest()
        expected = {
            "filesystem": {
                "catalog_metadata": 5,
                "scans": 2,
                "entries": 4,
                "scan_outcomes": 0,
            },
            "worktrees": {
                "catalog_identity": 1,
                "observations": 1,
                "worktrees": 1,
                "scan_references": 1,
                "repository_links": 0,
            },
        }
        if profile == outcome_profile.PROFILE:
            expected["filesystem"] = dict(outcome_profile.EXPECTED_FS_COUNTS)
        elif profile == hash_profile.PROFILE:
            expected["filesystem"] = dict(hash_profile.EXPECTED_FS_COUNTS)
        if {
            s: {t: len(r) for t, r in ts.items()} for s, ts in tables.items()
        } != expected:
            raise ValueError(
                "extracted counts differ from fixed fixture construction contract"
            )
        return {
            "version": 1,
            "profile": profile,
            "outcome_cases": outcome_cases,
            "hash_cases": hash_cases,
            "producer_inputs": producer_inputs,
            "imported_product_sources": module_sources,
            "scope": (
                "real terminal and changed/read-error scanner witnesses plus explicitly SQL-only value, empty-partial and hash-boundary rows"
                if profile == hash_profile.PROFILE
                else "disposable real complete/partial/interrupted scanner witnesses plus explicit SQL-only value and empty-partial witnesses"
                if profile == outcome_profile.PROFILE
                else "disposable synthetic fixture, not scanner execution or retained data"
            ),
            "source_commit": git("rev-parse", "HEAD"),
            "source_tree": git("rev-parse", "HEAD^{tree}"),
            "producer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "runtime": {"python": sys.version, "sqlite": sqlite3.sqlite_version},
            "api": api,
            "expected_counts": expected,
            "tables": tables,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("values", outcome_profile.PROFILE, hash_profile.PROFILE),
        default="values",
    )
    print(json.dumps(produce(parser.parse_args().profile), sort_keys=True, indent=2))
