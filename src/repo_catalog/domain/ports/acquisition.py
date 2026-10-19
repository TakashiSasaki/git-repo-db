"""Typed Protocol ports for P5 Git acquisition, Provider intake, Operational ledger, and Exchange."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.domain.acquisition import (
    GitAcquisitionReport,
    GitMetadataInput,
    GitNativeAcquisitionRequest,
    ProviderAcquisitionReport,
    ProviderIntakeBatch,
)
from repo_catalog.domain.exchange import (
    ExchangeImportReport,
    ExchangePackage,
    ExchangeSelectionScope,
)
from repo_catalog.domain.p1_coordination import RequestIdentity
from repo_catalog.domain.ports.p1_core import WorkBudget


class GitAcquisitionPort(Protocol):
    """Port for metadata-first Git acquisition and Notes delegation."""

    def acquire_from_native(
        self,
        source: GitNativeSource,
        request: GitNativeAcquisitionRequest,
        *,
        work: WorkBudget | None = None,
    ) -> GitAcquisitionReport: ...

    def acquire_metadata_only(
        self,
        unit: GitMetadataInput,
        *,
        work: WorkBudget | None = None,
    ) -> GitAcquisitionReport: ...


class ProviderAcquisitionPort(Protocol):
    """Port for Provider (GitHub) normalized intake into Context."""

    def admit_batch(
        self,
        batch: ProviderIntakeBatch,
    ) -> ProviderAcquisitionReport: ...


class OperationalLedgerPort(Protocol):
    """Port for non-authoritative Operational retry, continuation, and Exchange receipt state."""

    def record_retry_state(
        self,
        scope_key: object,
        *,
        not_before_us: int,
        reason: str,
        attempt_count: int = 1,
        state: dict[str, Any] | None = None,
        request: RequestIdentity | None = None,
    ) -> dict[str, Any]: ...

    def get_retry_state(
        self,
        scope_key: object,
        *,
        request: RequestIdentity | None = None,
    ) -> dict[str, Any] | None: ...

    def clear_retry_state(
        self,
        scope_key: object,
        *,
        request: RequestIdentity | None = None,
    ) -> bool: ...

    def record_cache_locator(
        self,
        cache_key: object,
        locator: str,
        *,
        cache_purpose: str = "metadata",
        observed_at_us: int | None = None,
        repository_uuidv4: str | None = None,
    ) -> None: ...

    def get_cache_locator(
        self,
        cache_key: object,
        *,
        cache_purpose: str = "metadata",
        repository_uuidv4: str | None = None,
    ) -> dict[str, Any] | None: ...

    def record_exchange_receipt(
        self,
        package_id: str,
        package_digest_sha256: str,
        sender_catalog_instance_uuidv4: str,
        report: dict[str, Any],
        *,
        observed_at_us: int = 0,
    ) -> None: ...

    def get_exchange_receipt(
        self,
        package_id: str,
        package_digest_sha256: str,
    ) -> dict[str, Any] | None: ...


class ExchangePort(Protocol):
    """Port for deterministic Exchange package export and receiver-verified import."""

    def export_package(
        self,
        *,
        selection: ExchangeSelectionScope | None = None,
        package_id: str | None = None,
        exported_at_us: int | None = None,
    ) -> ExchangePackage: ...

    def import_package(
        self,
        raw_package: ExchangePackage | str | bytes | dict[str, Any],
        *,
        work: WorkBudget | None = None,
        request: RequestIdentity | None = None,
        new_request: bool = False,
        permitted_repository_uuidv4s: tuple[str, ...] = (),
        selection: ExchangeSelectionScope | None = None,
        cut: Callable[[str], None] = lambda point: None,
    ) -> ExchangeImportReport: ...
