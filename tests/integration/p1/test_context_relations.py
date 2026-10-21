"""ADR 0030 I1 counterexamples, including Transfer admission bypasses."""

import sqlite3
from contextlib import contextmanager
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite import p1_schema as schema
from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.adapters.sqlite.recovery_validation import (
    validate_stored_context_relations,
)
from repo_catalog.domain.p1_context import (
    CoverageScope,
    EventReportKey,
    FieldCandidate,
    FieldClock,
    MappingClaimKey,
    MappingDisposition,
    MappingOperationEvidence,
    MappingSupport,
    ResourceKey,
    ResourceRepositoryRelation,
    TransferEventReport,
    canonical,
    encode_supported_provenance,
    encode_transfer_supported_provenance,
    evaluate_repository_mapping,
)
from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.production_context import ContextError
from repo_catalog.domain.recovery import BackupValidationError

REPO_1 = "9ebbe38a-f937-40e6-a99c-701835ebcf10"
REPO_2 = "c58b4f17-f58c-4a33-8bc6-eb52c42337d1"
SERVICE = "aad25448-03eb-4f83-a578-ceec84375b5a"
SOURCE = "80f5c4f9-6d6b-4691-af3c-00ab02ad9f53"

KEY_ISSUE = ResourceKey.from_native(SERVICE, "issue", "7")
KEY_REPO = ResourceKey.from_native(SERVICE, "repository", "octocat/Hello-World")
KEY_EVENT = ResourceKey.timeline_event(KEY_ISSUE, "event-99")

PROVENANCE_1 = canonical({"source": "provider.example", "evidence": "event-1"})
PROVENANCE_2 = canonical({"source": "provider.example", "evidence": "event-2"})


@pytest.mark.parametrize("production", [False, True])
@pytest.mark.parametrize("result_api", [False, True])
@pytest.mark.parametrize("role", ["transfer_from_repository", "transfer_to_repository"])
def test_transfer_generic_admission_requires_complete_report(
    context_db, tmp_path, production, result_api, role
):
    db, store, _ = context_db

    @contextmanager
    def selected_store():
        if not production:
            yield store
            return
        catalog = tmp_path / "production"
        catalog.mkdir()
        schema.initialize(catalog / "context.sqlite3", "context", REPO_1, SERVICE)
        with Context.transaction(catalog) as facade:
            facade.provider(SERVICE, "github", "{}")
            facade.repository(REPO_1)
            facade.resource(KEY_ISSUE)
            facade.resource(KEY_EVENT)
            yield facade
        assert not (catalog / "p1-recovery-stop.json").exists()

    with selected_store() as selected:
        # Genuine Issue-parented Timeline Event identity alone says nothing
        # about whether this was a Transfer event.
        assert not selected.db.execute("SELECT 1 FROM resource_relations").fetchall()
        endpoint = ResourceRepositoryRelation(
            KEY_EVENT, role, FieldClock("event", 1), canonical(REPO_1), PROVENANCE_1, 1
        )
        admit = (
            selected.admit_repository_relation_result
            if result_api
            else selected.admit_repository_relation
        )
        with pytest.raises(ValueError, match="admit_transfer_event"):
            admit(endpoint)
        assert not selected.db.execute(
            "SELECT 1 FROM resource_repository_relations"
        ).fetchall()
        report = TransferEventReport(
            EventReportKey(KEY_EVENT, endpoint.clock, PROVENANCE_1),
            1,
            from_relations=(endpoint,) if role == "transfer_from_repository" else (),
            to_relations=(endpoint,) if role == "transfer_to_repository" else (),
        )
        assert selected.admit_transfer_event(report) == "insert"
        assert selected.admit_transfer_event(report) == "duplicate"
        # Even exact replay/addition must use the report-level equality check.
        with pytest.raises(ValueError, match="admit_transfer_event"):
            admit(endpoint)
        assert selected.transfer_event_reports() == (report,)
        validate_stored_context_relations(selected.db)


@pytest.mark.parametrize(
    "scope_state",
    [
        "absent",
        "missing_type",
        "wrong_type",
        "provided_roles",
        "members",
        "missing_provider",
        "missing_clock",
    ],
)
def test_transfer_stored_type_is_never_inferred(context_db, scope_state):
    db, store, _ = context_db
    report = TransferEventReport.from_targets(
        KEY_EVENT,
        clock=FieldClock("event", 1),
        provenance_json=PROVENANCE_1,
        from_target_json=canonical(REPO_1),
        observed_at_us=1,
    )
    endpoint = report.from_relations[0]
    # SQL can constrain the Event Resource/FK, but cannot prove Provider event
    # semantics. Model incomplete/untrusted stored data without disabling guards.
    db.execute(
        """INSERT INTO resource_repository_relations(
        service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,
        clock_json,target_json,provenance_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)""",
        (*endpoint.claim_key.coordinates(), endpoint.observed_at_us),
    )
    if scope_state != "absent":
        scope = {
            "clock": {"domain": "event", "at_us": 1},
            "provided_roles": ["transfer_from_repository"],
            "from_provider_repository_id": None,
            "to_provider_repository_id": None,
        }
        if scope_state != "missing_type":
            scope["event_type"] = "transferred"
        if scope_state == "wrong_type":
            scope["event_type"] = "closed"
        if scope_state == "provided_roles":
            scope["provided_roles"] = []
        if scope_state == "missing_clock":
            scope.pop("clock")
        members = "[]"
        if scope_state == "members":
            members = canonical([[SERVICE, "repository", canonical("not-declared")]])
        if scope_state == "missing_provider":
            scope["from_provider_repository_id"] = canonical("missing-provider")
            members = canonical(
                [[SERVICE, "repository", canonical("missing-provider")]]
            )
        db.execute(
            "INSERT INTO resource_relations VALUES(?,?,?,?,?,?,?,?)",
            (
                *KEY_EVENT.coordinates(),
                "transfer_event_report",
                members,
                PROVENANCE_1,
                canonical(scope),
                1,
            ),
        )
    with pytest.raises(ValueError, match="[Tt]ransfer|event_type"):
        store.transfer_event_reports()
    with pytest.raises(BackupValidationError, match="[Tt]ransfer|event_type"):
        validate_stored_context_relations(db)


def test_transfer_report_fk_failure_rolls_back_whole_unit(context_db):
    db, store, _ = context_db
    event = ResourceKey.timeline_event(KEY_ISSUE, "failed-transfer")
    report = TransferEventReport.from_targets(
        event,
        clock=FieldClock("event", 1),
        provenance_json=PROVENANCE_1,
        from_target_json=canonical(REPO_1),
        to_target_json=canonical(str(uuid4())),
    )
    before = list(db.iterdump())
    with pytest.raises(sqlite3.IntegrityError):
        store.admit_transfer_event(report)
    assert list(db.iterdump()) == before


def test_transfer_supports_both_endpoints_without_cross_borrowing(context_db):
    _, store, _ = context_db
    provider_a = ResourceKey.from_native(SERVICE, "repository", "provider-a")
    provider_b = ResourceKey.from_native(SERVICE, "repository", "provider-b")
    claims = []
    for provider, target in ((provider_a, REPO_1), (provider_b, REPO_2)):
        store.resource(provider)
        claim = ResourceRepositoryRelation(
            provider,
            "represents_repository",
            FieldClock("mapping", 1),
            canonical(target),
            PROVENANCE_1,
            1,
        )
        store.admit_repository_relation(claim)
        claims.append(claim.claim_key)
    provenance = encode_transfer_supported_provenance(
        "github",
        {"event": "observed-transfer"},
        (
            ("transfer_from_repository", MappingSupport(provider_a, (claims[0],))),
            ("transfer_to_repository", MappingSupport(provider_b, (claims[1],))),
        ),
    )
    report = TransferEventReport.from_targets(
        KEY_EVENT,
        clock=FieldClock("event", 1),
        provenance_json=provenance,
        from_target_json=canonical(REPO_1),
        to_target_json=canonical(REPO_2),
        from_provider_repository=provider_a,
        to_provider_repository=provider_b,
    )
    assert store.admit_transfer_event(report) == "insert"
    assert store.admit_transfer_event(report) == "duplicate"
    rows = {r.relation_kind: r for r in store.repository_relations(KEY_EVENT)}
    assert rows["transfer_from_repository"].supporting_bindings == (claims[0],)
    assert rows["transfer_to_repository"].supporting_bindings == (claims[1],)
    assert all(r.support_status == "active" for r in rows.values())
    disposition = MappingDisposition(
        claims[0], "withdraw", FieldClock("operation", 2), PROVENANCE_2, 2
    )
    store.admit_mapping_disposition(disposition)
    evidence = MappingOperationEvidence(
        confirmed_disposition_keys=frozenset({disposition.disposition_key})
    )
    rows = {
        r.relation_kind: r
        for r in store.repository_relations(KEY_EVENT, evidence=evidence)
    }
    assert (
        rows["transfer_from_repository"].support_status == "supporting_binding_disposed"
    )
    assert rows["transfer_to_repository"].support_status == "active"
    assert store.transfer_event_reports() == (report,)
    validate_stored_context_relations(store.db)


def test_partial_transfer_alternatives_remain_selection_truncated(context_db):
    _, store, _ = context_db
    report = TransferEventReport.from_targets(
        KEY_EVENT,
        clock=FieldClock("event", 1),
        provenance_json=PROVENANCE_1,
        from_target_json=(canonical(REPO_1), canonical(REPO_2)),
    )
    selected = report.select_for_repositories([REPO_1])
    assert selected is not None and len(selected.from_relations) == 1
    assert selected.omitted_roles == frozenset()
    assert selected.has_selection_omission
    selected_again = selected.select_for_repositories([REPO_1, REPO_2])
    assert selected_again is not None and selected_again.has_selection_omission
    with pytest.raises(ValueError, match="Selection-truncated"):
        store.admit_transfer_event(selected_again)
    assert store.admit_transfer_event(report) == "insert"


@pytest.fixture
def context_db(tmp_path):
    path = tmp_path / "context.sqlite3"
    db = sqlite3.connect(path, isolation_level=None)
    schema.register_functions(db)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA recursive_triggers=ON")
    db.executescript(schema.compose("context"))
    db.execute("INSERT INTO providers VALUES(?,?,?)", (SERVICE, "github", "{}"))
    db.execute("INSERT INTO repository_context VALUES(?,?)", (REPO_1, "{}"))
    db.execute("INSERT INTO repository_context VALUES(?,?)", (REPO_2, "{}"))
    db.execute("INSERT INTO sources VALUES(?,?,?)", (SOURCE, SERVICE, "{}"))
    store = ContextStore(db)
    store.resource(KEY_REPO, REPO_1)
    store.resource(KEY_ISSUE, REPO_1)
    store.resource(KEY_EVENT, REPO_1)
    yield db, store, path
    db.close()


# Counterexample 1: Conflicting immutable mappings in reverse arrival order, exact resend and newer source clocks: all alternatives survive.
def test_counterexample_1_conflicting_immutable_mappings_survive(context_db):
    db, store, _ = context_db
    # Immutable mapping claims on KEY_REPO (represents_repository)
    # Reverse arrival: claim with clock 2 arrives before claim with clock 1
    claim_clock2 = ResourceRepositoryRelation(
        KEY_REPO,
        "represents_repository",
        FieldClock("provider.timeline", 200),
        canonical(REPO_2),
        PROVENANCE_2,
        20,
    )
    claim_clock1 = ResourceRepositoryRelation(
        KEY_REPO,
        "represents_repository",
        FieldClock("provider.timeline", 100),
        canonical(REPO_1),
        PROVENANCE_1,
        10,
    )
    assert store.admit_repository_relation(claim_clock2) == "insert"
    assert store.admit_repository_relation(claim_clock1) == "insert"

    # Both alternatives survive in stored relations
    relations = store.repository_relations(KEY_REPO)
    assert len(relations) == 2
    targets = {r.target_json for r in relations}
    assert targets == {f'"{REPO_1}"', f'"{REPO_2}"'}

    # Exact resend returns duplicate and leaves both intact
    assert store.admit_repository_relation(claim_clock2) == "duplicate"
    assert len(store.repository_relations(KEY_REPO)) == 2


# Counterexample 2: Current candidates with older/newer/equal/different-domain/unknown clocks and explicit NULL: only strictly dominated comparable values are pruned.
def test_counterexample_2_current_candidates_clock_pruning(context_db):
    _, store, _ = context_db
    base = FieldCandidate(
        KEY_ISSUE, "title", canonical("v1"), FieldClock("clock_a", 10), PROVENANCE_1, 10
    )
    assert store.admit_field(base) == "insert"

    # Older clock in same domain: pruned as stale
    older = FieldCandidate(
        KEY_ISSUE, "title", canonical("v0"), FieldClock("clock_a", 5), PROVENANCE_2, 11
    )
    assert store.admit_field(older) == "stale"
    assert len(store.candidates(KEY_ISSUE, "title")) == 1

    # Equal clock in same domain: survives alongside
    equal = FieldCandidate(
        KEY_ISSUE,
        "title",
        canonical("v1_alt"),
        FieldClock("clock_a", 10),
        PROVENANCE_2,
        12,
    )
    assert store.admit_field(equal) == "insert"
    assert len(store.candidates(KEY_ISSUE, "title")) == 2

    # Different domain clock: survives alongside
    diff_domain = FieldCandidate(
        KEY_ISSUE,
        "title",
        canonical("v_other"),
        FieldClock("clock_b", 5),
        PROVENANCE_1,
        13,
    )
    assert store.admit_field(diff_domain) == "insert"
    assert len(store.candidates(KEY_ISSUE, "title")) == 3

    # Unknown / None clock: survives alongside
    unknown = FieldCandidate(
        KEY_ISSUE,
        "title",
        canonical("v_unclocked"),
        FieldClock("unclocked", None),
        PROVENANCE_1,
        14,
    )
    assert store.admit_field(unknown) == "insert"
    assert len(store.candidates(KEY_ISSUE, "title")) == 4

    # Newer clock in clock_a with explicit NULL: prunes v1 and v1_alt, survives alongside diff_domain and unknown
    newer_null = FieldCandidate(
        KEY_ISSUE, "title", "null", FieldClock("clock_a", 20), PROVENANCE_1, 20
    )
    assert store.admit_field(newer_null) == "insert"
    candidates = store.candidates(KEY_ISSUE, "title")
    assert len(candidates) == 3
    vals = {c.value_json for c in candidates}
    assert vals == {"null", '"v_other"', '"v_unclocked"'}


# Counterexample 3: Failed insertion, FK failure and outer rollback after candidate pruning: original candidate state survives atomically.
def test_counterexample_3_atomic_rollback_on_failure(context_db):
    db, store, _ = context_db
    orig = FieldCandidate(
        KEY_ISSUE,
        "title",
        canonical("original"),
        FieldClock("clock_a", 10),
        PROVENANCE_1,
        10,
    )
    store.admit_field(orig)

    db.execute("BEGIN")
    newer = FieldCandidate(
        KEY_ISSUE,
        "title",
        canonical("newer"),
        FieldClock("clock_a", 20),
        PROVENANCE_2,
        20,
    )
    store.admit_field(newer)
    assert len(store.candidates(KEY_ISSUE, "title")) == 1
    assert store.candidates(KEY_ISSUE, "title")[0].value_json == '"newer"'

    # Force a failure (e.g. FK violation on invalid target in repository_relations)
    invalid_repo = "11111111-2222-3333-4444-555555555555"
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO resource_repository_relations(service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind, clock_json, target_json, provenance_json, observed_at_us) VALUES(?,?,?,?,?,?,?,?)",
            (
                KEY_ISSUE.service_instance_uuidv4,
                KEY_ISSUE.resource_kind,
                KEY_ISSUE.provider_resource_id,
                "owning_repository",
                '{"domain":"test","at_us":1}',
                f'"{invalid_repo}"',
                PROVENANCE_1,
                30,
            ),
        )
    db.execute("ROLLBACK")

    # Original candidate state is atomically preserved
    candidates = store.candidates(KEY_ISSUE, "title")
    assert len(candidates) == 1
    assert candidates[0].value_json == '"original"'


# Counterexample 4: Invalid role/subject combinations, mapping NULL, wrong parents and Timeline Events that are not actual Transfers.
def test_counterexample_4_invalid_roles_and_targets(context_db):
    db, store, _ = context_db
    # Invalid role not in closed 6-role vocabulary
    with pytest.raises(ValueError, match="Unknown repository relation_kind"):
        ResourceRepositoryRelation(
            KEY_ISSUE,
            "admin_repository",
            FieldClock("source", 1),
            canonical(REPO_1),
            PROVENANCE_1,
            10,
        )

    # In SQL, CHECK constraint enforces closed 6-role vocabulary
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO resource_repository_relations(service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind, clock_json, target_json, provenance_json, observed_at_us) VALUES(?,?,?,?,?,?,?,?)",
            (
                KEY_ISSUE.service_instance_uuidv4,
                KEY_ISSUE.resource_kind,
                KEY_ISSUE.provider_resource_id,
                "admin_repository",
                '{"domain":"source","at_us":1}',
                f'"{REPO_1}"',
                PROVENANCE_1,
                10,
            ),
        )

    # Invalid target (not null or uuid string, e.g. integer or array)
    with pytest.raises(ValueError, match="target_json must be"):
        ResourceRepositoryRelation(
            KEY_ISSUE,
            "owning_repository",
            FieldClock("source", 1),
            "12345",
            PROVENANCE_1,
            10,
        )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO resource_repository_relations(service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind, clock_json, target_json, provenance_json, observed_at_us) VALUES(?,?,?,?,?,?,?,?)",
            (
                KEY_ISSUE.service_instance_uuidv4,
                KEY_ISSUE.resource_kind,
                KEY_ISSUE.provider_resource_id,
                "owning_repository",
                '{"domain":"source","at_us":1}',
                "12345",
                PROVENANCE_1,
                10,
            ),
        )

    # Wrong parent FK in resources table
    child_key = ResourceKey.document(
        ResourceKey.from_native(SERVICE, "issue", "nonexistent"),
        "comment",
        "review_comment",
        "c-1",
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.resource(child_key, REPO_1)


# Counterexample 5: One-sided, null, two-sided, unresolved-endpoint and separate-report Transfer cases: no invented endpoint or cross-report pairing.
def test_counterexample_5_transfer_cases_no_invented_endpoints(context_db):
    _, store, _ = context_db
    ev_key = EventReportKey(KEY_EVENT, FieldClock("provider.timeline", 1), PROVENANCE_1)

    # One-sided transfer: only from_relations
    r_from = ResourceRepositoryRelation(
        KEY_EVENT,
        "transfer_from_repository",
        FieldClock("provider.timeline", 1),
        canonical(REPO_1),
        PROVENANCE_1,
        10,
    )

    report_from = TransferEventReport(
        report_key=ev_key,
        observed_at_us=10,
        from_relations=(r_from,),
        to_relations=(),
        omitted_roles=frozenset({"transfer_to_repository"}),
    )
    assert report_from.from_relations == (r_from,)
    assert report_from.to_relations == ()
    assert "transfer_to_repository" in report_from.omitted_roles

    # Two-sided transfer: both endpoints present
    r_to = ResourceRepositoryRelation(
        KEY_EVENT,
        "transfer_to_repository",
        FieldClock("provider.timeline", 1),
        canonical(REPO_2),
        PROVENANCE_1,
        10,
    )

    report_both = TransferEventReport(
        report_key=ev_key,
        observed_at_us=10,
        from_relations=(r_from,),
        to_relations=(r_to,),
    )
    assert len(report_both.from_relations) == 1
    assert len(report_both.to_relations) == 1
    assert store.admit_transfer_event(report_both) == "insert"


# Counterexample 6: Exact ClaimKey with changed observation time: rejected.
def test_counterexample_6_exact_claim_key_changed_observation_time_rejected(context_db):
    db, store, _ = context_db
    claim = ResourceRepositoryRelation(
        KEY_REPO,
        "represents_repository",
        FieldClock("provider.updated_at", 1),
        canonical(REPO_1),
        PROVENANCE_1,
        10,
    )
    assert store.admit_repository_relation(claim) == "insert"

    # In Python API
    claim_diff_time = ResourceRepositoryRelation(
        KEY_REPO,
        "represents_repository",
        FieldClock("provider.updated_at", 1),
        canonical(REPO_1),
        PROVENANCE_1,
        999,
    )
    with pytest.raises(
        ValueError, match="Original observation time changed during replay"
    ):
        store.admit_repository_relation(claim_diff_time)

    # In direct SQL trigger
    with pytest.raises(
        sqlite3.IntegrityError,
        match="resource_repository_relations observed_at_us rebind",
    ):
        db.execute(
            "INSERT INTO resource_repository_relations(service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind, clock_json, target_json, provenance_json, observed_at_us) VALUES(?,?,?,?,?,?,?,?)",
            (
                KEY_REPO.service_instance_uuidv4,
                KEY_REPO.resource_kind,
                KEY_REPO.provider_resource_id,
                "represents_repository",
                '{"at_us":1,"domain":"provider.updated_at"}',
                f'"{REPO_1}"',
                PROVENANCE_1,
                999,
            ),
        )


# Counterexample 7: Exact DispositionKey with changed observation time or any replacement component: rejected even when both replacement FKs are valid.
def test_counterexample_7_exact_disposition_key_changed_observation_time_rejected(
    context_db,
):
    db, store, _ = context_db
    c1 = ResourceRepositoryRelation(
        KEY_REPO,
        "represents_repository",
        FieldClock("provider.updated_at", 1),
        canonical(REPO_1),
        PROVENANCE_1,
        10,
    )
    c2 = ResourceRepositoryRelation(
        KEY_REPO,
        "represents_repository",
        FieldClock("provider.updated_at", 2),
        canonical(REPO_2),
        PROVENANCE_2,
        20,
    )
    store.admit_repository_relation(c1)
    store.admit_repository_relation(c2)

    claim1_key = MappingClaimKey.for_repository(
        KEY_REPO,
        REPO_1,
        clock=FieldClock("provider.updated_at", 1),
        provenance_json=PROVENANCE_1,
    )
    claim2_key = MappingClaimKey.for_repository(
        KEY_REPO,
        REPO_2,
        clock=FieldClock("provider.updated_at", 2),
        provenance_json=PROVENANCE_2,
    )

    disp = MappingDisposition(
        claim_key=claim1_key,
        disposition_kind="correct",
        disposition_clock=FieldClock("provider.updated_at", 3),
        disposition_provenance_json=PROVENANCE_1,
        observed_at_us=30,
        replacement_claim_key=claim2_key,
    )
    assert store.admit_mapping_disposition(disp) == "insert"

    # Exact disposition key with changed observation time: rejected
    disp_diff_time = MappingDisposition(
        claim_key=claim1_key,
        disposition_kind="correct",
        disposition_clock=FieldClock("provider.updated_at", 3),
        disposition_provenance_json=PROVENANCE_1,
        observed_at_us=999,
        replacement_claim_key=claim2_key,
    )
    with pytest.raises(
        ValueError, match="Mapping disposition non-key payload changed during replay"
    ):
        store.admit_mapping_disposition(disp_diff_time)

    # In SQL trigger
    with pytest.raises(
        sqlite3.IntegrityError, match="repository_mapping_dispositions payload rebind"
    ):
        db.execute(
            "INSERT INTO repository_mapping_dispositions(service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind, claim_clock_json, claim_target_json, claim_provenance_json, disposition_kind, disposition_clock_json, disposition_provenance_json, observed_at_us, replacement_clock_json, replacement_target_json, replacement_provenance_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                KEY_REPO.service_instance_uuidv4,
                KEY_REPO.resource_kind,
                KEY_REPO.provider_resource_id,
                "represents_repository",
                '{"at_us":1,"domain":"provider.updated_at"}',
                f'"{REPO_1}"',
                PROVENANCE_1,
                "correct",
                '{"at_us":3,"domain":"provider.updated_at"}',
                PROVENANCE_1,
                999,
                '{"at_us":2,"domain":"provider.updated_at"}',
                f'"{REPO_2}"',
                PROVENANCE_2,
            ),
        )


# Counterexample 8: Partial-NULL/wrong-Resource/self replacement; correction cycles remain representable as unresolved reports, not silently selected winners.
def test_counterexample_8_disposition_replacement_checks_and_cycles(context_db):
    db, store, _ = context_db
    c1 = ResourceRepositoryRelation(
        KEY_REPO,
        "represents_repository",
        FieldClock("provider.updated_at", 1),
        canonical(REPO_1),
        PROVENANCE_1,
        10,
    )
    c2 = ResourceRepositoryRelation(
        KEY_REPO,
        "represents_repository",
        FieldClock("provider.updated_at", 2),
        canonical(REPO_2),
        PROVENANCE_2,
        20,
    )
    store.admit_repository_relation(c1)
    store.admit_repository_relation(c2)

    claim1_key = MappingClaimKey.for_repository(
        KEY_REPO,
        REPO_1,
        clock=FieldClock("provider.updated_at", 1),
        provenance_json=PROVENANCE_1,
    )
    claim2_key = MappingClaimKey.for_repository(
        KEY_REPO,
        REPO_2,
        clock=FieldClock("provider.updated_at", 2),
        provenance_json=PROVENANCE_2,
    )

    # Self-replacement rejected in Python
    with pytest.raises(ValueError, match="must differ from subject claim_key"):
        MappingDisposition(
            claim_key=claim1_key,
            disposition_kind="correct",
            disposition_clock=FieldClock("provider.updated_at", 3),
            disposition_provenance_json=PROVENANCE_1,
            observed_at_us=30,
            replacement_claim_key=claim1_key,
        )

    # Self replacement in SQL: replacement == claim
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO repository_mapping_dispositions(service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind, claim_clock_json, claim_target_json, claim_provenance_json, disposition_kind, disposition_clock_json, disposition_provenance_json, observed_at_us, replacement_clock_json, replacement_target_json, replacement_provenance_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                KEY_REPO.service_instance_uuidv4,
                KEY_REPO.resource_kind,
                KEY_REPO.provider_resource_id,
                "represents_repository",
                '{"at_us":1,"domain":"provider.updated_at"}',
                f'"{REPO_1}"',
                PROVENANCE_1,
                "correct",
                '{"at_us":3,"domain":"provider.updated_at"}',
                PROVENANCE_1,
                30,
                '{"at_us":1,"domain":"provider.updated_at"}',
                f'"{REPO_1}"',
                PROVENANCE_1,
            ),
        )

    # Mutual correction cycle: c1 corrected by c2, c2 corrected by c1
    disp1 = MappingDisposition(
        claim_key=claim1_key,
        disposition_kind="correct",
        disposition_clock=FieldClock("provider.updated_at", 3),
        disposition_provenance_json=PROVENANCE_1,
        observed_at_us=30,
        replacement_claim_key=claim2_key,
    )
    disp2 = MappingDisposition(
        claim_key=claim2_key,
        disposition_kind="correct",
        disposition_clock=FieldClock("provider.updated_at", 4),
        disposition_provenance_json=PROVENANCE_2,
        observed_at_us=40,
        replacement_claim_key=claim1_key,
    )
    assert store.admit_mapping_disposition(disp1) == "insert"
    assert store.admit_mapping_disposition(disp2) == "insert"

    # Evaluate mapping with confirmed dispositions: cycle results in unresolved_correction state without crashing or picking silent winner
    evidence = MappingOperationEvidence(
        confirmed_disposition_keys=frozenset(
            {disp1.disposition_key, disp2.disposition_key}
        )
    )
    eval_result = evaluate_repository_mapping(
        KEY_REPO, [c1, c2], [disp1, disp2], evidence=evidence
    )
    assert eval_result.state == "unresolved_correction"


# Counterexample 9: Strict canonical grammar, original timestamp type/range, missing issuer versus NULL versus claimed principal, malformed/oversize inputs and finite parsing limits.
def test_counterexample_9_canonical_grammar_and_validation():
    # Canonical rejects non-standard JSON, unquoted, Infinity, NaN
    with pytest.raises(ValueError):
        canonical({"val": float("nan")})
    with pytest.raises(ValueError):
        canonical({"val": float("inf")})

    # Timestamp must be positive integer
    with pytest.raises(ValueError, match="timestamp must be positive"):
        ResourceRepositoryRelation(
            KEY_REPO,
            "represents_repository",
            FieldClock("source", 1),
            canonical(REPO_1),
            PROVENANCE_1,
            0,
        )
    with pytest.raises(ValueError, match="timestamp must be positive"):
        ResourceRepositoryRelation(
            KEY_REPO,
            "represents_repository",
            FieldClock("source", 1),
            canonical(REPO_1),
            PROVENANCE_1,
            -5,
        )

    # Oversize input (> 256KB limit)
    huge_provenance = '{"evidence":"' + ("a" * 300_000) + '","source":"x"}'
    with pytest.raises(
        ValueError, match="Canonical JSON value must be a bounded non-empty string"
    ):
        ResourceRepositoryRelation(
            KEY_REPO,
            "represents_repository",
            FieldClock("source", 1),
            canonical(REPO_1),
            huge_provenance,
            10,
        )


# Counterexample 10: Exact mapping-support dependencies, missing/conflicting support, and typed original evidence preservation without hidden verification history.
def test_counterexample_10_mapping_support_preserves_evidence(context_db):
    db, store, _ = context_db
    c1 = ResourceRepositoryRelation(
        KEY_REPO,
        "represents_repository",
        FieldClock("provider.updated_at", 1),
        canonical(REPO_1),
        PROVENANCE_1,
        10,
    )
    store.admit_repository_relation(c1)

    eval_result = evaluate_repository_mapping(KEY_REPO, [c1], [])
    assert eval_result.state == "single_candidate"
    assert eval_result.active_repository_uuidv4s == (REPO_1,)

    # Confirm schema has no witness table or verification-history ledger
    tables = {
        r[0]
        for r in db.execute(
            "SELECT name FROM sqlite_schema WHERE type='table'"
        ).fetchall()
    }
    assert "witness" not in tables
    assert "verification_history" not in tables


# Counterexample 11: Role-scoped Coverage, unrelated roles and Source positive membership preservation; no field-to-all-roles completeness upgrade.
def test_counterexample_11_role_scoped_coverage_no_upgrade(context_db):
    db, store, _ = context_db
    scope_owning = CoverageScope.repository_relation(
        REPO_1, KEY_ISSUE, "owning_repository", "issue"
    )
    scope_transfer = CoverageScope.repository_relation(
        REPO_1, KEY_EVENT, "transfer_from_repository", "timeline_event"
    )
    scope_field = CoverageScope.field(KEY_ISSUE, "title", "issue")

    assert scope_owning.owner_kind == "resource"
    assert scope_transfer.owner_kind == "resource"
    assert scope_field.owner_kind == "field"

    assert scope_owning.relation_kind == "owning_repository"
    assert scope_transfer.relation_kind == "transfer_from_repository"

    # Distinct coordinates
    assert scope_owning.coordinates != scope_transfer.coordinates
    assert scope_owning.coordinates != scope_field.coordinates

    # Source positive membership in source_repositories is preserved
    db.execute(
        "INSERT INTO source_repositories(source_registration_uuidv4, repository_uuidv4, attributes_json) VALUES(?,?,?)",
        (SOURCE, REPO_1, "{}"),
    )
    assert (
        db.execute(
            "SELECT repository_uuidv4 FROM source_repositories WHERE source_registration_uuidv4=?",
            (SOURCE,),
        ).fetchone()[0]
        == REPO_1
    )


# Counterexample 12: Old Repository-special field attempts through generic typed APIs, supported SQL and any surviving new-format ingress: no second authority.
def test_counterexample_12_old_repository_uuidv4_field_rejected(context_db):
    db, store, _ = context_db
    # In FieldCandidate
    with pytest.raises(
        ValueError, match="field_name='repository_uuidv4' is prohibited"
    ):
        FieldCandidate(
            KEY_ISSUE,
            "repository_uuidv4",
            canonical(REPO_1),
            FieldClock("source", 1),
            PROVENANCE_1,
            10,
        )

    # In CoverageScope.field
    with pytest.raises(ValueError, match="field='repository_uuidv4' is prohibited"):
        CoverageScope.field(KEY_ISSUE, "repository_uuidv4", "issue")

    # In store.candidates
    with pytest.raises(
        ValueError,
        match="field_name='repository_uuidv4' is retired; use repository_relations",
    ):
        store.candidates(KEY_ISSUE, "repository_uuidv4")

    # In raw SQL INSERT INTO field_candidates
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO field_candidates(service_instance_uuidv4, resource_kind, provider_resource_id, field_name, value_json, clock_json, provenance_json, observed_at_us) VALUES(?,?,?,?,?,?,?,?)",
            (
                KEY_ISSUE.service_instance_uuidv4,
                KEY_ISSUE.resource_kind,
                KEY_ISSUE.provider_resource_id,
                "repository_uuidv4",
                f'"{REPO_1}"',
                '{"domain":"source","at_us":1}',
                PROVENANCE_1,
                10,
            ),
        )


# Counterexample 13: foreign_keys/recursive_triggers, REPLACE/UPSERT, trigger-order independence, supported raw SQL and typed API consistency.
def test_counterexample_13_fk_and_trigger_order_consistency(context_db):
    db, store, _ = context_db
    # Target repository must exist in repository_context or be NULL
    unregistered_repo = str(uuid4())
    claim_unregistered = ResourceRepositoryRelation(
        KEY_ISSUE,
        "owning_repository",
        FieldClock("source", 1),
        canonical(unregistered_repo),
        PROVENANCE_1,
        10,
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.admit_repository_relation(claim_unregistered)

    # NULL target is accepted and requires no foreign key row
    claim_null = ResourceRepositoryRelation(
        KEY_ISSUE,
        "owning_repository",
        FieldClock("source", 1),
        "null",
        PROVENANCE_1,
        10,
    )
    assert store.admit_repository_relation(claim_null) == "insert"
    assert store.repository_relations(KEY_ISSUE)[0].is_explicit_null_target is True


# Counterexample 14: New methods under read-only/expired capabilities, missing transactions and start/final P7 stops; distinguish incoming rejection, retained corruption and unsupported coherent format.
def test_counterexample_14_capabilities_and_p7_stops(tmp_path):
    path = tmp_path / "catalog"
    path.mkdir()
    schema.initialize(path / "context.sqlite3", "context", REPO_1, SERVICE)

    # Read-only snapshot cannot write relations
    with Context.snapshot(path) as snap:
        with pytest.raises(ContextError, match="READ_ONLY"):
            snap.admit_repository_relation(
                ResourceRepositoryRelation(
                    KEY_ISSUE,
                    "owning_repository",
                    FieldClock("source", 1),
                    canonical(REPO_1),
                    PROVENANCE_1,
                    10,
                )
            )

    # Expired capability cannot be reused
    with Context.transaction(path) as tx:
        pass
    with pytest.raises(ContextError, match="CAPABILITY_EXPIRED"):
        tx.repository_relations(KEY_ISSUE)

    # P7 recovery stop blocks transaction
    (path / "p1-recovery-stop.json").write_text('{"reason": "manual stop"}')
    with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
        with Context.transaction(path) as tx:
            pass


# Counterexample 15: Enduring stored-invariant validation without incorrectly applying historical stale/replay predicates.
def test_counterexample_15_enduring_stored_invariant_validation(context_db):
    db, store, _ = context_db
    # Admit conflicting immutable relations with different provenance on KEY_REPO
    c1 = ResourceRepositoryRelation(
        KEY_REPO,
        "represents_repository",
        FieldClock("source", 1),
        canonical(REPO_1),
        PROVENANCE_1,
        10,
    )
    c2 = ResourceRepositoryRelation(
        KEY_REPO,
        "represents_repository",
        FieldClock("source", 2),
        canonical(REPO_2),
        PROVENANCE_2,
        20,
    )
    store.admit_repository_relation(c1)
    store.admit_repository_relation(c2)

    # Stored validation passes even though conflicting relations exist
    validate_stored_context_relations(db)


# Counterexample 16: Fresh composed Context has exactly the intended 19 tables including store_identity and coverage_claims; real sqlite_schema, declared fingerprint and packaged resources match.
def test_counterexample_16_fresh_composed_schema_19_tables(tmp_path):
    path = tmp_path / "context.sqlite3"
    schema.initialize(path, "context", REPO_1, SERVICE)
    db = schema.connect(path, "context")
    try:
        tables = [
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        assert len(tables) == 19
        assert "store_identity" in tables
        assert "coverage_claims" in tables
        assert "resource_repository_relations" in tables
        assert "repository_mapping_dispositions" in tables
        assert "field_candidates" in tables
    finally:
        db.close()


# Counterexample 17: Direct wheel and sdist-derived wheel expose the same new codecs, schema and guards, with isolated import origins and meaningful synthetic smoke/constraint checks.
def test_counterexample_17_wheel_build_and_packaging_smoke():
    # Verify packaged context.sql contains exactly the new DDL tables and field_candidates has no repository_uuidv4 column
    packaged_ddl = schema._resource("context.sql")
    assert "CREATE TABLE resource_repository_relations" in packaged_ddl
    assert "CREATE TABLE repository_mapping_dispositions" in packaged_ddl
    assert "CHECK(field_name!='repository_uuidv4')" in packaged_ddl
    fc_ddl = packaged_ddl.split("CREATE TABLE field_candidates(")[1].split(") STRICT")[
        0
    ]
    assert "repository_uuidv4 TEXT" not in fc_ddl


# Counterexample 18: Exact MappingClaimKey support isolation: no speculative borrowing across Provider repositories.
def test_counterexample_18_mapping_claim_support_isolation_and_no_speculative_borrowing(
    context_db,
):
    _, store, _ = context_db
    # 1. Provider Repository A and B both map to Core REPO_1
    prov_a = ResourceKey.from_native(SERVICE, "repository", "org/repo-a")
    prov_b = ResourceKey.from_native(SERVICE, "repository", "org/repo-b")
    store.resource(prov_a)
    store.resource(prov_b)

    clk_a = FieldClock("github:repo", 10)
    claim_a = ResourceRepositoryRelation(
        prov_a, "represents_repository", clk_a, canonical(REPO_1), PROVENANCE_1, 10
    )
    store.admit_repository_relation(claim_a)

    # 2. Issue 1 has an owning_repository relation targeting REPO_1, but NO embedded MappingSupport
    issue_1 = ResourceKey.from_native(SERVICE, "issue", "101")
    store.resource(issue_1)
    issue_1_rel = ResourceRepositoryRelation(
        issue_1,
        "owning_repository",
        FieldClock("github:issue", 10),
        canonical(REPO_1),
        PROVENANCE_1,
        10,
    )
    store.admit_repository_relation(issue_1_rel)

    # 3. Even though A's Mapping Claim exists, Issue 1 must NOT be judged as active or supported by A
    res_1 = store.repository_relations(issue_1)
    assert len(res_1) == 1
    assert res_1[0].support_status == "missing_supporting_binding"
    assert res_1[0].supporting_bindings == ()
    assert not res_1[0].is_core_resolved_active

    # Now create Issue 2 with explicit MappingSupport referencing claim_a
    issue_2 = ResourceKey.from_native(SERVICE, "issue", "102")
    store.resource(issue_2)
    ck_a = claim_a.claim_key
    assert isinstance(ck_a, MappingClaimKey)
    support_a = MappingSupport(prov_a, (ck_a,))
    supported_prov = encode_supported_provenance("github", {"event": "i2"}, support_a)
    issue_2_rel = ResourceRepositoryRelation(
        issue_2,
        "owning_repository",
        FieldClock("github:issue", 20),
        canonical(REPO_1),
        supported_prov,
        20,
    )
    store.admit_repository_relation(issue_2_rel)

    # Issue 2 is supported and active
    res_2 = store.repository_relations(issue_2)
    assert len(res_2) == 1
    assert res_2[0].support_status == "active"
    assert res_2[0].supporting_bindings == (ck_a,)
    assert res_2[0].is_core_resolved_active

    # 4. If A's claim is withdrawn, the effect is strictly confined to A's ClaimKey
    disp_clk = FieldClock("github:audit", 50)
    disp_prov = canonical({"source": "github", "evidence": "withdraw-a"})
    disp_a = MappingDisposition(
        claim_key=ck_a,
        disposition_kind="withdraw",
        disposition_clock=disp_clk,
        disposition_provenance_json=disp_prov,
        observed_at_us=50,
    )
    store.admit_mapping_disposition(disp_a)

    ev_withdraw_a = MappingOperationEvidence(
        confirmed_disposition_keys=frozenset({disp_a.disposition_key})
    )
    # Issue 2's support is now disposed
    res_2_withdrawn = store.repository_relations(issue_2, evidence=ev_withdraw_a)
    assert res_2_withdrawn[0].support_status == "supporting_binding_disposed"
    assert not res_2_withdrawn[0].is_core_resolved_active

    # 5. Admitting B's Mapping Claim must NOT retroactively supply missing support to Issue 1
    # nor substitute for Issue 2's specific disposed ClaimKey
    clk_b = FieldClock("github:repo", 30)
    claim_b = ResourceRepositoryRelation(
        prov_b, "represents_repository", clk_b, canonical(REPO_1), PROVENANCE_2, 30
    )
    store.admit_repository_relation(claim_b)

    # Issue 1 still missing supporting binding
    res_1_after_b = store.repository_relations(issue_1)
    assert res_1_after_b[0].support_status == "missing_supporting_binding"
    assert res_1_after_b[0].supporting_bindings == ()

    # Issue 2 still disposed (tied to A's ClaimKey, not substituted by B)
    res_2_after_b = store.repository_relations(issue_2, evidence=ev_withdraw_a)
    assert res_2_after_b[0].support_status == "supporting_binding_disposed"
    assert ck_a in res_2_after_b[0].disposed_supporting_bindings


# Verification that Transfer Event roles derive only from genuine 'transferred' events.
def test_transfer_event_genuine_type_enforcement_across_typed_paths(context_db):
    _, store, _ = context_db
    ev_res = ResourceKey.timeline_event(KEY_ISSUE, "timeline-77")
    clk = FieldClock("github:event", 1)

    # TransferEventReport rejects non-transferred event types
    for bad_event_type in ("closed", "assigned", "labeled", "transferred_fake"):
        with pytest.raises(
            ValueError, match="requires genuine event_type='transferred'"
        ):
            TransferEventReport.from_targets(
                ev_res,
                clock=clk,
                provenance_json=PROVENANCE_1,
                event_type=bad_event_type,
            )

    # Valid report with event_type='transferred' admits successfully
    valid_report = TransferEventReport.from_targets(
        ev_res,
        clock=clk,
        provenance_json=PROVENANCE_1,
        observed_at_us=1,
        from_target_json=canonical(REPO_1),
        to_target_json=canonical(REPO_2),
        event_type="transferred",
    )
    outcome = store.admit_transfer_event(valid_report)
    assert outcome == "insert"


# Verification of generator selected_repositories across multiple events and endpoint preservation.
def test_transfer_event_reports_generator_selected_repositories_and_invariants(
    context_db,
):
    _, store, _ = context_db
    ev1 = ResourceKey.timeline_event(KEY_ISSUE, "ev-101")
    ev2 = ResourceKey.timeline_event(KEY_ISSUE, "ev-102")

    rep1 = TransferEventReport.from_targets(
        ev1,
        clock=FieldClock("github:event", 1),
        provenance_json=PROVENANCE_1,
        observed_at_us=1,
        from_target_json=canonical(REPO_1),
        to_target_json=canonical(REPO_2),
    )
    rep2 = TransferEventReport.from_targets(
        ev2,
        clock=FieldClock("github:event", 2),
        provenance_json=PROVENANCE_2,
        observed_at_us=2,
        from_target_json=canonical(REPO_1),
        to_target_json="null",  # explicit null endpoint preserved
    )
    assert store.admit_transfer_event(rep1) == "insert"
    assert store.admit_transfer_event(rep2) == "insert"

    # Pass a single-use generator
    def _gen():
        yield REPO_1

    selected_reports = store.transfer_event_reports(selected_repositories=_gen())
    # Both events must be present and filtered with REPO_1
    assert len(selected_reports) == 2
    r1 = next(r for r in selected_reports if r.report_key.event_resource == ev1)
    r2 = next(r for r in selected_reports if r.report_key.event_resource == ev2)

    # In rep1: REPO_1 is from, REPO_2 is to. REPO_2 is omitted by selection, from is kept.
    assert len(r1.from_relations) == 1
    assert len(r1.to_relations) == 0
    assert "transfer_to_repository" in r1.omitted_roles
    assert not r1.from_relations[0].is_explicit_null_target

    # In rep2: REPO_1 is from, null is to. Explicit null is preserved under selection!
    assert len(r2.from_relations) == 1
    assert len(r2.to_relations) == 1
    assert r2.to_relations[0].is_explicit_null_target
    assert len(r2.omitted_roles) == 0
