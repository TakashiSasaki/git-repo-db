"""Typed portable equivalence evidence and non-authoritative graph projections.

An asserted equivalence never changes either endpoint's nominal identity. A
cancellation is independently meaningful even before its assertion arrives.
"""

from __future__ import annotations

import json
from collections import defaultdict

from repo_catalog.domain.shared_values import (
    CoreFailure,
    Provenance,
    encode,
    uuid4_value,
)
from repo_catalog.domain.time import validate_observation_us

_RELATION_FIELDS = frozenset(
    {
        "relation_uuidv4",
        "entity_kind",
        "left_repository_uuidv4",
        "right_repository_uuidv4",
        "left_service_instance_uuidv4",
        "right_service_instance_uuidv4",
        "evidence_json",
        "asserted_at_us",
    }
)
_CANCELLATION_FIELDS = frozenset(
    {
        "cancellation_uuidv4",
        "relation_uuidv4",
        "evidence_json",
        "asserted_at_us",
    }
)


def _reject_constant(value):
    raise ValueError(f"nonfinite JSON constant: {value}")


def identity_record(kind, record):
    """Validate the original typed record, preserving its supplied evidence text."""
    if kind not in ("relation", "cancellation"):
        raise CoreFailure("IDENTITY_RECORD", kind, "unknown identity evidence kind")
    expected = _RELATION_FIELDS if kind == "relation" else _CANCELLATION_FIELDS
    if type(record) is not dict or set(record) != expected:
        raise CoreFailure("IDENTITY_RECORD", kind, "identity evidence fields differ")
    uuid4_value(record["relation_uuidv4"])
    validate_observation_us(record["asserted_at_us"])
    evidence = record["evidence_json"]
    if type(evidence) is not str or not isinstance(
        json.loads(evidence, parse_constant=_reject_constant), dict
    ):
        raise CoreFailure("IDENTITY_RECORD", kind, "evidence must be a JSON object")
    if kind == "cancellation":
        uuid4_value(record["cancellation_uuidv4"])
    else:
        entity_kind = record["entity_kind"]
        if entity_kind not in ("repository", "service"):
            raise CoreFailure("IDENTITY_RECORD", entity_kind, "unknown endpoint kind")
        suffix = (
            "repository_uuidv4"
            if entity_kind == "repository"
            else "service_instance_uuidv4"
        )
        absent = (
            "service_instance_uuidv4"
            if entity_kind == "repository"
            else "repository_uuidv4"
        )
        left, right = record[f"left_{suffix}"], record[f"right_{suffix}"]
        uuid4_value(left)
        uuid4_value(right)
        if left == right or any(
            record[f"{side}_{absent}"] is not None for side in ("left", "right")
        ):
            raise CoreFailure(
                "IDENTITY_RECORD", kind, "distinct same-kind endpoints required"
            )
    return encode(record)


def _reports(kind, rows, maximum):
    grouped = defaultdict(lambda: defaultdict(list))
    reports = []
    identity = "relation_uuidv4" if kind == "relation" else "cancellation_uuidv4"
    for index, row in enumerate(rows):
        if index >= maximum:
            raise CoreFailure("IDENTITY_BUDGET", kind, "finite evidence limit")
        raw, original = row["record_json"], row["provenance"]
        record = json.loads(raw)
        if identity_record(kind, record) != raw:
            raise CoreFailure(
                "IDENTITY_RECORD", kind, "noncanonical stored identity record"
            )
        provenance = Provenance(*json.loads(original))
        if provenance.qualification != "reported" or provenance.encoded != original:
            raise CoreFailure(
                "UNTRUSTED_VERIFICATION",
                kind,
                "identity is attributed reported evidence",
            )
        report = {**record, "provenance": list(provenance.key)}
        grouped[record[identity]][raw].append(report)
        reports.append(report)
    reports.sort(key=encode)
    for payloads in grouped.values():
        for originals in payloads.values():
            originals.sort(key=encode)
    return grouped, reports


def _closure(edges, kind, maximum):
    graph = defaultdict(set)
    for left, right in edges:
        graph[left].add(right)
        graph[right].add(left)
    pairs = []
    for start in sorted(graph):
        seen, pending = {start}, [start]
        while pending:
            node = pending.pop()
            for neighbor in graph[node] - seen:
                seen.add(neighbor)
                pending.append(neighbor)
        for target in sorted(seen - {start}):
            if len(pairs) >= maximum:
                raise CoreFailure("IDENTITY_BUDGET", kind, "finite closure pair limit")
            suffix = (
                "repository_uuidv4"
                if kind == "repository"
                else "service_instance_uuidv4"
            )
            pairs.append({suffix: start, "equivalent_" + suffix: target})
    return pairs


def identity_status(
    relations,
    cancellations,
    *,
    repository_uuids,
    service_uuids=None,
    max_evidence=10000,
    max_closure_pairs=100000,
):
    """Derive conflicts, unresolved dependencies and two separate equivalence graphs.

    Context service identities are optional input, never an inferred Core FK.
    Supplying no Context snapshot leaves service assertions explicitly unresolved.
    Conflicting payloads never select a winner. Every reported cancellation
    suppresses its target, including cancellations whose own IDs conflict.
    """
    for value in (max_evidence, max_closure_pairs):
        if type(value) is not int or value <= 0:
            raise ValueError("positive finite identity projection limits required")
    assertions, relation_reports = _reports("relation", relations, max_evidence)
    cancelled, cancellation_reports = _reports(
        "cancellation", cancellations, max_evidence
    )
    known_repositories = frozenset(uuid4_value(value) for value in repository_uuids)
    known_services = (
        None
        if service_uuids is None
        else frozenset(uuid4_value(value) for value in service_uuids)
    )
    conflicts = []
    for kind, groups in (("relation", assertions), ("cancellation", cancelled)):
        for ident, payloads in sorted(groups.items()):
            if len(payloads) > 1:
                conflicts.append(
                    {
                        "kind": kind,
                        "record_uuidv4": ident,
                        "records": [
                            report
                            for raw in sorted(payloads)
                            for report in payloads[raw]
                        ],
                    }
                )
    targets = {report["relation_uuidv4"] for report in cancellation_reports}
    active, unresolved = [], []
    edges = {"repository": [], "service": []}
    for ident, payloads in sorted(assertions.items()):
        if len(payloads) != 1 or ident in targets:
            continue
        reports = next(iter(payloads.values()))
        record = reports[0]
        kind = record["entity_kind"]
        suffix = (
            "repository_uuidv4" if kind == "repository" else "service_instance_uuidv4"
        )
        endpoints = (record[f"left_{suffix}"], record[f"right_{suffix}"])
        known = known_repositories if kind == "repository" else known_services
        missing = (
            endpoints
            if known is None
            else tuple(value for value in endpoints if value not in known)
        )
        if missing:
            unresolved.append(
                {
                    "kind": "relation",
                    "record_uuidv4": ident,
                    "reason": "context_unavailable"
                    if known is None
                    else "endpoint_missing",
                    "entity_kind": kind,
                    "missing_endpoints": list(missing),
                }
            )
            continue
        active.extend(reports)
        edges[kind].append(endpoints)
    for ident in sorted(targets - assertions.keys()):
        unresolved.append(
            {
                "kind": "cancellation",
                "relation_uuidv4": ident,
                "reason": "assertion_not_present",
            }
        )
    return {
        "identity_relations": relation_reports,
        "identity_relation_cancellations": cancellation_reports,
        "active_identity_relations": active,
        "repository_equivalence_closure": _closure(
            edges["repository"], "repository", max_closure_pairs
        ),
        "service_equivalence_closure": _closure(
            edges["service"], "service", max_closure_pairs
        ),
        "identity_conflicts": conflicts,
        "identity_unresolved": unresolved,
    }


def identity_values(kind, entity_kind, record_json, provenance):
    """Validate one authority-owned unit and expose its complete semantic row."""
    if entity_kind not in ("repository", "service"):
        raise CoreFailure("IDENTITY_RECORD", entity_kind, "unknown identity authority")
    record = json.loads(record_json)
    if identity_record(kind, record) != record_json:
        raise CoreFailure("IDENTITY_RECORD", kind, "canonical original record required")
    if kind == "relation" and record["entity_kind"] != entity_kind:
        raise CoreFailure("IDENTITY_RECORD", kind, "wrong identity authority")
    if not isinstance(provenance, Provenance) or provenance.qualification != "reported":
        raise CoreFailure(
            "UNTRUSTED_VERIFICATION", kind, "reported provenance required"
        )
    values = (record["relation_uuidv4"], record_json, provenance.encoded)
    if kind == "cancellation":
        values = (record["cancellation_uuidv4"], *values)
    return values


def identity_evidence_sql(kind, entity_kind, record_json, provenance):
    """SQLite predicate; malformed input is a constraint refusal, never coercion."""
    try:
        original = Provenance(*json.loads(provenance))
        return int(
            original.encoded == provenance
            and bool(identity_values(kind, entity_kind, record_json, original))
        )
    except (ValueError, TypeError, AttributeError, OverflowError, RecursionError):
        return 0
