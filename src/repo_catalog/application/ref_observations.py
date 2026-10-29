"""Issue and replay actual bounded local ref enumeration observations.

Operational pins the entire result before Core admission; no native object
bodies are staged here. A lost pin cannot be reconstructed from a fresh scan.
"""

from __future__ import annotations

from dataclasses import dataclass

from repo_catalog.domain.p1_core import OID, CoreFailure, Provenance, encode
from repo_catalog.domain.ref_observation import (
    RefAbsenceEvidence,
    RefEnumerationLink,
    RefEnumerationObservation,
    RefEnumerationResult,
    RefObservation,
    RefObservationClaim,
    RefObservationKey,
    new_uuid7,
)


@dataclass(frozen=True)
class EnumeratedRef:
    name: bytes
    target: OID | None
    symbolic_target: bytes | None = None
    peeled: OID | None = None
    absent: bool = False
    form_known: bool = True
    absence_method: str = "enumeration"

    def __post_init__(self):
        if (
            type(self.name) is not bytes
            or not self.name.startswith(b"refs/")
            or b"\0" in self.name
            or self.target is not None
            and not isinstance(self.target, OID)
            or self.peeled is not None
            and (not isinstance(self.peeled, OID) or self.target is None)
            or self.peeled is not None
            and isinstance(self.peeled, OID)
            and isinstance(self.target, OID)
            and self.peeled.object_format != self.target.object_format
            or self.symbolic_target is not None
            and (
                type(self.symbolic_target) is not bytes
                or not self.symbolic_target.startswith(b"refs/")
                or b"\0" in self.symbolic_target
                or not self.form_known
            )
            or type(self.absent) is not bool
            or type(self.form_known) is not bool
            or self.absence_method not in ("lookup", "enumeration")
            or self.absent
            and (
                self.target is not None
                or self.symbolic_target is not None
                or self.peeled is not None
            )
        ):
            raise CoreFailure("REF", "scan", "invalid original ref result")


@dataclass(frozen=True)
class RefScan:
    refs: tuple[EnumeratedRef, ...]
    state: str
    completion: str | None

    def __post_init__(self):
        if (
            type(self.refs) is not tuple
            or self.state not in ("complete", "partial", "unknown")
            or self.state == "complete"
            and (not isinstance(self.completion, str) or not self.completion)
            or self.state != "complete"
            and self.completion is not None
        ):
            raise CoreFailure("ENUMERATION", "scan", "invalid original scan result")


def _charge(work, unit, amount):
    work.require(unit, amount)
    work.charge(unit, amount)


def encode_metered(work, value, limit=64 * 1024 * 1024):
    """Reserve a finite conservative bound before encoding caller metadata."""
    pending = [value]
    upper = 0
    nodes = 0
    scheduled = 1
    _charge(work, "metadata_units", 1)
    while pending:
        item = pending.pop()
        nodes += 1
        if nodes > 1_000_000:
            raise CoreFailure("BUDGET", "encoding", "finite value count")
        if isinstance(item, str):
            upper += 2 + 12 * len(item)
        elif isinstance(item, (tuple, list)):
            upper += 2 + len(item)
            scheduled += len(item)
            if scheduled > 1_000_000:
                raise CoreFailure("BUDGET", "encoding", "finite value count")
            _charge(work, "metadata_units", len(item))
            pending.extend(item)
        elif isinstance(item, dict):
            upper += 2 + 2 * len(item)
            scheduled += 2 * len(item)
            if scheduled > 1_000_000:
                raise CoreFailure("BUDGET", "encoding", "finite value count")
            _charge(work, "metadata_units", 2 * len(item))
            for key, child in item.items():
                if not isinstance(key, str):
                    raise CoreFailure("REQUEST", "encoding", "text keys required")
                pending.extend((key, child))
        elif item is None or type(item) is bool:
            upper += 5
        elif type(item) is int and -(2**63) <= item < 2**63:
            upper += 21
        else:
            raise CoreFailure("REQUEST", "encoding", "bounded JSON values required")
        if upper > limit:
            raise CoreFailure("BUDGET", "encoding", "finite metadata encoding limit")
    work.require("input_bytes", upper)
    try:
        result = encode(value)
    except BaseException:
        abandon = getattr(work, "abandon", None)
        if abandon:
            abandon("input_bytes")
        else:
            work.charge("input_bytes", upper)
        raise
    work.charge("input_bytes", len(result))
    return result


def pin_scan(
    core,
    progress,
    work,
    *,
    slot,
    binding,
    origin,
    repository,
    source,
    visibility,
    prefixes,
    nominated,
    observed_at_us,
    byte_limit,
    ref_limit,
    scan,
):
    """Persist the first returned scan in a request-local slot, then admit it.

    Callers create a fresh slot for every actual reread. Reusing a slot is
    redelivery, never an instruction to repeat Git I/O with its old identity.
    """
    max_pinned = min(byte_limit * 4 + 1_048_576, 128 * 1024 * 1024)
    saved = progress.load_bounded(slot, max_pinned)
    if saved is None:
        result = scan()
        if not isinstance(result, RefScan) or len(result.refs) > ref_limit + len(
            nominated
        ):
            raise CoreFailure("BUDGET", slot, "bounded scan result required")
        names = set()
        for ref in result.refs:
            _charge(work, "metadata_units", 1)
            if not isinstance(ref, EnumeratedRef):
                raise CoreFailure("ENUMERATION", slot, "typed scan item required")
            if (
                ref.name in names
                or not (
                    ref.name in nominated
                    or any(ref.name.startswith(prefix) for prefix in prefixes)
                )
                or ref.absent
                and (result.state != "complete" or ref.name not in nominated)
            ):
                raise CoreFailure(
                    "ENUMERATION", slot, "scan result outside original scope"
                )
            names.add(ref.name)
        # Reserve serialization work prior to creating hex strings or JSON.
        _charge(work, "metadata_units", len(result.refs))
        size = (
            4096
            + len(encode_metered(work, binding, max_pinned))
            + sum(
                2 * len(r.name)
                + (0 if r.symbolic_target is None else 2 * len(r.symbolic_target))
                + 512
                for r in result.refs
            )
        )
        if size > max_pinned or size >= 2**63:
            raise CoreFailure("BUDGET", slot, "finite pinned scan size")
        _charge(work, "metadata_units", 1 + len(result.refs))
        work.require("input_bytes", size)
        try:
            event_id = new_uuid7()
            completion = (
                None
                if result.completion is None
                else encode([origin, event_id, result.completion])
            )
            candidate = {
                "binding": binding,
                "event": event_id,
                "state": result.state,
                "completion": completion,
                "refs": [
                    [
                        r.name.hex(),
                        None if r.target is None else list(r.target.key),
                        None if r.symbolic_target is None else r.symbolic_target.hex(),
                        None if r.peeled is None else list(r.peeled.key),
                        r.absent,
                        new_uuid7(),
                        r.form_known,
                        r.absence_method,
                    ]
                    for r in result.refs
                ],
            }
            serialized = encode(candidate)
            if len(serialized) > size:
                raise CoreFailure("BUDGET", slot, "scan encoding exceeded reservation")
        except BaseException:
            abandon = getattr(work, "abandon", None)
            if abandon:
                abandon("input_bytes")
            else:
                work.charge("input_bytes", size)
            raise
        work.charge("input_bytes", len(serialized))
        saved = progress.save_once_bounded(
            slot, candidate, max_pinned, encoded=serialized
        )
    if saved.get("binding") != binding:
        raise CoreFailure("INCOMPATIBLE_REPLAY", slot, "scan slot cannot be rebound")
    event = RefEnumerationObservation(
        origin,
        saved["event"],
        repository,
        source,
        visibility,
        prefixes,
        nominated,
        saved["state"],
        saved["completion"],
        observed_at_us,
        byte_limit,
        ref_limit,
        len(saved["refs"]),
    )
    links = []
    for position, (
        raw_name,
        raw_target,
        raw_symbolic,
        raw_peeled,
        absent,
        obs_id,
        form_known,
        absence_method,
    ) in enumerate(saved["refs"]):
        _charge(work, "metadata_units", 1)
        _charge(
            work,
            "input_bytes",
            len(raw_name) + (len(raw_symbolic) if raw_symbolic else 0),
        )
        name = bytes.fromhex(raw_name)
        key = RefObservationKey(origin, obs_id)
        obs = RefObservation(key, repository, name, source, visibility, observed_at_us)
        provenance = Provenance(
            source, encode(event.identity), name.hex(), "local-git-ref", "1"
        )
        target = None if raw_target is None else OID(*raw_target)
        symbolic = None if raw_symbolic is None else bytes.fromhex(raw_symbolic)
        peeled = None if raw_peeled is None else OID(*raw_peeled)
        if absent:
            absence = RefAbsenceEvidence(
                source,
                visibility,
                name,
                absence_method,
                event.completion_coordinate,
                name if absence_method == "enumeration" else None,
                "complete" if absence_method == "enumeration" else None,
            )
            claim = RefObservationClaim(
                key, provenance, "absent", absence_evidence=absence
            )
            derivation = "absence"
        else:
            claim = RefObservationClaim(
                key,
                provenance,
                "present",
                ref_form=None
                if not form_known
                else None
                if target is None and symbolic is None
                else "symbolic"
                if symbolic
                else "direct",
                direct_target_oid=target
                if form_known and target is not None and symbolic is None
                else None,
                symbolic_target_ref_name=symbolic if form_known else None,
                resolved_target_oid=target
                if form_known and symbolic is not None
                else None,
                peeled_target_oid=peeled,
                root_oid=target,
            )
            derivation = "item"
        links.append(RefEnumerationLink(event, obs, claim, derivation, position))
    links = tuple(links)
    core.admit_ref_enumeration(event, links, work)
    return RefEnumerationResult(event, links)
