"""ADR 0031 I5: Typed Transfer Admission test suite.

Verifies:
1. Isolated disposable DB fixture where only the two SQL fences are dropped after
   exact packaged schema verification.
2. Normal product DB remains fenced and rejects Transfer admission and query.
3. G3=A native-I7 vs reported-I8 permanent semantic violation vs missing dependency.
4. Provider Event meaning: genuine event_type='transferred' and original coordinates.
5. Pre-bind strict type verification before SQLite affinity conversions.
6. Atomic admission under SAVEPOINT with zero partial writes on failure.
7. Exact replay idempotency vs payload/time mutation rejection.
8. Selection/truncation qualification and endpoint completeness.
9. Multi-event query filtering and prevention of endpoint cross-borrowing.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.p1_context import (
    EventReportKey,
    FieldClock,
    MappingClaimKey,
    MappingSupport,
    ResourceKey,
    ResourceRepositoryRelation,
    TransferEventReport,
    canonical,
)
from repo_catalog.domain.parent_report import ParentReportKey
from repo_catalog.domain.resource_identification import ResourceIdentification as RI
from repo_catalog.domain.resource_stage import UnsupportedResourceStage

SERVICE = "aad25448-03eb-4f83-a75e-cb7055fd33be"
REPO_1 = "9ebbe38a-f937-40e6-a99c-701835ebcf10"
REPO_2 = "c58b4f17-f58c-4a33-8bc6-eb52c42337d1"
REPO_3 = "d3333333-3333-4333-8333-333333333333"

KEY_ISSUE_7 = ResourceKey.from_native(SERVICE, "issue", "7")
KEY_ISSUE_8 = ResourceKey.from_native(SERVICE, "issue", "8")

KEY_EVENT_7 = ResourceKey.document(KEY_ISSUE_7, "comment", "timeline_event", "77")
KEY_EVENT_8 = ResourceKey.document(KEY_ISSUE_8, "comment", "timeline_event", "88")

KEY_PROV_REPO_1 = ResourceKey.from_native(SERVICE, "repository", "org/repo1")
KEY_PROV_REPO_2 = ResourceKey.from_native(SERVICE, "repository", "org/repo2")

CLOCK_EVENT = FieldClock("event-clock", 100)
CLOCK_PARENT = FieldClock("parent-clock", 50)

PROV_PARENT = canonical({"source": "parent-orig", "evidence": ["p-ev", 1]})
PROV_EVENT = canonical({"source": "event-orig", "evidence": ["e-ev", 2]})

FENCES = ("i2_transfer_stage_fence", "i2_transfer_report_stage_fence")


def _parent_scope(clock: FieldClock = CLOCK_PARENT) -> str:
    return canonical(
        {
            "clock": json.loads(clock.encode()),
            "document_kind": "timeline_event",
            "state": "complete",
        }
    )


def _parent_members(issue: ResourceKey) -> str:
    return canonical([list(issue.coordinates())])


def make_parent_report(
    event: ResourceKey = KEY_EVENT_7,
    issue: ResourceKey = KEY_ISSUE_7,
    clock: FieldClock = CLOCK_PARENT,
    provenance: str = PROV_PARENT,
) -> ParentReportKey:
    return ParentReportKey(
        resource=event,
        members_json=_parent_members(issue),
        provenance_json=provenance,
        scope_json=_parent_scope(clock),
    )


@pytest.fixture(params=["composed-sql", "product-factory"])
def normal_db(request, tmp_path):
    if request.param == "composed-sql":
        db = sqlite3.connect(":memory:", isolation_level=None)
        p1_schema.register_functions(db)
        p1_schema.configure(db)
        db.executescript(p1_schema.compose("context"))
    else:
        path = tmp_path / "context.sqlite3"
        p1_schema.initialize(path, "context", REPO_1, SERVICE)
        db = p1_schema.connect(path, "context")
    db.execute("INSERT OR IGNORE INTO providers VALUES(?,?,?)", (SERVICE, "test", "{}"))
    yield db
    db.close()


@pytest.fixture
def isolated_db(normal_db):
    assert p1_schema.schema_rows(normal_db) == p1_schema.expected_schema("context")
    for fence in FENCES:
        normal_db.execute(f"DROP TRIGGER {fence}")
    yield normal_db


def _setup_base_records(
    db: sqlite3.Connection,
    *,
    register_event: bool = True,
    register_issue: bool = True,
    register_parent_report: bool = True,
    register_repos: bool = True,
    register_prov_repos: bool = True,
    register_mapping_support: bool = False,
    issue_key: ResourceKey = KEY_ISSUE_7,
    event_key: ResourceKey = KEY_EVENT_7,
    parent_clock: FieldClock = CLOCK_PARENT,
    parent_prov: str = PROV_PARENT,
):
    db.execute("INSERT OR IGNORE INTO providers VALUES(?,?,?)", (SERVICE, "test", "{}"))

    if register_repos:
        for r_id in (REPO_1, REPO_2, REPO_3):
            db.execute(
                "INSERT OR IGNORE INTO repository_context VALUES(?,?)", (r_id, "{}")
            )

    if register_prov_repos:
        for prov_repo in (KEY_PROV_REPO_1, KEY_PROV_REPO_2):
            ri = RI.unscoped(prov_repo)
            db.execute(
                """INSERT OR IGNORE INTO resources(
                    service_instance_uuidv4, resource_kind, provider_resource_id,
                    identifier_namespace_kind, identifier_namespace_id, document_kind, provider_document_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (*prov_repo.coordinates(), *ri.columns),
            )

    if register_issue:
        ri_issue = RI.unscoped(issue_key)
        db.execute(
            """INSERT OR IGNORE INTO resources(
                service_instance_uuidv4, resource_kind, provider_resource_id,
                identifier_namespace_kind, identifier_namespace_id, document_kind, provider_document_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (*issue_key.coordinates(), *ri_issue.columns),
        )

    if register_event:
        ri_event = RI.scoped(
            event_key,
            issue_key,
            "timeline_event",
            "77" if issue_key == KEY_ISSUE_7 else "88",
        )
        db.execute(
            """INSERT OR IGNORE INTO resources(
                service_instance_uuidv4, resource_kind, provider_resource_id,
                identifier_namespace_kind, identifier_namespace_id, document_kind, provider_document_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (*event_key.coordinates(), *ri_event.columns),
        )

    if register_parent_report:
        db.execute(
            """INSERT OR IGNORE INTO resource_relations(
                service_instance_uuidv4, resource_kind, provider_resource_id,
                relation_kind, members_json, provenance_json, scope_json, observed_at_us
            ) VALUES (?, ?, ?, 'parent', ?, ?, ?, ?)""",
            (
                *event_key.coordinates(),
                _parent_members(issue_key),
                parent_prov,
                _parent_scope(parent_clock),
                10,
            ),
        )

    if register_mapping_support:
        for prov_repo, target_uuid in (
            (KEY_PROV_REPO_1, REPO_1),
            (KEY_PROV_REPO_2, REPO_2),
        ):
            db.execute(
                """INSERT OR IGNORE INTO resource_repository_relations(
                    service_instance_uuidv4, resource_kind, provider_resource_id,
                    relation_kind, target_json, clock_json, provenance_json, observed_at_us
                ) VALUES (?, ?, ?, 'represents_repository', ?, ?, ?, ?)""",
                (
                    *prov_repo.coordinates(),
                    canonical(target_uuid),
                    CLOCK_PARENT.encode(),
                    parent_prov,
                    10,
                ),
            )


def _make_mapping_support(prov_repo: ResourceKey, target_uuid: str) -> MappingSupport:
    claim = MappingClaimKey(
        resource=prov_repo,
        relation_kind="represents_repository",
        clock=CLOCK_PARENT,
        target_json=canonical(target_uuid),
        provenance_json=PROV_PARENT,
    )
    return MappingSupport(
        provider_repository=prov_repo,
        supporting_claims=(claim,),
    )


def test_schema_verification_and_isolation_exactness(normal_db):
    expected = p1_schema.expected_schema("context")
    assert p1_schema.schema_rows(normal_db) == expected

    for fence in FENCES:
        normal_db.execute(f"DROP TRIGGER {fence}")

    isolated_expected = tuple(
        r for r in expected if not (r[0] == "trigger" and r[1] in FENCES)
    )
    assert p1_schema.schema_rows(normal_db) == isolated_expected


def test_normal_fenced_product_refuses_transfer(normal_db):
    store = ContextStore(normal_db)
    _setup_base_records(normal_db)

    report = TransferEventReport.from_targets(
        KEY_EVENT_7,
        clock=CLOCK_EVENT,
        provenance_json=PROV_EVENT,
        observed_at_us=100,
        from_target_json=canonical(REPO_1),
        to_target_json=canonical(REPO_2),
        from_provider_repository=KEY_PROV_REPO_1,
        to_provider_repository=KEY_PROV_REPO_2,
        parent_report=make_parent_report(),
    )

    with pytest.raises(UnsupportedResourceStage) as exc:
        store.admit_transfer_event(report)
    assert "admit_transfer_event requires reviewed I3-I5 support" in str(exc.value)

    with pytest.raises(UnsupportedResourceStage) as exc:
        store.transfer_event_reports()
    assert "transfer_event_reports requires reviewed I3-I5 support" in str(exc.value)

    endpoint = ResourceRepositoryRelation(
        KEY_EVENT_7,
        "transfer_from_repository",
        CLOCK_EVENT,
        canonical(REPO_1),
        PROV_EVENT,
        100,
    )
    with pytest.raises(
        UnsupportedResourceStage, match="requires reviewed I3-I5 support"
    ):
        store.admit_repository_relation(endpoint)


def test_admit_transfer_event_2sided_success(isolated_db):
    store = ContextStore(isolated_db)
    _setup_base_records(isolated_db)

    report = TransferEventReport.from_targets(
        KEY_EVENT_7,
        clock=CLOCK_EVENT,
        provenance_json=PROV_EVENT,
        observed_at_us=100,
        from_target_json=canonical(REPO_1),
        to_target_json=canonical(REPO_2),
        from_provider_repository=KEY_PROV_REPO_1,
        to_provider_repository=KEY_PROV_REPO_2,
        parent_report=make_parent_report(),
    )

    outcome = store.admit_transfer_event(report)
    assert outcome == "insert"

    rep_row = isolated_db.execute(
        "SELECT members_json, scope_json, observed_at_us FROM resource_relations WHERE relation_kind='transfer_event_report'"
    ).fetchone()
    assert rep_row is not None
    assert rep_row[0] == report.members_json
    assert rep_row[1] == report.scope_json
    assert rep_row[2] == 100

    ep_rows = isolated_db.execute(
        "SELECT relation_kind, target_json, event_report_members_json, event_report_scope_json FROM resource_repository_relations WHERE relation_kind IN ('transfer_from_repository','transfer_to_repository') ORDER BY relation_kind"
    ).fetchall()
    assert len(ep_rows) == 2
    assert ep_rows[0][0] == "transfer_from_repository"
    assert ep_rows[0][1] == canonical(REPO_1)
    assert ep_rows[0][2] == report.members_json
    assert ep_rows[0][3] == report.scope_json

    assert ep_rows[1][0] == "transfer_to_repository"
    assert ep_rows[1][1] == canonical(REPO_2)
    assert ep_rows[1][2] == report.members_json
    assert ep_rows[1][3] == report.scope_json

    reconstructed = store.transfer_event_reports(KEY_EVENT_7)
    assert len(reconstructed) == 1
    assert reconstructed[0] == report


def test_admit_transfer_event_via_production_context(tmp_path):
    catalog = tmp_path / "production"
    catalog.mkdir()
    p1_schema.initialize(catalog / "context.sqlite3", "context", REPO_1, SERVICE)

    db = p1_schema.connect(catalog / "context.sqlite3", "context")
    for fence in FENCES:
        db.execute(f"DROP TRIGGER {fence}")

    db.execute("BEGIN IMMEDIATE")
    facade = Context(db, catalog, writable=True)
    try:
        _setup_base_records(facade.db)
        report = TransferEventReport.from_targets(
            KEY_EVENT_7,
            clock=CLOCK_EVENT,
            provenance_json=PROV_EVENT,
            observed_at_us=100,
            from_target_json=canonical(REPO_1),
            to_target_json=canonical(REPO_2),
            from_provider_repository=KEY_PROV_REPO_1,
            to_provider_repository=KEY_PROV_REPO_2,
            parent_report=make_parent_report(),
        )

        assert facade.admit_transfer_event(report) == "insert"
        reports = facade.transfer_event_reports(KEY_EVENT_7)
        assert len(reports) == 1
        assert reports[0] == report
        db.execute("COMMIT")
    finally:
        db.close()


def test_g3a_permanent_violation_mismatched_parent_issue(isolated_db):
    store = ContextStore(isolated_db)
    _setup_base_records(isolated_db)

    _setup_base_records(
        isolated_db,
        issue_key=KEY_ISSUE_8,
        event_key=KEY_EVENT_8,
    )

    i8_parent_exists = isolated_db.execute(
        "SELECT 1 FROM resource_relations WHERE relation_kind='parent' AND members_json=?",
        (_parent_members(KEY_ISSUE_8),),
    ).fetchone()
    assert i8_parent_exists is not None

    invalid_report = TransferEventReport.from_targets(
        KEY_EVENT_7,
        clock=CLOCK_EVENT,
        provenance_json=PROV_EVENT,
        observed_at_us=100,
        from_target_json=canonical(REPO_1),
        to_target_json=canonical(REPO_2),
        from_provider_repository=KEY_PROV_REPO_1,
        to_provider_repository=KEY_PROV_REPO_2,
        parent_members_json=_parent_members(KEY_ISSUE_8),
        parent_provenance_json=PROV_PARENT,
        parent_scope_json=_parent_scope(),
    )

    with pytest.raises(ValueError, match="G3=A permanent violation"):
        store.admit_transfer_event(invalid_report)

    assert (
        isolated_db.execute(
            "SELECT 1 FROM resource_relations WHERE relation_kind='parent' AND members_json=?",
            (_parent_members(KEY_ISSUE_8),),
        ).fetchone()
        is not None
    )

    assert (
        isolated_db.execute(
            "SELECT 1 FROM resource_relations WHERE relation_kind='transfer_event_report'"
        ).fetchone()
        is None
    )
    assert (
        isolated_db.execute(
            "SELECT 1 FROM resource_repository_relations WHERE relation_kind IN ('transfer_from_repository','transfer_to_repository')"
        ).fetchone()
        is None
    )


def test_dependency_missing_resupply_succeeds(isolated_db):
    store = ContextStore(isolated_db)

    _setup_base_records(
        isolated_db,
        register_event=False,
        register_issue=False,
        register_parent_report=False,
        register_repos=False,
        register_prov_repos=False,
    )

    report = TransferEventReport.from_targets(
        KEY_EVENT_7,
        clock=CLOCK_EVENT,
        provenance_json=PROV_EVENT,
        observed_at_us=100,
        from_target_json=canonical(REPO_1),
        to_target_json=canonical(REPO_2),
        from_provider_repository=KEY_PROV_REPO_1,
        to_provider_repository=KEY_PROV_REPO_2,
        parent_report=make_parent_report(),
    )

    with pytest.raises(ValueError, match="Missing dependency: Event resource"):
        store.admit_transfer_event(report)

    _setup_base_records(
        isolated_db,
        register_event=True,
        register_issue=False,
        register_parent_report=False,
        register_repos=False,
        register_prov_repos=False,
    )

    with pytest.raises(ValueError, match="Missing dependency: Parent Issue resource"):
        store.admit_transfer_event(report)

    _setup_base_records(
        isolated_db,
        register_event=True,
        register_issue=True,
        register_parent_report=False,
        register_repos=False,
        register_prov_repos=False,
    )

    with pytest.raises(ValueError, match="Missing dependency: eligible Parent report"):
        store.admit_transfer_event(report)

    _setup_base_records(
        isolated_db,
        register_event=True,
        register_issue=True,
        register_parent_report=True,
        register_repos=False,
        register_prov_repos=False,
    )

    with pytest.raises(
        ValueError, match="Missing dependency: from_provider_repository"
    ):
        store.admit_transfer_event(report)

    _setup_base_records(
        isolated_db,
        register_event=True,
        register_issue=True,
        register_parent_report=True,
        register_repos=False,
        register_prov_repos=True,
    )

    with pytest.raises(ValueError, match="Missing dependency: repository_uuidv4"):
        store.admit_transfer_event(report)

    _setup_base_records(
        isolated_db,
        register_event=True,
        register_issue=True,
        register_parent_report=True,
        register_repos=True,
        register_prov_repos=True,
    )

    assert (
        isolated_db.execute(
            "SELECT 1 FROM resource_relations WHERE relation_kind='transfer_event_report'"
        ).fetchone()
        is None
    )

    outcome = store.admit_transfer_event(report)
    assert outcome == "insert"


def test_mapping_support_dependency(isolated_db):
    store = ContextStore(isolated_db)
    _setup_base_records(isolated_db, register_mapping_support=False)

    support_1 = _make_mapping_support(KEY_PROV_REPO_1, REPO_1)
    prov_with_support = canonical(
        {
            "source": "event-orig",
            "evidence": {
                "transfer_mapping_supports": [
                    {
                        "relation_kind": "transfer_from_repository",
                        "target_json": canonical(REPO_1),
                        "mapping_support": support_1.to_dict(),
                    }
                ]
            },
        }
    )

    rel_from = ResourceRepositoryRelation(
        KEY_EVENT_7,
        "transfer_from_repository",
        CLOCK_EVENT,
        canonical(REPO_1),
        prov_with_support,
        100,
    )
    rel_to = ResourceRepositoryRelation(
        KEY_EVENT_7,
        "transfer_to_repository",
        CLOCK_EVENT,
        canonical(REPO_2),
        prov_with_support,
        100,
    )

    report = TransferEventReport(
        EventReportKey(KEY_EVENT_7, CLOCK_EVENT, prov_with_support),
        100,
        from_relations=(rel_from,),
        to_relations=(rel_to,),
        from_provider_repository=KEY_PROV_REPO_1,
        to_provider_repository=KEY_PROV_REPO_2,
        parent_report=make_parent_report(),
    )

    with pytest.raises(
        ValueError, match="Missing dependency: supporting MappingClaimKey absent"
    ):
        store.admit_transfer_event(report)

    _setup_base_records(isolated_db, register_mapping_support=True)
    assert store.admit_transfer_event(report) == "insert"


def test_provider_event_meaning_and_type(isolated_db):
    _setup_base_records(isolated_db)

    with pytest.raises(ValueError, match="requires genuine event_type='transferred'"):
        TransferEventReport.from_targets(
            KEY_EVENT_7,
            clock=CLOCK_EVENT,
            provenance_json=PROV_EVENT,
            observed_at_us=100,
            from_target_json=canonical(REPO_1),
            event_type="renamed",
            parent_report=make_parent_report(),
        )

    with pytest.raises(ValueError, match="requires genuine event_type='transferred'"):
        TransferEventReport.from_targets(
            KEY_EVENT_7,
            clock=CLOCK_EVENT,
            provenance_json=PROV_EVENT,
            observed_at_us=100,
            from_target_json=canonical(REPO_1),
            event_type="closed",
            parent_report=make_parent_report(),
        )


def test_prebind_type_strictness(isolated_db):
    _setup_base_records(isolated_db)

    with pytest.raises((TypeError, ValueError)):
        TransferEventReport.from_targets(
            KEY_EVENT_7,
            clock=CLOCK_EVENT,
            provenance_json=PROV_EVENT,
            observed_at_us=True,
            from_target_json=canonical(REPO_1),
            parent_report=make_parent_report(),
        )

    with pytest.raises((TypeError, ValueError)):
        TransferEventReport.from_targets(
            KEY_EVENT_7,
            clock=CLOCK_EVENT,
            provenance_json=PROV_EVENT,
            observed_at_us=123.45,
            from_target_json=canonical(REPO_1),
            parent_report=make_parent_report(),
        )

    with pytest.raises((TypeError, ValueError)):
        TransferEventReport.from_targets(
            KEY_EVENT_7,
            clock=CLOCK_EVENT,
            provenance_json=PROV_EVENT,
            observed_at_us="100",
            from_target_json=canonical(REPO_1),
            parent_report=make_parent_report(),
        )

    with pytest.raises((TypeError, ValueError)):
        FieldClock("event", True)

    with pytest.raises((TypeError, ValueError)):
        FieldClock("event", 12.3)

    with pytest.raises((TypeError, ValueError)):
        FieldClock("event", -1)


def test_atomicity_second_endpoint_failure_rolls_back(isolated_db):
    store = ContextStore(isolated_db)
    _setup_base_records(isolated_db)

    unregistered_repo = "11111111-2222-4333-8444-555555555555"

    report = TransferEventReport.from_targets(
        KEY_EVENT_7,
        clock=CLOCK_EVENT,
        provenance_json=PROV_EVENT,
        observed_at_us=100,
        from_target_json=canonical(REPO_1),
        to_target_json=canonical(unregistered_repo),
        from_provider_repository=KEY_PROV_REPO_1,
        to_provider_repository=KEY_PROV_REPO_2,
        parent_report=make_parent_report(),
    )

    with pytest.raises(ValueError, match="Missing dependency: repository_uuidv4"):
        store.admit_transfer_event(report)

    assert (
        isolated_db.execute(
            "SELECT 1 FROM resource_relations WHERE relation_kind='transfer_event_report'"
        ).fetchone()
        is None
    )
    assert (
        isolated_db.execute(
            "SELECT 1 FROM resource_repository_relations WHERE relation_kind IN ('transfer_from_repository','transfer_to_repository')"
        ).fetchone()
        is None
    )


def test_replay_idempotency_and_mutation_rejection(isolated_db):
    store = ContextStore(isolated_db)
    _setup_base_records(isolated_db)

    report = TransferEventReport.from_targets(
        KEY_EVENT_7,
        clock=CLOCK_EVENT,
        provenance_json=PROV_EVENT,
        observed_at_us=100,
        from_target_json=canonical(REPO_1),
        to_target_json=canonical(REPO_2),
        from_provider_repository=KEY_PROV_REPO_1,
        to_provider_repository=KEY_PROV_REPO_2,
        parent_report=make_parent_report(),
    )

    assert store.admit_transfer_event(report) == "insert"
    assert store.admit_transfer_event(report) == "duplicate"

    mutated_time_report = TransferEventReport.from_targets(
        KEY_EVENT_7,
        clock=CLOCK_EVENT,
        provenance_json=PROV_EVENT,
        observed_at_us=200,
        from_target_json=canonical(REPO_1),
        to_target_json=canonical(REPO_2),
        from_provider_repository=KEY_PROV_REPO_1,
        to_provider_repository=KEY_PROV_REPO_2,
        parent_report=make_parent_report(),
    )

    with pytest.raises(
        ValueError, match="Transfer report original payload/time rebind"
    ):
        store.admit_transfer_event(mutated_time_report)

    mutated_target_report = TransferEventReport.from_targets(
        KEY_EVENT_7,
        clock=CLOCK_EVENT,
        provenance_json=PROV_EVENT,
        observed_at_us=100,
        from_target_json=canonical(REPO_1),
        to_target_json=canonical(REPO_3),
        from_provider_repository=KEY_PROV_REPO_1,
        to_provider_repository=KEY_PROV_REPO_2,
        parent_report=make_parent_report(),
    )

    with pytest.raises(
        ValueError, match="Transfer report original payload/time rebind"
    ):
        store.admit_transfer_event(mutated_target_report)


def test_selection_and_truncation_rejection(isolated_db):
    store = ContextStore(isolated_db)
    _setup_base_records(isolated_db)

    report = TransferEventReport.from_targets(
        KEY_EVENT_7,
        clock=CLOCK_EVENT,
        provenance_json=PROV_EVENT,
        observed_at_us=100,
        from_target_json=canonical(REPO_1),
        to_target_json=canonical(REPO_2),
        from_provider_repository=KEY_PROV_REPO_1,
        to_provider_repository=KEY_PROV_REPO_2,
        parent_report=make_parent_report(),
    )

    selected = report.select_for_repositories([REPO_1])
    assert selected is not None
    assert selected.selection_truncated or selected.omitted_roles

    with pytest.raises(ValueError, match="(Selection truncated|Omitted roles)"):
        store.admit_transfer_event(selected)


def test_genuine_1sided_and_explicit_null_admission(isolated_db):
    store = ContextStore(isolated_db)
    _setup_base_records(isolated_db)

    one_sided_report = TransferEventReport.from_targets(
        KEY_EVENT_7,
        clock=CLOCK_EVENT,
        provenance_json=PROV_EVENT,
        observed_at_us=100,
        from_target_json=canonical(REPO_1),
        to_target_json=None,
        from_provider_repository=KEY_PROV_REPO_1,
        to_provider_repository=None,
        parent_report=make_parent_report(),
    )
    assert one_sided_report.is_one_sided
    assert store.admit_transfer_event(one_sided_report) == "insert"

    reconstructed = store.transfer_event_reports(KEY_EVENT_7)
    assert len(reconstructed) == 1
    assert reconstructed[0] == one_sided_report


def test_explicit_null_admission(isolated_db):
    store = ContextStore(isolated_db)
    _setup_base_records(isolated_db)

    null_report = TransferEventReport.from_targets(
        KEY_EVENT_7,
        clock=CLOCK_EVENT,
        provenance_json=PROV_EVENT,
        observed_at_us=100,
        from_target_json="null",
        to_target_json=canonical(REPO_2),
        from_provider_repository=None,
        to_provider_repository=KEY_PROV_REPO_2,
        parent_report=make_parent_report(),
    )
    assert store.admit_transfer_event(null_report) == "insert"

    reconstructed = store.transfer_event_reports(KEY_EVENT_7)
    assert len(reconstructed) == 1
    assert reconstructed[0] == null_report
    assert reconstructed[0].from_state == "explicit_null"
    assert reconstructed[0].to_state == "resolved"


def test_transfer_event_reports_filtering_and_no_cross_borrowing(isolated_db):
    store = ContextStore(isolated_db)
    _setup_base_records(isolated_db)

    clock_a = FieldClock("event-clock", 100)
    clock_b = FieldClock("event-clock", 200)

    report_a = TransferEventReport.from_targets(
        KEY_EVENT_7,
        clock=clock_a,
        provenance_json=canonical({"source": "event-a", "evidence": [1]}),
        observed_at_us=100,
        from_target_json=canonical(REPO_1),
        to_target_json=canonical(REPO_2),
        from_provider_repository=KEY_PROV_REPO_1,
        to_provider_repository=KEY_PROV_REPO_2,
        parent_report=make_parent_report(),
    )

    report_b = TransferEventReport.from_targets(
        KEY_EVENT_7,
        clock=clock_b,
        provenance_json=canonical({"source": "event-b", "evidence": [2]}),
        observed_at_us=200,
        from_target_json=canonical(REPO_2),
        to_target_json=canonical(REPO_3),
        from_provider_repository=KEY_PROV_REPO_1,
        to_provider_repository=KEY_PROV_REPO_2,
        parent_report=make_parent_report(),
    )

    assert store.admit_transfer_event(report_a) == "insert"
    assert store.admit_transfer_event(report_b) == "insert"

    all_reports = store.transfer_event_reports()
    assert len(all_reports) == 2
    assert all_reports[0] == report_a
    assert all_reports[1] == report_b

    r1_reports = store.transfer_event_reports(repository_uuidv4=REPO_1)
    assert len(r1_reports) == 1
    assert r1_reports[0] == report_a

    r3_reports = store.transfer_event_reports(repository_uuidv4=REPO_3)
    assert len(r3_reports) == 1
    assert r3_reports[0] == report_b

    selected_reports = store.transfer_event_reports(selected_repositories=[REPO_1])
    assert len(selected_reports) == 1
    assert selected_reports[0].report_key == report_a.report_key
    assert selected_reports[0].has_selection_omission
    assert selected_reports[0].omitted_roles == frozenset({"transfer_to_repository"})
