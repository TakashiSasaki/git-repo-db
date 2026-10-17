"""Linux local-directory activation; no shell, Git, credentials or remote dispatch.

For THIS adapter a file Scope Locator names an allowed local root directory, and
an absolute Repository Locator names a directory below it in the same namespace.
No chroot/path concatenation is invented. Other Scope-locator meanings need their
own explicitly supported adapter. The operator asserts the UUID binding; inode and
namespace checks do not prove global repository/Scope identity or host attestation.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from collections.abc import Callable
from urllib.parse import unquote_to_bytes, urlsplit

from repo_catalog.domain.access_connections import AccessReviewPlan, canonical
from repo_catalog.domain.access_registry import AccessRegistryError


def _fail(code: str = "EXECUTOR_CHANGED") -> None:
    raise AccessRegistryError(
        code, "local directory executor is unavailable or changed"
    )


def _path(locator: str) -> str:
    if locator.startswith("/"):
        value = locator
    else:
        parsed = urlsplit(locator)
        if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
            _fail("EXECUTOR_UNSUPPORTED")
        try:
            value = unquote_to_bytes(parsed.path).decode("utf-8", "strict")
        except UnicodeError:
            _fail("EXECUTOR_UNSUPPORTED")
    parts = value.split("/")
    if (
        not value.startswith("/")
        or value == "/"
        or len(parts) > 256
        or any(p in ("", ".", "..") for p in parts[1:])
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        _fail("EXECUTOR_UNSUPPORTED")
    return value


def _directory(path: str) -> int:
    """Open each absolute component without following a symlink, pin final fd."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    fd = os.open("/", flags)
    try:
        for part in path.split("/")[1:]:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or info.st_mode & 0o022:
            _fail("EXECUTOR_PERMISSIONS")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _identity(fd: int) -> tuple[int, int, int, int]:
    info = os.fstat(fd)
    return info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)


def _environment() -> tuple[int, ...]:
    ns = os.stat("/proc/self/ns/mnt")
    return os.getpid(), os.geteuid(), os.getegid(), ns.st_dev, ns.st_ino


class LocalDirectoryExecutor:
    """Factory must be chosen by trusted local application code, never by JSON."""

    def bind(self, plan: AccessReviewPlan) -> BoundLocalDirectory:
        if type(plan) is not AccessReviewPlan:
            _fail("TYPE")
        AccessReviewPlan(
            plan.assignment,
            plan.repository_uuidv4,
            plan.registration,
            plan.options_json,
            plan.context_json,
        )
        if not sys.platform.startswith("linux"):
            _fail("EXECUTOR_UNSUPPORTED")
        options, context = json.loads(plan.options_json), json.loads(plan.context_json)
        if options != {"version": 1, "transport": "file", "path_dialect": "posix"}:
            _fail("EXECUTOR_UNSUPPORTED")
        if context["executor_kind"] != "local" or context["path_dialect"] != "posix":
            _fail("EXECUTOR_UNSUPPORTED")
        root = _path(plan.registration.scope_locator_uri)
        repository = _path(plan.assignment.locator_text)
        if repository != root and not repository.startswith(root + "/"):
            _fail("EXECUTOR_SCOPE")
        return BoundLocalDirectory(root, repository)


class BoundLocalDirectory:
    def __init__(self, root: str, repository: str):
        self._root_path, self._repository_path = root, repository
        self._root_fd = self._repository_fd = -1
        self._closed = False
        try:
            self._environment = _environment()
            self._root_fd = _directory(root)
            self._repository_fd = _directory(repository)
            self._root = _identity(self._root_fd)
            self._repository = _identity(self._repository_fd)
            self._snapshot = canonical(
                {
                    "adapter": "linux-local-directory-1",
                    "root": [root, *self._root],
                    "repository": [repository, *self._repository],
                    "process_identity_and_mount_namespace": self._environment,
                }
            )
            self.evidence()
        except BaseException as error:
            self.close()
            if isinstance(error, OSError):
                _fail("EXECUTOR_UNAVAILABLE")
            raise

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            for fd in (self._root_fd, self._repository_fd):
                if fd >= 0:
                    os.close(fd)

    def evidence(self) -> str:
        if self._closed:
            _fail("EXECUTOR_CLOSED")
        try:
            if _environment() != self._environment:
                _fail()
            for path, fd, expected in (
                (self._root_path, self._root_fd, self._root),
                (self._repository_path, self._repository_fd, self._repository),
            ):
                other = _directory(path)
                try:
                    if _identity(fd) != expected or _identity(other) != expected:
                        _fail()
                finally:
                    os.close(other)
            return self._snapshot
        except OSError:
            _fail()

    def invoke(self, operation: Callable[[int], object]) -> object:
        # Workflow performed final Access check; recheck pinned local evidence.
        # The descriptor is valid only for the trusted callback's duration.
        self.evidence()
        return operation(self._repository_fd)
