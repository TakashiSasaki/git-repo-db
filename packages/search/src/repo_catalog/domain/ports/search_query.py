"""Optional derivative Search port, separate from basic authority Query."""

from __future__ import annotations

from typing import Protocol


class SearchIndexPort(Protocol):
    """Port for disposable derivative Search projection storage and candidate lookup."""

    def replace_projection(
        self,
        projection_kind: str,
        snapshot_token: str,
        documents: dict[str, str],
        *,
        repository_uuidv4: str,
        catalog_instance_uuidv4: str,
    ) -> int: ...

    def query_candidates(
        self,
        projection_kind: str,
        snapshot_token: str,
        query_text: str,
        expected_doc_count: int | None = None,
    ) -> dict[str, str] | None: ...
