"""Build disposable v2 sources without involving the catalog3 runtime."""

import copy
import hashlib
import sqlite3
from importlib.resources import files
from pathlib import Path

from repo_catalog.config import DEFAULTS, serialize

STAMP = "2026-01-01T00:00:00Z"


def initialize(state_dir):
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    config = copy.deepcopy(DEFAULTS)
    config["cache"].update(max_bytes=67108864, min_free_bytes=0)
    (state_dir / "catalog.toml").write_text(serialize(config))
    cache = state_dir / "cache"
    cache.mkdir(exist_ok=True)
    path = state_dir / "catalog.sqlite3"
    with sqlite3.connect(path) as db:
        for version, sql in enumerate(
            sorted(
                files("repo_catalog")
                .joinpath("resources/import_v2/migrations")
                .iterdir(),
                key=lambda r: r.name,
            ),
            1,
        ):
            db.executescript(sql.read_text())
            db.execute(
                "INSERT INTO schema_migrations VALUES(?,?,?)",
                (version, hashlib.sha256(sql.read_bytes()).hexdigest(), STAMP),
            )
            db.commit()
        db.execute(
            "INSERT INTO catalog_meta VALUES(1,?,0,2)",
            ("00000000-0000-4000-8000-000000000003",),
        )
    return path, cache
