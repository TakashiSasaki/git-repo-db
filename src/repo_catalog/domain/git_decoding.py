"""Supported Git decoding primitives, independent of producer authority."""

import hashlib
import json

from repo_catalog.domain.git_intrinsic import commit_structure
from repo_catalog.domain.models import CatalogError

DECODER_FIELDS = (
    "parser_module",
    "parser_version",
    "text_encoding",
    "metadata_encoding",
    "metadata_errors",
    "max_text_blob_bytes",
)


def decoder_settings(settings, key):
    """Bind a decoder's attribution and concrete settings to its own key."""
    if (
        not isinstance(settings, dict)
        or set(settings) != set(DECODER_FIELDS)
        or any(
            not isinstance(settings[field], str)
            or not settings[field]
            or "\0" in settings[field]
            for field in ("parser_module", "parser_version")
        )
        or settings["text_encoding"] not in ("utf-8", "latin-1")
        or settings["metadata_encoding"] not in ("utf-8", "latin-1")
        or settings["metadata_errors"] not in ("strict", "replace", "backslashreplace")
        or type(settings["max_text_blob_bytes"]) is not int
        or settings["max_text_blob_bytes"] < 0
    ):
        raise CatalogError("GIT_DECODER_FACT", "Unsupported concrete Git decoder")
    expected = hashlib.sha256(
        json.dumps(settings, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if key != expected:
        raise CatalogError(
            "GIT_DECODER_FACT", "Decoder key contradicts concrete settings"
        )
    return settings


def decode_blob(data, encoding, limit):
    if len(data) > limit:
        return "oversize", None
    try:
        value = data.decode(encoding, "strict")
    except UnicodeError:
        return "non_utf8", None
    return ("nul", None) if "\0" in value else ("eligible", value)


def decode_commit(object_format, body, settings):
    structure = commit_structure(object_format, body)

    def decode(value):
        return value.decode(settings["metadata_encoding"], settings["metadata_errors"])

    return decode(structure["raw_message"]), {
        key.decode("ascii", "backslashreplace"): decode(value)
        for key, value in structure["metadata_entries"]
    }


def validate_decoded_value(family, fmt, body, key, settings, subject, value, metadata):
    """Compare a claimed value with actual supported byte decoding.

    The name subject is a raw entry name. Its exact canonical tree-entry owner
    is checked by the SQLite adapter, rather than reparsing a whole tree for
    every name. Producer names and versions are attribution, never a ranking.
    """
    decoder_settings(settings, key)
    if family == "text":
        actual = decode_blob(
            body, settings["text_encoding"], settings["max_text_blob_bytes"]
        )
        valid = (subject, value) == actual
    elif family == "commit":
        message, headers = decode_commit(fmt, body, settings)
        valid = value == message and json.loads(metadata) == headers
    elif family == "name":
        valid = value == subject.decode(
            settings["metadata_encoding"], settings["metadata_errors"]
        )
    else:
        valid = False
    if not valid:
        raise CatalogError(
            "GIT_DECODER_FACT", "Claimed Git value contradicts raw bytes"
        )
