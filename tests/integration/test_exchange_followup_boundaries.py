"""Real capture dependencies and repository-scoped Exchange boundaries."""

import copy
import json
import uuid

import pytest

from repo_catalog.adapters.git.importer import GitImporter
from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.catalog_validation import check_catalog
from repo_catalog.application.job_service import JobService
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.query_service import QueryService
from repo_catalog.application.repository_identity import add_endpoint
from repo_catalog.domain.models import CancellationToken
from tests.support.git_fixture import FixtureRepo


def initialize(path):
    MaintenanceService(path).init("catalog-text-v1", 64 * 1024 * 1024, 0)
    return path


def capture(path, remote):
    initialize(path)
    owner = str(uuid.uuid4())
    store = Store(path)
    with store.transaction():
        store.execute(
            "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'synthetic','{}')",
            (owner,),
        )
        add_endpoint(store, owner, remote.url)
    job = JobService(store).create("sync", {"kind": "git"})
    GitImporter(store, CancellationToken()).sync(
        {"repository_uuidv4": owner, "name": "synthetic"}, job
    )
    JobService(store).update(job, "complete")
    return store, owner


def receive(store, unit):
    with store.transaction():
        return Graph(store.connection).receive(unit)


def export(store, owner):
    with store.transaction():
        return Graph(store.connection).export(owner)


def remote(tmp_path):
    repo = FixtureRepo(tmp_path / "remote.git")
    repo.commit("A", {b"a.txt": b"actual needle bytes"})
    repo.ref("refs/heads/main", "A")
    return repo


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("selected", [False, True])
def test_exact_ref_arrival_promotes_origin_after_reopen_and_onward(
    tmp_path, reverse, selected
):
    sender, owner = capture(tmp_path / "sender", remote(tmp_path))
    with sender:
        unit = export(sender, owner)
    ref = next(row for row in unit["records"] if row["table"] == "ref_observations")
    prefix = {**unit, "records": [row for row in unit["records"] if row is not ref]}
    if reverse:
        prefix["records"].reverse()
    path = initialize(tmp_path / "receiver")
    with Store(path) as receiver:
        assert receive(receiver, prefix)["staged_records"] > 0
        assert receiver.one("SELECT count(*) FROM available_git_objects")[0] == 3
        assert receiver.one("SELECT count(*) FROM current_snapshots")[0] == 0
        assert (
            receiver.one(
                "SELECT reason FROM exchange_staging WHERE table_name='root_origins'"
            )[0]
            == "missing_captured_ref"
        )
        if selected:
            acquisition = receiver.one(
                "SELECT git_acquisition_id FROM git_acquisitions"
            )[0]
            with receiver.transaction():
                pending = Graph(receiver.connection).export(
                    owner, git_acquisition_id=acquisition
                )
        else:
            pending = export(receiver, owner)
    third_path = initialize(tmp_path / "third")
    with Store(third_path) as third:
        assert receive(third, pending)["staged_records"] > 0
        assert receive(third, {**unit, "records": [ref]})["staged_records"] == 0, [
            dict(row)
            for row in third.all(
                "SELECT table_name,reason,record_json FROM exchange_staging"
            )
        ]
        assert third.one("SELECT count(*) FROM root_origins")[0] == 1
        assert not check_catalog(third, full=True)
    with Store(path) as receiver:
        assert receive(receiver, {**unit, "records": [ref]})["staged_records"] == 0
        assert receiver.one("SELECT count(*) FROM root_origins")[0] == 1
        assert receiver.one("SELECT count(*) FROM current_snapshots")[0] == 1
        assert receive(receiver, unit)["received_records"] == 0
        assert not check_catalog(receiver, full=True)


def test_existing_wrong_ref_target_stays_invalid_after_replay(tmp_path):
    sender, owner = capture(tmp_path / "sender", remote(tmp_path))
    with sender:
        unit = export(sender, owner)
    root = next(row for row in unit["records"] if row["table"] == "acquisition_roots")
    body = next(
        row
        for row in unit["records"]
        if row["table"] == "git_objects" and row["values"]["type"] == "blob"
    )
    malformed = copy.deepcopy(unit)
    wrong_root = next(row for row in malformed["records"] if row["key"] == root["key"])
    wrong_root["values"]["oid"] = body["values"]["oid"]
    wrong_root["values"]["expected_oid"] = body["values"]["oid"]
    with Store(initialize(tmp_path / "receiver")) as receiver:
        receive(receiver, malformed)
        reason = receiver.one(
            "SELECT reason FROM exchange_staging WHERE table_name='root_origins'"
        )[0]
        assert reason.startswith("invalid:")
        assert not receiver.one("SELECT 1 FROM root_origins")
        receive(receiver, malformed)
        assert (
            receiver.one(
                "SELECT reason FROM exchange_staging WHERE table_name='root_origins'"
            )[0]
            == reason
        )
        assert not receiver.one("SELECT 1 FROM root_origins")


def test_original_unit_replays_after_receipt_loss_and_new_onward_aliases(tmp_path):
    sender, owner = capture(tmp_path / "sender", remote(tmp_path))
    with sender:
        unit = export(sender, owner)
    path = initialize(tmp_path / "receiver")
    with Store(path) as receiver:
        assert receive(receiver, unit)["staged_records"] == 0, [
            dict(row)
            for row in receiver.all(
                "SELECT table_name,reason,record_json FROM exchange_staging"
            )
        ]
        with receiver.transaction():
            receiver.execute("DELETE FROM exchange_admissions")
            receiver.execute("DELETE FROM exchange_local_identities")
        assert not check_catalog(receiver, full=True)
    with Store(path) as receiver:
        onward = export(receiver, owner)
        assert receive(receiver, unit)["staged_records"] == 0
        assert receive(receiver, unit)["received_records"] == 0
        assert receiver.one("SELECT count(*) FROM acquisition_roots")[0] == 1
        assert receiver.one("SELECT count(*) FROM root_origins")[0] == 1
        assert not check_catalog(receiver, full=True)
    with Store(initialize(tmp_path / "third")) as third:
        assert receive(third, onward)["staged_records"] == 0
        assert receive(third, unit)["staged_records"] == 0
        assert third.one("SELECT count(*) FROM acquisition_roots")[0] == 1
        assert third.one("SELECT count(*) FROM root_origins")[0] == 1
        assert not check_catalog(third, full=True)


def test_resolved_foreign_subject_cannot_replace_required_capture_dependency(tmp_path):
    sender, owner = capture(tmp_path / "sender", remote(tmp_path))
    with sender:
        unit = export(sender, owner)
    claim = next(
        row
        for row in unit["records"]
        if row["table"] == "coverage_claims"
        and json.loads(row["values"]["coverage_scope_id"]["$ref"].split(":", 1)[1])[
            "kind"
        ]
        == "refs"
    )
    blob = next(
        row
        for row in unit["records"]
        if row["table"] == "git_objects" and row["values"]["type"] == "blob"
    )
    required_root = next(
        key for key in claim["requires"] if key.startswith("acquisition_roots:")
    )
    claim["requires"] = [
        blob["key"] if key == required_root else key for key in claim["requires"]
    ]
    with Store(initialize(tmp_path / "receiver")) as receiver:
        receive(receiver, unit)
        assert receiver.one("SELECT count(*) FROM available_git_objects")[0] == 3
        assert receiver.one("SELECT count(*) FROM current_snapshots")[0] == 1
        assert (
            receiver.one(
                "SELECT reason FROM exchange_staging WHERE table_name='coverage_claims'"
            )[0]
            == "invalid:completeness_dependencies"
        )
        assert not receiver.one(
            "SELECT 1 FROM coverage_claims c JOIN coverage_scopes s USING(coverage_scope_id) WHERE s.kind='refs'"
        )


def test_repository_search_does_not_require_unexported_source_inventory(tmp_path):
    sender_path = tmp_path / "sender"
    sender, owner = capture(sender_path, remote(tmp_path))
    registration = str(uuid.uuid4())
    with sender:
        with sender.transaction():
            sender.execute(
                "INSERT INTO sources VALUES('manual',?,NULL,'manual_git','manual',NULL)",
                (registration,),
            )
            sender.execute(
                "INSERT INTO source_repositories(source_id,repository_uuidv4) VALUES('manual',?)",
                (owner,),
            )
            CurrentApiState(sender.connection).assess_source_inventory(
                "manual",
                scope={
                    "source_registration_uuidv4": registration,
                    "endpoint": "synthetic-source-inventory",
                },
                observed_at_us=1,
                state="complete",
                members=[owner],
                terminal=True,
                parser_module="synthetic",
                parser_version="1",
            )
        unit = export(sender, owner)
    assert (
        QueryService(sender_path).query("search code", {"literal": "needle"}).status
        == "complete"
    )
    assert not any(
        row["table"] == "source_inventory_assessments" for row in unit["records"]
    )
    receiver_path = initialize(tmp_path / "receiver")
    with Store(receiver_path) as receiver:
        assert receive(receiver, unit)["staged_records"] == 0
        assert receiver.one("SELECT count(*) FROM source_repositories")[0] == 1
        assert receiver.one("SELECT count(*) FROM source_inventory_assessments")[0] == 0
    for options in (
        {"repo": owner},
        {"repos": [owner]},
        {"repo": owner, "source": registration},
    ):
        selected = QueryService(receiver_path).query(
            "search code", {"literal": "needle", **options}
        )
        assert selected.status == "complete"
        assert selected.data["items"]
        assert not selected.coverage.missing
    for options in ({}, {"source": registration}):
        entire = QueryService(receiver_path).query(
            "search code", {"literal": "needle", **options}
        )
        assert entire.status == "partial"
        assert entire.data["items"]
        assert [gap["reason"] for gap in entire.coverage.missing] == [
            "inventory_incomplete"
        ]
