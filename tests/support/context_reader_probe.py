"""Copied outside checkout: exercise the real installed API/CLI against producer state."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import os
import runpy
import shutil
import sqlite3
import subprocess
import sys
import sysconfig
from pathlib import Path
from unittest.mock import patch


def refuses(callback, codes):
    try:
        callback()
    except Exception as error:
        assert getattr(error, "code", None) in codes, (type(error), str(error))
        return error
    raise AssertionError("unexpected success")


def main(output):
    root = Path(__file__).resolve().parent
    runpy.run_path(str(root / "sitecustomize.py"))
    os.environ["PYTHONPATH"] = str(root)
    from repo_catalog.adapters.sqlite.catalog_runtime import (
        SnapshotReadLimits,
        persist_catalog_stop,
    )
    from repo_catalog.adapters.sqlite.production_context import Context
    from repo_catalog.application.context_query import ContextQueryService
    from repo_catalog.domain.p1_context import ResourceKey

    checks = []
    installed = Path(sysconfig.get_path("purelib")).resolve()
    distributions = {
        d.metadata["Name"]: d
        for d in importlib.metadata.distributions()
        if d.metadata["Name"].startswith("repo-catalog")
    }
    assert set(distributions) == {
        "repo-catalog-context",
        "repo-catalog-runtime",
        "repo-catalog-contracts",
    }
    owners = {}
    for name, distribution in distributions.items():
        for member in distribution.files:
            if str(member).startswith("repo_catalog/"):
                assert str(member) not in owners, str(member)
                owners[str(member)] = name
    for suffix in (
        "adapters.sqlite.git_core",
        "adapters.sqlite.core_schema_functions",
        "adapters.sqlite.core_coordination",
        "adapters.sqlite.p1_coordination",
        "adapters.sqlite.access_schema",
        "adapters.sqlite.production_search",
        "application.core_query",
        "application.core_recovery",
        "application.production_query",
        "application.acquisition",
        "application.exchange",
        "domain.p1_core",
        "domain.core_query",
        "domain.production_query",
        "cli.query_features",
        "cli.main",
    ):
        assert importlib.util.find_spec("repo_catalog." + suffix) is None, suffix
    assert importlib.util.find_spec("httpx") is None
    checks.append("physical_absence_unique_owners")

    data = json.loads((root / "fixture.json").read_text())
    fixture = root / "fixture"
    assert (
        hashlib.sha256((fixture / "context.sqlite3").read_bytes()).hexdigest()
        == data["context_sha256"]
    )
    key = ResourceKey(*data["resource"])
    touched = []

    def audit(event, args):
        if event == "sqlite3.connect":
            path = str(args[0])
            if path != ":memory:":
                assert Path(path).name == "context.sqlite3", path
                touched.append(path)

    sys.addaudithook(audit)

    def fresh(name):
        return Path(shutil.copytree(fixture, root / name))

    catalog = fresh("ordinary")
    service = ContextQueryService(catalog, mode="context_only")
    assert (
        json.loads(
            json.dumps(service.get_context_resource(key, include_text=True).to_dict())
        )
        == data["expected"]
    )
    assert all(
        not dep.available for dep in service.get_context_resource(key).core_dependencies
    )
    result = service.read_context_text(data["digest"])
    assert result.available and result.verified
    assert (
        result.body_bytes == data["text"].encode()
        and result.digest_sha256 == data["digest"]
    )
    assert touched
    assert sorted(p.name for p in catalog.glob("*.sqlite3")) == ["context.sqlite3"]
    assert service.snapshot_token().core_sha256 is None
    checks.append("resource_provenance_relations_unresolved_refs_exact_verified_text")

    def cli(directory, *extra):
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "repo_catalog.cli.production_query",
                "context-resource",
                "--catalog",
                str(directory),
                "--mode",
                "context_only",
                "--service",
                key.service_instance_uuidv4,
                "--kind",
                key.resource_kind,
                "--id",
                key.provider_resource_id,
                *extra,
            ],
            cwd=root,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
            timeout=30,
        )

    response = cli(catalog)
    assert response.returncode == 0, response.stderr
    assert json.loads(response.stdout) == data["expected"]
    checks.append("existing_cli_same_meaning")

    opaque = fresh("opaque")
    core = opaque / "core.sqlite3"
    core.write_bytes(b"opaque-not-a-sqlite-database")
    core.chmod(0)
    assert (
        json.loads(
            json.dumps(
                ContextQueryService(opaque, mode="context_only")
                .get_context_resource(key)
                .to_dict()
            )
        )
        == data["expected"]
    )
    assert cli(opaque).returncode == 0
    core.chmod(0o600)
    assert core.read_bytes() == b"opaque-not-a-sqlite-database"
    assert sorted(p.name for p in opaque.glob("*.sqlite3")) == [
        "context.sqlite3",
        "core.sqlite3",
    ]
    refuses(
        lambda: ContextQueryService(opaque).get_context_resource(key),
        {"MISSING_CAPABILITY"},
    )
    checks.append("opaque_coexisting_core_untouched_auto_refuses")

    for mode in ("paired", "core_only"):
        refuses(
            lambda: ContextQueryService(catalog, mode=mode).get_context_resource(key),
            {"MISSING_CAPABILITY"},
        )
    for name in (
        "get_git_object",
        "get_paired_resource",
        "search",
        "list_context_resources",
    ):
        assert not hasattr(service, name), name
    help_result = subprocess.run(
        [sys.executable, "-m", "repo_catalog.cli.production_query", "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert help_result.returncode == 0
    assert (
        "paired-resource" not in help_result.stdout
        and "git-object" not in help_result.stdout
        and "search-rebuild" not in help_result.stdout
    )
    checks.append("missing_capabilities_no_downgrade_or_false_stop")

    stopped = fresh("stopped")
    persist_catalog_stop(stopped, "synthetic prior stop")
    refuses(
        lambda: ContextQueryService(stopped).get_context_resource(key),
        {"RECOVERY_STOP", "RECOVERY_REQUIRED"},
    )
    response = cli(stopped)
    assert response.returncode == 2 and json.loads(response.stderr)["code"] in {
        "RECOVERY_STOP",
        "RECOVERY_REQUIRED",
    }
    checks.append("persistent_stop_api_cli")

    mid = fresh("mid-read")
    original = Context.read_text

    def stop_after_text(self, digest):
        result = original(self, digest)
        persist_catalog_stop(self.directory, "synthetic during-read stop")
        return result

    with patch.object(Context, "read_text", stop_after_text):
        refuses(
            lambda: ContextQueryService(mid, mode="context_only").get_context_resource(
                key
            ),
            {"RECOVERY_STOP", "RECOVERY_REQUIRED"},
        )
    checks.append("during_read_completion_fence")

    # Stop after Context's own snapshot capability has completed: the outer
    # Query completion fence must still refuse publishing its result.
    late = fresh("late-completion")
    from contextlib import contextmanager

    original_snapshot = Context.snapshot

    @contextmanager
    def stop_after_snapshot(*args, **kwargs):
        with original_snapshot(*args, **kwargs) as context:
            yield context
        persist_catalog_stop(late, "synthetic final completion stop")

    with patch.object(Context, "snapshot", stop_after_snapshot):
        refuses(
            lambda: ContextQueryService(late, mode="context_only").read_context_text(
                data["digest"]
            ),
            {"RECOVERY_STOP", "RECOVERY_REQUIRED"},
        )
    checks.append("outer_completion_fence")

    assert not service.read_context_text("0" * 64).available
    assert not (catalog / "p1-recovery-stop.json").exists()
    refuses(lambda: ContextQueryService(catalog, mode="bad"), {"INVALID_MODE"})
    absent = root / "absent"
    absent.mkdir()
    refuses(
        lambda: ContextQueryService(absent).read_context_text(data["digest"]),
        {"STORE_UNAVAILABLE"},
    )
    assert not list(absent.iterdir())
    refuses(
        lambda: ContextQueryService(
            catalog, read_limits=SnapshotReadLimits(max_total_rows=1)
        ).get_context_resource(key),
        {"QUERY_BUDGET"},
    )
    assert not (catalog / "p1-recovery-stop.json").exists()
    refuses(lambda: service.get_context_resource(object()), {"INVALID_INPUT"})
    bad_key = ResourceKey(*data["resource"])
    object.__setattr__(bad_key, "provider_resource_id", "[")
    refuses(lambda: service.get_context_resource(bad_key), {"INVALID_INPUT"})
    refuses(lambda: service.read_context_text(object()), {"INVALID_INPUT"})
    assert not (catalog / "p1-recovery-stop.json").exists()
    assert service.get_context_resource(key).resource == key
    checks.append("unavailable_input_budget_capability_not_corruption")

    for fault in ("text", "provenance"):
        damaged = fresh("damaged-" + fault)
        path = damaged / "context.sqlite3"
        with sqlite3.connect(path) as db:
            table = "text_bodies" if fault == "text" else "field_candidates"
            triggers = db.execute(
                "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name=?",
                (table,),
            ).fetchall()
            for name, _ in triggers:
                db.execute('DROP TRIGGER "' + name + '"')
            db.execute("PRAGMA ignore_check_constraints=ON")
            db.execute(
                "UPDATE text_bodies SET text_value='tampered'"
                if fault == "text"
                else "UPDATE field_candidates SET provenance_json='[]'"
            )
            for _, sql in triggers:
                db.execute(sql)
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        refuses(
            lambda: ContextQueryService(
                damaged, mode="context_only"
            ).get_context_resource(key),
            {"AUTHORITATIVE_CORRUPTION"},
        )
        assert (damaged / "p1-recovery-stop.json").is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before
        response = cli(damaged)
        assert response.returncode == 2
    checks.append("corrupt_text_and_stored_structure_stop_without_authority_write")

    origins = {}
    for name, module in list(sys.modules.items()):
        if name.startswith("repo_catalog.") and getattr(module, "__file__", None):
            path = Path(module.__file__).resolve()
            assert path.is_relative_to(installed), (name, path)
            assert path.relative_to(installed).as_posix() in owners
            origins[name] = str(path)
    checks.append("installed_runtime_closure_origins")
    assert not any(
        p.name in {"access.sqlite3", "operational.sqlite3", "search.sqlite3"}
        for p in root.rglob("*.sqlite3")
    )
    checks.append("no_implicit_optional_databases")
    output.write_text(
        json.dumps(
            {
                "result": "passed",
                "checks": checks,
                "installed_distributions": sorted(distributions),
                "owners": owners,
                "origins": origins,
                "fixture_sha256": data["context_sha256"],
                "sqlite": sqlite3.sqlite_version,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
