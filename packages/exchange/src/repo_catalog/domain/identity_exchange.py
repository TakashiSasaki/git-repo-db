"""Portable reported identity evidence; no identity graph or authority transfer."""

from __future__ import annotations

import json

from repo_catalog.domain.exchange import ExchangeError
from repo_catalog.domain.identity_assertions import identity_values
from repo_catalog.domain.p1_core import Provenance

IDENTITY_SECTIONS = {
    "repository_identity_assertions": ("core", "relation", "repository"),
    "repository_identity_cancellations": ("core", "cancellation", "repository"),
    "service_identity_assertions": ("context", "relation", "service"),
    "service_identity_cancellations": ("context", "cancellation", "service"),
}


def identity_columns(section):
    columns = ("relation_uuidv4", "record_json", "provenance")
    return (
        ("cancellation_uuidv4", *columns)
        if IDENTITY_SECTIONS[section][1] == "cancellation"
        else columns
    )


def decode_identity_row(section, row):
    """Check exact original record, provenance and every duplicated coordinate."""
    _, kind, entity_kind = IDENTITY_SECTIONS[section]
    columns = identity_columns(section)
    try:
        if type(row) is not dict or set(row) != set(columns):
            raise ValueError
        if any(type(value) is not str for value in row.values()):
            raise ValueError
        original = json.loads(row["provenance"])
        if (
            type(original) is not list
            or len(original) != 6
            or any(type(v) is not str for v in original)
        ):
            raise ValueError
        provenance = Provenance(*original)
        if provenance.encoded != row["provenance"]:
            raise ValueError
        values = identity_values(kind, entity_kind, row["record_json"], provenance)
        if values != tuple(row[column] for column in columns):
            raise ValueError
        return kind, provenance, json.loads(row["record_json"])
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise ExchangeError("INVALID_IDENTITY_EVIDENCE", section) from error


def identity_dependencies(data):
    """Exact service assertion targets and reported endpoints, never inferred ones."""
    from repo_catalog.domain.context_admission import DependencySet

    targets, providers = set(), set()
    for section in ("service_identity_assertions", "service_identity_cancellations"):
        for row in data.get(section, ()):
            kind, _, record = decode_identity_row(section, row)
            targets.add(record["relation_uuidv4"])
            if kind == "relation":
                providers.update(
                    (
                        record["left_service_instance_uuidv4"],
                        record["right_service_instance_uuidv4"],
                    )
                )
    return DependencySet(identity_assertions=targets, provider_registrations=providers)
