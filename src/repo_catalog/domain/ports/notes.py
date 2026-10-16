"""Opt-in P4 source/progress ports; no dependency on a particular store engine."""

from __future__ import annotations

from typing import Protocol

from repo_catalog.domain.p1_core import OID, NativeObject, NotesProof
from repo_catalog.domain.ports.p1_core import WorkBudget


class NotesSource(Protocol):
    object_format: str

    def metadata(self, oid: OID, work: WorkBudget) -> NativeObject: ...
    def note_body(self, proof: NotesProof, work: WorkBudget) -> NativeObject: ...
    def discover(self, work: WorkBudget, nominated: tuple[str, ...] = ()): ...


class NotesProgress(Protocol):
    """Request-local metadata only. Loss refuses old continuation, never zeroes it."""

    def load(self, scope: str) -> dict | None: ...
    def save_once(self, scope: str, value: dict) -> dict: ...
