"""Author smoke for an isolated installed wheel, invoked outside the checkout.

The driver is copied outside before execution. Import origins, schema bytes,
functions and runtime facts are receipts; this is not independent acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path

from repo_catalog.adapters.sqlite import p1_context, p1_schema
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.adapters.sqlite.recovery_validation import (
    validate_stored_context_relations,
)
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain import (
    resource_identification,
    resource_identity,
    resource_stage,
)
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.production_context import ResourceObservation
from repo_catalog.domain.resource_identification import ResourceIdentification as RI

REPO = "33333333-3333-4333-8333-333333333333"
INSTANCE = "44444444-4444-4444-8444-444444444444"
SERVICE = "22222222-2222-4222-8222-222222222222"


def verify():
    checks = []
    with tempfile.TemporaryDirectory(prefix="i2-installed-") as directory:
        path = Path(directory)
        p1_schema.verify_declared()
        for role in p1_schema.STORES:
            p1_schema.initialize(path / (role + ".sqlite3"), role, REPO, INSTANCE)
            db = p1_schema.connect(path / (role + ".sqlite3"), role)
            assert not db.execute("PRAGMA foreign_key_check").fetchall()
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            db.close()
            checks.append("initialized-" + role)
        namespace = ResourceKey.from_native(SERVICE, "pull_request", ["project", "7"])
        scoped = ResourceKey.document(namespace, "document", "body", ["D", []])
        declaration = RI.scoped(scoped, namespace, "body", ["D", []])
        globals_ = [
            ResourceKey.global_document(SERVICE, native)
            for native in ("", [], ["global", ["", []]])
        ]
        opaque = ResourceKey.from_native(SERVICE, "vendor.new-kind", [[]])
        with Context.transaction(path) as ctx:
            ctx.provider(SERVICE, "synthetic")
            ctx.observe(ResourceObservation(scoped, identification=declaration))
            for key in globals_:
                ctx.resource(key, identification=RI.global_document(key))
            ctx.resource(opaque)
            for key in (*globals_, scoped):
                try:
                    ctx.resource(ResourceKey(*key.coordinates()))
                except ValueError:
                    pass
                else:
                    raise AssertionError("bare Document accepted without a declaration")
            assert namespace not in ctx.resources()
            assert not ctx.db.execute("SELECT 1 FROM resource_relations").fetchone()
        checks.append("native-global-scoped-child-first")
        with Context.snapshot(path) as ctx:
            assert ctx.identification(ResourceKey(*scoped.coordinates())) == declaration
            for key in globals_:
                assert ctx.identification(
                    ResourceKey(*key.coordinates())
                ) == RI.global_document(key)
            try:
                ctx.transfer_event_reports()
            except resource_stage.UnsupportedResourceStage:
                pass
            else:
                raise AssertionError("explicit Transfer query accepted")
        checks.append("production-read-reopen")
        view = ProductionQueryService(path).get_context_resource(scoped)
        assert view.identification == declaration
        assert "parent" not in view.to_dict()
        checks.append("query-identification")
        for operation in (
            lambda: ExchangeService(path).export_transfer_events(),
            lambda: ProductionQueryService(path).transfer_event_reports(),
        ):
            try:
                operation()
            except resource_stage.UnsupportedResourceStage:
                pass
            else:
                raise AssertionError("unsupported Transfer consumer accepted")
        checks.append("explicit-consumer-stage-refusals")
        db = p1_schema.connect(path / "context.sqlite3", "context")
        store = p1_context.ContextStore(db)
        before = db.execute("SELECT * FROM resources ORDER BY 1,2,3").fetchall()
        try:
            store.resource(scoped, identification=RI.global_document(scoped))
        except sqlite3.IntegrityError as error:
            assert error.sqlite_errorcode == 1811
        else:
            raise AssertionError("same-key declaration rebind accepted")
        assert before == db.execute("SELECT * FROM resources ORDER BY 1,2,3").fetchall()
        checks.append("sql-preconflict-rebind")
        validate_stored_context_relations(db)
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        checks.append("stored-validation")
        runtime = {
            "sqlite_version": db.execute("SELECT sqlite_version()").fetchone()[0],
            "sqlite_source_id": db.execute("SELECT sqlite_source_id()").fetchone()[0],
            "compile_options": [
                tuple(row) for row in db.execute("PRAGMA compile_options")
            ],
            "pragmas": {
                name: [tuple(row) for row in db.execute(f"PRAGMA {name}")]
                for name in (
                    *p1_schema.REQUIRED_PRAGMAS,
                    "journal_mode",
                    "synchronous",
                    "encoding",
                )
            },
            "resource_functions": [
                tuple(row)
                for row in db.execute("PRAGMA function_list")
                if row[0].startswith("p1_resource_")
            ],
            "table_xinfo": [
                tuple(row) for row in db.execute("PRAGMA table_xinfo(resources)")
            ],
            "indexes": {
                row[1]: [
                    tuple(slot)
                    for slot in db.execute(f'PRAGMA index_xinfo("{row[1]}")')
                ]
                for row in db.execute("PRAGMA index_list(resources)").fetchall()
            },
        }
        assert len(runtime["resource_functions"]) == 2
        assert all(row[-1] & 2048 for row in runtime["resource_functions"])
        db.close()
    modules = (
        p1_schema,
        p1_context,
        resource_identification,
        resource_identity,
        resource_stage,
    )
    return {
        "author_verification": True,
        "checks": checks,
        "runtime": runtime,
        "manifest": p1_schema.expected_ddl_manifest(),
        "context_sql_sha256": hashlib.sha256(
            p1_schema.compose("context").encode()
        ).hexdigest(),
        "origins": {
            m.__name__: {
                "path": str(Path(m.__file__).resolve()),
                "sha256": hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest(),
            }
            for m in modules
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = verify()
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {
                "checks": len(receipt["checks"]),
                "sqlite": receipt["runtime"]["sqlite_version"],
            }
        )
    )
