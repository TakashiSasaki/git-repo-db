"""Author I3 probe copied outside checkout and run against each installed artifact."""

import argparse
import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path

from repo_catalog.adapters.sqlite import p1_context, p1_schema, production_context
from repo_catalog.adapters.sqlite.recovery_validation import (
    validate_stored_context_relations,
)
from repo_catalog.domain import parent_report
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.p1_context import canonical as J
from repo_catalog.domain.production_context import ContextError, ResourceRelation
from repo_catalog.domain.resource_identification import ResourceIdentification as RI

S = "22222222-2222-4222-8222-222222222222"
R = "11111111-1111-4111-8111-111111111111"
C = "33333333-3333-4333-8333-333333333333"


def verify():
    modules = (p1_schema, p1_context, production_context, parent_report)
    origins = {
        m.__name__: {
            "path": str(Path(m.__file__).resolve()),
            "sha256": hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest(),
        }
        for m in modules
    }
    assert all("site-packages" in r["path"] for r in origins.values()), origins
    p1_schema.verify_declared()
    with tempfile.TemporaryDirectory(prefix="i3-installed-") as work:
        directory = Path(work)
        p1_schema.initialize(directory / "context.sqlite3", "context", R, C)
        parent = ResourceKey.from_native(S, "project", "P7")
        other = ResourceKey.from_native(S, "project", "P8")
        child = ResourceKey.global_document(S, ["D", ["", []]])

        def report(target):
            return ResourceRelation(
                child,
                "parent",
                (target,),
                J({"source": "original", "evidence": "observation-7"}),
                J(
                    {
                        "clock": {"domain": "original", "at_us": None},
                        "document_kind": None,
                        "state": "complete",
                    }
                ),
                17,
            )

        original = report(parent)
        with production_context.Context.transaction(directory) as ctx:
            ctx.provider(S, "test")
            ctx.resource(child, identification=RI.global_document(child))
            try:
                ctx.relation(original)
            except ContextError as e:
                assert e.code == "RESOURCE_UNAVAILABLE"
            else:
                raise AssertionError("missing Parent admitted")
            assert not ctx.relations(child, "parent")
        with production_context.Context.transaction(directory) as ctx:
            ctx.resource(parent)
            ctx.resource(other)
            assert not ctx.relations(child, "parent")
            assert ctx.relation(original) == "insert"
            assert ctx.relation(original) == "duplicate"
            try:
                ctx.relation(original, permitted=lambda _: False)
            except ContextError as e:
                assert e.code == "PERMISSION_DENIED"
            else:
                raise AssertionError("replay bypassed policy")
            assert ctx.relation(report(other)) == "insert"
        with production_context.Context.snapshot(directory) as ctx:
            assert set(ctx.relations(child, "parent")) == {original, report(other)}
        db = p1_schema.connect(directory / "context.sqlite3", "context")
        validate_stored_context_relations(db)
        sql = "INSERT INTO resource_relations(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,members_json,provenance_json,scope_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)"
        before = [tuple(r) for r in db.execute("SELECT * FROM resource_relations")]
        missing = report(ResourceKey.from_native(S, "project", "missing"))
        try:
            db.execute(sql, (*missing.parent_report_key.coordinates(), 17))
        except sqlite3.IntegrityError as e:
            assert e.sqlite_errorcode == 787
        else:
            raise AssertionError("missing direct SQL Parent admitted")
        assert [
            tuple(r) for r in db.execute("SELECT * FROM resource_relations")
        ] == before
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        result = {
            "author_verification": True,
            "full_acceptance": False,
            "origins": origins,
            "sqlite": tuple(
                db.execute("SELECT sqlite_version(),sqlite_source_id()").fetchone()
            ),
            "context_fingerprint": p1_schema.fingerprint("context"),
            "function": [
                tuple(r)
                for r in db.execute("PRAGMA function_list")
                if r[0] == "p1_parent_report_v1"
            ],
            "relations": before,
            "table_xinfo": [
                tuple(r) for r in db.execute("PRAGMA table_xinfo(resource_relations)")
            ],
            "foreign_keys": [
                tuple(r)
                for r in db.execute("PRAGMA foreign_key_list(resource_relations)")
            ],
            "indexes": {
                r[1]: [tuple(s) for s in db.execute(f'PRAGMA index_xinfo("{r[1]}")')]
                for r in db.execute("PRAGMA index_list(resource_relations)").fetchall()
            },
        }
        db.close()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(verify(), indent=2) + "\n")
