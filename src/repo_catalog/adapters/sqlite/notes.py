"""P4 Operational continuation metadata; never stages incoming body bytes."""

from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.p1_core import CoreFailure
from repo_catalog.domain.ports.notes import request_scope


class NotesProgress:
    def __init__(self, work):
        self.work = work

    def _check(self):
        self.work.ledger.validate_continuation(
            self.work.request, self.work.attempt_uuidv4
        )
        self.work.require("metadata_units", 1)
        self.work.charge("metadata_units", 1)

    def bind(
        self,
        repository,
        instance,
        source_attribution,
        source_scope,
        work,
        *,
        catalog_repository_uuidv4=None,
    ):
        if work is not self.work:
            raise CoordinationError(
                "REQUEST_SCOPE", "notes-progress", "budget and progress differ"
            )
        catalog_seed = catalog_repository_uuidv4 or repository
        if self.work.ledger.store_identity() != (catalog_seed, instance):
            raise CoordinationError("STORE_IDENTITY", "notes-progress")
        self.work.ledger.validate_continuation(
            self.work.request,
            self.work.attempt_uuidv4,
            scope=request_scope(repository, instance, source_attribution, source_scope),
        )

    def load(self, scope):
        self._check()
        return self.work.ledger.get_progress(self.work.request, scope)

    def save_once(self, scope, value):
        self._check()
        return self.work.ledger.set_progress_once(self.work.request, scope, value)

    def load_bounded(self, scope, max_bytes):
        self._check()
        size = self.work.ledger.progress_length(self.work.request, scope)
        if size is None:
            return None
        if size > max_bytes:
            raise CoreFailure("BUDGET", scope, "finite pinned metadata limit")
        self.work.require("input_bytes", size)
        try:
            value, actual = self.work.ledger.get_progress_bounded(
                self.work.request, scope, size
            )
        except BaseException:
            self.work.abandon("input_bytes")
            raise
        self.work.charge("input_bytes", actual)
        return value

    def save_once_bounded(self, scope, value, max_bytes, *, encoded):
        self._check()
        prior = self.work.ledger.progress_length(self.work.request, scope)
        upper = max(len(encoded), prior or 0)
        if upper > max_bytes:
            raise CoreFailure("BUDGET", scope, "finite pinned metadata limit")
        self.work.require("input_bytes", upper)
        try:
            result, actual = self.work.ledger.set_progress_once_bounded(
                self.work.request, scope, encoded, upper
            )
        except BaseException:
            self.work.abandon("input_bytes")
            raise
        self.work.charge("input_bytes", actual)
        return result
