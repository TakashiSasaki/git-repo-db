"""Independent A6-H01 reproduction using an OS checkpoint and another DB handle.

No import of repository test fixtures, no replacement of bound.invoke/evidence.
"""

import importlib.util
import inspect
import json
import os
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from repo_catalog.adapters.filesystem import access_executor
from repo_catalog.adapters.filesystem.access_executor import LocalDirectoryExecutor
from repo_catalog.adapters.sqlite.access_connections import AccessConnections
from repo_catalog.adapters.sqlite.access_schema import initialize
from repo_catalog.application.access_workflow import AccessWorkflow
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


def run_case(workflow_class, api, change):
    with tempfile.TemporaryDirectory(prefix="r2-handoff-") as directory:
        base = Path(directory)
        root = base / "root"
        root.mkdir(mode=0o700)
        repo = root / "repo.git"
        repo.mkdir(mode=0o700)
        db = base / "access.sqlite3"
        initialize(db)
        scope, repository = str(uuid4()), str(uuid4())
        route = ScopeLocatorRegistration(scope, 10, root.as_uri())
        assignment = AssignmentKey(scope, str(repo), "local")
        chosen = AccessSelection(repository, scope)
        now = [0]
        cancelled = [False]
        started, changed = threading.Event(), threading.Event()
        failures, invoked, bounds = [], [], []
        with AccessConnections(db, writable=True) as store:
            store.register_scope(AccessScope(scope, "independent-review"))
            store.register_locator(route)
            store.set_locator_enabled(route, True)
            store.configure_scope(ScopeExecutionContext(scope, canonical({"version": 1, "executor_kind": "local", "executor_ref": "test", "identity_view": "owner", "path_dialect": "posix"}), True))
            store.bind_repository(RepositoryBinding(scope, str(repo), repository, True))
            store.configure_connection(ConnectionConfiguration(scope, "local", canonical({"version": 1, "transport": "file", "path_dialect": "posix"}), True))
            store.assign_connection(LocatorConnection(assignment, True))

            class Factory:
                def bind(self, plan):
                    bound = LocalDirectoryExecutor().bind(plan)
                    bounds.append(bound)
                    return bound

            def mutate():
                try:
                    if not started.wait(5):
                        raise RuntimeError("OS checkpoint not reached")
                    if change == "expiry":
                        now[0] = 1_000_000_000
                    elif change == "cancel":
                        cancelled[0] = True
                    else:
                        # A genuinely separate SQLite handle modifies committed state.
                        with AccessConnections(db, writable=True) as other:
                            if change == "revoke":
                                other.revoke_local_approval(assignment)
                            elif change == "newest":
                                other.register_locator(ScopeLocatorRegistration(scope, 20, root.as_uri()))
                            else:
                                raise AssertionError(change)
                except BaseException as error:
                    failures.append(repr(error))
                finally:
                    changed.set()

            real_environment = access_executor._environment

            def os_checkpoint():
                value = real_environment()
                # Synchronize at the adapter's final real OS evidence validation.
                if any(frame.function == "invoke" and frame.filename == access_executor.__file__ for frame in inspect.stack()):
                    started.set()
                    if not changed.wait(5):
                        raise RuntimeError("concurrent mutation did not complete")
                    if failures:
                        raise RuntimeError(failures)
                return value

            def guard():
                if cancelled[0]:
                    raise AccessRegistryError("CANCELLED", "synthetic cancellation")

            with workflow_class(store, lifetime_seconds=1, monotonic_ns=lambda: now[0]) as workflow:
                workflow.approve(workflow.begin_review(chosen), lambda _: True)
                token = workflow.activate(chosen, Factory(), lambda _: True)
                helper = threading.Thread(target=mutate)
                helper.start()
                with patch.object(access_executor, "_environment", os_checkpoint):
                    try:
                        if api == "descriptor":
                            workflow.dispatch_once(token, lambda fd: invoked.append(os.fstat(fd).st_ino), guard=guard)
                        else:
                            workflow.dispatch_reviewed_once(token, lambda fd, _plan, _check: invoked.append(os.fstat(fd).st_ino), guard=guard)
                    except AccessRegistryError as error:
                        code = error.code
                    else:
                        code = None
                helper.join(5)
                if helper.is_alive() or failures or not started.is_set():
                    raise RuntimeError({"thread_alive": helper.is_alive(), "failures": failures})
                try:
                    workflow.dispatch_once(token, lambda _fd: None, guard=lambda: None)
                except AccessRegistryError as error:
                    replay = error.code
                else:
                    replay = None
                descriptors_closed = []
                for descriptor in (bounds[0]._root_fd, bounds[0]._repository_fd):
                    try:
                        os.fstat(descriptor)
                    except OSError:
                        descriptors_closed.append(True)
                    else:
                        descriptors_closed.append(False)
                return {"api": api, "change": change, "rejection": code, "callback_started": bool(invoked), "token_replay": replay, "bound_closed": bounds[0]._closed, "descriptors_closed": descriptors_closed}


def main():
    classes = {"reviewed_head": AccessWorkflow}
    if len(sys.argv) > 1:
        spec = importlib.util.spec_from_file_location("r2_a5_workflow", sys.argv[1])
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        classes["a5_parent"] = module.AccessWorkflow
    result = {"sqlite": sqlite3.sqlite_version, "source_id": sqlite3.connect(":memory:").execute("select sqlite_source_id()").fetchone()[0], "cases": []}
    for label, cls in classes.items():
        for api in ("descriptor", "reviewed"):
            for change in ("expiry", "revoke", "newest", "cancel"):
                result["cases"].append({"source": label, **run_case(cls, api, change)})
    print(json.dumps(result, indent=2))
    for case in result["cases"]:
        if case["source"] == "reviewed_head":
            assert case["rejection"] and not case["callback_started"], case
            assert case["bound_closed"] and all(case["descriptors_closed"]), case
            assert case["token_replay"] == "TOKEN", case
        else:
            assert case["callback_started"], case


if __name__ == "__main__":
    main()
