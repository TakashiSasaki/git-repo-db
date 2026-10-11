"""Canonical Git structure from bytes, shared by writers and computed readers."""

from repo_catalog.domain.models import CatalogError


def _oid(object_format, raw):
    width = 40 if object_format == "sha1" else 64
    if (
        object_format not in ("sha1", "sha256")
        or len(raw) != width
        or any(char not in b"0123456789abcdefABCDEF" for char in raw)
    ):
        raise CatalogError("GIT_OBJECT_STRUCTURE", "Malformed canonical target OID")
    return bytes.fromhex(raw.decode("ascii"))


def _headers(data):
    try:
        headers, message = data.split(b"\n\n", 1)
        entries = []
        offset = 0
        for line in headers.split(b"\n"):
            if not line.startswith(b" "):
                key, value = line.split(b" ", 1)
                entries.append((key, value, offset))
            offset += len(line) + 1
        return headers, message, entries
    except (ValueError, TypeError, AttributeError) as error:
        raise CatalogError(
            "GIT_OBJECT_STRUCTURE", "Malformed Git object headers"
        ) from error


def commit_structure(object_format, data):
    headers, message, entries = _headers(data)
    trees = [(value, offset) for key, value, offset in entries if key == b"tree"]
    if len(trees) != 1:
        raise CatalogError("GIT_OBJECT_STRUCTURE", "Commit requires exactly one tree")
    tree, tree_offset = trees[0]
    parents = [
        {"parent_oid": _oid(object_format, value), "parent_header_offset": offset}
        for key, value, offset in entries
        if key == b"parent"
    ]
    return {
        "tree_oid": _oid(object_format, tree),
        "tree_header_offset": tree_offset,
        "parents": parents,
        "raw_headers": headers,
        "raw_message": message,
        "metadata_entries": [
            (key, value) for key, value, _ in entries if key not in (b"tree", b"parent")
        ],
    }


def tree_structure(object_format, data):
    if object_format not in ("sha1", "sha256") or not isinstance(data, bytes):
        raise CatalogError("GIT_OBJECT_STRUCTURE", "Malformed tree identity")
    offset, entries, names = 0, [], set()
    width = 20 if object_format == "sha1" else 32
    try:
        while offset < len(data):
            space = data.index(b" ", offset)
            end = data.index(b"\0", space)
            raw_mode = data[offset:space]
            mode = int(raw_mode, 8)
            name = data[space + 1 : end]
            child = data[end + 1 : end + 1 + width]
            if (
                raw_mode.strip(b"01234567")
                or not name
                or b"/" in name
                or name in (b".", b"..")
                or name in names
                or len(child) != width
                or mode not in (0o40000, 0o100644, 0o100755, 0o120000, 0o160000)
            ):
                raise CatalogError("GIT_OBJECT_STRUCTURE", "Malformed tree entry")
            names.add(name)
            entries.append(
                {
                    "raw_name": name,
                    "entry_offset": offset,
                    "entry_length": end + 1 + width - offset,
                    "mode": mode,
                    "child_oid": child,
                }
            )
            offset = end + 1 + width
    except (ValueError, TypeError, AttributeError) as error:
        raise CatalogError("GIT_OBJECT_STRUCTURE", "Malformed tree entry") from error
    return entries


def tag_structure(object_format, data):
    _raw_headers, _message, entries = _headers(data)
    # Git's tag identity is the mandatory initial object/type pair. Additional
    # headers cannot redefine it: a dict over all headers would silently let a
    # later "object" line redirect the tag to unrelated, otherwise valid bytes.
    if (
        len(entries) < 2
        or entries[0][0] != b"object"
        or entries[0][2] != 0
        or entries[1][0] != b"type"
        or entries[1][2] != len(b"object ") + len(entries[0][1]) + 1
    ):
        raise CatalogError("GIT_OBJECT_STRUCTURE", "Malformed initial tag target")
    try:
        target = _oid(object_format, entries[0][1])
        typ = entries[1][1].decode("ascii")
    except UnicodeError as error:
        raise CatalogError("GIT_OBJECT_STRUCTURE", "Malformed tag target") from error
    if typ not in ("blob", "commit", "tree", "tag"):
        raise CatalogError("GIT_OBJECT_STRUCTURE", "Malformed tag target type")
    return {"target_oid": target, "target_type": typ}
