"""Isolated C-prime schema constructor and bounded row-local predicates.

No UDF queries a database. No production code is modified or runtime checks faked.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.domain.p1_context import canonical, validate_mapping_clock

ROOT = Path(__file__).resolve().parent
TYPED = {
    "review": {"pull_request"},
    "document": {"pull_request"},
    "thread": {"pull_request", "review"},
    "comment": {"pull_request", "issue", "review", "thread"},
}
ROLES = {"transfer_from_repository", "transfer_to_repository"}


def parse(raw):
    if type(raw) is not str or len(raw.encode("utf-8")) > 262144:
        raise ValueError("bounded canonical text required")
    # Check depth before parsing, counting only unquoted container delimiters.
    depth = 0
    quoted = False
    escaped = False
    for ch in raw:
        if quoted:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
        elif ch == '"':
            quoted = True
        elif ch in "[{":
            depth += 1
            if depth > 40:
                raise ValueError("JSON depth limit")
        elif ch in "]}":
            depth -= 1
    result = json.loads(raw)
    if canonical(result) != raw:
        raise ValueError("noncanonical JSON")
    return result


def identity(raw):
    value = parse(raw)
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > 4096 or depth > 32:
            raise ValueError("identity limit")
        if type(item) is str:
            item.encode("utf-8")
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        else:
            raise ValueError("only strings/arrays are identity values")
    return value


def predicate(fn):
    def wrapped(*args):
        try:
            fn(*args)
            return 1
        except (
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            OverflowError,
            RecursionError,
            UnicodeError,
        ):
            return 0

    return wrapped


def resource(kind, raw, namespace_kind, namespace_id, document_kind, document_id):
    value = identity(raw)
    if type(kind) is not str or not kind:
        raise ValueError("kind required")
    if kind == "document" and all(
        x is None for x in (namespace_kind, namespace_id, document_kind)
    ):
        # Explicit complete Provider-global Document form, not an opaque fallback.
        # Requiring the native ID also rejects an all-omitted typed payload.
        identity(document_id)
        if document_id != raw:
            raise ValueError("independent Document native identity")
    elif kind in TYPED:
        if (
            namespace_kind not in TYPED[kind]
            or type(document_kind) is not str
            or not document_kind
        ):
            raise ValueError("known document contract")
        identity(namespace_id)
        doc = identity(document_id)
        # Exactly one unreleased encoding: canonical namespace ID TEXT component.
        if value != [namespace_kind, namespace_id, document_kind, doc]:
            raise ValueError("document coordinates")
    elif any(
        x is not None
        for x in (namespace_kind, namespace_id, document_kind, document_id)
    ):
        raise ValueError("unknown/non-document cannot claim typed columns")


def document_input(
    native_contract, raw, *, namespace_id=None, document_kind=None, document_id=None
):
    """Validate an adapter-selected native contract, never infer/fallback by shape.

    Selection must come from the genuine Provider identification contract, not
    from an input failure or a sender's unverified claim. SQL cannot establish
    that external fact. The selector is not stored or added to Resource identity.
    """
    if native_contract == "provider_global":
        if any(x is not None for x in (namespace_id, document_kind, document_id)):
            raise ValueError("global contract cannot discard scoped coordinates")
        extra = (None, None, None, raw)
    elif native_contract == "pr_scoped":
        extra = ("pull_request", namespace_id, document_kind, document_id)
    else:
        raise ValueError("explicit supported native Document contract required")
    resource("document", raw, *extra)
    return extra


def member(raw):
    if type(raw) is not list or len(raw) != 3:
        raise ValueError("full ResourceKey triple")
    service, kind, ident = raw
    if not p1_schema.uuid4(service) or type(kind) is not str or not kind:
        raise ValueError("member key")
    identity(ident)


def parent(kind, service, members, scope):
    values = parse(members)
    s = parse(scope)
    if type(values) is not list or len(values) != 1:
        raise ValueError("singleton Parent")
    member(values[0])
    if type(s) is not dict or set(s) != {"clock", "document_kind", "state"}:
        raise ValueError("complete Parent scope")
    independent = kind == "document" and s["document_kind"] is None
    if (
        values[0][0] != service
        or kind not in TYPED
        or (not independent and values[0][1] not in TYPED[kind])
    ):
        raise ValueError("typed Parent kind/namespace")
    validate_mapping_clock(canonical(s["clock"]))
    if s["state"] != "complete" or (
        not independent
        and (type(s["document_kind"]) is not str or not s["document_kind"])
    ):
        raise ValueError("Parent scope values")


def event(service, kind, members, scope):
    values = parse(members)
    s = parse(scope)
    if kind != "comment" or type(values) is not list:
        raise ValueError("event owner")
    for value in values:
        member(value)
        if value[0] != service or value[1] != "repository":
            raise ValueError("event provider endpoint")
    if len({canonical(v) for v in values}) != len(values):
        raise ValueError("duplicate member")
    fields = {
        "clock",
        "event_type",
        "from_provider_repository_id",
        "to_provider_repository_id",
        "provided_roles",
        "parent_members_json",
        "parent_scope_json",
        "parent_provenance_json",
        "endpoints",
    }
    if type(s) is not dict or set(s) != fields:
        raise ValueError("event scope")
    validate_mapping_clock(canonical(s["clock"]))
    if type(s["event_type"]) is not str or not s["event_type"]:
        raise ValueError("event type syntax")
    parent(kind, service, s["parent_members_json"], s["parent_scope_json"])
    ps = parse(s["parent_scope_json"])
    pm = parse(s["parent_members_json"])
    if ps["document_kind"] != "timeline_event" or pm[0][1] != "issue":
        raise ValueError("typed timeline Parent")
    pp = parse(s["parent_provenance_json"])
    if (
        type(pp) is not dict
        or type(pp.get("source")) is not str
        or not pp["source"]
        or pp.get("evidence") is None
    ):
        raise ValueError("full Parent report provenance")
    endpoints = s["endpoints"]
    if type(endpoints) is not list:
        raise ValueError("endpoints")
    seen = set()
    for endpoint in endpoints:
        if type(endpoint) is not list or len(endpoint) != 2 or endpoint[0] not in ROLES:
            raise ValueError("endpoint")
        target = parse(endpoint[1])
        if target is not None and not p1_schema.uuid4(target):
            raise ValueError("target")
        key = tuple(endpoint)
        if key in seen:
            raise ValueError("duplicate endpoint")
        seen.add(key)
    expected_members = []
    supplied_roles = set(e[0] for e in endpoints)
    for prefix in ("from", "to"):
        ident = s[f"{prefix}_provider_repository_id"]
        if ident is not None:
            identity(ident)
            if [f"transfer_{prefix}_repository", "null"] in endpoints:
                raise ValueError(
                    "explicit null and unresolved Provider endpoint conflict"
                )
            supplied_roles.add(f"transfer_{prefix}_repository")
            coord = [service, "repository", ident]
            if coord not in expected_members:
                expected_members.append(coord)
    if (
        values != expected_members
        or s["provided_roles"] != sorted(supplied_roles)
        or not supplied_roles
    ):
        raise ValueError("coherent endpoint membership/roles")


def relation(kind, service, resource_kind, members, scope):
    values = parse(members)
    if type(values) is not list:
        raise ValueError("relation members array")
    for value in values:
        member(value)
    if kind == "parent":
        parent(resource_kind, service, members, scope)
    elif kind == "transfer_event_report":
        event(service, resource_kind, members, scope)


def projection(raw, *path):
    try:
        value = parse(raw)
        for key in path:
            value = value[key]
        return (
            value
            if isinstance(value, (str, int)) or value is None
            else canonical(value)
        )
    except (ValueError, TypeError, KeyError, IndexError):
        return None


def endpoint(role, target, scope, clock):
    s = parse(scope)
    if s["clock"] != parse(clock) or [role, target] not in s["endpoints"]:
        raise ValueError("endpoint absent from this complete report")


def register(db):
    p1_schema.register_functions(db)
    for name, arity, fn in (
        ("cp_identity", 1, identity),
        ("cp_resource", 6, resource),
        ("cp_relation", 5, relation),
        ("cp_endpoint", 4, endpoint),
    ):
        db.create_function(name, arity, predicate(fn), deterministic=True)
    db.create_function("cp_get", -1, projection, deterministic=True)


def sql():
    baseline = p1_schema.compose("context")
    # Exact section anchors fail closed if frozen inputs differ.
    start = baseline.index("CREATE TABLE resources(")
    end = baseline.index("CREATE TABLE text_bodies(", start)
    baseline = (
        baseline[:start] + (ROOT / "resources.sql").read_text() + "\n" + baseline[end:]
    )
    start = baseline.index("CREATE TABLE resource_relations(")
    end = baseline.index("CREATE TABLE collections(", start)
    baseline = (
        baseline[:start] + (ROOT / "relations.sql").read_text() + "\n" + baseline[end:]
    )
    # Retain all baseline six-role checks, real Repository FK and maintenance triggers.
    start = baseline.index(
        " event_parent_resource_kind TEXT GENERATED",
        baseline.index("CREATE TABLE resource_repository_relations("),
    )
    end = baseline.index(" CHECK(typeof(source_clock_us)", start)
    baseline = (
        baseline[:start] + (ROOT / "transfer-columns.sql").read_text() + baseline[end:]
    )
    old = "FOREIGN KEY(service_instance_uuidv4,resource_kind,provider_resource_id,event_document_kind,event_parent_resource_kind) REFERENCES resources(service_instance_uuidv4,resource_kind,provider_resource_id,document_kind,parent_resource_kind)"
    assert baseline.count(old) == 1
    baseline = baseline.replace(
        old, (ROOT / "transfer-constraints.sql").read_text().strip()
    )
    return baseline + "\n" + (ROOT / "guards.sql").read_text()


def connect(path=":memory:", *, fresh=True):
    if sqlite3.sqlite_version_info < p1_schema.MIN_SQLITE:
        raise RuntimeError("real SQLite >=3.51.3 required")
    db = sqlite3.connect(path, isolation_level=None, cached_statements=0)
    register(db)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA recursive_triggers=ON")
    db.execute("PRAGMA synchronous=EXTRA")
    assert db.execute("PRAGMA foreign_keys").fetchone() == (1,)
    assert db.execute("PRAGMA recursive_triggers").fetchone() == (1,)
    if fresh:
        db.executescript(sql())
    return db
