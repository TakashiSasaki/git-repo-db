"""Rich Query composition, retaining existing paired and Search entry points."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

from repo_catalog.adapters.sqlite.catalog_runtime import SnapshotReadLimits
from repo_catalog.application.paired_query import (
    PinnedCatalogSnapshot as PinnedCatalogSnapshot,
)
from repo_catalog.application.paired_search import PairedSearchService
from repo_catalog.domain.query_contracts import CatalogReadMode

if TYPE_CHECKING:
    from repo_catalog.domain.p1_context import MappingOperationEvidence


class ProductionQueryService(PairedSearchService):
    def __init__(
        self,
        directory: Path | str,
        *,
        mode: CatalogReadMode | Literal["auto"] = "auto",
        read_limits: SnapshotReadLimits = SnapshotReadLimits(),
        mapping_evidence: MappingOperationEvidence | None = None,
    ):
        super().__init__(
            directory,
            mode=mode,
            read_limits=read_limits,
            mapping_evidence=mapping_evidence,
        )
