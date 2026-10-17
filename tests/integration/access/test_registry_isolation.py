"""Ensure the opt-in registry cannot become a hidden normal-runtime dependency."""

import ast
from pathlib import Path

from scripts.audit_callsite_dependencies import (
    ISOLATED_TARGET_MODULES,
    is_baseline_source,
    isolated_runtime_imports,
)

ROOT = Path(__file__).resolve().parents[3]
OWNED = {
    "src/repo_catalog/domain/access_registry.py",
    "src/repo_catalog/domain/access_connections.py",
    "src/repo_catalog/domain/ports/access_connections.py",
    "src/repo_catalog/adapters/sqlite/access_connections.py",
    "src/repo_catalog/domain/ports/access_registry.py",
    "src/repo_catalog/adapters/sqlite/access_schema.py",
    "src/repo_catalog/adapters/sqlite/access_registry.py",
}


def test_explicit_isolated_ownership_is_not_a_prefix_escape():
    assert OWNED <= ISOLATED_TARGET_MODULES
    assert is_baseline_source(ROOT / "src/repo_catalog/application/access_future.py")
    for source in (
        "from repo_catalog.adapters.sqlite import access_registry",
        "from . import access_registry",
    ):
        assert isolated_runtime_imports(source, "repo_catalog.adapters.sqlite") == {
            "repo_catalog.adapters.sqlite.access_registry"
        }


def test_normal_runtime_has_no_access_import():
    for path in (ROOT / "src/repo_catalog").rglob("*.py"):
        if is_baseline_source(path):
            package = ".".join(path.relative_to(ROOT / "src").parts[:-1])
            imported = isolated_runtime_imports(path.read_text(), package)
            assert not imported, (str(path), imported)


def test_access_domain_does_not_import_adapters():
    for relative in sorted(OWNED):
        if "/domain/" not in relative:
            continue
        tree = ast.parse((ROOT / relative).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert ".adapters" not in (node.module or "")
            elif isinstance(node, ast.Import):
                assert all(".adapters" not in item.name for item in node.names)
