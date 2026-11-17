"""Read-only retained-authority validation using the canonical recovery validators."""

from pathlib import Path

from repo_catalog.adapters.sqlite.catalog_runtime import catalog_gate
from repo_catalog.adapters.sqlite.core_recovery import (
    CoreRecoveryAdapter,
    _confirmed_integrity_failure,
    assert_catalog_not_stopped,
    stop_catalog,
)
from repo_catalog.domain.recovery import BackupScope, CorruptionDetectedError


def verify_retained(directory, scope):
    directory = Path(directory)
    scope = BackupScope(scope)
    adapter = CoreRecoveryAdapter()
    if scope == BackupScope.PAIRED:
        from repo_catalog.adapters.sqlite.recovery import SQLiteRecoveryAdapter

        adapter = SQLiteRecoveryAdapter()
    with catalog_gate(directory, exclusive=True):
        assert_catalog_not_stopped(directory)
        try:
            summary = adapter._validate_and_summarize_core(directory / "core.sqlite3")
            core_identity = adapter._extract_identities(
                directory / "core.sqlite3", "core"
            )
            if scope == BackupScope.PAIRED:
                adapter._validate_and_summarize_context(directory / "context.sqlite3")
                if (
                    adapter._extract_identities(
                        directory / "context.sqlite3", "context"
                    )
                    != core_identity
                ):
                    from repo_catalog.domain.recovery import BackupValidationError

                    raise BackupValidationError("paired identity differs")
        except Exception as error:
            category = _confirmed_integrity_failure(error)
            if category is not None:
                stop_catalog(
                    directory,
                    "diagnostic confirmed authoritative corruption",
                    {"classification": category},
                )
                raise CorruptionDetectedError(str(error)) from error
            raise
        assert_catalog_not_stopped(directory)
        return {
            "scope": scope,
            "verified_clean": True,
            "retained_byte_summary": summary,
        }
