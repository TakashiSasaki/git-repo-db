"""Opt-in production Notes acquisition. Public Schema 21 runtime is unchanged.

A discovery UUID pair denotes one original observation. Its first result and
Capture allocation are durably pinned in Operational before Core admission;
retry replays those exact metadata values. A new scan needs a new observation.
No body bytes enter progress storage. Core facts remain usable if it is lost.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import uuid4

from repo_catalog.application.ref_observations import (
    EnumeratedRef,
    RefScan,
    encode_metered,
    pin_scan,
)
from repo_catalog.domain.notes import (
    mapping_evidence,
    mapping_inventory,
    mapping_proof,
    ref_mapping_inventory,
)
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
from repo_catalog.domain.ref_observation import (
    NotesMappingGroup,
    RefObservationClaim,
    new_uuid7,
    uuid7_value,
)


@dataclass(frozen=True)
class Discovery:
    observation: GitObservation
    captures: tuple[Capture, ...]
    failure_code: str | None
    detail: str
    enumerations: tuple = ()


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


@dataclass(frozen=True)
class RefNoteAcquisition:
    claim: RefObservationClaim
    target: OID
    note: OID | None
    physical_copy_uuidv4: str | None
    role_verified: bool
    body_retained: bool
    failure_code: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class RefNotesInventory:
    group: NotesMappingGroup
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
        for value in (source.discovery_bytes, source.discovery_refs):
            if type(value) is not int or not 0 < value < 2**63:
                raise CoreFailure(
                    "BUDGET",
                    "notes-source",
                    "positive finite discovery bounds required",
                )
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
        max_pinned = min(self.source.discovery_bytes * 8 + 1_048_576, 128 * 1024 * 1024)
        saved = self.progress.load_bounded(scope, max_pinned)
        if saved is None:
            inventory = self.source.discover(self.work, nominated)
            scans = getattr(inventory, "scans", ())
            if (
                not isinstance(scans, tuple)
                or len(scans) > 2
                or inventory.terminal
                and len(scans) != 2
            ):
                raise CoreFailure(
                    "NOTES_SCOPE", scope, "original scan boundaries required"
                )
            count = len(inventory.refs) + sum(len(scan.refs) for scan in scans)
            self.work.require("metadata_units", count)
            self.work.charge("metadata_units", count)
            estimate = (
                4096
                + len(encode_metered(self.work, binding, max_pinned))
                + sum(2 * len(name) + 256 for name, _ in inventory.refs)
            )
            estimate += sum(
                2 * len(name) + 256 for scan in scans for name, _ in scan.refs
            )
            if estimate > max_pinned:
                raise CoreFailure("BUDGET", scope, "finite pinned discovery limit")
            self.work.require("input_bytes", estimate)
            try:
                candidate = {
                    "binding": binding,
                    "refs": [
                        [name.hex(), *oid.key, str(uuid4())]
                        for name, oid in inventory.refs
                    ],
                    "status": inventory.status,
                    "terminal": inventory.terminal,
                    "failure_code": inventory.failure_code,
                    "detail": inventory.detail,
                    "scans": [
                        [
                            scan.state,
                            [[name.hex(), *oid.key] for name, oid in scan.refs],
                        ]
                        for scan in scans
                    ],
                }
                serialized = encode(candidate)
                if len(serialized) > estimate:
                    raise CoreFailure(
                        "BUDGET", scope, "discovery encoding exceeded reservation"
                    )
            except BaseException:
                abandon = getattr(self.work, "abandon", None)
                if abandon:
                    abandon("input_bytes")
                else:
                    self.work.charge("input_bytes", estimate)
                raise
            self.work.charge("input_bytes", len(serialized))
            saved = self.progress.save_once_bounded(
                scope, candidate, max_pinned, encoded=serialized
            )
        if saved["binding"] != binding:
            raise CoreFailure(
                "INCOMPATIBLE_REPLAY", scope, "discovery identity cannot be rebound"
            )
        if saved["terminal"] and len(saved.get("scans", ())) != 2:
            raise CoreFailure(
                "CONTINUATION_UNAVAILABLE",
                scope,
                "original scan boundaries were not pinned",
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
        enumerations = []
        names = tuple(
            sorted(set(n.encode("utf-8", "surrogateescape") for n in nominated))
        )
        event_scope = (b"refs/notes/",)
        for index, (state, refs) in enumerate(saved.get("scans", ())):
            slot = encode(["p4-enumeration", origin_uuidv4, observation_uuidv4, index])
            scan_binding = [binding, self.source.scope, index]

            def scan(state=state, refs=refs):
                return RefScan(
                    tuple(
                        EnumeratedRef(
                            bytes.fromhex(name), OID(fmt, oid), form_known=False
                        )
                        for name, fmt, oid in refs
                    ),
                    state,
                    "git-for-each-ref:exit-0" if state == "complete" else None,
                )

            enumerations.append(
                pin_scan(
                    self.core,
                    self.progress,
                    self.work,
                    slot=slot,
                    binding=scan_binding,
                    origin=origin_uuidv4,
                    repository=repository_uuidv4,
                    source=source_attribution,
                    visibility=encode(
                        [self.source.scope, "git-for-each-ref:resolvable"]
                    ),
                    prefixes=event_scope,
                    nominated=names,
                    observed_at_us=observed_at_us,
                    byte_limit=self.source.discovery_bytes,
                    ref_limit=self.source.discovery_refs,
                    scan=scan,
                )
            )
        failure_code, detail = saved["failure_code"], saved["detail"]
        # A separate exact lookup is the only basis for a negative result;
        # for-each-ref may omit a dangling symbolic ref.
        known = {bytes.fromhex(ref[0]) for ref in saved["refs"]}
        lookup = getattr(self.source, "lookup_ref_presence", None)
        if lookup is not None and failure_code is None:
            for name in names:
                if name in known:
                    continue
                slot = encode(
                    ["p4-named-lookup", origin_uuidv4, observation_uuidv4, name.hex()]
                )

                def named_lookup(name=name):
                    present = lookup(name, self.work)
                    return RefScan(
                        (
                            EnumeratedRef(
                                name,
                                None,
                                absent=not present,
                                form_known=False,
                                absence_method="lookup",
                            ),
                        ),
                        "complete",
                        "git-show-ref-exists:" + ("0" if present else "2"),
                    )

                try:
                    enumerations.append(
                        pin_scan(
                            self.core,
                            self.progress,
                            self.work,
                            slot=slot,
                            binding=[binding, self.source.scope, name.hex()],
                            origin=origin_uuidv4,
                            repository=repository_uuidv4,
                            source=source_attribution,
                            visibility=encode(
                                [self.source.scope, "git-show-ref-exists"]
                            ),
                            prefixes=(),
                            nominated=(name,),
                            observed_at_us=observed_at_us,
                            byte_limit=self.source.discovery_bytes,
                            ref_limit=self.source.discovery_refs,
                            scan=named_lookup,
                        )
                    )
                except CoreFailure as error:
                    failure_code, detail = error.code, str(error)
                    break
        return Discovery(
            observation, captures, failure_code, detail, tuple(enumerations)
        )

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

    def inventory_ref(self, claim: RefObservationClaim) -> RefNotesInventory:
        """Pin and report one whole root-scoped inventory for this exact Claim."""
        repository = self._ready()
        if not isinstance(claim, RefObservationClaim) or claim.root_oid is None:
            raise CoreFailure("NOTES_ROLE", claim, "exact present-root claim required")
        projection = self.core.ref_observation(claim.ref_observation_key, self.work)
        if (
            projection.ref_observation.repository_uuidv4 != repository
            or claim not in projection.claims
        ):
            raise CoreFailure(
                "NOTES_SCOPE",
                claim.ref_observation_key,
                "exact repository and claim required",
            )
        identity = (
            *claim.ref_observation_key.key,
            encode_metered(self.work, claim.provenance.key),
        )
        slot = encode_metered(self.work, ["p4-ref-inventory", *identity])
        max_bytes = 64 * 1024 * 1024
        saved = self.progress.load_bounded(slot, max_bytes)
        if saved is None:
            status, members, _, failure = ref_mapping_inventory(
                claim,
                lambda oid: self.source.metadata(oid, self.work),
                self.work,
            )
            self.work.require("metadata_units", len(members))
            self.work.charge("metadata_units", len(members))
            estimate = 4096 + sum(
                2 * sum(len(part) for part in member) + 64 for member in members
            )
            if estimate > max_bytes:
                raise CoreFailure("BUDGET", slot, "finite inventory metadata limit")
            self.work.require("input_bytes", estimate)
            try:
                candidate = {
                    "verification_uuidv7": new_uuid7(),
                    "status": status,
                    "members": members,
                    "failure_code": None if failure is None else failure.code,
                    "detail": "" if failure is None else str(failure),
                }
                serialized = encode(candidate)
                if len(serialized) > estimate:
                    raise CoreFailure(
                        "BUDGET", slot, "inventory encoding exceeded reservation"
                    )
            except BaseException:
                abandon = getattr(self.work, "abandon", None)
                if abandon:
                    abandon("input_bytes")
                else:
                    self.work.charge("input_bytes", estimate)
                raise
            self.work.charge("input_bytes", len(serialized))
            saved = self.progress.save_once_bounded(
                slot, candidate, max_bytes, encoded=serialized
            )
        provenance = Provenance(
            self.source_attribution,
            saved["verification_uuidv7"],
            encode_metered(self.work, [*identity, "all-notes-mappings"]),
            "native-notes",
            "1",
            "reported",
        )
        members = saved["members"]
        if isinstance(members, list) and len(members) <= 100_000:
            self.work.require("metadata_units", len(members))
            self.work.charge("metadata_units", len(members))
        if (
            not isinstance(members, list)
            or len(members) > 100_000
            or any(
                not isinstance(member, list)
                or len(member) != 3
                or any(not isinstance(part, str) for part in member)
                for member in members
            )
        ):
            raise CoreFailure("NOTES_INVENTORY", slot, "invalid pinned inventory")
        upper = (
            2
            + len(members) * 16
            + sum(6 * sum(len(part) for part in member) for member in members)
        )
        if upper > max_bytes:
            raise CoreFailure("BUDGET", slot, "finite inventory encoding limit")
        self.work.require("input_bytes", upper)
        try:
            encoded_members = encode(members)
        except BaseException:
            abandon = getattr(self.work, "abandon", None)
            if abandon:
                abandon("input_bytes")
            else:
                self.work.charge("input_bytes", upper)
            raise
        self.work.charge("input_bytes", len(encoded_members))
        self.work.require("input_bytes", 2 * len(encoded_members))
        self.work.charge("input_bytes", 2 * len(encoded_members))
        group = NotesMappingGroup(
            claim,
            "git-notes",
            "1",
            "native-notes-tree",
            "all-notes-mappings",
            saved["status"],
            tuple(tuple(member) for member in members),
            provenance,
        )
        self.core.admit_notes_mapping_group(group, self.work)
        return RefNotesInventory(group, saved["failure_code"], saved["detail"])

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

    def acquire_ref_note(
        self,
        claim: RefObservationClaim,
        target: OID,
        *,
        retain_body=True,
        physical_copy_uuidv4=None,
    ) -> RefNoteAcquisition:
        """Build receiver evidence and retain only under this exact result Claim."""
        repository = self._ready()
        if not isinstance(claim, RefObservationClaim) or claim.root_oid is None:
            raise CoreFailure("NOTES_ROLE", claim, "exact present-root claim required")
        subject = self.core.ref_observation(claim.ref_observation_key, self.work)
        if (
            subject.ref_observation.repository_uuidv4 != repository
            or claim not in subject.claims
        ):
            raise CoreFailure(
                "NOTES_SCOPE",
                claim.ref_observation_key,
                "exact repository and claim required",
            )
        identity = (
            *claim.ref_observation_key.key,
            encode_metered(self.work, claim.provenance.key),
        )
        slot = encode_metered(
            self.work, ["p4-ref-note-verification", *identity, *target.key]
        )
        prior = self.progress.load_bounded(slot, 4096)
        verification_id = prior["verification_uuidv7"] if prior else new_uuid7()
        uuid7_value(verification_id)

        def receiver(value):
            return Provenance(
                "local-receiver",
                value,
                encode_metered(self.work, [*identity, *target.key]),
                "native-notes",
                "1",
                "receiver_intrinsic",
            )

        try:
            evidence = mapping_evidence(
                claim,
                target,
                lambda oid: self.source.metadata(oid, self.work),
                self.work,
                receiver(verification_id),
            )
            if prior is None:
                candidate = {"verification_uuidv7": verification_id}
                saved = self.progress.save_once_bounded(
                    slot,
                    candidate,
                    4096,
                    encoded=encode_metered(self.work, candidate, 4096),
                )
                uuid7_value(saved["verification_uuidv7"])
                evidence = replace(
                    evidence, provenance=receiver(saved["verification_uuidv7"])
                )
            self.core.admit_notes_mapping_evidence(evidence, self.work)
        except CoreFailure as error:
            if error.code in ("AUTHORITATIVE_CORRUPTION", "RECOVERY_STOP"):
                raise
            return RefNoteAcquisition(
                claim, target, None, None, False, False, error.code, str(error)
            )
        note = evidence.mapping.note_oid
        if not retain_body:
            return RefNoteAcquisition(claim, target, note, None, True, False)
        try:
            native = self.source.note_body(evidence, self.work)
            if physical_copy_uuidv4 is None:
                copy_scope = encode_metered(
                    self.work, ["p4-ref-note-copy", *identity, *evidence.mapping.key]
                )
                saved = self.progress.load_bounded(copy_scope, 4096)
                if saved is None:
                    candidate = {"physical_copy_uuidv4": str(uuid4())}
                    saved = self.progress.save_once_bounded(
                        copy_scope,
                        candidate,
                        4096,
                        encoded=encode_metered(self.work, candidate, 4096),
                    )
                physical_copy_uuidv4 = saved["physical_copy_uuidv4"]
                uuid4_value(physical_copy_uuidv4)
            self.core.admit_ref_note(evidence, native, physical_copy_uuidv4, self.work)
            return RefNoteAcquisition(
                claim, target, note, physical_copy_uuidv4, True, True
            )
        except CoreFailure as error:
            if error.code in ("AUTHORITATIVE_CORRUPTION", "RECOVERY_STOP"):
                raise
            return RefNoteAcquisition(
                claim, target, note, None, True, False, error.code, str(error)
            )
