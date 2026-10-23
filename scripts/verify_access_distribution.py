"""Build wheel and sdist-derived wheel; smoke each outside checkout on real SQLite.

Uses the locked environment's hatchling. No runtime-version override, no credentials,
no real catalog, no activation. Temporary virtualenvs intentionally contain only
this wheel: the isolated Access registry must not need Provider/HTTP dependencies.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE = r"""
import importlib.util, json, os, sqlite3, sys, tempfile
os.umask(0o022)
from pathlib import Path
from uuid import uuid4
from repo_catalog.adapters.sqlite.access_schema import initialize, require_runtime, fingerprint
from repo_catalog.adapters.sqlite.access_registry import AccessRegistry
from repo_catalog.domain.access_registry import AccessScope, ScopeLocatorRegistration
import repo_catalog
module_origin = Path(repo_catalog.__file__).resolve()
assert module_origin.is_relative_to(Path(sys.prefix).resolve()), module_origin
require_runtime()
assert importlib.util.find_spec("httpx") is None
s = str(uuid4())
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "access.sqlite3"
    initialize(path)
    with AccessRegistry(path, writable=True) as store:
        store.register_scope(AccessScope(s, "installed"))
        a = ScopeLocatorRegistration(s, 1, "file:///a")
        b = ScopeLocatorRegistration(s, 2, "file:///b")
        again = ScopeLocatorRegistration(s, 3, "file:///a")
        for value in (a, b, again):
            store.register_locator(value)
        assert store.first_choices(s) == (again,)
        assert store.history(s).registrations == (again, b, a)
        assert not store.locator_enabled(again)
    from repo_catalog.adapters.sqlite.access_connections import AccessConnections
    from repo_catalog.domain.access_connections import (
        ScopeExecutionContext, RepositoryBinding, ConnectionConfiguration,
        AssignmentKey, LocatorConnection, canonical,
    )
    from repo_catalog.domain.access_registry import AccessRegistryError
    from dataclasses import replace
    repo = str(uuid4())
    context = canonical({"version": 1, "executor_kind": "local", "executor_ref": "installed", "identity_view": "owner", "path_dialect": "posix"})
    options = canonical({"version": 1, "transport": "file", "path_dialect": "posix"})
    key = AssignmentKey(s, "/repos/app.git", "local")
    with AccessConnections(path, writable=True) as store:
        store.set_locator_enabled(again, True)
        store.configure_scope(ScopeExecutionContext(s, context, True))
        store.bind_repository(RepositoryBinding(s, key.locator_text, repo, True))
        profile = ConnectionConfiguration(s, "local", options, True)
        store.configure_connection(profile)
        store.assign_connection(LocatorConnection(key, True))
        plan = store.review_plan(repo, s)
        grant = store.record_local_approval(plan, 10)
        assert store.current_grant(repo, s) == grant
        disabled = replace(profile, enabled=False)
        store.configure_connection(disabled, expected=profile)
        store.configure_connection(profile, expected=disabled)
        try:
            store.current_grant(repo, s)
        except AccessRegistryError as error:
            assert error.code == "APPROVAL_REQUIRED"
        else:
            raise AssertionError("ABA grant resurrection")
    from repo_catalog.application.access_workflow import AccessWorkflow
    from repo_catalog.domain.access_workflow import AccessSelection
    from repo_catalog.adapters.filesystem.access_executor import LocalDirectoryExecutor
    import os, subprocess, sys
    root = Path(directory) / "executor"
    root.mkdir(mode=0o700)
    repository = root / "repo.git"
    repository.mkdir(mode=0o700)
    newest = ScopeLocatorRegistration(s, 30, root.as_uri())
    local_key = AssignmentKey(s, str(repository), "local")
    with AccessConnections(path, writable=True) as store:
        store.register_locator(newest)
        store.set_locator_enabled(newest, True)
        store.bind_repository(RepositoryBinding(s, str(repository), repo, True))
        store.assign_connection(LocatorConnection(local_key, True))
        selected = AccessSelection(repo, s, local_key)
        with AccessWorkflow(store) as workflow:
            workflow.approve(workflow.begin_review(selected), lambda shown: True)
            token = workflow.activate(selected, LocalDirectoryExecutor(), lambda shown: True)
            assert workflow.dispatch_once(token, lambda fd: os.fstat(fd).st_ino, guard=lambda: None) == repository.stat().st_ino
    # Installed read-only CLI needs no TTY. Mutating CLI paths are PTY-tested separately.
    output = subprocess.check_output([sys.executable, "-I", "-m", "repo_catalog.cli.access_workflow", "review", "--access-db", str(path), "--repository", repo, "--scope", s, "--locator", str(repository), "--profile", "local"], text=True)
    assert json.loads(output)["status"] == "review-only"
    assert not (Path(directory) / "core.sqlite3").exists()
    # Installed A4 acquires actual Git metadata into a non-seed Repository UUID.
    # This is fixture creation; product acquisition never writes the source repo.
    from contextlib import closing
    from repo_catalog.adapters.sqlite import p1_schema
    from repo_catalog.adapters.sqlite.git_core import GitCore
    from repo_catalog.application.access_acquisition import AccessGitAcquisition
    from repo_catalog.domain.acquisition import GitNativeAcquisitionRequest
    from repo_catalog.domain.p1_core import OID
    subprocess.run(["git", "init", "--bare", "--object-format=sha1", str(repository)], check=True, capture_output=True)
    tree = subprocess.check_output(["git", "-C", str(repository), "hash-object", "-w", "-t", "tree", "--stdin"], input=b"").strip()
    body = b"tree " + tree + b"\nauthor Test <test@example.org> 1 +0000\ncommitter Test <test@example.org> 1 +0000\n\ninstalled fixture\n"
    commit = subprocess.check_output(["git", "-C", str(repository), "hash-object", "-w", "-t", "commit", "--stdin"], input=body).decode().strip()
    catalog = Path(directory) / "domain-catalog"
    catalog.mkdir()
    seed, instance = str(uuid4()), str(uuid4())
    for role in ("core", "operational"):
        p1_schema.initialize(catalog / f"{role}.sqlite3", role, seed, instance)
    request = GitNativeAcquisitionRequest(repo, str(uuid4()), str(uuid4()), "installed-local-source", 50, select_oids=(OID("sha1", commit),), include_refs=False)
    with AccessConnections(path) as store:
        report = AccessGitAcquisition(store, catalog).acquire(selected, request, object_format="sha1", reviewer=lambda shown: True, new_request=True)
        assert report.repository_uuidv4 == repo != seed
        assert OID("sha1", commit) in report.retained_objects
    with closing(GitCore(catalog / "core.sqlite3")) as core:
        assert core.catalog_identity() == (seed, instance)
        assert core.read_metadata(OID("sha1", commit)) == body
    subprocess.run([sys.executable, "-I", "-m", "repo_catalog.cli.access_acquisition", "--help"], check=True, capture_output=True)
    # Installed A5 preserves all Scope history and removes transferable consent.
    from repo_catalog.adapters.sqlite.access_backup import AccessBackup
    from repo_catalog.application.access_maintenance import AccessMaintenance
    service = AccessBackup()
    bundle = Path(directory) / "access-backup"
    restored = Path(directory) / "access-restored"
    manifest = service.backup(path, bundle)
    assert manifest["row_counts"]["scope_locators"] == 4
    assert manifest["row_counts"]["local_access_grants"] == 0
    assert service.inspect(bundle) == manifest
    service.restore(bundle, restored)
    with AccessConnections(restored / "access.sqlite3", writable=True) as copy:
        assert copy.first_choices(s) == (newest,)
        assert len(copy.history(s).registrations) == 4
        assert not copy.locator_enabled(newest)
        copy.set_locator_enabled(newest, True)
        try:
            copy.current_grant(repo, s, assignment=local_key)
        except AccessRegistryError as error:
            assert error.code == "APPROVAL_REQUIRED"
        else:
            raise AssertionError("restored approval survived")
    fork = AccessMaintenance(service, clock_us=lambda: 100).fork_scope(restored / "access.sqlite3", s, "file:///new-scope")
    with AccessConnections(restored / "access.sqlite3") as copy:
        assert len(copy.history(s).registrations) == 4
        new_scope = fork["target_scope_uuidv4"]
        assert new_scope != s
        assert copy.history(new_scope).registrations == (ScopeLocatorRegistration(new_scope, 100, "file:///new-scope"),)
        assert not copy.scope_context(new_scope).enabled
    subprocess.run([sys.executable, "-I", "-m", "repo_catalog.cli.access_maintenance", "inspect", "--bundle", str(bundle)], check=True, capture_output=True)
# Installed A3 policy, SQLite constraints and typed Exchange round-trip.
from contextlib import closing
from repo_catalog.domain.context_registration import registration_json, RegistrationError
from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.exchange import FORMAT as EXCHANGE_FORMAT, ExchangeSelectionScope
from repo_catalog.domain.p1_core import RepositoryClaim, Provenance
from repo_catalog.domain.context_admission import DependencySet
# This exact external file is test harness code. Product modules still resolve
# solely from the installed wheel, including under Python's isolated mode.
authority_spec = importlib.util.spec_from_file_location("installed_fixture_authority", os.environ["REPO_CATALOG_SMOKE_AUTHORITY"])
authority = importlib.util.module_from_spec(authority_spec)
authority_spec.loader.exec_module(authority)
for role in ("provider", "repository", "source", "membership"):
    assert registration_json(role, "{}") == {}
    try:
        registration_json(role, '{"credential_ref":"not-domain-data"}')
    except RegistrationError:
        pass
    else:
        raise AssertionError("installed registration input leak")
with tempfile.TemporaryDirectory() as directory:
    base = Path(directory)
    producer, receiver = base / "producer", base / "receiver"
    producer.mkdir(); receiver.mkdir()
    repository_id, service = str(uuid4()), str(uuid4())
    for destination in (producer, receiver):
        instance = str(uuid4())
        for role in ("core", "context", "operational"):
            p1_schema.initialize(destination / f"{role}.sqlite3", role, repository_id, instance)
    admission_service, _ = authority.fixture_service(DependencySet(
        provider_registrations=frozenset({service}), repositories=frozenset({repository_id})))
    admission = authority.fixture_context(admission_service)
    with Context.transaction(producer, authorization=admission_service) as ctx:
        ctx.provider(service, "github", '{"name":"Original provider"}', admission=admission)
        ctx.repository(repository_id, '{"name":"app"}', admission=admission)
        try:
            ctx.db.execute("UPDATE providers SET configuration_json=?", ('{"token":"DO-NOT-STORE"}',))
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("installed SQL boundary leak")
    historical_url = "https://historical.example/repository.git"
    evidence = Provenance("source", "observation", "coordinate", "decoder", "1")
    with closing(GitCore(producer / "core.sqlite3")) as core:
        core.admit_repository_claim(RepositoryClaim(repository_id, "endpoint", historical_url, evidence))
    package = ExchangeService(producer).export_package(selection=ExchangeSelectionScope(all_selected=True))
    assert package.format == EXCHANGE_FORMAT == "git-repo-db/adr0030-exchange-v4"
    ExchangeService(receiver).import_package(package, new_request=True, permitted_repository_uuidv4s=(repository_id,))
    with closing(GitCore(receiver / "core.sqlite3")) as core:
        rows = core.sql("SELECT value FROM repository_claims WHERE field='endpoint'")
        assert json.loads(rows[0][0]) == historical_url
    with Context.snapshot(receiver) as ctx:
        assert ctx.db.execute("SELECT configuration_json FROM providers").fetchone()[0] == '{"name":"Original provider"}'
        tables = [r[0] for r in ctx.db.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
        assert len(tables) == 19, f"Expected 19 tables in Context, got {len(tables)}: {tables}"
        assert "resource_repository_relations" in tables
        assert "repository_mapping_dispositions" in tables
        # Verify UDF registration
        assert ctx.db.execute("SELECT p1_mapping_target('\"9ebbe38a-f937-40e6-a99c-701835ebcf10\"')").fetchone()[0] == 1
        assert ctx.db.execute("SELECT p1_mapping_clock('{\"at_us\":1,\"domain\":\"test\"}')").fetchone()[0] == 1
        assert ctx.db.execute("SELECT p1_mapping_provenance('{\"evidence\":\"e\",\"source\":\"s\"}')").fetchone()[0] == 1
    assert not (receiver / "access.sqlite3").exists()
from repo_catalog.application.acquisition import ProviderAcquisition
from repo_catalog.adapters.github.production_intake import github_repository_id
from repo_catalog.domain.acquisition import ProviderIntakeBatch, ProviderRegistration, RepositoryRegistration, ProviderIssueIntake, ProviderTimelineIntake, make_provenance
from repo_catalog.domain.p1_context import ResourceKey, ResourceRepositoryRelation, FieldClock, canonical
with tempfile.TemporaryDirectory() as directory:
    destination = Path(directory)
    repository_id, instance, service = str(uuid4()), str(uuid4()), str(uuid4())
    for role in ("core", "context"):
        p1_schema.initialize(destination / f"{role}.sqlite3", role, repository_id, instance)
    node = {"id": "R_installed", "databaseId": 1}
    node_identifier = github_repository_id(node, graphql=True)
    # Change the key representation while retaining the original evidence text.
    claims = tuple(ResourceRepositoryRelation(ResourceKey(service, "repository", identifier), "represents_repository", FieldClock("installed:mapping", 1), canonical(repository_id), make_provenance("installed", {"explicit_mapping": evidence_identifier}), 1)
                   for identifier, evidence_identifier in ((github_repository_id({"id": 1}, graphql=False), "1"), (node_identifier, node_identifier)))
    ProviderAcquisition(destination).admit_batch(ProviderIntakeBatch(service,
        providers=(ProviderRegistration(service),), repositories=(RepositoryRegistration(repository_id),), mapping_claims=claims,
        issues=(ProviderIssueIntake({"id": 7, "repository": {"id": 1}}, 10, make_provenance("installed", "issue")),),
        timeline_events=(ProviderTimelineIntake("issue", 7, "EV_installed", {"id": "EV_installed", "__typename": "TransferredEvent", "issue": {"databaseId": 7}, "fromRepository": node}, 20, make_provenance("installed", "event"), graphql=True),)))
    with Context.snapshot(destination) as ctx:
        qualified, = ctx.provider_repository_roles(ResourceKey.from_native(service, "issue", "7"))
        assert qualified.supports[0].supporting_claims == (claims[0].claim_key,)
        report, = ctx.transfer_event_reports()
        assert report.from_relation.embedded_support.supporting_claims == (claims[1].claim_key,)
        assert report.to_state == "absent" and report.observed_at_us == 20
    assert not (destination / "access.sqlite3").exists()
    # Installed I2 -> I3, including original Node namespace and a different seed.
    target = destination / "receiver"
    target.mkdir()
    target_seed, target_instance = str(uuid4()), str(uuid4())
    for role in ("core", "context", "operational"):
        p1_schema.initialize(target / f"{role}.sqlite3", role, target_seed, target_instance)
    package = ExchangeService(destination).export_package(selection=ExchangeSelectionScope(
        repository_uuidv4s=(repository_id,), object_oids=(),
        resource_keys=(qualified.resource, report.event_resource), source_uuidv4s=()))
    ExchangeService(target).import_package(package, new_request=True, permitted_repository_uuidv4s=(repository_id,))
    with Context.snapshot(target) as ctx:
        assert ctx.provider_repository_roles(qualified.resource) == (qualified,)
        assert ctx.transfer_event_reports() == (report,)
    with closing(GitCore(target / "core.sqlite3")) as core:
        assert core.catalog_identity() == (target_seed, target_instance)
        assert {r[0] for r in core.sql("SELECT repository_uuidv4 FROM repositories")} == {target_seed, repository_id}
    assert not (target / "access.sqlite3").exists()
    # Installed I4: Query/Search and fresh paired restore consume the I2/I3 facts.
    from repo_catalog.application.production_query import ProductionQueryService
    from repo_catalog.application.recovery import RecoveryService
    from repo_catalog.domain.production_query import SearchQuery
    from repo_catalog.domain.p1_context import MappingDisposition, MappingOperationEvidence
    disposition = MappingDisposition(claims[0].claim_key, "withdraw", FieldClock("installed:operation", 30), make_provenance("installed", "withdraw"), 30)
    with Context.transaction(target) as ctx:
        ctx.admit_mapping_disposition(disposition)
    q = ProductionQueryService(target)
    assert q.get_context_resource(qualified.resource).repository_roles[0].state == "contested_candidate"
    checked = ProductionQueryService(target, mapping_evidence=MappingOperationEvidence(frozenset({disposition.disposition_key})))
    assert checked.get_context_resource(qualified.resource).repository_roles[0].state == "withdrawn"
    q.rebuild_search(("context_text",))
    found = q.search(SearchQuery("owning_repository", projection_kinds=("context_text",)))
    assert found.backend == "verified_projection_scan" and found.hits
    backup, restored = destination / "paired-backup", destination / "paired-restored"
    recovery = RecoveryService()
    recovery.create_consistent_backup(target, backup)
    recovery.restore_backup(backup, restored, target_seed)
    with Context.snapshot(restored) as ctx:
        assert ctx.mapping_dispositions(claims[0].claim_key) == (disposition,)
        assert ctx.transfer_event_reports() == (report,)
    rq = ProductionQueryService(restored)
    assert rq.get_context_resource(qualified.resource) == q.get_context_resource(qualified.resource)
    assert rq.search(SearchQuery("owning_repository", projection_kinds=("context_text",))).backend == "authority_scan"
    rq.rebuild_search(("context_text",))
    assert rq.search(SearchQuery("owning_repository", projection_kinds=("context_text",))).backend == "verified_projection_scan"
    assert not any((restored / f"{role}.sqlite3").exists() for role in ("operational", "access"))
print(json.dumps({"sqlite": sqlite3.sqlite_version, "sqlite_source_id": sqlite3.connect(":memory:").execute("SELECT sqlite_source_id()").fetchone()[0], "module_origin": str(module_origin), "interpreter": sys.executable, "ddl_sha256": fingerprint(), "context_ddl_sha256": p1_schema.fingerprint("context"), "table_count": len(tables), "exchange_format": EXCHANGE_FORMAT, "local_git_acquired": True, "access_backup_restored": True, "scope_forked": True, "installed_i2_i3_cross_seed": "passed", "installed_i4_query_search_backup": "passed", "installed_smoke": "passed"}))
"""


def run(*args: str, cwd: Path, env: dict[str, str]) -> str:
    try:
        result = subprocess.run(
            args, cwd=cwd, env=env, check=True, text=True, capture_output=True
        )
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result.stdout
    except subprocess.CalledProcessError as error:
        print("STDERR:", error.stderr, file=sys.stderr)
        print("STDOUT:", error.stdout, file=sys.stderr)
        print("COMMAND FAILED:", args[0] if args else "empty", file=sys.stderr)
        raise


def main() -> None:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    results = []
    with tempfile.TemporaryDirectory(prefix="access-distribution-") as temporary:
        base = Path(temporary)
        authority = base / "fixture_authority.py"
        shutil.copyfile(ROOT / "tests/support/context_admission.py", authority)
        env["REPO_CATALOG_SMOKE_AUTHORITY"] = str(authority)
        built = base / "built"
        built.mkdir()
        print(
            run(
                sys.executable,
                "-m",
                "hatchling",
                "build",
                "-t",
                "wheel",
                "-t",
                "sdist",
                "-d",
                str(built),
                cwd=ROOT,
                env=env,
            )
        )
        direct = next(built.glob("*.whl"))
        archive = next(built.glob("*.tar.gz"))
        unpacked = base / "sdist"
        unpacked.mkdir()
        with tarfile.open(archive) as source:
            source.extractall(unpacked, filter="data")
        source_root = next(unpacked.iterdir())
        rebuilt = base / "rebuilt"
        rebuilt.mkdir()
        print(
            run(
                sys.executable,
                "-m",
                "hatchling",
                "build",
                "-t",
                "wheel",
                "-d",
                str(rebuilt),
                cwd=source_root,
                env=env,
            )
        )
        for label, wheel in (
            ("wheel", direct),
            ("sdist-wheel", next(rebuilt.glob("*.whl"))),
        ):
            target = base / label
            venv.EnvBuilder(with_pip=False).create(target)
            python = target / "bin/python"
            # Pure Python wheel only; verify all archive members before extracting.
            with zipfile.ZipFile(wheel) as package:
                assert any(
                    name.endswith("access_ddl/registry.sql")
                    for name in package.namelist()
                )
                for name in package.namelist():
                    parts = Path(name).parts
                    if Path(name).is_absolute() or ".." in parts:
                        raise ValueError("unsafe wheel member")
            print(
                run(
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    "--no-deps",
                    str(wheel),
                    cwd=base,
                    env=env,
                )
            )
            # Retain the actual installed runtime even when the domain smoke
            # fails, and exercise both artifacts before returning a failure.
            if reference := os.environ.get("CI_RUNTIME_REFERENCE"):
                run(
                    str(python),
                    "-I",
                    str(ROOT / "scripts/ci_python_runtime.py"),
                    "probe",
                    str(ROOT / "artifacts/runtime" / (label + ".json")),
                    "--reference",
                    str(Path(reference).resolve()),
                    cwd=base,
                    env=env,
                )
            runtime = json.loads(
                run(
                    str(python),
                    "-I",
                    "-c",
                    "import json, sqlite3, sys, repo_catalog; "
                    "from repo_catalog.adapters.sqlite import p1_schema; "
                    "from repo_catalog.adapters.sqlite.access_schema import fingerprint; "
                    "print(json.dumps(dict(interpreter=sys.executable, "
                    "sqlite=sqlite3.sqlite_version, "
                    "sqlite_source_id=sqlite3.connect(':memory:').execute("
                    "'SELECT sqlite_source_id()').fetchone()[0], "
                    "module_origin=repo_catalog.__file__, "
                    "context_ddl_sha256=p1_schema.fingerprint('context'), "
                    "ddl_sha256=fingerprint())))",
                    cwd=base,
                    env=env,
                )
            )
            try:
                output = run(str(python), "-I", "-c", SMOKE, cwd=base, env=env)
            except subprocess.CalledProcessError as error:
                result = {
                    **runtime,
                    "installed_smoke": "failed",
                    "exit_code": error.returncode,
                    "stdout": error.stdout,
                    "stderr": error.stderr,
                }
            else:
                result = json.loads(output)
                result["exit_code"] = 0
            result["artifact_kind"] = label
            result["wheel_sha256"] = hashlib.sha256(wheel.read_bytes()).hexdigest()
            result["source_sdist_sha256"] = hashlib.sha256(
                archive.read_bytes()
            ).hexdigest()
            results.append(result)
            print(label, json.dumps(result))
        assert len(results) == 2
        if all(result["exit_code"] == 0 for result in results):
            assert results[0]["context_ddl_sha256"] == results[1]["context_ddl_sha256"]
            assert results[0]["table_count"] == 19
            assert results[1]["table_count"] == 19
    evidence = ROOT / "artifacts/access-registry"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "distribution.json").write_text(json.dumps(results, indent=2) + "\n")
    if any(result["exit_code"] != 0 for result in results):
        raise SystemExit("Installed Access smoke failed; see distribution.json")


if __name__ == "__main__":
    main()
