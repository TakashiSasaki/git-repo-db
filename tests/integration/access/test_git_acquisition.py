"""A4 actual local Git -> Core, under Access approval and durable request budgets."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.access_native import AccessGitSource
from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.sqlite.access_connections import AccessConnections
from repo_catalog.adapters.sqlite.access_schema import initialize as initialize_access
from repo_catalog.adapters.sqlite.acquisition import (
    InMemoryNotesProgress,
    UnlimitedWorkBudget,
)
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_coordination import persist_catalog_stop
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.application.access_acquisition import AccessGitAcquisition
from repo_catalog.application.access_workflow import AccessWorkflow
from repo_catalog.application.acquisition import GitAcquisition
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
from repo_catalog.domain.acquisition import (
    GitNativeAcquisitionRequest,
    NotesAcquisitionSpec,
)
from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.p1_core import (
    OID,
    Capture,
    CoreFailure,
    Provenance,
    RepositoryClaim,
)
from tests.integration.p5.conftest import build_sample_git_repo, git


@pytest.fixture(params=["sha1", "sha256"])
def setup(tmp_path, request):
    fmt = request.param
    root = tmp_path / "executor"
    root.mkdir(mode=0o700)
    repo = root / "source.git"
    objects = build_sample_git_repo(repo, fmt)
    scope, target, seed, instance = (str(uuid4()) for _ in range(4))
    cat = tmp_path / "catalog"
    cat.mkdir()
    for role in ("core", "operational"):
        initialize(cat / f"{role}.sqlite3", role, seed, instance)
    access = tmp_path / "access.sqlite3"
    initialize_access(access)
    store = AccessConnections(access, writable=True)
    route = ScopeLocatorRegistration(scope, 1, root.as_uri())
    key = AssignmentKey(scope, str(repo), "local")
    store.register_scope(AccessScope(scope, "local"))
    store.register_locator(route)
    store.set_locator_enabled(route, True)
    store.configure_scope(
        ScopeExecutionContext(
            scope,
            canonical(
                {
                    "version": 1,
                    "executor_kind": "local",
                    "executor_ref": "here",
                    "identity_view": "owner",
                    "path_dialect": "posix",
                }
            ),
            True,
        )
    )
    store.bind_repository(RepositoryBinding(scope, str(repo), target, True))
    store.configure_connection(
        ConnectionConfiguration(
            scope,
            "local",
            canonical({"version": 1, "transport": "file", "path_dialect": "posix"}),
            True,
        )
    )
    store.assign_connection(LocatorConnection(key, True))
    selection = AccessSelection(target, scope)
    with AccessWorkflow(store) as workflow:
        workflow.approve(workflow.begin_review(selection), lambda _: True)
    unit = GitNativeAcquisitionRequest(
        target,
        str(uuid4()),
        str(uuid4()),
        "local-fixture",
        1700000000000000,
        select_oids=(objects["commit2"], objects["tree"], objects["tag"]),
    )
    yield dict(
        fmt=fmt,
        root=root,
        repo=repo,
        objects=objects,
        scope=scope,
        target=target,
        seed=seed,
        instance=instance,
        cat=cat,
        access=access,
        store=store,
        route=route,
        key=key,
        selection=selection,
        unit=unit,
    )
    store.close()


def acquire(data, *, unit=None, selection=None, **kwargs):
    return AccessGitAcquisition(data["store"], data["cat"]).acquire(
        selection or data["selection"],
        unit or data["unit"],
        object_format=data["fmt"],
        reviewer=kwargs.pop("reviewer", lambda _: True),
        **kwargs,
    )


def rows(data, table):
    db = connect(data["cat"] / "core.sqlite3", "core")
    try:
        return db.execute(f"SELECT * FROM {table}").fetchall()
    finally:
        db.close()


def usage(data):
    db = connect(data["cat"] / "operational.sqlite3", "operational")
    try:
        return db.execute("SELECT COUNT(*) FROM work_accounting").fetchone()[0]
    finally:
        db.close()


def test_nonseed_repository_acquires_actual_metadata(setup):
    report = acquire(setup, new_request=True)
    assert report.repository_uuidv4 == setup["target"] != setup["seed"]
    assert set(report.retained_objects) == set(setup["unit"].select_oids)
    assert {r[0] for r in rows(setup, "repositories")} == {
        setup["target"],
        setup["seed"],
    }
    core = GitCore(setup["cat"] / "core.sqlite3")
    try:
        assert core.catalog_identity() == (setup["seed"], setup["instance"])
        assert core.read_metadata(setup["objects"]["commit2"]).endswith(
            b"Second commit\n"
        )
    finally:
        core.close()
    assert all(
        r[3] in ("commit", "tree", "tag") for r in rows(setup, "retained_metadata")
    )
    assert rows(setup, "retained_notes") == []
    assert usage(setup) > 0
    assert not (setup["cat"] / "context.sqlite3").exists()


def test_metadata_only_retention_policy(setup):
    unit = replace(setup["unit"], retain_bytes=False)
    report = acquire(setup, unit=unit, new_request=True)
    assert report.retained_objects == ()
    assert rows(setup, "retained_metadata") == []
    assert rows(setup, "scalar_claims")


def test_nonseed_notes_reuse_original_capture_and_budget(setup):
    unit = replace(
        setup["unit"],
        notes=NotesAcquisitionSpec(
            discover_notes=True,
            acquire_inventories=True,
            target_oids=(setup["objects"]["commit2"],),
        ),
    )
    first = acquire(setup, unit=unit, new_request=True)
    before = usage(setup)
    second = acquire(setup, unit=unit)
    assert usage(setup) > before
    assert first.notes_discoveries[0].captures == second.notes_discoveries[0].captures
    assert first.note_acquisitions[0].body_retained
    assert {r[2] for r in rows(setup, "captures")} == {setup["target"]}
    assert len(rows(setup, "retained_notes")) == 1


def test_original_native_replay_does_not_duplicate_facts(setup):
    acquire(setup, new_request=True)
    before = {
        name: rows(setup, name)
        for name in (
            "repositories",
            "git_observations",
            "retained_metadata",
            "coverage_claims",
        )
    }
    count = usage(setup)
    acquire(setup)
    assert usage(setup) > count
    assert before == {name: rows(setup, name) for name in before}


def test_new_request_must_be_explicit(setup):
    with pytest.raises(CoordinationError, match="CONTINUATION_UNAVAILABLE"):
        acquire(setup)
    assert rows(setup, "git_objects") == []


def test_no_approval_no_git_or_request_accounting(setup, monkeypatch):
    setup["store"].revoke_local_approval(setup["key"])
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *_a, **_k: pytest.fail("Git invoked without approval"),
    )
    with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
        acquire(setup, new_request=True)
    assert usage(setup) == 0


def test_decline_activation_leaves_core_and_budget_untouched(setup):
    with pytest.raises(AccessRegistryError, match="DECLINED"):
        acquire(setup, new_request=True, reviewer=lambda _: False)
    assert usage(setup) == 0 and rows(setup, "git_objects") == []


def test_repo_mismatch_before_any_side_effect(setup):
    with pytest.raises(AccessRegistryError, match="REPOSITORY_SCOPE"):
        acquire(
            setup,
            unit=replace(setup["unit"], repository_uuidv4=setup["seed"]),
            new_request=True,
        )
    assert usage(setup) == 0


def test_foreign_repository_claim_rejected_before_admission(setup):
    prov = Provenance("source", "observation", "coordinate", "decoder", "1")
    unit = replace(
        setup["unit"],
        repository_claims=(RepositoryClaim(setup["seed"], "name", "wrong", prov),),
    )
    with pytest.raises(CoreFailure, match="foreign repository"):
        acquire(setup, unit=unit, new_request=True)
    assert usage(setup) == 0 and rows(setup, "repository_claims") == []


def test_foreign_notes_capture_rejected_before_admission(setup):
    cap = Capture(
        str(uuid4()),
        str(uuid4()),
        setup["seed"],
        "source",
        "refs/notes/commits",
        setup["objects"]["notes_commit"],
    )
    unit = replace(setup["unit"], notes=NotesAcquisitionSpec(explicit_captures=(cap,)))
    with pytest.raises(CoreFailure, match="foreign Notes"):
        acquire(setup, unit=unit, new_request=True)
    assert usage(setup) == 0


def test_core_stop_before_activation_blocks_git(setup, monkeypatch):
    persist_catalog_stop(setup["cat"], "synthetic stop")
    monkeypatch.setattr(
        subprocess, "Popen", lambda *_a, **_k: pytest.fail("Git after stop")
    )
    with pytest.raises((CoreFailure, CoordinationError)):
        acquire(setup, new_request=True)
    assert usage(setup) == 0


def test_stop_during_confirmation_blocks_git_and_accounting(setup, monkeypatch):
    def confirm(_):
        persist_catalog_stop(setup["cat"], "stop during local confirmation")
        return True

    monkeypatch.setattr(
        subprocess, "Popen", lambda *_a, **_k: pytest.fail("Git after stop")
    )
    with pytest.raises((CoreFailure, CoordinationError)):
        acquire(setup, new_request=True, reviewer=confirm)
    assert usage(setup) == 0


def test_cancelled_before_source_input(setup, monkeypatch):
    monkeypatch.setattr(
        subprocess, "Popen", lambda *_a, **_k: pytest.fail("Git despite cancel")
    )
    with pytest.raises(CoreFailure, match="cancelled"):
        acquire(setup, new_request=True, cancelled=lambda: True)
    assert usage(setup) == 0


def test_zero_budget_never_starts_git(setup, monkeypatch):
    monkeypatch.setattr(
        subprocess, "Popen", lambda *_a, **_k: pytest.fail("unbudgeted Git")
    )
    with pytest.raises((CoreFailure, CoordinationError)):
        acquire(
            setup,
            new_request=True,
            work_limits={
                "metadata_units": 1,
                "input_bytes": 1,
                "verification_bytes": 1,
                "proof_steps": 1,
            },
        )
    assert rows(setup, "git_objects") == []


def test_access_plan_change_rejected_on_retry_before_git(setup, monkeypatch):
    acquire(setup, new_request=True)
    new = ScopeLocatorRegistration(setup["scope"], 2, setup["root"].as_uri())
    setup["store"].register_locator(new)
    setup["store"].set_locator_enabled(new, True)
    with AccessWorkflow(setup["store"]) as workflow:
        workflow.approve(workflow.begin_review(setup["selection"]), lambda _: True)
    monkeypatch.setattr(
        subprocess, "Popen", lambda *_a, **_k: pytest.fail("retargeted retry")
    )
    with pytest.raises(CoreFailure, match="original request cannot change"):
        acquire(setup)


def test_changed_request_oids_rejected_before_git(setup, monkeypatch):
    acquire(setup, new_request=True)
    monkeypatch.setattr(
        subprocess, "Popen", lambda *_a, **_k: pytest.fail("changed request executed")
    )
    with pytest.raises(CoreFailure, match="original request cannot change"):
        acquire(
            setup,
            unit=replace(setup["unit"], select_oids=(setup["objects"]["commit1"],)),
        )


def test_physical_source_replacement_cannot_resume(setup, monkeypatch):
    acquire(setup, new_request=True)
    old = setup["root"] / "old"
    setup["repo"].rename(old)
    shutil.copytree(old, setup["repo"])
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *_a, **_k: pytest.fail("replacement source consumed"),
    )
    with pytest.raises(CoreFailure, match="original physical source changed"):
        acquire(setup)


def test_wrong_operational_pair_is_not_reinterpreted_as_repository_target(setup):
    op = setup["cat"] / "operational.sqlite3"
    op.unlink()
    initialize(op, "operational", setup["target"], setup["instance"])
    with pytest.raises(CoordinationError, match="STORE_IDENTITY"):
        acquire(setup, new_request=True)


def test_operational_loss_cannot_reset_request_budget(setup):
    acquire(setup, new_request=True)
    op = setup["cat"] / "operational.sqlite3"
    op.unlink()
    initialize(op, "operational", setup["seed"], setup["instance"])
    with pytest.raises(CoordinationError, match="CONTINUATION_UNAVAILABLE"):
        acquire(setup, new_request=True)


def test_ordinary_blob_body_is_never_retained(setup):
    with pytest.raises(CoreFailure):
        acquire(
            setup,
            unit=replace(setup["unit"], select_oids=(setup["objects"]["blob"],)),
            new_request=True,
        )
    assert (
        rows(setup, "retained_metadata") == [] and rows(setup, "retained_notes") == []
    )


def test_promised_missing_metadata_is_not_lazy_fetched(setup, monkeypatch):
    git(setup["repo"], "config", "extensions.partialClone", "origin")
    git(setup["repo"], "config", "remote.origin.promisor", "true")
    marker = setup["root"] / "called"
    git(setup["repo"], "config", "remote.origin.url", "ext::sh -c touch " + str(marker))
    missing = OID(setup["fmt"], "f" * (40 if setup["fmt"] == "sha1" else 64))
    report = acquire(
        setup,
        unit=replace(setup["unit"], select_oids=(missing,), include_refs=False),
        new_request=True,
    )
    assert report.status == "unknown" and report.nominal_missing_objects == (missing,)
    assert not marker.exists()


def test_alternate_object_database_rejected_before_git(setup, monkeypatch):
    (setup["repo"] / "objects/info/alternates").write_text("/another/objects\n")
    monkeypatch.setattr(
        subprocess, "Popen", lambda *_a, **_k: pytest.fail("external alternates input")
    )
    with pytest.raises(CoreFailure, match="unsupported"):
        acquire(setup, new_request=True)


def test_gitdir_pointer_file_is_not_silently_followed(setup, monkeypatch):
    # Turn the reviewed directory into a linked-worktree-like pointer.
    (setup["repo"] / ".git").write_text("gitdir: /outside\n")
    monkeypatch.setattr(
        subprocess, "Popen", lambda *_a, **_k: pytest.fail("gitdir pointer followed")
    )
    with pytest.raises(CoreFailure):
        acquire(setup, new_request=True)


def test_path_config_and_trace_environment_cannot_redirect_input(setup, monkeypatch):
    outside = setup["root"] / "outside.git"
    build_sample_git_repo(outside, setup["fmt"])
    marker = setup["root"] / "trace"
    for key, val in {
        "GIT_DIR": str(outside),
        "GIT_TRACE": str(marker),
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.bare",
        "GIT_CONFIG_VALUE_0": "nonsense",
        "GIT_OBJECT_DIRECTORY": str(outside / "objects"),
    }.items():
        monkeypatch.setenv(key, val)
    report = acquire(setup, new_request=True)
    assert report.retained_objects
    assert not marker.exists()


def test_plain_p5_native_scope_cannot_replay_under_another_repository(setup):
    # Shared request identity with explicit cumulative progress must still bind target.
    source = GitNativeSource(setup["repo"])
    work = UnlimitedWorkBudget()
    progress = InMemoryNotesProgress()
    app = GitAcquisition(setup["cat"])
    app.acquire_from_native(source, setup["unit"], work=work, progress=progress)
    with pytest.raises(CoreFailure, match="request intent changed"):
        app.acquire_from_native(
            source,
            replace(setup["unit"], repository_uuidv4=setup["seed"]),
            work=work,
            progress=progress,
        )


def test_reviewed_request_cannot_be_mutated_by_confirmation_callback(setup):
    original = setup["unit"].select_oids

    def confirm(doc):
        doc["request"]["selected"].clear()
        object.__setattr__(setup["unit"], "select_oids", ())
        return True

    report = acquire(setup, new_request=True, reviewer=confirm)
    assert report.retained_objects == original


def test_actual_source_path_is_self_contained_core_evidence(setup):
    acquire(setup, new_request=True)
    claims = rows(setup, "repository_claims")
    assert len(claims) == 1
    assert claims[0][0:2] == (setup["target"], "git_path")
    assert json.loads(claims[0][2]) == str(setup["repo"])
    assert "actual-local-git-path" in claims[0][3]


def test_worktree_with_local_git_directory_is_supported(setup):
    original = setup["root"] / "original.git"
    setup["repo"].rename(original)
    setup["repo"].mkdir()
    shutil.copytree(original, setup["repo"] / ".git")
    git(setup["repo"], "config", "core.bare", "false")
    report = acquire(setup, new_request=True)
    assert report.retained_objects == setup["unit"].select_oids


@pytest.mark.parametrize(
    "text",
    [
        "[include]\npath=/outside\n",
        '[includeIf "gitdir:/tmp/"]\npath=/outside\n',
        "[Include.path]\nfoo=bar\n",
        "[core]\nworktree=/outside\n",
    ],
)
def test_indirect_config_rejected_before_git(setup, monkeypatch, text):
    with (setup["repo"] / "config").open("a") as stream:
        stream.write(text)
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *_a, **_k: pytest.fail("indirect configuration read"),
    )
    with pytest.raises(CoreFailure, match="unsupported"):
        acquire(setup, new_request=True)


def test_symlink_objects_rejected(setup, monkeypatch):
    actual = setup["root"] / "objects"
    (setup["repo"] / "objects").rename(actual)
    (setup["repo"] / "objects").symlink_to(actual, target_is_directory=True)
    monkeypatch.setattr(
        subprocess, "Popen", lambda *_a, **_k: pytest.fail("object symlink followed")
    )
    with pytest.raises(CoreFailure):
        acquire(setup, new_request=True)


def test_revocation_after_format_probe_stops_before_more_git(setup, monkeypatch):
    original = AccessGitSource._run

    def revoke(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        setup["store"].revoke_local_approval(setup["key"])
        return result

    monkeypatch.setattr(AccessGitSource, "_run", revoke)
    with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
        acquire(setup, new_request=True)
    assert rows(setup, "retained_metadata") == []


def test_stop_after_format_probe_stops_before_more_git(setup, monkeypatch):
    original = AccessGitSource._run

    def stop(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        persist_catalog_stop(setup["cat"], "stop after format probe")
        return result

    monkeypatch.setattr(AccessGitSource, "_run", stop)
    with pytest.raises((CoreFailure, CoordinationError)):
        acquire(setup, new_request=True)
    assert rows(setup, "retained_metadata") == []


def test_changed_configuration_between_commands_is_detected(setup, monkeypatch):
    original = AccessGitSource._run

    def edit(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        with (setup["repo"] / "config").open("a") as stream:
            stream.write("[include]\npath=/outside\n")
        return result

    monkeypatch.setattr(AccessGitSource, "_run", edit)
    with pytest.raises(CoreFailure, match="unsupported or changed"):
        acquire(setup, new_request=True)
    assert rows(setup, "retained_metadata") == []


def test_late_core_stop_cannot_return_success(setup, monkeypatch):
    original = GitAcquisition.acquire_from_native

    def stop(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        persist_catalog_stop(setup["cat"], "stop at result boundary")
        return result

    monkeypatch.setattr(GitAcquisition, "acquire_from_native", stop)
    with pytest.raises((CoreFailure, CoordinationError)):
        acquire(setup, new_request=True)
    assert rows(setup, "retained_metadata")  # Committed prefix is not rolled back.


def test_descriptor_numbers_are_not_resume_identity(setup):
    acquire(setup, new_request=True)
    descriptors = [os.open(os.devnull, os.O_RDONLY) for _ in range(9)]
    try:
        report = acquire(setup)
    finally:
        for descriptor in descriptors:
            os.close(descriptor)
    assert report.retained_objects


def cli_args(setup):
    return [
        "--access-db",
        str(setup["access"]),
        "--catalog",
        str(setup["cat"]),
        "--repository",
        setup["target"],
        "--scope",
        setup["scope"],
        "--capture-origin",
        setup["unit"].capture_origin_uuidv4,
        "--capture",
        setup["unit"].capture_uuidv4,
        "--source-attribution",
        "cli-fixture",
        "--observed-at-us",
        str(setup["unit"].observed_at_us),
        "--object-format",
        setup["fmt"],
        "--oid",
        setup["objects"]["commit2"].full_oid,
        "--new-request",
    ]


def test_cli_noninteractive_cannot_acquire(setup):
    result = subprocess.run(
        [sys.executable, "-m", "repo_catalog.cli.access_acquisition", *cli_args(setup)],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2 and "LOCAL_TTY_REQUIRED" in result.stderr
    assert usage(setup) == 0 and rows(setup, "git_objects") == []


def test_cli_interactive_acquires_actual_git(setup, monkeypatch, capsys):
    from repo_catalog.cli import access_acquisition as cli

    class Input(io.StringIO):
        def isatty(self):
            return True

    class Error(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(
        sys,
        "stdin",
        Input("acquire-local-git " + setup["scope"] + " " + setup["target"] + "\n"),
    )
    monkeypatch.setattr(sys, "stderr", Error())
    assert cli.main(cli_args(setup)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["git_acquired"] is True
    assert result["repository_uuidv4"] == setup["target"]
    assert rows(setup, "retained_metadata")


def test_nonseed_paired_native_notes_preserves_catalog_pairing(setup):
    from repo_catalog.application.acquisition import PairedAcquisitionCoordinator

    initialize(
        setup["cat"] / "context.sqlite3", "context", setup["seed"], setup["instance"]
    )
    unit = replace(
        setup["unit"],
        notes=NotesAcquisitionSpec(discover_notes=True, acquire_inventories=True),
    )
    result = PairedAcquisitionCoordinator(setup["cat"]).admit_paired(
        git_source=GitNativeSource(setup["repo"]), git_request=unit, new_request=True
    )
    assert result.admission.core_committed and result.admission.context_committed
    assert result.git_report.repository_uuidv4 == setup["target"]
    assert rows(setup, "captures")
    db = connect(setup["cat"] / "core.sqlite3", "core")
    try:
        assert tuple(
            db.execute(
                "SELECT repository_uuidv4,catalog_instance_uuidv4 FROM store_identity"
            ).fetchone()
        ) == (setup["seed"], setup["instance"])
    finally:
        db.close()


def test_cli_actual_pty_confirmation_executes_only_after_reply(setup):
    import pty
    import select
    import time

    master, slave = pty.openpty()
    child = subprocess.Popen(
        [sys.executable, "-m", "repo_catalog.cli.access_acquisition", *cli_args(setup)],
        stdin=slave,
        stderr=slave,
        stdout=subprocess.PIPE,
        text=True,
    )
    os.close(slave)
    terminal = bytearray()
    deadline = time.monotonic() + 20
    try:
        while b"Type exactly to confirm" not in terminal:
            assert time.monotonic() < deadline, bytes(terminal)
            if select.select([master], [], [], 0.2)[0]:
                terminal.extend(os.read(master, 8192))
        assert rows(setup, "git_objects") == []
        os.write(
            master,
            (
                "acquire-local-git " + setup["scope"] + " " + setup["target"] + "\n"
            ).encode(),
        )
        output, _ = child.communicate(timeout=30)
        assert child.returncode == 0, bytes(terminal)
        assert json.loads(output)["git_acquired"] is True
        assert rows(setup, "retained_metadata")
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()
        os.close(master)


# R226-02: approved Access must budget display preparation and reuse that
# request's work/progress in actual acquisition, without a second attempt.
def ref_input_request(data, path="reported"):
    from repo_catalog.domain.acquisition import RefNotesInput
    from repo_catalog.domain.ref_observation import (
        NotesMappingGroup,
        RefObservation,
        RefObservationClaim,
        RefObservationKey,
        new_uuid7,
    )

    subject = RefObservation(
        RefObservationKey(str(uuid4()), new_uuid7()),
        data["target"],
        b"refs/notes/external",
        "external",
        "visible",
    )
    report = Provenance("external", "read", "result", "test", "1")
    root = data["objects"]["tree"]
    claim = RefObservationClaim(
        subject.ref_observation_key, report, "present", root_oid=root
    )
    group = NotesMappingGroup(
        claim,
        "git-notes",
        "1",
        "tree",
        "all",
        "complete",
        ((root.full_oid, root.full_oid, path),),
        report,
    )
    return replace(
        data["unit"],
        notes=NotesAcquisitionSpec(
            ref_inputs=(RefNotesInput(subject, (claim,), mapping_groups=(group,)),)
        ),
    )


def test_r226_02_access_preparation_uses_one_cumulative_request(setup, monkeypatch):
    from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger

    original = OperationalAcquisitionLedger.create_budget
    attempts = []

    def create(self, **kw):
        result = original(self, **kw)
        attempts.append(result[1])
        return result

    monkeypatch.setattr(OperationalAcquisitionLedger, "create_budget", create)
    request = ref_input_request(setup)
    acquire(setup, unit=request, new_request=True)
    first = usage(setup)
    acquire(setup, unit=request, new_request=False)
    assert len(attempts) == 2 and len(set(attempts)) == 2
    assert usage(setup) > first
    assert len(rows(setup, "notes_mapping_groups")) == 1
    assert not (setup["cat"] / "p1-recovery-stop.json").exists()


def test_r226_02_access_tiny_budget_stops_before_encoding_or_activation(
    setup, monkeypatch
):
    import repo_catalog.domain.ref_observation as refs

    original = refs.encode
    request = ref_input_request(setup, "x" * 200_000)

    def checked(value):
        result = original(value)
        assert len(result) < 100_000, "unreserved large serialization"
        return result

    monkeypatch.setattr(refs, "encode", checked)

    def no_activation(_):
        pytest.fail("input preparation must fail before executor activation review")

    for fresh in (True, False):
        with pytest.raises(CoreFailure) as failure:
            acquire(
                setup,
                unit=request,
                new_request=fresh,
                work_limits={"input_bytes": 1},
                reviewer=no_activation,
            )
        assert failure.value.code == "BUDGET"
    assert not rows(setup, "ref_observations")
    assert not (setup["cat"] / "p1-recovery-stop.json").exists()
