"""Opt-in A1b settings and local-consent persistence, without transport dispatch.

record_local_approval is a trusted LOCAL administration operation, not an intake
method. A2 must supply an operator-facing review and independently activated
executor. Returning a stored grant does not authenticate a human or remote host.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import fields

from repo_catalog.adapters.sqlite import access_schema as schema
from repo_catalog.adapters.sqlite.access_registry import AccessRegistry
from repo_catalog.domain.access_connections import (
    AccessPreference,
    AccessReviewPlan,
    AssignmentKey,
    ConnectionConfiguration,
    LocalAccessGrant,
    LocatorConnection,
    RepositoryBinding,
    ScopeExecutionContext,
    name,
    repository_locator,
)
from repo_catalog.domain.access_registry import (
    AccessRegistryError,
    ScopeLocatorRegistration,
    page_size,
    scope_uuid,
)

# Trusted fixed table/column vocabulary; never interpolated caller SQL.
_LAYOUT = {
    ScopeExecutionContext: (
        "scope_execution_contexts",
        ("scope_uuidv4", "execution_context_json", "enabled"),
        1,
    ),
    RepositoryBinding: (
        "repository_locators",
        ("scope_uuidv4", "locator_text", "repository_uuidv4", "enabled"),
        2,
    ),
    ConnectionConfiguration: (
        "connection_configurations",
        ("scope_uuidv4", "configuration_name", "options_json", "enabled"),
        2,
    ),
    LocatorConnection: (
        "locator_connections",
        ("scope_uuidv4", "locator_text", "configuration_name", "purpose", "enabled"),
        4,
    ),
    AccessPreference: (
        "repository_access_preferences",
        (
            "repository_uuidv4",
            "scope_uuidv4",
            "purpose",
            "locator_text",
            "configuration_name",
        ),
        3,
    ),
}


def _input(value, expected_type):
    if type(value) is not expected_type:
        raise AccessRegistryError("TYPE", "typed Access value required")
    return expected_type(*(getattr(value, field.name) for field in fields(value)))


class AccessConnections(AccessRegistry):
    """Each call owns one transaction. No generic SQL, import or execution port."""

    @contextmanager
    def _transaction(self, *, write=False):
        # Access configuration is bounded operator data. Validate the complete
        # snapshot here rather than letting a damaged FK silently remove a
        # candidate from joins. This deliberately favors integrity over a large
        # registry's scan throughput; no verification bypass or mutable counter.
        with super()._transaction(write=write) as db:
            self._validating = True
            try:
                schema.validate(db)
            except AccessRegistryError as error:
                if error.code == "CORRUPT":
                    self._corrupt()
                raise
            finally:
                self._validating = False
            yield db

    def _authorize(self, action, a, b, database, trigger):
        if (
            self._active
            and getattr(self, "_validating", False)
            and action == sqlite3.SQLITE_PRAGMA
            and a in ("integrity_check", "foreign_key_check")
            and b is None
        ):
            return sqlite3.SQLITE_OK
        if (
            self._active
            and self._writing
            and action == sqlite3.SQLITE_DELETE
            and a == "repository_access_preferences"
        ):
            return sqlite3.SQLITE_OK
        return super()._authorize(action, a, b, database, trigger)

    def _decode(self, cls, row):
        if row is None:
            raise AccessRegistryError("NOT_FOUND", "Access configuration is absent")
        try:
            if cls is ScopeExecutionContext:
                return cls(row[0], row[1], schema._boolean(row[2]))
            if cls in (RepositoryBinding, ConnectionConfiguration):
                return cls(*row[:3], schema._boolean(row[3]))
            if cls is LocatorConnection:
                return cls(AssignmentKey(*row[:4]), schema._boolean(row[4]))
            if cls is AccessPreference:
                return cls(row[0], AssignmentKey(row[1], row[3], row[4], row[2]))
        except (ValueError, TypeError):
            self._corrupt()
        raise AssertionError("unrecognized trusted layout")

    def _get(self, db, cls, key):
        table, columns, width = _LAYOUT[cls]
        clause = " AND ".join(f"{column}=?" for column in columns[:width])
        row = db.execute(f"SELECT * FROM {table} WHERE {clause}", key).fetchone()
        return None if row is None else self._decode(cls, row)

    def _put(self, value, expected):
        cls = type(value)
        table, columns, width = _LAYOUT[cls]
        if expected is not None:
            expected = _input(expected, cls)
            if expected.row[:width] != value.row[:width]:
                raise AccessRegistryError(
                    "IDENTITY", "explicit key changes are unsupported"
                )
        with self._transaction(write=True) as db:
            key = value.row[:width]
            prior = self._get(db, cls, key)
            if expected is None:
                if prior == value:
                    return "duplicate"
                if prior is not None:
                    raise AccessRegistryError(
                        "BINDING_CONFLICT"
                        if cls is RepositoryBinding
                        else "SETTINGS_CONFLICT",
                        "explicit expected prior settings required",
                    )
            elif prior != expected:
                raise AccessRegistryError(
                    "STALE_SETTINGS", "settings changed since inspection"
                )
            if prior == value:
                return "duplicate"
            if prior is None:
                placeholders = ",".join("?" for _ in columns)
                db.execute(f"INSERT INTO {table} VALUES({placeholders})", value.row)
                return "insert"
            if (
                cls is RepositoryBinding
                and prior.repository_uuidv4 != value.repository_uuidv4
            ):
                # Rebinding cannot leave a preference for the former repository.
                db.execute(
                    "DELETE FROM repository_access_preferences WHERE scope_uuidv4=? AND locator_text=?",
                    value.key,
                )
            setters = ",".join(f"{column}=?" for column in columns[width:])
            clause = " AND ".join(f"{column}=?" for column in columns[:width])
            db.execute(
                f"UPDATE {table} SET {setters} WHERE {clause}", value.row[width:] + key
            )
            return "update"

    def configure_scope(
        self,
        value: ScopeExecutionContext,
        *,
        expected: ScopeExecutionContext | None = None,
    ) -> str:
        return self._put(_input(value, ScopeExecutionContext), expected)

    def bind_repository(
        self, value: RepositoryBinding, *, expected: RepositoryBinding | None = None
    ) -> str:
        return self._put(_input(value, RepositoryBinding), expected)

    def configure_connection(
        self,
        value: ConnectionConfiguration,
        *,
        expected: ConnectionConfiguration | None = None,
    ) -> str:
        return self._put(_input(value, ConnectionConfiguration), expected)

    def assign_connection(
        self, value: LocatorConnection, *, expected: LocatorConnection | None = None
    ) -> str:
        return self._put(_input(value, LocatorConnection), expected)

    def set_preference(
        self, value: AccessPreference, *, expected: AccessPreference | None = None
    ) -> str:
        return self._put(_input(value, AccessPreference), expected)

    def _read(self, cls, key):
        with self._transaction() as db:
            value = self._get(db, cls, key)
            if value is None:
                raise AccessRegistryError("NOT_FOUND", "Access configuration is absent")
            return value

    def scope_context(self, identity: str) -> ScopeExecutionContext:
        return self._read(ScopeExecutionContext, (scope_uuid(identity),))

    def binding(self, identity: str, locator: str) -> RepositoryBinding:
        scope_uuid(identity)
        repository_locator(locator)
        return self._read(RepositoryBinding, (identity, locator))

    def configuration(
        self, identity: str, configuration_name: str
    ) -> ConnectionConfiguration:
        return self._read(
            ConnectionConfiguration, (scope_uuid(identity), name(configuration_name))
        )

    def assignment(self, key: AssignmentKey) -> LocatorConnection:
        return self._read(LocatorConnection, _input(key, AssignmentKey).key)

    def _plan(
        self,
        db,
        repository: str,
        key: AssignmentKey,
        registration: ScopeLocatorRegistration,
    ) -> AccessReviewPlan:
        if key.scope_uuidv4 != registration.scope_uuidv4:
            raise AccessRegistryError("SCOPE_MISMATCH", "selected Scope does not match")
        context = self._get(db, ScopeExecutionContext, (key.scope_uuidv4,))
        binding = self._get(db, RepositoryBinding, key.key[:2])
        profile = self._get(
            db, ConnectionConfiguration, (key.scope_uuidv4, key.configuration_name)
        )
        assignment = self._get(db, LocatorConnection, key.key)
        if any(value is None for value in (context, binding, profile, assignment)):
            raise AccessRegistryError(
                "UNCONFIGURED", "complete Access assignment required"
            )
        if binding.repository_uuidv4 != repository:
            raise AccessRegistryError(
                "BINDING_CONFLICT", "locator belongs to another repository"
            )
        if not self._has_registration(db, registration):
            raise AccessRegistryError("NOT_FOUND", "Scope registration is absent")
        control = db.execute(
            "SELECT enabled FROM scope_locator_controls WHERE scope_uuidv4=? AND registered_at_us=? AND scope_locator_uri=?",
            registration.key,
        ).fetchone()
        try:
            enabled = False if control is None else schema._boolean(control[0])
        except ValueError:
            self._corrupt()
        if not enabled or not all(
            v.enabled for v in (context, binding, profile, assignment)
        ):
            raise AccessRegistryError("DISABLED", "selected Access route is disabled")
        try:
            return AccessReviewPlan(
                key,
                repository,
                registration,
                profile.options_json,
                context.context_json,
            )
        except ValueError:
            self._corrupt()

    def _review(self, db, repository, identity, key, registration, bound):
        self._scope(db, identity)
        if registration is None:
            rows = db.execute(
                "SELECT * FROM scope_first_choices WHERE scope_uuidv4=? ORDER BY scope_locator_uri LIMIT ?",
                (identity, bound + 1),
            ).fetchall()
            if len(rows) > bound:
                raise AccessRegistryError(
                    "CANDIDATE_LIMIT", "Scope tie set exceeds bound"
                )
            if not rows:
                raise AccessRegistryError("UNCONFIGURED", "Scope locator required")
            if len(rows) != 1:
                raise AccessRegistryError(
                    "AMBIGUOUS", "explicit Scope registration required"
                )
            registration = self._registration(rows[0])
        if key is None:
            preference = self._get(
                db, AccessPreference, (repository, identity, "git-read")
            )
            if preference is not None:
                key = preference.assignment
            else:
                rows = db.execute(
                    "SELECT a.scope_uuidv4,a.locator_text,a.configuration_name,a.purpose FROM locator_connections a JOIN repository_locators r USING(scope_uuidv4,locator_text) JOIN connection_configurations p USING(scope_uuidv4,configuration_name) WHERE a.scope_uuidv4=? AND r.repository_uuidv4=? AND a.enabled=1 AND r.enabled=1 AND p.enabled=1 ORDER BY a.locator_text,a.configuration_name LIMIT ?",
                    (identity, repository, bound + 1),
                ).fetchall()
                if len(rows) > bound:
                    raise AccessRegistryError(
                        "CANDIDATE_LIMIT", "assignment set exceeds bound"
                    )
                if not rows:
                    raise AccessRegistryError(
                        "UNCONFIGURED", "no enabled repository assignment"
                    )
                if len(rows) != 1:
                    raise AccessRegistryError(
                        "AMBIGUOUS", "explicit assignment or preference required"
                    )
                try:
                    key = AssignmentKey(*rows[0])
                except ValueError:
                    self._corrupt()
        return self._plan(db, repository, key, registration)

    @staticmethod
    def _selection(repository, identity, assignment, registration, max_candidates):
        scope_uuid(repository)
        scope_uuid(identity)
        bound = page_size(max_candidates)
        key = None if assignment is None else _input(assignment, AssignmentKey)
        route = None if registration is None else AccessRegistry._input(registration)
        if (key is not None and key.scope_uuidv4 != identity) or (
            route is not None and route.scope_uuidv4 != identity
        ):
            raise AccessRegistryError(
                "SCOPE_MISMATCH", "explicit choice belongs to another Scope"
            )
        return key, route, bound

    def review_plan(
        self,
        repository_uuidv4: str,
        scope_uuidv4: str,
        *,
        assignment: AssignmentKey | None = None,
        registration: ScopeLocatorRegistration | None = None,
        max_candidates: int = 1000,
    ) -> AccessReviewPlan:
        key, route, bound = self._selection(
            repository_uuidv4, scope_uuidv4, assignment, registration, max_candidates
        )
        with self._transaction() as db:
            return self._review(db, repository_uuidv4, scope_uuidv4, key, route, bound)

    def record_local_approval(
        self, plan: AccessReviewPlan, approved_at_us: int
    ) -> LocalAccessGrant:
        """Record explicit LOCAL operator consent to the reviewed non-secret values.

        Trusted administration only: never invoke on deserialized import/restore.
        This is not dispatch, executor activation, or proof of a human click.
        """
        value = _input(plan, AccessReviewPlan)
        grant = LocalAccessGrant(value, approved_at_us)
        with self._transaction(write=True) as db:
            current = self._plan(
                db, value.repository_uuidv4, value.assignment, value.registration
            )
            if current != value:
                raise AccessRegistryError(
                    "REVIEW_CHANGED", "reviewed settings no longer match"
                )
            db.execute(
                "DELETE FROM local_access_grants WHERE scope_uuidv4=? AND locator_text=? AND configuration_name=? AND purpose=?",
                value.assignment.key,
            )
            db.execute(
                "INSERT INTO local_access_grants VALUES(?,?,?,?,?,?,?,?,?,?)",
                (*value.row, grant.approved_at_us),
            )
        return grant

    def revoke_local_approval(self, key: AssignmentKey) -> None:
        value = _input(key, AssignmentKey)
        with self._transaction(write=True) as db:
            db.execute(
                "DELETE FROM local_access_grants WHERE scope_uuidv4=? AND locator_text=? AND configuration_name=? AND purpose=?",
                value.key,
            )

    def current_grant(
        self,
        repository_uuidv4: str,
        scope_uuidv4: str,
        *,
        assignment: AssignmentKey | None = None,
        registration: ScopeLocatorRegistration | None = None,
        max_candidates: int = 1000,
    ) -> LocalAccessGrant:
        """Read locally stored consent for this exact plan; never execute it."""
        key, route, bound = self._selection(
            repository_uuidv4, scope_uuidv4, assignment, registration, max_candidates
        )
        with self._transaction() as db:
            selected = self._review(
                db, repository_uuidv4, scope_uuidv4, key, route, bound
            )
            row = db.execute(
                "SELECT * FROM local_access_grants WHERE scope_uuidv4=? AND locator_text=? AND configuration_name=? AND purpose=?",
                selected.assignment.key,
            ).fetchone()
            if row is None:
                raise AccessRegistryError(
                    "APPROVAL_REQUIRED", "explicit local review required"
                )
            try:
                recorded = AccessReviewPlan(
                    AssignmentKey(*row[:4]),
                    row[4],
                    ScopeLocatorRegistration(row[0], row[5], row[6]),
                    row[7],
                    row[8],
                )
                grant = LocalAccessGrant(recorded, row[9])
                actual = self._plan(
                    db, row[4], recorded.assignment, recorded.registration
                )
            except ValueError:
                self._corrupt()
            if recorded != actual:
                self._corrupt()
            if recorded != selected:
                raise AccessRegistryError(
                    "APPROVAL_REQUIRED", "selected registration needs its own approval"
                )
            return grant
