"""Explicit ASCII wire variant for Git's reversible surrogateescape scalars.

Only Repository scalar claims use this grammar. Context text and ordinary package JSON
retain strict UTF-8 validation. The tag is representation, never verification.
"""

import json

from repo_catalog.domain.exchange import ExchangeError, _parse_json
from repo_catalog.domain.p1_repository import encode

SCALAR_ENCODING = "git-surrogateescape-json-v1"


def _escaped(value):
    if type(value) is str:
        return any(0xD800 <= ord(character) <= 0xDFFF for character in value)
    if isinstance(value, list):
        return any(_escaped(item) for item in value)
    if isinstance(value, dict):
        return any(_escaped(key) or _escaped(item) for key, item in value.items())
    return False


def scalar_value_json(row):
    """Recover exactly the original canonical ScalarClaim value JSON text."""
    if "value_encoding" not in row and "value_ascii" not in row:
        return row["value_json"]
    value = row.get("value_ascii")
    if (
        row.get("value_encoding") != SCALAR_ENCODING
        or "value_json" in row
        or type(value) is not str
        or not value.isascii()
    ):
        raise ExchangeError("INVALID_SCALAR_ENCODING", "scalar_claims")
    decoded = _parse_json(value)
    if (
        type(decoded) is not list
        or len(decoded) != 2
        or decoded[0] != "known"
        or type(decoded[1]) is not str
        or encode(decoded) != value
    ):
        raise ExchangeError("INVALID_SCALAR_ENCODING", "scalar_claims")
    text = decoded[1]
    if not _escaped(text) or any(
        0xD800 <= ord(character) <= 0xDFFF and not 0xDC80 <= ord(character) <= 0xDCFF
        for character in text
    ):
        raise ExchangeError("INVALID_SCALAR_ENCODING", "scalar_claims")
    return value


def encode_scalar_row(row):
    """Use one canonical representation for each supported scalar value."""
    value = row["value_json"]
    if not _escaped(json.loads(value)):
        return row
    variant = {key: entry for key, entry in row.items() if key != "value_json"}
    variant.update(value_encoding=SCALAR_ENCODING, value_ascii=value)
    scalar_value_json(variant)
    return variant
