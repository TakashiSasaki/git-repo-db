"""P4 Operational continuation metadata; never stages incoming body bytes."""

from repo_catalog.domain.p1_coordination import CoordinationError
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
