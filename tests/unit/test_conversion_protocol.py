import ctypes

import pytest

from scripts.conversion import archive, common, engine, source
from scripts.schema_contract import tagged_key
from tests.support.conversion_fixture import make_source


@pytest.mark.parametrize(
    "key",
    [
        b"",
        b"T",
        b"T" + (999).to_bytes(8, "big"),
        b"N" + (1).to_bytes(8, "big") + b"x",
        b"I" + (2).to_bytes(8, "big") + b"+1",
        b"X" + bytes(8),
    ],
)
def test_noncanonical_target_keys_rejected(key):
    with pytest.raises(common.ConversionError, match="INVALID_TARGET_KEY"):
        archive.decode_key(key)


def test_tlv_inverse_keeps_boundaries_types_and_pk_order():
    values = [
        ("null", None),
        ("text", b""),
        ("blob", b"\x00\xff"),
        ("integer", -(2**63)),
        ("real", 1.25),
    ]
    assert archive.decode_key(tagged_key(values)) == values


def test_guarded_entry_refuses_missing_policy(tmp_path):
    with pytest.raises(common.ConversionError, match="GUARDED_WORKER_REQUIRED"):
        engine.run(None, "archive", tmp_path)


def test_remote_filesystem_is_blocking(tmp_path, monkeypatch):
    class RemoteFS:
        def statfs(self, path, buffer):
            ctypes.c_ulong.from_buffer(buffer).value = 0x6969  # NFS
            return 0

    monkeypatch.setattr(common.ctypes, "CDLL", lambda _: RemoteFS())
    with pytest.raises(common.ConversionError, match="NONLOCAL_OR_UNSUPPORTED"):
        common.require_local_filesystem(tmp_path)


def test_json_constants_are_not_silently_accepted():
    with pytest.raises(ValueError):
        common.strict_json('{"legacy":NaN}')


def test_source_cache_special_files_are_not_read(tmp_path):
    import os

    cache = make_source(tmp_path / "v2.sqlite3")
    os.mkfifo(cache / "pipe")
    with pytest.raises(common.ConversionError, match="CACHE_NOT_REGULAR"):
        source.cache_inventory([cache])
