"""Pure Source Git membership coordinates, independent of endpoint existence."""

import json

from repo_catalog.domain.shared_values import encode, uuid4_value


class DuplicateSourceInventoryMember(ValueError):
    pass


def validate_source_inventory_members(members):
    if type(members) not in (tuple, list):
        raise ValueError("Source Git members require an explicit sequence")
    for member in members:
        uuid4_value(member)
    if len(set(members)) != len(members):
        raise DuplicateSourceInventoryMember(
            "Source Git members must have unique UUID4 coordinates"
        )


def source_inventory_members_sql(encoded):
    try:
        if type(encoded) is not str:
            return 0
        members = json.loads(encoded)
        if type(members) is not list:
            return 0
        validate_source_inventory_members(members)
        return int(encode(sorted(members)) == encoded)
    except (ValueError, TypeError, RecursionError, OverflowError):
        return 0
