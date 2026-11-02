"""Standalone installed-artifact probe; copied outside the checkout by packaging tests."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import sysconfig
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4


def main(output):
    from repo_catalog.adapters.filesystem.access_executor import LocalDirectoryExecutor
    from repo_catalog.adapters.sqlite import access_schema as schema
    from repo_catalog.adapters.sqlite.access_backup import AccessBackup
    from repo_catalog.adapters.sqlite.access_connections import AccessConnections
    from repo_catalog.application.access_workflow import AccessWorkflow
    from repo_catalog.domain.access_backup import AccessBackupLimits
    from repo_catalog.domain.access_connections import (
        AccessPreference,
        AssignmentKey,
        ConnectionConfiguration,
        LocatorConnection,
        RepositoryBinding,
        ScopeExecutionContext,
        canonical,
    )
    from repo_catalog.domain.access_registry import (
        AccessRegistryError,
        AccessScope,
        ScopeLocatorRegistration,
    )
    from repo_catalog.domain.access_workflow import AccessSelection

    os.umask(0o022)
    root = Path.cwd()
    checks = []
    installed = Path(sysconfig.get_path("purelib")).resolve()
    distributions = list(importlib.metadata.distributions())
    assert [d.metadata["Name"] for d in distributions] == ["repo-catalog-access"]
    distribution = distributions[0]
    assert not distribution.requires
    owners = {}
    for member in distribution.files:
        name = str(member)
        if name.startswith("repo_catalog/") and not name.endswith(".pyc"):
            assert name not in owners
            owners[name] = distribution.metadata["Name"]
            if name.endswith(".py"):
                module = importlib.import_module(name[:-3].replace("/", "."))
                assert Path(module.__file__).resolve().is_relative_to(installed)
    assert len(owners) == 19, owners
    assert {n for n in owners if n.endswith(".sql")} == {
        "repo_catalog/adapters/sqlite/access_ddl/registry.sql",
        "repo_catalog/adapters/sqlite/access_ddl/connections.sql",
    }
    for name in (
        "adapters.sqlite.git_core",
        "adapters.sqlite.production_context",
        "adapters.sqlite.catalog_runtime",
        "adapters.sqlite.p1_schema",
        "adapters.sqlite.acquisition",
        "adapters.sqlite.production_search",
        "application.access_acquisition",
        "application.acquisition",
        "application.exchange",
        "application.recovery",
        "cli.main",
        "domain.p1_core",
        "domain.p1_context",
        "domain.acquisition",
    ):
        assert importlib.util.find_spec("repo_catalog." + name) is None, name
    assert importlib.util.find_spec("httpx") is None
    checks.append("exact_dependency_free_installation_origins_ownership_and_absence")

    def refuses(action, *codes):
        try:
            action()
        except AccessRegistryError as error:
            assert error.code in codes, (error.code, codes)
            return error.code
        raise AssertionError("unexpected success: " + repr(action))

    path = root / "access.sqlite3"
    refuses(lambda: AccessConnections(path), "MISSING")
    assert not path.exists()
    schema.initialize(path)
    refuses(lambda: schema.initialize(path), "EXISTS")
    scope, repo = str(uuid4()), str(uuid4())
    executor = root / "executor"
    executor.mkdir(mode=0o700)
    repository = executor / "repo.git"
    repository.mkdir(mode=0o700)
    old = ScopeLocatorRegistration(scope, 10, "file:///old")
    route = ScopeLocatorRegistration(scope, 20, executor.as_uri())
    key = AssignmentKey(scope, str(repository), "local")
    options = canonical({"version": 1, "transport": "file", "path_dialect": "posix"})
    context = canonical(
        {
            "version": 1,
            "executor_kind": "local",
            "executor_ref": "installed",
            "identity_view": "owner",
            "path_dialect": "posix",
        }
    )
    profile = ConnectionConfiguration(scope, "local", options, True)
    selected = AccessSelection(repo, scope, key, route)
    with AccessConnections(path, writable=True) as store:
        # Registration and inspection cannot invoke Git, credential helpers or network.
        with (
            patch(
                "subprocess.Popen",
                side_effect=AssertionError("process during registration"),
            ),
            patch(
                "socket.socket.connect",
                side_effect=AssertionError("network during registration"),
            ),
        ):
            store.register_scope(AccessScope(scope, "synthetic"))
            for reg in (old, route):
                store.register_locator(reg)
            assert store.first_choices(scope) == (route,)
            assert store.history(scope).registrations == (route, old)
            store.set_locator_enabled(route, True)
            store.configure_scope(ScopeExecutionContext(scope, context, True))
            binding = RepositoryBinding(scope, str(repository), repo, True)
            store.bind_repository(binding)
            store.bind_repository(binding)  # exact replay
            refuses(
                lambda: store.bind_repository(
                    replace(binding, repository_uuidv4=str(uuid4()))
                ),
                "BINDING_CONFLICT",
            )
            store.configure_connection(profile)
            store.assign_connection(LocatorConnection(key, True))
            store.set_preference(AccessPreference(repo, key))
            assert store.review_plan(repo, scope).assignment == key
        with AccessWorkflow(store) as workflow:
            refuses(lambda: store.current_grant(repo, scope), "APPROVAL_REQUIRED")
            # Trusted synthetic reviewer: this is not a claim of human consent.
            workflow.approve(workflow.begin_review(selected), lambda shown: True)
            token = workflow.activate(
                selected, LocalDirectoryExecutor(), lambda shown: True
            )
            assert (
                workflow.dispatch_once(
                    token, lambda fd: os.fstat(fd).st_ino, guard=lambda: None
                )
                == repository.stat().st_ino
            )
            disabled = replace(profile, enabled=False)
            store.configure_connection(disabled, expected=profile)
            store.configure_connection(profile, expected=disabled)
            refuses(lambda: store.current_grant(repo, scope), "APPROVAL_REQUIRED")
            stale = workflow.begin_review(selected)
            store.set_locator_enabled(route, False)
            refuses(
                lambda: workflow.approve(stale, lambda shown: True),
                "DISABLED",
                "STALE_REVIEW",
                "SETTINGS_CHANGED",
            )
            store.set_locator_enabled(route, True)
            workflow.approve(workflow.begin_review(selected), lambda shown: True)
        # Tied latest registration refuses automatic choice, even when disabled.
        tie = ScopeLocatorRegistration(scope, 20, "file:///tied")
        store.register_locator(tie)
        assert len(store.first_choices(scope)) == 2
        refuses(lambda: store.review_plan(repo, scope), "AMBIGUOUS")
        refuses(lambda: store.first_choices(scope, max_candidates=1), "CANDIDATE_LIMIT")
        assert not schema.stop_path(path).exists()
        assert store.current_grant(repo, scope, assignment=key, registration=route)
    checks.append("registry_logical_repository_history_ties_replay_conflicts_limits")
    checks.append("workflow_review_dispatch_revalidation_and_ABA_revocation")

    def cli(module, *args, success=True):
        response = subprocess.run(
            [sys.executable, "-I", "-m", "repo_catalog.cli." + module, *map(str, args)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert response.returncode == (0 if success else 2), response.stderr
        return json.loads(response.stdout if success else response.stderr)

    selection_args = (
        "--access-db",
        path,
        "--repository",
        repo,
        "--scope",
        scope,
        "--locator",
        repository,
        "--profile",
        "local",
        "--scope-uri",
        route.scope_locator_uri,
        "--registered-at-us",
        20,
    )
    assert cli("access_workflow", "review", *selection_args)["status"] == "review-only"
    for command in ("approve", "preflight"):
        assert (
            cli("access_workflow", command, *selection_args, success=False)["code"]
            == "LOCAL_TTY_REQUIRED"
        )
    checks.append("CLI_review_and_noninteractive_approval_preflight_refusal")

    # Hold a live reader while committing a new Scope: coherent backup must include WAL.
    db = schema._connect(path, writable=True)
    db.execute("PRAGMA wal_autocheckpoint=0")
    db.execute("BEGIN")
    db.execute("SELECT * FROM access_identity").fetchall()
    extra = str(uuid4())
    with AccessConnections(path, writable=True) as store:
        store.register_scope(AccessScope(extra, "committed WAL"))
    assert Path(str(path) + "-wal").stat().st_size > 0
    bundle = root / "bundle"
    cli("access_maintenance", "backup", "--access-db", path, "--destination", bundle)
    db.close()
    manifest = cli("access_maintenance", "inspect", "--bundle", bundle)
    assert manifest["status"] == "ok"
    restored = root / "restored"
    receipt = cli(
        "access_maintenance", "restore", "--bundle", bundle, "--destination", restored
    )["result"]
    assert receipt["local_grants"] == receipt["enabled_routes"] == 0
    assert receipt["requires_local_reapproval"]
    restored_path = restored / "access.sqlite3"
    with AccessConnections(restored_path, writable=True) as store:
        assert store.scope(extra).display_name == "committed WAL"
        history = store.history(scope).registrations
        assert set(history) == {old, route, tie}
        assert not store.locator_enabled(route)
        refuses(
            lambda: store.current_grant(
                repo, scope, assignment=key, registration=route
            ),
            "DISABLED",
            "APPROVAL_REQUIRED",
        )
        store.set_locator_enabled(route, True)
        refuses(
            lambda: store.current_grant(
                repo, scope, assignment=key, registration=route
            ),
            "APPROVAL_REQUIRED",
        )
        with AccessWorkflow(store) as workflow:
            workflow.approve(workflow.begin_review(selected), lambda shown: True)
    fork = cli(
        "access_maintenance",
        "fork",
        "--access-db",
        restored_path,
        "--source-scope",
        scope,
        "--scope-uri",
        executor.as_uri(),
    )["result"]
    assert fork
    with AccessConnections(restored_path) as store:
        assert store.history(scope).registrations == history
        new_scope = fork["target_scope_uuidv4"]
        assert new_scope != scope
        registrations = store.history(new_scope).registrations
        assert len(registrations) == 1
        assert registrations[0].scope_locator_uri == executor.as_uri()
        assert registrations[0].registered_at_us > route.registered_at_us
        assert not store.scope_context(new_scope).enabled
    # No overwrite, strict bundle members, finite resource bounds and input preservation.
    refuses(lambda: AccessBackup().restore(bundle, restored), "EXISTS")
    refuses(
        lambda: AccessBackup(AccessBackupLimits(max_bytes=1)).inspect(bundle), "LIMIT"
    )
    snapshot = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in bundle.iterdir()
    }
    (bundle / "unexpected").write_text("untrusted member")
    refuses(lambda: AccessBackup().restore(bundle, root / "rejected"), "BACKUP_FORMAT")
    assert not (root / "rejected").exists()
    assert all(
        hashlib.sha256((bundle / name).read_bytes()).hexdigest() == digest
        for name, digest in snapshot.items()
    )
    checks.append("WAL_backup_CLI_inspect_inactive_restore_reapproval_and_fork")
    checks.append("backup_limits_strict_members_preserved_input_no_overwrite")

    damaged = root / "damaged.sqlite3"
    shutil.copy2(path, damaged)
    damaged.write_bytes(b"confirmed non SQLite database")
    refuses(lambda: AccessConnections(damaged), "CORRUPT")
    assert schema.stop_path(damaged).exists()
    assert not (root / "p1-recovery-stop.json").exists()
    with AccessConnections(path) as store:
        assert store.scope(scope).scope_uuidv4 == scope
    assert not list(root.rglob("core.sqlite3"))
    assert not list(root.rglob("context.sqlite3"))
    assert not list(root.rglob("operational.sqlite3"))
    assert not list(root.rglob("search.sqlite3"))
    checks.append("isolated_Access_corruption_stop_and_no_other_store_creation")
    for name, module in tuple(sys.modules.items()):
        if name.startswith("repo_catalog.") and getattr(module, "__file__", None):
            assert Path(module.__file__).resolve().is_relative_to(installed), name
    Path(output).write_text(
        json.dumps(
            {
                "result": "passed",
                "checks": checks,
                "installed_distributions": [distribution.metadata["Name"]],
                "runtime_dependencies": distribution.requires or [],
                "unique_product_files": len(owners),
                "python": sys.version,
                "sqlite": sqlite3.sqlite_version,
                "access_fingerprint": schema.fingerprint(),
                "fork": fork,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main(sys.argv[1])
