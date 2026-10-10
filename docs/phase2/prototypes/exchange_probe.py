"""Disposable Schema 18 Exchange/CAS characterization and operation counts.

Run from the checkout with an explicit synthetic --state-dir. This script
executes the current production Graph, complete packaged DDL and CAS adapter;
it does not define a replacement Exchange wire format or acceptance policy.
Wall times are deliberately omitted because other workstreams may run together.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from repo_catalog.adapters.sqlite.cas_integrity import (  # noqa: E402
    register_git_object_sql_function,
    repair_payload,
    verify_all,
)
from repo_catalog.adapters.sqlite.exchange import Graph  # noqa: E402
from repo_catalog.adapters.sqlite.payloads import intern_payload  # noqa: E402
from repo_catalog.adapters.sqlite.schema import schema_sql  # noqa: E402


def catalog():
    db = sqlite3.connect(":memory:", isolation_level=None)
    register_git_object_sql_function(db)
    db.executescript(schema_sql())
    return db


def uid():
    return str(uuid.uuid4())


def repository(db):
    identity = uid()
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,?,'{}')",
        (identity, "synthetic"),
    )
    return identity


def acquisition(db, owner, object_format):
    identity = uid()
    db.execute(
        "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,object_format,kind,request) "
        "VALUES(?,?,?,'git','{}')",
        (identity, owner, object_format),
    )
    return identity


def blob(db, owner, acquired, object_format, body):
    oid = hashlib.new(object_format, f"blob {len(body)}\0".encode() + body).digest()
    reference = intern_payload(db, body, representation="git-object-raw-v1")
    object_id = db.execute(
        "INSERT INTO git_objects(object_format,oid,type,size,verified) "
        "VALUES(?,?,'blob',?,1) RETURNING git_object_id",
        (object_format, oid, len(body)),
    ).fetchone()[0]
    db.execute(
        "INSERT INTO git_object_payloads VALUES(?,'git-object-raw-v1',?)",
        (object_id, reference.sha256),
    )
    db.execute(
        "INSERT INTO repository_object_sources VALUES(?,?,?)",
        (owner, object_id, acquired),
    )
    return reference.sha256


def receive(db, unit):
    db.execute("BEGIN")
    try:
        result = Graph(db).receive(unit)
        db.execute("COMMIT")
        return result
    except BaseException:
        db.execute("ROLLBACK")
        raise


def measure(db, operation):
    progress_calls = 0
    statements = []

    def progress():
        nonlocal progress_calls
        progress_calls += 1
        return 0

    db.set_progress_handler(progress, 100)
    db.set_trace_callback(statements.append)
    try:
        value = operation()
    finally:
        db.set_progress_handler(None, 0)
        db.set_trace_callback(None)
    scans = [
        statement
        for statement in statements
        if statement.upper().startswith("SELECT ")
        and " WHERE " not in statement.upper()
        and " FROM " in statement.upper()
    ]
    return {
        "sqlite_vm_steps_estimate": progress_calls * 100,
        "statements": len(statements),
        "unfiltered_select_statements": len(scans),
    }, value


def characterize_git():
    source, target = catalog(), catalog()
    try:
        owner = repository(source)
        digests = []
        for object_format in ("sha1", "sha256"):
            acquired = acquisition(source, owner, object_format)
            digests.append(
                blob(
                    source, owner, acquired, object_format, b"synthetic-domain-content"
                )
            )
        assert digests[0] == digests[1]
        unit = Graph(source).export(owner)
        reversed_unit = copy.deepcopy(unit)
        reversed_unit["records"].reverse()
        first = receive(target, reversed_unit)
        repeated = receive(target, unit)
        assert first["staged_records"] == 0
        assert repeated["received_records"] == 0
        assert target.execute("SELECT count(*) FROM stored_bytes").fetchone() == (1,)
        assert target.execute("SELECT count(*) FROM git_objects").fetchone() == (2,)

        late = catalog()
        try:
            prefix = copy.deepcopy(unit)
            prefix["records"] = [
                row for row in unit["records"] if row["table"] != "stored_bytes"
            ]
            before_body = receive(late, prefix)
            assert before_body["staged_records"] > 0
            body_unit = copy.deepcopy(unit)
            body_unit["records"] = [
                row for row in unit["records"] if row["table"] == "stored_bytes"
            ]
            after_body = receive(late, body_unit)
            assert after_body["staged_records"] == 0
            assert late.execute("SELECT count(*) FROM git_objects").fetchone() == (2,)
        finally:
            late.close()

        corruption = b"!" * len(b"synthetic-domain-content")
        target.execute("DROP TRIGGER stored_bytes_immutable")
        target.execute("UPDATE stored_bytes SET body=?", (corruption,))
        target.execute(
            "CREATE TRIGGER stored_bytes_immutable BEFORE UPDATE ON stored_bytes "
            "BEGIN SELECT RAISE(ABORT,'Immutable stored bytes'); END"
        )
        corrupt = verify_all(target)
        assert len(corrupt["corrupt"]) == 1
        assert target.execute("SELECT count(*) FROM payload_quarantine").fetchone() == (
            1,
        )
        repaired = repair_payload(target, digests[0], b"synthetic-domain-content")
        assert repaired["repaired"]
        assert verify_all(target)["corrupt"] == []
        assert target.execute("SELECT count(*) FROM payload_quarantine").fetchone() == (
            0,
        )
        assert target.execute(
            "SELECT count(*) FROM unresolved_payloads"
        ).fetchone() == (1,)
        for db in (source, target):
            assert db.execute("PRAGMA foreign_key_check").fetchall() == []
            assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        return {
            "verified_object_formats": ["sha1", "sha256"],
            "exported_records": len(unit["records"]),
            "physical_bodies_after_receive": 1,
            "reversed_receive": first,
            "repeated_receive": repeated,
            "missing_body_receive": before_body,
            "late_body_receive": after_body,
            "corrupt_physical_bodies": len(corrupt["corrupt"]),
            "active_quarantine_after_repair": 0,
            "historical_diagnostics_after_repair": 1,
        }
    finally:
        source.close()
        target.close()


def operation_counts(sizes):
    db = catalog()
    try:
        selected = repository(db)
        unrelated = repository(db)
        acquired = acquisition(db, unrelated, "sha1")
        inserted = 0
        results = []
        for size in sizes:
            for index in range(inserted, size):
                blob(db, unrelated, acquired, "sha1", f"unrelated-{index:08d}".encode())
            inserted = size
            graph = Graph(db, persist_identities=False)
            export_counts, unit = measure(db, lambda: graph.export(selected))
            block_counts, _ = measure(db, graph.refresh_resolution_blocks)
            assert len(unit["records"]) == 1
            assert db.execute("SELECT count(*) FROM exchange_staging").fetchone() == (
                0,
            )
            results.append(
                {
                    "unrelated_git_objects": size,
                    "selected_export": export_counts,
                    "conflict_free_refresh": block_counts,
                }
            )
        return results
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("--sizes", nargs="+", type=int, default=[0, 256, 1024, 4096])
    args = parser.parse_args()
    if args.sizes != sorted(set(args.sizes)) or any(size < 0 for size in args.sizes):
        parser.error("sizes must be unique increasing nonnegative counts")
    args.state_dir.mkdir(parents=True, exist_ok=False)
    source_path = ROOT / "src/repo_catalog/adapters/sqlite/exchange.py"
    result = {
        "kind": "production-characterization; no replacement-policy acceptance",
        "head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "head_tree": subprocess.check_output(
            ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
        ).strip(),
        "exchange_source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "schema_sha256": hashlib.sha256(schema_sql().encode()).hexdigest(),
        "python": sys.version.split()[0],
        "sqlite": sqlite3.sqlite_version,
        "git_and_cas": characterize_git(),
        "operation_counts": operation_counts(args.sizes),
        "measurement": "VM callbacks every 100 opcodes; no wall-time comparison",
    }
    report = args.state_dir / "exchange-operation-counts.json"
    report.write_text(json.dumps(result, indent=2) + "\n")
    print(report)


if __name__ == "__main__":
    main()
