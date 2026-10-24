"""Independently reproduce reviewer finding and verify all scanner defense vectors.

Measures:
1. Max queue length in charge_input (pending)
2. Max snapshot length (children)
3. Cumulative and selection work charges
4. Post-traversal mutation double-charging prevention
5. User callback exception containment (iter, dict keys/values, dataclass access)
6. Dataclass member capacity pre-reservation
7. Store relation behavior under Context.owned_transaction
"""

import argparse
import json
import sqlite3
import sys
import tempfile
from dataclasses import dataclass, make_dataclass
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
from tests.support.context_admission import (
    FixturePolicy,
    fixture_context,
    fixture_service,
)

SERVICE = "11111111-1111-4111-8111-111111111111"


class DetailedObserver:
    def __init__(self, target_filename: str):
        self.target_filename = str(Path(target_filename).resolve())
        self.queue_lengths = []
        self.snapshot_lengths = []
        self.members_lengths = []
        self.max_queue_len = 0
        self.max_snapshot_len = 0
        self.max_members_len = 0

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
            members = frame.f_locals.get("members")
            if isinstance(members, list):
                m_len = len(members)
                self.members_lengths.append(m_len)
                if m_len > self.max_members_len:
                    self.max_members_len = m_len
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


# Case 7: Dataclass capacity pre-reservation
@dataclass
class ProbeDataclass:
    f1: int
    f2: str
    f3: list
    f4: dict
    f5: int
    f6: int


Fields1000 = make_dataclass("Fields1000", [(f"f_{i}", int) for i in range(1000)])


class TrackedFields1000(Fields1000):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.accesses = 0

    def __getattribute__(self, name):
        if name.startswith("f_"):
            object.__setattr__(
                self, "accesses", object.__getattribute__(self, "accesses") + 1
            )
        return super().__getattribute__(name)


# Case 8: Broken callbacks
class BrokenIter(list):
    def __iter__(self):
        yield 1
        raise RuntimeError("iteration error")


class BrokenValuesDict(dict):
    def values(self):
        raise ValueError("values retrieval error")


class BrokenKeysDict(dict):
    def keys(self):
        raise KeyError("keys retrieval error")


@dataclass
class BrokenAttrDataclass:
    field_a: int = 1

    def __getattribute__(self, name):
        if name == "field_a":
            raise RuntimeError("attribute access error")
        return super().__getattribute__(name)


# Case 9: Post-traversal mutating list and dict (double charge verification)
class MutatingList(list):
    def __iter__(self):
        it = super().__iter__()
        for x in it:
            yield x
        self.append(999)


class MutatingDict(dict):
    def values(self):
        return list(super().values())

    def keys(self):
        ks = list(super().keys())
        self["mutated"] = 999
        return ks


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

    # Case 7 - Dataclass capacity pre-reservation
    obs7 = DetailedObserver(target_file)
    ctx7 = fixture_context(
        service,
        selection=AdmissionSelection(all_selected=True, max_work=100),
        budget=AdmissionBudget(work_limit=6),
    )
    dc7 = ProbeDataclass(1, "", [], {}, 5, 6)
    res7 = None
    try:
        obs7.run(lambda: service.charge_input(ctx7, dc7))
    except AdmissionRefused as e:
        res7 = e.code
    results["case_7_dataclass_capacity"] = {
        "refusal_code": res7,
        "max_queue_len": obs7.max_queue_len,
        "used_work": ctx7.budget.used_work,
    }

    # Case 7b - Dataclass selection budget with 1000 fields
    obs7b = DetailedObserver(target_file)
    ctx7b = fixture_context(
        service,
        selection=AdmissionSelection(all_selected=True, max_work=7),
        budget=AdmissionBudget(work_limit=10000),
    )
    dc7b = TrackedFields1000(*range(1000))
    res7b = None
    try:
        obs7b.run(lambda: service.charge_input(ctx7b, dc7b))
    except AdmissionRefused as e:
        res7b = e.code
    results["case_7b_dataclass_selection_1000_fields"] = {
        "refusal_code": res7b,
        "max_queue_len": obs7b.max_queue_len,
        "max_members_len": obs7b.max_members_len,
        "used_work": ctx7b.budget.used_work,
        "attribute_accesses": dc7b.accesses,
    }

    # Case 8 - Callback exception containment
    ctx8_iter = fixture_context(service, budget=AdmissionBudget(work_limit=100))
    res8_iter = None
    try:
        service.charge_input(ctx8_iter, BrokenIter([1, 2]))
    except AdmissionRefused as e:
        res8_iter = e.code
    except Exception as e:
        res8_iter = f"UNHANDLED_{type(e).__name__}"

    ctx8_vals = fixture_context(service, budget=AdmissionBudget(work_limit=100))
    res8_vals = None
    try:
        service.charge_input(ctx8_vals, BrokenValuesDict({"k": 1}))
    except AdmissionRefused as e:
        res8_vals = e.code
    except Exception as e:
        res8_vals = f"UNHANDLED_{type(e).__name__}"

    ctx8_keys = fixture_context(service, budget=AdmissionBudget(work_limit=100))
    res8_keys = None
    try:
        service.charge_input(ctx8_keys, BrokenKeysDict({"k": 1}))
    except AdmissionRefused as e:
        res8_keys = e.code
    except Exception as e:
        res8_keys = f"UNHANDLED_{type(e).__name__}"

    ctx8_attr = fixture_context(service, budget=AdmissionBudget(work_limit=100))
    res8_attr = None
    try:
        service.charge_input(ctx8_attr, BrokenAttrDataclass())
    except AdmissionRefused as e:
        res8_attr = e.code
    except Exception as e:
        res8_attr = f"UNHANDLED_{type(e).__name__}"

    results["case_8_callback_containment"] = {
        "broken_iter_code": res8_iter,
        "broken_iter_used_work": ctx8_iter.budget.used_work,
        "broken_values_code": res8_vals,
        "broken_values_used_work": ctx8_vals.budget.used_work,
        "broken_keys_code": res8_keys,
        "broken_keys_used_work": ctx8_keys.budget.used_work,
        "broken_attr_code": res8_attr,
        "broken_attr_used_work": ctx8_attr.budget.used_work,
    }

    # Case 9 - Post-traversal mutation double-charge prevention
    ctx9_list = fixture_context(
        service,
        selection=AdmissionSelection(all_selected=True, max_work=100),
        budget=AdmissionBudget(work_limit=100),
    )
    res9_list = None
    try:
        service.charge_input(ctx9_list, MutatingList([1, 2]))
    except AdmissionRefused as e:
        res9_list = e.code

    ctx9_dict = fixture_context(
        service,
        selection=AdmissionSelection(all_selected=True, max_work=100),
        budget=AdmissionBudget(work_limit=100),
    )
    res9_dict = None
    try:
        service.charge_input(ctx9_dict, MutatingDict({"a": 1, "b": 2}))
    except AdmissionRefused as e:
        res9_dict = e.code

    results["case_9_single_charge_mutation"] = {
        "list_refusal_code": res9_list,
        "list_used_work": ctx9_list.budget.used_work,
        "dict_refusal_code": res9_dict,
        "dict_used_work": ctx9_dict.budget.used_work,
    }

    # Real store relation case
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
