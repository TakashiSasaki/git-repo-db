"""Stdlib-only OP-01 driver copied outside the checkout for each installation.

No rich fixture, acquisition adapter, Context implementation or pytest import is
permitted here. Every catalog below is synthetic, local and disposable.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import os
import runpy
import socket
import sqlite3
import subprocess
import sys
import sysconfig
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from uuid import uuid4


def refuses(callback, exception, code=None):
    try:
        callback()
    except exception as error:
        if code is not None:
            assert error.code == code, (error.code, code)
        return error
    raise AssertionError("operation unexpectedly succeeded")


def mutate(path, table, assignment):
    """Privileged fault injection; restore the exact production trigger schema."""
    with sqlite3.connect(path) as db:
        triggers = db.execute(
            "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name=?",
            (table,),
        ).fetchall()
        for name, _ in triggers:
            db.execute('DROP TRIGGER "' + name + '"')
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("UPDATE " + table + " SET " + assignment)
        for _, sql in triggers:
            db.execute(sql)


def main(output):
    # The isolated interpreter ignores PYTHONPATH for product import isolation.
    # Load the existing stdlib-only guard explicitly, then propagate it to CLI
    # child processes without adding any checkout path.
    harness = Path(__file__).resolve().parent
    runpy.run_path(str(harness / "sitecustomize.py"))
    os.environ["PYTHONPATH"] = str(harness)
    refuses(lambda: socket.getaddrinfo("outside.example.invalid", 443), PermissionError)

    from repo_catalog.adapters.sqlite import p1_schema as schema
    from repo_catalog.adapters.sqlite.core_coordination import (
        SnapshotReadLimits,
        persist_catalog_stop,
    )
    from repo_catalog.adapters.sqlite.git_core import GitCore
    from repo_catalog.application.core_query import CoreQueryService
    from repo_catalog.domain.p1_core import (
        NativeObject,
        RepositoryClaim,
        native_object_oid,
    )
    from repo_catalog.domain.query_contracts import PageRequest, QueryError
    from repo_catalog.domain.query_work import UnlimitedWorkBudget
    from repo_catalog.domain.ref_observation import (
        RefObservation,
        RefObservationClaim,
        RefObservationKey,
        new_uuid7,
    )
    from repo_catalog.domain.shared_values import OID, CoreFailure, Provenance

    installed = Path(sysconfig.get_path("purelib")).resolve()
    expected_names = {"repo-catalog-core", "repo-catalog-contracts"}
    distributions = {
        d.metadata["Name"]: d
        for d in importlib.metadata.distributions()
        if d.metadata["Name"].startswith("repo-catalog")
    }
    assert set(distributions) == expected_names, set(distributions)
    assert importlib.util.find_spec("httpx") is None
    owners = {}
    for name, distribution in distributions.items():
        for member in distribution.files:
            if str(member).startswith("repo_catalog/"):
                assert str(member) not in owners, (
                    member,
                    owners.get(str(member)),
                    name,
                )
                owners[str(member)] = name
    assert owners
    absent = (
        "adapters.sqlite.p1_context",
        "adapters.sqlite.production_context",
        "adapters.sqlite.access_schema",
        "adapters.sqlite.acquisition",
        "adapters.sqlite.p1_coordination",
        "adapters.sqlite.search",
        "adapters.sqlite.schema",
        "application.production_query",
        "application.ref_observations",
        "application.acquisition",
        "application.exchange",
        "domain.production_query",
        "domain.ports.production_query",
        "cli.query_features",
        "cli.main",
    )
    for suffix in absent:
        assert importlib.util.find_spec("repo_catalog." + suffix) is None, suffix
    origins = {}
    for suffix in (
        "adapters.sqlite.p1_schema",
        "adapters.sqlite.git_core",
        "adapters.sqlite.core_coordination",
        "application.core_query",
        "domain.shared_values",
        "domain.query_contracts",
        "domain.core_query",
        "domain.ports.core_query",
        "cli.production_query",
    ):
        module = importlib.import_module("repo_catalog." + suffix)
        origin = Path(module.__file__).resolve()
        assert origin.is_relative_to(installed), origin
        origins[suffix] = str(origin)
    assert not hasattr(
        importlib.import_module("repo_catalog.domain.core_query"), "SearchQuery"
    )
    assert not hasattr(
        importlib.import_module("repo_catalog.domain.ports.core_query"), "SearchPort"
    )
    assert not hasattr(CoreQueryService, "search")
    assert not hasattr(CoreQueryService, "rebuild_search")

    repo, instance = str(uuid4()), str(uuid4())
    catalog = Path("catalog")
    catalog.mkdir()
    path = catalog / "core.sqlite3"
    schema.initialize(path, "core", repo, instance)
    assert list(catalog.glob("*.sqlite3")) == [path]
    schema.verify_declared("core")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    refuses(lambda: schema.initialize(path, "core", repo, instance), FileExistsError)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before

    tree_body = b""
    tree_oid = OID("sha1", native_object_oid("sha1", "tree", tree_body))
    body = (
        f"tree {tree_oid.object_oid}\n"
        "author Fixture <fixture@example.invalid> 1700000000 +0000\n"
        "committer Fixture <fixture@example.invalid> 1700000000 +0000\n\n"
        "minimal installed Core\n"
    ).encode()
    commit_oid = OID("sha1", native_object_oid("sha1", "commit", body))
    native = NativeObject(
        commit_oid, "commit", body, len(body), hashlib.sha256(body).hexdigest()
    )
    tree = NativeObject(
        tree_oid, "tree", tree_body, 0, hashlib.sha256(tree_body).hexdigest()
    )
    provenance = Provenance("fixture", "read-1", "repository", "fixture", "1")
    key = RefObservationKey(str(uuid4()), new_uuid7())
    subject = RefObservation(key, repo, b"refs/heads/main", "fixture", "visible")
    claim = RefObservationClaim(key, provenance, "present", "direct", commit_oid)
    with closing(GitCore(path)) as core:
        core.admit_repository_claim(
            RepositoryClaim(repo, "name", "fixture", provenance)
        )
        core.admit_metadata(tree, str(uuid4()), UnlimitedWorkBudget())
        core.admit_metadata(native, str(uuid4()), UnlimitedWorkBudget())
        core.admit_ref_observation(subject)
        core.admit_ref_observation_claim(claim)
        count = len(core.sql("SELECT * FROM git_objects"))
        invalid = replace(native, body=b"tampered")
        refuses(
            lambda: core.admit_metadata(invalid, str(uuid4()), UnlimitedWorkBudget()),
            CoreFailure,
        )
        assert len(core.sql("SELECT * FROM git_objects")) == count
        refuses(
            lambda: core.sql(
                "UPDATE repositories SET repository_uuidv4=repository_uuidv4"
            ),
            sqlite3.DatabaseError,
        )
        refuses(lambda: core.sql("DELETE FROM repositories"), sqlite3.DatabaseError)
    refuses(
        lambda: RepositoryClaim(repo, "observation_us", True, provenance),
        CoreFailure,
        "TIME",
    )

    service = CoreQueryService(catalog, mode="core_only")
    assert CoreQueryService(catalog).snapshot_token().mode == "core_only"
    assert service.get_repository_view().repository_uuidv4 == repo
    assert service.get_repository_view().claims["name"][0].value == "fixture"
    view = service.get_git_object(commit_oid, include_bytes=True)
    assert view.retained_bytes.verified and view.retained_bytes.body_bytes == body
    assert service.read_metadata_bytes(commit_oid).body_bytes == body
    first = service.list_git_objects(PageRequest(limit=1))
    assert first.items and first.next_cursor and first.has_more
    second = service.list_git_objects(PageRequest(limit=1, cursor=first.next_cursor))
    assert second.items and first.items[0].object_oid != second.items[0].object_oid
    assert service.list_ref_observations().items[0].ref_observation == subject
    assert service.snapshot_token().context_sha256 is None
    token = service.snapshot_token().encode()
    refuses(lambda: service.list_git_objects(PageRequest(limit=0)), QueryError)
    assert not (catalog / "p1-recovery-stop.json").exists()

    def cli(*arguments):
        result = subprocess.run(
            [str(Path(sys.executable).parent / "repo-catalog-query"), *arguments],
            text=True,
            capture_output=True,
            check=True,
        )
        return json.loads(result.stdout)

    assert (
        cli("status", "--catalog", str(catalog), "--mode", "core_only")[
            "repository_uuidv4"
        ]
        == repo
    )
    payload = cli(
        "git-object",
        "--catalog",
        str(catalog),
        "--mode",
        "core_only",
        "--format",
        "sha1",
        "--object-oid",
        commit_oid.object_oid,
        "--include-bytes",
    )
    assert payload["object_oid"] == commit_oid.object_oid
    help_result = subprocess.run(
        [sys.executable, "-m", "repo_catalog.cli.production_query", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "search" not in help_result.stdout.lower()

    # An opaque coexisting database is deliberately unusable. Explicit Core
    # reads preserve it and make no assertion about its health or identity.
    context = catalog / "context.sqlite3"
    context.write_bytes(b"opaque Context bytes: this is intentionally not SQLite")
    digest = hashlib.sha256(context.read_bytes()).hexdigest()
    context.chmod(0)
    connect = sqlite3.connect

    def core_only_connection(database, *args, **kwargs):
        assert "context.sqlite3" not in str(database), database
        return connect(database, *args, **kwargs)

    sqlite3.connect = core_only_connection
    try:
        assert service.get_repository_view().repository_uuidv4 == repo
        assert service.snapshot_token().encode() == token
    finally:
        sqlite3.connect = connect
    assert (
        cli("status", "--catalog", str(catalog), "--mode", "core_only")[
            "context_sha256"
        ]
        is None
    )
    for mode in ("auto", "context_only", "paired"):
        refuses(
            lambda: CoreQueryService(catalog, mode=mode).snapshot_token(),
            QueryError,
            "MISSING_CAPABILITY",
        )
    context.chmod(0o600)
    assert hashlib.sha256(context.read_bytes()).hexdigest() == digest
    assert not (catalog / "operational.sqlite3").exists()
    assert not (catalog / "search.sqlite3").exists()
    missing = Path("missing")
    missing.mkdir()
    refuses(
        lambda: CoreQueryService(missing, mode="core_only").snapshot_token(),
        QueryError,
        "STORE_UNAVAILABLE",
    )
    assert not list(missing.glob("*.sqlite3"))

    marker = json.JSONDecodeError("caller JSON failure", "", 0)

    class BrokenBudget(UnlimitedWorkBudget):
        def require(self, unit, amount=1):
            raise marker

    observed = refuses(
        lambda: service.list_ref_observations(work=BrokenBudget()), json.JSONDecodeError
    )
    assert observed is marker
    assert not (catalog / "p1-recovery-stop.json").exists()
    refuses(
        lambda: service.list_ref_observations(
            work=UnlimitedWorkBudget(work_limits={"metadata_units": 0})
        ),
        CoreFailure,
        "BUDGET",
    )
    assert not (catalog / "p1-recovery-stop.json").exists()
    limited = CoreQueryService(
        catalog, mode="core_only", read_limits=SnapshotReadLimits(max_sql_vm_steps=1)
    )
    refuses(limited.snapshot_token, (QueryError, CoreFailure))
    assert not (catalog / "p1-recovery-stop.json").exists()

    # Validate packaged resources and live connection safety without weakening
    # production checks. Every modified installed resource is restored exactly.
    ddl_dir = Path(schema.__file__).parent / "p1_ddl"
    for name in ("core.sql", "coverage.sql", "fingerprints.json"):
        resource = ddl_dir / name
        raw = resource.read_bytes()
        try:
            resource.write_bytes(
                raw + b"\n-- deliberate tamper\n" if name.endswith(".sql") else b"{}"
            )
            refuses(lambda: schema.verify_declared("core"), schema.SchemaError)
            resource.unlink()
            refuses(lambda: schema.verify_declared("core"), FileNotFoundError)
        finally:
            resource.write_bytes(raw)
    with closing(schema.connect(path, "core")) as db:
        db.execute("PRAGMA foreign_keys=OFF")
        refuses(lambda: schema.validate(db, "core"), schema.SchemaError)
    with closing(schema.connect(path, "core")) as db:
        db.create_function("p1_native", 6, lambda *args: 1)
        refuses(lambda: schema.validate(db, "core"), schema.SchemaError)
    malformed = Path("malformed")
    malformed.mkdir()
    wrong = malformed / "core.sqlite3"
    schema.initialize(wrong, "core", repo, instance)
    with sqlite3.connect(wrong) as db:
        db.execute("CREATE TABLE unexpected(value TEXT)")
    refuses(lambda: schema.connect(wrong, "core"), schema.SchemaError)
    bad_identity = malformed / "identity.sqlite3"
    schema.initialize(bad_identity, "core", repo, instance)
    mutate(bad_identity, "store_identity", "store_role='context'")
    refuses(lambda: schema.connect(bad_identity, "core"), schema.SchemaError)

    # A real retained-byte failure must persist the stop, unlike caller errors.
    mutate(path, "retained_metadata", "body=zeroblob(length(body))")
    assert service.get_git_object(commit_oid).metadata_retained
    refuses(
        lambda: service.read_metadata_bytes(commit_oid),
        CoreFailure,
        "AUTHORITATIVE_CORRUPTION",
    )
    assert (catalog / "p1-recovery-stop.json").exists()
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "from repo_catalog.application.core_query import CoreQueryService; CoreQueryService('catalog',mode='core_only').snapshot_token()",
        ],
        capture_output=True,
        text=True,
    )
    assert child.returncode != 0 and "normal catalog operation stopped" in child.stderr
    stopped_cli = subprocess.run(
        [
            str(Path(sys.executable).parent / "repo-catalog-query"),
            "status",
            "--catalog",
            str(catalog),
            "--mode",
            "core_only",
        ],
        capture_output=True,
        text=True,
    )
    assert stopped_cli.returncode != 0
    assert "RECOVERY_STOP" in stopped_cli.stderr

    inflight = Path("inflight")
    inflight.mkdir()
    schema.initialize(inflight / "core.sqlite3", "core", repo, str(uuid4()))

    def stopped_during_read():
        with CoreQueryService(inflight, mode="core_only").open_snapshot():
            persist_catalog_stop(inflight, "synthetic concurrent stop")

    refuses(stopped_during_read, CoreFailure, "RECOVERY_STOP")
    evidence = {
        "result": "passed",
        "python": sys.version,
        "executable": sys.executable,
        "sqlite": sqlite3.sqlite_version,
        "sqlite_source_id": sqlite3.connect(":memory:")
        .execute("SELECT sqlite_source_id()")
        .fetchone()[0],
        "installed_distributions": sorted(distributions),
        "owned_product_files": len(owners),
        "origins": origins,
        "checks": [
            "offline_guard",
            "physical_absence",
            "unique_owners",
            "fresh_initialization",
            "typed_admission",
            "invalid_input_atomicity",
            "insert_only",
            "retained_bytes",
            "pagination",
            "api_and_cli",
            "opaque_context",
            "missing_db_no_creation",
            "caller_error_boundary",
            "finite_budgets",
            "resources",
            "connection_guards",
            "physical_schema",
            "retained_corruption_stop",
            "new_process_stop",
            "completion_stop",
        ],
    }
    Path(output).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
