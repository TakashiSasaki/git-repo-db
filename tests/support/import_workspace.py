"""Explicit scratch setup for isolated importer tests; never ordinary init."""

import re
import sqlite3
from contextlib import contextmanager

from repo_catalog.adapters.import_v2 import workspace


def memory_workspace(db):
    db.execute("ATTACH DATABASE ':memory:' AS import_workspace")
    # Recipe-only tests have no catalog identity and do not run finalization.
    db.executescript(
        re.sub(
            r"\bCREATE (TABLE|TRIGGER|INDEX) (\w+)",
            r"CREATE \1 import_workspace.\2",
            workspace.schema_sql(),
        )
    )


def create_workspace(store):
    path = workspace.path_for(store.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=False)
    workspace.attach(store.connection, store.db_path, creating=True)
    with store.transaction():
        workspace.initialize(store.connection)
    return path


@contextmanager
def inspect_import(state):
    db = sqlite3.connect(state / "catalog.sqlite3", uri=True, isolation_level=None)
    try:
        workspace.attach(db, state / "catalog.sqlite3")
        yield db
    finally:
        db.close()
