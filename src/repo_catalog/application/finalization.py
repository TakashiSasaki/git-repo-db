"""Explicit readiness and current selection from preserved source evidence."""

from __future__ import annotations

import json

from repo_catalog.domain.models import CatalogError

IDENTITY_TABLES = {
    "service_instances",
    "sources",
    "repositories",
    "repository_bindings",
    "repository_endpoints",
    "source_repositories",
}


CRITICAL_COLUMNS = {
    "id",
    "pr_id",
    "repo_id",
    "object_id",
    "object_format",
    "oid",
    "provider_id",
    "thread_id",
    "binding_id",
}
DOMAIN_IDENTITIES = {
    "pull_requests",
    "change_requests",
    "pr_documents",
    "documents",
    "git_objects",
    "review_threads",
    "pr_reviews",
    "review_comments",
}
CRITICAL_CODES = {
    "SOURCE_FOREIGN_KEY_FAILURE",
    "IDENTITY_CONFLICT",
    "OBJECT_HASH_MISMATCH",
    "EXPECTED_OID_MISMATCH",
    "INVALID_VERIFICATION_ASSERTION",
    "THREAD_IDENTITY_CONFLICT",
    "PARENT_ORDER_MISMATCH",
    "GIT_PARENT_ORDER_MISMATCH",
    "GIT_HEADER_TREE_MISMATCH",
    "GIT_TAG_TARGET_MISMATCH",
    "GIT_OBJECT_RELATION_MISMATCH",
    "PAYLOAD_DIGEST_MISMATCH",
    "OBJECT_FORMAT_MISMATCH",
    "ACQUISITION_ROLE_CONFLICT",
}


def check_catalog(store):
    """Bounded structural audit; callers choose when to perform it."""
    issues = [dict(row) for row in store.all("PRAGMA foreign_key_check")]
    integrity = [row[0] for row in store.all("PRAGMA quick_check")]
    if integrity != ["ok"]:
        issues.append({"code": "SQLITE_STRUCTURAL_CORRUPTION", "details": integrity})
    for row in store.all(
        "SELECT id,code,details FROM validation_results WHERE severity='blocking'"
    ):
        details = json.loads(row["details"])
        record = store.one(
            "SELECT source_table FROM legacy_records WHERE id=?",
            (details.get("record_id"),),
        )
        if (
            (record and record[0] in IDENTITY_TABLES)
            or details.get("recipe") in IDENTITY_TABLES
            or (
                record
                and record[0] in DOMAIN_IDENTITIES
                and details.get("column") in CRITICAL_COLUMNS
            )
            or row["code"] in CRITICAL_CODES
            or "OWNER_MISMATCH" in row["code"]
        ):
            issues.append({"diagnostic_id": row["id"], "code": row["code"]})
    return issues


def archived_rows(store, table):
    """Read only current-selection evidence, preserving undecodable assertions."""
    for record in store.all(
        "SELECT id,source_id FROM legacy_records WHERE source_table=? ORDER BY id",
        (table,),
    ):
        run = store.one(
            "SELECT manifest FROM conversion_runs WHERE source_id=?",
            (record["source_id"],),
        )
        encoding = json.loads(run[0]).get("encoding", "UTF-8") if run else "UTF-8"
        values = {}
        for row in store.all(
            "SELECT column_name,storage_type,value_bytes FROM legacy_values WHERE record_id=?",
            (record[0],),
        ):
            kind, raw = row["storage_type"], bytes(row["value_bytes"])
            try:
                value = (
                    None
                    if kind == "null"
                    else int(raw.decode("ascii"))
                    if kind == "integer"
                    else raw.decode(encoding)
                    if kind == "text"
                    else raw
                )
            except (ValueError, UnicodeError):
                value = raw
            values[row["column_name"]] = value
        yield record[0], values


def finalize_catalog(store):
    """Validate readiness; restore explicit same-owner published assertions only."""
    with store.transaction():
        if (
            store.one("SELECT lifecycle FROM database_identity WHERE singleton=1")[0]
            == "validated"
        ):
            return {
                "lifecycle": "validated",
                "restored": [],
                "unresolved_current": [],
                "catalog": store.revision(),
            }
        issues = check_catalog(store)
        runs = store.all("SELECT * FROM conversion_runs")
        for run in runs:
            manifest = json.loads(run["manifest"])
            if run["parser_version"] != "offline-v2/1" or not manifest.get("complete"):
                issues.append({"run_id": run["id"], "code": "IMPORT_INCOMPLETE"})
            if manifest.get("source_foreign_key_issues"):
                issues.append({"run_id": run["id"], "code": "SOURCE_OWNER_CORRUPTION"})
        if issues:
            raise CatalogError(
                "TARGET_NOT_READY",
                "Critical import or owner evidence prevents finalization",
                {"issues": issues},
            )
        unresolved, restored = [], []

        # These are saved publication assertions, never new observations.
        for record_id, legacy in archived_rows(store, "pr_observations"):
            candidate = store.one(
                "SELECT * FROM change_request_observations WHERE id=? AND change_request_id=?",
                (legacy.get("id"), legacy.get("pr_id")),
            )
            if (
                legacy.get("published") == 1
                and candidate
                and candidate["observed_at"]
                and candidate["payload"] == legacy.get("payload")
            ):
                store.execute(
                    "UPDATE change_request_observations SET published=1 WHERE id=?",
                    (candidate["id"],),
                )

        selections = (
            (
                "repositories",
                "current_snapshot",
                "repositories",
                "current_snapshot_id",
                "snapshots",
                "repo_id",
                True,
            ),
            (
                "pull_requests",
                "current_observation",
                "change_requests",
                "current_observation_id",
                "change_request_observations",
                "change_request_id",
                True,
            ),
            (
                "pr_documents",
                "current_version",
                "documents",
                "current_version_id",
                "document_versions",
                "document_id",
                False,
            ),
        )
        for (
            source_table,
            source_pointer,
            target_table,
            target_pointer,
            facts,
            owner_column,
            needs_published,
        ) in selections:
            for record_id, legacy in archived_rows(store, source_table):
                owner, candidate_id = legacy.get("id"), legacy.get(source_pointer)
                target = store.one(
                    f"SELECT {target_pointer} FROM {target_table} WHERE id=?", (owner,)
                )
                if not target:
                    continue
                if candidate_id is None:
                    if target[0] is None:
                        unresolved.append(
                            {
                                "table": target_table,
                                "owner_id": owner,
                                "record_id": record_id,
                                "reason": "no_saved_current_selection",
                            }
                        )
                    continue
                candidate = store.one(
                    f"SELECT * FROM {facts} WHERE id=? AND {owner_column}=?",
                    (candidate_id, owner),
                )
                valid = candidate is not None and (
                    not needs_published or candidate["published"] == 1
                )
                if valid and facts == "snapshots":
                    valid = (
                        store.one(
                            "SELECT 1 FROM git_acquisitions WHERE id=? AND repo_id=? AND object_format IS NOT NULL AND refs_observed_at IS NOT NULL",
                            (candidate["acquisition_id"], owner),
                        )
                        is not None
                    )
                if valid and facts == "document_versions":
                    valid = (
                        store.one(
                            "SELECT 1 FROM document_observations WHERE document_id=? AND version_id=? AND observed_at IS NOT NULL",
                            (owner, candidate_id),
                        )
                        is not None
                    )
                if valid and target[0] in (None, candidate_id):
                    store.execute(
                        f"UPDATE {target_table} SET {target_pointer}=? WHERE id=?",
                        (candidate_id, owner),
                    )
                    restored.append(
                        {
                            "table": target_table,
                            "owner_id": owner,
                            "candidate_id": candidate_id,
                            "record_id": record_id,
                        }
                    )
                else:
                    unresolved.append(
                        {
                            "table": target_table,
                            "owner_id": owner,
                            "record_id": record_id,
                            "reason": "saved_selection_not_suitable",
                        }
                    )

        for run in runs:
            # The original manifest/typed archive remains unchanged. Readiness
            # decisions are retained inside the catalog, independent of paths.
            previous = store.one(
                "SELECT 1 FROM validation_results WHERE run_id=? AND code='RUNTIME_FINALIZATION'",
                (run["id"],),
            )
            if not previous:
                store.execute(
                    "INSERT INTO validation_results(run_id,invariant_id,code,severity,observed_at,details) VALUES(?,'runtime-readiness','RUNTIME_FINALIZATION','info',datetime('now'),?)",
                    (
                        run["id"],
                        json.dumps(
                            {"restored": restored, "unresolved": unresolved},
                            sort_keys=True,
                        ),
                    ),
                )
        # Old process state is historical; it cannot become a running job.
        store.execute("DELETE FROM cache_leases")
        store.execute("DELETE FROM space_reservations")
        store.execute(
            "UPDATE database_identity SET lifecycle='validated' WHERE singleton=1"
        )
        store.publish()
        return {
            "lifecycle": "validated",
            "restored": restored,
            "unresolved_current": unresolved,
            "catalog": store.revision(),
        }
