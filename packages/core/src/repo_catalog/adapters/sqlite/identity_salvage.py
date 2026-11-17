"""Typed immutable identity recovery units, independent of Context installation.

Only the paired adapter supplies Context row classes and admission capabilities.
Extraction qualifications, recovered flags and claimed sender identity never
replace canonical row, payload, provenance and authority checks.
"""

from __future__ import annotations

import json

from repo_catalog.domain.identity_assertions import identity_values
from repo_catalog.domain.shared_values import Provenance

IDENTITY_CANDIDATES = {
    "repository_identity_assertion": (
        "repository",
        "relation",
        "repository_identity_assertions",
    ),
    "repository_identity_cancellation": (
        "repository",
        "cancellation",
        "repository_identity_cancellations",
    ),
    "service_identity_assertion": (
        "service",
        "relation",
        "service_identity_assertions",
    ),
    "service_identity_cancellation": (
        "service",
        "cancellation",
        "service_identity_cancellations",
    ),
}


def identity_source_candidate(store, table, row):
    """Classify plain untrusted source columns without evaluating source SQL."""
    for candidate, (entity, kind, target) in IDENTITY_CANDIDATES.items():
        owner = "core" if entity == "repository" else "context"
        if store == owner and table == target:
            ident = "relation_uuidv4" if kind == "relation" else "cancellation_uuidv4"
            return candidate, str(row.get(ident)), dict(row)
    return None


def decode_identity_candidate(candidate, payload, row_types, work):
    """Revalidate the exact full semantic row, without manufacturing dependencies."""
    entity, kind, table = IDENTITY_CANDIDATES[candidate]
    if type(payload) is not dict or any(
        type(value) is not str for value in payload.values()
    ):
        raise ValueError("exact typed identity row required")
    size = sum(len(value) for value in payload.values())
    work.require("input_bytes", size * 4)
    actual = 0
    try:
        for value in payload.values():
            actual += len(value.encode("utf-8"))
    finally:
        work.charge("input_bytes", actual)
    work.require("metadata_units", len(payload))
    try:
        row_type = row_types[table]
        columns, values = row_type.insert_bindings(payload)
        if columns != row_type.WRITE_COLUMNS:
            raise ValueError("complete identity row required")
        row_type.from_record(payload)
        original = Provenance(*json.loads(payload["provenance"]))
        if original.encoded != payload["provenance"]:
            raise ValueError("canonical original provenance required")
        expected = identity_values(kind, entity, payload["record_json"], original)
        if values != expected:
            raise ValueError("identity row coordinates differ from original record")
        return kind, original
    except (RecursionError, OverflowError) as error:
        raise ValueError(
            "identity metadata exceeds supported JSON structure"
        ) from error
    finally:
        work.charge("metadata_units", len(payload))
