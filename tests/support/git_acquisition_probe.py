"""Stdlib-only real installed local/Access Git acquisition consumer."""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
import runpy
import sqlite3
import sys
import sysconfig
from contextlib import ExitStack, closing, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4


def refuses(call, classes, codes=None):
    try:
        call()
    except classes as error:
        if codes is not None:
            assert error.code in codes, (type(error), str(error), codes)
        return error
    raise AssertionError("operation unexpectedly succeeded")


def main(output):
    root = Path(__file__).resolve().parent
    runpy.run_path(str(root / "sitecustomize.py"))
    os.environ["PYTHONPATH"] = str(root)
    data = json.loads((root / "fixture.json").read_text())
    access = data["access"]
    from repo_catalog.adapters.git.native import GitNativeSource
    from repo_catalog.adapters.sqlite.acquisition import (
        InMemoryNotesProgress,
        OperationalAcquisitionLedger,
    )
    from repo_catalog.adapters.sqlite.catalog_runtime import persist_catalog_stop
    from repo_catalog.adapters.sqlite.git_core import GitCore
    from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
    from repo_catalog.application.core_query import CoreQueryService
    from repo_catalog.application.git_acquisition import GitAcquisition
    from repo_catalog.domain.git_acquisition import (
        GitNativeAcquisitionRequest,
        NotesAcquisitionSpec,
    )
    from repo_catalog.domain.p1_coordination import (
        CoordinationError,
        NotesLimits,
        RequestIdentity,
    )
    from repo_catalog.domain.query_work import UnlimitedWorkBudget
    from repo_catalog.domain.ref_observation import NotesMapping
    from repo_catalog.domain.shared_values import OID, CoreFailure

    installed = Path(sysconfig.get_path("purelib")).resolve()
    distributions = {
        d.metadata["Name"]: d
        for d in importlib.metadata.distributions()
        if d.metadata["Name"].startswith("repo-catalog")
    }
    expected = {
        "repo-catalog-core",
        "repo-catalog-git-acquisition",
        "repo-catalog-operational",
        "repo-catalog-runtime",
        "repo-catalog-contracts",
    }
    if access:
        expected.add("repo-catalog-access")
    assert set(distributions) == expected, set(distributions)
    owners = {}
    for name, distribution in distributions.items():
        for member in distribution.files:
            if str(member).startswith("repo_catalog/"):
                assert str(member) not in owners, member
                owners[str(member)] = name
    assert not importlib.util.find_spec("httpx")
    for module in (
        "application.acquisition",
        "domain.acquisition",
        "domain.p1_context",
        "domain.search_query",
        "application.exchange",
        "application.recovery",
        "application.paired_query",
        "application.production_query",
        "adapters.sqlite.p1_coordination",
        "adapters.sqlite.production_context",
        "cli.main",
    ):
        assert importlib.util.find_spec("repo_catalog." + module) is None, module
    if not access:
        assert (
            importlib.util.find_spec("repo_catalog.adapters.sqlite.access_schema")
            is None
        )
    else:
        assert not distributions["repo-catalog-access"].requires
    checks = ["resolved_five_or_six_owners_actual_optional_absence"]
    source_path = root / "executor/source.git"
    source = GitNativeSource(source_path)
    objects = {name: OID(*value) for name, value in data["objects"].items()}

    def catalog(name, *, operational=True):
        directory = root / name
        directory.mkdir()
        repository, instance = str(uuid4()), str(uuid4())
        initialize(directory / "core.sqlite3", "core", repository, instance)
        if operational:
            initialize(
                directory / "operational.sqlite3", "operational", repository, instance
            )
        return directory, repository, instance

    def unit(repository, *, notes=False):
        return GitNativeAcquisitionRequest(
            repository,
            str(uuid4()),
            str(uuid4()),
            "synthetic-local",
            1700000000000000,
            select_object_oids=(objects["commit2"],),
            include_refs=notes,
            notes=NotesAcquisitionSpec(
                discover_notes=True,
                acquire_inventories=True,
                target_object_oids=(objects["commit2"],),
            )
            if notes
            else None,
        )

    target, seed, instance = catalog("catalog")
    repository = str(uuid4()) if access else seed
    request = unit(repository, notes=True)
    stack = ExitStack()
    try:
        if access:
            from repo_catalog.adapters.sqlite.access_connections import (
                AccessConnections,
            )
            from repo_catalog.adapters.sqlite.access_schema import (
                initialize as initialize_access,
            )
            from repo_catalog.application.access_acquisition import AccessGitAcquisition
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

            access_path = root / "access.sqlite3"
            initialize_access(access_path)
            store = stack.enter_context(AccessConnections(access_path, writable=True))
            scope = str(uuid4())
            route = ScopeLocatorRegistration(scope, 1, (root / "executor").as_uri())
            key = AssignmentKey(scope, str(source_path), "local")
            store.register_scope(AccessScope(scope, "synthetic"))
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
            store.bind_repository(
                RepositoryBinding(scope, str(source_path), repository, True)
            )
            store.configure_connection(
                ConnectionConfiguration(
                    scope,
                    "local",
                    canonical(
                        {"version": 1, "transport": "file", "path_dialect": "posix"}
                    ),
                    True,
                )
            )
            store.assign_connection(LocatorConnection(key, True))
            selection = AccessSelection(repository, scope)
            service = AccessGitAcquisition(store, target)

            def acquire(value=request, *, new=False):
                return service.acquire(
                    selection,
                    value,
                    object_format="sha1",
                    reviewer=lambda _document: True,
                    new_request=new,
                )

            with patch(
                "subprocess.Popen", side_effect=AssertionError("unapproved Git command")
            ):
                refuses(lambda: acquire(new=True), AccessRegistryError)

            def approve():
                with AccessWorkflow(store) as workflow:
                    workflow.approve(
                        workflow.begin_review(selection), lambda _document: True
                    )

            approve()
            checks.append("exact_scope_and_assignment_approval_before_git")
        else:
            service = GitAcquisition(target, operational=target)

            def acquire(value=request, *, new=False):
                return service.acquire_from_native(source, value, new_request=new)

        report = acquire(new=True)
        assert (
            report.status == "complete"
            and report.ref_enumerations
            and report.ref_note_acquisitions
        )
        assert objects["commit2"] in report.retained_objects
        reader = CoreQueryService(target)
        body = reader.read_metadata_bytes(objects["commit2"])
        assert (
            body.available
            and body.verified
            and body.body_bytes.hex() == data["commit_hex"]
        )
        with closing(GitCore(target / "core.sqlite3")) as core:
            assert core.sql("SELECT count(*) FROM ref_retained_notes")[0][0] > 0
            assert not core.sql(
                "SELECT 1 FROM retained_metadata WHERE object_format=? AND object_oid=?",
                objects["blob"].key,
            )
        assert (
            not (target / "context.sqlite3").exists()
            and not (target / "search.sqlite3").exists()
        )
        checks.append("real_local_metadata_refs_notes_actual_bytes_no_file_archive")

        with closing(connect(target / "operational.sqlite3", "operational")) as db:
            spent = dict(
                db.execute(
                    "SELECT work_kind,sum(spent_or_reserved) FROM request_budgets GROUP BY work_kind"
                )
            )
        retry = acquire()
        assert (
            retry.status == "complete"
            and retry.ref_enumerations == report.ref_enumerations
        )
        with closing(connect(target / "operational.sqlite3", "operational")) as db:
            after = dict(
                db.execute(
                    "SELECT work_kind,sum(spent_or_reserved) FROM request_budgets GROUP BY work_kind"
                )
            )
            assert all(after[k] >= value for k, value in spent.items())
            assert any(after[k] > value for k, value in spent.items())
        changed = replace(request, select_object_oids=(objects["commit1"],))
        with patch(
            "subprocess.Popen", side_effect=AssertionError("changed retry reached Git")
        ):
            refuses(lambda: acquire(changed), (CoreFailure, CoordinationError))
        assert not (target / "p1-recovery-stop.json").exists()
        checks.append("original_ref_identity_frozen_intent_and_cumulative_retry")

        # Claim-local retained-byte evidence cannot be borrowed by another report.
        note = next(
            value for value in report.ref_note_acquisitions if value.body_retained
        )
        group = next(
            value.group
            for value in report.ref_notes_inventories
            if value.group.ref_claim == note.claim
        )
        member = next(
            value
            for value in group.members
            if value[0] == note.target.object_oid and value[1] == note.note.object_oid
        )
        mapping = NotesMapping(
            note.claim.root_object_oid,
            group.interpretation_kind,
            group.interpretation_version,
            group.interpretation_scope,
            note.target,
            note.note,
            member[2],
        )
        with OperationalAcquisitionLedger(target / "operational.sqlite3") as ledger:
            _, _, work, _ = ledger.create_budget(
                scope=["synthetic-claim-check"], new_request=True
            )
            verified = reader.read_ref_note_bytes(note.claim, mapping, work)
            assert (
                verified.available
                and verified.verified
                and verified.body_bytes.hex() == data["note_hex"]
            )
            other = replace(
                note.claim,
                provenance=replace(
                    note.claim.provenance,
                    coordinate="other-unverified-synthetic-report",
                ),
            )
            with closing(GitCore(target / "core.sqlite3")) as core:
                core.admit_ref_observation_claim(other)
            unavailable = reader.read_ref_note_bytes(other, mapping, work)
            assert not unavailable.available and not unavailable.verified
        checks.append("exact_claim_notes_eligibility_and_unverified_report")

        if access:
            from repo_catalog.adapters.git.access_native import AccessGitSource

            # Revoke after a real bounded format command, before the next command.
            original = AccessGitSource._run
            calls = 0

            def revoked(native, *args, **kwargs):
                nonlocal calls
                result = original(native, *args, **kwargs)
                calls += 1
                store.revoke_local_approval(key)
                return result

            with patch.object(AccessGitSource, "_run", revoked):
                refuses(
                    lambda: acquire(unit(repository), new=True), AccessRegistryError
                )
            assert calls == 1
            approve()
            store.set_locator_enabled(route, False)
            store.set_locator_enabled(route, True)
            with patch(
                "subprocess.Popen", side_effect=AssertionError("ABA grant reused")
            ):
                refuses(
                    lambda: acquire(unit(repository), new=True), AccessRegistryError
                )
            approve()
            next_route = ScopeLocatorRegistration(
                scope, 2, (root / "executor").as_uri()
            )
            store.register_locator(next_route)
            store.set_locator_enabled(next_route, True)
            approve()
            with patch(
                "subprocess.Popen",
                side_effect=AssertionError("frozen route retargeted"),
            ):
                refuses(lambda: acquire(), CoreFailure)
            assert not (target / "p1-recovery-stop.json").exists()
            checks.append("current_authorization_revocation_ABA_and_frozen_access_plan")

            from repo_catalog.cli import access_acquisition as cli

            class TTY(io.StringIO):
                def isatty(self):
                    return True

            argv = [
                "--access-db",
                str(access_path),
                "--catalog",
                str(target),
                "--repository",
                repository,
                "--scope",
                scope,
                "--capture-origin",
                str(uuid4()),
                "--capture",
                str(uuid4()),
                "--source-attribution",
                "synthetic-cli",
                "--observed-at-us",
                "1700000000000000",
                "--object-format",
                "sha1",
                "--object-oid",
                objects["commit2"].object_oid,
                "--notes",
                "--note-target",
                objects["commit2"].object_oid,
                "--new-request",
            ]
            captured = io.StringIO()
            with (
                patch.object(
                    sys,
                    "stdin",
                    TTY("acquire-local-git " + scope + " " + repository + "\n"),
                ),
                patch.object(sys, "stderr", TTY()),
                redirect_stdout(captured),
            ):
                assert cli.main(argv) == 0
            cli_result = json.loads(captured.getvalue())
            assert cli_result["git_acquired"] and cli_result["status"] == report.status
            assert sorted(cli_result["retained_objects"]) == sorted(
                list(value.key) for value in report.retained_objects
            )
            assert cli_result["retained_notes_count"] == len(
                {
                    value.note
                    for value in report.ref_note_acquisitions
                    if value.body_retained and value.note is not None
                }
            )
            checks.append("existing_interactive_cli_actual_acquisition_api_parity")
        else:
            from repo_catalog.cli import access_acquisition as cli

            stderr = io.StringIO()
            argv = [
                "--access-db",
                "absent-access.sqlite3",
                "--catalog",
                str(target),
                "--repository",
                repository,
                "--scope",
                str(uuid4()),
                "--capture-origin",
                str(uuid4()),
                "--capture",
                str(uuid4()),
                "--source-attribution",
                "synthetic",
                "--observed-at-us",
                "1700000000000000",
                "--object-format",
                "sha1",
            ]
            with patch.object(sys, "stderr", stderr):
                assert cli.main(argv) == 2
            assert json.loads(stderr.getvalue())["code"] == "MISSING_CAPABILITY"
            assert not (root / "absent-access.sqlite3").exists()
            assert not any(
                name.startswith(
                    (
                        "repo_catalog.application.access_workflow",
                        "repo_catalog.adapters.filesystem.access_executor",
                        "repo_catalog.adapters.sqlite.access_connections",
                    )
                )
                for name in sys.modules
            )
            checks.append("no_saved_settings_resolver_or_access_cli_fallback")

        # Every native path, including constructor overrides, requires actual O.
        missing, missing_repo, _ = catalog("missing-operational", operational=False)
        with patch("subprocess.Popen", side_effect=AssertionError("Git without O")):
            refuses(
                lambda: GitAcquisition(
                    missing, operational=missing
                ).acquire_from_native(source, unit(missing_repo), new_request=True),
                CoordinationError,
                {"CONTINUATION_UNAVAILABLE"},
            )
            refuses(
                lambda: GitAcquisition(missing).acquire_from_native(
                    source,
                    unit(missing_repo),
                    work=UnlimitedWorkBudget(),
                    progress=InMemoryNotesProgress(),
                ),
                CoordinationError,
                {"CONTINUATION_UNAVAILABLE"},
            )
        assert not (missing / "operational.sqlite3").exists()
        assert not (missing / "p1-recovery-stop.json").exists()
        checks.append("durable_required_no_volatile_shortcut_or_implicit_O")

        bounded, bounded_repo, bounded_instance = catalog("bounded")
        bounded_request = unit(bounded_repo)
        request_id = RequestIdentity(
            bounded_request.capture_origin_uuidv4, bounded_request.capture_uuidv4
        )
        bound_scope = ["p5-git-native", bounded_repo, *request_id.values()]
        with OperationalAcquisitionLedger(bounded / "operational.sqlite3") as ledger:
            _, _, work, progress = ledger.create_budget(
                scope=bound_scope,
                request=request_id,
                new_request=True,
                work_limits={name: 0 for name in NotesLimits.work_limits()},
            )
            with patch(
                "subprocess.Popen", side_effect=AssertionError("unreserved Git")
            ):
                refuses(
                    lambda: GitAcquisition(bounded).acquire_from_native(
                        source, bounded_request, work=work, progress=progress
                    ),
                    CoreFailure,
                    {"BUDGET"},
                )
            with patch(
                "subprocess.Popen",
                side_effect=AssertionError("constructor progress bypass"),
            ):
                refuses(
                    lambda: GitAcquisition(
                        bounded, operational=bounded, progress=InMemoryNotesProgress()
                    ).acquire_from_native(source, bounded_request),
                    CoordinationError,
                    {"CONTINUATION_UNAVAILABLE"},
                )
        assert not (bounded / "p1-recovery-stop.json").exists()
        checks.append("prework_zero_budget_and_effective_constructor_capability")

        loss, loss_repo, loss_instance = catalog("lost-accounting")
        loss_request = unit(loss_repo)
        loss_service = GitAcquisition(loss, operational=loss)
        assert (
            loss_service.acquire_from_native(
                source, loss_request, new_request=True
            ).status
            == "complete"
        )
        with closing(connect(loss / "operational.sqlite3", "operational")) as db:
            db.execute("DELETE FROM request_continuations")
        with patch(
            "subprocess.Popen", side_effect=AssertionError("Git after partial O loss")
        ):
            refuses(
                lambda: loss_service.acquire_from_native(source, loss_request),
                CoordinationError,
                {"CONTINUATION_UNAVAILABLE"},
            )
        (loss / "operational.sqlite3").unlink()
        initialize(
            loss / "operational.sqlite3", "operational", loss_repo, loss_instance
        )
        with patch("subprocess.Popen", side_effect=AssertionError("old request reset")):
            refuses(
                lambda: loss_service.acquire_from_native(
                    source, loss_request, new_request=True
                ),
                CoordinationError,
                {"CONTINUATION_UNAVAILABLE"},
            )
        assert (
            loss_service.acquire_from_native(
                source, unit(loss_repo), new_request=True
            ).status
            == "complete"
        )
        assert not (loss / "p1-recovery-stop.json").exists()
        checks.append("partial_whole_O_loss_old_request_refusal_genuine_new_request")

        callback, callback_repo, _ = catalog("callback-error")
        marker = json.JSONDecodeError("external native input callback", "", 0)
        with patch.object(source, "metadata", side_effect=marker):
            error = refuses(
                lambda: GitAcquisition(
                    callback, operational=callback
                ).acquire_from_native(source, unit(callback_repo), new_request=True),
                json.JSONDecodeError,
            )
        assert error is marker and not (callback / "p1-recovery-stop.json").exists()
        checks.append("input_callback_exception_identity_no_false_corruption_stop")

        opaque, opaque_repo, _ = catalog("opaque-optional")
        for role in ("context", "search"):
            (opaque / (role + ".sqlite3")).write_bytes(b"opaque unused optional state")
        before = {
            role: hashlib.sha256(
                (opaque / (role + ".sqlite3")).read_bytes()
            ).hexdigest()
            for role in ("context", "search")
        }
        assert (
            GitAcquisition(opaque, operational=opaque)
            .acquire_from_native(source, unit(opaque_repo), new_request=True)
            .status
            == "complete"
        )
        assert before == {
            role: hashlib.sha256(
                (opaque / (role + ".sqlite3")).read_bytes()
            ).hexdigest()
            for role in before
        }
        checks.append("explicit_local_mode_ignores_opaque_context_search")

        # Challenge completion after owned Core cleanup in the actual package.
        fenced, fenced_repo, _ = catalog("cleanup-stop")
        original_close = GitCore.close

        def stopped(core):
            original_close(core)
            persist_catalog_stop(fenced, "synthetic installed cleanup stop")

        with patch.object(GitCore, "close", stopped):
            refuses(
                lambda: GitAcquisition(fenced, operational=fenced).acquire_from_native(
                    source, unit(fenced_repo), new_request=True
                ),
                CoordinationError,
                {"RECOVERY_REQUIRED"},
            )
        assert (fenced / "p1-recovery-stop.json").exists()
        checks.append("owned_cleanup_final_catalog_completion_fence")
    finally:
        stack.close()

    origins = {}
    for name, module in tuple(sys.modules.items()):
        if name == "repo_catalog" or name.startswith("repo_catalog."):
            for location in getattr(module, "__path__", ()):
                assert Path(location).resolve().is_relative_to(installed), name
            filename = getattr(module, "__file__", None)
            if filename:
                origin = Path(filename).resolve()
                assert origin.is_relative_to(installed), (name, origin)
                relative = origin.relative_to(installed).as_posix()
                assert relative in owners, relative
                origins[name] = {"path": str(origin), "owner": owners[relative]}
    assert not any(
        name in sys.modules
        for name in (
            "repo_catalog.domain.p1_context",
            "repo_catalog.application.acquisition",
            "repo_catalog.domain.search_query",
            "repo_catalog.application.paired_query",
        )
    )
    Path(output).write_text(
        json.dumps(
            {
                "result": "passed",
                "checks": checks,
                "access": access,
                "installed_distributions": sorted(distributions),
                "origins": origins,
                "python": sys.version,
                "sqlite": sqlite3.sqlite_version,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main(sys.argv[1])
