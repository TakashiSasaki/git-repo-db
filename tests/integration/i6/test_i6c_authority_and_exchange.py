"""Comprehensive tests for ADR 0031 I6-C Authority Boundaries, Selective Exchange,
and Resource Identification Wire Validation.
"""

import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.acquisition import (
    PairedAcquisitionCoordinator,
    ProviderAcquisition,
)
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.acquisition import (
    ProviderIntakeBatch,
    ProviderRegistration,
    RepositoryRegistration,
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
    ExchangeSelectionScope,
    empty_context_section,
)
from repo_catalog.domain.exchange_rows import validate_rows
from repo_catalog.domain.p1_context import (
    FieldClock,
    MappingClaimKey,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.p1_coordination import AdmissionFailure
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
from tests.integration.p5.conftest import init_catalog_stores
from tests.support.context_admission import fixture_service
from tests.support.i6a import isolated_context_db


@pytest.fixture(autouse=True)
def _patch_sqlite_version(monkeypatch):
    monkeypatch.setattr(p1_schema.sqlite3, "sqlite_version_info", (3, 51, 3))
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 51, 3))


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


def test_receiver_empty_selection_admits_zero_resources(tmp_path: Path):
    """When receiver specifies resource_keys=(), sender resources are not admitted."""
    dir_a = tmp_path / "sender"
    repo_id, inst_id = init_catalog_stores(dir_a)
    rk1 = ResourceKey(inst_id, "issue", encode_identity(["1"]))
    rk2 = ResourceKey(inst_id, "issue", encode_identity(["2"]))

    auth_a, adm_a, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(
            resources={rk1, rk2},
            repositories={repo_id},
            provider_registrations={inst_id},
        ),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with Context.transaction(dir_a, authorization=auth_a, admission=adm_a) as ctx:
        ctx.provider(inst_id, "synthetic", "{}")
        ctx.repository(repo_id, "{}")
        ctx.resource(rk1, identification=ResourceIdentification.unscoped(rk1))
        ctx.resource(rk2, identification=ResourceIdentification.unscoped(rk2))

    svc_a = ExchangeService(dir_a)
    pkg = svc_a.export_package(
        selection=ExchangeSelectionScope(
            all_selected=False,
            repository_uuidv4s=(repo_id,),
            resource_keys=(rk1, rk2),
            object_oids=(),
            source_uuidv4s=(),
        )
    )
    assert len(pkg.context["resources"]) == 2

    # Receiver specifies empty resource_keys
    dir_b = tmp_path / "receiver"
    init_catalog_stores(dir_b)
    svc_b = ExchangeService(dir_b)
    sel_empty = ExchangeSelectionScope(
        all_selected=False,
        repository_uuidv4s=(repo_id,),
        resource_keys=(),
        object_oids=(),
        source_uuidv4s=(),
    )
    auth_b, adm_b, policy_b = create_local_admission_service(
        "exchange_import",
        grants=DependencySet(repositories={repo_id}),
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(
            all_selected=False,
            repository_uuidv4s=(repo_id,),
            resource_keys=(),
            object_oids=(),
            source_uuidv4s=(),
            max_work=10000,
        ),
    )
    report = svc_b.import_package(
        pkg,
        permitted_repository_uuidv4s=(repo_id,),
        selection=sel_empty,
        authorization=auth_b,
        admission=adm_b,
        new_request=True,
    )
    assert report.admitted_context_resources == 0
    with closing(sqlite3.connect(dir_b / "context.sqlite3")) as db:
        res_count = db.execute("SELECT count(*) FROM resources").fetchone()[0]
        assert res_count == 0
    # Verify policy calls: never called for resources
    assert not any(c[2].resources for c in policy_b.calls)


def test_receiver_selective_subset_omits_unselected_sender_resources(tmp_path: Path):
    """Receiver selecting one Resource must not admit sender's other Resources."""
    dir_a = tmp_path / "sender"
    repo_id, inst_id = init_catalog_stores(dir_a)
    rk1 = ResourceKey(inst_id, "issue", encode_identity(["1"]))
    rk2 = ResourceKey(inst_id, "issue", encode_identity(["2"]))

    auth_a, adm_a, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(
            resources={rk1, rk2},
            repositories={repo_id},
            provider_registrations={inst_id},
        ),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with Context.transaction(dir_a, authorization=auth_a, admission=adm_a) as ctx:
        ctx.provider(inst_id, "synthetic", "{}")
        ctx.repository(repo_id, "{}")
        ctx.resource(rk1, identification=ResourceIdentification.unscoped(rk1))
        ctx.resource(rk2, identification=ResourceIdentification.unscoped(rk2))

    svc_a = ExchangeService(dir_a)
    pkg = svc_a.export_package(
        selection=ExchangeSelectionScope(
            all_selected=False,
            repository_uuidv4s=(repo_id,),
            resource_keys=(rk1, rk2),
            object_oids=(),
            source_uuidv4s=(),
        )
    )

    # Receiver selects only rk1
    dir_b = tmp_path / "receiver"
    init_catalog_stores(dir_b)
    svc_b = ExchangeService(dir_b)
    sel_subset = ExchangeSelectionScope(
        all_selected=False,
        repository_uuidv4s=(repo_id,),
        resource_keys=(rk1,),
        object_oids=(),
        source_uuidv4s=(),
    )
    auth_b, adm_b, policy_b = create_local_admission_service(
        "exchange_import",
        grants=DependencySet(
            resources={rk1},
            repositories={repo_id},
            provider_registrations={inst_id},
        ),
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(
            all_selected=False,
            repository_uuidv4s=(repo_id,),
            resource_keys=(rk1,),
            object_oids=(),
            source_uuidv4s=(),
            max_work=10000,
        ),
    )
    report = svc_b.import_package(
        pkg,
        permitted_repository_uuidv4s=(repo_id,),
        selection=sel_subset,
        authorization=auth_b,
        admission=adm_b,
        new_request=True,
    )
    assert report.admitted_context_resources == 1
    with closing(sqlite3.connect(dir_b / "context.sqlite3")) as db:
        rows = db.execute(
            "SELECT resource_kind, provider_resource_id FROM resources"
        ).fetchall()
        assert rows == [("issue", encode_identity(["1"]))]
    # Verify policy calls: rk1 observed, rk2 NEVER observed
    admitted_keys = [c[2].resources for c in policy_b.calls if c[2].resources]
    assert any(rk1 in k for k in admitted_keys)
    assert not any(rk2 in k for k in admitted_keys)


def test_paired_provider_authorized_batch_succeeds_and_persists(tmp_path: Path):
    """Authorized paired Provider batch succeeds and persists real records."""
    dir_p = tmp_path / "paired"
    repo_id, inst_id = init_catalog_stores(dir_p)
    batch = ProviderIntakeBatch(
        service_instance_uuidv4=inst_id,
        providers=(ProviderRegistration(inst_id, "synthetic", "{}"),),
        repositories=(RepositoryRegistration(repo_id, "{}"),),
    )
    auth, adm, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(repositories={repo_id}, provider_registrations={inst_id}),
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    coord = PairedAcquisitionCoordinator(dir_p, authorization=auth, admission=adm)
    res = coord.admit_paired(provider_batch=batch)
    assert res.admission.core_committed is True
    assert res.admission.context_committed is True
    with closing(sqlite3.connect(dir_p / "context.sqlite3")) as db:
        prov_rows = db.execute(
            "SELECT service_instance_uuidv4 FROM providers"
        ).fetchall()
        repo_rows = db.execute(
            "SELECT repository_uuidv4 FROM repository_context"
        ).fetchall()
        assert prov_rows == [(inst_id,)]
        assert repo_rows == [(repo_id,)]


def test_paired_provider_missing_authority_fails_closed(tmp_path: Path):
    """No authority supplied to paired coordinator yields typed PERMISSION_DENIED."""
    dir_p = tmp_path / "paired"
    repo_id, inst_id = init_catalog_stores(dir_p)
    batch = ProviderIntakeBatch(
        service_instance_uuidv4=inst_id,
        providers=(ProviderRegistration(inst_id, "synthetic", "{}"),),
        repositories=(RepositoryRegistration(repo_id, "{}"),),
    )
    coord = PairedAcquisitionCoordinator(dir_p)
    with pytest.raises(AdmissionRefused) as exc_info:
        coord.admit_paired(provider_batch=batch)
    assert exc_info.value.code == "PERMISSION_DENIED"


def test_paired_provider_foreign_authority_rejected(tmp_path: Path):
    """Foreign authorization service handle is rejected fail closed."""
    dir_p = tmp_path / "paired"
    repo_id, inst_id = init_catalog_stores(dir_p)
    batch = ProviderIntakeBatch(
        service_instance_uuidv4=inst_id,
        providers=(ProviderRegistration(inst_id, "synthetic", "{}"),),
        repositories=(RepositoryRegistration(repo_id, "{}"),),
    )
    auth1, adm1, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(repositories={repo_id}, provider_registrations={inst_id}),
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    auth2, adm2, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(repositories={repo_id}, provider_registrations={inst_id}),
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    coord = PairedAcquisitionCoordinator(dir_p, authorization=auth1, admission=adm2)
    with pytest.raises(AdmissionRefused) as exc_info:
        coord.admit_paired(provider_batch=batch)
    assert exc_info.value.code == "PERMISSION_DENIED"


def test_paired_provider_wrong_principal_rejected(tmp_path: Path):
    """Mismatched caller principal is rejected fail closed."""
    dir_p = tmp_path / "paired"
    repo_id, inst_id = init_catalog_stores(dir_p)
    batch = ProviderIntakeBatch(
        service_instance_uuidv4=inst_id,
        providers=(ProviderRegistration(inst_id, "synthetic", "{}"),),
        repositories=(RepositoryRegistration(repo_id, "{}"),),
    )
    auth, adm, policy = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(repositories={repo_id}, provider_registrations={inst_id}),
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    policy._principal = "other-principal"
    coord = PairedAcquisitionCoordinator(dir_p, authorization=auth, admission=adm)
    with pytest.raises((AdmissionRefused, AdmissionFailure)) as exc_info:
        coord.admit_paired(provider_batch=batch)
    if isinstance(exc_info.value, AdmissionFailure):
        assert exc_info.value.cause.code == "PERMISSION_DENIED"
    else:
        assert exc_info.value.code == "PERMISSION_DENIED"


def test_paired_provider_denied_dependency_fails_closed_no_writes(tmp_path: Path):
    """Permission denied for dependency results in no unauthorized Context writes."""
    dir_p = tmp_path / "paired"
    repo_id, inst_id = init_catalog_stores(dir_p)
    batch = ProviderIntakeBatch(
        service_instance_uuidv4=inst_id,
        providers=(ProviderRegistration(inst_id, "synthetic", "{}"),),
        repositories=(RepositoryRegistration(repo_id, "{}"),),
    )
    other_repo = str(uuid4())
    auth, adm, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(
            repositories={other_repo}, provider_registrations={inst_id}
        ),
        permitted_repositories=frozenset({other_repo}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    coord = PairedAcquisitionCoordinator(dir_p, authorization=auth, admission=adm)
    with pytest.raises(AdmissionFailure) as exc_info:
        coord.admit_paired(provider_batch=batch)
    assert exc_info.value.cause.code == "PERMISSION_DENIED"
    with closing(sqlite3.connect(dir_p / "context.sqlite3")) as db:
        rows = db.execute("SELECT repository_uuidv4 FROM repository_context").fetchall()
        assert len(rows) == 0


def test_paired_provider_revocation_before_commit_fails_closed(tmp_path: Path):
    """Permission revocation before COMMIT fails closed."""
    dir_p = tmp_path / "paired"
    repo_id, inst_id = init_catalog_stores(dir_p)
    batch = ProviderIntakeBatch(
        service_instance_uuidv4=inst_id,
        providers=(ProviderRegistration(inst_id, "synthetic", "{}"),),
        repositories=(RepositoryRegistration(repo_id, "{}"),),
    )
    auth, adm, policy = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(repositories={repo_id}, provider_registrations={inst_id}),
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    coord = PairedAcquisitionCoordinator(dir_p, authorization=auth, admission=adm)

    def revoke_on_cut(point):
        if point == "during_context":
            policy.grants = DependencySet()

    with pytest.raises(AdmissionFailure) as exc_info:
        coord.admit_paired(provider_batch=batch, cut=revoke_on_cut)
    assert exc_info.value.cause.code == "PERMISSION_DENIED"
    with closing(sqlite3.connect(dir_p / "context.sqlite3")) as db:
        assert db.execute("SELECT count(*) FROM providers").fetchone()[0] == 0


def test_paired_provider_context_callback_failure_preserves_core_and_fails_context(
    tmp_path: Path,
):
    """Context callback failure after Core commit leaves Core committed and Context rolled back."""
    dir_p = tmp_path / "paired"
    repo_id, inst_id = init_catalog_stores(dir_p)
    auth, adm, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(repositories={repo_id}),
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    coord = PairedAcquisitionCoordinator(dir_p, authorization=auth, admission=adm)

    def failing_context_fn(ctx):
        raise RuntimeError("Context callback intentional error")

    def core_fn(core):
        core.admit_repository(repo_id)
        return None

    with pytest.raises(AdmissionFailure) as exc_info:
        coord.admit_paired(core_fn=core_fn, context_fn=failing_context_fn)

    # Core committed first, Context failed
    assert exc_info.value.outcome.core_committed is True
    assert exc_info.value.outcome.context_committed is False
    with closing(sqlite3.connect(dir_p / "core.sqlite3")) as db:
        core_repos = [
            r[0]
            for r in db.execute("SELECT repository_uuidv4 FROM repositories").fetchall()
        ]
        assert repo_id in core_repos


def test_exchange_import_permitted_locally_selected_resource_succeeds(tmp_path: Path):
    """Permitted, locally selected Resource import succeeds in Core+Context receiver."""
    dir_a = tmp_path / "sender"
    repo_id_a, inst_id_a = init_catalog_stores(dir_a)
    rk1 = ResourceKey(inst_id_a, "issue", encode_identity(["1"]))
    auth_a, adm_a, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(
            resources={rk1},
            repositories={repo_id_a},
            provider_registrations={inst_id_a},
        ),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with Context.transaction(dir_a, authorization=auth_a, admission=adm_a) as ctx:
        ctx.provider(inst_id_a, "synthetic", "{}")
        ctx.repository(repo_id_a, "{}")
        ctx.resource(rk1, identification=ResourceIdentification.unscoped(rk1))

    svc_a = ExchangeService(dir_a)
    pkg = svc_a.export_package(
        selection=ExchangeSelectionScope(
            all_selected=False,
            repository_uuidv4s=(repo_id_a,),
            resource_keys=(rk1,),
            object_oids=(),
            source_uuidv4s=(),
        )
    )

    dir_b = tmp_path / "receiver"
    repo_id_b, inst_id_b = init_catalog_stores(dir_b)
    svc_b = ExchangeService(dir_b)
    report = svc_b.import_package(
        pkg,
        permitted_repository_uuidv4s=(repo_id_a,),
        grants=DependencySet(
            resources={rk1},
            repositories={repo_id_a},
            provider_registrations={inst_id_a},
        ),
        new_request=True,
    )
    assert report.admitted_context_resources == 1
    with closing(sqlite3.connect(dir_b / "context.sqlite3")) as db:
        rows = db.execute(
            "SELECT resource_kind, provider_resource_id FROM resources"
        ).fetchall()
        assert rows == [("issue", encode_identity(["1"]))]
    with closing(sqlite3.connect(dir_b / "core.sqlite3")) as db:
        repos = [
            r[0]
            for r in db.execute("SELECT repository_uuidv4 FROM repositories").fetchall()
        ]
        assert repo_id_a in repos


def test_exchange_import_permitted_repo_without_finite_resource_grant_fails_closed(
    tmp_path: Path,
):
    """Permitted repository without finite resource grant fails closed: typed PERMISSION_DENIED, no DB writes."""
    dir_a = tmp_path / "sender"
    repo_id_a, inst_id_a = init_catalog_stores(dir_a)
    rk1 = ResourceKey(inst_id_a, "issue", encode_identity(["1"]))
    auth_a, adm_a, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(
            resources={rk1},
            repositories={repo_id_a},
            provider_registrations={inst_id_a},
        ),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with Context.transaction(dir_a, authorization=auth_a, admission=adm_a) as ctx:
        ctx.provider(inst_id_a, "synthetic", "{}")
        ctx.repository(repo_id_a, "{}")
        ctx.resource(rk1, identification=ResourceIdentification.unscoped(rk1))

    svc_a = ExchangeService(dir_a)
    pkg = svc_a.export_package(
        selection=ExchangeSelectionScope(
            all_selected=False,
            repository_uuidv4s=(repo_id_a,),
            resource_keys=(rk1,),
            object_oids=(),
            source_uuidv4s=(),
        )
    )

    dir_b = tmp_path / "receiver"
    repo_id_b, inst_id_b = init_catalog_stores(dir_b)
    svc_b = ExchangeService(dir_b)
    with pytest.raises(AdmissionRefused) as exc_info:
        svc_b.import_package(
            pkg,
            permitted_repository_uuidv4s=(repo_id_a,),
            # No grants supplied!
            new_request=True,
        )
    assert exc_info.value.code == "PERMISSION_DENIED"

    # Zero database writes
    with closing(sqlite3.connect(dir_b / "context.sqlite3")) as db:
        assert db.execute("SELECT count(*) FROM resources").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM repository_context").fetchone()[0] == 0
    with closing(sqlite3.connect(dir_b / "core.sqlite3")) as db:
        core_repos = [
            r[0]
            for r in db.execute("SELECT repository_uuidv4 FROM repositories").fetchall()
        ]
        assert repo_id_a not in core_repos
        assert core_repos == [repo_id_b]


def test_exchange_import_context_only_receiver_with_grants_succeeds(tmp_path: Path):
    """Context-only receiver with finite grants imports selected resource."""
    dir_a = tmp_path / "sender"
    repo_id_a, inst_id_a = init_catalog_stores(dir_a)
    rk1 = ResourceKey(inst_id_a, "issue", encode_identity(["1"]))
    auth_a, adm_a, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(
            resources={rk1},
            repositories={repo_id_a},
            provider_registrations={inst_id_a},
        ),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with Context.transaction(dir_a, authorization=auth_a, admission=adm_a) as ctx:
        ctx.provider(inst_id_a, "synthetic", "{}")
        ctx.repository(repo_id_a, "{}")
        ctx.resource(rk1, identification=ResourceIdentification.unscoped(rk1))

    svc_a = ExchangeService(dir_a)
    pkg = svc_a.export_package(
        selection=ExchangeSelectionScope(
            all_selected=False,
            repository_uuidv4s=(repo_id_a,),
            resource_keys=(rk1,),
            object_oids=(),
            source_uuidv4s=(),
        )
    )

    # Context-only receiver
    dir_b = tmp_path / "receiver"
    repo_id_b, inst_id_b = init_catalog_stores(dir_b, stores=("context", "operational"))
    svc_b = ExchangeService(dir_b)
    assert not svc_b._has_core()

    report = svc_b.import_package(
        pkg,
        permitted_repository_uuidv4s=(repo_id_a,),
        grants=DependencySet(
            resources={rk1},
            repositories={repo_id_a},
            provider_registrations={inst_id_a},
        ),
        new_request=True,
    )
    assert report.admitted_context_resources == 1
    with closing(sqlite3.connect(dir_b / "context.sqlite3")) as db:
        rows = db.execute(
            "SELECT resource_kind, provider_resource_id FROM resources"
        ).fetchall()
        assert rows == [("issue", encode_identity(["1"]))]


def test_exchange_import_foreign_receiver_authority_rejected(tmp_path: Path):
    """Foreign receiver authority service is rejected fail closed with zero database writes."""
    dir_a = tmp_path / "sender"
    repo_id_a, inst_id_a = init_catalog_stores(dir_a)
    rk1 = ResourceKey(inst_id_a, "issue", encode_identity(["1"]))
    auth_a, adm_a, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(
            resources={rk1},
            repositories={repo_id_a},
            provider_registrations={inst_id_a},
        ),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with Context.transaction(dir_a, authorization=auth_a, admission=adm_a) as ctx:
        ctx.provider(inst_id_a, "synthetic", "{}")
        ctx.repository(repo_id_a, "{}")
        ctx.resource(rk1, identification=ResourceIdentification.unscoped(rk1))

    svc_a = ExchangeService(dir_a)
    pkg = svc_a.export_package(
        selection=ExchangeSelectionScope(
            all_selected=False,
            repository_uuidv4s=(repo_id_a,),
            resource_keys=(rk1,),
            object_oids=(),
            source_uuidv4s=(),
        )
    )

    dir_b = tmp_path / "receiver"
    repo_id_b, inst_id_b = init_catalog_stores(dir_b)
    svc_b = ExchangeService(dir_b)

    auth1, adm1, _ = create_local_admission_service(
        "exchange_import",
        grants=DependencySet(resources={rk1}, repositories={repo_id_a}),
        permitted_repositories=frozenset({repo_id_a}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    auth2, adm2, _ = create_local_admission_service(
        "exchange_import",
        grants=DependencySet(resources={rk1}, repositories={repo_id_a}),
        permitted_repositories=frozenset({repo_id_a}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with pytest.raises(AdmissionRefused) as exc_info:
        svc_b.import_package(
            pkg,
            permitted_repository_uuidv4s=(repo_id_a,),
            authorization=auth1,
            admission=adm2,
            new_request=True,
        )
    assert exc_info.value.code == "PERMISSION_DENIED"
    with closing(sqlite3.connect(dir_b / "context.sqlite3")) as db:
        assert db.execute("SELECT count(*) FROM resources").fetchone()[0] == 0


def test_exchange_import_mismatched_receiver_principal_rejected(tmp_path: Path):
    """Mismatched receiver principal is rejected fail closed."""
    dir_a = tmp_path / "sender"
    repo_id_a, inst_id_a = init_catalog_stores(dir_a)
    rk1 = ResourceKey(inst_id_a, "issue", encode_identity(["1"]))
    auth_a, adm_a, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(
            resources={rk1},
            repositories={repo_id_a},
            provider_registrations={inst_id_a},
        ),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with Context.transaction(dir_a, authorization=auth_a, admission=adm_a) as ctx:
        ctx.provider(inst_id_a, "synthetic", "{}")
        ctx.repository(repo_id_a, "{}")
        ctx.resource(rk1, identification=ResourceIdentification.unscoped(rk1))

    svc_a = ExchangeService(dir_a)
    pkg = svc_a.export_package(
        selection=ExchangeSelectionScope(
            all_selected=False,
            repository_uuidv4s=(repo_id_a,),
            resource_keys=(rk1,),
            object_oids=(),
            source_uuidv4s=(),
        )
    )

    dir_b = tmp_path / "receiver"
    repo_id_b, inst_id_b = init_catalog_stores(dir_b)
    svc_b = ExchangeService(dir_b)

    auth, adm, policy = create_local_admission_service(
        "exchange_import",
        grants=DependencySet(resources={rk1}, repositories={repo_id_a}),
        permitted_repositories=frozenset({repo_id_a}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    policy._principal = "different-principal"
    with pytest.raises(AdmissionRefused) as exc_info:
        svc_b.import_package(
            pkg,
            permitted_repository_uuidv4s=(repo_id_a,),
            authorization=auth,
            admission=adm,
            new_request=True,
        )
    assert exc_info.value.code == "PERMISSION_DENIED"


def test_exchange_import_revocation_between_validation_and_lease_fails_closed(
    tmp_path: Path,
):
    """Revocation between initial validation and commit fails closed."""
    dir_a = tmp_path / "sender"
    repo_id_a, inst_id_a = init_catalog_stores(dir_a)
    rk1 = ResourceKey(inst_id_a, "issue", encode_identity(["1"]))
    auth_a, adm_a, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(
            resources={rk1},
            repositories={repo_id_a},
            provider_registrations={inst_id_a},
        ),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with Context.transaction(dir_a, authorization=auth_a, admission=adm_a) as ctx:
        ctx.provider(inst_id_a, "synthetic", "{}")
        ctx.repository(repo_id_a, "{}")
        ctx.resource(rk1, identification=ResourceIdentification.unscoped(rk1))

    svc_a = ExchangeService(dir_a)
    pkg = svc_a.export_package(
        selection=ExchangeSelectionScope(
            all_selected=False,
            repository_uuidv4s=(repo_id_a,),
            resource_keys=(rk1,),
            object_oids=(),
            source_uuidv4s=(),
        )
    )

    dir_b = tmp_path / "receiver"
    repo_id_b, inst_id_b = init_catalog_stores(dir_b)
    svc_b = ExchangeService(dir_b)

    auth, adm, policy = create_local_admission_service(
        "exchange_import",
        grants=DependencySet(
            resources={rk1},
            repositories={repo_id_a},
            provider_registrations={inst_id_a},
        ),
        permitted_repositories=frozenset({repo_id_a}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )

    def revoke_cut(point):
        if point == "during_context":
            policy.grants = DependencySet()

    with pytest.raises(AdmissionFailure) as exc_info:
        svc_b.import_package(
            pkg,
            permitted_repository_uuidv4s=(repo_id_a,),
            authorization=auth,
            admission=adm,
            cut=revoke_cut,
            new_request=True,
        )
    assert exc_info.value.cause.code == "PERMISSION_DENIED"


def test_exchange_import_exact_replay_and_revocation(tmp_path: Path):
    """Replay succeeds when authorized; fails closed upon revocation."""
    dir_a = tmp_path / "sender"
    repo_id_a, inst_id_a = init_catalog_stores(dir_a)
    rk1 = ResourceKey(inst_id_a, "issue", encode_identity(["1"]))
    auth_a, adm_a, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(
            resources={rk1},
            repositories={repo_id_a},
            provider_registrations={inst_id_a},
        ),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with Context.transaction(dir_a, authorization=auth_a, admission=adm_a) as ctx:
        ctx.provider(inst_id_a, "synthetic", "{}")
        ctx.repository(repo_id_a, "{}")
        ctx.resource(rk1, identification=ResourceIdentification.unscoped(rk1))

    svc_a = ExchangeService(dir_a)
    pkg = svc_a.export_package(
        selection=ExchangeSelectionScope(
            all_selected=False,
            repository_uuidv4s=(repo_id_a,),
            resource_keys=(rk1,),
            object_oids=(),
            source_uuidv4s=(),
        )
    )

    dir_b = tmp_path / "receiver"
    repo_id_b, inst_id_b = init_catalog_stores(dir_b)
    svc_b = ExchangeService(dir_b)

    auth, adm, policy = create_local_admission_service(
        "exchange_import",
        grants=DependencySet(
            resources={rk1},
            repositories={repo_id_a},
            provider_registrations={inst_id_a},
        ),
        permitted_repositories=frozenset({repo_id_a}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )

    # First import
    rep1 = svc_b.import_package(
        pkg,
        permitted_repository_uuidv4s=(repo_id_a,),
        authorization=auth,
        admission=adm,
        new_request=True,
    )
    assert rep1.idempotent_replay is False

    # Second import (replay)
    rep2 = svc_b.import_package(
        pkg,
        permitted_repository_uuidv4s=(repo_id_a,),
        authorization=auth,
        admission=adm,
        new_request=True,
    )
    assert rep2.idempotent_replay is True

    # Revoke grant
    policy.grants = DependencySet()
    with pytest.raises(AdmissionRefused) as exc_info:
        svc_b.import_package(
            pkg,
            permitted_repository_uuidv4s=(repo_id_a,),
            authorization=auth,
            admission=adm,
            new_request=True,
        )
    assert exc_info.value.code == "PERMISSION_DENIED"


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


def test_exchange_import_missing_provider_registration_fails_closed_zero_writes(
    tmp_path,
):
    """P1 regression: Core+Context package with provider registration and resource.

    Grants cover resource and repository but omit provider_registrations.
    Must fail closed immediately with PERMISSION_DENIED before Core commit (0 Core & Context writes).
    """
    sender_path = tmp_path / "sender"
    receiver_path = tmp_path / "receiver"
    repo_uuid = str(uuid4())
    receiver_repo = str(uuid4())
    sender_instance = str(uuid4())
    receiver_instance = str(uuid4())

    init_catalog_stores(
        sender_path,
        repository_uuidv4=repo_uuid,
        catalog_instance_uuidv4=sender_instance,
    )
    init_catalog_stores(
        receiver_path,
        repository_uuidv4=receiver_repo,
        catalog_instance_uuidv4=receiver_instance,
    )

    # Populate sender with Provider, Repository, and Resource
    res_key = ResourceKey(sender_instance, "issue", encode_identity(["bug-99"]))
    auth_s, adm_s, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(
            resources={res_key},
            repositories={repo_uuid},
            provider_registrations={sender_instance},
        ),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with Context.transaction(sender_path, authorization=auth_s, admission=adm_s) as ctx:
        ctx.provider(sender_instance, "github", "{}")
        ctx.repository(repo_uuid)
        ctx.resource(res_key)

    sender_service = ExchangeService(sender_path)
    pkg = sender_service.export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )

    receiver_service = ExchangeService(receiver_path)

    # Receiver grant covers resource and repo, but OMITS provider_registrations!
    grants_missing_provider = DependencySet(
        resources={res_key},
        repositories={repo_uuid},
        # provider_registrations is EMPTY!
    )

    with pytest.raises(AdmissionRefused) as exc_info:
        receiver_service.import_package(
            pkg,
            permitted_repository_uuidv4s=(repo_uuid,),
            grants=grants_missing_provider,
            new_request=True,
        )
    assert exc_info.value.code == "PERMISSION_DENIED"

    # CRITICAL: Verify ZERO writes of sender's repo/provider/resource to both Core and Context
    with sqlite3.connect(receiver_path / "core.sqlite3") as core_db:
        core_count = core_db.execute(
            "SELECT count(*) FROM repositories WHERE repository_uuidv4=?", (repo_uuid,)
        ).fetchone()[0]
        assert core_count == 0

    with sqlite3.connect(receiver_path / "context.sqlite3") as ctx_db:
        prov_count = ctx_db.execute("SELECT count(*) FROM providers").fetchone()[0]
        res_count = ctx_db.execute("SELECT count(*) FROM resources").fetchone()[0]
        assert prov_count == 0
        assert res_count == 0


def test_exchange_import_missing_repository_grant_fails_closed_zero_writes(tmp_path):
    """P1 regression: permitted_repository_uuidv4s has repo, but grants.repositories omits it.

    Must fail closed immediately with PERMISSION_DENIED and 0 writes.
    """
    sender_path = tmp_path / "sender"
    receiver_path = tmp_path / "receiver"
    repo_uuid = str(uuid4())
    receiver_repo = str(uuid4())
    sender_instance = str(uuid4())
    receiver_instance = str(uuid4())

    init_catalog_stores(
        sender_path,
        repository_uuidv4=repo_uuid,
        catalog_instance_uuidv4=sender_instance,
    )
    init_catalog_stores(
        receiver_path,
        repository_uuidv4=receiver_repo,
        catalog_instance_uuidv4=receiver_instance,
    )

    res_key = ResourceKey(sender_instance, "issue", encode_identity(["bug-100"]))
    auth_s, adm_s, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(
            resources={res_key},
            repositories={repo_uuid},
            provider_registrations={sender_instance},
        ),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with Context.transaction(sender_path, authorization=auth_s, admission=adm_s) as ctx:
        ctx.provider(sender_instance, "github", "{}")
        ctx.repository(repo_uuid)
        ctx.resource(res_key)

    sender_service = ExchangeService(sender_path)
    pkg = sender_service.export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )

    receiver_service = ExchangeService(receiver_path)

    # Receiver grant covers resource and provider, but OMITS repositories!
    grants_missing_repo = DependencySet(
        resources={res_key},
        provider_registrations={sender_instance},
        # repositories is EMPTY!
    )

    with pytest.raises(AdmissionRefused) as exc_info:
        receiver_service.import_package(
            pkg,
            permitted_repository_uuidv4s=(repo_uuid,),
            grants=grants_missing_repo,
            new_request=True,
        )
    assert exc_info.value.code == "PERMISSION_DENIED"

    with sqlite3.connect(receiver_path / "core.sqlite3") as core_db:
        core_count = core_db.execute(
            "SELECT count(*) FROM repositories WHERE repository_uuidv4=?", (repo_uuid,)
        ).fetchone()[0]
        assert core_count == 0

    with sqlite3.connect(receiver_path / "context.sqlite3") as ctx_db:
        assert ctx_db.execute("SELECT count(*) FROM resources").fetchone()[0] == 0


def test_exchange_import_custom_policy_supported_interface(tmp_path):
    """P2 regression: Custom AuthorizationPolicy without _principal or _permitted_repositories.

    Must validate through policy protocol lease() without raising AttributeError.
    """
    from contextlib import contextmanager

    class CustomMinimalPolicy:
        """Implements only the public AuthorizationPolicy protocol."""

        def __init__(self, allowed_resources, allowed_repositories, allowed_providers):
            self.allowed_resources = allowed_resources
            self.allowed_repositories = allowed_repositories
            self.allowed_providers = allowed_providers
            self.lease_calls = []

        @contextmanager
        def lease(self, principal, operation, dependencies):
            self.lease_calls.append((principal, operation, dependencies))
            if (
                not dependencies.resources <= self.allowed_resources
                or not dependencies.repositories <= self.allowed_repositories
                or not dependencies.provider_registrations <= self.allowed_providers
            ):
                raise AdmissionRefused("PERMISSION_DENIED")

            class MinimalLease:
                def check_current(self):
                    pass

            yield MinimalLease()

    sender_path = tmp_path / "sender"
    receiver_path = tmp_path / "receiver"
    repo_uuid = str(uuid4())
    sender_instance = str(uuid4())
    receiver_instance = str(uuid4())

    init_catalog_stores(
        sender_path,
        repository_uuidv4=repo_uuid,
        catalog_instance_uuidv4=sender_instance,
    )
    init_catalog_stores(
        receiver_path,
        repository_uuidv4=repo_uuid,
        catalog_instance_uuidv4=receiver_instance,
    )

    res_key = ResourceKey(sender_instance, "issue", encode_identity(["custom-1"]))
    auth_s, adm_s, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(
            resources={res_key},
            repositories={repo_uuid},
            provider_registrations={sender_instance},
        ),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with Context.transaction(sender_path, authorization=auth_s, admission=adm_s) as ctx:
        ctx.provider(sender_instance, "synthetic", "{}")
        ctx.repository(repo_uuid)
        ctx.resource(res_key)

    pkg = ExchangeService(sender_path).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )

    # Negative case: custom policy does not allow res_key
    custom_policy_denying = CustomMinimalPolicy(
        allowed_resources=set(),
        allowed_repositories={repo_uuid},
        allowed_providers={sender_instance},
    )
    auth_denying = ContextAdmissionService(
        custom_policy_denying, lambda cred: "custom-user"
    )
    adm_denying = auth_denying.context(
        "cred",
        "exchange_import",
        ExchangeSelectionScope(all_selected=True),
        AdmissionBudget(),
    )

    receiver_service = ExchangeService(receiver_path)
    with pytest.raises(AdmissionRefused) as exc_info:
        receiver_service.import_package(
            pkg,
            permitted_repository_uuidv4s=(repo_uuid,),
            authorization=auth_denying,
            admission=adm_denying,
            new_request=True,
        )
    assert exc_info.value.code == "PERMISSION_DENIED"

    # Positive case: custom policy allows res_key
    custom_policy_allowing = CustomMinimalPolicy(
        allowed_resources={res_key},
        allowed_repositories={repo_uuid},
        allowed_providers={sender_instance},
    )
    auth_allowing = ContextAdmissionService(
        custom_policy_allowing, lambda cred: "custom-user"
    )
    adm_allowing = auth_allowing.context(
        "cred",
        "exchange_import",
        ExchangeSelectionScope(all_selected=True),
        AdmissionBudget(),
    )

    report = receiver_service.import_package(
        pkg,
        permitted_repository_uuidv4s=(repo_uuid,),
        authorization=auth_allowing,
        admission=adm_allowing,
        new_request=True,
    )
    assert report.admitted_context_resources == 1
    with sqlite3.connect(receiver_path / "context.sqlite3") as ctx_db:
        assert ctx_db.execute("SELECT count(*) FROM resources").fetchone()[0] == 1
