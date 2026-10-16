"""Domain ports for P7 recovery operations under ADR 0026."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol

from repo_catalog.domain.recovery import (
    ActivationReceipt,
    BackupReceipt,
    BackupScope,
    MergeReceipt,
    RecoveryBudget,
    RestoreReceipt,
    SalvageReceipt,
)


class StopFencingPort(Protocol):
    def stop_catalog(
        self, catalog_dir: Path, reason: str, details: dict | None = None
    ) -> None: ...

    def is_catalog_stopped(self, catalog_dir: Path) -> bool: ...

    def assert_catalog_not_stopped(self, catalog_dir: Path) -> None: ...


class BackupPort(Protocol):
    def create_consistent_backup(
        self,
        catalog_dir: Path,
        destination_path: Path,
        scope: BackupScope = BackupScope.PAIRED,
        *,
        snapshot_cut_callback: Callable[[], None] | None = None,
    ) -> BackupReceipt: ...


class SalvagePort(Protocol):
    def extract_salvage(
        self,
        catalog_dir: Path,
        output_file: Path,
        max_records: int | None = None,
        max_bytes: int | None = None,
        budget: RecoveryBudget | None = None,
    ) -> SalvageReceipt: ...


class RestorePort(Protocol):
    def restore_backup(
        self,
        backup_path: Path,
        destination_dir: Path,
        expected_repository_uuidv4: str,
    ) -> RestoreReceipt: ...


class SalvageMergePort(Protocol):
    def merge_salvage(
        self,
        fresh_destination_dir: Path,
        salvage_file: Path,
        budget: RecoveryBudget | None = None,
    ) -> MergeReceipt: ...


class ActivationPort(Protocol):
    def activate(
        self,
        fresh_catalog_dir: Path,
        target_locator_path: Path,
    ) -> ActivationReceipt: ...
