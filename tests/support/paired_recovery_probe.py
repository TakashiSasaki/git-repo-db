"""Actual installed paired lifecycle and safety controls; synthetic catalogs only."""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import os
import runpy
import sqlite3
import subprocess
import sys
import sysconfig
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4


def refuses(call, exception):
    try:
        call()
    except exception as error:
        return error
    raise AssertionError("operation unexpectedly succeeded")


def evidence(directory):
    return {
        p.name: p.read_bytes()
        for p in directory.iterdir()
        if p.is_file()
        and (
            p.name.startswith(("core.sqlite3", "context.sqlite3"))
            or p.name == "p1-recovery-stop.json"
        )
    }


def main(output):
    root = Path(__file__).resolve().parent
    runpy.run_path(str(root / "sitecustomize.py"))
    os.chdir(root)
    from repo_catalog.adapters.sqlite import p1_schema as schema
    from repo_catalog.adapters.sqlite.catalog_runtime import persist_catalog_stop
    from repo_catalog.adapters.sqlite.core_recovery import RecoveryWorkBudget
    from repo_catalog.adapters.sqlite.git_core import GitCore
    from repo_catalog.adapters.sqlite.p1_context import ContextStore
    from repo_catalog.application.core_query import CoreQueryService
    from repo_catalog.application.core_recovery import CoreRecoveryService
    from repo_catalog.application.recovery import RecoveryService
    from repo_catalog.domain.context_admission import (
        AdmissionSelection,
        DependencySet,
        create_local_admission_service,
    )
    from repo_catalog.domain.p1_coordination import CoordinationError
    from repo_catalog.domain.p1_core import NativeObject, native_object_oid
    from repo_catalog.domain.recovery import (
        BackupScope,
        RecoveryBudget,
        RecoveryCapabilityError,
        RecoveryError,
    )
    from repo_catalog.domain.ref_observation import (
        NotesMapping,
        NotesMappingEvidence,
        RefObservation,
        RefObservationClaim,
        RefObservationKey,
        new_uuid7,
    )
    from repo_catalog.domain.shared_values import OID, Provenance

    installed = Path(sysconfig.get_path("purelib")).resolve()
    distributions = {
        d.metadata["Name"]: d
        for d in importlib.metadata.distributions()
        if d.metadata["Name"].startswith("repo-catalog")
    }
    assert set(distributions) == {
        "repo-catalog-paired-recovery",
        "repo-catalog-core",
        "repo-catalog-context",
        "repo-catalog-operational",
        "repo-catalog-search",
        "repo-catalog-runtime",
        "repo-catalog-contracts",
    }
    assert importlib.util.find_spec("httpx") is None
    owners = {}
    for name, distribution in distributions.items():
        for member in distribution.files:
            if str(member).startswith("repo_catalog/"):
                assert str(member) not in owners
                owners[str(member)] = name
    for suffix in (
        "application.acquisition",
        "application.git_acquisition",
        "application.exchange",
        "domain.exchange",
        "application.paired_query",
        "application.production_query",
        "adapters.sqlite.p1_coordination",
        "adapters.sqlite.access_connections",
    ):
        assert importlib.util.find_spec("repo_catalog." + suffix) is None, suffix
    assert (
        owners["repo_catalog/application/recovery.py"] == "repo-catalog-paired-recovery"
    )
    checks = ["resolved_seven_owners_actual_unrelated_absence"]

    def native(kind, body):
        return NativeObject(
            OID("sha1", native_object_oid("sha1", kind, body)),
            kind,
            body,
            len(body),
            hashlib.sha256(body).hexdigest(),
        )

    repository, instance = str(uuid4()), str(uuid4())

    def catalog(name):
        directory = root / name
        directory.mkdir()
        for role in ("core", "context"):
            schema.initialize(
                directory / (role + ".sqlite3"), role, repository, instance
            )
        return directory

    def text(directory, value):
        auth, admission, _ = create_local_admission_service(
            "salvage_merge",
            grants=DependencySet(),
            selection=AdmissionSelection(all_selected=True),
        )
        with closing(schema.connect(directory / "context.sqlite3", "context")) as db:
            store = ContextStore(db, authorization=auth)
            with store.admission_transaction(admission=admission):
                return store.text(value)

    service, scope = RecoveryService(), BackupScope.PAIRED
    source = catalog("source")
    tree = native("tree", b"")
    commit = native(
        "commit",
        (
            f"tree {tree.object_oid.object_oid}\nauthor Fixture <fixture@example.invalid> 1700000000 +0000\ncommitter Fixture <fixture@example.invalid> 1700000000 +0000\n\npaired fixture\n"
        ).encode(),
    )
    with closing(GitCore(source / "core.sqlite3")) as core:
        core.admit_repository(repository)
        core.admit_metadata(tree, str(uuid4()), RecoveryWorkBudget())
        core.admit_metadata(commit, str(uuid4()), RecoveryWorkBudget())
    text(source, "baseline Context text")
    backup = root / "backup"
    receipt = service.create_consistent_backup(source, backup, scope)
    assert receipt.verified_clean and set(receipt.manifest.stores) == {
        "core",
        "context",
    }
    assert receipt.manifest.retained_byte_summary.commit_count == 1
    assert (
        not (source / "operational.sqlite3").exists()
        and not (source / "search.sqlite3").exists()
    )
    checks.append(
        "verified_paired_baseline_actual_metadata_and_context_no_derivative_DBS"
    )

    note = native("blob", b"\0\xffexact recovered Notes\r\n")
    notes_tree = native(
        "tree",
        b"100644 "
        + commit.object_oid.object_oid.encode()
        + b"\0"
        + bytes.fromhex(note.object_oid.object_oid),
    )
    key = RefObservationKey(str(uuid4()), new_uuid7())
    claim = RefObservationClaim(
        key,
        Provenance("source", "read", "original", "fixture", "1"),
        "present",
        root_object_oid=notes_tree.object_oid,
    )
    mapping = NotesMapping(
        notes_tree.object_oid,
        "git-notes",
        "1",
        "native-notes-tree",
        commit.object_oid,
        note.object_oid,
        commit.object_oid.object_oid,
    )
    proof = NotesMappingEvidence(
        claim,
        mapping,
        "single-path",
        Provenance(
            "receiver", "path", "checked", "native-notes", "1", "receiver_intrinsic"
        ),
        (notes_tree,),
    )
    with closing(GitCore(source / "core.sqlite3")) as core:
        core.admit_ref_observation(
            RefObservation(key, repository, b"refs/notes/\xff", "synthetic", "visible")
        )
        core.admit_ref_observation_claim(claim)
        core.admit_ref_note(proof, note, str(uuid4()), RecoveryWorkBudget())

    # Real committed WALs survive abrupt producer exit, without SQLite shutdown
    # cleanup. Product salvage must inspect preserved copies and retain originals.
    worker = r"""
import os,sys
from pathlib import Path
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.domain.shared_values import OID
from repo_catalog.domain.context_admission import AdmissionSelection,DependencySet,create_local_admission_service
directory=Path(sys.argv[1])
if sys.argv[2]=='core':
 core=GitCore(directory/'core.sqlite3');core.admit_object(OID('sha1','9'*40))
else:
 db=connect(directory/'context.sqlite3','context')
 auth,admission,_=create_local_admission_service('salvage_merge',grants=DependencySet(),selection=AdmissionSelection(all_selected=True))
 store=ContextStore(db,authorization=auth)
 with store.admission_transaction(admission=admission):store.text('WAL-only Context text')
os._exit(0)
"""
    for role in ("core", "context"):
        subprocess.run(
            [sys.executable, "-I", "-c", worker, str(source), role],
            check=True,
            timeout=30,
        )
        assert (source / (role + ".sqlite3-wal")).stat().st_size > 32
    service.stop_suspect_catalog(source, "synthetic installed paired incident")
    preserved = evidence(source)
    salvage = root / "salvage.jsonl"
    rescued = service.extract_salvage(
        source, salvage, scope=scope, request_id="paired-extract"
    )
    assert rescued.candidate_count > 0 and evidence(source) == preserved
    refuses(
        lambda: service.create_consistent_backup(
            source, root / "stopped-backup", scope
        ),
        RecoveryError,
    )
    checks.append(
        "read_only_paired_salvage_preserves_real_WALs_and_persistent_source_stop"
    )

    def restored(name):
        target = root / name
        restored_receipt = service.restore_backup(backup, target, repository)
        assert restored_receipt.revalidated_clean and set(
            restored_receipt.revalidated_stores
        ) == {"core", "context"}
        assert (
            not (target / "operational.sqlite3").exists()
            and not (target / "search.sqlite3").exists()
        )
        return target

    refuses(
        lambda: CoreRecoveryService().restore_backup(
            backup, root / "wrong-scope", repository
        ),
        RecoveryCapabilityError,
    )
    assert not (root / "wrong-scope").exists()
    fresh = restored("fresh")
    merged = service.merge_salvage(fresh, salvage, request_id="typed-merge")
    assert merged.admitted_units > 0
    replay = service.merge_salvage(fresh, salvage, request_id="typed-merge")
    assert replay.replayed_units > 0
    body = CoreQueryService(fresh, mode="core_only").read_ref_note_bytes(
        claim, mapping, RecoveryWorkBudget()
    )
    assert body.available and body.verified and body.body_bytes == note.body
    other = replace(
        claim, provenance=replace(claim.provenance, coordinate="unverified-other-claim")
    )
    with closing(GitCore(fresh / "core.sqlite3")) as core:
        core.admit_ref_observation_claim(other)
        recovered_identity = core.catalog_identity()
        assert recovered_identity == (repository, instance)
        assert core.sql("SELECT 1 FROM git_objects WHERE object_oid=?", ("9" * 40,))
    assert (
        not CoreQueryService(fresh, mode="core_only")
        .read_ref_note_bytes(other, mapping, RecoveryWorkBudget())
        .available
    )
    with closing(schema.connect(fresh / "context.sqlite3", "context")) as db:
        assert db.execute(
            "SELECT 1 FROM text_bodies WHERE text_value='WAL-only Context text'"
        ).fetchone()
    checks.append("typed_paired_merge_exact_claim_notes_WAL_text_and_idempotent_replay")

    unbacked = catalog("unbacked")
    before = evidence(unbacked)
    refuses(lambda: service.merge_salvage(unbacked, salvage), RecoveryError)
    refuses(
        lambda: service.activate_catalog(unbacked, root / "unbacked-active"),
        RecoveryError,
    )
    assert evidence(unbacked) == before and not (root / "unbacked-active").exists()
    checks.append("all_family_baseline_guard_before_any_authority_write_or_activation")

    limited = restored("limited")
    budget = RecoveryBudget(max_work_units={"json_decode_bytes": 1})
    partial = service.merge_salvage(
        limited, salvage, budget=budget, request_id="limited"
    )
    assert not partial.input_complete and partial.unprocessed_units > 0
    usage_path = limited / "p1-recovery-request-limited.json"
    usage = json.loads(usage_path.read_text())["cumulative_usage"]
    again = service.merge_salvage(limited, salvage, budget=budget, request_id="limited")
    assert (
        not again.input_complete
        and json.loads(usage_path.read_text())["cumulative_usage"] == usage
    )
    usage_path.unlink()
    refuses(
        lambda: service.merge_salvage(
            limited, salvage, budget=budget, request_id="limited"
        ),
        RecoveryError,
    )
    assert not usage_path.exists() and not service.is_stopped(limited)
    checks.append(
        "finite_partial_work_cumulative_retry_and_lost_external_accounting_refusal"
    )

    for suffix in (".json", ".reserved.json"):
        target = restored("loss-" + ("report" if suffix == ".json" else "reservation"))
        lost = target / ("p1-recovery-request-final" + suffix)
        original = GitCore.close
        removed = []

        def lost_on_close(core):
            original(core)
            if lost.exists():
                lost.unlink()
                removed.append(True)

        with patch.object(GitCore, "close", lost_on_close):
            refuses(
                lambda: service.merge_salvage(target, salvage, request_id="final"),
                RecoveryError,
            )
        assert removed and not lost.exists() and not service.is_stopped(target)
    checks.append(
        "final_owned_cleanup_accounting_loss_refuses_without_repair_or_false_stop"
    )

    missing_capability = catalog("capability")
    original_resource = schema._resource

    def absent_resource(name):
        if name == "search.sql":
            raise FileNotFoundError("synthetic unavailable Search capability")
        return original_resource(name)

    with patch.object(schema, "_resource", absent_resource):
        refuses(
            lambda: service.create_consistent_backup(
                missing_capability, root / "missing-capability", scope
            ),
            RecoveryCapabilityError,
        )
        service.create_consistent_backup(
            missing_capability, root / "git-only", BackupScope.GIT_ONLY
        )
    assert not (root / "missing-capability").exists() and not service.is_stopped(
        missing_capability
    )
    checks.append(
        "missing_paired_reconstruction_capability_refuses_without_git_only_exemption_leak"
    )

    stopped_target = restored("late-stop")
    original_close = GitCore.close

    def stopped_close(core):
        original_close(core)
        persist_catalog_stop(stopped_target, "synthetic installed owned cleanup stop")

    with patch.object(GitCore, "close", stopped_close):
        refuses(
            lambda: service.merge_salvage(stopped_target, salvage), CoordinationError
        )
    assert service.is_stopped(stopped_target)
    checks.append("post_owned_merge_cleanup_stop_fence")

    # A normal failed publication preserves the previous locator; a late stop
    # after committed publication may leave a stopped target, never success.
    locator = root / "active"
    previous = root / "previous"
    previous.mkdir()
    locator.symlink_to(previous)
    refuses(
        lambda: service.activate_catalog(
            fresh, locator, fault_stage="during_locator_replacement"
        ),
        RecoveryError,
    )
    assert locator.resolve() == previous.resolve()
    activation = service.activate_catalog(fresh, locator)
    assert locator.resolve() == fresh.resolve()
    assert activation.clean_operational and set(activation.reconstructed_stores) == {
        "operational",
        "search",
    }
    assert activation.search_derivative_state == "initialized_empty"
    assert (fresh / "p1-recovery-request-typed-merge.json").is_file()
    for role in ("operational", "search"):
        with closing(schema.connect(fresh / (role + ".sqlite3"), role)) as db:
            assert (
                tuple(
                    db.execute(
                        "SELECT repository_uuidv4,catalog_instance_uuidv4 FROM store_identity"
                    ).fetchone()
                )
                == recovered_identity
            )
            if role == "search":
                assert (
                    db.execute("SELECT count(*) FROM search_documents").fetchone()[0]
                    == 0
                )
    assert evidence(source) == preserved and service.is_stopped(source)
    checks.append(
        "verified_activation_reconstructs_O_S_empty_Search_preserves_prior_fault_and_original_source"
    )

    origins = {}
    for name, module in list(sys.modules.items()):
        if name.startswith("repo_catalog.") and getattr(module, "__file__", None):
            path = Path(module.__file__).resolve()
            assert path.is_relative_to(installed), (name, path)
            relative = path.relative_to(installed).as_posix()
            assert relative in owners, (name, relative)
            origins[name] = {"path": str(path), "owner": owners[relative]}
    output.write_text(
        json.dumps(
            {
                "result": "passed",
                "checks": checks,
                "distributions": sorted(distributions),
                "owners": owners,
                "origins": origins,
                "source_evidence": {
                    k: hashlib.sha256(v).hexdigest() for k, v in preserved.items()
                },
                "python": sys.version,
                "sqlite": sqlite3.sqlite_version,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
