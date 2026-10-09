"""Production Git interpretation contracts over independently retained raw inputs."""

import json
import shutil
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.git.parsing import reparse_git
from repo_catalog.adapters.sqlite.cas_integrity import (
    diagnose_corruption,
    repair_payload,
)
from repo_catalog.adapters.sqlite.parser_model import ParserModel
from repo_catalog.domain.models import CatalogError
from tests.integration.test_catalog3_git_runtime import collect, register, runtime
from tests.support.git_fixture import FixtureRepo


def fixture(tmp_path):
    remote = FixtureRepo(tmp_path / "remote.git")
    remote.commit("A", {b"a.txt": b"immutable raw input"})
    remote.ref("refs/heads/main", "A")
    return remote


def insert_fact(store, table, row):
    store.execute(
        f"INSERT INTO {table}({','.join(row)}) VALUES({','.join('?' for _ in row)})",
        tuple(row.values()),
    )


def test_offline_git_reparse_preserves_acquisition_and_byte_identities(tmp_path):
    remote = fixture(tmp_path)
    with runtime(tmp_path) as store:
        repo = register(store, remote.url)
        original = collect(store, repo)
        acquisition = original["git_acquisition_id"]
        before = {
            table: [tuple(row) for row in store.all(f"SELECT * FROM {table}")]
            for table in (
                "git_acquisitions",
                "git_objects",
                "git_object_payloads",
                "git_acquisition_publications",
                "stored_bytes",
            )
        }
        original_result = store.one(
            "SELECT parsed_result_uuidv4 FROM current_snapshots"
        )[0]
        shutil.rmtree(store.path / "cache")
        alternative = reparse_git(store, acquisition)
        assert alternative["parsed_result_uuidv4"] != original_result
        assert (
            store.one("SELECT parsed_result_uuidv4 FROM current_snapshots")[0]
            == original_result
        )
        for table, rows in before.items():
            assert [tuple(row) for row in store.all(f"SELECT * FROM {table}")] == rows
        with store.transaction():
            ParserModel(store.connection).select_fact(
                alternative["parsed_result_uuidv4"], fact_kind="git"
            )
            ParserModel(store.connection).select_fact(
                alternative["parsed_result_uuidv4"],
                fact_kind="git",
                git_acquisition_id=acquisition,
            )
        assert (
            store.one("SELECT parsed_result_uuidv4 FROM current_snapshots")[0]
            == alternative["parsed_result_uuidv4"]
        )
        outputs = json.loads(
            store.one(
                "SELECT fact_manifest_json FROM parsed_result_publications WHERE parsed_result_uuidv4=?",
                (alternative["parsed_result_uuidv4"],),
            )[0]
        )
        assert {member["table"] for member in outputs} >= {
            "snapshots",
            "ref_observations",
            "commits",
            "tree_entries",
            "git_text_facts",
            "root_manifests",
            "root_manifest_entries",
        }
        assert not store.all("PRAGMA foreign_key_check")
        assert store.one("PRAGMA integrity_check")[0] == "ok"


@pytest.mark.parametrize(
    "attack", ["late", "update", "delete", "replace", "null", "other-owner"]
)
def test_result_owned_git_facts_reject_sql_history_reinterpretation(tmp_path, attack):
    remote = fixture(tmp_path)
    with runtime(tmp_path) as store:
        repo = register(store, remote.url)
        collect(store, repo)
        row = dict(store.one("SELECT * FROM git_text_facts"))
        with pytest.raises(sqlite3.IntegrityError):
            if attack == "update":
                store.execute("UPDATE git_text_facts SET raw_text='changed'")
            elif attack == "delete":
                store.execute("DELETE FROM git_text_facts")
            elif attack == "replace":
                values = dict(row)
                values["raw_text"] = "changed"
                store.execute(
                    f"INSERT OR REPLACE INTO git_text_facts({','.join(values)}) VALUES({','.join('?' for _ in values)})",
                    tuple(values.values()),
                )
            else:
                values = dict(row)
                values["git_fact_uuidv4"] = str(uuid.uuid4())
                if attack == "null":
                    values["repository_uuidv4"] = None
                if attack == "other-owner":
                    values["repository_uuidv4"] = "20000000-0000-4000-8000-000000000001"
                insert_fact(store, "git_text_facts", values)
        assert dict(store.one("SELECT * FROM git_text_facts")) == row


def test_quarantine_disables_git_input_and_reparse_without_repairing_history(tmp_path):
    remote = fixture(tmp_path)
    with runtime(tmp_path) as store:
        repo = register(store, remote.url)
        original = collect(store, repo)
        # A different acquisition's distinct raw object subgraph stays usable.
        other_remote = FixtureRepo(tmp_path / "unrelated.git")
        other_remote.commit("U", {b"different.txt": b"unrelated acquisition text"})
        other_remote.ref("refs/heads/main", "U")
        other_owner = "20000000-0000-4000-8000-000000000001"
        from repo_catalog.application.repository_identity import add_endpoint

        with store.transaction():
            store.execute(
                "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'other','{}')",
                (other_owner,),
            )
            add_endpoint(store, other_owner, other_remote.url)
        collect(store, {"repository_uuidv4": other_owner, "name": "other"})
        physical = store.one(
            "SELECT p.payload_sha256,s.body FROM git_object_payloads p JOIN stored_bytes s ON s.sha256=p.payload_sha256 JOIN git_objects g USING(git_object_id) WHERE g.type='blob' AND s.body=?",
            (b"immutable raw input",),
        )
        digest, raw = physical
        trigger = store.one(
            "SELECT sql FROM sqlite_schema WHERE name='stored_bytes_immutable'"
        )[0]
        store.execute("DROP TRIGGER stored_bytes_immutable")
        store.execute(
            "UPDATE stored_bytes SET body=? WHERE sha256=?", (b"x" * len(raw), digest)
        )
        store.execute(trigger)
        diagnose_corruption(store.connection, digest)
        assert store.one("SELECT count(*) FROM current_snapshots")[0] == 1
        assert (
            store.one("SELECT repository_uuidv4 FROM current_snapshots")[0]
            == other_owner
        )
        assert store.one("SELECT count(*) FROM current_git_text_facts")[0] == 1
        with pytest.raises(CatalogError, match="Quarantined"):
            reparse_git(store, original["git_acquisition_id"])
        assert store.one("SELECT count(*) FROM parsed_results")[0] == 2
        repair_payload(store.connection, digest, raw)
        assert store.one("SELECT count(*) FROM current_snapshots")[0] == 2
        assert (
            store.one(
                "SELECT raw_text FROM current_git_text_facts WHERE repository_uuidv4=?",
                (repo["repository_uuidv4"],),
            )[0]
            == raw.decode()
        )


def test_invalid_selected_verification_never_substitutes_newer_evidence(tmp_path):
    remote = fixture(tmp_path)
    with runtime(tmp_path) as store:
        repo = register(store, remote.url)
        collect(store, repo)
        model = ParserModel(store.connection)
        selected = store.one(
            "SELECT parser_profile_uuidv4,parser_profile_verification_uuidv4 FROM parser_profile_selection_decisions"
        )
        evidence = json.loads(
            store.one(
                "SELECT evidence_json FROM parser_profile_verifications WHERE parser_profile_verification_uuidv4=?",
                (selected[1],),
            )[0]
        )
        with store.transaction():
            newer = model.verify_profile(
                selected[0], criteria={"test": "new passing run"}, evidence=evidence
            )
            model.trust_verification(newer)
            model.invalidate_verification(selected[1], "selected evidence withdrawn")
        assert store.one("SELECT count(*) FROM current_snapshots")[0] == 0
        assert store.one("SELECT count(*) FROM current_git_commits")[0] == 0
        assert store.one("SELECT count(*) FROM commits")[0] == 1


def test_identical_git_bytes_keep_distinct_profile_metadata_and_text(tmp_path):
    from tests.integration.test_catalog3_git_readers import latin_profile
    from tests.support.git_fixture import git

    remote = FixtureRepo(tmp_path / "metadata.git")
    tree = remote.tree({b"a.txt": b"\xfftext"})
    commit = (
        git(
            remote.path,
            "commit-tree",
            tree,
            input="unicode 認証 message\n".encode(),
            extra={"GIT_AUTHOR_NAME": "認証"},
        )
        .strip()
        .decode()
    )
    remote.ref("refs/heads/main", commit)
    with runtime(tmp_path) as store:
        repo = register(store, remote.url)
        acquisition = collect(store, repo)["git_acquisition_id"]
        original = dict(store.one("SELECT * FROM current_git_commits"))
        assert "認証" in json.loads(original["metadata"])["author"]
        assert (
            store.one("SELECT text_state FROM current_git_text_facts")[0] == "non_utf8"
        )
        model = ParserModel(store.connection)
        with store.transaction():
            profile, verification = latin_profile(model)
        alternative = reparse_git(store, acquisition, profile_uuid=profile)
        interpreted = store.one(
            "SELECT * FROM commits WHERE parsed_result_uuidv4=?",
            (alternative["parsed_result_uuidv4"],),
        )
        assert interpreted["git_object_id"] == original["git_object_id"]
        assert interpreted["raw_headers"] == original["raw_headers"]
        assert (
            "認証".encode().decode("latin-1")
            in json.loads(interpreted["metadata"])["author"]
        )
        assert (
            store.one(
                "SELECT raw_text FROM git_text_facts WHERE parsed_result_uuidv4=?",
                (alternative["parsed_result_uuidv4"],),
            )[0]
            == "ÿtext"
        )
        assert (
            store.one("SELECT parsed_result_uuidv4 FROM current_git_commits")[0]
            == original["parsed_result_uuidv4"]
        )
        with store.transaction():
            model.select_profile(
                profile,
                verification,
                repository_uuidv4=repo["repository_uuidv4"],
                fact_kind="git",
            )
            model.select_fact(alternative["parsed_result_uuidv4"], fact_kind="git")
            model.select_fact(
                alternative["parsed_result_uuidv4"],
                fact_kind="git",
                git_acquisition_id=acquisition,
            )
        assert store.one("SELECT raw_text FROM current_git_text_facts")[0] == "ÿtext"
        assert store.one("SELECT count(*) FROM git_objects")[0] == 3
        assert store.one("SELECT count(*) FROM git_object_payloads")[0] == 3


@pytest.mark.parametrize("reverse", [False, True])
def test_conflicting_git_fact_uuid_never_selects_arrival_order_winner(
    tmp_path, reverse
):
    import copy

    from repo_catalog.adapters.sqlite.exchange import Graph

    remote = fixture(tmp_path)
    sender = tmp_path / "sender"
    receiver = tmp_path / "receiver"
    sender.mkdir()
    receiver.mkdir()
    with runtime(sender) as store:
        repo = register(store, remote.url)
        collect(store, repo)
        unit = Graph(store.connection).export(repo["repository_uuidv4"])
    variant = copy.deepcopy(unit)
    fact = next(
        record for record in variant["records"] if record["table"] == "git_text_facts"
    )
    fact["values"]["raw_text"] = "conflicting immutable interpretation"
    with runtime(receiver) as store:
        graph = Graph(store.connection)
        for incoming in [variant, unit] if reverse else [unit, variant]:
            graph.receive(incoming)
            for verification in store.all(
                "SELECT parser_profile_verification_uuidv4 FROM parser_profile_verifications"
            ):
                ParserModel(store.connection).trust_verification(verification[0])
        assert store.one("SELECT count(*) FROM exchange_staging")[0] >= 1
        assert store.one("SELECT count(*) FROM current_snapshots")[0] == 0
        assert store.one("SELECT count(*) FROM current_git_text_facts")[0] == 0
        assert store.one("SELECT count(*) FROM git_text_facts")[0] == 1
        graph.receive(unit)
        assert store.one("SELECT count(*) FROM current_git_text_facts")[0] == 0


def test_interrupted_bounded_git_fact_staging_resumes_original_uuids(
    tmp_path, monkeypatch
):
    from repo_catalog.adapters.git.parsing import GitParsing
    from repo_catalog.application.job_service import JobService

    remote = fixture(tmp_path)
    with runtime(tmp_path) as store:
        repo = register(store, remote.url)
        store.config["collection"]["write_batch_rows"] = 2
        job = JobService(store).create("sync", {"kind": "git"})
        write = GitParsing.write
        emitted = 0

        def interrupt(self, *args):
            nonlocal emitted
            emitted += 1
            if emitted == 4:
                raise CatalogError(
                    "CANCELLED", "Synthetic interruption after committed fact batch"
                )
            return write(self, *args)

        monkeypatch.setattr(GitParsing, "write", interrupt)
        with pytest.raises(CatalogError, match="Synthetic interruption"):
            collect(store, repo, job=job)
        result = store.one("SELECT parsed_result_uuidv4 FROM parsed_results")[0]
        retained = {
            table: [row[0] for row in store.all(f"SELECT git_fact_uuidv4 FROM {table}")]
            for table in ("commits", "tree_entries", "root_manifests", "git_text_facts")
        }
        assert sum(map(len, retained.values())) >= 2
        assert not store.one("SELECT 1 FROM parsed_result_publications")
        assert not store.one("SELECT 1 FROM current_snapshots")
        JobService(store).update(job, "interrupted")
        JobService(store).resume(job)
        monkeypatch.setattr(GitParsing, "write", write)
        collect(store, repo, job=job)
        assert (
            store.one("SELECT parsed_result_uuidv4 FROM current_snapshots")[0] == result
        )
        assert store.one("SELECT count(*) FROM git_acquisitions")[0] == 1
        for table, identities in retained.items():
            assert set(identities) <= {
                row[0] for row in store.all(f"SELECT git_fact_uuidv4 FROM {table}")
            }
        assert store.one("SELECT count(*) FROM parsed_result_publications")[0] == 1
        assert not store.all("PRAGMA foreign_key_check")


def test_exchange_retains_complete_git_manifest_until_exact_publication(tmp_path):
    from repo_catalog.adapters.sqlite.exchange import Graph

    remote = fixture(tmp_path)
    sender = tmp_path / "sender"
    receiver = tmp_path / "receiver"
    sender.mkdir()
    receiver.mkdir()
    with runtime(sender) as store:
        repo = register(store, remote.url)
        collect(store, repo)
        header = dict(store.one("SELECT * FROM root_manifests WHERE complete=1"))
        entry = dict(store.one("SELECT * FROM root_manifest_entries"))
        unit = Graph(store.connection).export(repo["repository_uuidv4"])
    with runtime(receiver) as store:
        graph = Graph(store.connection)
        received = graph.receive(unit)
        assert received["staged_records"] == 0
        restored = store.one(
            "SELECT complete FROM root_manifests WHERE git_fact_uuidv4=?",
            (header["git_fact_uuidv4"],),
        )
        assert restored[0] == 1
        restored_entry = store.one(
            "SELECT raw_path FROM root_manifest_entries WHERE git_fact_uuidv4=?",
            (entry["git_fact_uuidv4"],),
        )
        assert restored_entry[0] == entry["raw_path"]
        assert graph.receive(unit)["staged_records"] == 0
        assert store.one("SELECT count(*) FROM root_manifest_entries")[0] == 1
        with pytest.raises(sqlite3.IntegrityError, match="sealed"):
            # Receiver-local parent identities were remapped; use its stored row.
            late = dict(store.one("SELECT * FROM root_manifest_entries"))
            late["git_fact_uuidv4"] = str(uuid.uuid4())
            late["raw_path"] = b"late"
            insert_fact(store, "root_manifest_entries", late)
        assert not store.all("PRAGMA foreign_key_check")
