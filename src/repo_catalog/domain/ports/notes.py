"""Opt-in P4 source/progress ports; no dependency on a particular store engine."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from repo_catalog.domain.p1_core import OID, NativeObject, NotesProof
from repo_catalog.domain.ports.p1_core import WorkBudget


class NotesSource(Protocol):
    object_format: str
    scope: str
    discovery_bytes: int
    discovery_refs: int

    def metadata(self, oid: OID, work: WorkBudget) -> NativeObject: ...
    def note_body(self, proof: NotesProof, work: WorkBudget) -> NativeObject: ...
    def discover(self, work: WorkBudget, nominated: tuple[str, ...] = ()): ...


class NotesProgress(Protocol):
    """Request-local metadata only. Loss refuses old continuation, never zeroes it."""

    def bind(
        self,
        repository,
        instance,
        source_attribution,
        source_scope,
        work,
        *,
        catalog_repository_uuidv4: str | None = None,
    ) -> None: ...

    def load(self, scope: str) -> dict | None: ...
    def scan_guard(self, scope: str) -> AbstractContextManager[None]: ...
    def save_once(self, scope: str, value: dict) -> dict: ...
    def load_bounded(self, scope: str, max_bytes: int) -> dict | None: ...
    def save_once_bounded(
        self, scope: str, value: dict, max_bytes: int, *, encoded: str
    ) -> dict: ...


def request_scope(
    repository_uuidv4, catalog_instance_uuidv4, source_attribution, source_scope
):
    """Exact explicit Notes request intent, independent of per-attempt limits."""
    from repo_catalog.domain.p1_core import CoreFailure, encode, uuid4_value

    uuid4_value(repository_uuidv4)
    uuid4_value(catalog_instance_uuidv4)
    if not source_attribution or not source_scope:
        raise CoreFailure(
            "NOTES_SCOPE", "request", "actual source attribution/scope required"
        )
    return encode(
        [
            repository_uuidv4,
            catalog_instance_uuidv4,
            source_attribution,
            "p4-notes/1",
            source_scope,
        ]
    )
