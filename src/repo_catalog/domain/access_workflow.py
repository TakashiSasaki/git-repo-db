"""Ephemeral Access review/execution values; never portable authority or DB keys."""

from __future__ import annotations

from dataclasses import dataclass

from repo_catalog.domain.access_connections import (
    AccessReviewPlan,
    AssignmentKey,
)
from repo_catalog.domain.access_registry import (
    AccessRegistryError,
    ScopeLocatorRegistration,
    page_size,
    scope_uuid,
)


@dataclass(frozen=True)
class AccessSelection:
    repository_uuidv4: str
    scope_uuidv4: str
    assignment: AssignmentKey | None = None
    registration: ScopeLocatorRegistration | None = None
    max_candidates: int = 1000

    def __post_init__(self) -> None:
        scope_uuid(self.repository_uuidv4)
        scope_uuid(self.scope_uuidv4)
        page_size(self.max_candidates)
        for value, kind in (
            (self.assignment, AssignmentKey),
            (self.registration, ScopeLocatorRegistration),
        ):
            if value is not None:
                if type(value) is not kind:
                    raise AccessRegistryError(
                        "TYPE", "typed explicit selection required"
                    )
                kind(*value.key)
                if value.scope_uuidv4 != self.scope_uuidv4:
                    raise AccessRegistryError(
                        "SCOPE_MISMATCH", "selection Scope differs"
                    )

    @property
    def options(self) -> dict:
        return {
            "assignment": self.assignment,
            "registration": self.registration,
            "max_candidates": self.max_candidates,
        }


def review_document(plan: AccessReviewPlan) -> dict:
    """Exact non-secret operator display, not a deserialization/admission format."""
    return {
        "scope_uuidv4": plan.assignment.scope_uuidv4,
        "repository_uuidv4": plan.repository_uuidv4,
        "repository_locator": plan.assignment.locator_text,
        "configuration_name": plan.assignment.configuration_name,
        "purpose": plan.assignment.purpose,
        "scope_registration": list(plan.registration.key),
        "reviewed_options_json": plan.options_json,
        "reviewed_context_json": plan.context_json,
    }
