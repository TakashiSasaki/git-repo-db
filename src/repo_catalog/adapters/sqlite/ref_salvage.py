"""Untrusted ADR 0036 salvage units from a preserved working copy.

This module never opens the suspect catalog or executes its schema. The caller
owns the forensic copy, durable request budget and output publication.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, replace
from pathlib import Path

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_coordination import (
    catalog_completion,
    catalog_gate,
    persist_catalog_stop,
)
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.application.ref_exchange import decode_ref_units
from repo_catalog.application.ref_observations import encode_metered
from repo_catalog.domain.git_native import parse_metadata
from repo_catalog.domain.p1_core import (
    OID,
    CoreCoverageScope,
    CoreFailure,
    NativeObject,
    Provenance,
    _notes_group,
    account_verification,
    uuid4_value,
    valid_note_role,
)
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.ref_coverage import (
    RefNotesInventoryCoverageProof,
    deserialize_structures,
    verify_ref_notes_inventory,
)
from repo_catalog.domain.ref_exchange import (
    _provenance,
    claim_from_wire,
    claim_to_wire,
    enumeration_from_wire,
    enumeration_to_wire,
    mapping_claim_from_wire,
    mapping_evidence_from_wire,
    mapping_from_wire,
    mapping_group_from_wire,
    mapping_to_wire,
    observation_from_wire,
    observation_to_wire,
    ref_note_from_wire,
)
from repo_catalog.domain.ref_observation import RefObservationKey

_COLUMNS = {
    "repositories": ("repository_uuidv4",),
    "ref_observations": (
        "observation_origin_uuidv4",
        "ref_observation_uuidv7",
        "repository_uuidv4",
        "ref_name_bytes",
        "source_attribution",
        "visibility_scope",
        "observed_at_us",
    ),
    "ref_observation_claims": (
        "observation_origin_uuidv4",
        "ref_observation_uuidv7",
        "provenance",
        "presence_state",
        "ref_form",
        "direct_format",
        "direct_target_object_oid",
        "symbolic_target_ref_name",
        "resolved_format",
        "resolved_target_object_oid",
        "peeled_format",
        "peeled_target_object_oid",
        "root_format",
        "root_object_oid",
        "absence_evidence",
    ),
    "ref_enumeration_observations": (
        "observation_origin_uuidv4",
        "enumeration_uuidv7",
        "repository_uuidv4",
        "source_attribution",
        "visibility_scope",
        "enumeration_scope_json",
        "enumeration_state",
        "completion_coordinate",
        "observed_at_us",
        "byte_limit",
        "ref_limit",
        "link_count",
    ),
    "ref_enumeration_links": (
        "enumeration_origin_uuidv4",
        "enumeration_uuidv7",
        "observation_origin_uuidv4",
        "ref_observation_uuidv7",
        "claim_provenance",
        "derivation",
        "position",
    ),
    "notes_mappings": (
        "object_format",
        "root_object_oid",
        "interpretation_kind",
        "interpretation_version",
        "interpretation_scope",
        "annotated_object_oid",
        "note_object_oid",
        "mapping_path_json",
    ),
    "notes_mapping_claims": (
        "observation_origin_uuidv4",
        "ref_observation_uuidv7",
        "ref_claim_provenance",
        "object_format",
        "root_object_oid",
        "interpretation_kind",
        "interpretation_version",
        "interpretation_scope",
        "annotated_object_oid",
        "note_object_oid",
        "mapping_path_json",
        "provenance",
    ),
    "notes_mapping_groups": (
        "observation_origin_uuidv4",
        "ref_observation_uuidv7",
        "ref_claim_provenance",
        "object_format",
        "root_object_oid",
        "interpretation_kind",
        "interpretation_version",
        "interpretation_scope",
        "group_scope",
        "status",
        "membership",
        "provenance",
    ),
    "notes_mapping_evidence": (
        "observation_origin_uuidv4",
        "ref_observation_uuidv7",
        "ref_claim_provenance",
        "object_format",
        "root_object_oid",
        "interpretation_kind",
        "interpretation_version",
        "interpretation_scope",
        "annotated_object_oid",
        "note_object_oid",
        "mapping_path_json",
        "verification_scope",
        "provenance",
        "proof_bundle",
    ),
    "ref_retained_notes": (
        "object_format",
        "object_oid",
        "physical_copy_uuidv4",
        "body",
        "size",
        "digest_sha256",
        "observation_origin_uuidv4",
        "ref_observation_uuidv7",
        "ref_claim_provenance",
        "role_format",
        "root_object_oid",
        "interpretation_kind",
        "interpretation_version",
        "interpretation_scope",
        "annotated_object_oid",
        "note_object_oid",
        "mapping_path_json",
        "verification_scope",
        "role_provenance",
        "proof_bundle",
    ),
    "coverage_scopes": (
        "owner_kind",
        "owner_coordinates_json",
        "repository_uuidv4",
        "observation_origin_uuidv4",
        "ref_observation_uuidv7",
        "object_format",
        "object_oid",
        "field",
        "coverage_kind",
    ),
    "coverage_claims": (
        "owner_kind",
        "owner_coordinates_json",
        "observed_at_us",
        "coverage_state",
        "details_json",
    ),
    "ref_coverage_proofs": (
        "owner_kind",
        "owner_coordinates_json",
        "observed_at_us",
        "coverage_state",
        "observation_origin_uuidv4",
        "ref_observation_uuidv7",
        "ref_claim_provenance",
        "object_format",
        "root_object_oid",
        "interpretation_kind",
        "interpretation_version",
        "interpretation_scope",
        "group_scope",
        "group_status",
        "group_membership",
        "group_provenance",
        "verification_provenance",
        "structures_json",
    ),
}


@dataclass
class RefSalvageScan:
    candidates: list[dict]
    omissions: list[str]
    exhausted: bool


class _WorkCallbackFailure(Exception):
    def __init__(self, original):
        super().__init__(str(original))
        self.original = original


class _WorkCallbackLimits:
    def __init__(self, guarded):
        self.guarded = guarded

    @property
    def note_bytes(self):
        return self.guarded._invoke(lambda: self.guarded.inner.limits.note_bytes)


class _WorkCallbackBoundary:
    """Keep callback failures and byte-access capabilities outside admission."""

    def __init__(self, inner, core):
        self.inner, self.core = inner, core
        self.limits = _WorkCallbackLimits(self)

    def _invoke(self, operation):
        prior_admitting = self.core._admitting
        prior_checked = getattr(self.core, "_checked_byte_read", False)
        self.core._admitting = False
        self.core._checked_byte_read = False
        try:
            return operation()
        except Exception as error:
            raise _WorkCallbackFailure(error) from error
        finally:
            self.core._admitting = prior_admitting
            self.core._checked_byte_read = prior_checked

    def require(self, unit, amount=1):
        return self._invoke(lambda: self.inner.require(unit, amount))

    def charge(self, unit, amount):
        return self._invoke(lambda: self.inner.charge(unit, amount))

    def __getattr__(self, name):
        if name != "abandon":
            raise AttributeError(name)
        self._invoke(lambda: getattr(self.inner, name))
        return lambda unit: self._invoke(lambda: self.inner.abandon(unit))


def _charge(work, unit, amount):
    work.require(unit, amount)
    work.charge(unit, amount)


def _wire_key(wire, work):
    _charge(work, "metadata_units", len(wire))
    for value in wire.values():
        if isinstance(value, str):
            _charge(work, "input_bytes", len(value))
    return tuple(wire.values())


class _UnsafeSourceShape(ValueError):
    """A suspect table cannot be evaluated as plain stored columns."""


def _validate_source_shape(conn, table, work, *, required=(), allow_generated=False):
    """Inspect every column descriptor without selecting any recovered value."""
    remaining_bytes = work._max["input_bytes"] - work.usage["input_bytes"]
    remaining_units = work._max["metadata_units"] - work.usage["metadata_units"]
    limit = min(513, remaining_units, remaining_bytes // 264)
    if limit <= 0:
        raise CoreFailure("BUDGET", table, "finite source schema inspection limit")
    work.require("metadata_units", limit)
    try:
        work.require("input_bytes", limit * 264)
    except BaseException:
        work.abandon("metadata_units")
        raise
    try:
        rows = conn.execute(
            "SELECT CASE WHEN octet_length(name)<=256 THEN name END,hidden "
            "FROM pragma_table_xinfo(?) LIMIT ?",
            (table, limit),
        ).fetchall()
    except BaseException:
        work.abandon("metadata_units")
        work.abandon("input_bytes")
        raise
    work.charge("metadata_units", len(rows))
    work.charge(
        "input_bytes",
        sum(
            (
                len(name)
                if isinstance(name, bytes)
                else len(name.encode("utf-8"))
                if isinstance(name, str)
                else 0
            )
            + 8
            for name, _ in rows
        ),
    )
    if len(rows) == limit:
        if limit < 513:
            raise CoreFailure("BUDGET", table, "incomplete source schema inspection")
        raise _UnsafeSourceShape("excessive source column count")
    if not rows or any(
        not isinstance(name, (bytes, str)) or type(hidden) is not int
        for name, hidden in rows
    ):
        raise _UnsafeSourceShape("missing or invalid source column descriptors")
    if any(hidden not in (0, 2, 3) for _, hidden in rows) or (
        not allow_generated and any(hidden != 0 for _, hidden in rows)
    ):
        raise _UnsafeSourceShape("generated or hidden source columns are forbidden")
    try:
        names = [
            name.decode("utf-8") if isinstance(name, bytes) else name
            for name, hidden in rows
            if hidden == 0
        ]
    except UnicodeDecodeError as error:
        raise _UnsafeSourceShape("invalid source column name") from error
    if not names or not set(required).issubset(names):
        raise _UnsafeSourceShape("required stored source column is missing")
    return names


def _rows(conn, table, work, *, maximum, max_row_bytes, columns=None):
    """Fetch one bounded row per statement, reserving before SQLite steps it.

    Callers supply only compiled fixed table/column names. OFFSET scan work is
    charged rather than pretending repeated prefix scans are free. Invalid
    UTF-8 is diagnosed per row so unrelated rows remain available.
    """
    columns = _COLUMNS[table] if columns is None else columns
    _validate_source_shape(conn, table, work, required=columns)
    sizes = " + ".join(
        f"CASE WHEN typeof({c}) IN ('text','blob') THEN octet_length({c}) "
        f"WHEN {c} IS NULL THEN 0 ELSE 8 END"
        for c in columns
    )
    types = ",".join(f"typeof({c})" for c in columns)
    projected = ",".join(f"CASE WHEN ({sizes})<=? THEN {c} END" for c in columns)
    query = f"SELECT ({sizes}),{types},{projected} FROM {table} NOT INDEXED LIMIT 1 OFFSET ?"
    offset = 0
    while offset < maximum:
        remaining = work._max["input_bytes"] - work.usage["input_bytes"]
        allowance = min(max_row_bytes, remaining)
        if allowance <= 0:
            raise CoreFailure("BUDGET", table, "no input budget for salvage row")
        # The bounded SQL projection repeats the size expression for each
        # selected column, in addition to walking the OFFSET prefix.
        scan_cost = offset + 1 + len(columns) * len(columns)
        work.require("metadata_units", scan_cost)
        try:
            work.require("input_bytes", allowance)
        except BaseException:
            work.abandon("metadata_units")
            raise
        count_records = "input_records" in work._max
        if count_records:
            try:
                work.require("input_records", 1)
            except BaseException:
                work.abandon("metadata_units")
                work.abandon("input_bytes")
                raise
        try:
            row = conn.execute(
                query, (allowance,) * len(columns) + (offset,)
            ).fetchone()
        except BaseException:
            work.abandon("metadata_units")
            work.abandon("input_bytes")
            if count_records:
                work.abandon("input_records")
            raise
        work.charge("metadata_units", scan_cost)
        if count_records:
            work.charge("input_records", int(row is not None))
        if row is None:
            work.charge("input_bytes", 0)
            return
        row_size = row[0]
        if type(row_size) is not int or row_size < 0:
            work.abandon("input_bytes")
            yield None, "invalid row size"
        elif row_size > allowance:
            work.charge("input_bytes", 0)
            yield None, "row exceeds finite input limit"
        else:
            work.charge("input_bytes", row_size)
            kinds = row[1 : 1 + len(columns)]
            values = row[1 + len(columns) :]
            try:
                parsed = {}
                for name, kind, value in zip(columns, kinds, values, strict=True):
                    kind = kind.decode("ascii")
                    if (name == "ref_name_bytes" and kind != "blob") or (
                        name == "symbolic_target_ref_name"
                        and kind not in ("blob", "null")
                    ):
                        raise ValueError("ref value is not a stored BLOB")
                    parsed[name] = value.decode("utf-8") if kind == "text" else value
                yield parsed, None
            except (UnicodeDecodeError, AttributeError, ValueError):
                yield None, "invalid stored text"
        offset += 1
    raise CoreFailure("BUDGET", table, "finite row limit reached")


def _observation_wire(row):
    return {
        "observation_origin_uuidv4": row["observation_origin_uuidv4"],
        "ref_observation_uuidv7": row["ref_observation_uuidv7"],
        "repository_uuidv4": row["repository_uuidv4"],
        "ref_name_hex": row["ref_name_bytes"].hex(),
        "source_attribution": row["source_attribution"],
        "visibility_scope": row["visibility_scope"],
        "observed_at_us": row["observed_at_us"],
    }


def _claim_wire(row):
    def pair(prefix):
        fmt, object_oid = row[prefix + "_format"], row[prefix + "_target_object_oid"]
        if fmt is None and object_oid is None:
            return None
        return [fmt, object_oid]

    root = (
        None
        if row["root_format"] is None and row["root_object_oid"] is None
        else [row["root_format"], row["root_object_oid"]]
    )
    symbolic = row["symbolic_target_ref_name"]
    return {
        "observation_origin_uuidv4": row["observation_origin_uuidv4"],
        "ref_observation_uuidv7": row["ref_observation_uuidv7"],
        "provenance_json": row["provenance"],
        "presence_state": row["presence_state"],
        "ref_form": row["ref_form"],
        "direct_target_object_oid": pair("direct"),
        "symbolic_target_hex": None if symbolic is None else symbolic.hex(),
        "resolved_target_object_oid": pair("resolved"),
        "peeled_target_object_oid": pair("peeled"),
        "root_object_oid": root,
        "absence_evidence_json": row["absence_evidence"],
    }


def _record(kind, identity, payload, table, work):
    return {
        "candidate_id": encode_metered(work, [kind, *identity]),
        "candidate_type": "ref_" + kind,
        "extraction_provenance": {"store": "core", "table": table},
        "provenance": None,
        "payload": payload,
        "extraction_status": "clean",
        "error": None,
    }


def _notes_wire(row, *, evidence=False, retained=False):
    result = {
        "observation_origin_uuidv4": row["observation_origin_uuidv4"],
        "ref_observation_uuidv7": row["ref_observation_uuidv7"],
        "ref_claim_provenance_json": row["ref_claim_provenance"],
        "object_format": row["role_format"] if retained else row["object_format"],
        "root_object_oid": row["root_object_oid"],
        "interpretation_kind": row["interpretation_kind"],
        "interpretation_version": row["interpretation_version"],
        "interpretation_scope": row["interpretation_scope"],
    }
    if "group_scope" in row:
        result.update(
            group_scope=row["group_scope"],
            status=row["status"],
            membership_json=row["membership"],
            provenance_json=row["provenance"],
        )
    else:
        result.update(
            annotated_object_oid=row["annotated_object_oid"],
            note_object_oid=row["note_object_oid"],
            mapping_path_json=row["mapping_path_json"],
        )
        if evidence:
            result.update(
                verification_scope=row["verification_scope"],
                evidence_provenance_json=row["role_provenance"]
                if retained
                else row["provenance"],
                proof_bundle_json=row["proof_bundle"],
            )
        else:
            result["provenance_json"] = row["provenance"]
    return result


def _precheck_unresolved_notes(row, wire, kind, work):
    """Check copied Notes content without inventing a missing result Claim."""
    RefObservationKey(wire["observation_origin_uuidv4"], wire["ref_observation_uuidv7"])
    _provenance(wire["ref_claim_provenance_json"])
    if kind == "group":
        OID(wire["object_format"], wire["root_object_oid"])
        if (
            not all(
                type(wire[name]) is str and wire[name]
                for name in (
                    "interpretation_kind",
                    "interpretation_version",
                    "interpretation_scope",
                    "group_scope",
                )
            )
            or _provenance(wire["provenance_json"]).qualification != "reported"
        ):
            raise ValueError("original group scope and report required")
        raw = wire["membership_json"]
        if type(raw) is not str:
            raise ValueError("original whole group required")
        _charge(work, "input_bytes", 3 * len(raw))
        if not _notes_group(wire["object_format"], wire["status"], raw):
            raise ValueError("invalid original whole group")
        return
    mapping = mapping_from_wire(wire)
    if kind == "mapping":
        if _provenance(wire["provenance_json"]).qualification != "reported":
            raise ValueError("original Mapping report required")
        return
    evidence_provenance = _provenance(wire["evidence_provenance_json"])
    if (
        mapping.interpretation_kind != "git-notes"
        or mapping.interpretation_version != "1"
        or mapping.mapping_path is None
        or wire["verification_scope"] != "single-path"
        or evidence_provenance.qualification != "receiver_intrinsic"
        or evidence_provenance.decoder != "native-notes"
        or evidence_provenance.decoder_version != "1"
    ):
        raise ValueError("supported original Notes role required")
    proof = wire["proof_bundle_json"]
    if type(proof) is not str:
        raise ValueError("original structural proof required")
    _charge(work, "input_bytes", 4 * len(proof))
    if not valid_note_role(
        *mapping.root_object_oid.key,
        mapping.annotated_object_oid.object_oid,
        mapping.note_object_oid.object_oid,
        mapping.mapping_path,
        proof,
    ):
        raise ValueError("original Notes structural proof failed")
    if kind == "note":
        if (
            row["object_format"] != row["role_format"]
            or row["object_oid"] != row["note_object_oid"]
        ):
            raise ValueError("physical copy role identity differs")
        body = row["body"]
        if type(body) is not bytes:
            raise ValueError("exact stored note bytes required")
        uuid4_value(row["physical_copy_uuidv4"])
        NativeObject(
            mapping.note_object_oid, "blob", body, row["size"], row["digest_sha256"]
        ).validate()
        _charge(work, "input_bytes", 2 * len(body))
        wire.update(
            physical_copy_uuidv4=row["physical_copy_uuidv4"],
            body_hex=body.hex(),
            size=row["size"],
            digest_sha256=row["digest_sha256"],
        )


def scan_ref_units(conn: sqlite3.Connection, work, *, max_records, max_row_bytes):
    """Pin one coherent read-only source snapshot for typed extraction."""
    if conn.in_transaction:
        raise ValueError("dedicated forensic reader connection required")
    unit = "ref_source_vm_steps"
    available = work._max[unit] - work.usage[unit]
    if available <= 0:
        return RefSalvageScan([], ["core:typed-scan: finite SQLite VM budget"], True)
    work.require(unit, available)
    steps = [0]

    def progress():
        steps[0] += 1
        return int(steps[0] > available)

    previous_factory = conn.text_factory
    previous_limits = []
    try:
        remaining = work._max["input_bytes"] - work.usage["input_bytes"]
        length_limit = max(65536, min(max_row_bytes * 4, max(65536, remaining)))
        for category, ceiling in (
            (sqlite3.SQLITE_LIMIT_LENGTH, length_limit),
            (sqlite3.SQLITE_LIMIT_COLUMN, 512),
            (sqlite3.SQLITE_LIMIT_SQL_LENGTH, 256 * 1024),
        ):
            previous_limits.append((category, conn.setlimit(category, ceiling)))
        conn.set_progress_handler(progress, 1)
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA trusted_schema=OFF")
        conn.text_factory = bytes
        conn.execute("BEGIN")
        return _scan_ref_units(
            conn, work, max_records=max_records, max_row_bytes=max_row_bytes
        )
    except sqlite3.DatabaseError as error:
        if getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT:
            return RefSalvageScan(
                [], ["core:typed-scan: finite SQLite VM budget"], True
            )
        raise
    finally:
        conn.set_progress_handler(None, 0)
        if conn.in_transaction:
            conn.rollback()
        conn.text_factory = previous_factory
        for category, ceiling in previous_limits:
            conn.setlimit(category, ceiling)
        work.charge(unit, min(steps[0], available))


def _scan_ref_units(conn: sqlite3.Connection, work, *, max_records, max_row_bytes):
    """Build independent subjects, Claims and whole enumeration candidates."""
    tables, omissions = {}, []
    exhausted = False
    remaining_records = max_records
    for table in _COLUMNS:
        tables[table] = []
        try:
            if remaining_records <= 0:
                raise CoreFailure("BUDGET", table, "finite salvage record limit")
            _charge(work, "metadata_units", 1)
            descriptor = conn.execute(f"PRAGMA table_list('{table}')").fetchone()
            if (
                descriptor is None
                or descriptor[0] != b"main"
                or descriptor[1] != table.encode("ascii")
                or descriptor[2] != b"table"
            ):
                omissions.append(f"core:{table}: ordinary source table unavailable")
                continue
            for row, error in _rows(
                conn,
                table,
                work,
                maximum=remaining_records,
                max_row_bytes=max_row_bytes,
            ):
                remaining_records -= 1
                if error:
                    omissions.append(f"core:{table}: {error}")
                else:
                    tables[table].append(row)
        except CoreFailure as error:
            if error.code != "BUDGET":
                raise
            omissions.append(f"core:{table}: finite salvage budget")
            exhausted = True
            break
        except _UnsafeSourceShape as error:
            omissions.append(f"core:{table}: {error}")
        except sqlite3.DatabaseError as error:
            omissions.append(f"core:{table}: unreadable ({error})")
            if getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT:
                exhausted = True
                break

    repositories = {row["repository_uuidv4"] for row in tables["repositories"]}
    observations, claims, candidates = {}, {}, []
    for row in tables.get("ref_observations", []):
        try:
            with account_verification(work):
                _charge(work, "input_bytes", 2 * len(row["ref_name_bytes"]))
                value = observation_from_wire(_observation_wire(row))
                wire = observation_to_wire(value)
            key = value.ref_observation_key.key
            observations[key] = wire
            candidates.append(
                _record(
                    "subject",
                    key,
                    {
                        "observation": wire,
                        "repository_present": value.repository_uuidv4 in repositories,
                    },
                    "ref_observations",
                    work,
                )
            )
        except CoreFailure as error:
            if error.code == "BUDGET":
                omissions.append("core:ref_observations: finite salvage budget")
                exhausted = True
                break
            omissions.append(f"core:ref_observations: invalid candidate ({error})")
        except (ValueError, TypeError, AttributeError, KeyError) as error:
            omissions.append(f"core:ref_observations: invalid candidate ({error})")

    for row in tables.get("ref_observation_claims", []):
        try:
            with account_verification(work):
                symbolic = row["symbolic_target_ref_name"]
                if symbolic is not None:
                    _charge(work, "input_bytes", 2 * len(symbolic))
                claim = claim_from_wire(_claim_wire(row))
                wire = claim_to_wire(claim)
                observation = observations.get(claim.ref_observation_key.key)
                if observation is None:
                    # The whole Claim value and its provenance are still
                    # original input; an event may resolve its subject from a
                    # validated baseline without inventing either value.
                    claims[claim.identity] = wire
                    omissions.append(
                        "core:ref_observation_claims: original subject requires receiver baseline/input"
                    )
                    candidates.append(
                        _record(
                            "claim",
                            claim.identity,
                            {
                                "observation": None,
                                "claim": wire,
                                "repository_present": False,
                            },
                            "ref_observation_claims",
                            work,
                        )
                    )
                    continue
                decode_ref_units(
                    {
                        "ref_observations": [observation],
                        "ref_observation_claims": [wire],
                        "ref_enumeration_observations": [],
                        "ref_enumeration_links": [],
                    }
                )
            claims[claim.identity] = wire
            candidates.append(
                _record(
                    "claim",
                    claim.identity,
                    {
                        "observation": observation,
                        "claim": wire,
                        "repository_present": observation["repository_uuidv4"]
                        in repositories,
                    },
                    "ref_observation_claims",
                    work,
                )
            )
        except CoreFailure as error:
            if error.code == "BUDGET":
                omissions.append("core:ref_observation_claims: finite salvage budget")
                exhausted = True
                break
            omissions.append(
                f"core:ref_observation_claims: invalid candidate ({error})"
            )
        except (ValueError, TypeError, AttributeError, KeyError) as error:
            omissions.append(
                f"core:ref_observation_claims: invalid candidate ({error})"
            )

    # If link enumeration was incomplete, no event can be proven whole.
    if not exhausted and not any(
        x.startswith("core:ref_enumeration_links:") for x in omissions
    ):
        for row in tables.get("ref_enumeration_observations", []):
            try:
                with account_verification(work):
                    event = enumeration_from_wire(row)
                    event_wire = enumeration_to_wire(event)
                    links, obs_rows, claim_rows = [], {}, {}
                    unresolved = False
                    for link in tables.get("ref_enumeration_links", []):
                        _charge(work, "metadata_units", 1)
                        if (
                            link["enumeration_origin_uuidv4"],
                            link["enumeration_uuidv7"],
                        ) != event.identity:
                            continue
                        key = (
                            link["observation_origin_uuidv4"],
                            link["ref_observation_uuidv7"],
                        )
                        identity = (*key, link["claim_provenance"])
                        RefObservationKey(*key)
                        _provenance(identity[2])
                        if key in observations:
                            obs_rows[key] = observations[key]
                        else:
                            unresolved = True
                        if identity in claims:
                            claim_rows[identity] = claims[identity]
                        else:
                            unresolved = True
                        links.append(
                            {
                                "enumeration_origin_uuidv4": link[
                                    "enumeration_origin_uuidv4"
                                ],
                                "enumeration_uuidv7": link["enumeration_uuidv7"],
                                "observation_origin_uuidv4": key[0],
                                "ref_observation_uuidv7": key[1],
                                "claim_provenance_json": identity[2],
                                "derivation": link["derivation"],
                                "position": link["position"],
                            }
                        )
                    section = {
                        "ref_observations": list(obs_rows.values()),
                        "ref_observation_claims": list(claim_rows.values()),
                        "ref_enumeration_observations": [event_wire],
                        "ref_enumeration_links": links,
                    }
                    if len(links) != event.link_count:
                        raise ValueError("whole original link count required")
                    if sorted(link["position"] for link in links) != list(
                        range(event.link_count)
                    ):
                        raise ValueError("original link order is incomplete")
                    if len(
                        {
                            (
                                link["observation_origin_uuidv4"],
                                link["ref_observation_uuidv7"],
                            )
                            for link in links
                        }
                    ) != len(links):
                        raise ValueError("duplicate original link subject")
                    if any(
                        link["derivation"] not in ("item", "absence") for link in links
                    ):
                        raise ValueError("invalid original link derivation")
                    if unresolved:
                        omissions.append(
                            "core:ref_enumeration_observations: original link dependency requires receiver baseline/input"
                        )
                    else:
                        decode_ref_units(section)
                candidates.append(
                    _record(
                        "enumeration",
                        event.identity,
                        {
                            "section": section,
                            "repository_present": event.repository_uuidv4
                            in repositories,
                        },
                        "ref_enumeration_observations",
                        work,
                    )
                )
            except CoreFailure as error:
                if error.code == "BUDGET":
                    omissions.append(
                        "core:ref_enumeration_observations: finite salvage budget"
                    )
                    exhausted = True
                    break
                omissions.append(
                    f"core:ref_enumeration_observations: incomplete ({error})"
                )
            except (ValueError, TypeError, AttributeError, KeyError) as error:
                omissions.append(
                    f"core:ref_enumeration_observations: incomplete ({error})"
                )
    mappings, groups = set(), {}
    for row in tables.get("notes_mappings", []):
        try:
            with account_verification(work):
                _charge(work, "metadata_units", 1)
                mapping = mapping_from_wire(row)
                _charge(work, "input_bytes", 2 * len(row["mapping_path_json"]))
                wire = mapping_to_wire(mapping)
                mappings.add(tuple(row[key] for key in _COLUMNS["notes_mappings"]))
                candidates.append(
                    _record(
                        "mapping_content",
                        mapping.key,
                        {"unit": wire},
                        "notes_mappings",
                        work,
                    )
                )
        except CoreFailure as error:
            if error.code in ("BUDGET", "QUERY_BUDGET"):
                omissions.append("core:notes_mappings: finite salvage budget")
                exhausted = True
                break
            omissions.append(f"core:notes_mappings: invalid candidate ({error})")
        except (ValueError, TypeError, AttributeError, KeyError) as error:
            omissions.append(f"core:notes_mappings: invalid candidate ({error})")
    checked_evidence = set()

    for table, kind in (
        ("notes_mapping_claims", "mapping"),
        ("notes_mapping_groups", "group"),
        ("notes_mapping_evidence", "evidence"),
        ("ref_retained_notes", "note"),
    ):
        for row in tables.get(table, []):
            try:
                with account_verification(work):
                    _charge(work, "metadata_units", 1)
                    key = (
                        row["observation_origin_uuidv4"],
                        row["ref_observation_uuidv7"],
                    )
                    identity = (*key, row["ref_claim_provenance"])
                    observation = observations.get(key)
                    claim_wire = claims.get(identity)
                    claim = None if claim_wire is None else claim_from_wire(claim_wire)
                    wire = _notes_wire(
                        row,
                        evidence=kind in ("evidence", "note"),
                        retained=kind == "note",
                    )
                    if kind != "group":
                        mapping_key = tuple(
                            wire[key] for key in _COLUMNS["notes_mappings"]
                        )
                        if mapping_key not in mappings:
                            omissions.append(
                                f"core:{table}: original shared Mapping row missing; exact coordinates retained"
                            )
                    if observation is None or claim is None:
                        omissions.append(
                            f"core:{table}: original Claim or subject requires receiver baseline/input"
                        )
                    if claim is None:
                        _precheck_unresolved_notes(row, wire, kind, work)
                        if kind == "group":
                            groups[_wire_key(wire, work)] = wire
                        elif kind == "evidence":
                            checked_evidence.add(_wire_key(wire, work))
                        elif kind == "note":
                            evidence_wire = dict(wire)
                            for field in (
                                "physical_copy_uuidv4",
                                "body_hex",
                                "size",
                                "digest_sha256",
                            ):
                                evidence_wire.pop(field)
                            if _wire_key(evidence_wire, work) not in checked_evidence:
                                omissions.append(
                                    f"core:{table}: exact original evidence row missing; copy retains its checked proof"
                                )
                    elif kind == "mapping":
                        mapping_claim_from_wire(wire, claim)
                    elif kind == "group":
                        mapping_group_from_wire(wire, claim)
                        groups[_wire_key(wire, work)] = wire
                    else:
                        evidence = mapping_evidence_from_wire(wire, claim)
                        evidence.validate()
                        evidence_key = _wire_key(wire, work)
                        if kind == "evidence":
                            checked_evidence.add(evidence_key)
                        else:
                            if evidence_key not in checked_evidence:
                                omissions.append(
                                    f"core:{table}: exact original evidence row missing; copy retains its checked proof"
                                )
                            if (
                                row["object_format"] != row["role_format"]
                                or row["object_oid"] != row["note_object_oid"]
                            ):
                                raise ValueError("physical copy role identity differs")
                            body = row["body"]
                            if type(body) is not bytes:
                                raise ValueError("exact stored note bytes required")
                            _charge(work, "input_bytes", 2 * len(body))
                            wire.update(
                                physical_copy_uuidv4=row["physical_copy_uuidv4"],
                                body_hex=body.hex(),
                                size=row["size"],
                                digest_sha256=row["digest_sha256"],
                            )
                            native, _ = ref_note_from_wire(wire, evidence)
                            native.validate()
                    scope_id = (
                        *identity,
                        wire["object_format"],
                        wire["root_object_oid"],
                        wire["interpretation_kind"],
                        wire["interpretation_version"],
                        wire["interpretation_scope"],
                    )
                    if kind == "group":
                        unit_id = (
                            *scope_id,
                            wire["group_scope"],
                            wire["provenance_json"],
                        )
                    elif kind == "note":
                        unit_id = (*identity, wire["physical_copy_uuidv4"])
                    else:
                        unit_id = (
                            *scope_id,
                            wire["annotated_object_oid"],
                            wire["provenance_json"]
                            if kind == "mapping"
                            else wire["evidence_provenance_json"],
                        )
                    candidates.append(
                        _record(
                            kind,
                            unit_id,
                            {
                                "observation": observation,
                                "claim": claim_wire,
                                "repository_present": observation is not None
                                and observation["repository_uuidv4"] in repositories,
                                "unit": wire,
                            },
                            table,
                            work,
                        )
                    )
            except CoreFailure as error:
                if error.code == "BUDGET":
                    omissions.append(f"core:{table}: finite salvage budget")
                    exhausted = True
                    break
                omissions.append(f"core:{table}: invalid candidate ({error})")
            except (ValueError, TypeError, AttributeError, KeyError) as error:
                omissions.append(f"core:{table}: invalid candidate ({error})")

    coverage_histories = {}
    for row in tables.get("coverage_scopes", []):
        if row["owner_kind"] != "ref_observation":
            continue
        try:
            with account_verification(work):
                _charge(work, "metadata_units", 1)
                key = (row["observation_origin_uuidv4"], row["ref_observation_uuidv7"])
                observation = observations.get(key)
                if observation is None:
                    omissions.append(
                        "core:ref_observations: Coverage owner subject requires receiver baseline/input"
                    )
                scope = CoreCoverageScope(
                    "ref_observation", (*key, row["coverage_kind"])
                )
                scope_json = encode_metered(work, scope.coordinates)
                if row["owner_coordinates_json"] != scope_json or any(
                    row[column] is not None
                    for column in (
                        "repository_uuidv4",
                        "object_format",
                        "object_oid",
                        "field",
                    )
                ):
                    raise ValueError("original Coverage scope columns differ")
                history = []
                for claim_row in tables.get("coverage_claims", []):
                    _charge(work, "metadata_units", 1)
                    if (
                        claim_row["owner_kind"],
                        claim_row["owner_coordinates_json"],
                    ) != (scope.owner_kind, scope_json):
                        continue
                    _charge(work, "input_bytes", len(claim_row["details_json"] or ""))
                    coverage = CoverageClaim(
                        scope,
                        claim_row["observed_at_us"],
                        claim_row["coverage_state"],
                        claim_row["details_json"],
                    )
                    history.append(
                        {
                            "observed_at_us": coverage.observed_at_us,
                            "state": coverage.state,
                            "details_json": coverage.details_json,
                        }
                    )
                history.sort(key=lambda item: (item["observed_at_us"], item["state"]))
                coverage_histories[scope_json] = history
                for index in range(max(1, len(history))):
                    _charge(work, "metadata_units", index + 1)
                    prefix = history[: index + 1]
                    target = (
                        ()
                        if not prefix
                        else (prefix[-1]["observed_at_us"], prefix[-1]["state"])
                    )
                    candidates.append(
                        _record(
                            "coverage",
                            key + (scope.coordinates[-1], *target),
                            {
                                "observation": observation,
                                "repository_present": observation is not None
                                and observation["repository_uuidv4"] in repositories,
                                "scope_json": scope_json,
                                "history": prefix,
                            },
                            "coverage_claims",
                            work,
                        )
                    )
        except CoreFailure as error:
            if error.code == "BUDGET":
                omissions.append("core:coverage_claims: finite salvage budget")
                exhausted = True
                break
            omissions.append(f"core:coverage_claims: invalid candidate ({error})")
        except (ValueError, TypeError, AttributeError, KeyError) as error:
            omissions.append(f"core:coverage_claims: invalid candidate ({error})")

    coverage_incomplete = exhausted or any(
        x.startswith(("core:coverage_claims:", "core:coverage_scopes:"))
        for x in omissions
    )
    if not coverage_incomplete:
        for row in tables.get("ref_coverage_proofs", []):
            try:
                with account_verification(work):
                    _charge(work, "metadata_units", 1)
                    key = (
                        row["observation_origin_uuidv4"],
                        row["ref_observation_uuidv7"],
                    )
                    identity = (*key, row["ref_claim_provenance"])
                    observation, claim_wire = (
                        observations.get(key),
                        claims.get(identity),
                    )
                    claim = None if claim_wire is None else claim_from_wire(claim_wire)
                    if observation is None or claim is None:
                        omissions.append(
                            "core:ref_coverage_proofs: original Claim or subject requires receiver baseline/input"
                        )
                    scope = CoreCoverageScope(
                        "ref_observation",
                        tuple(json.loads(row["owner_coordinates_json"])),
                    )
                    scope_json = encode_metered(work, scope.coordinates)
                    if (
                        row["owner_kind"] != scope.owner_kind
                        or scope_json != row["owner_coordinates_json"]
                    ):
                        raise ValueError("invalid original Coverage proof owner")
                    if scope.coordinates[-1] != "notes-mapping-inventory":
                        raise ValueError("unsupported Coverage proof kind")
                    history = coverage_histories.get(scope_json, [])
                    matched = [
                        item
                        for item in history
                        if item["observed_at_us"] == row["observed_at_us"]
                        and item["state"] == row["coverage_state"]
                    ]
                    if len(matched) > 1:
                        raise ValueError("ambiguous original Coverage Claim")
                    if not matched:
                        omissions.append(
                            "core:ref_coverage_proofs: original Coverage Claim requires receiver baseline/input"
                        )
                    group_wire = {
                        "observation_origin_uuidv4": key[0],
                        "ref_observation_uuidv7": key[1],
                        "ref_claim_provenance_json": identity[2],
                        "object_format": row["object_format"],
                        "root_object_oid": row["root_object_oid"],
                        "interpretation_kind": row["interpretation_kind"],
                        "interpretation_version": row["interpretation_version"],
                        "interpretation_scope": row["interpretation_scope"],
                        "group_scope": row["group_scope"],
                        "status": row["group_status"],
                        "membership_json": row["group_membership"],
                        "provenance_json": row["group_provenance"],
                    }
                    if _wire_key(group_wire, work) not in groups:
                        omissions.append(
                            "core:ref_coverage_proofs: original whole Group row missing; exact coordinates retained"
                        )
                    if claim is None:
                        _precheck_unresolved_notes(row, group_wire, "group", work)
                        group = None
                    else:
                        group = mapping_group_from_wire(group_wire, claim)
                    structures = deserialize_structures(
                        row["structures_json"],
                        work,
                        max_structures=max_records,
                        max_bytes=max_row_bytes,
                    )
                    verification = _provenance(row["verification_provenance"])
                    if (
                        verification.qualification != "receiver_intrinsic"
                        or verification.decoder != "git-native-notes-inventory"
                        or verification.decoder_version != "1"
                        or row["coverage_state"] != "complete"
                    ):
                        raise ValueError(
                            "supported original inventory verification required"
                        )
                    for native in structures:
                        _charge(work, "metadata_units", 1)
                        if native.native_type not in ("commit", "tree"):
                            raise ValueError(
                                "inventory proof contains nonstructural body"
                            )
                        native.validate()
                        parse_metadata(
                            native.object_oid.object_format,
                            native.native_type,
                            native.body,
                        )
                    if claim is not None and matched:
                        coverage = CoverageClaim(
                            scope,
                            row["observed_at_us"],
                            row["coverage_state"],
                            matched[0]["details_json"],
                        )
                        proof = RefNotesInventoryCoverageProof(
                            coverage, group, verification, structures
                        )
                        verify_ref_notes_inventory(
                            proof,
                            work,
                            max_structures=max_records,
                            max_bytes=max_row_bytes,
                        )
                candidates.append(
                    _record(
                        "coverage_proof",
                        (
                            *identity,
                            row["observed_at_us"],
                            row["verification_provenance"],
                        ),
                        {
                            "observation": observation,
                            "claim": claim_wire,
                            "repository_present": observation is not None
                            and observation["repository_uuidv4"] in repositories,
                            "scope_json": scope_json,
                            "history": history,
                            "group": group_wire,
                            "observed_at_us": row["observed_at_us"],
                            "state": row["coverage_state"],
                            "verification_provenance_json": row[
                                "verification_provenance"
                            ],
                            "structures_json": row["structures_json"],
                        },
                        "ref_coverage_proofs",
                        work,
                    )
                )
            except CoreFailure as error:
                if error.code in ("BUDGET", "QUERY_BUDGET"):
                    omissions.append("core:ref_coverage_proofs: finite salvage budget")
                    exhausted = True
                    break
                omissions.append(
                    f"core:ref_coverage_proofs: invalid candidate ({error})"
                )
            except (ValueError, TypeError, AttributeError, KeyError) as error:
                omissions.append(
                    f"core:ref_coverage_proofs: invalid candidate ({error})"
                )
    return RefSalvageScan(candidates, omissions, exhausted)


def _complete_enumeration_section(core, section, work):
    """Resolve exact original link dependencies from the validated baseline."""
    observations, claims = {}, {}
    for row in section["ref_observations"]:
        _charge(work, "metadata_units", 1)
        subject = observation_from_wire(row)
        old = observations.setdefault(subject.ref_observation_key.key, subject)
        if old != subject:
            raise CoreFailure(
                "INCOMPATIBLE_REPLAY", subject.ref_observation_key, "subject changed"
            )
    for row in section["ref_observation_claims"]:
        _charge(work, "metadata_units", 1)
        claim = claim_from_wire(row)
        old = claims.setdefault(claim.identity, claim)
        if old != claim:
            raise CoreFailure("INCOMPATIBLE_REPLAY", claim.identity, "Claim changed")
    completed = dict(section)
    completed["ref_observations"] = list(section["ref_observations"])
    completed["ref_observation_claims"] = list(section["ref_observation_claims"])
    checked = {}
    for link in section["ref_enumeration_links"]:
        _charge(work, "metadata_units", 1)
        key = RefObservationKey(
            link["observation_origin_uuidv4"], link["ref_observation_uuidv7"]
        )
        identity = (*key.key, link["claim_provenance_json"])
        if key.key in observations and identity in claims:
            continue
        if key.key not in checked:
            try:
                checked[key.key] = core.ref_observation(key, work)
            except CoreFailure as error:
                if error.code == "OBSERVATION_UNAVAILABLE":
                    return None
                raise
        projection = checked[key.key]
        if (
            key.key in observations
            and observations[key.key] != projection.ref_observation
        ):
            raise CoreFailure(
                "INCOMPATIBLE_REPLAY", key, "subject differs from baseline"
            )
        if key.key not in observations:
            subject = projection.ref_observation
            _charge(work, "input_bytes", 2 * len(subject.ref_name_bytes))
            observations[key.key] = subject
            completed["ref_observations"].append(observation_to_wire(subject))
        if identity not in claims:
            match = None
            for candidate in projection.claims:
                _charge(work, "metadata_units", 1)
                if encode_metered(work, candidate.provenance.key) == identity[2]:
                    match = candidate
                    break
            if match is None:
                return None
            if match.symbolic_target_ref_name is not None:
                _charge(work, "input_bytes", 2 * len(match.symbolic_target_ref_name))
            claims[identity] = match
            completed["ref_observation_claims"].append(claim_to_wire(match))
    return completed


def _repository_dependency(core, repository, supplied, work):
    if supplied:
        core.admit_repository(repository)
        return
    _charge(work, "metadata_units", 1)
    if not core.sql(
        "SELECT 1 FROM repositories WHERE repository_uuidv4=?", (repository,)
    ):
        raise CoreFailure(
            "MISSING_DEPENDENCY", repository, "original repository unavailable"
        )


def _complete_claim_payload(core, payload, kind, work):
    """Resolve a missing original subject/Claim without synthesizing either."""
    if payload["observation"] is not None and payload["claim"] is not None:
        return payload
    wire = payload.get("group") if kind == "ref_coverage_proof" else payload.get("unit")
    if payload["claim"] is not None:
        supplied = claim_from_wire(payload["claim"])
        key = supplied.ref_observation_key
    elif type(wire) is dict:
        supplied = None
        key = RefObservationKey(
            wire["observation_origin_uuidv4"], wire["ref_observation_uuidv7"]
        )
    else:
        raise ValueError("original Claim coordinates required")
    try:
        projection = core.ref_observation(key, work)
    except CoreFailure as error:
        if error.code == "OBSERVATION_UNAVAILABLE":
            return None
        raise
    subject = projection.ref_observation
    if payload["observation"] is not None:
        if observation_from_wire(payload["observation"]) != subject:
            raise CoreFailure(
                "INCOMPATIBLE_REPLAY", key, "subject differs from baseline"
            )
    else:
        _charge(work, "input_bytes", 2 * len(subject.ref_name_bytes))
    if supplied is None:
        coordinate = wire["ref_claim_provenance_json"]
        for candidate in projection.claims:
            _charge(work, "metadata_units", 1)
            if encode_metered(work, candidate.provenance.key) == coordinate:
                supplied = candidate
                break
        if supplied is None:
            return None
        if supplied.symbolic_target_ref_name is not None:
            _charge(work, "input_bytes", 2 * len(supplied.symbolic_target_ref_name))
    return dict(
        payload,
        observation=payload["observation"]
        if payload["observation"] is not None
        else observation_to_wire(subject),
        claim=payload["claim"]
        if payload["claim"] is not None
        else claim_to_wire(supplied),
    )


def admit_ref_unit(core, kind, payload, work):
    """Admit one redecoded subject, result or complete original event.

    Embedded dependencies make each unit independent of JSONL ordering. A
    source repository row is only a nominal identity, not issuer authentication.
    """
    if kind == "ref_mapping_content":
        if type(payload) is not dict or set(payload) != {"unit"}:
            raise ValueError("exact shared Mapping content required")
        mapping = mapping_from_wire(payload["unit"])
        _charge(work, "metadata_units", 1)
        existed = bool(
            core.sql(
                "SELECT 1 FROM notes_mappings WHERE object_format=? AND root_object_oid=? AND interpretation_kind=? AND interpretation_version=? AND interpretation_scope=? AND annotated_object_oid=? AND note_object_oid=? AND mapping_path_json=?",
                mapping.key,
            )
        )
        core.admit_notes_mapping(mapping, work)
        return existed
    if type(payload) is not dict or type(payload.get("repository_present")) is not bool:
        raise ValueError("typed original repository dependency required")
    if kind == "ref_coverage":
        if set(payload) != {
            "observation",
            "repository_present",
            "scope_json",
            "history",
        }:
            raise ValueError("exact Coverage candidate shape required")
        if payload["observation"] is None:
            raw_scope = payload["scope_json"]
            if type(raw_scope) is not str:
                raise ValueError("canonical Coverage scope required")
            _charge(work, "input_bytes", 2 * len(raw_scope))
            coordinates = json.loads(raw_scope)
            if type(coordinates) is not list or len(coordinates) != 3:
                raise ValueError("typed Coverage scope required")
            key = RefObservationKey(*coordinates[:2])
            try:
                projection = core.ref_observation(key, work)
            except CoreFailure as error:
                if error.code == "OBSERVATION_UNAVAILABLE":
                    return None
                raise
            subject = projection.ref_observation
            _charge(work, "input_bytes", 2 * len(subject.ref_name_bytes))
            payload = dict(payload, observation=observation_to_wire(subject))
        observation = observation_from_wire(payload["observation"])
        scope, history = _coverage_history(payload, observation, work)
        _repository_dependency(
            core, observation.repository_uuidv4, payload["repository_present"], work
        )
        core.admit_ref_observation(observation)
        _charge(work, "metadata_units", 1)
        scope_exists = bool(
            core.sql(
                "SELECT 1 FROM coverage_scopes WHERE owner_kind=? AND owner_coordinates_json=?",
                (scope.owner_kind, scope.encoded),
            )
        )
        core.admit_coverage_scope(scope)
        results = _admit_coverage_history(core, scope, history, work)
        if not results:
            return scope_exists
        if results[-1] == "stale":
            return None
        return results[-1] == "duplicate"
    if kind == "ref_subject":
        if set(payload) != {"observation", "repository_present"}:
            raise ValueError("exact subject candidate shape required")
        observation = observation_from_wire(payload["observation"])
        _charge(work, "metadata_units", 1)
        existed = bool(
            core.sql(
                "SELECT 1 FROM ref_observations WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=?",
                observation.ref_observation_key.key,
            )
        )
        _repository_dependency(
            core, observation.repository_uuidv4, payload["repository_present"], work
        )
        core.admit_ref_observation(observation)
        return existed
    if kind in (
        "ref_claim",
        "ref_mapping",
        "ref_group",
        "ref_evidence",
        "ref_note",
        "ref_coverage_proof",
    ):
        expected = {"observation", "claim", "repository_present"}
        if kind == "ref_coverage_proof":
            expected |= {
                "scope_json",
                "history",
                "group",
                "observed_at_us",
                "state",
                "verification_provenance_json",
                "structures_json",
            }
        elif kind != "ref_claim":
            expected.add("unit")
        if set(payload) != expected:
            raise ValueError("exact claim candidate shape required")
        payload = _complete_claim_payload(core, payload, kind, work)
        if payload is None:
            return None
        section = {
            "ref_observations": [payload["observation"]],
            "ref_observation_claims": [payload["claim"]],
            "ref_enumeration_observations": [],
            "ref_enumeration_links": [],
        }
        observations, claims, _, _ = decode_ref_units(section)
        if len(observations) != 1 or len(claims) != 1:
            raise ValueError("one original subject and Claim required")
        observation = next(iter(observations.values()))
        claim = next(iter(claims.values()))
        _charge(work, "metadata_units", 1)
        claim_existed = bool(
            core.sql(
                "SELECT 1 FROM ref_observation_claims WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND provenance=?",
                claim.identity,
            )
        )
        _repository_dependency(
            core, observation.repository_uuidv4, payload["repository_present"], work
        )
        core.admit_ref_observation(observation)
        core.admit_ref_observation_claim(claim)
        if kind == "ref_claim":
            return claim_existed
        if kind == "ref_coverage_proof":
            scope, history = _coverage_history(payload, observation, work)
            matching = [
                x
                for x in history
                if (x.observed_at_us, x.state)
                == (payload["observed_at_us"], payload["state"])
            ]
            if not matching:
                scope_json = encode_metered(work, scope.coordinates)
                for (
                    owner,
                    coords,
                    observed,
                    state,
                    details,
                ) in core.exchange_metadata_rows("coverage_claims", (), work):
                    _charge(work, "metadata_units", 1)
                    if (owner, coords, observed, state) != (
                        scope.owner_kind,
                        scope_json,
                        payload["observed_at_us"],
                        payload["state"],
                    ):
                        continue
                    try:
                        matching.append(CoverageClaim(scope, observed, state, details))
                    except (
                        ValueError,
                        TypeError,
                        RecursionError,
                        OverflowError,
                    ) as error:
                        core._integrity_stop(
                            (scope, "invalid stored Coverage Claim", str(error))
                        )
                if not matching:
                    return None
                history = sorted(
                    (*history, matching[0]), key=lambda x: (x.observed_at_us, x.state)
                )
            if len(matching) != 1:
                core._integrity_stop((scope, "duplicate stored Coverage Claim"))
            group = mapping_group_from_wire(payload["group"], claim)
            structures = deserialize_structures(
                payload["structures_json"],
                work,
                max_structures=100_000,
                max_bytes=work.limits.note_bytes,
            )
            proof = RefNotesInventoryCoverageProof(
                matching[0],
                group,
                _provenance(payload["verification_provenance_json"]),
                structures,
            )
            verify_ref_notes_inventory(
                proof, work, max_structures=100_000, max_bytes=work.limits.note_bytes
            )
            core.admit_notes_mapping_group(group, work)
            core.admit_coverage_scope(scope)
            _admit_coverage_history(core, scope, history, work)
            _charge(work, "metadata_units", 1)
            if not core.sql(
                "SELECT 1 FROM coverage_claims WHERE owner_kind=? AND owner_coordinates_json=? AND observed_at_us=? AND coverage_state=?",
                (
                    scope.owner_kind,
                    scope.encoded,
                    matching[0].observed_at_us,
                    matching[0].state,
                ),
            ):
                return None
            existing = core.ref_coverage_proofs(matching[0], work)
            existed = any(p == proof for p in existing)
            core.admit_ref_coverage_proof(proof, work)
            _, instance = core.catalog_identity()
            local = replace(
                proof,
                verification_provenance=Provenance(
                    "salvage-receiver:" + instance,
                    encode_metered(
                        work,
                        [
                            "source-inventory-evidence",
                            *proof.verification_provenance.key,
                        ],
                    ),
                    encode_metered(
                        work,
                        [
                            "claim",
                            *claim.ref_observation_key.key,
                            list(claim.provenance.key),
                            "group",
                            *claim.root_object_oid.key,
                            group.interpretation_kind,
                            group.interpretation_version,
                            group.interpretation_scope,
                            group.group_scope,
                            list(group.provenance.key),
                        ],
                    ),
                    "git-native-notes-inventory",
                    "1",
                    "receiver_intrinsic",
                ),
            )
            core.admit_ref_coverage_proof(local, work)
            return existed
        wire = payload["unit"]
        if type(wire) is not dict:
            raise ValueError("typed original Notes unit required")
        if kind == "ref_mapping":
            mapping = mapping_claim_from_wire(wire, claim)
            _charge(work, "metadata_units", 1)
            existed = bool(
                core.sql(
                    "SELECT 1 FROM notes_mapping_claims WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND ref_claim_provenance=? AND object_format=? AND root_object_oid=? AND interpretation_kind=? AND interpretation_version=? AND interpretation_scope=? AND annotated_object_oid=? AND note_object_oid=? AND mapping_path_json=? AND provenance=?",
                    mapping.key,
                )
            )
            core.admit_notes_mapping_claim(mapping)
            return existed
        if kind == "ref_group":
            group = mapping_group_from_wire(wire, claim)
            _charge(work, "metadata_units", 1)
            existed = bool(
                core.sql(
                    "SELECT 1 FROM notes_mapping_groups WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND ref_claim_provenance=? AND object_format=? AND root_object_oid=? AND interpretation_kind=? AND interpretation_version=? AND interpretation_scope=? AND group_scope=? AND status=? AND membership=? AND provenance=?",
                    group.key,
                )
            )
            core.admit_notes_mapping_group(group, work)
            return existed
        evidence = mapping_evidence_from_wire(wire, claim)
        if kind == "ref_evidence":
            mapping = evidence.mapping
            projection = core.notes_mapping_projection(
                claim,
                mapping.annotated_object_oid,
                mapping.interpretation_kind,
                mapping.interpretation_version,
                mapping.interpretation_scope,
                work,
            )
            existed = False
            for record in projection.evidence:
                _charge(work, "metadata_units", 1)
                _charge(work, "input_bytes", len(record.proof_bundle))
                if (
                    record.mapping == mapping
                    and record.verification_scope == evidence.verification_scope
                    and record.provenance == evidence.provenance
                    and record.proof_bundle == wire["proof_bundle_json"]
                ):
                    existed = True
                    break
            core.admit_notes_mapping_evidence(evidence, work)
        else:
            native, copy_id = ref_note_from_wire(wire, evidence)
            _charge(work, "metadata_units", 1)
            existed = bool(
                core.sql(
                    "SELECT 1 FROM ref_retained_notes WHERE object_format=? AND object_oid=? AND physical_copy_uuidv4=?",
                    (*native.object_oid.key, copy_id),
                )
            )
            core.admit_ref_note(evidence, native, copy_id, work)
        _, instance = core.catalog_identity()
        local = replace(
            evidence,
            provenance=Provenance(
                "salvage-receiver:" + instance,
                encode_metered(work, ["source-evidence", *evidence.provenance.key]),
                encode_metered(
                    work,
                    [
                        "claim",
                        *claim.ref_observation_key.key,
                        list(claim.provenance.key),
                        "mapping",
                        *evidence.mapping.key,
                    ],
                ),
                "native-notes",
                "1",
                "receiver_intrinsic",
            ),
        )
        core.admit_notes_mapping_evidence(local, work)
        return existed
    if kind == "ref_enumeration":
        if set(payload) != {"section", "repository_present"}:
            raise ValueError("exact enumeration candidate shape required")
        section = payload["section"]
        if type(section) is not dict or set(section) != {
            "ref_observations",
            "ref_observation_claims",
            "ref_enumeration_observations",
            "ref_enumeration_links",
        }:
            raise ValueError("complete typed enumeration section required")
        section = _complete_enumeration_section(core, section, work)
        if section is None:
            return None
        _, _, events, links = decode_ref_units(section)
        if len(events) != 1:
            raise ValueError("one original event required")
        event = next(iter(events.values()))
        bucket = links.get(event.identity, {})
        if len(section["ref_enumeration_links"]) != event.link_count:
            raise ValueError("whole original link count required")
        _charge(work, "metadata_units", 1)
        existed = bool(
            core.sql(
                "SELECT 1 FROM ref_enumeration_observations WHERE observation_origin_uuidv4=? AND enumeration_uuidv7=?",
                event.identity,
            )
        )
        _repository_dependency(
            core, event.repository_uuidv4, payload["repository_present"], work
        )
        core.admit_ref_enumeration(
            event, tuple(bucket[i] for i in sorted(bucket)), work
        )
        return existed
    raise ValueError("unknown typed ref salvage unit")


def _stop_for_sqlite_corruption(directory, error):
    code = getattr(error, "sqlite_errorcode", 0)
    if type(code) is int and code & 255 in (
        sqlite3.SQLITE_CORRUPT,
        sqlite3.SQLITE_NOTADB,
    ):
        persist_catalog_stop(
            directory, "Confirmed Core SQLite corruption during salvage"
        )
        raise CoreFailure(
            "AUTHORITATIVE_CORRUPTION", "catalog", "stored Core SQLite corruption"
        ) from error


def admit_ref_unit_atomic(directory: Path, kind, payload, work):
    """Commit every dependency and receiver check of one candidate together."""
    directory = Path(directory)
    with catalog_gate(directory, exclusive=True):
        if (directory / "p1-recovery-stop.json").exists():
            raise CoreFailure("RECOVERY_STOP", "catalog", "catalog stopped")
        try:
            db = connect(directory / "core.sqlite3", "core")
        except sqlite3.DatabaseError as error:
            _stop_for_sqlite_corruption(directory, error)
            raise
        with closing(db):
            try:
                db.execute("BEGIN IMMEDIATE")
            except sqlite3.DatabaseError as error:
                _stop_for_sqlite_corruption(directory, error)
                raise
            try:
                with GitCore.for_transaction(db) as capability:
                    # Confirmed target damage must publish its stop fence even
                    # when a coordinator owns this transaction.
                    capability._directory = directory
                    guarded = _WorkCallbackBoundary(work, capability)
                    with account_verification(guarded):
                        result = admit_ref_unit(capability, kind, payload, guarded)
                if result is None:
                    # A missing dependency or stale terminal is not a partial
                    # admission: all writes of this individual unit roll back.
                    db.rollback()
                    return None
                try:
                    with catalog_completion(directory):
                        if (directory / "p1-recovery-stop.json").exists():
                            raise CoreFailure(
                                "RECOVERY_STOP", "catalog", "catalog stopped"
                            )
                        db.commit()
                except sqlite3.DatabaseError as error:
                    _stop_for_sqlite_corruption(directory, error)
                    raise
                return result
            except _WorkCallbackFailure as failure:
                if db.in_transaction:
                    db.rollback()
                raise failure.original from None
            except BaseException:
                if db.in_transaction:
                    db.rollback()
                raise


def _coverage_history(payload, observation, work):
    raw = payload["scope_json"]
    if type(raw) is not str:
        raise ValueError("canonical Coverage scope required")
    _charge(work, "input_bytes", 2 * len(raw))
    scope = CoreCoverageScope("ref_observation", tuple(json.loads(raw)))
    if (
        scope.encoded != raw
        or scope.coordinates[:2] != observation.ref_observation_key.key
    ):
        raise ValueError("Coverage owner differs from original subject")
    values = payload["history"]
    if type(values) is not list:
        raise ValueError("bounded original Coverage history required")
    history = []
    for value in values:
        _charge(work, "metadata_units", 1)
        if type(value) is not dict or set(value) != {
            "observed_at_us",
            "state",
            "details_json",
        }:
            raise ValueError("typed Coverage Claim required")
        details = value["details_json"]
        if details is not None and type(details) is not str:
            raise ValueError("canonical Coverage details required")
        _charge(work, "input_bytes", len(details or ""))
        history.append(
            CoverageClaim(scope, value["observed_at_us"], value["state"], details)
        )
    coordinates = [(x.observed_at_us, x.state) for x in history]
    if coordinates != sorted(set(coordinates)):
        raise ValueError("whole ordered unique Coverage history required")
    return scope, history


def _admit_coverage_history(core, scope, history, work):
    """Recognize checked historical replay before the current stale fence."""
    existing = {}
    scope_json = encode_metered(work, scope.coordinates)
    for owner, coords, observed, state, details in core.exchange_metadata_rows(
        "coverage_claims", (), work
    ):
        _charge(work, "metadata_units", 1)
        if (owner, coords) != (scope.owner_kind, scope_json):
            continue
        try:
            value = CoverageClaim(scope, observed, state, details)
        except (ValueError, TypeError, RecursionError, OverflowError) as error:
            core._integrity_stop((scope, "invalid stored Coverage Claim", str(error)))
        key = (value.observed_at_us, value.state)
        if key in existing:
            core._integrity_stop((scope, "duplicate stored Coverage Claim"))
        existing[key] = value
    results = []
    for value in history:
        _charge(work, "metadata_units", 1)
        key = (value.observed_at_us, value.state)
        if key in existing:
            # Advisory details are not part of Coverage identity; preserve the
            # existing value exactly as the production admission contract does.
            result = "duplicate"
        else:
            result = core.admit_coverage(value)
        if result == "insert":
            existing[key] = value
        results.append(result)
    return results
