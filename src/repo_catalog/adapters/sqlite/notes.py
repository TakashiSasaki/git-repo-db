"""P4 Operational continuation metadata; never stages incoming body bytes."""

import hashlib
import os
from contextlib import contextmanager

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

    @contextmanager
    def scan_guard(self, scope):
        """Serialize read-then-pin across processes without holding a DB transaction."""
        self._check()
        if os.name != "posix":
            raise CoordinationError("UNSUPPORTED_PLATFORM", "notes-scan", os.name)
        import fcntl

        if not isinstance(scope, str) or len(scope) > 4 * 1024 * 1024:
            raise CoreFailure("BUDGET", "notes-scan", "finite guard scope required")
        upper = 16 * len(scope) + 80
        self.work.require("input_bytes", upper)
        try:
            normalized = self.work.ledger._progress_scope(scope)
            request_bytes = "".join(self.work.request.values()).encode("ascii")
            scope_bytes = normalized.encode("ascii")
            stripe = hashlib.sha256(request_bytes + b"\0" + scope_bytes).hexdigest()[:4]
            actual = (
                len(scope.encode("utf-8", "surrogatepass"))
                + len(request_bytes)
                + len(scope_bytes)
                + 1
            )
        except BaseException:
            self.work.abandon("input_bytes")
            raise
        self.work.charge("input_bytes", actual)
        # Fixed, finite stripes are coordination only; their hashes are never
        # domain identities. Never unlink a stripe while a process may hold it.
        path = self.work.ledger._path.parent / f"p1-ref-acquisition-{stripe}.lock"
        try:
            handle = path.open("a+b")
        except OSError as error:
            raise CoordinationError(
                "CONTINUATION_UNAVAILABLE", "notes-scan", str(error)
            ) from error
        try:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise CoreFailure(
                    "ACQUISITION_BUSY",
                    scope,
                    "another scan owns the acquisition guard; retry",
                ) from error
            try:
                self._check()
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            handle.close()

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

    def request_identity(self):
        self._check()
        return self.work.request.values()

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
