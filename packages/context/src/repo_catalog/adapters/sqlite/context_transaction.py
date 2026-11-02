"""Context binding over the canonical shared transaction-owner guard."""

from repo_catalog.adapters.sqlite.admission_transaction import (
    AdmissionTransaction as TransactionGuard,
)


class AdmissionTransaction(TransactionGuard):
    """Context callback transaction with its live local admission binding."""

    def __init__(self, db, *, _context_admission=None):
        super().__init__(db)
        self._context_admission = _context_admission

    def _check_admission_active(self):
        from repo_catalog.domain.context_admission import AdmissionRefused

        if not self._active or not self._db.in_transaction:
            raise AdmissionRefused("PERMISSION_DENIED")

    @property
    def context_admission_binding(self):
        self._check_admission_active()
        return self._context_admission
