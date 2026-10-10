"""Adversarial validation of typed owners and verified Git normalization."""

import base64
import copy
import hashlib
import json

import pytest

from repo_catalog.adapters.git.parsing import (
    install_git_object,
    validate_git_acquisition,
)
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.domain.models import CatalogError
from tests.integration.test_catalog3_exchange import databases as databases
from tests.integration.test_catalog3_exchange import (
    fixture,
    receive,
    uid,
)


def git_fixture(db, *, repository=None, suffix="", decoder_settings=None):
    repo, acquisition, snapshot = repository or uid(), uid(), uid()
    if not db.execute(
        "SELECT 1 FROM repositories WHERE repository_uuidv4=?", (repo,)
    ).fetchone():
        db.execute(
            "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'git','{}')",
            (repo,),
        )
    blob = ("hello Git" + suffix).encode()

    def oid(kind, body):
        return hashlib.sha1(
            kind.encode() + b" " + str(len(body)).encode() + b"\0" + body
        ).digest()

    blob_oid = oid("blob", blob)
    tree = b"100644 file.txt\0" + blob_oid
    tree_oid = oid("tree", tree)
    commit = (
        b"tree "
        + tree_oid.hex().encode()
        + b"\nauthor Test <test@example.invalid> 0 +0000\ncommitter Test <test@example.invalid> 0 +0000\n\nmessage\n"
    )
    commit_oid = oid("commit", commit)
    refs = [
        {
            "name": "refs/heads/main",
            "name_b64": base64.b64encode(b"refs/heads/main").decode(),
            "oid": commit_oid.hex(),
            "peeled": None,
            "type": "commit",
        }
    ]
    db.execute(
        "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,kind,object_format,request,roots_manifest) VALUES(?,?,'git','sha1','{}',?)",
        (acquisition, repo, json.dumps(refs)),
    )
    for kind, body in (("blob", blob), ("tree", tree), ("commit", commit)):
        install_git_object(
            db,
            "sha1",
            oid(kind, body),
            kind,
            body,
            repository_uuid=repo,
            acquisition=acquisition,
            **(decoder_settings or {}),
        )
    db.execute(
        "INSERT INTO snapshots(snapshot_id,git_acquisition_id,repository_uuidv4,complete,generation) VALUES(?,?,?,0,1)",
        (snapshot, acquisition, repo),
    )
    db.execute(
        "INSERT INTO ref_observations(repository_uuidv4,snapshot_id,raw_ref_name,kind,object_format,target_oid,target_type) VALUES(?,?,?,'head','sha1',?,'commit')",
        (repo, snapshot, b"refs/heads/main", commit_oid),
    )
    db.execute(
        "INSERT INTO acquisition_roots(git_acquisition_id,repository_uuidv4,object_format,oid,role,complete) VALUES(?,?,'sha1',?,'head',1)",
        (acquisition, repo, commit_oid),
    )
    validate_git_acquisition(db, acquisition)
    db.execute("UPDATE snapshots SET complete=1 WHERE snapshot_id=?", (snapshot,))
    return {
        "repository": repo,
        "acquisition": acquisition,
        "snapshot": snapshot,
        "blob": blob_oid,
        "tree": tree_oid,
        "commit": commit_oid,
    }


def test_git_roundtrip_recomputes_complete_intrinsic_rows(databases):
    source, target = databases
    expected = git_fixture(source)
    unit = Graph(source).export(expected["repository"])
    assert not {"commits", "tree_entries", "commit_parents", "parsed_results"} & {
        r["table"] for r in unit["records"]
    }
    unit["records"].reverse()
    result = receive(target, unit)
    assert result["staged_records"] == 0, target.execute(
        "SELECT table_name,reason FROM exchange_staging"
    ).fetchall()
    assert target.execute("SELECT count(*) FROM available_git_objects").fetchone() == (
        3,
    )
    assert target.execute("SELECT count(*) FROM tree_entries").fetchone() == (1,)
    assert target.execute("SELECT count(*) FROM current_snapshots").fetchone() == (1,)
    assert receive(target, unit)["received_records"] == 0


def test_git_partial_capture_does_not_hide_valid_objects_or_claim_scope(databases):
    source, target = databases
    expected = git_fixture(source)
    unit = Graph(source).export(expected["repository"])
    missing = next(r for r in unit["records"] if r["table"] == "ref_observations")
    partial = {**unit, "records": [r for r in unit["records"] if r is not missing]}
    result = receive(target, partial)
    assert result["staged_records"] > 0
    assert target.execute("SELECT count(*) FROM available_git_objects").fetchone() == (
        3,
    )
    assert target.execute("SELECT count(*) FROM current_snapshots").fetchone() == (0,)
    assert receive(target, {**unit, "records": [missing]})["staged_records"] == 0
    assert target.execute("SELECT count(*) FROM current_snapshots").fetchone() == (1,)


def test_foreign_owner_is_rejected_before_intake(databases):
    source, target = databases
    expected = fixture(source)
    other = fixture(source, source_local="other")
    unit = Graph(source).export(expected["repository"])
    foreign = next(
        r
        for r in Graph(source).export(other["repository"])["records"]
        if r["table"] == "repositories"
    )
    unit["records"].append(foreign)
    with pytest.raises(CatalogError, match="Foreign repository"):
        receive(target, unit)
    assert target.execute("SELECT count(*) FROM exchange_staging").fetchone() == (0,)


def test_unknown_fields_and_untyped_foreign_ids_fail_closed(databases):
    source, target = databases
    expected = fixture(source)
    unit = Graph(source).export(expected["repository"])
    document = next(r for r in unit["records"] if r["table"] == "document_state")
    document["values"]["whole_response"] = "secret response"
    with pytest.raises(CatalogError, match="Unexpected domain"):
        receive(target, unit)
    assert target.execute("SELECT count(*) FROM exchange_staging").fetchone() == (0,)
    unit = Graph(source).export(expected["repository"])
    document = next(r for r in unit["records"] if r["table"] == "document_state")
    document["values"]["change_request_id"] = expected["cr"]
    with pytest.raises(CatalogError, match="portable references"):
        receive(target, unit)


def test_single_immutable_variant_does_not_choose_winner(databases):
    source, target = databases
    expected = fixture(source)
    unit = Graph(source).export(expected["repository"])
    binding = next(r for r in unit["records"] if r["table"] == "repository_bindings")
    conflict = copy.deepcopy(binding)
    conflict["values"]["provider_repository_id"] = "different provider owner"
    unit["records"].append(conflict)
    result = receive(target, unit)
    assert result["staged_records"] > 0
    assert target.execute(
        "SELECT count(*) FROM eligible_document_state"
    ).fetchone() == (0,)
    assert target.execute(
        "SELECT count(*) FROM exchange_staging WHERE reason='conflict:competing_variants'"
    ).fetchone() == (2,)


def test_exchange_preserves_explicit_sender_decoder_without_receiver_winner(databases):
    source, target = databases
    expected = git_fixture(
        source,
        suffix="é",
        decoder_settings={"text_encoding": "latin-1", "metadata_encoding": "latin-1"},
    )
    key, text = source.execute(
        "SELECT decoder_key,raw_text FROM git_text_facts"
    ).fetchone()
    unit = Graph(source).export(expected["repository"])
    assert {"git_commit_facts", "git_text_facts", "git_name_facts"} <= {
        r["table"] for r in unit["records"]
    }
    unit["records"].reverse()
    result = receive(target, unit)
    assert result["staged_records"] == 0, target.execute(
        "SELECT table_name,reason FROM exchange_staging"
    ).fetchall()
    assert target.execute(
        "SELECT decoder_key,raw_text,text_encoding FROM git_text_facts"
    ).fetchall() == [(key, text, "latin-1")]
    assert receive(target, unit)["received_records"] == 0
    assert (
        receive(source, Graph(target).export(expected["repository"]))["staged_records"]
        == 0
    )


def test_forged_sender_decoder_value_does_not_claim_git_bytes(databases):
    source, target = databases
    expected = git_fixture(source)
    unit = Graph(source).export(expected["repository"])
    fact = next(r for r in unit["records"] if r["table"] == "git_text_facts")
    fact["values"]["raw_text"] = "forged derived text"
    result = receive(target, unit)
    assert result["staged_records"] == 1
    assert target.execute("SELECT reason FROM exchange_staging").fetchone() == (
        "invalid:git_decoder_value",
    )
    assert target.execute("SELECT count(*) FROM available_git_objects").fetchone() == (
        3,
    )
    assert target.execute("SELECT count(*) FROM git_text_facts").fetchone() == (0,)


def test_required_shared_git_bytes_repeat_per_owner_and_deduplicate(databases):
    source, target = databases
    first, second = git_fixture(source), git_fixture(source)
    for owner in (first, second):
        unit = Graph(source).export(owner["repository"])
        assert sum(r["table"] == "stored_bytes" for r in unit["records"]) == 3
        assert receive(target, unit)["staged_records"] == 0
    assert target.execute("SELECT count(*) FROM git_objects").fetchone() == (3,)
    assert target.execute("SELECT count(*) FROM stored_bytes").fetchone() == (3,)
    assert target.execute(
        "SELECT count(*) FROM repository_object_sources"
    ).fetchone() == (6,)
    assert target.execute(
        "SELECT count(*) FROM snapshots WHERE complete=1"
    ).fetchone() == (2,)


@pytest.mark.parametrize(
    "table",
    [
        "payload_quarantine",
        "payload_corruption_diagnostics",
        "exchange_admissions",
        "exchange_staging",
    ],
)
def test_local_operational_or_quarantine_record_cannot_enter_domain_wire(
    databases, table
):
    source, target = databases
    expected = fixture(source)
    unit = Graph(source).export(expected["repository"])
    assert table not in {r["table"] for r in unit["records"]}
    unit["records"].append({"table": table, "key": table + ":{}", "values": {}})
    with pytest.raises(CatalogError, match="Unexpected domain"):
        receive(target, unit)
    assert target.execute("SELECT count(*) FROM repositories").fetchone() == (0,)
