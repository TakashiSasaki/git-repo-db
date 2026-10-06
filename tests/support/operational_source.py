"""Synthetic operational v2 fixtures prepared outside the converter guard."""

import copy
from pathlib import Path

from repo_catalog.adapters.sqlite import index
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.config import DEFAULTS, serialize
from repo_catalog.domain.models import CatalogError

STAMP = "2026-01-01T00:00:00Z"


class PartialIndex:
    """Cancel the actual rebuild after its first committed 200-document batch."""

    def __init__(self):
        self.calls = 0

    def check(self):
        self.calls += 1
        if self.calls == 3:
            raise CatalogError("CANCELLED", "Synthetic fixture checkpoint")


def add_operational_indexes(
    database, *, kinds=("code",), analyze=False, documents=3, partial=False
):
    """Add real app-generated FTS, including to the malformed P2 fixture.

    Replaces only synthetic search/index fixture rows before generating new
    ones; all other acquisition facts and deliberately invalid values remain.
    """
    database = Path(database)
    config = copy.deepcopy(DEFAULTS)
    config["database"]["filename"] = database.name
    config["cache"].update(max_bytes=67108864, min_free_bytes=0)
    (database.parent / "catalog.toml").write_text(serialize(config))
    with Store(database.parent) as store:
        with store.transaction():
            store.execute("DELETE FROM index_membership")
            store.execute("DELETE FROM index_generations")
            store.execute("DELETE FROM search_documents")
            for kind in ("code", "pr", "commits"):
                for number in range(documents):
                    store.execute(
                        "INSERT INTO search_documents(kind,source_key,body,metadata) VALUES(?,?,?,?)",
                        (
                            kind,
                            f"synthetic-{kind}-{number}",
                            f"Original Abc {kind} {number} 日本語",
                            "{}",
                        ),
                    )
        for kind in kinds:
            try:
                index.rebuild(store, kind, token=PartialIndex() if partial else None)
            except CatalogError as exc:
                if not partial or exc.code != "CANCELLED":
                    raise
        with store.transaction():
            store.execute("UPDATE index_generations SET created_at=?", (STAMP,))
        if analyze:
            store.execute("ANALYZE")


def make_operational_source(
    state_dir, *, kinds=(), analyze=False, documents=3, partial=False
):
    state_dir = Path(state_dir)
    MaintenanceService(state_dir).init("catalog-text-v1", 67108864, 0)
    database = state_dir / "catalog.sqlite3"
    with Store(state_dir) as store:
        with store.transaction():
            store.execute(
                "UPDATE catalog_meta SET db_instance_id='00000000-0000-4000-8000-000000000003'"
            )
            store.execute("UPDATE schema_migrations SET applied_at=?", (STAMP,))
    add_operational_indexes(
        database, kinds=kinds, analyze=analyze, documents=documents, partial=partial
    )
    cache = state_dir / "cache"
    (cache / "synthetic-evidence").write_bytes(b"synthetic-cache-original")
    return database, cache
