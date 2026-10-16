"""Application recovery service for P7 under ADR 0026."""

from __future__ import annotations

from pathlib import Path

from repo_catalog.adapters.sqlite.recovery import (
    SQLiteRecoveryAdapter,
    assert_catalog_not_stopped,
    is_catalog_stopped,
    stop_catalog,
)
from repo_catalog.domain.recovery import (
    ActivationReceipt,
    BackupReceipt,
    BackupScope,
    MergeReceipt,
    RestoreReceipt,
    SalvageReceipt,
)


class RecoveryService:
    """Orchestrates consistent backup, persistent stop, salvage, fresh restore, and safe activation."""

    def __init__(self, adapter: SQLiteRecoveryAdapter | None = None) -> None:
        self.adapter = adapter or SQLiteRecoveryAdapter()

    def create_consistent_backup(
        self,
        catalog_dir: Path | str,
        destination_path: Path | str,
        scope: BackupScope = BackupScope.PAIRED,
    ) -> BackupReceipt:
        """Create a durable, consistent, verified backup of authoritative stores."""
        return self.adapter.create_consistent_backup(
            Path(catalog_dir), Path(destination_path), scope=scope
        )

    def stop_suspect_catalog(
        self,
        catalog_dir: Path | str,
        reason: str,
        details: dict | None = None,
    ) -> None:
        """Immediately enter persistent recovery stop mode for the affected catalog."""
        stop_catalog(Path(catalog_dir), reason, details)

    def is_stopped(self, catalog_dir: Path | str) -> bool:
        """Check if catalog is stopped."""
        return is_catalog_stopped(Path(catalog_dir))

    def assert_not_stopped(self, catalog_dir: Path | str) -> None:
        """Raise CatalogStoppedError if catalog is stopped."""
        assert_catalog_not_stopped(Path(catalog_dir))

    def extract_salvage(
        self,
        catalog_dir: Path | str,
        output_file: Path | str,
        max_records: int | None = None,
    ) -> SalvageReceipt:
        """Perform read-only, bounded, untrusted salvage extraction from a suspect catalog."""
        return self.adapter.extract_salvage(
            Path(catalog_dir), Path(output_file), max_records=max_records
        )

    def restore_backup(
        self,
        backup_path: Path | str,
        destination_dir: Path | str,
        expected_repository_uuidv4: str,
    ) -> RestoreReceipt:
        """Restore and revalidate a baseline backup into a fresh destination directory."""
        return self.adapter.restore_backup(
            Path(backup_path), Path(destination_dir), expected_repository_uuidv4
        )

    def merge_salvage(
        self,
        fresh_destination_dir: Path | str,
        salvage_file: Path | str,
    ) -> MergeReceipt:
        """Merge untrusted salvaged candidates into the fresh destination with receiver verification."""
        return self.adapter.merge_salvage(
            Path(fresh_destination_dir), Path(salvage_file)
        )

    def activate_catalog(
        self,
        fresh_catalog_dir: Path | str,
        target_locator_path: Path | str,
    ) -> ActivationReceipt:
        """Validate fresh catalog, reconstruct Operational and Search, and safely activate."""
        return self.adapter.activate(Path(fresh_catalog_dir), Path(target_locator_path))
