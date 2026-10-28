"""The opt-in Core factory does not load or require Context implementation."""

import subprocess
import sys

import pytest

from repo_catalog.adapters.sqlite import p1_schema

REPO = "00000000-0000-4000-8000-000000000001"
INSTANCE = "00000000-0000-4000-8000-000000000002"


def test_core_factory_without_context_import(tmp_path):
    script = """
import sqlite3
import builtins
import sys
real_import = builtins.__import__
def guarded(name, *args, **kwargs):
    names = [name] + [name + "." + item for item in (args[2] or () if len(args) > 2 else ())]
    if any(n.startswith("repo_catalog.") and any(
        part in n for part in ("context", "resource_identification", "parent_report")
    ) for n in names):
        raise AssertionError("Context implementation imported: " + name)
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded
from repo_catalog.adapters.sqlite import p1_schema as schema
path = sys.argv[1]
schema.initialize(path, "core", sys.argv[2], sys.argv[3])
db = schema.connect(path, "core")
assert not any(row[0].startswith("p1_transfer_") for row in db.execute("PRAGMA function_list"))
try:
    db.execute("UPDATE repositories SET repository_uuidv4=repository_uuidv4")
except sqlite3.IntegrityError:
    pass
else:
    raise AssertionError("Core immutability guard failed")
db.close()
"""
    subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "core.db"), REPO, INSTANCE],
        check=True,
    )


def test_context_factory_still_requires_context_functions(tmp_path):
    path = tmp_path / "context.db"
    p1_schema.initialize(path, "context", REPO, INSTANCE)
    db = p1_schema.connect(path, "context")
    try:
        db.create_function("p1_transfer_event_v1", 7, lambda *args: 1)
        with pytest.raises(p1_schema.SchemaError, match="p1_transfer_event_v1"):
            p1_schema.validate(db, "context")
    finally:
        db.close()


def test_core_validation_keeps_configuration_guards(tmp_path):
    path = tmp_path / "core.db"
    p1_schema.initialize(path, "core", REPO, INSTANCE)
    db = p1_schema.connect(path, "core")
    try:
        db.execute("PRAGMA foreign_keys=OFF")
        with pytest.raises(p1_schema.SchemaError, match="foreign_keys"):
            p1_schema.validate(db, "core")
    finally:
        db.close()


def test_core_validation_rejects_nondeterministic_constraint_function(tmp_path):
    path = tmp_path / "core.db"
    p1_schema.initialize(path, "core", REPO, INSTANCE)
    db = p1_schema.connect(path, "core")
    try:
        db.create_function("p1_native", 6, lambda *args: 1)
        with pytest.raises(p1_schema.SchemaError, match="p1_native"):
            p1_schema.validate(db, "core")
    finally:
        db.close()
