"""Read-only review probe; only disposable in-memory databases are mutated."""

import json
import sqlite3
import sys

from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.p1_context import canonical as J
from repo_catalog.domain.resource_identification import ResourceIdentification as RI
from repo_catalog.domain.resource_stage import has_transfer_fence

S = "22222222-2222-4222-8222-222222222222"
F = ("i2_transfer_stage_fence", "i2_transfer_report_stage_fence")


def fresh():
    db = sqlite3.connect(":memory:", isolation_level=None)
    p1_schema.register_functions(db)
    p1_schema.configure(db)
    db.executescript(p1_schema.compose("context"))
    assert p1_schema.schema_rows(db) == p1_schema.expected_schema("context")
    return db


fence = []
for state, drops, alter in [
    ("normal", (), False),
    ("endpoint_missing", F[:1], False),
    ("report_missing", F[1:], False),
    ("both_missing", F, False),
    ("endpoint_changed", F[:1], True),
]:
    db = fresh()
    for name in drops:
        db.execute("DROP TRIGGER " + name)
    if alter:
        db.execute(
            "CREATE TRIGGER i2_transfer_stage_fence BEFORE INSERT ON resource_repository_relations BEGIN SELECT 1; END"
        )
    fence.append(
        {
            "state": state,
            "legacy_has_transfer_fence": has_transfer_fence(db),
            "exact_schema_match": p1_schema.schema_rows(db)
            == p1_schema.expected_schema("context"),
        }
    )
    db.close()
assert [r["legacy_has_transfer_fence"] for r in fence] == [
    True,
    False,
    True,
    False,
    True,
]
assert [r["exact_schema_match"] for r in fence] == [True, False, False, False, False]

db = fresh()
for name in F:
    db.execute("DROP TRIGGER " + name)
db.execute("INSERT INTO providers VALUES(?,?,?)", (S, "synthetic", "{}"))
i7 = ResourceKey.from_native(S, "issue", "I7-probe")
event = ResourceKey.document(i7, "comment", "timeline_event", "E-probe")
for key, ident in [
    (i7, RI.unscoped(i7)),
    (event, RI.scoped(event, i7, "timeline_event", "E-probe")),
]:
    db.execute(
        "INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id) VALUES(?,?,?,?,?,?,?)",
        (*key.coordinates(), *ident.columns),
    )
pclock = {"domain": "parent-probe", "at_us": 50}
eclock = {"domain": "event-probe", "at_us": 100}
parent_members = J([i7.coordinates()])
parent_provenance = J({"source": "original-parent", "evidence": "probe"})
parent_scope = J(
    {"clock": pclock, "document_kind": "timeline_event", "state": "complete"}
)
provenance = J({"source": "original-event", "evidence": "probe"})
scope = J(
    {
        "clock": eclock,
        "event_type": "transferred",
        "parent_members_json": parent_members,
        "parent_provenance_json": parent_provenance,
        "parent_scope_json": parent_scope,
        "provided_roles": ["transfer_from_repository"],
        "from_provider_repository_id": None,
        "to_provider_repository_id": None,
        "endpoints": [["transfer_from_repository", "null"]],
    }
)
rel_cols = "service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,members_json,provenance_json,scope_json,observed_at_us"
ep_cols = "service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,target_json,clock_json,provenance_json,observed_at_us,event_report_members_json,event_report_scope_json"
trace = []
db.set_trace_callback(trace.append)
db.execute("BEGIN")
db.execute("PRAGMA defer_foreign_keys=ON")
db.execute(
    "INSERT INTO resource_relations(" + rel_cols + ") VALUES(?,?,?,?,?,?,?,?)",
    (*event.coordinates(), "transfer_event_report", "[]", provenance, scope, 101),
)
db.execute(
    "INSERT INTO resource_repository_relations("
    + ep_cols
    + ") VALUES(?,?,?,?,?,?,?,?,?,?)",
    (
        *event.coordinates(),
        "transfer_from_repository",
        "null",
        J(eclock),
        provenance,
        101,
        "[]",
        scope,
    ),
)


def counts():
    return [
        db.execute(
            "SELECT COUNT(*) FROM resource_relations WHERE relation_kind='transfer_event_report'"
        ).fetchone()[0],
        db.execute(
            "SELECT COUNT(*) FROM resource_repository_relations WHERE relation_kind='transfer_from_repository'"
        ).fetchone()[0],
    ]


assert counts() == [1, 1]
try:
    db.execute("COMMIT")
except sqlite3.IntegrityError as error:
    failure = {
        "error": str(error),
        "sqlite_errorname": error.sqlite_errorname,
        "pending_after_failure": db.in_transaction,
        "rows_after_failure": counts(),
    }
else:
    raise AssertionError("missing original Parent must fail deferred COMMIT")
assert failure["pending_after_failure"] and failure["rows_after_failure"] == [1, 1]
db.execute("ROLLBACK")
assert counts() == [0, 0] and not db.in_transaction
result = {
    "python": sys.version,
    "executable": sys.executable,
    "sqlite": db.execute("SELECT sqlite_version(),sqlite_source_id()").fetchone(),
    "fence_state_probe": fence,
    "deferred_commit": failure
    | {
        "rows_after_rollback": counts(),
        "transaction_after_rollback": db.in_transaction,
    },
    "trace": trace,
    "scope": "disposable raw SQL diagnostic; no normal product Transfer acceptance or I6 implementation execution",
}
print(json.dumps(result, ensure_ascii=False, indent=2))
