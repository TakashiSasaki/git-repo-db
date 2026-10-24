"""I3 counterexamples use only committed I1 admission, never Provider intake."""

from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.acquisition import make_provenance
from repo_catalog.domain.context_admission import DependencySet, dependencies
from repo_catalog.domain.exchange import (
    ExchangeError,
    ExchangeSelectionScope,
    decode_package,
    encode_package,
)
from repo_catalog.domain.p1_context import (
    FieldClock,
    ResourceKey,
    ResourceRepositoryRelation,
    canonical,
)
from repo_catalog.domain.p1_coordination import AdmissionFailure, RequestIdentity
from repo_catalog.domain.p1_core import OID
from repo_catalog.domain.resource_identification import ResourceIdentification as RI
from tests.integration.p5.conftest import init_catalog_stores
from tests.support.context_admission import fixture_transaction


def local_grants(
    issue, r1, r2, *, resources=(), sources=(), providers=(), units=(), oids=()
):
    """Declare finite authority for the named synthetic source setup only."""
    return dependencies((issue, *resources, *units, *oids)) | DependencySet(
        repositories={r1, r2},
        sources=sources,
        source_repository_pairs={
            (source, repo) for source in sources for repo in (r1, r2)
        },
        provider_registrations={issue.service_instance_uuidv4, *providers},
    )


def catalog(path):
    seed = str(uuid4())
    init_catalog_stores(
        path, repository_uuidv4=seed, stores=("core", "context", "operational")
    )
    return seed


def fixture(path):
    r1 = catalog(path)
    r2 = str(uuid4())
    service = str(uuid4())
    issue = ResourceKey.from_native(service, "issue", "7")
    oid = OID("sha1", "1" * 40)
    core = GitCore(path / "core.sqlite3")
    core.admit_repository(r2)
    core.admit_object(oid)
    core.close()
    with fixture_transaction(path, local_grants(issue, r1, r2)) as ctx:
        ctx.provider(service, "github", "{}")
        ctx.repository(r1)
        ctx.repository(r2)
        ctx.resource(issue)
        ctx.admit_repository_relation(
            ResourceRepositoryRelation(
                issue,
                "owning_repository",
                FieldClock("provider", 11),
                canonical(r1),
                make_provenance("fixture", "owning"),
                12,
            )
        )
    return r1, r2, issue, oid


def scope(**kwargs):
    return ExchangeSelectionScope(all_selected=True, **kwargs)


def rows(path, store, table):
    db = connect(path / (store + ".sqlite3"), store)
    result = db.execute("SELECT * FROM " + table).fetchall()
    db.close()
    return result


def receive(path, package, permitted=(), **kwargs):
    grants = kwargs.pop("grants", None)
    if grants is None and permitted and "authorization" not in kwargs:
        from repo_catalog.domain.context_admission import DependencySet
        from repo_catalog.domain.p1_context import ResourceKey

        res_set = set()
        prov_set = set()
        if (
            hasattr(package, "context")
            and package.context
            and "resources" in package.context
        ):
            for r in package.context["resources"]:
                res_set.add(
                    ResourceKey(
                        r["service_instance_uuidv4"],
                        r["resource_kind"],
                        r["provider_resource_id"],
                    )
                )
                prov_set.add(r["service_instance_uuidv4"])
        grants = DependencySet(
            repositories=set(permitted),
            resources=res_set,
            provider_registrations=prov_set,
        )
    return ExchangeService(path).import_package(
        package,
        permitted_repository_uuidv4s=permitted,
        new_request=True,
        grants=grants,
        **kwargs,
    )


def test_cross_seed_permission_identity_replay(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    r1, r2, issue, oid = fixture(a)
    seed = catalog(b)
    old_identity = rows(b, "core", "store_identity")
    package = ExchangeService(a).export_package(selection=scope())
    assert decode_package(encode_package(package)) == package
    report = receive(b, package, (r1,))
    assert rows(b, "core", "store_identity") == old_identity
    assert {r[0] for r in rows(b, "core", "repositories")} == {seed, r1}
    assert len(rows(b, "context", "resource_repository_relations")) == 1
    assert report.omissions
    assert receive(b, package, (r1,)).idempotent_replay


def test_empty_and_omitted_independent_sets(tmp_path):
    r1, r2, issue, oid = fixture(tmp_path)
    with pytest.raises(ExchangeError, match="SELECTION_REQUIRED"):
        ExchangeService(tmp_path).export_package()
    package = ExchangeService(tmp_path).export_package(
        selection=ExchangeSelectionScope(
            repository_uuidv4s=(r1,),
            object_oids=(),
            resource_keys=(),
            source_uuidv4s=(),
        )
    )
    assert package.core["repositories"] == [{"repository_uuidv4": r1}]
    assert not package.core["git_objects"]
    assert not package.context["resources"]


def test_package_key_binding_before_commits_and_sender_namespace(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    r1, *_ = fixture(a)
    catalog(b)
    package = ExchangeService(a).export_package(selection=scope())
    receive(b, package, (r1,))
    changed = replace(package, exported_at_us=99, digest_sha256=None)
    before = rows(b, "core", "repositories"), rows(b, "context", "resources")
    with pytest.raises(ExchangeError, match="PACKAGE_KEY_REBOUND"):
        receive(b, changed, (r1,), request=RequestIdentity(str(uuid4()), str(uuid4())))
    assert before == (rows(b, "core", "repositories"), rows(b, "context", "resources"))
    another = replace(
        changed, sender_catalog_instance_uuidv4=str(uuid4()), digest_sha256=None
    )
    receive(b, another, (r1,))


@pytest.mark.parametrize(
    "point,core_committed,context_committed",
    [
        ("before_core_commit", False, False),
        ("after_core_commit", True, False),
        ("before_core_checkpoint", True, False),
        ("after_core_checkpoint", True, False),
        ("during_context", True, False),
        ("after_context_commit", True, True),
        ("before_context_checkpoint", True, True),
        ("after_context_checkpoint", True, True),
    ],
)
def test_crash_windows_and_fact_based_retry(
    tmp_path, point, core_committed, context_committed
):
    a, b = tmp_path / "a", tmp_path / "b"
    r1, *_ = fixture(a)
    catalog(b)
    package = ExchangeService(a).export_package(selection=scope())

    def cut(p):
        if p == point:
            raise RuntimeError("cut:" + p)

    with pytest.raises(AdmissionFailure):
        receive(b, package, (r1,), cut=cut)
    assert (r1 in {r[0] for r in rows(b, "core", "repositories")}) == core_committed
    assert bool(rows(b, "context", "resources")) == context_committed
    receive(b, package, (r1,))
    assert len(rows(b, "context", "resources")) == 1


def test_operational_loss_requires_new_issuance(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    r1, *_ = fixture(a)
    catalog(b)
    package = ExchangeService(a).export_package(selection=scope())
    receive(b, package, (r1,))
    identity = rows(b, "core", "store_identity")[0]
    (b / "operational.sqlite3").unlink()
    from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget

    with pytest.raises(Exception, match="CONTINUATION_UNAVAILABLE"):
        receive(b, package, (r1,), work=UnlimitedWorkBudget())
    initialize(b / "operational.sqlite3", "operational", identity[1], identity[2])
    with pytest.raises(Exception, match="CONTINUATION_UNAVAILABLE"):
        receive(b, package, (r1,))
    receive(b, package, (r1,), request=RequestIdentity(str(uuid4()), str(uuid4())))


def test_transfer_reports_never_shrunk_or_mixed(tmp_path):
    from repo_catalog.domain.p1_context import (
        MappingSupport,
        ProviderEndpointDeclaration,
        TransferEventReport,
        encode_transfer_supported_provenance,
    )
    from repo_catalog.domain.parent_report import ParentObservation, ParentReportKey
    from repo_catalog.domain.production_context import ResourceRelation

    a, b = tmp_path / "a", tmp_path / "b"
    r1, r2, issue, _ = fixture(a)
    catalog(b)
    event = ResourceKey.timeline_event(issue, "event-1")
    # These are newly authored disposable fixture originals, declared before
    # any selection. Provider native identities never come from Core UUIDs or
    # surviving translated endpoint rows.
    provider_from = ResourceKey.from_native(
        issue.service_instance_uuidv4, "repository", "fixture-from-provider"
    )
    provider_to = ResourceKey.from_native(
        issue.service_instance_uuidv4, "repository", "fixture-to-provider"
    )
    mappings = tuple(
        ResourceRepositoryRelation(
            provider,
            "represents_repository",
            FieldClock("fixture-mapping", 10),
            canonical(repository),
            make_provenance("fixture-mapping", evidence),
            11,
        )
        for provider, repository, evidence in (
            (provider_from, r1, "from-original"),
            (provider_to, r2, "to-original"),
        )
    )
    parent = ParentObservation(
        ParentReportKey(
            event,
            canonical([list(issue.coordinates())]),
            make_provenance("fixture-parent", "independent-parent-original"),
            canonical(
                {
                    "clock": {"domain": "fixture-parent", "at_us": 12},
                    "document_kind": "timeline_event",
                    "state": "complete",
                }
            ),
        ),
        13,
    )
    original_provenance = encode_transfer_supported_provenance(
        "provider",
        {"event": "original-event"},
        (
            (
                "transfer_from_repository",
                MappingSupport(provider_from, (mappings[0].claim_key,)),
            ),
            (
                "transfer_to_repository",
                MappingSupport(provider_to, (mappings[1].claim_key,)),
            ),
        ),
    )
    reports = [
        TransferEventReport.from_targets(
            event,
            clock=FieldClock("provider", 20),
            provenance_json=original_provenance,
            observed_at_us=21,
            from_target_json=canonical(r1),
            to_target_json=canonical(r2),
            parent_report=parent,
            endpoint_declaration=ProviderEndpointDeclaration(
                provider_from, provider_to
            ),
            endpoints=(
                ("transfer_from_repository", canonical(r1)),
                ("transfer_to_repository", canonical(r2)),
            ),
        ),
        TransferEventReport.from_targets(
            event,
            clock=FieldClock("provider", 22),
            provenance_json=make_provenance("provider", "one-sided-original"),
            observed_at_us=23,
            from_target_json="null",
            parent_report=parent,
            endpoint_declaration=ProviderEndpointDeclaration(
                "explicit_null", "not_reported"
            ),
            endpoints=(("transfer_from_repository", "null"),),
        ),
    ]
    with fixture_transaction(
        a,
        local_grants(
            issue,
            r1,
            r2,
            resources=(event, provider_from, provider_to),
            units=(*mappings, parent, *reports),
        ),
    ) as ctx:
        ctx.resource(
            event, identification=RI.scoped(event, issue, "timeline_event", "event-1")
        )
        for provider in (provider_from, provider_to):
            ctx.resource(provider)
        for mapping in mappings:
            ctx.admit_repository_relation(mapping)
        ctx.relation(
            ResourceRelation(
                event,
                "parent",
                (issue,),
                parent.provenance_json,
                parent.scope_json,
                parent.observed_at_us,
            )
        )
        for report in reports:
            ctx.admit_transfer_event(report)
    package = ExchangeService(a).export_package(selection=scope())
    receive(b, package, (r1,))
    with Context.snapshot(b) as ctx:
        received = ctx.transfer_event_reports(event)
        assert len(received) == 1
        assert received[0].report_key == reports[1].report_key
        assert received[0].from_relations[0].is_explicit_null_target
    c = tmp_path / "c"
    catalog(c)
    receive(c, package, (r1, r2))
    with Context.snapshot(c) as ctx:
        assert set(ctx.transfer_event_reports(event)) == set(reports)
    changed_report = TransferEventReport.from_targets(
        event,
        clock=reports[0].clock,
        provenance_json=reports[0].provenance_json,
        observed_at_us=reports[0].observed_at_us,
        from_target_json=canonical(r1),
        to_target_json="null",
        parent_report=parent,
        endpoint_declaration=ProviderEndpointDeclaration(
            provider_from, "explicit_null"
        ),
        endpoints=(
            ("transfer_from_repository", canonical(r1)),
            ("transfer_to_repository", "null"),
        ),
    )
    for row in package.context["resource_relations"]:
        if row["scope_json"] == reports[0].scope_json:
            row["scope_json"] = changed_report.scope_json
            row["members_json"] = changed_report.members_json
    for row in package.context["resource_repository_relations"]:
        if (
            row["clock_json"] == reports[0].clock.encode()
            and row["relation_kind"] == "transfer_to_repository"
        ):
            row["target_json"] = "null"
    before = rows(c, "core", "git_objects")
    package.core["git_objects"].append({"object_format": "sha1", "full_oid": "2" * 40})
    changed = replace(package, package_id=str(uuid4()), digest_sha256=None)
    with pytest.raises(ExchangeError, match="IMMUTABLE_REPLAY_CONFLICT"):
        receive(c, changed, (r1, r2))
    assert rows(c, "core", "git_objects") == before


def test_mapping_claim_support_and_dispositions_are_exact(tmp_path):
    from repo_catalog.domain.p1_context import (
        MappingDisposition,
        MappingSupport,
        encode_supported_provenance,
    )
    from repo_catalog.domain.production_context import ResourceRelation

    a, b = tmp_path / "a", tmp_path / "b"
    r1, r2, issue, _ = fixture(a)
    catalog(b)
    provider_repo = ResourceKey.from_native(
        issue.service_instance_uuidv4, "repository", "R_provider_node_A"
    )
    mapping = ResourceRepositoryRelation(
        provider_repo,
        "represents_repository",
        FieldClock("mapping", 10),
        canonical(r1),
        make_provenance("mapping", "original"),
        10,
    )
    owning = ResourceRepositoryRelation(
        issue,
        "owning_repository",
        FieldClock("provider", 30),
        canonical(r1),
        encode_supported_provenance(
            "provider",
            "resolved-original",
            MappingSupport(provider_repo, (mapping.claim_key,)),
        ),
        30,
    )
    withdrawal = MappingDisposition(
        mapping.claim_key,
        "withdraw",
        FieldClock("mapping", 31),
        make_provenance("mapping", "withdraw-original"),
        31,
    )
    with fixture_transaction(
        a,
        local_grants(
            issue,
            r1,
            r2,
            resources=(provider_repo,),
            units=(mapping, owning, withdrawal),
        ),
    ) as ctx:
        ctx.resource(provider_repo)
        ctx.admit_repository_relation(mapping)
        ctx.admit_repository_relation(owning)
        ctx.admit_mapping_disposition(withdrawal)
        ctx.relation(
            ResourceRelation(
                issue,
                "provider_repository",
                (provider_repo,),
                make_provenance("provider", "original-provider-role"),
                "{}",
                30,
            )
        )
    selected = ExchangeSelectionScope(
        repository_uuidv4s=(r1,),
        object_oids=(),
        resource_keys=(issue,),
        source_uuidv4s=(),
    )
    package = ExchangeService(a).export_package(selection=selected)
    receive(b, package, (r1,))
    assert rows(a, "context", "repository_mapping_dispositions") == rows(
        b, "context", "repository_mapping_dispositions"
    )
    exported = rows(b, "context", "resource_repository_relations")
    assert any(r[6] == owning.provenance_json for r in exported)
    assert rows(a, "context", "resource_relations") == rows(
        b, "context", "resource_relations"
    )
    before = rows(b, "core", "git_objects")
    package.context["repository_mapping_dispositions"][0]["observed_at_us"] += 1
    package.core["git_objects"].append({"object_format": "sha1", "full_oid": "2" * 40})
    changed = replace(package, package_id=str(uuid4()), digest_sha256=None)
    with pytest.raises(ExchangeError, match="IMMUTABLE_REPLAY_CONFLICT"):
        receive(b, changed, (r1,))
    assert rows(b, "core", "git_objects") == before


def test_empty_oid_and_context_payload_cannot_override_selection(tmp_path):
    from repo_catalog.domain.exchange import (
        ExchangePackage,
        empty_context_section,
        empty_core_section,
    )
    from repo_catalog.domain.resource_identification import ResourceIdentification

    seed = catalog(tmp_path)
    data = empty_core_section()
    data["git_objects"] = [{"object_format": "sha1", "full_oid": "a" * 40}]
    ctxdata = empty_context_section()
    service = str(uuid4())
    ctxdata["providers"] = [
        {
            "service_instance_uuidv4": service,
            "provider_kind": "github",
            "configuration_json": "{}",
        }
    ]
    ctxdata["resources"] = [
        ResourceIdentification.unscoped(
            ResourceKey.from_native(service, "issue", "99")
        ).to_wire()
    ]
    selected = ExchangeSelectionScope(
        repository_uuidv4s=(), object_oids=(), resource_keys=(), source_uuidv4s=()
    )
    package = ExchangePackage(
        str(uuid4()), None, str(uuid4()), seed, selected, core=data, context=ctxdata
    )
    receive(tmp_path, package)
    assert not rows(tmp_path, "core", "git_objects")
    assert not rows(tmp_path, "context", "resources")


def test_malformed_unselected_repository_rejected_before_binding(tmp_path):
    from repo_catalog.domain.exchange import ExchangePackage, empty_core_section

    seed = catalog(tmp_path)
    data = empty_core_section()
    data["repositories"] = [{"repository_uuidv4": "malformed"}]
    package = ExchangePackage(
        str(uuid4()), None, str(uuid4()), seed, scope(), core=data
    )
    with pytest.raises(Exception):
        receive(tmp_path, package)
    assert not any(
        "adr0030-package-binding" in r[2]
        for r in rows(tmp_path, "operational", "request_continuations")
    )


def test_bounded_typed_core_graph_and_shared_oid_identity(tmp_path):
    from repo_catalog.domain.p1_core import (
        Provenance,
        RelationGroup,
        RelationMember,
        ScalarClaim,
    )

    r1, r2, issue, one = fixture(tmp_path)
    two = OID("sha1", "2" * 40)
    three = OID("sha1", "3" * 40)
    provenance = Provenance("fixture", "graph", "actual-edge", "fixture", "1")
    with __import__("contextlib").closing(GitCore(tmp_path / "core.sqlite3")) as core:
        for oid, target in ((one, two), (two, three), (three, one)):
            core.admit_claim(ScalarClaim(oid, "type", "commit", provenance))
            core.admit_group(
                RelationGroup(
                    oid,
                    "commit_parents",
                    "all",
                    "complete",
                    (RelationMember(0, target),),
                    provenance,
                )
            )
    selected = ExchangeSelectionScope(
        repository_uuidv4s=(r1, r2),
        object_oids=(one,),
        resource_keys=(),
        source_uuidv4s=(),
        max_depth=1,
    )
    package = ExchangeService(tmp_path).export_package(selection=selected)
    assert {
        (r["object_format"], r["full_oid"]) for r in package.core["git_objects"]
    } == {one.key, two.key}
    assert any(r["full_oid"] == two.full_oid for r in package.core["scalar_claims"])
    assert package.selection_report["dependency_reasons"]
    package = ExchangeService(tmp_path).export_package(
        selection=replace(selected, max_depth=8)
    )
    assert len(package.core["git_objects"]) == 3
    assert len(package.core["repositories"]) == 2


def test_graph_work_byte_unit_limits_are_reported_without_recovery_stop(tmp_path):
    fixture(tmp_path)
    for selected in (scope(max_work=1), scope(max_bytes=1), scope(max_units=0)):
        package = ExchangeService(tmp_path).export_package(selection=selected)
        assert package.selection_report["omissions"]
        assert not (tmp_path / "p1-recovery-stop.json").exists()


def test_complete_source_inventory_and_coverage_stay_whole(tmp_path):
    from repo_catalog.domain.p1_context import CoverageClaim, CoverageScope
    from repo_catalog.domain.production_context import SourceInventory

    a, b = tmp_path / "a", tmp_path / "b"
    r1, r2, issue, _ = fixture(a)
    catalog(b)
    source = str(uuid4())
    original_scope = canonical(
        {
            "coverage_kind": "repositories",
            "service_instance_uuidv4": issue.service_instance_uuidv4,
        }
    )
    inventory = SourceInventory(
        source,
        original_scope,
        40,
        "complete",
        True,
        (r1, r2),
        make_provenance("provider", "original-inventory"),
    )
    claim = CoverageClaim(
        CoverageScope.source_inventory(source, original_scope, "repositories"),
        40,
        "complete",
    )
    with fixture_transaction(a, local_grants(issue, r1, r2, sources=(source,))) as ctx:
        ctx.source(source, issue.service_instance_uuidv4, "{}")
        ctx.inventory(inventory)
        ctx.prove_inventory(claim, inventory)
    package = ExchangeService(a).export_package(selection=scope())
    receive(b, package, (r1,))
    assert not rows(b, "context", "source_inventory_evidence")
    assert not rows(b, "context", "coverage_claims")
    c = tmp_path / "c"
    catalog(c)
    receive(c, package, (r1, r2))
    assert rows(a, "context", "source_inventory_evidence") == rows(
        c, "context", "source_inventory_evidence"
    )
    assert rows(a, "context", "coverage_claims") == rows(
        c, "context", "coverage_claims"
    )
    assert rows(a, "context", "source_coverage_proofs") == rows(
        c, "context", "source_coverage_proofs"
    )


def test_competing_package_binding_connections(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger

    catalog(tmp_path)
    barrier = Barrier(2)
    sender, package = str(uuid4()), str(uuid4())

    def compete(digest):
        with OperationalAcquisitionLedger(tmp_path) as ledger:
            request = RequestIdentity(str(uuid4()), str(uuid4()))
            ledger.create_budget(
                scope=["race", digest], request=request, new_request=True
            )
            barrier.wait(timeout=10)
            try:
                return ledger.work_ledger.bind_exchange_package(
                    request, sender, package, digest
                )
            except ExchangeError as error:
                return error.code

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(compete, ("a" * 64, "b" * 64)))
    assert results.count(True) == 1
    assert results.count("PACKAGE_KEY_REBOUND") == 1


@pytest.mark.parametrize("point", ["after_core_commit", "after_context_commit"])
def test_process_exit_before_checkpoint_recovery_uses_facts(tmp_path, point):
    import subprocess
    import sys

    a, b = tmp_path / "a", tmp_path / "b"
    r1, *_ = fixture(a)
    catalog(b)
    package = ExchangeService(a).export_package(selection=scope())
    wire = tmp_path / "package.json"
    wire.write_text(encode_package(package))
    request = RequestIdentity(str(uuid4()), str(uuid4()))
    code = """
import os,sys
from pathlib import Path
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.p1_coordination import RequestIdentity
p,wire,repo,origin,request,point=sys.argv[1:]
def cut(where):
    if where==point: os._exit(77)
ExchangeService(Path(p)).import_package(Path(wire).read_text(),request=RequestIdentity(origin,request),new_request=True,permitted_repository_uuidv4s=(repo,),cut=cut)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(b), str(wire), r1, *request.values(), point],
        timeout=30,
    )
    assert result.returncode == 77
    assert r1 in {r[0] for r in rows(b, "core", "repositories")}
    assert bool(rows(b, "context", "resources")) == (point == "after_context_commit")
    receive(b, package, (r1,), request=request)
    assert len(rows(b, "context", "resources")) == 1


def test_native_metadata_notes_and_capture_coverage_without_provider_intake(tmp_path):
    from repo_catalog.adapters.git.native import GitNativeSource
    from repo_catalog.application.acquisition import GitAcquisition
    from repo_catalog.domain.acquisition import (
        GitNativeAcquisitionRequest,
        NotesAcquisitionSpec,
    )
    from tests.integration.p5.conftest import build_sample_git_repo

    a, b = tmp_path / "a", tmp_path / "b"
    r1 = catalog(a)
    catalog(b)
    native = tmp_path / "native"
    oids = build_sample_git_repo(native)
    origin, capture = str(uuid4()), str(uuid4())
    request = GitNativeAcquisitionRequest(
        repository_uuidv4=r1,
        capture_origin_uuidv4=origin,
        capture_uuidv4=capture,
        source_attribution="original-git",
        observed_at_us=50,
        select_oids=(oids["commit1"], oids["commit2"], oids["tree"], oids["tag"]),
        retain_bytes=True,
        notes=NotesAcquisitionSpec(
            discover_notes=True,
            acquire_inventories=True,
            target_oids=(oids["commit2"],),
            retain_note_bodies=True,
        ),
    )
    GitAcquisition(a, operational=a).acquire_from_native(
        GitNativeSource(native), request, new_request=True
    )
    from contextlib import closing

    from repo_catalog.domain.p1_core import CoreCoverageScope
    from repo_catalog.domain.p1_coverage import CoverageClaim

    pair = tuple(rows(a, "core", "captures")[0][:2])
    cap_scope = CoreCoverageScope("capture", (*pair, "notes_inventory"))
    with closing(GitCore(a / "core.sqlite3")) as core:
        core.admit_coverage_scope(cap_scope)
        core.admit_coverage(CoverageClaim(cap_scope, 51, "partial"))
    package = ExchangeService(a).export_package(selection=scope())
    assert (
        package.core["captures"]
        and package.core["retained_metadata"]
        and package.core["retained_notes"]
    )
    receive(b, package, (r1,))
    assert rows(a, "core", "captures") == rows(b, "core", "captures")
    assert rows(a, "core", "coverage_claims") == rows(b, "core", "coverage_claims")
    assert rows(a, "core", "notes_claims") == rows(b, "core", "notes_claims")
    assert rows(a, "core", "notes_groups") == rows(b, "core", "notes_groups")
    for section in ("note_roles", "retained_notes"):
        original_root = package.core[section][0]["root"]
        package.core[section][0]["root"] = "2" * 40
        changed = replace(package, package_id=str(uuid4()), digest_sha256=None)
        with pytest.raises(ExchangeError, match="NOTES_CAPTURE_ROOT"):
            receive(b, changed, (r1,))
        assert not any(
            changed.package_id in r[2] and "adr0030-package-binding" in r[2]
            for r in rows(b, "operational", "request_continuations")
        )
        package.core[section][0]["root"] = original_root
    for limited in (scope(max_units=10), scope(max_bytes=500)):
        partial = ExchangeService(a).export_package(selection=limited)
        c = tmp_path / str(uuid4())
        catalog(c)
        receive(c, partial, (r1,))
        assert partial.selection_report["omissions"]


def test_receiver_selection_stop_and_access_unchanged(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    r1, *_ = fixture(a)
    catalog(b)
    package = ExchangeService(a).export_package(selection=scope())
    sentinel = b / "access.sqlite3"
    sentinel.write_bytes(b"access-is-independent")
    empty = ExchangeSelectionScope(
        repository_uuidv4s=(), object_oids=(), resource_keys=(), source_uuidv4s=()
    )
    receive(b, package, (r1,), selection=empty)
    assert not rows(b, "context", "resources") and not rows(b, "core", "git_objects")
    assert sentinel.read_bytes() == b"access-is-independent"
    (b / "p1-recovery-stop.json").write_text("{}")
    before = rows(b, "operational", "request_continuations")
    with pytest.raises(Exception, match="RECOVERY_REQUIRED"):
        receive(b, package, (r1,))
    assert rows(b, "operational", "request_continuations") == before


def test_receiver_flags_and_zero_admission_limits_are_enforced(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    r1, *_ = fixture(a)
    catalog(b)
    package = ExchangeService(a).export_package(selection=scope())
    for selection in (
        scope(include_core=False, include_context=False, include_retained_bytes=False),
        scope(max_units=0),
        scope(max_bytes=0),
    ):
        receiver = tmp_path / str(uuid4())
        catalog(receiver)
        report = receive(receiver, package, (r1,), selection=selection)
        assert not rows(receiver, "core", "git_objects")
        assert not rows(receiver, "context", "resources")
        assert report.omissions
    from repo_catalog.domain.p1_core import CoreFailure

    with pytest.raises(CoreFailure) as exhausted:
        receive(b, package, (r1,), selection=scope(max_work=0))
    assert exhausted.value.code == "BUDGET"
    assert not rows(b, "core", "git_objects")


def test_missing_repository_unit_does_not_rollback_independent_object(tmp_path):
    from repo_catalog.domain.exchange import ExchangePackage, empty_core_section
    from repo_catalog.domain.p1_core import Provenance

    seed = catalog(tmp_path)
    unknown = str(uuid4())
    data = empty_core_section()
    data["git_objects"] = [{"object_format": "sha1", "full_oid": "b" * 40}]
    data["repository_claims"] = [
        {
            "repository_uuidv4": unknown,
            "field": "name",
            "value_json": '"example"',
            "provenance_json": Provenance(
                "reporter", "event", "field", "decoder", "1"
            ).encoded,
        }
    ]
    package = ExchangePackage(
        str(uuid4()), None, str(uuid4()), seed, scope(), core=data
    )
    report = receive(tmp_path, package, (unknown,))
    assert len(rows(tmp_path, "core", "git_objects")) == 1
    assert not rows(tmp_path, "core", "repository_claims")
    assert any(
        r["section"] == "repository_claims"
        and r["reason"] == "missing_required_dependency"
        for r in report.omissions
    )


def test_malformed_scalar_tag_cannot_be_reencoded_as_known_claim(tmp_path):
    from repo_catalog.domain.exchange import ExchangePackage, empty_core_section
    from repo_catalog.domain.p1_core import Provenance

    seed = catalog(tmp_path)
    data = empty_core_section()
    data["git_objects"] = [{"object_format": "sha1", "full_oid": "c" * 40}]
    data["scalar_claims"] = [
        {
            "object_format": "sha1",
            "full_oid": "c" * 40,
            "field": "size",
            "value_json": '["bogus",1]',
            "provenance_json": Provenance(
                "reporter", "event", "field", "decoder", "1"
            ).encoded,
            "authority": "reported",
        }
    ]
    package = ExchangePackage(
        str(uuid4()), None, str(uuid4()), seed, scope(), core=data
    )
    with pytest.raises(ExchangeError, match="NONCANONICAL_CLAIM"):
        receive(tmp_path, package)
    assert not rows(tmp_path, "core", "scalar_claims")
    assert not any(
        "adr0030-package-binding" in r[2]
        for r in rows(tmp_path, "operational", "request_continuations")
    )


def test_binding_sql_update_delete_replace_and_upsert_cannot_rebind(tmp_path):
    import sqlite3

    from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger

    catalog(tmp_path)
    with OperationalAcquisitionLedger(tmp_path) as ledger:
        request, _, _, _ = ledger.create_budget(scope=["binding-sql"])
        sender, package = str(uuid4()), str(uuid4())
        ledger.work_ledger.bind_exchange_package(request, sender, package, "a" * 64)
        slot = canonical(["adr0030-package-binding", sender, package])
        predicate = (
            "request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json=?"
        )
        parameters = (*request.values(), slot)
        for sql, values in (
            (
                "UPDATE request_continuations SET cursor_json=? WHERE " + predicate,
                (canonical({"digest_sha256": "b" * 64}), *parameters),
            ),
            ("DELETE FROM request_continuations WHERE " + predicate, parameters),
            (
                "INSERT OR REPLACE INTO request_continuations VALUES(?,?,?,?)",
                (*parameters, canonical({"digest_sha256": "b" * 64})),
            ),
            (
                "INSERT INTO request_continuations VALUES(?,?,?,?) ON CONFLICT(request_origin_uuidv4,request_uuidv4,continuation_scope_json) DO UPDATE SET cursor_json=excluded.cursor_json",
                (*parameters, canonical({"digest_sha256": "b" * 64})),
            ),
        ):
            with pytest.raises(sqlite3.IntegrityError, match="immutable Exchange"):
                ledger.db.execute(sql, values)
        assert not ledger.work_ledger.bind_exchange_package(
            request, sender, package, "a" * 64
        )


def test_core_reference_missing_dependency_retains_original_report_clock(tmp_path):
    from repo_catalog.domain.p1_context import FieldCandidate

    a, b = tmp_path / "a", tmp_path / "b"
    r1, r2, issue, oid = fixture(a)
    catalog(b)
    original = FieldCandidate(
        issue,
        "reported_core_reference:head",
        canonical(list(oid.key)),
        FieldClock("provider-head", 73),
        make_provenance("provider", "original-head"),
        74,
    )
    with fixture_transaction(a, local_grants(issue, r1, r2, oids=(oid,))) as ctx:
        ctx.admit_field(original)
        ctx.link_core(
            issue, "head", *oid.key, original.provenance_json, lambda *_: True
        )
    package = ExchangeService(a).export_package(selection=scope())
    selected = scope(include_core=False)
    report = receive(b, package, (r1, r2), selection=selected)
    with Context.snapshot(b) as ctx:
        assert ctx.candidates(issue, original.field_name) == (original,)
        assert not ctx.db.execute("SELECT 1 FROM core_references").fetchall()
    assert any(r["reason"] == "missing_core_oid" for r in report.omissions)


@pytest.mark.parametrize("kind", ["source_inventory", "collection"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("members_json", "[]"),
        ("terminal_state", "partial"),
        ("provenance_json", canonical({"source": "forged", "evidence": "different"})),
    ],
)
def test_contradictory_coverage_proof_is_rejected_before_binding(
    tmp_path, kind, field, value
):
    from repo_catalog.domain.p1_context import CoverageClaim, CoverageScope
    from repo_catalog.domain.production_context import (
        CollectionObservation,
        SourceInventory,
    )

    a, b = tmp_path / "a", tmp_path / "b"
    r1, r2, issue, _ = fixture(a)
    catalog(b)
    provenance = make_provenance("provider", "original-complete")
    source = str(uuid4())
    child = ResourceKey.document(issue, "comment", "comment", "99")
    with fixture_transaction(
        a, local_grants(issue, r1, r2, sources=(source,), resources=(child,))
    ) as ctx:
        if kind == "source_inventory":
            original_scope = canonical(
                {
                    "coverage_kind": "repositories",
                    "service_instance_uuidv4": issue.service_instance_uuidv4,
                }
            )
            ctx.source(source, issue.service_instance_uuidv4, "{}")
            inventory = SourceInventory(
                source, original_scope, 80, "complete", True, (r1, r2), provenance
            )
            ctx.inventory(inventory)
            ctx.prove_inventory(
                CoverageClaim(
                    CoverageScope.source_inventory(
                        source, original_scope, "repositories"
                    ),
                    80,
                    "complete",
                ),
                inventory,
            )
        else:
            ctx.resource(child, identification=RI.scoped(child, issue, "comment", "99"))
            observation = CollectionObservation(
                issue,
                "comments",
                provenance,
                canonical({"coverage_kind": "comments"}),
                80,
                "complete",
                (child,),
            )
            ctx.collection(observation)
            ctx.prove_collection(
                CoverageClaim(
                    CoverageScope.collection(issue, "comments", provenance, "comments"),
                    80,
                    "complete",
                ),
                observation,
                required_scope_json=observation.scope_json,
            )
    package = ExchangeService(a).export_package(selection=scope())
    package.context["coverage_proofs"][0][field] = value
    malformed = replace(package, digest_sha256=None)
    with pytest.raises(ExchangeError, match="INVALID_COVERAGE_PROOF"):
        receive(b, malformed, (r1, r2))
    assert not rows(b, "context", "resources")
    assert not any(
        "adr0030-package-binding" in r[2]
        for r in rows(b, "operational", "request_continuations")
    )


@pytest.mark.parametrize("raw_dict", [False, True])
def test_caller_mutation_after_preflight_cannot_change_bound_content(
    tmp_path, raw_dict
):
    a, b = tmp_path / "a", tmp_path / "b"
    r1, r2, _, oid = fixture(a)
    catalog(b)
    package = ExchangeService(a).export_package(selection=scope())
    original_digest = package.digest_sha256
    raw = package.to_dict() if raw_dict else package

    def mutate(point):
        if point == "after_preflight":
            data = raw["core"] if raw_dict else raw.core
            data["git_objects"][0]["full_oid"] = "2" * 40

    report = receive(b, raw, (r1, r2), cut=mutate)
    assert report.package_digest_sha256 == original_digest
    assert {tuple(r) for r in rows(b, "core", "git_objects")} == {oid.key}


def test_selection_cannot_hide_conflicting_inventory_terminal_for_completeness(
    tmp_path,
):
    from repo_catalog.domain.p1_context import CoverageClaim, CoverageScope
    from repo_catalog.domain.production_context import SourceInventory

    a, b = tmp_path / "a", tmp_path / "b"
    r1, r2, issue, _ = fixture(a)
    catalog(b)
    source = str(uuid4())
    original_scope = canonical(
        {
            "coverage_kind": "repositories",
            "service_instance_uuidv4": issue.service_instance_uuidv4,
        }
    )
    complete = SourceInventory(
        source,
        original_scope,
        90,
        "complete",
        True,
        (r1,),
        make_provenance("provider", "complete-first"),
    )
    competing = replace(
        complete,
        state="partial",
        terminal=False,
        repositories=(r2,),
        provenance_json=make_provenance("provider", "competing-second"),
    )
    with fixture_transaction(a, local_grants(issue, r1, r2, sources=(source,))) as ctx:
        ctx.source(source, issue.service_instance_uuidv4, "{}")
        ctx.inventory(complete)
        ctx.prove_inventory(
            CoverageClaim(
                CoverageScope.source_inventory(source, original_scope, "repositories"),
                90,
                "complete",
            ),
            complete,
        )
        ctx.inventory(competing)
    selected = scope(repository_uuidv4s=(r1,))
    package = ExchangeService(a).export_package(selection=selected)
    assert not package.context["coverage_claims"]
    assert not package.context["coverage_proofs"]
    receive(b, package, (r1,))
    assert not rows(b, "context", "coverage_claims")
    for limit in (8, 12, 18, 30):
        bounded = ExchangeService(a).export_package(selection=scope(max_units=limit))
        if bounded.context["coverage_claims"]:
            assert len(bounded.context["source_inventories"]) == 2


def test_capture_non_utf8_ref_preserves_native_key(tmp_path):
    from contextlib import closing

    from repo_catalog.domain.p1_core import Capture

    a, b = tmp_path / "a", tmp_path / "b"
    r1, _, _, oid = fixture(a)
    catalog(b)
    capture = Capture(
        str(uuid4()),
        str(uuid4()),
        r1,
        "original-source",
        b"refs/notes/non-utf8-\xff".decode("utf-8", "surrogateescape"),
        oid,
    )
    with closing(GitCore(a / "core.sqlite3")) as core:
        core.admit_capture(capture)
    package = ExchangeService(a).export_package(selection=scope())
    wire = encode_package(package)
    receive(b, decode_package(wire), (r1,))
    assert rows(a, "core", "captures") == rows(b, "core", "captures")


@pytest.mark.parametrize(
    "section",
    ["resource_repository_relations", "field_candidates", "resource_relations"],
)
def test_internally_contradictory_original_times_rejected_before_binding(
    tmp_path, section
):
    from repo_catalog.domain.p1_context import FieldCandidate
    from repo_catalog.domain.production_context import ResourceRelation

    a, b = tmp_path / "a", tmp_path / "b"
    r1, r2, issue, _ = fixture(a)
    catalog(b)
    with fixture_transaction(a, local_grants(issue, r1, r2)) as ctx:
        ctx.admit_field(
            FieldCandidate(
                issue,
                "state",
                '"open"',
                FieldClock("provider", 1),
                make_provenance("fixture", "field"),
                1,
            )
        )
        ctx.relation(
            ResourceRelation(
                issue, "related", (), make_provenance("fixture", "relation"), "{}", 1
            )
        )
    package = ExchangeService(a).export_package(selection=scope())
    row = package.context[section][0]
    package.context[section].append(
        {**row, "observed_at_us": row["observed_at_us"] + 1}
    )
    package = replace(package, digest_sha256=None)
    with pytest.raises(ExchangeError, match="IMMUTABLE_REPLAY_CONFLICT"):
        receive(b, package, (r1, r2))
    assert not rows(b, "core", "git_objects")
    assert not any(
        "adr0030-package-binding" in r[2]
        for r in rows(b, "operational", "request_continuations")
    )


def test_existing_relation_time_conflict_rejected_before_independent_core_commit(
    tmp_path,
):
    a, b = tmp_path / "a", tmp_path / "b"
    r1, r2, issue, _ = fixture(a)
    catalog(b)
    package = ExchangeService(a).export_package(selection=scope())
    receive(b, package, (r1, r2))
    before = rows(b, "core", "git_objects")
    package.context["resource_repository_relations"][0]["observed_at_us"] += 1
    package.core["git_objects"].append({"object_format": "sha1", "full_oid": "2" * 40})
    changed = replace(package, package_id=str(uuid4()), digest_sha256=None)
    with pytest.raises(ExchangeError, match="IMMUTABLE_REPLAY_CONFLICT"):
        receive(b, changed, (r1, r2))
    assert rows(b, "core", "git_objects") == before
    assert not any(
        changed.package_id in r[2] and "adr0030-package-binding" in r[2]
        for r in rows(b, "operational", "request_continuations")
    )


def test_capture_pair_conflicting_payload_rejected_before_binding(tmp_path):
    from contextlib import closing

    from repo_catalog.domain.p1_core import Capture

    a, b = tmp_path / "a", tmp_path / "b"
    r1, _, _, oid = fixture(a)
    catalog(b)
    capture = Capture(str(uuid4()), str(uuid4()), r1, "source", "refs/heads/main", oid)
    with closing(GitCore(a / "core.sqlite3")) as core:
        core.admit_capture(capture)
    package = ExchangeService(a).export_package(selection=scope())
    package.core["captures"].append(
        {**package.core["captures"][0], "source": "contradictory-source"}
    )
    malformed = replace(package, digest_sha256=None)
    with pytest.raises(ExchangeError, match="IMMUTABLE_REPLAY_CONFLICT"):
        receive(b, malformed, (r1,))
    assert not rows(b, "core", "git_objects")


def test_shared_oid_does_not_coalesce_repository_membership_reports(tmp_path):
    from contextlib import closing

    from repo_catalog.domain.p1_core import GitObservation, Provenance

    a, b = tmp_path / "a", tmp_path / "b"
    r1, r2, _, oid = fixture(a)
    catalog(b)
    original = []
    capture_origin, capture_id = str(uuid4()), str(uuid4())
    with closing(GitCore(a / "core.sqlite3")) as core:
        for repository in (r1, r2):
            observation = GitObservation(
                capture_origin,
                capture_id,
                repository,
                "membership",
                ("fixture", *oid.key),
                {
                    "object": list(oid.key),
                    "source": "original-source",
                    "observed_at_us": 100,
                },
                Provenance("fixture", "shared-original", "membership", "fixture", "1"),
            )
            core.admit_observation(observation)
            original.append(observation)
    package = ExchangeService(a).export_package(selection=scope())
    receive(b, package, (r1, r2))
    assert len(rows(b, "core", "git_objects")) == 1
    assert {r[2] for r in rows(b, "core", "git_observations")} == {r1, r2}
    assert rows(a, "core", "git_observations") == rows(b, "core", "git_observations")
    c = tmp_path / "c"
    catalog(c)
    receive(c, package, (r1,))
    assert {r[2] for r in rows(c, "core", "git_observations")} == {r1}
    assert r2 not in {r[0] for r in rows(c, "core", "repositories")}


@pytest.mark.parametrize("existing", [False, True])
def test_collection_scope_binding_rejected_before_core_commit(tmp_path, existing):
    from repo_catalog.domain.production_context import CollectionObservation

    a, b = tmp_path / "a", tmp_path / "b"
    r1, r2, issue, _ = fixture(a)
    catalog(b)
    with fixture_transaction(a, local_grants(issue, r1, r2)) as ctx:
        ctx.collection(
            CollectionObservation(
                issue,
                "comments",
                make_provenance("fixture", "collection"),
                canonical({"coverage_kind": "comments"}),
                10,
                "complete",
            )
        )
    package = ExchangeService(a).export_package(selection=scope())
    if existing:
        receive(b, package, (r1, r2))
    before = rows(b, "core", "git_objects")
    original = package.context["collections"][0]
    changed_row = {
        **original,
        "scope_json": canonical({"coverage_kind": "comments", "changed": True}),
    }
    package.context["collections"] = (
        [changed_row] if existing else [original, changed_row]
    )
    package.core["git_objects"].append({"object_format": "sha1", "full_oid": "2" * 40})
    changed = replace(package, package_id=str(uuid4()), digest_sha256=None)
    with pytest.raises(ExchangeError, match="IMMUTABLE_REPLAY_CONFLICT"):
        receive(b, changed, (r1, r2))
    assert rows(b, "core", "git_objects") == before


@pytest.mark.parametrize("section", ["collections", "resource_relations"])
def test_modeled_collection_member_cannot_borrow_another_parent(tmp_path, section):
    from repo_catalog.domain.production_context import (
        CollectionObservation,
        ResourceRelation,
    )

    a, b = tmp_path / "a", tmp_path / "b"
    r1, r2, issue, _ = fixture(a)
    catalog(b)
    other = ResourceKey.from_native(issue.service_instance_uuidv4, "issue", "8")
    child = ResourceKey.document(other, "comment", "comments", "1")
    with fixture_transaction(
        a, local_grants(issue, r1, r2, resources=(other, child))
    ) as ctx:
        ctx.resource(other)
        ctx.resource(child, identification=RI.scoped(child, other, "comments", "1"))
        if section == "collections":
            ctx.collection(
                CollectionObservation(
                    issue,
                    "comments",
                    make_provenance("fixture", "collection"),
                    "{}",
                    10,
                    "complete",
                )
            )
        else:
            ctx.relation(
                ResourceRelation(
                    issue,
                    "comments",
                    (),
                    make_provenance("fixture", "relation"),
                    "{}",
                    10,
                )
            )
    package = ExchangeService(a).export_package(selection=scope())
    package.context[section][0]["members_json"] = canonical([child.coordinates()])
    with pytest.raises(ExchangeError, match="MEMBER_OWNER"):
        receive(b, replace(package, digest_sha256=None), (r1, r2))
    assert not rows(b, "core", "git_objects")
    assert not any(
        "adr0030-package-binding" in r[2]
        for r in rows(b, "operational", "request_continuations")
    )


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize(
    "section",
    [
        "repository_claims",
        "scalar_claims",
        "relation_groups",
        "notes_claims",
        "notes_groups",
    ],
)
def test_core_immutable_unique_payload_preflight(tmp_path, section, existing):
    from contextlib import closing

    from repo_catalog.domain.p1_core import (
        Capture,
        NotesClaim,
        NotesGroup,
        Provenance,
        RelationGroup,
        RepositoryClaim,
        ScalarClaim,
    )

    a, b = tmp_path / "a", tmp_path / "b"
    r1, r2, _, oid = fixture(a)
    catalog(b)
    prov = Provenance("fixture", "same-original", "claim", "fixture", "1")
    capture = Capture(str(uuid4()), str(uuid4()), r1, "fixture", "refs/notes/test", oid)
    with closing(GitCore(a / "core.sqlite3")) as core:
        core.admit_repository_claim(RepositoryClaim(r1, "name", "one", prov))
        core.admit_claim(ScalarClaim(oid, "type", "blob", prov))
        core.admit_group(
            RelationGroup(oid, "commit_parents", "all", "known_empty", (), prov)
        )
        core.admit_notes_claim(NotesClaim(capture, oid, oid, prov))
        core.admit_notes_group(NotesGroup(capture, "all", "unknown", (), prov))
    package = ExchangeService(a).export_package(selection=scope())
    if existing:
        receive(b, package, (r1, r2))
    before = rows(b, "core", "git_objects")
    original = package.core[section][0]
    changed_row = dict(original)
    if section == "repository_claims":
        changed_row["value_json"] = '"two"'
    elif section == "scalar_claims":
        changed_row["value_json"] = '["known","tree"]'
    elif section == "relation_groups":
        changed_row["status"] = "unknown"
    elif section == "notes_claims":
        changed_row["note"] = "2" * 40
    else:
        changed_row["status"] = "partial"
    package.core[section] = [changed_row] if existing else [original, changed_row]
    package.core["git_objects"].append({"object_format": "sha1", "full_oid": "2" * 40})
    changed = replace(package, package_id=str(uuid4()), digest_sha256=None)
    with pytest.raises(ExchangeError, match="IMMUTABLE_REPLAY_CONFLICT"):
        receive(b, changed, (r1, r2))
    assert rows(b, "core", "git_objects") == before


@pytest.mark.parametrize("store", ["core", "context"])
def test_advisory_coverage_details_do_not_rebind_semantic_claim(tmp_path, store):
    from contextlib import closing

    from repo_catalog.domain.p1_context import CoverageScope
    from repo_catalog.domain.p1_core import CoreCoverageScope
    from repo_catalog.domain.p1_coverage import CoverageClaim

    a, b = tmp_path / "a", tmp_path / "b"
    r1, r2, issue, _ = fixture(a)
    catalog(b)
    if store == "core":
        claim_scope = CoreCoverageScope("repository", (r1, "fixture"))
        with closing(GitCore(a / "core.sqlite3")) as core:
            core.admit_coverage_scope(claim_scope)
            core.admit_coverage(
                CoverageClaim(claim_scope, 40, "partial", '{"detail":"original"}')
            )
    else:
        from repo_catalog.domain.p1_context import CoverageClaim as ContextClaim

        claim_scope = CoverageScope.repository(r1, "fixture")
        with fixture_transaction(a, local_grants(issue, r1, r2)) as ctx:
            ctx.scope(claim_scope)
            ctx.admit_coverage(
                ContextClaim(claim_scope, 40, "partial", '{"detail":"original"}')
            )
    package = ExchangeService(a).export_package(selection=scope())
    receive(b, package, (r1, r2))
    before = rows(b, store, "coverage_claims")
    data = package.core if store == "core" else package.context
    data["coverage_claims"][0]["details_json"] = '{"detail":"other-advisory"}'
    receive(b, replace(package, package_id=str(uuid4()), digest_sha256=None), (r1, r2))
    assert rows(b, store, "coverage_claims") == before


@pytest.mark.parametrize(
    "case", ["collection_service", "collection_source", "inventory_service"]
)
def test_context_scope_cannot_rebind_provider_or_source_service(tmp_path, case):
    import json

    from repo_catalog.domain.production_context import (
        CollectionObservation,
        SourceInventory,
    )

    a, b = tmp_path / "a", tmp_path / "b"
    r1, r2, issue, _ = fixture(a)
    catalog(b)
    source, other_source, other_service = str(uuid4()), str(uuid4()), str(uuid4())
    with fixture_transaction(
        a,
        local_grants(
            issue, r1, r2, sources=(source, other_source), providers=(other_service,)
        ),
    ) as ctx:
        ctx.source(source, issue.service_instance_uuidv4)
        ctx.provider(other_service, "github")
        ctx.source(other_source, other_service)
        ctx.collection(
            CollectionObservation(
                issue,
                "comments",
                make_provenance("fixture", "scope"),
                canonical(
                    {"coverage_kind": "comments", "source_registration_uuidv4": source}
                ),
                10,
                "complete",
            )
        )
        ctx.inventory(
            SourceInventory(
                source,
                canonical(
                    {
                        "coverage_kind": "repositories",
                        "service_instance_uuidv4": issue.service_instance_uuidv4,
                    }
                ),
                10,
                "complete",
                True,
                (),
                make_provenance("fixture", "inventory"),
            )
        )
    package = ExchangeService(a).export_package(selection=scope())
    section = "source_inventories" if case == "inventory_service" else "collections"
    row = package.context[section][0]
    changed_scope = json.loads(row["scope_json"])
    if case == "collection_source":
        changed_scope["source_registration_uuidv4"] = other_source
    else:
        changed_scope["service_instance_uuidv4"] = other_service
    row["scope_json"] = canonical(changed_scope)
    with pytest.raises(ExchangeError, match="COLLECTION_SERVICE|SOURCE_SERVICE"):
        receive(b, replace(package, digest_sha256=None), (r1, r2))
    assert not rows(b, "core", "git_objects")
    assert not any(
        "adr0030-package-binding" in r[2]
        for r in rows(b, "operational", "request_continuations")
    )


@pytest.mark.parametrize("explicit_receiver", [False, True])
def test_empty_package_cannot_bypass_resolved_zero_work_ceiling(
    tmp_path, explicit_receiver
):
    from repo_catalog.domain.exchange import ExchangePackage, empty_core_section
    from repo_catalog.domain.p1_core import CoreFailure

    seed = catalog(tmp_path)
    selection = scope(max_work=0)
    package = ExchangePackage(
        str(uuid4()), None, str(uuid4()), seed, selection, core=empty_core_section()
    )
    before = rows(tmp_path, "core", "repositories")
    kwargs = {"selection": selection} if explicit_receiver else {}
    with pytest.raises(CoreFailure) as error:
        receive(tmp_path, package, **kwargs)
    assert error.value.code == "BUDGET"
    assert rows(tmp_path, "core", "repositories") == before
    assert not any(
        "adr0030-package-binding" in r[2]
        for r in rows(tmp_path, "operational", "request_continuations")
    )
