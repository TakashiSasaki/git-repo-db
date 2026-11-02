"""Finite in-memory work accounting; never a durable acquisition/recovery ledger."""

from repo_catalog.domain.p1_coordination import CoordinationError, NotesLimits
from repo_catalog.domain.shared_values import CoreFailure


class UnlimitedWorkBudget:
    """In-memory bounded WorkBudget used when caller does not supply an Operational ledger."""

    def __init__(
        self,
        *,
        note_bytes: int = 16 * 1024 * 1024,
        work_limits: dict[str, int] | None = None,
    ) -> None:
        self.limits = NotesLimits(note_bytes=note_bytes)
        self._max = dict(NotesLimits.work_limits())
        if work_limits is not None:
            self._max.update(work_limits)
        self.usage: dict[str, int] = dict.fromkeys(self._max, 0)
        self._pending: dict[str, int] = {}

    def require(self, unit: str, amount: int = 1) -> None:
        if type(amount) is not int or amount < 0:
            raise ValueError("nonnegative integer work amount required")
        limit = self._max.get(unit)
        if limit is None:
            raise ValueError(f"unknown work unit: {unit}")
        if self.usage[unit] + amount > limit:
            raise CoreFailure("BUDGET", unit, "finite cumulative request budget")
        if unit in self._pending:
            raise CoordinationError("UNSETTLED_WORK", "request", unit)
        self.usage[unit] += amount
        self._pending[unit] = amount

    def abandon(self, unit: str) -> None:
        if unit not in self._pending:
            raise CoordinationError("UNRESERVED_WORK", "request", unit)
        del self._pending[unit]

    def charge(self, unit: str, amount: int) -> None:
        if unit not in self._pending:
            raise CoordinationError("UNRESERVED_WORK", "request", unit)
        reserved = self._pending.pop(unit)
        if type(amount) is not int or amount < 0 or amount > reserved:
            raise ValueError("invalid charged work amount")
        self.usage[unit] += amount - reserved
