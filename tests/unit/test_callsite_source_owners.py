"""Keep namespace ownership auditable without hiding newly added source files."""

import hashlib

import pytest

from scripts import audit_callsite_dependencies as audit


def test_index_covers_every_python_owner_and_packaged_resource():
    report = audit.build()
    modules = report["modules"]
    assert {entry["path"] for entry in modules if entry["path"].endswith(".py")} == {
        path.relative_to(audit.ROOT).as_posix() for path in audit.source_files()
    }
    assert set(report["source_roots"].values()) == {
        "repo-catalog",
        "repo-catalog-core",
        "repo-catalog-contracts",
        "repo-catalog-runtime",
        "repo-catalog-context",
        "repo-catalog-access",
        "repo-catalog-paired-query",
        "repo-catalog-search",
        "repo-catalog-operational",
        "repo-catalog-git-acquisition",
        "repo-catalog-exchange",
        "repo-catalog-paired-recovery",
        "repo-catalog-filesystem",
        "repo-catalog-worktrees",
        "repo-catalog-local",
    }
    baseline = {entry["path"]: entry for entry in report["modules"]}
    assert (
        baseline["packages/contracts/src/repo_catalog/domain/time.py"]["owner"]
        == "repo-catalog-contracts"
    )
    core = baseline["packages/core/src/repo_catalog/adapters/sqlite/git_core.py"]
    assert core["owner"] == "repo-catalog-core"
    assert (
        core["sha256"]
        == hashlib.sha256((audit.ROOT / core["path"]).read_bytes()).hexdigest()
    )
    for package, module in (
        ("filesystem", "store"),
        ("worktrees", "catalog"),
        ("local", "service"),
    ):
        path = f"packages/{package}/src/repo_catalog/{package}/{module}.py"
        assert baseline[path]["owner"] == f"repo-catalog-{package}"
    assert core["functions"]
    assert {entry["path"] for entry in report["packaged_resources"]} == {
        path.relative_to(audit.ROOT).as_posix()
        for path in audit.source_files((".sql", ".json", ".graphql"))
    }


@pytest.mark.parametrize("suffix", [".py", ".sql"])
def test_duplicate_installed_path_ownership_is_refused(tmp_path, suffix):
    roots = (tmp_path / "first/src", tmp_path / "second/src")
    for source in roots:
        path = source / "repo_catalog" / ("duplicate" + suffix)
        path.parent.mkdir(parents=True)
        path.write_text("# source fixture\n")
    with pytest.raises(ValueError, match="Overlapping installed source ownership"):
        audit.source_files((suffix,), roots=roots)


def test_new_core_module_is_not_hidden_by_a_package_prefix(tmp_path):
    source = tmp_path / "src"
    future = source / "repo_catalog/domain/core_query_future.py"
    future.parent.mkdir(parents=True)
    future.write_text("def future(): return None\n")
    assert audit.source_files(roots=[source]) == [future]
    assert audit.product_imports(
        "from .core_query import CoreQueryService",
        "repo_catalog.application",
    ) == {
        "repo_catalog.application.core_query",
        "repo_catalog.application.core_query.CoreQueryService",
    }


def test_current_runtime_import_index_checks_all_distribution_roots():
    report = audit.build()
    modules = {entry["path"]: entry for entry in report["modules"]}
    for path in audit.source_files():
        package = ".".join(audit.source_relative(path).parent.parts)
        entry = modules[path.relative_to(audit.ROOT).as_posix()]
        assert entry["direct_product_imports"] == sorted(
            audit.product_imports(path.read_text(), package)
        )
    assert report["status"] == "current-separated-source-index"
    assert all(
        not role.startswith("normal.")
        for roles in report["schema_owners"].values()
        for role in roles
    )
