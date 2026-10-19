"""Linux fd-bound local Git input after explicit Access activation.

Only ordinary worktrees with an in-place .git directory and bare repositories are
supported. Linked worktrees, external object alternates and symlinked storage are
rejected. No clone/fetch, credentials, hooks, textconv or ordinary blob interface.
Owned local filesystem and trusted Git executable are prerequisites, not a sandbox
against the filesystem owner. Mutable refs are observations, not an atomic snapshot.
"""

from __future__ import annotations

import os
import re
import selectors
import shutil
import stat
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from repo_catalog.adapters.filesystem.access_executor import (
    _directory,
    _environment,
    _identity,
)
from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.domain.p1_core import CoreFailure


class AccessGitSource(GitNativeSource):
    """Pin actual repository/storage descriptors; keep persistent keys fd-independent."""

    def __init__(
        self,
        descriptor: int,
        path: str,
        *,
        object_format: str,
        work,
        guard: Callable[[], None],
        bind_identity: Callable[[dict], None],
        metadata_bytes: int = 64 * 1024 * 1024,
    ):
        if object_format not in ("sha1", "sha256"):
            raise CoreFailure(
                "NATIVE_FORMAT", "access", "explicit expected format required"
            )
        if type(metadata_bytes) is not int or not 0 < metadata_bytes < 2**63:
            raise CoreFailure(
                "BUDGET", "access", "positive finite metadata bound required"
            )
        self.path = Path(path)  # Actual reviewed spelling, never /proc fd as identity.
        self.object_format = object_format
        self.metadata_bytes = metadata_bytes
        self._guard, self._work = guard, work
        self._fds: list[int] = []
        self._closed = False
        try:
            self._git = shutil.which("git", path=os.defpath)
            if self._git is None:
                self._fail("GIT_UNAVAILABLE")
            self._env_identity = _environment()
            self._repo = self._keep(os.dup(descriptor))
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
            try:
                self._gitdir = self._keep(os.open(".git", flags, dir_fd=self._repo))
                self._relative = ".git"
            except FileNotFoundError:
                self._gitdir = self._keep(os.dup(self._repo))
                self._relative = "."
            self._objects = self._keep(os.open("objects", flags, dir_fd=self._gitdir))
            self._refs = self._keep(os.open("refs", flags, dir_fd=self._gitdir))
            self._original = tuple(_identity(fd) for fd in self._fds)
            self._config = self._read_config()
            self._verify()
            identity = {
                "adapter": "linux-pinned-git-1",
                "path": str(self.path),
                "git_dir_kind": "bare" if self._relative == "." else "worktree",
                "repository_and_storage": [list(item) for item in self._original],
                # Omit process/fd numbers: a retry in another process is legitimate.
                "user_group_mount_namespace": list(self._env_identity[1:]),
                "expected_object_format": object_format,
                "configuration_token": list(self._config),
            }
            bind_identity(identity)  # Persist/recheck before the first Git invocation.
            actual = self._run("rev-parse", "--show-object-format=storage").strip()
            if actual != object_format.encode("ascii"):
                self._fail("NATIVE_FORMAT")
        except BaseException as error:
            self.close()
            if isinstance(error, OSError):
                raise CoreFailure(
                    "GIT_INPUT", "access", "local storage unavailable"
                ) from None
            raise

    @staticmethod
    def _fail(code="EXECUTOR_CHANGED"):
        raise CoreFailure(
            code, "access-git", "reviewed local Git storage is unsupported or changed"
        )

    def _keep(self, fd):
        self._fds.append(fd)
        return fd

    def close(self):
        if not self._closed:
            self._closed = True
            for fd in reversed(self._fds):
                os.close(fd)
            self._fds.clear()

    def _verify(self):
        if self._closed:
            self._fail("EXECUTOR_CLOSED")
        self._guard()
        if _environment() != self._env_identity:
            self._fail()
        current = _directory(str(self.path))
        try:
            if _identity(current) != self._original[0]:
                self._fail()
        finally:
            os.close(current)
        if tuple(_identity(fd) for fd in self._fds) != self._original:
            self._fail()
        for item in self._original:
            if item[2] != os.geteuid() or item[3] & 0o022:
                self._fail("EXECUTOR_PERMISSIONS")
        for parent, name, fd in (
            (self._repo, self._relative, self._gitdir),
            (self._gitdir, "objects", self._objects),
            (self._gitdir, "refs", self._refs),
        ):
            observed = os.stat(name, dir_fd=parent, follow_symlinks=False)
            actual = os.fstat(fd)
            if not stat.S_ISDIR(observed.st_mode) or (
                observed.st_dev,
                observed.st_ino,
            ) != (actual.st_dev, actual.st_ino):
                self._fail()
        for name in ("HEAD", "config"):
            info = os.stat(name, dir_fd=self._gitdir, follow_symlinks=False)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_mode & 0o022
            ):
                self._fail("EXECUTOR_UNSUPPORTED")
        if self._config_token() != self._config:
            self._fail()
        for name in ("commondir", "gitdir", "config.worktree"):
            try:
                os.stat(name, dir_fd=self._gitdir, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                self._fail("EXECUTOR_UNSUPPORTED")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        info_fd = os.open("info", flags, dir_fd=self._objects)
        try:
            for name in ("alternates", "http-alternates"):
                try:
                    os.stat(name, dir_fd=info_fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    self._fail("EXECUTOR_UNSUPPORTED")
        finally:
            os.close(info_fd)
        # Filesystem validation can block after the preceding guard. Refuse a
        # cancellation/revocation/stop observed during that final preparation
        # before handing these options to the next Git subprocess.
        self._guard()

    def _config_token(self):
        info = os.stat("config", dir_fd=self._gitdir, follow_symlinks=False)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o022
        ):
            self._fail("EXECUTOR_UNSUPPORTED")
        return (
            info.st_dev,
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )

    def _read_config(self):
        """Bound source-config input; reject indirect config/worktree file lookup."""
        self._guard()
        token = self._config_token()
        if token[2] > 128 * 1024:
            self._fail("BUDGET")
        fd = os.open(
            "config", os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self._gitdir
        )
        try:
            limit = token[2] + 1
            self._work.require("input_bytes", limit)
            data = os.read(fd, limit)
            self._work.charge("input_bytes", len(data))
        finally:
            os.close(fd)
        if len(data) != token[2] or self._config_token() != token:
            self._fail()
        # Git recognizes one UTF-8 BOM at byte zero. Match its lexical view for
        # indirect-config rejection while retaining the exact file token/bytes.
        inspected = data.removeprefix(b"\xef\xbb\xbf")
        if re.search(
            rb"(?im)^\s*\[\s*include(?:if)?(?:\s|[.\]])", inspected
        ) or re.search(rb"(?im)^\s*(?:worktree|worktreeconfig)\s*=", inspected):
            self._fail("EXECUTOR_UNSUPPORTED")
        return token

    def _environment(self):
        # Do not inherit GIT_CONFIG_COUNT, GIT_DIR, aliases, trace paths, SSH
        # commands, credentials or object selection from the caller environment.
        return {
            "PATH": os.defpath,
            "LC_ALL": "C",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_ALLOW_PROTOCOL": "",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OBJECT_DIRECTORY": f"/proc/self/fd/{self._objects}",
        }

    def _process_options(self):
        self._verify()
        return {"pass_fds": tuple(self._fds), "cwd": f"/proc/self/fd/{self._repo}"}

    def _command(self, *args):
        if not args or args[0] not in ("rev-parse", "cat-file", "for-each-ref"):
            self._fail("GIT_COMMAND")
        return [
            self._git,
            "--no-replace-objects",
            f"--git-dir=/proc/self/fd/{self._gitdir}",
            "-c",
            "core.fsmonitor=false",
            "-c",
            f"core.hooksPath={os.devnull}",
            "-c",
            "protocol.allow=never",
            *args,
        ]

    def _run(self, *args, data=None):
        # Only the fixed storage-format bootstrap uses this path. Metadata/refs
        # and Notes reuse P4's streamed, prepaid byte/verification/proof accounting.
        if args != ("rev-parse", "--show-object-format=storage") or data is not None:
            self._fail("GIT_COMMAND")
        self._work.require("metadata_units", 1)
        self._work.charge("metadata_units", 1)
        process = subprocess.Popen(
            self._command(*args),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=self._environment(),
            **self._process_options(),
        )
        output = bytearray()
        deadline = time.monotonic() + 30
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    self._guard()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        self._fail("GIT_TIMEOUT")
                    if not selector.select(min(remaining, 0.25)):
                        continue
                    amount = 129 - len(output)
                    self._work.require("input_bytes", amount)
                    block = os.read(process.stdout.fileno(), amount)
                    self._work.charge("input_bytes", len(block))
                    if not block:
                        break
                    output.extend(block)
                    if len(output) > 128:
                        self._fail("BUDGET")
            if process.wait(timeout=max(0.001, deadline - time.monotonic())):
                self._fail("GIT_INPUT")
            return bytes(output)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()
