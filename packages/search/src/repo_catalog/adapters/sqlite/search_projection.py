"""Legacy pair-facing Search facade over the canonical optional index engine."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from typing import TYPE_CHECKING

from repo_catalog.adapters.sqlite.production_search import (
    _query_candidate_rows,
    _replace_projection_rows,
)
from repo_catalog.domain.p1_coordination import CoordinationError, SnapshotToken
from repo_catalog.domain.query_contracts import canonical_json as _json

if TYPE_CHECKING:
    from repo_catalog.adapters.sqlite.paired_coordination import PairedSnapshot


def validate_pair(core, context):
    from repo_catalog.adapters.sqlite.paired_coordination import (
        validate_pair as validate,
    )

    return validate(core, context)


class SearchProjection:
    """Discardable authority-derived candidates; None requires authority scan.

    Public builders read actual pinned authority. There is no general text/body
    admission API: P6 owns additional typed projectors, including verified notes.
    """

    def __init__(self, db: sqlite3.Connection | None):
        self.db = db

    @staticmethod
    def context_documents(pair: PairedSnapshot) -> dict[str, str]:
        if validate_pair(pair.core, pair.context) != pair.token:
            raise CoordinationError("SNAPSHOT_CONTENT", "search")
        documents = {}
        for row in pair.context.execute(
            "SELECT c.service_instance_uuidv4,c.resource_kind,c.provider_resource_id,c.field_name,"
            "c.clock_json,c.value_json,c.provenance_json,b.text_value "
            "FROM field_candidates c LEFT JOIN text_bodies b ON c.text_body_sha256=b.sha256"
        ):
            # Only this named local FK denotes retained text. Reported digests
            # remain qualified metadata even if equal bytes happen to be local.
            value = row[7] if row[3] == "text_body_sha256" else json.loads(row[5])
            if isinstance(value, str):
                documents[_json(tuple(row[:7]))] = value
        return documents

    def rebuild_context(self, pair: PairedSnapshot):
        self._replace("context_text", pair.token, self.context_documents(pair))

    def rebuild_git_metadata(self, pair: PairedSnapshot):
        if validate_pair(pair.core, pair.context) != pair.token:
            raise CoordinationError("SNAPSHOT_CONTENT", "search")
        documents = {
            _json(tuple(row)): row[1]
            for row in pair.core.execute(
                "SELECT object_format,object_oid FROM git_objects"
            )
        }
        self._replace("git_metadata", pair.token, documents)

    def _replace(self, kind: str, token: SnapshotToken, documents: dict[str, str]):
        if self.db is None:
            raise CoordinationError("UNAVAILABLE", "search")
        _replace_projection_rows(self.db, kind, token.encode(), documents)

    def candidates(
        self, kind: str, token: SnapshotToken, needle: str
    ) -> set[str] | None:
        if self.db is None:
            return None
        try:
            self.db.execute("BEGIN")
            rows = _query_candidate_rows(self.db, kind, token.encode(), needle)
            return set(rows) if rows is not None else None
        except (sqlite3.DatabaseError, ValueError, TypeError, RecursionError):
            return None
        finally:
            self.db.rollback()

    def read(
        self,
        kind: str,
        token: SnapshotToken,
        needle: str,
        authoritative_scan: Callable[[], dict[str, str]],
    ) -> tuple[str, dict[str, str]]:
        candidates = self.candidates(kind, token, needle)
        rows = authoritative_scan()  # caller retains pinned authority snapshot
        expected = {key for key, text in rows.items() if needle in text}
        if candidates is not None and candidates != expected:
            # A matching freshness token alone cannot prove a damaged/truncated
            # projection complete. The conservative P1 adapter verifies against
            # direct authority; optimized completeness proof belongs to P6.
            candidates = None
        return (
            "projection" if candidates is not None else "authority_scan",
            {
                key: text
                for key, text in rows.items()
                if needle in text and (candidates is None or key in candidates)
            },
        )
