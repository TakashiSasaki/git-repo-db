"""Bounded closed authored JSON shapes, independent of storage and transports.

This is the existing authored-metadata grammar: objects have declared fields,
arrays have one element shape, scalar slots never accept an object/envelope.
Text is descriptive domain text; it is not inspected or decoded as a payload.
"""

from __future__ import annotations

import json

MAX_AUTHORED_BYTES = 1024 * 1024
MAX_AUTHORED_DEPTH = 12
MAX_AUTHORED_ELEMENTS = 4096


def parse_authored_object(encoded: str) -> dict:
    """Preserve exact canonical JSON after bounded structural/type checks."""
    if type(encoded) is not str:
        raise TypeError("Authored metadata requires JSON text")
    if (
        len(encoded) > MAX_AUTHORED_BYTES
        or len(encoded.encode("utf-8")) > MAX_AUTHORED_BYTES
    ):
        raise ValueError("Authored metadata exceeds finite byte limit")
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
            if depth > MAX_AUTHORED_DEPTH:
                raise ValueError("Authored metadata exceeds finite depth limit")
        elif char in "]}":
            depth -= 1

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate authored metadata key")
            result[key] = value
        return result

    def constant(_value):
        raise ValueError("Nonfinite authored metadata value")

    data = json.loads(encoded, object_pairs_hook=unique, parse_constant=constant)
    if type(data) is not dict:
        raise ValueError("Authored metadata requires a JSON object")
    pending, count = [data], 0
    while pending:
        item = pending.pop()
        count += 1
        if count > MAX_AUTHORED_ELEMENTS:
            raise ValueError("Authored metadata exceeds finite element limit")
        if type(item) is dict:
            pending.extend(item)
            pending.extend(item.values())
        elif type(item) is list:
            pending.extend(item)
        elif type(item) is str:
            item.encode("utf-8")
    if (
        json.dumps(
            data,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        != encoded
    ):
        raise ValueError("Authored metadata must be canonical JSON")
    return data


def validate_authored_value(spec, value) -> None:
    """Validate the closed shape without classifying the contents of prose."""
    if value is None:
        return
    if type(spec) is dict:
        if type(value) is not dict or value.keys() - spec.keys():
            raise ValueError("Unknown or malformed authored metadata field")
        for key, item in value.items():
            validate_authored_value(spec[key], item)
    elif type(spec) is list:
        if type(value) is not list:
            raise ValueError("Authored metadata membership requires an array")
        for item in value:
            validate_authored_value(spec[0], item)
    elif type(value) not in spec:
        raise ValueError("Authored metadata has wrong scalar type")
