"""Independent behavioral verification test suite for ADR 0031 I6-C obligations.

Verifies:
1. Single full sender package and independently configured receiver-local finite grants
   (DependencySet without ambient sender authority).
2. Empty, strict-subset, and complete receiver selection on that same package.
3. Exact admitted/omitted rowsets and atomic-unit semantics in SQLite tables
   (repository_context, resources, resource_repository_relations, resource_relations,
   repository_mapping_dispositions, sources, source_repositories).
4. Both Context-only (ExchangeService.import_package) and paired Core+Context
   (PairedAcquisitionCoordinator) import paths.
5. Genuine handle issued by another authorization service passed into product routes fails closed.
6. Permission revocation triggered at actual transaction/COMMIT boundaries.
7. Exact replay and cached receipt behavior after revocation (fail-closed receipt invariants).
8. Source, MappingClaim, and Disposition permissions verified independently with withholding tests.
9. Authorized paired Provider acquisition and supported Core-first failure/recovery bookkeeping
   (Core commit durable, Context rolled back, operational recovery state tracked).
10. Retention of both Transfer SQL fences (i2_transfer_stage_fence, i2_transfer_report_stage_fence)
    and ordinary Transfer refusal with UnsupportedResourceStage.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest

from repo_catalog.adapters.github.production_intake import github_repository_id
from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.acquisition import (
    PairedAcquisitionCoordinator,
    ProviderAcquisition,
)
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.acquisition import (
    ProviderIntakeBatch,
    ProviderRegistration,
    ProviderTimelineIntake,
    RepositoryRegistration,
    make_provenance,
)
from repo_catalog.domain.context_admission import (
    AdmissionRefused,
    AdmissionSelection,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.exchange import FORMAT, ExchangeSelectionScope
from repo_catalog.domain.p1_context import (
    FieldClock,
    MappingDisposition,
    ResourceKey,
    ResourceRepositoryRelation,
    canonical,
)
from repo_catalog.domain.p1_coordination import AdmissionFailure, RequestIdentity
from repo_catalog.domain.production_context import ResourceRelation
from repo_catalog.domain.resource_identification import ResourceIdentification
from repo_catalog.domain.resource_identity import encode_identity
from repo_catalog.domain.resource_stage import UnsupportedResourceStage


def _init_catalog_stores(
    directory: Path,
    *,
    repo_id: str | None = None,
    instance_id: str | None = None,
    include_core: bool = True,
    include_context: bool = True,
    include_operational: bool = True,
) -> tuple[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    repository_uuidv4 = repo_id or str(uuid4())
    catalog_instance_uuidv4 = instance_id or str(uuid4())
    if include_core:
        p1_schema.initialize(
            directory / "core.sqlite3",
            "core",
            repository_uuidv4,
            catalog_instance_uuidv4,
        )
    if include_context:
        p1_schema.initialize(
            directory / "context.sqlite3",
            "context",
            repository_uuidv4,
            catalog_instance_uuidv4,
        )
    if include_operational:
        p1_schema.initialize(
            directory / "operational.sqlite3",
            "operational",
            repository_uuidv4,
            catalog_instance_uuidv4,
        )
    return repository_uuidv4, catalog_instance_uuidv4


# =============================================================================
# OBLIGATION 1, 2, 3: Single Sender Package, Independent Receiver Grants,
# Empty/Subset/Complete Receiver Selection, and Exact SQLite Rowsets
# =============================================================================


def test_obligation_1_2_3_single_package_receiver_selections_and_rowsets(
    tmp_path: Path,
) -> None:
    """Obligations 1, 2, 3: Export one full package; test empty, subset, and complete receiver selection.

    Asserts:
    - Sender exports a single package containing 2 repositories, 1 source, 3 resources,
      mapping claims, resource relation, and disposition.
    - Receiver configures finite DependencySet independently (no sender authority).
    - Empty receiver selection admits 0 rows to all SQLite tables.
    - Strict-subset receiver selection admits exactly selected Repo A and Resource A1,
      omitting Repo B, Resource A2, Resource B1, mapping claims, and relations.
    - Resource relation rel_a1_a2 is omitted under subset selection because member A2 is unselected
      (enforcing atomic-unit semantics).
    - Complete receiver selection admits all rows across all tables.
    """
    sender_dir = tmp_path / "sender"
    repo_a, inst_s = _init_catalog_stores(sender_dir)
    repo_b = str(uuid4())
    source_1 = str(uuid4())
    service = inst_s

    # Define resources:
    # r_repo: represents repository for repo_a
    # res_a1: issue 101 on repo_a
    # res_a2: issue 102 on repo_a
    # res_b1: issue 201 on repo_b
    r_repo = ResourceKey(service, "repository", encode_identity(["repo_a_ext"]))
    res_a1 = ResourceKey(service, "issue", encode_identity(["101"]))
    res_a2 = ResourceKey(service, "issue", encode_identity(["102"]))
    res_b1 = ResourceKey(service, "issue", encode_identity(["201"]))

    # Claims:
    # claim_rep: represents repo_a
    claim_rep = ResourceRepositoryRelation(
        r_repo,
        "represents_repository",
        FieldClock("clock:repo", 1),
        canonical(repo_a),
        canonical({"source": "test", "evidence": "claim_rep"}),
        100,
    )
    # Disposition for claim_rep
    disp_rep = MappingDisposition(
        claim_rep.claim_key,
        "withdraw",
        FieldClock("clock:disp", 2),
        canonical({"source": "test", "evidence": "disp_rep"}),
        200,
    )

    # ResourceRelation: res_a1 references res_a2
    rel_a1_a2 = ResourceRelation(
        res_a1,
        "references",
        (res_a2,),
        canonical({"source": "test", "evidence": "rel_ref"}),
        canonical({"scope": "global"}),
        150,
    )

    # Populate sender catalog
    sender_grants = DependencySet(
        repositories={repo_a, repo_b},
        sources={source_1},
        source_repository_pairs={(source_1, repo_a)},
        resources={r_repo, res_a1, res_a2, res_b1},
        mapping_claims={claim_rep.claim_key},
        dispositions={disp_rep.disposition_key},
        provider_registrations={service},
    )
    auth_s, adm_s, _ = create_local_admission_service(
        "provider_intake",
        grants=sender_grants,
        permitted_repositories=frozenset({repo_a, repo_b}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )

    with Context.transaction(sender_dir, authorization=auth_s, admission=adm_s) as ctx:
        ctx.provider(service, "synthetic", "{}")
        ctx.repository(repo_a, "{}")
        ctx.repository(repo_b, "{}")
        ctx.source(source_1, service, "{}")
        ctx.associate_source(
            source_1,
            repo_a,
            canonical({"source": "test", "evidence": "assoc_1"}),
        )
        ctx.resource(r_repo, identification=ResourceIdentification.unscoped(r_repo))
        ctx.resource(res_a1, identification=ResourceIdentification.unscoped(res_a1))
        ctx.resource(res_a2, identification=ResourceIdentification.unscoped(res_a2))
        ctx.resource(res_b1, identification=ResourceIdentification.unscoped(res_b1))
        ctx.admit_repository_relation(claim_rep)
        ctx.admit_mapping_disposition(disp_rep)
        ctx.relation(rel_a1_a2)

    # Sender exports a SINGLE full package (all_selected=True)
    sender_service = ExchangeService(sender_dir)
    full_pkg = sender_service.export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )
    assert full_pkg.format == FORMAT
    assert len(full_pkg.context["repositories"]) == 2
    assert len(full_pkg.context["resources"]) == 4
    assert len(full_pkg.context["resource_repository_relations"]) == 1
    assert len(full_pkg.context["resource_relations"]) == 1
    assert len(full_pkg.context["repository_mapping_dispositions"]) == 1

    # -------------------------------------------------------------------------
    # PART 2A: Empty Receiver Selection on the same full package
    # -------------------------------------------------------------------------
    recv_empty_dir = tmp_path / "receiver_empty"
    _init_catalog_stores(recv_empty_dir)
    empty_receiver_service = ExchangeService(recv_empty_dir)

    empty_selection = ExchangeSelectionScope(
        all_selected=False,
        repository_uuidv4s=(),
        resource_keys=(),
        object_oids=(),
        source_uuidv4s=(),
    )
    # Receiver configures finite grants independently
    empty_grants = DependencySet(provider_registrations={service})
    auth_empty, adm_empty, _ = create_local_admission_service(
        "exchange_import",
        grants=empty_grants,
        permitted_repositories=frozenset(),
        selection=empty_selection,
    )

    report_empty = empty_receiver_service.import_package(
        full_pkg,
        selection=empty_selection,
        permitted_repository_uuidv4s=(),
        authorization=auth_empty,
        admission=adm_empty,
        new_request=True,
    )
    assert report_empty.admitted_context_resources == 0

    # Verify SQLite rowsets: exactly 0 rows in all relevant Context tables
    with closing(sqlite3.connect(recv_empty_dir / "context.sqlite3")) as db:
        assert db.execute("SELECT count(*) FROM repository_context").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM resources").fetchone()[0] == 0
        assert (
            db.execute("SELECT count(*) FROM resource_repository_relations").fetchone()[
                0
            ]
            == 0
        )
        assert db.execute("SELECT count(*) FROM resource_relations").fetchone()[0] == 0
        assert (
            db.execute(
                "SELECT count(*) FROM repository_mapping_dispositions"
            ).fetchone()[0]
            == 0
        )
        assert db.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM source_repositories").fetchone()[0] == 0

    # -------------------------------------------------------------------------
    # PART 2B: Strict-Subset Receiver Selection on the same full package
    # -------------------------------------------------------------------------
    recv_subset_dir = tmp_path / "receiver_subset"
    _init_catalog_stores(recv_subset_dir)
    subset_receiver_service = ExchangeService(recv_subset_dir)

    # Select ONLY repo_a and res_a1 (omit repo_b, res_a2, res_b1, r_repo)
    # Set max_depth=0 to test strict subset without expanding along relations
    subset_selection = ExchangeSelectionScope(
        all_selected=False,
        repository_uuidv4s=(repo_a,),
        resource_keys=(res_a1,),
        object_oids=(),
        source_uuidv4s=(),
        max_depth=0,
    )
    subset_grants = DependencySet(
        repositories={repo_a},
        resources={res_a1},
        provider_registrations={service},
    )
    auth_subset, adm_subset, _ = create_local_admission_service(
        "exchange_import",
        grants=subset_grants,
        permitted_repositories=frozenset({repo_a}),
        selection=subset_selection,
    )

    report_subset = subset_receiver_service.import_package(
        full_pkg,
        selection=subset_selection,
        permitted_repository_uuidv4s=(repo_a,),
        authorization=auth_subset,
        admission=adm_subset,
        new_request=True,
    )
    assert report_subset.admitted_context_resources == 1
    assert len(report_subset.omissions) > 0

    # Verify SQLite rowsets for subset:
    with closing(sqlite3.connect(recv_subset_dir / "context.sqlite3")) as db:
        # repository_context: repo_a admitted, repo_b omitted
        repos = [
            r[0]
            for r in db.execute(
                "SELECT repository_uuidv4 FROM repository_context"
            ).fetchall()
        ]
        assert repos == [repo_a]

        # resources: res_a1 admitted, res_a2, res_b1, r_repo omitted
        res_ids = [
            r[0]
            for r in db.execute("SELECT provider_resource_id FROM resources").fetchall()
        ]
        assert res_ids == [encode_identity(["101"])]

        # resource_relations: exactly 0 because rel_a1_a2 depends on unselected res_a2
        # (atomic unit semantics verified)
        assert db.execute("SELECT count(*) FROM resource_relations").fetchone()[0] == 0

        # resource_repository_relations: 0 because r_repo was not selected
        assert (
            db.execute("SELECT count(*) FROM resource_repository_relations").fetchone()[
                0
            ]
            == 0
        )
        assert (
            db.execute(
                "SELECT count(*) FROM repository_mapping_dispositions"
            ).fetchone()[0]
            == 0
        )

    # -------------------------------------------------------------------------
    # PART 2C: Complete Receiver Selection on the same full package
    # -------------------------------------------------------------------------
    recv_complete_dir = tmp_path / "receiver_complete"
    _init_catalog_stores(recv_complete_dir)
    complete_receiver_service = ExchangeService(recv_complete_dir)

    complete_selection = ExchangeSelectionScope(all_selected=True)
    complete_grants = DependencySet(
        repositories={repo_a, repo_b},
        sources={source_1},
        source_repository_pairs={(source_1, repo_a)},
        resources={r_repo, res_a1, res_a2, res_b1},
        mapping_claims={claim_rep.claim_key},
        dispositions={disp_rep.disposition_key},
        provider_registrations={service},
    )
    auth_comp, adm_comp, _ = create_local_admission_service(
        "exchange_import",
        grants=complete_grants,
        permitted_repositories=frozenset({repo_a, repo_b}),
        selection=complete_selection,
    )

    report_complete = complete_receiver_service.import_package(
        full_pkg,
        selection=complete_selection,
        permitted_repository_uuidv4s=(repo_a, repo_b),
        authorization=auth_comp,
        admission=adm_comp,
        new_request=True,
    )
    assert report_complete.admitted_context_resources == 4

    # Verify complete SQLite rowsets:
    with closing(sqlite3.connect(recv_complete_dir / "context.sqlite3")) as db:
        repos = set(
            r[0]
            for r in db.execute(
                "SELECT repository_uuidv4 FROM repository_context"
            ).fetchall()
        )
        assert repos == {repo_a, repo_b}

        res_count = db.execute("SELECT count(*) FROM resources").fetchone()[0]
        assert res_count == 4

        claim_count = db.execute(
            "SELECT count(*) FROM resource_repository_relations"
        ).fetchone()[0]
        assert claim_count == 1

        rel_count = db.execute("SELECT count(*) FROM resource_relations").fetchone()[0]
        assert rel_count == 1

        disp_count = db.execute(
            "SELECT count(*) FROM repository_mapping_dispositions"
        ).fetchone()[0]
        assert disp_count == 1

        src_count = db.execute("SELECT count(*) FROM sources").fetchone()[0]
        assert src_count == 1

        sr_count = db.execute("SELECT count(*) FROM source_repositories").fetchone()[0]
        assert sr_count == 1


# =============================================================================
# OBLIGATION 4: Both Context-Only and Paired Core+Context Import Paths
# =============================================================================


def test_obligation_4_context_only_and_paired_import_paths(tmp_path: Path) -> None:
    """Obligation 4: Exercise both Context-only (ExchangeService.import_package) and Paired Core+Context (PairedAcquisitionCoordinator).

    Asserts:
    - Context-only path executes when receiver has no Core store; imports Context cleanly.
    - Paired Core+Context coordinator path executes atomic Core-first and Context-second steps.
    - SQLite rows in Core and Context verify persistence on their respective paths.
    """
    # 4A: Context-only import path
    ctx_only_dir = tmp_path / "context_only_receiver"
    repo_id, inst_id = _init_catalog_stores(
        ctx_only_dir, include_core=False, include_context=True, include_operational=True
    )
    assert not (ctx_only_dir / "core.sqlite3").exists()

    res_key = ResourceKey(inst_id, "issue", encode_identity(["ctx_only_1"]))
    grants = DependencySet(
        repositories={repo_id},
        resources={res_key},
        provider_registrations={inst_id},
    )
    auth_ctx, adm_ctx, _ = create_local_admission_service(
        "exchange_import",
        grants=grants,
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )

    # Create Context-only package from temporary sender
    sender_dir = tmp_path / "sender_ctx_only"
    _init_catalog_stores(
        sender_dir,
        repo_id=repo_id,
        instance_id=inst_id,
        include_core=False,
        include_context=True,
        include_operational=True,
    )
    auth_s, adm_s, _ = create_local_admission_service(
        "provider_intake",
        grants=grants,
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with Context.transaction(sender_dir, authorization=auth_s, admission=adm_s) as ctx:
        ctx.provider(inst_id, "synthetic", "{}")
        ctx.repository(repo_id, "{}")
        ctx.resource(res_key, identification=ResourceIdentification.unscoped(res_key))

    ctx_pkg = ExchangeService(sender_dir).export_package(
        selection=ExchangeSelectionScope(all_selected=True, include_core=False)
    )
    assert ctx_pkg.core is None

    # Import into context-only receiver
    report = ExchangeService(ctx_only_dir).import_package(
        ctx_pkg,
        permitted_repository_uuidv4s=(repo_id,),
        authorization=auth_ctx,
        admission=adm_ctx,
        new_request=True,
    )
    assert report.context_imported is True
    assert report.core_imported is False
    assert report.admitted_context_resources == 1
    assert not (ctx_only_dir / "core.sqlite3").exists()

    with closing(sqlite3.connect(ctx_only_dir / "context.sqlite3")) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM resources WHERE provider_resource_id=?",
                (encode_identity(["ctx_only_1"]),),
            ).fetchone()[0]
            == 1
        )

    # 4B: Paired Core+Context path via PairedAcquisitionCoordinator
    paired_dir = tmp_path / "paired_catalog"
    paired_repo, paired_inst = _init_catalog_stores(paired_dir)

    paired_res = ResourceKey(paired_inst, "issue", encode_identity(["paired_1"]))
    paired_grants = DependencySet(
        repositories={paired_repo},
        resources={paired_res},
        provider_registrations={paired_inst},
    )
    auth_pair, adm_pair, _ = create_local_admission_service(
        "provider_intake",
        grants=paired_grants,
        permitted_repositories=frozenset({paired_repo}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )

    coord = PairedAcquisitionCoordinator(
        paired_dir, authorization=auth_pair, admission=adm_pair
    )

    def core_step(core: GitCore) -> None:
        core.admit_repository(paired_repo)

    def context_step(ctx: Context) -> None:
        ctx.provider(paired_inst, "synthetic", "{}")
        ctx.repository(paired_repo, "{}")
        ctx.resource(
            paired_res, identification=ResourceIdentification.unscoped(paired_res)
        )

    res = coord.admit_paired(core_fn=core_step, context_fn=context_step)
    assert res.admission.core_committed is True
    assert res.admission.context_committed is True

    with closing(sqlite3.connect(paired_dir / "core.sqlite3")) as db:
        core_repos = [
            r[0]
            for r in db.execute("SELECT repository_uuidv4 FROM repositories").fetchall()
        ]
        assert paired_repo in core_repos

    with closing(sqlite3.connect(paired_dir / "context.sqlite3")) as db:
        ctx_repos = [
            r[0]
            for r in db.execute(
                "SELECT repository_uuidv4 FROM repository_context"
            ).fetchall()
        ]
        assert paired_repo in ctx_repos
        res_count = db.execute("SELECT count(*) FROM resources").fetchone()[0]
        assert res_count == 1


# =============================================================================
# OBLIGATION 5: Foreign Authorization Handle Passed into Product Routes
# =============================================================================


def test_obligation_5_foreign_authorization_handle_rejected(tmp_path: Path) -> None:
    """Obligation 5: Pass a genuine handle issued by another authorization service into product routes.

    Asserts:
    - Service 1 issues genuine handle `adm1`.
    - Service 2 issues genuine handle `adm2`.
    - Passing `adm1` to routes configured with Service 2 fails closed with PERMISSION_DENIED:
      * auth2.validate_context(adm1)
      * Context.transaction(..., authorization=auth2, admission=adm1)
      * ExchangeService.import_package(..., authorization=auth2, admission=adm1)
      * PairedAcquisitionCoordinator(..., authorization=auth2, admission=adm1).admit_paired()
      * ProviderAcquisition(..., authorization=auth2, admission=adm1)
    - 0 rows written to SQLite.
    """
    catalog_dir = tmp_path / "foreign_handle_catalog"
    repo_id, inst_id = _init_catalog_stores(catalog_dir)
    res_key = ResourceKey(inst_id, "issue", encode_identity(["fh_1"]))

    grants = DependencySet(
        repositories={repo_id},
        resources={res_key},
        provider_registrations={inst_id},
    )

    auth1, adm1, _ = create_local_admission_service(
        "provider_intake",
        grants=grants,
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
        principal="user-service-1",
        credential="cred-service-1",
    )

    auth2, adm2, _ = create_local_admission_service(
        "provider_intake",
        grants=grants,
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
        principal="user-service-2",
        credential="cred-service-2",
    )

    # 1. Direct validate_context cross-service refusal
    with pytest.raises(AdmissionRefused) as exc:
        auth2.validate_context(adm1)
    assert exc.value.code == "PERMISSION_DENIED"

    # 2. Context.transaction with foreign handle
    with pytest.raises(AdmissionRefused) as exc:
        with Context.transaction(
            catalog_dir, authorization=auth2, admission=adm1
        ) as ctx:
            ctx.repository(repo_id, "{}")
    assert exc.value.code == "PERMISSION_DENIED"

    # 3. ProviderAcquisition with foreign handle
    acq = ProviderAcquisition(catalog_dir, authorization=auth2, admission=adm1)
    batch = ProviderIntakeBatch(
        service_instance_uuidv4=inst_id,
        providers=(ProviderRegistration(inst_id, "synthetic", "{}"),),
        repositories=(RepositoryRegistration(repo_id, "{}"),),
    )
    with pytest.raises(AdmissionRefused) as exc:
        acq.admit_batch(batch)
    assert exc.value.code == "PERMISSION_DENIED"

    # 4. PairedAcquisitionCoordinator initialized with foreign admission handle
    coord = PairedAcquisitionCoordinator(
        catalog_dir, authorization=auth2, admission=adm1
    )
    with pytest.raises(AdmissionRefused) as exc:
        coord.admit_paired(
            core_fn=lambda c: None,
            context_fn=lambda x: None,
        )
    assert exc.value.code == "PERMISSION_DENIED"

    # 5. ExchangeService with foreign admission handle
    sender_dir = tmp_path / "sender_pkg"
    _init_catalog_stores(sender_dir, repo_id=repo_id, instance_id=inst_id)
    with Context.transaction(sender_dir, authorization=auth1, admission=adm1) as ctx:
        ctx.provider(inst_id, "synthetic", "{}")
        ctx.repository(repo_id, "{}")
    pkg = ExchangeService(sender_dir).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )

    receiver_service = ExchangeService(catalog_dir)
    with pytest.raises(AdmissionRefused) as exc:
        receiver_service.import_package(
            pkg,
            permitted_repository_uuidv4s=(repo_id,),
            authorization=auth2,
            admission=adm1,
            new_request=True,
        )
    assert exc.value.code == "PERMISSION_DENIED"

    # Verify 0 rows written in target catalog
    with closing(sqlite3.connect(catalog_dir / "context.sqlite3")) as db:
        assert db.execute("SELECT count(*) FROM repository_context").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM providers").fetchone()[0] == 0


# =============================================================================
# OBLIGATION 6: Permission Revocation at Actual Transaction/COMMIT Boundaries
# =============================================================================


def test_obligation_6_permission_revocation_at_commit_boundaries(
    tmp_path: Path,
) -> None:
    """Obligation 6: Trigger permission revocation at actual transaction/COMMIT boundaries.

    Asserts:
    - Direct Context.transaction precommit lease check aborts and rolls back when policy is revoked.
    - ExchangeService.import_package cut hook during_context triggers revocation before commit,
      resulting in AdmissionFailure, clean rollback, and 0 persisted rows.
    """
    # 6A: Direct Context.transaction revocation before commit
    cat_dir = tmp_path / "commit_boundary_catalog"
    repo_id, inst_id = _init_catalog_stores(cat_dir)
    res_key = ResourceKey(inst_id, "issue", encode_identity(["commit_rev_1"]))

    auth, adm, policy = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(
            repositories={repo_id},
            resources={res_key},
            provider_registrations={inst_id},
        ),
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )

    with pytest.raises(AdmissionRefused) as exc:
        with Context.transaction(cat_dir, authorization=auth, admission=adm) as ctx:
            ctx.provider(inst_id, "synthetic", "{}")
            ctx.repository(repo_id, "{}")
            ctx.resource(
                res_key, identification=ResourceIdentification.unscoped(res_key)
            )
            # Revoke permission before commit boundary is reached
            policy.grants = DependencySet()

    assert exc.value.code == "PERMISSION_DENIED"
    with closing(sqlite3.connect(cat_dir / "context.sqlite3")) as db:
        assert db.execute("SELECT count(*) FROM repository_context").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM resources").fetchone()[0] == 0

    # 6B: ExchangeService.import_package cut hook revocation before COMMIT
    sender_dir = tmp_path / "sender_rev"
    _init_catalog_stores(sender_dir, repo_id=repo_id, instance_id=inst_id)
    auth_s, adm_s, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(
            repositories={repo_id},
            resources={res_key},
            provider_registrations={inst_id},
        ),
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with Context.transaction(sender_dir, authorization=auth_s, admission=adm_s) as ctx:
        ctx.provider(inst_s := inst_id, "synthetic", "{}")
        ctx.repository(repo_id, "{}")
        ctx.resource(res_key, identification=ResourceIdentification.unscoped(res_key))

    pkg = ExchangeService(sender_dir).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )

    receiver_dir = tmp_path / "recv_rev"
    _init_catalog_stores(receiver_dir)
    auth_r, adm_r, policy_r = create_local_admission_service(
        "exchange_import",
        grants=DependencySet(
            repositories={repo_id},
            resources={res_key},
            provider_registrations={inst_s},
        ),
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )

    def revoke_at_cut(point: str) -> None:
        if point == "during_context":
            policy_r.grants = DependencySet()

    with pytest.raises(AdmissionFailure) as exc_info:
        ExchangeService(receiver_dir).import_package(
            pkg,
            permitted_repository_uuidv4s=(repo_id,),
            authorization=auth_r,
            admission=adm_r,
            cut=revoke_at_cut,
            new_request=True,
        )
    assert exc_info.value.cause.code == "PERMISSION_DENIED"

    # Context rolled back cleanly
    with closing(sqlite3.connect(receiver_dir / "context.sqlite3")) as db:
        assert db.execute("SELECT count(*) FROM repository_context").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM resources").fetchone()[0] == 0


# =============================================================================
# OBLIGATION 7: Exact Replay and Cached Receipt Invariants After Revocation
# =============================================================================


def test_obligation_7_exact_replay_and_cached_receipt_revocation(
    tmp_path: Path,
) -> None:
    """Obligation 7: Verify exact replay and cached receipt behavior after revocation.

    Asserts:
    - First import succeeds: idempotent_replay is False.
    - Second import (replay) succeeds: idempotent_replay is True.
    - After permission revocation, replay attempt FAILS CLOSED with PERMISSION_DENIED.
    - Cached receipts or prior success do NOT grant bypass of current authority.
    """
    sender_dir = tmp_path / "replay_sender"
    repo_id, inst_id = _init_catalog_stores(sender_dir)
    res_key = ResourceKey(inst_id, "issue", encode_identity(["replay_1"]))

    auth_s, adm_s, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(
            repositories={repo_id},
            resources={res_key},
            provider_registrations={inst_id},
        ),
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with Context.transaction(sender_dir, authorization=auth_s, admission=adm_s) as ctx:
        ctx.provider(inst_id, "synthetic", "{}")
        ctx.repository(repo_id, "{}")
        ctx.resource(res_key, identification=ResourceIdentification.unscoped(res_key))

    pkg = ExchangeService(sender_dir).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )

    receiver_dir = tmp_path / "replay_receiver"
    _init_catalog_stores(receiver_dir)
    auth_r, adm_r, policy_r = create_local_admission_service(
        "exchange_import",
        grants=DependencySet(
            repositories={repo_id},
            resources={res_key},
            provider_registrations={inst_id},
        ),
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )

    receiver_service = ExchangeService(receiver_dir)

    # 1. First import
    rep1 = receiver_service.import_package(
        pkg,
        permitted_repository_uuidv4s=(repo_id,),
        authorization=auth_r,
        admission=adm_r,
        new_request=True,
    )
    assert rep1.idempotent_replay is False

    # 2. Second import (replay)
    rep2 = receiver_service.import_package(
        pkg,
        permitted_repository_uuidv4s=(repo_id,),
        authorization=auth_r,
        admission=adm_r,
        new_request=True,
    )
    assert rep2.idempotent_replay is True

    # 3. Revoke permission
    policy_r.grants = DependencySet()

    # 4. Third import attempt fails closed
    with pytest.raises(AdmissionRefused) as exc:
        receiver_service.import_package(
            pkg,
            permitted_repository_uuidv4s=(repo_id,),
            authorization=auth_r,
            admission=adm_r,
            new_request=True,
        )
    assert exc.value.code == "PERMISSION_DENIED"


# =============================================================================
# OBLIGATION 8: Independent Source, MappingClaim, and Disposition Permissions
# =============================================================================


def test_obligation_8_independent_source_mapping_claim_and_disposition_permissions(
    tmp_path: Path,
) -> None:
    """Obligation 8: Verify Source, MappingClaim, and Disposition permissions independently.

    Asserts:
    - Withholding only Source: policy refusal and package import rejection with PERMISSION_DENIED.
    - Withholding only MappingClaim: policy refusal and package import rejection with PERMISSION_DENIED.
    - Withholding only Disposition: policy refusal and package import rejection with PERMISSION_DENIED.
    - Direct Context mutation with missing permission fails closed.
    """
    sender_dir = tmp_path / "perm_sender"
    repo_id, inst_id = _init_catalog_stores(sender_dir)
    source_id = str(uuid4())

    r_repo = ResourceKey(inst_id, "repository", encode_identity(["repo_perm"]))
    claim_rep = ResourceRepositoryRelation(
        r_repo,
        "represents_repository",
        FieldClock("clock:perm", 1),
        canonical(repo_id),
        canonical({"source": "test", "evidence": "perm_claim"}),
        100,
    )
    disp_rep = MappingDisposition(
        claim_rep.claim_key,
        "withdraw",
        FieldClock("clock:disp_perm", 2),
        canonical({"source": "test", "evidence": "perm_disp"}),
        200,
    )

    full_grants = DependencySet(
        repositories={repo_id},
        sources={source_id},
        source_repository_pairs={(source_id, repo_id)},
        resources={r_repo},
        mapping_claims={claim_rep.claim_key},
        dispositions={disp_rep.disposition_key},
        provider_registrations={inst_id},
    )
    auth_s, adm_s, _ = create_local_admission_service(
        "provider_intake",
        grants=full_grants,
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with Context.transaction(sender_dir, authorization=auth_s, admission=adm_s) as ctx:
        ctx.provider(inst_id, "synthetic", "{}")
        ctx.repository(repo_id, "{}")
        ctx.source(source_id, inst_id, "{}")
        ctx.associate_source(
            source_id,
            repo_id,
            canonical({"source": "test", "evidence": "perm_assoc"}),
        )
        ctx.resource(r_repo, identification=ResourceIdentification.unscoped(r_repo))
        ctx.admit_repository_relation(claim_rep)
        ctx.admit_mapping_disposition(disp_rep)

    pkg = ExchangeService(sender_dir).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )

    recv_dir = tmp_path / "perm_recv"
    _init_catalog_stores(recv_dir, repo_id=repo_id)
    recv_svc = ExchangeService(recv_dir)

    # -------------------------------------------------------------------------
    # 8A: Withhold Source only
    # -------------------------------------------------------------------------
    grants_no_source = DependencySet(
        repositories={repo_id},
        resources={r_repo},
        mapping_claims={claim_rep.claim_key},
        dispositions={disp_rep.disposition_key},
        provider_registrations={inst_id},
    )
    _, _, policy_no_source = create_local_admission_service(
        "provider_intake",
        grants=grants_no_source,
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with pytest.raises(AdmissionRefused) as exc:
        with policy_no_source.lease(
            "local-authority",
            "provider_intake",
            DependencySet(sources={source_id}),
        ):
            pass
    assert exc.value.code == "PERMISSION_DENIED"

    with pytest.raises(AdmissionRefused) as exc:
        recv_svc.import_package(
            pkg,
            permitted_repository_uuidv4s=(repo_id,),
            grants=grants_no_source,
            new_request=True,
        )
    assert exc.value.code == "PERMISSION_DENIED"

    # Direct Context mutation withholding source
    cat_no_source = tmp_path / "ctx_no_source"
    _init_catalog_stores(cat_no_source, repo_id=repo_id)
    auth_ns, adm_ns, _ = create_local_admission_service(
        "provider_intake",
        grants=grants_no_source,
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with pytest.raises(AdmissionRefused) as exc:
        with Context.transaction(
            cat_no_source, authorization=auth_ns, admission=adm_ns
        ) as ctx:
            ctx.source(source_id, inst_id, "{}")
    assert exc.value.code == "PERMISSION_DENIED"

    # -------------------------------------------------------------------------
    # 8B: Withhold MappingClaim only
    # -------------------------------------------------------------------------
    grants_no_mapping = DependencySet(
        repositories={repo_id},
        sources={source_id},
        source_repository_pairs={(source_id, repo_id)},
        resources={r_repo},
        dispositions={disp_rep.disposition_key},
        provider_registrations={inst_id},
    )
    _, _, policy_no_mapping = create_local_admission_service(
        "provider_intake",
        grants=grants_no_mapping,
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with pytest.raises(AdmissionRefused) as exc:
        with policy_no_mapping.lease(
            "local-authority",
            "provider_intake",
            DependencySet(mapping_claims={claim_rep.claim_key}),
        ):
            pass
    assert exc.value.code == "PERMISSION_DENIED"

    with pytest.raises(AdmissionRefused) as exc:
        recv_svc.import_package(
            pkg,
            permitted_repository_uuidv4s=(repo_id,),
            grants=grants_no_mapping,
            new_request=True,
        )
    assert exc.value.code == "PERMISSION_DENIED"

    # -------------------------------------------------------------------------
    # 8C: Withhold Disposition only
    # -------------------------------------------------------------------------
    grants_no_disp = DependencySet(
        repositories={repo_id},
        sources={source_id},
        source_repository_pairs={(source_id, repo_id)},
        resources={r_repo},
        mapping_claims={claim_rep.claim_key},
        provider_registrations={inst_id},
    )
    _, _, policy_no_disp = create_local_admission_service(
        "provider_intake",
        grants=grants_no_disp,
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with pytest.raises(AdmissionRefused) as exc:
        with policy_no_disp.lease(
            "local-authority",
            "provider_intake",
            DependencySet(dispositions={disp_rep.disposition_key}),
        ):
            pass
    assert exc.value.code == "PERMISSION_DENIED"

    with pytest.raises(AdmissionRefused) as exc:
        recv_svc.import_package(
            pkg,
            permitted_repository_uuidv4s=(repo_id,),
            grants=grants_no_disp,
            new_request=True,
        )
    assert exc.value.code == "PERMISSION_DENIED"

    # Direct Context mutation withholding disposition
    cat_no_disp = tmp_path / "ctx_no_disp"
    _init_catalog_stores(cat_no_disp, repo_id=repo_id)
    auth_nd, adm_nd, _ = create_local_admission_service(
        "provider_intake",
        grants=grants_no_disp,
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with pytest.raises(AdmissionRefused) as exc:
        with Context.transaction(
            cat_no_disp, authorization=auth_nd, admission=adm_nd
        ) as ctx:
            ctx.provider(inst_id, "synthetic", "{}")
            ctx.repository(repo_id, "{}")
            ctx.resource(r_repo, identification=ResourceIdentification.unscoped(r_repo))
            ctx.admit_repository_relation(claim_rep)
            ctx.admit_mapping_disposition(disp_rep)
    assert exc.value.code == "PERMISSION_DENIED"


# =============================================================================
# OBLIGATION 9: Paired Core-First Failure and Operational Recovery Bookkeeping
# =============================================================================


def test_obligation_9_paired_core_first_failure_and_operational_recovery_state(
    tmp_path: Path,
) -> None:
    """Obligation 9: Execute authorized paired Provider acquisition and supported Core-first failure/recovery.

    Asserts:
    - Core commit commits first and is durable.
    - Context fails second and is rolled back.
    - Operational database tracks exact recovery state (adr0030-partial with core_committed=true, context_committed=false).
    - Cross-store atomic rollback is NOT assumed.
    """
    sender_dir = tmp_path / "p9_sender"
    receiver_dir = tmp_path / "p9_receiver"
    repo_id, inst_s = _init_catalog_stores(sender_dir)
    _init_catalog_stores(receiver_dir)

    with closing(GitCore(sender_dir / "core.sqlite3")) as core:
        core.admit_repository(repo_id)

    res_key = ResourceKey(inst_s, "issue", encode_identity(["p9_issue"]))
    auth_s, adm_s, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(
            repositories={repo_id},
            resources={res_key},
            provider_registrations={inst_s},
        ),
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    with Context.transaction(sender_dir, authorization=auth_s, admission=adm_s) as ctx:
        ctx.provider(inst_s, "synthetic", "{}")
        ctx.repository(repo_id, "{}")
        ctx.resource(res_key, identification=ResourceIdentification.unscoped(res_key))

    pkg = ExchangeService(sender_dir).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )

    auth_r, adm_r, _ = create_local_admission_service(
        "exchange_import",
        grants=DependencySet(
            repositories={repo_id},
            resources={res_key},
            provider_registrations={inst_s},
        ),
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )

    def cut_fail_context(point: str) -> None:
        if point == "during_context":
            raise RuntimeError("Injected Context failure after Core commit")

    req = RequestIdentity(str(uuid4()), str(uuid4()))
    with pytest.raises(AdmissionFailure) as exc_info:
        ExchangeService(receiver_dir).import_package(
            pkg,
            permitted_repository_uuidv4s=(repo_id,),
            authorization=auth_r,
            admission=adm_r,
            cut=cut_fail_context,
            request=req,
            new_request=True,
        )

    # 1. Outcome reflects Core committed, Context aborted
    assert exc_info.value.outcome.core_committed is True
    assert exc_info.value.outcome.context_committed is False

    # 2. Durable Core state: repository is present
    with closing(sqlite3.connect(receiver_dir / "core.sqlite3")) as db:
        core_repos = [
            r[0]
            for r in db.execute("SELECT repository_uuidv4 FROM repositories").fetchall()
        ]
        assert repo_id in core_repos

    # 3. Rolled-back Context state: repository and resources are NOT present
    with closing(sqlite3.connect(receiver_dir / "context.sqlite3")) as db:
        ctx_repos = [
            r[0]
            for r in db.execute(
                "SELECT repository_uuidv4 FROM repository_context"
            ).fetchall()
        ]
        assert repo_id not in ctx_repos
        assert db.execute("SELECT count(*) FROM resources").fetchone()[0] == 0

    # 4. Operational recovery state: request_continuations records adr0030-partial
    with closing(sqlite3.connect(receiver_dir / "operational.sqlite3")) as db:
        rows = db.execute(
            "SELECT continuation_scope_json, cursor_json FROM request_continuations"
        ).fetchall()
        partial_records = [
            json.loads(cursor) for scope, cursor in rows if "adr0030-partial" in scope
        ]
        assert len(partial_records) == 1
        assert partial_records[0] == {
            "core_committed": True,
            "context_committed": False,
        }

    # 5. Also exercise PairedAcquisitionCoordinator directly
    paired_cat = tmp_path / "p9_paired"
    paired_repo, paired_inst = _init_catalog_stores(paired_cat)
    auth_p, adm_p, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(repositories={paired_repo}),
        permitted_repositories=frozenset({paired_repo}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    coord = PairedAcquisitionCoordinator(
        paired_cat, authorization=auth_p, admission=adm_p
    )

    def core_step(core: GitCore) -> None:
        core.admit_repository(paired_repo)

    def failing_ctx_step(ctx: Context) -> None:
        ctx.repository(paired_repo, "{}")
        raise RuntimeError("Injected Context crash in paired coordinator")

    with pytest.raises(AdmissionFailure) as exc_coord:
        coord.admit_paired(core_fn=core_step, context_fn=failing_ctx_step)

    assert exc_coord.value.outcome.core_committed is True
    assert exc_coord.value.outcome.context_committed is False

    with closing(sqlite3.connect(paired_cat / "core.sqlite3")) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM repositories WHERE repository_uuidv4=?",
                (paired_repo,),
            ).fetchone()[0]
            == 1
        )
    with closing(sqlite3.connect(paired_cat / "context.sqlite3")) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM repository_context WHERE repository_uuidv4=?",
                (paired_repo,),
            ).fetchone()[0]
            == 0
        )


# =============================================================================
# OBLIGATION 10: Retention of Both Transfer SQL Fences and Ordinary Refusal
# =============================================================================


def test_obligation_10_transfer_sql_fences_and_unsupported_resource_stage(
    tmp_path: Path,
) -> None:
    """Obligation 10: Retain both Transfer SQL fences and prove ordinary Transfer remains refused with UnsupportedResourceStage.

    Asserts:
    - sqlite_schema has both i2_transfer_stage_fence and i2_transfer_report_stage_fence triggers active.
    - ProviderAcquisition refuses timeline TransferredEvent intake with UnsupportedResourceStage.
    - Direct SQL INSERT of transfer relations into resource_repository_relations is aborted by SQL trigger.
    - Direct SQL INSERT of transfer relations into resource_relations is aborted by SQL trigger.
    """
    fence_dir = tmp_path / "fence_catalog"
    repo_id, inst_id = _init_catalog_stores(fence_dir)
    service = inst_id

    # 1. Verify SQL triggers are present in sqlite_schema
    with closing(p1_schema.connect(fence_dir / "context.sqlite3", "context")) as db:
        triggers = {
            r[0]: (r[1], r[2])
            for r in db.execute(
                "SELECT name, tbl_name, sql FROM sqlite_schema WHERE type='trigger'"
            ).fetchall()
        }
        assert "i2_transfer_stage_fence" in triggers
        assert triggers["i2_transfer_stage_fence"][0] == "resource_repository_relations"
        assert "I2_TRANSFER_UNSUPPORTED" in triggers["i2_transfer_stage_fence"][1]

        assert "i2_transfer_report_stage_fence" in triggers
        assert triggers["i2_transfer_report_stage_fence"][0] == "resource_relations"
        assert (
            "I2_TRANSFER_UNSUPPORTED" in triggers["i2_transfer_report_stage_fence"][1]
        )

    # 2. ProviderAcquisition refuses transfer intake with UnsupportedResourceStage
    node = {"id": "R_fence_node", "databaseId": 505}
    node_id = github_repository_id(node, graphql=True)
    claim = ResourceRepositoryRelation(
        ResourceKey(service, "repository", node_id),
        "represents_repository",
        FieldClock("fence:clock", 1),
        canonical(repo_id),
        make_provenance("fence", {"mapping": node_id}),
        1,
    )
    auth, adm, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(
            provider_registrations=frozenset({service}),
            repositories=frozenset({repo_id}),
            mapping_claims=frozenset({claim.claim_key}),
            resources=frozenset({claim.resource}),
        ),
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )

    transfer_batch = ProviderIntakeBatch(
        service,
        providers=(ProviderRegistration(service, "github"),),
        repositories=(RepositoryRegistration(repo_id),),
        mapping_claims=(claim,),
        timeline_events=(
            ProviderTimelineIntake(
                "issue",
                505,
                "EV_fence_test",
                {
                    "id": "EV_fence_test",
                    "__typename": "TransferredEvent",
                    "issue": {"databaseId": 505},
                    "fromRepository": node,
                },
                50,
                make_provenance("fence", "event"),
                graphql=True,
            ),
        ),
    )
    acq = ProviderAcquisition(fence_dir, authorization=auth, admission=adm)
    with pytest.raises(UnsupportedResourceStage) as exc:
        acq.admit_batch(transfer_batch)
    assert "Provider Transfer intake" in str(exc.value)

    # 3. Direct SQL trigger abort on resource_repository_relations
    with closing(p1_schema.connect(fence_dir / "context.sqlite3", "context")) as db:
        with pytest.raises(sqlite3.DatabaseError) as exc_sql1:
            db.execute(
                """INSERT INTO resource_repository_relations (
                    service_instance_uuidv4, resource_kind, provider_resource_id,
                    relation_kind, clock_json, target_json, provenance_json, observed_at_us
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    service,
                    "comment",
                    encode_identity(["t1"]),
                    "transfer_from_repository",
                    canonical({"domain": "clock", "at_us": 1}),
                    canonical(repo_id),
                    canonical({"source": "fence", "evidence": "direct_sql"}),
                    100,
                ),
            )
        assert "I2_TRANSFER_UNSUPPORTED" in str(exc_sql1.value)

        # 4. Direct SQL trigger abort on resource_relations
        with pytest.raises(sqlite3.DatabaseError) as exc_sql2:
            db.execute(
                """INSERT INTO resource_relations (
                    service_instance_uuidv4, resource_kind, provider_resource_id,
                    relation_kind, members_json, provenance_json, scope_json, observed_at_us
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    service,
                    "issue",
                    encode_identity(["t2"]),
                    "transfer_event_report",
                    canonical([]),
                    canonical({"source": "fence", "evidence": "direct_sql"}),
                    canonical({}),
                    100,
                ),
            )
        assert "I2_TRANSFER_UNSUPPORTED" in str(exc_sql2.value)

        # Confirm 0 rows in both tables
        assert (
            db.execute("SELECT count(*) FROM resource_repository_relations").fetchone()[
                0
            ]
            == 0
        )
        assert db.execute("SELECT count(*) FROM resource_relations").fetchone()[0] == 0
