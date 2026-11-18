"""Explicit-role initialization, validating existing authorities before any create."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from repo_catalog.adapters.sqlite import p1_schema

ROLES = {
    "repository": ("repository",),
    "context": ("context",),
    "paired": ("repository", "context"),
    "operational": ("operational",),
    "search": ("search",),
}


def inspect_role(path, role):
    if sqlite3.sqlite_version_info < p1_schema.MIN_SQLITE:
        raise p1_schema.SchemaError(
            "SQLite runtime is below the supported WAL safety floor"
        )
    p1_schema.verify_declared(role)
    with closing(
        sqlite3.connect(
            Path(path).resolve().as_uri() + "?mode=ro", uri=True, isolation_level=None
        )
    ) as db:
        db.row_factory = sqlite3.Row
        p1_schema.register_functions(db, role)
        p1_schema.configure(db, role)
        db.execute("BEGIN")
        p1_schema.validate(db, role)
        if any(tuple(row) != ("ok",) for row in db.execute("PRAGMA quick_check")):
            raise p1_schema.SchemaError("database integrity check failed")
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise p1_schema.SchemaError("database foreign key check failed")
        return tuple(
            db.execute(
                "SELECT repository_uuidv4,catalog_instance_uuidv4 FROM store_identity"
            ).fetchone()
        )


def initialize(directory, scope, *, repository=None, instance=None):
    directory = Path(directory)
    roles = ROLES[scope]
    p1_schema.reject_legacy_layout(directory)
    identities = []
    for role in dict.fromkeys((*roles, "repository", "context")):
        path = directory / (role + ".sqlite3")
        if path.exists():
            identities.append(inspect_role(path, role))
    if identities and any(value != identities[0] for value in identities):
        raise ValueError("PAIR_IDENTITY: existing roles belong to different catalogs")
    if identities:
        actual_repo, actual_instance = identities[0]
        if (repository is not None and repository != actual_repo) or (
            instance is not None and instance != actual_instance
        ):
            raise ValueError(
                "STORE_IDENTITY: supplied identity differs from existing roles"
            )
        repository, instance = identities[0]
    else:
        repository, instance = repository or str(uuid4()), instance or str(uuid4())
    if not p1_schema.uuid4(repository) or not p1_schema.uuid4(instance):
        raise ValueError("canonical UUIDv4 identities required")
    if (directory / "p1-recovery-stop.json").exists():
        raise ValueError("RECOVERY_REQUIRED")
    directory.mkdir(parents=True, exist_ok=True)
    created, reused = [], []
    for role in roles:
        path = directory / (role + ".sqlite3")
        if path.exists():
            reused.append(role)
        else:
            p1_schema.initialize(path, role, repository, instance)
            created.append(role)
    return {
        "created": created,
        "reused": reused,
        "repository_uuidv4": repository,
        "catalog_instance_uuidv4": instance,
    }
