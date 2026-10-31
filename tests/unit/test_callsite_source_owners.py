"""Keep namespace ownership auditable without hiding newly added source files."""

import hashlib

import pytest

from scripts import audit_callsite_dependencies as audit


def test_index_covers_every_python_owner_and_packaged_resource():
    report = audit.build()
    modules = report["modules"] + report["isolated_modules"]
    assert {entry["path"] for entry in modules if entry["path"].endswith(".py")} == {
        path.relative_to(audit.ROOT).as_posix() for path in audit.source_files()
    }
    assert set(report["source_roots"].values()) == {
        "repo-catalog",
        "repo-catalog-core",
        "repo-catalog-contracts",
    }
    baseline = {entry["path"]: entry for entry in report["modules"]}
    isolated = {entry["path"]: entry for entry in report["isolated_modules"]}
    assert (
        baseline["packages/contracts/src/repo_catalog/domain/time.py"]["owner"]
        == "repo-catalog-contracts"
    )
    core = isolated["packages/core/src/repo_catalog/adapters/sqlite/git_core.py"]
    assert core["owner"] == "repo-catalog-core"
    assert (
        core["sha256"]
        == hashlib.sha256((audit.ROOT / core["path"]).read_bytes()).hexdigest()
    )
    assert "functions" not in core
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


def test_new_core_module_is_not_hidden_by_a_package_prefix():
    future = audit.ROOT / "packages/core/src/repo_catalog/domain/core_query_future.py"
    assert audit.is_baseline_source(future)
    assert not audit.is_baseline_source(future.with_name("core_query.py"))
    assert audit.isolated_runtime_imports(
        "from repo_catalog.application.core_query import CoreQueryService",
        "repo_catalog.cli",
    ) == {"repo_catalog.application.core_query"}


def test_normal_runtime_import_guard_checks_all_distribution_roots():
    for path in audit.source_files():
        if audit.is_baseline_source(path):
            package = ".".join(audit.source_relative(path).parent.parts)
            assert not audit.isolated_runtime_imports(path.read_text(), package), path
