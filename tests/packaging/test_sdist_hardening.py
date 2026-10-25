"""Independent wire-format regressions for the ADR 0033 archive boundary."""

import gzip
import io
import json
import shutil
import struct
import subprocess
import sys
import tarfile
import zlib
from pathlib import Path

import pytest

from scripts import check_sdist_contract as contract

ROOT = Path(__file__).resolve().parents[2]
SPECIMENS = (
    ROOT
    / "docs/implementation/evidence/adr0033-independent-review-20261023"
    / "archive/counterexamples"
)
DIST = "repo_catalog-0.2.0/"
PKG_INFO = b"Metadata-Version: 2.4\nName: repo-catalog\nVersion: 0.2.0\n\n"
RETAINED_ATTACKS = (
    "pax-hidden-log",
    "concatenated",
    "metadata1",
    "metadata2",
    "corrupt-gzip-crc",
    "missing-gzip-trailer",
    "malformed-second-gzip-member",
)


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    shutil.copytree(SPECIMENS / "source", root)
    return root


def source_members(source):
    """Read the fixture independently of the checker's inventory routine."""
    members = {
        p.relative_to(source).as_posix(): p.read_bytes()
        for p in source.rglob("*")
        if p.is_file()
    }
    return {**members, "PKG-INFO": PKG_INFO}


def tar_bytes(members, *, extra=(), prefix=DIST):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, raw in members.items():
            info = tarfile.TarInfo(prefix + name)
            info.size = len(raw)
            tar.addfile(info, io.BytesIO(raw))
        for info, raw in extra:
            tar.addfile(info, io.BytesIO(raw))
    return stream.getvalue()


def write_archive(tmp_path, raw):
    path = tmp_path / "fixture.tar.gz"
    path.write_bytes(gzip.compress(raw, mtime=0))
    return path


def raw_extension(payload, kind=tarfile.XHDTYPE):
    """Write opaque extension bytes without tarfile repairing their syntax."""
    header = tarfile.TarInfo("PaxHeaders/fixture")
    header.type = kind
    header.size = len(payload)
    return (
        header.tobuf(format=tarfile.USTAR_FORMAT)
        + payload
        + b"\0" * (-len(payload) % 512)
    )


def pax_record(key, value):
    body = f" {key}={value}\n".encode()
    length = len(body) + 1
    while len(str(length)) + len(body) != length:
        length = len(str(length)) + len(body)
    return str(length).encode() + body


@pytest.mark.parametrize("attack", RETAINED_ATTACKS)
def test_all_retained_review_counterexamples_are_rejected(attack):
    with pytest.raises(ValueError):
        contract.check_sdist(SPECIMENS / (attack + ".tar.gz"), SPECIMENS / "source")


@pytest.mark.parametrize("attack", RETAINED_ATTACKS)
def test_retained_attacks_have_nonzero_cli_and_failed_receipt(tmp_path, attack):
    output = tmp_path / "receipt.json"
    result = subprocess.run(
        [
            sys.executable,
            ROOT / "scripts/check_sdist_contract.py",
            "--source-root",
            SPECIMENS / "source",
            "--sdist",
            SPECIMENS / (attack + ".tar.gz"),
            "--output",
            output,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    receipt = json.loads(output.read_text())
    assert receipt["status"] == "failed"
    assert receipt["error"]


@pytest.mark.parametrize(
    "payload",
    [
        pax_record("review.hidden", "small hidden payload"),
        pax_record("mtime", "1"),
        pax_record("mtime", "1" * (1024 * 1024)),
        b"0 path=x\n",
        b"-1 path=x\n",
        b"999999999999999999999999999999 path=x\n",
        b"8 path=unaccounted-tail\n",
        b"12 path=x",  # no terminal newline and declared length exceeds payload
        b"not-a-length path=x\n",
    ],
    ids=[
        "unknown-key",
        "unrequired-timestamp",
        "giant-timestamp",
        "zero-length",
        "negative-length",
        "giant-declared-length",
        "short-declared-length",
        "truncated-record",
        "nonnumeric-length",
    ],
)
@pytest.mark.parametrize("kind", [tarfile.XHDTYPE, tarfile.XGLTYPE])
def test_unapproved_local_and_global_pax_fail(source, tmp_path, payload, kind):
    raw = raw_extension(payload, kind) + tar_bytes(source_members(source))
    with pytest.raises(ValueError):
        contract.check_sdist(write_archive(tmp_path, raw), source)


def test_unapproved_gnu_longname_cannot_hide_raw_header(source, tmp_path):
    raw = raw_extension((DIST + "README.md\0").encode(), tarfile.GNUTYPE_LONGNAME)
    raw += tar_bytes(source_members(source))
    with pytest.raises(ValueError):
        contract.check_sdist(write_archive(tmp_path, raw), source)


@pytest.mark.parametrize("field", ["crc", "isize"])
def test_each_gzip_trailer_field_is_verified(source, tmp_path, field):
    path = write_archive(tmp_path, tar_bytes(source_members(source)))
    raw = bytearray(path.read_bytes())
    raw[-8 if field == "crc" else -4] ^= 1
    path.write_bytes(raw)
    with pytest.raises((gzip.BadGzipFile, zlib.error)):
        gzip.decompress(raw)
    with pytest.raises(ValueError):
        contract.check_sdist(path, source)


@pytest.mark.parametrize("cut", range(1, 10))
def test_gzip_trailer_and_deflate_truncations_fail(source, tmp_path, cut):
    path = write_archive(tmp_path, tar_bytes(source_members(source)))
    path.write_bytes(path.read_bytes()[:-cut])
    with pytest.raises(ValueError):
        contract.check_sdist(path, source)


@pytest.mark.parametrize(
    "tail",
    [b"garbage", b"\0", b"\0" * 512, gzip.compress(b""), gzip.compress(b"\0" * 1024)],
    ids=["garbage", "one-zero", "zero-padding", "empty-gzip", "zero-gzip"],
)
def test_no_uninspected_bytes_after_single_gzip_member(source, tmp_path, tail):
    path = write_archive(tmp_path, tar_bytes(source_members(source)))
    path.write_bytes(path.read_bytes() + tail)
    with pytest.raises(ValueError):
        contract.check_sdist(path, source)


@pytest.mark.parametrize("padding_blocks", [0, 1, 20])
def test_tar_zero_padding_remains_valid(source, tmp_path, padding_blocks):
    raw = tar_bytes(source_members(source)) + b"\0" * (512 * padding_blocks)
    report = contract.check_sdist(write_archive(tmp_path, raw), source)
    assert report["status"] == "passed"
    assert report["unpacked_bytes"] == sum(map(len, source_members(source).values()))
    assert report["member_count"] == len(source_members(source))


@pytest.mark.parametrize("tail", [b"\0" * 511 + b"x", b"\0", b"hidden log"])
def test_tar_padding_cannot_conceal_nonzero_or_partial_blocks(source, tmp_path, tail):
    with pytest.raises(ValueError):
        contract.check_sdist(
            write_archive(tmp_path, tar_bytes(source_members(source)) + tail), source
        )


@pytest.mark.parametrize("end_blocks", [0, 1, 2])
def test_tar_requires_both_end_blocks(source, tmp_path, end_blocks):
    members = source_members(source)
    used = sum(512 + ((len(raw) + 511) // 512) * 512 for raw in members.values())
    raw = tar_bytes(members)[:used] + b"\0" * (512 * end_blocks)
    path = write_archive(tmp_path, raw)
    if end_blocks == 2:
        assert contract.check_sdist(path, source)["status"] == "passed"
    else:
        with pytest.raises(ValueError):
            contract.check_sdist(path, source)


@pytest.mark.parametrize("corruption", ["checksum", "giant-size", "negative-size"])
def test_malformed_raw_tar_headers_fail(source, tmp_path, corruption):
    raw = bytearray(tar_bytes(source_members(source)))
    if corruption == "checksum":
        raw[0] ^= 1
    else:
        raw[124:136] = (
            b"77777777777\0" if corruption == "giant-size" else b"-0000000001\0"
        )
        raw[148:156] = b" " * 8
        raw[148:156] = f"{sum(raw[:512]):06o}\0 ".encode()
    with pytest.raises(ValueError):
        contract.check_sdist(write_archive(tmp_path, raw), source)


@pytest.mark.parametrize("over", [0, 512])
def test_decompressed_envelope_exact_boundary(source, tmp_path, over):
    # Logical member bytes stay small; the separate physical envelope includes
    # the documented maximum header/body alignment and 10 KiB tail allowance.
    limit = 2**23 + 512 * (512 + 511) + 10240
    raw = tar_bytes(source_members(source))
    path = write_archive(tmp_path, raw + b"\0" * (limit + over - len(raw)))
    if over:
        with pytest.raises(ValueError, match="budget"):
            contract.check_sdist(path, source)
    else:
        assert contract.check_sdist(path, source)["status"] == "passed"


def test_inflation_is_bounded_before_tarfile_header_parsing(
    source, tmp_path, monkeypatch
):
    raw = tar_bytes(source_members(source)) + b"\0" * (10 * 1024 * 1024)
    path = write_archive(tmp_path, raw)

    def forbidden(*args, **kwargs):
        pytest.fail("tarfile parsed attacker input before the inflation bound")

    monkeypatch.setattr(tarfile.TarInfo, "frombuf", forbidden)
    monkeypatch.setattr(tarfile.TarFile, "next", forbidden)
    with pytest.raises(ValueError, match="budget"):
        contract.check_sdist(path, source)


def gzip_with_exact_size(raw, size):
    """Valid DEFLATE empty stored blocks exercise compressed size, not garbage."""
    compressor = zlib.compressobj(wbits=-15)
    body = compressor.compress(raw) + compressor.flush()
    # Each non-final stored block is five bytes and ends on a byte boundary.
    remainder = (size - 18 - len(body)) % 5
    comment = b"x" * (remainder - 1) + b"\0" if remainder else b""
    header = b"\x1f\x8b\x08" + bytes([8 if comment else 0]) + b"\0" * 4 + b"\x00\xff"
    blocks = (size - len(header) - len(comment) - len(body) - 8) // 5
    result = (
        header
        + comment
        + b"\x00\x00\x00\xff\xff" * blocks
        + body
        + struct.pack("<II", zlib.crc32(raw), len(raw) & 0xFFFFFFFF)
    )
    assert len(result) == size
    assert gzip.decompress(result) == raw
    return result


@pytest.mark.parametrize("over", [0, 1])
def test_real_compressed_two_mib_boundary(source, tmp_path, over):
    path = tmp_path / "boundary.tar.gz"
    path.write_bytes(
        gzip_with_exact_size(tar_bytes(source_members(source)), 2**21 + over)
    )
    if over:
        with pytest.raises(ValueError, match="compressed.*budget"):
            contract.check_sdist(path, source)
    else:
        assert contract.check_sdist(path, source)["compressed_bytes"] == 2**21


@pytest.mark.parametrize("over", [0, 1])
def test_real_logical_eight_mib_boundary(source, tmp_path, over):
    members = source_members(source)
    members["PKG-INFO"] += b"A" * (2**23 - sum(map(len, members.values())) + over)
    path = write_archive(tmp_path, tar_bytes(members))
    if over:
        with pytest.raises(ValueError, match="unpacked.*budget"):
            contract.check_sdist(path, source)
    else:
        assert contract.check_sdist(path, source)["unpacked_bytes"] == 2**23


@pytest.mark.parametrize("over", [0, 1])
def test_real_logical_512_member_boundary(source, tmp_path, over):
    current = len(source_members(source))
    for i in range(512 - current + over):
        (source / f"src/repo_catalog/boundary_{i}.py").write_bytes(b"")
    path = write_archive(tmp_path, tar_bytes(source_members(source)))
    if over:
        with pytest.raises(ValueError, match="member.*budget"):
            contract.check_sdist(path, source)
    else:
        assert contract.check_sdist(path, source)["member_count"] == 512


@pytest.mark.parametrize("field", [b"Name", b"Version", b"Metadata-Version", b"name"])
@pytest.mark.parametrize("position", ["before", "after"])
def test_metadata_singletons_are_case_insensitively_unique(
    source, tmp_path, field, position
):
    members = source_members(source)
    value = {
        b"Name": b"repo-catalog",
        b"name": b"repo-catalog",
        b"Version": b"0.2.0",
        b"Metadata-Version": b"2.4",
    }[field]
    duplicate = field + b": " + value + b"\n"
    members["PKG-INFO"] = (
        duplicate + PKG_INFO
        if position == "before"
        else PKG_INFO.replace(b"\n\n", b"\n" + duplicate + b"\n")
    )
    with pytest.raises(ValueError):
        contract.check_sdist(write_archive(tmp_path, tar_bytes(members)), source)


@pytest.mark.parametrize("version", [b"garbage", b"2", b"2.0", b"99.9", b""])
def test_invalid_metadata_version_is_rejected(source, tmp_path, version):
    members = source_members(source)
    members["PKG-INFO"] = PKG_INFO.replace(b"2.4", version)
    with pytest.raises(ValueError):
        contract.check_sdist(write_archive(tmp_path, tar_bytes(members)), source)


@pytest.mark.parametrize(
    "name,version", [("$invalid", "0.2.0"), ("repo-catalog", "not-a-version")]
)
def test_metadata_identity_syntax_even_when_invalid_project_matches(
    source, tmp_path, name, version
):
    (source / "pyproject.toml").write_text(
        f'[project]\nname="{name}"\nversion="{version}"\n'
    )
    members = source_members(source)
    members["PKG-INFO"] = (
        f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n\n".encode()
    )
    prefix = f"{name.replace('-', '_')}-{version}/"
    with pytest.raises(ValueError, match="PKG-INFO"):
        contract.check_sdist(
            write_archive(tmp_path, tar_bytes(members, prefix=prefix)), source
        )


@pytest.mark.parametrize("missing", ["schema.sql", "contract.json", "query.graphql"])
def test_each_runtime_resource_remains_required(source, tmp_path, missing):
    members = source_members(source)
    del members["src/repo_catalog/" + missing]
    with pytest.raises(ValueError, match="missing"):
        contract.check_sdist(write_archive(tmp_path, tar_bytes(members)), source)


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.BLKTYPE])
def test_links_and_device_nodes_cannot_replace_source_inputs(source, tmp_path, kind):
    members = source_members(source)
    del members["README.md"]
    info = tarfile.TarInfo(DIST + "README.md")
    info.type = kind
    info.linkname = "../outside"
    path = write_archive(tmp_path, tar_bytes(members, extra=[(info, b"")]))
    with pytest.raises(ValueError):
        contract.check_sdist(path, source)


@pytest.mark.parametrize("name", [DIST + "../escape", DIST + "README.md"])
def test_traversal_and_duplicate_headers_still_fail(source, tmp_path, name):
    info = tarfile.TarInfo(name)
    path = write_archive(
        tmp_path, tar_bytes(source_members(source), extra=[(info, b"")])
    )
    with pytest.raises(ValueError):
        contract.check_sdist(path, source)


def test_distribution_gate_refuses_before_extract_rebuild_or_install(
    source, tmp_path_factory, monkeypatch
):
    from tests.packaging import test_p1_distribution as distribution

    commands = []
    extractions = []

    def fake_build(args, cwd, env):
        commands.append(list(map(str, args)))
        out = Path(args[args.index("--out-dir") + 1])
        out.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SPECIMENS / "concatenated.tar.gz", out / "attack.tar.gz")
        return ""

    monkeypatch.setattr(distribution, "ROOT", source)
    monkeypatch.setattr(distribution, "run", fake_build)
    monkeypatch.setattr(
        tarfile.TarFile, "extractall", lambda *args, **kwargs: extractions.append(args)
    )
    with pytest.raises(ValueError):
        distribution.p1_distributions.__wrapped__(tmp_path_factory)
    assert len(commands) == 2  # only the explicit source sdist/direct-wheel builds
    assert not extractions
    assert not any("install" in command for command in commands)
