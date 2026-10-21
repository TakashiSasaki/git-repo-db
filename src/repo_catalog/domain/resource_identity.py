"""Strict, bounded canonical Resource identity values (ADR 0031 I1).

Native values and serialized identity TEXT have separate entry points. This
codec neither normalizes Provider IDs nor infers relationships from them.
Only exact ``str`` and ``list`` instances are accepted as native values.

All limits are inclusive: 262,144 bytes of ASCII-escaped canonical JSON,
32 array containers on a path, and 4,096 value nodes (root, arrays and strings).
A scalar root has depth zero; an array root has depth one. A string inside the
32nd array is allowed. Empty strings and arrays each count as one node.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Final, TypeAlias, cast

IdentityValue: TypeAlias = str | list["IdentityValue"]

MAX_IDENTITY_BYTES: Final = 262_144
MAX_IDENTITY_ARRAY_DEPTH: Final = 32
MAX_IDENTITY_NODES: Final = 4_096

_SHORT_ESCAPES: Final = frozenset('"\\\b\f\n\r\t')
_HEX_DIGITS: Final = frozenset("0123456789abcdefABCDEF")


def _validate_native(value: IdentityValue) -> None:
    """Validate before library serialization, using O(array depth) frames.

    Count the exact escaped output size without allocating escaped strings or
    pushing all siblings onto a work stack. Native cycles fail the finite depth
    limit, and oversized lists fail before even traversing their children.
    """
    stack: list[tuple[Iterator[IdentityValue], int]] = [(iter((value,)), 0)]
    nodes = size = 0
    while stack:
        iterator, depth = stack[-1]
        try:
            item = next(iterator)
        except StopIteration:
            stack.pop()
            continue
        nodes += 1
        if nodes > MAX_IDENTITY_NODES:
            raise ValueError("Identity exceeds maximum value node count")
        if type(item) is list:
            array_depth = depth + 1
            if array_depth > MAX_IDENTITY_ARRAY_DEPTH:
                raise ValueError("Identity exceeds maximum array depth")
            if len(item) > MAX_IDENTITY_NODES - nodes:
                raise ValueError("Identity exceeds maximum value node count")
            size += 2 + max(0, len(item) - 1)
            stack.append((iter(item), array_depth))
        elif type(item) is str:
            # Every scalar uses at least one output byte, plus JSON quotes.
            if len(item) + size + 2 > MAX_IDENTITY_BYTES:
                raise ValueError("Identity exceeds maximum canonical byte length")
            size += 2
            for char in item:
                codepoint = ord(char)
                if 0xD800 <= codepoint <= 0xDFFF:
                    raise ValueError("Identity strings require Unicode scalar values")
                if char in _SHORT_ESCAPES:
                    size += 2
                elif codepoint < 0x20 or 0x7F <= codepoint <= 0xFFFF:
                    size += 6
                elif codepoint > 0xFFFF:
                    size += 12
                else:
                    size += 1
                if size > MAX_IDENTITY_BYTES:
                    raise ValueError("Identity exceeds maximum canonical byte length")
        else:
            raise TypeError("Identity values must be exact strings or lists")
        if size > MAX_IDENTITY_BYTES:
            raise ValueError("Identity exceeds maximum canonical byte length")


def encode_identity(value: IdentityValue) -> str:
    """Encode a native identity without coercion, trimming or normalization.

    Raise TypeError for forbidden native types (including str/list subclasses),
    or ValueError for invalid Unicode scalars or an exceeded finite limit.
    Byte accounting includes JSON quotes, brackets, commas and escape expansion.
    """
    _validate_native(value)
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def _scan_string(text: str, index: int) -> int:
    """Scan JSON string syntax without allocating a decoded string."""
    index += 1
    while index < len(text):
        char = text[index]
        index += 1
        if char == '"':
            return index
        if char == "\\":
            if index == len(text):
                break
            escape = text[index]
            index += 1
            if escape == "u":
                if index + 4 > len(text) or any(
                    text[pos] not in _HEX_DIGITS for pos in range(index, index + 4)
                ):
                    raise ValueError("Invalid JSON Unicode escape in identity")
                index += 4
            elif escape not in '"\\/bfnrt':
                raise ValueError("Invalid JSON escape in identity")
        elif ord(char) < 0x20:
            raise ValueError("Unescaped JSON control character in identity")
    raise ValueError("Unterminated JSON identity string")


def _prescan(text: str) -> None:
    """Check the complete restricted grammar and bounds before json.loads.

    This scanner accepts valid alternate JSON escapes for the final canonical
    equality check, but never numbers, objects or other nonidentity tokens.
    Only array depth is retained; no input-proportional token collection exists.
    """
    index = depth = nodes = 0
    while True:
        if index == len(text):
            raise ValueError("Missing JSON identity value")
        char = text[index]
        nodes += 1
        if nodes > MAX_IDENTITY_NODES:
            raise ValueError("Identity exceeds maximum value node count")
        if char == "[":
            index += 1
            depth += 1
            if depth > MAX_IDENTITY_ARRAY_DEPTH:
                raise ValueError("Identity exceeds maximum array depth")
            if index < len(text) and text[index] == "]":
                index += 1
                depth -= 1
            else:
                continue
        elif char == '"':
            index = _scan_string(text, index)
        else:
            raise ValueError("Expected identity string or array")

        # A completed value may finish multiple enclosing arrays.
        while True:
            if depth == 0:
                if index != len(text):
                    raise ValueError("Trailing data after JSON identity")
                return
            if index == len(text):
                raise ValueError("Unterminated JSON identity array")
            char = text[index]
            index += 1
            if char == ",":
                break
            if char != "]":
                raise ValueError("Expected comma or closing identity array bracket")
            depth -= 1


def parse_identity(text: str) -> IdentityValue:
    """Parse already serialized canonical identity TEXT without repairing it.

    Only exact str TEXT is accepted; byte buffers, including invalid UTF-8, are
    rejected as TypeError. Transport decoders must independently use strict
    UTF-8. Canonical TEXT is ASCII only: raw non-ASCII, BOM and in-memory
    surrogates are rejected before JSON decoding. Malformed, noncanonical or
    over-limit TEXT raises ValueError. Returned arrays are fresh native lists.
    """
    if type(text) is not str:
        raise TypeError("Serialized identity must be exact string TEXT")
    if not text or len(text) > MAX_IDENTITY_BYTES:
        raise ValueError("Identity requires bounded nonempty canonical TEXT")
    if not text.isascii():
        raise ValueError("Canonical identity TEXT must contain only ASCII")
    _prescan(text)
    value = cast(IdentityValue, json.loads(text))
    if encode_identity(value) != text:
        raise ValueError("Identity TEXT is not canonical")
    return value
