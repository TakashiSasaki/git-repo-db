"""Explicit test-only CPython extension load, including standalone Python builds.

Some Python distributions have a built-in _sqlite3, which sys.path cannot shadow.
Load the prepared extension explicitly BEFORE importing sqlite3.
"""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path


def activate():
    if "sqlite3" in sys.modules or "_sqlite3" in sys.modules:
        raise RuntimeError("Minimum SQLite must be activated before sqlite3 import")
    root = Path(__file__).resolve().parents[1] / "artifacts/sqlite-min"
    (library,) = (root / "cpython").glob("_sqlite3*.so")
    manifest = json.loads((root / "manifest.json").read_bytes())
    if hashlib.sha256(library.read_bytes()).hexdigest() != manifest["extension_sha256"]:
        raise RuntimeError("Prepared minimum SQLite extension SHA mismatch")
    spec = importlib.util.spec_from_file_location("_sqlite3", library)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["_sqlite3"] = module
    import sqlite3

    assert sqlite3.sqlite_version == "3.46.1", sqlite3.sqlite_version
