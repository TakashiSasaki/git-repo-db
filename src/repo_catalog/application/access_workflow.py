"""Opt-in local review and one-shot pre-dispatch checks on A1b persistence.

This module never chooses a transport or imports an adapter. Adapters/reviewers and
operation callbacks are trusted local code, not content from Access or Exchange.
No token is serialized, stored in SQLite or accepted from another process/session.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TypeVar

from repo_catalog.domain.access_connections import AccessReviewPlan, LocalAccessGrant
from repo_catalog.domain.access_registry import AccessRegistryError
from repo_catalog.domain.access_workflow import AccessSelection, review_document
from repo_catalog.domain.ports.access_connections import AccessConfiguration
from repo_catalog.domain.ports.access_workflow import (
    AccessExecutorFactory,
    BoundAccessExecutor,
)

T = TypeVar("T")
Reviewer = Callable[[dict], bool]


@dataclass
class _Pending:
    kind: str
    selection: AccessSelection
    plan: AccessReviewPlan
    deadline_ns: int
    grant: LocalAccessGrant | None = None
    executor: BoundAccessExecutor | None = None
    evidence: str | None = None


class AccessWorkflow:
    """Single-thread-owned local session, independent of any domain catalog.

    Integration MUST supply a domain-stop guard to dispatch_once when touching a
    catalog. The standalone CLI only fstats a pinned directory and has no catalog.
    A successful final check admits ONE operation; revocation after that boundary
    does not claim cancellation of work already in flight. Retries get no token.
    """

    def __init__(
        self,
        store: AccessConfiguration,
        *,
        lifetime_seconds: int = 300,
        max_pending: int = 64,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
        epoch_us: Callable[[], int] = lambda: time.time_ns() // 1000,
    ):
        if (
            type(lifetime_seconds) is not int
            or not 1 <= lifetime_seconds <= 3600
            or type(max_pending) is not int
            or not 1 <= max_pending <= 1024
        ):
            raise AccessRegistryError("LIMIT", "finite session limits required")
        self._store = store
        self._ttl = lifetime_seconds * 1_000_000_000
        self._limit = max_pending
        self._now = monotonic_ns
        self._epoch = epoch_us
        self._pid = os.getpid()
        self._thread = threading.get_ident()
        self._pending: dict[object, _Pending] = {}
        self._closed = False

    def __enter__(self) -> AccessWorkflow:
        self._ready()
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def close(self) -> None:
        self._closed = True
        pending, self._pending = self._pending, {}
        for item in pending.values():
            if item.executor is not None:
                item.executor.close()

    def _ready(self) -> None:
        if (
            self._closed
            or os.getpid() != self._pid
            or threading.get_ident() != self._thread
        ):
            raise AccessRegistryError("SESSION_CLOSED", "local session unavailable")

    def _age(self, pending: _Pending) -> None:
        if self._now() >= pending.deadline_ns:
            raise AccessRegistryError("EXPIRED", "review or activation expired")

    def _room(self) -> None:
        self._ready()
        for token, value in tuple(self._pending.items()):
            if self._now() >= value.deadline_ns:
                self._pending.pop(token)
                if value.executor is not None:
                    value.executor.close()
        if len(self._pending) >= self._limit:
            raise AccessRegistryError("PENDING_LIMIT", "pending session limit reached")

    def _save(self, value: _Pending) -> object:
        self._room()
        self._age(value)
        token = object()  # Process-local capability handle, NOT a domain identifier.
        self._pending[token] = value
        return token

    def _take(self, token: object, kind: str) -> _Pending:
        self._ready()
        try:
            value = self._pending.pop(token)
        except (KeyError, TypeError):
            raise AccessRegistryError(
                "TOKEN", "unknown or consumed local token"
            ) from None
        try:
            if value.kind != kind:
                raise AccessRegistryError("TOKEN", "wrong local token purpose")
            self._age(value)
            return value
        except BaseException:
            if value.executor is not None:
                value.executor.close()
            raise

    @staticmethod
    def _selection(value: AccessSelection) -> AccessSelection:
        if type(value) is not AccessSelection:
            raise AccessRegistryError("TYPE", "typed Access selection required")
        # Reconstruct all nested values; callers cannot mutate the stored selection
        # by later changing their own dataclass objects.
        return AccessSelection(
            value.repository_uuidv4,
            value.scope_uuidv4,
            None if value.assignment is None else replace(value.assignment),
            None if value.registration is None else replace(value.registration),
            value.max_candidates,
        )

    def _review(self, selection: AccessSelection) -> AccessReviewPlan:
        return self._store.review_plan(
            selection.repository_uuidv4, selection.scope_uuidv4, **selection.options
        )

    def _grant(self, selection: AccessSelection) -> LocalAccessGrant:
        return self._store.current_grant(
            selection.repository_uuidv4, selection.scope_uuidv4, **selection.options
        )

    def inspect(self, selection: AccessSelection) -> dict:
        """Read/display settings only; no local executor or credential is probed."""
        self._ready()
        return review_document(self._review(self._selection(selection)))

    def begin_review(self, selection: AccessSelection) -> object:
        self._room()
        selection = self._selection(selection)
        plan = self._review(selection)
        return self._save(_Pending("review", selection, plan, self._now() + self._ttl))

    def approve(self, token: object, reviewer: Reviewer) -> LocalAccessGrant:
        value = self._take(token, "review")
        # A callback is a local integration boundary, NOT a bool from an import.
        if (
            reviewer({"operation": "approve", "plan": review_document(value.plan)})
            is not True
        ):
            raise AccessRegistryError("DECLINED", "local review was not approved")
        self._ready()
        self._age(value)
        if self._review(value.selection) != value.plan:
            raise AccessRegistryError("REVIEW_CHANGED", "selected settings changed")
        # A1b rechecks the full explicit plan atomically with recording consent.
        # A concurrent new default may create a consent for the shown old plan;
        # it never grants consent to the unseen new plan. Dispatch rechecks selection.
        self._ready()
        self._age(value)
        return self._store.record_local_approval(value.plan, self._epoch())

    def activate(
        self,
        selection: AccessSelection,
        factory: AccessExecutorFactory,
        reviewer: Reviewer,
    ) -> object:
        """Explicit local activation; any executor inspection starts after a grant.

        bind may inspect local OS state; it must not send network requests or read
        credentials. Unsupported remote/container execution is rejected by the
        supplied local adapter, not treated as an authenticated declaration.
        """
        self._room()
        selection = self._selection(selection)
        grant = self._grant(selection)
        bound = factory.bind(grant.plan)
        try:
            evidence = bound.evidence()
            value = _Pending(
                "execution",
                selection,
                grant.plan,
                self._now() + self._ttl,
                grant,
                bound,
                evidence,
            )
            document = {
                "operation": "activate-local",
                "plan": review_document(grant.plan),
                "executor_evidence_json": evidence,
            }
            if reviewer(document) is not True:
                raise AccessRegistryError("DECLINED", "local executor not activated")
            self._ready()
            self._age(value)
            if bound.evidence() != evidence or self._grant(selection) != grant:
                raise AccessRegistryError(
                    "ACTIVATION_CHANGED", "activation inputs changed"
                )
            return self._save(value)
        except BaseException:
            bound.close()
            raise

    def dispatch_once(
        self,
        token: object,
        operation: Callable[[int], T],
        *,
        guard: Callable[[], None],
    ) -> T:
        """Final check then ONE trusted callback, outside all SQLite transactions.

        The required guard is the embedding application's cancellation/catalog-stop
        boundary, NOT a bool read from Access. It may reject; it cannot authorize
        a stale Access grant. No implicit retry or plan retargeting is performed.
        """
        value = self._take(token, "execution")
        assert value.executor is not None and value.grant is not None
        try:
            guard()
            self._ready()
            self._age(value)
            if value.executor.evidence() != value.evidence:
                raise AccessRegistryError(
                    "EXECUTOR_CHANGED", "local environment changed"
                )
            if self._grant(value.selection) != value.grant:
                raise AccessRegistryError("GRANT_CHANGED", "reviewed grant changed")
            # Final Access read has committed before invoking trusted work. The
            # adapter uses pinned descriptors; subsequent revocation is in-flight.
            self._ready()
            self._age(value)
            return value.executor.invoke(operation)
        finally:
            value.executor.close()
