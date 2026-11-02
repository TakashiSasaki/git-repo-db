"""A1b settings/consent ports. No network, generic SQL, import or activation port."""

from typing import Protocol

from repo_catalog.domain.access_connections import (
    AccessPreference,
    AccessReviewPlan,
    AssignmentKey,
    ConnectionConfiguration,
    LocalAccessGrant,
    LocatorConnection,
    RepositoryBinding,
    ScopeExecutionContext,
)
from repo_catalog.domain.access_registry import ScopeLocatorRegistration
from repo_catalog.domain.ports.access_registry import AccessRegistryWrite


class AccessConfiguration(AccessRegistryWrite, Protocol):
    def configure_scope(
        self,
        value: ScopeExecutionContext,
        *,
        expected: ScopeExecutionContext | None = None,
    ) -> str: ...
    def bind_repository(
        self, value: RepositoryBinding, *, expected: RepositoryBinding | None = None
    ) -> str: ...
    def configure_connection(
        self,
        value: ConnectionConfiguration,
        *,
        expected: ConnectionConfiguration | None = None,
    ) -> str: ...
    def assign_connection(
        self, value: LocatorConnection, *, expected: LocatorConnection | None = None
    ) -> str: ...
    def set_preference(
        self, value: AccessPreference, *, expected: AccessPreference | None = None
    ) -> str: ...
    def scope_context(self, identity: str) -> ScopeExecutionContext: ...
    def binding(self, identity: str, locator: str) -> RepositoryBinding: ...
    def configuration(
        self, identity: str, configuration_name: str
    ) -> ConnectionConfiguration: ...
    def assignment(self, key: AssignmentKey) -> LocatorConnection: ...
    def review_plan(
        self,
        repository_uuidv4: str,
        scope_uuidv4: str,
        *,
        assignment: AssignmentKey | None = None,
        registration: ScopeLocatorRegistration | None = None,
        max_candidates: int = 1000,
    ) -> AccessReviewPlan: ...
    def record_local_approval(
        self, plan: AccessReviewPlan, approved_at_us: int
    ) -> LocalAccessGrant: ...
    def revoke_local_approval(self, key: AssignmentKey) -> None: ...
    def current_grant(
        self,
        repository_uuidv4: str,
        scope_uuidv4: str,
        *,
        assignment: AssignmentKey | None = None,
        registration: ScopeLocatorRegistration | None = None,
        max_candidates: int = 1000,
    ) -> LocalAccessGrant: ...
