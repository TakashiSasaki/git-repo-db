"""Reproducible disposable acceptance checks for the packaged Catalog3 model.

Run with the installed project, without the test-only parser bootstrap::

    uv run --no-sync python scripts/validate_remaining_contracts.py --output REPORT

The report describes executed checks. Trigger installation and DML compilation
are reported separately from behavioral constraint probes; this is not a claim
that every trigger branch has been exercised.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from collections import Counter
from importlib.resources import files
from pathlib import Path

from repo_catalog.adapters.sqlite.json_contracts import guard_sql, validate_catalog
from repo_catalog.adapters.sqlite.json_contracts import inventory as json_inventory
from repo_catalog.adapters.sqlite.schema import DDL_SHA256, SCHEMA_VERSION, schema_sql
from repo_catalog.adapters.sqlite.text_bodies import intern_text_body
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.domain.document import text_body_sha256
from repo_catalog.domain.time import validate_epoch_us


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def quoted(name):
    return '"' + name.replace('"', '""') + '"'


def rejected(db, sql, parameters):
    db.execute("SAVEPOINT rejected_probe")
    try:
        db.execute(sql, parameters)
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError(f"Invalid values were admitted: {sql}")
    finally:
        db.execute("ROLLBACK TO rejected_probe")
        db.execute("RELEASE rejected_probe")


def baseline_contracts(db):
    """Small direct-SQL probes complement the ordinary behavioral suites."""
    coverage_columns = [r[1] for r in db.execute("PRAGMA table_info(coverage_claims)")]
    require(
        coverage_columns
        == [
            "coverage_claim_id",
            "coverage_scope_id",
            "coverage_state",
            "observed_at_us",
            "details_json",
        ],
        "Coverage v2 must retain exactly its five claim columns",
    )
    repository = str(uuid.uuid4())
    service = str(uuid.uuid4())
    registration = str(uuid.uuid4())
    db.execute(
        "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata) "
        "VALUES(?,'github','synthetic','{}')",
        (service,),
    )
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'synthetic','{}')",
        (repository,),
    )
    db.execute(
        "INSERT INTO sources(source_id,source_registration_uuidv4,discovery_kind,name,settings) "
        "VALUES('synthetic-source',?,'manual_git','synthetic',NULL)",
        (registration,),
    )
    bad_uuid_values = [
        "not-a-uuid",
        str(uuid.uuid5(uuid.NAMESPACE_DNS, "synthetic.invalid")),
        "550E8400-E29B-41D4-A716-446655440000",
        repository + "\x00",
        None,
    ]
    for invalid in bad_uuid_values:
        rejected(
            db,
            "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'bad','{}')",
            (invalid,),
        )
        rejected(
            db,
            "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata) "
            "VALUES(?,'git','bad','{}')",
            (invalid,),
        )
        rejected(
            db,
            "INSERT INTO sources(source_id,source_registration_uuidv4,discovery_kind,name,settings) "
            "VALUES('bad-source',?,'manual_git','bad',NULL)",
            (invalid,),
        )

    db.execute(
        "INSERT INTO repository_bindings(repository_binding_id,repository_uuidv4,"
        "service_instance_uuidv4,provider_repository_id,metadata) VALUES('binding',?,?,'001','{}')",
        (repository, service),
    )
    for change_request in ("pr-a", "pr-b"):
        db.execute(
            "INSERT INTO change_requests(change_request_id,repository_uuidv4,repository_binding_id,"
            "change_request_kind,provider_change_request_number) VALUES(?,?,'binding','pull_request',?)",
            (change_request, repository, 1 if change_request == "pr-a" else 2),
        )
    natural_key = [
        r[1]
        for r in sorted(db.execute("PRAGMA table_info(documents)"), key=lambda r: r[5])
        if r[5]
    ]
    require(
        natural_key
        == ["change_request_id", "kind", "provider_change_request_document_id"],
        "Document natural identity changed",
    )
    table_names = {
        r[0] for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")
    }
    require(
        "document_versions" not in table_names, "Document version table was introduced"
    )
    require(
        not table_names.intersection({"reviews", "review_comments"}),
        "Retired review marker tables remain",
    )
    current_keys = {}
    for table, expected in (
        (
            "issue_resources",
            ["service_instance_uuidv4", "kind", "provider_resource_id"],
        ),
        (
            "review_resources",
            ["change_request_id", "kind", "provider_change_request_document_id"],
        ),
    ):
        info = db.execute(f"PRAGMA table_info({quoted(table)})").fetchall()
        key = [r[1] for r in sorted(info, key=lambda r: r[5]) if r[5]]
        require(key == expected, f"Current resource identity changed: {table}")
        require(
            "parsed_result_uuidv4" not in {r[1] for r in info},
            "Mutable resource became an immutable result member",
        )
        current_keys[table] = key
    page_parents = {
        r[2] for r in db.execute("PRAGMA foreign_key_list(current_collection_pages)")
    }
    require(
        page_parents == {"fetch_collections", "parser_profiles"},
        "Current collection proof must retain exact context/profile without mutable body dependencies",
    )
    for kind in ("review", "review-comment"):
        rejected(
            db,
            "INSERT INTO documents(change_request_id,kind,provider_change_request_document_id) VALUES('pr-a',?,'1')",
            (kind,),
        )
    for table in table_names:
        columns = {r[1] for r in db.execute(f"PRAGMA table_info({quoted(table)})")}
        require(
            not columns.intersection(
                {"document_id", "document_version_id", "change_request_document_id"}
            ),
            f"Document surrogate column in {table}",
        )
    document_keys = [
        ("pr-a", "pr-title", "00123"),
        ("pr-a", "pr-body", "00123"),
        ("pr-a", "pr-body", "123"),
        ("pr-b", "pr-body", "00123"),
    ]
    db.executemany("INSERT INTO documents VALUES(?,?,?)", document_keys)
    require(
        db.execute("SELECT count(*) FROM documents").fetchone()[0] == 4,
        "Distinct document tuples were merged",
    )
    bodies = ["認証\n", "認証\r\n", "e\u0301", "é", ""]
    body_hashes = []
    for body in bodies:
        digest = intern_text_body(db, body)
        require(
            digest == hashlib.sha256(body.encode("utf-8")).digest(),
            "Text hash mismatch",
        )
        require(digest == text_body_sha256(body), "Text domain identity mismatch")
        require(
            intern_text_body(db, body) == digest,
            "Repeated text admission changed identity",
        )
        body_hashes.append(digest.hex())
    require(len(set(body_hashes)) == len(bodies), "Exact UTF-8 bodies were normalized")

    storage_times = [-(1 << 63), -1, 0, 1, (1 << 63) - 1]
    for value in [None, *storage_times]:
        db.execute(
            "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata,created_at_us) "
            "VALUES(?,'git','timestamp','{}',?)",
            (str(uuid.uuid4()), value),
        )
        if value is not None:
            require(validate_epoch_us(value) == value, "Signed timestamp rejected")
    require(
        db.execute(
            "SELECT created_at_us,typeof(created_at_us) FROM service_instances "
            "WHERE name='timestamp' AND created_at_us IS NOT NULL ORDER BY created_at_us"
        ).fetchall()
        == [(value, "integer") for value in storage_times],
        "Signed int64 timestamp values changed",
    )
    for value in (1.5, "2026-10-09T00:00:00Z", b"0"):
        rejected(
            db,
            "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata,created_at_us) "
            "VALUES(?,'git','invalid-time','{}',?)",
            (str(uuid.uuid4()), value),
        )
    invalid_domain_times = [-(1 << 63) - 1, 1 << 63, True, False, None, 0.0, "0"]
    for value in invalid_domain_times:
        try:
            validate_epoch_us(value)
        except (TypeError, ValueError):
            pass
        else:
            raise AssertionError(
                f"Invalid timestamp admitted by domain boundary: {value!r}"
            )
    temporal_columns = []
    irregular = {"safe_watermark", "last_used", "not_before", "first_seen", "last_seen"}
    for (table,) in db.execute("SELECT name FROM sqlite_schema WHERE type='table'"):
        for _, name, kind, *_ in db.execute(f"PRAGMA table_info({quoted(table)})"):
            if (
                name.removesuffix("_us").endswith("_at")
                or name.removesuffix("_us") in irregular
            ):
                require(
                    name.endswith("_us") and kind == "INTEGER",
                    f"Invalid time column: {table}.{name}",
                )
                temporal_columns.append(f"{table}.{name}")

    db.execute(
        "INSERT INTO coverage_scopes(coverage_scope_id,repository_uuidv4,kind) VALUES('coverage',?,'git')",
        (repository,),
    )

    def claim(value, state):
        db.execute(
            "INSERT INTO coverage_claims(coverage_scope_id,coverage_state,observed_at_us,details_json) "
            "VALUES('coverage',?,?,NULL)",
            (state, value),
        )

    def current():
        return db.execute(
            "SELECT observed_at_us,coverage_state,claim_count FROM current_coverage "
            "WHERE coverage_scope_id='coverage'"
        ).fetchone()

    claim(-1, "complete")
    require(current() == (-1, "complete", 1), "Negative coverage observation was lost")
    claim(0, "unknown")
    require(current() == (0, "unknown", 1), "Latest unknown coverage fell back")
    claim(1, "partial")
    claim(1, "complete")
    claim(1, "unknown")
    require(
        current() == (1, "conflict", 3), "Latest coverage candidate set was truncated"
    )
    return {
        "status": "passed",
        "coverage_claim_columns": coverage_columns,
        "coverage_latest_unknown_and_conflict": "passed",
        "portable_uuid_owners_checked": [
            "repositories",
            "service_instances",
            "sources",
        ],
        "invalid_uuid_probes": len(bad_uuid_values) * 3,
        "document_primary_key": natural_key,
        "document_surrogates_absent": True,
        "current_resource_primary_keys": current_keys,
        "review_markers_and_immutable_review_documents_absent": True,
        "current_page_required_parent_tables": sorted(page_parents),
        "distinct_document_tuples": len(document_keys),
        "exact_utf8_text_sha256": body_hashes,
        "timestamp_storage_values": storage_times,
        "invalid_domain_timestamp_probes": len(invalid_domain_times),
        "nullable_timestamp": "passed",
        "timestamp_columns": sorted(temporal_columns),
    }


def validate_schema():
    with sqlite3.connect(":memory:", autocommit=True) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA recursive_triggers=ON")
        ddl = schema_sql()
        require(
            hashlib.sha256(ddl.encode()).digest() == DDL_SHA256,
            "DDL fingerprint mismatch",
        )
        db.executescript(ddl)
        require(
            db.execute("PRAGMA foreign_keys").fetchone() == (1,),
            "Foreign keys disabled",
        )
        require(
            db.execute("PRAGMA recursive_triggers").fetchone() == (1,),
            "Recursive triggers disabled",
        )
        inventory = {kind: [] for kind in ("table", "view", "trigger", "index")}
        rows = db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema "
            "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type,name"
        ).fetchall()
        for kind, name, _, _ in rows:
            inventory[kind].append(name)
        for name in inventory["view"]:
            db.execute(f"SELECT * FROM {quoted(name)}").fetchall()
        for kind, name, table, sql in rows:
            if kind == "index":
                db.execute(f"PRAGMA index_xinfo({quoted(name)})").fetchall()
                predicate = re.search(
                    r"\bWHERE\b(.*)\Z", sql, re.IGNORECASE | re.DOTALL
                )
                where = " WHERE " + predicate[1] if predicate else ""
                db.execute(
                    f"SELECT * FROM {quoted(table)} INDEXED BY {quoted(name)}{where} LIMIT 0"
                ).fetchall()
        trigger_tables = sorted(
            {table for kind, _, table, _ in rows if kind == "trigger"}
        )
        for table in trigger_tables:
            columns = [r[1] for r in db.execute(f"PRAGMA table_info({quoted(table)})")]
            assignments = ",".join(f"{quoted(name)}={quoted(name)}" for name in columns)
            for statement in (
                f"INSERT INTO {quoted(table)} DEFAULT VALUES",
                f"UPDATE {quoted(table)} SET {assignments}",
                f"DELETE FROM {quoted(table)}",
            ):
                db.execute("EXPLAIN " + statement).fetchall()
        contracts = baseline_contracts(db)
        json_fields = json_inventory(db)
        json_audit = validate_catalog(db)
        require(
            files("repo_catalog").joinpath("resources/json_contracts.sql").read_text()
            == guard_sql(),
            "Packaged JSON guards differ from their schema registry",
        )
        foreign_keys = db.execute("PRAGMA foreign_key_check").fetchall()
        integrity = [r[0] for r in db.execute("PRAGMA integrity_check")]
        require(not foreign_keys, "Fresh model foreign-key violations")
        require(integrity == ["ok"], "Fresh model integrity check failed")
        return {
            "status": "passed",
            "schema_version": SCHEMA_VERSION,
            "ddl_sha256": DDL_SHA256.hex(),
            "foreign_keys": True,
            "recursive_triggers": True,
            "schema_object_counts": {
                kind: len(names) for kind, names in inventory.items()
            },
            "schema_objects": inventory,
            "queried_views": inventory["view"],
            "accessed_named_indexes": inventory["index"],
            "compiled_trigger_dml_tables": trigger_tables,
            "trigger_check_scope": "All trigger DDL installed; INSERT/UPDATE/DELETE compiled for every trigger table. Behavioral branches are covered by the ordinary tests and baseline probes.",
            "foreign_key_check": foreign_keys,
            "integrity_check": integrity,
            "baseline_contracts": contracts,
            "json_inventory": {
                "status": "passed",
                "field_count": len(json_fields),
                "categories": dict(Counter(field["category"] for field in json_fields)),
                "fields": json_fields,
                "authored_record_audit": json_audit,
                "packaged_guards_match_registry": True,
            },
        }


def validate_initialization():
    with tempfile.TemporaryDirectory(prefix="catalog3-remaining-acceptance-") as stage:
        state = Path(stage) / "state"
        MaintenanceService(state).init("catalog-text-v1", 33554432, 0)
        with sqlite3.connect(state / "catalog.sqlite3") as db:
            identity = db.execute(
                "SELECT format_id,schema_version,lifecycle,hex(ddl_sha256) FROM database_identity"
            ).fetchone()
            require(
                identity
                == (
                    "repo-catalog/catalog3",
                    SCHEMA_VERSION,
                    "validated",
                    DDL_SHA256.hex().upper(),
                ),
                "Fresh initialization identity mismatch",
            )
            foreign_keys = db.execute("PRAGMA foreign_key_check").fetchall()
            integrity = [r[0] for r in db.execute("PRAGMA integrity_check")]
            require(
                not foreign_keys and integrity == ["ok"],
                "Initialized model integrity failure",
            )
        return {
            "status": "passed",
            "identity": list(identity),
            "foreign_key_check": foreign_keys,
            "integrity_check": integrity,
            "test_only_bootstrap": False,
        }


def version(command):
    result = subprocess.run(
        command, capture_output=True, text=True, check=True, timeout=10
    )
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = {
        "environment": {
            "python": sys.version.split()[0],
            "sqlite": sqlite3.sqlite_version,
            "git": version(["git", "--version"]),
            "uv": version(["uv", "--version"]),
            "platform": platform.platform(),
        },
        "not_executed": [
            "Live authenticated source acquisition",
            "Physical hardware power-loss testing",
            "Non-Linux atomic restore publication",
        ],
    }
    require(
        os.environ.get("REPO_CATALOG_TEST_BOOTSTRAP") != "1",
        "Acceptance must not use test bootstrap",
    )
    for name, check in (
        ("complete_packaged_ddl", validate_schema),
        ("fresh_initialization", validate_initialization),
    ):
        try:
            report[name] = check()
        except Exception as error:
            report[name] = {
                "status": "failed",
                "error": f"{type(error).__name__}: {error}",
            }
    report["status"] = (
        "passed"
        if all(
            report[name]["status"] == "passed"
            for name in ("complete_packaged_ddl", "fresh_initialization")
        )
        else "failed"
    )
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
