"""Atomic coverage admission and reads derived from the immutable claim set."""

from __future__ import annotations

import sqlite3

from repo_catalog.domain.coverage import validate_claim
from repo_catalog.domain.models import CatalogError


def _rows(cursor: sqlite3.Cursor) -> list[dict]:
    """Read either ordinary tuple rows or sqlite3.Row without changing a connection."""
    columns = tuple(column[0] for column in cursor.description)
    return [dict(zip(columns, row, strict=True)) for row in cursor]


def admit_claim(
    connection: sqlite3.Connection,
    coverage_scope_id: str,
    coverage_state: str,
    observed_at_us: int,
    details_json: str | None = None,
) -> int | None:
    """Insert an eligible claim, or return None for stale or duplicate input.

    Eligibility and insertion share one SQLite write statement. Competing
    writers cannot pass separate stale/duplicate checks before either inserts.
    Excluding a duplicate before INSERT also respects the retention triggers;
    no conflict clause can replace a claim or change its advisory details.

    Scope creation belongs to the caller. This statement participates in the
    caller's transaction when one exists and never commits that transaction.
    """
    try:
        validate_claim(coverage_scope_id, coverage_state, observed_at_us)
    except (TypeError, ValueError) as cause:
        raise CatalogError(
            "INVALID_COVERAGE_CLAIM",
            "Coverage requires a scope, a stored state and an integer observation time",
        ) from cause
    if details_json is not None and not isinstance(details_json, str):
        raise CatalogError(
            "INVALID_COVERAGE_CLAIM", "Coverage details must be JSON text or NULL"
        )
    cursor = connection.execute(
        """INSERT INTO coverage_claims(
               coverage_scope_id,coverage_state,observed_at_us,details_json
           )
           SELECT :scope,:state,:observed,:details
           WHERE NOT EXISTS(
               SELECT 1 FROM coverage_claims
               WHERE coverage_scope_id=:scope AND observed_at_us>:observed
           ) AND NOT EXISTS(
               SELECT 1 FROM coverage_claims
               WHERE coverage_scope_id=:scope AND observed_at_us=:observed
                   AND coverage_state=:state
           )
           RETURNING coverage_claim_id""",
        {
            "scope": coverage_scope_id,
            "state": coverage_state,
            "observed": observed_at_us,
            "details": details_json,
        },
    )
    try:
        row = cursor.fetchone()
        return row[0] if row is not None else None
    finally:
        # Finalize RETURNING even for autocommit connections, releasing its write
        # statement promptly while leaving an explicit caller transaction intact.
        cursor.close()


def export_current_claims(
    connection: sqlite3.Connection, coverage_scope_id: str
) -> list[dict]:
    """Return all maximal-time facts; this is not a multi-catalog wire format.

    Local IDs remain local. A future exchange boundary must resolve destination
    scopes and IDs explicitly. Unknown and conflicting claims, including their
    separate advisory details, are all preserved in this selection.
    """
    return _rows(
        connection.execute(
            """SELECT coverage_claim_id,coverage_scope_id,coverage_state,
                      observed_at_us,details_json
               FROM coverage_claims
               WHERE coverage_scope_id=? AND observed_at_us=(
                   SELECT MAX(observed_at_us) FROM coverage_claims
                   WHERE coverage_scope_id=?
               )
               ORDER BY coverage_state""",
            (coverage_scope_id, coverage_scope_id),
        )
    )


def current_coverages(
    connection: sqlite3.Connection, repository_id: str, kind: str | None = None
) -> list[dict]:
    """Expand each current scope with its distinct advisory-bearing claims.

    One statement reads the view and claims in the same SQLite snapshot. Empty
    scopes have the view's unknown result and an empty claims list; no observed
    time, detail object or synthetic claim is invented for them.
    """
    rows = _rows(
        connection.execute(
            """SELECT v.*,
                      c.coverage_claim_id AS selected_claim_id,
                      c.coverage_state AS selected_coverage_state,
                      c.details_json AS selected_details_json
               FROM current_coverage v
               LEFT JOIN coverage_claims c
                 ON c.coverage_scope_id=v.coverage_scope_id
                    AND c.observed_at_us=v.observed_at_us
               WHERE v.repository_id=? AND (? IS NULL OR v.kind=?)
               ORDER BY v.kind,v.change_request_id,v.coverage_scope_id,c.coverage_state""",
            (repository_id, kind, kind),
        )
    )
    scopes = {}
    for row in rows:
        claim_id = row.pop("selected_claim_id")
        claim_state = row.pop("selected_coverage_state")
        details_json = row.pop("selected_details_json")
        scope = scopes.setdefault(row["coverage_scope_id"], {**row, "claims": []})
        if claim_id is not None:
            scope["claims"].append(
                {
                    "coverage_claim_id": claim_id,
                    "coverage_scope_id": row["coverage_scope_id"],
                    "coverage_state": claim_state,
                    "observed_at_us": row["observed_at_us"],
                    "details_json": details_json,
                }
            )
    return list(scopes.values())
