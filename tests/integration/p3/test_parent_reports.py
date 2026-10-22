"""I3 typed Parent evidence; direct SQL deliberately bypasses Python admission."""

import json
import os
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.p1_context import canonical as J
from repo_catalog.domain.production_context import ContextError, ResourceRelation
from repo_catalog.domain.resource_identification import ResourceIdentification as RI

S = "22222222-2222-4222-8222-222222222222"
R = "11111111-1111-4111-8111-111111111111"
C = "33333333-3333-4333-8333-333333333333"
PROV = J({"source": "original-provider", "evidence": ["capture", "parent-7"]})
COLS = "service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,members_json,provenance_json,scope_json,observed_at_us"
INSERT = f"INSERT INTO resource_relations({COLS}) VALUES(?,?,?,?,?,?,?,?)"


def key(kind, native):
    return ResourceKey.from_native(S, kind, native)


def report(child, parent, subtype=None, observed=17, clock=11, provenance=PROV):
    return ResourceRelation(
        child,
        "parent",
        (parent,),
        provenance,
        J(
            {
                "clock": {"domain": "provider-clock", "at_us": clock},
                "document_kind": subtype,
                "state": "complete",
            }
        ),
        observed,
    )


def row(value):
    return (*value.parent_report_key.coordinates(), value.observed_at_us)


def snapshot(db):
    return {
        name: sorted(db.execute(f'SELECT * FROM "{name}"').fetchall(), key=J)
        for (name,) in db.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


@pytest.fixture
def raw(request):
    db = sqlite3.connect(":memory:", isolation_level=None)
    p1_schema.register_functions(db)
    p1_schema.configure(db)
    statements = []
    db.set_trace_callback(statements.append)
    db.executescript(p1_schema.compose("context"))
    db.execute("INSERT INTO providers VALUES(?,?,?)", (S, "test", "{}"))
    try:
        yield db
    finally:
        target = os.environ.get("I3_SQL_TRACE")
        if target:
            import hashlib

            path = Path(target)
            path.mkdir(parents=True, exist_ok=True)
            name = hashlib.sha256(request.node.nodeid.encode()).hexdigest()
            (path / (name + ".json")).write_text(
                json.dumps(
                    {
                        "nodeid": request.node.nodeid,
                        "statements": statements,
                        "final_rows": snapshot(db),
                        "sqlite": db.execute(
                            "SELECT sqlite_version(),sqlite_source_id()"
                        ).fetchone(),
                    },
                    ensure_ascii=True,
                    indent=2,
                )
                + "\n"
            )
        db.close()


def resource(db, value, declaration=None):
    declaration = declaration or RI.unscoped(value)
    db.execute(
        "INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id) VALUES(?,?,?,?,?,?,?)",
        (*value.coordinates(), *declaration.columns),
    )


@pytest.fixture
def pair(raw):
    child = key("document", ["native", ["D", []]])
    parent = key("project", "P7")
    resource(raw, child, RI.global_document(child))
    resource(raw, parent)
    return raw, child, parent


@pytest.mark.parametrize("native", ["", [], [""], [[]], ["D", ["é", []]]])
def test_global_child_first_late_parent_original_resupply(tmp_path, native):
    p1_schema.initialize(tmp_path / "context.sqlite3", "context", R, C)
    child, parent = key("document", native), key("project", ["P", "7"])
    original = report(child, parent, clock=None, observed=None)
    with Context.transaction(tmp_path) as ctx:
        ctx.provider(S, "test")
        ctx.resource(child, identification=RI.global_document(child))
        assert ctx.relations(child, "parent") == ()
        before = snapshot(ctx.db)
        with pytest.raises(ContextError, match="RESOURCE_UNAVAILABLE"):
            ctx.relation(original)
        assert snapshot(ctx.db) == before
    with Context.transaction(tmp_path) as ctx:
        ctx.resource(parent)
        assert ctx.relations(child, "parent") == ()
        with pytest.raises(ContextError, match="OMITTED_BY_SELECTION"):
            ctx.relation(original, selected_resources=frozenset({child}))
        with pytest.raises(ContextError, match="PERMISSION_DENIED"):
            ctx.relation(original, permitted=lambda candidate: candidate != parent)
        assert ctx.relations(child, "parent") == ()
        assert ctx.relation(original) == "insert"
        assert ctx.relation(original) == "duplicate"
        with pytest.raises(ContextError, match="PERMISSION_DENIED"):
            ctx.relation(original, permitted=lambda _: False)
        with pytest.raises(ContextError, match="OMITTED_BY_SELECTION"):
            ctx.relation(original, selected_resources=frozenset())
    with Context.snapshot(tmp_path) as ctx:
        assert ctx.relations(child, "parent") == (original,)
        assert (
            ctx.relations(child, "parent")[0].parent_report_key
            == original.parent_report_key
        )
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def test_scoped_alternatives_i8_document_children_and_nonleaf(tmp_path):
    p1_schema.initialize(tmp_path / "context.sqlite3", "context", R, C)
    i7, i8 = key("issue", "I7"), key("issue", "I8")
    event = ResourceKey.timeline_event(i7, ["E", "7"])
    pr = key("pull_request", ["project", "7"])
    doc = ResourceKey.document(pr, "document", "body", ["D", "1"])
    global_doc, child = key("document", "global"), key("unknown-child", "child")
    reports = (
        report(event, i7, "timeline_event"),
        report(event, i8, "timeline_event"),
        report(doc, pr, "body"),
        report(global_doc, doc),
        report(child, global_doc),
    )
    with Context.transaction(tmp_path) as ctx:
        ctx.provider(S, "test")
        ctx.resource(
            event, identification=RI.scoped(event, i7, "timeline_event", ["E", "7"])
        )
        ctx.resource(doc, identification=RI.scoped(doc, pr, "body", ["D", "1"]))
        for value in (i7, i8, pr, child):
            ctx.resource(value)
        ctx.resource(global_doc, identification=RI.global_document(global_doc))
        for value in reports:
            assert ctx.relation(value) == "insert"
        assert set(ctx.relations(event, "parent")) == set(reports[:2])
        assert ctx.relations(doc, "parent") == (reports[2],)
        assert ctx.relations(global_doc, "parent") == (reports[3],)
        assert ctx.relations(child, "parent") == (reports[4],)
        with pytest.raises(ValueError, match="I2_TRANSFER_UNSUPPORTED"):
            ctx.relation(
                ResourceRelation(event, "transfer_event_report", (), PROV, "{}", 17)
            )


@pytest.mark.parametrize("which", ["child", "parent"])
def test_sql_missing_resource_is_foreign_key_error(raw, which):
    child, parent = key("document", "D"), key("project", "P")
    if which != "child":
        resource(raw, child, RI.global_document(child))
    if which != "parent":
        resource(raw, parent)
    before = snapshot(raw)
    with pytest.raises(sqlite3.IntegrityError) as error:
        raw.execute(INSERT, row(report(child, parent)))
    assert error.value.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY
    assert snapshot(raw) == before


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-subtype",
        "wrong-subtype",
        "wrong-parent-kind",
        "null-clock",
        "missing-clock",
        "incomplete",
        "multi",
        "empty",
        "null-member",
        "short-member",
        "cross-service",
        "noncanonical-member",
        "null-identity",
        "number-identity",
        "duplicate-scope-key",
        "noncanonical-scope",
        "null-provenance",
        "missing-evidence",
        "null-scope",
        "zero-observed",
        "negative-observed",
        "null-child",
        "null-parent-kind",
        "bool-clock",
        "deep-scope",
        "oversize-scope",
        "surrogate",
    ],
)
def test_sql_invalid_parent_never_stores_or_hides_behind_ignore(pair, mutation):
    db, child, parent = pair
    values = list(row(report(child, parent)))
    scope = json.loads(values[6])
    if mutation == "missing-subtype":
        scope.pop("document_kind")
    if mutation == "wrong-subtype":
        scope["document_kind"] = "body"
    if mutation == "wrong-parent-kind":
        # A scoped Document cannot use an Issue as its typed PR Parent.
        pr = key("pull_request", "PR")
        child = ResourceKey.document(pr, "document", "body", "D")
        resource(db, child, RI.scoped(child, pr, "body", "D"))
        values[0:3] = child.coordinates()
        scope["document_kind"] = "body"
        values[4] = J([[S, "issue", J("I7")]])
    if mutation == "null-clock":
        scope["clock"] = None
    if mutation == "missing-clock":
        scope.pop("clock")
    if mutation == "bool-clock":
        scope["clock"]["at_us"] = True
    if mutation == "incomplete":
        scope["state"] = "partial"
    if mutation == "multi":
        values[4] = J([parent.coordinates(), child.coordinates()])
    if mutation == "empty":
        values[4] = "[]"
    if mutation == "null-member":
        values[4] = "[null]"
    if mutation == "short-member":
        values[4] = J([[S, "project"]])
    if mutation == "cross-service":
        values[4] = J([[C, "project", J("P")]])
    if mutation == "noncanonical-member":
        values[4] = values[4] + " "
    if mutation == "null-identity":
        values[4] = J([[S, "project", None]])
    if mutation == "number-identity":
        values[4] = J([[S, "project", "7"]])
    if mutation == "null-parent-kind":
        values[4] = J([[S, None, J("P")]])
    if mutation == "null-provenance":
        values[5] = None
    if mutation == "missing-evidence":
        values[5] = J({"source": "original"})
    if mutation == "zero-observed":
        values[7] = 0
    if mutation == "negative-observed":
        values[7] = -1
    if mutation == "null-child":
        values[2] = None
    values[6] = J(scope)
    if mutation == "duplicate-scope-key":
        values[6] = values[6][:-1] + ',"state":"complete"}'
    if mutation == "noncanonical-scope":
        values[6] += " "
    if mutation == "null-scope":
        values[6] = None
    if mutation == "deep-scope":
        values[6] = "[" * 80 + "[]" + "]" * 80
    if mutation == "oversize-scope":
        values[6] = J({"x": "a" * 262145})
    if mutation == "surrogate":
        values[4] = J([[S, "project", '"\\ud800"']])
    before = snapshot(db)
    for sql in (INSERT, INSERT.replace("INSERT INTO", "INSERT OR IGNORE INTO")):
        with pytest.raises(sqlite3.DatabaseError):
            db.execute(sql, values)
        assert snapshot(db) == before
    assert not db.execute("PRAGMA foreign_key_check").fetchall()


@pytest.mark.parametrize(
    "verb", ["insert", "ignore", "nothing", "replace", "or-replace", "upsert", "noop"]
)
@pytest.mark.parametrize("observed", [None, 18])
def test_sql_observation_rebind_precedes_conflicts(pair, verb, observed):
    db, child, parent = pair
    original = row(report(child, parent))
    db.execute(INSERT, original)
    sql = {
        "insert": INSERT,
        "ignore": INSERT.replace("INSERT INTO", "INSERT OR IGNORE INTO"),
        "nothing": INSERT + " ON CONFLICT DO NOTHING",
        "replace": INSERT.replace("INSERT INTO", "REPLACE INTO"),
        "or-replace": INSERT.replace("INSERT INTO", "INSERT OR REPLACE INTO"),
        "upsert": INSERT
        + " ON CONFLICT DO UPDATE SET observed_at_us=excluded.observed_at_us",
        "noop": INSERT
        + " ON CONFLICT DO UPDATE SET observed_at_us=resource_relations.observed_at_us",
    }[verb]
    before = snapshot(db)
    with pytest.raises(sqlite3.IntegrityError, match="observation rebind"):
        db.execute(sql, (*original[:-1], observed))
    assert snapshot(db) == before


@pytest.mark.parametrize(
    "delta", ["members", "provenance", "scope-clock", "scope-domain"]
)
def test_distinct_complete_report_keys_are_preserved(pair, delta):
    db, child, parent = pair
    original = report(child, parent)
    if delta == "members":
        other = key("project", "P8")
        resource(db, other)
        alternative = report(child, other)
    elif delta == "provenance":
        alternative = replace(
            original, provenance_json=J({"source": "other", "evidence": "different"})
        )
    elif delta == "scope-clock":
        alternative = report(child, parent, clock=12)
    else:
        scope = json.loads(original.scope_json)
        scope["clock"]["domain"] = "independent-clock"
        alternative = replace(original, scope_json=J(scope))
    for value in (original, alternative):
        db.execute(INSERT, row(value))
    assert len(db.execute("SELECT * FROM resource_relations").fetchall()) == 2
    assert original.parent_report_key != alternative.parent_report_key


def test_sql_full_report_typed_reference(pair):
    db, child, parent = pair
    original = report(child, parent)
    db.execute(INSERT, row(original))
    names = COLS.split(",")[:-1] + ["source_document_kind", "parent_kind"]
    # Disposable test consumer proves the actual complete nine-column target.
    db.execute(
        "CREATE TABLE probe("
        + ",".join(n + " TEXT NOT NULL" for n in names)
        + ", FOREIGN KEY("
        + ",".join(names)
        + ") REFERENCES resource_relations("
        + ",".join(names)
        + ")) STRICT"
    )
    target = (*original.parent_report_key.coordinates(), "", parent.resource_kind)
    sql = "INSERT INTO probe VALUES(" + ",".join("?" for _ in target) + ")"
    db.execute(sql, target)
    for index in range(len(target)):
        changed = list(target)
        changed[index] += "different"
        before = snapshot(db)
        with pytest.raises(sqlite3.IntegrityError) as error:
            db.execute(sql, changed)
        assert error.value.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY
        assert snapshot(db) == before
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("subtype", [None, "", "other", "body"])
def test_global_scoped_nonnull_absence_projection(raw, subtype):
    pr = key("pull_request", "PR")
    scoped = ResourceKey.document(pr, "document", "body", "D")
    resource(raw, pr)
    resource(raw, scoped, RI.scoped(scoped, pr, "body", "D"))
    global_doc = key("document", "global")
    resource(raw, global_doc, RI.global_document(global_doc))
    for child in (scoped, global_doc):
        before = snapshot(raw)
        if subtype == ("body" if child == scoped else None):
            raw.execute(INSERT, row(report(child, pr, subtype)))
            assert raw.execute(
                "SELECT source_document_kind FROM resource_relations WHERE provider_resource_id=?",
                (child.provider_resource_id,),
            ).fetchone() == (subtype or "",)
        else:
            with pytest.raises((ValueError, sqlite3.IntegrityError)):
                raw.execute(INSERT, row(report(child, pr, subtype)))
            assert snapshot(raw) == before


def test_sql_mutation_guards_atomic_multirow_and_savepoint(pair):
    db, child, parent = pair
    original = row(report(child, parent))
    before = snapshot(db)
    bad = (*original[:4], "[]", *original[5:])
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            f"INSERT INTO resource_relations({COLS}) VALUES(?,?,?,?,?,?,?,?),(?,?,?,?,?,?,?,?)",
            (*original, *bad),
        )
    assert snapshot(db) == before
    db.execute("BEGIN IMMEDIATE")
    db.execute("SAVEPOINT report_unit")
    db.execute(INSERT, original)
    db.execute("ROLLBACK TO report_unit")
    assert snapshot(db) == before
    db.execute("RELEASE report_unit")
    db.execute(INSERT, original)
    db.execute("ROLLBACK")
    assert snapshot(db) == before
    db.execute(INSERT, original)
    before = snapshot(db)
    for sql in (
        "UPDATE resource_relations SET members_json=members_json",
        "DELETE FROM resource_relations",
        INSERT.replace("INSERT INTO", "REPLACE INTO"),
    ):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(sql, original if "?" in sql else ())
        assert snapshot(db) == before
    with pytest.raises(sqlite3.OperationalError):
        db.execute("UPDATE resource_relations SET parent_id=?", (J("fabricated"),))
    assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]


def test_general_ordered_multimember_report_unchanged(pair):
    db, child, parent = pair
    values = (
        S,
        child.resource_kind,
        child.provider_resource_id,
        "opaque-ordered-group",
        J([parent.coordinates(), child.coordinates()]),
        PROV,
        "{}",
        None,
    )
    db.execute(INSERT, values)
    assert db.execute(f"SELECT {COLS} FROM resource_relations").fetchone() == values
    assert db.execute(
        "SELECT parent_id,source_document_kind FROM resource_relations"
    ).fetchone() == (None, None)


def test_stored_parent_revalidation_is_bounded_not_full_recovery(pair):
    from repo_catalog.adapters.sqlite.recovery_validation import (
        validate_stored_context_relations,
    )
    from repo_catalog.domain.recovery import BackupValidationError

    db, child, parent = pair
    original = row(report(child, parent))
    db.execute(INSERT, original)
    validate_stored_context_relations(db)
    triggers = db.execute(
        "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name='resource_relations'"
    ).fetchall()
    for name, _ in triggers:
        db.execute(f'DROP TRIGGER "{name}"')
    db.execute("PRAGMA ignore_check_constraints=ON")
    db.execute("UPDATE resource_relations SET scope_json='{}'")
    db.execute("PRAGMA ignore_check_constraints=OFF")
    for _, sql in triggers:
        db.execute(sql)
    with pytest.raises(BackupValidationError):
        validate_stored_context_relations(db)


def test_source_subtype_replay_and_policy_rejections_preserve_existing_unit(tmp_path):
    p1_schema.initialize(tmp_path / "context.sqlite3", "context", R, C)
    child, parent = key("document", "D"), key("pull_request", "P")
    original = report(child, parent)
    with Context.transaction(tmp_path) as ctx:
        ctx.provider(S, "test")
        ctx.resource(child, identification=RI.global_document(child))
        ctx.resource(parent)
        ctx.relation(original)
        before = snapshot(ctx.db)
        for invalid, expected in (
            (replace(original, observed_at_us=18), "EVIDENCE_REBIND"),
            (
                replace(
                    original,
                    scope_json=J(
                        {
                            "clock": {"domain": "provider-clock", "at_us": 11},
                            "document_kind": "body",
                            "state": "complete",
                        }
                    ),
                ),
                "PARENT_SOURCE_TYPE",
            ),
        ):
            with pytest.raises(ContextError, match=expected):
                ctx.relation(invalid)
            assert snapshot(ctx.db) == before
        assert ctx.relations(child, "parent") == (original,)
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def test_sql_exact_replay_nothing_and_insert_select_returning(pair):
    db, child, parent = pair
    original = row(report(child, parent))
    returned = db.execute(
        INSERT + " RETURNING parent_id,source_document_kind", original
    ).fetchall()
    assert returned == [(parent.provider_resource_id, "")]
    before = snapshot(db)
    for sql in (
        INSERT + " ON CONFLICT DO NOTHING",
        INSERT.replace("INSERT INTO", "INSERT OR IGNORE INTO"),
    ):
        db.execute(sql, original)
        assert snapshot(db) == before
    alternate = report(child, parent, clock=12)
    select = f"INSERT INTO resource_relations({COLS}) SELECT ?,?,?,?,?,?,?,? RETURNING report_clock_json"
    assert db.execute(select, row(alternate)).fetchall() == [
        (J({"domain": "provider-clock", "at_us": 12}),)
    ]
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_parent_typed_construction_bounds_before_general_json_decode():
    child, parent = key("document", "D"), key("project", "P")
    with pytest.raises(ValueError, match="nesting depth"):
        ResourceRelation(
            child, "parent", (parent,), PROV, "[" * 5000 + "[]" + "]" * 5000, 17
        )


def test_parent_udf_registration_required_and_deterministic(raw):
    assert any(
        r[0] == "p1_parent_report_v1" and r[4] == 7 and r[5] & 2048
        for r in raw.execute("PRAGMA function_list")
    )
    raw.create_function("p1_parent_report_v1", 7, None)
    with pytest.raises(p1_schema.SchemaError, match="p1_parent_report_v1"):
        p1_schema.verify_connection(raw)
