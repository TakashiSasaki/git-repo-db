"""Recheck enduring admission invariants without executing recovered schema."""

import codecs
import hashlib
import json
import re
import sqlite3

from repo_catalog.adapters.sqlite.p1_schema import expected_schema
from repo_catalog.domain.p1_context import (
    CoverageScope,
    EventReportKey,
    FieldClock,
    MappingClaimKey,
    MappingDisposition,
    ResourceKey,
    ResourceRepositoryRelation,
    TransferEventReport,
    canonical,
    validate_provider_repository_scope,
)
from repo_catalog.domain.p1_core import CoreFailure
from repo_catalog.domain.parent_report import validate_parent_report
from repo_catalog.domain.recovery import BackupValidationError


class StoredContextInvariantError(BackupValidationError):
    """A trusted pure Context decoder proved retained domain evidence invalid.

    This explicit boundary retains the decoder cause for diagnostics without
    confusing a deterministic stored-data violation with an unexpected adapter
    ValueError, unavailable I/O or exhausted resource budget.
    """


class StoredRefInvariantError(BackupValidationError):
    """A trusted typed RefObservation reader found invalid stored authority."""


class RefValidationBudgetError(BackupValidationError):
    """A finite validation budget was exhausted; this does not prove corruption."""


_REF_AUTHORITY_TABLES = frozenset(
    {
        "ref_observations",
        "ref_observation_claims",
        "ref_enumeration_observations",
        "ref_enumeration_links",
        "notes_mappings",
        "notes_mapping_claims",
        "notes_mapping_groups",
        "notes_mapping_evidence",
        "ref_coverage_proofs",
        "ref_retained_notes",
    }
)


def _charge_validation_lengths(connection, table, columns, work):
    """Reserve full variable inputs before a trusted stored-data scan."""
    if not columns:
        return
    size_expr = "+".join(f'coalesce(octet_length("{column}"),0)' for column in columns)
    cursor = connection.execute(f'SELECT {size_expr} FROM "{table}"')
    while True:
        work.require("metadata_units", 1)
        try:
            row = cursor.fetchone()
        except BaseException:
            work.abandon("metadata_units")
            raise
        work.charge("metadata_units", 0 if row is None else 1)
        if row is None:
            return
        size = row[0]
        if type(size) is not int or size < 0:
            raise BackupValidationError("Invalid stored validation input length")
        work.require("input_bytes", size)
        work.charge("input_bytes", size)


def charge_ref_integrity_inputs(connection, work):
    """Reserve variable inputs before SQLite's full-table integrity check."""
    for table in sorted(_REF_AUTHORITY_TABLES):
        columns = [
            row[1]
            for row in connection.execute(f'PRAGMA table_xinfo("{table}")')
            if row[2].upper() in ("TEXT", "BLOB") and not row[6]
        ]
        _charge_validation_lengths(connection, table, columns, work)


def _charge_note_comparisons(connection, work):
    """Bound exact-body comparisons made by trusted cross-family guards."""
    cursor = connection.execute(
        "SELECT count(*),sum(octet_length(body)) FROM ref_retained_notes GROUP BY object_format,object_oid"
    )
    while True:
        work.require("metadata_units", 1)
        try:
            row = cursor.fetchone()
        except BaseException:
            work.abandon("metadata_units")
            raise
        work.charge("metadata_units", 0 if row is None else 1)
        if row is None:
            break
        ref_count, ref_bytes = row
        amount = 2 * ref_count * ref_bytes
        work.require("input_bytes", amount)
        work.charge("input_bytes", amount)


def validate_stored_ref_authority(connection, work, budget):
    """Recheck every ref family and physical note copy on one pinned snapshot.

    Each scan sizes keys before materializing them, and the Core's typed readers
    independently validate subject, original claims, link boundaries, mappings,
    proofs and bodies. No recovered SQL or sender verification is trusted.
    """
    from repo_catalog.adapters.sqlite.p1_core import Core
    from repo_catalog.domain.p1_core import OID, CoreCoverageScope
    from repo_catalog.domain.p1_coverage import CoverageClaim
    from repo_catalog.domain.ref_observation import RefObservationKey

    remaining = budget.max_input_records
    max_bytes = budget.max_input_bytes
    max_units = budget.max_input_records

    def scan(table, columns):
        nonlocal remaining
        order = ",".join('"' + c + '"' for c in columns)
        lengths = "+".join(
            f'coalesce(octet_length("{column}"),0)' for column in columns
        )
        sizes = connection.execute(f'SELECT {lengths} FROM "{table}" ORDER BY {order}')
        values = None
        while True:
            work.require("metadata_units", 2)
            try:
                size_row = sizes.fetchone()
            except BaseException:
                work.abandon("metadata_units")
                raise
            work.charge("metadata_units", 1 if size_row is None else 2)
            if size_row is None:
                break
            if remaining == 0:
                raise CoreFailure("BUDGET", table, "finite backup record limit")
            remaining -= 1
            size = size_row[0]
            if type(size) is not int or not 0 <= size <= max_bytes:
                raise CoreFailure("BUDGET", table, "finite backup metadata limit")
            work.require("input_bytes", size)
            try:
                if values is None:
                    values = connection.execute(
                        f'SELECT {order} FROM "{table}" ORDER BY {order}'
                    )
                row = values.fetchone()
                if row is None:
                    raise StoredRefInvariantError("Ref validation scan changed")
            except BaseException:
                work.abandon("input_bytes")
                raise
            work.charge("input_bytes", size)
            yield row

    def charge_metadata(units):
        work.require("metadata_units", units)
        work.charge("metadata_units", units)

    connection.row_factory = sqlite3.Row
    connection.execute("BEGIN")
    try:
        with Core.for_transaction(connection) as core:
            for row in scan(
                "ref_observations",
                ("observation_origin_uuidv4", "ref_observation_uuidv7"),
            ):
                key = core._stored("ref observation", RefObservationKey, *row)
                core.ref_observation(
                    key, work, max_claims=max_units, max_bytes=max_bytes
                )

            for row in scan(
                "ref_enumeration_observations",
                ("observation_origin_uuidv4", "enumeration_uuidv7"),
            ):
                if (
                    core.ref_enumeration(
                        *row, work, max_links=max_units, max_bytes=max_bytes
                    )
                    is None
                ):
                    raise StoredRefInvariantError("Missing enumerated event")

            mapping_cols = (
                "object_format",
                "root_object_oid",
                "interpretation_kind",
                "interpretation_version",
                "interpretation_scope",
                "annotated_object_oid",
                "note_object_oid",
                "mapping_path_json",
            )
            for row in scan("notes_mappings", mapping_cols):
                mapping = core._stored(
                    "notes mapping",
                    lambda value: core._decode_mapping(
                        value, work=work, max_metadata_bytes=max_bytes
                    ),
                    row,
                )
                charge_metadata(4)
                core._assert_stored_mapping(mapping, "notes mapping")

            common = (
                "observation_origin_uuidv4",
                "ref_observation_uuidv7",
                "ref_claim_provenance",
                "object_format",
                "root_object_oid",
                "interpretation_kind",
                "interpretation_version",
                "interpretation_scope",
            )
            scopes = set()
            for table in (
                "notes_mapping_claims",
                "notes_mapping_evidence",
                "notes_mapping_groups",
            ):
                columns = common + (
                    () if table == "notes_mapping_groups" else ("annotated_object_oid",)
                )
                for row in scan(table, columns):
                    values = tuple(row)
                    # A group can be empty, so use a typed sentinel only as a
                    # projection filter, never as a stored or exported object.
                    target = (
                        values[8]
                        if len(values) > 8
                        else "0" * (40 if values[3] == "sha1" else 64)
                    )
                    scope_key = (*values[:8], target)
                    key_bytes = sum(
                        len(value.encode("utf-8"))
                        for value in scope_key
                        if isinstance(value, str)
                    )
                    work.require("input_bytes", key_bytes)
                    scopes.add(scope_key)
                    work.charge("input_bytes", key_bytes)
            for (
                origin,
                ref_id,
                provenance,
                fmt,
                root,
                kind,
                version,
                scope,
                target,
            ) in scopes:
                row = core._bounded_stored_row(
                    "ref_observation_claims",
                    (origin, ref_id, provenance),
                    work,
                    max_bytes,
                )
                if row is None:
                    raise StoredRefInvariantError("Missing mapping result Claim")
                claim = core._stored(
                    "mapping Claim",
                    lambda value: core._decode_ref_claim(
                        value, work=work, max_metadata_bytes=max_bytes
                    ),
                    row,
                )
                root_object_oid = core._stored("mapping root", OID, fmt, root)
                target_object_oid = core._stored("mapping target", OID, fmt, target)
                if claim.root_object_oid != root_object_oid:
                    raise StoredRefInvariantError("Mapping Claim/root mismatch")
                core.notes_mapping_projection(
                    claim,
                    target_object_oid,
                    kind,
                    version,
                    scope,
                    work,
                    max_units=max_units,
                    max_bytes=max_bytes,
                )

            notes = total_bytes = 0
            for row in scan(
                "ref_retained_notes",
                ("object_format", "object_oid", "physical_copy_uuidv4"),
            ):
                copy = core._bounded_stored_row(
                    "ref_retained_notes", tuple(row), work, max_bytes, max_bytes
                )
                if copy is None:
                    raise StoredRefInvariantError("Missing retained note copy")
                _, _, body = core._validate_stored_ref_note(
                    copy, work, max_bytes, max_bytes
                )
                notes += 1
                total_bytes += len(body)

            proof_claims = {}
            for row in scan(
                "ref_coverage_proofs",
                ("owner_coordinates_json", "observed_at_us", "coverage_state"),
            ):
                coords, observed, state = row
                if not isinstance(coords, str):
                    raise StoredRefInvariantError("Invalid Coverage owner encoding")
                identity = (coords, observed, state)
                work.require("input_bytes", len(coords.encode("utf-8")))
                proof_claims[identity] = proof_claims.get(identity, 0) + 1
                work.charge("input_bytes", len(coords.encode("utf-8")))
            for (coords, observed, state), expected in proof_claims.items():
                claim = core._stored(
                    "ref Coverage Claim",
                    lambda value: CoverageClaim(
                        CoreCoverageScope("ref_observation", tuple(json.loads(value))),
                        observed,
                        state,
                    ),
                    coords,
                )
                if claim.scope.encoded != coords:
                    raise StoredRefInvariantError("Noncanonical Coverage owner")
                proofs = core.ref_coverage_proofs(
                    claim,
                    work,
                    max_proofs=max_units,
                    max_bytes=max_bytes,
                    max_structures=budget.max_input_records,
                )
                if len(proofs) != expected:
                    raise StoredRefInvariantError("Coverage proof count mismatch")
            return notes, total_bytes
    except sqlite3.OperationalError as error:
        if str(error).startswith("Could not decode to UTF-8 column"):
            raise StoredRefInvariantError("Invalid stored ref text encoding") from error
        raise
    except CoreFailure as error:
        if error.code in ("BUDGET", "QUERY_BUDGET"):
            raise RefValidationBudgetError(str(error)) from error
        if error.code == "AUTHORITATIVE_CORRUPTION":
            raise StoredRefInvariantError(str(error)) from error
        raise
    finally:
        if connection.in_transaction:
            connection.rollback()


# INSERT-time replay/current-terminal predicates are deliberately excluded:
# old Coverage evidence remains valid history after a later terminal arrives,
# and rrr_no_rebind / rmd_no_rebind are INSERT-time replay/stale guards.
_PERSISTENT_GUARDS = {
    "core": {
        "relation_targets",
        "notes_mapping_group_targets",
        "ref_absence_subject",
        "ref_notes_same_representation",
        "metadata_same_representation",
        "intrinsic_claim_guard",
        "intrinsic_group_guard",
        "core_coverage_members",
        "ref_coverage_proof_requires_typed_evidence",
    },
    "context": {
        "coverage_proof_owner",
        "source_coverage_owner",
        "rrr_event_report_time",
    },
}


def validate_stored_context_relations(connection: sqlite3.Connection) -> None:
    """Validate enduring stored invariants on Context repository relations and scopes.

    Evaluates stored rows using trusted domain validators and relational checks
    without executing untrusted triggers or replaying INSERT-only stale predicates.
    """
    try:
        from repo_catalog.domain.resource_identification import ResourceIdentification
        from repo_catalog.domain.resource_stage import validate_stage_storage

        validate_stage_storage(connection)
        for row in connection.execute(
            "SELECT service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id FROM resources"
        ):
            ResourceIdentification.from_storage(ResourceKey(*row[:3]), row[3:])
        mapping_claims: set[tuple[str, str, str, str, str, str, str]] = set()
        relations: list[ResourceRepositoryRelation] = []
        for row in connection.execute(
            """SELECT service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,
                      clock_json,target_json,provenance_json,observed_at_us
            FROM resource_repository_relations"""
        ):
            rel = ResourceRepositoryRelation(
                resource=ResourceKey(row[0], row[1], row[2]),
                relation_kind=row[3],
                clock=FieldClock.from_json(row[4]),
                target_json=row[5],
                provenance_json=row[6],
                observed_at_us=row[7],
            )
            relations.append(rel)
            if rel.relation_kind == "represents_repository":
                mapping_claims.add(rel.claim_key.coordinates())

        transfer_groups: dict[
            tuple[str, str, str, str, str], list[ResourceRepositoryRelation]
        ] = {}
        for rel in relations:
            support = rel.embedded_support
            if support is not None:
                for claim in support.supporting_claims:
                    if claim.coordinates() not in mapping_claims:
                        raise BackupValidationError(
                            "Stored Context relation references missing supporting MappingClaimKey"
                        )
            if rel.relation_kind in (
                "transfer_from_repository",
                "transfer_to_repository",
            ):
                key_coord = (
                    rel.resource.service_instance_uuidv4,
                    rel.resource.resource_kind,
                    rel.resource.provider_resource_id,
                    rel.clock_json,
                    rel.provenance_json,
                )
                transfer_groups.setdefault(key_coord, []).append(rel)

        for row in connection.execute(
            """SELECT service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,
                      claim_clock_json,claim_target_json,claim_provenance_json,
                      disposition_kind,disposition_clock_json,disposition_provenance_json,
                      observed_at_us,replacement_clock_json,replacement_target_json,replacement_provenance_json
            FROM repository_mapping_dispositions"""
        ):
            res = ResourceKey(row[0], row[1], row[2])
            claim_key = MappingClaimKey(
                resource=res,
                relation_kind=row[3],
                clock=FieldClock.from_json(row[4]),
                target_json=row[5],
                provenance_json=row[6],
            )
            if claim_key.coordinates() not in mapping_claims:
                raise BackupValidationError(
                    "Stored MappingDisposition references missing MappingClaimKey"
                )
            replacement_key = None
            if row[11] is not None or row[12] is not None or row[13] is not None:
                if row[11] is None or row[12] is None or row[13] is None:
                    raise BackupValidationError(
                        "Stored MappingDisposition has partial-null replacement"
                    )
                replacement_key = MappingClaimKey(
                    resource=res,
                    relation_kind=row[3],
                    clock=FieldClock.from_json(row[11]),
                    target_json=row[12],
                    provenance_json=row[13],
                )
                if replacement_key.coordinates() not in mapping_claims:
                    raise BackupValidationError(
                        "Stored MappingDisposition replacement MappingClaimKey is missing"
                    )
            MappingDisposition(
                claim_key=claim_key,
                disposition_kind=row[7],
                disposition_clock=FieldClock.from_json(row[8]),
                disposition_provenance_json=row[9],
                observed_at_us=row[10],
                replacement_claim_key=replacement_key,
            )

        scope_meta: dict[
            tuple[str, str, str, str, str], tuple[str, str, int | None]
        ] = {}
        for row in connection.execute(
            """SELECT service_instance_uuidv4,resource_kind,provider_resource_id,
                      relation_kind,members_json,provenance_json,scope_json,observed_at_us
            FROM resource_relations"""
        ):
            parsed_scope = json.loads(row[6])
            if row[3] == "parent":
                parent, subtype = validate_parent_report(
                    *row[:3], row[4], row[5], row[6], row[7]
                )
                if (
                    not connection.execute(
                        "SELECT 1 FROM resources WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND reference_document_kind=?",
                        (*row[:3], subtype or ""),
                    ).fetchone()
                    or not connection.execute(
                        "SELECT 1 FROM resources WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
                        parent.coordinates(),
                    ).fetchone()
                ):
                    raise BackupValidationError(
                        "Stored Parent report reference missing"
                    )
            if row[3] == "provider_repository_roles":
                members = tuple(ResourceKey(*m) for m in json.loads(row[4]))
                validate_provider_repository_scope(
                    ResourceKey(*row[:3]), members, row[5], row[6], row[7]
                )
                for member in members:
                    if not connection.execute(
                        "SELECT 1 FROM resources WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
                        member.coordinates(),
                    ).fetchone():
                        raise BackupValidationError(
                            "Stored Provider role member resource missing"
                        )
            if row[3] == "transfer_event_report":
                if not isinstance(parsed_scope, dict) or "clock" not in parsed_scope:
                    raise BackupValidationError(
                        "Stored transfer_event_report scope_json is missing clock"
                    )
                key_coord = (
                    row[0],
                    row[1],
                    row[2],
                    canonical(parsed_scope["clock"]),
                    row[5],
                )
                metadata = (row[6], row[4], row[7])
                if key_coord in scope_meta and scope_meta[key_coord] != metadata:
                    raise BackupValidationError(
                        "Conflicting stored transfer_event_report scopes for same EventReportKey"
                    )
                scope_meta[key_coord] = metadata
                transfer_groups.setdefault(key_coord, [])

        for key_coord, rels in transfer_groups.items():
            svc, r_kind, p_id, clk_json, prov_json = key_coord
            rep_key = EventReportKey(
                ResourceKey(svc, r_kind, p_id),
                FieldClock.from_json(clk_json),
                prov_json,
            )
            if not connection.execute(
                "SELECT 1 FROM resources WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
                rep_key.issue_parent.coordinates(),
            ).fetchone():
                raise BackupValidationError(
                    "Stored transfer event report parent issue resource is missing"
                )
            if key_coord not in scope_meta:
                raise BackupValidationError(
                    "Stored Transfer endpoint requires transfer_event_report scope"
                )
            scope_json, members_json, obs_us = scope_meta[key_coord]
            parsed_scope = json.loads(scope_json)
            from repo_catalog.domain.parent_report import (
                ParentObservation,
                ParentReportKey,
            )

            parent_key = ParentReportKey(
                rep_key.event_resource,
                parsed_scope.get("parent_members_json", ""),
                parsed_scope.get("parent_provenance_json", ""),
                parsed_scope.get("parent_scope_json", ""),
            )
            parent_row = connection.execute(
                "SELECT observed_at_us FROM resource_relations WHERE "
                "service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? "
                "AND relation_kind=? AND members_json=? AND provenance_json=? AND scope_json=?",
                parent_key.coordinates(),
            ).fetchone()
            if parent_row is None:
                raise BackupValidationError(
                    "Stored Transfer Event Report parent observation is missing"
                )
            report = TransferEventReport.from_stored_scope(
                rep_key,
                rels,
                scope_json,
                members_json,
                obs_us,
                parent_report=ParentObservation(parent_key, parent_row[0]),
            )
            if report.parent_issue != report.issue_resource:
                raise BackupValidationError(
                    "Stored Transfer Event Report has ineligible parent issue (G3=A Q-S10 violation)"
                )
            for provider in (
                report.from_provider_repository,
                report.to_provider_repository,
            ):
                if (
                    provider is not None
                    and not connection.execute(
                        "SELECT 1 FROM resources WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
                        provider.coordinates(),
                    ).fetchone()
                ):
                    raise BackupValidationError(
                        "Stored Transfer Provider endpoint resource is missing"
                    )

        for owner_kind, coords_json in connection.execute(
            "SELECT owner_kind,owner_coordinates_json FROM coverage_scopes"
        ):
            coords = json.loads(coords_json)
            if not isinstance(coords, list):
                raise BackupValidationError(
                    "Stored coverage_scopes coordinates must be a JSON array"
                )
            scope = CoverageScope(owner_kind, tuple(coords))
            if (
                scope.relation_repository_uuidv4 is not None
                and not connection.execute(
                    "SELECT 1 FROM repository_context WHERE repository_uuidv4=?",
                    (scope.relation_repository_uuidv4,),
                ).fetchone()
            ):
                raise BackupValidationError(
                    "Stored role-scoped CoverageScope references missing repository_context"
                )
    except BackupValidationError:
        raise
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        raise StoredContextInvariantError(
            f"Stored context relation invariant failed: {error}"
        ) from error


validate_context_relation_invariants = validate_stored_context_relations


def validate_stored_admission_guards(
    connection: sqlite3.Connection, role: str, *, work=None
) -> None:
    """Evaluate trusted packaged enduring BEFORE INSERT predicates on stored rows.

    integrity_check checks CHECK constraints, not relational admission triggers.
    Only packaged SQL is interpreted here; recovered trigger bodies are never run.
    """
    remaining = set(_PERSISTENT_GUARDS[role])
    for kind, name, _, sql in expected_schema(role):
        if kind != "trigger" or name not in remaining:
            continue
        match = re.fullmatch(
            r"CREATE TRIGGER \w+ BEFORE INSERT ON (\w+)\s+WHEN (.*?)\s+BEGIN.*",
            sql,
            flags=re.DOTALL,
        )
        if match is None:
            raise RuntimeError(f"Unsupported packaged recovery guard: {name}")
        table, predicate = match.groups()
        predicate = re.sub(r"\bNEW\.(\w+)", r'"recovery_candidate"."\1"', predicate)
        if work is not None and role == "core" and table in _REF_AUTHORITY_TABLES:
            columns = [
                row[1]
                for row in connection.execute(f'PRAGMA table_xinfo("{table}")')
                if row[2].upper() in ("TEXT", "BLOB") and not row[6]
            ]
            _charge_validation_lengths(connection, table, columns, work)
            if name == "ref_notes_same_representation":
                _charge_note_comparisons(connection, work)
        if connection.execute(
            f'SELECT 1 FROM "{table}" AS recovery_candidate WHERE {predicate} LIMIT 1'
        ).fetchone():
            raise BackupValidationError(
                f"Stored {role} domain admission invariant failed: {name}"
            )
        remaining.remove(name)
    if remaining:
        raise RuntimeError(f"Missing packaged recovery guards: {sorted(remaining)}")
    if role == "context":
        validate_stored_context_relations(connection)


def _skip_sql_quoted(sql: str, position: int) -> int:
    quote = sql[position]
    closing = "]" if quote == "[" else quote
    position += 1
    while position < len(sql):
        if sql[position] == closing:
            if position + 1 < len(sql) and sql[position + 1] == closing:
                position += 2
                continue
            return position + 1
        position += 1
    raise RuntimeError("Unterminated quoted packaged SQL")


def _packaged_checks(sql: str):
    """Extract balanced CHECK expressions only from trusted packaged DDL."""
    position = 0
    while position < len(sql):
        if sql[position] in "'\"`[":
            position = _skip_sql_quoted(sql, position)
            continue
        if sql.startswith("--", position):
            end = sql.find("\n", position)
            position = len(sql) if end < 0 else end + 1
            continue
        if sql.startswith("/*", position):
            end = sql.find("*/", position + 2)
            if end < 0:
                raise RuntimeError("Unterminated packaged SQL comment")
            position = end + 2
            continue
        match = re.match(r"[A-Za-z_][A-Za-z_0-9]*", sql[position:])
        if match is None:
            position += 1
            continue
        token = match.group()
        position += len(token)
        if token.upper() != "CHECK":
            continue
        while position < len(sql) and sql[position].isspace():
            position += 1
        if position >= len(sql) or sql[position] != "(":
            raise RuntimeError("Unsupported packaged CHECK syntax")
        start = position + 1
        depth = 1
        position += 1
        while position < len(sql) and depth:
            if sql.startswith("--", position):
                end = sql.find("\n", position)
                position = len(sql) if end < 0 else end + 1
                continue
            if sql.startswith("/*", position):
                end = sql.find("*/", position + 2)
                if end < 0:
                    raise RuntimeError("Unterminated packaged CHECK comment")
                position = end + 2
                continue
            if sql[position] in "'\"`[":
                position = _skip_sql_quoted(sql, position)
                continue
            if sql[position] == "(":
                depth += 1
            elif sql[position] == ")":
                depth -= 1
            position += 1
        if depth:
            raise RuntimeError("Unbalanced packaged CHECK expression")
        yield sql[start : position - 1]


def validate_stored_checks(
    connection: sqlite3.Connection, role: str, *, retained_bytes: bool, work=None
) -> None:
    # SQLite readonly integrity_check can report 'ok' without surfacing failed
    # application-UDF CHECKs. Re-evaluate every trusted expression explicitly.
    # SQLite CHECK accepts NULL: WHERE NOT(expression) preserves that meaning.
    body_tables = {
        "retained_metadata",
        "ref_retained_notes",
        "text_bodies",
    }
    for kind, table, _, sql in expected_schema(role):
        if kind != "table" or (table in body_tables) != retained_bytes:
            continue
        for expression in _packaged_checks(sql):
            if work is not None and role == "core" and table in _REF_AUTHORITY_TABLES:
                column_names = [
                    row[1]
                    for row in connection.execute(f'PRAGMA table_xinfo("{table}")')
                ]
                used = [
                    column
                    for column in column_names
                    if re.search(
                        r"(?<![A-Za-z0-9_])" + re.escape(column) + r"(?![A-Za-z0-9_])",
                        expression,
                    )
                ]
                _charge_validation_lengths(connection, table, used, work)
            if connection.execute(
                f'SELECT 1 FROM "{table}" WHERE NOT ({expression}) LIMIT 1'
            ).fetchone():
                raise BackupValidationError(
                    f"Stored {role} CHECK constraint failed: {table}"
                )


def validate_stored_text_encoding(
    connection: sqlite3.Connection, role: str, *, work=None
) -> None:
    """Decode actual TEXT bytes before UDF/SQLite automatic decoding can hide it.

    BLOBs (including binary Notes and native Git bytes) are deliberately excluded.
    Chunking bounds Python materialization even for a huge metadata TEXT value.
    The temporary row offsets are read coordinates, never persisted identity.
    """
    chunk_bytes = 65536
    for kind, table, _, _ in expected_schema(role):
        if kind != "table":
            continue
        for column in connection.execute(f'PRAGMA table_xinfo("{table}")'):
            name, declared_type, hidden = column[1], column[2], column[6]
            if declared_type.upper() != "TEXT" or hidden:
                continue
            quoted = '"' + name.replace('"', '""') + '"'
            base = f"FROM \"{table}\" NOT INDEXED WHERE typeof({quoted})='text'"
            if work is not None and role == "core" and table in _REF_AUTHORITY_TABLES:
                lengths = connection.execute(f"SELECT octet_length({quoted}) {base}")
                ordinal = 0
                while True:
                    work.require("metadata_units", 1)
                    try:
                        length = lengths.fetchone()
                    except BaseException:
                        work.abandon("metadata_units")
                        raise
                    work.charge("metadata_units", 0 if length is None else 1)
                    if length is None:
                        break
                    size = length[0]
                    decoder = codecs.getincrementaldecoder("utf-8")()
                    offset = 0
                    try:
                        while offset < size:
                            amount = min(chunk_bytes, size - offset)
                            work.require("input_bytes", amount)
                            try:
                                raw = connection.execute(
                                    f"SELECT substr(CAST({quoted} AS BLOB),?,?) {base} LIMIT 1 OFFSET ?",
                                    (offset + 1, amount, ordinal),
                                ).fetchone()[0]
                            except BaseException:
                                work.abandon("input_bytes")
                                raise
                            work.charge("input_bytes", len(raw))
                            if not raw:
                                raise RuntimeError(
                                    "Stored text changed during validation"
                                )
                            offset += len(raw)
                            decoder.decode(raw, final=offset >= size)
                        if size == 0:
                            decoder.decode(b"", final=True)
                    except UnicodeDecodeError:
                        raise BackupValidationError(
                            f"Stored authoritative {role} TEXT {table}.{name} is invalid UTF-8"
                        ) from None
                    ordinal += 1
                continue
            rows = connection.execute(
                f"SELECT length(CAST({quoted} AS BLOB)), "
                f"substr(CAST({quoted} AS BLOB),1,{chunk_bytes}) {base}"
            )
            for ordinal, (size, first) in enumerate(rows):
                decoder = codecs.getincrementaldecoder("utf-8")()
                try:
                    if size == 0:
                        first = b""
                    decoder.decode(first, final=size <= chunk_bytes)
                    offset = len(first)
                    while offset < size:
                        raw = connection.execute(
                            f"SELECT substr(CAST({quoted} AS BLOB),?,?) {base} LIMIT 1 OFFSET ?",
                            (offset + 1, min(chunk_bytes, size - offset), ordinal),
                        ).fetchone()[0]
                        if not raw:
                            raise RuntimeError("Stored text changed during validation")
                        offset += len(raw)
                        decoder.decode(raw, final=offset >= size)
                except UnicodeDecodeError:
                    raise BackupValidationError(
                        f"Stored authoritative {role} TEXT {table}.{name} is invalid UTF-8"
                    ) from None


def verify_existing_context_text(connection, digest, expected_bytes, max_bytes, work):
    """Verify one exact existing text key inside the caller's writer transaction.

    Reserve finite allocation and verification work before fetching stored bytes.
    A digest mismatch is positive evidence about retained authority, independently
    of the already checked incoming text. A limit or read error proves no damage.
    """
    work.require("metadata_units", 1)
    row = connection.execute(
        "SELECT length(CAST(text_value AS BLOB)) FROM text_bodies WHERE sha256=?",
        (digest,),
    ).fetchone()
    work.charge("metadata_units", 1)
    if row is None:
        if bounded_domain_exists(
            connection,
            "SELECT 1 FROM field_candidates WHERE field_name='text_body_sha256' AND value_json=? LIMIT 1",
            (json.dumps(digest),),
            work,
            "required_context_text",
        ):
            raise BackupValidationError(
                "Existing required retained Context text is missing"
            )
        return False
    size = row[0]
    if size > max_bytes:
        raise CoreFailure(
            "BUDGET", "context_text", "existing text exceeds finite payload limit"
        )
    work.require("input_bytes", size)
    # Hashing and exact byte comparison each process the stored representation.
    work.require("verification_bytes", size * 2)
    raw = connection.execute(
        "SELECT CAST(text_value AS BLOB) FROM text_bodies WHERE sha256=?",
        (digest,),
    ).fetchone()[0]
    work.charge("input_bytes", len(raw))
    actual_digest = hashlib.sha256(raw).hexdigest()
    exact = raw == expected_bytes
    work.charge("verification_bytes", len(raw) * 2)
    if actual_digest != digest:
        raise BackupValidationError("Existing retained Context text SHA-256 mismatch")
    if not exact:
        raise ValueError("Exact UTF8 text digest collision")
    return True


def bounded_domain_exists(connection, sql, parameters, work, scope):
    """Bound a trusted read's VM work before inferring a dependency absent.

    One metadata unit reserves at most 100 SQLite VM instructions. A crash
    retains the full reservation; a live measurement settles completed quanta.
    All callers use fixed trusted SQL, never text from recovery candidates.
    """
    cap = min(4096, work._max["metadata_units"] - work.usage["metadata_units"])
    if cap <= 0:
        raise CoreFailure(
            "BUDGET", scope, "no metadata work remains for dependency check"
        )
    work.require("metadata_units", cap)
    ticks = 0

    def progress():
        nonlocal ticks
        ticks += 1
        return int(ticks >= cap)

    connection.set_progress_handler(progress, 100)
    try:
        try:
            found = connection.execute(sql, parameters).fetchone() is not None
        except sqlite3.OperationalError as error:
            if getattr(error, "sqlite_errorcode", 0) & 255 == sqlite3.SQLITE_INTERRUPT:
                raise CoreFailure(
                    "BUDGET", scope, "finite dependency-query VM work exhausted"
                ) from error
            raise
    finally:
        connection.set_progress_handler(None, 0)
        work.charge("metadata_units", min(cap, ticks + 1))
    return found
