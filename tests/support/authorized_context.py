"""Finite, explicit local composition for legacy low-level Context fixtures.

This test helper owns real product transactions. Grants are fixed by the
fixture, never inferred from an attempted write or expanded after a refusal.
"""

from contextlib import contextmanager
from functools import wraps

from repo_catalog.adapters.sqlite.context_admission import MUTATIONS
from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.domain.context_admission import AdmissionRefused
from tests.support.context_admission import fixture_context, fixture_service


class _FixtureRollback(Exception):
    pass


class FixtureContextStore:
    """Issue finite fixture invocations and retain commit-owned policy leases."""

    def __init__(self, connection, grants):
        self.service, self.policy = fixture_service(grants)
        self.store = ContextStore(connection, authorization=self.service)
        self._active = True
        self._transaction_depth = 0

    def close(self):
        self._active = False

    def _check_active(self):
        if not self._active:
            raise AdmissionRefused("PERMISSION_DENIED")

    @contextmanager
    def transaction(self, *, rollback=False):
        """Own the actual SQL transaction, including deliberate rollback tests."""
        self._check_active()
        admission = fixture_context(self.service)
        try:
            with self.store.admission_transaction(admission=admission):
                self._transaction_depth += 1
                try:
                    yield self
                    if rollback:
                        raise _FixtureRollback()
                finally:
                    self._transaction_depth -= 1
        except _FixtureRollback:
            if not rollback:
                raise

    def __getattr__(self, name):
        value = getattr(self.store, name)
        if name not in MUTATIONS:
            return value

        @wraps(value)
        def write(*args, **kwargs):
            self._check_active()
            if self._transaction_depth:
                return value(*args, **kwargs)
            with self.transaction():
                return value(*args, **kwargs)

        return write
