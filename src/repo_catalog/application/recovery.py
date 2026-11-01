"""Explicit paired Recovery composition over the Core lifecycle."""

from repo_catalog.adapters.sqlite.recovery import SQLiteRecoveryAdapter
from repo_catalog.application.core_recovery import CoreRecoveryService


class RecoveryService(CoreRecoveryService):
    """Core and Context Recovery; paired backup remains the default."""

    def __init__(self, adapter: SQLiteRecoveryAdapter | None = None) -> None:
        super().__init__(adapter or SQLiteRecoveryAdapter())
