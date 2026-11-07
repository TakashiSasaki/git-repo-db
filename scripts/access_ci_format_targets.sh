# Shared by Access Ruff checks and its scoped offline reproducer.
targets=(
  scripts/preflight_access.py
  scripts/compare_access_regressions.py
  scripts/audit_access_acceptance.py
  packages/core/src/repo_catalog/adapters/sqlite/git_core.py
  packages/access/src/repo_catalog/domain/access_backup.py
  packages/access/src/repo_catalog/domain/ports/access_backup.py
  packages/access/src/repo_catalog/adapters/sqlite/access_backup.py
  packages/access/src/repo_catalog/application/access_maintenance.py
  packages/access/src/repo_catalog/cli/access_maintenance.py
  src/repo_catalog/domain/native_acquisition.py
  src/repo_catalog/adapters/git/access_native.py
  src/repo_catalog/application/access_acquisition.py
  src/repo_catalog/cli/access_acquisition.py
  src/repo_catalog/adapters/git/native.py
  src/repo_catalog/adapters/git/notes.py
  src/repo_catalog/application/notes.py
  src/repo_catalog/adapters/sqlite/notes.py
  src/repo_catalog/adapters/sqlite/acquisition.py
  src/repo_catalog/domain/ports/notes.py
  tests/unit/test_native_acquisition_values.py
  packages/context/src/repo_catalog/domain/context_registration.py
  src/repo_catalog/domain/acquisition.py
  src/repo_catalog/domain/exchange.py
  packages/context/src/repo_catalog/adapters/sqlite/p1_context.py
  packages/context/src/repo_catalog/adapters/sqlite/production_context.py
  src/repo_catalog/application/acquisition.py
  src/repo_catalog/application/exchange.py
  src/repo_catalog/application/production_query.py
  tests/unit/test_context_registration_values.py
  tests/integration/p1/test_context_relations.py
  tests/integration/p3/test_production_context.py
  tests/integration/p5/test_provider_acquisition.py
  tests/integration/p6/conftest.py
  scripts/audit_context_registration.py
  packages/access/src/repo_catalog/domain/access_workflow.py
  packages/access/src/repo_catalog/domain/ports/access_workflow.py
  packages/access/src/repo_catalog/application/access_workflow.py
  packages/access/src/repo_catalog/adapters/filesystem/access_executor.py
  packages/access/src/repo_catalog/cli/access_workflow.py
  packages/access/src/repo_catalog/domain/access_connections.py
  packages/access/src/repo_catalog/domain/ports/access_connections.py
  packages/access/src/repo_catalog/adapters/sqlite/access_connections.py
  packages/access/src/repo_catalog/domain/access_registry.py
  packages/access/src/repo_catalog/domain/ports/access_registry.py
  packages/access/src/repo_catalog/adapters/sqlite/access_registry.py
  packages/access/src/repo_catalog/adapters/sqlite/access_schema.py
  tests/unit/test_access*_values.py
  tests/integration/access
  scripts/verify_access_distribution.py
)

archive_access_formatter_source() {
  git archive --format=tar.gz HEAD -- \
    .gitignore AGENTS.md README.md pyproject.toml uv.lock \
    src packages scripts .github \
    tests/__init__.py tests/conftest.py tests/support tests/unit \
    tests/integration/__init__.py tests/integration/access \
    tests/integration/p1 tests/integration/p3 tests/integration/p5 tests/integration/p6 \
    > "$1"
}

# Only successful development runs with a completed Ruff check can use the
# smaller formatter reproduction scope. All other paths retain the full archive.
access_ci_formatter_only() {
  [[ "$1" == success && "$2" == development && "$3" == true && \
     "$4" == false && "$5" == false ]]
}
