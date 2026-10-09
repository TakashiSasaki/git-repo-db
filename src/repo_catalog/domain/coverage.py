"""Coverage is a set of immutable, timestamped evaluations of one scope.

Only scope, observation time and coverage state determine claim identity and
admission. Advisory details never resolve a conflict or break a timestamp tie.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

from repo_catalog.domain.time import validate_epoch_us

STORED_COVERAGE_STATES = frozenset({"complete", "partial", "unknown", "not_applicable"})
AdmissionDecision = Literal["insert", "stale", "duplicate"]


def _validate_state(coverage_state: str) -> None:
    if not isinstance(coverage_state, str):
        raise TypeError("Coverage state must be a string")
    if coverage_state not in STORED_COVERAGE_STATES:
        raise ValueError("Unknown stored coverage state")


def validate_claim(
    coverage_scope_id: str, coverage_state: str, observed_at_us: int
) -> None:
    """Validate the semantic claim without consulting advisory details."""
    if not isinstance(coverage_scope_id, str):
        raise TypeError("Coverage scope must be a string")
    if not coverage_scope_id:
        raise ValueError("Coverage scope must not be empty")
    _validate_state(coverage_state)
    validate_epoch_us(observed_at_us)


def derive_coverage_state(states: Iterable[str]) -> str:
    """Resolve states already restricted to one scope and observation time.

    No observations is represented by unknown without inventing a stored claim.
    Conflict is a derived result and is never an admissible stored state.
    """
    determinate = set()
    for state in states:
        _validate_state(state)
        if state != "unknown":
            determinate.add(state)
    if not determinate:
        return "unknown"
    if len(determinate) == 1:
        return next(iter(determinate))
    return "conflict"


def latest_claims(
    claims: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Keep the maximal-time claim set for one scope, including unknown.

    Callers may retain local IDs and advisory fields in these mappings; neither
    affects selection. Claim dictionaries are copied, never merged or rewritten.
    """
    scope, latest, selected = None, None, []
    for original in claims:
        claim = dict(original)
        validate_claim(
            claim["coverage_scope_id"],
            claim["coverage_state"],
            claim["observed_at_us"],
        )
        if scope is None:
            scope = claim["coverage_scope_id"]
        elif claim["coverage_scope_id"] != scope:
            raise ValueError("Coverage resolution requires one scope")
        stamp = claim["observed_at_us"]
        if latest is None or stamp > latest:
            latest, selected = stamp, [claim]
        elif stamp == latest:
            selected.append(claim)
    return tuple(sorted(selected, key=lambda claim: claim["coverage_state"]))


def decide_admission(
    existing: Iterable[Mapping[str, Any]], incoming: Mapping[str, Any]
) -> AdmissionDecision:
    """Decide admission without modifying or merging either claim set.

    Same-time unknown claims remain facts even when a determinate claim already
    exists; only resolution treats unknown as weaker. SQLite writers separately
    enforce this decision atomically when concurrent admission is possible.
    """
    validate_claim(
        incoming["coverage_scope_id"],
        incoming["coverage_state"],
        incoming["observed_at_us"],
    )
    current = latest_claims(existing)
    if not current:
        return "insert"
    if incoming["coverage_scope_id"] != current[0]["coverage_scope_id"]:
        raise ValueError("Coverage admission requires one scope")
    if incoming["observed_at_us"] < current[0]["observed_at_us"]:
        return "stale"
    if incoming["observed_at_us"] == current[0]["observed_at_us"] and any(
        claim["coverage_state"] == incoming["coverage_state"] for claim in current
    ):
        return "duplicate"
    return "insert"
