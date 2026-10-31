"""P1 immutable Git values and bounded native validation, isolated from runtime.

Canonical JSON encodes the entire genuine semantic value (not its hash). Arrays
preserve coordinates and order; strings preserve arbitrary original provenance.
The reference native grammar is deliberately narrow; P2/P4 can extend parsers
without inventing identity or promoting sender assertions to local checks.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import sqlite3


from repo_catalog.domain.shared_values import (
    OID,
    CoreFailure,
    Provenance,
    encode,
    uuid4_value,
)

_work_scope = ContextVar("p1_native_work", default=None)


@contextmanager
def account_verification(work):
    """Count actual repeated Python and SQLite CHECK hashing, including failures."""
    state = {"work": work, "error": None}
    token = _work_scope.set(state)
    try:
        yield
    except Exception:
        if state["error"] is not None:
            raise state["error"]
        raise
    finally:
        _work_scope.reset(token)


def _performed(unit, amount):
    state = _work_scope.get()
    if state is not None:
        try:
            state["work"].require(unit, amount)
            state["work"].charge(unit, amount)
        except Exception as error:
            state["error"] = error
            raise


ScalarField = Literal[
    "type",
    "size",
    "message",
    "author",
    "committer",
    "encoding",
    "supplied_digest",
    "parent_count",
    "tree_count",
    "raw_name_hex",
    "decoded_name",
    "decoder_settings",
    "author_name",
    "author_email",
    "author_time_us",
    "committer_name",
    "committer_email",
    "committer_time_us",
    "tag_name",
    "tagger",
    "header_data",
]


def claim_value(field: ScalarField, value: object) -> str:
    valid = field in {
        "type",
        "size",
        "message",
        "author",
        "committer",
        "encoding",
        "supplied_digest",
        "parent_count",
        "tree_count",
        "raw_name_hex",
        "decoded_name",
        "decoder_settings",
        "author_name",
        "author_email",
        "author_time_us",
        "committer_name",
        "committer_email",
        "committer_time_us",
        "tag_name",
        "tagger",
        "header_data",
    }
    if value is not None:
        if field == "type":
            valid = value in ("commit", "tree", "blob", "tag")
        elif field in ("author_time_us", "committer_time_us"):
            valid = type(value) is int and -(2**63) <= value < 2**63
        elif field in ("size", "parent_count", "tree_count"):
            valid = type(value) is int and 0 <= value < 2**63
        else:
            valid = valid and isinstance(value, str)
    if not valid:
        raise CoreFailure("CLAIM", field, "unsupported field or typed claim value")
    return encode(["unknown"] if value is None else ["known", value])


@dataclass(frozen=True)
class ScalarClaim:
    subject: OID
    field: ScalarField
    value: object
    provenance: Provenance

    def __post_init__(self) -> None:
        claim_value(self.field, self.value)

    @property
    def key(self) -> tuple[str, ...]:
        return (
            *self.subject.key,
            self.field,
            claim_value(self.field, self.value),
            self.provenance.encoded,
        )


@dataclass(frozen=True)
class RelationMember:
    """Actual ordinal, None when genuinely unreported, or tree mode/name coordinates.

    Parent encodings use real ordinals; unpositioned members stay explicitly None.
    Transport tuple order is not a new fact. Complete ordered parent lists require
    all actual contiguous ordinals.
    """

    coordinate: int | None | tuple[object, ...]
    target: OID

    @property
    def value(self) -> list[object]:
        return [self.coordinate, *self.target.key]


@dataclass(frozen=True)
class RelationGroup:
    subject: OID
    relation: Literal["commit_parents", "commit_tree", "tree_entries", "tag_target"]
    scope: str
    status: Literal["unknown", "partial", "known_empty", "complete"]
    members: tuple[RelationMember, ...]
    provenance: Provenance

    def __post_init__(self) -> None:
        if not self.scope or not valid_group(
            self.subject.object_format, self.relation, self.status, self.membership
        ):
            raise CoreFailure(
                "GROUP",
                (self.subject, self.scope),
                "invalid whole typed relation group",
            )

    @property
    def membership(self) -> str:
        return encode(
            canonical_relation_members(
                self.relation, [member.value for member in self.members]
            )
        )

    @property
    def key(self) -> tuple[str, ...]:
        return (
            *self.subject.key,
            self.relation,
            self.scope,
            self.status,
            self.membership,
            self.provenance.encoded,
        )


@dataclass(frozen=True)
class NativeObject:
    object_oid: OID
    native_type: Literal["commit", "tree", "tag", "blob"]
    body: bytes
    declared_size: int
    digest_sha256: str

    def validate(self) -> None:
        if not valid_native(
            *self.object_oid.key,
            self.native_type,
            self.body,
            self.declared_size,
            self.digest_sha256,
        ):
            raise CoreFailure(
                "NATIVE_INTEGRITY",
                self.object_oid,
                "exact native OID/type/size/digest mismatch",
            )


@dataclass(frozen=True)
class Projection:
    canonical: object | None
    alternatives: tuple[object, ...]
    reported_conflict: bool
    checked_scope: str | None


def native_object_oid(fmt: str, kind: str, body: bytes) -> str:
    _performed("verification_bytes", len(body))
    return hashlib.new(fmt, f"{kind} {len(body)}\0".encode() + body).hexdigest()


def _body_digest(body: bytes) -> str:
    _performed("verification_bytes", len(body))
    return hashlib.sha256(body).hexdigest()


def valid_native(
    fmt: str, object_oid: str, kind: str, body: bytes, size: int, digest: str
) -> bool:
    try:
        OID(fmt, object_oid)  # type: ignore[arg-type]
        return (
            kind in ("commit", "tree", "tag", "blob")
            and type(body) is bytes
            and type(size) is int
            and 0 <= size < 2**63
            and size == len(body)
            and _body_digest(body) == digest
            and native_object_oid(fmt, kind, body) == object_oid
        )
    except (ValueError, TypeError):
        return False


def canonical_relation_members(relation: str, members: list) -> list:
    """Normalize packaging order only where explicit coordinates own ordering."""
    if relation == "commit_parents":
        return sorted(
            members,
            key=lambda member: (
                member[0] is None,
                member[0] if member[0] is not None else 0,
                member[1],
                member[2],
            ),
        )
    return members


def valid_group(fmt: str, relation: str, status: str, membership: str) -> bool:
    try:
        members = json.loads(membership)
        if (
            encode(members) != membership
            or not isinstance(members, list)
            or status not in ("unknown", "partial", "known_empty", "complete")
            or relation
            not in ("commit_parents", "commit_tree", "tree_entries", "tag_target")
        ):
            return False
        if status in ("unknown", "known_empty") and members:
            return False
        if encode(canonical_relation_members(relation, members)) != membership:
            return False
        slots = []
        unknown_targets = set()
        for coordinate, target_format, target_object_oid in members:
            OID(target_format, target_object_oid)
            if target_format != fmt:
                return False
            if relation == "tree_entries":
                if not isinstance(coordinate, list) or not 2 <= len(coordinate) <= 4:
                    return False
                mode, name_hex = coordinate[:2]
                if len(coordinate) >= 3:
                    path = bytes.fromhex(coordinate[2])
                    if path.hex() != coordinate[2] or not path or b"\0" in path:
                        return False
                if len(coordinate) == 4 and (
                    type(coordinate[3]) is not int or coordinate[3] < 0
                ):
                    return False
                name = bytes.fromhex(name_hex)
                if (
                    mode not in ("40000", "100644", "100755", "120000", "160000")
                    or not name
                    or b"/" in name
                    or b"\0" in name
                    or name.hex() != name_hex
                ):
                    return False
                slots.append(name_hex)
            elif relation == "commit_parents" and coordinate is None:
                if target_object_oid in unknown_targets or status == "complete":
                    return False
                unknown_targets.add(target_object_oid)
                continue
            else:
                if type(coordinate) is not int or coordinate < 0:
                    return False
                slots.append(coordinate)
        if len(set(slots)) != len(slots):
            return False
        if (
            relation == "commit_parents"
            and status == "complete"
            and sorted(slots) != list(range(len(members)))
        ):
            return False
        if relation in ("commit_tree", "tag_target") and (
            len(members) > 1 or slots not in ([], [0])
        ):
            return False
        return status != "complete" or bool(members)
    except (ValueError, TypeError, KeyError, IndexError):
        return False


def tree_entries(body: bytes, fmt: str) -> dict[bytes, tuple[bytes, str]]:
    """Production native tree grammar; P1 semantic-key representations unchanged."""
    from repo_catalog.domain.git_native import parse_tree

    return parse_tree(fmt, body)


def valid_note_role(
    fmt: str, root: str, target: str, note: str, path: str, bundle: str
) -> bool:
    try:
        for object_oid in (root, target, note):
            OID(fmt, object_oid)  # type: ignore[arg-type]
        proof = json.loads(bundle)
        if encode(proof) != bundle or not proof:
            return False
        expected, suffix, actual_path = root, target, []
        for index, (object_oid, kind, hex_body) in enumerate(proof):
            _performed("proof_steps", 1)
            body = bytes.fromhex(hex_body)
            if (
                body.hex() != hex_body
                or object_oid != expected
                or native_object_oid(fmt, kind, body) != object_oid
            ):
                return False
            from repo_catalog.domain.git_native import parse_metadata

            parsed = parse_metadata(fmt, kind, body)
            if index == 0 and kind == "commit":
                expected = parsed.relations["commit_tree"][0][2]
                continue
            if kind != "tree":
                return False
            entries = tree_entries(body, fmt)
            leaf, directory = suffix.encode(), suffix[:2].encode()
            if leaf in entries:
                actual_path.append(suffix)
                return (
                    index == len(proof) - 1
                    and not (len(suffix) > 2 and directory in entries)
                    and entries[leaf] == (b"100644", note)
                    and path == "/".join(actual_path)
                )
            if (
                len(suffix) <= 2
                or directory not in entries
                or entries[directory][0] != b"40000"
            ):
                return False
            actual_path.append(suffix[:2])
            suffix, expected = suffix[2:], entries[directory][1]
        return False
    except (ValueError, TypeError, KeyError, UnicodeError):
        return False


def valid_coverage_members(value: str) -> bool:
    try:
        members = json.loads(value)
        if not isinstance(members, list) or encode(members) != value:
            return False
        for member in members:
            if not isinstance(member, list) or len(member) != 2:
                return False
            OID(*member)
        return len({encode(m) for m in members}) == len(members)
    except (ValueError, TypeError):
        return False


def register_functions(connection: sqlite3.Connection) -> None:
    """Checks are repeatable at SQLite admission; no trust in a verified flag."""

    def check_claim(field: str, value: str) -> bool:
        try:
            decoded = json.loads(value)
            original = None if decoded == ["unknown"] else decoded[1]
            return claim_value(field, original) == value
        except (ValueError, TypeError, IndexError):
            return False

    connection.create_function(
        "p1_coverage_members", 1, valid_coverage_members, deterministic=True
    )
    connection.create_function("p1_claim", 2, check_claim, deterministic=True)
    connection.create_function("p1_group", 4, valid_group, deterministic=True)

    def retained_native(fmt, object_oid, kind, body, size, digest):
        if not valid_native(fmt, object_oid, kind, body, size, digest):
            return False
        if kind == "blob":
            return True  # Physical notes-role FK separately restricts this body.
        try:
            from repo_catalog.domain.git_native import parse_metadata

            parse_metadata(fmt, kind, body)
            return True
        except (ValueError, TypeError, IndexError, UnicodeError):
            return False

    connection.create_function("p1_native", 6, retained_native, deterministic=True)
    connection.create_function("p1_note_role", 6, valid_note_role, deterministic=True)
    connection.create_function("p1_notes_group", 3, _notes_group, deterministic=True)

    connection.create_function(
        "p1_intrinsic_claim", 4, _intrinsic_claim, deterministic=True
    )
    connection.create_function(
        "p1_intrinsic_group", 6, _intrinsic_group, deterministic=True
    )

    def provenance(value: str) -> bool:
        try:
            fields = json.loads(value)
            return (
                isinstance(fields, list)
                and len(fields) == 6
                and Provenance(*fields).encoded == value
            )
        except (ValueError, TypeError):
            return False

    connection.create_function("p1_provenance", 1, provenance, deterministic=True)

    def observation(origin, capture, repository, kind, scope, value, original):
        try:
            parsed_scope, parsed_value = json.loads(scope), json.loads(value)
            result = GitObservation(
                origin,
                capture,
                repository,
                kind,
                tuple(parsed_scope),
                parsed_value,
                Provenance(*json.loads(original)),
            )
            return encode(result.scope) == scope and encode(result.value) == value
        except (ValueError, TypeError, KeyError, AttributeError):
            return False

    def repository_claim(repository, field, value, original):
        try:
            result = RepositoryClaim(
                repository, field, json.loads(value), Provenance(*json.loads(original))
            )
            return result.key[2] == value
        except (ValueError, TypeError, KeyError, AttributeError):
            return False

    connection.create_function("p1_git_observation", 7, observation, deterministic=True)
    connection.create_function(
        "p1_repository_claim", 4, repository_claim, deterministic=True
    )


def intrinsic_members(fmt: str, kind: str, body: bytes, relation: str) -> list[object]:
    """Check the named relation using the production whole-native grammar."""
    from repo_catalog.domain.git_native import parse_metadata

    parsed = parse_metadata(fmt, kind, body)
    if relation not in parsed.relations:
        raise ValueError("relation not checked by this native grammar")
    return parsed.relations[relation]


def _intrinsic_claim(field: str, value: str, kind: str, body: bytes) -> bool:
    if field == "type":
        return value == claim_value("type", kind)
    if field == "size":
        return value == claim_value("size", len(body))
    # The frozen four-argument SQL guard lacks an object-format parameter.
    # Commit/tag headers carry their full typed width intrinsically. Tree count
    # is derived from the checked tree_entries group, never guessed here.
    if kind not in ("commit", "tag"):
        return False
    try:
        from repo_catalog.domain.git_native import parse_metadata

        first = body.partition(b"\n")[0].partition(b" ")[2]
        fmt = {40: "sha1", 64: "sha256"}.get(len(first))
        if fmt is None:
            return False
        scalars = parse_metadata(fmt, kind, body).scalars
        return field in scalars and value == claim_value(field, scalars[field])
    except (ValueError, TypeError, IndexError, UnicodeError):
        return False


def _intrinsic_group(
    fmt: str, relation: str, status: str, membership: str, kind: str, body: bytes
) -> bool:
    try:
        members = intrinsic_members(fmt, kind, body, relation)
        return membership == encode(members) and status == (
            "complete" if members else "known_empty"
        )
    except (ValueError, TypeError, IndexError, UnicodeError):
        return False


def _notes_group(fmt: str, status: str, membership: str) -> bool:
    try:
        values = json.loads(membership)
        if (
            encode(values) != membership
            or not isinstance(values, list)
            or status not in ("unknown", "partial", "known_empty", "complete")
            or (status in ("unknown", "known_empty") and values)
            or (status == "complete" and not values)
        ):
            return False
        targets = []
        for target, note, path in values:
            OID(fmt, target)  # type: ignore[arg-type]
            OID(fmt, note)  # type: ignore[arg-type]
            if path is not None and (not isinstance(path, str) or not path):
                return False
            targets.append(target)
        return len(set(targets)) == len(targets)
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class RepositoryClaim:
    repository_uuidv4: str
    field: Literal[
        "name",
        "git_path",
        "object_format",
        "endpoint",
        "observation_us",
        "identity_assertion",
        "identity_cancellation",
    ]
    value: object
    provenance: Provenance

    def __post_init__(self) -> None:
        uuid4_value(self.repository_uuidv4)
        if self.field not in (
            "name",
            "git_path",
            "object_format",
            "endpoint",
            "observation_us",
            "identity_assertion",
            "identity_cancellation",
        ):
            raise CoreFailure(
                "REPOSITORY_CLAIM", self.field, "typed repository claim required"
            )
        if self.field == "observation_us":
            if self.value is not None and (
                type(self.value) is not int or not 0 < self.value < 2**63
            ):
                raise CoreFailure(
                    "TIME",
                    self.field,
                    "positive int64 Unix microseconds or null required",
                )
        elif not isinstance(self.value, str):
            raise CoreFailure(
                "REPOSITORY_CLAIM", self.field, "typed repository string value required"
            )
        if self.field in ("identity_assertion", "identity_cancellation"):
            uuid4_value(self.value)

    @property
    def key(self) -> tuple[str, ...]:
        return (
            self.repository_uuidv4,
            self.field,
            encode(self.value),
            self.provenance.encoded,
        )


@dataclass(frozen=True)
class GitObservation:
    """Original occurrence pair plus typed coordinates, never local retry IDs.

    Scope/value are complete lossless semantic values. The kind determines the
    required domain vocabulary; optional real details remain explicit fields.
    No body bytes, publication success or mutable acquisition flags belong here.
    """

    capture_origin_uuidv4: str
    capture_uuidv4: str
    repository_uuidv4: str
    kind: Literal["acquisition", "ref", "root", "snapshot", "membership", "manifest"]
    scope: tuple[object, ...]
    value: dict[str, object]
    provenance: Provenance

    def __post_init__(self) -> None:
        for value in (
            self.capture_origin_uuidv4,
            self.capture_uuidv4,
            self.repository_uuidv4,
        ):
            uuid4_value(value)
        required = {
            "acquisition": {"source", "observed_at_us", "endpoint"},
            "ref": {"ref", "observed_at_us", "target"},
            "root": {"object", "role", "observed_at_us"},
            "snapshot": {"roots", "predecessor", "observed_at_us"},
            "membership": {"object", "source", "observed_at_us"},
            "manifest": {"entries", "requested_scope", "observed_at_us"},
        }
        if (
            not self.scope
            or self.kind not in required
            or not required[self.kind] <= self.value.keys()
        ):
            raise CoreFailure(
                "OBSERVATION",
                self.kind,
                "typed genuine observation coordinates required",
            )
        allowed = {
            "acquisition": {
                "source",
                "observed_at_us",
                "endpoint",
                "object_format",
                "roots",
                "settings",
                "enumeration_state",
                "terminal_observation",
                "ref_observed_at_us",
                "requested_scope",
            },
            "ref": {
                "ref",
                "observed_at_us",
                "target",
                "peeled",
                "target_type",
                "root_kind",
                "ref_kind",
                "source_ordinal",
                "source",
                "enumeration_state",
                "terminal_observation",
            },
            "root": {
                "object",
                "role",
                "observed_at_us",
                "ref",
                "source_ordinal",
                "source",
                "expected_object_oid",
                "root_kind",
                "enumeration_state",
                "terminal_observation",
            },
            "snapshot": {
                "roots",
                "predecessor",
                "observed_at_us",
                "refs",
                "enumeration_state",
                "terminal_observation",
                "source",
            },
            "membership": {
                "object",
                "source",
                "observed_at_us",
                "endpoint",
                "ref",
                "role",
            },
            "manifest": {
                "entries",
                "requested_scope",
                "observed_at_us",
                "counts",
                "enumeration_state",
                "terminal_observation",
                "root",
            },
        }
        if not self.value.keys() <= allowed[self.kind]:
            raise CoreFailure(
                "OBSERVATION", self.scope, "unsupported observation field"
            )
        for name in ("source", "role", "ref", "requested_scope"):
            if name in self.value and (
                not isinstance(self.value[name], str) or not self.value[name]
            ):
                raise CoreFailure(
                    "OBSERVATION", name, "genuine nonempty coordinate required"
                )
        for name in ("source_ordinal",):
            if name in self.value and (
                type(self.value[name]) is not int or self.value[name] < 0
            ):
                raise CoreFailure(
                    "OBSERVATION", name, "actual nonnegative ordinal required"
                )
        if "enumeration_state" in self.value:
            state = self.value["enumeration_state"]
            if state not in ("unknown", "partial", "known_empty", "complete") or (
                state in ("known_empty", "complete")
                and self.value.get("terminal_observation") is not True
            ):
                raise CoreFailure(
                    "OBSERVATION",
                    self.scope,
                    "closed enumeration requires original terminal evidence",
                )
        if (
            "terminal_observation" in self.value
            and type(self.value["terminal_observation"]) is not bool
        ):
            raise CoreFailure(
                "OBSERVATION", self.scope, "typed terminal report required"
            )
        if "object_format" in self.value and self.value["object_format"] not in (
            "sha1",
            "sha256",
        ):
            raise CoreFailure("OBSERVATION", self.scope, "native format required")
        if (
            "endpoint" in self.value
            and self.value["endpoint"] is not None
            and not isinstance(self.value["endpoint"], str)
        ):
            raise CoreFailure(
                "OBSERVATION", self.scope, "endpoint string or genuine absence required"
            )
        if (
            "ref_observed_at_us" in self.value
            and self.value["ref_observed_at_us"] is not None
            and (
                type(self.value["ref_observed_at_us"]) is not int
                or not 0 < self.value["ref_observed_at_us"] < 2**63
            )
        ):
            raise CoreFailure(
                "TIME", self.scope, "positive int64 Unix microseconds or null required"
            )
        if "ref_kind" in self.value and self.value["ref_kind"] not in (
            "head",
            "tag",
            "other",
        ):
            raise CoreFailure("OBSERVATION", self.scope, "typed ref kind required")
        if "target_type" in self.value and self.value["target_type"] not in (
            None,
            "commit",
            "tree",
            "tag",
            "blob",
        ):
            raise CoreFailure(
                "OBSERVATION", self.scope, "typed native target report required"
            )
        if "root_kind" in self.value and self.value["root_kind"] not in (
            "commit",
            "tree",
            "tag",
            "blob",
            "unknown",
        ):
            raise CoreFailure("OBSERVATION", self.scope, "typed root kind required")
        for root in self.value.get("roots", []):
            OID(*root)
        for ref in self.value.get("refs", []):
            if (
                not isinstance(ref, dict)
                or not {"ref", "target"} <= ref.keys()
                or not ref.keys()
                <= {"ref", "target", "peeled", "target_type", "ref_kind"}
                or not isinstance(ref["ref"], str)
                or not ref["ref"].startswith("refs/")
            ):
                raise CoreFailure(
                    "OBSERVATION", self.scope, "typed snapshot ref required"
                )
            for name in ("target", "peeled"):
                if ref.get(name) is not None:
                    OID(*ref[name])
        for entry in self.value.get("entries", []):
            if (
                not isinstance(entry, dict)
                or not {"raw_path_hex", "mode", "object"} <= entry.keys()
                or not entry.keys()
                <= {"raw_path_hex", "mode", "object", "ordinal", "byte_offset"}
            ):
                raise CoreFailure(
                    "OBSERVATION", self.scope, "typed manifest entry required"
                )
            path = bytes.fromhex(entry["raw_path_hex"])
            if (
                not path
                or b"\0" in path
                or path.hex() != entry["raw_path_hex"]
                or entry["mode"]
                not in ("40000", "100644", "100755", "120000", "160000")
            ):
                raise CoreFailure(
                    "OBSERVATION",
                    self.scope,
                    "exact native manifest path/mode required",
                )
            OID(*entry["object"])
            for name in ("ordinal", "byte_offset"):
                if name in entry and (type(entry[name]) is not int or entry[name] < 0):
                    raise CoreFailure(
                        "OBSERVATION",
                        self.scope,
                        "actual manifest coordinates required",
                    )
        if "counts" in self.value and (
            not isinstance(self.value["counts"], dict)
            or any(type(v) is not int or v < 0 for v in self.value["counts"].values())
        ):
            raise CoreFailure(
                "OBSERVATION", self.scope, "nonnegative actual manifest counts required"
            )
        observed = self.value["observed_at_us"]
        if observed is not None and (
            type(observed) is not int or not 0 < observed < 2**63
        ):
            raise CoreFailure(
                "TIME", self.scope, "positive int64 Unix microseconds or null required"
            )
        if self.value.get("terminal_observation") is True and observed is None:
            raise CoreFailure(
                "TIME", self.scope, "terminal observation requires a positive timestamp"
            )
        if any(
            name in self.value
            for name in ("body", "raw_text", "verified", "complete", "local_revision")
        ):
            raise CoreFailure(
                "OBSERVATION",
                self.scope,
                "bytes and mutable authority are not observations",
            )
        if self.kind == "ref" and (
            not isinstance(self.value["ref"], str)
            or not self.value["ref"].startswith("refs/")
        ):
            raise CoreFailure("OBSERVATION", self.scope, "full original ref required")
        for name in ("object", "target", "peeled", "expected_object_oid", "root"):
            if name in self.value and self.value[name] is not None:
                OID(*self.value[name])
        if self.kind == "snapshot":
            for root in self.value["roots"]:
                OID(*root)
            if self.value["predecessor"] is not None:
                for part in self.value["predecessor"]:
                    uuid4_value(part)
        encode(self.value)

    @property
    def key(self) -> tuple[str, ...]:
        return (
            self.capture_origin_uuidv4,
            self.capture_uuidv4,
            self.repository_uuidv4,
            self.kind,
            encode(self.scope),
            encode(self.value),
            self.provenance.encoded,
        )


@dataclass(frozen=True)
class CoreCoverageScope:
    owner_kind: Literal["repository", "ref_observation", "object", "field"]
    coordinates: tuple[str, ...]

    def __post_init__(self) -> None:
        widths = {
            "repository": 2,
            "ref_observation": 3,
            "object": 3,
            "field": 4,
        }
        if (
            self.owner_kind not in widths
            or len(self.coordinates) != widths[self.owner_kind]
            or any(not isinstance(c, str) or not c for c in self.coordinates)
        ):
            raise CoreFailure(
                "COVERAGE_SCOPE", self, "full typed Git owner coordinates required"
            )
        if self.owner_kind == "repository":
            uuid4_value(self.coordinates[0])
        elif self.owner_kind == "ref_observation":
            from repo_catalog.domain.ref_observation import RefObservationKey

            RefObservationKey(*self.coordinates[:2])
        else:
            OID(*self.coordinates[:2])

    @property
    def encoded(self) -> str:
        return encode(self.coordinates)
