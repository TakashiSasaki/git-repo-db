"""Receiver-checked Notes mapping grammar and Claim-scoped terminal evidence.

Only commit/tree structural representations are read. Targets, note bodies and
unrelated descendant trees are never dependencies of a narrow mapping proof.
Inventory closure is stronger: every entry must belong to the supported grammar.
"""

from __future__ import annotations

import re
from typing import Callable, Literal

from repo_catalog.domain.git_native import parse_metadata
from repo_catalog.domain.p1_core import (
    OID,
    CoreFailure,
    NativeObject,
    account_verification,
)
from repo_catalog.domain.ports.p1_core import WorkBudget

Status = Literal["unknown", "partial", "known_empty", "complete"]
MetadataReader = Callable[[OID], NativeObject]
GRAMMAR = "p4-notes/1"


def _charge(work: WorkBudget, unit: str, amount: int = 1) -> None:
    work.require(unit, amount)
    work.charge(unit, amount)


def account_proof_bundle(
    structures: tuple[NativeObject, ...], work: WorkBudget
) -> None:
    """Charge canonical proof materialization before allocating encoded bodies."""
    size = 2 + max(0, len(structures) - 1)
    for structure in structures:
        _charge(work, "proof_steps")
        if structure.native_type not in ("commit", "tree"):
            raise CoreFailure("NOTES_ROLE", "proof", "structural type required")
        size += (
            4
            + len(structure.oid.full_oid)
            + 2
            + len(structure.native_type)
            + 2
            + 2 * len(structure.body)
            + 2
        )
    if size > 64 * 1024 * 1024:
        raise CoreFailure("BUDGET", "proof", "finite encoded proof limit")
    _charge(work, "input_bytes", size)


def _structure(oid: OID, read: MetadataReader, work: WorkBudget):
    # Charge the attempted operation before calling a potentially failing source.
    # Input bytes are separately metered by the actual source reader.
    _charge(work, "proof_steps")
    _charge(work, "metadata_units")
    native = read(oid)
    if not isinstance(native, NativeObject) or native.oid != oid:
        raise CoreFailure(
            "NATIVE_INTEGRITY", oid, "structural reader returned wrong OID"
        )
    if native.native_type not in ("commit", "tree"):
        raise CoreFailure("NOTES_ROLE", oid, "Notes root/path must be commit or tree")
    native.validate()
    parsed = parse_metadata(oid.object_format, native.native_type, native.body)
    return native, parsed


def _entries(parsed, work):
    result = {}
    for coordinate, _fmt, target in parsed.relations["tree_entries"]:
        _charge(work, "metadata_units")
        result[bytes.fromhex(coordinate[1])] = (coordinate[0], target)
    return result


def _mapping_path(
    root: OID,
    owner: object,
    target: OID,
    read_metadata: MetadataReader,
    work: WorkBudget,
):
    """Acquire exactly the relevant mapping path; unsupported paths fail closed."""
    if target.object_format != root.object_format:
        raise CoreFailure("NOTES_ROLE", (owner, target), "target format mismatch")
    structures, path = [], []
    current, suffix = root, target.full_oid
    with account_verification(work):
        while True:
            native, parsed = _structure(current, read_metadata, work)
            structures.append(native)
            if len(structures) == 1 and native.native_type == "commit":
                current = OID(
                    current.object_format, parsed.relations["commit_tree"][0][2]
                )
                continue
            if native.native_type != "tree":
                raise CoreFailure(
                    "NOTES_ROLE", current, "only the root can be a commit"
                )
            entries = _entries(parsed, work)
            leaf, directory = suffix.encode("ascii"), suffix[:2].encode("ascii")
            if leaf in entries:
                mode, note = entries[leaf]
                if mode != "100644" or (len(suffix) > 2 and directory in entries):
                    raise CoreFailure(
                        "NOTES_ROLE",
                        (owner, target),
                        "ambiguous or non-note leaf",
                    )
                path.append(suffix)
                return (
                    OID(current.object_format, note),
                    "/".join(path),
                    tuple(structures),
                )
            if (
                len(suffix) <= 2
                or directory not in entries
                or entries[directory][0] != "40000"
            ):
                raise CoreFailure(
                    "NOTES_ROLE",
                    (owner, target),
                    "target has no supported Notes mapping",
                )
            path.append(suffix[:2])
            suffix, current = (
                suffix[2:],
                OID(current.object_format, entries[directory][1]),
            )


def mapping_evidence(
    ref_claim, target: OID, read_metadata: MetadataReader, work: WorkBudget, provenance
):
    """Acquire the relevant path without inventing a legacy Capture."""
    from repo_catalog.domain.ref_observation import (
        NotesMapping,
        NotesMappingEvidence,
        RefObservationClaim,
    )

    if not isinstance(ref_claim, RefObservationClaim) or ref_claim.root_oid is None:
        raise CoreFailure("NOTES_ROLE", ref_claim, "claim with exact root required")
    note, path, structures = _mapping_path(
        ref_claim.root_oid, ref_claim.identity, target, read_metadata, work
    )
    mapping = NotesMapping(
        ref_claim.root_oid, "git-notes", "1", "native-notes-tree", target, note, path
    )
    evidence = NotesMappingEvidence(
        ref_claim, mapping, "single-path", provenance, structures
    )
    account_proof_bundle(structures, work)
    with account_verification(work):
        evidence.validate()
    return evidence


def _mapping_inventory(
    root: OID, owner: object, read_metadata: MetadataReader, work: WorkBudget
):
    """Deterministic depth-first native-order inventory with positive terminal.

    The first refusal stops traversal. Already checked mappings remain partial.
    A complete/known-empty result requires exhausting the entire supported tree
    grammar. A tree's unrelated valid entry prevents terminal closure, rather
    than being omitted. No body availability is promised by this inventory.
    """
    structures: list[NativeObject] = []
    members: list[tuple[str, str, str]] = []
    targets: set[str] = set()
    fmt = root.object_format
    width = len(root.full_oid)

    def read(oid):
        native, parsed = _structure(oid, read_metadata, work)
        structures.append(native)
        return native, parsed

    def walk(oid, prefix, path, chain, is_root=False):
        native, parsed = read(oid)
        chain = (*chain, native)
        if is_root and native.native_type == "commit":
            walk(OID(fmt, parsed.relations["commit_tree"][0][2]), prefix, path, chain)
            return
        if native.native_type != "tree":
            raise CoreFailure("NOTES_INVENTORY", oid, "fanout child must be a tree")
        entries = _entries(parsed, work)
        for raw_name, (mode, linked) in entries.items():
            _charge(work, "metadata_units")
            try:
                name = raw_name.decode("ascii")
            except UnicodeError as error:
                raise CoreFailure(
                    "NOTES_INVENTORY", (owner, path), "non-hex Notes entry"
                ) from error
            if re.fullmatch("[0-9a-f]+", name) is None:
                raise CoreFailure(
                    "NOTES_INVENTORY", (owner, path), "non-hex Notes entry"
                )
            if mode == "40000" and len(name) == 2 and len(prefix) + 2 < width:
                walk(OID(fmt, linked), prefix + name, (*path, name), chain)
            elif mode == "100644" and len(prefix) + len(name) == width:
                target = prefix + name
                if target in targets:
                    raise CoreFailure(
                        "NOTES_INVENTORY",
                        (owner, target),
                        "duplicate target mapping",
                    )
                from repo_catalog.domain.p1_core import encode, valid_note_role

                note_path = "/".join((*path, name))
                account_proof_bundle(chain, work)
                bundle = encode(
                    [
                        [item.oid.full_oid, item.native_type, item.body.hex()]
                        for item in chain
                    ]
                )
                if not valid_note_role(*root.key, target, linked, note_path, bundle):
                    raise CoreFailure(
                        "NOTES_ROLE", (owner, target), "invalid inventory member proof"
                    )
                targets.add(target)
                members.append((target, linked, note_path))
            else:
                raise CoreFailure(
                    "NOTES_INVENTORY",
                    (owner, path),
                    "unsupported Notes entry mode/name/fanout",
                )

    failure = None
    try:
        with account_verification(work):
            walk(root, "", (), (), is_root=True)
    except CoreFailure as error:
        failure = error
    status: Status = (
        ("partial" if members else "unknown")
        if failure is not None
        else ("complete" if members else "known_empty")
    )
    return status, tuple(members), tuple(structures), failure


def ref_mapping_inventory(claim, read_metadata: MetadataReader, work: WorkBudget):
    from repo_catalog.domain.ref_observation import RefObservationClaim

    if not isinstance(claim, RefObservationClaim) or claim.root_oid is None:
        raise CoreFailure("NOTES_ROLE", claim, "exact present-root claim required")
    return _mapping_inventory(claim.root_oid, claim.identity, read_metadata, work)
