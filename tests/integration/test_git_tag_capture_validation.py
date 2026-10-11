"""Captured tag peels are canonical relationships, including selected late intake."""

import base64
import copy
import json
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.git.parsing import GitParsing
from repo_catalog.adapters.sqlite.exchange import (
    Graph,
    canonical,
    encode,
    record_digest,
)
from repo_catalog.adapters.sqlite.index import rebuild
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.catalog_validation import check_catalog
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.query_service import QueryService
from repo_catalog.domain.git_intrinsic import tag_structure
from repo_catalog.domain.models import CatalogError
from tests.integration.test_catalog3_git_runtime import collect, register, runtime
from tests.integration.test_git_direct_objects import OWNER, oid
from tests.integration.test_phase1_exchange_scaling import _measure_vm_steps
from tests.support.git_fixture import FixtureRepo, git

REF = b"refs/tags/nested"
UNRELATED = "unrelated retained content"


def put(store, table, **values):
    return store.execute(
        f"INSERT INTO {table}({','.join(values)}) VALUES({','.join('?' for _ in values)})",
        tuple(values.values()),
    )


def opened(path):
    MaintenanceService(path).init("catalog-text-v1", 64 * 1024 * 1024, 0)
    return Store(path)


def capture(store, fmt, kind="commit", *, attack=None):
    put(store, "repositories", repository_uuidv4=OWNER, name="tags", metadata="{}")
    objects, terminals = [], []
    for content in (b"actual captured content", UNRELATED.encode()):
        blob = oid(fmt, "blob", content)
        tree = b"100644 file.txt\0" + blob
        commit = b"tree " + oid(fmt, "tree", tree).hex().encode() + b"\n\n" + content
        selected = [("blob", content), ("tree", tree), ("commit", commit)]
        terminal = next(body for typ, body in selected if typ == kind)
        objects.extend(selected[: [typ for typ, _ in selected].index(kind) + 1])
        terminals.append(oid(fmt, kind, terminal))
    current, target_type = terminals[0], kind
    tags = []
    for index in range(3):
        raw = (
            b"object "
            + current.hex().encode()
            + b"\ntype "
            + target_type.encode()
            + b"\ntag nested-"
            + str(index).encode()
            + b"\n\ncanonical tag"
        )
        current, target_type = oid(fmt, "tag", raw), "tag"
        tags.append(current)
        objects.append(("tag", raw))
    peeled = (
        terminals[1]
        if attack == "unrelated"
        else tags[0]
        if attack == "intermediate"
        else terminals[0]
    )
    if attack == "missing-peel":
        peeled = None
    if attack == "type":
        target_type = "commit"
    acquisition = str(uuid.uuid4())
    manifest = [
        {
            "name": REF.decode(),
            "name_b64": base64.b64encode(REF).decode(),
            "oid": current.hex(),
            "type": target_type,
            "peeled": peeled.hex() if peeled is not None else None,
        }
    ]
    put(
        store,
        "git_acquisitions",
        git_acquisition_id=acquisition,
        repository_uuidv4=OWNER,
        object_format=fmt,
        kind="git",
        request="{}",
        roots_manifest=json.dumps(manifest),
        refs_observed_at_us=0,
    )
    parser = GitParsing(store, OWNER)
    for typ, raw in objects:
        parser.install_object(
            fmt, oid(fmt, typ, raw), typ, raw, acquisition=acquisition
        )
    put(
        store,
        "snapshots",
        snapshot_id=acquisition,
        git_acquisition_id=acquisition,
        repository_uuidv4=OWNER,
        complete=0,
        generation=0,
        created_at_us=0,
    )
    put(
        store,
        "ref_observations",
        snapshot_id=acquisition,
        repository_uuidv4=OWNER,
        raw_ref_name=REF,
        kind="tag",
        object_format=fmt,
        target_oid=current,
        target_type=target_type,
        peeled_oid=peeled,
    )
    root = put(
        store,
        "acquisition_roots",
        git_acquisition_id=acquisition,
        repository_uuidv4=OWNER,
        object_format=fmt,
        oid=peeled or current,
        role="tag",
        expected_oid=peeled or current,
        complete=0,
    ).lastrowid
    put(
        store,
        "root_origins",
        acquisition_root_id=root,
        repository_uuidv4=OWNER,
        origin_kind="ref",
        raw_ref_name=REF,
        source_ordinal=0,
        snapshot_id=acquisition,
    )
    return acquisition, root, terminals, parser


def complete(store):
    store.execute("UPDATE acquisition_roots SET complete=1")
    store.execute("UPDATE snapshots SET complete=1")


def export(store, acquisition=None):
    with store.transaction():
        return Graph(store.connection).export(OWNER, git_acquisition_id=acquisition)


def receive(store, unit):
    with store.transaction():
        return Graph(store.connection).receive(unit)


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize(
    "attack", ["unrelated", "intermediate", "missing-peel", "type"]
)
def test_false_tag_capture_never_grants_native_completion_or_query_provenance(
    tmp_path, fmt, attack
):
    with runtime(tmp_path) as store:
        acquisition, root, _, parser = capture(store, fmt, attack=attack)
        assert not store.one("SELECT 1 FROM available_git_acquisitions")
        with pytest.raises(CatalogError) as error:
            parser.validate_acquisition(acquisition)
        assert error.value.code == "GIT_REF_IDENTITY"
        with pytest.raises(sqlite3.IntegrityError, match="closure incomplete"):
            store.execute("UPDATE acquisition_roots SET complete=1")
        with pytest.raises(sqlite3.IntegrityError, match="after exact closure"):
            row = dict(store.one("SELECT * FROM acquisition_roots"))
            row.update(acquisition_root_id=root + 1, role="insertion", complete=1)
            put(store, "acquisition_roots", **row)
        # Simulate damaged retained completion flags, then restore the exact DDL.
        guards = [
            store.one("SELECT sql FROM sqlite_schema WHERE name=?", (name,))[0]
            for name in ("acquisition_roots_complete", "snapshots_complete_update")
        ]
        with store.transaction():
            store.execute("DROP TRIGGER acquisition_roots_complete")
            store.execute("DROP TRIGGER snapshots_complete_update")
            complete(store)
            for guard in guards:
                store.execute(guard)
        assert not store.one("SELECT 1 FROM available_snapshots")
        assert any(
            issue.get("code") == "GIT_REF_IDENTITY"
            for issue in check_catalog(store, full=True)
        )
        with pytest.raises(CatalogError) as error:
            export(store, acquisition)
        assert error.value.code == "GIT_REF_IDENTITY"
        query = dict(
            repos=[OWNER], scope="recorded", refs=[REF.decode()], literal=UNRELATED
        )
        assert QueryService(store.path).query("search code", query).data["items"] == []
        rebuild(store, "code")
        assert QueryService(store.path).query("search code", query).data["items"] == []


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("kind", ["blob", "tree", "commit"])
def test_nested_tags_to_all_real_terminal_types_roundtrip(tmp_path, fmt, kind):
    with runtime(tmp_path) as store:
        acquisition, _, _, parser = capture(store, fmt, kind)
        assert (
            parser.validate_acquisition(acquisition)
            == 3 + ["blob", "tree", "commit"].index(kind) + 1
        )
        complete(store)
        assert store.one("SELECT 1 FROM available_snapshots")
        assert check_catalog(store, full=True) == []
        unit = export(store, acquisition)
    unit["records"].reverse()
    with opened(tmp_path / "receiver") as receiver:
        assert receive(receiver, unit)["staged_records"] == 0
        assert receiver.one("SELECT 1 FROM available_snapshots")
        assert receive(receiver, unit)["received_records"] == 0
        assert check_catalog(receiver, full=True) == []


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_matching_wire_peel_copies_cannot_override_raw_tag_chain(tmp_path, fmt):
    with runtime(tmp_path) as store:
        _, _, terminals, _ = capture(store, fmt)
        complete(store)
        unit = export(store)
    for record in unit["records"]:
        values = record["values"]
        if record["table"] == "git_acquisitions":
            refs = json.loads(values["roots_manifest"])
            refs[0]["peeled"] = terminals[1].hex()
            values["roots_manifest"] = json.dumps(refs)
        elif record["table"] == "ref_observations":
            values["peeled_oid"] = encode(terminals[1])
        elif record["table"] == "acquisition_roots":
            values["oid"] = values["expected_oid"] = encode(terminals[1])
    unit["records"].reverse()
    with opened(tmp_path / "receiver") as receiver:
        receive(receiver, unit)
        assert not receiver.one("SELECT 1 FROM snapshots WHERE complete=1")
        assert not receiver.one("SELECT 1 FROM available_git_acquisitions")
        reasons = [
            tuple(row)
            for row in receiver.all(
                "SELECT record_key,reason FROM exchange_staging ORDER BY record_key"
            )
        ]
        assert any(reason == "invalid:git_ref_identity" for _, reason in reasons)
        receive(receiver, unit)
        assert reasons == [
            tuple(row)
            for row in receiver.all(
                "SELECT record_key,reason FROM exchange_staging ORDER BY record_key"
            )
        ]
        with pytest.raises(CatalogError):
            export(receiver)


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_selected_pending_tag_bytes_survive_onward_and_late_delivery(tmp_path, fmt):
    with runtime(tmp_path) as store:
        acquisition, _, terminals, _ = capture(store, fmt, "blob")
        complete(store)
        unit = export(store)
    obj = next(
        row
        for row in unit["records"]
        if row["table"] == "git_objects"
        and row["values"]["oid"] == encode(terminals[0])
    )
    mapping = next(
        row
        for row in unit["records"]
        if row["table"] == "git_object_payloads"
        and row["values"]["git_object_id"]["$ref"] == obj["key"]
    )
    payload = next(
        row
        for row in unit["records"]
        if row["key"] == mapping["values"]["payload_sha256"]["$ref"]
    )
    raw = next(
        row
        for row in unit["records"]
        if row["key"] == payload["values"]["sha256"]["$ref"]
    )
    late = {raw["key"], payload["key"]}
    prefix = {
        **unit,
        "records": [row for row in reversed(unit["records"]) if row["key"] not in late],
    }
    path = tmp_path / "receiver"
    with opened(path) as receiver:
        assert receive(receiver, prefix)["staged_records"] > 0
        assert check_catalog(receiver, full=True) == []
        before, onward = _measure_vm_steps(
            receiver.connection, lambda: export(receiver, acquisition)
        )
        expected = {row["key"] for row in onward["records"]}
        assert mapping["key"] in expected
        # Genuine-shaped pending mappings for unrelated natural Git identities
        # must neither enter this closure nor make it scan the entire intake.
        with receiver.transaction():
            for index in range(1000):
                extra = copy.deepcopy(mapping)
                identity = canonical(
                    {
                        "object_format": fmt,
                        "oid": encode(oid(fmt, "blob", str(index).encode())),
                    }
                )
                extra["values"]["git_object_id"]["$ref"] = "git_objects:" + identity
                extra["key"] = "git_object_payloads:" + canonical(
                    {"git_object_id": extra["values"]["git_object_id"]}
                )
                receiver.execute(
                    "INSERT INTO exchange_staging VALUES(?,?,?,?,?,?,?)",
                    (
                        extra["key"],
                        record_digest(extra),
                        extra["table"],
                        OWNER,
                        unit["origin_catalog_uuidv4"],
                        canonical(extra),
                        "missing_dependency",
                    ),
                )
        after, selected = _measure_vm_steps(
            receiver.connection, lambda: export(receiver, acquisition)
        )
        assert {row["key"] for row in selected["records"]} == expected
        assert after <= before + 15000
    with opened(tmp_path / "onward") as onward_receiver:
        receive(onward_receiver, onward)
        assert not onward_receiver.one("SELECT 1 FROM available_snapshots")
        result = receive(onward_receiver, {**unit, "records": [raw, payload]})
        assert result["staged_records"] == 0, result
        assert result["rejected_records"] == 0
        assert onward_receiver.one("SELECT 1 FROM available_snapshots")
        assert check_catalog(onward_receiver, full=True) == []
    with Store(path) as receiver:
        # The 1000 deliberately unrelated dependencies remain pending.
        assert (
            receive(receiver, {**unit, "records": [raw, payload]})["staged_records"]
            == 1000
        )
        assert receiver.one("SELECT 1 FROM available_snapshots")


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_native_import_records_fully_peeled_nested_tags(tmp_path, fmt):
    remote = FixtureRepo(tmp_path / "remote.git", fmt)
    terminal = remote.commit("A", {b"file.txt": b"canonical nested bytes"})
    target, target_type = terminal, "commit"
    for index in range(3):
        raw = (
            f"object {target}\ntype {target_type}\ntag depth-{index}\n"
            "tagger Fixture <fixture@example.invalid> 1700000000 +0000\n\ncanonical tag"
        ).encode()
        target = (
            git(remote.path, "hash-object", "-w", "-t", "tag", "--stdin", input=raw)
            .strip()
            .decode()
        )
        target_type = "tag"
    remote.ref(REF.decode(), target)
    with runtime(tmp_path) as store:
        result = collect(store, register(store, remote.url))
        assert (
            store.one("SELECT hex(peeled_oid) FROM ref_observations")[0].lower()
            == terminal
        )
        assert store.one("SELECT 1 FROM available_snapshots")
        assert GitParsing(store).validate_acquisition(result["git_acquisition_id"]) == 6


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("later_header", ["object", "type"])
def test_tag_target_uses_same_initial_identity_headers_as_git(
    tmp_path, fmt, later_header
):
    remote = FixtureRepo(tmp_path / "remote.git", fmt)
    first = remote.commit("A", {b"file.txt": b"actual tag target"})
    other = remote.commit("B", {b"file.txt": b"unrelated target"})
    extra = f"object {other}" if later_header == "object" else "type blob"
    raw = (
        f"object {first}\ntype commit\ntag additional-header\n"
        f"tagger Fixture <fixture@example.invalid> 1700000000 +0000\n{extra}\n\nmessage"
    ).encode()
    tag = (
        git(remote.path, "hash-object", "-w", "-t", "tag", "--stdin", input=raw)
        .strip()
        .decode()
    )
    actual = git(remote.path, "rev-parse", tag + "^{}").strip().decode()
    assert actual == first
    assert tag_structure(fmt, raw) == {
        "target_oid": bytes.fromhex(actual),
        "target_type": "commit",
    }
    remote.ref(REF.decode(), tag)
    with runtime(tmp_path) as store:
        result = collect(store, register(store, remote.url))
        assert store.one("SELECT hex(target_oid) FROM tag_objects")[0].lower() == actual
        assert store.one("SELECT 1 FROM available_snapshots")
        assert GitParsing(store).validate_acquisition(result["git_acquisition_id"]) == 4
        assert not store.one(
            "SELECT 1 FROM git_objects WHERE oid=?", (bytes.fromhex(other),)
        )
