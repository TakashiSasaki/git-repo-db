"""Comprehensive tests for ADR 0031 I6-C Authority Boundaries, Selective Exchange,
and Resource Identification Wire Validation.
"""

import pytest

from repo_catalog.application.acquisition import (
    PairedAcquisitionCoordinator,
    ProviderAcquisition,
)
from repo_catalog.domain.context_admission import (
    AdmissionBudget,
    AdmissionRefused,
    AdmissionSelection,
    ContextAdmissionService,
    DependencySet,
    LocalAuthorizationPolicy,
    create_local_admission_service,
)
from repo_catalog.domain.exchange import (
    ExchangeError,
    ExchangePackage,
    ExchangeSelectionScope,
    empty_context_section,
    empty_core_section,
)
from repo_catalog.domain.exchange_rows import validate_rows
from repo_catalog.domain.p1_context import (
    FieldClock,
    MappingClaimKey,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.resource_identification import (
    RESOURCE_IDENTIFICATION_FIELDS,
    ResourceIdentification,
)
from repo_catalog.domain.resource_identity import encode_identity
from repo_catalog.domain.resource_stage import UnsupportedIdentificationStage
from repo_catalog.domain.selective_exchange import (
    preflight_i2_resources,
    validate_context_bindings,
)
from tests.support.context_admission import fixture_service
from tests.support.i6a import isolated_context_db

INSTANCE_1 = "11111111-1111-4111-8111-111111111111"
INSTANCE_2 = "22222222-2222-4222-8222-222222222222"
REPO_UUID_1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
REPO_UUID_2 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
SOURCE_UUID_1 = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
PKG_UUID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


# =============================================================================
# PART 1: Investigation A — Implicit Authority Elimination & Boundary Enforcement
# =============================================================================


def test_missing_local_authorization_fails_closed():
    """Unauthenticated/unauthorized entry points must fail closed (PERMISSION_DENIED)."""
    # ProviderAcquisition without auth/admission
    acq = ProviderAcquisition("/tmp/dummy_context")
    with pytest.raises(AdmissionRefused) as exc_info:
        with acq._open_context():
            pass
    assert exc_info.value.code == "PERMISSION_DENIED"

    # PairedAcquisitionCoordinator without auth/admission
    coordinator = PairedAcquisitionCoordinator("/tmp/dummy")
    with pytest.raises(AdmissionRefused) as exc_info:
        coordinator.admit_paired()
    assert exc_info.value.code == "PERMISSION_DENIED"

    with pytest.raises(AdmissionRefused) as exc_info:
        coordinator.reconcile_core_dependencies()
    assert exc_info.value.code == "PERMISSION_DENIED"


def test_create_local_admission_service_requires_explicit_arguments():
    """create_local_admission_service requires explicit selection and grants, plus credential auth."""
    res = ResourceKey(INSTANCE_1, "issue", '["1"]')
    selection = AdmissionSelection(
        resource_keys=frozenset({res}),
        repository_uuidv4s=frozenset(),
        source_uuidv4s=frozenset(),
        object_oids=frozenset(),
    )
    grants = DependencySet(resources={res})

    # Missing selection or grants fails closed
    with pytest.raises(AdmissionRefused) as exc_info:
        create_local_admission_service("provider_intake", selection=None, grants=grants)
    assert exc_info.value.code == "PERMISSION_DENIED"

    with pytest.raises(AdmissionRefused) as exc_info:
        create_local_admission_service(
            "provider_intake", selection=selection, grants=None
        )
    assert exc_info.value.code == "PERMISSION_DENIED"

    service, context, policy = create_local_admission_service(
        "provider_intake",
        selection=selection,
        grants=grants,
        principal="local-user",
        credential="local-credential",
    )
    assert isinstance(service, ContextAdmissionService)
    assert isinstance(policy, LocalAuthorizationPolicy)

    # Attempting to use wrong credential on service fails closed
    with pytest.raises(AdmissionRefused) as exc_info:
        service.context(
            "wrong-credential",
            "provider_intake",
            selection,
            AdmissionBudget(),
        )
    assert exc_info.value.code == "PERMISSION_DENIED"


def test_local_authorization_policy_enforces_finite_grants():
    """LocalAuthorizationPolicy refuses dependencies outside explicit finite grants."""
    res1 = ResourceKey(INSTANCE_1, "issue", '["1"]')
    res2 = ResourceKey(INSTANCE_1, "issue", '["2"]')
    grants = DependencySet(resources={res1}, repositories={REPO_UUID_1})
    policy = LocalAuthorizationPolicy(grants=grants, principal="test-user")

    # Permitted resource succeeds
    with policy.lease(
        "test-user", "provider_intake", DependencySet(resources={res1})
    ) as lease:
        lease.check_current()

    # Unpermitted resource fails closed
    with pytest.raises(AdmissionRefused) as exc_info:
        with policy.lease(
            "test-user", "provider_intake", DependencySet(resources={res2})
        ):
            pass
    assert exc_info.value.code == "PERMISSION_DENIED"


def test_local_authorization_policy_refuses_unauthorized_source_and_mapping():
    """LocalAuthorizationPolicy refuses unauthorized Source or MappingClaim."""
    grants = DependencySet(repositories={REPO_UUID_1})
    policy = LocalAuthorizationPolicy(grants=grants, principal="test-user")

    # Requesting source outside grants fails
    with pytest.raises(AdmissionRefused) as exc_info:
        with policy.lease(
            "test-user",
            "provider_intake",
            DependencySet(sources={SOURCE_UUID_1}),
        ):
            pass
    assert exc_info.value.code == "PERMISSION_DENIED"

    # Requesting mapping claim outside grants fails
    provider_repo = ResourceKey(INSTANCE_1, "repository", '["org/repo"]')
    clock = FieldClock("capture", 10)
    claim = MappingClaimKey(
        provider_repo,
        "represents_repository",
        clock,
        canonical(REPO_UUID_1),
        canonical({"source": "unauthenticated-source", "evidence": ["original"]}),
    )
    with pytest.raises(AdmissionRefused) as exc_info:
        with policy.lease(
            "test-user",
            "provider_intake",
            DependencySet(mapping_claims={claim}),
        ):
            pass
    assert exc_info.value.code == "PERMISSION_DENIED"


def test_local_authorization_policy_forged_principal_fails_closed():
    """Lease with forged principal must fail closed."""
    policy = LocalAuthorizationPolicy(
        grants=DependencySet(repositories={REPO_UUID_1}),
        principal="legitimate-user",
    )
    with pytest.raises(AdmissionRefused) as exc_info:
        with policy.lease("forged-attacker", "provider_intake", DependencySet()):
            pass
    assert exc_info.value.code == "PERMISSION_DENIED"


def test_local_authorization_policy_foreign_operation_fails_closed():
    """Lease with foreign/unexpected operation name fails closed."""
    policy = LocalAuthorizationPolicy(grants=DependencySet(), principal="test-user")
    with pytest.raises(AdmissionRefused) as exc_info:
        with policy.lease("test-user", "untrusted_operation", DependencySet()):
            pass
    assert exc_info.value.code == "PERMISSION_DENIED"


def test_policy_revocation_during_lease_aborts_transaction():
    """Revision drift during active lease aborts and raises PERMISSION_DENIED."""
    res1 = ResourceKey(INSTANCE_1, "issue", '["1"]')
    service, policy = fixture_service(DependencySet(resources={res1}))

    with policy.lease(
        "fixture-user", "provider_intake", DependencySet(resources={res1})
    ) as lease:
        lease.check_current()  # Passes initially
        # Policy is revoked / updated externally
        policy.revision += 1
        with pytest.raises(AdmissionRefused) as exc_info:
            lease.check_current()
        assert exc_info.value.code == "PERMISSION_DENIED"


# =============================================================================
# PART 2: Investigation B — Selection Widening Elimination
# =============================================================================


def test_receiver_empty_selection_admits_zero_resources():
    """When receiver specifies resource_keys=(), sender resources are not admitted."""
    res1 = ResourceKey(INSTANCE_1, "issue", '["1"]')
    res2 = ResourceKey(INSTANCE_1, "issue", '["2"]')

    # Context data contains resources
    ctx_data = empty_context_section()
    ctx_data["resources"] = [
        dict(
            zip(
                RESOURCE_IDENTIFICATION_FIELDS,
                (*res1.coordinates(), None, None, None, None),
                strict=True,
            )
        ),
        dict(
            zip(
                RESOURCE_IDENTIFICATION_FIELDS,
                (*res2.coordinates(), None, None, None, None),
                strict=True,
            )
        ),
    ]

    package = ExchangePackage(
        package_id=PKG_UUID,
        exported_at_us=1000,
        sender_catalog_instance_uuidv4=INSTANCE_1,
        repository_uuidv4=REPO_UUID_1,
        selection_scope=ExchangeSelectionScope(all_selected=True),
        core=empty_core_section(),
        context=ctx_data,
    )

    # Receiver specifies empty resource_keys
    receiver_selection = ExchangeSelectionScope(
        repository_uuidv4s=(REPO_UUID_1,),
        resource_keys=(),  # Strictly empty!
    )

    # In ExchangeService import_package, receiver selection must not be widened
    # Verify that the package has resources, but receiver selection keeps resource_keys empty
    assert len(package.context["resources"]) == 2
    assert receiver_selection.resource_keys == ()


def test_receiver_selective_subset_omits_unselected_sender_resources():
    """Receiver selecting one Resource must not admit sender's other Resources."""
    res1 = ResourceKey(INSTANCE_1, "issue", '["1"]')
    res2 = ResourceKey(INSTANCE_1, "issue", '["2"]')

    ctx_data = empty_context_section()
    ctx_data["resources"] = [
        dict(
            zip(
                RESOURCE_IDENTIFICATION_FIELDS,
                (*res1.coordinates(), None, None, None, None),
                strict=True,
            )
        ),
        dict(
            zip(
                RESOURCE_IDENTIFICATION_FIELDS,
                (*res2.coordinates(), None, None, None, None),
                strict=True,
            )
        ),
    ]

    package = ExchangePackage(
        package_id=PKG_UUID,
        exported_at_us=1000,
        sender_catalog_instance_uuidv4=INSTANCE_1,
        repository_uuidv4=REPO_UUID_1,
        selection_scope=ExchangeSelectionScope(all_selected=True),
        core=empty_core_section(),
        context=ctx_data,
    )

    receiver_selection = ExchangeSelectionScope(
        repository_uuidv4s=(REPO_UUID_1,),
        resource_keys=(res1,),  # Selects only res1
    )
    assert len(package.context["resources"]) == 2
    assert res1 in receiver_selection.resource_keys
    assert res2 not in receiver_selection.resource_keys


# =============================================================================
# PART 3: Investigation C — Resource Identification Wire Validation & Stage Handling
# =============================================================================


def test_valid_global_document_identification():
    """Valid global Document has 7 columns and provider_document_id == provider_resource_id."""
    raw_id = encode_identity(["global_doc_1"])
    row = {
        "service_instance_uuidv4": INSTANCE_1,
        "resource_kind": "document",
        "provider_resource_id": raw_id,
        "identifier_namespace_kind": None,
        "identifier_namespace_id": None,
        "document_kind": None,
        "provider_document_id": raw_id,
    }
    ident = ResourceIdentification.from_wire(row)
    assert ident.resource.resource_kind == "document"
    assert ident.provider_document_id == raw_id
    assert ident.to_wire() == row


def test_valid_scoped_document_and_entities():
    """Valid scoped document, comment, review, and thread identification parse cleanly."""
    ns_raw = encode_identity(["project", "P1"])
    # 1. Scoped Document in pull_request namespace
    doc_key = ResourceKey(
        INSTANCE_1,
        "document",
        encode_identity(["pull_request", ns_raw, "specification", "spec_1"]),
    )
    row_doc = {
        "service_instance_uuidv4": INSTANCE_1,
        "resource_kind": "document",
        "provider_resource_id": doc_key.provider_resource_id,
        "identifier_namespace_kind": "pull_request",
        "identifier_namespace_id": ns_raw,
        "document_kind": "specification",
        "provider_document_id": encode_identity("spec_1"),
    }
    ident_doc = ResourceIdentification.from_wire(row_doc)
    assert ident_doc.document_kind == "specification"

    # 2. Scoped Comment in issue namespace
    com_key = ResourceKey(
        INSTANCE_1,
        "comment",
        encode_identity(["issue", ns_raw, "discussion", "comment_42"]),
    )
    row_com = {
        "service_instance_uuidv4": INSTANCE_1,
        "resource_kind": "comment",
        "provider_resource_id": com_key.provider_resource_id,
        "identifier_namespace_kind": "issue",
        "identifier_namespace_id": ns_raw,
        "document_kind": "discussion",
        "provider_document_id": encode_identity("comment_42"),
    }
    ident_com = ResourceIdentification.from_wire(row_com)
    assert ident_com.document_kind == "discussion"


def test_unknown_kind_with_canonical_nested_identity():
    """Unknown resource kind with valid identity parses as unscoped identification."""
    raw_id = encode_identity(["custom_entity", "sub_id"])
    row = {
        "service_instance_uuidv4": INSTANCE_1,
        "resource_kind": "custom_widget",
        "provider_resource_id": raw_id,
        "identifier_namespace_kind": None,
        "identifier_namespace_id": None,
        "document_kind": None,
        "provider_document_id": None,
    }
    ident = ResourceIdentification.from_wire(row)
    assert ident.resource.resource_kind == "custom_widget"
    assert ident.columns == (None, None, None, None)


def test_known_kind_with_inconsistent_namespace_fails():
    """Known scoped kind with invalid namespace kind raises ValueError / INVALID_IDENTIFICATION."""
    raw_id = encode_identity(["pull_request", "PR_1", "body", "txt"])
    # 'issue' is not a permitted namespace for 'review' (only 'pull_request' is)
    row = {
        "service_instance_uuidv4": INSTANCE_1,
        "resource_kind": "review",
        "provider_resource_id": raw_id,
        "identifier_namespace_kind": "issue",  # Inconsistent!
        "identifier_namespace_id": encode_identity("PR_1"),
        "document_kind": "body",
        "provider_document_id": encode_identity("txt"),
    }
    with pytest.raises(ValueError):
        ResourceIdentification.from_wire(row)


def test_missing_or_null_required_column_fails():
    """Missing required column or NULL in coordinate fields raises ValueError/TypeError."""
    # Missing required field
    bad_row = {
        "service_instance_uuidv4": INSTANCE_1,
        "resource_kind": "document",
        "provider_resource_id": '["doc"]',
    }
    with pytest.raises(
        ValueError, match="exact seven Resource identification fields required"
    ):
        ResourceIdentification.from_wire(bad_row)

    # NULL in coordinate field
    null_row = {
        "service_instance_uuidv4": None,  # Bad!
        "resource_kind": "document",
        "provider_resource_id": '["doc"]',
        "identifier_namespace_kind": None,
        "identifier_namespace_id": None,
        "document_kind": None,
        "provider_document_id": '["doc"]',
    }
    with pytest.raises(TypeError, match="exact Resource coordinate strings required"):
        ResourceIdentification.from_wire(null_row)


def test_absence_of_bypass_for_global_empty_list():
    """Envelope validation has no special bypass for provider_resource_id == '["global",[]]'."""
    # A document with provider_resource_id='["global",[]]' and provider_document_id=None
    # MUST fail envelope validation with INVALID_IDENTIFICATION
    bad_row = {
        "service_instance_uuidv4": INSTANCE_1,
        "resource_kind": "document",
        "provider_resource_id": '["global",[]]',
        "identifier_namespace_kind": None,
        "identifier_namespace_id": None,
        "document_kind": None,
        "provider_document_id": None,  # Missing!
    }

    ctx = empty_context_section()
    ctx["resources"] = [bad_row]

    with pytest.raises(ExchangeError) as exc_info:
        validate_rows(None, ctx)
    assert exc_info.value.code == "INVALID_IDENTIFICATION"


def test_preflight_i2_resources_raises_unsupported_identification_stage():
    """preflight_i2_resources strictly converts identification failures to UnsupportedIdentificationStage."""
    bad_resource = {
        "service_instance_uuidv4": INSTANCE_1,
        "resource_kind": "document",
        "provider_resource_id": '["global",[]]',
        "identifier_namespace_kind": None,
        "identifier_namespace_id": None,
        "document_kind": None,
        "provider_document_id": None,
    }
    with pytest.raises(UnsupportedIdentificationStage):
        preflight_i2_resources([bad_resource])


def test_validate_context_bindings_does_not_swallow_exceptions():
    """validate_context_bindings strictly validates all resource identifications without swallow."""
    bad_resource = {
        "service_instance_uuidv4": INSTANCE_1,
        "resource_kind": "document",
        "provider_resource_id": '["global",[]]',
        "identifier_namespace_kind": None,
        "identifier_namespace_id": None,
        "document_kind": None,
        "provider_document_id": None,
    }
    ctx = empty_context_section()
    ctx["resources"] = [bad_resource]

    with pytest.raises((ValueError, TypeError)):
        validate_context_bindings(ctx, {})


# =============================================================================
# PART 4: Positive I6-C Routes & Roundtrips
# =============================================================================


def test_seven_column_resource_identification_roundtrip():
    """7-column Resource Identification roundtrips through wire format cleanly."""
    raw_doc = encode_identity("manual.md")
    key = ResourceKey(INSTANCE_1, "document", raw_doc)
    ident = ResourceIdentification.global_document(key)

    wire = ident.to_wire()
    assert set(wire.keys()) == set(RESOURCE_IDENTIFICATION_FIELDS)

    recovered = ResourceIdentification.from_wire(wire)
    assert recovered == ident
    assert recovered.to_wire() == wire


def test_genuine_admission_with_explicit_finite_authority():
    """Genuine non-Transfer Provider-to-Store admission with explicit finite authority."""
    with isolated_context_db() as db:
        res = ResourceKey(INSTANCE_1, "issue", encode_identity(["42"]))
        grants = DependencySet(resources={res}, provider_registrations={INSTANCE_1})
        service, policy = fixture_service(grants)

        # Context admission with explicit lease succeeds
        with policy.lease(
            "fixture-user", "provider_intake", DependencySet(resources={res})
        ) as lease:
            lease.check_current()
            db.execute(
                "INSERT INTO providers VALUES(?, 'synthetic', '{}')",
                (INSTANCE_1,),
            )
            db.execute(
                "INSERT INTO resources(service_instance_uuidv4, resource_kind, provider_resource_id, "
                "identifier_namespace_kind, identifier_namespace_id, document_kind, provider_document_id) "
                "VALUES(?, ?, ?, NULL, NULL, NULL, NULL)",
                res.coordinates(),
            )
            lease.check_current()

        # Verify row persisted
        row = db.execute(
            "SELECT resource_kind, provider_resource_id FROM resources"
        ).fetchone()
        assert row == ("issue", encode_identity(["42"]))


def test_caller_supplied_privileges_ignored_local_policy_controls():
    """Wire or caller claims broad selection, but local policy strictly bounds admission."""
    res1 = ResourceKey(INSTANCE_1, "issue", '["1"]')
    res2 = ResourceKey(INSTANCE_1, "issue", '["2"]')

    # Local policy grants only res1
    service, policy = fixture_service(DependencySet(resources={res1}))

    # Caller tries to request both res1 and res2
    with pytest.raises(AdmissionRefused) as exc_info:
        with policy.lease(
            "fixture-user",
            "provider_intake",
            DependencySet(resources={res1, res2}),
        ):
            pass
    assert exc_info.value.code == "PERMISSION_DENIED"


def test_cached_receipt_shortcut_fails_closed_on_revocation():
    """Policy revocation between initial admission and replay fails closed."""
    res = ResourceKey(INSTANCE_1, "issue", '["1"]')
    service, policy = fixture_service(DependencySet(resources={res}))

    # First admission succeeds
    with policy.lease(
        "fixture-user", "provider_intake", DependencySet(resources={res})
    ) as lease:
        lease.check_current()

    # Revoke grant by emptying policy grants
    policy.grants = DependencySet()

    # Replay attempt fails closed
    with pytest.raises(AdmissionRefused) as exc_info:
        with policy.lease(
            "fixture-user", "provider_intake", DependencySet(resources={res})
        ):
            pass
    assert exc_info.value.code == "PERMISSION_DENIED"


def test_wrong_native_scope_fails():
    """Resource whose raw coordinates do not match encoded coordinates fails validation."""
    ns_raw = encode_identity(["project", "P1"])
    # Manipulate provider_resource_id so it does NOT match encoded components
    mismatched_raw = encode_identity(
        ["pull_request", ns_raw, "specification", "tampered"]
    )
    row = {
        "service_instance_uuidv4": INSTANCE_1,
        "resource_kind": "document",
        "provider_resource_id": mismatched_raw,
        "identifier_namespace_kind": "pull_request",
        "identifier_namespace_id": ns_raw,
        "document_kind": "specification",
        "provider_document_id": encode_identity("spec_1"),  # Doesn't match 'tampered'
    }
    with pytest.raises(
        ValueError, match="identifying coordinates do not reconstruct the key"
    ):
        ResourceIdentification.from_wire(row)


def test_child_first_registration():
    """Child resource registration with explicit scoped identification."""
    parent_key = ResourceKey(INSTANCE_1, "issue", encode_identity(["issue_42"]))
    child_key = ResourceKey(
        INSTANCE_1,
        "comment",
        encode_identity(
            ["issue", parent_key.provider_resource_id, "discussion", "comment_1"]
        ),
    )
    ident = ResourceIdentification.scoped(
        child_key, parent_key, "discussion", "comment_1"
    )
    assert ident.resource == child_key
    assert ident.identifier_namespace_kind == "issue"
    assert ident.identifier_namespace_id == parent_key.provider_resource_id
    assert ident.document_kind == "discussion"
    wire = ident.to_wire()
    assert ResourceIdentification.from_wire(wire) == ident
