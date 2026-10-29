"""Portable ref observations use actual ref identities and dependencies."""

import copy
import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.exchange import (
    ExchangeError,
    ExchangeSelectionScope,
    decode_package,
    encode_package,
)
from repo_catalog.domain.p1_core import OID, CoreCoverageScope, CoreFailure, Provenance
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.ref_observation import (
    RefAbsenceEvidence,
    RefObservation,
    RefObservationClaim,
    RefObservationKey,
    new_uuid7,
)
from tests.integration.p1 import test_core as p1_fixtures
from tests.integration.p1.test_core import Budget
from tests.integration.p1.test_ref_coverage_i3 import proof_fixture
from tests.integration.p4 import conftest as p4_fixtures
from tests.integration.p4.test_ref_observation_i2 import discover
from tests.integration.p5.conftest import init_catalog_stores

acquisition = p4_fixtures.acquisition
p1_core_fixture = p1_fixtures.core


def test_export_stored_group_utf8_corruption_stops_catalog(acquisition, tmp_path):
    app, _, _, repository, origin, core_path, _ = acquisition
    p4_fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    app.inventory_ref(claim)
    selection = ExchangeSelectionScope(
        all_selected=True,
        include_context=False,
        include_retained_bytes=False,
        object_oids=(),
        ref_observation_keys=(claim.ref_observation_key,),
    )
    service = ExchangeService(tmp_path, operational=tmp_path)
    assert service.export_package(selection=selection).core["notes_mapping_groups"]

    db = connect(core_path, "core")
    try:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_notes_mapping_groups_update'"
        ).fetchone()[0]
        db.execute("DROP TRIGGER p1_immutable_notes_mapping_groups_update")
        db.execute("UPDATE notes_mapping_groups SET group_scope=CAST(x'80' AS TEXT)")
        db.execute(trigger)
        db.commit()
    finally:
        db.close()

    with pytest.raises(CoreFailure) as corruption:
        service.export_package(selection=selection)
    assert corruption.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (core_path.parent / "p1-recovery-stop.json").exists()
    with pytest.raises(CoreFailure) as stopped:
        app.core.ensure_available()
    assert stopped.value.code == "RECOVERY_STOP"


def test_ref_export_typed_read_keeps_budget_and_noncorruption_errors(
    acquisition, monkeypatch
):
    app, _, _, repository, origin, core_path, _ = acquisition
    p4_fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    app.inventory_ref(claim)
    calls = []
    original_read = app.core._ref_exchange_fixed_rows

    def counted_read(*args, **kwargs):
        calls.append(kwargs["lengths"])
        return original_read(*args, **kwargs)

    monkeypatch.setattr(app.core, "_ref_exchange_fixed_rows", counted_read)
    with pytest.raises(CoreFailure) as limited:
        app.core.ref_exchange_rows(
            "groups", claim.identity, Budget(), maximum=10, max_bytes=1
        )
    assert limited.value.code == "QUERY_BUDGET"
    assert calls == [True]  # No variable-width values were fetched.
    calls.clear()
    budget = Budget()
    rows = app.core.ref_exchange_rows(
        "groups", claim.identity, budget, maximum=10, max_bytes=10000
    )
    assert rows and calls == [True, False]
    assert budget.counts["metadata_units"] == len(rows)
    assert budget.counts["input_bytes"] == sum(
        len(value.encode("utf-8")) for row in rows for value in row
    )

    with pytest.raises(sqlite3.OperationalError):
        app.core.sql("SELECT missing_column FROM notes_mapping_groups")

    class FailingWork:
        def require(self, unit, amount=1):
            raise sqlite3.OperationalError("Could not decode to UTF-8 from callback")

    with pytest.raises(sqlite3.OperationalError, match="from callback"):
        app.core.ref_exchange_rows(
            "groups", claim.identity, FailingWork(), maximum=10, max_bytes=10000
        )
    assert not (core_path.parent / "p1-recovery-stop.json").exists()
    app.core.ensure_available()


def test_unsupported_ref_coverage_claim_roundtrips_as_unknown(acquisition, tmp_path):
    app, _, _, repository, origin, _, _ = acquisition
    p4_fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    scope = CoreCoverageScope(
        "ref_observation", (*claim.ref_observation_key.key, "ref-enumeration")
    )
    original = CoverageClaim(scope, 20, "complete", '{"origin":"source"}')
    app.core.admit_coverage_scope(scope)
    app.core.admit_coverage(original)
    assert app.core.coverage(scope, app.work).state == "unknown"
    selection = ExchangeSelectionScope(
        all_selected=True,
        include_context=False,
        include_retained_bytes=False,
        object_oids=(),
        ref_observation_keys=(claim.ref_observation_key,),
    )
    source = ExchangeService(tmp_path, operational=tmp_path)
    package = decode_package(encode_package(source.export_package(selection=selection)))
    assert any(
        (
            row["owner_kind"],
            row["owner_coordinates_json"],
            row["observed_at_us"],
            row["coverage_state"],
            row["details_json"],
        )
        == (scope.owner_kind, scope.encoded, 20, "complete", original.details_json)
        for row in package.core["coverage_claims"]
    )
    assert not package.core["ref_coverage_proofs"]

    destination = tmp_path / "receiver"
    init_catalog_stores(
        destination, repository_uuidv4=repository, stores=("core", "operational")
    )
    receiver = ExchangeService(destination, operational=destination)
    receiver.import_package(
        package, new_request=True, permitted_repository_uuidv4s=(repository,)
    )
    with closing(GitCore(destination / "core.sqlite3")) as core:
        coverage = core.coverage(scope, Budget())
        assert coverage.state == "unknown"
        assert coverage.claims == (original,)
    onward = receiver.export_package(selection=selection)
    assert onward.core["coverage_claims"] == package.core["coverage_claims"]
    assert not onward.core["ref_coverage_proofs"]


def test_rootless_ref_and_original_enumeration_roundtrip(acquisition, tmp_path):
    app, path, _fmt, repository, origin, *_ = acquisition
    name = "refs/notes/missing"
    p4_fixtures.fixture_note(acquisition)
    discovery = discover(app, repository, origin, str(uuid4()), (name,))
    result = next(
        e
        for e in discovery.enumerations
        if not e.event.prefixes and e.event.nominated == (name.encode(),)
    )
    link = result.links[0]
    selection = ExchangeSelectionScope(
        all_selected=True,
        include_context=False,
        include_retained_bytes=False,
        object_oids=(),
        ref_observation_keys=(link.observation.ref_observation_key,),
    )
    source = ExchangeService(tmp_path, operational=tmp_path)
    package = decode_package(encode_package(source.export_package(selection=selection)))
    assert package.core["ref_observations"]
    assert len(package.core["ref_enumeration_observations"]) == 1
    assert len(package.core["ref_enumeration_links"]) == 1
    assert package.core["git_objects"] == []

    destination = tmp_path / "receiver"
    init_catalog_stores(
        destination, repository_uuidv4=repository, stores=("core", "operational")
    )
    receiver = ExchangeService(destination, operational=destination)
    first_import = receiver.import_package(
        package, new_request=True, permitted_repository_uuidv4s=(repository,)
    )
    assert not first_import.idempotent_replay
    replay = receiver.import_package(
        package, permitted_repository_uuidv4s=(repository,)
    )
    assert replay.idempotent_replay
    with closing(GitCore(destination / "core.sqlite3")) as core:
        assert core.ref_observation(
            link.observation.ref_observation_key, app.work
        ).claims == (link.claim,)
        assert core.ref_enumeration(*result.event.identity, app.work) == result


def test_object_only_does_not_select_rootless_observation(acquisition, tmp_path):
    app, path, _fmt, repository, origin, *_ = acquisition
    capture, _, _ = p4_fixtures.fixture_note(acquisition)
    missing = "refs/notes/missing"
    discovery = discover(app, repository, origin, str(uuid4()), (missing,))
    absence = next(
        e.links[0]
        for e in discovery.enumerations
        if not e.event.prefixes and e.event.nominated == (missing.encode(),)
    )
    selection = ExchangeSelectionScope(
        all_selected=True,
        include_context=False,
        include_retained_bytes=False,
        object_oids=(capture.root,),
    )
    package = ExchangeService(tmp_path, operational=tmp_path).export_package(
        selection=selection
    )
    assert package.core["ref_observations"]
    assert all(
        r["ref_observation_uuidv7"]
        != absence.observation.ref_observation_key.ref_observation_uuidv7
        for r in package.core["ref_observations"]
    )


def test_claim_scoped_note_proof_body_repeat_and_reverse(acquisition, tmp_path):
    app, _path, _fmt, repository, origin, *_ = acquisition
    _, target, note = p4_fixtures.fixture_note(acquisition, fanout=1)
    observed = discover(app, repository, origin, str(uuid4()))
    first, second = (event.links[0].claim for event in observed.enumerations)
    acquired = app.acquire_ref_note(first, target)
    assert acquired.body_retained
    selection = ExchangeSelectionScope(
        all_selected=True,
        include_context=False,
        object_oids=(),
        ref_observation_keys=(first.ref_observation_key,),
    )
    source = ExchangeService(tmp_path, operational=tmp_path)
    package = source.export_package(selection=selection)
    assert package.core["notes_mapping_evidence"]
    assert len(package.core["ref_retained_notes"]) == 1
    destination = tmp_path / "receiver"
    init_catalog_stores(
        destination, repository_uuidv4=repository, stores=("core", "operational")
    )
    receiver = ExchangeService(destination, operational=destination)
    receiver.import_package(
        package, new_request=True, permitted_repository_uuidv4s=(repository,)
    )
    receiver.import_package(package, permitted_repository_uuidv4s=(repository,))
    with closing(GitCore(destination / "core.sqlite3")) as core:
        projection = core.notes_mapping_projection(
            first, target, "git-notes", "1", "native-notes-tree", app.work
        )
        assert projection.canonical_note_oid == note
        assert len(projection.evidence) >= 2  # original attribution plus receiver check
        mapping = projection.evidence[0].mapping
        assert core.read_ref_note(first, mapping, app.work) == b"\0\xffbinary\r\n"
    reverse = receiver.export_package(selection=selection)
    source.import_package(
        reverse, new_request=True, permitted_repository_uuidv4s=(repository,)
    )
    assert app.core.read_ref_note(first, mapping, app.work) == b"\0\xffbinary\r\n"
    # Rechecking a transferred local proof must not recursively grow its
    # provenance on every reverse/onward transfer.
    for _ in range(2):
        onward = source.export_package(selection=selection)
        receiver.import_package(
            onward, new_request=True, permitted_repository_uuidv4s=(repository,)
        )
        reverse = receiver.export_package(selection=selection)
        source.import_package(
            reverse, new_request=True, permitted_repository_uuidv4s=(repository,)
        )
    with closing(GitCore(destination / "core.sqlite3")) as core:
        checked = core.notes_mapping_projection(
            first, target, "git-notes", "1", "native-notes-tree", app.work
        )
        assert len(checked.evidence) == 3
    assert first != second


@pytest.mark.parametrize("empty", [False, True])
def test_verified_inventory_coverage_roundtrips_with_original_and_local_proofs(
    p1_core_fixture, tmp_path, empty
):
    source_core, path, repository = p1_core_fixture
    proof = proof_fixture(p1_core_fixture, empty=empty)
    source_core.admit_ref_coverage_proof(proof, Budget())
    selection = ExchangeSelectionScope(
        all_selected=True,
        include_context=False,
        include_retained_bytes=False,
        object_oids=(),
        ref_observation_keys=(proof.group.ref_claim.ref_observation_key,),
    )
    package = ExchangeService(path.parent).export_package(selection=selection)
    assert len(package.core["ref_coverage_proofs"]) == 1
    assert not package.core["ref_retained_notes"]
    destination = tmp_path / "receiver"
    init_catalog_stores(
        destination, repository_uuidv4=repository, stores=("core", "operational")
    )
    receiver = ExchangeService(destination, operational=destination)
    receiver.import_package(
        package, new_request=True, permitted_repository_uuidv4s=(repository,)
    )
    with closing(GitCore(destination / "core.sqlite3")) as core:
        result = core.coverage(proof.coverage_claim.scope, Budget())
        assert result.state == "complete"
        assert result.known_empty is empty
        received = core.ref_coverage_proofs(proof.coverage_claim, Budget())
        assert len(received) == 2
        assert proof in received
    third = tmp_path / "third"
    init_catalog_stores(
        third, repository_uuidv4=repository, stores=("core", "operational")
    )
    onward = receiver.export_package(selection=selection)
    third_service = ExchangeService(third, operational=third)
    third_service.import_package(
        onward, new_request=True, permitted_repository_uuidv4s=(repository,)
    )
    reverse = third_service.export_package(selection=selection)
    receiver.import_package(
        reverse, new_request=True, permitted_repository_uuidv4s=(repository,)
    )
    with closing(GitCore(destination / "core.sqlite3")) as core:
        received = core.ref_coverage_proofs(proof.coverage_claim, Budget())
        assert len(received) == 3
        assert core.coverage(proof.coverage_claim.scope, Budget()).state == "complete"


def test_distinct_conflicts_survive_and_evidence_rebinding_is_refused(
    acquisition, tmp_path
):
    app, _path, fmt, repository, origin, *_ = acquisition
    p4_fixtures.fixture_note(acquisition)
    event = discover(app, repository, origin, str(uuid4())).enumerations[0]
    original = event.links[0].claim
    subject = event.links[0].observation
    other_root = OID(fmt, "b" * (40 if fmt == "sha1" else 64))
    competing = replace(
        original,
        provenance=replace(original.provenance, coordinate="independent-root"),
        root_oid=other_root,
    )
    absence = RefObservationClaim(
        original.ref_observation_key,
        replace(original.provenance, coordinate="independent-absence"),
        "absent",
        absence_evidence=RefAbsenceEvidence(
            subject.source_attribution,
            subject.visibility_scope,
            subject.ref_name_bytes,
            "lookup",
            "separate-completion",
        ),
    )
    app.core.admit_ref_observation_claim(competing)
    app.core.admit_ref_observation_claim(absence)
    selection = ExchangeSelectionScope(
        all_selected=True,
        include_context=False,
        include_retained_bytes=False,
        object_oids=(),
        ref_observation_keys=(subject.ref_observation_key,),
    )
    package = ExchangeService(tmp_path, operational=tmp_path).export_package(
        selection=selection
    )
    destination = tmp_path / "receiver"
    init_catalog_stores(
        destination, repository_uuidv4=repository, stores=("core", "operational")
    )
    receiver = ExchangeService(destination, operational=destination)
    receiver.import_package(
        package, new_request=True, permitted_repository_uuidv4s=(repository,)
    )
    with closing(GitCore(destination / "core.sqlite3")) as core:
        projection = core.ref_observation(subject.ref_observation_key, app.work)
        assert projection.conflict
        assert set(projection.claims) == {original, competing, absence}

    altered = copy.deepcopy(package.core)
    row = next(
        r
        for r in altered["ref_observation_claims"]
        if r["provenance_json"] == original.provenance.encoded
    )
    row["root_oid"] = [fmt, "c" * (40 if fmt == "sha1" else 64)]
    forged = replace(package, package_id=str(uuid4()), core=altered, digest_sha256=None)
    with pytest.raises(ExchangeError) as error:
        receiver.import_package(
            forged, new_request=True, permitted_repository_uuidv4s=(repository,)
        )
    assert error.value.code == "IMMUTABLE_REPLAY_CONFLICT"
    assert not (destination / "p1-recovery-stop.json").exists()


def test_lossless_symbolic_direct_resolved_and_peeled_metadata(acquisition, tmp_path):
    app, _path, fmt, repository, origin, *_ = acquisition
    width = 40 if fmt == "sha1" else 64
    observation = RefObservation(
        RefObservationKey(origin, new_uuid7()),
        repository,
        b"refs/heads/branch-\xff",
        "source",
        "local-visible",
        1234567,
    )
    claim = RefObservationClaim(
        observation.ref_observation_key,
        Provenance("source", "read", "symbolic", "native", "1"),
        "present",
        "symbolic",
        symbolic_target_ref_name=b"refs/tags/target-\xfe",
        resolved_target_oid=OID(fmt, "a" * width),
        peeled_target_oid=OID(fmt, "b" * width),
        root_oid=OID(fmt, "a" * width),
    )
    app.core.admit_ref_observation(observation)
    app.core.admit_ref_observation_claim(claim)
    selection = ExchangeSelectionScope(
        all_selected=True,
        include_context=False,
        include_retained_bytes=False,
        object_oids=(),
        ref_observation_keys=(observation.ref_observation_key,),
    )
    package = ExchangeService(tmp_path, operational=tmp_path).export_package(
        selection=selection
    )
    destination = tmp_path / "receiver"
    init_catalog_stores(
        destination, repository_uuidv4=repository, stores=("core", "operational")
    )
    ExchangeService(destination, operational=destination).import_package(
        package, new_request=True, permitted_repository_uuidv4s=(repository,)
    )
    with closing(GitCore(destination / "core.sqlite3")) as core:
        projection = core.ref_observation(observation.ref_observation_key, app.work)
        assert projection.ref_observation == observation
        assert projection.claims == (claim,)


def test_forged_structural_proof_is_refused_without_catalog_stop(acquisition, tmp_path):
    app, _path, _fmt, repository, origin, *_ = acquisition
    _, target, _ = p4_fixtures.fixture_note(acquisition)
    event = discover(app, repository, origin, str(uuid4())).enumerations[0]
    claim = event.links[0].claim
    assert app.acquire_ref_note(claim, target).body_retained
    selection = ExchangeSelectionScope(
        all_selected=True,
        include_context=False,
        object_oids=(),
        ref_observation_keys=(claim.ref_observation_key,),
    )
    package = ExchangeService(tmp_path, operational=tmp_path).export_package(
        selection=selection
    )
    altered = copy.deepcopy(package.core)
    row = altered["notes_mapping_evidence"][0]
    bundle = json.loads(row["proof_bundle_json"])
    raw = bytearray.fromhex(bundle[0][2])
    raw[0] ^= 1
    bundle[0][2] = raw.hex()
    row["proof_bundle_json"] = json.dumps(bundle, sort_keys=True, separators=(",", ":"))
    forged = replace(package, package_id=str(uuid4()), core=altered, digest_sha256=None)
    destination = tmp_path / "receiver"
    init_catalog_stores(
        destination, repository_uuidv4=repository, stores=("core", "operational")
    )
    with pytest.raises(CoreFailure) as error:
        ExchangeService(destination, operational=destination).import_package(
            forged, new_request=True, permitted_repository_uuidv4s=(repository,)
        )
    assert error.value.code in ("NATIVE_INTEGRITY", "NOTES_ROLE")
    assert not (destination / "p1-recovery-stop.json").exists()
    with closing(GitCore(destination / "core.sqlite3")) as core:
        assert core.sql("SELECT count(*) FROM ref_observations")[0][0] == 0


def test_explicit_member_selection_preserves_whole_original_event(
    acquisition, tmp_path
):
    app, path, _fmt, repository, origin, *_ = acquisition
    capture, _, _ = p4_fixtures.fixture_note(acquisition)
    p4_fixtures.git(path, "update-ref", "refs/notes/second", capture.root.full_oid)
    event = discover(app, repository, origin, str(uuid4())).enumerations[0]
    assert len(event.links) == 2
    selection = ExchangeSelectionScope(
        all_selected=True,
        include_context=False,
        include_retained_bytes=False,
        object_oids=(),
        ref_observation_keys=(event.links[0].observation.ref_observation_key,),
    )
    package = ExchangeService(tmp_path, operational=tmp_path).export_package(
        selection=selection
    )
    assert len(package.core["ref_observations"]) == 2
    assert len(package.core["ref_enumeration_observations"]) == 1
    assert len(package.core["ref_enumeration_links"]) == 2
    destination = tmp_path / "receiver"
    init_catalog_stores(
        destination, repository_uuidv4=repository, stores=("core", "operational")
    )
    ExchangeService(destination, operational=destination).import_package(
        package, new_request=True, permitted_repository_uuidv4s=(repository,)
    )
    with closing(GitCore(destination / "core.sqlite3")) as core:
        assert core.ref_enumeration(*event.event.identity, app.work) == event


@pytest.mark.parametrize("limits", [{"max_work": 10}, {"max_bytes": 1}])
def test_tiny_export_limits_never_claim_complete_output(acquisition, tmp_path, limits):
    app, _path, _fmt, repository, origin, core_path, *_ = acquisition
    p4_fixtures.fixture_note(acquisition)
    event = discover(app, repository, origin, str(uuid4())).enumerations[0]
    selection = ExchangeSelectionScope(
        all_selected=True,
        include_context=False,
        object_oids=(),
        ref_observation_keys=(event.links[0].observation.ref_observation_key,),
        **limits,
    )
    try:
        package = ExchangeService(tmp_path, operational=tmp_path).export_package(
            selection=selection
        )
    except CoreFailure as error:
        assert error.code in ("BUDGET", "QUERY_BUDGET")
    else:
        assert not package.core["ref_enumeration_observations"]
        assert any(
            item["reason"] in ("work_limit", "resource_limit", "byte_limit")
            for item in package.selection_report["omissions"]
        )
    assert not (core_path.parent / "p1-recovery-stop.json").exists()


def test_stale_imported_coverage_is_reported_without_losing_newer_partial(
    p1_core_fixture, tmp_path
):
    source, path, repository = p1_core_fixture
    proof = proof_fixture(p1_core_fixture)
    source.admit_ref_coverage_proof(proof, Budget())
    subject = source.ref_observation(
        proof.group.ref_claim.ref_observation_key, Budget()
    ).ref_observation
    selection = ExchangeSelectionScope(
        all_selected=True,
        include_context=False,
        include_retained_bytes=False,
        object_oids=(),
        ref_observation_keys=(subject.ref_observation_key,),
    )
    package = ExchangeService(path.parent).export_package(selection=selection)
    destination = tmp_path / "receiver"
    init_catalog_stores(
        destination, repository_uuidv4=repository, stores=("core", "operational")
    )
    with closing(GitCore(destination / "core.sqlite3")) as core:
        core.admit_repository(repository)
        core.admit_ref_observation(subject)
        core.admit_ref_observation_claim(proof.group.ref_claim)
        core.admit_coverage_scope(proof.coverage_claim.scope)
        core.admit_coverage(CoverageClaim(proof.coverage_claim.scope, 30, "partial"))
    report = ExchangeService(destination, operational=destination).import_package(
        package, new_request=True, permitted_repository_uuidv4s=(repository,)
    )
    assert any(item["reason"] == "stale_coverage_claim" for item in report.omissions)
    with closing(GitCore(destination / "core.sqlite3")) as core:
        projection = core.coverage(proof.coverage_claim.scope, Budget())
        assert projection.state == "partial" and projection.observed_at_us == 30
        assert core.ref_coverage_proofs(proof.coverage_claim, Budget()) == ()
