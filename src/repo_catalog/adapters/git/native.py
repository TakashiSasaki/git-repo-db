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
from dataclasses import dataclass
from pathlib import Path

from repo_catalog.domain.git_native import parse_metadata
from repo_catalog.domain.p1_core import OID, CoreFailure, NativeObject


@dataclass(frozen=True)
class NativeRef:
    name: bytes
    target: OID
    object_type: str
    peeled: OID | None
    symbolic_target: bytes | None


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

    def _process_options(self):
        """Trusted adapter subprocess parameters; not caller-provided Git config."""
        return {}

    def _command(self, *args):
        return ["git", "--no-replace-objects", "-C", str(self.path), *args]

    def _run(self, *args, data=None):
        try:
            result = subprocess.run(
                self._command(*args),
                input=data,
                capture_output=True,
                env=self._environment(),
                **self._process_options(),
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

    def metadata(self, object_oid: OID, work=None) -> NativeObject:
        if work is not None:
            from repo_catalog.adapters.git.notes import GitNotesSource

            return GitNotesSource(self).metadata(object_oid, work)
        if object_oid.object_format != self.object_format:
            raise CoreFailure(
                "NATIVE_FORMAT",
                object_oid,
                "Git storage format differs from requested OID",
            )
        header = (
            self._run(
                "cat-file",
                "--batch-check",
                data=(object_oid.object_oid + "\n").encode(),
            )
            .strip()
            .split()
        )
        if header == [object_oid.object_oid.encode(), b"missing"]:
            raise CoreFailure(
                "OBJECT_UNAVAILABLE",
                object_oid,
                "requested native object is unavailable locally",
            )
        if len(header) != 3 or header[0] != object_oid.object_oid.encode():
            raise CoreFailure(
                "GIT_INPUT", object_oid, "unexpected native object header"
            )
        kind = header[1].decode("ascii")
        if kind not in ("commit", "tree", "tag"):
            raise CoreFailure(
                "RETENTION_PURPOSE",
                object_oid,
                "ordinary blob bodies are excluded from metadata input",
            )
        size = int(header[2])
        if size < 0 or size > self.metadata_bytes:
            raise CoreFailure(
                "BUDGET", object_oid, "native metadata exceeds finite input limit"
            )
        # cat-file's <type> form emits the exact representation, never pretty
        # tree output. Read at most the checked size plus one overrun sentinel.
        try:
            process = subprocess.Popen(
                self._command("cat-file", kind, object_oid.object_oid),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=self._environment(),
                **self._process_options(),
            )
        except OSError as error:
            raise CoreFailure(
                "GIT_INPUT", object_oid, "local Git could not start"
            ) from error
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
                            "GIT_INPUT", object_oid, "local Git output timed out"
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
                    object_oid,
                    "native object size changed or output was truncated",
                )
            if process.wait(timeout=max(0.001, deadline - time.monotonic())):
                raise CoreFailure(
                    "OBJECT_UNAVAILABLE", object_oid, "native object could not be read"
                )
            body = bytes(body)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CoreFailure(
                "GIT_INPUT", object_oid, "local Git output failed"
            ) from error
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            if process.stdout is not None:
                process.stdout.close()
        native = NativeObject(
            object_oid, kind, body, size, hashlib.sha256(body).hexdigest()
        )
        native.validate()
        parse_metadata(object_oid.object_format, kind, body)
        return native

    def ref_records(self, work=None) -> tuple[NativeRef, ...]:
        """Finite local enumeration, prepaid before reads and record parsing."""
        from repo_catalog.adapters.git.notes import GitNotesSource
        from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget

        active = work if work is not None else UnlimitedWorkBudget()
        source = GitNotesSource(self)
        raw = source._output(
            (
                "for-each-ref",
                "--format=%(refname)%00%(objectname)%00%(objecttype)%00%(*objectname)%00%(symref)",
            ),
            source.discovery_bytes,
            active,
        )
        result = []
        for line in raw.splitlines():
            active.require("metadata_units", 1)
            active.charge("metadata_units", 1)
            if len(result) >= source.discovery_refs:
                raise CoreFailure("BUDGET", "refs", "finite ref count")
            pieces = line.split(b"\0")
            if len(pieces) != 5:
                raise CoreFailure("GIT_INPUT", "refs", "malformed ref record")
            name, target, kind, peeled, symbolic = pieces
            result.append(
                NativeRef(
                    name,
                    OID(self.object_format, target.decode("ascii")),
                    kind.decode("ascii"),
                    OID(self.object_format, peeled.decode("ascii")) if peeled else None,
                    symbolic or None,
                )
            )
        return tuple(result)

    def refs(self, work=None) -> tuple[tuple[bytes, OID, str, OID | None], ...]:
        return tuple(
            (r.name, r.target, r.object_type, r.peeled) for r in self.ref_records(work)
        )

    def lookup_ref_presence(self, name: bytes, work) -> bool:
        """Named local lookup distinguishes missing refs from errors, without resolving."""
        if (
            not isinstance(name, bytes)
            or not name.startswith(b"refs/")
            or b"\0" in name
        ):
            raise CoreFailure("REF", name, "exact full ref required")
        work.require("metadata_units", 1)
        work.charge("metadata_units", 1)
        work.require("input_bytes", len(name))
        work.charge("input_bytes", len(name))
        try:
            valid = subprocess.run(
                self._command("check-ref-format", os.fsdecode(name)),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=self._environment(),
                **self._process_options(),
                timeout=30,
            )
            if valid.returncode != 0:
                raise CoreFailure("REF", name, "invalid exact Git ref name")
            work.require("metadata_units", 1)
            work.charge("metadata_units", 1)
            work.require("input_bytes", len(name))
            work.charge("input_bytes", len(name))
            result = subprocess.run(
                self._command("show-ref", "--exists", os.fsdecode(name)),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=self._environment(),
                **self._process_options(),
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CoreFailure("GIT_INPUT", name, "named ref lookup failed") from error
        if result.returncode == 0:
            return True
        if result.returncode == 2:
            return False
        raise CoreFailure("GIT_INPUT", name, "named ref lookup did not complete")
