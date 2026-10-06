"""Exact SQLite values, deterministic PK serialization and bounded batches."""

import struct
from dataclasses import dataclass

from .common import ConversionError, canonical, digest
from .types import archive_bytes, identifier, row_digest, tagged_key


@dataclass(frozen=True)
class Record:
    table: str
    key: bytes
    row_sha256: bytes
    values: tuple  # schema order: (column name, storage type, exact encoded bytes)

    def value(self, name):
        return next((kind, raw) for column, kind, raw in self.values if column == name)


def rows(db, table):
    columns = list(db.execute(f"PRAGMA table_xinfo({identifier(table)})"))
    primary = sorted((c for c in columns if c["pk"]), key=lambda c: c["pk"])
    if not primary or any(c["hidden"] for c in columns):
        raise ConversionError("UNSUPPORTED_SOURCE_KEY")
    names = [c["name"] for c in columns]
    expressions = []
    for name in names:
        quoted = identifier(name)
        expressions += [
            f"typeof({quoted})",
            f"CASE WHEN typeof({quoted}) IN ('text','blob') THEN CAST({quoted} AS BLOB) ELSE {quoted} END",
        ]
    order = ",".join(identifier(c["name"]) for c in primary)
    for row in db.execute(
        f"SELECT {','.join(expressions)} FROM {identifier(table)} ORDER BY {order}"
    ):
        raw = [(name, row[i * 2], row[i * 2 + 1]) for i, name in enumerate(names)]
        by_name = {name: (kind, value) for name, kind, value in raw}
        yield Record(
            table,
            tagged_key([by_name[c["name"]] for c in primary]),
            row_digest(raw),
            tuple(
                (name, kind, archive_bytes(kind, value)) for name, kind, value in raw
            ),
        )


def batches(db, tables, size):
    if size < 1:
        raise ConversionError("INVALID_BATCH_SIZE")
    for table in sorted(tables):
        index, pending = 0, []
        for record in rows(db, table):
            pending.append(record)
            if len(pending) == size:
                yield table, index, tuple(pending)
                index += 1
                pending = []
        if pending or index == 0:
            yield table, index, tuple(pending)


def input_manifest(source_sha256, table, index, records):
    value = {
        "source_sha256": source_sha256,
        "table": table,
        "index": index,
        "rows": [{"key": r.key.hex(), "sha256": r.row_sha256.hex()} for r in records],
    }
    return digest(canonical(value).encode())


def decode_key(data):
    """Inverse P1 TLV for target lookup; reject noncanonical/malformed keys."""
    result, offset = [], 0
    tags = {b"N": "null", b"I": "integer", b"R": "real", b"T": "text", b"B": "blob"}
    try:
        while offset < len(data):
            if len(data) - offset < 9:
                raise ValueError()
            kind = tags[data[offset : offset + 1]]
            length = int.from_bytes(data[offset + 1 : offset + 9], "big")
            offset += 9
            if length > len(data) - offset:
                raise ValueError()
            raw = data[offset : offset + length]
            offset += length
            if kind == "integer":
                value = int(raw.decode("ascii"))
            elif kind == "real":
                value = struct.unpack(">d", raw)[0]
            elif kind == "null":
                if raw:
                    raise ValueError()
                value = None
            else:
                value = raw
            result.append((kind, value))
        if not result or tagged_key(result) != data:
            raise ValueError()
        return result
    except (KeyError, ValueError, UnicodeError, struct.error):
        raise ConversionError("INVALID_TARGET_KEY") from None
