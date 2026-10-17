"""A2 local operator/executor boundaries on actual SQLite and OS directories."""

import json
import os
import pty
import select
import sqlite3
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from repo_catalog.adapters.filesystem import access_executor as executor
from repo_catalog.adapters.filesystem.access_executor import LocalDirectoryExecutor
from repo_catalog.adapters.sqlite import access_schema as schema
from repo_catalog.adapters.sqlite.access_connections import AccessConnections
from repo_catalog.application.access_workflow import AccessWorkflow
from repo_catalog.cli import access_workflow as cli
from repo_catalog.domain.access_connections import (
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

SCOPE = "550e8400-e29b-41d4-a716-446655440000"
REPO = "650e8400-e29b-41d4-a716-446655440000"
OTHER = "750e8400-e29b-41d4-a716-446655440000"
CONTEXT = canonical(
    {
        "version": 1,
        "executor_kind": "local",
        "executor_ref": "test",
        "identity_view": "owner",
        "path_dialect": "posix",
    }
)
OPTIONS = canonical({"version": 1, "transport": "file", "path_dialect": "posix"})


@pytest.fixture
def fixture(tmp_path):
    root = tmp_path / "executor"
    root.mkdir(mode=0o700)
    repository = root / "repo.git"
    repository.mkdir(mode=0o700)
    path = tmp_path / "access.sqlite3"
    schema.initialize(path)
    route = ScopeLocatorRegistration(SCOPE, 10, root.as_uri())
    key = AssignmentKey(SCOPE, str(repository), "local")
    with AccessConnections(path, writable=True) as store:
        store.register_scope(AccessScope(SCOPE, "local"))
        store.register_locator(route)
        store.set_locator_enabled(route, True)
        store.configure_scope(ScopeExecutionContext(SCOPE, CONTEXT, True))
        store.bind_repository(RepositoryBinding(SCOPE, str(repository), REPO, True))
        store.configure_connection(
            ConnectionConfiguration(SCOPE, "local", OPTIONS, True)
        )
        store.assign_connection(LocatorConnection(key, True))
        yield store, path, root, repository, route, key


def selection(fixture, *, explicit=False):
    *_, route, key = fixture
    return AccessSelection(
        REPO, SCOPE, key if explicit else None, route if explicit else None
    )


def allow(_document):
    return True


def approve(workflow, selected):
    return workflow.approve(workflow.begin_review(selected), allow)


def activated(workflow, selected):
    approve(workflow, selected)
    return workflow.activate(selected, LocalDirectoryExecutor(), allow)


def inspect_fd(fd):
    info = os.fstat(fd)
    return info.st_dev, info.st_ino


def no_catalog():
    """Only tests local directory inspection, not domain acquisition."""


def test_review_and_approval_are_not_execution(fixture, monkeypatch):
    store, _, _, _, route, _ = fixture
    monkeypatch.setattr(
        executor, "_directory", lambda _: pytest.fail("unexpected probe")
    )
    with AccessWorkflow(store) as workflow:
        shown = workflow.inspect(selection(fixture))
        assert shown["scope_registration"] == list(route.key)
        with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
            store.current_grant(REPO, SCOPE)
        observed = []
        token = workflow.begin_review(selection(fixture))
        grant = workflow.approve(token, lambda d: observed.append(d) is None)
        assert observed[0]["plan"] == shown
        assert grant.plan == store.current_grant(REPO, SCOPE).plan
        with pytest.raises(AccessRegistryError, match="TOKEN"):
            workflow.approve(token, allow)


@pytest.mark.parametrize("response", [False, None, 1, "yes", {}, []])
def test_only_explicit_true_confirms_local_callback(fixture, response):
    with AccessWorkflow(fixture[0]) as workflow:
        token = workflow.begin_review(selection(fixture))
        with pytest.raises(AccessRegistryError, match="DECLINED"):
            workflow.approve(token, lambda _: response)
        with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
            fixture[0].current_grant(REPO, SCOPE)


@pytest.mark.parametrize(
    "key,value",
    [
        ("lifetime_seconds", 0),
        ("lifetime_seconds", True),
        ("lifetime_seconds", 3601),
        ("lifetime_seconds", 1.5),
        ("max_pending", 0),
        ("max_pending", 1025),
    ],
)
def test_finite_limits(fixture, key, value):
    with pytest.raises(AccessRegistryError, match="LIMIT"):
        AccessWorkflow(fixture[0], **{key: value})


def test_token_not_transferable_or_deserializable(fixture):
    with AccessWorkflow(fixture[0]) as first, AccessWorkflow(fixture[0]) as second:
        token = first.begin_review(selection(fixture))
        for value in (token, object(), {}, "approved", True):
            with pytest.raises(AccessRegistryError, match="TOKEN"):
                second.approve(value, allow)
        first.approve(token, allow)


def test_ticket_expiry_and_capacity(fixture):
    now = [0]
    with AccessWorkflow(
        fixture[0], lifetime_seconds=1, max_pending=1, monotonic_ns=lambda: now[0]
    ) as workflow:
        token = workflow.begin_review(selection(fixture))
        with pytest.raises(AccessRegistryError, match="PENDING_LIMIT"):
            workflow.begin_review(selection(fixture))
        now[0] = 1_000_000_000
        with pytest.raises(AccessRegistryError, match="EXPIRED"):
            workflow.approve(token, allow)
        approve(workflow, selection(fixture))


def test_expiry_during_review_denies_without_grant(fixture):
    now = [0]
    with AccessWorkflow(
        fixture[0], lifetime_seconds=1, monotonic_ns=lambda: now[0]
    ) as workflow:

        def slow(_):
            now[0] = 2_000_000_000
            return True

        with pytest.raises(AccessRegistryError, match="EXPIRED"):
            workflow.approve(workflow.begin_review(selection(fixture)), slow)
        with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
            fixture[0].current_grant(REPO, SCOPE)


@pytest.mark.parametrize("change", ["context", "latest", "disabled"])
def test_review_rechecks_after_operator_response(fixture, change):
    store, _, root, _, route, _ = fixture
    with AccessWorkflow(store) as workflow:

        def changed(_):
            if change == "context":
                old = store.scope_context(SCOPE)
                data = json.loads(old.context_json)
                data["identity_view"] = "another"
                store.configure_scope(
                    replace(old, context_json=canonical(data)), expected=old
                )
            elif change == "latest":
                new = ScopeLocatorRegistration(SCOPE, 20, (root / "other").as_uri())
                store.register_locator(new)
                store.set_locator_enabled(new, True)
            else:
                store.set_locator_enabled(route, False)
            return True

        with pytest.raises(AccessRegistryError, match="REVIEW_CHANGED|DISABLED"):
            workflow.approve(workflow.begin_review(selection(fixture)), changed)


def test_stored_grant_required_before_any_executor_probe(fixture):
    class Forbidden:
        def bind(self, _):
            pytest.fail("unapproved probe")

    with AccessWorkflow(fixture[0]) as workflow:
        with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
            workflow.activate(selection(fixture), Forbidden(), allow)


def test_activation_must_be_local_and_single_use(fixture):
    store, _, _, repository, _, _ = fixture
    with AccessWorkflow(store) as workflow:
        approve(workflow, selection(fixture))
        shown = []
        token = workflow.activate(
            selection(fixture),
            LocalDirectoryExecutor(),
            lambda d: shown.append(d) is None,
        )
        evidence = json.loads(shown[0]["executor_evidence_json"])
        assert evidence["repository"][0] == str(repository)
        assert evidence["process_identity_and_mount_namespace"][0] == os.getpid()
        fd_seen = []

        def operation(fd):
            assert not store._db.in_transaction
            fd_seen.append(fd)
            return inspect_fd(fd)

        assert workflow.dispatch_once(token, operation, guard=no_catalog) == (
            repository.stat().st_dev,
            repository.stat().st_ino,
        )
        with pytest.raises(OSError):
            os.fstat(fd_seen[0])
        with pytest.raises(AccessRegistryError, match="TOKEN"):
            workflow.dispatch_once(token, inspect_fd, guard=no_catalog)


def test_denied_activation_closes_local_descriptors(fixture):
    factory = LocalDirectoryExecutor()
    bound = []

    class Capture:
        def bind(self, plan):
            result = factory.bind(plan)
            bound.append(result)
            return result

    with AccessWorkflow(fixture[0]) as workflow:
        approve(workflow, selection(fixture))
        with pytest.raises(AccessRegistryError, match="DECLINED"):
            workflow.activate(selection(fixture), Capture(), lambda _: False)
    assert bound[0]._closed


@pytest.mark.parametrize(
    "change", ["revocation", "profile-aba", "latest", "tie", "access-stop"]
)
def test_dispatch_rechecks_permissions_and_default_selection(fixture, change):
    store, path, root, _, route, key = fixture
    with AccessWorkflow(store) as workflow:
        token = activated(workflow, selection(fixture))
        if change == "revocation":
            store.revoke_local_approval(key)
        elif change == "profile-aba":
            old = store.configuration(SCOPE, "local")
            new = replace(old, enabled=False)
            store.configure_connection(new, expected=old)
            store.configure_connection(old, expected=new)
        elif change in ("latest", "tie"):
            new = ScopeLocatorRegistration(
                SCOPE,
                20 if change == "latest" else route.registered_at_us,
                (root / "other").as_uri(),
            )
            store.register_locator(new)
        else:
            schema.persist_stop(path)
        called = []
        with pytest.raises(AccessRegistryError):
            workflow.dispatch_once(
                token, lambda fd: called.append(fd), guard=no_catalog
            )
        assert called == []


def test_explicit_old_registration_is_not_implicit_fallback(fixture):
    store, _, root, _, _, _ = fixture
    with AccessWorkflow(store) as workflow:
        token = activated(workflow, selection(fixture, explicit=True))
        store.register_locator(
            ScopeLocatorRegistration(SCOPE, 20, (root / "new").as_uri())
        )
        assert workflow.dispatch_once(token, inspect_fd, guard=no_catalog)


def test_a_at_new_time_cannot_borrow_old_grant(fixture):
    store, _, _, _, route, _ = fixture
    with AccessWorkflow(store) as workflow:
        approve(workflow, selection(fixture))
        new = replace(route, registered_at_us=20)
        store.register_locator(new)
        store.set_locator_enabled(new, True)
        with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
            workflow.activate(selection(fixture), LocalDirectoryExecutor(), allow)


def test_guard_rejection_and_guard_side_effect_are_checked(fixture):
    store, *_, key = fixture
    with AccessWorkflow(store) as workflow:
        token = activated(workflow, selection(fixture))

        def stopped():
            raise AccessRegistryError("CATALOG_STOP", "domain guard rejected")

        with pytest.raises(AccessRegistryError, match="CATALOG_STOP"):
            workflow.dispatch_once(
                token, lambda _: pytest.fail("executed"), guard=stopped
            )
        token = workflow.activate(selection(fixture), LocalDirectoryExecutor(), allow)
        with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
            workflow.dispatch_once(
                token,
                lambda _: pytest.fail("executed"),
                guard=lambda: store.revoke_local_approval(key),
            )


def test_inflight_revocation_no_fake_cancellation_or_retry(fixture):
    store, *_, key = fixture
    with AccessWorkflow(store) as workflow:
        token = activated(workflow, selection(fixture))

        def already_started(fd):
            # A write really succeeds while the callback runs: no DB transaction is held.
            store.revoke_local_approval(key)
            return inspect_fd(fd)

        assert workflow.dispatch_once(token, already_started, guard=no_catalog)
        with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
            workflow.activate(selection(fixture), LocalDirectoryExecutor(), allow)


def test_operation_failure_closes_executor_and_consumes_ticket(fixture):
    with AccessWorkflow(fixture[0]) as workflow:
        token = activated(workflow, selection(fixture))
        fds = []

        def failed(fd):
            fds.append(fd)
            raise RuntimeError("intentional trusted callback failure")

        with pytest.raises(RuntimeError):
            workflow.dispatch_once(token, failed, guard=no_catalog)
        with pytest.raises(OSError):
            os.fstat(fds[0])
        with pytest.raises(AccessRegistryError, match="TOKEN"):
            workflow.dispatch_once(token, inspect_fd, guard=no_catalog)


@pytest.mark.parametrize("changed", ["repository", "root", "permissions", "namespace"])
def test_actual_executor_binding_change_rejected(fixture, changed, monkeypatch):
    _, _, root, repository, _, _ = fixture
    with AccessWorkflow(fixture[0]) as workflow:
        token = activated(workflow, selection(fixture))
        if changed == "repository":
            repository.rename(repository.with_name("old.git"))
            repository.mkdir(mode=0o700)
        elif changed == "root":
            root.rename(root.with_name("old-root"))
            root.mkdir(mode=0o700)
            repository.mkdir(mode=0o700)
        elif changed == "permissions":
            repository.chmod(0o777)
        else:
            original = executor._environment()
            monkeypatch.setattr(
                executor, "_environment", lambda: (*original[:-1], original[-1] + 1)
            )
        with pytest.raises(AccessRegistryError, match="EXECUTOR_"):
            workflow.dispatch_once(
                token, lambda _: pytest.fail("executed"), guard=no_catalog
            )


@pytest.mark.parametrize(
    "kind", ["symlink", "traversal", "outside", "https", "container", "missing"]
)
def test_finite_local_adapter_rejects_unsupported_execution(fixture, kind):
    store, _, root, repository, route, key = fixture
    plan = store.review_plan(REPO, SCOPE)
    if kind == "symlink":
        repository.rmdir()
        other = root / "other"
        other.mkdir()
        repository.symlink_to(other)
    elif kind == "traversal":
        plan = replace(
            plan,
            assignment=replace(
                key, locator_text=str(root / "repo.git" / ".." / "repo.git")
            ),
        )
    elif kind == "outside":
        plan = replace(plan, assignment=replace(key, locator_text=str(root.parent)))
    elif kind == "https":
        plan = replace(
            plan,
            registration=replace(
                route, scope_locator_uri="https://host.example/environment"
            ),
        )
    elif kind == "container":
        plan = replace(
            plan,
            context_json=canonical(
                {**json.loads(CONTEXT), "executor_kind": "container"}
            ),
        )
    else:
        repository.rmdir()
    with pytest.raises(AccessRegistryError, match="EXECUTOR_"):
        LocalDirectoryExecutor().bind(plan)


def test_close_and_expiry_close_pending_executor(fixture):
    now = [0]
    workflow = AccessWorkflow(
        fixture[0], lifetime_seconds=1, monotonic_ns=lambda: now[0]
    )
    token = activated(workflow, selection(fixture))
    bound = workflow._pending[token].executor
    now[0] = 1_000_000_000
    with pytest.raises(AccessRegistryError, match="EXPIRED"):
        workflow.dispatch_once(token, inspect_fd, guard=no_catalog)
    assert bound._closed
    token = workflow.activate(selection(fixture), LocalDirectoryExecutor(), allow)
    bound = workflow._pending[token].executor
    workflow.close()
    assert bound._closed
    with pytest.raises(AccessRegistryError, match="SESSION_CLOSED"):
        workflow.dispatch_once(token, inspect_fd, guard=no_catalog)


def test_no_network_subprocess_or_credentials_in_review_preflight(fixture, monkeypatch):
    import socket

    monkeypatch.setattr(
        socket, "create_connection", lambda *a, **k: pytest.fail("network")
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("subprocess"))
    with AccessWorkflow(fixture[0]) as workflow:
        token = activated(workflow, selection(fixture))
        assert workflow.dispatch_once(token, inspect_fd, guard=no_catalog)


def arguments(fixture, command):
    return [
        command,
        "--access-db",
        str(fixture[1]),
        "--repository",
        REPO,
        "--scope",
        SCOPE,
    ]


def test_cli_review_only_and_pipe_refusal(fixture, capsys):
    assert cli.main(arguments(fixture, "review")) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "review-only"
    for command in ("approve", "preflight"):
        assert cli.main(arguments(fixture, command)) == 2
        assert json.loads(capsys.readouterr().err)["code"] == "LOCAL_TTY_REQUIRED"
    with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
        fixture[0].current_grant(REPO, SCOPE)


@pytest.mark.parametrize(
    "extra",
    [
        ["--locator", "/a"],
        ["--profile", "p"],
        ["--scope-uri", "file:///a"],
        ["--registered-at-us", "1"],
        ["--yes"],
    ],
)
def test_cli_rejects_partial_or_bypass_arguments(fixture, extra):
    with pytest.raises(SystemExit):
        cli.main(arguments(fixture, "approve") + extra)


def terminal_process(fixture, command, answer):
    """Real PTY test; test automation is not a claim of a human approving."""
    master, slave = pty.openpty()
    process = None
    output = bytearray()
    try:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[3] / "src")
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "repo_catalog.cli.access_workflow",
                *arguments(fixture, command),
            ],
            stdin=slave,
            stderr=slave,
            stdout=subprocess.PIPE,
            env=env,
        )
        os.close(slave)
        slave = -1
        deadline = time.monotonic() + 10
        while b"\n> " not in output:
            if time.monotonic() >= deadline or process.poll() is not None:
                raise AssertionError((process.poll(), output.decode(errors="replace")))
            if select.select([master], [], [], 0.1)[0]:
                output.extend(os.read(master, 65536))
        os.write(master, (answer + "\n").encode())
        stdout, _ = process.communicate(timeout=10)
        return process.returncode, stdout, bytes(output)
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
        if slave >= 0:
            os.close(slave)


def test_real_terminal_approval_and_directory_preflight(fixture):
    code, output, shown = terminal_process(
        fixture, "approve", f"approve {SCOPE} {REPO}"
    )
    assert code == 0 and json.loads(output)["status"] == "approved-locally"
    assert SCOPE.encode() in shown and REPO.encode() in shown
    code, output, shown = terminal_process(
        fixture, "preflight", f"activate-local {SCOPE} {REPO}"
    )
    assert code == 0
    assert json.loads(output)["status"] == "local-directory-preflight-only"
    assert json.loads(output)["git_acquired"] is False
    assert b"executor_evidence_json" in shown
    assert not (fixture[1].parent / "core.sqlite3").exists()


def test_real_terminal_decline_has_no_grant(fixture):
    code, output, _ = terminal_process(fixture, "approve", "no")
    assert code == 2 and output == b""
    with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
        fixture[0].current_grant(REPO, SCOPE)


def test_no_schema_or_domain_store_change(fixture):
    assert (
        schema.fingerprint()
        == "89bcafeda815150fa4770f5758edf7d2d36d505b76717aa19054f9ad689765da"
    )
    with AccessWorkflow(fixture[0]) as workflow:
        token = activated(workflow, selection(fixture))
        workflow.dispatch_once(token, inspect_fd, guard=no_catalog)
    with sqlite3.connect(fixture[1]) as db:
        tables = {
            r[0]
            for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")
        }
    assert tables == set(schema.TABLES)


def test_session_cannot_cross_process_or_thread(fixture, monkeypatch):
    import repo_catalog.application.access_workflow as module

    with AccessWorkflow(fixture[0]) as workflow:
        token = workflow.begin_review(selection(fixture))
        with monkeypatch.context() as patch:
            patch.setattr(module.os, "getpid", lambda: workflow._pid + 1)
            with pytest.raises(AccessRegistryError, match="SESSION_CLOSED"):
                workflow.approve(token, allow)
        with monkeypatch.context() as patch:
            patch.setattr(module.threading, "get_ident", lambda: workflow._thread + 1)
            with pytest.raises(AccessRegistryError, match="SESSION_CLOSED"):
                workflow.approve(token, allow)
        workflow.approve(token, allow)


def test_revoked_during_activation_denies_and_closes(fixture):
    store, *_, key = fixture
    with AccessWorkflow(store) as workflow:
        approve(workflow, selection(fixture))

        def revoked(_):
            store.revoke_local_approval(key)
            return True

        with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
            workflow.activate(selection(fixture), LocalDirectoryExecutor(), revoked)
        assert workflow._pending == {}


def test_default_new_registration_during_activation_denies(fixture):
    store, _, root, _, _, _ = fixture
    with AccessWorkflow(store) as workflow:
        approve(workflow, selection(fixture))

        def changed(_):
            store.register_locator(
                ScopeLocatorRegistration(SCOPE, 20, (root / "later").as_uri())
            )
            return True

        with pytest.raises(AccessRegistryError, match="DISABLED"):
            workflow.activate(selection(fixture), LocalDirectoryExecutor(), changed)


def test_wrong_token_purpose_consumes_and_closes(fixture):
    with AccessWorkflow(fixture[0]) as workflow:
        token = activated(workflow, selection(fixture))
        bound = workflow._pending[token].executor
        with pytest.raises(AccessRegistryError, match="TOKEN"):
            workflow.approve(token, allow)
        assert bound._closed
        token = workflow.begin_review(selection(fixture))
        with pytest.raises(AccessRegistryError, match="TOKEN"):
            workflow.dispatch_once(token, inspect_fd, guard=no_catalog)


def test_access_store_replacement_prevents_dispatch(fixture):
    store, path, *_ = fixture
    with AccessWorkflow(store) as workflow:
        token = activated(workflow, selection(fixture))
        replacement = path.with_name("replacement.sqlite3")
        schema.initialize(replacement)
        os.replace(replacement, path)
        with pytest.raises(AccessRegistryError, match="PATH_CHANGED"):
            workflow.dispatch_once(
                token, lambda _: pytest.fail("executed"), guard=no_catalog
            )


def test_fd_cleanup_when_pending_capacity_exhausted(fixture):
    with AccessWorkflow(fixture[0], max_pending=1) as workflow:
        token = activated(workflow, selection(fixture))
        bound = workflow._pending[token].executor
        with pytest.raises(AccessRegistryError, match="PENDING_LIMIT"):
            workflow.activate(selection(fixture), LocalDirectoryExecutor(), allow)
        workflow.close()
        assert bound._closed


def test_display_documents_do_not_leak_session_handles(fixture):
    with AccessWorkflow(fixture[0]) as workflow:
        document = workflow.inspect(selection(fixture))
        assert "token" not in document and "approved" not in document
        data = json.dumps(document)
        with pytest.raises(AccessRegistryError, match="TOKEN"):
            workflow.approve(data, allow)


def test_application_has_no_adapter_imports():
    import ast

    source = (
        Path(__file__).resolve().parents[3]
        / "src/repo_catalog/application/access_workflow.py"
    )
    for node in ast.walk(ast.parse(source.read_text())):
        if isinstance(node, ast.ImportFrom):
            assert ".adapters" not in (node.module or "")


@pytest.mark.parametrize("phase", ["approval", "dispatch"])
def test_expiry_during_final_database_validation(fixture, phase, monkeypatch):
    now = [0]
    with AccessWorkflow(
        fixture[0], lifetime_seconds=1, monotonic_ns=lambda: now[0]
    ) as workflow:
        selected = selection(fixture)
        if phase == "approval":
            token = workflow.begin_review(selected)
            original = workflow._review

            def slow(selection):
                result = original(selection)
                now[0] = 2_000_000_000
                return result

            monkeypatch.setattr(workflow, "_review", slow)
            with pytest.raises(AccessRegistryError, match="EXPIRED"):
                workflow.approve(token, allow)
        else:
            token = activated(workflow, selected)
            original = workflow._grant

            def slow(selection):
                result = original(selection)
                now[0] = 2_000_000_000
                return result

            monkeypatch.setattr(workflow, "_grant", slow)
            with pytest.raises(AccessRegistryError, match="EXPIRED"):
                workflow.dispatch_once(token, inspect_fd, guard=no_catalog)
