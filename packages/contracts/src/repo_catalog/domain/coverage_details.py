"""Coverage advisory metadata: closed domain descriptions, never API originals.

Details remain outside claim identity, state selection, trust and completeness
proof. Declared scalar prose is preserved verbatim; no DLP or content decoding is
claimed. Unknown encoded-response/envelope fields have no storage slot here.
"""

from repo_catalog.domain.authored_metadata import (
    parse_authored_object,
    validate_authored_value,
)
from repo_catalog.domain.shared_values import uuid4_value

_TEXT = (str,)
_COUNT = (int,)
_SCHEMA = {
    "reason": _TEXT,
    "detail": _TEXT,
    "advisory": _TEXT,
    "original": (bool,),
    "missing": [{"kind": _TEXT, "reason": _TEXT, "role": _TEXT, "roles": [_TEXT]}],
    "capture_origin_uuidv4": _TEXT,
    "capture_uuidv4": _TEXT,
    "retained_count": _COUNT,
    "metadata_only_count": _COUNT,
    "nominal_missing_count": _COUNT,
    "refs_checked": _COUNT,
}


def validate_coverage_details(encoded: str | None) -> dict | None:
    if encoded is None:
        return None
    details = parse_authored_object(encoded)
    validate_authored_value(_SCHEMA, details)
    for name in ("capture_origin_uuidv4", "capture_uuidv4"):
        if details.get(name) is not None:
            uuid4_value(details[name])
    for name in (
        "retained_count",
        "metadata_only_count",
        "nominal_missing_count",
        "refs_checked",
    ):
        if details.get(name) is not None and not 0 <= details[name] < 2**63:
            raise ValueError("Coverage advisory count must be nonnegative int64")
    return details


def coverage_details_sql(encoded) -> int:
    """SQLite defense shares the exact pre-affinity Python admission grammar."""
    try:
        validate_coverage_details(encoded)
        return 1
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        return 0
