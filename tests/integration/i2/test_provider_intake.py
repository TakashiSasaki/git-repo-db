"""I2 Provider observations use frozen I1 keys, never URL/OID/Access identity."""

import json
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.github.production_intake import (
    github_repository_id,
    normalize_issue,
    normalize_timeline_event,
)
from repo_catalog.adapters.sqlite.p1_coordination import persist_catalog_stop
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.acquisition import ProviderAcquisition
from repo_catalog.domain.acquisition import (
    AcquisitionError,
    ProviderIntakeBatch,
    ProviderIssueIntake,
    ProviderPullRequestIntake,
    ProviderRegistration,
    ProviderRepositoryIntake,
    ProviderTimelineIntake,
    RepositoryRegistration,
    make_provenance,
)
from repo_catalog.domain.p1_context import (
    FieldClock,
    MappingDisposition,
    MappingOperationEvidence,
    ProviderRepositoryRoleScope,
    ProviderRepositoryScope,
    QualifiedMappingEvaluation,
    QualifiedProviderRepositoryRole,
    ResourceKey,
    ResourceRepositoryRelation,
    canonical,
)
from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.production_context import ResourceRelation
from repo_catalog.domain.resource_identification import ResourceIdentification as RI
from repo_catalog.domain.resource_identity import encode_identity, parse_identity
from tests.integration.p5.conftest import init_catalog_stores


def setup(path):
    r1, _ = init_catalog_stores(path, stores=("core", "context", "operational"))
    r2, service = str(uuid4()), str(uuid4())
    ProviderAcquisition(path).admit_batch(
        ProviderIntakeBatch(
            service,
            providers=(ProviderRegistration(service),),
            repositories=(RepositoryRegistration(r1), RepositoryRegistration(r2)),
        )
    )
    return service, r1, r2


def provenance(label):
    return make_provenance("original-provider", {"observation": label})


def mapping(service, provider, target, label="mapping", clock=10):
    return ResourceRepositoryRelation(
        ResourceKey.from_native(service, "repository", provider),
        "represents_repository",
        FieldClock("original-mapping", clock),
        canonical(target),
        provenance(label),
        clock,
    )


def snapshot(path, table):
    with Context.snapshot(path) as ctx:
        return tuple(ctx.db.execute("SELECT * FROM " + table))


def issue_batch(
    service, repository, *, identifier=7, label="issue", updated="2026-10-19T01:00:00Z"
):
    payload = {"id": identifier, "updated_at": updated, "repository": repository}
    return ProviderIntakeBatch(
        service, issues=(ProviderIssueIntake(payload, 50, provenance(label)),)
    )


def timeline(service, event=100, *, label="event", **payload):
    return ProviderIntakeBatch(
        service,
        timeline_events=(
            ProviderTimelineIntake(
                "issue",
                7,
                event,
                {
                    "id": event,
                    "event": "transferred",
                    "created_at": "2026-10-19T01:00:00Z",
                    **payload,
                },
                60,
                provenance(label),
            ),
        ),
    )


def test_pr_base_head_have_distinct_core_and_exact_provider_support(tmp_path):
    s, r1, r2 = setup(tmp_path)
    a, b = mapping(s, "1", r1, "A"), mapping(s, "2", r2, "B")
    ProviderAcquisition(tmp_path).admit_batch(
        ProviderIntakeBatch(
            s,
            mapping_claims=(a, b),
            pull_requests=(
                ProviderPullRequestIntake(
                    {
                        "id": 9,
                        "updated_at": "2026-10-19T01:00:00Z",
                        "base": {"repo": {"id": 1}},
                        "head": {"repo": {"id": 2}},
                    },
                    50,
                    provenance("PR"),
                ),
            ),
        )
    )
    key = ResourceKey.from_native(s, "pull_request", "9")
    with Context.snapshot(tmp_path) as ctx:
        qualified = {
            q.scope.relation_kind: q for q in ctx.provider_repository_roles(key)
        }
        assert qualified["base_repository"].supports[0].supporting_claims == (
            a.claim_key,
        )
        assert qualified["head_repository"].supports[0].supporting_claims == (
            b.claim_key,
        )
        assert {
            q.resolved_candidates[0].target_repository_uuidv4
            for q in qualified.values()
        } == {r1, r2}
        assert not ctx.repository_relations(key, relation_kind="owning_repository")
        assert len(ctx.repository_relations(key)) == 2


def test_mapping_conflict_retains_both_exact_claim_keys(tmp_path):
    s, r1, r2 = setup(tmp_path)
    a, b = mapping(s, "1", r1, "A"), mapping(s, "1", r2, "B", 11)
    acq = ProviderAcquisition(tmp_path)
    acq.admit_batch(ProviderIntakeBatch(s, mapping_claims=(a, b)))
    acq.admit_batch(issue_batch(s, {"id": 1}))
    with Context.snapshot(tmp_path) as ctx:
        (role,) = ctx.provider_repository_roles(
            ResourceKey.from_native(s, "issue", "7")
        )
        assert role.state == "conflict"
        assert {
            key for support in role.supports for key in support.supporting_claims
        } == {a.claim_key, b.claim_key}
        assert len(ctx.repository_relations(role.resource)) == 2


def test_other_provider_claim_cannot_resolve_reference_or_typed_qualification(tmp_path):
    s, r1, _ = setup(tmp_path)
    claim = mapping(s, "B", r1)
    acq = ProviderAcquisition(tmp_path)
    acq.admit_batch(ProviderIntakeBatch(s, mapping_claims=(claim,)))
    acq.admit_batch(issue_batch(s, {"id": 1}))
    with Context.snapshot(tmp_path) as ctx:
        key = ResourceKey.from_native(s, "issue", "7")
        (role,) = ctx.provider_repository_roles(key)
        assert role.state == "unresolved_provider_only" and not role.resolved_candidates
        assert not ctx.repository_relations(key)
    with pytest.raises(ValueError, match="exact Provider"):
        QualifiedProviderRepositoryRole(
            key,
            ProviderRepositoryRoleScope.unresolved(
                "owning_repository", encode_identity("A"), FieldClock("provider", 1), 1
            ),
            provenance("issue"),
            QualifiedMappingEvaluation(
                claim.resource, "single_candidate", (claim.claim_key,)
            ),
        )


@pytest.mark.parametrize("kind", ["withdraw", "dispute", "correct"])
def test_disposition_qualification_keeps_original_provider_and_claims(tmp_path, kind):
    s, r1, r2 = setup(tmp_path)
    claim, replacement = (
        mapping(s, "1", r1, "A"),
        mapping(s, "1", r2, "replacement", 11),
    )
    acq = ProviderAcquisition(tmp_path)
    acq.admit_batch(ProviderIntakeBatch(s, mapping_claims=(claim,)))
    acq.admit_batch(issue_batch(s, {"id": 1}))
    before = snapshot(tmp_path, "resource_relations")
    disposition = MappingDisposition(
        claim.claim_key,
        kind,
        FieldClock("operation", 20),
        provenance(kind),
        20,
        replacement.claim_key if kind == "correct" else None,
    )
    acq.admit_batch(
        ProviderIntakeBatch(
            s,
            mapping_claims=(replacement,) if kind == "correct" else (),
            mapping_dispositions=(disposition,),
        )
    )
    with Context.snapshot(tmp_path) as ctx:
        key = ResourceKey.from_native(s, "issue", "7")
        (ordinary,) = ctx.provider_repository_roles(key)
        assert (
            ordinary.mapping.unconfirmed_dispositions
            or ordinary.mapping.disputed_dispositions
        )
        (qualified,) = ctx.provider_repository_roles(
            key,
            evidence=MappingOperationEvidence(frozenset({disposition.disposition_key})),
        )
        if kind == "dispute":
            assert qualified.mapping == ordinary.mapping
        else:
            assert qualified.mapping != ordinary.mapping
        assert any(
            r.claim_key == claim.claim_key
            for r in ctx.repository_relations(claim.resource)
        )
        assert ctx.mapping_dispositions(claim.claim_key) == (disposition,)
    assert snapshot(tmp_path, "resource_relations") == before


def test_missing_null_unresolved_and_late_mapping_are_distinct(tmp_path):
    s, r1, _ = setup(tmp_path)
    acq = ProviderAcquisition(tmp_path)
    acq.admit_batch(
        ProviderIntakeBatch(
            s, issues=(ProviderIssueIntake({"id": 1}, None, provenance("missing")),)
        )
    )
    acq.admit_batch(issue_batch(s, None, identifier=2, label="null"))
    acq.admit_batch(issue_batch(s, {"id": 1}, identifier=3, label="unresolved"))
    with Context.snapshot(tmp_path) as ctx:
        assert not ctx.provider_repository_roles(
            ResourceKey.from_native(s, "issue", "1")
        )
        (null,) = ctx.provider_repository_roles(
            ResourceKey.from_native(s, "issue", "2")
        )
        assert (
            null.state == "explicit_null"
            and null.resolved_candidates[0].target_json == "null"
        )
        (unresolved,) = ctx.provider_repository_roles(
            ResourceKey.from_native(s, "issue", "3")
        )
        assert (
            unresolved.state == "unresolved_provider_only"
            and not unresolved.resolved_candidates
        )
    before = snapshot(tmp_path, "resource_relations")
    claim = mapping(s, "1", r1)
    acq.admit_batch(ProviderIntakeBatch(s, mapping_claims=(claim,)))
    with Context.snapshot(tmp_path) as ctx:
        (resolved,) = ctx.provider_repository_roles(
            ResourceKey.from_native(s, "issue", "3")
        )
        assert resolved.supports[0].supporting_claims == (claim.claim_key,)
    assert snapshot(tmp_path, "resource_relations") == before


def test_provider_native_namespaces_do_not_borrow_decimal_mapping(tmp_path):
    s, r1, _ = setup(tmp_path)
    acq = ProviderAcquisition(tmp_path)
    native = {"id": "R_opaque_A", "databaseId": 1, "nameWithOwner": "owner/name"}
    acq.admit_batch(
        ProviderIntakeBatch(
            s,
            mapping_claims=(mapping(s, "1", r1),),
            provider_repositories=(
                ProviderRepositoryIntake(native, 10, provenance("repo"), graphql=True),
            ),
            issues=(
                ProviderIssueIntake(
                    {"id": "I_opaque", "databaseId": 7, "repository": native},
                    20,
                    provenance("issue"),
                    graphql=True,
                ),
            ),
        )
    )
    with Context.snapshot(tmp_path) as ctx:
        (role,) = ctx.provider_repository_roles(
            ResourceKey.from_native(s, "issue", "7")
        )
        assert role.scope.provider_repository_id == canonical(
            ["github:node_id", "R_opaque_A"]
        )
        assert role.state == "unresolved_provider_only"
        assert not role.resolved_candidates
    assert github_repository_id({"id": "123"}, graphql=True) != github_repository_id(
        {"id": 123}, graphql=False
    )


@pytest.mark.parametrize(
    "endpoints,expected",
    [
        (
            {"from_repository": {"id": 1}, "to_repository": {"id": 2}},
            ("resolved", "resolved"),
        ),
        ({"from_repository": {"id": 1}}, ("resolved", "absent")),
        ({"to_repository": {"id": 2}}, ("absent", "resolved")),
        (
            {"from_repository": None, "to_repository": {"id": 2}},
            ("explicit_null", "resolved"),
        ),
        (
            {"from_repository": {"id": 99}, "to_repository": {"id": 98}},
            ("unresolved_provider_only", "unresolved_provider_only"),
        ),
    ],
)
def test_transfer_preserves_complete_original_endpoint_states(
    tmp_path, endpoints, expected
):
    s, r1, r2 = setup(tmp_path)
    a, b = mapping(s, "1", r1, "A"), mapping(s, "2", r2, "B")
    acq = ProviderAcquisition(tmp_path)
    acq.admit_batch(ProviderIntakeBatch(s, mapping_claims=(a, b)))
    acq.admit_batch(timeline(s, **endpoints))
    with Context.snapshot(tmp_path) as ctx:
        (report,) = ctx.transfer_event_reports()
        assert (report.from_state, report.to_state) == expected
        assert report.issue_resource == ResourceKey.from_native(s, "issue", "7")
        assert report.observed_at_us == 60
        for relation in (*report.from_relations, *report.to_relations):
            if relation.target_json != "null":
                wanted = (
                    a if relation.relation_kind == "transfer_from_repository" else b
                )
                assert relation.embedded_support.supporting_claims == (
                    wanted.claim_key,
                )
        assert not ctx.db.execute(
            "SELECT 1 FROM resource_relations WHERE relation_kind='provider_repository_roles'"
        ).fetchall()


@pytest.mark.parametrize("graphql", [False, True])
def test_non_transfer_cannot_promote_repository_fields_or_forged_flag(
    tmp_path, graphql
):
    s, _, _ = setup(tmp_path)
    event_id = "EV_opaque" if graphql else 100
    payload = (
        {"id": event_id, "__typename": "LabeledEvent", "fromRepository": {"id": "R_A"}}
        if graphql
        else {"id": event_id, "event": "labeled", "from_repository": {"id": 1}}
    )
    unit = normalize_timeline_event(
        s, "issue", 7, event_id, payload, 50, provenance("labeled"), graphql=graphql
    )
    acq = ProviderAcquisition(tmp_path)
    acq.admit_unit(unit)
    with Context.snapshot(tmp_path) as ctx:
        assert not ctx.transfer_event_reports() and not ctx.repository_relations(
            unit.primary_resource
        )
    with pytest.raises(AcquisitionError, match="TRANSFER_TYPE_EVIDENCE"):
        acq.admit_unit(replace(unit, transfer_event=True))
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def test_graphql_transfer_parent_namespace_and_original_type(tmp_path):
    s, r1, _ = setup(tmp_path)
    parent = normalize_issue(
        s, {"id": "I_node", "databaseId": 7}, 40, provenance("issue"), graphql=True
    ).primary_resource
    node = {"id": "R_A", "databaseId": 1}
    claim = mapping(s, parse_identity(github_repository_id(node, graphql=True)), r1)
    intake = ProviderTimelineIntake(
        "issue",
        "I_node",
        "EV_node",
        {
            "id": "EV_node",
            "__typename": "TransferredEvent",
            "createdAt": "2026-10-19T01:00:00Z",
            "issue": {"id": "I_node", "databaseId": 7},
            "fromRepository": node,
        },
        50,
        provenance("event"),
        graphql=True,
        parent_resource=parent,
    )
    acq = ProviderAcquisition(tmp_path)
    acq.admit_batch(
        ProviderIntakeBatch(s, mapping_claims=(claim,), timeline_events=(intake,))
    )
    with Context.snapshot(tmp_path) as ctx:
        (report,) = ctx.transfer_event_reports()
        assert report.issue_resource == parent
        assert json.loads(report.event_resource.provider_resource_id)[3] == [
            "github:node_id",
            "EV_node",
        ]
        assert (
            ctx.candidates(report.event_resource, "provider_event_type")[0].value_json
            == '"TransferredEvent"'
        )
        assert report.from_relations[0].embedded_support.supporting_claims == (
            claim.claim_key,
        )


@pytest.mark.parametrize(
    ("graphql", "parent_id", "observed_issue"),
    [
        (False, 999, None),
        (True, 999, None),
        (True, "I_wrong", {"id": "I_actual", "databaseId": 7}),
        (True, "I_actual", None),
        (True, "I_actual", {"id": "I_actual", "databaseId": 8}),
        (True, 7, {"id": "I_actual", "fullDatabaseId": 7, "databaseId": 8}),
        (True, "I_actual", {"id": "I_actual", "databaseId": 7, "fullDatabaseId": 8}),
    ],
)
def test_timeline_parent_override_cannot_forge_observed_issue(
    tmp_path, graphql, parent_id, observed_issue
):
    service, _, _ = setup(tmp_path)
    event_id = "EV_native" if graphql else 100
    payload = {"id": event_id, "event": "transferred"}
    if graphql:
        payload["__typename"] = "TransferredEvent"
    if observed_issue is not None:
        payload["issue"] = observed_issue
    with pytest.raises(AcquisitionError, match="EVENT_PARENT_MISMATCH"):
        normalize_timeline_event(
            service,
            "issue",
            parent_id,
            event_id,
            payload,
            50,
            provenance("contradictory-parent"),
            graphql=graphql,
            parent_resource=ResourceKey.from_native(service, "issue", "7"),
        )


def test_reacquired_event_does_not_reissue_provenance_after_mapping_change(tmp_path):
    s, r1, r2 = setup(tmp_path)
    acq = ProviderAcquisition(tmp_path)
    claim = mapping(s, "1", r1)
    acq.admit_batch(ProviderIntakeBatch(s, mapping_claims=(claim,)))
    original = timeline(s, from_repository={"id": 1}, to_repository={"id": 2})
    acq.admit_batch(original)
    before = (
        snapshot(tmp_path, "resource_relations"),
        snapshot(tmp_path, "resource_repository_relations"),
    )
    acq.admit_batch(
        ProviderIntakeBatch(
            s,
            mapping_claims=(mapping(s, "2", r2, "new-mapping"),),
            mapping_dispositions=(
                MappingDisposition(
                    claim.claim_key,
                    "withdraw",
                    FieldClock("operation", 70),
                    provenance("withdraw"),
                    70,
                ),
            ),
        )
    )
    acq.admit_batch(original)
    assert snapshot(tmp_path, "resource_relations") == before[0]

    def transfer_rows(rs):
        return tuple(r for r in rs if r[3].startswith("transfer_"))

    assert transfer_rows(
        snapshot(tmp_path, "resource_repository_relations")
    ) == transfer_rows(before[1])
    with Context.snapshot(tmp_path) as ctx:
        (report,) = ctx.transfer_event_reports()
        assert (
            report.observed_at_us == 60
            and report.to_state == "unresolved_provider_only"
        )
    raw_relations = snapshot(tmp_path, "resource_relations")
    acq.admit_batch(original)
    assert snapshot(tmp_path, "resource_relations") == raw_relations


def test_separate_event_reports_never_pair_endpoints(tmp_path):
    s, r1, r2 = setup(tmp_path)
    acq = ProviderAcquisition(tmp_path)
    acq.admit_batch(
        ProviderIntakeBatch(
            s, mapping_claims=(mapping(s, "1", r1), mapping(s, "2", r2))
        )
    )
    acq.admit_batch(timeline(s, label="from-report", from_repository={"id": 1}))
    acq.admit_batch(timeline(s, label="to-report", to_repository={"id": 2}))
    with Context.snapshot(tmp_path) as ctx:
        reports = ctx.transfer_event_reports()
        assert len(reports) == 2 and all(len(r.provided_roles) == 1 for r in reports)


def test_generic_provider_scope_cannot_create_transfer(tmp_path):
    s, _, _ = setup(tmp_path)
    event = ResourceKey.timeline_event(ResourceKey.from_native(s, "issue", "7"), "100")
    provider = ResourceKey.from_native(s, "repository", "1")
    with Context.transaction(tmp_path) as ctx:
        ctx.resource(ResourceKey.from_native(s, "issue", "7"))
        ctx.resource(
            event,
            identification=RI.scoped(
                event, ResourceKey.from_native(s, "issue", "7"), "timeline_event", "100"
            ),
        )
    scope = ProviderRepositoryScope(
        {
            "transfer_from_repository": ProviderRepositoryRoleScope.unresolved(
                "transfer_from_repository",
                encode_identity("1"),
                FieldClock("event", 10),
                10,
            )
        }
    )
    relation = ResourceRelation(
        event,
        "provider_repository_roles",
        (provider,),
        provenance("forged"),
        scope.encoded,
        10,
    )
    with pytest.raises(ValueError, match="Transfer roles"):
        ProviderAcquisition(tmp_path).admit_batch(
            ProviderIntakeBatch(s, relations=(relation,))
        )
    assert not snapshot(tmp_path, "resource_relations")
    assert not (tmp_path / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize(
    "payload",
    [
        {"id": 101, "event": "transferred"},
        {"event": "transferred"},
        {"id": 100, "event": "transferred", "from_repository": {}},
    ],
)
def test_invalid_event_input_rolls_back_without_recovery_stop(tmp_path, payload):
    s, _, _ = setup(tmp_path)
    before = snapshot(tmp_path, "resources")
    with pytest.raises(ValueError):
        ProviderAcquisition(tmp_path).admit_batch(
            ProviderIntakeBatch(
                s,
                timeline_events=(
                    ProviderTimelineIntake(
                        "issue", 7, 100, payload, 10, provenance("invalid")
                    ),
                ),
            )
        )
    assert snapshot(tmp_path, "resources") == before
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def test_caller_transaction_batch_failure_rolls_back_partial_domain_and_access_untouched(
    tmp_path,
):
    s, _, _ = setup(tmp_path)
    access = tmp_path / "access.sqlite3"
    access.write_bytes(b"access-sentinel-do-not-read-or-modify")
    before = snapshot(tmp_path, "resources")
    with Context.transaction(tmp_path) as ctx:
        batch = issue_batch(s, {"id": 1})
        invalid = ProviderTimelineIntake(
            "issue", 7, 100, {"id": 101, "event": "transferred"}, 50, provenance("bad")
        )
        with pytest.raises(AcquisitionError):
            ProviderAcquisition(tmp_path).admit_batch(
                replace(batch, timeline_events=(invalid,)), context=ctx
            )
    assert snapshot(tmp_path, "resources") == before
    assert access.read_bytes() == b"access-sentinel-do-not-read-or-modify"


def test_p7_stop_rejects_provider_intake(tmp_path):
    s, _, _ = setup(tmp_path)
    persist_catalog_stop(tmp_path, "synthetic-test-stop")
    with pytest.raises(CoordinationError):
        ProviderAcquisition(tmp_path).admit_batch(issue_batch(s, {"id": 1}))
    assert (tmp_path / "p1-recovery-stop.json").exists()


def test_issue_ownership_keeps_incomparable_source_clock_domains(tmp_path):
    s, r1, r2 = setup(tmp_path)
    acq = ProviderAcquisition(tmp_path)
    acq.admit_batch(
        ProviderIntakeBatch(
            s, mapping_claims=(mapping(s, "1", r1), mapping(s, "2", r2))
        )
    )
    for domain, repo in (("provider:REST:owner", 1), ("provider:GraphQL:owner", 2)):
        unit = normalize_issue(
            s, {"id": 7, "repository": {"id": repo}}, 50, provenance(domain)
        )
        (relation,) = unit.relations
        entry = ProviderRepositoryScope.from_json(relation.scope_json).roles[
            "owning_repository"
        ]
        scope = ProviderRepositoryScope(
            {"owning_repository": replace(entry, clock=FieldClock(domain, 30))}
        )
        acq.admit_unit(
            replace(unit, relations=(replace(relation, scope_json=scope.encoded),))
        )
    with Context.snapshot(tmp_path) as ctx:
        key = ResourceKey.from_native(s, "issue", "7")
        roles = ctx.provider_repository_roles(key)
        assert {q.scope.clock.domain for q in roles} == {
            "provider:REST:owner",
            "provider:GraphQL:owner",
        }
        assert {r.target_repository_uuidv4 for r in ctx.repository_relations(key)} == {
            r1,
            r2,
        }


def test_oid_url_name_and_source_membership_are_not_mapping_evidence(tmp_path):
    from contextlib import closing

    from repo_catalog.adapters.sqlite.git_core import GitCore
    from repo_catalog.domain.acquisition import SourceRegistration
    from repo_catalog.domain.p1_core import OID

    s, r1, _ = setup(tmp_path)
    with closing(GitCore(tmp_path / "core.sqlite3")) as core:
        core.admit_object(OID("sha1", "a" * 40))
    ProviderAcquisition(tmp_path).admit_batch(
        ProviderIntakeBatch(
            s,
            sources=(
                SourceRegistration(str(uuid4()), s, associated_repositories=(r1,)),
            ),
            provider_repositories=(
                ProviderRepositoryIntake(
                    {
                        "id": 1,
                        "name": "same-name",
                        "html_url": "https://example.invalid/same",
                    },
                    10,
                    provenance("repo"),
                ),
            ),
            pull_requests=(
                ProviderPullRequestIntake(
                    {"id": 7, "head": {"sha": "a" * 40, "repo": {"id": 1}}},
                    10,
                    provenance("PR"),
                ),
            ),
        )
    )
    with Context.snapshot(tmp_path) as ctx:
        key = ResourceKey.from_native(s, "pull_request", "7")
        (role,) = ctx.provider_repository_roles(key)
        assert role.state == "unresolved_provider_only" and not role.resolved_candidates
        assert ctx.core_dependencies(key) and not ctx.repository_relations(key)
        assert not ctx.db.execute(
            "SELECT 1 FROM resource_repository_relations"
        ).fetchall()


def test_declared_resolved_provider_scope_does_not_supply_its_own_mapping(tmp_path):
    s, r1, _ = setup(tmp_path)
    issue, provider = (
        ResourceKey.from_native(s, "issue", "7"),
        ResourceKey.from_native(s, "repository", "1"),
    )
    scope = ProviderRepositoryScope(
        {
            "owning_repository": ProviderRepositoryRoleScope.resolved(
                "owning_repository",
                encode_identity("1"),
                r1,
                FieldClock("provider", 10),
                10,
            )
        }
    )
    ProviderAcquisition(tmp_path).admit_batch(
        ProviderIntakeBatch(
            s,
            relations=(
                ResourceRelation(
                    issue,
                    "provider_repository_roles",
                    (provider,),
                    provenance("claimed-resolved"),
                    scope.encoded,
                    10,
                ),
            ),
        )
    )
    with Context.snapshot(tmp_path) as ctx:
        (role,) = ctx.provider_repository_roles(issue)
        assert role.state == "unresolved_provider_only" and not role.resolved_candidates
        assert not ctx.repository_relations(issue)


def test_graphql_event_does_not_infer_destination_from_current_issue_repository(
    tmp_path,
):
    s, _, _ = setup(tmp_path)
    payload = {
        "id": "EV",
        "__typename": "TransferredEvent",
        "fromRepository": {"id": "R_A"},
        "issue": {"databaseId": 7, "repository": {"id": "R_B"}},
    }
    ProviderAcquisition(tmp_path).admit_batch(
        ProviderIntakeBatch(
            s,
            timeline_events=(
                ProviderTimelineIntake(
                    "issue",
                    7,
                    "EV",
                    payload,
                    None,
                    provenance("transfer"),
                    graphql=True,
                ),
            ),
        )
    )
    with Context.snapshot(tmp_path) as ctx:
        (report,) = ctx.transfer_event_reports()
        assert (
            report.from_state == "unresolved_provider_only"
            and report.to_state == "absent"
        )
        assert report.clock.at_us is None and report.observed_at_us is None
        assert report.provenance_json == provenance("transfer")


def test_same_original_event_key_cannot_change_observation_time(tmp_path):
    s, _, _ = setup(tmp_path)
    acq = ProviderAcquisition(tmp_path)
    batch = timeline(s, from_repository={"id": 1})
    acq.admit_batch(batch)
    before = snapshot(tmp_path, "resource_relations")
    with pytest.raises(ValueError):
        acq.admit_batch(
            replace(
                batch,
                timeline_events=(replace(batch.timeline_events[0], observed_at_us=61),),
            )
        )
    assert snapshot(tmp_path, "resource_relations") == before
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def test_stop_during_claim_admission_rolls_back_real_context_work(
    tmp_path, monkeypatch
):
    from repo_catalog.adapters.sqlite.p1_schema import connect

    s, r1, _ = setup(tmp_path)
    before = snapshot(tmp_path, "resources")
    with pytest.raises((CoordinationError, ValueError)) as failure:
        with Context.transaction(tmp_path) as ctx:
            original = ctx.admit_repository_relation

            def admit_and_stop(*args, **kwargs):
                result = original(*args, **kwargs)
                persist_catalog_stop(tmp_path, "synthetic-mid-admission-stop")
                return result

            monkeypatch.setattr(ctx, "admit_repository_relation", admit_and_stop)
            ProviderAcquisition(tmp_path).admit_batch(
                ProviderIntakeBatch(
                    s,
                    mapping_claims=(mapping(s, "1", r1),),
                    issues=(ProviderIssueIntake({"id": 7}, 10, provenance("issue")),),
                ),
                context=ctx,
            )
    assert getattr(failure.value, "code", None) in {
        "RECOVERY_REQUIRED",
        "RECOVERY_STOP",
        "CATALOG_STOPPED",
    }
    db = connect(tmp_path / "context.sqlite3", "context")
    try:
        assert tuple(db.execute("SELECT * FROM resources")) == before
        assert not db.execute("SELECT 1 FROM resource_repository_relations").fetchall()
    finally:
        db.close()
    assert (tmp_path / "p1-recovery-stop.json").exists()


def test_latest_unresolved_owner_does_not_fall_back_to_old_mapped_owner(tmp_path):
    s, r1, _ = setup(tmp_path)
    acq = ProviderAcquisition(tmp_path)
    acq.admit_batch(ProviderIntakeBatch(s, mapping_claims=(mapping(s, "1", r1),)))
    acq.admit_batch(
        issue_batch(s, {"id": 1}, label="older", updated="2026-10-19T01:00:00Z")
    )
    acq.admit_batch(
        issue_batch(s, {"id": 2}, label="newer", updated="2026-10-19T02:00:00Z")
    )
    with Context.snapshot(tmp_path) as ctx:
        (role,) = ctx.provider_repository_roles(
            ResourceKey.from_native(s, "issue", "7")
        )
        assert (
            role.scope.provider_repository_id == encode_identity("2")
            and role.state == "unresolved_provider_only"
        )
        assert not role.resolved_candidates
        assert len(ctx.relations(role.resource, "provider_repository_roles")) == 2


@pytest.mark.parametrize("kind", ["issue", "pull_request", "repository"])
def test_graphql_type_mismatch_cannot_change_resource_kind(tmp_path, kind):
    from repo_catalog.adapters.github.production_intake import normalize_pull_request

    s, _, _ = setup(tmp_path)
    with pytest.raises(AcquisitionError, match="RESOURCE_KIND"):
        if kind == "issue":
            normalize_issue(
                s,
                {"id": "U", "__typename": "User"},
                10,
                provenance("bad"),
                graphql=True,
            )
        elif kind == "pull_request":
            normalize_pull_request(
                s,
                {"id": "I", "__typename": "Issue"},
                10,
                provenance("bad"),
                graphql=True,
            )
        else:
            github_repository_id({"id": "I", "__typename": "Issue"}, graphql=True)
    assert (
        normalize_issue(
            s,
            {"id": "PR", "__typename": "PullRequest"},
            10,
            provenance("PR"),
            graphql=True,
        )
        is None
    )


def test_mapping_qualification_does_not_rewrite_source_or_coverage(tmp_path):
    from repo_catalog.domain.acquisition import SourceRegistration
    from repo_catalog.domain.p1_context import CoverageClaim, CoverageScope
    from repo_catalog.domain.production_context import SourceInventory

    s, r1, _ = setup(tmp_path)
    source = str(uuid4())
    scope = canonical({"coverage_kind": "repositories", "service_instance_uuidv4": s})
    inventory = SourceInventory(
        source, scope, 30, "complete", True, (r1,), provenance("inventory")
    )
    coverage = CoverageClaim(
        CoverageScope.source_inventory(source, scope, "repositories"), 30, "complete"
    )
    acq = ProviderAcquisition(tmp_path)
    acq.admit_batch(
        ProviderIntakeBatch(
            s,
            sources=(SourceRegistration(source, s, associated_repositories=(r1,)),),
            source_inventory_proofs=((coverage, inventory),),
        )
    )
    tables = (
        "source_repositories",
        "source_inventory_evidence",
        "coverage_claims",
        "source_coverage_proofs",
    )
    before = {table: snapshot(tmp_path, table) for table in tables}
    claim = mapping(s, "1", r1)
    disposition = MappingDisposition(
        claim.claim_key,
        "withdraw",
        FieldClock("operation", 40),
        provenance("withdraw"),
        40,
    )
    acq.admit_batch(
        ProviderIntakeBatch(
            s, mapping_claims=(claim,), mapping_dispositions=(disposition,)
        )
    )
    assert {table: snapshot(tmp_path, table) for table in tables} == before


@pytest.mark.parametrize(
    "changed", ["event_resource", "clock", "provenance", "members"]
)
def test_transfer_type_and_endpoint_evidence_must_belong_to_same_report(
    tmp_path, changed
):
    s, _, _ = setup(tmp_path)
    unit = normalize_timeline_event(
        s,
        "issue",
        7,
        100,
        {"id": 100, "event": "transferred", "from_repository": {"id": 1}},
        10,
        provenance("event"),
    )
    if changed == "event_resource":
        unit = replace(
            unit,
            primary_resource=ResourceKey.timeline_event(
                ResourceKey.from_native(s, "issue", "7"), "101"
            ),
        )
    elif changed == "clock":
        unit = replace(unit, clock=FieldClock("other-source", 10))
    elif changed == "provenance":
        unit = replace(unit, provenance_json=provenance("different-source"))
    else:
        unit = replace(
            unit,
            relations=tuple(
                replace(rel, members=())
                if rel.relation_kind == "provider_repository_roles"
                else rel
                for rel in unit.relations
            ),
        )
    with pytest.raises(
        AcquisitionError, match="TRANSFER_TYPE_EVIDENCE|TRANSFER_REPORT_UNIT"
    ):
        ProviderAcquisition(tmp_path).admit_unit(unit)
    assert not snapshot(tmp_path, "resource_relations")
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def test_qualified_read_keyword_contract_reference_and_production_match(tmp_path):
    from repo_catalog.adapters.sqlite.p1_context import ContextStore

    s, r1, _ = setup(tmp_path)
    acq = ProviderAcquisition(tmp_path)
    acq.admit_batch(ProviderIntakeBatch(s, mapping_claims=(mapping(s, "1", r1),)))
    acq.admit_batch(issue_batch(s, {"id": 1}))
    key = ResourceKey.from_native(s, "issue", "7")
    with Context.snapshot(tmp_path) as ctx:
        assert ctx.provider_repository_roles(
            resource=key, evidence=None
        ) == ContextStore(ctx.db).provider_repository_roles(resource=key, evidence=None)


def test_invalid_retained_provider_scope_triggers_p7_stop(tmp_path):
    from repo_catalog.adapters.sqlite.p1_schema import connect

    s, _, _ = setup(tmp_path)
    ProviderAcquisition(tmp_path).admit_batch(issue_batch(s, {"id": 1}))
    db = connect(tmp_path / "context.sqlite3", "context")
    try:
        # Privileged invalid insertion bypasses typed admission in a disposable
        # catalog; original immutable rows and schema guards remain untouched.
        db.execute(
            "INSERT INTO resource_relations SELECT service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,'[]',?,scope_json,observed_at_us FROM resource_relations LIMIT 1",
            (provenance("invalid-stored-members"),),
        )
        db.commit()
    finally:
        db.close()
    with pytest.raises(ValueError) as error:
        with Context.snapshot(tmp_path) as ctx:
            ctx.provider_repository_roles(ResourceKey.from_native(s, "issue", "7"))
    assert getattr(error.value, "code", None) == "AUTHORITATIVE_CORRUPTION"
    assert (tmp_path / "p1-recovery-stop.json").exists()
