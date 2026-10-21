"""I2 tests execute packaged DDL/UDFs and real production capabilities."""

import hashlib
import json
import sqlite3
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.github.production_intake import normalize_timeline_event
from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.adapters.sqlite.recovery_validation import (
    StoredContextInvariantError,
    validate_stored_context_relations,
)
from repo_catalog.application.acquisition import ProviderAcquisition
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.exchange import ExchangeError
from repo_catalog.domain.p1_context import (
    FieldCandidate,
    FieldClock,
    ResourceKey,
    TransferEventReport,
    canonical,
)
from repo_catalog.domain.p1_coordination import RequestIdentity
from repo_catalog.domain.production_context import ResourceObservation, ResourceRelation
from repo_catalog.domain.production_query import SearchQuery
from repo_catalog.domain.resource_identification import ResourceIdentification as RI
from repo_catalog.domain.resource_identity import encode_identity, parse_identity
from repo_catalog.domain.resource_stage import (
    UnsupportedIdentificationStage,
    UnsupportedResourceStage,
    preflight_transfer,
)
from tests.integration.i3.test_selective_exchange import (
    catalog,
    fixture,
    receive,
    scope,
)

S = "22222222-2222-4222-8222-222222222222"
PROV = canonical({"source": "i2-product", "evidence": "original"})
INSERT = "INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id) VALUES(?,?,?,?,?,?,?)"


def snapshot(db):
    return {
        name: db.execute(f'SELECT * FROM "{name}" ORDER BY 1').fetchall()
        for (name,) in db.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    }


def authorities(path):
    result = {}
    for role in ("core", "context"):
        db = p1_schema.connect(path / (role + ".sqlite3"), role)
        try:
            result[role] = snapshot(db)
        finally:
            db.close()
    return result


@pytest.fixture
def db():
    db = sqlite3.connect(":memory:", isolation_level=None)
    p1_schema.register_functions(db)
    p1_schema.configure(db)
    db.executescript(p1_schema.compose("context"))
    db.execute("INSERT INTO providers VALUES(?,'synthetic','{}')", (S,))
    yield db
    db.close()


@pytest.mark.parametrize("native", ["", [], [""], [[]], ["a", ["b", []]], "é\x00😀"])
def test_global_and_child_first_roundtrip(db, native):
    store = ContextStore(db)
    key = ResourceKey.global_document(S, native)
    declaration = RI.global_document(key)
    store.resource(key, identification=declaration)
    store.resource(ResourceKey(*key.coordinates()), identification=declaration)
    assert store.identification(key) == declaration
    namespace = ResourceKey.from_native(S, "issue", ["project", "I7"])
    child = ResourceKey.timeline_event(namespace, native)
    child_declaration = RI.scoped(child, namespace, "timeline_event", native)
    store.resource(child, identification=child_declaration)
    assert store.identification(child) == child_declaration
    assert not db.execute(
        "SELECT 1 FROM resources WHERE resource_kind='issue'"
    ).fetchall()
    store.resource(namespace)
    assert not db.execute("SELECT 1 FROM resource_relations").fetchall()
    assert not db.execute("PRAGMA foreign_key_check").fetchall()


@pytest.mark.parametrize(
    "verb,suffix",
    [
        ("INSERT", ""),
        ("INSERT OR IGNORE", ""),
        ("INSERT", " ON CONFLICT DO NOTHING"),
        ("REPLACE", ""),
        ("INSERT OR REPLACE", ""),
        ("INSERT", " ON CONFLICT DO UPDATE SET document_kind=excluded.document_kind"),
        ("INSERT", " ON CONFLICT DO UPDATE SET document_kind=document_kind WHERE 0"),
    ],
)
@pytest.mark.parametrize("global_first", [False, True])
def test_conflicting_declaration_refuses_before_all_conflict_shortcuts(
    db, verb, suffix, global_first
):
    namespace = ResourceKey.from_native(S, "pull_request", "7")
    key = ResourceKey.document(namespace, "document", "body", ["D", []])
    scoped, global_ = (
        RI.scoped(key, namespace, "body", ["D", []]),
        RI.global_document(key),
    )
    first, second = (global_, scoped) if global_first else (scoped, global_)
    db.execute(INSERT, (*key.coordinates(), *first.columns))
    before = snapshot(db)
    with pytest.raises(sqlite3.IntegrityError) as error:
        db.execute(
            INSERT.replace("INSERT", verb, 1) + suffix,
            (*key.coordinates(), *second.columns),
        )
    assert error.value.sqlite_errorcode == 1811
    assert snapshot(db) == before


@pytest.mark.parametrize(
    "raw",
    [
        None,
        b'"7"',
        "7",
        "null",
        "{}",
        "[true]",
        ' "7"',
        '"\\u0037"',
        '"é"',
        '"\\ud800"',
        "[" * 33 + "]" * 33,
    ],
)
def test_direct_sql_canonical_refusal(db, raw):
    before = snapshot(db)
    with pytest.raises(sqlite3.Error):
        db.execute(INSERT, (S, "opaque", raw, None, None, None, None))
    assert snapshot(db) == before


def test_unknown_binary_names_and_full_fk(db):
    for kind in ("opaque", "Opaque", " opaque ", "\x00"):
        for native in ("A", "a", "é", "e\u0301", "", [], [""], [[]]):
            ContextStore(db).resource(ResourceKey.from_native(S, kind, native))
    assert db.execute("SELECT count(*) FROM resources").fetchone()[0] == 32
    for index in db.execute("PRAGMA index_list(resources)").fetchall():
        assert all(
            r[4] == "BINARY"
            for r in db.execute(f'PRAGMA index_xinfo("{index[1]}")')
            if r[5]
        )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO field_candidates(service_instance_uuidv4,resource_kind,provider_resource_id,field_name,value_json,clock_json,provenance_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)",
            (
                S,
                "OPAQUE",
                encode_identity("A"),
                "title",
                '"value"',
                '{"at_us":1,"domain":"provider"}',
                PROV,
                2,
            ),
        )


@pytest.mark.parametrize(
    "raw,bad",
    [
        ('"' + "a" * 262142 + '"', '"' + "a" * 262143 + '"'),
        ("[" * 32 + "]" * 32, "[" * 33 + "]" * 33),
        (
            "[" + ",".join('""' for _ in range(4095)) + "]",
            "[" + ",".join('""' for _ in range(4096)) + "]",
        ),
    ],
)
def test_real_sql_inclusive_identity_limits_and_prescan(db, monkeypatch, raw, bad):
    db.execute(INSERT, (S, "limit", raw, None, None, None, None))
    before = snapshot(db)
    from repo_catalog.domain import resource_identity

    def decoder_must_not_run(*args, **kwargs):
        raise AssertionError("over-limit identity reached JSON decoder")

    with monkeypatch.context() as patch:
        patch.setattr(resource_identity.json, "loads", decoder_must_not_run)
        assert db.execute("SELECT p1_resource_identity_v1(?)", (bad,)).fetchone() == (
            0,
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(INSERT, (S, "limit", bad, None, None, None, None))
    assert snapshot(db) == before


@pytest.mark.parametrize(
    "pragma,value",
    [
        ("foreign_keys", 0),
        ("recursive_triggers", 0),
        ("ignore_check_constraints", 1),
        ("defer_foreign_keys", 1),
        ("trusted_schema", 0),
    ],
)
def test_unsupported_connection_configuration_refuses(db, pragma, value):
    db.execute(f"PRAGMA {pragma}={value}")
    with pytest.raises(p1_schema.SchemaError, match="configuration"):
        p1_schema.verify_connection(db)


def test_missing_resource_function_refuses_configuration(db):
    db.create_function("p1_resource_identity_v1", 1, None)
    with pytest.raises(p1_schema.SchemaError, match="deterministic"):
        p1_schema.verify_connection(db)


def test_production_reopen_query_and_opaque_reports(tmp_path):
    catalog(tmp_path)
    namespace = ResourceKey.from_native(S, "pull_request", "missing")
    child = ResourceKey.document(namespace, "document", "body", ["D", []])
    declaration = RI.scoped(child, namespace, "body", ["D", []])
    opaque = ResourceKey.from_native(S, "unknown-kind", [])
    with Context.transaction(tmp_path) as ctx:
        ctx.provider(S, "synthetic")
        ctx.observe(ResourceObservation(child, identification=declaration))
        ctx.resource(opaque)
        ctx.relation(
            ResourceRelation(child, "ordered-opaque", (opaque,), PROV, "{}", 2)
        )
    with Context.snapshot(tmp_path) as ctx:
        assert ctx.identification(ResourceKey(*child.coordinates())) == declaration
        assert ctx.relations(child, "ordered-opaque")[0].members == (opaque,)
        assert namespace not in ctx.resources()
    view = ProductionQueryService(tmp_path).get_context_resource(child)
    assert view.identification == declaration
    assert view.identifier_namespace == namespace
    assert "parent" not in view.to_dict()
    assert view.provider_document_id == '["D",[]]'


@pytest.mark.parametrize("graphql", [False, True])
def test_real_nontransfer_provider_native_event_persists_and_reopens(tmp_path, graphql):
    catalog(tmp_path)
    with Context.transaction(tmp_path) as ctx:
        ctx.provider(S, "synthetic")
    native = "EV_opaque" if graphql else 100
    payload = (
        {"id": native, "__typename": "LabeledEvent"}
        if graphql
        else {"id": native, "event": "labeled"}
    )
    unit = normalize_timeline_event(
        S, "issue", 7, native, payload, 5, PROV, graphql=graphql
    )
    ProviderAcquisition(tmp_path).admit_unit(unit)
    with Context.snapshot(tmp_path) as ctx:
        declaration = ctx.identification(
            ResourceKey(*unit.primary_resource.coordinates())
        )
        assert parse_identity(declaration.provider_document_id) == (
            ["github:node_id", native] if graphql else "100"
        )
        assert unit.primary_resource in ctx.resources()
        assert not ctx.repository_relations(unit.primary_resource)
        assert not ctx.db.execute(
            "SELECT 1 FROM resource_relations WHERE relation_kind='transfer_event_report'"
        ).fetchall()
        for observation in unit.observations:
            for candidate in observation.fields:
                assert candidate in ctx.candidates(
                    candidate.resource, candidate.field_name
                )


def test_supported_observation_late_sql_failure_rolls_back_whole_unit(tmp_path):
    catalog(tmp_path)
    key = ResourceKey.global_document(S, ["body", []])
    with Context.transaction(tmp_path) as ctx:
        ctx.provider(S, "synthetic")
        before = snapshot(ctx.db)
        field = FieldCandidate(
            key,
            "text_body_sha256",
            canonical("a" * 64),
            FieldClock("provider", 1),
            PROV,
            2,
        )
        with pytest.raises(sqlite3.IntegrityError):
            ctx.observe(ResourceObservation(key, (field,), RI.global_document(key)))
        assert snapshot(ctx.db) == before
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def test_real_commit_refusal_rolls_back_supported_resource(tmp_path, monkeypatch):
    from repo_catalog.adapters.sqlite import production_context

    catalog(tmp_path)
    original = production_context.connect

    def refusing_commit(path, role):
        connection = original(path, role)
        connection.set_authorizer(
            lambda action, first, *rest: (
                sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_TRANSACTION and first == "COMMIT"
                else sqlite3.SQLITE_OK
            )
        )
        return connection

    with monkeypatch.context() as patch:
        patch.setattr(production_context, "connect", refusing_commit)
        with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
            with Context.transaction(tmp_path) as ctx:
                ctx.provider(S, "synthetic")
                key = ResourceKey.global_document(S, [])
                ctx.resource(key, identification=RI.global_document(key))
    with Context.snapshot(tmp_path) as ctx:
        assert ctx.resources() == ()
        assert not ctx.db.execute("SELECT 1 FROM providers").fetchall()


@pytest.mark.parametrize(
    "representation",
    ["transfer_event_report", "transfer_from_repository", "transfer_to_repository"],
)
def test_empty_explicit_transfer_routes_refuse_without_stop(tmp_path, representation):
    catalog(tmp_path)
    with Context.transaction(tmp_path) as ctx:
        with pytest.raises(UnsupportedResourceStage):
            if representation == "transfer_event_report":
                ctx.transfer_event_reports()
            else:
                ctx.relations_for_repository(str(uuid4()), representation)
    assert not (tmp_path / "p1-recovery-stop.json").exists()
    for operation in (
        lambda: ExchangeService(tmp_path).export_transfer_events(),
        lambda: ProductionQueryService(tmp_path).transfer_event_reports(),
    ):
        with pytest.raises(UnsupportedResourceStage):
            operation()


@pytest.mark.parametrize("nested", [False, True])
def test_structural_preflight_never_interprets_payload_text(nested):
    item = {"relation_kind": "transfer_event_report"}
    value = {"units": [{"operations": [item]}]} if nested else item
    with pytest.raises(UnsupportedResourceStage):
        preflight_transfer(value)
    preflight_transfer(
        {
            "relation_kind": "ordinary",
            "scope": {"relation_kind": "transfer_event_report"},
            "value": "transfer_event_report",
        }
    )


def test_selected_real_wire_without_identification_refuses_before_core_effects(
    tmp_path,
):
    a, b = tmp_path / "a", tmp_path / "b"
    r1, _, issue, _ = fixture(a)
    catalog(b)
    package = ExchangeService(a).export_package(selection=scope())
    row = dict(package.context["resources"][0])
    row.update(resource_kind="document", provider_resource_id='["global",[]]')
    data = dict(package.context, resources=[*package.context["resources"], row])
    hostile = replace(package, context=data, digest_sha256=None)
    before = authorities(b)
    with pytest.raises(UnsupportedIdentificationStage):
        receive(b, hostile, (r1,))
    assert authorities(b) == before
    with Context.snapshot(b) as ctx:
        assert ctx.resources() == ()
    # Same valid envelope can select Core independently, including on replay.
    report = receive(
        b,
        hostile,
        (r1,),
        selection=scope(include_context=False),
        request=RequestIdentity(str(uuid4()), str(uuid4())),
    )
    assert report.admitted_core_objects == 1


@pytest.mark.parametrize("provider_only", [False, True])
@pytest.mark.parametrize("prime_replay", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_real_selected_transfer_wire_refuses_before_effects_and_replay(
    tmp_path, provider_only, prime_replay, reverse
):
    a, b = tmp_path / "a", tmp_path / "b"
    r1, _, issue, _ = fixture(a)
    catalog(b)
    package = ExchangeService(a).export_package(selection=scope())
    event = ResourceKey.timeline_event(issue, ["event", "N"])
    provider = ResourceKey.from_native(
        issue.service_instance_uuidv4, "repository", "R_node"
    )
    report = TransferEventReport.from_targets(
        event,
        clock=FieldClock("provider:event", 3),
        provenance_json=PROV,
        observed_at_us=4,
        from_target_json=None if provider_only else "null",
        to_target_json=None,
        from_provider_repository=provider if provider_only else None,
    )
    data = {key: list(rows) for key, rows in package.context.items()}
    for key in (event, provider):
        data["resources"].append(
            dict(
                zip(
                    (
                        "service_instance_uuidv4",
                        "resource_kind",
                        "provider_resource_id",
                    ),
                    key.coordinates(),
                )
            )
        )
    data["resource_relations"].append(
        dict(
            zip(
                (
                    "service_instance_uuidv4",
                    "resource_kind",
                    "provider_resource_id",
                    "relation_kind",
                    "members_json",
                    "provenance_json",
                    "scope_json",
                    "observed_at_us",
                ),
                (
                    *event.coordinates(),
                    "transfer_event_report",
                    report.members_json,
                    PROV,
                    report.scope_json,
                    4,
                ),
            )
        )
    )
    for endpoint in (*report.from_relations, *report.to_relations):
        data["resource_repository_relations"].append(
            dict(
                zip(
                    (
                        "service_instance_uuidv4",
                        "resource_kind",
                        "provider_resource_id",
                        "relation_kind",
                        "target_json",
                        "clock_json",
                        "provenance_json",
                        "observed_at_us",
                    ),
                    (
                        *event.coordinates(),
                        endpoint.relation_kind,
                        endpoint.target_json,
                        endpoint.clock_json,
                        PROV,
                        4,
                    ),
                )
            )
        )
    if reverse:
        for rows in data.values():
            rows.reverse()
    hostile = replace(package, context=data, digest_sha256=None)
    if prime_replay:
        receive(b, hostile, (r1,), selection=scope(include_context=False))
    before = authorities(b)
    with pytest.raises(UnsupportedResourceStage):
        receive(b, hostile, (r1,), request=RequestIdentity(str(uuid4()), str(uuid4())))
    assert authorities(b) == before
    assert not (b / "p1-recovery-stop.json").exists()


def test_real_wire_parser_rejects_unrecognized_nested_operations_before_effects(
    tmp_path,
):
    a, b = tmp_path / "a", tmp_path / "b"
    r1, _, _, _ = fixture(a)
    catalog(b)
    raw = ExchangeService(a).export_package(selection=scope()).to_dict()
    raw["context"]["units"] = [
        {"operations": [{"relation_kind": "transfer_event_report"}]}
    ]
    digest_scope = {key: value for key, value in raw.items() if key != "digest_sha256"}
    raw["digest_sha256"] = hashlib.sha256(
        json.dumps(
            digest_scope,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    before = authorities(b)
    # V4 has no nested operation extension. The real decoder must refuse it;
    # the normalized preflight is not advertised as a new wire parser.
    with pytest.raises(ExchangeError):
        receive(b, raw, (r1,))
    assert authorities(b) == before


def test_unknown_ordered_wire_and_opaque_transfer_text_remain_supported(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    r1, _, _, _ = fixture(a)
    catalog(b)
    owner = ResourceKey.from_native(S, "vendor.unknown", [])
    members = tuple(
        ResourceKey.from_native(S, "vendor.member", native)
        for native in (["B", []], ["A", []])
    )
    relation = ResourceRelation(
        owner,
        "transfer_event_report ",
        members,
        PROV,
        canonical({"units": [{"relation_kind": "transfer_event_report"}]}),
        7,
    )
    with Context.transaction(a) as ctx:
        ctx.provider(S, "synthetic")
        for key in (owner, *members):
            ctx.resource(key)
        ctx.relation(relation)
    package = ExchangeService(a).export_package(selection=scope())
    receive(b, package, (r1,))
    with Context.snapshot(b) as ctx:
        assert ctx.relations(owner, relation.relation_kind) == (relation,)
        assert ctx.identification(owner) == RI.unscoped(owner)
    onward = ExchangeService(b).export_package(selection=scope())
    assert package.context["resource_relations"] == onward.context["resource_relations"]


@pytest.mark.parametrize("poison", ["report", "endpoint"])
@pytest.mark.parametrize("route", ["context", "query", "export", "search"])
def test_matching_schema_poison_stops_before_ordinary_exposure(tmp_path, poison, route):
    catalog(tmp_path)
    namespace = ResourceKey.from_native(S, "issue", "7")
    key = ResourceKey.timeline_event(namespace, "E")
    with Context.transaction(tmp_path) as ctx:
        ctx.provider(S, "synthetic")
        ctx.resource(
            key, identification=RI.scoped(key, namespace, "timeline_event", "E")
        )
    db = p1_schema.connect(tmp_path / "context.sqlite3", "context")
    trigger = (
        "i2_transfer_report_stage_fence"
        if poison == "report"
        else "i2_transfer_stage_fence"
    )
    ddl = db.execute(
        "SELECT sql FROM sqlite_schema WHERE name=?", (trigger,)
    ).fetchone()[0]
    db.execute("DROP TRIGGER " + trigger)
    if poison == "report":
        db.execute(
            "INSERT INTO resource_relations VALUES(?,?,?,?,?,?,?,?)",
            (*key.coordinates(), "transfer_event_report", "[]", PROV, "{}", 2),
        )
    else:
        db.execute(
            "INSERT INTO resource_repository_relations(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,target_json,clock_json,provenance_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)",
            (
                *key.coordinates(),
                "transfer_from_repository",
                "null",
                '{"at_us":1,"domain":"provider"}',
                PROV,
                2,
            ),
        )
    db.execute(ddl)
    before = snapshot(db)
    with pytest.raises(StoredContextInvariantError):
        validate_stored_context_relations(db)
    db.close()
    with pytest.raises(ValueError, match="AUTHORITATIVE_CORRUPTION"):
        if route == "context":
            with Context.snapshot(tmp_path) as ctx:
                ctx.resources()
        elif route == "query":
            ProductionQueryService(tmp_path).get_context_resource(key)
        elif route == "export":
            ExchangeService(tmp_path).export_package(selection=scope())
        else:
            ProductionQueryService(tmp_path).search(
                SearchQuery("Transfer", projection_kinds=("context_text",))
            )
    assert (tmp_path / "p1-recovery-stop.json").exists()
    db = p1_schema.connect(tmp_path / "context.sqlite3", "context")
    assert snapshot(db) == before
    db.close()
