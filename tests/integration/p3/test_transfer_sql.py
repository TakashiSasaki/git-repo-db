"""I4 product SQL. Only isolated tests drop the two named I2 fences.

Both fresh composed SQL and the normal product connection factory are exercised.
Successful isolated inserts never establish product Transfer availability.
"""

import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest

from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import AdmissionRefused, DependencySet
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.p1_context import canonical as J
from repo_catalog.domain.resource_identification import ResourceIdentification as RI
from repo_catalog.domain.resource_stage import UnsupportedResourceStage
from tests.support.context_admission import fixture_context, fixture_service

S = "22222222-2222-4222-8222-222222222222"
R = "11111111-1111-4111-8111-111111111111"
C = "33333333-3333-4333-8333-333333333333"
P = J({"source": "parent-original", "evidence": ["capture", 7]})
E = J({"source": "event-original", "evidence": ["capture", 9]})
CLOCK = {"domain": "event-clock", "at_us": 23}
REL_COLS = "service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,members_json,provenance_json,scope_json,observed_at_us"
EP_COLS = "service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,target_json,clock_json,provenance_json,observed_at_us,event_report_members_json,event_report_scope_json"
REL = f"INSERT INTO resource_relations({REL_COLS}) VALUES(?,?,?,?,?,?,?,?)"
EP = f"INSERT INTO resource_repository_relations({EP_COLS}) VALUES(?,?,?,?,?,?,?,?,?,?)"
FENCES = ("i2_transfer_stage_fence", "i2_transfer_report_stage_fence")


def key(kind, native, service=S):
    return ResourceKey.from_native(service, kind, native)


def add_resource(db, value, identification=None):
    ri = identification or RI.unscoped(value)
    db.execute(
        "INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id) VALUES(?,?,?,?,?,?,?)",
        (*value.coordinates(), *ri.columns),
    )


def parent(event, issue, *, provenance=P, clock=11, observed=17):
    return (
        *event.coordinates(),
        "parent",
        J([issue.coordinates()]),
        provenance,
        J(
            {
                "clock": {"domain": "parent-clock", "at_us": clock},
                "document_kind": "timeline_event",
                "state": "complete",
            }
        ),
        observed,
    )


def event_row(event, support, **changes):
    scope = {
        "clock": CLOCK,
        "event_type": "transferred",
        "from_provider_repository_id": None,
        "to_provider_repository_id": None,
        "provided_roles": ["transfer_from_repository", "transfer_to_repository"],
        "endpoints": [
            ["transfer_from_repository", "null"],
            ["transfer_to_repository", "null"],
        ],
        "parent_members_json": support[4],
        "parent_provenance_json": support[5],
        "parent_scope_json": support[6],
    }
    scope.update(changes)
    return (*event.coordinates(), "transfer_event_report", "[]", E, J(scope), 29)


def endpoint(report, role="transfer_from_repository"):
    return (
        *report[:3],
        role,
        "null",
        J(json.loads(report[6])["clock"]),
        report[5],
        report[7],
        report[4],
        report[6],
    )


def rows(db):
    return {
        name: sorted(
            [tuple(row) for row in db.execute(f'SELECT * FROM "{name}"')], key=J
        )
        for (name,) in db.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


@pytest.fixture(params=["composed-sql", "product-factory"])
def normal_db(request, tmp_path):
    if request.param == "composed-sql":
        db = sqlite3.connect(":memory:", isolation_level=None)
        p1_schema.register_functions(db)
        p1_schema.configure(db)
        db.executescript(p1_schema.compose("context"))
    else:
        path = tmp_path / "context.sqlite3"
        p1_schema.initialize(path, "context", R, C)
        db = p1_schema.connect(path, "context")
    statements = []
    db.set_trace_callback(statements.append)
    db.execute("INSERT INTO providers VALUES(?,?,?)", (S, "test", "{}"))
    yield db
    target = os.environ.get("I4_SQL_TRACE")
    if target:
        out = Path(target)
        out.mkdir(parents=True, exist_ok=True)
        (
            out / (hashlib.sha256(request.node.nodeid.encode()).hexdigest() + ".json")
        ).write_text(
            J(
                {
                    "nodeid": request.node.nodeid,
                    "connection": request.param,
                    "statements": statements,
                    "final_rows": rows(db),
                    "sqlite": tuple(
                        db.execute(
                            "SELECT sqlite_version(),sqlite_source_id()"
                        ).fetchone()
                    ),
                }
            )
        )
    db.close()


@pytest.fixture
def isolated(normal_db):
    # Only mutation: two DROP TRIGGER statements, after exact schema verification.
    assert p1_schema.schema_rows(normal_db) == p1_schema.expected_schema("context")
    for fence in FENCES:
        normal_db.execute(f"DROP TRIGGER {fence}")
    yield normal_db


def setup(
    db,
    *,
    issue=True,
    support=True,
    subtype="timeline_event",
    kind="comment",
    service=S,
    native="I7",
    local="E9",
):
    i7 = key("issue", native, service)
    event = ResourceKey.document(i7, kind, subtype, local)
    add_resource(db, event, RI.scoped(event, i7, subtype, local))
    if issue:
        add_resource(db, i7)
    pr = parent(event, i7)
    if support:
        db.execute(REL, pr)
    return event, i7, pr, event_row(event, pr)


def reject_unchanged(db, sql, values, *, code=None):
    before = rows(db)
    with pytest.raises(sqlite3.IntegrityError) as error:
        db.execute(sql, values)
    if code is not None:
        assert error.value.sqlite_errorcode == code
    assert rows(db) == before


def test_native_i7_and_originals(isolated):
    db = isolated
    event, i7, pr, report = setup(db)
    i8 = key("issue", "I8")
    add_resource(db, i8)
    db.execute(REL, parent(event, i8))
    db.execute(REL, report)
    db.execute(EP, endpoint(report))
    db.execute(EP, endpoint(report, "transfer_to_repository"))
    assert (
        len(
            db.execute(
                "SELECT * FROM resource_relations WHERE relation_kind='parent'"
            ).fetchall()
        )
        == 2
    )
    actual = db.execute(
        f"SELECT {REL_COLS} FROM resource_relations WHERE relation_kind='transfer_event_report'"
    ).fetchone()
    assert tuple(actual) == report
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_i8_is_permanently_ineligible_and_retained(isolated):
    db = isolated
    event, i7, pr, report = setup(db)
    i8 = key("issue", "I8")
    add_resource(db, i8)
    other = parent(event, i8)
    db.execute(REL, other)
    reject_unchanged(db, REL, event_row(event, other), code=787)
    # Arrival of correct I7 support cannot make the I8 payload eligible.
    alternate = parent(event, i7, provenance=J({"source": "another", "evidence": 1}))
    db.execute(REL, alternate)
    reject_unchanged(db, REL, event_row(event, other), code=787)
    db.execute(REL, report)
    assert (
        len(
            db.execute(
                "SELECT * FROM resource_relations WHERE relation_kind='parent'"
            ).fetchall()
        )
        == 3
    )


@pytest.mark.parametrize("missing", ["resource", "report"])
def test_dependency_arrival_requires_original_resupply(isolated, missing):
    db = isolated
    event, i7, pr, report = setup(db, issue=missing != "resource", support=False)
    reject_unchanged(db, REL, report, code=787)
    if missing == "resource":
        reject_unchanged(db, REL, pr, code=787)
        add_resource(db, i7)
    assert (
        db.execute(
            "SELECT count(*) FROM resource_relations WHERE relation_kind='transfer_event_report'"
        ).fetchone()[0]
        == 0
    )
    db.execute(REL, pr)
    assert (
        db.execute(
            "SELECT count(*) FROM resource_relations WHERE relation_kind='transfer_event_report'"
        ).fetchone()[0]
        == 0
    )
    db.execute(REL, report)
    db.execute(EP, endpoint(report))


@pytest.mark.parametrize(
    "part",
    [
        "members",
        "scope-clock",
        "scope-state",
        "provenance",
        "event",
        "service",
        "subtype",
        "resource-kind",
        "issue-id",
    ],
)
def test_complete_parent_and_native_reference(isolated, part):
    db = isolated
    event, i7, pr, report = setup(db)
    scope = json.loads(report[6])
    if part == "members":
        scope["parent_members_json"] = J([key("issue", "missing").coordinates()])
    elif part == "scope-clock":
        ps = json.loads(pr[6])
        ps["clock"]["at_us"] = 12
        scope["parent_scope_json"] = J(ps)
    elif part == "scope-state":
        ps = json.loads(pr[6])
        ps["state"] = "partial"
        scope["parent_scope_json"] = J(ps)
    elif part == "provenance":
        scope["parent_provenance_json"] = J({"source": "other", "evidence": 7})
    elif part == "issue-id":
        scope["parent_members_json"] = J([key("issue", "I8").coordinates()])
    else:
        if part == "service":
            db.execute("INSERT INTO providers VALUES(?,?,?)", (C, "test", "{}"))
        if part == "resource-kind":
            e2 = key("opaque_event", "E-other")
            add_resource(db, e2)
        else:
            e2, _, pr2, _ = setup(
                db,
                support=False,
                issue=part != "event",
                subtype="body" if part == "subtype" else "timeline_event",
                service=C if part == "service" else S,
                native="different" if part in ("service", "subtype") else "I7",
                local="E-other",
            )
            if part == "subtype":
                ps = json.loads(pr2[6])
                ps["document_kind"] = "body"
                pr2 = (*pr2[:6], J(ps), pr2[7])
                db.execute(REL, pr2)
                scope["parent_members_json"] = pr2[4]
                scope["parent_scope_json"] = pr2[6]
        report = (*e2.coordinates(), *report[3:])
        # An E9 report cannot substitute for the absent E-other report.
    report = (*report[:6], J(scope), report[7])
    reject_unchanged(db, REL, report)


@pytest.mark.parametrize(
    "part",
    [
        "event",
        "members",
        "scope",
        "clock",
        "provenance",
        "time",
        "null-members",
        "null-scope",
        "undeclared-target",
        "role",
    ],
)
def test_endpoint_full_event_reference(isolated, part):
    db = isolated
    event, _, _, report = setup(db)
    db.execute(REL, report)
    ep = list(endpoint(report))
    if part == "event":
        e2, _, _, r2 = setup(db, local="E-other", native="I-other")
        ep[:3] = e2.coordinates()
    elif part == "members":
        ep[8] = J([key("repository", "other").coordinates()])
    elif part == "scope":
        scope = json.loads(ep[9])
        scope["event_type"] = "other"
        ep[9] = J(scope)
    elif part == "clock":
        ep[5] = J({"domain": "different", "at_us": 23})
    elif part == "provenance":
        ep[6] = P
    elif part == "time":
        ep[7] = 30
    elif part == "null-members":
        ep[8] = None
    elif part == "null-scope":
        ep[9] = None
    elif part == "undeclared-target":
        ep[4] = J(R)
    elif part == "role":
        ep[3] = "owning_repository"
    reject_unchanged(db, EP, ep)


BAD = [
    "null-members",
    "null-scope",
    "null-provenance",
    "null-child",
    "wrong-kind",
    "wrong-original-type",
    "missing-field",
    "null-support",
    "wrong-support-type",
    "noncanonical-id",
    "noncanonical-scope",
    "bool-clock",
    "float-clock",
    "string-clock",
    "zero-clock",
    "int64-clock",
    "zero-observed",
    "negative-observed",
    "oversize",
    "deep",
    "null-issue",
    "case-service",
    "case-kind",
]


@pytest.mark.parametrize("mutation", BAD)
def test_null_types_canonical_bounds(isolated, mutation):
    db = isolated
    _, _, _, original = setup(db)
    report = list(original)
    scope = json.loads(report[6])
    if mutation == "null-members":
        report[4] = None
    elif mutation == "null-scope":
        report[6] = None
    elif mutation == "null-provenance":
        report[5] = None
    elif mutation == "null-child":
        report[2] = None
    elif mutation == "wrong-kind":
        report[1] = "issue"
    elif mutation == "wrong-original-type":
        scope["event_type"] = 7
    elif mutation == "missing-field":
        scope.pop("clock")
    elif mutation == "null-support":
        scope["parent_scope_json"] = None
    elif mutation == "wrong-support-type":
        scope["parent_members_json"] = []
    elif mutation == "noncanonical-id":
        member = json.loads(scope["parent_members_json"])
        member[0][2] += " "
        scope["parent_members_json"] = J(member)
    elif mutation == "noncanonical-scope":
        report[6] += " "
    elif mutation.endswith("-clock"):
        scope["clock"]["at_us"] = {
            "bool-clock": True,
            "float-clock": 1.5,
            "string-clock": "23",
            "zero-clock": 0,
            "int64-clock": 2**63,
        }[mutation]
    elif mutation == "zero-observed":
        report[7] = 0
    elif mutation == "negative-observed":
        report[7] = -1
    elif mutation == "oversize":
        scope["event_type"] = "x" * 262144
    elif mutation == "deep":
        scope["event_type"] = [
            [[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]
        ]
    elif mutation == "null-issue":
        member = json.loads(scope["parent_members_json"])
        member[0][2] = None
        scope["parent_members_json"] = J(member)
    elif mutation == "case-service":
        # UUID contains no letters: use an actually different service coordinate.
        member = json.loads(scope["parent_members_json"])
        member[0][0] = C
        scope["parent_members_json"] = J(member)
    elif mutation == "case-kind":
        member = json.loads(scope["parent_members_json"])
        member[0][1] = "Issue"
        scope["parent_members_json"] = J(member)
    if report[6] == original[6]:
        report[6] = J(scope)
    reject_unchanged(db, REL, report)
    reject_unchanged(db, REL.replace("INSERT", "INSERT OR IGNORE"), report)


CONFLICT = ["insert", "ignore", "replace", "nothing", "upsert-noop", "upsert-update"]


def conflict(sql, mode, table):
    if mode in ("ignore", "replace"):
        return sql.replace("INSERT", "INSERT OR " + mode.upper())
    if mode == "nothing":
        return sql + " ON CONFLICT DO NOTHING"
    if mode == "upsert-noop":
        return sql + " ON CONFLICT DO UPDATE SET observed_at_us=observed_at_us"
    if mode == "upsert-update":
        return sql + " ON CONFLICT DO UPDATE SET observed_at_us=excluded.observed_at_us"
    return sql


@pytest.mark.parametrize("mode", CONFLICT)
@pytest.mark.parametrize(
    "payload",
    [
        "report-time",
        "report-scope",
        "report-members",
        "endpoint-time",
        "endpoint-scope",
        "endpoint-members",
    ],
)
def test_preconflict_rebind_refused(isolated, mode, payload):
    db = isolated
    _, _, _, report = setup(db)
    db.execute(REL, report)
    db.execute(EP, endpoint(report))
    is_ep = payload.startswith("endpoint")
    row = list(endpoint(report) if is_ep else report)
    if payload.endswith("time"):
        row[7] += 1
    elif payload.endswith("members"):
        row[8 if is_ep else 4] = J([key("repository", "extra").coordinates()])
    else:
        at = 9 if is_ep else 6
        scope = json.loads(row[at])
        scope["event_type"] = "renamed"
        row[at] = J(scope)
    reject_unchanged(db, conflict(EP if is_ep else REL, mode, ""), row)


@pytest.mark.parametrize("action", ["update", "delete", "replace", "upsert"])
@pytest.mark.parametrize(
    "table", ["resources", "resource_relations", "resource_repository_relations"]
)
def test_originals_immutable(isolated, table, action):
    db = isolated
    _, _, _, report = setup(db)
    db.execute(REL, report)
    db.execute(EP, endpoint(report))
    if action == "update":
        reject_unchanged(
            db, f"UPDATE {table} SET provider_resource_id=provider_resource_id", ()
        )
    elif action == "delete":
        reject_unchanged(db, f"DELETE FROM {table}", ())
    elif table == "resources":
        columns = "service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id"
        values = tuple(
            db.execute(f"SELECT {columns} FROM resources LIMIT 1").fetchone()
        )
        sql = f"INSERT INTO resources({columns}) VALUES(?,?,?,?,?,?,?)"
        reject_unchanged(
            db,
            sql.replace("INSERT", "INSERT OR REPLACE")
            if action == "replace"
            else sql
            + " ON CONFLICT DO UPDATE SET provider_resource_id=provider_resource_id",
            values,
        )
    else:
        sql, values = (
            (REL, report) if table == "resource_relations" else (EP, endpoint(report))
        )
        reject_unchanged(
            db,
            sql.replace("INSERT", "INSERT OR REPLACE")
            if action == "replace"
            else sql + " ON CONFLICT DO UPDATE SET observed_at_us=observed_at_us",
            values,
        )


def test_exact_replay_and_null_original_times(isolated):
    db = isolated
    event, issue, pr, report = setup(db)
    # Explicit original NULLs remain NULL and support/report clocks are independent.
    alt = parent(event, issue, clock=None, observed=None)
    db.execute(REL, alt)
    report = (*event_row(event, alt)[:7], None)
    db.execute(REL, report)
    ep = endpoint(report)
    db.execute(EP, ep)
    before = rows(db)
    db.execute(REL + " ON CONFLICT DO NOTHING", report)
    db.execute(EP.replace("INSERT", "INSERT OR IGNORE"), ep)
    assert rows(db) == before


@pytest.mark.parametrize("rollback", ["multirow", "savepoint", "transaction"])
def test_atomic_sql_boundaries(isolated, rollback):
    db = isolated
    _, _, _, report = setup(db)
    before = rows(db)
    bad = list(report)
    bad[2] = J("missing")
    if rollback == "multirow":
        reject_unchanged(db, REL + ",(?,?,?,?,?,?,?,?)", (*report, *bad))
    else:
        db.execute("SAVEPOINT unit" if rollback == "savepoint" else "BEGIN")
        db.execute(REL, report)
        db.execute(EP, endpoint(report))
        wrong = list(endpoint(report, "transfer_to_repository"))
        wrong[7] = 999
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(EP, wrong)
        db.execute("ROLLBACK TO unit" if rollback == "savepoint" else "ROLLBACK")
        if rollback == "savepoint":
            db.execute("RELEASE unit")
        assert rows(db) == before


@pytest.mark.parametrize("mode", CONFLICT)
def test_product_fences_remain(normal_db, mode):
    db = normal_db
    _, _, _, report = setup(db)
    for sql, row in ((REL, report), (EP, endpoint(report))):
        before = rows(db)
        with pytest.raises(sqlite3.IntegrityError, match="I2_TRANSFER_UNSUPPORTED"):
            db.execute(conflict(sql, mode, ""), row)
        assert rows(db) == before
    assert set(FENCES) <= {
        row[0]
        for row in db.execute("SELECT name FROM sqlite_schema WHERE type='trigger'")
    }


def test_product_admission_is_still_fenced(tmp_path):
    p1_schema.initialize(tmp_path / "context.sqlite3", "context", R, C)
    # Preserve the old stage assertion after the new current-authority boundary;
    # an unwired caller now fails earlier with a permission refusal.
    with Context.transaction(tmp_path) as ctx:
        with pytest.raises(AdmissionRefused, match="PERMISSION_DENIED"):
            ctx.admit_transfer_event(None)
    service, _ = fixture_service(DependencySet())
    with Context.transaction(tmp_path, authorization=service) as ctx:
        with pytest.raises(UnsupportedResourceStage):
            ctx.admit_transfer_event(None, admission=fixture_context(service))


def test_connection_requires_all_i4_functions(normal_db):
    db = normal_db
    p1_schema.verify_connection(db)
    for name, arity in [
        ("p1_transfer_event_v1", 7),
        ("p1_transfer_value_v1", 2),
        ("p1_transfer_endpoint_v1", 4),
    ]:
        db.create_function(name, arity, lambda *args: 1, deterministic=False)
        with pytest.raises(p1_schema.SchemaError, match=name):
            p1_schema.verify_connection(db)
        p1_schema.register_functions(db)
    for pragma, wrong in [
        ("foreign_keys", 0),
        ("recursive_triggers", 0),
        ("ignore_check_constraints", 1),
        ("defer_foreign_keys", 1),
        ("trusted_schema", 0),
    ]:
        db.execute(f"PRAGMA {pragma}={wrong}")
        with pytest.raises(p1_schema.SchemaError, match=pragma):
            p1_schema.verify_connection(db)
        p1_schema.configure(db)


def test_binary_collation_and_nonwritable_projections(isolated):
    db = isolated
    event, _, _, report = setup(db)
    lowercase = key("issue", "i7")
    add_resource(db, lowercase)
    other = parent(event, lowercase)
    db.execute(REL, other)
    # Even an input SELECT evaluated with NOCASE cannot change the FK target's BINARY comparison.
    reject_unchanged(
        db,
        REL.replace("VALUES(?,?,?,?,?,?,?,?)", "SELECT ?,?,?,?,?,?,?,? COLLATE NOCASE"),
        event_row(event, other),
        code=787,
    )
    for name in (
        "resources_native_event_fk",
        "parent_report_typed_fk",
        "event_report_identity_fk",
    ):
        assert all(
            r[4] == "BINARY" for r in db.execute(f"PRAGMA index_xinfo({name})") if r[5]
        )
    before = rows(db)
    with pytest.raises(sqlite3.OperationalError, match="generated column"):
        db.execute(
            f"INSERT INTO resource_relations({REL_COLS},event_support_id) VALUES(?,?,?,?,?,?,?,?,?)",
            (*report, J("I7")),
        )
    assert rows(db) == before


def test_endpoint_cannot_exist_without_original_report(isolated):
    db = isolated
    _, _, _, report = setup(db)
    reject_unchanged(db, EP, endpoint(report), code=787)
    db.execute(REL, report)
    db.execute(EP, endpoint(report))


def test_sql_event_syntax_is_not_i5_semantic_authentication(isolated):
    db = isolated
    event, _, pr, _ = setup(db)
    report = event_row(event, pr, event_type="unverified-original-type")
    db.execute(REL, report)
    # Deliberate scope limit: syntax plus typed references is not Provider truth.
    assert (
        json.loads(
            db.execute(
                "SELECT scope_json FROM resource_relations WHERE relation_kind='transfer_event_report'"
            ).fetchone()[0]
        )["event_type"]
        == "unverified-original-type"
    )
