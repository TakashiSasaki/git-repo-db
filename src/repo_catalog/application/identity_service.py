"""Explicit admission and inspection of identity-equivalence assertions."""

import json
from pathlib import Path

from repo_catalog.adapters.filesystem.locks import FileLock
from repo_catalog.adapters.sqlite.identity_relations import IdentityRelations
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.domain.models import CatalogError, Result


def identity_action(state_dir, action, input_path=None):
    path = Path(state_dir)
    if action == "status":
        with Store(path, readonly=True) as store, store.transaction(read=True):
            return Result(
                {
                    table: [dict(row) for row in store.all("SELECT * FROM " + table)]
                    for table in (
                        "identity_relations",
                        "identity_relation_cancellations",
                        "active_identity_relations",
                        "repository_equivalence_closure",
                        "service_equivalence_closure",
                        "identity_relation_staging",
                    )
                },
                catalog=store.revision(),
            )
    try:
        record = json.loads(Path(input_path).read_text())
    except (ValueError, UnicodeError) as exc:
        raise CatalogError(
            "INVALID_ARGUMENT", "Identity assertion must be a JSON object"
        ) from exc
    if not isinstance(record, dict):
        raise CatalogError(
            "INVALID_ARGUMENT", "Identity assertion must be a JSON object"
        )
    with FileLock(path / "locks/writer.lock"), Store(path) as store:
        with store.transaction():
            state = IdentityRelations(store.connection).admit(action, record)
            response = Result(
                {"state": state},
                status="partial" if state in ("staged", "conflict") else "complete",
                catalog=store.revision(),
            )
            if response.status == "partial":
                response.coverage.add("identity", state)
            return response
