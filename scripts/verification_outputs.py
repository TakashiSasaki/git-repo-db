"""Confine private verification outputs; never follow caller-supplied links."""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import stat
from pathlib import Path


def private_path(root: Path, path: Path) -> Path:
    root = root.absolute()
    path = Path(os.path.abspath(path))
    roots = [
        root / "documentation/.build/inputs",
        root / "documentation/.build/verification",
    ]
    if not any(base in path.parents for base in roots):
        raise ValueError(
            "Private output must remain in dedicated input/verification directories"
        )
    protected = {
        ".git",
        ".venv",
        "cache",
        ".cache",
        ".uv-cache",
        "evidence",
        "catalogs",
        "artifacts",
        "__pycache__",
        "pyvenv.cfg",
    }
    if any(
        part in protected
        for part in path.relative_to(root / "documentation/.build").parts
    ):
        raise ValueError("Protected private-output location refused")
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Linked private output refused")
    if path.exists():
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError("Nonregular or aliased private output refused")
        with path.open("rb") as stream:
            if stream.read(16) == b"SQLite format 3\x00":
                raise ValueError("Catalog private-output collision refused")
    return path


def directory_fd(path: Path) -> int:
    """Walk/create directories with no-follow dirfds, including all ancestors."""
    path = path.absolute()
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            try:
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
            except FileNotFoundError:
                os.mkdir(part, mode=0o700, dir_fd=fd)
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def write_private(root: Path, path: Path, data: bytes) -> None:
    path = private_path(root, path)
    fd = directory_fd(path.parent)
    name = ".pending-" + secrets.token_hex(16)
    try:
        temporary = os.open(
            name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd
        )
        with os.fdopen(temporary, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        private_path(root, path)
        # Replacing a leaf does not dereference it; all writes use the pinned fd.
        os.replace(name, path.name, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(name, dir_fd=fd)
        os.close(fd)


def write_private_json(root: Path, path: Path, value: dict) -> None:
    write_private(root, path, (json.dumps(value, indent=2) + "\n").encode())


def private_attempt(root: Path) -> Path:
    base = root / "documentation/.build/verification"
    probe = private_path(root, base / ".probe")
    fd = directory_fd(probe.parent)
    name = "attempt-" + secrets.token_hex(16)
    try:
        os.mkdir(name, mode=0o700, dir_fd=fd)
    finally:
        os.close(fd)
    return base / name


@contextlib.contextmanager
def private_log(root: Path, path: Path):
    path = private_path(root, path)
    fd = directory_fd(path.parent)
    try:
        log = os.open(
            path.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=fd,
        )
    finally:
        os.close(fd)
    with os.fdopen(log, "w") as stream:
        yield stream
