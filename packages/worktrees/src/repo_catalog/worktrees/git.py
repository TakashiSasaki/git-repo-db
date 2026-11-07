"""Bounded read-only Git plumbing on native Windows and POSIX."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import replace

from .models import (
    DiscoveryResult,
    WorktreeEntry,
    WorktreeError,
    native_path,
    observation_uuid,
)


class _Git:
    def __init__(self, timeout: float, limit: int):
        if (
            type(timeout) not in (int, float)
            or not 0 < timeout <= 3600
            or type(limit) is not int
            or not 0 < limit <= 256 * 1024 * 1024
        ):
            raise WorktreeError("LIMIT", "finite positive Git limits required")
        self.executable = shutil.which("git")
        if self.executable is None:
            raise WorktreeError("GIT_UNAVAILABLE", "Git executable unavailable")
        self.deadline = time.monotonic() + timeout
        self.remaining = limit
        self.env = {
            "PATH": os.environ.get("PATH", os.defpath),
            "LC_ALL": "C",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ALLOW_PROTOCOL": "",
        }
        for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
            if key in os.environ:
                self.env[key] = os.environ[key]

    def run(self, path: bytes, *args: str, allow_failure=False):
        remaining_time = self.deadline - time.monotonic()
        if remaining_time <= 0 or self.remaining <= 0:
            raise WorktreeError("LIMIT", "Git discovery budget exhausted")
        command = [
            self.executable,
            "--no-replace-objects",
            "-c",
            "core.fsmonitor=false",
            "-c",
            f"core.hooksPath={os.devnull}",
            "-c",
            "protocol.allow=never",
            "-C",
            os.fsdecode(path),
            *args,
        ]
        chunks = []
        too_large = threading.Event()
        read_failed = threading.Event()
        size = 0
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=self.env,
            )
        except OSError:
            raise WorktreeError("GIT_INPUT", "Git could not start") from None

        def read_output():
            nonlocal size
            try:
                while block := process.stdout.read(65536):
                    size += len(block)
                    if size > self.remaining:
                        too_large.set()
                        process.kill()
                        return
                    chunks.append(block)
            except (OSError, ValueError):
                read_failed.set()

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        try:
            process.wait(timeout=remaining_time)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise WorktreeError("LIMIT", "Git discovery timed out") from None
        finally:
            reader.join(timeout=1)
            process.stdout.close()
        self.remaining -= size
        if too_large.is_set():
            raise WorktreeError("LIMIT", "Git output budget exceeded")
        if read_failed.is_set() or reader.is_alive():
            raise WorktreeError("GIT_INPUT", "Git output could not be read")
        if process.returncode and not allow_failure:
            raise WorktreeError("GIT_INPUT", "Git topology command failed")
        return process.returncode, b"".join(chunks)

    def value(self, path, *args):
        raw = self.run(path, "rev-parse", *args)[1]
        if raw.endswith(b"\n"):
            raw = raw[:-1]
            if os.name == "nt" and raw.endswith(b"\r"):
                raw = raw[:-1]
        return raw


def _inspect(git: _Git, path: bytes) -> WorktreeEntry:
    bare = git.value(path, "--is-bare-repository") == b"true"
    git_dir = native_path(git.value(path, "--absolute-git-dir"))
    common = native_path(git.value(path, "--path-format=absolute", "--git-common-dir"))
    root = git_dir if bare else native_path(git.value(path, "--show-toplevel"))
    fmt = git.value(path, "--show-object-format=storage").decode("ascii")
    if fmt not in ("sha1", "sha256"):
        raise WorktreeError("GIT_FORMAT", "unsupported Git object format")
    code, head = git.run(path, "rev-parse", "--verify", "HEAD", allow_failure=True)
    head_oid = None if code else head.strip().decode("ascii")
    if head_oid is not None and not re.fullmatch(
        r"[0-9a-f]{40}" if fmt == "sha1" else r"[0-9a-f]{64}", head_oid
    ):
        raise WorktreeError("GIT_INPUT", "invalid HEAD object identity")
    code, branch = git.run(path, "symbolic-ref", "-q", "HEAD", allow_failure=True)
    branch = None if code else branch.removesuffix(b"\n")
    return WorktreeEntry(
        root, git_dir, common, head_oid, branch, bare, object_format=fmt
    )


def _porcelain(raw: bytes, common: bytes, max_worktrees: int):
    if raw and not raw.endswith(b"\0\0"):
        raise WorktreeError("GIT_INPUT", "truncated worktree listing")
    entries = []
    for record in raw.split(b"\0\0"):
        if not record:
            continue
        fields = {}
        for item in record.split(b"\0"):
            key, _, value = item.partition(b" ")
            if key in fields:
                raise WorktreeError("GIT_INPUT", "duplicate worktree field")
            fields[key] = value
        if b"worktree" not in fields:
            raise WorktreeError("GIT_INPUT", "worktree path missing")
        head = fields.get(b"HEAD")
        if head and not re.fullmatch(rb"[0-9a-f]{40}|[0-9a-f]{64}", head):
            raise WorktreeError("GIT_INPUT", "invalid listed HEAD identity")
        entries.append(
            WorktreeEntry(
                native_path(fields[b"worktree"]),
                None,
                common,
                head.decode("ascii") if head and set(head) != {48} else None,
                fields.get(b"branch"),
                b"bare" in fields,
                fields.get(b"locked"),
                fields.get(b"prunable"),
            )
        )
        if len(entries) > max_worktrees:
            raise WorktreeError("LIMIT", "worktree count exceeds discovery limit")
    return entries


def _git_marker(path: bytes) -> bool:
    """Distinguish plain directories from broken Git pointers/configuration."""
    current = os.fsdecode(path)
    while True:
        if os.path.lexists(os.path.join(current, ".git")):
            return True
        if os.path.isfile(os.path.join(current, "HEAD")) and os.path.isdir(
            os.path.join(current, "objects")
        ):
            return True
        parent = os.path.dirname(current)
        if parent == current:
            return False
        current = parent


def discover_topology(
    root,
    *,
    expand=True,
    timeout_seconds=30,
    output_limit_bytes=8 * 1024 * 1024,
    max_worktrees=10000,
) -> DiscoveryResult:
    path = native_path(root)
    occurrence = observation_uuid()
    observed = time.time_ns() // 1000
    if (
        type(expand) is not bool
        or type(max_worktrees) is not int
        or not 0 < max_worktrees <= 100000
    ):
        raise WorktreeError("LIMIT", "invalid worktree discovery options")
    entries = []
    errors = []
    common = None
    try:
        git = _Git(timeout_seconds, output_limit_bytes)
        if not os.path.isdir(path):
            raise WorktreeError("PATH_UNAVAILABLE", "input directory unavailable")
        code, _ = git.run(path, "rev-parse", "--git-dir", allow_failure=True)
        if code:
            status = "error" if _git_marker(path) else "not_git"
            return DiscoveryResult(
                None,
                occurrence,
                path,
                None,
                (),
                status,
                ("GIT_INPUT",) if status == "error" else (),
                observed,
            )
        initial = _inspect(git, path)
        common = initial.common_dir
        entries = [initial]
        if expand:
            raw = git.run(path, "worktree", "list", "--porcelain", "-z")[1]
            listed = _porcelain(raw, common, max_worktrees)
            if not listed:
                raise WorktreeError(
                    "GIT_INPUT", "Git returned an empty worktree listing"
                )
            entries = []
            for entry in listed:
                try:
                    actual = (
                        initial
                        if entry.root_path == initial.root_path
                        else _inspect(git, entry.root_path)
                    )
                    if actual.common_dir != common:
                        raise WorktreeError(
                            "TOPOLOGY_CHANGED", "worktree common directory changed"
                        )
                    entries.append(
                        replace(actual, locked=entry.locked, prunable=entry.prunable)
                    )
                except (WorktreeError, OSError, UnicodeError) as error:
                    code = getattr(error, "code", "GIT_INPUT")
                    entries.append(replace(entry, error=code))
                    errors.append(code)
    except (WorktreeError, OSError, UnicodeError) as error:
        errors.append(getattr(error, "code", "GIT_INPUT"))
    status = "partial" if errors and entries else "error" if errors else "complete"
    return DiscoveryResult(
        None, occurrence, path, common, tuple(entries), status, tuple(errors), observed
    )
