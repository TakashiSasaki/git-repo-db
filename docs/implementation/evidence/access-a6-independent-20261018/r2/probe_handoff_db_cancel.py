"""Independent cancellation during the final handoff's real grant transaction."""

import inspect
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from repo_catalog.adapters.filesystem.access_executor import LocalDirectoryExecutor
from repo_catalog.adapters.sqlite.access_connections import AccessConnections
from repo_catalog.adapters.sqlite.access_schema import initialize
from repo_catalog.application.access_workflow import AccessWorkflow
from repo_catalog.domain.access_connections import AssignmentKey, ConnectionConfiguration, LocatorConnection, RepositoryBinding, ScopeExecutionContext, canonical
from repo_catalog.domain.access_registry import AccessRegistryError, AccessScope, ScopeLocatorRegistration
from repo_catalog.domain.access_workflow import AccessSelection


def run(api):
    with tempfile.TemporaryDirectory(prefix="r2-db-cancel-") as directory:
        base = Path(directory)
        root = base / "root"
        root.mkdir(mode=0o700)
        repo = root / "repo.git"
        repo.mkdir(mode=0o700)
        path = base / "access.sqlite3"
        initialize(path)
        scope, repository = str(uuid4()), str(uuid4())
        route = ScopeLocatorRegistration(scope, 10, root.as_uri())
        assignment = AssignmentKey(scope, str(repo), "local")
        selection = AccessSelection(repository, scope)
        cancelled, invoked, injected = [False], [], []
        with AccessConnections(path, writable=True) as store:
            store.register_scope(AccessScope(scope, "independent-db-review"))
            store.register_locator(route)
            store.set_locator_enabled(route, True)
            store.configure_scope(ScopeExecutionContext(scope, canonical({"version": 1, "executor_kind": "local", "executor_ref": "test", "identity_view": "owner", "path_dialect": "posix"}), True))
            store.bind_repository(RepositoryBinding(scope, str(repo), repository, True))
            store.configure_connection(ConnectionConfiguration(scope, "local", canonical({"version": 1, "transport": "file", "path_dialect": "posix"}), True))
            store.assign_connection(LocatorConnection(assignment, True))

            def guard():
                if cancelled[0]:
                    raise AccessRegistryError("CANCELLED", "synthetic cancellation")

            with AccessWorkflow(store) as workflow:
                workflow.approve(workflow.begin_review(selection), lambda _: True)
                token = workflow.activate(selection, LocalDirectoryExecutor(), lambda _: True)
                real_plan = store._plan

                def cancel_during_plan(*args, **kwargs):
                    result = real_plan(*args, **kwargs)
                    if any(frame.function == "handoff" for frame in inspect.stack()):
                        cancelled[0] = True
                        injected.append(store._db.in_transaction)
                    return result

                with patch.object(store, "_plan", cancel_during_plan):
                    try:
                        if api == "descriptor":
                            workflow.dispatch_once(token, lambda fd: invoked.append(fd), guard=guard)
                        else:
                            workflow.dispatch_reviewed_once(token, lambda fd, plan, check: invoked.append(fd), guard=guard)
                    except AccessRegistryError as error:
                        rejection = error.code
                    else:
                        rejection = None
        return {"api": api, "cancelled_during_actual_grant_transaction": bool(injected) and all(injected), "callback_started": bool(invoked), "rejection": rejection}


if __name__ == "__main__":
    print(json.dumps({"sqlite": sqlite3.sqlite_version, "results": [run(api) for api in ("descriptor", "reviewed")]}, indent=2))
