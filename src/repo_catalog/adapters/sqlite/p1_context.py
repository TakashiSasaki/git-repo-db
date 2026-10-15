"""Executable P1 reference adapter. No runtime initializer imports this module.

All writes use the caller's transaction, including independent Context rollback.
P3 owns collection/provenance parser integration and optimized current updates.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable

from repo_catalog.domain.coverage import derive_coverage_state
from repo_catalog.domain.p1_context import (
    CoverageClaim,
    CoverageProjection,
    CoverageScope,
    FieldCandidate,
    FieldClock,
    ResourceKey,
)


def register_functions(db: sqlite3.Connection) -> None:
    db.create_function(
        "p1_text_sha256",
        1,
        lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest(),
        deterministic=True,
    )


class ContextStore:
    def __init__(self, connection: sqlite3.Connection):
        self.db = connection

    def resource(self, key: ResourceKey, repository_uuidv4: str | None) -> None:
        """Admit nominal identity, independently of current repository evidence.

        The optional repository is a validated caller registration precondition;
        it does not assert membership. Use admit_repository with original clocks.
        """
        if (
            repository_uuidv4 is not None
            and not self.db.execute(
                "SELECT 1 FROM repository_context WHERE repository_uuidv4=?",
                (repository_uuidv4,),
            ).fetchone()
        ):
            raise ValueError("Repository registration absent")
        prior = self.db.execute(
            "SELECT 1 FROM resources WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
            key.coordinates(),
        ).fetchone()
        if prior:
            return
        parent = (None, None, None, None)
        if key.resource_kind in {"review", "comment", "thread", "document"}:
            parent = tuple(json.loads(key.provider_resource_id))
            if len(parent) != 4 or any(
                not isinstance(value, str) or not value for value in parent
            ):
                raise ValueError("Full genuine parent/document coordinates required")
        self.db.execute(
            "INSERT INTO resources VALUES(?,?,?,?,?,?,?)", (*key.coordinates(), *parent)
        )

    def admit_repository(
        self,
        resource: ResourceKey,
        repository_uuidv4: str,
        clock: FieldClock,
        provenance_json: str,
        observed_at_us: int,
    ) -> str:
        from repo_catalog.domain.p1_context import canonical

        return self.admit_field(
            FieldCandidate(
                resource,
                "repository_uuidv4",
                canonical(repository_uuidv4),
                clock,
                provenance_json,
                observed_at_us,
            )
        )

    def repository_candidates(
        self, resource: ResourceKey
    ) -> tuple[FieldCandidate, ...]:
        return self.candidates(resource, "repository_uuidv4")

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
            rows = self.db.execute(
                """SELECT observed_at_us,coverage_state,details_json FROM coverage_claims WHERE owner_kind=? AND owner_coordinates_json=? AND observed_at_us=(SELECT MAX(observed_at_us) FROM coverage_claims WHERE owner_kind=? AND owner_coordinates_json=?) ORDER BY coverage_state""",
                (scope.owner_kind, scope.encoded, scope.owner_kind, scope.encoded),
            ).fetchall()
            claims = tuple(CoverageClaim(scope, row[0], row[1], row[2]) for row in rows)
            state = derive_coverage_state(claim.state for claim in claims)
            empty = False
            if state == "complete":
                proofs = self.db.execute(
                    "SELECT members_json FROM coverage_proofs WHERE owner_kind=? AND owner_coordinates_json=? AND observed_at_us=? AND coverage_state=?",
                    (scope.owner_kind, scope.encoded, rows[0][0], "complete"),
                ).fetchall()
                source_proofs = self.db.execute(
                    "SELECT members_json FROM source_coverage_proofs WHERE owner_kind=? AND owner_coordinates_json=? AND observed_at_us=? AND coverage_state=?",
                    (scope.owner_kind, scope.encoded, rows[0][0], "complete"),
                ).fetchall()
                proofs = [*proofs, *source_proofs]
                empty = bool(proofs) and all(row[0] == "[]" for row in proofs)
            return CoverageProjection(
                state, rows[0][0] if rows else None, claims, empty
            )
        finally:
            self.db.execute("RELEASE p1_coverage_read")

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
