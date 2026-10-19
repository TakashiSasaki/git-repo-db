"""A6 counterexamples at the final bound-executor callback handoff."""

import pytest

from repo_catalog.adapters.filesystem.access_executor import LocalDirectoryExecutor
from repo_catalog.application.access_workflow import AccessWorkflow
from repo_catalog.domain.access_registry import (
    AccessRegistryError,
    ScopeLocatorRegistration,
)
from tests.integration.access.test_workflow import (
    SCOPE,
    allow,
    approve,
    inspect_fd,
    selection,
)
from tests.integration.access.test_workflow import (
    fixture as fixture,
)


@pytest.mark.parametrize("api", ["descriptor", "reviewed"])
@pytest.mark.parametrize(
    "change,code",
    [
        ("expiry", "EXPIRED"),
        ("revocation", "APPROVAL_REQUIRED|GRANT_CHANGED"),
        ("latest", "DISABLED|GRANT_CHANGED"),
        ("cancel", "CANCELLED"),
    ],
)
def test_final_executor_handoff_rechecks_before_callback(
    fixture, monkeypatch, api, change, code
):
    """A real bound executor can block after the workflow's preceding checks."""
    store, _, root, _, _, key = fixture
    now = [0]
    stopped = [False]
    invoked = []
    bounds = []

    class Factory:
        def bind(self, plan):
            bound = LocalDirectoryExecutor().bind(plan)
            bounds.append(bound)
            original = bound.invoke

            def invoke(operation):
                original_evidence = bound.evidence

                def delayed_evidence():
                    result = original_evidence()
                    if change == "expiry":
                        now[0] = 1_000_000_000
                    elif change == "revocation":
                        store.revoke_local_approval(key)
                    elif change == "latest":
                        store.register_locator(
                            ScopeLocatorRegistration(SCOPE, 20, (root / "new").as_uri())
                        )
                    else:
                        stopped[0] = True
                    return result

                monkeypatch.setattr(bound, "evidence", delayed_evidence)
                return original(operation)

            monkeypatch.setattr(bound, "invoke", invoke)
            return bound

    def guard():
        if stopped[0]:
            raise AccessRegistryError("CANCELLED", "external operation stopped")

    with AccessWorkflow(
        store, lifetime_seconds=1, monotonic_ns=lambda: now[0]
    ) as workflow:
        approve(workflow, selection(fixture))
        token = workflow.activate(selection(fixture), Factory(), allow)
        with pytest.raises(AccessRegistryError, match=code):
            if api == "descriptor":
                workflow.dispatch_once(
                    token, lambda fd: invoked.append(fd), guard=guard
                )
            else:
                workflow.dispatch_reviewed_once(
                    token, lambda fd, plan, check: invoked.append(fd), guard=guard
                )
        assert invoked == []
        assert bounds[0]._closed
        with pytest.raises(AccessRegistryError, match="TOKEN"):
            workflow.dispatch_once(token, inspect_fd, guard=guard)
