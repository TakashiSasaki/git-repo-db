"""Production durable Context using P1 identities, physical schema and ports.

The public Schema 21 initializer does not import this adapter. Standalone Context
and coordinated callbacks share the same caller-owned transaction operations.
Acquisition, HTTP, Exchange, Search and recovery activation remain later stages.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import ExitStack, closing, contextmanager
from functools import wraps
from pathlib import Path

from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.p1_coordination import (
    catalog_completion,
    catalog_gate,
    persist_catalog_stop,
)
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.domain.context_registration import registration_json
from repo_catalog.domain.p1_context import (
    RELATION_KINDS,
    CoverageClaim,
    CoverageProjection,
    CoverageScope,
    FieldCandidate,
    FieldClock,
    MappingClaimKey,
    MappingDisposition,
    MappingOperationEvidence,
    QualifiedMappingEvaluation,
    RelationAdmissionOutcome,
    RelationAdmissionResult,
    RelationKind,
    ResolvedRepositoryRelation,
    ResourceKey,
    ResourceRepositoryRelation,
    TransferEventReport,
    canonical,
)
from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.p1_core import OID, uuid4_value
from repo_catalog.domain.production_context import (
    CollectionObservation,
    ContextError,
    CoreDependency,
    CoreReference,
    ResourceObservation,
    ResourceRelation,
    SourceInventory,
    json_value,
)


class _GuardedCursor:
    """Observe deferred SQLite read faults before the application can catch them."""

    def __init__(self, cursor, on_error, on_complete):
        self._cursor, self._on_error = cursor, on_error
        self._on_complete = on_complete

    def _call(self, method, *args):
        try:
            value = method(*args)
            self._on_complete()
            return value
        except BaseException as error:
            self._on_error(error)
            raise

    def fetchone(self):
        row = self._call(self._cursor.fetchone)
        return None if row is None else tuple(row)

    def fetchall(self):
        return [tuple(row) for row in self._call(self._cursor.fetchall)]

    def __iter__(self):
        return self

    def __next__(self):
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row

    def close(self):
        close = getattr(self._cursor, "close", None)
        if close is not None:
            return self._call(close)
        # P1's restricted coordinator cursor has no close method. Exhaust its
        # public read capability so RETURNING statements cannot hold COMMIT open.
        self._call(self._cursor.fetchall)


class _GuardedConnection:
    def __init__(self, connection, on_error, on_complete):
        self._connection, self._on_error = connection, on_error
        self._on_complete = on_complete

    @property
    def in_transaction(self):
        return self._connection.in_transaction

    def execute(self, sql, parameters=()):
        try:
            cursor = self._connection.execute(sql, parameters)
        except BaseException as error:
            self._on_error(error)
            raise
        completion = (
            self._on_complete
            if sql.lstrip().upper().startswith("SELECT")
            else lambda: None
        )
        return _GuardedCursor(cursor, self._on_error, completion)


def _complete_operations(cls):
    """Bind ordinary operation completion to the persistent stop fence."""
    for name, method in tuple(vars(cls).items()):
        if name.startswith("_") or not callable(method):
            continue

        def completed(operation):
            @wraps(operation)
            def call(self, *args, **kwargs):
                result = operation(self, *args, **kwargs)
                self._read_complete()
                return result

            return call

        setattr(cls, name, completed(method))
    return cls


@_complete_operations
class Context(ContextStore):
    """An expiring capability bound to one transaction or pinned read snapshot.

    Use ``transaction`` for Context-only writes, ``for_transaction`` inside a P1
    coordinator callback, or ``for_snapshot`` on its pinned Context read. The
    underlying connections are trusted infrastructure, not a public SQL port.
    """

    def __init__(self, connection, directory: Path, *, writable: bool = False):
        self.directory = Path(directory)
        super().__init__(
            _GuardedConnection(
                connection,
                lambda error: self._record_corruption(self.directory, error),
                self._read_complete,
            )
        )
        self._writable = writable
        self._active = True
        self._check()
        roles = self.db.execute("SELECT store_role FROM store_identity").fetchall()
        if roles != [("context",)]:
            raise ContextError("STORE_ROLE", "context", "Context authority required")
        self._validate_schema()
        # Validate registration authority in the pinned transaction, including
        # raw trusted-factory writes. No incoming rejected settings cause a stop.
        self._validate_registrations()

    def _check(self, *, write: bool = False):
        if not self._active:
            raise ContextError("CAPABILITY_EXPIRED", "context")
        if (self.directory / "p1-recovery-stop.json").exists():
            raise CoordinationError("RECOVERY_REQUIRED", "catalog")
        if not self.db.in_transaction:
            raise ContextError("TRANSACTION_REQUIRED", "context")
        if write and not self._writable:
            raise ContextError("READ_ONLY", "context")

    def _read_complete(self):
        self._check()
        # The short fence is acquired after SQLite stepping, avoiding recursive
        # locking when a same-process detector publishes a stop during a SELECT.
        with catalog_completion(self.directory):
            pass

    @staticmethod
    def _record_corruption(directory: Path, error: BaseException):
        code = getattr(error, "sqlite_errorcode", 0) or 0
        # sqlite3's stored-TEXT decoding failure may carry no SQLite errorcode.
        # This precise read error establishes malformed persisted UTF-8, unlike
        # an incoming Python value or generic SQLite operational/input error.
        invalid_utf8 = isinstance(error, sqlite3.OperationalError) and str(
            error
        ).startswith("Could not decode to UTF-8 column")
        if (
            code & 255 in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB)
            or getattr(error, "code", None) == "AUTHORITATIVE_CORRUPTION"
            or invalid_utf8
        ):
            persist_catalog_stop(directory, str(error))

    @classmethod
    @contextmanager
    def for_transaction(cls, db, directory: Path) -> Iterator[Context]:
        """Bind to P1 AdmissionTransaction; never end its outer transaction."""
        capability = cls(db, directory, writable=True)
        try:
            yield capability
            capability._read_complete()
        except BaseException as error:
            cls._record_corruption(Path(directory), error)
            raise
        finally:
            capability._active = False

    @classmethod
    @contextmanager
    def for_snapshot(cls, db, directory: Path) -> Iterator[Context]:
        from repo_catalog.adapters.sqlite.p1_coordination import ReadSnapshot

        if (
            isinstance(db, ReadSnapshot)
            and Path(directory).resolve() != db.catalog_directory
        ):
            raise ContextError("SNAPSHOT_OWNER", "context", "foreign catalog directory")
        capability = cls(db, directory)
        try:
            yield capability
            capability._read_complete()
        except BaseException as error:
            cls._record_corruption(Path(directory), error)
            raise
        finally:
            capability._active = False

    @classmethod
    @contextmanager
    def transaction(cls, directory: Path) -> Iterator[Context]:
        """Gated independent Context transaction, valid without any other store."""
        directory = Path(directory)
        with catalog_gate(directory, exclusive=True):
            if (directory / "p1-recovery-stop.json").exists():
                raise CoordinationError("RECOVERY_REQUIRED", "catalog")
            try:
                with closing(connect(directory / "context.sqlite3", "context")) as db:
                    db.execute("BEGIN IMMEDIATE")
                    try:
                        with cls.for_transaction(db, directory) as capability:
                            yield capability
                        with catalog_completion(directory):
                            db.commit()
                    except BaseException as error:
                        cls._record_corruption(directory, error)
                        db.rollback()
                        raise
            except BaseException as error:
                cls._record_corruption(directory, error)
                raise

    @classmethod
    @contextmanager
    def snapshot(cls, directory: Path, *, read_limits=None) -> Iterator[Context]:
        """Pin Context alone; no claimed Core pairing or derivative dependency."""
        directory = Path(directory)
        with ExitStack() as stack:
            with catalog_gate(directory, exclusive=False):
                try:
                    if (directory / "p1-recovery-stop.json").exists():
                        raise CoordinationError("RECOVERY_REQUIRED", "catalog")
                    db = stack.enter_context(
                        closing(connect(directory / "context.sqlite3", "context"))
                    )
                    db.execute("PRAGMA query_only=ON")
                    db.execute("BEGIN")
                    db.execute("SELECT * FROM store_identity").fetchall()
                    from repo_catalog.adapters.sqlite.p1_coordination import (
                        apply_snapshot_read_limits,
                    )

                    apply_snapshot_read_limits(db, read_limits)
                except BaseException as error:
                    cls._record_corruption(directory, error)
                    raise
            try:
                with cls.for_snapshot(db, directory) as capability:
                    yield capability
            finally:
                db.rollback()

    def snapshot_identity(self):
        """Return the checked identity of this live Context capability."""
        self._check()
        from repo_catalog.adapters.sqlite.p1_coordination import _identity

        return _identity(self.db, "context")

    def snapshot_fingerprint(self):
        """Metadata fence; retained text bytes remain typed-read verified."""
        self._check()
        from repo_catalog.adapters.sqlite.p1_coordination import _digest

        return _digest(self.db, metadata_only=True)

    @contextmanager
    def _unit(self):
        self._check(write=True)
        self.db.execute("SAVEPOINT p3_unit")
        try:
            yield
            self._read_complete()
            self._check(write=True)
            self.db.execute("RELEASE p3_unit")
        except BaseException:
            self.db.execute("ROLLBACK TO p3_unit")
            self.db.execute("RELEASE p3_unit")
            raise

    @contextmanager
    def _stored(self, scope: str):
        """Invalid decoded authoritative rows are storage faults, not input errors."""
        try:
            yield
            self._read_complete()
        except (ValueError, TypeError, AttributeError) as error:
            persist_catalog_stop(self.directory, f"Invalid retained {scope}: {error}")
            raise ContextError("AUTHORITATIVE_CORRUPTION", scope) from error

    def _validate_schema(self):
        rows = self.db.execute(
            "SELECT name, sql FROM sqlite_schema WHERE type='table' AND name IN ('resource_repository_relations', 'repository_mapping_dispositions', 'field_candidates')"
        ).fetchall()
        tables = {name: sql for name, sql in rows}
        if {
            "resource_repository_relations",
            "repository_mapping_dispositions",
            "field_candidates",
        } - set(tables):
            raise ContextError(
                "UNSUPPORTED_SCHEMA",
                "context",
                "Context schema predates ADR 0030 relations",
            )
        if "repository_uuidv4 TEXT" in (tables.get("field_candidates") or ""):
            raise ContextError(
                "UNSUPPORTED_SCHEMA",
                "context",
                "Context schema predates ADR 0030 relations",
            )

    def _validate_registrations(self):
        for table, column, kind in (
            ("providers", "configuration_json", "provider"),
            ("repository_context", "configuration_json", "repository"),
            ("sources", "configuration_json", "source"),
            ("source_repositories", "attributes_json", "membership"),
        ):
            with self._stored("registration"):
                for row in self.db.execute(f"SELECT {column} FROM {table}"):
                    registration_json(kind, row[0])

    def registration_metadata(self, kind: str, encoded: str) -> dict:
        """Read a persisted registration value, never sanitize a stored violation."""
        self._check()
        with self._stored("registration"):
            return registration_json(kind, encoded)

    def provider(self, service: str, kind: str, configuration_json: str = "{}"):
        self._check(write=True)
        registration_json("provider", configuration_json)
        prior = self.db.execute(
            "SELECT provider_kind FROM providers WHERE service_instance_uuidv4=?",
            (service,),
        ).fetchone()
        if prior and prior[0] != kind:
            raise ContextError("IDENTITY_REBIND", "provider", service)
        self.db.execute(
            "INSERT INTO providers VALUES(?,?,?) ON CONFLICT(service_instance_uuidv4) DO UPDATE SET configuration_json=excluded.configuration_json",
            (service, kind, configuration_json),
        )

    def repository(self, repository_uuidv4: str, configuration_json: str = "{}"):
        self._check(write=True)
        registration_json("repository", configuration_json)
        self.db.execute(
            "INSERT INTO repository_context VALUES(?,?) ON CONFLICT(repository_uuidv4) DO UPDATE SET configuration_json=excluded.configuration_json",
            (repository_uuidv4, configuration_json),
        )

    def source(self, source: str, service: str, configuration_json: str = "{}"):
        self._check(write=True)
        registration_json("source", configuration_json)
        prior = self.db.execute(
            "SELECT service_instance_uuidv4 FROM sources WHERE source_registration_uuidv4=?",
            (source,),
        ).fetchone()
        if prior and prior[0] != service:
            raise ContextError("IDENTITY_REBIND", "source", source)
        self.db.execute(
            "INSERT INTO sources VALUES(?,?,?) ON CONFLICT(source_registration_uuidv4) DO UPDATE SET configuration_json=excluded.configuration_json",
            (source, service, configuration_json),
        )

    def source_repositories(self, source: str) -> tuple[str, ...]:
        self._check()
        return tuple(
            row[0]
            for row in self.db.execute(
                "SELECT repository_uuidv4 FROM source_repositories WHERE source_registration_uuidv4=? ORDER BY repository_uuidv4",
                (source,),
            )
        )

    def associate_source(
        self, source: str, repository: str, attributes_json: str = "{}"
    ):
        self._check(write=True)
        registration_json("membership", attributes_json)
        self.db.execute(
            "INSERT INTO source_repositories VALUES(?,?,?) ON CONFLICT(source_registration_uuidv4,repository_uuidv4) DO NOTHING",
            (source, repository, attributes_json),
        )

    def inventory(self, observation: SourceInventory):
        """Append actual terminal evidence; positives survive every later scan."""
        with self._unit():
            scope = json_value(observation.scope_json)
            service = self.db.execute(
                "SELECT service_instance_uuidv4 FROM sources WHERE source_registration_uuidv4=?",
                (observation.source_registration_uuidv4,),
            ).fetchone()
            if service is None:
                raise ContextError("SOURCE_UNAVAILABLE", "source_inventory")
            if (
                isinstance(scope, dict)
                and "service_instance_uuidv4" in scope
                and scope["service_instance_uuidv4"] != service[0]
            ):
                raise ContextError("SOURCE_SERVICE", "source_inventory")
            for repository in observation.repositories:
                self.associate_source(
                    observation.source_registration_uuidv4,
                    repository,
                    observation.provenance_json,
                )
            self.db.execute(
                "INSERT INTO source_inventory_evidence VALUES(?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                observation.values,
            )

    def resource(self, key: ResourceKey, repository_uuidv4: str | None = None):
        self._check(write=True)
        return super().resource(key, repository_uuidv4)

    def resources(self, *, kind: str | None = None) -> tuple[ResourceKey, ...]:
        self._check()
        return tuple(
            ResourceKey(*row)
            for row in self.db.execute(
                "SELECT service_instance_uuidv4,resource_kind,provider_resource_id FROM resources WHERE (? IS NULL OR resource_kind=?) ORDER BY service_instance_uuidv4,resource_kind,provider_resource_id",
                (kind, kind),
            )
        )

    def observe(self, observation: ResourceObservation) -> tuple[str, ...]:
        """Admit one modeled resource atomically, with per-field original clocks."""
        with self._unit():
            self.resource(observation.resource)
            return tuple(self.admit_field(field) for field in observation.fields)

    def inherit_fields(
        self, parent: ResourceKey, child: ResourceKey, fields: Sequence[str]
    ) -> tuple[str, ...]:
        """Explicit field-specific inheritance retains original evidence verbatim.

        No inheritance of absent fields, synthetic clock, receipt time or copied
        raw response is introduced. The real resource relation is checked first.
        """
        with self._unit():
            self._require_resource(parent)
            self._require_resource(child)
            if child.service_instance_uuidv4 != parent.service_instance_uuidv4:
                raise ContextError("INHERITANCE_OWNER", "field")
            if child.resource_kind in {"review", "comment", "thread", "document"}:
                coordinates = json.loads(child.provider_resource_id)
                if tuple(coordinates[:2]) != parent.coordinates()[1:]:
                    raise ContextError("INHERITANCE_OWNER", "field")
            else:
                raise ContextError("INHERITANCE_OWNER", "field")
            results = []
            for field_name in fields:
                for candidate in self.candidates(parent, field_name):
                    results.append(
                        self.admit_field(
                            FieldCandidate(
                                child,
                                field_name,
                                candidate.value_json,
                                candidate.clock,
                                candidate.provenance_json,
                                candidate.observed_at_us,
                            )
                        )
                    )
            return tuple(results)

    def _require_resource(self, key: ResourceKey):
        if not self.db.execute(
            "SELECT 1 FROM resources WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
            key.coordinates(),
        ).fetchone():
            raise ContextError("RESOURCE_UNAVAILABLE", "context", str(key))

    def _members(self, owner: ResourceKey, kind: str, members: Sequence[ResourceKey]):
        child_kind = {
            "reviews": "review",
            "comments": "comment",
            "threads": "thread",
            "documents": "document",
        }.get(kind)
        for member in members:
            self._require_resource(member)
            if child_kind is not None and (
                member.resource_kind != child_kind
                or member.service_instance_uuidv4 != owner.service_instance_uuidv4
                or tuple(json.loads(member.provider_resource_id)[:2])
                != owner.coordinates()[1:]
            ):
                raise ContextError("MEMBER_OWNER", "relation")

    def relation(self, relation: ResourceRelation) -> str:
        with self._unit():
            if relation.relation_kind == "transfer_event_report":
                raise ValueError("Transfer reports require admit_transfer_event()")
            self._members(relation.resource, relation.relation_kind, relation.members)
            key = (
                *relation.resource.coordinates(),
                relation.relation_kind,
                relation.members_json,
                relation.provenance_json,
                relation.scope_json,
            )
            prior = self.db.execute(
                "SELECT observed_at_us FROM resource_relations WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND relation_kind=? AND members_json=? AND provenance_json=? AND scope_json=?",
                key,
            ).fetchone()
            if prior:
                if prior[0] != relation.observed_at_us:
                    raise ContextError("EVIDENCE_REBIND", "relation")
                return "duplicate"
            self.db.execute(
                "INSERT INTO resource_relations VALUES(?,?,?,?,?,?,?,?)",
                (*key, relation.observed_at_us),
            )
            return "insert"

    def relations(
        self, resource: ResourceKey, relation_kind: str
    ) -> tuple[ResourceRelation, ...]:
        self._check()
        with self._stored("relation"):
            values = tuple(
                ResourceRelation(
                    resource,
                    relation_kind,
                    tuple(ResourceKey(*member) for member in json.loads(row[0])),
                    row[1],
                    row[2],
                    row[3],
                )
                for row in self.db.execute(
                    "SELECT members_json,provenance_json,scope_json,observed_at_us FROM resource_relations WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND relation_kind=? ORDER BY observed_at_us,members_json,provenance_json,scope_json",
                    (*resource.coordinates(), relation_kind),
                )
            )
            for value in values:
                self._members(resource, relation_kind, value.members)
            return values

    def collection(self, observation: CollectionObservation):
        with self._unit():
            scope = json_value(observation.scope_json)
            if isinstance(scope, dict):
                if (
                    "service_instance_uuidv4" in scope
                    and scope["service_instance_uuidv4"]
                    != observation.resource.service_instance_uuidv4
                ):
                    raise ContextError("COLLECTION_SERVICE", "collection")
                if "source_registration_uuidv4" in scope:
                    source = self.db.execute(
                        "SELECT service_instance_uuidv4 FROM sources WHERE source_registration_uuidv4=?",
                        (scope["source_registration_uuidv4"],),
                    ).fetchone()
                    if source != (observation.resource.service_instance_uuidv4,):
                        raise ContextError("SOURCE_SERVICE", "collection")
            self._members(
                observation.resource, observation.collection_kind, observation.members
            )
            key = (
                *observation.resource.coordinates(),
                observation.collection_kind,
                observation.provenance_json,
            )
            prior = self.db.execute(
                "SELECT scope_json FROM collections WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND collection_kind=? AND provenance_json=?",
                key,
            ).fetchone()
            if prior and prior[0] != observation.scope_json:
                raise ContextError("EVIDENCE_REBIND", "collection")
            if not prior:
                self.db.execute(
                    "INSERT INTO collections VALUES(?,?,?,?,?,?)",
                    (*key, observation.scope_json),
                )
            self.db.execute(
                "INSERT INTO collection_terminals VALUES(?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                observation.terminal,
            )

    def collection_coverage(
        self,
        resource: ResourceKey,
        collection_kind: str,
        provenance_json: str,
        coverage_kind: str,
        *,
        required_scope_json: str,
    ) -> CoverageProjection:
        """Query the exact collection, including genuine head/base/child scope."""
        self._check()
        json_value(required_scope_json)
        row = self.db.execute(
            "SELECT scope_json FROM collections WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND collection_kind=? AND provenance_json=?",
            (*resource.coordinates(), collection_kind, provenance_json),
        ).fetchone()
        if row and row[0] != required_scope_json:
            raise ContextError("PROOF_SCOPE", "coverage")
        return self.coverage(
            CoverageScope.collection(
                resource, collection_kind, provenance_json, coverage_kind
            )
        )

    def prove_collection(
        self,
        claim: CoverageClaim,
        observation: CollectionObservation,
        *,
        required_scope_json: str,
    ):
        """Link full semantic evidence; exact head/base/nested scope is mandatory."""
        with self._unit():
            json_value(required_scope_json)
            if observation.scope_json != required_scope_json:
                raise ContextError("PROOF_SCOPE", "coverage")
            persisted = self.db.execute(
                "SELECT scope_json FROM collections WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND collection_kind=? AND provenance_json=?",
                (
                    *observation.resource.coordinates(),
                    observation.collection_kind,
                    observation.provenance_json,
                ),
            ).fetchone()
            if persisted is None or persisted[0] != required_scope_json:
                raise ContextError("PROOF_SCOPE", "coverage")
            self.scope(claim.scope)
            if self.admit_coverage(claim) == "stale":
                raise ContextError("STALE_CLAIM", "coverage")
            self.db.execute(
                "INSERT INTO coverage_proofs VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                (
                    claim.scope.owner_kind,
                    claim.scope.encoded,
                    claim.observed_at_us,
                    claim.state,
                    *observation.terminal,
                ),
            )

    def prove_inventory(self, claim: CoverageClaim, observation: SourceInventory):
        with self._unit():
            self.scope(claim.scope)
            if self.admit_coverage(claim) == "stale":
                raise ContextError("STALE_CLAIM", "coverage")
            self.db.execute(
                "INSERT INTO source_coverage_proofs VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                (
                    claim.scope.owner_kind,
                    claim.scope.encoded,
                    claim.observed_at_us,
                    claim.state,
                    *observation.values,
                ),
            )

    def text(self, text_value: str) -> str:
        self._check(write=True)
        if not isinstance(text_value, str):
            raise ContextError("TEXT_REQUIRED", "text")
        digest = hashlib.sha256(text_value.encode("utf-8")).hexdigest()
        prior = self.db.execute(
            "SELECT 1 FROM text_bodies WHERE sha256=?", (digest,)
        ).fetchone()
        if prior:
            # Replaying an incoming body must not mask corruption in the actual
            # retained copy as an ordinary untrusted-input collision rejection.
            self.read_text(digest)
        else:
            self._check_missing_text(digest)
        return super().text(text_value)

    def _check_missing_text(self, digest: str):
        # Canonical field JSON equals the real generated text FK coordinate.
        # Compare stored values directly so an unrelated malformed JSON field
        # cannot mask this actual retained-text dependency.
        expected = self.db.execute(
            "SELECT 1 FROM field_candidates WHERE field_name='text_body_sha256' AND value_json=? LIMIT 1",
            (canonical(digest),),
        ).fetchone()
        if expected:
            persist_catalog_stop(self.directory, "Context retained text is missing")
            raise ContextError("AUTHORITATIVE_CORRUPTION", "text", digest)

    def read_text(self, digest: str) -> str:
        self._check()
        row = self.db.execute(
            "SELECT CAST(text_value AS BLOB) FROM text_bodies WHERE sha256=?", (digest,)
        ).fetchone()
        if row is None:
            self._check_missing_text(digest)
            raise ContextError("TEXT_UNAVAILABLE", "text", digest)
        if hashlib.sha256(row[0]).hexdigest() != digest:
            persist_catalog_stop(
                self.directory, "Context retained text digest mismatch"
            )
            raise ContextError("AUTHORITATIVE_CORRUPTION", "text", digest)
        with self._stored("text"):
            return row[0].decode("utf-8", errors="strict")

    def admit_text(
        self,
        resource: ResourceKey,
        text_value: str | None,
        clock: FieldClock,
        provenance_json: str,
        observed_at_us: int | None,
    ) -> str:
        with self._unit():
            digest = self.text(text_value) if text_value is not None else None
            return self.admit_field(
                FieldCandidate(
                    resource,
                    "text_body_sha256",
                    canonical(digest),
                    clock,
                    provenance_json,
                    observed_at_us,
                )
            )

    def candidates(self, resource: ResourceKey, field_name: str):
        self._check()
        if field_name == "repository_uuidv4":
            raise ValueError(
                "field_candidates is not repository relationship authority; use repository_relations"
            )
        with self._stored("field"):
            return super().candidates(resource, field_name)

    def admit_field(self, candidate: FieldCandidate) -> str:
        self._check(write=True)
        if candidate.field_name.startswith("reported_core_reference:"):
            value = json.loads(candidate.value_json)
            if (
                not candidate.field_name.removeprefix("reported_core_reference:")
                or not isinstance(value, list)
                or len(value) != 2
                or any(not isinstance(item, str) for item in value)
            ):
                raise ContextError("REFERENCE_VALUE", "core_reference")
            OID(*value)
        return super().admit_field(candidate)

    def admit_repository_relation(
        self,
        claim: ResourceRepositoryRelation,
        *,
        require_support: bool = False,
    ) -> RelationAdmissionOutcome:
        with self._unit():
            return super().admit_repository_relation(
                claim, require_support=require_support
            )

    def admit_repository_relation_result(
        self,
        claim: ResourceRepositoryRelation,
        *,
        require_support: bool = False,
    ) -> RelationAdmissionResult:
        with self._unit():
            return super().admit_repository_relation_result(
                claim, require_support=require_support
            )

    def admit_mapping_disposition(self, disposition: MappingDisposition) -> str:
        with self._unit():
            return super().admit_mapping_disposition(disposition)

    def admit_transfer_event(self, report: TransferEventReport) -> str:
        with self._unit():
            return super().admit_transfer_event(report)

    def mapping_dispositions(
        self, subject: MappingClaimKey | ResourceKey | None = None
    ) -> tuple[MappingDisposition, ...]:
        self._check()
        if subject is not None and not isinstance(
            subject, (MappingClaimKey, ResourceKey)
        ):
            raise ValueError("subject must be MappingClaimKey, ResourceKey, or None")
        with self._stored("repository_mapping_disposition"):
            return super().mapping_dispositions(subject)

    def evaluate_provider_repository(
        self,
        resource: ResourceKey,
        *,
        evidence: MappingOperationEvidence | None = None,
    ) -> QualifiedMappingEvaluation:
        self._check()
        if (
            not isinstance(resource, ResourceKey)
            or resource.resource_kind != "repository"
        ):
            raise ValueError(
                "evaluate_provider_repository requires a repository resource"
            )
        if evidence is not None and not isinstance(evidence, MappingOperationEvidence):
            raise ValueError(
                "evidence must be a MappingOperationEvidence instance or None"
            )
        with self._stored("repository_relation"):
            return super().evaluate_provider_repository(resource, evidence=evidence)

    def repository_relations(
        self,
        resource: ResourceKey,
        relation_kind: RelationKind | str | None = None,
        *,
        evidence: MappingOperationEvidence | None = None,
    ) -> tuple[ResolvedRepositoryRelation, ...]:
        self._check()
        if not isinstance(resource, ResourceKey):
            raise ValueError("ResourceKey required")
        if relation_kind is not None and relation_kind not in RELATION_KINDS:
            raise ValueError(f"Unknown relation_kind: {relation_kind!r}")
        if evidence is not None and not isinstance(evidence, MappingOperationEvidence):
            raise ValueError(
                "evidence must be a MappingOperationEvidence instance or None"
            )
        with self._stored("repository_relation"):
            return super().repository_relations(
                resource, relation_kind, evidence=evidence
            )

    def relations_for_repository(
        self,
        repository_uuidv4: str,
        relation_kind: RelationKind | str | None = None,
        *,
        evidence: MappingOperationEvidence | None = None,
    ) -> tuple[ResolvedRepositoryRelation, ...]:
        self._check()
        uuid4_value(repository_uuidv4)
        if relation_kind is not None and relation_kind not in RELATION_KINDS:
            raise ValueError(f"Unknown relation_kind: {relation_kind!r}")
        if evidence is not None and not isinstance(evidence, MappingOperationEvidence):
            raise ValueError(
                "evidence must be a MappingOperationEvidence instance or None"
            )
        with self._stored("repository_relation"):
            return super().relations_for_repository(
                repository_uuidv4, relation_kind, evidence=evidence
            )

    def relations_for_provider_repository(
        self,
        service_or_resource: str | ResourceKey,
        provider_repository_id: str | None = None,
        relation_kind: RelationKind | str | None = None,
        *,
        evidence: MappingOperationEvidence | None = None,
    ) -> tuple[ResolvedRepositoryRelation, ...]:
        self._check()
        if isinstance(service_or_resource, ResourceKey):
            if service_or_resource.resource_kind != "repository":
                raise ValueError(
                    "relations_for_provider_repository requires a repository resource"
                )
            service = service_or_resource.service_instance_uuidv4
            prov_id = service_or_resource.provider_resource_id
            if isinstance(provider_repository_id, str):
                relation_kind = provider_repository_id
        else:
            service = service_or_resource
            uuid4_value(service)
            if provider_repository_id is None or not isinstance(
                provider_repository_id, str
            ):
                raise ValueError(
                    "provider_repository_id required when passing service instance uuid"
                )
            prov_id = provider_repository_id
        if relation_kind is not None and relation_kind not in RELATION_KINDS:
            raise ValueError(f"Unknown relation_kind: {relation_kind!r}")
        if evidence is not None and not isinstance(evidence, MappingOperationEvidence):
            raise ValueError(
                "evidence must be a MappingOperationEvidence instance or None"
            )
        with self._stored("repository_relation"):
            return super().relations_for_provider_repository(
                service,
                prov_id,
                relation_kind,
                evidence=evidence,
            )

    def transfer_event_reports(
        self,
        resource: ResourceKey | None = None,
        *,
        repository_uuidv4: str | None = None,
        selected_repositories: Iterable[str] | None = None,
    ) -> tuple[TransferEventReport, ...]:
        self._check()
        if resource is not None:
            if not isinstance(resource, ResourceKey) or resource.resource_kind not in (
                "issue",
                "comment",
            ):
                raise ValueError(
                    "transfer_event_reports requires an issue or comment resource"
                )
        if repository_uuidv4 is not None:
            uuid4_value(repository_uuidv4)
        selected_tuple: tuple[str, ...] | None = None
        if selected_repositories is not None:
            selected_tuple = tuple(selected_repositories)
            for repo_id in selected_tuple:
                uuid4_value(repo_id)
        with self._stored("transfer_event"):
            return super().transfer_event_reports(
                resource,
                repository_uuidv4=repository_uuidv4,
                selected_repositories=selected_tuple,
            )

    def scope(self, scope: CoverageScope):
        self._check(write=True)
        return super().scope(scope)

    def admit_coverage(self, claim: CoverageClaim) -> str:
        self._check(write=True)
        return super().admit_coverage(claim)

    def coverage(self, scope: CoverageScope) -> CoverageProjection:
        self._check()
        # The capability is already pinned. No SAVEPOINT is issued through a
        # read-only P1 ReadSnapshot, whose authorizer correctly prohibits it.
        with self._stored("coverage"):
            return self._coverage_in_snapshot(scope)

    def link_core(
        self,
        resource: ResourceKey,
        role: str,
        object_format: str,
        full_oid: str,
        provenance_json: str,
        validate: Callable[[str, str], bool],
    ):
        self._check(write=True)
        return super().link_core(
            resource, role, object_format, full_oid, provenance_json, validate
        )

    def report_core_reference(
        self,
        reference: CoreReference,
        *,
        clock: FieldClock,
        observed_at_us: int | None,
    ) -> str:
        """Preserve an attributed portable reference without claiming Core exists.

        The current attributed field is distinct from P1 required dependencies.
        Required links use ``link_core`` after actual nominal resolution. A
        missing reported OID cannot turn a sound pair into a corrupt catalog.
        """
        return self.admit_field(
            FieldCandidate(
                reference.resource,
                "reported_core_reference:" + reference.role,
                canonical(reference.oid.key),
                clock,
                reference.provenance_json,
                observed_at_us,
            )
        )

    def core_dependencies(
        self,
        resource: ResourceKey,
        validate: Callable[[str, str], bool] | None = None,
    ) -> tuple[CoreDependency, ...]:
        self._check()
        with self._stored("core_reference"):
            references = tuple(
                CoreReference(resource, row[0], OID(row[1], row[2]), row[3])
                for row in self.db.execute(
                    "SELECT role,object_format,full_oid,provenance_json FROM core_references WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? ORDER BY role,object_format,full_oid,provenance_json",
                    resource.coordinates(),
                )
            )
        required = tuple(
            CoreDependency(
                reference,
                bool(validate and validate(*reference.oid.key)),
                required=True,
            )
            for reference in references
        )
        reported = []
        for row in self.db.execute(
            "SELECT DISTINCT field_name FROM field_candidates WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND field_name GLOB 'reported_core_reference:*' ORDER BY field_name",
            resource.coordinates(),
        ):
            for candidate in self.candidates(resource, row[0]):
                with self._stored("core_reference"):
                    value = json.loads(candidate.value_json)
                    if (
                        not isinstance(value, list)
                        or len(value) != 2
                        or any(not isinstance(item, str) for item in value)
                    ):
                        raise ContextError("REFERENCE_VALUE", "core_reference")
                    oid = OID(*value)
                reported.append(
                    CoreDependency(
                        CoreReference(
                            resource,
                            candidate.field_name.removeprefix(
                                "reported_core_reference:"
                            ),
                            oid,
                            candidate.provenance_json,
                        ),
                        bool(validate and validate(*oid.key)),
                        candidate=candidate,
                    )
                )
        return (*required, *reported)
