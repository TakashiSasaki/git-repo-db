import json
import sqlite3
import sys

from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.production_context import (
    CollectionObservation,
    ResourceRelation,
    SourceInventory,
)
from repo_catalog.domain.resource_identification import ResourceIdentification
from repo_catalog.domain.resource_identity import encode_identity, parse_identity

S = "11111111-1111-4111-8111-111111111111"
checks = []


def check(name, f):
    try:
        assert f()
        checks.append({"name": name, "status": "pass"})
    except Exception as e:
        checks.append({"name": name, "status": "fail", "exception": repr(e)})


def rejects(value):
    try:
        parse_identity(value)
    except (ValueError, TypeError):
        return True
    return False


check(
    "meaningful empties distinct",
    lambda: len({encode_identity(x) for x in ["", [], [""], [[]]]}) == 4,
)
check("unicode canonical ASCII", lambda: encode_identity("é") == '"\\u00e9"')
for value in [' "D" ', '"\\u0044"', '"é"', "7", "true", "null", "[1]", "{}"]:
    check("reject ID " + repr(value), lambda value=value: rejects(value))
D = ResourceKey(S, "document", encode_identity("D"))
check(
    "global document four columns",
    lambda: (
        ResourceIdentification.global_document(D).columns == (None, None, None, '"D"')
    ),
)
I7 = ResourceKey(S, "issue", encode_identity("I7"))
E = ResourceKey(
    S,
    "comment",
    encode_identity(["issue", I7.provider_resource_id, "timeline_event", "E"]),
)
check(
    "scoped explicit declaration canonical profile",
    lambda: (
        ResourceIdentification.scoped(E, I7, "timeline_event", "E").columns
        == ("issue", '"I7"', "timeline_event", '"E"')
    ),
)
X = ResourceKey(S, "x-widget", encode_identity(["p", []]))
p = '{"evidence":"C","source":"fixture"}'
a = ResourceRelation(D, "links", (E, X), p, "{}", 200)
b = ResourceRelation(D, "links", (X, E), p, "{}", 200)
check("generic members retain order", lambda: a.members_json != b.members_json)
c = CollectionObservation(D, "related", p, "{}", 200, "complete", ())
d = CollectionObservation(D, "related", p, "{}", 201, "partial", ())
check(
    "empty complete and empty partial terminals distinct",
    lambda: c.terminal != d.terminal,
)
R1 = "22222222-2222-4222-8222-222222222222"
R2 = "33333333-3333-4333-8333-333333333333"
inv1 = SourceInventory(S, "{}", 200, "partial", False, (R1, R2), p)
inv2 = SourceInventory(S, "{}", 200, "partial", False, (R2, R1), p)
check(
    "source inventory sorted set order", lambda: inv1.members_json == inv2.members_json
)
out = {
    "scope": "existing domain codec/types only; no v5 product behavior tested",
    "python": sys.version,
    "executable": sys.executable,
    "sqlite": sqlite3.sqlite_version,
    "sqlite_source_id": sqlite3.connect(":memory:")
    .execute("select sqlite_source_id()")
    .fetchone()[0],
    "checks": checks,
}
print(json.dumps(out, indent=2))
sys.exit(any(c["status"] != "pass" for c in checks))
