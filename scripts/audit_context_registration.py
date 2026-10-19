"""Check A3's finite registration vocabulary and every superseded P1 JSON route.

This is a source/contract audit, not a real-data extractor or approval mechanism.
The prior P1 column ledger remains a baseline route record; A3 explicitly overrides
its 25 paths into generic registration JSON. No old input is silently discarded.
"""

from __future__ import annotations

import json
from pathlib import Path

from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.domain.context_registration import EXCHANGE_REGISTRATIONS, FIELD_TYPES

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/implementation/access-a3-routing.json"
P1 = ROOT / "docs/implementation/p1-disposition.json"
TABLE_ROLES = {
    "providers": "provider",
    "repository_context": "repository",
    "sources": "source",
    "source_repositories": "membership",
}


def check() -> tuple[int, int]:
    p1 = json.loads(P1.read_text())
    ledger = json.loads(LEDGER.read_text())
    if p1.get("registration_routing_override") != LEDGER.relative_to(ROOT).as_posix():
        raise ValueError("P1 ledger must explicitly point to its current A3 override")
    if ledger["field_types"] != FIELD_TYPES:
        raise ValueError(
            "Registration domain vocabulary differs from the routing ledger"
        )
    actual = {}
    for table, row in p1["legacy_tables"].items():
        for column, route in row["columns"].items():
            for target in route.get("targets", []):
                if (
                    target["store"] == "context"
                    and target["table"] in TABLE_ROLES
                    and set(target["columns"])
                    & {"configuration_json", "attributes_json"}
                ):
                    actual[f"{table}.{column}"] = target["table"]
    routes = ledger["p1_route_overrides"]
    if set(actual) != set(routes):
        raise ValueError(
            "Missing or extra A3 override for a baseline registration JSON route"
        )
    for source, table in actual.items():
        row = routes[source]
        if row["p1_target"] != table or not row["disposition"] or not row["rule"]:
            raise ValueError("Incomplete authored registration disposition")
    sql = p1_schema.compose("context")
    for table, kind in TABLE_ROLES.items():
        column = "attributes_json" if kind == "membership" else "configuration_json"
        expected = f"p1_registration_json('{kind}',{column})"
        if expected not in sql:
            raise ValueError(f"Missing physical registration CHECK for {kind}")
    if set(EXCHANGE_REGISTRATIONS) != {
        "providers",
        "repositories",
        "sources",
        "source_repositories",
    }:
        raise ValueError("Exchange registration routing set differs")
    return len(routes), sum(len(v) for v in FIELD_TYPES.values())


if __name__ == "__main__":
    routes, fields = check()
    print(
        f"A3 registration routing: {routes} legacy JSON routes; {fields} typed fields; no omitted route"
    )
