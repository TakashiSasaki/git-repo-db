"""Independent bounded scanner observations; no production replacement or patch.

Run with PYTHONPATH=<published checkout>/src for each published source, or with
an installed wheel interpreter from an external working directory.
"""

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from repo_catalog.domain import context_admission as admission
from repo_catalog.domain import context_dependencies as planner
from repo_catalog.domain import exchange
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.resource_identification import ResourceIdentification

SERVICE = "11111111-1111-4111-8111-111111111111"


class DenyPolicy:
    calls = 0

    def lease(self, *args):
        self.calls += 1
        raise AssertionError("scanner must refuse before policy or persistence")


def observe(action, budget=None, state=None):
    """Observe actual CPython frames/C list.extend calls, never replace a callee."""
    events = []
    calls = Counter()
    maxima = Counter()
    source_paths = {
        str(Path(m.__file__).resolve()) for m in (admission, planner, exchange)
    }
    last_lengths = {}
    failed = False

    def work(frame):
        if budget is not None:
            return budget.used_work
        if state is not None:
            return state[0]
        return frame.f_locals.get("work")

    def trace(frame, event, arg):
        nonlocal failed
        path = str(Path(frame.f_code.co_filename).resolve())
        if path not in source_paths:
            return None
        name = frame.f_code.co_name
        if event == "call":
            calls[name] += 1
        if event == "exception" and isinstance(arg[1], (admission.AdmissionRefused,)):
            failed = True
        if event in ("line", "return", "exception"):
            pending = frame.f_locals.get("pending")
            if type(pending) is list:
                length = len(pending)
                maxima[name + ":queue_length"] = max(
                    maxima[name + ":queue_length"], length
                )
                maxima[name + ":queue_shallow_bytes"] = max(
                    maxima[name + ":queue_shallow_bytes"], sys.getsizeof(pending)
                )
                key = id(frame)
                previous = last_lengths.get(key, 0)
                if length > previous and len(events) < 80:
                    events.append(
                        dict(
                            event="queue_growth",
                            function=name,
                            next_line=frame.f_lineno,
                            old=previous,
                            new=length,
                            used_work=work(frame),
                            after_refusal=failed,
                        )
                    )
                last_lengths[key] = length
        return trace

    def profile(frame, event, arg):
        if event == "call" and frame.f_code.co_name in (
            "loads",
            "parse_identity",
            "_parse_json",
        ):
            calls["parser:" + frame.f_code.co_name] += 1
        if event in ("c_call", "c_return") and getattr(arg, "__name__", "") == "extend":
            owner = getattr(arg, "__self__", None)
            if type(owner) is list and frame.f_code.co_filename in source_paths:
                calls["actual_list.extend:" + event] += 1
                if len(events) < 80:
                    events.append(
                        dict(
                            event=event + ":list.extend",
                            function=frame.f_code.co_name,
                            line=frame.f_lineno,
                            length=len(owner),
                            used_work=work(frame),
                            after_refusal=failed,
                            queue_shallow_bytes=sys.getsizeof(owner),
                            entry_tuple_shallow_bytes=sum(
                                sys.getsizeof(x) for x in owner if type(x) is tuple
                            ),
                        )
                    )

    sys.settrace(trace)
    sys.setprofile(profile)
    try:
        value = action()
        outcome = "returned"
        if isinstance(value, planner.ContextDependencyPlan):
            result = dict(
                work_units=value.work_units,
                emitted_units=value.emitted_units,
                section_counts={k: len(v) for k, v in value.context.items()},
                omission_reasons=[x.reason for x in value.omissions],
            )
        else:
            result = value
    except Exception as error:
        outcome = type(error).__name__
        result = dict(code=getattr(error, "code", None), message=str(error))
    finally:
        sys.settrace(None)
        sys.setprofile(None)
    return dict(
        outcome=outcome,
        result=result,
        calls=dict(calls),
        maxima=dict(maxima),
        events=events,
        used_work=budget.used_work if budget else state[0] if state else None,
    )


def run_admission(shape, n, limit, prior, selection_limit=None):
    policy = DenyPolicy()
    service = admission.ContextAdmissionService(
        policy, lambda credential: "scanner-review"
    )
    budget = admission.AdmissionBudget(work_limit=limit)
    selected = limit if selection_limit is None else selection_limit
    context = service.context(
        "synthetic",
        "provider_intake",
        admission.AdmissionSelection(
            resource_keys=frozenset(),
            repository_uuidv4s=frozenset(),
            source_uuidv4s=frozenset(),
            object_oids=frozenset(),
            max_work=selected,
        ),
        budget,
    )
    # Spend prior work through the real production method, rather than mutating usage.
    budget.charge(work=prior)
    values = [None] * n
    if shape == "dict":
        unit = {"k" + str(i): None for i in range(n)}
    elif shape == "typed_resources":
        unit = tuple(
            ResourceKey.from_native(SERVICE, "issue", str(i)) for i in range(n)
        )
    elif shape == "cycle":
        unit = []
        unit.append(unit)
    elif shape == "string":
        unit = "a" * n
    else:
        unit = values
    record = observe(lambda: service.charge_input(context, unit), budget=budget)
    record.update(
        shape=shape,
        input_children=n,
        input_json_bytes=(
            len(
                json.dumps(
                    [key.coordinates() for key in unit]
                    if shape == "typed_resources"
                    else unit
                )
            )
            if shape != "cycle"
            else None
        ),
        work_limit=limit,
        selection_work_limit=selected,
        prior_work=prior,
        policy_calls=policy.calls,
        persistence="not reached; scanner has no persistence",
    )
    return record


def run_bounded(label, value, limit, prior=0, root="generic"):
    state = [prior]
    reservations = []

    class Refused(Exception):
        pass

    def spend(amount=1):
        old = state[0]
        if amount > limit - old:
            state[0] += 1
            reservations.append(dict(before=old, amount=amount, accepted=False))
            raise Refused
        state[0] += amount
        if len(reservations) < 40:
            reservations.append(dict(before=old, amount=amount, accepted=True))

    record = observe(
        lambda: exchange._bounded_json(value, root=root, spend=spend), state=state
    )
    record.update(
        label=label, work_limit=limit, prior_work=prior, reservations=reservations
    )
    return record


def context_data():
    data = {key: [] for key in exchange.CONTEXT_SECTION_KEYS}
    data["providers"] = [
        dict(
            service_instance_uuidv4=SERVICE,
            provider_kind="synthetic-review",
            configuration_json="{}",
        )
    ]
    data["resources"] = [
        ResourceIdentification.unscoped(
            ResourceKey.from_native(SERVICE, "issue", str(i))
        ).to_wire()
        for i in range(2)
    ]
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    records = {
        "binding": {
            "python": sys.version,
            "executable": sys.executable,
            "sqlite": sqlite3.sqlite_version,
            "sqlite_source_id": sqlite3.connect(":memory:")
            .execute("select sqlite_source_id()")
            .fetchone()[0],
            "modules": {
                m.__name__: {
                    "path": m.__file__,
                    "sha256": hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest(),
                }
                for m in (admission, planner, exchange)
            },
        },
        "admission": [],
        "bounded_json": [],
        "planner": [],
    }
    for shape in ("list", "dict", "typed_resources"):
        for n, limit, prior, selected in (
            (16, 17, 16, None),
            (1000, 10000, 9999, None),
            (1000, 10000, 10000, None),
            (1000, 10000, 0, 0),
            (1000, 0, 0, None),
        ):
            records["admission"].append(run_admission(shape, n, limit, prior, selected))
    records["admission"].append(run_admission("cycle", 1, 100, 0))
    records["admission"].append(run_admission("string", 8192, 1, 0))
    for label, value, role in (
        ("list1000", [None] * 1000, "generic"),
        ("dict1000", {str(i): None for i in range(1000)}, "generic"),
        (
            "embedded_json",
            {"scope_json": "[" + ",".join(["null"] * 1000) + "]"},
            "generic",
        ),
        (
            "typed_identity",
            {
                "provider_resource_id": "[" + ",".join(['"a"'] * 1000) + "]",
                "resource_kind": "issue",
            },
            "row:resources",
        ),
    ):
        for limit, prior in ((0, 0), (1, 0), (17, 0), (1000, 1000), (100000, 0)):
            records["bounded_json"].append(
                run_bounded(label, value, limit, prior, role)
            )
    cycle = []
    cycle.append(cycle)
    records["bounded_json"].append(run_bounded("cycle", cycle, 1000))
    depth = None
    for _ in range(34):
        depth = [depth]
    records["bounded_json"].append(run_bounded("depth34", depth, 1000))
    data = context_data()
    full = planner.plan_context_dependencies(
        data, exchange.ExchangeSelectionScope(all_selected=True)
    )
    for limit, prior in (
        (0, 0),
        (1, 0),
        (17, 0),
        (17, 17),
        (full.work_units - 1, 0),
        (full.work_units, 0),
    ):
        record = observe(
            lambda: planner.plan_context_dependencies(
                data,
                exchange.ExchangeSelectionScope(all_selected=True, max_work=limit),
                prior_work=prior,
            )
        )
        record.update(
            work_limit=limit, prior_work=prior, input_json_bytes=len(json.dumps(data))
        )
        records["planner"].append(record)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(records, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": args.output,
                "admission_cases": len(records["admission"]),
                "bounded_json_cases": len(records["bounded_json"]),
                "planner_cases": len(records["planner"]),
            }
        )
    )


if __name__ == "__main__":
    main()
