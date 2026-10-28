"""Real Core query entry points with Context and Search implementations absent."""

import json
import subprocess
import sys

import pytest

from repo_catalog.adapters.sqlite.p1_coordination import persist_catalog_stop
from repo_catalog.application.production_query import ProductionQueryService
from tests.integration.p6.conftest import REPOSITORY, populate_rich_catalog

GUARD = """
import importlib.abc
import sys
class BlockOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith("repo_catalog.") and any(
            part in fullname for part in ("context", "search", "resource_identification", "parent_report")
        ):
            raise AssertionError("optional implementation imported: " + fullname)
        return None
sys.meta_path.insert(0, BlockOptional())
"""


def run_guarded(script, *args):
    result = subprocess.run(
        [sys.executable, "-c", GUARD + script, *map(str, args)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result


@pytest.mark.parametrize("coexisting", [False, True])
def test_explicit_core_query_without_optional_imports(tmp_path, coexisting):
    catalog = tmp_path / "catalog"
    fixture = populate_rich_catalog(catalog, include_context=coexisting)
    if not coexisting:
        (catalog / "operational.sqlite3").unlink()
        (catalog / "search.sqlite3").unlink()
    result = run_guarded(
        """
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.p1_core import OID
from repo_catalog.domain.production_query import PageRequest
service = ProductionQueryService(sys.argv[1], mode="core_only")
assert service.detect_mode() == "core_only"
assert service.get_repository_view().repository_uuidv4 == sys.argv[2]
assert service.get_git_object(OID("sha1", sys.argv[3]), include_bytes=True).retained_bytes.verified
first = service.list_git_objects(PageRequest(limit=1))
assert first.items and first.next_cursor
assert service.list_git_objects(PageRequest(limit=1, cursor=first.next_cursor)).items
assert service.list_notes_captures().total_count == 1
assert service.snapshot_token().context_sha256 is None
if sys.argv[4] == "absent":
    assert ProductionQueryService(sys.argv[1]).snapshot_token().mode == "core_only"
""",
        catalog,
        REPOSITORY,
        fixture["commit_obj"].oid.full_oid,
        "present" if coexisting else "absent",
    )
    assert result.stderr == ""
    if coexisting:
        assert ProductionQueryService(catalog).detect_mode() == "paired"
        assert ProductionQueryService(catalog).snapshot_token().mode == "paired"
    else:
        assert not (catalog / "context.sqlite3").exists()
        assert not (catalog / "search.sqlite3").exists()
        assert not (catalog / "operational.sqlite3").exists()


@pytest.mark.parametrize("coexisting", [False, True])
def test_cli_core_entry_and_persistent_stop_without_optional_imports(
    tmp_path, coexisting
):
    catalog = tmp_path / "catalog"
    populate_rich_catalog(catalog, include_context=coexisting)
    if not coexisting:
        (catalog / "search.sqlite3").unlink()
        (catalog / "operational.sqlite3").unlink()
    script = """
import runpy
sys.argv = ["production_query", "git-objects", "--catalog", sys.argv[1], "--mode", "core_only", "--limit", "1"]
runpy.run_module("repo_catalog.cli.production_query", run_name="__main__")
"""
    assert json.loads(run_guarded(script, catalog).stdout)["total_count"] > 0
    persist_catalog_stop(catalog, "known Context corruption")
    stopped = subprocess.run(
        [sys.executable, "-c", GUARD + script, str(catalog)],
        capture_output=True,
        text=True,
    )
    assert stopped.returncode == 2
    assert json.loads(stopped.stderr)["code"] == "RECOVERY_STOP"


def test_core_snapshot_rechecks_stop_during_operation(tmp_path):
    catalog = tmp_path / "catalog"
    populate_rich_catalog(catalog, include_context=False)
    run_guarded(
        """
from pathlib import Path
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.adapters.sqlite.p1_coordination import persist_catalog_stop
from repo_catalog.domain.p1_core import CoreFailure
service = ProductionQueryService(sys.argv[1], mode="core_only")
try:
    with service.open_snapshot():
        persist_catalog_stop(Path(sys.argv[1]), "detected authoritative corruption")
except CoreFailure as error:
    assert error.code == "RECOVERY_STOP"
else:
    raise AssertionError("completion ignored persistent stop")
""",
        catalog,
    )
