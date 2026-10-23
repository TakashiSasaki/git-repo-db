"""Real normal Context relation entry: both Transfer fences stay installed."""

import argparse
import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path

from study import SERVICE, DenyPolicy, observe

from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import (
    AdmissionBudget,
    AdmissionSelection,
    ContextAdmissionService,
)
from repo_catalog.domain.p1_context import ResourceKey, canonical
from repo_catalog.domain.production_context import ResourceRelation
from repo_catalog.domain.resource_stage import has_transfer_fence


def run(n, limit, remaining, selected):
    db = sqlite3.connect(":memory:", isolation_level=None)
    p1_schema.register_functions(db)
    p1_schema.configure(db)
    db.executescript(p1_schema.compose("context"))
    db.execute(
        "INSERT INTO store_identity VALUES('context',?,?)",
        (
            "9ebbe38a-f937-40e6-a99c-701835ebcf10",
            "aad25448-03eb-4f83-a75e-cb7055fd33be",
        ),
    )
    p1_schema.validate(db, "context")
    assert has_transfer_fence(db)
    owner = ResourceKey.from_native(SERVICE, "issue", "owner")
    members = tuple(ResourceKey.from_native(SERVICE, "issue", str(i)) for i in range(n))
    report = ResourceRelation(
        owner,
        "x-links",
        members,
        canonical({"source": "review", "evidence": "synthetic"}),
        "{}",
        1,
    )
    policy = DenyPolicy()
    service = ContextAdmissionService(policy, lambda token: "scanner-review")
    budget = AdmissionBudget(work_limit=limit)
    issued = service.context(
        "synthetic",
        "provider_intake",
        AdmissionSelection(
            resource_keys=frozenset({owner, *members}),
            repository_uuidv4s=frozenset(),
            source_uuidv4s=frozenset(),
            object_oids=frozenset(),
            max_work=selected,
        ),
        budget,
    )
    budget.charge(work=limit - remaining)
    before = db.execute("select count(*) from resource_relations").fetchone()[0]
    sql = []
    db.set_trace_callback(sql.append)
    with tempfile.TemporaryDirectory(prefix="pr155-scanner-") as directory:

        def action():
            with Context.owned_transaction(
                db, Path(directory), authorization=service, admission=issued
            ) as context:
                return context.relation(report, admission=issued)

        record = observe(action, budget=budget)
    db.set_trace_callback(None)
    after = db.execute("select count(*) from resource_relations").fetchone()[0]
    record.update(
        input_children=n,
        input_json_bytes=len(report.members_json.encode()),
        work_limit=limit,
        prior_work=limit - remaining,
        remaining_work=remaining,
        selection_work_limit=selected,
        policy_calls=policy.calls,
        sql=sql,
        rows_before=before,
        rows_after=after,
        in_transaction=db.in_transaction,
        exact_transfer_fences_preserved=has_transfer_fence(db),
        adapter_path=__import__(Context.__module__, fromlist=["__file__"]).__file__,
    )
    db.close()
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    records = [
        run(n, 10000, remaining, selected)
        for n, remaining, selected in (
            (16, 8, 10000),
            (1000, 8, 10000),
            (1000, 0, 10000),
            (1000, 10000, 7),
        )
    ]
    record = {
        "cases": records,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    Path(args.output).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            [
                {
                    "children": x["input_children"],
                    "remaining": x["remaining_work"],
                    "selection": x["selection_work_limit"],
                    "outcome": x["outcome"],
                    "queue_max": x["maxima"].get("charge_input:queue_length"),
                    "used_work": x["used_work"],
                    "policy_calls": x["policy_calls"],
                    "rows_after": x["rows_after"],
                }
                for x in records
            ]
        )
    )


if __name__ == "__main__":
    main()
