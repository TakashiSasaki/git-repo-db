"""Exact PR listing acquisition scope; source data, never execution settings."""

from repo_catalog.domain.p1_context import canonical
from repo_catalog.domain.p1_repository import OID
from repo_catalog.domain.production_context import json_value
from repo_catalog.domain.ref_observation import RefObservationKey


def anchored_code_scope(
    scope,
    *,
    head,
    base,
    anchor_provenance_json,
    member_provenance_jsons,
    expected_count=None,
):
    """Describe actual acquisition inputs, never infer an anchor during query."""
    if (
        type(scope) is not dict
        or type(head) is not OID
        or type(base) is not OID
        or head.object_format != base.object_format
    ):
        raise ValueError("same-format actual head/base OIDs required")
    json_value(anchor_provenance_json, provenance=True)
    originals = tuple(member_provenance_jsons)
    if len(originals) > 10000:
        raise ValueError("finite page provenance set required")
    for original in originals:
        json_value(original, provenance=True)
    result = {
        **scope,
        "head_object_oid": list(head.key),
        "base_object_oid": list(base.key),
        "anchor_provenance_json": anchor_provenance_json,
        "member_provenance_jsons": sorted(set(originals)),
    }
    if expected_count is not None:
        if type(expected_count) is not int or not 0 <= expected_count <= 100_000_000:
            raise ValueError("actual nonnegative reported count required")
        result["expected_count"] = expected_count
    encoded = canonical(result)
    json_value(encoded)
    return encoded


def decode_git_role_checks(scope):
    """Validate finite reported native checks; this does not verify Repository facts."""
    checks = scope.get("role_checks") if type(scope) is dict else None
    if type(checks) is not list or not 0 < len(checks) <= 10000:
        raise ValueError("finite nonempty actual role checks required")
    result, seen = [], set()
    for check in checks:
        if type(check) is not dict or set(check) != {
            "role",
            "expected_oid",
            "ref_name_hex",
            "actual_oid",
            "ref_observation_key",
        }:
            raise ValueError("exact actual role check fields required")
        role = check["role"]
        if type(role) is not str or not role or len(role) > 16384:
            raise ValueError("bounded role required")
        expected = check["expected_oid"]
        if type(expected) is not list or len(expected) != 2:
            raise ValueError("typed expected OID required")
        expected = OID(*expected)
        actual = check["actual_oid"]
        if actual is not None:
            if type(actual) is not list or len(actual) != 2:
                raise ValueError("typed actual OID required")
            actual = OID(*actual)
            if actual.object_format != expected.object_format:
                raise ValueError("same-format role target required")
        name = check["ref_name_hex"]
        if type(name) is not str or not 0 < len(name) <= 32768:
            raise ValueError("bounded lossless ref name required")
        raw = bytes.fromhex(name)
        if raw.hex() != name or not raw.startswith(b"refs/") or b"\0" in raw:
            raise ValueError("canonical lossless ref name required")
        key = check["ref_observation_key"]
        if type(key) is not list or len(key) != 2:
            raise ValueError("actual native ref observation key required")
        key = RefObservationKey(*key)
        coordinate = (role, *key.key)
        if coordinate in seen:
            raise ValueError("duplicate role check occurrence")
        seen.add(coordinate)
        result.append(
            {
                "role": role,
                "expected_oid": list(expected.key),
                "actual_oid": list(actual.key) if actual else None,
                "ref_name_hex": name,
                "ref_observation_key": list(key.key),
            }
        )
    return tuple(
        sorted(result, key=lambda check: (check["role"], check["ref_observation_key"]))
    )


def git_role_check_scope(scope, *, head, base, anchor_provenance_json, role_checks):
    """Describe real native ref checks alongside the exact original API anchor."""
    if type(scope) is not dict or type(head) is not OID:
        raise ValueError("typed comparison scope required")
    result = {**scope, "coverage_kind": "git_role_checks", "role_checks": role_checks}
    result["role_checks"] = list(decode_git_role_checks(result))
    if any(
        check["expected_oid"][0] != head.object_format
        for check in result["role_checks"]
    ):
        raise ValueError("same-format comparison checks required")
    return anchored_code_scope(
        result,
        head=head,
        base=base,
        anchor_provenance_json=anchor_provenance_json,
        member_provenance_jsons=[],
    )
