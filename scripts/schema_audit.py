"""Read-only v2 structural diagnostics. Never migrate, fetch, repair or run GC.

Reports counts and schema, never row values, URLs, credentials or payloads.
Use --fixture-schema to construct the actual installed schema in a fresh temp DB.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path


def identifier(value):
    return '"' + value.replace('"', '""') + '"'


@contextmanager
def readonly(path):
    path = Path(path).resolve(strict=True)
    # Read-only WAL access may create/update shm. Require a sealed offline DB.
    if any(
        Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")
    ):
        raise ValueError(
            "Unsealed SQLite sidecars present; obtain a sealed offline copy first"
        )
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("BEGIN")
    try:
        yield db
    finally:
        db.rollback()
        db.close()


def schema_inventory(db):
    tables = []
    for row in db.execute(
        "SELECT name,sql FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ):
        name = row["name"]
        indexes = []
        for index in db.execute(f"PRAGMA index_list({identifier(name)})"):
            index_sql = db.execute(
                "SELECT sql FROM sqlite_schema WHERE type='index' AND name=?",
                (index["name"],),
            ).fetchone()
            indexes.append(
                {
                    **dict(index),
                    "columns": [
                        dict(c)
                        for c in db.execute(
                            f"PRAGMA index_xinfo({identifier(index['name'])})"
                        )
                    ],
                    "sql": index_sql[0] if index_sql else None,
                }
            )
        tables.append(
            {
                "name": name,
                "sql": row["sql"],
                "columns": [
                    dict(c)
                    for c in db.execute(f"PRAGMA table_xinfo({identifier(name)})")
                ],
                "foreign_keys": [
                    dict(f)
                    for f in db.execute(f"PRAGMA foreign_key_list({identifier(name)})")
                ],
                "indexes": indexes,
            }
        )
    triggers = [
        dict(row)
        for row in db.execute(
            "SELECT name,tbl_name,sql FROM sqlite_schema WHERE type='trigger' ORDER BY name"
        )
    ]
    material = json.dumps(
        {"tables": tables, "triggers": triggers}, sort_keys=True
    ).encode()
    return {
        "sqlite_version": sqlite3.sqlite_version,
        "schema_version": db.execute(
            "SELECT schema_version FROM catalog_meta"
        ).fetchone()[0],
        "schema_sha256": hashlib.sha256(material).hexdigest(),
        "tables": tables,
        "triggers": triggers,
    }


OWNERSHIP = {
    "current_snapshot": "SELECT count(*) FROM repositories r LEFT JOIN snapshots p ON p.id=r.current_snapshot WHERE r.current_snapshot IS NOT NULL AND (p.id IS NULL OR p.repo_id!=r.id OR p.published!=1)",
    "current_pr_observation": "SELECT count(*) FROM pull_requests r LEFT JOIN pr_observations p ON p.id=r.current_observation WHERE r.current_observation IS NOT NULL AND (p.id IS NULL OR p.pr_id!=r.id OR p.published!=1)",
    "current_document_version": "SELECT count(*) FROM pr_documents d LEFT JOIN document_versions v ON v.id=d.current_version WHERE d.current_version IS NOT NULL AND (v.id IS NULL OR v.document_id!=d.id)",
    "snapshot_run_repo": "SELECT count(*) FROM snapshots s JOIN collection_runs r ON r.id=s.run_id WHERE s.repo_id!=r.repo_id",
    "run_cache_repo": "SELECT count(*) FROM collection_runs r JOIN cache_entries c ON c.id=r.cache_id WHERE r.repo_id!=c.repo_id",
    "root_run_repo": "SELECT count(*) FROM acquisition_roots a JOIN collection_runs r ON r.id=a.run_id WHERE a.repo_id!=r.repo_id",
    "object_source_run_repo": "SELECT count(*) FROM repository_object_sources p JOIN collection_runs r ON r.id=p.run_id WHERE p.repo_id!=r.repo_id",
    "collection_pr_repo": "SELECT count(*) FROM collections c JOIN pull_requests p ON p.id=c.pr_id WHERE c.repo_id!=p.repo_id",
    "resource_version_document": "SELECT count(*) FROM resource_observations o JOIN document_versions v ON v.id=o.version_id WHERE o.document_id!=v.document_id",
    "review_document_pr": "SELECT count(*) FROM pr_reviews r JOIN pr_documents d ON d.id=r.document_id WHERE r.pr_id!=d.pr_id",
    "comment_thread_pr": "SELECT count(*) FROM review_comments c JOIN pr_documents d ON d.id=c.document_id JOIN review_threads t ON t.id=c.thread_id WHERE d.pr_id!=t.pr_id",
    "code_observation_pr": "SELECT count(*) FROM pr_code_observations c JOIN pr_observations o ON o.id=c.observation_id WHERE c.pr_id!=o.pr_id",
    "code_acquisition_pr": "SELECT count(*) FROM pr_git_links l JOIN pr_code_observations c ON c.id=l.code_observation JOIN pull_requests p ON p.id=c.pr_id JOIN acquisition_roots a ON a.id=l.acquisition_id WHERE a.repo_id!=p.repo_id OR a.observation_id IS NOT c.observation_id OR a.pr_number IS NOT p.number",
    "preferred_endpoint": "SELECT count(*) FROM repositories r LEFT JOIN repository_endpoints e ON e.repo_id=r.id AND e.is_preferred=1 WHERE e.id IS NULL OR e.url!=r.url",
    "primary_source_membership": "SELECT count(*) FROM repositories r LEFT JOIN source_repositories m ON m.repo_id=r.id AND m.source_id=r.source_id WHERE m.repo_id IS NULL",
    "git_object_type_commit": "SELECT count(*) FROM commits c JOIN git_objects g ON g.id=c.object_id JOIN git_objects t ON t.id=c.tree_id WHERE g.type!='commit' OR t.type!='tree'",
    "git_object_type_blob": "SELECT count(*) FROM blob_content_map b JOIN git_objects g ON g.id=b.object_id WHERE g.type!='blob'",
    "git_object_type_parent": "SELECT count(*) FROM commit_parents p JOIN git_objects g ON g.id=p.parent_id WHERE g.type!='commit'",
    "git_object_type_tag": "SELECT count(*) FROM tag_objects t JOIN git_objects g ON g.id=t.object_id WHERE g.type!='tag'",
    "page_gaps": "SELECT count(*) FROM (SELECT collection_id FROM collection_pages GROUP BY collection_id HAVING min(ordinal)!=0 OR max(ordinal)+1!=count(*))",
    "complete_commit_listing_fragment": "SELECT count(*) FROM pr_code_observations c JOIN pr_observations o ON o.id=c.observation_id JOIN collections l ON l.pr_id=c.pr_id AND l.job_id=o.job_id AND l.kind='pr-commits' AND l.state='complete' WHERE c.state='complete' AND (SELECT count(*) FROM pr_commits m WHERE m.code_observation=c.id)!=(SELECT count(*) FROM collection_memberships m WHERE m.collection_id=l.id)",
    "complete_file_listing_fragment": "SELECT count(*) FROM pr_code_observations c JOIN pr_observations o ON o.id=c.observation_id JOIN collections l ON l.pr_id=c.pr_id AND l.job_id=o.job_id AND l.kind='pr-files' AND l.state='complete' WHERE c.state='complete' AND (SELECT count(*) FROM pr_file_changes m WHERE m.code_observation=c.id)!=(SELECT count(*) FROM collection_memberships m WHERE m.collection_id=l.id)",
}

JSON_COLUMNS = {
    "sources": ("settings",),
    "inventory_runs": ("scope",),
    "repositories": ("metadata",),
    "jobs": ("request", "checkpoint"),
    "collection_runs": ("request", "roots_manifest"),
    "commits": ("metadata",),
    "coverage_components": ("details",),
    "pr_observations": ("payload",),
    "pr_documents": ("metadata",),
    "resource_observations": ("metadata",),
    "pr_reviews": ("payload",),
    "review_threads": ("payload",),
    "review_comments": ("payload",),
    "pr_events": ("payload",),
    "pr_code_observations": ("details",),
    "pr_commits": ("payload",),
    "pr_file_changes": ("payload",),
    "collections": ("scope",),
    "collection_pages": ("request",),
    "sync_checkpoints": ("value",),
    "search_documents": ("metadata",),
    "service_instances": ("metadata",),
    "repository_bindings": ("metadata",),
    "repository_endpoints": ("metadata",),
}
BOOLEAN_COLUMNS = {
    "preservation_obligations": (
        "roots_fixed",
        "structure_done",
        "digest_done",
        "text_done",
        "published",
    ),
    "snapshots": ("published",),
    "acquisition_roots": ("published",),
    "git_objects": ("verified",),
    "root_manifests": ("complete",),
    "pr_observations": ("published",),
    "pr_documents": ("deleted",),
    "repository_endpoints": ("is_preferred",),
}
ORDINAL_COLUMNS = {
    "commit_parents": ("parent_ordinal",),
    "pr_events": ("ordinal",),
    "pr_commits": ("ordinal",),
    "pr_file_changes": ("ordinal",),
    "collection_pages": ("ordinal",),
    "collection_memberships": ("ordinal",),
}
STATE_VALUES = {
    "jobs": (
        "queued",
        "running",
        "waiting",
        "complete",
        "failed",
        "interrupted",
        "cancelled",
    ),
    "inventory_runs": ("running", "complete", "partial"),
    "collection_runs": ("planned", "fetching", "refs_captured", "published"),
    "cache_entries": ("available", "evicting", "evicted"),
    "collections": ("running", "partial", "complete"),
    "pr_code_observations": ("pending", "partial", "complete"),
    "index_generations": ("building", "ready", "retired", "removed", "unavailable"),
    "content_locations": ("available", "unavailable"),
}


def diagnose(db, *, hash_payloads=False):
    inventory = schema_inventory(db)
    if inventory["schema_version"] != 2:
        raise ValueError("This diagnostic requires v2; no automatic schema conversion")
    checks = {code: db.execute(sql).fetchone()[0] for code, sql in OWNERSHIP.items()}
    checks["foreign_keys"] = sum(1 for _ in db.execute("PRAGMA foreign_key_check"))
    checks["sqlite_integrity"] = sum(
        r[0] != "ok" for r in db.execute("PRAGMA integrity_check")
    )
    for table, columns in JSON_COLUMNS.items():
        for column in columns:
            col = identifier(column)
            checks[f"json:{table}.{column}"] = db.execute(
                f"SELECT count(*) FROM {identifier(table)} WHERE {col} IS NOT NULL AND NOT json_valid({col})"
            ).fetchone()[0]
    for group, label, expression in (
        (BOOLEAN_COLUMNS, "boolean", "NOT IN (0,1)"),
        (ORDINAL_COLUMNS, "ordinal", "<0"),
    ):
        for table, columns in group.items():
            for column in columns:
                checks[f"{label}:{table}.{column}"] = db.execute(
                    f"SELECT count(*) FROM {identifier(table)} WHERE {identifier(column)} {expression}"
                ).fetchone()[0]
    for table, states in STATE_VALUES.items():
        checks[f"state:{table}"] = db.execute(
            f"SELECT count(*) FROM {identifier(table)} WHERE state NOT IN ({','.join('?' for _ in states)})",
            states,
        ).fetchone()[0]
    for table in ("jobs", "cache_leases", "collection_runs"):
        checks[f"attempt:{table}"] = db.execute(
            f"SELECT count(*) FROM {identifier(table)} WHERE attempt<1"
        ).fetchone()[0]
    for table, fmt, oid in (
        ("ref_observations", "object_format", "target_oid"),
        ("acquisition_roots", "object_format", "oid"),
        ("tree_entries", "child_format", "child_oid"),
        ("root_manifest_entries", "object_format", "oid"),
        ("pr_git_links", "object_format", "oid"),
    ):
        checks[f"oid:{table}"] = db.execute(
            f"SELECT count(*) FROM {identifier(table)} WHERE NOT (({fmt}='sha1' AND typeof({oid})='blob' AND length({oid})=20) OR ({fmt}='sha256' AND typeof({oid})='blob' AND length({oid})=32))"
        ).fetchone()[0]
    payload_checks = {}
    if hash_payloads:
        for table, body, digest in (
            ("api_responses", "body", "payload_sha256"),
            ("document_versions", "body", "body_sha256"),
        ):
            bad, skipped = 0, 0
            for row in db.execute(
                f"SELECT {body},{digest},length(CAST({body} AS BLOB)) FROM {table} WHERE length(CAST({body} AS BLOB))<=33554432"
            ):
                raw = row[0].encode("utf-8") if isinstance(row[0], str) else row[0]
                bad += hashlib.sha256(raw).digest() != row[1]
            skipped = db.execute(
                f"SELECT count(*) FROM {table} WHERE length(CAST({body} AS BLOB))>33554432"
            ).fetchone()[0]
            checks[f"sha256:{table}"] = bad
            payload_checks[table] = {"oversize_unverified": skipped}
    names = {t["name"] for t in inventory["tables"]}
    return {
        "schema_version": 2,
        "schema_sha256": inventory["schema_sha256"],
        "counts": {
            t: db.execute(f"SELECT count(*) FROM {identifier(t)}").fetchone()[0]
            for t in sorted(names)
        },
        "violations": {k: v for k, v in checks.items() if v},
        "checks_run": len(checks),
        "payload_hashing": hash_payloads,
        "payload_checks": payload_checks,
        "limitations": [
            "No repair or completeness upgrade",
            "No raw Git closure verification",
            "JSON validity does not establish expected shape",
            "Zero violations does not establish migration readiness or absent data",
            "No row identifiers or payloads in report",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--database", type=Path)
    choice.add_argument("--fixture-schema", action="store_true")
    parser.add_argument("--hash-payloads", action="store_true")
    args = parser.parse_args()
    if args.fixture_schema:
        from repo_catalog.application.maintenance_service import MaintenanceService

        with tempfile.TemporaryDirectory(
            prefix="repo-catalog-schema-audit-"
        ) as directory:
            state = Path(directory) / "state"
            MaintenanceService(state).init("catalog-text-v1", 67108864, 0)
            with readonly(state / "catalog.sqlite3") as db:
                result = schema_inventory(db)
    else:
        with args.database.open("rb") as stream:
            before = hashlib.file_digest(stream, "sha256").digest()
        with readonly(args.database) as db:
            result = diagnose(db, hash_payloads=args.hash_payloads)
        with args.database.open("rb") as stream:
            after = hashlib.file_digest(stream, "sha256").digest()
        if before != after:
            raise ValueError(
                "Source DB changed during diagnosis; do not use this report"
            )
        result["source_file_unchanged"] = True
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
