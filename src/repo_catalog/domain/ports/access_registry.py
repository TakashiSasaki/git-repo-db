"""Read/write registry ports, deliberately without grants, dispatch or raw SQL."""

from typing import Literal, Protocol

from repo_catalog.domain.access_registry import (
    AccessScope,
    RegistrationPage,
    RegistrationResult,
    ScopeLocatorRegistration,
)


class AccessRegistryRead(Protocol):
    def scope(self, scope_uuidv4: str) -> AccessScope: ...
    def history(
        self,
        scope_uuidv4: str,
        *,
        limit: int = 100,
        after: ScopeLocatorRegistration | None = None,
    ) -> RegistrationPage: ...
    def first_choices(
        self, scope_uuidv4: str, *, max_candidates: int = 1000
    ) -> tuple[ScopeLocatorRegistration, ...]: ...
    def locator_enabled(self, registration: ScopeLocatorRegistration) -> bool: ...


class AccessRegistryWrite(AccessRegistryRead, Protocol):
    def register_scope(self, scope: AccessScope) -> Literal["insert", "duplicate"]: ...
    def rename_scope(self, scope_uuidv4: str, display_name: str) -> None: ...
    def register_locator(
        self, registration: ScopeLocatorRegistration
    ) -> RegistrationResult: ...
    def set_locator_enabled(
        self, registration: ScopeLocatorRegistration, enabled: bool
    ) -> None: ...
