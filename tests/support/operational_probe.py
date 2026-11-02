"""Stdlib-only consumer for the three-product durable Operational minimum."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
import runpy
import sqlite3
import subprocess
import sys
import sysconfig
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4


def refuses(call, codes):
    try:
        call()
    except Exception as error:
        assert getattr(error, "code", None) in codes, (type(error), str(error), codes)
        return error
    raise AssertionError("operation unexpectedly succeeded")


def main(output):
    root = Path(__file__).resolve().parent
    runpy.run_path(str(root / "sitecustomize.py"))
    os.environ["PYTHONPATH"] = str(root)
    from repo_catalog.adapters.sqlite import p1_schema as schema
    from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
    from repo_catalog.domain.p1_coordination import RequestIdentity
    from repo_catalog.domain.request_scope import request_scope

    installed = Path(sysconfig.get_path("purelib")).resolve()
    distributions = {
        d.metadata["Name"]: d
        for d in importlib.metadata.distributions()
        if d.metadata["Name"].startswith("repo-catalog")
    }
    assert set(distributions) == {
        "repo-catalog-operational",
        "repo-catalog-runtime",
        "repo-catalog-contracts",
    }
    owners = {}
    for name, distribution in distributions.items():
        for member in distribution.files:
            if str(member).startswith("repo_catalog/"):
                assert str(member) not in owners, member
                owners[str(member)] = name
    for module in (
        "domain.p1_core",
        "domain.p1_context",
        "domain.acquisition",
        "domain.search_query",
        "adapters.sqlite.git_core",
        "adapters.sqlite.production_context",
        "adapters.sqlite.p1_coordination",
        "adapters.sqlite.access_schema",
        "application.acquisition",
        "application.exchange",
        "application.recovery",
    ):
        assert importlib.util.find_spec("repo_catalog." + module) is None, module
    assert importlib.util.find_spec("httpx") is None
    assert "repo_catalog/adapters/sqlite/p1_ddl/operational.sql" in owners
    for role in ("core", "context", "search"):
        assert "repo_catalog/adapters/sqlite/p1_ddl/" + role + ".sql" not in owners
    checks = ["three_owner_closure_no_authority_or_high_level_code"]
    path = root / "operational.sqlite3"
    try:
        OperationalAcquisitionLedger(path)
    except schema.SchemaError:
        pass
    else:
        raise AssertionError("missing Operational accepted")
    assert not path.exists()
    repository, instance = str(uuid4()), str(uuid4())
    schema.initialize(path, "operational", repository, instance)
    assert not any(
        (root / (role + ".sqlite3")).exists()
        for role in ("core", "context", "access", "search")
    )
    checks.append("explicit_only_initialization_no_optional_databases")

    request = RequestIdentity(str(uuid4()), str(uuid4()))
    scope = request_scope(
        repository, instance, "synthetic-local", '["local-git","synthetic"]'
    )
    with OperationalAcquisitionLedger(path) as ledger:
        _, attempt, work, progress = ledger.create_budget(
            scope=scope,
            request=request,
            new_request=True,
            work_limits={"input_bytes": 1024 * 1024},
        )
        work.require("input_bytes", 8)
        work.charge("input_bytes", 4)
        assert ledger.work_ledger.usage(request)["input_bytes"] == 4
        refuses(
            lambda: ledger.create_budget(scope='["changed-intent"]', request=request),
            {"REQUEST_SCOPE"},
        )
        # The same explicit scope pins one progress value rather than replacing it.
        assert progress.save_once(scope, {"pinned": "original"}) == {
            "pinned": "original"
        }
        assert progress.save_once(scope, {"pinned": "new"}) == {"pinned": "original"}
    with OperationalAcquisitionLedger(path) as ledger:
        _, _, resumed, progress = ledger.create_budget(scope=scope, request=request)
        assert ledger.work_ledger.usage(request)["input_bytes"] >= 4
        assert progress.load(scope) == {"pinned": "original"}
        refuses(lambda: resumed.require("input_bytes", 2 * 1024 * 1024), {"BUDGET"})
    checks.append("frozen_intent_progress_reopen_and_cumulative_budget")

    # Existing source accounting test kills a blocked reader. Repeat one real
    # installed abrupt process exit after durable reservation, before settlement.
    with OperationalAcquisitionLedger(path) as ledger:
        crash_attempt = str(uuid4())
        ledger.work_ledger.attempt(request, crash_attempt)
        before = ledger.work_ledger.usage(request)["proof_steps"]
    program = """
import os,sys
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.adapters.sqlite.operational_coordination import WorkLedger,NotesWorkBudget
from repo_catalog.domain.p1_coordination import NotesLimits,RequestIdentity
db=connect(sys.argv[1],'operational')
work=NotesWorkBudget(WorkLedger(db),RequestIdentity(*sys.argv[2:4]),sys.argv[4],NotesLimits())
work.require('proof_steps',7)
os._exit(23)
"""
    child = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            program,
            str(path),
            *request.values(),
            crash_attempt,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert child.returncode == 23, child.stderr
    with OperationalAcquisitionLedger(path) as ledger:
        assert ledger.work_ledger.usage(request)["proof_steps"] == before + 7
        ledger.work_ledger.validate_continuation(request, crash_attempt)
    checks.append("process_crash_keeps_unsettled_reservation")

    # Partial accounting loss refuses old continuation rather than known zero.
    with closing(schema.connect(path, "operational")) as db:
        db.execute("DELETE FROM work_accounting WHERE work_kind='proof_steps'")
    with OperationalAcquisitionLedger(path) as ledger:
        refuses(
            lambda: ledger.create_budget(scope=scope, request=request),
            {"CONTINUATION_UNAVAILABLE"},
        )
    assert not (root / "p1-recovery-stop.json").exists()
    checks.append("partial_loss_refuses_without_authority_stop")

    # Whole-file loss/replacement cannot recreate the witnessed old request,
    # even when the caller labels it new; a genuinely new request remains possible.
    path.unlink()
    schema.initialize(path, "operational", repository, instance)
    with OperationalAcquisitionLedger(path) as ledger:
        refuses(
            lambda: ledger.create_budget(scope=scope, request=request),
            {"CONTINUATION_UNAVAILABLE"},
        )
        refuses(
            lambda: ledger.create_budget(
                scope=scope, request=request, new_request=True
            ),
            {"CONTINUATION_UNAVAILABLE"},
        )
        ledger.create_budget(scope=scope, new_request=True)
    checks.append("whole_store_loss_no_old_request_reset")

    # Existing connection must notice file identity replacement.
    with OperationalAcquisitionLedger(path) as ledger:
        moved = root / "moved.sqlite3"
        path.rename(moved)
        schema.initialize(path, "operational", repository, instance)
        refuses(
            lambda: ledger.create_budget(scope=scope, new_request=True),
            {"CONTINUATION_UNAVAILABLE"},
        )
    checks.append("live_handle_replacement_fails_closed")

    real_connect = schema.sqlite3.connect

    def vanished(database, *args, **kwargs):
        path.unlink()
        return real_connect(database, *args, **kwargs)

    with patch.object(schema.sqlite3, "connect", vanished):
        try:
            OperationalAcquisitionLedger(path)
        except sqlite3.OperationalError:
            pass
        else:
            raise AssertionError("vanished Operational reopened")
    assert not path.exists()
    checks.append("existence_open_race_never_creates_database")

    # File ownership and every loaded origin are bound to this consumer install.
    origins = {}
    for name, module in tuple(sys.modules.items()):
        if name == "repo_catalog" or name.startswith("repo_catalog."):
            for location in getattr(module, "__path__", ()):
                assert Path(location).resolve().is_relative_to(installed), name
            filename = getattr(module, "__file__", None)
            if filename:
                origin = Path(filename).resolve()
                assert origin.is_relative_to(installed), (name, origin)
                relative = origin.relative_to(installed).as_posix()
                assert relative in owners, relative
                origins[name] = {"path": str(origin), "owner": owners[relative]}
    Path(output).write_text(
        json.dumps(
            {
                "result": "passed",
                "checks": checks,
                "installed_distributions": sorted(distributions),
                "origins": origins,
                "python": sys.version,
                "sqlite": sqlite3.sqlite_version,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main(sys.argv[1])
