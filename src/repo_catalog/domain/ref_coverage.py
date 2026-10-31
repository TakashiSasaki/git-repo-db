"""Receiver-checked completeness of one ref Claim's Notes inventory.

The evidence is one whole supported traversal. It is not source authentication,
file-body availability, or permission to combine independently partial groups.
"""

import json
from dataclasses import dataclass

from repo_catalog.domain.p1_core import (
    OID,
    CoreCoverageScope,
    CoreFailure,
    NativeObject,
    Provenance,
    encode,
)
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.ref_observation import NotesMappingGroup

REF_NOTES_INVENTORY = "notes-mapping-inventory"


class LocalRefCoverageWork:
    """Finite implicit budget for a metadata-only Coverage read without a caller ledger."""

    def __init__(self, max_bytes: int):
        if type(max_bytes) is not int or not 0 < max_bytes < 2**63:
            raise CoreFailure(
                "QUERY_BUDGET", "ref-coverage", "positive finite byte limit required"
            )
        self.remaining = {"input_bytes": 16 * max_bytes + 4096, "metadata_units": 64}
        self.pending = {}

    def require(self, unit: str, amount: int = 1) -> None:
        if type(amount) is not int or amount < 0 or unit in self.pending:
            raise CoreFailure("QUERY_BUDGET", unit, "invalid work reservation")
        if unit not in self.remaining or amount > self.remaining[unit]:
            raise CoreFailure("QUERY_BUDGET", unit, "finite local Coverage read budget")
        self.remaining[unit] -= amount
        self.pending[unit] = amount

    def charge(self, unit: str, amount: int) -> None:
        reserved = self.pending.pop(unit)
        if type(amount) is not int or not 0 <= amount <= reserved:
            raise CoreFailure("QUERY_BUDGET", unit, "invalid charged work")
        self.remaining[unit] += reserved - amount

    def abandon(self, unit: str) -> None:
        # A rejected read cannot refund work already reserved and attempted.
        self.pending.pop(unit)


@dataclass(frozen=True)
class RefNotesInventoryCoverageProof:
    coverage_claim: CoverageClaim
    group: NotesMappingGroup
    verification_provenance: Provenance
    structures: tuple[NativeObject, ...]

    def __post_init__(self) -> None:
        claim, group, provenance = (
            self.coverage_claim,
            self.group,
            self.verification_provenance,
        )
        if (
            not isinstance(claim, CoverageClaim)
            or not isinstance(claim.scope, CoreCoverageScope)
            or not isinstance(group, NotesMappingGroup)
            or not isinstance(provenance, Provenance)
            or claim.scope.owner_kind != "ref_observation"
            or claim.scope.coordinates
            != (*group.ref_claim.ref_observation_key.key, REF_NOTES_INVENTORY)
            or claim.state != "complete"
            or (
                group.interpretation_kind,
                group.interpretation_version,
                group.interpretation_scope,
                group.group_scope,
            )
            != ("git-notes", "1", "native-notes-tree", "all-notes-mappings")
            or group.status not in ("complete", "known_empty")
            or provenance.qualification != "receiver_intrinsic"
            or provenance.decoder != "git-native-notes-inventory"
            or provenance.decoder_version != "1"
            or type(self.structures) is not tuple
            or not self.structures
        ):
            raise CoreFailure(
                "REF_COVERAGE_PROOF",
                "notes-inventory",
                "exact typed terminal evidence required",
            )


def _charge(work, unit, amount=1):
    work.require(unit, amount)
    work.charge(unit, amount)


def serialize_structures(structures, work, *, max_structures, max_bytes):
    """Reserve each actual scan and encoded byte before creating the bundle."""
    if (
        type(max_structures) is not int
        or not 0 < max_structures < 2**63
        or type(max_bytes) is not int
        or not 0 < max_bytes < 2**63
        or type(structures) is not tuple
        or not 0 < len(structures) <= max_structures
    ):
        raise CoreFailure("BUDGET", "ref-coverage", "finite structure limits required")
    upper = 2
    for native in structures:
        _charge(work, "proof_steps")
        if (
            not isinstance(native, NativeObject)
            or not isinstance(native.object_oid, OID)
            or type(native.native_type) is not str
            or len(native.native_type) > 6
            or native.native_type not in ("commit", "tree")
            or type(native.body) is not bytes
            or type(native.declared_size) is not int
            or not 0 <= native.declared_size < 2**63
            or type(native.digest_sha256) is not str
            or len(native.digest_sha256) != 64
        ):
            raise CoreFailure(
                "REF_COVERAGE_PROOF", "structure", "typed native structure required"
            )
        upper += 256 + 2 * len(native.body)
        if upper > max_bytes:
            raise CoreFailure(
                "BUDGET", "ref-coverage", "finite encoded structure limit"
            )
    work.require("input_bytes", upper)
    try:
        result = encode(
            [
                [
                    *native.object_oid.key,
                    native.native_type,
                    native.body.hex(),
                    native.declared_size,
                    native.digest_sha256,
                ]
                for native in structures
            ]
        )
        if len(result) > upper:
            raise CoreFailure(
                "BUDGET", "ref-coverage", "structure encoding exceeded reservation"
            )
    except BaseException:
        abandon = getattr(work, "abandon", None)
        if abandon is None:
            work.charge("input_bytes", upper)
        else:
            abandon("input_bytes")
        raise
    work.charge("input_bytes", len(result))
    return result


def deserialize_structures(value, work, *, max_structures, max_bytes):
    """Decode only a bounded, canonical structure bundle and charge the work."""
    if type(value) is not str or len(value) > max_bytes:
        raise CoreFailure(
            "QUERY_BUDGET", "ref-coverage", "finite structure bundle required"
        )
    _charge(work, "input_bytes", len(value))
    try:
        data = json.loads(value)
        if type(data) is not list or not data:
            raise ValueError("nonempty structure list required")
        if len(data) > max_structures:
            raise CoreFailure(
                "QUERY_BUDGET", "ref-coverage", "finite structure count limit"
            )
        structures = []
        for entry in data:
            _charge(work, "proof_steps")
            if (
                type(entry) is not list
                or len(entry) != 6
                or type(entry[3]) is not str
                or len(entry[3]) % 2
                or len(entry[3]) > max_bytes
            ):
                raise ValueError("invalid structure coordinates")
            _charge(work, "input_bytes", len(entry[3]))
            body = bytes.fromhex(entry[3])
            structures.append(
                NativeObject(
                    OID(entry[0], entry[1]), entry[2], body, entry[4], entry[5]
                )
            )
        result = tuple(structures)
        if (
            serialize_structures(
                result, work, max_structures=max_structures, max_bytes=max_bytes
            )
            != value
        ):
            raise ValueError("noncanonical structure bundle")
        return result
    except CoreFailure:
        raise
    except (TypeError, ValueError, IndexError, RecursionError) as error:
        raise CoreFailure(
            "REF_COVERAGE_PROOF", "structure", "invalid structure bundle"
        ) from error


def verify_ref_notes_inventory(proof, work, *, max_structures, max_bytes):
    """Replay the complete supported Notes grammar over this exact ordered input."""
    from repo_catalog.domain.notes import ref_mapping_inventory

    if not isinstance(proof, RefNotesInventoryCoverageProof):
        raise CoreFailure(
            "REF_COVERAGE_PROOF", "notes-inventory", "typed proof required"
        )
    bundle = serialize_structures(
        proof.structures, work, max_structures=max_structures, max_bytes=max_bytes
    )
    index = 0

    def read(object_oid):
        nonlocal index
        if index == len(proof.structures):
            raise CoreFailure(
                "OBJECT_UNAVAILABLE", object_oid, "structural frontier remains"
            )
        native = proof.structures[index]
        if native.object_oid != object_oid:
            raise CoreFailure(
                "REF_COVERAGE_PROOF", object_oid, "out-of-order structure"
            )
        _charge(work, "input_bytes", len(native.body))
        index += 1
        return native

    status, members, consumed, failure = ref_mapping_inventory(
        proof.group.ref_claim, read, work
    )
    if failure is not None and failure.code in ("BUDGET", "QUERY_BUDGET"):
        raise failure
    _charge(
        work,
        "metadata_units",
        len(members) + len(proof.group.members) + len(consumed) + len(proof.structures),
    )
    if (
        failure is not None
        or index != len(proof.structures)
        or consumed != proof.structures
        or status != proof.group.status
        or members != proof.group.members
    ):
        raise CoreFailure(
            "REF_COVERAGE_PROOF",
            "notes-inventory",
            "complete traversal does not match group",
        )
    return bundle
