"""Regression tests for I155-M01 Admission Scanner work-budget enforcement.

Verifies:
- Variable-sized child queues are never constructed after work budget exhaustion.
- Remaining work bounds (cumulative and selection) are enforced before queue growth.
- Refused reservations charge contractually defined fixed unit without unauthorized work.
- Exact-boundary successes and completed units are preserved without double-charging.
- Input mutation defenses, UTF-8 chunk bounds, depth/cycle stops, and precedence.
"""

import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.adapters.sqlite.production_context import Context
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


class Observer:
    """Instrument frame execution and C-level list.extend without replacing callees."""

    def __init__(self, target_filename: str):
        self.target_filename = str(Path(target_filename).resolve())
        self.queue_lengths = []
        self.extend_calls = []
        self.snapshot_lengths = []
        self.max_queue_len = 0
        self.max_snapshot_len = 0

    def trace(self, frame, event, arg):
        if str(Path(frame.f_code.co_filename).resolve()) == self.target_filename:
            pending = frame.f_locals.get("pending")
            if type(pending) is list:
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

    def profile(self, frame, event, arg):
        if (
            event in ("c_call", "c_return")
            and getattr(arg, "__name__", "") == "extend"
            and str(Path(frame.f_code.co_filename).resolve()) == self.target_filename
        ):
            owner = getattr(arg, "__self__", None)
            if type(owner) is list:
                self.extend_calls.append((event, len(owner)))

    def run(self, fn):
        old_trace = sys.gettrace()
        old_profile = sys.getprofile()
        sys.settrace(self.trace)
        sys.setprofile(self.profile)
        try:
            return fn()
        finally:
            sys.settrace(old_trace)
            sys.setprofile(old_profile)


def run_store_relation(
    n: int,
    limit: int,
    remaining: int,
    selected: int,
    observer: Observer | None = None,
):
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
    policy = FixturePolicy(
        DependencySet(
            resources=frozenset({owner, *members}),
        )
    )
    service = ContextAdmissionService(policy, lambda token: "fixture-user")
    budget = AdmissionBudget(work_limit=limit)
    issued = service.context(
        "fixture-credential",
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

    outcome = None
    refusal_code = None
    with tempfile.TemporaryDirectory(prefix="scanner-reg-") as directory:

        def action():
            with Context.owned_transaction(
                db, Path(directory), authorization=service, admission=issued
            ) as ctx:
                return ctx.relation(report, admission=issued)

        try:
            if observer is not None:
                observer.run(action)
            else:
                action()
            outcome = "success"
        except AdmissionRefused as exc:
            outcome = "AdmissionRefused"
            refusal_code = exc.code
    db.set_trace_callback(None)
    after = db.execute("select count(*) from resource_relations").fetchone()[0]
    fences = has_transfer_fence(db)
    in_tx = db.in_transaction
    db.close()
    return {
        "outcome": outcome,
        "code": refusal_code,
        "used_work": budget.used_work,
        "prior_work": limit - remaining,
        "policy_calls": len(policy.calls),
        "rows_before": before,
        "rows_after": after,
        "in_transaction": in_tx,
        "fences": fences,
        "sql": sql,
    }


def test_i155_m01_real_store_counterexample_prevented():
    """Independent PR #156 counterexample: 1000 members, work_limit 10000, prior 9992.

    Defect behavior: queue extended from 2 to 1002 entries before refusal at 10001.
    Fixed behavior: reservation fails before queue growth, queue <= 6, refusal at 10001.
    """
    from repo_catalog.domain import context_admission

    obs = Observer(context_admission.__file__)
    res = run_store_relation(1000, 10000, 8, 10000, observer=obs)

    assert res["outcome"] == "AdmissionRefused"
    assert res["code"] == "INPUT_LIMIT"
    assert res["used_work"] == 10001
    assert res["policy_calls"] == 0
    assert res["rows_before"] == res["rows_after"] == 0
    assert not res["in_transaction"]
    assert res["fences"]
    assert res["sql"][-1] == "ROLLBACK"

    # Queue must never expand to 1002 entries
    assert obs.max_queue_len <= 6
    assert not any(length >= 1000 for event, length in obs.extend_calls)


def test_i155_m01_real_store_exhausted_prior_work():
    """Already exhausted prior work: limit 10000, prior 10000.

    Root queue of 1 entry only; refuses at used_work 10001.
    """
    from repo_catalog.domain import context_admission

    obs = Observer(context_admission.__file__)
    res = run_store_relation(1000, 10000, 0, 10000, observer=obs)

    assert res["outcome"] == "AdmissionRefused"
    assert res["code"] == "INPUT_LIMIT"
    assert res["used_work"] == 10001
    assert obs.max_queue_len == 1
    assert len(obs.extend_calls) == 0


def test_i155_m01_real_store_selection_work_limit_7():
    """Separate PR #156 counterexample: limit 10000, prior 0, selection.max_work 7.

    Defect behavior: queue extended to 1002 before refusal at 8.
    Fixed behavior: refuses at 8 without expanding queue (max <= 6).
    """
    from repo_catalog.domain import context_admission

    obs = Observer(context_admission.__file__)
    res = run_store_relation(1000, 10000, 10000, 7, observer=obs)

    assert res["outcome"] == "AdmissionRefused"
    assert res["code"] == "INPUT_LIMIT"
    assert res["used_work"] == 8
    assert res["policy_calls"] == 0
    assert res["rows_before"] == res["rows_after"] == 0
    assert not res["in_transaction"]
    assert obs.max_queue_len <= 6
    assert not any(length >= 1000 for event, length in obs.extend_calls)


def test_i155_m01_zero_work_limit():
    """Zero total work limit must refuse immediately on initial pop."""
    from repo_catalog.domain import context_admission

    obs = Observer(context_admission.__file__)
    res = run_store_relation(16, 0, 0, 0, observer=obs)

    assert res["outcome"] == "AdmissionRefused"
    assert res["code"] == "INPUT_LIMIT"
    assert res["used_work"] == 1
    assert obs.max_queue_len == 1


@pytest.mark.parametrize(
    "container_fn,item_count,exact_cost",
    [
        (lambda: (), 0, 1),
        (lambda: [], 0, 1),
        (lambda: {}, 0, 1),
        (lambda: (1,), 1, 2),
        (lambda: [1, 2], 2, 3),
        (lambda: frozenset({1, 2, 3}), 3, 4),
        (
            lambda: {1: 2},
            1,
            3,
        ),  # dict with int key/val: pop dict (1) + pop val (1) + pop key (1)
        (
            lambda: {"a": 1},
            1,
            4,
        ),  # dict with str key: pop dict (1) + val (1) + key (1) + str chunk (1)
        (lambda: [[1], 2], 2, 4),  # outer (1) + 2 (1) + [1] (1) + 1 (1)
    ],
    ids=[
        "empty-tuple",
        "empty-list",
        "empty-dict",
        "1-tuple",
        "2-list",
        "3-frozenset",
        "1-int-dict",
        "1-str-dict",
        "nested-list",
    ],
)
def test_exact_sufficient_budget_vs_one_below(container_fn, item_count, exact_cost):
    """Exact sufficient budget succeeds; one unit below fails without queue growth."""
    service, _ = fixture_service(DependencySet())

    # Exact sufficient budget must succeed
    context_exact = fixture_context(
        service,
        selection=AdmissionSelection(all_selected=True, max_work=exact_cost),
        budget=AdmissionBudget(work_limit=exact_cost),
    )
    service.charge_input(context_exact, container_fn())
    assert context_exact.budget.used_work == exact_cost

    # One unit below sufficient budget must fail with INPUT_LIMIT
    one_below = exact_cost - 1
    context_short = fixture_context(
        service,
        selection=AdmissionSelection(all_selected=True, max_work=one_below),
        budget=AdmissionBudget(work_limit=one_below),
    )
    with pytest.raises(AdmissionRefused) as exc:
        service.charge_input(context_short, container_fn())
    assert exc.value.code == "INPUT_LIMIT"


def test_large_tuple_list_frozenset_queue_never_constructed_without_budget():
    """Large containers (10,000 items) must not build child queue when budget is 5."""
    from repo_catalog.domain import context_admission

    service, _ = fixture_service(DependencySet())
    large_list = list(range(10_000))
    large_tuple = tuple(range(10_000))
    large_frozenset = frozenset(range(10_000))

    for container in (large_list, large_tuple, large_frozenset):
        context = fixture_context(service, budget=AdmissionBudget(work_limit=5))
        obs = Observer(context_admission.__file__)
        with pytest.raises(AdmissionRefused) as exc:
            obs.run(lambda: service.charge_input(context, container))
        assert exc.value.code == "INPUT_LIMIT"
        assert obs.max_queue_len == 1
        assert len(obs.extend_calls) == 0


def test_dictionary_key_value_expansion_bounded():
    """Large dict (5,000 items, 10,000 children) must not build child queue when budget is 5."""
    from repo_catalog.domain import context_admission

    service, _ = fixture_service(DependencySet())
    large_dict = {f"k{i}": i for i in range(5_000)}

    context = fixture_context(service, budget=AdmissionBudget(work_limit=5))
    obs = Observer(context_admission.__file__)
    with pytest.raises(AdmissionRefused) as exc:
        obs.run(lambda: service.charge_input(context, large_dict))
    assert exc.value.code == "INPUT_LIMIT"
    assert obs.max_queue_len == 1
    assert len(obs.extend_calls) == 0


@dataclass
class SyntheticDataclass:
    f1: int
    f2: str
    f3: list
    f4: dict
    f5: int
    f6: int


def test_dataclass_member_expansion():
    """Dataclass with 6 fields: exact budget (7) succeeds; budget (6) fails without child queue."""
    service, _ = fixture_service(DependencySet())
    instance = SyntheticDataclass(1, "", [], {}, 5, 6)
    # Pop dataclass (1) + 6 fields (6) = 7 units
    context_exact = fixture_context(service, budget=AdmissionBudget(work_limit=7))
    service.charge_input(context_exact, instance)
    assert context_exact.budget.used_work == 7

    context_short = fixture_context(service, budget=AdmissionBudget(work_limit=6))
    with pytest.raises(AdmissionRefused) as exc:
        service.charge_input(context_short, instance)
    assert exc.value.code == "INPUT_LIMIT"


def test_strings_chunking_and_unicode_precedence():
    """Strings chunk in 4096-byte blocks; bounds and precedence are strictly maintained."""
    service, _ = fixture_service(DependencySet())

    # String of 10,000 chars has 3 chunks (4096, 4096, 1808) -> 1 (pop) + 3 (chunks) = 4 units
    long_str = "x" * 10_000
    ctx_exact = fixture_context(service, budget=AdmissionBudget(work_limit=4))
    service.charge_input(ctx_exact, long_str)
    assert ctx_exact.budget.used_work == 4
    assert ctx_exact.budget.used_bytes == 10_000

    # With work_limit=2 (pop + 1 chunk), stops at chunk 2 without encoding chunk 3
    ctx_short = fixture_context(service, budget=AdmissionBudget(work_limit=2))
    with pytest.raises(AdmissionRefused) as exc:
        service.charge_input(ctx_short, long_str)
    assert exc.value.code == "INPUT_LIMIT"
    assert ctx_short.budget.used_work == 3  # 1 pop + 1 chunk + 1 failed reservation
    assert ctx_short.budget.used_bytes == 4096

    # Invalid surrogate Unicode:
    # If budget allows encoding: raises INVALID_PROVENANCE
    bad_unicode = "valid\ud800bad"
    ctx_unicode = fixture_context(service, budget=AdmissionBudget(work_limit=10))
    with pytest.raises(AdmissionRefused) as exc:
        service.charge_input(ctx_unicode, bad_unicode)
    assert exc.value.code == "INVALID_PROVENANCE"

    # If budget exhausted before encoding: raises INPUT_LIMIT (precedence)
    ctx_precedence = fixture_context(service, budget=AdmissionBudget(work_limit=1))
    with pytest.raises(AdmissionRefused) as exc:
        service.charge_input(ctx_precedence, bad_unicode)
    assert exc.value.code == "INPUT_LIMIT"


def test_nested_depth_and_cyclic_reference_stops():
    """Depth limit and cyclic references stop finitely with INPUT_LIMIT."""
    service, _ = fixture_service(DependencySet())

    # Direct cycle: [cycle]
    cycle = []
    cycle.append(cycle)
    ctx_cycle = fixture_context(service, budget=AdmissionBudget(work_limit=100))
    with pytest.raises(AdmissionRefused) as exc:
        service.charge_input(ctx_cycle, cycle)
    assert exc.value.code == "INPUT_LIMIT"
    assert (
        ctx_cycle.budget.used_work == 14
    )  # exactly 13 pops (depth 0..12) + 1 pop (depth 13 > 12)

    # Nesting exceeding depth limit 12
    nested = 0
    for _ in range(14):
        nested = [nested]
    ctx_depth = fixture_context(
        service, budget=AdmissionBudget(work_limit=100, depth_limit=12)
    )
    with pytest.raises(AdmissionRefused) as exc:
        service.charge_input(ctx_depth, nested)
    assert exc.value.code == "INPUT_LIMIT"


def test_repeated_admission_and_exact_replay(tmp_path):
    """Admitting legitimate report twice: first is 'insert', second is 'duplicate'."""
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
    db.execute(
        "INSERT INTO providers VALUES(?, 'synthetic', '{}')",
        (SERVICE,),
    )
    db.execute(
        "INSERT INTO resources VALUES(?, 'issue', '\"owner\"', NULL, NULL, NULL, NULL)",
        (SERVICE,),
    )
    db.execute(
        "INSERT INTO resources VALUES(?, 'issue', '\"m1\"', NULL, NULL, NULL, NULL)",
        (SERVICE,),
    )

    owner = ResourceKey.from_native(SERVICE, "issue", "owner")
    members = (ResourceKey.from_native(SERVICE, "issue", "m1"),)
    report = ResourceRelation(
        owner,
        "x-links",
        members,
        canonical({"source": "review", "evidence": "replay"}),
        "{}",
        100,
    )
    policy = FixturePolicy(
        DependencySet(
            resources=frozenset({owner, *members}),
            provider_registrations=frozenset({SERVICE}),
        )
    )
    service = ContextAdmissionService(policy, lambda token: "fixture-user")

    # First admission
    dir1 = tmp_path / "dir1"
    dir1.mkdir()
    ctx1 = service.context(
        "fixture-credential",
        "provider_intake",
        AdmissionSelection(
            resource_keys=frozenset({owner, *members}),
            repository_uuidv4s=frozenset(),
            source_uuidv4s=frozenset(),
            object_oids=frozenset(),
        ),
        AdmissionBudget(work_limit=1000),
    )
    with Context.owned_transaction(
        db, dir1, authorization=service, admission=ctx1
    ) as c1:
        res1 = c1.relation(report, admission=ctx1)
    assert res1 == "insert"
    assert policy.active == 0

    # Replay admission
    dir2 = tmp_path / "dir2"
    dir2.mkdir()
    ctx2 = service.context(
        "fixture-credential",
        "provider_intake",
        AdmissionSelection(
            resource_keys=frozenset({owner, *members}),
            repository_uuidv4s=frozenset(),
            source_uuidv4s=frozenset(),
            object_oids=frozenset(),
        ),
        AdmissionBudget(work_limit=1000),
    )
    with Context.owned_transaction(
        db, dir2, authorization=service, admission=ctx2
    ) as c2:
        res2 = c2.relation(report, admission=ctx2)
    assert res2 == "duplicate"
    assert policy.active == 0
    assert db.execute("select count(*) from resource_relations").fetchone()[0] == 1
    db.close()


def test_permission_denial_and_selection_omission():
    """Unauthenticated or unselected input fails without unauthorized work or leaks."""
    policy = FixturePolicy(DependencySet())

    def authenticate(cred):
        if cred != "fixture-credential":
            raise AdmissionRefused("PERMISSION_DENIED")
        return "fixture-user"

    service = ContextAdmissionService(policy, authenticate)

    # Invalid credential
    with pytest.raises(AdmissionRefused) as exc:
        service.context(
            "bad-token",
            "provider_intake",
            AdmissionSelection(all_selected=True),
            AdmissionBudget(),
        )
    assert exc.value.code == "PERMISSION_DENIED"

    # Context tampering: mutating principal
    ctx = fixture_context(service)
    tampered = ctx.__class__(
        principal="attacker",
        operation=ctx.operation,
        selection=ctx.selection,
        budget=ctx.budget,
    )
    with pytest.raises(AdmissionRefused) as exc:
        service.charge_input(tampered, ("test",))
    assert exc.value.code == "PERMISSION_DENIED"
    assert ctx.budget.used_work == 0


def test_mutation_defense_iterator_mismatch():
    """Subclass whose iteration yields more items than len() reports cannot bypass reservation."""

    class MutatingList(list):
        def __iter__(self):
            # Yields 10 items even though len reports 2
            return iter(list(range(10)))

    service, _ = fixture_service(DependencySet())
    tricky = MutatingList([1, 2])
    assert len(tricky) == 2

    # Budget of 3: enough for 2 items (pop tricky + 2 children), but not 10
    ctx = fixture_context(service, budget=AdmissionBudget(work_limit=3))
    with pytest.raises(AdmissionRefused) as exc:
        service.charge_input(ctx, tricky)
    assert exc.value.code == "INPUT_LIMIT"


def test_mutation_defense_appending_during_iteration_bounded():
    """List subclass whose __iter__ appends 1000 items cannot expand queue or snapshot (discussion_r4366012662)."""
    from repo_catalog.domain import context_admission

    class AppendingList(list):
        def __iter__(self):
            for i in range(1000):
                self.append(i)
            return super().__iter__()

    service, _ = fixture_service(DependencySet())
    item = AppendingList([1, 2])
    assert len(item) == 2

    obs = Observer(context_admission.__file__)
    ctx = fixture_context(
        service,
        selection=AdmissionSelection(all_selected=True, max_work=3),
        budget=AdmissionBudget(work_limit=10000),
    )
    with pytest.raises(AdmissionRefused) as exc:
        obs.run(lambda: service.charge_input(ctx, item))
    assert exc.value.code == "INPUT_LIMIT"
    assert obs.max_queue_len <= 1
    assert obs.max_snapshot_len <= 2
    assert ctx.budget.used_work == 2
    assert len(item) == 1002


def test_mutation_defense_changing_length_during_iteration_bounded():
    """Container whose length mutates while yielding elements is bounded during traversal."""
    from repo_catalog.domain import context_admission

    class ChangingLenList(list):
        def __iter__(self):
            for i in range(500):
                self.append(i)
                yield i

    service, _ = fixture_service(DependencySet())
    item = ChangingLenList([1, 2])
    obs = Observer(context_admission.__file__)
    ctx = fixture_context(
        service,
        selection=AdmissionSelection(all_selected=True, max_work=3),
        budget=AdmissionBudget(work_limit=10000),
    )
    with pytest.raises(AdmissionRefused) as exc:
        obs.run(lambda: service.charge_input(ctx, item))
    assert exc.value.code == "INPUT_LIMIT"
    assert obs.max_queue_len <= 1
    assert obs.max_snapshot_len <= 2
    assert ctx.budget.used_work == 2


def test_mutation_defense_deceptive_or_dynamic_len_bounded():
    """Subclass with misleading or dynamically changing __len__ cannot bypass reservation."""
    from repo_catalog.domain import context_admission

    class DynamicLenList(list):
        def __init__(self, *args):
            super().__init__(*args)
            self.calls = 0

        def __len__(self):
            self.calls += 1
            return 2 if self.calls == 1 else 1000

        def __iter__(self):
            yield from range(1000)

    service, _ = fixture_service(DependencySet())
    item = DynamicLenList([1, 2])
    obs = Observer(context_admission.__file__)
    ctx = fixture_context(
        service,
        selection=AdmissionSelection(all_selected=True, max_work=3),
        budget=AdmissionBudget(work_limit=10000),
    )
    with pytest.raises(AdmissionRefused) as exc:
        obs.run(lambda: service.charge_input(ctx, item))
    assert exc.value.code == "INPUT_LIMIT"
    assert obs.max_queue_len <= 1
    assert obs.max_snapshot_len <= 2
    assert ctx.budget.used_work == 2


def test_mutation_defense_snapshot_bounded_before_queue_extend():
    """Snapshot generation aborts immediately when child count breaches remaining budget."""
    from repo_catalog.domain import context_admission

    class OverflowList(list):
        def __iter__(self):
            yield from range(1000)

    service, _ = fixture_service(DependencySet())
    item = OverflowList([1, 2])
    obs = Observer(context_admission.__file__)
    ctx = fixture_context(
        service,
        selection=AdmissionSelection(all_selected=True, max_work=5),
        budget=AdmissionBudget(work_limit=10000),
    )
    with pytest.raises(AdmissionRefused) as exc:
        obs.run(lambda: service.charge_input(ctx, item))
    assert exc.value.code == "INPUT_LIMIT"
    assert obs.max_queue_len <= 1
    assert obs.max_snapshot_len <= 2
    assert ctx.budget.used_work == 2


def test_mutation_defense_real_store_relation_armed_list():
    """Real Context.owned_transaction store relation admission bounds mutating list queues."""
    from repo_catalog.domain import context_admission

    class ArmedList(list):
        def __init__(self, *args):
            super().__init__(*args)
            self.armed = False

        def __iter__(self):
            if self.armed:
                for i in range(1000):
                    self.append(ResourceKey.from_native(SERVICE, "issue", f"extra_{i}"))
            return super().__iter__()

    owner = ResourceKey.from_native(SERVICE, "issue", "owner")
    k0 = ResourceKey.from_native(SERVICE, "issue", "0")
    k1 = ResourceKey.from_native(SERVICE, "issue", "1")
    gl = ArmedList([k0, k1])

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

    policy = FixturePolicy(DependencySet(resources=frozenset({owner, k0, k1})))
    service = ContextAdmissionService(policy, lambda cred: "fixture-user")

    ctx = service.context(
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

    obs = Observer(context_admission.__file__)
    with tempfile.TemporaryDirectory() as directory:
        with pytest.raises(AdmissionRefused) as exc:
            with Context.owned_transaction(
                db, Path(directory), authorization=service, admission=ctx
            ) as c:
                obs.run(lambda: c.relation(report, admission=ctx))
        assert exc.value.code == "INPUT_LIMIT"

    assert obs.max_queue_len <= 6
    assert obs.max_snapshot_len <= 2
    assert db.execute("select count(*) from resource_relations").fetchone()[0] == 0
    assert has_transfer_fence(db)
    assert not db.in_transaction
    db.close()


def test_post_traversal_mutation_charged_only_once():
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

    class DummyPolicy:
        def lease(self, principal, operation, deps):
            pass

    service = ContextAdmissionService(DummyPolicy(), lambda cred: "user")

    # List mutation charges exactly 2 units (1 root pop + 1 refusal unit)
    ctx1 = service.context(
        "cred",
        "provider_intake",
        AdmissionSelection(all_selected=True, max_work=100),
        AdmissionBudget(work_limit=100),
    )
    with pytest.raises(AdmissionRefused) as exc1:
        service.charge_input(ctx1, MutatingList([1, 2]))
    assert exc1.value.code == "INPUT_LIMIT"
    assert ctx1.budget.used_work == 2

    # Dict mutation charges exactly 2 units (1 root pop + 1 refusal unit)
    ctx2 = service.context(
        "cred",
        "provider_intake",
        AdmissionSelection(all_selected=True, max_work=100),
        AdmissionBudget(work_limit=100),
    )
    with pytest.raises(AdmissionRefused) as exc2:
        service.charge_input(ctx2, MutatingDict({"a": 1, "b": 2}))
    assert exc2.value.code == "INPUT_LIMIT"
    assert ctx2.budget.used_work == 2
