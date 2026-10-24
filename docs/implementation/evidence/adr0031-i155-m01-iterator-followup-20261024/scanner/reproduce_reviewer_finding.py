"""Independently reproduce GitHub Codex review finding (discussion_r4366012662) on PR #158.

Measures:
1. Max queue length in charge_input (pending)
2. Max snapshot length (children)
3. Cumulative and selection work charges
4. Store relation behavior under Context.owned_transaction
"""

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain import context_admission
from repo_catalog.domain.context_admission import (
    AdmissionBudget,
    AdmissionRefused,
    AdmissionSelection,
    ContextAdmissionService,
    DependencySet,
)
from repo_catalog.domain.p1_context import ResourceKey, canonical
from repo_catalog.domain.production_context import ResourceRelation
from repo_catalog.domain.resource_stage import has_transfer_fence
from tests.support.context_admission import FixturePolicy, fixture_context, fixture_service

SERVICE = "11111111-1111-4111-8111-111111111111"


class DetailedObserver:
    def __init__(self, target_filename: str):
        self.target_filename = str(Path(target_filename).resolve())
        self.queue_lengths = []
        self.snapshot_lengths = []
        self.max_queue_len = 0
        self.max_snapshot_len = 0

    def trace(self, frame, event, arg):
        if str(Path(frame.f_code.co_filename).resolve()) == self.target_filename:
            pending = frame.f_locals.get("pending")
            if isinstance(pending, list):
                length = len(pending)
                self.queue_lengths.append(length)
                if length > self.max_queue_len:
                    self.max_queue_len = length
            children = frame.f_locals.get("children")
            if isinstance(children, (list, tuple)):
                c_len = len(children)
                self.snapshot_lengths.append(c_len)
                if c_len > self.max_snapshot_len:
                    self.max_snapshot_len = c_len
        return self.trace

    def run(self, fn):
        old_trace = sys.gettrace()
        sys.settrace(self.trace)
        try:
            return fn()
        finally:
            sys.settrace(old_trace)


# Case 1: A list subclass whose __iter__ mutates the source by appending children.
class Case1List(list):
    def __iter__(self):
        for i in range(1000):
            self.append(i)
        return super().__iter__()


# Case 2: A declared small length that changes during iteration.
class Case2List(list):
    def __iter__(self):
        for i in range(500):
            self.append(i)
            yield i


# Case 3: Materialized snapshot and mutated original have the same final length.
class Case3List(list):
    def __iter__(self):
        for i in range(1000):
            self.append(i)
        return super().__iter__()


# Case 4: A misleading or dynamically changing __len__.
class Case4List(list):
    def __init__(self, *args):
        super().__init__(*args)
        self.calls = 0

    def __len__(self):
        self.calls += 1
        return 2 if self.calls == 1 else 1000

    def __iter__(self):
        yield from range(1000)


# Case 5: An input that exceeds remaining work during snapshot creation, before pending.extend.
class Case5List(list):
    def __iter__(self):
        yield from range(1000)


# Real store relation case: Armed mutating list for ResourceRelation
class ArmedMutatingList(list):
    def __init__(self, *args):
        super().__init__(*args)
        self.armed = False

    def __iter__(self):
        if self.armed:
            for i in range(1000):
                self.append(ResourceKey.from_native(SERVICE, "issue", f"extra_{i}"))
        return super().__iter__()


def run_all():
    target_file = context_admission.__file__
    service, _ = fixture_service(DependencySet())
    results = {}

    # Case 1
    obs1 = DetailedObserver(target_file)
    ctx1 = fixture_context(
        service,
        selection=AdmissionSelection(all_selected=True, max_work=3),
        budget=AdmissionBudget(work_limit=10000),
    )
    c1 = Case1List([1, 2])
    res1 = None
    try:
        obs1.run(lambda: service.charge_input(ctx1, c1))
    except AdmissionRefused as e:
        res1 = e.code
    results["case_1_appending_list"] = {
        "refusal_code": res1,
        "max_queue_len": obs1.max_queue_len,
        "max_snapshot_len": obs1.max_snapshot_len,
        "used_work": ctx1.budget.used_work,
        "final_input_len": len(c1),
    }

    # Case 2
    obs2 = DetailedObserver(target_file)
    ctx2 = fixture_context(
        service,
        selection=AdmissionSelection(all_selected=True, max_work=3),
        budget=AdmissionBudget(work_limit=10000),
    )
    c2 = Case2List([1, 2])
    res2 = None
    try:
        obs2.run(lambda: service.charge_input(ctx2, c2))
    except AdmissionRefused as e:
        res2 = e.code
    results["case_2_changing_len"] = {
        "refusal_code": res2,
        "max_queue_len": obs2.max_queue_len,
        "max_snapshot_len": obs2.max_snapshot_len,
        "used_work": ctx2.budget.used_work,
        "final_input_len": len(c2),
    }

    # Case 3
    obs3 = DetailedObserver(target_file)
    ctx3 = fixture_context(
        service,
        selection=AdmissionSelection(all_selected=True, max_work=3),
        budget=AdmissionBudget(work_limit=10000),
    )
    c3 = Case3List([1, 2])
    res3 = None
    try:
        obs3.run(lambda: service.charge_input(ctx3, c3))
    except AdmissionRefused as e:
        res3 = e.code
    results["case_3_same_final_length"] = {
        "refusal_code": res3,
        "max_queue_len": obs3.max_queue_len,
        "max_snapshot_len": obs3.max_snapshot_len,
        "used_work": ctx3.budget.used_work,
        "final_input_len": len(c3),
    }

    # Case 4
    obs4 = DetailedObserver(target_file)
    ctx4 = fixture_context(
        service,
        selection=AdmissionSelection(all_selected=True, max_work=3),
        budget=AdmissionBudget(work_limit=10000),
    )
    c4 = Case4List([1, 2])
    res4 = None
    try:
        obs4.run(lambda: service.charge_input(ctx4, c4))
    except AdmissionRefused as e:
        res4 = e.code
    results["case_4_deceptive_len"] = {
        "refusal_code": res4,
        "max_queue_len": obs4.max_queue_len,
        "max_snapshot_len": obs4.max_snapshot_len,
        "used_work": ctx4.budget.used_work,
    }

    # Case 5
    obs5 = DetailedObserver(target_file)
    ctx5 = fixture_context(
        service,
        selection=AdmissionSelection(all_selected=True, max_work=5),
        budget=AdmissionBudget(work_limit=10000),
    )
    c5 = Case5List([1, 2])
    res5 = None
    try:
        obs5.run(lambda: service.charge_input(ctx5, c5))
    except AdmissionRefused as e:
        res5 = e.code
    results["case_5_exceeds_during_snapshot"] = {
        "refusal_code": res5,
        "max_queue_len": obs5.max_queue_len,
        "max_snapshot_len": obs5.max_snapshot_len,
        "used_work": ctx5.budget.used_work,
    }

    # Case 6 - Positive exact boundary
    ctx6_list = fixture_context(
        service,
        selection=AdmissionSelection(all_selected=True, max_work=6),
        budget=AdmissionBudget(work_limit=6),
    )
    service.charge_input(ctx6_list, [1, 2, 3, 4, 5])

    ctx6_tuple = fixture_context(
        service,
        selection=AdmissionSelection(all_selected=True, max_work=6),
        budget=AdmissionBudget(work_limit=6),
    )
    service.charge_input(ctx6_tuple, (1, 2, 3, 4, 5))

    results["case_6_exact_boundaries"] = {
        "list_used_work": ctx6_list.budget.used_work,
        "tuple_used_work": ctx6_tuple.budget.used_work,
    }

    # Real store relation case
    db = sqlite3.connect(":memory:", isolation_level=None)
    p1_schema.register_functions(db)
    p1_schema.configure(db)
    db.executescript(p1_schema.compose("context"))
    db.execute(
        "INSERT INTO store_identity VALUES('context',?,?)",
        ("9ebbe38a-f937-40e6-a99c-701835ebcf10", "aad25448-03eb-4f83-a75e-cb7055fd33be"),
    )
    p1_schema.validate(db, "context")

    owner = ResourceKey.from_native(SERVICE, "issue", "owner")
    k0 = ResourceKey.from_native(SERVICE, "issue", "0")
    k1 = ResourceKey.from_native(SERVICE, "issue", "1")
    gl = ArmedMutatingList([k0, k1])

    report = ResourceRelation(
        owner,
        "x-links",
        gl,
        canonical({"source": "review", "evidence": "synthetic"}),
        "{}",
        1,
    )
    assert len(gl) == 2
    gl.armed = True

    policy = FixturePolicy(DependencySet(resources=frozenset({owner, k0, k1})))
    service_store = ContextAdmissionService(policy, lambda cred: "fixture-user")

    ctx_store = service_store.context(
        "fixture-credential",
        "provider_intake",
        AdmissionSelection(
            resource_keys=frozenset({owner, k0, k1}),
            repository_uuidv4s=frozenset(),
            source_uuidv4s=frozenset(),
            object_oids=frozenset(),
            max_work=25,
        ),
        AdmissionBudget(work_limit=10000),
    )

    obs_store = DetailedObserver(target_file)
    store_refusal = None
    with tempfile.TemporaryDirectory() as directory:
        def action():
            with Context.owned_transaction(
                db, Path(directory), authorization=service_store, admission=ctx_store
            ) as c:
                return c.relation(report, admission=ctx_store)
        try:
            obs_store.run(action)
        except AdmissionRefused as e:
            store_refusal = e.code

    results["real_store_relation"] = {
        "refusal_code": store_refusal,
        "max_queue_len": obs_store.max_queue_len,
        "max_snapshot_len": obs_store.max_snapshot_len,
        "used_work": ctx_store.budget.used_work,
        "final_gl_len": len(gl),
        "db_rows": db.execute("select count(*) from resource_relations").fetchone()[0],
        "transfer_fence": has_transfer_fence(db),
        "in_transaction": db.in_transaction,
    }
    db.close()

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", "-o", type=Path, default=None)
    args = parser.parse_args()

    results = run_all()
    out_json = json.dumps(results, indent=2) + "\n"
    if args.output:
        args.output.write_text(out_json)
    print(out_json)


if __name__ == "__main__":
    main()
