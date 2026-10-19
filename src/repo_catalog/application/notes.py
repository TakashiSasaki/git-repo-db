"""Opt-in production Notes acquisition. Public Schema 21 runtime is unchanged.

A discovery UUID pair denotes one original observation. Its first result and
Capture allocation are durably pinned in Operational before Core admission;
retry replays those exact metadata values. A new scan needs a new observation.
No body bytes enter progress storage. Core facts remain usable if it is lost.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from repo_catalog.domain.notes import mapping_inventory, mapping_proof
from repo_catalog.domain.p1_core import (
    OID,
    Capture,
    CoreFailure,
    GitObservation,
    Provenance,
    encode,
    uuid4_value,
)
from repo_catalog.domain.ports.notes import NotesProgress, NotesSource


@dataclass(frozen=True)
class Discovery:
    observation: GitObservation
    captures: tuple[Capture, ...]
    failure_code: str | None
    detail: str


@dataclass(frozen=True)
class NoteAcquisition:
    capture: Capture
    target: OID
    note: OID | None
    physical_copy_uuidv4: str | None
    role_verified: bool
    body_retained: bool
    failure_code: str | None = None
    detail: str = ""


class NotesAcquisition:
    def __init__(
        self,
        core,
        source: NotesSource,
        work,
        progress: NotesProgress,
        *,
        source_attribution: str,
        repository_uuidv4: str | None = None,
    ):
        self.core, self.source, self.work, self.progress = core, source, work, progress
        self.source_attribution = source_attribution
        if repository_uuidv4 is not None:
            uuid4_value(repository_uuidv4)
        self.repository_uuidv4 = repository_uuidv4
        self._ready()

    def _ready(self):
        # Metadata read crosses the supported catalog stop gate before input I/O.
        self.core.ensure_available()
        self.work.require("metadata_units", 1)
        self.work.charge("metadata_units", 1)
        catalog_seed, instance = self.core.catalog_identity()
        repository = self.repository_uuidv4 or catalog_seed
        self.progress.bind(
            repository,
            instance,
            self.source_attribution,
            self.source.scope,
            self.work,
            catalog_repository_uuidv4=catalog_seed,
        )
        return repository

    def discover(
        self,
        repository_uuidv4: str,
        source_attribution: str,
        origin_uuidv4: str,
        observation_uuidv4: str,
        observed_at_us: int,
        nominated: tuple[str, ...] = (),
    ) -> Discovery:
        actual_repository = self._ready()
        if (
            repository_uuidv4 != actual_repository
            or source_attribution != self.source_attribution
        ):
            raise CoreFailure(
                "NOTES_SCOPE", "discovery", "request source/repository mismatch"
            )
        for value in (repository_uuidv4, origin_uuidv4, observation_uuidv4):
            uuid4_value(value)
        if type(observed_at_us) is not int or not 0 < observed_at_us < 2**63:
            raise CoreFailure(
                "TIME", "notes-discovery", "positive int64 epoch microseconds required"
            )
        scope = encode(["p4-discovery", origin_uuidv4, observation_uuidv4])
        binding = [
            repository_uuidv4,
            source_attribution,
            observed_at_us,
            sorted(set(nominated)),
        ]
        saved = self.progress.load(scope)
        if saved is None:
            inventory = self.source.discover(self.work, nominated)
            saved = self.progress.save_once(
                scope,
                {
                    "binding": binding,
                    "refs": [
                        [name.hex(), *oid.key, str(uuid4())]
                        for name, oid in inventory.refs
                    ],
                    "status": inventory.status,
                    "terminal": inventory.terminal,
                    "failure_code": inventory.failure_code,
                    "detail": inventory.detail,
                },
            )
        if saved["binding"] != binding:
            raise CoreFailure(
                "INCOMPATIBLE_REPLAY", scope, "discovery identity cannot be rebound"
            )
        captures = tuple(
            Capture(
                origin_uuidv4,
                capture_id,
                repository_uuidv4,
                source_attribution,
                bytes.fromhex(name).decode("utf-8", "surrogateescape"),
                OID(fmt, oid),
            )
            for name, fmt, oid, capture_id in saved["refs"]
        )
        provenance = Provenance(
            source_attribution,
            encode([origin_uuidv4, observation_uuidv4]),
            "local-notes-discovery",
            "p4-notes",
            "1",
        )
        observation = GitObservation(
            origin_uuidv4,
            observation_uuidv4,
            repository_uuidv4,
            "snapshot",
            ("local-notes-refs", source_attribution, tuple(binding[3])),
            {
                "roots": [list(c.root.key) for c in captures],
                "predecessor": None,
                "observed_at_us": observed_at_us,
                "source": source_attribution,
                "refs": [{"ref": c.ref, "target": list(c.root.key)} for c in captures],
                "enumeration_state": saved["status"],
                "terminal_observation": saved["terminal"],
            },
            provenance,
        )
        self.work.require("metadata_units", 1 + len(captures))
        self.work.charge("metadata_units", 1 + len(captures))
        self.core.admit_observation(observation)
        for capture in captures:
            self.core.admit_capture(capture)
        return Discovery(observation, captures, saved["failure_code"], saved["detail"])

    def inventory(self, capture):
        actual_repository = self._ready()
        if capture.repository_uuidv4 != actual_repository:
            raise CoreFailure(
                "NOTES_SCOPE", capture.pair, "request source/repository mismatch"
            )
        self.core.admit_capture(capture)
        result = mapping_inventory(
            capture, lambda oid: self.source.metadata(oid, self.work), self.work
        )
        self.core.admit_notes_inventory(result, self.work)
        return result

    def acquire_note(
        self, capture, target, *, retain_body=True, physical_copy_uuidv4=None
    ):
        actual_repository = self._ready()
        if capture.repository_uuidv4 != actual_repository:
            raise CoreFailure(
                "NOTES_SCOPE", capture.pair, "request source/repository mismatch"
            )
        self.core.admit_capture(capture)
        try:
            proof = mapping_proof(
                capture,
                target,
                lambda oid: self.source.metadata(oid, self.work),
                self.work,
            )
        except CoreFailure as error:
            return NoteAcquisition(
                capture, target, None, None, False, False, error.code, str(error)
            )
        # Independently admissible role metadata survives body input refusal.
        self.core.admit_notes_role(proof, self.work)
        if not retain_body:
            return NoteAcquisition(capture, target, proof.note, None, True, False)
        try:
            native = self.source.note_body(proof, self.work)
            if physical_copy_uuidv4 is None:
                scope = encode(
                    [
                        "p4-note-copy",
                        *capture.pair,
                        *target.key,
                        *proof.note.key,
                        proof.path,
                    ]
                )
                saved = self.progress.load(scope)
                if saved is None:
                    saved = self.progress.save_once(
                        scope, {"physical_copy_uuidv4": str(uuid4())}
                    )
                physical_copy_uuidv4 = saved["physical_copy_uuidv4"]
            self.core.admit_note(proof, native, physical_copy_uuidv4, self.work)
            return NoteAcquisition(
                capture, target, proof.note, physical_copy_uuidv4, True, True
            )
        except CoreFailure as error:
            return NoteAcquisition(
                capture, target, proof.note, None, True, False, error.code, str(error)
            )
