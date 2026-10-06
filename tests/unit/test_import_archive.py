"""Exact typed preservation primitives used by the packaged v2 importer."""

import sqlite3
import struct

import pytest

from repo_catalog.adapters.import_v2.archive import decode_key, rows
from repo_catalog.adapters.import_v2.common import ConversionError
from repo_catalog.adapters.import_v2.types import archive_bytes, row_digest, tagged_key


def test_typed_keys_and_rows_preserve_type_names_and_boundaries():
    values = [
        ("null", None),
        ("integer", 1),
        ("real", 1.0),
        ("text", b"1"),
        ("blob", b"1"),
    ]
    assert len({tagged_key([value]) for value in values}) == len(values)
    for value in values:
        assert decode_key(tagged_key([value])) == [value]
    assert tagged_key([("text", b"a"), ("text", b"bc")]) != tagged_key(
        [("text", b"ab"), ("text", b"c")]
    )
    assert row_digest([("a", "text", b"1")]) != row_digest([("b", "text", b"1")])
    assert row_digest([("a", "text", b"1")]) != row_digest([("a", "blob", b"1")])
    with pytest.raises(ConversionError):
        decode_key(b"I" + (2).to_bytes(8, "big") + b"01")


@pytest.mark.parametrize("encoding", ["UTF-8", "UTF-16le", "UTF-16be"])
def test_archive_retains_exact_sqlite_storage_bytes_even_malformed_text(encoding):
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.execute(f"PRAGMA encoding='{encoding}'")
        db.execute(
            "CREATE TABLE original(id INTEGER PRIMARY KEY, malformed TEXT, missing TEXT, payload BLOB, amount REAL)"
        )
        db.execute(
            "INSERT INTO original VALUES(-7,CAST(x'fffe00' AS TEXT),NULL,x'00ff',1.25)"
        )
        record = next(rows(db, "original"))
        assert record.key == tagged_key([("integer", -7)])
        assert record.value("malformed") == (
            "text",
            db.execute("SELECT CAST(malformed AS BLOB) FROM original").fetchone()[0],
        )
        assert record.value("missing") == ("null", b"")
        assert record.value("payload") == ("blob", b"\x00\xff")
        assert record.value("amount") == ("real", struct.pack(">d", 1.25))


def test_archive_encoder_rejects_coercion_that_loses_original_storage_type():
    assert archive_bytes("integer", -(2**63)) == b"-9223372036854775808"
    assert archive_bytes("text", b"original\x00bytes") == b"original\x00bytes"
    for kind, invalid in [
        ("integer", True),
        ("integer", 1.0),
        ("real", 1),
        ("text", "decoded"),
        ("null", 0),
    ]:
        with pytest.raises(ValueError):
            archive_bytes(kind, invalid)
