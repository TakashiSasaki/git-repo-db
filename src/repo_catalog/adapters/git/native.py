"""Selective local Git metadata input; no fetch, file-body or closure endpoint.

Commands disable replacement objects and optional locks. Each requested immutable
OID is checked by both Git and the receiving domain. The configured finite size
limit is checked before reading object output into memory. This is P2's native
input foundation; P5 owns acquisition orchestration and observation persistence.
"""

from __future__ import annotations

import hashlib
import os
import selectors
import subprocess
import time
from pathlib import Path

from repo_catalog.domain.git_native import parse_metadata
from repo_catalog.domain.p1_core import OID, CoreFailure, NativeObject


class GitNativeSource:
    def __init__(self, path: Path, *, metadata_bytes: int = 64 * 1024 * 1024):
        if type(metadata_bytes) is not int or not 0 < metadata_bytes < 2**63:
            raise CoreFailure(
                "BUDGET", path, "positive finite metadata byte limit required"
            )
        self.path = Path(path).resolve()
        self.metadata_bytes = metadata_bytes
        fmt = self._run("rev-parse", "--show-object-format=storage").strip()
        if fmt not in (b"sha1", b"sha256"):
            raise CoreFailure(
                "NATIVE_FORMAT", path, "unsupported Git storage object format"
            )
        self.object_format = fmt.decode("ascii")

    def _environment(self):
        env = dict(os.environ)
        # Repository-selection environment must not redirect this explicit path.
        for key in (
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_COMMON_DIR",
            "GIT_INDEX_FILE",
            "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            "GIT_REPLACE_REF_BASE",
        ):
            env.pop(key, None)
        env.update(
            GIT_NO_REPLACE_OBJECTS="1",
            GIT_OPTIONAL_LOCKS="0",
            GIT_NO_LAZY_FETCH="1",
            LC_ALL="C",
        )
        return env

    def _command(self, *args):
        return ["git", "--no-replace-objects", "-C", str(self.path), *args]

    def _run(self, *args, data=None):
        try:
            result = subprocess.run(
                self._command(*args),
                input=data,
                capture_output=True,
                env=self._environment(),
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CoreFailure(
                "GIT_INPUT", self.path, "local Git command failed: " + str(error)
            ) from error
        if result.returncode:
            raise CoreFailure(
                "GIT_INPUT", self.path, result.stderr.decode("utf-8", "replace").strip()
            )
        return result.stdout

    def metadata(self, oid: OID) -> NativeObject:
        if oid.object_format != self.object_format:
            raise CoreFailure(
                "NATIVE_FORMAT", oid, "Git storage format differs from requested OID"
            )
        header = (
            self._run("cat-file", "--batch-check", data=(oid.full_oid + "\n").encode())
            .strip()
            .split()
        )
        if header == [oid.full_oid.encode(), b"missing"]:
            raise CoreFailure(
                "OBJECT_UNAVAILABLE",
                oid,
                "requested native object is unavailable locally",
            )
        if len(header) != 3 or header[0] != oid.full_oid.encode():
            raise CoreFailure("GIT_INPUT", oid, "unexpected native object header")
        kind = header[1].decode("ascii")
        if kind not in ("commit", "tree", "tag"):
            raise CoreFailure(
                "RETENTION_PURPOSE",
                oid,
                "ordinary blob bodies are excluded from metadata input",
            )
        size = int(header[2])
        if size < 0 or size > self.metadata_bytes:
            raise CoreFailure(
                "BUDGET", oid, "native metadata exceeds finite input limit"
            )
        # cat-file's <type> form emits the exact representation, never pretty
        # tree output. Read at most the checked size plus one overrun sentinel.
        try:
            process = subprocess.Popen(
                self._command("cat-file", kind, oid.full_oid),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=self._environment(),
            )
        except OSError as error:
            raise CoreFailure("GIT_INPUT", oid, "local Git could not start") from error
        try:
            assert process.stdout is not None
            body = bytearray()
            deadline = time.monotonic() + 30
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while len(body) <= size:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise CoreFailure(
                            "GIT_INPUT", oid, "local Git output timed out"
                        )
                    chunk = os.read(
                        process.stdout.fileno(), min(65536, size + 1 - len(body))
                    )
                    if not chunk:
                        break
                    body.extend(chunk)
            if len(body) != size:
                raise CoreFailure(
                    "GIT_INPUT",
                    oid,
                    "native object size changed or output was truncated",
                )
            if process.wait(timeout=max(0.001, deadline - time.monotonic())):
                raise CoreFailure(
                    "OBJECT_UNAVAILABLE", oid, "native object could not be read"
                )
            body = bytes(body)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CoreFailure("GIT_INPUT", oid, "local Git output failed") from error
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            if process.stdout is not None:
                process.stdout.close()
        native = NativeObject(oid, kind, body, size, hashlib.sha256(body).hexdigest())
        native.validate()
        parse_metadata(oid.object_format, kind, body)
        return native

    def refs(self) -> tuple[tuple[bytes, OID, str, OID | None], ...]:
        """Actual local full ref observations; no remote freshness/completeness."""
        raw = self._run(
            "for-each-ref",
            "--format=%(refname)%00%(objectname)%00%(objecttype)%00%(*objectname)",
        )
        result = []
        for line in raw.splitlines():
            name, target, kind, peeled = line.split(b"\0")
            result.append(
                (
                    name,
                    OID(self.object_format, target.decode("ascii")),
                    kind.decode("ascii"),
                    OID(self.object_format, peeled.decode("ascii")) if peeled else None,
                )
            )
        return tuple(result)
