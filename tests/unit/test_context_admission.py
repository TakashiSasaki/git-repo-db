"""R10--R12 local authority, denial precedence and complete dependency closure."""

from dataclasses import FrozenInstanceError, replace

import pytest

from repo_catalog.domain.context_admission import (
    AdmissionBudget,
    AdmissionContext,
    AdmissionRefused,
    AdmissionSelection,
    AuthenticatedPrincipal,
    ContextAdmissionService,
    DependencySet,
    dependencies,
    extract_provenance_sources,
    validate_originals,
)
from repo_catalog.domain.p1_context import (
    FieldClock,
    MappingClaimKey,
    MappingDisposition,
    MappingOperationEvidence,
    MappingSupport,
    ProviderEndpointDeclaration,
    ResourceKey,
    ResourceRepositoryRelation,
    TransferEventReport,
    canonical,
    encode_supported_provenance,
)
from repo_catalog.domain.parent_report import ParentObservation, ParentReportKey
from repo_catalog.domain.production_context import SourceInventory
from tests.support.context_admission import fixture_context, fixture_service

SERVICE = "a1111111-1111-4111-8111-111111111111"
REPO = "b1111111-1111-4111-8111-111111111111"
OTHER_REPO = "b2222222-2222-4222-8222-222222222222"
SOURCE = "c1111111-1111-4111-8111-111111111111"
PARENT = ResourceKey.from_native(SERVICE, "issue", "7")
OTHER_PARENT = ResourceKey.from_native(SERVICE, "issue", "8")
EVENT = ResourceKey.document(PARENT, "comment", "timeline_event", "77")
PROVIDER_REPO = ResourceKey.from_native(SERVICE, "repository", "org/repo")
CLOCK = FieldClock("capture", 10)
PROVENANCE = canonical({"source": "unauthenticated-source", "evidence": ["original"]})


def mapping(target=REPO, provenance=PROVENANCE):
    return MappingClaimKey(
        PROVIDER_REPO, "represents_repository", CLOCK, canonical(target), provenance
    )


def report():
    parent = ParentObservation(
        ParentReportKey(
            EVENT,
            canonical([list(OTHER_PARENT.coordinates())]),
            PROVENANCE,
            canonical(
                {
                    "clock": {"domain": "capture", "at_us": 10},
                    "document_kind": "timeline_event",
                    "state": "complete",
                }
            ),
        ),
        None,
    )
    return TransferEventReport.from_targets(
        EVENT,
        clock=CLOCK,
        provenance_json=PROVENANCE,
        observed_at_us=20,
        from_target_json=canonical(REPO),
        to_target_json="null",
        parent_report=parent,
        endpoint_declaration=ProviderEndpointDeclaration(
            PROVIDER_REPO, "explicit_null"
        ),
        endpoints=(
            ("transfer_from_repository", canonical(REPO)),
            ("transfer_to_repository", "null"),
        ),
    )


def refused(code):
    return pytest.raises(AdmissionRefused, match=f"^{code}$")


def test_context_is_bound_to_exact_issuing_service_and_principal():
    deps = dependencies(PARENT)
    service, policy = fixture_service(deps)
    foreign, foreign_policy = fixture_service(deps)
    valid = fixture_context(service)
    attacks = (
        fixture_context(foreign),
        replace(valid, principal="admin"),
        replace(valid),
        AdmissionContext(
            "fixture-user", "provider_intake", valid.selection, valid.budget
        ),
        None,
    )
    for attack in attacks:
        with refused("PERMISSION_DENIED"):
            with service.authorize(attack, deps):
                pytest.fail("foreign/forged context reached operation")
    assert not policy.calls and not foreign_policy.calls
    with service.authorize(valid, deps):
        assert policy.active == 1
    assert policy.active == 0


def test_mutating_issued_principal_is_refused_before_policy():
    service, policy = fixture_service(DependencySet())
    context = fixture_context(service)
    object.__setattr__(context, "principal", "admin")
    with refused("PERMISSION_DENIED"):
        service.validate_context(context)
    assert not policy.calls


@pytest.mark.parametrize("principal", [None, False, 1, {}, ["admin"], ""])
def test_authenticator_must_supply_local_principal(principal):
    service, policy = fixture_service(DependencySet())
    service = ContextAdmissionService(policy, lambda credential: principal)
    with refused("PERMISSION_DENIED"):
        fixture_context(service)


def test_local_session_principal_and_invalid_credentials():
    service, policy = fixture_service(DependencySet())
    principal = AuthenticatedPrincipal("user", "local-session")
    service = ContextAdmissionService(policy, lambda credential: principal)
    assert fixture_context(service).principal is principal
    original, _ = fixture_service(DependencySet())
    with refused("PERMISSION_DENIED"):
        original.context(
            "bad",
            "provider_intake",
            AdmissionSelection(all_selected=True),
            AdmissionBudget(),
        )


@pytest.mark.parametrize("operation", [None, "", "trusted", "provider", True])
def test_unsupported_operation_refuses_before_authentication(operation):
    service, policy = fixture_service(DependencySet())
    called = []
    service = ContextAdmissionService(
        policy, lambda credential: called.append(credential)
    )
    with refused("PERMISSION_DENIED"):
        service.context(
            "credential",
            operation,
            AdmissionSelection(all_selected=True),
            AdmissionBudget(),
        )
    assert not called and not policy.calls


def test_policy_denial_precedes_selection_without_existence_details():
    deps = dependencies(PARENT)
    service, policy = fixture_service(DependencySet())
    empty = AdmissionSelection(
        resource_keys=(), repository_uuidv4s=(), source_uuidv4s=(), object_oids=()
    )
    context = fixture_context(service, selection=empty)
    with refused("PERMISSION_DENIED"):
        with service.authorize(context, deps):
            pytest.fail("denied")
    policy.grants = deps
    with refused("OMITTED_BY_SELECTION"):
        with service.authorize(context, deps):
            pytest.fail("unselected")
    assert len(policy.calls) == 2


@pytest.mark.parametrize(
    "dimension",
    [
        "resources",
        "repositories",
        "sources",
        "source_repository_pairs",
        "mapping_claims",
        "dispositions",
        "provider_registrations",
    ],
)
def test_each_dependency_dimension_has_independent_permission(dimension):
    claim = mapping()
    disposition = MappingDisposition(claim, "withdraw", CLOCK, PROVENANCE)
    deps = DependencySet(
        resources={PARENT},
        repositories={REPO},
        sources={SOURCE},
        source_repository_pairs={(SOURCE, REPO)},
        mapping_claims={claim},
        dispositions={disposition.disposition_key},
        provider_registrations={SERVICE},
    )
    service, policy = fixture_service(deps)
    context = fixture_context(service)
    policy.denied = DependencySet(**{dimension: getattr(deps, dimension)})
    with refused("PERMISSION_DENIED"):
        with service.authorize(context, deps):
            pytest.fail("one missing permission accepted")


def test_replay_rechecks_policy_and_revocation_invalidates_held_lease():
    deps = dependencies(PARENT)
    service, policy = fixture_service(deps)
    context = fixture_context(service)
    with service.authorize(context, deps):
        pass
    policy.grants = DependencySet()
    with refused("PERMISSION_DENIED"):
        with service.authorize(context, deps):
            pytest.fail("stale grant")
    policy.grants = deps
    with refused("PERMISSION_DENIED"):
        with service.authorize(context, deps) as lease:
            policy.revision += 1
            lease.check_current()
    assert policy.active == 0


def test_request_budget_charges_failures_and_rollbacks_without_refunds():
    deps = dependencies(PARENT)
    service, _ = fixture_service(deps)
    budget = AdmissionBudget(work_limit=6)
    context = fixture_context(service, budget=budget)
    with pytest.raises(RuntimeError):
        with service.authorize(context, deps):
            raise RuntimeError("rolled back")
    assert budget.used_work == 3
    with service.authorize(context, deps):
        pass
    with refused("INPUT_LIMIT"):
        with service.authorize(context, deps):
            pytest.fail("exhausted")
    assert budget.used_work == 9
    with pytest.raises(FrozenInstanceError):
        budget.work_limit = 100


@pytest.mark.parametrize("value", [True, -1, float("inf"), "100"])
def test_budget_requires_finite_strict_limits(value):
    with refused("INPUT_LIMIT"):
        AdmissionBudget(work_limit=value)


def test_selection_omission_empty_and_independent_repository_permission():
    with refused("OMITTED_BY_SELECTION"):
        AdmissionSelection(repository_uuidv4s={REPO})
    service, _ = fixture_service(DependencySet(repositories={REPO}))
    with refused("PERMISSION_DENIED"):
        with service.authorize(fixture_context(service), dependencies(PARENT)):
            pytest.fail("Repository grants Resource permission")


def test_source_provenance_is_recursive_explicit_bounded_and_canonical():
    encoded = canonical(
        {
            "source": SOURCE,
            "claimed_issuer": SOURCE,
            "evidence": [{"nested": {"source_registration_uuidv4": SOURCE}}],
        }
    )
    assert extract_provenance_sources(encoded) == frozenset({SOURCE})
    assert not extract_provenance_sources(
        canonical({"source": SOURCE, "evidence": "original"})
    )
    assert not extract_provenance_sources(
        canonical({"source_registration_uuidv4": None})
    )
    with refused("INVALID_PROVENANCE"):
        extract_provenance_sources('{"source_registration_uuidv4":"x", "evidence":1}')
    with refused("INPUT_LIMIT"):
        extract_provenance_sources("[" * 13 + "0" + "]" * 13)


def test_mapping_support_and_disposition_include_full_claims_and_replacements():
    original = mapping(
        provenance=canonical(
            {"source": "claim", "evidence": {"source_registration_uuidv4": SOURCE}}
        )
    )
    replacement = mapping(OTHER_REPO)
    support = MappingSupport(PROVIDER_REPO, (original,))
    relation = ResourceRepositoryRelation(
        PARENT,
        "owning_repository",
        CLOCK,
        canonical(REPO),
        encode_supported_provenance("reported", "evidence", support),
        20,
    )
    disposition = MappingDisposition(
        original, "correct", CLOCK, PROVENANCE, 20, replacement
    )
    deps = dependencies(
        (
            relation,
            disposition,
            MappingOperationEvidence(frozenset({disposition.disposition_key})),
        )
    )
    assert deps.resources == frozenset({PARENT, PROVIDER_REPO})
    assert deps.repositories == frozenset({REPO, OTHER_REPO})
    assert deps.sources == frozenset({SOURCE})
    assert deps.mapping_claims == frozenset({original, replacement})
    assert deps.dispositions == frozenset({disposition.disposition_key})


def test_source_inventory_known_positive_pairs_are_dependencies():
    inventory = SourceInventory(SOURCE, "{}", 10, "partial", True, (REPO,), PROVENANCE)
    deps = dependencies(inventory)
    assert deps.source_repository_pairs == frozenset({(SOURCE, REPO)})
    assert deps.sources == frozenset({SOURCE}) and deps.repositories == frozenset(
        {REPO}
    )


def test_transfer_includes_native_and_different_reported_parent_and_endpoints():
    value = report()
    deps = dependencies(value)
    assert {EVENT, PARENT, OTHER_PARENT, PROVIDER_REPO} <= deps.resources
    assert REPO in deps.repositories
    before = repr(value)
    validate_originals(value)
    assert repr(value) == before


class MemoryPolicy:
    """Test authority with finite grants, revision revocation and commit fence."""

    def __init__(self, grants):
        from threading import RLock

        self._lock = RLock()
        self._grants = grants
        self._revision = 0

    def revoke(self):
        with self._lock:
            self._grants = DependencySet()
            self._revision += 1

    def lease(self, principal, operation, deps):
        from contextlib import contextmanager

        @contextmanager
        def held():
            with self._lock:
                if (
                    principal != "local-user"
                    or operation != "exchange_import"
                    or not deps.issubset(self._grants)
                ):
                    raise AdmissionRefused("PERMISSION_DENIED")
                revision = self._revision
                policy = self

                class Lease:
                    def check_current(self):
                        if revision != policy._revision:
                            raise AdmissionRefused("PERMISSION_DENIED")

                yield Lease()

        return held()


def test_commit_fence_serializes_other_thread_revocation_and_rechecks_next_request():
    from threading import Event, Thread

    deps = dependencies(PARENT)
    policy = MemoryPolicy(deps)
    service = ContextAdmissionService(policy, lambda credential: "local-user")
    context = service.context(
        "local-credential",
        "exchange_import",
        AdmissionSelection(all_selected=True),
        AdmissionBudget(),
    )
    attempted, completed = Event(), Event()

    def revoke():
        attempted.set()
        policy.revoke()
        completed.set()

    with service.authorize(context, deps) as lease:
        thread = Thread(target=revoke)
        thread.start()
        assert attempted.wait(1)
        assert not completed.wait(0.05)
        lease.check_current()
    thread.join(timeout=1)
    assert completed.is_set()
    with refused("PERMISSION_DENIED"):
        with service.authorize(context, deps):
            pytest.fail("revoked replay")


def test_same_thread_revocation_invalidates_commit_lease():
    deps = dependencies(PARENT)
    policy = MemoryPolicy(deps)
    service = ContextAdmissionService(policy, lambda credential: "local-user")
    context = service.context(
        "local-credential",
        "exchange_import",
        AdmissionSelection(all_selected=True),
        AdmissionBudget(),
    )
    with refused("PERMISSION_DENIED"):
        with service.authorize(context, deps):
            policy.revoke()


def test_provenance_uses_context_ascii_canonical_profile():
    encoded = canonical(
        {"source": "報告", "evidence": {"source_registration_uuidv4": SOURCE}}
    )
    assert extract_provenance_sources(encoded) == frozenset({SOURCE})


def test_coverage_dependencies_preserve_resource_source_and_positive_pair():
    from repo_catalog.domain.p1_context import CoverageScope

    deps = dependencies(
        (
            CoverageScope.source(SOURCE, REPO, "known"),
            CoverageScope.repository_relation(
                REPO, PARENT, "owning_repository", "known"
            ),
        )
    )
    assert deps.resources == frozenset({PARENT})
    assert deps.source_repository_pairs == frozenset({(SOURCE, REPO)})
    assert deps.repositories == frozenset({REPO})


def test_scope_source_references_are_explicit_dependencies():
    from repo_catalog.domain.production_context import CollectionObservation

    observation = CollectionObservation(
        PARENT,
        "children",
        PROVENANCE,
        canonical({"nested": [{"source_registration_uuidv4": SOURCE}]}),
        20,
        "partial",
        (OTHER_PARENT,),
    )
    deps = dependencies(observation)
    assert deps.sources == frozenset({SOURCE})
    assert deps.resources == frozenset({PARENT, OTHER_PARENT})


def test_actual_input_cost_charges_reprocessing_and_failure_without_refund():
    service, _ = fixture_service(DependencySet())
    budget = AdmissionBudget(bytes_limit=7)
    context = fixture_context(service, budget=budget)
    service.charge_input(context, ("日本",))
    assert budget.used_bytes == 6
    with refused("INPUT_LIMIT"):
        service.charge_input(context, ("日本",))
    assert budget.used_bytes == 12
    assert budget.used_work > 0


def test_input_cost_validates_issued_identity_before_work():
    service, policy = fixture_service(DependencySet())
    context = fixture_context(service)
    with refused("PERMISSION_DENIED"):
        service.charge_input(replace(context, principal="admin"), "payload")
    assert not policy.calls and context.budget.used_work == 0


def test_service_does_not_retain_finished_invocations():
    import gc
    from weakref import ref

    service, _ = fixture_service(DependencySet())
    context = fixture_context(service)
    finished = ref(context)
    del context
    gc.collect()
    assert finished() is None
    service.validate_context(fixture_context(service))


def test_authenticated_session_fields_cannot_change_after_context_issue():
    _, policy = fixture_service(DependencySet())
    principal = AuthenticatedPrincipal("user", "session")
    service = ContextAdmissionService(policy, lambda credential: principal)
    context = fixture_context(service)
    object.__setattr__(principal, "subject", "admin")
    with refused("PERMISSION_DENIED"):
        service.validate_context(context)
    assert not policy.calls


@pytest.mark.parametrize(
    "target,field,value",
    [("selection", "all_selected", False), ("budget", "work_limit", 100_000_000)],
)
def test_nested_invocation_limits_and_selection_are_bound_at_issue(
    target, field, value
):
    service, policy = fixture_service(DependencySet())
    context = fixture_context(service)
    object.__setattr__(getattr(context, target), field, value)
    with refused("PERMISSION_DENIED"):
        service.validate_context(context)
    assert not policy.calls


@pytest.mark.parametrize("container", ["field", "tuple", "observation"])
def test_reserved_core_reference_fields_carry_independent_oid_dependency(container):
    from repo_catalog.domain.p1_context import FieldCandidate
    from repo_catalog.domain.p1_core import OID

    oid = OID("sha1", "a" * 40)
    field = FieldCandidate(
        PARENT,
        "reported_core_reference:head",
        canonical(oid.key),
        CLOCK,
        PROVENANCE,
        20,
    )
    from repo_catalog.domain.production_context import ResourceObservation

    values = {
        "field": field,
        "tuple": (field,),
        "observation": ResourceObservation(PARENT, (field,)),
    }
    deps = dependencies(values[container])
    assert deps.object_oids == frozenset({oid})
    assert deps.resources == frozenset({PARENT})


def test_reserved_core_reference_fields_reject_malformed_oid_before_sql():
    from repo_catalog.domain.p1_context import FieldCandidate

    field = FieldCandidate(
        PARENT,
        "reported_core_reference:head",
        canonical(["sha1", "bad"]),
        CLOCK,
        PROVENANCE,
        20,
    )
    with pytest.raises(ValueError):
        dependencies(field)
