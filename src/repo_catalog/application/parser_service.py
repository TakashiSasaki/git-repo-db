"""Git content reanalysis and bounded supplementary message inspection."""

from pathlib import Path

from repo_catalog.adapters.filesystem.locks import FileLock
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.domain.models import CatalogError, Result


class ParserService:
    def __init__(self, state_dir):
        self.path = Path(state_dir)

    def execute(self, action, options):
        if action == "inspect-message":
            return self._inspect_message(options)
        if action != "reparse":
            raise CatalogError("INVALID_ARGUMENT", "Unknown parser action")
        from repo_catalog.application.parsing_service import ParsingService

        with FileLock(self.path / "locks/writer.lock"), Store(self.path) as store:
            value = ParsingService(store).reparse(
                options["git_acquisition_id"],
                text_encoding=options.get("text_encoding", "utf-8"),
                metadata_encoding=options.get("metadata_encoding", "utf-8"),
                metadata_errors=options.get("metadata_errors", "backslashreplace"),
            )
            return Result({"action": action, "result": value}, catalog=store.revision())

    def _inspect_message(self, options):
        """Inspection of optional external recording admits no catalog facts."""
        from repo_catalog.adapters.recording import LocalArchiveReader, RecordingError

        try:
            recorded = LocalArchiveReader(self.path / "transport-archive").read(
                options["archive_reference"], max_body_bytes=options["max_bytes"]
            )
        except RecordingError as error:
            raise CatalogError(error.code, str(error)) from error
        return Result(
            {
                "archive_reference": options["archive_reference"],
                "context": recorded.context,
                "body_bytes": len(recorded.body) if recorded.body is not None else None,
                "admitted": False,
            }
        )
