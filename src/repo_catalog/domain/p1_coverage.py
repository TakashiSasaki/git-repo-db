"""Shared P1 five-column Coverage values for Core and Context owners.

The whole owner coordinate tuple is losslessly encoded by each typed scope.
Advisory details are excluded from claim identity and latest-state selection.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, Protocol

from repo_catalog.domain.coverage import derive_coverage_state as derive_coverage_state
from repo_catalog.domain.time import validate_epoch_us

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
        validate_epoch_us(self.observed_at_us)
        if self.state not in {"unknown", "partial", "complete", "not_applicable"}:
            raise ValueError("Invalid authoritative coverage state")
        if (
            self.details_json is not None
            and json.dumps(
                json.loads(self.details_json),
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            != self.details_json
        ):
            raise ValueError("Details must be canonical JSON")


@dataclass(frozen=True)
class CoverageProjection:
    state: str
    observed_at_us: int | None
    claims: tuple[CoverageClaim, ...]
    known_empty: bool
