"""Select current comparison evidence by observation and actual domain values."""

from __future__ import annotations

import hashlib
import json


def finalize_pending_assessment(existing, candidate):
    """Recognize completion of one capture, never a freshness decision.

    The pending form has the same immutable owner, comparison, parser and
    observation clock. Only the final state and added diagnostic details may
    become known. A reversed delivery of that exact pending form is harmless.
    """
    if existing["state"] == "pending" and candidate["state"] in {
        "partial",
        "complete",
    }:
        pending, final = existing, candidate
    elif candidate["state"] == "pending" and existing["state"] in {
        "partial",
        "complete",
    }:
        pending, final = candidate, existing
    else:
        return None
    if any(
        pending[column] != final[column]
        for column in pending.keys() | final.keys()
        if column not in {"state", "details_json"}
    ):
        return None
    pending_details = json.loads(pending["details_json"])
    final_details = json.loads(final["details_json"])
    if any(final_details.get(key) != value for key, value in pending_details.items()):
        return None
    return final


def _rows(store, statement, parameters):
    cursor = store.execute(statement, parameters)
    columns = tuple(column[0] for column in cursor.description)
    return (dict(zip(columns, row, strict=True)) for row in cursor)


def _canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda item: {"bytes": item.hex()},
    )


def _listing_signature(store, listing_id, kind):
    if listing_id is None:
        return None
    progress = next(
        _rows(
            store,
            "SELECT state,terminal,context_proven FROM code_listing_progress WHERE code_listing_id=?",
            (listing_id,),
        ),
        None,
    )
    table = "code_commits" if kind == "commits" else "code_file_changes"
    digest = hashlib.sha256()
    for row in _rows(
        store,
        f"SELECT * FROM {table} WHERE code_listing_id=? ORDER BY position",
        (listing_id,),
    ):
        row.pop("code_listing_id")
        row["metadata"] = json.loads(row["metadata"])
        digest.update(_canonical(row).encode() + b"\n")
    return progress, digest.hexdigest()


def current_code_assessment(
    store, change_request_id, object_format, head_oid, base_oid
):
    """Return equivalent maximal observations, or no selection on disagreement.

    Capture identifiers and parser versions cannot break a tie. Compare the
    actual normalized enumerations and role targets, including partial states.
    Old captures remain only as their minimal Git acquisition/target evidence.
    """
    rows = list(
        _rows(
            store,
            "WITH target AS MATERIALIZED (SELECT * FROM code_assessments WHERE change_request_id=? AND object_format IS ? AND head_oid IS ? AND base_oid IS ?) SELECT * FROM target WHERE observed_at_us IS (SELECT max(observed_at_us) FROM target) ORDER BY code_assessment_id",
            (change_request_id, object_format, head_oid, base_oid),
        )
    )
    if len(rows) < 2:
        return rows[0] if rows else None
    listings, signatures = {}, set()
    for row in rows:
        signature = {
            "state": row["state"],
            "details": json.loads(row["details_json"]),
            "roles": list(
                _rows(
                    store,
                    "SELECT role,object_format,oid FROM code_acquisitions WHERE code_assessment_id=? ORDER BY role",
                    (row["code_assessment_id"],),
                )
            ),
        }
        for kind, column in (
            ("commits", "commit_code_listing_id"),
            ("files", "file_code_listing_id"),
        ):
            key = (kind, row[column])
            if key not in listings:
                listings[key] = _listing_signature(store, row[column], kind)
            signature[kind] = listings[key]
        signatures.add(_canonical(signature))
        if len(signatures) > 1:
            return None
    return rows[0]
