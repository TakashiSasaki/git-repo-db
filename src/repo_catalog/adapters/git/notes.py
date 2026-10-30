"""Bounded local Notes input, purpose-bound to receiver-checked mapping proofs.

No fetch and no generic blob body interface. Discovery is two local enumeration
observations, never an atomic ref snapshot or evidence of remote absence.
"""

from __future__ import annotations

import hashlib
import os
import selectors
import subprocess
import time
from dataclasses import dataclass

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.domain.git_native import parse_metadata
from repo_catalog.domain.notes import account_proof_bundle
from repo_catalog.domain.p1_core import (
    OID,
    CoreFailure,
    NativeObject,
    NotesProof,
    account_verification,
    encode,
)
from repo_catalog.domain.ports.p1_core import WorkBudget


def _prepay(work, unit, count=1):
    work.require(unit, count)
    work.charge(unit, count)


@dataclass(frozen=True)
class RefScanSnapshot:
    refs: tuple[tuple[bytes, OID], ...]
    state: str


@dataclass(frozen=True)
class RefInventory:
    refs: tuple[tuple[bytes, OID], ...]
    nominated: tuple[bytes, ...]
    status: str
    terminal: bool
    failure_code: str | None = None
    detail: str = ""
    scans: tuple[RefScanSnapshot, ...] = ()


class GitNotesSource:
    """P4 extension of one explicit P2 local source, with finite byte/work bounds."""

    def __init__(
        self,
        source: GitNativeSource,
        *,
        discovery_bytes: int = 16 * 1024 * 1024,
        discovery_refs: int = 100_000,
        timeout_seconds: int = 30,
    ):
        for value in (discovery_bytes, discovery_refs, timeout_seconds):
            if type(value) is not int or not 0 < value < 2**63:
                raise CoreFailure(
                    "BUDGET", "notes-source", "positive finite bound required"
                )
        self.source = source
        self.object_format = source.object_format
        self.discovery_bytes = discovery_bytes
        self.discovery_refs = discovery_refs
        self.timeout_seconds = timeout_seconds

    @property
    def scope(self):
        return encode(
            ["local-git", os.fsencode(self.source.path).hex(), self.object_format]
        )

    def _output(self, args, cap, work, consume=None, data=None):
        """Reserve before every read; exceptions retain unsettled upper bounds.

        Input is counted here; hash and parser passes are independently counted
        below and at the receiving Core. Memory contains only bounded incidental
        input. Child output is killed at a byte limit or deadline.
        """
        _prepay(work, "metadata_units")  # actual attempted Git operation
        try:
            process = subprocess.Popen(
                self.source._command(*args),
                stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=self.source._environment(),
                **self.source._process_options(),
            )
        except OSError as error:
            raise CoreFailure("GIT_INPUT", self.source.path, str(error)) from error
        body = bytearray()
        deadline = time.monotonic() + self.timeout_seconds
        try:
            assert process.stdout is not None
            if data is not None:
                assert process.stdin is not None
                process.stdin.write(data)
                process.stdin.close()
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise CoreFailure(
                            "GIT_INPUT", args, "local Git output timed out"
                        )
                    # One sentinel detects an oversized output without ever
                    # accepting/truncating it as a complete representation.
                    amount = min(65536, cap + 1 - len(body))
                    work.require("input_bytes", amount)
                    chunk = os.read(process.stdout.fileno(), amount)
                    work.charge("input_bytes", len(chunk))
                    if not chunk:
                        break
                    body.extend(chunk)
                    if consume is not None:
                        consume(chunk)
                    if len(body) > cap:
                        raise CoreFailure("BUDGET", args, "finite native output limit")
            if process.wait(timeout=max(0.001, deadline - time.monotonic())):
                raise CoreFailure("GIT_INPUT", args, "local Git command failed")
            return bytes(body)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CoreFailure("GIT_INPUT", args, "local Git output failed") from error
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            if process.stdout is not None:
                process.stdout.close()

    def _native(self, oid, kinds, cap, work):
        if oid.object_format != self.object_format:
            raise CoreFailure(
                "NATIVE_FORMAT", oid, "Git storage format differs from requested OID"
            )
        header = (
            self._output(
                ("cat-file", "--batch-check"),
                128,
                work,
                data=(oid.full_oid + "\n").encode("ascii"),
            )
            .strip()
            .split()
        )
        if header == [oid.full_oid.encode(), b"missing"]:
            raise CoreFailure(
                "OBJECT_UNAVAILABLE", oid, "native object unavailable locally"
            )
        if len(header) != 3 or header[0] != oid.full_oid.encode():
            raise CoreFailure("GIT_INPUT", oid, "unexpected native object header")
        kind = header[1].decode("ascii", "replace")
        if kind not in kinds:
            raise CoreFailure(
                "RETENTION_PURPOSE", oid, "native type outside the requested Notes role"
            )
        size_raw = header[2]
        if not size_raw.isdigit() or len(size_raw) > 19:
            raise CoreFailure("GIT_INPUT", oid, "invalid declared native size")
        size = int(size_raw)
        if size > cap:
            raise CoreFailure(
                "BUDGET", oid, "native body exceeds configured per-object limit"
            )
        body = self._output(("cat-file", kind, oid.full_oid), size, work)
        if len(body) != size:
            raise CoreFailure(
                "NATIVE_INTEGRITY", oid, "native size changed or output truncated"
            )
        _prepay(work, "verification_bytes", len(body))
        native = NativeObject(oid, kind, body, size, hashlib.sha256(body).hexdigest())
        with account_verification(work):
            native.validate()
            if kind != "blob":
                parse_metadata(oid.object_format, kind, body)
        return native

    def metadata(self, oid: OID, work: WorkBudget) -> NativeObject:
        """Bounded production structural input; ordinary file blobs refused."""
        return self._native(
            oid, ("commit", "tree", "tag"), self.source.metadata_bytes, work
        )

    def lookup_ref_presence(self, name: bytes, work: WorkBudget) -> bool:
        return self.source.lookup_ref_presence(name, work)

    def note_body(self, proof: NotesProof, work: WorkBudget) -> NativeObject:
        """Read only the exact blob whose relevant structure the receiver checks."""
        from repo_catalog.domain.ref_observation import NotesMappingEvidence

        account_proof_bundle(proof.structures, work)
        with account_verification(work):
            proof.validate()
        if isinstance(proof, NotesMappingEvidence):
            root, note, scope = (
                proof.mapping.root_oid,
                proof.mapping.note_oid,
                proof.ref_claim.identity,
            )
        else:
            root, note, scope = proof.capture.root, proof.note, proof.capture.pair
        if root.object_format != self.object_format:
            raise CoreFailure("NATIVE_FORMAT", scope, "proof storage format mismatch")
        return self._native(note, ("blob",), work.limits.note_bytes, work)

    def _scan(self, nominated, work, observed):
        pending = bytearray()
        records = 0

        def consume(chunk):
            nonlocal records
            pending.extend(chunk)
            lines = pending.split(b"\n")
            pending[:] = lines.pop()
            for line in lines:
                _prepay(work, "metadata_units")
                records += 1
                if records > self.discovery_refs:
                    raise CoreFailure(
                        "BUDGET", "notes-discovery", "finite ref record limit"
                    )
                pieces = bytes(line).split(b"\0")
                if len(pieces) != 2:
                    raise CoreFailure(
                        "GIT_INPUT", "notes-discovery", "malformed ref record"
                    )
                name, raw_oid = pieces
                if not (name.startswith(b"refs/notes/") or name in nominated):
                    continue
                oid = OID(self.object_format, raw_oid.decode("ascii"))
                if name in observed:
                    raise CoreFailure("GIT_INPUT", name, "duplicate ref record")
                observed[name] = oid

        self._output(
            (
                "for-each-ref",
                "--format=%(refname)%00%(objectname)",
                "refs/notes/",
                *[os.fsdecode(n) for n in nominated],
            ),
            self.discovery_bytes,
            work,
            consume,
        )
        if pending:
            raise CoreFailure("GIT_INPUT", "notes-discovery", "unterminated ref record")

    def discover(
        self, work: WorkBudget, nominated: tuple[str, ...] = ()
    ) -> RefInventory:
        if not isinstance(nominated, tuple) or len(nominated) > self.discovery_refs:
            raise CoreFailure(
                "BUDGET", "notes-discovery", "finite nominated tuple required"
            )
        _prepay(work, "metadata_units", len(nominated))
        names = tuple(sorted(set(os.fsencode(n) for n in nominated)))
        if sum(len(n) for n in names) > self.discovery_bytes:
            raise CoreFailure(
                "BUDGET", "notes-discovery", "finite nominated ref byte limit"
            )
        for name in names:
            components = name.split(b"/")
            if (
                not name.startswith(b"refs/")
                or name.endswith((b"/", b"."))
                or any(c < 32 or c == 127 or c in b" ~^:?*[\\" for c in name)
                or b".." in name
                or b"@{" in name
                or any(
                    not component
                    or component.startswith(b".")
                    or component.endswith(b".lock")
                    for component in components
                )
            ):
                raise CoreFailure(
                    "NOTES_SCOPE", name, "exact valid full nominated ref required"
                )
        first, second = {}, {}
        scans = []
        try:
            self._scan(names, work, first)
            scans.append(RefScanSnapshot(tuple(first.items()), "complete"))
            self._scan(names, work, second)
            scans.append(RefScanSnapshot(tuple(second.items()), "complete"))
            _prepay(work, "metadata_units", len(first) + len(second))
            if first != second:
                return RefInventory(
                    scans[0].refs,
                    names,
                    "partial" if first else "unknown",
                    False,
                    "REF_CHANGED",
                    "local enumerations differ",
                    tuple(scans),
                )
            return RefInventory(
                scans[0].refs,
                names,
                "complete" if first else "known_empty",
                True,
                scans=tuple(scans),
            )
        except CoreFailure as error:
            current = first if not scans else second
            if current and len(scans) < 2:
                scans.append(RefScanSnapshot(tuple(current.items()), "partial"))
            return RefInventory(
                tuple(first.items()),
                names,
                "partial" if first else "unknown",
                False,
                error.code,
                str(error),
                tuple(scans),
            )
