"""Opt-in P4 source/progress ports; no dependency on a particular store engine."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from repo_catalog.domain.p1_core import OID, NativeObject
from repo_catalog.domain.ports.p1_core import WorkBudget
from repo_catalog.domain.ref_observation import NotesMappingEvidence
from repo_catalog.domain.request_scope import request_scope as request_scope


class NotesSource(Protocol):
    object_format: str
    scope: str
    discovery_bytes: int
    discovery_refs: int

    def metadata(self, object_oid: OID, work: WorkBudget) -> NativeObject: ...
    def note_body(
        self, proof: NotesMappingEvidence, work: WorkBudget
    ) -> NativeObject: ...
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
    def request_identity(self) -> tuple[str, str]: ...
    def scan_guard(self, scope: str) -> AbstractContextManager[None]: ...
    def save_once(self, scope: str, value: dict) -> dict: ...
    def load_bounded(self, scope: str, max_bytes: int) -> dict | None: ...
    def save_once_bounded(
        self, scope: str, value: dict, max_bytes: int, *, encoded: str
    ) -> dict: ...
