"""Typed canonical collection membership, independent of storage and Repository.

Members describe nominal Context resources. They do not certify body retention,
complete enumeration, remote freshness or an optional Repository target's existence.
"""

import json

from repo_catalog.domain.p1_context import ResourceKey, canonical

COLLECTION_CHILD_KINDS = {
    "reviews": "review",
    "comments": "comment",
    "threads": "thread",
    "documents": "document",
}


def validate_collection_members(owner, kind, encoded):
    if type(owner) is not ResourceKey or type(kind) is not str or not kind:
        raise ValueError("Typed collection owner and kind required")
    if type(encoded) is not str:
        raise ValueError("Collection members require canonical JSON text")
    depth = 0
    quoted = escaped = False
    for char in encoded:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 2:
                raise ValueError("Collection members require flat typed triples")
        elif char in "]}":
            depth -= 1
    values = json.loads(encoded)
    if type(values) is not list or canonical(values) != encoded:
        raise ValueError("Collection members require a canonical array")
    seen = set()
    expected_kind = COLLECTION_CHILD_KINDS.get(kind)
    for value in values:
        if (
            type(value) is not list
            or len(value) != 3
            or any(type(x) is not str for x in value)
        ):
            raise ValueError("Collection member requires an exact ResourceKey triple")
        member = ResourceKey(*value)
        if member in seen:
            raise ValueError("Duplicate collection member")
        if expected_kind is not None and (
            member.resource_kind != expected_kind
            or member.service_instance_uuidv4 != owner.service_instance_uuidv4
        ):
            raise ValueError("Collection member kind/service differs from owner")
        seen.add(member)


def collection_members_sql(service, owner_kind, owner_id, kind, encoded):
    try:
        validate_collection_members(
            ResourceKey(service, owner_kind, owner_id), kind, encoded
        )
        return 1
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        return 0
