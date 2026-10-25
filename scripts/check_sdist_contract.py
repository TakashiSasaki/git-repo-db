"""Check ADR 0033 source membership, budgets and complete wheel equivalence.

Stdlib-only inspection; build mode uses the caller's prepared Hatchling. No
product imports, dependency downloads, Git mutation or SQLite setup occur here.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
import tomllib
import zipfile
import zlib
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

MAX_COMPRESSED = 2 * 1024 * 1024
MAX_UNPACKED = 8 * 1024 * 1024
MAX_MEMBERS = 512
# Hatchling 1.32.4's real product archive has 159 plain headers, no PAX
# metadata, 5,921,698 file bytes and a 6,051,840-byte tar stream. Allow each
# logical member one header and at most 511 alignment bytes, plus one tar
# record of end padding. Extensions need a separately reviewed calibration;
# none (including PAX keys/values) are currently required or permitted.
MAX_TAR_STREAM = MAX_UNPACKED + MAX_MEMBERS * (512 + 511) + tarfile.RECORDSIZE
SUPPORTED_METADATA_VERSIONS = {"1.0", "1.1", "1.2", "2.1", "2.2", "2.3", "2.4", "2.5"}
# PEP 440 public and local version grammar, without a packaging dependency.
VERSION_PATTERN = re.compile(
    r"v?(?:[0-9]+!)?[0-9]+(?:\.[0-9]+)*"
    r"(?:[-_.]?(?:alpha|a|beta|b|preview|pre|c|rc)[-_.]?[0-9]*)?"
    r"(?:(?:-[0-9]+)|(?:[-_.]?(?:post|rev|r)[-_.]?[0-9]*))?"
    r"(?:[-_.]?dev[-_.]?[0-9]*)?"
    r"(?:\+[a-z0-9]+(?:[-_.][a-z0-9]+)*)?",
    re.IGNORECASE,
)
PRODUCT_SUFFIXES = {".py", ".sql", ".json", ".graphql"}
ROOT_FILES = ("pyproject.toml", "README.md", ".gitignore")
LICENSE_FILES = tuple(
    base + suffix
    for base in ("LICENSE", "LICENCE", "COPYING", "NOTICE")
    for suffix in ("", ".txt", ".md")
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_name(name, directory=False):
    value = name[:-1] if directory and name.endswith("/") else name
    parts = value.split("/")
    if (
        not value
        or "\\" in value
        or any(p in ("", ".", "..") for p in parts)
        or any(":" in p for p in parts)
        or PurePosixPath(value).is_absolute()
    ):
        raise ValueError("unsafe member: " + name)
    return value


def source_inventory(root):
    root = Path(root).resolve()
    package = root / "src/repo_catalog"
    if not package.is_dir() or package.is_symlink():
        raise ValueError("missing/linked product source directory")
    # Git supplies the frozen tracked input set. Git archives have no .git;
    # there the complete regular-file tree supplies the same source contract.
    if (root / ".git").exists():
        names = (
            subprocess.check_output(
                ["git", "ls-files", "-z", "--", "src/repo_catalog"], cwd=root
            )
            .decode()
            .split("\0")[:-1]
        )
    else:
        names = []
        for p in package.rglob("*"):
            if "__pycache__" in p.parts or p.suffix in (".pyc", ".pyo"):
                continue
            if p.is_symlink():
                raise ValueError("linked source input: " + str(p))
            if p.is_file():
                names.append(p.relative_to(root).as_posix())
    if not names:
        raise ValueError("empty product source inventory")
    for name in names:
        if Path(name).suffix not in PRODUCT_SUFFIXES:
            raise ValueError("unclassified product input: " + name)
    names += list(ROOT_FILES) + [n for n in LICENSE_FILES if (root / n).exists()]
    result = {}
    for name in sorted(names):
        safe_name(name)
        path = root / name
        if (
            path.is_symlink()
            or not path.is_file()
            or not path.resolve().is_relative_to(root)
        ):
            raise ValueError("missing/linked source input: " + name)
        raw = path.read_bytes()
        result[name] = {"bytes": len(raw), "sha256": sha(raw)}
    return result


def read_sdist_stream(archive):
    """Validate exactly one bounded gzip member, including CRC/ISIZE and EOF.

    Do not use gzip.GzipFile: its concatenation and trailing-zero handling would
    permit bytes outside the one inspected archive. zlib validates the gzip
    trailer; its output limit bounds inflation before any tar/PAX parsing.
    """
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    output = io.BytesIO()
    digest = hashlib.sha256()
    compressed = 0
    with archive.open("rb") as stream:
        while chunk := stream.read(64 * 1024):
            compressed += len(chunk)
            if compressed > MAX_COMPRESSED:
                raise ValueError("compressed sdist budget exceeded")
            digest.update(chunk)
            pending = chunk
            while pending:
                try:
                    raw = decoder.decompress(
                        pending, min(64 * 1024, MAX_TAR_STREAM - output.tell() + 1)
                    )
                except zlib.error as error:
                    raise ValueError(
                        "invalid gzip stream/trailer: " + str(error)
                    ) from error
                output.write(raw)
                if output.tell() > MAX_TAR_STREAM:
                    raise ValueError("decompressed tar stream budget exceeded")
                if decoder.eof:
                    if decoder.unused_data or stream.read(1):
                        raise ValueError(
                            "trailing bytes/additional gzip member forbidden"
                        )
                    return output.getvalue(), compressed, digest.hexdigest()
                pending = decoder.unconsumed_tail
    raise ValueError("incomplete gzip stream/trailer")


def check_tar_structure(raw):
    """Inspect physical tar records before tarfile can consume any extensions."""
    if len(raw) % tarfile.BLOCKSIZE:
        raise ValueError("unaligned/truncated tar stream")
    offset, count, unpacked = 0, 0, 0
    zero = bytes(tarfile.BLOCKSIZE)
    while offset + tarfile.BLOCKSIZE <= len(raw):
        header = raw[offset : offset + tarfile.BLOCKSIZE]
        if header == zero:
            tail = raw[offset:]
            if len(tail) < 2 * tarfile.BLOCKSIZE or any(tail):
                raise ValueError("invalid tar end padding or hidden trailing payload")
            return count
        count += 1
        if count > MAX_MEMBERS:
            raise ValueError("sdist member budget exceeded")
        # frombuf parses exactly one fixed-size header, never extension bodies.
        # In particular, do not call TarFile.next() before rejecting x/g/GNU
        # records: it reads and materializes their payload before returning.
        try:
            member = tarfile.TarInfo.frombuf(header, "utf-8", "strict")
        except (tarfile.TarError, UnicodeError, ValueError) as error:
            raise ValueError("invalid raw tar header: " + str(error)) from error
        if member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE):
            raise ValueError(
                "links/special members or unapproved PAX/tar extensions forbidden"
            )
        if member.size < 0 or (member.isdir() and member.size) or member.linkname:
            raise ValueError("invalid raw tar member size/link target")
        if member.isfile():
            unpacked += member.size
            if unpacked > MAX_UNPACKED:
                raise ValueError("unpacked sdist budget exceeded")
        start = offset + tarfile.BLOCKSIZE
        end = start + member.size
        offset = start + (member.size + 511) // 512 * 512
        if offset > len(raw):
            raise ValueError("truncated tar member")
        if any(raw[end:offset]):
            raise ValueError("nonzero tar member padding forbidden")
    raise ValueError("missing tar end markers")


def check_metadata_identity(raw, project):
    info = BytesParser().parsebytes(raw)
    fields = ("Metadata-Version", "Name", "Version")
    if info.defects or any(len(info.get_all(name, [])) != 1 for name in fields):
        raise ValueError("invalid generated PKG-INFO singleton identity fields")
    if (
        info["Metadata-Version"] not in SUPPORTED_METADATA_VERSIONS
        or re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", info["Name"])
        is None
        or VERSION_PATTERN.fullmatch(info["Version"]) is None
        or info["Name"] != project["name"]
        or info["Version"] != project["version"]
    ):
        raise ValueError("invalid generated PKG-INFO identity/version")


def check_sdist(archive, root):
    archive, root = Path(archive), Path(root)
    compressed = archive.stat().st_size
    if compressed > MAX_COMPRESSED:
        raise ValueError("compressed sdist budget exceeded")
    tar_raw, compressed, archive_sha256 = read_sdist_stream(archive)
    raw_header_count = check_tar_structure(tar_raw)
    expected = source_inventory(root)
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    dist = re.sub(r"[-_.]+", "_", project["name"]) + "-" + project["version"]
    actual, seen, count, unpacked = {}, set(), 0, 0
    metadata = None
    with tarfile.open(fileobj=io.BytesIO(tar_raw), mode="r:") as tar:
        for member in tar:
            count += 1
            if count > MAX_MEMBERS:
                raise ValueError("sdist member budget exceeded")
            name = safe_name(member.name, member.isdir())
            if name in seen:
                raise ValueError("duplicate member: " + name)
            seen.add(name)
            if name != dist and not name.startswith(dist + "/"):
                raise ValueError("unexpected distribution root: " + name)
            relative = name[len(dist) + 1 :]
            if member.isdir():
                if name != dist and not any(
                    n.startswith(relative + "/") for n in expected
                ):
                    raise ValueError("unexpected directory: " + relative)
                continue
            if not member.isfile():
                raise ValueError("links/special members forbidden: " + name)
            unpacked += member.size
            if unpacked > MAX_UNPACKED:
                raise ValueError("unpacked sdist budget exceeded")
            if relative != "PKG-INFO" and relative not in expected:
                raise ValueError("unexpected member: " + relative)
            raw = tar.extractfile(member).read()
            actual[relative] = {"bytes": len(raw), "sha256": sha(raw)}
            if relative == "PKG-INFO":
                metadata = raw
            elif actual[relative] != expected[relative]:
                raise ValueError("source hash/size mismatch: " + relative)
    if set(actual) != set(expected) | {"PKG-INFO"}:
        raise ValueError(
            "missing required members: "
            + str(sorted((set(expected) | {"PKG-INFO"}) - set(actual)))
        )
    check_metadata_identity(metadata, project)
    return {
        "status": "passed",
        "archive": archive.name,
        "sha256": archive_sha256,
        "compressed_bytes": compressed,
        "tar_stream_bytes": len(tar_raw),
        "raw_header_count": raw_header_count,
        "unpacked_bytes": unpacked,
        "member_count": count,
        "file_count": len(actual),
        "product_files": sum(n.startswith("src/repo_catalog/") for n in actual),
        "source_inventory_sha256": sha(json.dumps(expected, sort_keys=True).encode()),
        "source_files": expected,
        "members": actual,
        "budgets": {
            "compressed_bytes": MAX_COMPRESSED,
            "unpacked_bytes": MAX_UNPACKED,
            "members": MAX_MEMBERS,
            "tar_stream_bytes": MAX_TAR_STREAM,
        },
    }


def wheel_contents(path):
    files = {}
    with zipfile.ZipFile(path) as wheel:
        for member in wheel.infolist():
            name = safe_name(member.filename, member.is_dir())
            if name in files:
                raise ValueError("duplicate wheel member: " + name)
            if member.is_dir() or (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("non-regular wheel member: " + name)
            files[name] = wheel.read(member)
    records = [n for n in files if n.endswith(".dist-info/RECORD")]
    if len(records) != 1:
        raise ValueError("expected one wheel RECORD")
    record = records[0]
    listed = set()
    for row in csv.reader(io.StringIO(files[record].decode())):
        if len(row) != 3:
            raise ValueError("invalid RECORD row")
        name, digest, length = row
        if name in listed or name not in files:
            raise ValueError("duplicate/unknown RECORD member")
        listed.add(name)
        if name == record:
            if digest or length:
                raise ValueError("RECORD self hash must be empty")
        else:
            wanted = (
                base64.urlsafe_b64encode(hashlib.sha256(files[name]).digest())
                .rstrip(b"=")
                .decode()
            )
            if digest != "sha256=" + wanted or length != str(len(files[name])):
                raise ValueError("wheel RECORD hash/size mismatch: " + name)
    if listed != set(files):
        raise ValueError("wheel RECORD is incomplete")
    return files


def compare_wheels(direct, derived, *, sdist_metadata=None):
    left, right = wheel_contents(direct), wheel_contents(derived)
    if sdist_metadata is not None:
        metadata = [
            raw for name, raw in left.items() if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata) != 1 or sha(metadata[0]) != sdist_metadata:
            raise ValueError("sdist PKG-INFO differs from wheel METADATA")
    if left != right:
        names = sorted(
            n for n in left.keys() | right.keys() if left.get(n) != right.get(n)
        )
        raise ValueError("wheel content/metadata mismatch: " + str(names))
    return {
        "status": "passed",
        "direct": {
            "bytes": Path(direct).stat().st_size,
            "sha256": sha(Path(direct).read_bytes()),
        },
        "sdist_wheel": {
            "bytes": Path(derived).stat().st_size,
            "sha256": sha(Path(derived).read_bytes()),
        },
        "members": {
            n: {"bytes": len(raw), "sha256": sha(raw)}
            for n, raw in sorted(left.items())
        },
        "product_files": sum(n.startswith("repo_catalog/") for n in left),
        "metadata_files": sum(".dist-info/" in n for n in left),
    }


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    parser.add_argument("--sdist", type=Path)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--sdist-wheel", type=Path)
    args = parser.parse_args()
    if args.build == bool(args.sdist) or bool(args.wheel) != bool(args.sdist_wheel):
        parser.error("choose --build or --sdist; supply both wheel paths together")
    try:
        if args.build:
            import tempfile

            with tempfile.TemporaryDirectory(prefix="sdist-contract-") as temp:
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "hatchling",
                        "build",
                        "-t",
                        "sdist",
                        "-d",
                        temp,
                    ],
                    cwd=args.source_root,
                    check=True,
                )
                archives = list(Path(temp).glob("*.tar.gz"))
                if len(archives) != 1:
                    raise ValueError("expected exactly one built sdist")
                result = check_sdist(archives[0], args.source_root)
        else:
            result = check_sdist(args.sdist, args.source_root)
        if args.wheel:
            result["wheel_equivalence"] = compare_wheels(
                args.wheel,
                args.sdist_wheel,
                sdist_metadata=result["members"]["PKG-INFO"]["sha256"],
            )
        save(args.output, result)
        print(
            json.dumps(
                {
                    k: v
                    for k, v in result.items()
                    if k not in ("members", "source_files", "wheel_equivalence")
                }
            )
        )
    except (
        ValueError,
        OSError,
        tarfile.TarError,
        zipfile.BadZipFile,
        subprocess.CalledProcessError,
    ) as error:
        save(args.output, {"status": "failed", "error": str(error)})
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
