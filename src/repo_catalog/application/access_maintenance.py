"""Explicit Access-only maintenance; never restores local execution consent."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from repo_catalog.domain.access_backup import ScopeFork
from repo_catalog.domain.access_registry import AccessScope, ScopeLocatorRegistration
from repo_catalog.domain.ports.access_backup import AccessMaintenancePort


class AccessMaintenance:
    def __init__(
        self,
        store: AccessMaintenancePort,
        *,
        clock_us: Callable[[], int] = lambda: time.time_ns() // 1000,
    ):
        self.store = store
        self.clock_us = clock_us

    def backup(self, source: str | Path, destination: str | Path) -> dict:
        return self.store.backup(source, destination)

    def inspect(self, bundle: str | Path) -> dict:
        return self.store.inspect(bundle)

    def restore(self, bundle: str | Path, destination: str | Path) -> dict:
        return self.store.restore(bundle, destination)

    def fork_scope(
        self,
        source: str | Path,
        source_scope_uuidv4: str,
        locator_uri: str,
        *,
        display_name: str = "",
        target_scope_uuidv4: str | None = None,
    ) -> dict:
        # A new explicitly requested local registration, not an imported old timestamp.
        target = str(uuid4()) if target_scope_uuidv4 is None else target_scope_uuidv4
        request = ScopeFork(
            source_scope_uuidv4,
            AccessScope(target, display_name),
            ScopeLocatorRegistration(target, self.clock_us(), locator_uri),
        )
        return self.store.fork_scope(source, request)
