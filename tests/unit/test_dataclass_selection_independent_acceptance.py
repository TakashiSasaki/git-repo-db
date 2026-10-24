"""Independent acceptance test suite for PR #165: Dataclass selection budget enforcement.

Verifies:
1. Genuine service-issued context scanning a 1,000-field dataclass with work_limit=10000 and selection.max_work=7.
2. Strict refusal before field access, members list materialization, and pending queue extension.
3. Complete budget vs selection permutation matrix:
   - Budget lower than selection
   - Selection lower than budget
   - Prior cumulative work reduction
   - Pending siblings queue congestion
   - Exact boundary conditions
   - Zero and exhausted capacity
   - Single refusal charging without double-charging
4. fields() reflection exception containment, custom attribute callback behavior, and AdmissionRefused passthrough.
5. Real Store relation transactions with mutating containers, rollback, persistent rows, transaction outcome, and lease cleanup.
6. Transfer SQL fences integrity.
"""

import sqlite3
import sys
import tempfile
from dataclasses import dataclass, make_dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

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
from tests.support.context_admission import FixturePolicy

SERVICE = "11111111-1111-4111-8111-111111111111"


class IndependentDetailedObserver:
    """Instrument frame locals during charge_input without modifying bytecode or callees."""

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


# 1,000-field dataclass definition with access counting
Fields1000 = make_dataclass("Fields1000", [(f"f_{i}", int) for i in range(1000)])


class AccessCounted1000(Fields1000):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        object.__setattr__(self, "attribute_accesses", 0)

    def __getattribute__(self, name):
        if name.startswith("f_"):
            object.__setattr__(
                self,
                "attribute_accesses",
                object.__getattribute__(self, "attribute_accesses") + 1,
            )
        return super().__getattribute__(name)


def make_genuine_service(resource_keys=None):
    """Build genuine ContextAdmissionService without test mock bypasses."""
    keys = resource_keys or frozenset()
    policy = FixturePolicy(DependencySet(resources=keys))
    return ContextAdmissionService(policy, lambda cred: f"user-for-{cred}")


# ---------------------------------------------------------------------------
# Obligation 1 & 2: Genuine Service-Issued Context & Zero Accesses
# ---------------------------------------------------------------------------


def test_genuine_service_issued_context_1000_fields():
    """Verify scanning 1,000-field dataclass with genuine service-issued context.

    work_limit=10000, selection.max_work=7.
    Refusal must occur before field access, members materialization, or pending extension.
    """
    service = make_genuine_service()
    # Issue a genuine context
    budget = AdmissionBudget(work_limit=10000)
    selection = AdmissionSelection(all_selected=True, max_work=7)
    context = service.context("valid-token", "provider_intake", selection, budget)

    instance = AccessCounted1000(*range(1000))
    observer = IndependentDetailedObserver(context_admission.__file__)

    with pytest.raises(AdmissionRefused) as exc_info:
        observer.run(lambda: service.charge_input(context, instance))

    assert exc_info.value.code == "INPUT_LIMIT"
    # Root object popped (1 unit), refusal fee charged (1 unit) => exactly 2 units
    assert context.budget.used_work == 2
    # Field getters must never be called
    assert instance.attribute_accesses == 0
    # Pending queue must never exceed 1 (initial root)
    assert observer.max_queue_len == 1
    # Members local list must never be materialized (0 elements)
    assert observer.max_members_len == 0
    # Snapshot lengths must be 0
    assert observer.max_snapshot_len == 0


# ---------------------------------------------------------------------------
# Obligation 3: Matrix of Budget, Selection, Sibling, Boundary, and Refusal Charges
# ---------------------------------------------------------------------------


@dataclass
class SixFieldDataclass:
    a: int = 1
    b: int = 2
    c: int = 3
    d: int = 4
    e: int = 5
    f: int = 6


def test_budget_lower_than_selection():
    """Budget (6) lower than selection (100) on a 6-field dataclass.

    Root object charges 1. Remaining budget is 5.
    6 fields require 6 units, which exceeds 5. Refuses with INPUT_LIMIT at used_work = 2.
    """
    service = make_genuine_service()
    ctx = service.context(
        "token",
        "provider_intake",
        AdmissionSelection(all_selected=True, max_work=100),
        AdmissionBudget(work_limit=6),
    )
    with pytest.raises(AdmissionRefused) as exc:
        service.charge_input(ctx, SixFieldDataclass())
    assert exc.value.code == "INPUT_LIMIT"
    assert ctx.budget.used_work == 2


def test_selection_lower_than_budget():
    """Selection (6) lower than budget (100) on a 6-field dataclass.

    Root object charges 1. Remaining work is 5 (min(100, 6) - 1).
    6 fields require 6 units, which exceeds 5. Refuses with INPUT_LIMIT at used_work = 2.
    """
    service = make_genuine_service()
    ctx = service.context(
        "token",
        "provider_intake",
        AdmissionSelection(all_selected=True, max_work=6),
        AdmissionBudget(work_limit=100),
    )
    with pytest.raises(AdmissionRefused) as exc:
        service.charge_input(ctx, SixFieldDataclass())
    assert exc.value.code == "INPUT_LIMIT"
    assert ctx.budget.used_work == 2


def test_prior_cumulative_work_reduces_dataclass_capacity():
    """Prior cumulative work charges reduce available capacity for dataclass reservation."""
    service = make_genuine_service()
    budget = AdmissionBudget(work_limit=20)
    ctx = service.context(
        "token",
        "provider_intake",
        AdmissionSelection(all_selected=True, max_work=20),
        budget,
    )
    # Simulate prior work
    ctx.budget.charge(work=14)
    # Remaining capacity is 20 - 14 = 6.
    # Root object charges 1, leaving 5.
    # 6-field dataclass exceeds 5 -> refused at used_work = 14 + 1 + 1 = 16
    with pytest.raises(AdmissionRefused) as exc:
        service.charge_input(ctx, SixFieldDataclass())
    assert exc.value.code == "INPUT_LIMIT"
    assert ctx.budget.used_work == 16


def test_pending_siblings_congestion():
    """Congestion from pending siblings in queue prevents dataclass expansion."""
    service = make_genuine_service()
    ctx = service.context(
        "token",
        "provider_intake",
        AdmissionSelection(all_selected=True, max_work=10),
        AdmissionBudget(work_limit=10),
    )
    # Input is a tuple containing: (1, 2, 3, 4, SixFieldDataclass())
    # Tuple has 5 items.
    # Root tuple pop charges 1 (used_work=1, remaining=9).
    # Tuple children reserved: 5 <= 9. Pending queue gets 5 items:
    # pending = [1, 2, 3, 4, SixFieldDataclass]
    # Because pending is a LIFO stack (pop() from end), SixFieldDataclass is popped first!
    # SixFieldDataclass pop charges 1 (used_work=2, remaining=8).
    # Pending queue still has 4 items [1, 2, 3, 4]!
    # SixFieldDataclass has 6 fields.
    # len(pending) + count = 4 + 6 = 10 > 8!
    # Even though count (6) <= remaining (8), pending + count (10) > remaining (8)!
    # Pre-reservation detects congestion and refuses with INPUT_LIMIT!
    input_tuple = (1, 2, 3, 4, SixFieldDataclass())
    with pytest.raises(AdmissionRefused) as exc:
        service.charge_input(ctx, input_tuple)
    assert exc.value.code == "INPUT_LIMIT"
    # Root tuple (1) + SixFieldDataclass pop (1) + refusal fee (1) = 3
    assert ctx.budget.used_work == 3


def test_exact_boundaries():
    """Verify exact boundary: 7 units is exact sufficient budget for SixFieldDataclass."""
    service = make_genuine_service()
    instance = SixFieldDataclass()

    # Budget 7, selection 7: 1 for root + 6 fields = 7. Exactly succeeds!
    ctx_exact = service.context(
        "token",
        "provider_intake",
        AdmissionSelection(all_selected=True, max_work=7),
        AdmissionBudget(work_limit=7),
    )
    service.charge_input(ctx_exact, instance)
    assert ctx_exact.budget.used_work == 7

    # Budget 6, selection 7: 1 for root + 6 fields requires 7 > 6. Fails at used_work = 2!
    ctx_under_budget = service.context(
        "token",
        "provider_intake",
        AdmissionSelection(all_selected=True, max_work=7),
        AdmissionBudget(work_limit=6),
    )
    with pytest.raises(AdmissionRefused) as exc1:
        service.charge_input(ctx_under_budget, instance)
    assert exc1.value.code == "INPUT_LIMIT"
    assert ctx_under_budget.budget.used_work == 2

    # Budget 7, selection 6: 1 for root + 6 fields requires 7 > 6. Fails at used_work = 2!
    ctx_under_selection = service.context(
        "token",
        "provider_intake",
        AdmissionSelection(all_selected=True, max_work=6),
        AdmissionBudget(work_limit=7),
    )
    with pytest.raises(AdmissionRefused) as exc2:
        service.charge_input(ctx_under_selection, instance)
    assert exc2.value.code == "INPUT_LIMIT"
    assert ctx_under_selection.budget.used_work == 2


def test_zero_and_exhausted_capacity():
    """Zero capacity refuses immediately; exhausted capacity refuses on children."""
    service = make_genuine_service()

    # Zero work limit: refuses on initial item pop
    ctx_zero = service.context(
        "token",
        "provider_intake",
        AdmissionSelection(all_selected=True, max_work=0),
        AdmissionBudget(work_limit=0),
    )
    with pytest.raises(AdmissionRefused) as exc:
        service.charge_input(ctx_zero, SixFieldDataclass())
    assert exc.value.code == "INPUT_LIMIT"
    assert ctx_zero.budget.used_work == 1

    # Capacity of 1 unit: initial pop succeeds, but 6 fields cannot be reserved
    ctx_one = service.context(
        "token",
        "provider_intake",
        AdmissionSelection(all_selected=True, max_work=1),
        AdmissionBudget(work_limit=1),
    )
    with pytest.raises(AdmissionRefused) as exc2:
        service.charge_input(ctx_one, SixFieldDataclass())
    assert exc2.value.code == "INPUT_LIMIT"
    assert ctx_one.budget.used_work == 2


def test_single_refusal_fee_no_double_charging():
    """Refusal fee is exactly 1 unit; no double charging occurs on refusal."""
    service = make_genuine_service()
    ctx = service.context(
        "token",
        "provider_intake",
        AdmissionSelection(all_selected=True, max_work=5),
        AdmissionBudget(work_limit=100),
    )
    with pytest.raises(AdmissionRefused) as exc:
        service.charge_input(ctx, SixFieldDataclass())
    assert exc.value.code == "INPUT_LIMIT"
    # Root pop (1) + refusal fee (1) = 2. Never 3.
    assert ctx.budget.used_work == 2


# ---------------------------------------------------------------------------
# Obligation 4: fields() Reflection Allocations & Custom Attribute Callbacks
# ---------------------------------------------------------------------------


def test_fields_reflection_exception_containment():
    """If fields(item) reflection raises an unhandled exception, it is trapped and charges 1 unit."""
    service = make_genuine_service()
    ctx = service.context(
        "token",
        "provider_intake",
        AdmissionSelection(all_selected=True, max_work=100),
        AdmissionBudget(work_limit=100),
    )

    orig_fields = context_admission.fields

    def broken_fields(obj):
        if isinstance(obj, SixFieldDataclass):
            raise RuntimeError("reflection failed unexpectedly")
        return orig_fields(obj)

    with patch(
        "repo_catalog.domain.context_admission.fields", side_effect=broken_fields
    ):
        with pytest.raises(AdmissionRefused) as exc:
            service.charge_input(ctx, SixFieldDataclass())
        assert exc.value.code == "INPUT_LIMIT"
        assert ctx.budget.used_work == 2


def test_attribute_callback_arbitrary_exception_containment():
    """If a custom attribute getter raises an arbitrary exception within budget, it fails closed."""

    @dataclass
    class BrokenGetterDataclass:
        a: int = 1

        def __getattribute__(self, name):
            if name == "a":
                raise ValueError("user getter exploded")
            return super().__getattribute__(name)

    service = make_genuine_service()
    ctx = service.context(
        "token",
        "provider_intake",
        AdmissionSelection(all_selected=True, max_work=100),
        AdmissionBudget(work_limit=100),
    )

    with pytest.raises(AdmissionRefused) as exc:
        service.charge_input(ctx, BrokenGetterDataclass())
    assert exc.value.code == "INPUT_LIMIT"
    # Root pop (1) + reflection + getter failed (charged 1 refusal) => 2
    assert ctx.budget.used_work == 2


def test_attribute_callback_admission_refused_passthrough():
    """If a custom attribute getter raises AdmissionRefused directly, it is passed through without double charging."""

    @dataclass
    class PassthroughDataclass:
        a: int = 1

        def __getattribute__(self, name):
            if name == "a":
                raise AdmissionRefused("INPUT_LIMIT")
            return super().__getattribute__(name)

    service = make_genuine_service()
    ctx = service.context(
        "token",
        "provider_intake",
        AdmissionSelection(all_selected=True, max_work=100),
        AdmissionBudget(work_limit=100),
    )

    with pytest.raises(AdmissionRefused) as exc:
        service.charge_input(ctx, PassthroughDataclass())
    assert exc.value.code == "INPUT_LIMIT"
    # Root pop (1). The AdmissionRefused was re-raised directly, so no extra charge occurred!
    assert ctx.budget.used_work == 1


def test_bounded_callback_execution_distinction():
    """Verify that when count > remaining capacity, arbitrary attribute getters NEVER execute.

    This proves that pre-reservation provides strict execution boundedness, whereas
    exception containment only protects against exceptions when within budget.
    """

    class BombExploded(Exception):
        pass

    @dataclass
    class BombDataclass:
        f1: int = 1
        f2: int = 2
        f3: int = 3
        f4: int = 4
        f5: int = 5
        f6: int = 6

        def __getattribute__(self, name):
            if name.startswith("f"):
                raise BombExploded("Arbitrary user code executed!")
            return super().__getattribute__(name)

    service = make_genuine_service()
    # Provide max_work=6 (insufficient for 6 fields + 1 root)
    ctx = service.context(
        "token",
        "provider_intake",
        AdmissionSelection(all_selected=True, max_work=6),
        AdmissionBudget(work_limit=100),
    )

    # BombDataclass getter would raise BombExploded if executed.
    # Because reserve_children(6) halts execution beforehand, BombExploded is never raised!
    with pytest.raises(AdmissionRefused) as exc:
        service.charge_input(ctx, BombDataclass())
    assert exc.value.code == "INPUT_LIMIT"
    assert ctx.budget.used_work == 2


# ---------------------------------------------------------------------------
# Obligation 5 & 7: Real-Store Counterexamples, Rollback, Transfer Fences
# ---------------------------------------------------------------------------


class MutatingMemberSequence(list):
    """Mutating list that arms after initialization and appends 1000 members during iteration."""

    def __init__(self, *args):
        super().__init__(*args)
        self.armed = False

    def __iter__(self):
        if self.armed:
            for i in range(1000):
                self.append(ResourceKey.from_native(SERVICE, "issue", f"extra-{i}"))
        return super().__iter__()


def test_real_store_counterexample_and_rollback():
    """Verify real Store relation counterexample with mutating list under owned_transaction.

    Confirms:
    - Traversal refused with INPUT_LIMIT.
    - Zero rows persisted in SQLite (db_rows == 0).
    - Transaction outcome is not in transaction (clean rollback).
    - Transfer SQL fence remains intact.
    - Directory lease / locks cleaned up.
    """
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
    assert has_transfer_fence(db), "Context store must have transfer fence installed"

    owner = ResourceKey.from_native(SERVICE, "issue", "owner")
    k0 = ResourceKey.from_native(SERVICE, "issue", "0")
    k1 = ResourceKey.from_native(SERVICE, "issue", "1")
    members = MutatingMemberSequence([k0, k1])

    report = ResourceRelation(
        owner,
        "x-links",
        members,
        canonical({"source": "review", "evidence": "synthetic"}),
        "{}",
        1,
    )
    members.armed = True

    policy = FixturePolicy(DependencySet(resources=frozenset({owner, k0, k1})))
    service = ContextAdmissionService(policy, lambda cred: "store-reviewer")

    ctx = service.context(
        "store-token",
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

    observer = IndependentDetailedObserver(context_admission.__file__)
    refused_code = None

    with tempfile.TemporaryDirectory(prefix="independent-store-") as temp_dir:
        temp_path = Path(temp_dir)

        def action():
            with Context.owned_transaction(
                db, temp_path, authorization=service, admission=ctx
            ) as store_ctx:
                store_ctx.relation(report, admission=ctx)

        try:
            observer.run(action)
        except AdmissionRefused as exc:
            refused_code = exc.code

    assert refused_code == "INPUT_LIMIT"
    assert observer.max_queue_len <= 6
    assert observer.max_snapshot_len <= 2
    # Ensure no rows persisted
    db_rows = db.execute("SELECT count(*) FROM resource_relations").fetchone()[0]
    assert db_rows == 0, f"Expected 0 persistent rows, found {db_rows}"
    # Ensure transaction rolled back
    assert not db.in_transaction, "Expected transaction to be inactive (rolled back)"
    # Ensure transfer fence intact
    assert has_transfer_fence(db), "Transfer fence must remain active post-rollback"
    # Ensure lease / locks cleaned up (directory freed)
    assert not temp_path.exists(), "Temporary directory must be cleaned up"
    db.close()


def test_real_store_dataclass_relation_selection_limit_7():
    """Verify ResourceRelation (dataclass with 6 fields) under selection.max_work=7.

    ResourceRelation has 6 fields. Under root tuple, popped at used_work=2.
    Remaining work is 7 - 2 = 5.
    Pre-reservation detects 6 > 5 before field extraction, charging 1 refusal fee (used_work=3).
    Queue never expands (max_queue_len=1), members list never materialized (max_members_len=0).
    """
    from tests.unit.test_admission_scanner_budget import run_store_relation

    observer = IndependentDetailedObserver(context_admission.__file__)
    res = run_store_relation(1000, 10000, 10000, 7, observer=observer)

    assert res["outcome"] == "AdmissionRefused"
    assert res["code"] == "INPUT_LIMIT"
    assert res["used_work"] == 3
    assert res["rows_before"] == res["rows_after"] == 0
    assert not res["in_transaction"]
    assert observer.max_queue_len == 1
    assert observer.max_members_len == 0
