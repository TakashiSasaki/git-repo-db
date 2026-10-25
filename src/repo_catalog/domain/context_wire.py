"""Pure ADR 0031 v5 Context codec; decoding never grants admission authority.

All row profiles and semantic types are shared with the product domain. Ordinary
Provider/Exchange routes and both Transfer SQL fences remain independently gated.
"""

from __future__ import annotations

import copy
import json

from repo_catalog.domain.context_registration import (
    RegistrationError,
    validate_exchange_registrations,
)
from repo_catalog.domain.exchange import (
    CONTEXT_SECTION_KEYS,
    MAX_PACKAGE_BYTES,
    ExchangeError,
    _bounded_json,
    _parse_json,
)
from repo_catalog.domain.exchange_rows import validate_replay_consistency, validate_rows


def decode_context_v5(raw: str | bytes | dict) -> dict:
    """Return validated lossless v5 Context rows without changing any originals.

    This is the explicitly versioned Context section codec. Full untrusted wire
    envelopes must enter through ``decode_package`` to verify version and digest.
    It cannot supply missing Parent originals or endpoint declarations from Event
    clocks, surviving rows, or arrival order.
    """
    if type(raw) in (str, bytes):
        if len(raw) > MAX_PACKAGE_BYTES:
            raise ExchangeError("INPUT_LIMIT", "context", "wire bytes")
        try:
            text = raw.decode("utf-8") if type(raw) is bytes else raw
            if len(text.encode("utf-8")) > MAX_PACKAGE_BYTES:
                raise ExchangeError("INPUT_LIMIT", "context", "UTF-8 wire bytes")
        except UnicodeError as error:
            raise ExchangeError("MALFORMED_JSON", "context", "invalid UTF-8") from error
        data = _parse_json(text)
    elif type(raw) is dict:
        data = raw
    else:
        raise ExchangeError("MALFORMED_CONTEXT_SECTION", "context", "object required")
    _bounded_json(data, root="context")
    if type(data) is not dict or set(data) != set(CONTEXT_SECTION_KEYS):
        raise ExchangeError(
            "MALFORMED_CONTEXT_SECTION", "context", "exact sections required"
        )
    if any(
        type(rows) is not list or any(type(row) is not dict for row in rows)
        for rows in data.values()
    ):
        raise ExchangeError(
            "MALFORMED_CONTEXT_SECTION", "context", "row arrays required"
        )
    try:
        validate_rows(None, data)
        validate_exchange_registrations(data)
        validate_replay_consistency(None, data)
        from repo_catalog.domain.selective_exchange import validate_context

        validate_context(data)
    except ExchangeError:
        raise
    except RegistrationError as error:
        raise ExchangeError("CONTEXT_REGISTRATION", error.kind, error.code) from None
    except (ValueError, TypeError, KeyError, IndexError) as error:
        code = getattr(error, "code", "INVALID_CONTEXT")
        raise ExchangeError(code, "context", "invalid typed Context unit") from error
    return copy.deepcopy(data)


def encode_context_v5(data: dict) -> str:
    """Encode exact validated Context rows using the outer canonical JSON profile."""
    decoded = decode_context_v5(data)
    result = json.dumps(
        decoded,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    if len(result.encode("utf-8")) > MAX_PACKAGE_BYTES:
        raise ExchangeError("INPUT_LIMIT", "context", "UTF-8 wire bytes")
    return result
