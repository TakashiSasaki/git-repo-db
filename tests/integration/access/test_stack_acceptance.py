"""A6 cross-stage acceptance: actual Git, inactive restore, reapproval and fork.

Disposable local fixtures only; no remote execution or independent-review claim.
"""

from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.access_backup import AccessBackup
from repo_catalog.adapters.sqlite.access_connections import AccessConnections
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.application.access_maintenance import AccessMaintenance
from repo_catalog.application.access_workflow import AccessWorkflow
from repo_catalog.domain.access_registry import AccessRegistryError
from repo_catalog.domain.access_workflow import AccessSelection
from repo_catalog.domain.p1_core import CoreFailure
from tests.integration.access.test_git_acquisition import acquire, rows, usage
from tests.integration.access.test_git_acquisition import setup as setup


def core_facts(data):
    return {
        table: tuple(tuple(row) for row in rows(data, table))
        for table in (
            "repositories",
            "repository_claims",
            "git_objects",
            "git_observations",
            "ref_observations",
            "retained_metadata",
            "ref_retained_notes",
        )
    }


def approve(store, selected):
    with AccessWorkflow(store) as workflow:
        workflow.approve(workflow.begin_review(selected), lambda _: True)


def restored(data, tmp_path):
    backup = AccessBackup()
    bundle = tmp_path / "bundle"
    destination = tmp_path / "restored"
    backup.backup(data["access"], bundle)
    receipt = backup.restore(bundle, destination)
    assert receipt["local_grants"] == receipt["enabled_routes"] == 0
    return destination / "access.sqlite3"


def test_restore_reapproval_resumes_same_request_without_rewriting_core(
    setup, tmp_path
):
    data = setup
    first = acquire(data, new_request=True)
    original = core_facts(data)
    spent = usage(data)
    with AccessConnections(restored(data, tmp_path), writable=True) as store:
        copy = {**data, "store": store}
        assert store.scope(data["scope"]) == data["store"].scope(data["scope"])
        assert store.history(data["scope"]) == data["store"].history(data["scope"])
        with pytest.raises(AccessRegistryError, match="DISABLED"):
            acquire(copy)
        assert core_facts(data) == original and usage(data) == spent
        store.set_locator_enabled(data["route"], True)
        with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
            acquire(copy)
        assert core_facts(data) == original and usage(data) == spent
        approve(store, data["selection"])
        replay = acquire(copy)
        assert replay.repository_uuidv4 == first.repository_uuidv4
        assert core_facts(data) == original
        assert usage(data) > spent
    # Domain evidence has no dependency on the restored Access database.
    core = GitCore(data["cat"] / "core.sqlite3")
    try:
        assert core.read_metadata(data["objects"]["commit2"]).endswith(
            b"Second commit\n"
        )
    finally:
        core.close()


def test_fork_cannot_retarget_original_request_but_new_capture_can_acquire(
    setup, tmp_path
):
    data = setup
    acquire(data, new_request=True)
    original = core_facts(data)
    access = restored(data, tmp_path)
    target = str(uuid4())
    AccessMaintenance(AccessBackup(), clock_us=lambda: 42).fork_scope(
        access,
        data["scope"],
        data["root"].as_uri(),
        target_scope_uuidv4=target,
    )
    with AccessConnections(access, writable=True) as store:
        assert store.history(data["scope"]).registrations == (data["route"],)
        (registration,) = store.history(target).registrations
        assert registration.registered_at_us == 42
        key = replace(data["key"], scope_uuidv4=target)
        for reader, writer, arguments in (
            (store.scope_context, store.configure_scope, (target,)),
            (store.binding, store.bind_repository, (target, key.locator_text)),
            (
                store.configuration,
                store.configure_connection,
                (target, key.configuration_name),
            ),
            (store.assignment, store.assign_connection, (key,)),
        ):
            value = reader(*arguments)
            assert not value.enabled
            writer(replace(value, enabled=True), expected=value)
        store.set_locator_enabled(registration, True)
        selected = AccessSelection(data["target"], target)
        approve(store, selected)
        copy = {**data, "store": store}
        with pytest.raises(CoreFailure) as error:
            acquire(copy, selection=selected)
        assert error.value.code == "INCOMPATIBLE_REPLAY"
        assert core_facts(data) == original
        fresh = replace(data["unit"], capture_uuidv4=str(uuid4()))
        report = acquire(copy, unit=fresh, selection=selected, new_request=True)
        assert report.repository_uuidv4 == data["target"] != data["seed"]
        assert {row[0] for row in rows(data, "repositories")} == {
            data["target"],
            data["seed"],
        }
        assert not store.locator_enabled(data["route"])
        assert store.history(data["scope"]).registrations == (data["route"],)
        assert store.history(target).registrations == (registration,)


def test_remote_locator_registration_and_rotation_leave_core_facts_unchanged(setup):
    data = setup
    acquire(data, new_request=True)
    original = core_facts(data)
    store = data["store"]
    binding = store.binding(data["scope"], data["key"].locator_text)
    profile = store.configuration(data["scope"], "local")
    assignment = store.assignment(data["key"])
    for kind, locator in (
        ("https", "https://git.example.org/team/app.git"),
        ("ssh", "git@git.example.org:team/app.git"),
    ):
        key = replace(data["key"], locator_text=locator, configuration_name=kind)
        options = '{"transport":"' + kind + '","version":1}'
        new_profile = replace(profile, configuration_name=kind, options_json=options)
        store.bind_repository(replace(binding, locator_text=locator))
        store.configure_connection(new_profile)
        store.assign_connection(replace(assignment, assignment=key))
        store.configure_connection(
            replace(new_profile, enabled=False), expected=new_profile
        )
        assert store.binding(data["scope"], locator).repository_uuidv4 == data["target"]
    assert core_facts(data) == original


@pytest.mark.parametrize("access_state", ["absent", "stopped"])
def test_domain_read_survives_unavailable_access_after_real_acquisition(
    setup, access_state
):
    from repo_catalog.adapters.sqlite.access_schema import persist_stop

    data = setup
    acquire(data, new_request=True)
    original = core_facts(data)
    data["store"].close()
    if access_state == "absent":
        data["access"].unlink()
    else:
        persist_stop(data["access"])
    with pytest.raises(AccessRegistryError, match="MISSING|STOPPED"):
        AccessConnections(data["access"])
    assert core_facts(data) == original
    core = GitCore(data["cat"] / "core.sqlite3")
    try:
        assert core.read_metadata(data["objects"]["commit2"]).endswith(
            b"Second commit\n"
        )
    finally:
        core.close()
