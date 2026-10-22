"""Executable P1 reference adapter. No runtime initializer imports this module.

All writes use the caller's transaction, including independent Context rollback.
P3 owns collection/provenance parser integration and optimized current updates.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterable
from functools import wraps

from repo_catalog.domain.p1_context import (
    RELATION_KINDS,
    TRANSFER_RELATION_KINDS,
    CoverageClaim,
    CoverageProjection,
    CoverageScope,
    FieldCandidate,
    FieldClock,
    MappingClaimKey,
    MappingDisposition,
    MappingOperationEvidence,
    QualifiedMappingEvaluation,
    QualifiedProviderRepositoryRole,
    RelationAdmissionResult,
    RelationKind,
    ResolvedRepositoryRelation,
    ResourceKey,
    ResourceRepositoryRelation,
    SupportStatus,
    TransferEventReport,
    evaluate_repository_mapping,
    p1_mapping_clock,
    p1_mapping_provenance,
    p1_mapping_target,
    qualify_provider_role_scopes,
    validate_provider_repository_scope,
)
from repo_catalog.domain.p1_coverage import derive_coverage_state
from repo_catalog.domain.resource_identification import (
    ResourceIdentification,
    identification_sql,
    identity_sql,
    require_identification,
)
from repo_catalog.domain.resource_stage import (
    UnsupportedResourceStage,
    refuse_transfer,
    validate_stage_storage,
)


def register_functions(db: sqlite3.Connection) -> None:
    from repo_catalog.domain.context_registration import registration_json
    from repo_catalog.domain.parent_report import parent_report_sql

    db.create_function("p1_parent_report_v1", 7, parent_report_sql, deterministic=True)

    db.create_function("p1_resource_identity_v1", 1, identity_sql, deterministic=True)
    db.create_function(
        "p1_resource_identification_v1", 6, identification_sql, deterministic=True
    )

    def registration(kind, encoded):
        try:
            registration_json(kind, encoded)
            return 1
        except (ValueError, TypeError, RecursionError, OverflowError):
            return 0

    db.create_function("p1_registration_json", 2, registration, deterministic=True)
    db.create_function(
        "p1_text_sha256",
        1,
        lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest(),
        deterministic=True,
    )
    db.create_function("p1_mapping_target", 1, p1_mapping_target, deterministic=True)
    db.create_function("p1_mapping_clock", 1, p1_mapping_clock, deterministic=True)
    db.create_function(
        "p1_mapping_provenance", 1, p1_mapping_provenance, deterministic=True
    )


def _stage_checked(cls):
    for name, method in tuple(vars(cls).items()):
        if name.startswith("_") or not callable(method):
            continue

        def checked(operation):
            @wraps(operation)
            def call(self, *args, **kwargs):
                validate_stage_storage(self.db)
                return operation(self, *args, **kwargs)

            return call

        setattr(cls, name, checked(method))
    return cls


@_stage_checked
class ContextStore:
    def __init__(self, connection: sqlite3.Connection):
        self.db = connection

    def resource(
        self,
        key: ResourceKey,
        repository_uuidv4: str | None = None,
        *,
        identification: ResourceIdentification | None = None,
    ) -> None:
        """Admit nominal identity, independently of current repository evidence.

        The optional repository is a validated caller registration precondition;
        it does not assert membership. Use admit_repository_relation with original clocks.
        """
        if not isinstance(key, ResourceKey):
            raise ValueError("ResourceKey required")
        declaration = require_identification(key, identification)
        if (
            repository_uuidv4 is not None
            and not self.db.execute(
                "SELECT 1 FROM repository_context WHERE repository_uuidv4=?",
                (repository_uuidv4,),
            ).fetchone()
        ):
            raise ValueError("Repository registration absent")
        self.db.execute(
            """INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,
            identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT DO NOTHING""",
            (*key.coordinates(), *declaration.columns),
        )

    def identification(self, key: ResourceKey) -> ResourceIdentification:
        row = self.db.execute(
            "SELECT identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id "
            "FROM resources WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
            key.coordinates(),
        ).fetchone()
        if row is None:
            raise ValueError("Resource registration absent")
        return ResourceIdentification.from_storage(key, row)

    def admit_repository_relation(
        self,
        relation: ResourceRepositoryRelation,
        *,
        require_support: bool = False,
    ) -> str:
        """Admit a typed Resource--Repository relation row atomically.

        Exact 7-column key replay compares original observed_at_us before any
        stale handling. Only owning_repository, base_repository and
        head_repository participate in AFTER INSERT pruning of strictly older
        comparable clocks within the same Resource, role and clock domain.
        """
        if not isinstance(relation, ResourceRepositoryRelation):
            raise ValueError("ResourceRepositoryRelation required")
        refuse_transfer(relation.relation_kind)
        if relation.relation_kind in TRANSFER_RELATION_KINDS:
            raise ValueError("Transfer endpoints require admit_transfer_event()")
        return self._admit_repository_relation(
            relation, require_support=require_support
        )

    def _admit_repository_relation(
        self, relation: ResourceRepositoryRelation, *, require_support: bool = False
    ) -> str:
        """Insert a validated row; Transfer callers must validate the whole report first."""
        refuse_transfer(relation.relation_kind)
        self.db.execute("SAVEPOINT p1_repository_relation")
        try:
            coords = relation.claim_key.coordinates()
            prior = self.db.execute(
                """SELECT observed_at_us FROM resource_repository_relations
                WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?
                  AND relation_kind=? AND clock_json=? AND target_json=? AND provenance_json=?""",
                coords,
            ).fetchone()
            if prior is not None:
                if prior[0] != relation.observed_at_us:
                    raise ValueError("Original observation time changed during replay")
                self.db.execute("RELEASE p1_repository_relation")
                return "duplicate"
            support = relation.embedded_support
            if support is not None or require_support:
                if (
                    require_support
                    and relation.relation_kind != "represents_repository"
                    and relation.target_repository_uuidv4 is not None
                    and support is None
                ):
                    raise ValueError(
                        "Resolved repository relation requires explicit MappingSupport"
                    )
                if support is not None:
                    for claim in support.supporting_claims:
                        exists = self.db.execute(
                            """SELECT 1 FROM resource_repository_relations
                            WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?
                              AND relation_kind=? AND clock_json=? AND target_json=? AND provenance_json=?""",
                            claim.coordinates(),
                        ).fetchone()
                        if exists is None:
                            raise ValueError(
                                "Supporting MappingClaimKey is absent from resource_repository_relations"
                            )
            try:
                self.db.execute(
                    """INSERT INTO resource_repository_relations(
                        service_instance_uuidv4,resource_kind,provider_resource_id,
                        relation_kind,clock_json,target_json,provenance_json,observed_at_us
                    ) VALUES(?,?,?,?,?,?,?,?)""",
                    (*coords, relation.observed_at_us),
                )
            except sqlite3.IntegrityError as error:
                if "stale current repository relation candidate" in str(error):
                    self.db.execute("ROLLBACK TO p1_repository_relation")
                    self.db.execute("RELEASE p1_repository_relation")
                    return "stale"
                raise
            self.db.execute("RELEASE p1_repository_relation")
            return "insert"
        except BaseException:
            self.db.execute("ROLLBACK TO p1_repository_relation")
            self.db.execute("RELEASE p1_repository_relation")
            raise

    def admit_repository_relation_result(
        self,
        relation: ResourceRepositoryRelation,
        *,
        require_support: bool = False,
    ) -> RelationAdmissionResult:
        """Typed admission outcome wrapper distinguishing missing support dependency."""
        if not isinstance(relation, ResourceRepositoryRelation):
            raise ValueError("ResourceRepositoryRelation required")
        refuse_transfer(relation.relation_kind)
        if relation.relation_kind in TRANSFER_RELATION_KINDS:
            raise ValueError("Transfer endpoints require admit_transfer_event()")
        support = relation.embedded_support
        if support is not None:
            for claim in support.supporting_claims:
                exists = self.db.execute(
                    """SELECT 1 FROM resource_repository_relations
                    WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?
                      AND relation_kind=? AND clock_json=? AND target_json=? AND provenance_json=?""",
                    claim.coordinates(),
                ).fetchone()
                if exists is None:
                    return RelationAdmissionResult(
                        "missing_dependency",
                        "Supporting MappingClaimKey is absent",
                    )
        if (
            relation.target_repository_uuidv4 is not None
            and not self.db.execute(
                "SELECT 1 FROM repository_context WHERE repository_uuidv4=?",
                (relation.target_repository_uuidv4,),
            ).fetchone()
        ):
            return RelationAdmissionResult(
                "missing_dependency",
                "Target repository_uuidv4 is not registered in repository_context",
            )
        outcome = self.admit_repository_relation(
            relation, require_support=require_support
        )
        return RelationAdmissionResult(outcome)  # type: ignore[arg-type]

    def admit_mapping_disposition(self, disposition: MappingDisposition) -> str:
        """Admit an immutable MappingDisposition targeting a complete MappingClaimKey."""
        if not isinstance(disposition, MappingDisposition):
            raise ValueError("MappingDisposition required")
        self.db.execute("SAVEPOINT p1_mapping_disposition")
        try:
            key_coords = disposition.key_coordinates()
            prior = self.db.execute(
                """SELECT observed_at_us,replacement_clock_json,replacement_target_json,replacement_provenance_json
                FROM repository_mapping_dispositions
                WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?
                  AND relation_kind=? AND claim_clock_json=? AND claim_target_json=? AND claim_provenance_json=?
                  AND disposition_kind=? AND disposition_clock_json=? AND disposition_provenance_json=?""",
                key_coords,
            ).fetchone()
            expected_payload = (
                disposition.observed_at_us,
                disposition.replacement_clock_json,
                disposition.replacement_target_json,
                disposition.replacement_provenance_json,
            )
            if prior is not None:
                if tuple(prior) != expected_payload:
                    raise ValueError(
                        "Mapping disposition non-key payload changed during replay"
                    )
                self.db.execute("RELEASE p1_mapping_disposition")
                return "duplicate"
            self.db.execute(
                """INSERT INTO repository_mapping_dispositions(
                    service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,
                    claim_clock_json,claim_target_json,claim_provenance_json,
                    disposition_kind,disposition_clock_json,disposition_provenance_json,
                    observed_at_us,replacement_clock_json,replacement_target_json,replacement_provenance_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (*key_coords, *expected_payload),
            )
            self.db.execute("RELEASE p1_mapping_disposition")
            return "insert"
        except BaseException:
            self.db.execute("ROLLBACK TO p1_mapping_disposition")
            self.db.execute("RELEASE p1_mapping_disposition")
            raise

    def admit_transfer_event(self, report: TransferEventReport) -> str:
        """Admit one complete TransferEventReport unit atomically."""
        raise UnsupportedResourceStage("admit_transfer_event")

    def _raw_relations_from_rows(
        self, rows: Iterable[tuple]
    ) -> tuple[ResourceRepositoryRelation, ...]:
        return tuple(
            ResourceRepositoryRelation(
                resource=ResourceKey(row[0], row[1], row[2]),
                relation_kind=row[3],
                clock=FieldClock.from_json(row[4]),
                target_json=row[5],
                provenance_json=row[6],
                observed_at_us=row[7],
            )
            for row in rows
        )

    def mapping_dispositions(
        self, subject: MappingClaimKey | ResourceKey | None = None
    ) -> tuple[MappingDisposition, ...]:
        if isinstance(subject, MappingClaimKey):
            rows = self.db.execute(
                """SELECT service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,
                          claim_clock_json,claim_target_json,claim_provenance_json,
                          disposition_kind,disposition_clock_json,disposition_provenance_json,
                          observed_at_us,replacement_clock_json,replacement_target_json,replacement_provenance_json
                FROM repository_mapping_dispositions
                WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?
                  AND relation_kind=? AND claim_clock_json=? AND claim_target_json=? AND claim_provenance_json=?
                ORDER BY disposition_kind,disposition_clock_json,disposition_provenance_json""",
                subject.coordinates(),
            ).fetchall()
        elif isinstance(subject, ResourceKey):
            rows = self.db.execute(
                """SELECT service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,
                          claim_clock_json,claim_target_json,claim_provenance_json,
                          disposition_kind,disposition_clock_json,disposition_provenance_json,
                          observed_at_us,replacement_clock_json,replacement_target_json,replacement_provenance_json
                FROM repository_mapping_dispositions
                WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?
                ORDER BY claim_clock_json,claim_target_json,claim_provenance_json,
                         disposition_kind,disposition_clock_json,disposition_provenance_json""",
                subject.coordinates(),
            ).fetchall()
        elif subject is None:
            rows = self.db.execute(
                """SELECT service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,
                          claim_clock_json,claim_target_json,claim_provenance_json,
                          disposition_kind,disposition_clock_json,disposition_provenance_json,
                          observed_at_us,replacement_clock_json,replacement_target_json,replacement_provenance_json
                FROM repository_mapping_dispositions
                ORDER BY service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,
                         claim_clock_json,claim_target_json,claim_provenance_json,
                         disposition_kind,disposition_clock_json,disposition_provenance_json"""
            ).fetchall()
        else:
            raise ValueError("subject must be MappingClaimKey, ResourceKey, or None")

        results: list[MappingDisposition] = []
        for row in rows:
            res = ResourceKey(row[0], row[1], row[2])
            claim_key = MappingClaimKey(
                resource=res,
                relation_kind=row[3],
                clock=FieldClock.from_json(row[4]),
                target_json=row[5],
                provenance_json=row[6],
            )
            replacement_key = None
            if row[11] is not None or row[12] is not None or row[13] is not None:
                if row[11] is None or row[12] is None or row[13] is None:
                    raise ValueError("Partial null replacement in stored disposition")
                replacement_key = MappingClaimKey(
                    resource=res,
                    relation_kind=row[3],
                    clock=FieldClock.from_json(row[11]),
                    target_json=row[12],
                    provenance_json=row[13],
                )
            results.append(
                MappingDisposition(
                    claim_key=claim_key,
                    disposition_kind=row[7],
                    disposition_clock=FieldClock.from_json(row[8]),
                    disposition_provenance_json=row[9],
                    observed_at_us=row[10],
                    replacement_claim_key=replacement_key,
                )
            )
        return tuple(results)

    def evaluate_provider_repository(
        self,
        provider_repository: ResourceKey,
        *,
        evidence: MappingOperationEvidence | None = None,
    ) -> QualifiedMappingEvaluation:
        if (
            not isinstance(provider_repository, ResourceKey)
            or provider_repository.resource_kind != "repository"
        ):
            raise ValueError("provider_repository must be a repository ResourceKey")
        rows = self.db.execute(
            """SELECT service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,
                      clock_json,target_json,provenance_json,observed_at_us
            FROM resource_repository_relations
            WHERE service_instance_uuidv4=? AND resource_kind='repository'
              AND provider_resource_id=? AND relation_kind='represents_repository'
            ORDER BY clock_json,target_json,provenance_json""",
            (
                provider_repository.service_instance_uuidv4,
                provider_repository.provider_resource_id,
            ),
        ).fetchall()
        claims = self._raw_relations_from_rows(rows)
        dispositions = self.mapping_dispositions(provider_repository)
        return evaluate_repository_mapping(
            provider_repository, claims, dispositions, evidence=evidence
        )

    def _qualify_relation(
        self,
        relation: ResourceRepositoryRelation,
        *,
        evidence: MappingOperationEvidence | None = None,
    ) -> ResolvedRepositoryRelation:
        if relation.relation_kind == "represents_repository":
            ck = relation.claim_key
            assert isinstance(ck, MappingClaimKey)
            evaluation = self.evaluate_provider_repository(
                relation.resource, evidence=evidence
            )
            dispositions = self.mapping_dispositions(ck)
            if evaluation.state in (
                "unresolved_correction",
                "evidence_contradictory",
            ):
                status: SupportStatus = "conflicting_support"
            elif ck in evaluation.withdrawn_claims or ck in evaluation.corrected_claims:
                status = "supporting_binding_disposed"
            elif evaluation.state == "conflict":
                status = "conflicting_support"
            elif any(
                d.claim_key == ck
                for d in (
                    *evaluation.unconfirmed_dispositions,
                    *evaluation.disputed_dispositions,
                )
            ):
                status = "unconfirmed_disposition"
            else:
                status = "self_binding"
            is_act = ck in evaluation.active_claims
            return ResolvedRepositoryRelation(
                relation=relation,
                support_status=status,
                supporting_bindings=(ck,) if is_act else (),
                disposed_supporting_bindings=() if is_act else (ck,),
                dispositions=dispositions,
            )

        if relation.is_explicit_null_target:
            return ResolvedRepositoryRelation(
                relation=relation,
                support_status="explicit_null",
            )

        support = relation.embedded_support
        if support is not None:
            prov_repo = support.provider_repository
            existing_rows = self.db.execute(
                """SELECT service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,
                          clock_json,target_json,provenance_json,observed_at_us
                FROM resource_repository_relations
                WHERE service_instance_uuidv4=? AND resource_kind='repository'
                  AND provider_resource_id=? AND relation_kind='represents_repository'""",
                (
                    prov_repo.service_instance_uuidv4,
                    prov_repo.provider_resource_id,
                ),
            ).fetchall()
            existing_keys = {
                r.claim_key for r in self._raw_relations_from_rows(existing_rows)
            }
            if any(sc not in existing_keys for sc in support.supporting_claims):
                present = tuple(
                    sc for sc in support.supporting_claims if sc in existing_keys
                )
                return ResolvedRepositoryRelation(
                    relation=relation,
                    support_status="missing_supporting_binding",
                    supporting_bindings=present,
                )
            evaluation = self.evaluate_provider_repository(prov_repo, evidence=evidence)
            all_disps = self.mapping_dispositions(prov_repo)
            rel_disps = tuple(
                d for d in all_disps if d.claim_key in support.supporting_claims
            )
            active_sc = tuple(
                sc for sc in support.supporting_claims if sc in evaluation.active_claims
            )
            disposed_sc = tuple(
                sc
                for sc in support.supporting_claims
                if sc not in evaluation.active_claims
            )
            if evaluation.state in (
                "conflict",
                "unresolved_correction",
                "evidence_contradictory",
            ):
                status = "conflicting_support"
            elif not active_sc:
                status = "supporting_binding_disposed"
            elif any(
                d.claim_key in support.supporting_claims
                for d in (
                    *evaluation.unconfirmed_dispositions,
                    *evaluation.disputed_dispositions,
                )
            ):
                status = "unconfirmed_disposition"
            else:
                status = "active"
            return ResolvedRepositoryRelation(
                relation=relation,
                support_status=status,
                supporting_bindings=active_sc,
                disposed_supporting_bindings=disposed_sc,
                dispositions=rel_disps,
            )

        # No embedded MappingSupport: ADR 0030 preserves exact original MappingClaimKey
        # support. Core-target relations without explicit MappingSupport do not borrow
        # unlinked represents_repository claims across other Provider repositories in the service.
        return ResolvedRepositoryRelation(
            relation=relation,
            support_status="missing_supporting_binding",
        )

    def repository_relations(
        self,
        resource: ResourceKey,
        relation_kind: RelationKind | None = None,
        *,
        evidence: MappingOperationEvidence | None = None,
    ) -> tuple[ResolvedRepositoryRelation, ...]:
        refuse_transfer(relation_kind)
        if not isinstance(resource, ResourceKey):
            raise ValueError("ResourceKey required")
        if relation_kind is not None and relation_kind not in RELATION_KINDS:
            raise ValueError(f"Unknown relation_kind: {relation_kind!r}")
        rows = self.db.execute(
            """SELECT service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,
                      clock_json,target_json,provenance_json,observed_at_us
            FROM resource_repository_relations
            WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?
              AND (? IS NULL OR relation_kind=?)
            ORDER BY relation_kind,clock_json,target_json,provenance_json""",
            (*resource.coordinates(), relation_kind, relation_kind),
        ).fetchall()
        raw = self._raw_relations_from_rows(rows)
        return tuple(self._qualify_relation(r, evidence=evidence) for r in raw)

    def relations_for_repository(
        self,
        repository_uuidv4: str,
        relation_kind: RelationKind | None = None,
        *,
        evidence: MappingOperationEvidence | None = None,
    ) -> tuple[ResolvedRepositoryRelation, ...]:
        refuse_transfer(relation_kind)
        if relation_kind is not None and relation_kind not in RELATION_KINDS:
            raise ValueError(f"Unknown relation_kind: {relation_kind!r}")
        rows = self.db.execute(
            """SELECT service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,
                      clock_json,target_json,provenance_json,observed_at_us
            FROM resource_repository_relations
            WHERE repository_uuidv4=? AND (? IS NULL OR relation_kind=?)
            ORDER BY relation_kind,service_instance_uuidv4,resource_kind,provider_resource_id,
                     clock_json,target_json,provenance_json""",
            (repository_uuidv4, relation_kind, relation_kind),
        ).fetchall()
        raw = self._raw_relations_from_rows(rows)
        return tuple(self._qualify_relation(r, evidence=evidence) for r in raw)

    def relations_for_provider_repository(
        self,
        service_instance_uuidv4: str,
        provider_repository_id: str,
        relation_kind: RelationKind | None = None,
        *,
        evidence: MappingOperationEvidence | None = None,
    ) -> tuple[ResolvedRepositoryRelation, ...]:
        refuse_transfer(relation_kind)
        if relation_kind is not None and relation_kind not in RELATION_KINDS:
            raise ValueError(f"Unknown relation_kind: {relation_kind!r}")
        prov_key = ResourceKey(
            service_instance_uuidv4, "repository", provider_repository_id
        )
        rows = self.db.execute(
            """SELECT service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,
                      clock_json,target_json,provenance_json,observed_at_us
            FROM resource_repository_relations
            WHERE service_instance_uuidv4=? AND (? IS NULL OR relation_kind=?)
            ORDER BY relation_kind,resource_kind,provider_resource_id,clock_json,target_json,provenance_json""",
            (service_instance_uuidv4, relation_kind, relation_kind),
        ).fetchall()
        matched: list[ResolvedRepositoryRelation] = []
        for rel in self._raw_relations_from_rows(rows):
            if rel.resource == prov_key:
                matched.append(self._qualify_relation(rel, evidence=evidence))
            elif (
                rel.embedded_support is not None
                and rel.embedded_support.provider_repository == prov_key
            ):
                matched.append(self._qualify_relation(rel, evidence=evidence))
        return tuple(matched)

    def provider_repository_roles(
        self, resource: ResourceKey, *, evidence: MappingOperationEvidence | None = None
    ) -> tuple[QualifiedProviderRepositoryRole, ...]:
        records = []
        for members, provenance, scope_json, observed in self.db.execute(
            "SELECT members_json,provenance_json,scope_json,observed_at_us FROM resource_relations WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND relation_kind='provider_repository_roles' ORDER BY scope_json,provenance_json",
            resource.coordinates(),
        ):
            actual_members = tuple(ResourceKey(*m) for m in json.loads(members))
            scope = validate_provider_repository_scope(
                resource, actual_members, provenance, scope_json, observed
            )
            for role in scope.roles.values():
                provider = (
                    None
                    if role.provider_repository_id is None
                    else ResourceKey(
                        resource.service_instance_uuidv4,
                        "repository",
                        role.provider_repository_id,
                    )
                )
                if provider is not None:
                    if not self.db.execute(
                        "SELECT 1 FROM resources WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
                        provider.coordinates(),
                    ).fetchone():
                        raise ValueError("Provider role member resource missing")
                evaluation = (
                    None
                    if provider is None
                    else self.evaluate_provider_repository(provider, evidence=evidence)
                )
                records.append(
                    QualifiedProviderRepositoryRole(
                        resource, role, provenance, evaluation
                    )
                )
        kept = qualify_provider_role_scopes([r.scope for r in records])
        return tuple(r for r in records if r.scope in kept)

    def transfer_event_reports(
        self,
        resource: ResourceKey | None = None,
        *,
        repository_uuidv4: str | None = None,
        selected_repositories: Iterable[str] | None = None,
    ) -> tuple[TransferEventReport, ...]:
        """Reconstruct TransferEventReport units grouped strictly by EventReportKey.

        Never cross-pairs endpoints from different EventReportKeys.
        """
        raise UnsupportedResourceStage("transfer_event_reports")

    def text(self, text_value: str) -> str:
        digest = hashlib.sha256(text_value.encode("utf-8")).hexdigest()
        prior = self.db.execute(
            "SELECT text_value FROM text_bodies WHERE sha256=?", (digest,)
        ).fetchone()
        if prior is not None and prior[0] != text_value:
            raise ValueError("Exact UTF8 text digest collision")
        if prior is None:
            self.db.execute("INSERT INTO text_bodies VALUES(?,?)", (digest, text_value))
        return digest

    def candidates(
        self, resource: ResourceKey, field_name: str
    ) -> tuple[FieldCandidate, ...]:
        if field_name == "repository_uuidv4":
            raise ValueError(
                "field_name='repository_uuidv4' is retired; use repository_relations"
            )
        rows = self.db.execute(
            "SELECT value_json,clock_json,provenance_json,observed_at_us FROM field_candidates WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND field_name=? ORDER BY clock_json,value_json,provenance_json",
            (*resource.coordinates(), field_name),
        )
        return tuple(
            FieldCandidate(
                resource,
                field_name,
                row[0],
                FieldClock(**json.loads(row[1])),
                row[2],
                row[3],
            )
            for row in rows
        )

    def admit_field(self, candidate: FieldCandidate) -> str:
        """Replace dominated comparable candidates, preserving all equal/incomparable.

        An exact original report includes its actual observation time. Conflicting
        reuse of the same immutable evidence coordinate fails before mutation.
        The savepoint makes a candidate-set update atomic even in autocommit mode.
        """
        if not isinstance(candidate, FieldCandidate):
            raise ValueError("FieldCandidate required")
        self.db.execute("SAVEPOINT p1_field")
        try:
            existing = self.candidates(candidate.resource, candidate.field_name)
            for prior in existing:
                if (prior.value_json, prior.clock, prior.provenance_json) == (
                    candidate.value_json,
                    candidate.clock,
                    candidate.provenance_json,
                ):
                    if prior.observed_at_us != candidate.observed_at_us:
                        raise ValueError(
                            "Original observation time changed during replay"
                        )
                    self.db.execute("RELEASE p1_field")
                    return "duplicate"
            comparable = [
                prior
                for prior in existing
                if prior.clock.domain == candidate.clock.domain
                and prior.clock.at_us is not None
            ]
            if candidate.clock.at_us is not None:
                if any(
                    prior.clock.at_us > candidate.clock.at_us for prior in comparable
                ):
                    self.db.execute("RELEASE p1_field")
                    return "stale"
                self.db.execute(
                    "DELETE FROM field_candidates WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND field_name=? AND clock_domain=? AND source_clock_us<?",
                    (
                        *candidate.resource.coordinates(),
                        candidate.field_name,
                        candidate.clock.domain,
                        candidate.clock.at_us,
                    ),
                )
            self.db.execute(
                "INSERT INTO field_candidates(service_instance_uuidv4,resource_kind,provider_resource_id,field_name,value_json,clock_json,provenance_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)",
                (
                    *candidate.resource.coordinates(),
                    candidate.field_name,
                    candidate.value_json,
                    candidate.clock.encode(),
                    candidate.provenance_json,
                    candidate.observed_at_us,
                ),
            )
            self.db.execute("RELEASE p1_field")
            return "insert"
        except BaseException:
            self.db.execute("ROLLBACK TO p1_field")
            self.db.execute("RELEASE p1_field")
            raise

    def scope(self, scope: CoverageScope) -> None:
        if not isinstance(scope, CoverageScope):
            raise ValueError("CoverageScope required")
        if (
            scope.relation_repository_uuidv4 is not None
            and not self.db.execute(
                "SELECT 1 FROM repository_context WHERE repository_uuidv4=?",
                (scope.relation_repository_uuidv4,),
            ).fetchone()
        ):
            raise ValueError("Repository registration absent")
        fields: dict[str, str] = {"coverage_kind": scope.coordinates[-1]}
        names = {
            "repository": ("repository_uuidv4",),
            "source": ("source_registration_uuidv4", "repository_uuidv4"),
            "source_inventory": ("source_registration_uuidv4", "source_scope_json"),
            "resource": (
                "service_instance_uuidv4",
                "resource_kind",
                "provider_resource_id",
            ),
            "field": (
                "service_instance_uuidv4",
                "resource_kind",
                "provider_resource_id",
                "field_name",
            ),
            "collection": (
                "service_instance_uuidv4",
                "resource_kind",
                "provider_resource_id",
                "collection_kind",
                "collection_provenance_json",
            ),
        }
        fields.update(zip(names[scope.owner_kind], scope.coordinates[:-1], strict=True))
        columns = ("owner_kind", "owner_coordinates_json", *fields)
        self.db.execute(
            f"INSERT INTO coverage_scopes({','.join(columns)}) VALUES({','.join('?' for _ in columns)}) ON CONFLICT(owner_kind,owner_coordinates_json) DO NOTHING",
            (scope.owner_kind, scope.encoded, *fields.values()),
        )

    def admit_coverage(self, claim: CoverageClaim) -> str:
        """Atomic stale/duplicate admission; details never alter semantic identity."""
        cursor = self.db.execute(
            """INSERT INTO coverage_claims(owner_kind,owner_coordinates_json,observed_at_us,coverage_state,details_json)
          SELECT ?,?,?,?,? WHERE NOT EXISTS(SELECT 1 FROM coverage_claims WHERE owner_kind=? AND owner_coordinates_json=? AND observed_at_us>?)
          AND NOT EXISTS(SELECT 1 FROM coverage_claims WHERE owner_kind=? AND owner_coordinates_json=? AND observed_at_us=? AND coverage_state=?) RETURNING coverage_state""",
            (
                claim.scope.owner_kind,
                claim.scope.encoded,
                claim.observed_at_us,
                claim.state,
                claim.details_json,
                claim.scope.owner_kind,
                claim.scope.encoded,
                claim.observed_at_us,
                claim.scope.owner_kind,
                claim.scope.encoded,
                claim.observed_at_us,
                claim.state,
            ),
        )
        result = cursor.fetchone()
        cursor.close()
        if result:
            return "insert"
        current = self.coverage(claim.scope)
        return "stale" if current.observed_at_us > claim.observed_at_us else "duplicate"

    def coverage(self, scope: CoverageScope) -> CoverageProjection:
        self.db.execute("SAVEPOINT p1_coverage_read")
        try:
            return self._coverage_in_snapshot(scope)
        finally:
            self.db.execute("RELEASE p1_coverage_read")

    def _coverage_in_snapshot(self, scope: CoverageScope) -> CoverageProjection:
        """Projection over a caller-pinned snapshot, including read capabilities."""
        rows = self.db.execute(
            """SELECT observed_at_us,coverage_state,details_json FROM coverage_claims WHERE owner_kind=? AND owner_coordinates_json=? AND observed_at_us=(SELECT MAX(observed_at_us) FROM coverage_claims WHERE owner_kind=? AND owner_coordinates_json=?) ORDER BY coverage_state""",
            (scope.owner_kind, scope.encoded, scope.owner_kind, scope.encoded),
        ).fetchall()
        claims = tuple(CoverageClaim(scope, row[0], row[1], row[2]) for row in rows)
        state = derive_coverage_state(claim.state for claim in claims)
        empty = False
        if state == "complete":
            proofs = self.db.execute(
                "SELECT members_json,service_instance_uuidv4,resource_kind,provider_resource_id,collection_kind,provenance_json,terminal_observed_at_us,terminal_state FROM coverage_proofs WHERE owner_kind=? AND owner_coordinates_json=? AND observed_at_us=? AND coverage_state=?",
                (scope.owner_kind, scope.encoded, rows[0][0], "complete"),
            ).fetchall()
            source_proofs = self.db.execute(
                "SELECT members_json,source_registration_uuidv4,scope_json,inventory_observed_at_us,inventory_state FROM source_coverage_proofs WHERE owner_kind=? AND owner_coordinates_json=? AND observed_at_us=? AND coverage_state=?",
                (scope.owner_kind, scope.encoded, rows[0][0], "complete"),
            ).fetchall()
            dependencies: dict[tuple, list[tuple[str, str]]] = {}
            for proof in proofs:
                current = self.db.execute(
                    """SELECT observed_at_us,terminal_state,members_json,1 FROM collection_terminals WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND collection_kind=? AND provenance_json=? AND observed_at_us=(SELECT MAX(observed_at_us) FROM collection_terminals WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND collection_kind=? AND provenance_json=?)""",
                    (*proof[1:6], *proof[1:6]),
                ).fetchall()
                dependencies.setdefault(("collection", *proof[1:6]), []).append(
                    (
                        self._proof_qualification(
                            proof[6], proof[7], proof[0], current
                        ),
                        proof[0],
                    )
                )
            for proof in source_proofs:
                current = self.db.execute(
                    """SELECT observed_at_us,coverage_state,members_json,terminal FROM source_inventory_evidence WHERE source_registration_uuidv4=? AND scope_json=? AND observed_at_us=(SELECT MAX(observed_at_us) FROM source_inventory_evidence WHERE source_registration_uuidv4=? AND scope_json=?)""",
                    (*proof[1:3], *proof[1:3]),
                ).fetchall()
                dependencies.setdefault(("source", *proof[1:3]), []).append(
                    (
                        self._proof_qualification(
                            proof[3], proof[4], proof[0], current
                        ),
                        proof[0],
                    )
                )
            qualifications = []
            members = []
            for alternatives in dependencies.values():
                statuses = {status for status, _ in alternatives}
                qualifications.append(
                    "conflict"
                    if "conflict" in statuses
                    else "valid"
                    if "valid" in statuses
                    else "unknown"
                )
                members.extend(
                    value for status, value in alternatives if status == "valid"
                )
            if "conflict" in qualifications:
                state = "conflict"
            elif not qualifications or "unknown" in qualifications:
                state = "unknown"
            empty = (
                bool(qualifications)
                and all(q == "valid" for q in qualifications)
                and all(value == "[]" for value in members)
            )
        return CoverageProjection(state, rows[0][0] if rows else None, claims, empty)

    @staticmethod
    def _proof_qualification(
        observed_at_us: int, state: str, members_json: str, current: list
    ) -> str:
        """Qualify immutable dependencies against current actual terminal evidence.

        A blocked proof does not rewrite the original claim. Equal-time unknown
        is weaker than a determinate observation, matching Coverage semantics.
        """
        if not current:
            return "unknown"
        determinate = [row for row in current if row[1] != "unknown"]
        if (
            derive_coverage_state(row[1] for row in current) == "conflict"
            or len({(row[2], row[3]) for row in determinate}) > 1
        ):
            return "conflict"
        if (
            current[0][0] != observed_at_us
            or any(
                row[1] != state or row[2] != members_json or not row[3]
                for row in determinate
            )
            or not determinate
        ):
            return "unknown"
        return "valid"

    def link_core(
        self,
        resource: ResourceKey,
        role: str,
        object_format: str,
        full_oid: str,
        provenance_json: str,
        validate: Callable[[str, str], bool],
    ) -> None:
        if not validate(object_format, full_oid):
            raise ValueError("Required portable Core identity is absent")
        self.db.execute(
            "INSERT INTO core_references VALUES(?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            (*resource.coordinates(), role, object_format, full_oid, provenance_json),
        )
