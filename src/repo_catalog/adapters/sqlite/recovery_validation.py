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
    ProviderRepositoryScope,
    ResourceKey,
    ResourceRepositoryRelation,
    TransferEventReport,
    canonical,
)
from repo_catalog.domain.p1_core import CoreFailure
from repo_catalog.domain.recovery import BackupValidationError

# INSERT-time replay/current-terminal predicates are deliberately excluded:
# old Coverage evidence remains valid history after a later terminal arrives,
# and rrr_no_rebind / rmd_no_rebind are INSERT-time replay/stale guards.
_PERSISTENT_GUARDS = {
    "core": {
        "relation_targets",
        "notes_group_targets",
        "notes_inventory_guard",
        "metadata_same_representation",
        "intrinsic_claim_guard",
        "intrinsic_group_guard",
        "notes_same_representation",
        "notes_claim_format",
        "notes_group_format",
        "core_coverage_members",
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
            if isinstance(parsed_scope, dict) and "repository_roles" in parsed_scope:
                ProviderRepositoryScope.from_json(row[6])
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
            report = TransferEventReport.from_stored_scope(
                rep_key, rels, scope_json, members_json, obs_us
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
        raise BackupValidationError(
            f"Stored context relation invariant failed: {error}"
        ) from error


validate_context_relation_invariants = validate_stored_context_relations


def validate_stored_admission_guards(connection: sqlite3.Connection, role: str) -> None:
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
    connection: sqlite3.Connection, role: str, *, retained_bytes: bool
) -> None:
    # SQLite readonly integrity_check can report 'ok' without surfacing failed
    # application-UDF CHECKs. Re-evaluate every trusted expression explicitly.
    # SQLite CHECK accepts NULL: WHERE NOT(expression) preserves that meaning.
    body_tables = {"retained_metadata", "retained_notes", "text_bodies"}
    for kind, table, _, sql in expected_schema(role):
        if kind != "table" or (table in body_tables) != retained_bytes:
            continue
        for expression in _packaged_checks(sql):
            if connection.execute(
                f'SELECT 1 FROM "{table}" WHERE NOT ({expression}) LIMIT 1'
            ).fetchone():
                raise BackupValidationError(
                    f"Stored {role} CHECK constraint failed: {table}"
                )


def validate_stored_text_encoding(connection: sqlite3.Connection, role: str) -> None:
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
