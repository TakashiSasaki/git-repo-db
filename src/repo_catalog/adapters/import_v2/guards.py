"""Irreversible worker-only guards; never install in the application/test runner.

Kernel seccomp denies network, exec and new processes, including C-library
acquisition. CPython audit checks deny accidental filesystem/SQLite writes
outside the dedicated workspace. This is trusted converter isolation, not an
arbitrary native-code filesystem sandbox. SQLite additionally opens source RO.
"""

import ctypes
import os
import platform
import sqlite3
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

from .common import ConversionError


@dataclass(frozen=True)
class WorkerPolicy:
    workspace: Path
    protected: tuple


def kernel_deny():
    # seccomp_data: syscall nr at 0, architecture at 4. Fail closed on unsupported
    # platforms rather than silently replacing the guarantee with socket mocks.
    machines = {
        "x86_64": (
            0xC000003E,
            [
                41,
                42,
                43,
                44,
                45,
                46,
                47,
                49,
                50,
                53,
                56,
                57,
                58,
                59,
                288,
                299,
                307,
                322,
                425,
                426,
                427,
                435,
            ],
        ),
        "aarch64": (
            0xC00000B7,
            [
                198,
                199,
                200,
                201,
                202,
                203,
                206,
                207,
                211,
                212,
                220,
                221,
                242,
                243,
                269,
                281,
                425,
                426,
                427,
                435,
            ],
        ),
    }
    if sys.platform != "linux" or platform.machine() not in machines:
        raise ConversionError("KERNEL_GUARD_UNAVAILABLE")
    arch, denied = machines[platform.machine()]

    class Filter(ctypes.Structure):
        _fields_ = [
            ("code", ctypes.c_ushort),
            ("jt", ctypes.c_ubyte),
            ("jf", ctypes.c_ubyte),
            ("k", ctypes.c_uint),
        ]

    class Program(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ushort), ("filters", ctypes.POINTER(Filter))]

    instructions = [
        (0x20, 0, 0, 4),
        (0x15, 1, 0, arch),
        (0x06, 0, 0, 0x80000000),
        (0x20, 0, 0, 0),
    ]
    if platform.machine() == "x86_64":
        # x32 syscall numbers bypass the ordinary x86_64 number list.
        instructions += [(0x35, 0, 1, 0x40000000), (0x06, 0, 0, 0x50001)]
    for number in denied:
        instructions += [(0x15, 0, 1, number), (0x06, 0, 0, 0x50001)]
    # CPython's open audit event does not expose dir_fd. Close that bypass at
    # the syscall boundary (readers use absolute paths, never FD-relative open).
    for number in (257, 437) if platform.machine() == "x86_64" else (56, 437):
        instructions += [
            (0x15, 0, 4, number),
            (0x20, 0, 0, 16),
            (0x15, 1, 0, 0xFFFFFF9C),
            (0x06, 0, 0, 0x50001),
            (0x20, 0, 0, 0),
        ]
    instructions += [(0x06, 0, 0, 0x7FFF0000)]
    filters = (Filter * len(instructions))(*(Filter(*i) for i in instructions))
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) or libc.prctl(
        22, 2, ctypes.byref(Program(len(filters), filters)), 0, 0
    ):
        raise ConversionError("KERNEL_GUARD_UNAVAILABLE")


def install(workspace, protected=()):
    """Install once in a fresh single-threaded worker, before any DB is opened."""
    workspace = Path(workspace).resolve()
    protected = tuple(Path(p).resolve() for p in protected)
    if any(workspace == p or workspace.is_relative_to(p) for p in protected):
        raise ConversionError("SOURCE_WORKSPACE_OVERLAP")

    def check(path, directory_fd=None):
        if isinstance(path, int) or directory_fd not in (None, -1):
            raise PermissionError("Converter denies FD-relative mutation")
        path = Path(os.fsdecode(path)).resolve()
        if not path.is_relative_to(workspace) or any(
            path == p
            or path.is_relative_to(p)
            or str(path) in {str(p) + suffix for suffix in ("-wal", "-shm", "-journal")}
            for p in protected
        ):
            raise PermissionError("Converter denies source/outside-workspace write")
        try:
            identity = path.stat()
        except FileNotFoundError:
            pass
        else:
            # resolve() follows symlinks, but a pre-existing hardlink retains
            # another path to the same source/cache inode. Writable converter
            # files have no legitimate need for multiple links.
            if stat.S_ISREG(identity.st_mode) and identity.st_nlink != 1:
                raise PermissionError("Converter denies hardlinked file mutation")

    def audit(event, args):
        if event.startswith(("subprocess.", "os.exec", "os.spawn")) or event in {
            "os.system",
            "os.fork",
            "os.forkpty",
            "os.posix_spawn",
            "socket.__new__",
            "socket.connect",
            "socket.getaddrinfo",
        }:
            raise PermissionError("Converter denies network/process acquisition")
        if event == "open":
            path, mode, flags = args
            if (mode and any(c in mode for c in "wax+")) or flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
            ):
                check(path)
        elif event in {
            "os.remove",
            "os.rmdir",
            "os.mkdir",
            "os.chmod",
            "os.chown",
            "os.truncate",
            "os.utime",
        }:
            check(
                args[0],
                args[-1] if event != "os.truncate" else None,
            )
        elif event == "os.link":
            raise PermissionError("Converter denies hardlink creation")
        elif event in {"os.rename", "os.symlink"}:
            if event != "os.symlink":
                check(args[0], args[2] if len(args) > 2 else None)
            check(args[1], args[2] if event == "os.symlink" else args[3])
        elif event == "sqlite3.connect":
            database = os.fsdecode(args[0])
            if database == ":memory:":
                return
            if database.startswith("file:"):
                url = urlsplit(database)
                path = Path(unquote(url.path)).resolve()
                options = parse_qsl(url.query)
                if (
                    options.count(("mode", "ro")) == 1
                    and options.count(("immutable", "1")) == 1
                    and sum(k in {"mode", "immutable"} for k, v in options) == 2
                ):
                    return
            else:
                path = Path(database).resolve()
            check(path)
        elif event == "sqlite3.enable_load_extension":
            if args[1]:
                raise PermissionError("Converter denies native extension loading")

    # No sockets are inherited from this CLI; prevent passing caller socket FDs
    # or writable source handles into the guarded process.
    if len(list(Path("/proc/self/task").iterdir())) != 1:
        raise ConversionError("FRESH_SINGLE_THREAD_WORKER_REQUIRED")
    for fd in (0, 1, 2):
        try:
            if stat.S_ISSOCK(os.fstat(fd).st_mode):
                raise ConversionError("INHERITED_NETWORK_FD")
        except OSError:
            pass
    for name in os.listdir("/proc/self/fd"):
        fd = int(name)
        if fd >= 3:
            try:
                os.close(fd)
            except OSError:
                pass
    kernel_deny()
    sys.addaudithook(audit)  # Cannot be removed. No mutable global policy.
    # Some non-stdlib bindings do not emit connection audit events. Refuse them
    # rather than letting a second accidental writable connection bypass policy.
    events = []
    sys.addaudithook(
        lambda event, args: events.append(event) if event == "sqlite3.connect" else None
    )
    sqlite3.connect(":memory:").close()
    if not events:
        raise ConversionError("SQLITE_AUDIT_UNAVAILABLE")
    return WorkerPolicy(workspace, protected)
