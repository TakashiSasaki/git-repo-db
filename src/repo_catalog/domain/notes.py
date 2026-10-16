"""Receiver-checked Notes mapping grammar and capture-scoped terminal evidence.

Only commit/tree structural representations are read. Targets, note bodies and
unrelated descendant trees are never dependencies of a narrow mapping proof.
Inventory closure is stronger: every entry must belong to the supported grammar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Literal

from repo_catalog.domain.git_native import parse_metadata
from repo_catalog.domain.p1_core import (
    OID,
    Capture,
    CoreFailure,
    NativeObject,
    NotesProof,
    account_verification,
)
from repo_catalog.domain.ports.p1_core import WorkBudget

Status = Literal["unknown", "partial", "known_empty", "complete"]
MetadataReader = Callable[[OID], NativeObject]
GRAMMAR = "p4-notes/1"


def _charge(work: WorkBudget, unit: str, amount: int = 1) -> None:
    work.require(unit, amount)
    work.charge(unit, amount)


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


def mapping_proof(
    capture: Capture, target: OID, read_metadata: MetadataReader, work: WorkBudget
) -> NotesProof:
    """Acquire exactly the relevant mapping path; unsupported paths fail closed."""
    if target.object_format != capture.root.object_format:
        raise CoreFailure(
            "NOTES_ROLE", (capture.pair, target), "target format mismatch"
        )
    structures, path = [], []
    current, suffix = capture.root, target.full_oid
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
                        (capture.pair, target),
                        "ambiguous or non-note leaf",
                    )
                path.append(suffix)
                proof = NotesProof(
                    capture,
                    target,
                    OID(current.object_format, note),
                    "/".join(path),
                    tuple(structures),
                )
                proof.validate()
                return proof
            if (
                len(suffix) <= 2
                or directory not in entries
                or entries[directory][0] != "40000"
            ):
                raise CoreFailure(
                    "NOTES_ROLE",
                    (capture.pair, target),
                    "target has no supported Notes mapping",
                )
            path.append(suffix[:2])
            suffix, current = (
                suffix[2:],
                OID(current.object_format, entries[directory][1]),
            )


@dataclass(frozen=True)
class NotesInventory:
    """One immutable inventory attempt, never a union with another attempt.

    Structures are the ordered successful structural reads. A failure diagnostic
    describes the stopped operation; it confers no terminal authority. Only a
    receiver replay of the full structural closure establishes terminal status.
    """

    capture: Capture
    status: Status
    members: tuple[tuple[str, str, str], ...]
    structures: tuple[NativeObject, ...]
    failure: CoreFailure | None = None


def mapping_inventory(
    capture: Capture, read_metadata: MetadataReader, work: WorkBudget
) -> NotesInventory:
    """Deterministic depth-first native-order inventory with positive terminal.

    The first refusal stops traversal. Already checked mappings remain partial.
    A complete/known-empty result requires exhausting the entire supported tree
    grammar. A tree's unrelated valid entry prevents terminal closure, rather
    than being omitted. No body availability is promised by this inventory.
    """
    structures: list[NativeObject] = []
    members: list[tuple[str, str, str]] = []
    targets: set[str] = set()
    fmt = capture.root.object_format
    width = len(capture.root.full_oid)

    def read(oid):
        native, parsed = _structure(oid, read_metadata, work)
        structures.append(native)
        return native, parsed

    def walk(oid, prefix, path, chain, root=False):
        native, parsed = read(oid)
        chain = (*chain, native)
        if root and native.native_type == "commit":
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
                    "NOTES_INVENTORY", (capture.pair, path), "non-hex Notes entry"
                ) from error
            if re.fullmatch("[0-9a-f]+", name) is None:
                raise CoreFailure(
                    "NOTES_INVENTORY", (capture.pair, path), "non-hex Notes entry"
                )
            if mode == "40000" and len(name) == 2 and len(prefix) + 2 < width:
                walk(OID(fmt, linked), prefix + name, (*path, name), chain)
            elif mode == "100644" and len(prefix) + len(name) == width:
                target = prefix + name
                if target in targets:
                    raise CoreFailure(
                        "NOTES_INVENTORY",
                        (capture.pair, target),
                        "duplicate target mapping",
                    )
                proof = NotesProof(
                    capture,
                    OID(fmt, target),
                    OID(fmt, linked),
                    "/".join((*path, name)),
                    chain,
                )
                proof.validate()
                targets.add(target)
                members.append((target, linked, proof.path))
            else:
                raise CoreFailure(
                    "NOTES_INVENTORY",
                    (capture.pair, path),
                    "unsupported Notes entry mode/name/fanout",
                )

    failure = None
    try:
        with account_verification(work):
            walk(capture.root, "", (), (), root=True)
    except CoreFailure as error:
        failure = error
    status: Status = (
        ("partial" if members else "unknown")
        if failure is not None
        else ("complete" if members else "known_empty")
    )
    return NotesInventory(capture, status, tuple(members), tuple(structures), failure)


def verify_inventory(inventory: NotesInventory, work: WorkBudget) -> NotesInventory:
    """Recompute supplied structure in its actual order, with no sender authority.

    A partial attempt may deliberately retain a proved prefix even when the full
    supplied tree would allow more work. Rechecking never promotes that attempt.
    An unavailable required next structure is an honest nonterminal boundary.
    """
    index = 0

    def read(oid):
        nonlocal index
        if index == len(inventory.structures):
            raise CoreFailure(
                "OBJECT_UNAVAILABLE", oid, "inventory structural frontier remains"
            )
        native = inventory.structures[index]
        if native.oid != oid:
            raise CoreFailure(
                "NOTES_INVENTORY", oid, "out-of-order structural evidence"
            )
        index += 1
        return native

    checked = mapping_inventory(inventory.capture, read, work)
    if checked.failure is not None and checked.failure.code == "BUDGET":
        raise checked.failure
    terminal = inventory.status in ("complete", "known_empty")
    valid = (
        index == len(inventory.structures)
        and checked.structures == inventory.structures
        and inventory.members == checked.members[: len(inventory.members)]
        and inventory.status in ("unknown", "partial", "complete", "known_empty")
        and (inventory.status != "unknown" or not inventory.members)
        and (inventory.status != "partial" or bool(inventory.members))
        and (
            not terminal
            or (
                inventory.status == checked.status
                and inventory.members == checked.members
                and checked.failure is None
                and inventory.failure is None
            )
        )
    )
    if not valid:
        raise CoreFailure(
            "NOTES_INVENTORY",
            inventory.capture.pair,
            "inventory does not match receiver structural checks",
        )
    return inventory
