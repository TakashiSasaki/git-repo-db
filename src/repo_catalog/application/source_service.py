"""Explicit local configuration of a portable Source registration."""

import json
from pathlib import Path

from repo_catalog.adapters.filesystem.locks import FileLock
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application import repository_identity as identity
from repo_catalog.application.job_plans import reject_secrets
from repo_catalog.domain.models import CatalogError, Result


def configure_source(state_dir, selector, input_path):
    try:
        settings = json.loads(Path(input_path).read_text())
    except (ValueError, UnicodeError) as exc:
        raise CatalogError(
            "INVALID_ARGUMENT", "Source settings must be a JSON object"
        ) from exc
    if not isinstance(settings, dict):
        raise CatalogError("INVALID_ARGUMENT", "Source settings must be a JSON object")
    reject_secrets(settings)
    path = Path(state_dir)
    with FileLock(path / "locks/writer.lock"), Store(path) as store:
        with store.transaction():
            source = dict(identity.source(store, selector))
            source["settings"] = json.dumps(settings, sort_keys=True, allow_nan=False)
            identity.source_settings(source)
            if source["discovery_kind"] == "manual_git":
                settings["url"] = identity.git_url(settings["url"])
                source["settings"] = json.dumps(
                    settings, sort_keys=True, allow_nan=False
                )
            if source["discovery_kind"] == "github_inventory":
                reject_secrets(identity.github_config(store, source))
            store.execute(
                "UPDATE sources SET settings=? WHERE source_id=?",
                (source["settings"], source["source_id"]),
            )
            store.publish()
            return Result(
                {
                    "source_id": source["source_id"],
                    "source_registration_uuidv4": source["source_registration_uuidv4"],
                    "configured": True,
                },
                catalog=store.revision(),
            )
