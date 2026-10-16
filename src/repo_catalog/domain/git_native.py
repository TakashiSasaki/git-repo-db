"""Lossless native Git metadata grammar for both storage object formats.

This decoder validates structure, never graph closure or signature authenticity.
Header and message strings use reversible UTF-8/surrogateescape; header_data also
contains the exact header bytes in hexadecimal. Unknown extension headers and
folded signature/mergetag headers are preserved. Structural headers have fixed
positions and cardinality. Tree names are raw bytes, ordered by Git's basename
comparison (directories compare with a trailing slash).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from repo_catalog.domain.p1_core import OID, CoreFailure, _performed, encode

DECODER = "git-native"
DECODER_VERSION = "1"


def text(raw: bytes) -> str:
    return raw.decode("utf-8", "surrogateescape")


def _fail(kind: str, message: str) -> None:
    raise CoreFailure("NATIVE_SYNTAX", kind, message)


def headers(body: bytes, kind: str) -> tuple[list[tuple[bytes, bytes]], bytes, bytes]:
    raw, separator, message = body.partition(b"\n\n")
    if not separator or b"\0" in body:
        _fail(kind, "native metadata requires a blank separator and no NUL")
    fields: list[tuple[bytes, list[bytes]]] = []
    # Do not split all lines before accounting. An untrusted header containing
    # millions of tiny lines must stop at its finite metadata allowance before
    # allocating the corresponding list and byte strings.
    offset = 0
    while offset <= len(raw):
        _performed("metadata_units", 1)
        end = raw.find(b"\n", offset)
        if end < 0:
            end = len(raw)
        line = raw[offset:end]
        offset = end + 1
        if line.startswith(b" "):
            if not fields:
                _fail(kind, "orphan native header continuation")
            fields[-1][1].append(line)
            continue
        key, space, value = line.partition(b" ")
        if not space or re.fullmatch(rb"[A-Za-z0-9-]+", key) is None:
            _fail(kind, "malformed native header")
        fields.append((key, [value]))
    # Join each folded value once: repeated bytes concatenation is quadratic
    # for large signatures and is amplified by independent SQL guard checks.
    return [(key, b"\n".join(parts)) for key, parts in fields], raw, message


def _oid(fmt: str, raw: bytes, kind: str) -> OID:
    try:
        result = OID(fmt, raw.decode("ascii"))
        if not any(char != "0" for char in result.full_oid):
            _fail(kind, "null native object reference")
        return result
    except (UnicodeError, CoreFailure) as error:
        raise CoreFailure(
            "NATIVE_SYNTAX", kind, "invalid native object reference"
        ) from error


def identity(raw: bytes, kind: str) -> tuple[str, str, int]:
    match = re.fullmatch(rb"([^<>\n\0]*) <([^<>\n\0]*)> (-?[0-9]+) ([+-][0-9]{4})", raw)
    if match is None:
        _fail(kind, "malformed native identity/time/timezone")
    name, email, seconds, zone = match.groups()
    if int(zone[1:3]) > 23 or int(zone[3:]) > 59:
        _fail(kind, "unsupported native timezone outside HHMM range")
    # Bound before int(): Python's digit guard and pathological conversions must
    # never escape this typed parser boundary.
    if len(seconds.lstrip(b"-0")) > 13 or len(seconds) > 32:
        _fail(kind, "native timestamp exceeds supported signed int64 microseconds")
    micros = int(seconds) * 1_000_000
    if not -(2**63) <= micros < 2**63:
        _fail(kind, "native timestamp exceeds signed int64 microseconds")
    return text(name), text(email), micros


@dataclass(frozen=True)
class Metadata:
    """Decoded facts; all identities remain the original P1 OID values."""

    scalars: dict[str, object]
    relations: dict[str, list]


def _base(kind: str, body: bytes, raw_headers: bytes | None = None) -> dict:
    result = {"type": kind, "size": len(body)}
    if raw_headers is not None:
        result.update(
            header_data=raw_headers.hex(),
            decoder_settings=encode(
                {"text": "utf-8/surrogateescape", "headers": "hex"}
            ),
        )
    return result


def parse_commit(fmt: str, body: bytes) -> Metadata:
    fields, raw_headers, message = headers(body, "commit")
    if not fields or fields[0][0] != b"tree":
        _fail("commit", "tree must be the first native commit header")
    tree = _oid(fmt, fields[0][1], "commit")
    index, parents = 1, []
    while index < len(fields) and fields[index][0] == b"parent":
        parents.append([len(parents), *_oid(fmt, fields[index][1], "commit").key])
        index += 1
    if [key for key, _ in fields[index : index + 2]] != [b"author", b"committer"]:
        _fail("commit", "native author and committer headers required after parents")
    author, committer = fields[index][1], fields[index + 1][1]
    extra = fields[index + 2 :]
    if any(key in (b"tree", b"parent", b"author", b"committer") for key, _ in extra):
        _fail("commit", "repeated or misplaced native structural header")
    encodings = [value for key, value in extra if key == b"encoding"]
    if len(encodings) > 1 or any(not value or b"\n" in value for value in encodings):
        _fail("commit", "one nonempty single-line encoding header supported")
    scalars = _base("commit", body, raw_headers)
    scalars.update(
        message=text(message),
        author=text(author),
        committer=text(committer),
        parent_count=len(parents),
    )
    for role, value in (("author", author), ("committer", committer)):
        name, email, at = identity(value, "commit")
        scalars.update(
            {role + "_name": name, role + "_email": email, role + "_time_us": at}
        )
    if encodings:
        scalars["encoding"] = text(encodings[0])
    return Metadata(
        scalars, {"commit_tree": [[0, *tree.key]], "commit_parents": parents}
    )


def parse_tree(fmt: str, body: bytes) -> dict[bytes, tuple[bytes, str]]:
    width = {"sha1": 20, "sha256": 32}.get(fmt)
    if width is None:
        _fail("tree", "unsupported native object format")
    result, offset, previous = {}, 0, None
    while offset < len(body):
        _performed("metadata_units", 1)
        space, zero = body.find(b" ", offset), body.find(b"\0", offset)
        if space < offset or zero <= space or zero + 1 + width > len(body):
            _fail("tree", "truncated native tree entry")
        mode, name = body[offset:space], body[space + 1 : zero]
        if mode not in (b"40000", b"100644", b"100755", b"120000", b"160000"):
            _fail("tree", "unsupported native tree mode")
        if not name or b"/" in name or name in (b".", b"..") or name in result:
            _fail("tree", "invalid or duplicate native tree name")
        order = name + (b"/" if mode == b"40000" else b"\0")
        if previous is not None and order <= previous:
            _fail("tree", "native tree entries are not in Git basename order")
        end = zero + 1 + width
        target = body[zero + 1 : end].hex()
        _oid(fmt, target.encode("ascii"), "tree")
        result[name] = mode, target
        previous, offset = order, end
    return result


def parse_tag(fmt: str, body: bytes) -> Metadata:
    fields, raw_headers, message = headers(body, "tag")
    if [key for key, _ in fields[:3]] != [b"object", b"type", b"tag"]:
        _fail("tag", "native object/type/tag header order required")
    target = _oid(fmt, fields[0][1], "tag")
    if fields[1][1] not in (b"commit", b"tree", b"tag", b"blob"):
        _fail("tag", "invalid native tag target type")
    if not fields[2][1] or b"\n" in fields[2][1]:
        _fail("tag", "nonempty single-line native tag name required")
    extras = fields[3:]
    if any(key in (b"object", b"type", b"tag") for key, _ in extras):
        _fail("tag", "repeated native tag structural header")
    taggers = [value for key, value in extras if key == b"tagger"]
    if len(taggers) > 1 or (taggers and extras[0][0] != b"tagger"):
        _fail("tag", "one native tagger immediately after tag header is supported")
    scalars = _base("tag", body, raw_headers)
    scalars.update(message=text(message), tag_name=text(fields[2][1]))
    if taggers:
        identity(taggers[0], "tag")
        scalars["tagger"] = text(taggers[0])
    return Metadata(scalars, {"tag_target": [[0, *target.key]]})


def parse_metadata(fmt: str, kind: str, body: bytes) -> Metadata:
    """Check a whole native metadata representation, without reading children."""
    if type(body) is not bytes:
        _fail(kind, "exact bytes required")
    if kind == "commit":
        return parse_commit(fmt, body)
    if kind == "tag":
        return parse_tag(fmt, body)
    if kind == "tree":
        entries = parse_tree(fmt, body)
        scalars = _base(kind, body)
        scalars["tree_count"] = len(entries)
        return Metadata(
            scalars,
            {
                "tree_entries": [
                    [[mode.decode("ascii"), name.hex()], fmt, target]
                    for name, (mode, target) in entries.items()
                ]
            },
        )
    raise CoreFailure(
        "RETENTION_PURPOSE", kind, "only native commit/tree/tag metadata is supported"
    )
