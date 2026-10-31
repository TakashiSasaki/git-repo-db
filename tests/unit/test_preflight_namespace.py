"""Workspace preflight confines every namespace owner before trusting the CLI."""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest

from scripts import preflight_access


def console_check(tmp_path, namespace_extra=None, version_extra=False):
    roots = [
        tmp_path / name / "repo_catalog"
        for name in ("src", "packages/core/src", "packages/contracts/src")
    ]
    for root in roots:
        root.mkdir(parents=True)
    version = ModuleType("repo_catalog._version")
    version.__file__ = str(
        (namespace_extra if version_extra else roots[-1]) / "_version.py"
    )
    version.__version__ = "0.2.0"
    namespace = ModuleType("repo_catalog")
    namespace.__path__ = list(map(str, roots))
    if namespace_extra is not None and not version_extra:
        namespace.__path__.append(str(namespace_extra))
    namespace._version = version
    console = tmp_path / "repo-catalog"
    console.write_text("#!" + sys.executable + "\n")
    with (
        patch.object(preflight_access, "ROOT", tmp_path),
        patch.object(preflight_access.shutil, "which", return_value=str(console)),
        patch.object(
            preflight_access.subprocess,
            "run",
            return_value=SimpleNamespace(stdout="0.2.0", stderr=""),
        ),
        patch.dict(
            sys.modules,
            {"repo_catalog": namespace, "repo_catalog._version": version},
        ),
    ):
        return preflight_access.check_console_script()


def test_exact_workspace_namespace_is_accepted(tmp_path):
    result = console_check(tmp_path)
    assert len(result["namespace_roots"]) == 3
    assert result["version"] == "0.2.0"


def test_foreign_namespace_root_is_refused_even_with_correct_version(tmp_path):
    with pytest.raises(SystemExit, match="namespace roots differ"):
        console_check(tmp_path, tmp_path / "foreign/repo_catalog")


def test_foreign_version_module_is_refused_even_with_correct_namespace(tmp_path):
    with pytest.raises(SystemExit, match="does not originate"):
        console_check(tmp_path, tmp_path / "foreign/repo_catalog", version_extra=True)
