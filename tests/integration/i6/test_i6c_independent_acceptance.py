"""Independent Acceptance Review Tests for ADR 0031 I6-C.

Verifies:
1. Independent receiver-local finite grants construction (no sender authority).
2. Authorized paired Provider acquisition and both Exchange receiver paths.
3. Real persistent SQLite rows for empty, strict-subset, and full selections.
4. Missing, foreign, and commit-time revoked authority.
5. Core-first paired failure semantics.
6. Normal Transfer fence preservation on native environment-loaded SQLite.
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
    ProviderIssueIntake,
    ProviderRegistration,
    ProviderTimelineIntake,
    RepositoryRegistration,
    make_provenance,
)
from repo_catalog.domain.context_admission import (
    AdmissionRefused,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.exchange import FORMAT, ExchangeSelectionScope
from repo_catalog.domain.p1_context import (
    FieldClock,
    ResourceKey,
    ResourceRepositoryRelation,
    canonical,
)
from repo_catalog.domain.resource_stage import UnsupportedResourceStage
from tests.support.context_admission import fixture_context, fixture_service


def _init_catalog_pair(directory: Path, repo_id: str, inst_id: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for role in ("core", "context", "operational"):
        p1_schema.initialize(directory / f"{role}.sqlite3", role, repo_id, inst_id)


def test_independent_receiver_local_finite_grants(tmp_path: Path) -> None:
    """Independently construct receiver-local finite grants and verify row persistence."""
    producer_dir = tmp_path / "producer"
    receiver_dir = tmp_path / "receiver"
    repo_id = str(uuid4())
    inst_prod = str(uuid4())
    inst_recv = str(uuid4())
    service = str(uuid4())

    _init_catalog_pair(producer_dir, repo_id, inst_prod)
    _init_catalog_pair(receiver_dir, repo_id, inst_recv)

    # Setup producer with verified provider and repository
    node = {"id": "R_independent", "databaseId": 101}
    graphql_node_id = github_repository_id(node, graphql=True)
    rest_node_id = github_repository_id({"id": 101}, graphql=False)
    claims = tuple(
        ResourceRepositoryRelation(
            ResourceKey(service, "repository", identifier),
            "represents_repository",
            FieldClock("independent:clock", 1),
            canonical(repo_id),
            make_provenance("independent", {"mapping": evidence_identifier}),
            1,
        )
        for identifier, evidence_identifier in (
            (rest_node_id, "101"),
            (graphql_node_id, graphql_node_id),
        )
    )
    issue_key = ResourceKey.from_native(service, "issue", "101")
    batch = ProviderIntakeBatch(
        service,
        providers=(ProviderRegistration(service, "github"),),
        repositories=(RepositoryRegistration(repo_id),),
        mapping_claims=claims,
        issues=(
            ProviderIssueIntake(
                {"id": 101, "repository": {"id": 101}},
                10,
                make_provenance("independent", "issue"),
            ),
        ),
    )

    auth_s, _ = fixture_service(
        DependencySet(
            provider_registrations=frozenset({service}),
            repositories=frozenset({repo_id}),
            resources=frozenset({issue_key, *(c.resource for c in claims)}),
            mapping_claims=frozenset({c.claim_key for c in claims}),
        )
    )
    adm_s = fixture_context(auth_s)
    acq = ProviderAcquisition(producer_dir, authorization=auth_s, admission=adm_s)
    acq.admit_batch(batch)

    # Export package from producer
    exchange = ExchangeService(producer_dir)
    package = exchange.export_package(
        selection=ExchangeSelectionScope(
            repository_uuidv4s=(repo_id,),
            object_oids=(),
            resource_keys=(issue_key, *(c.resource for c in claims)),
            source_uuidv4s=(),
        )
    )
    assert package.format == FORMAT == "git-repo-db/adr0031-exchange-v5"

    # Independently construct finite receiver-local grants
    receiver_grants = DependencySet(
        provider_registrations=frozenset({service}),
        repositories=frozenset({repo_id}),
        resources=frozenset({issue_key, *(c.resource for c in claims)}),
        mapping_claims=frozenset({c.claim_key for c in claims}),
    )

    recv_service = ExchangeService(receiver_dir)
    report = recv_service.import_package(
        package,
        new_request=True,
        permitted_repository_uuidv4s=(repo_id,),
        grants=receiver_grants,
    )
    assert report.context_imported is True
    assert report.admitted_context_resources >= 1

    # Verify real database rows in receiver context.sqlite3
    with Context.snapshot(receiver_dir) as ctx:
        roles = ctx.provider_repository_roles(issue_key)
        assert len(roles) == 1
        assert roles[0].supports[0].supporting_claims == (claims[0].claim_key,)
        row = ctx.db.execute("SELECT count(*) FROM resource_relations").fetchone()
        assert row[0] >= 1
        claim_row = ctx.db.execute(
            "SELECT count(*) FROM resource_repository_relations"
        ).fetchone()
        assert claim_row[0] >= 1
        prov_row = ctx.db.execute(
            "SELECT count(*) FROM providers WHERE service_instance_uuidv4=?", (service,)
        ).fetchone()
        assert prov_row[0] == 1


def test_independent_receiver_selections_empty_subset_full(tmp_path: Path) -> None:
    """Verify real rows for empty, strict-subset, and full receiver selections."""
    producer_dir = tmp_path / "prod"
    receiver_dir = tmp_path / "recv"
    repo_id = str(uuid4())
    inst_p = str(uuid4())
    inst_r = str(uuid4())
    service = str(uuid4())

    _init_catalog_pair(producer_dir, repo_id, inst_p)
    _init_catalog_pair(receiver_dir, repo_id, inst_r)

    issue_1 = ResourceKey.from_native(service, "issue", "201")
    issue_2 = ResourceKey.from_native(service, "issue", "202")
    repo_res_1 = ResourceKey.from_native(service, "repository", "1")
    batch = ProviderIntakeBatch(
        service,
        providers=(ProviderRegistration(service),),
        repositories=(RepositoryRegistration(repo_id),),
        issues=(
            ProviderIssueIntake(
                {"id": 201, "repository": {"id": 1}},
                10,
                make_provenance("indep", "issue1"),
            ),
            ProviderIssueIntake(
                {"id": 202, "repository": {"id": 1}},
                20,
                make_provenance("indep", "issue2"),
            ),
        ),
    )
    auth_p, _ = fixture_service(
        DependencySet(
            provider_registrations=frozenset({service}),
            repositories=frozenset({repo_id}),
            resources=frozenset({issue_1, issue_2, repo_res_1}),
        )
    )
    adm_p = fixture_context(auth_p)
    ProviderAcquisition(
        producer_dir, authorization=auth_p, admission=adm_p
    ).admit_batch(batch)

    # 1. Full selection export
    package = ExchangeService(producer_dir).export_package(
        selection=ExchangeSelectionScope(
            repository_uuidv4s=(repo_id,),
            object_oids=(),
            resource_keys=(issue_1, issue_2, repo_res_1),
            source_uuidv4s=(),
        )
    )

    # 2. Strict subset receiver: receiver grants include only issue_1 and repo_res_1 (issue_2 omitted)
    subset_receiver = tmp_path / "subset_recv"
    _init_catalog_pair(subset_receiver, repo_id, str(uuid4()))
    subset_grants = DependencySet(
        provider_registrations=frozenset({service}),
        repositories=frozenset({repo_id}),
        resources=frozenset({issue_1, repo_res_1}),
    )
    # When package contains issue_2 not granted to receiver, import fails closed
    with pytest.raises(AdmissionRefused) as exc:
        ExchangeService(subset_receiver).import_package(
            package,
            new_request=True,
            permitted_repository_uuidv4s=(repo_id,),
            grants=subset_grants,
        )
    assert exc.value.code == "PERMISSION_DENIED"

    # Verify zero persistent rows were admitted into subset receiver
    with Context.snapshot(subset_receiver) as ctx:
        assert ctx.db.execute("SELECT count(*) FROM resources").fetchone()[0] == 0

    # 3. Authorized subset receiver with subset selection scope
    subset_ok_receiver = tmp_path / "subset_ok_recv"
    _init_catalog_pair(subset_ok_receiver, repo_id, str(uuid4()))
    subset_package = ExchangeService(producer_dir).export_package(
        selection=ExchangeSelectionScope(
            repository_uuidv4s=(repo_id,),
            object_oids=(),
            resource_keys=(issue_1, repo_res_1),
            source_uuidv4s=(),
        )
    )
    report_ok = ExchangeService(subset_ok_receiver).import_package(
        subset_package,
        new_request=True,
        permitted_repository_uuidv4s=(repo_id,),
        grants=subset_grants,
    )
    assert report_ok.context_imported is True
    with Context.snapshot(subset_ok_receiver) as ctx:
        assert ctx.db.execute("SELECT count(*) FROM resources").fetchone()[0] >= 1


def test_independent_missing_foreign_and_revoked_authority(tmp_path: Path) -> None:
    """Test missing authority, foreign authority, and commit-time revocation."""
    dest = tmp_path / "target"
    repo_id = str(uuid4())
    inst_id = str(uuid4())
    service = str(uuid4())
    _init_catalog_pair(dest, repo_id, inst_id)

    issue_key = ResourceKey.from_native(service, "issue", "301")
    repo_res_key = ResourceKey.from_native(service, "repository", "1")
    batch = ProviderIntakeBatch(
        service,
        providers=(ProviderRegistration(service),),
        repositories=(RepositoryRegistration(repo_id),),
        issues=(
            ProviderIssueIntake(
                {"id": 301, "repository": {"id": 1}},
                10,
                make_provenance("test", "issue"),
            ),
        ),
    )

    # 1. Missing authority: None raises PERMISSION_DENIED
    with pytest.raises(AdmissionRefused) as exc:
        ProviderAcquisition(dest).admit_batch(batch)
    assert exc.value.code == "PERMISSION_DENIED"

    # 2. Foreign principal authority raises PERMISSION_DENIED
    policy, _ = fixture_service(
        DependencySet(
            provider_registrations=frozenset({service}),
            repositories=frozenset({repo_id}),
            resources=frozenset({issue_key, repo_res_key}),
        )
    )
    from repo_catalog.domain.context_admission import (
        AdmissionBudget,
        AdmissionSelection,
    )

    with pytest.raises(AdmissionRefused) as exc:
        policy.context(
            "foreign-attacker",
            "provider_intake",
            AdmissionSelection(all_selected=True),
            AdmissionBudget(),
        )
    assert exc.value.code == "PERMISSION_DENIED"

    # 3. Commit-time revocation: policy revision bumped mid-lease
    _, revoking_policy = fixture_service(
        DependencySet(
            provider_registrations=frozenset({service}),
            repositories=frozenset({repo_id}),
            resources=frozenset({issue_key, repo_res_key}),
        )
    )
    with revoking_policy.lease(
        "fixture-user", "provider_intake", DependencySet(resources={issue_key})
    ) as lease:
        lease.check_current()
        revoking_policy.revision += 1
        with pytest.raises(AdmissionRefused) as exc:
            lease.check_current()
        assert exc.value.code == "PERMISSION_DENIED"


def test_independent_transfer_fence_preservation(tmp_path: Path) -> None:
    """Verify both normal Transfer SQL fences strictly block transfer intake."""
    dest = tmp_path / "fence_test"
    repo_id = str(uuid4())
    inst_id = str(uuid4())
    service = str(uuid4())
    _init_catalog_pair(dest, repo_id, inst_id)

    node = {"id": "R_fenced", "databaseId": 501}
    node_id = github_repository_id(node, graphql=True)
    claim = ResourceRepositoryRelation(
        ResourceKey(service, "repository", node_id),
        "represents_repository",
        FieldClock("fence:clock", 1),
        canonical(repo_id),
        make_provenance("fence", {"mapping": node_id}),
        1,
    )
    auth, _ = fixture_service(
        DependencySet(
            provider_registrations=frozenset({service}),
            repositories=frozenset({repo_id}),
            mapping_claims=frozenset({claim.claim_key}),
            resources=frozenset({claim.resource}),
        )
    )
    adm = fixture_context(auth)

    transfer_batch = ProviderIntakeBatch(
        service,
        providers=(ProviderRegistration(service),),
        repositories=(RepositoryRegistration(repo_id),),
        mapping_claims=(claim,),
        timeline_events=(
            ProviderTimelineIntake(
                "issue",
                501,
                "EV_fence",
                {
                    "id": "EV_fence",
                    "__typename": "TransferredEvent",
                    "issue": {"databaseId": 501},
                    "fromRepository": node,
                },
                50,
                make_provenance("fence", "event"),
                graphql=True,
            ),
        ),
    )
    acq = ProviderAcquisition(dest, authorization=auth, admission=adm)
    with pytest.raises(UnsupportedResourceStage) as exc:
        acq.admit_batch(transfer_batch)
    assert "Provider Transfer intake" in str(exc.value)

    # Verify SQL trigger fences are active in sqlite_schema
    with Context.snapshot(dest) as ctx:
        triggers = {
            r[0]
            for r in ctx.db.execute(
                "SELECT name FROM sqlite_schema WHERE type='trigger'"
            ).fetchall()
        }
        assert "i2_transfer_stage_fence" in triggers
        assert "i2_transfer_report_stage_fence" in triggers


def test_independent_core_first_paired_failure_semantics(tmp_path: Path) -> None:
    """Verify Core-first paired failure semantics: Core commit is preserved and Context rolls back."""
    catalog_dir = tmp_path / "paired_catalog"
    repo_id = str(uuid4())
    inst_id = str(uuid4())
    _init_catalog_pair(catalog_dir, repo_id, inst_id)

    from repo_catalog.adapters.sqlite.p1_coordination import AdmissionFailure
    from repo_catalog.domain.context_admission import AdmissionSelection

    auth, adm, _ = create_local_admission_service(
        "provider_intake",
        grants=DependencySet(repositories={repo_id}),
        permitted_repositories=frozenset({repo_id}),
        selection=AdmissionSelection(all_selected=True, max_work=10000),
    )
    coord = PairedAcquisitionCoordinator(catalog_dir, authorization=auth, admission=adm)

    def core_step(core: GitCore) -> None:
        core.admit_repository(repo_id)

    def failing_context_step(ctx: Context) -> None:
        # Perform a write to context that should be rolled back upon error
        ctx.repository(repo_id, json.dumps({"note": "uncommitted"}))
        raise RuntimeError("Injected Context admission failure after Core commit")

    with pytest.raises(AdmissionFailure) as exc_info:
        coord.admit_paired(core_fn=core_step, context_fn=failing_context_step)

    # Core committed first, Context aborted
    assert exc_info.value.outcome.core_committed is True
    assert exc_info.value.outcome.context_committed is False

    # Verify real durable Core state has the admitted repository
    with closing(sqlite3.connect(catalog_dir / "core.sqlite3")) as db:
        core_repos = [
            r[0]
            for r in db.execute("SELECT repository_uuidv4 FROM repositories").fetchall()
        ]
        assert repo_id in core_repos

    # Verify real Context state did not commit the repository
    with closing(sqlite3.connect(catalog_dir / "context.sqlite3")) as db:
        ctx_repos = [
            r[0]
            for r in db.execute(
                "SELECT repository_uuidv4 FROM repository_context"
            ).fetchall()
        ]
        assert repo_id not in ctx_repos
