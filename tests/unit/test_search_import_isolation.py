"""Search storage and selected projectors do not load unrelated authorities."""

import subprocess
import sys

import pytest


def _run_without_imports(code, forbidden, path):
    guard = """
import importlib.abc
import sys

class AbsentModules(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + ".") for name in forbidden):
            raise AssertionError("Unavailable authority imported: " + fullname)

sys.meta_path.insert(0, AbsentModules())
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "forbidden = " + repr(forbidden) + "\n" + guard + code,
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_search_storage_works_without_core_context_or_paired_imports(tmp_path):
    _run_without_imports(
        """
from pathlib import Path
import sqlite3

from repo_catalog.adapters.sqlite.production_search import ProductionSearchAdapter
from repo_catalog.domain.query_contracts import SnapshotFenceToken, canonical_json
from repo_catalog.domain.search_query import SearchQuery

directory = Path(sys.argv[1])
adapter = ProductionSearchAdapter(directory)
token = SnapshotFenceToken(
    "core_only", "00000000-0000-4000-8000-000000000001",
    "00000000-0000-4000-8000-000000000002", "1" * 64,
).encode()
key = canonical_json(["scalar", "test"])
request = SearchQuery("needle", projection_kinds=("git_metadata",))
assert adapter.query_candidates("git_metadata", token, request.query_text) is None
assert not list(directory.iterdir())
assert adapter.replace_projection("git_metadata", token, {key: "needle"}) == 1
assert adapter.query_candidates("git_metadata", token, "needle", 1) == {key: "needle"}
assert adapter.query_candidates("git_metadata", token, "needle", 2) is None
with sqlite3.connect(adapter.path) as db:
    db.execute("DELETE FROM search_documents")
assert adapter.query_candidates("git_metadata", token, "needle", 1) is None
assert not (directory / "p1-recovery-stop.json").exists()
assert not any((directory / name).exists() for name in (
    "core.sqlite3", "context.sqlite3", "operational.sqlite3", "access.sqlite3"
))
""",
        (
            "repo_catalog.adapters.sqlite.git_core",
            "repo_catalog.adapters.sqlite.p1_core",
            "repo_catalog.adapters.sqlite.core_coordination",
            "repo_catalog.adapters.sqlite.p1_context",
            "repo_catalog.adapters.sqlite.production_context",
            "repo_catalog.adapters.sqlite.p1_coordination",
            "repo_catalog.domain.p1_core",
            "repo_catalog.domain.p1_context",
            "repo_catalog.domain.core_query",
            "repo_catalog.domain.context_query",
            "repo_catalog.domain.production_query",
        ),
        tmp_path,
    )


@pytest.mark.parametrize(
    ("module", "forbidden"),
    [
        (
            "repo_catalog.adapters.sqlite.search_core",
            (
                "repo_catalog.adapters.sqlite.p1_context",
                "repo_catalog.adapters.sqlite.production_context",
                "repo_catalog.adapters.sqlite.p1_coordination",
                "repo_catalog.domain.p1_context",
                "repo_catalog.domain.context_query",
            ),
        ),
        (
            "repo_catalog.adapters.sqlite.search_context",
            (
                "repo_catalog.adapters.sqlite.git_core",
                "repo_catalog.adapters.sqlite.p1_core",
                "repo_catalog.adapters.sqlite.core_coordination",
                "repo_catalog.adapters.sqlite.p1_coordination",
                "repo_catalog.domain.p1_core",
                "repo_catalog.domain.core_query",
            ),
        ),
    ],
)
def test_projector_loads_only_its_selected_authority(module, forbidden, tmp_path):
    _run_without_imports(
        "import importlib\nimportlib.import_module(" + repr(module) + ")\n",
        forbidden,
        tmp_path,
    )
