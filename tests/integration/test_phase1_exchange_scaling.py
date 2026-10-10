"""Guard repository-scoped Exchange work against unrelated catalog growth."""

import hashlib
import json
import sqlite3
import uuid

from repo_catalog.adapters.sqlite.cas_integrity import register_git_object_sql_function
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.adapters.sqlite.schema import schema_sql


def _uid():
    return str(uuid.uuid4())


def _catalog():
    db = sqlite3.connect(":memory:", isolation_level=None)
    register_git_object_sql_function(db)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA recursive_triggers=ON")
    db.executescript(schema_sql())
    return db


def _repository(db, name):
    repository = _uid()
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,?,'{}')",
        (repository, name),
    )
    return repository


def _git_acquisition(db, repository):
    acquisition = _uid()
    db.execute(
        "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,object_format,kind,request) "
        "VALUES(?,?,'sha1','git','{}')",
        (acquisition, repository),
    )
    return acquisition


def _add_unrelated_git_objects(db, repositories, count):
    """Add actual Git blob bodies with matching SHA-1 identities and CAS rows."""
    acquisitions = [_git_acquisition(db, repository) for repository in repositories]
    db.execute("BEGIN")
    try:
        for index in range(count):
            body = f"unrelated-repository-object-{index:06d}".encode()
            oid = hashlib.sha1(f"blob {len(body)}\0".encode() + body).digest()
            reference = intern_payload(db, body, representation="git-object-raw-v1")
            git_object_id = db.execute(
                "INSERT INTO git_objects(object_format,oid,type,size,verified) "
                "VALUES('sha1',?,'blob',?,1) RETURNING git_object_id",
                (oid, len(body)),
            ).fetchone()[0]
            db.execute(
                "INSERT INTO git_object_payloads(git_object_id,payload_representation,payload_sha256) "
                "VALUES(?,'git-object-raw-v1',?)",
                (git_object_id, reference.sha256),
            )
            repository = repositories[index % len(repositories)]
            db.execute(
                "INSERT INTO repository_object_sources(repository_uuidv4,git_object_id,git_acquisition_id) "
                "VALUES(?,?,?)",
                (repository, git_object_id, acquisitions[index % len(acquisitions)]),
            )
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise


def _measure_vm_steps(db, operation):
    """Return a stable SQLite VM-work estimate without using wall time."""
    callbacks = 0

    def progress():
        nonlocal callbacks
        callbacks += 1
        return 0

    db.set_progress_handler(progress, 100)
    try:
        value = operation()
    finally:
        db.set_progress_handler(None, 0)
    # SQLite invokes the callback every 100 VM opcodes. The estimate is within
    # 99 opcodes of the actual work and is deterministic for this connection.
    return callbacks * 100, value


def test_export_vm_work_is_scoped_away_from_thousands_of_unrelated_git_objects():
    db = _catalog()
    try:
        selected = _repository(db, "selected")
        unrelated = [_repository(db, "unrelated-a"), _repository(db, "unrelated-b")]

        def graph():
            return Graph(db, persist_identities=False).export(selected)

        before_steps, before_export = _measure_vm_steps(db, graph)
        _add_unrelated_git_objects(db, unrelated, 4096)
        after_steps, after_export = _measure_vm_steps(db, graph)

        # Each exchange unit has a fresh origin-catalog identity. Its selected
        # repository graph and record order must remain identical.
        assert after_export["repository_uuidv4"] == before_export["repository_uuidv4"]
        assert after_export["records"] == before_export["records"]
        assert len(after_export["records"]) == 1
        # A global walk of git_object_payloads performs many VM operations for
        # every added object. Repository-scoped export must stay effectively
        # constant as other repositories accumulate Git history.
        assert after_steps <= before_steps + 2_000
    finally:
        db.close()


def test_intake_context_does_not_materialize_unrelated_admission_receipts():
    db = _catalog()
    try:
        selected = _repository(db, "selected")
        unrelated = _repository(db, "unrelated")
        # These are deliberately synthetic receipt-shaped bookkeeping rows,
        # not claimed to be admitted logical domain facts. Their large valid
        # JSON makes a global parse/materialization regression observable.
        receipt_json = json.dumps(
            {
                "key": "synthetic-unrelated-receipt",
                "table": "repositories",
                "values": {
                    "repository_uuidv4": unrelated,
                    "name": "unrelated",
                    "metadata": "{}",
                    "padding": "x" * 1024,
                },
            },
            separators=(",", ":"),
        )
        db.executemany(
            "INSERT INTO exchange_admissions(record_key,table_name,local_key_json,content_sha256,record_json) "
            "VALUES(?,?,?,?,?)",
            (
                (
                    f"synthetic-receipt-{index:06d}",
                    "repositories",
                    json.dumps({"repository_uuidv4": unrelated}, separators=(",", ":")),
                    bytes(32),
                    receipt_json,
                )
                for index in range(12000)
            ),
        )

        statements = []
        db.set_trace_callback(statements.append)
        try:
            context = Graph(db, persist_identities=False).original_intake_context(
                repository_uuidv4=selected
            )
        finally:
            db.set_trace_callback(None)

        assert context == []
        global_receipt_scans = [
            statement
            for statement in statements
            if "FROM EXCHANGE_ADMISSIONS" in statement.upper()
            and "WHERE RECORD_KEY" not in statement.upper()
        ]
        assert global_receipt_scans == []
    finally:
        db.close()
