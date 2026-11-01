"""Context-specific Recovery validation, explicitly composed with Core helpers."""

import hashlib
import json
import sqlite3

from repo_catalog.adapters.sqlite.core_recovery_validation import (
    StoredAuthorityInvariantError,
    bounded_domain_exists,
)
from repo_catalog.adapters.sqlite.core_recovery_validation import (
    validate_stored_admission_guards as _validate_stored_admission_guards,
)
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


class StoredContextInvariantError(StoredAuthorityInvariantError):
    """A trusted pure Context decoder proved retained domain evidence invalid.

    This explicit boundary retains the decoder cause for diagnostics without
    confusing a deterministic stored-data violation with an unexpected adapter
    ValueError, unavailable I/O or exhausted resource budget.
    """


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
    """Compose optional Context guards and typed relation validation explicitly."""
    if role == "context":
        _validate_stored_admission_guards(
            connection,
            role,
            work=work,
            guard_names={
                "coverage_proof_owner",
                "source_coverage_owner",
                "rrr_event_report_time",
            },
        )
        validate_stored_context_relations(connection)
    else:
        _validate_stored_admission_guards(connection, role, work=work)


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
