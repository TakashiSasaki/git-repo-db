"""Current Access ownership and domain layering, without opt-in exclusions."""

import ast
from pathlib import Path

from scripts.audit_callsite_dependencies import (
    owned_source,
    source_files,
    source_owner,
)

ROOT = Path(__file__).resolve().parents[3]
OWNED = {
    owned_source(relative)
    for relative in (
        "domain/access_backup.py",
        "domain/ports/access_backup.py",
        "adapters/sqlite/access_backup.py",
        "application/access_maintenance.py",
        "cli/access_maintenance.py",
        "domain/native_acquisition.py",
        "adapters/git/access_native.py",
        "application/access_acquisition.py",
        "cli/access_acquisition.py",
        "domain/access_registry.py",
        "domain/access_connections.py",
        "domain/access_workflow.py",
        "domain/ports/access_workflow.py",
        "application/access_workflow.py",
        "adapters/filesystem/access_executor.py",
        "cli/access_workflow.py",
        "domain/ports/access_connections.py",
        "adapters/sqlite/access_connections.py",
        "domain/ports/access_registry.py",
        "adapters/sqlite/access_schema.py",
        "adapters/sqlite/access_registry.py",
    )
}


def test_explicit_access_source_ownership():
    for relative in OWNED:
        path = ROOT / relative
        assert path.is_file()
        owner = source_owner(path)
        assert owner == (
            "repo-catalog-git-acquisition"
            if "/git-acquisition/" in relative
            else "repo-catalog-access"
        )


def test_access_sources_are_not_excluded_from_current_audit():
    indexed = {path.relative_to(ROOT).as_posix() for path in source_files()}
    assert OWNED <= indexed


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
