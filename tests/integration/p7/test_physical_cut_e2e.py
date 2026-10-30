"""Coordinated Ref-only storage, transport, backup and stopped-source recovery."""

import json
from contextlib import closing
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.adapters.sqlite.recovery import SQLiteRecoveryAdapter
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.cli.production_query import main
from repo_catalog.domain.exchange import (
    FORMAT,
    ExchangeError,
    decode_package,
    encode_package,
)
from repo_catalog.domain.p1_core import CoreFailure
from repo_catalog.domain.production_query import SearchQuery
from repo_catalog.domain.recovery import BackupScope, RecoveryError
from repo_catalog.domain.ref_observation import new_uuid7
from tests.integration.p4 import conftest as fixtures
from tests.integration.p5.test_ref_inventory_wiring import enable_context, run_request
from tests.integration.p5.test_ref_notes_inputs import with_input
from tests.integration.p6.test_ref_search_transition import two_claims

acquisition = fixtures.acquisition


@pytest.mark.parametrize("paired", [False, True], ids=["core", "paired"])
def test_ref_only_transport_backup_and_corrupt_source_recovery(
    acquisition, tmp_path, paired, capsys
):
    app, _, _, repository, _, path, _ = acquisition
    if paired:
        enable_context(acquisition)
    value, target = two_claims(acquisition)
    run_request(acquisition, with_input(acquisition, value), paired=paired)
    first = replace(
        value, claims=(value.claims[0],), mapping_groups=(value.mapping_groups[0],)
    )
    run_request(
        acquisition,
        with_input(acquisition, first, target_oids=(target,), acquire_inventories=True),
        paired=paired,
    )
    service = ProductionQueryService(path.parent)
    view = service.get_git_object(target)
    assert {entry.mapping.ref_claim for entry in view.ref_notes_targets} == set(
        value.claims
    )
    query = SearchQuery(query_text="needle-only-one-claim", projection_kinds=("notes",))
    authority = service.search(query)
    assert authority.total_count == 1
    service.rebuild_search(("notes",))
    assert service.search(query).hits == authority.hits
    assert main(["ref-observations", "--catalog", str(path.parent)]) == 0
    assert len(json.loads(capsys.readouterr().out)["items"][0]["claims"]) == 2

    # Transport is explicitly Core-only; paired backup/recovery is checked below.
    from repo_catalog.domain.exchange import ExchangeSelectionScope

    package = ExchangeService(path.parent).export_package(
        selection=ExchangeSelectionScope(all_selected=True, include_context=False)
    )
    assert package.format == FORMAT == "git-repo-db/adr0036-exchange-v7"
    wire = json.loads(encode_package(package))
    wire["format"] = "git-repo-db/adr0036-exchange-v6"
    with pytest.raises(ExchangeError):
        decode_package(json.dumps(wire))
    assert not {
        "captures",
        "notes_claims",
        "notes_groups",
        "notes_inventories",
        "note_roles",
        "retained_notes",
    }.intersection(package.core)
    wire["format"] = FORMAT
    wire["core"]["captures"] = []
    with pytest.raises(ExchangeError):
        decode_package(json.dumps(wire))
    receiver = tmp_path / "receiver"
    receiver.mkdir()
    instance = str(uuid4())
    for role in ("core", "operational"):
        initialize(receiver / (role + ".sqlite3"), role, repository, instance)
    ExchangeService(receiver, operational=receiver).import_package(
        package, new_request=True, permitted_repository_uuidv4s=(repository,)
    )
    received = ProductionQueryService(receiver)
    assert received.search(query).total_count == 1
    assert set(
        received.get_ref_observation(
            value.observation.ref_observation_key, UnlimitedWorkBudget()
        ).claims
    ) == set(value.claims)
    second_view = received.get_notes_mapping(
        value.claims[1],
        target,
        "git-notes",
        "1",
        "native-notes-tree",
        UnlimitedWorkBudget(),
    )
    assert second_view.groups and not second_view.evidence

    adapter = SQLiteRecoveryAdapter()
    outside = tmp_path.parent / (tmp_path.name + "-cut-evidence")
    outside.mkdir()
    backup = outside / "healthy"
    scope = BackupScope.PAIRED if paired else BackupScope.GIT_ONLY
    assert adapter.create_consistent_backup(path.parent, backup, scope).verified_clean
    manifest = json.loads((backup / "manifest.json").read_text())
    assert manifest["manifest_version"] == 2
    # A genuinely new post-backup subject must arrive through typed salvage.
    late = replace(
        value.observation,
        ref_observation_key=replace(
            value.observation.ref_observation_key, ref_observation_uuidv7=new_uuid7()
        ),
        ref_name_bytes=b"refs/notes/late",
    )
    run_request(
        acquisition,
        with_input(
            acquisition, replace(value, observation=late, claims=(), mapping_groups=())
        ),
        paired=paired,
    )
    with closing(connect(path, "core")) as db:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_ref_retained_notes_update'"
        ).fetchone()[0]
        db.execute("DROP TRIGGER p1_immutable_ref_retained_notes_update")
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("UPDATE ref_retained_notes SET body=zeroblob(size)")
        db.execute(trigger)
        db.commit()
    with pytest.raises(CoreFailure) as damage:
        service.search(query)
    assert damage.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (path.parent / "p1-recovery-stop.json").exists()
    with pytest.raises(RecoveryError):
        adapter.create_consistent_backup(path.parent, outside / "forbidden", scope)
    preserved = {
        p.name: p.read_bytes() for p in path.parent.glob("core.sqlite3*") if p.is_file()
    }
    salvage = outside / "untrusted.jsonl"
    extracted = adapter.extract_salvage(path.parent, salvage)
    assert extracted.partial and extracted.candidate_count > 0
    assert {
        p.name: p.read_bytes() for p in path.parent.glob("core.sqlite3*") if p.is_file()
    } == preserved
    restored = outside / "fresh"
    assert adapter.restore_backup(backup, restored, repository).revalidated_clean
    merged = adapter.merge_salvage(restored, salvage)
    assert merged.admitted_units > 0
    recovered = ProductionQueryService(restored)
    assert recovered.search(query).total_count == 1
    assert (
        recovered.get_ref_observation(
            late.ref_observation_key, UnlimitedWorkBudget()
        ).ref_observation
        == late
    )
    assert recovered.detect_mode() == ("paired" if paired else "core_only")
    with closing(GitCore(restored / "core.sqlite3")) as core:
        assert not {
            "captures",
            "notes_claims",
            "notes_groups",
            "note_roles",
            "retained_notes",
        }.intersection(
            row[0]
            for row in core.sql("SELECT name FROM sqlite_schema WHERE type='table'")
        )
    assert adapter.activate(restored, outside / "active").clean_operational
    assert (path.parent / "p1-recovery-stop.json").exists()
