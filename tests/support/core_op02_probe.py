"""Stdlib-only installed OP-02 checks on disposable synthetic catalogs.

Copied outside the checkout and run with isolated Python. Context evidence is
opaque, and no optional fixture, adapter, high-level Exchange or pytest is used.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import os
import runpy
import shutil
import socket
import sqlite3
import sys
import sysconfig
from contextlib import closing
from pathlib import Path
from uuid import uuid4


def refuses(callback, exception):
    try:
        callback()
    except exception as error:
        return error
    raise AssertionError("operation unexpectedly succeeded")


def evidence_files(directory):
    return {
        path.name: path.read_bytes()
        for path in directory.iterdir()
        if path.is_file()
        and (
            path.name.startswith(("core.sqlite3", "context.sqlite3"))
            or path.name == "p1-recovery-stop.json"
        )
    }


def only_core(directory):
    assert sorted(path.name for path in directory.glob("*.sqlite3")) == ["core.sqlite3"]


def main(output):
    harness = Path(__file__).resolve().parent
    runpy.run_path(str(harness / "sitecustomize.py"))
    os.environ["PYTHONPATH"] = str(harness)
    refuses(lambda: socket.getaddrinfo("outside.example.invalid", 443), PermissionError)

    from repo_catalog.adapters.sqlite import core_recovery as adapter_module
    from repo_catalog.adapters.sqlite import p1_schema as schema
    from repo_catalog.adapters.sqlite.core_recovery import RecoveryWorkBudget
    from repo_catalog.adapters.sqlite.git_core import GitCore
    from repo_catalog.application.core_recovery import CoreRecoveryService
    from repo_catalog.domain.p1_core import NativeObject, native_object_oid
    from repo_catalog.domain.recovery import (
        ActivationError,
        BackupScope,
        CatalogStoppedError,
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

    checks = []
    installed = Path(sysconfig.get_path("purelib")).resolve()
    distributions = {
        item.metadata["Name"]: item
        for item in importlib.metadata.distributions()
        if item.metadata["Name"].startswith("repo-catalog")
    }
    assert set(distributions) == {"repo-catalog-core", "repo-catalog-contracts"}
    owners = {}
    for name, distribution in distributions.items():
        for member in distribution.files:
            if str(member).startswith("repo_catalog/"):
                assert str(member) not in owners, str(member)
                owners[str(member)] = name
    assert importlib.util.find_spec("httpx") is None
    absent = (
        "application.recovery",
        "adapters.sqlite.recovery",
        "adapters.sqlite.recovery_context",
        "adapters.sqlite.recovery_validation",
        "adapters.sqlite.p1_context",
        "adapters.sqlite.production_context",
        "adapters.sqlite.p1_coordination",
        "domain.ports.p1_coordination",
        "adapters.sqlite.acquisition",
        "adapters.sqlite.search",
        "adapters.sqlite.access_schema",
        "application.acquisition",
        "application.ref_observations",
        "application.exchange",
        "application.ref_exchange",
        "domain.exchange",
    )
    for suffix in absent:
        assert importlib.util.find_spec("repo_catalog." + suffix) is None, suffix
    origins = {}
    for suffix in (
        "application.core_recovery",
        "adapters.sqlite.core_recovery",
        "adapters.sqlite.core_recovery_validation",
        "adapters.sqlite.recovery_budget",
        "adapters.sqlite.ref_salvage",
        "domain.recovery",
        "domain.ref_exchange",
        "application.ref_reconstruction",
    ):
        module = importlib.import_module("repo_catalog." + suffix)
        path = Path(module.__file__).resolve()
        assert path.is_relative_to(installed), path
        assert path.relative_to(installed).as_posix() in owners, path
        origins[suffix] = str(path)
    checks.append("physical_absence_unique_owners_and_installed_origins")

    def native(kind, body):
        return NativeObject(
            OID("sha1", native_object_oid("sha1", kind, body)),
            kind,
            body,
            len(body),
            hashlib.sha256(body).hexdigest(),
        )

    def new_catalog(name):
        directory = Path(name).resolve()
        directory.mkdir()
        repository, instance = str(uuid4()), str(uuid4())
        schema.initialize(directory / "core.sqlite3", "core", repository, instance)
        with closing(GitCore(directory / "core.sqlite3")) as core:
            core.admit_repository(repository)
        only_core(directory)
        return directory, repository

    service = CoreRecoveryService()
    scope = BackupScope.GIT_ONLY
    source, repository = new_catalog("source")
    tree = native("tree", b"")
    commit = native(
        "commit",
        (
            f"tree {tree.object_oid.object_oid}\n"
            "author Fixture <fixture@example.invalid> 1700000000 +0000\n"
            "committer Fixture <fixture@example.invalid> 1700000000 +0000\n\n"
            "installed recovery\n"
        ).encode(),
    )
    with closing(GitCore(source / "core.sqlite3")) as core:
        work = RecoveryWorkBudget()
        core.admit_metadata(tree, str(uuid4()), work)
        core.admit_metadata(commit, str(uuid4()), work)
    backup = Path("baseline").resolve()
    backup_receipt = service.create_consistent_backup(source, backup, scope=scope)
    assert backup_receipt.verified_clean and backup_receipt.verified_retained_bytes > 0
    assert backup_receipt.scope == scope
    assert set(backup_receipt.manifest.stores) == {"core"}
    checks.append("verified_git_only_backup_with_actual_metadata_bytes")

    paired_artifact = Path("paired-declared-backup").resolve()
    shutil.copytree(backup, paired_artifact)
    paired_context = b"opaque paired artifact requires Context validation"
    (paired_artifact / "stores/context.sqlite3").write_bytes(paired_context)
    paired_manifest_path = paired_artifact / "manifest.json"
    paired_manifest = json.loads(paired_manifest_path.read_text())
    paired_manifest["scope"] = BackupScope.PAIRED.value
    paired_manifest["stores"]["context"] = {
        "path": "stores/context.sqlite3",
        "bytes": len(paired_context),
        "sha256": hashlib.sha256(paired_context).hexdigest(),
        "schema_fingerprint": paired_manifest["stores"]["core"]["schema_fingerprint"],
    }
    paired_manifest["overall_sha256"] = hashlib.sha256(
        "".join(
            paired_manifest["stores"][name]["sha256"]
            for name in sorted(paired_manifest["stores"])
        ).encode("ascii")
    ).hexdigest()
    paired_raw = json.dumps(paired_manifest).encode()
    paired_manifest_path.write_bytes(paired_raw)
    (paired_artifact / "manifest.json.sha256").write_text(
        hashlib.sha256(paired_raw).hexdigest() + "  manifest.json\n"
    )
    paired_target = Path("paired-target").resolve()
    refuses(
        lambda: service.restore_backup(paired_artifact, paired_target, repository),
        RecoveryCapabilityError,
    )
    assert not paired_target.exists()
    assert not service.is_stopped(source)
    checks.append("paired_declared_artifact_is_not_downgraded_to_git_only")

    # A mapping and note body added after the baseline must be reconstructed and
    # verified by the receiver rather than merely inherited from the backup.
    note = native("blob", b"\0\xffrecovered Notes\r\n")
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
        Provenance("fixture", "read", "claim", "fixture", "1"),
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
            "fixture", "receiver", "path", "native-notes", "1", "receiver_intrinsic"
        ),
        (notes_tree,),
    )
    with closing(GitCore(source / "core.sqlite3")) as core:
        core.admit_ref_observation(
            RefObservation(key, repository, b"refs/notes/commits", "fixture", "visible")
        )
        core.admit_ref_observation_claim(claim)
        core.admit_ref_note(proof, note, str(uuid4()), RecoveryWorkBudget())
    only_core(source)

    # Explicit capability refusal must not inspect/diagnose these opaque files.
    opaque = {
        "context.sqlite3": b"opaque unvalidated Context evidence\0\xff",
        "context.sqlite3-wal": b"opaque necessary WAL evidence",
        "context.sqlite3-journal": b"opaque rollback evidence",
    }
    for name, body in opaque.items():
        (source / name).write_bytes(body)
    source_before = evidence_files(source)
    refuses(
        lambda: service.create_consistent_backup(
            source, Path("unsupported-paired"), scope=BackupScope.PAIRED
        ),
        RecoveryCapabilityError,
    )
    assert not service.is_stopped(source)
    assert evidence_files(source) == source_before
    assert not Path("unsupported-paired").exists()
    checks.append("paired_capability_refused_without_false_corruption")

    service.stop_suspect_catalog(source, "synthetic incident: preserve source")
    source_before = evidence_files(source)
    refuses(lambda: service.assert_not_stopped(source), CatalogStoppedError)
    refuses(
        lambda: service.create_consistent_backup(
            source, Path("stopped-backup"), scope=scope
        ),
        CatalogStoppedError,
    )
    assert not Path("stopped-backup").exists()
    checks.append("persistent_source_stop_fences_normal_backup")

    preserved = []
    copy_files = adapter_module._copy_forensic_files

    def observe_preservation(catalog_dir, forensic_dir, *args, **kwargs):
        result = copy_files(catalog_dir, forensic_dir, *args, **kwargs)
        preserved.append({name: (forensic_dir / name).read_bytes() for name in opaque})
        return result

    adapter_module._copy_forensic_files = observe_preservation
    salvage = Path("salvage.jsonl").resolve()
    try:
        extraction = service.extract_salvage(
            source, salvage, scope=scope, request_id="bound-output"
        )
    finally:
        adapter_module._copy_forensic_files = copy_files
    assert extraction.candidate_count > 0
    assert preserved == [opaque]
    assert any(
        "context" in item.lower() and "uninspect" in item.lower()
        for item in extraction.unreadable_scope
    )
    records = [json.loads(line) for line in salvage.read_text().splitlines()]
    assert records
    assert not any(
        str(item["candidate_type"]).startswith("context") for item in records
    )
    assert evidence_files(source) == source_before
    checks.append("opaque_context_and_sidecars_preserved_without_interpretation")

    request_key = "extract-" + hashlib.sha256(b"bound-output").hexdigest()[:40]
    request_path = source / f"p1-recovery-request-{request_key}.json"
    usage_before = json.loads(request_path.read_text())["cumulative_usage"]
    moved_output = Path("different-output")
    moved_output.mkdir()
    service.extract_salvage(
        source, moved_output / "retry.jsonl", scope=scope, request_id="bound-output"
    )
    usage_after = json.loads(request_path.read_text())["cumulative_usage"]
    assert set(usage_before) == set(usage_after)
    assert all(usage_after[key] >= value for key, value in usage_before.items())
    assert any(usage_after[key] > value for key, value in usage_before.items())
    refuses(
        lambda: service.extract_salvage(
            source,
            Path("changed-scope.jsonl"),
            scope=BackupScope.PAIRED,
            request_id="bound-output",
        ),
        RecoveryError,
    )
    assert evidence_files(source) == source_before
    checks.append("source_bound_work_accumulates_across_output_paths_and_scope_refusal")

    destination = Path("restored").resolve()
    restored = service.restore_backup(backup, destination, repository)
    assert restored.revalidated_clean and restored.scope == scope
    assert restored.revalidated_stores == ["core"]
    only_core(destination)
    merged = service.merge_salvage(destination, salvage, request_id="typed-merge")
    assert merged.admitted_units > 0 and merged.input_complete
    with closing(GitCore(destination / "core.sqlite3")) as core:
        work = RecoveryWorkBudget()
        assert core.ref_observation(key, work).claims == (claim,)
        assert core.read_ref_note(claim, mapping, work) == note.body
    replay = service.merge_salvage(destination, salvage, request_id="typed-merge")
    assert replay.replayed_units > 0 and replay.input_complete
    assert not service.is_stopped(destination)
    only_core(destination)
    checks.append("fresh_restore_receiver_validated_typed_notes_merge_and_replay")

    paired_candidate = json.loads(json.dumps(records[0]))
    paired_candidate.setdefault("extraction_provenance", {})["scope"] = (
        BackupScope.PAIRED.value
    )
    paired_salvage = Path("paired-declared-salvage.jsonl").resolve()
    paired_salvage.write_text(json.dumps(paired_candidate) + "\n")
    paired_merge_target = Path("paired-merge-target").resolve()
    service.restore_backup(backup, paired_merge_target, repository)
    refuses(
        lambda: service.merge_salvage(paired_merge_target, paired_salvage),
        RecoveryCapabilityError,
    )
    assert not service.is_stopped(paired_merge_target)
    only_core(paired_merge_target)
    checks.append("supplied_paired_salvage_scope_refused_for_git_only_target")

    invalid_notes = json.loads(json.dumps(records))
    changed = 0
    for record in invalid_notes:
        if record["candidate_type"] == "ref_note":
            wire = record["payload"]["unit"]
            original = wire["body_hex"]
            wire["body_hex"] = ("01" if original[:2] != "01" else "02") + original[2:]
            changed += 1
    assert changed > 0
    invalid_file = Path("invalid-note-bytes.jsonl").resolve()
    invalid_file.write_text(
        "".join(json.dumps(record) + "\n" for record in invalid_notes)
    )
    invalid_target = Path("invalid-note-target").resolve()
    service.restore_backup(backup, invalid_target, repository)
    invalid_merge = service.merge_salvage(invalid_target, invalid_file)
    assert invalid_merge.rejected_units > 0
    assert invalid_merge.admitted_units > 0
    assert not service.is_stopped(invalid_target)
    with sqlite3.connect(invalid_target / "core.sqlite3") as connection:
        assert (
            connection.execute("SELECT count(*) FROM ref_retained_notes").fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM ref_observation_claims"
            ).fetchone()[0]
            > 0
        )
    only_core(invalid_target)
    checks.append(
        "receiver_rejects_changed_note_bytes_while_independent_claims_survive"
    )

    limited_dir = Path("limited-target").resolve()
    service.restore_backup(backup, limited_dir, repository)
    limited_budget = RecoveryBudget(max_work_units={"json_decode_bytes": 1})
    limited = service.merge_salvage(
        limited_dir, salvage, budget=limited_budget, request_id="finite-merge"
    )
    assert not limited.input_complete
    assert limited.admitted_units == 0
    assert not service.is_stopped(limited_dir)
    only_core(limited_dir)
    checks.append("finite_merge_limit_without_authority_corruption")

    lost_state = destination / "p1-recovery-request-typed-merge.json"
    lost_state.unlink()
    refuses(
        lambda: service.merge_salvage(destination, salvage, request_id="typed-merge"),
        RecoveryError,
    )
    assert not service.is_stopped(destination)
    checks.append("lost_durable_request_state_fails_closed_without_operational")

    unbacked, _ = new_catalog("unbacked")
    generic = [
        {
            "candidate_type": "git_metadata",
            "extraction_provenance": {"scope": "git_only", "table": table},
            "payload": payload,
        }
        for table, payload in (
            ("repositories", {"repository_uuidv4": str(uuid4())}),
            ("git_objects", {"object_format": "sha1", "object_oid": "f" * 40}),
        )
    ]
    retained = [row for row in records if row["candidate_type"] == "retained_body"]
    assert retained

    def authority(directory):
        with closing(sqlite3.connect(directory / "core.sqlite3")) as db:
            schema.register_functions(db, "core")
            tables = db.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
            ).fetchall()
            return {
                name: db.execute(f'SELECT * FROM "{name}"').fetchall()
                for (name,) in tables
            }

    unbacked_before = authority(unbacked)
    for index, candidates in enumerate((generic, retained, [*generic, *records])):
        supplied = Path(f"unbacked-{index}.jsonl")
        supplied.write_text("".join(json.dumps(row) + "\n" for row in candidates))
        refuses(lambda: service.merge_salvage(unbacked, supplied), RecoveryError)
        assert authority(unbacked) == unbacked_before
        assert not service.is_stopped(unbacked)
    refuses(
        lambda: service.activate_catalog(unbacked, Path("unbacked-active")),
        ActivationError,
    )
    assert not Path("unbacked-active").exists()
    assert not service.is_stopped(unbacked)
    only_core(unbacked)
    checks.append("untrusted_fresh_filename_is_not_a_verified_baseline")

    mismatched = Path("mismatched-target").resolve()
    service.restore_backup(backup, mismatched, repository)
    baseline_path = mismatched / "p1-restored-baseline.json"
    baseline = json.loads(baseline_path.read_text())
    baseline["catalog_instance_uuidv4"] = str(uuid4())
    baseline_path.write_text(json.dumps(baseline))
    supplied = Path("mismatched.jsonl")
    supplied.write_text(
        "".join(json.dumps(row) + "\n" for row in [*generic, *retained])
    )
    mismatched_before = authority(mismatched)
    refuses(lambda: service.merge_salvage(mismatched, supplied), RecoveryError)
    assert authority(mismatched) == mismatched_before
    assert not service.is_stopped(mismatched)
    assert evidence_files(source) == source_before
    checks.append("all_families_require_matching_baseline_before_authority_writes")

    polluted = Path("polluted-target").resolve()
    service.restore_backup(backup, polluted, repository)
    (polluted / "context.sqlite3").write_bytes(opaque["context.sqlite3"])
    refuses(
        lambda: service.activate_catalog(polluted, Path("polluted-active")),
        RecoveryError,
    )
    assert not Path("polluted-active").exists()
    assert (polluted / "context.sqlite3").read_bytes() == opaque["context.sqlite3"]
    checks.append("unvalidated_context_is_not_promoted_in_git_only_activation")

    damaged_target = Path("damaged-target").resolve()
    service.restore_backup(backup, damaged_target, repository)
    with sqlite3.connect(damaged_target / "core.sqlite3") as connection:
        triggers = connection.execute(
            "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name='retained_metadata'"
        ).fetchall()
        for name, _ in triggers:
            connection.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(
            "UPDATE retained_metadata SET body=zeroblob(length(body)) WHERE native_type='commit'"
        )
        for _, definition in triggers:
            connection.execute(definition)
    refuses(
        lambda: service.activate_catalog(damaged_target, Path("damaged-active")),
        ActivationError,
    )
    assert service.is_stopped(damaged_target)
    assert not Path("damaged-active").exists()
    assert evidence_files(source) == source_before and service.is_stopped(source)
    only_core(damaged_target)
    checks.append(
        "final_retained_byte_validation_stops_damaged_target_before_publication"
    )

    old = Path("previous-active").resolve()
    old.mkdir()
    (old / "marker").write_text("previous valid locator")
    failed_locator = Path("failed-active")
    failed_locator.symlink_to(old)
    refuses(
        lambda: service.activate_catalog(
            destination, failed_locator, fault_stage="during_locator_replacement"
        ),
        ActivationError,
    )
    assert failed_locator.resolve() == old
    assert (old / "marker").read_text() == "previous valid locator"
    assert evidence_files(source) == source_before and service.is_stopped(source)
    only_core(destination)
    checks.append("failed_locator_publication_preserves_previous_locator_and_source")

    # Failure injection does not stop a valid target; activation revalidates it.
    active = Path("active")
    activation = service.activate_catalog(destination, active)
    assert active.resolve() == destination
    assert activation.reconstructed_stores == []
    assert activation.clean_operational is None
    assert activation.search_derivative_state == "not_initialized"
    assert activation.source_backup_id == backup_receipt.backup_id
    only_core(destination)
    assert evidence_files(source) == source_before and service.is_stopped(source)
    checks.append(
        "safe_git_only_activation_truthful_receipt_without_optional_databases"
    )

    empty_source, empty_repository = new_catalog("zero-body-source")
    empty_backup = Path("zero-body-backup").resolve()
    receipt = service.create_consistent_backup(empty_source, empty_backup, scope=scope)
    assert receipt.verified_retained_bytes == 0
    service.stop_suspect_catalog(empty_source, "synthetic zero-body incident")
    empty_before = evidence_files(empty_source)
    empty_salvage = Path("zero-body.jsonl").resolve()
    service.extract_salvage(
        empty_source, empty_salvage, scope=scope, request_id="zero-body"
    )
    empty_target = Path("zero-body-target").resolve()
    service.restore_backup(empty_backup, empty_target, empty_repository)
    service.merge_salvage(empty_target, empty_salvage)
    empty_active = Path("zero-body-active")
    empty_activation = service.activate_catalog(empty_target, empty_active)
    assert empty_active.resolve() == empty_target
    assert empty_activation.reconstructed_stores == []
    only_core(empty_target)
    assert evidence_files(empty_source) == empty_before and service.is_stopped(
        empty_source
    )
    checks.append("complete_zero_retained_body_git_only_lifecycle")

    # Even runtime codec paths must not have pulled optional implementations in.
    assert not any("repo_catalog." + suffix in sys.modules for suffix in absent)
    for name, module in tuple(sys.modules.items()):
        if name.startswith("repo_catalog.") and getattr(module, "__file__", None):
            assert Path(module.__file__).resolve().is_relative_to(installed), name
    checks.append("runtime_dependency_closure_stays_in_minimal_installed_owners")
    output.write_text(
        json.dumps(
            {
                "result": "passed",
                "installed_distributions": sorted(distributions),
                "checks": checks,
                "origins": origins,
                "python": sys.version,
                "sqlite": sqlite3.sqlite_version,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
