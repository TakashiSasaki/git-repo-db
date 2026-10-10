"""Independent native-decoder and late/receipt-loss Exchange boundary probes."""
import copy
import hashlib
import json
import sqlite3
import uuid

import pytest

from test_independent_domain_qa import REPO, graph_fixture, insert, new_store, oid, store
from repo_catalog.adapters.git.parsing import GitParsing
from repo_catalog.adapters.sqlite.coverage import admit_claim
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.catalog_validation import check_catalog
from repo_catalog.application.git_query_context import decoded_fact, decoded_name
from repo_catalog.domain.models import CatalogError


FAMILIES = [("git_text_facts", "raw_text"), ("git_commit_facts", "message_text"), ("git_name_facts", "decoded_name")]
SETTING_FIELDS = ("parser_module", "parser_version", "text_encoding", "metadata_encoding", "metadata_errors", "max_text_blob_bytes")


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("family,field", FAMILIES)
def test_native_decoder_insert_compares_actual_bytes(store, fmt, family, field):
    graph_fixture(store, fmt)
    forged = dict(store.one(f"SELECT * FROM {family}"))
    forged["parser_module"], forged["parser_version"] = "independent-native-qa", "fresh-attribution"
    settings = {k: forged[k] for k in SETTING_FIELDS}
    forged["decoder_key"] = hashlib.sha256(json.dumps(settings, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if "git_fact_uuidv4" in forged:
        forged["git_fact_uuidv4"] = str(uuid.uuid4())
    forged[field] = "ordinary false decoder claim"
    if family == "git_text_facts":
        forged["text_state"] = "eligible"
    before = store.one(f"SELECT count(*) FROM {family}")[0]
    with pytest.raises(sqlite3.IntegrityError, match="decoder value contradicts"):
        insert(store, family, **forged)
    assert store.one(f"SELECT count(*) FROM {family}")[0] == before
    assert check_catalog(store, full=True) == []


@pytest.mark.parametrize("family,field", FAMILIES)
def test_retained_decoder_damage_is_excluded_and_diagnosed(store, tmp_path, family, field):
    default, _acq, ids, bodies, _head = graph_fixture(store)
    latin = GitParsing(store, REPO, text_encoding="latin-1", metadata_encoding="latin-1")
    for typ, body in bodies.items():
        latin.parse_object(store.one("SELECT * FROM git_objects WHERE git_object_id=?", (ids[typ],)), body)
    # Explicit retained-row corruption injection, restoring the identical guard.
    trigger = store.one("SELECT sql FROM sqlite_schema WHERE name=?", (family + "_immutable",))[0]
    with store.transaction():
        store.execute(f"DROP TRIGGER {family}_immutable")
        changes = f"{field}=?" + (",text_state='eligible'" if family == "git_text_facts" else "")
        store.execute(f"UPDATE {family} SET {changes} WHERE decoder_key=?", ("retained decoder damage", default.decoder_key))
        store.execute(trigger)
    assert store.one("SELECT sql FROM sqlite_schema WHERE name=?", (family + "_immutable",))[0] == trigger
    if family == "git_name_facts":
        decoded = decoded_name(store, ids["tree"], b"odd-\xff.txt")
        assert decoded["decoded_name"] == "odd-ÿ.txt"
    else:
        typ = "blob" if family == "git_text_facts" else "commit"
        decoded = decoded_fact(store, ids[typ], typ)
        assert decoded["fact"][field] == ("ÿhello" if typ == "blob" else "ÿmessage\n")
    assert not decoded["decoder_conflict"]
    assert not store.one(f"SELECT 1 FROM valid_{family} WHERE decoder_key=?", (default.decoder_key,))
    issues = check_catalog(store, full=True)
    assert any(issue["code"] == "GIT_DECODER_FACT" and issue["table"] == family and issue["decoder_key"] == default.decoder_key for issue in issues)
    unit = Graph(store.connection).export(REPO)
    with new_store(tmp_path / "receiver") as target:
        outcome = Graph(target.connection).receive(unit)
        assert outcome["rejected_records"] == 1 and outcome["staged_records"] == 0
        assert check_catalog(target, full=True) == []


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_strict_metadata_diagnostic_keeps_existing_canonical_structure(store, fmt):
    tree = oid(fmt, "tree", b"")
    raw = b"tree " + tree.hex().encode() + b"\nauthor QA <qa@example.invalid> 0 +0000\n\n\xffmessage"
    parser = GitParsing(store)
    ident = parser.install_object(fmt, oid(fmt, "commit", raw), "commit", raw, decode=False)
    obj = store.one("SELECT * FROM git_objects WHERE git_object_id=?", (ident,))
    before = store.revision()
    with pytest.raises(CatalogError) as failure:
        GitParsing(store, metadata_errors="strict").parse_object(obj, raw)
    assert failure.value.code == "PARSER_DECODE"
    assert store.revision() == before
    assert store.one("SELECT 1 FROM commits WHERE git_object_id=?", (ident,))
    assert store.one("SELECT count(*) FROM git_commit_facts")[0] == 0
    assert store.one("SELECT count(*) FROM available_git_objects")[0] == 1
    assert check_catalog(store, full=True) == []
    GitParsing(store, metadata_errors="replace").parse_object(obj, raw)
    assert store.one("SELECT message_text FROM valid_git_commit_facts")[0] == "�message"


def test_pending_exact_ref_origin_survives_selected_onward_then_late_arrival(store, tmp_path):
    _parser, acq, _ids, _bodies, _head = graph_fixture(store)
    unit = Graph(store.connection).export(REPO, git_acquisition_id=acq)
    first = {**unit, "records": [r for r in unit["records"] if r["table"] != "ref_observations"]}
    late = {**unit, "records": [r for r in unit["records"] if r["table"] == "ref_observations"]}
    path = tmp_path / "receiver"
    with new_store(path) as target:
        outcome = Graph(target.connection).receive(first)
        assert outcome["staged_records"] > 0
        assert target.one("SELECT reason FROM exchange_staging WHERE table_name='root_origins'")[0] == "missing_captured_ref"
        assert not target.one("SELECT 1 FROM root_origins")
        onward = Graph(target.connection).export(REPO, git_acquisition_id=acq)
        assert any(r["table"] == "root_origins" for r in onward["records"])
        for table in ("snapshots", "acquisition_roots"):
            records = [r for r in onward["records"] if r["table"] == table]
            assert len(records) == len({r["key"] for r in records}) == 1
    with new_store(tmp_path / "third") as third:
        pending = Graph(third.connection).receive(onward)
        assert pending["staged_records"] > 0
        assert not third.one("SELECT 1 FROM exchange_staging WHERE reason LIKE 'conflict:%'")
        assert Graph(third.connection).receive(late)["staged_records"] == 0
        assert third.one("SELECT snapshot_id FROM current_snapshots")[0] == acq
        assert third.one("SELECT count(*) FROM root_origins")[0] == 1
    with Store(path) as target:
        assert Graph(target.connection).receive(late)["staged_records"] == 0
        assert target.one("SELECT snapshot_id FROM current_snapshots")[0] == acq
        assert target.one("SELECT count(*) FROM root_origins")[0] == 1
        assert Graph(target.connection).receive(unit)["staged_records"] == 0
        assert check_catalog(target, full=True) == []


@pytest.mark.parametrize("keep_admissions", [False, True])
def test_receipt_loss_and_new_aliases_do_not_own_git_closure(store, tmp_path, keep_admissions):
    _parser, acq, _ids, _bodies, _head = graph_fixture(store)
    scope = "independent-git-closure"
    insert(store, "coverage_scopes", coverage_scope_id=scope, repository_uuidv4=REPO, kind="git")
    admit_claim(store.connection, scope, "complete", 0, json.dumps({"snapshot_id": acq, "git_acquisition_id": acq}))
    unit = Graph(store.connection).export(REPO)
    assert any(r["table"] == "coverage_claims" and r.get("requires") for r in unit["records"])
    with new_store(tmp_path / "receiver") as target:
        assert Graph(target.connection).receive(unit)["staged_records"] == 0
        before = {table: target.one(f"SELECT count(*) FROM {table}")[0] for table in ("git_objects", "acquisition_roots", "root_origins", "coverage_claims")}
        with target.transaction():
            target.execute("DELETE FROM exchange_local_identities")
            if not keep_admissions:
                target.execute("DELETE FROM exchange_admissions")
        onward = Graph(target.connection).export(REPO)
        assert Graph(target.connection).receive(unit)["staged_records"] == 0
        assert {table: target.one(f"SELECT count(*) FROM {table}")[0] for table in before} == before
        assert target.one("SELECT snapshot_id FROM current_snapshots")[0] == acq
        assert check_catalog(target, full=True) == []
        with new_store(tmp_path / "third") as third:
            assert Graph(third.connection).receive(onward)["staged_records"] == 0
            assert Graph(third.connection).receive(unit)["staged_records"] == 0
            assert third.one("SELECT count(*) FROM acquisition_roots")[0] == 1
            assert third.one("SELECT count(*) FROM root_origins")[0] == 1
