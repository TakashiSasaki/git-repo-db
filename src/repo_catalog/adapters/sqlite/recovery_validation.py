"""Recheck enduring admission invariants without executing recovered schema."""

import re
import sqlite3

from repo_catalog.adapters.sqlite.p1_schema import expected_schema
from repo_catalog.domain.recovery import BackupValidationError

# INSERT-time replay/current-terminal predicates are deliberately excluded:
# old Coverage evidence remains valid history after a later terminal arrives.
_PERSISTENT_GUARDS = {
    "core": {
        "relation_targets",
        "notes_group_targets",
        "notes_inventory_guard",
        "metadata_same_representation",
        "intrinsic_claim_guard",
        "intrinsic_group_guard",
        "notes_same_representation",
        "notes_claim_format",
        "notes_group_format",
        "core_coverage_members",
    },
    "context": {"coverage_proof_owner", "source_coverage_owner"},
}


def validate_stored_admission_guards(connection: sqlite3.Connection, role: str) -> None:
    """Evaluate trusted packaged enduring BEFORE INSERT predicates on stored rows.

    integrity_check checks CHECK constraints, not relational admission triggers.
    Only packaged SQL is interpreted here; recovered trigger bodies are never run.
    """
    remaining = set(_PERSISTENT_GUARDS[role])
    for kind, name, _, sql in expected_schema(role):
        if kind != "trigger" or name not in remaining:
            continue
        match = re.fullmatch(
            r"CREATE TRIGGER \w+ BEFORE INSERT ON (\w+)\s+WHEN (.*?)\s+BEGIN.*",
            sql,
            flags=re.DOTALL,
        )
        if match is None:
            raise RuntimeError(f"Unsupported packaged recovery guard: {name}")
        table, predicate = match.groups()
        predicate = re.sub(r"\bNEW\.(\w+)", r'"recovery_candidate"."\1"', predicate)
        if connection.execute(
            f'SELECT 1 FROM "{table}" AS recovery_candidate WHERE {predicate} LIMIT 1'
        ).fetchone():
            raise BackupValidationError(
                f"Stored {role} domain admission invariant failed: {name}"
            )
        remaining.remove(name)
    if remaining:
        raise RuntimeError(f"Missing packaged recovery guards: {sorted(remaining)}")


def validate_context_text_encoding(connection: sqlite3.Connection) -> None:
    # Read exact bytes explicitly: SQLite's automatic text decoding otherwise
    # turns confirmed invalid stored UTF-8 into a generic SQLITE_ERROR.
    for (raw,) in connection.execute(
        "SELECT CAST(text_value AS BLOB) FROM text_bodies"
    ):
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            raise BackupValidationError(
                "Stored Context text is invalid UTF-8"
            ) from None
