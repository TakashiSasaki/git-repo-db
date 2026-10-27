"""Check the live runtime facts to which the documentation entrypoints point."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from repo_catalog.adapters.sqlite.p1_schema import STORES
from repo_catalog.adapters.sqlite.schema import (
    OPERATIONAL_SCHEMA_VERSION,
    SCHEMA_VERSION,
    SEARCH_SCHEMA_VERSION,
)
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.cli.main import main as cli_main
from repo_catalog.domain.models import CatalogError

ROOT = Path(__file__).resolve().parents[2]


def test_runtime_entrypoints_and_disposable_initialization(tmp_path):
    assert (SCHEMA_VERSION, OPERATIONAL_SCHEMA_VERSION, SEARCH_SCHEMA_VERSION) == (
        21,
        1,
        1,
    )
    assert STORES == ("core", "context", "operational", "search")
    for path in (
        "docs/cli.md",
        "docs/data-model.md",
        "docs/implementation-status.md",
        "docs/model-integration-status.md",
        "README.md",
    ):
        assert "current-runtime-reference.md" in (ROOT / path).read_text()
    state = tmp_path / "catalog"
    assert (
        cli_main(
            [
                "--state-dir",
                str(state),
                "--format",
                "json",
                "init",
                "--profile",
                "catalog-text-v1",
                "--cache-max-bytes",
                str(64 * 1024 * 1024),
                "--min-free-bytes",
                "0",
            ]
        )
        == 0
    )
    assert sorted(p.name for p in state.glob("*.sqlite3")) == ["catalog.sqlite3"]
    with Store(state) as store:
        with pytest.raises(CatalogError):
            store.open_search(create=False)
        assert not (state / "search.sqlite3").exists()
        assert not (state / "operational.sqlite3").exists()
        assert store.operational is not None
        assert (state / "operational.sqlite3").is_file()
    assert (ROOT / "src/repo_catalog/cli/access_workflow.py").is_file()
    assert (ROOT / "src/repo_catalog/cli/access_acquisition.py").is_file()


@pytest.mark.parametrize(
    ("module", "expected"),
    [
        ("repo_catalog.cli.main", False),
        ("repo_catalog.cli.access_workflow", True),
        ("repo_catalog.cli.access_acquisition", True),
    ],
)
def test_cli_import_boundary_in_fresh_process(module, expected):
    source = (
        "import importlib, sys; importlib.import_module(sys.argv[1]); "
        "print('repo_catalog.adapters.sqlite.access_schema' in sys.modules)"
    )
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    result = subprocess.run(
        [sys.executable, "-c", source, module],
        cwd=ROOT,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    assert result.stdout.strip() == str(expected)
