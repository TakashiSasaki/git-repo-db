# Legacy-only assertions below cover deferred physical diagnostics, not public API compatibility.
"""Real Repository query entry points with Context and Search implementations absent."""

import json
import subprocess
import sys

import pytest

from repo_catalog.adapters.sqlite.repository_coordination import persist_catalog_stop
from repo_catalog.application.production_query import ProductionQueryService
from tests.integration.p6.conftest import REPOSITORY, populate_rich_catalog

GUARD = """
import importlib.abc
import sys
class BlockOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        # Model uninstalled optional feature entry points. The real CLI catches
        # only exact missing-module errors and falls back to its Repository owner.
        if fullname in (
            "repo_catalog.cli.query_features",
            "repo_catalog.cli.search_query_features",
            "repo_catalog.cli.paired_query_features",
            "repo_catalog.cli.context_query_features",
        ):
            raise ModuleNotFoundError("optional feature absent", name=fullname)
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
def test_explicit_repository_query_without_optional_imports(tmp_path, coexisting):
    catalog = tmp_path / "catalog"
    fixture = populate_rich_catalog(catalog, include_context=coexisting)
    if not coexisting:
        (catalog / "operational.sqlite3").unlink()
        (catalog / "search.sqlite3").unlink()
    result = run_guarded(
        """
from repo_catalog.application.repository_query import RepositoryQueryService
from repo_catalog.domain.p1_repository import OID
from repo_catalog.domain.query_contracts import PageRequest
service = RepositoryQueryService(sys.argv[1], mode="repository_only")
assert service.detect_mode() == "repository_only"
assert service.get_repository_view().repository_uuidv4 == sys.argv[2]
assert service.get_git_object(OID("sha1", sys.argv[3]), include_bytes=True).retained_bytes.verified
first = service.list_git_objects(PageRequest(limit=1))
assert first.items and first.next_cursor
assert service.list_git_objects(PageRequest(limit=1, cursor=first.next_cursor)).items
assert service.list_ref_observations().items
assert service.snapshot_token().context_sha256 is None
if sys.argv[4] == "absent":
    assert RepositoryQueryService(sys.argv[1]).snapshot_token().mode == "repository_only"
""",
        catalog,
        REPOSITORY,
        fixture["commit_obj"].object_oid.object_oid,
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
def test_cli_repository_entry_and_persistent_stop_without_optional_imports(
    tmp_path, coexisting
):
    catalog = tmp_path / "catalog"
    populate_rich_catalog(catalog, include_context=coexisting)
    if not coexisting:
        (catalog / "search.sqlite3").unlink()
        (catalog / "operational.sqlite3").unlink()
    script = """
import runpy
sys.argv = ["production_query", "git-objects", "--catalog", sys.argv[1], "--mode", "repository_only", "--limit", "1"]
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


def test_repository_snapshot_rechecks_stop_during_operation(tmp_path):
    catalog = tmp_path / "catalog"
    populate_rich_catalog(catalog, include_context=False)
    run_guarded(
        """
from pathlib import Path
from repo_catalog.application.repository_query import RepositoryQueryService
from repo_catalog.adapters.sqlite.repository_coordination import persist_catalog_stop
from repo_catalog.domain.p1_repository import RepositoryFailure
service = RepositoryQueryService(sys.argv[1], mode="repository_only")
try:
    with service.open_snapshot():
        persist_catalog_stop(Path(sys.argv[1]), "detected authoritative corruption")
except RepositoryFailure as error:
    assert error.code == "RECOVERY_STOP"
else:
    raise AssertionError("completion ignored persistent stop")
""",
        catalog,
    )


def test_explicit_repository_ignores_coexisting_identity_while_auto_requires_pair(
    tmp_path,
):
    from uuid import uuid4

    from repo_catalog.adapters.sqlite.p1_schema import initialize
    from repo_catalog.domain.p1_coordination import CoordinationError

    catalog = tmp_path / "catalog"
    populate_rich_catalog(catalog, include_context=False)
    initialize(catalog / "context.sqlite3", "context", REPOSITORY, str(uuid4()))
    run_guarded(
        """
from repo_catalog.application.repository_query import RepositoryQueryService
service = RepositoryQueryService(sys.argv[1], mode="repository_only")
assert service.get_repository_view().repository_uuidv4 == sys.argv[2]
""",
        catalog,
        REPOSITORY,
    )
    with pytest.raises(CoordinationError, match="PAIR_IDENTITY"):
        ProductionQueryService(catalog).snapshot_token()
