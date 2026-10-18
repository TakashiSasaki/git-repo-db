"""Independent-review regressions: real Git boundaries and selected metadata input."""

from __future__ import annotations

import hashlib
import os
import subprocess
from contextlib import closing
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.filesystem.access_executor import LocalDirectoryExecutor
from repo_catalog.adapters.git.access_native import AccessGitSource
from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.git.notes import GitNotesSource
from repo_catalog.adapters.sqlite.acquisition import (
    InMemoryNotesProgress,
    UnlimitedWorkBudget,
)
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.application.access_workflow import AccessWorkflow
from repo_catalog.application.acquisition import (
    GitAcquisition,
    PairedAcquisitionCoordinator,
)
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.access_registry import AccessRegistryError
from repo_catalog.domain.acquisition import GitMetadataInput, NotesAcquisitionSpec
from repo_catalog.domain.exchange import ExchangeError
from repo_catalog.domain.p1_coordination import CoordinationError, RequestIdentity
from repo_catalog.domain.p1_core import (
    OID,
    Capture,
    CoreCoverageScope,
    CoreFailure,
    GitObservation,
    NotesClaim,
    NotesGroup,
    Provenance,
    RepositoryClaim,
)
from repo_catalog.domain.p1_coverage import CoverageClaim
from tests.integration.access.test_workflow import allow, approve, selection
from tests.integration.access.test_workflow import fixture as fixture
from tests.integration.p5.conftest import build_sample_git_repo, init_catalog_stores


@pytest.mark.parametrize("bom", [b"", b"\xef\xbb\xbf"])
@pytest.mark.parametrize("section", [b"[include]", b'[includeIf "gitdir:/**"]'])
@pytest.mark.parametrize("valid", [True, False])
def test_indirect_git_config_is_rejected_before_any_command(
    tmp_path, monkeypatch, bom, section, valid
):
    repo = tmp_path / "repo.git"
    subprocess.run(["git", "init", "--bare", "-q", str(repo)], check=True)
    outside = tmp_path / "outside.cfg"
    outside.write_bytes(b"[core]\n bare = true\n" if valid else b"INVALID CONFIG\n")
    original = (repo / "config").read_bytes()
    (repo / "config").write_bytes(
        bom + section + b"\n path = " + os.fsencode(outside) + b"\n" + original
    )
    commands = []
    popen = subprocess.Popen

    def record(*args, **kwargs):
        commands.append(args[0])
        return popen(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", record)
    descriptor = os.open(repo, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(CoreFailure) as error:
            AccessGitSource(
                descriptor,
                str(repo),
                object_format="sha1",
                work=UnlimitedWorkBudget(),
                guard=lambda: None,
                bind_identity=lambda _: None,
            )
        assert error.value.code == "EXECUTOR_UNSUPPORTED"
        assert commands == []
    finally:
        os.close(descriptor)


def test_safe_bom_git_config_remains_supported(tmp_path):
    repo = tmp_path / "repo.git"
    subprocess.run(["git", "init", "--bare", "-q", str(repo)], check=True)
    config = repo / "config"
    config.write_bytes(b"\xef\xbb\xbf" + config.read_bytes())
    descriptor = os.open(repo, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with closing(
            AccessGitSource(
                descriptor,
                str(repo),
                object_format="sha1",
                work=UnlimitedWorkBudget(),
                guard=lambda: None,
                bind_identity=lambda _: None,
            )
        ) as source:
            assert source.object_format == "sha1"
    finally:
        os.close(descriptor)


@pytest.mark.parametrize("command", ["bootstrap", "refs"])
def test_git_command_rechecks_guard_after_final_filesystem_preparation(
    tmp_path, monkeypatch, command
):
    repo = tmp_path / "repo.git"
    subprocess.run(["git", "init", "--bare", "-q", str(repo)], check=True)
    stopped, active = [False], [False]
    commands = []
    source = None
    real_stat, real_popen = os.stat, subprocess.Popen
    real_options = AccessGitSource._process_options

    def guard():
        if stopped[0]:
            raise CoreFailure("CANCELLED", "review", "synthetic cancellation")

    def options(self):
        active[0] = True
        try:
            return real_options(self)
        finally:
            active[0] = False

    def stat(path, *args, **kwargs):
        try:
            return real_stat(path, *args, **kwargs)
        finally:
            if active[0] and path == "http-alternates":
                stopped[0] = True

    def popen(*args, **kwargs):
        commands.append(args[0])
        return real_popen(*args, **kwargs)

    descriptor = os.open(repo, os.O_RDONLY | os.O_DIRECTORY)
    before = set(os.listdir("/proc/self/fd"))
    try:
        if command == "refs":
            source = AccessGitSource(
                descriptor,
                str(repo),
                object_format="sha1",
                work=UnlimitedWorkBudget(),
                guard=guard,
                bind_identity=lambda _: None,
            )
        monkeypatch.setattr(AccessGitSource, "_process_options", options)
        monkeypatch.setattr(os, "stat", stat)
        monkeypatch.setattr(subprocess, "Popen", popen)
        with pytest.raises(CoreFailure) as error:
            if source is None:
                source = AccessGitSource(
                    descriptor,
                    str(repo),
                    object_format="sha1",
                    work=UnlimitedWorkBudget(),
                    guard=guard,
                    bind_identity=lambda _: None,
                )
            else:
                source.refs(UnlimitedWorkBudget())
        assert error.value.code == "CANCELLED"
        assert stopped[0]
        assert commands == []
    finally:
        if source is not None:
            source.close()
        assert set(os.listdir("/proc/self/fd")) == before
        os.close(descriptor)


@pytest.mark.parametrize("api", ["descriptor", "reviewed"])
def test_callback_rechecks_cancel_after_final_grant_transaction(
    fixture, monkeypatch, api
):
    store = fixture[0]
    stopped, invoked, bounds = [False], [], []

    class Factory:
        def bind(self, plan):
            bound = LocalDirectoryExecutor().bind(plan)
            bounds.append(bound)
            return bound

    def guard():
        if stopped[0]:
            raise AccessRegistryError("CANCELLED", "synthetic cancellation")

    with AccessWorkflow(store) as workflow:
        approve(workflow, selection(fixture))
        token = workflow.activate(selection(fixture), Factory(), allow)
        original = store._plan
        calls = []

        def plan(*args, **kwargs):
            result = original(*args, **kwargs)
            calls.append(store._db.in_transaction)
            # current_grant constructs both selected and recorded plans. The
            # fourth read belongs to the final handoff transaction.
            if len(calls) == 4:
                stopped[0] = True
            return result

        monkeypatch.setattr(store, "_plan", plan)
        with pytest.raises(AccessRegistryError, match="CANCELLED"):
            if api == "descriptor":
                workflow.dispatch_once(
                    token, lambda fd: invoked.append(fd), guard=guard
                )
            else:
                workflow.dispatch_reviewed_once(
                    token, lambda fd, plan, check: invoked.append(fd), guard=guard
                )
        assert calls == [True] * 4
        assert invoked == []
        assert bounds[0]._closed
        with pytest.raises(AccessRegistryError, match="TOKEN"):
            workflow.dispatch_once(token, lambda fd: None, guard=guard)


def metadata_unit(repository, fmt="sha1"):
    origin, capture = str(uuid4()), str(uuid4())
    provenance = Provenance("external", "original", "slot", "parser", "1")
    oid = OID(fmt, "1" * (40 if fmt == "sha1" else 64))
    return GitMetadataInput(
        repository,
        origin,
        capture,
        "external",
        100,
        object_format=fmt,
        nominal_objects=(oid,),
        repository_claims=(RepositoryClaim(repository, "name", "R1", provenance),),
        observations=(
            GitObservation(
                origin,
                capture,
                repository,
                "acquisition",
                ("original-source",),
                {"source": "external", "observed_at_us": 100, "endpoint": "observed"},
                provenance,
            ),
        ),
    )


def authoritative_rows(directory):
    with closing(connect(directory / "core.sqlite3", "core")) as db:
        return {
            name: db.execute(f'SELECT * FROM "{name}"').fetchall()
            for (name,) in db.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
            )
        }


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("paired", [False, True])
def test_nonseed_external_metadata_preserves_pairing_and_replay(tmp_path, fmt, paired):
    cat = tmp_path / "catalog"
    seed, instance = init_catalog_stores(cat)
    target = str(uuid4())
    unit = metadata_unit(target, fmt)
    service = GitAcquisition(cat, operational=cat)

    def acquire(new_request):
        if paired:
            return (
                PairedAcquisitionCoordinator(cat)
                .admit_paired(git_input=unit, new_request=new_request)
                .git_report
            )
        return service.acquire_metadata_only(unit, new_request=new_request)

    report = acquire(True)
    original = authoritative_rows(cat)
    assert report.repository_uuidv4 == target != seed
    assert report.ref_observations == unit.observations
    assert acquire(False).admitted_objects == unit.nominal_objects
    assert authoritative_rows(cat) == original
    with closing(GitCore(cat / "core.sqlite3")) as core:
        assert core.catalog_identity() == (seed, instance)
    same_seed = tmp_path / "same-seed"
    init_catalog_stores(same_seed, repository_uuidv4=seed)
    package = ExchangeService(cat).export_package()
    ExchangeService(same_seed).import_package(package, work=UnlimitedWorkBudget())
    forwarded = ExchangeService(same_seed).export_package()
    assert forwarded.core["repository_claims"] == package.core["repository_claims"]
    assert forwarded.core["git_observations"] == package.core["git_observations"]
    other = tmp_path / "different-seed"
    init_catalog_stores(other)
    before = authoritative_rows(other)
    # Until an explicit repository-set Exchange contract exists, keep this fence.
    with pytest.raises(ExchangeError) as error:
        ExchangeService(other).import_package(package, work=UnlimitedWorkBudget())
    assert error.value.code == "REPOSITORY_MISMATCH"
    assert authoritative_rows(other) == before


@pytest.mark.parametrize(
    "kind",
    [
        "claim",
        "observation",
        "notes",
        "notes_claim",
        "notes_group",
        "scope",
        "coverage",
        "proof",
    ],
)
@pytest.mark.parametrize("paired", [False, True])
def test_foreign_metadata_repository_is_rejected_before_any_admission(
    tmp_path, kind, paired
):
    cat = tmp_path / "catalog"
    target, _ = init_catalog_stores(cat)
    foreign = str(uuid4())
    unit = metadata_unit(target)
    scope = CoreCoverageScope("repository", (foreign, "git_metadata"))
    claim = CoverageClaim(scope, 100, "partial")
    if kind == "claim":
        unit = replace(unit, repository_claims=metadata_unit(foreign).repository_claims)
    elif kind == "observation":
        unit = replace(unit, observations=metadata_unit(foreign).observations)
    elif kind.startswith("notes"):
        capture = Capture(
            str(uuid4()),
            str(uuid4()),
            foreign,
            "source",
            "refs/notes/x",
            unit.nominal_objects[0],
        )
        spec = NotesAcquisitionSpec(explicit_captures=(capture,))
        if kind == "notes_claim":
            spec = NotesAcquisitionSpec(
                external_claims=(
                    NotesClaim(
                        capture,
                        unit.nominal_objects[0],
                        unit.nominal_objects[0],
                        unit.repository_claims[0].provenance,
                    ),
                )
            )
        elif kind == "notes_group":
            spec = NotesAcquisitionSpec(
                external_groups=(
                    NotesGroup(
                        capture,
                        "all",
                        "known_empty",
                        (),
                        unit.repository_claims[0].provenance,
                    ),
                )
            )
        unit = replace(unit, notes=spec)
    elif kind == "scope":
        unit = replace(unit, coverage_scopes=(scope,))
    elif kind == "coverage":
        unit = replace(unit, coverage_claims=(claim,))
    else:
        unit = replace(
            unit, coverage_proofs=((claim, (), unit.repository_claims[0].provenance),)
        )
    before = authoritative_rows(cat)
    with pytest.raises(CoreFailure) as error:
        if paired:
            PairedAcquisitionCoordinator(cat).admit_paired(
                git_input=unit, new_request=True
            )
        else:
            GitAcquisition(cat, operational=cat).acquire_metadata_only(
                unit, new_request=True
            )
    assert error.value.code == "REPOSITORY_SCOPE"
    assert authoritative_rows(cat) == before


@pytest.mark.parametrize("paired", [False, True])
@pytest.mark.parametrize("owner", ["selected", "foreign", "absent"])
def test_metadata_capture_coverage_resolves_the_actual_capture_owner(
    tmp_path, paired, owner
):
    cat = tmp_path / "catalog"
    target, _ = init_catalog_stores(cat)
    unit = metadata_unit(target)
    capture = Capture(
        str(uuid4()),
        str(uuid4()),
        target if owner == "selected" else str(uuid4()),
        "original",
        "refs/notes/test",
        unit.nominal_objects[0],
    )
    if owner != "absent":
        with closing(GitCore(cat / "core.sqlite3")) as core:
            core.admit_repository(capture.repository_uuidv4)
            core.admit_capture(capture)
    unit = replace(
        unit,
        coverage_scopes=(CoreCoverageScope("capture", (*capture.pair, "inventory")),),
    )
    before = authoritative_rows(cat)

    def acquire():
        if paired:
            return PairedAcquisitionCoordinator(cat).admit_paired(
                git_input=unit, new_request=True
            )
        return GitAcquisition(cat, operational=cat).acquire_metadata_only(
            unit, new_request=True
        )

    if owner == "selected":
        acquire()
        assert authoritative_rows(cat)["captures"] == before["captures"]
    else:
        with pytest.raises(CoreFailure) as error:
            acquire()
        assert error.value.code == "REPOSITORY_SCOPE"
        assert authoritative_rows(cat) == before


def test_metadata_nonseed_keeps_physical_operational_pairing(tmp_path):
    cat, foreign = tmp_path / "catalog", tmp_path / "foreign"
    init_catalog_stores(cat)
    init_catalog_stores(foreign)
    before = authoritative_rows(cat)
    with pytest.raises(CoordinationError) as error:
        GitAcquisition(cat, operational=foreign).acquire_metadata_only(
            metadata_unit(str(uuid4())), new_request=True
        )
    assert error.value.code == "STORE_IDENTITY"
    assert authoritative_rows(cat) == before


def test_metadata_intent_with_explicit_cumulative_progress_contains_no_body(tmp_path):
    cat, repo = tmp_path / "catalog", tmp_path / "input.git"
    seed, _ = init_catalog_stores(cat)
    objects = build_sample_git_repo(repo)
    native = GitNativeSource(repo).metadata(objects["commit2"])
    unit = replace(metadata_unit(seed), native_objects=(native,))
    work, progress = UnlimitedWorkBudget(), InMemoryNotesProgress()
    service = GitAcquisition(cat)
    service.acquire_metadata_only(unit, work=work, progress=progress)
    before = authoritative_rows(cat)
    spent = dict(work.usage)
    service.acquire_metadata_only(unit, work=work, progress=progress)
    assert work.usage["input_bytes"] > spent["input_bytes"]
    assert authoritative_rows(cat) == before
    assert native.body.decode() not in str(progress._store)
    with pytest.raises(CoreFailure) as error:
        service.acquire_metadata_only(
            replace(unit, source_attribution="changed"), work=work, progress=progress
        )
    assert error.value.code == "INCOMPATIBLE_REPLAY"
    assert authoritative_rows(cat) == before


def test_new_explicit_metadata_request_can_add_compatible_same_capture_facts(tmp_path):
    cat = tmp_path / "catalog"
    seed, _ = init_catalog_stores(cat)
    unit = metadata_unit(seed)
    service = GitAcquisition(cat, operational=cat)
    service.acquire_metadata_only(unit, new_request=True)
    extra = OID("sha1", "2" * 40)
    changed = replace(unit, nominal_objects=(*unit.nominal_objects, extra))
    report = service.acquire_metadata_only(
        changed,
        new_request=True,
        request_identity=RequestIdentity(str(uuid4()), str(uuid4())),
    )
    assert report.capture_origin_uuidv4 == unit.capture_origin_uuidv4
    assert report.capture_uuidv4 == unit.capture_uuidv4
    assert report.admitted_objects == changed.nominal_objects


@pytest.mark.parametrize(
    "field",
    ["repository_uuidv4", "source_attribution", "observed_at_us", "nominal_objects"],
)
def test_metadata_retry_cannot_change_original_intent(tmp_path, field):
    cat = tmp_path / "catalog"
    seed, _ = init_catalog_stores(cat)
    unit = metadata_unit(seed)
    service = GitAcquisition(cat, operational=cat)
    service.acquire_metadata_only(unit, new_request=True)
    changes = {
        "repository_uuidv4": str(uuid4()),
        "source_attribution": "other-source",
        "observed_at_us": 101,
        "nominal_objects": (OID("sha1", "2" * 40),),
    }
    changed = replace(unit, **{field: changes[field]})
    if field == "repository_uuidv4":
        changed = replace(changed, repository_claims=(), observations=())
    before = authoritative_rows(cat)
    with pytest.raises((CoreFailure, CoordinationError)) as error:
        service.acquire_metadata_only(changed)
    assert error.value.code in ("INCOMPATIBLE_REPLAY", "REQUEST_SCOPE")
    assert authoritative_rows(cat) == before


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("paired", [False, True])
@pytest.mark.parametrize("nonseed", [False, True])
def test_external_metadata_live_notes_keeps_source_capture_and_budget(
    tmp_path, fmt, paired, nonseed
):
    cat = tmp_path / "catalog"
    seed, instance = init_catalog_stores(cat)
    target = str(uuid4()) if nonseed else seed
    repo = tmp_path / "source.git"
    objects = build_sample_git_repo(repo, fmt)
    source = GitNotesSource(GitNativeSource(repo))
    unit = replace(
        metadata_unit(target, fmt),
        notes=NotesAcquisitionSpec(
            discover_notes=True,
            acquire_inventories=True,
            target_oids=(objects["commit2"],),
        ),
    )
    service = GitAcquisition(cat, operational=cat)

    def acquire(new_request):
        if paired:
            return (
                PairedAcquisitionCoordinator(cat)
                .admit_paired(
                    git_input=unit, notes_source=source, new_request=new_request
                )
                .git_report
            )
        return service.acquire_metadata_only(
            unit, notes_source=source, new_request=new_request
        )

    def expenditure():
        with closing(connect(cat / "operational.sqlite3", "operational")) as db:
            return dict(
                db.execute(
                    "SELECT work_kind,spent_or_reserved FROM request_budgets WHERE request_origin_uuidv4=? AND request_uuidv4=?",
                    (unit.capture_origin_uuidv4, unit.capture_uuidv4),
                )
            )

    first = acquire(True)
    spent = expenditure()
    before = authoritative_rows(cat)
    repeated = acquire(False)
    later = expenditure()
    assert all(later[kind] >= amount for kind, amount in spent.items())
    assert later["metadata_units"] > spent["metadata_units"]
    assert repeated.notes_discoveries[0].captures == first.notes_discoveries[0].captures
    assert first.note_acquisitions[0].body_retained
    capture = first.notes_discoveries[0].captures[0]
    assert capture.repository_uuidv4 == target
    with closing(GitCore(cat / "core.sqlite3")) as core:
        assert core.catalog_identity() == (seed, instance)
        assert (
            core.read_note(capture, objects["commit2"], objects["note_blob"])
            == b"Reviewed-by: CI\n"
        )
    assert authoritative_rows(cat) == before


def test_external_metadata_cannot_switch_notes_source_with_explicit_progress(
    tmp_path, monkeypatch
):
    cat = tmp_path / "catalog"
    seed, _ = init_catalog_stores(cat)
    sources = []
    for name in ("a.git", "b.git"):
        repo = tmp_path / name
        build_sample_git_repo(repo)
        sources.append(GitNotesSource(GitNativeSource(repo)))
    unit = replace(metadata_unit(seed), notes=NotesAcquisitionSpec(discover_notes=True))
    work, progress = UnlimitedWorkBudget(), InMemoryNotesProgress()
    service = GitAcquisition(cat)
    service.acquire_metadata_only(
        unit, notes_source=sources[0], work=work, progress=progress
    )
    before = authoritative_rows(cat)
    monkeypatch.setattr(
        sources[1],
        "discover",
        lambda *args, **kwargs: pytest.fail("changed source was read"),
    )
    with pytest.raises(CoreFailure) as error:
        service.acquire_metadata_only(
            unit, notes_source=sources[1], work=work, progress=progress
        )
    assert error.value.code == "INCOMPATIBLE_REPLAY"
    assert authoritative_rows(cat) == before


@pytest.mark.parametrize("paired", [False, True])
@pytest.mark.parametrize("field", ["repository", "source", "ref", "root"])
def test_metadata_preflights_existing_capture_binding_without_coverage(
    tmp_path, paired, field
):
    cat = tmp_path / "catalog"
    target, _ = init_catalog_stores(cat)
    unit = metadata_unit(target)
    capture = Capture(
        str(uuid4()),
        str(uuid4()),
        str(uuid4()) if field == "repository" else target,
        "reported-source",
        "refs/notes/original",
        unit.nominal_objects[0],
    )
    with closing(GitCore(cat / "core.sqlite3")) as core:
        core.admit_repository(capture.repository_uuidv4)
        core.admit_capture(capture)
    changes = {
        "repository": {"repository_uuidv4": target},
        "source": {"source": "other-original-source"},
        "ref": {"ref": "refs/notes/other"},
        "root": {"root": OID("sha1", "2" * 40)},
    }
    candidate = replace(capture, **changes[field])
    unit = replace(unit, notes=NotesAcquisitionSpec(explicit_captures=(candidate,)))
    before = authoritative_rows(cat)
    with pytest.raises(CoreFailure) as error:
        if paired:
            PairedAcquisitionCoordinator(cat).admit_paired(
                git_input=unit, new_request=True
            )
        else:
            GitAcquisition(cat, operational=cat).acquire_metadata_only(
                unit, new_request=True
            )
    assert error.value.code == (
        "REPOSITORY_SCOPE" if field == "repository" else "INCOMPATIBLE_REPLAY"
    )
    assert authoritative_rows(cat) == before


@pytest.mark.parametrize("paired", [False, True])
@pytest.mark.parametrize(
    "damage", ["source", "utf8", "ref", "oid", "repository_parent", "root_parent"]
)
def test_stored_capture_corruption_stops_before_any_metadata_admission(
    tmp_path, paired, damage
):
    cat = tmp_path / "catalog"
    seed, _ = init_catalog_stores(cat)
    unit = metadata_unit(seed)
    capture = Capture(
        str(uuid4()),
        str(uuid4()),
        seed,
        "original",
        "refs/notes/test",
        unit.nominal_objects[0],
    )
    with closing(GitCore(cat / "core.sqlite3")) as core:
        core.admit_capture(capture)
    with closing(connect(cat / "core.sqlite3", "core")) as db:
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("PRAGMA ignore_check_constraints=ON")
        table = {"repository_parent": "repositories", "root_parent": "git_objects"}.get(
            damage, "captures"
        )
        action = "update" if table == "captures" else "delete"
        trigger = f"p1_immutable_{table}_{action}"
        sql = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name=?", (trigger,)
        ).fetchone()[0]
        db.execute(f"DROP TRIGGER {trigger}")
        if damage == "source":
            db.execute("UPDATE captures SET source=''")
        elif damage == "utf8":
            db.execute("UPDATE captures SET source=CAST(X'ff' AS TEXT)")
        elif damage == "ref":
            db.execute('UPDATE captures SET ref=\'["wrong","00"]\'')
        elif damage == "oid":
            db.execute("UPDATE captures SET root='invalid'")
        elif damage == "repository_parent":
            db.execute("DELETE FROM repositories WHERE repository_uuidv4=?", (seed,))
        else:
            db.execute(
                "DELETE FROM git_objects WHERE object_format=? AND full_oid=?",
                capture.root.key,
            )
        db.execute(sql)
        db.commit()
    # The synthetic attack restores the exact trusted physical schema. Only
    # domain data/FKs are damaged; rejection cannot rely on schema drift.
    path = cat / "core.sqlite3"
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    unit = replace(unit, notes=NotesAcquisitionSpec(explicit_captures=(capture,)))
    with pytest.raises(CoreFailure) as error:
        if paired:
            PairedAcquisitionCoordinator(cat).admit_paired(
                git_input=unit, new_request=True
            )
        else:
            GitAcquisition(cat, operational=cat).acquire_metadata_only(
                unit, new_request=True
            )
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (cat / "p1-recovery-stop.json").exists()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
