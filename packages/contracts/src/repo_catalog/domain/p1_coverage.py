"""Shared P1 five-column Coverage values for Core and Context owners.

The whole owner coordinate tuple is losslessly encoded by each typed scope.
Advisory details are excluded from claim identity and latest-state selection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from repo_catalog.domain.coverage import derive_coverage_state as derive_coverage_state
from repo_catalog.domain.coverage_details import validate_coverage_details
from repo_catalog.domain.time import validate_required_observation_us

CoverageState = Literal["unknown", "partial", "complete", "not_applicable"]


class CoverageOwner(Protocol):
    owner_kind: str

    @property
    def encoded(self) -> str: ...


@dataclass(frozen=True)
class CoverageClaim:
    scope: CoverageOwner
    observed_at_us: int
    state: CoverageState
    details_json: str | None = None

    def __post_init__(self) -> None:
        validate_required_observation_us(self.observed_at_us)
        if self.state not in {"unknown", "partial", "complete", "not_applicable"}:
            raise ValueError("Invalid authoritative coverage state")
        validate_coverage_details(self.details_json)


@dataclass(frozen=True)
class CoverageProjection:
    state: str
    observed_at_us: int | None
    claims: tuple[CoverageClaim, ...]
    known_empty: bool
