"""I4 row-local SQL contracts. These do not admit or authenticate a Transfer.

The original report owns its complete support payload; projections never query
storage. I5 must validate Provider semantics and atomically supply all endpoints.
"""

from repo_catalog.domain.p1_context import (
    TRANSFER_RELATION_KINDS,
    FieldClock,
    ResourceKey,
    _parse_canonical_json,
    canonical,
    validate_mapping_provenance,
    validate_mapping_target,
)
from repo_catalog.domain.parent_report import validate_parent_report
from repo_catalog.domain.time import validate_observation_us

ERRORS = (ValueError, TypeError, OverflowError, RecursionError, KeyError, IndexError)


def validate_event(service, kind, identity, members, provenance, scope, observed):
    ResourceKey(service, kind, identity)
    validate_mapping_provenance(provenance)
    validate_observation_us(observed)
    values = _parse_canonical_json(members)
    details = _parse_canonical_json(scope)
    if kind != "comment" or type(values) is not list or type(details) is not dict:
        raise ValueError("typed Event report required")
    if set(details) != {
        "clock",
        "event_type",
        "from_provider_repository_id",
        "to_provider_repository_id",
        "provided_roles",
        "endpoints",
        "parent_members_json",
        "parent_scope_json",
        "parent_provenance_json",
    }:
        raise ValueError("complete original Event scope required")
    FieldClock.from_json(canonical(details["clock"]))
    # Actual event meaning ('transferred') is an I5 Admission obligation.
    if type(details["event_type"]) is not str or not details["event_type"]:
        raise ValueError("original Event type must be nonempty text")
    parent, subtype = validate_parent_report(
        service,
        kind,
        identity,
        details["parent_members_json"],
        details["parent_provenance_json"],
        details["parent_scope_json"],
        None,
    )
    if parent.resource_kind != "issue" or subtype != "timeline_event":
        raise ValueError("Timeline Event Issue support required")
    endpoints = details["endpoints"]
    if type(endpoints) is not list:
        raise ValueError("original endpoint declarations required")
    seen = set()
    for endpoint in endpoints:
        if (
            type(endpoint) is not list
            or len(endpoint) != 2
            or type(endpoint[0]) is not str
            or endpoint[0] not in TRANSFER_RELATION_KINDS
        ):
            raise ValueError("invalid endpoint declaration")
        validate_mapping_target(endpoint[1])
        pair = tuple(endpoint)
        if pair in seen:
            raise ValueError("duplicate endpoint declaration")
        seen.add(pair)
    if endpoints != [list(pair) for pair in sorted(seen)]:
        raise ValueError("endpoint declarations must be canonically ordered")
    expected = []
    roles = {entry[0] for entry in endpoints}
    for prefix in ("from", "to"):
        native = details[f"{prefix}_provider_repository_id"]
        role = f"transfer_{prefix}_repository"
        if native is not None:
            key = ResourceKey(service, "repository", native)
            if (role, "null") in seen:
                raise ValueError("explicit null conflicts with Provider endpoint")
            roles.add(role)
            if list(key.coordinates()) not in expected:
                expected.append(list(key.coordinates()))
        elif any(
            endpoint_role == role and target != "null" for endpoint_role, target in seen
        ):
            raise ValueError(
                "resolved endpoint requires its original Provider Repository"
            )
    if values != expected or details["provided_roles"] != sorted(roles) or not roles:
        raise ValueError("incoherent original Event members/roles")


def event_sql(*args):
    """Total bounded predicate, including canonical nested support strings."""
    try:
        validate_event(*args)
        return 1
    except ERRORS:
        return 0


def value_sql(scope, name):
    """Bounded total generated projection; SQL separately requires non-NULL."""
    try:
        details = _parse_canonical_json(scope)
        if name in ("parent_service", "parent_kind", "parent_id"):
            member = _parse_canonical_json(details["parent_members_json"])[0]
            value = member[("parent_service", "parent_kind", "parent_id").index(name)]
        else:
            value = details[name]
        return value if type(value) is str or value is None else canonical(value)
    except ERRORS:
        return None


def endpoint_sql(role, target, scope, clock):
    try:
        details = _parse_canonical_json(scope)
        return int(
            details["clock"] == _parse_canonical_json(clock)
            and [role, target] in details["endpoints"]
        )
    except ERRORS:
        return 0
