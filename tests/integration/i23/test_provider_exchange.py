"""Actual I2 observations cross the I3 wire; receiver qualifications stay local."""

import hashlib
import json
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.github.production_intake import github_repository_id
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.acquisition import ProviderAcquisition
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.acquisition import (
    ProviderIntakeBatch,
    ProviderIssueIntake,
    ProviderPullRequestIntake,
    ProviderRegistration,
    ProviderTimelineIntake,
    RepositoryRegistration,
    SourceRegistration,
    make_provenance,
)
from repo_catalog.domain.exchange import ExchangeSelectionScope, encode_package
from repo_catalog.domain.p1_context import (
    CoverageClaim,
    CoverageScope,
    FieldClock,
    MappingDisposition,
    MappingOperationEvidence,
    ResourceKey,
    ResourceRepositoryRelation,
    canonical,
)
from repo_catalog.domain.p1_coordination import RequestIdentity
from repo_catalog.domain.production_context import SourceInventory
from repo_catalog.domain.resource_identity import encode_identity
from tests.integration.p5.conftest import init_catalog_stores
from tests.integration.p5.test_exchange import _setup_source_catalog


def provenance(label):
    return make_provenance("original-provider", {"observation": label})


def claim(service, provider, repository, label):
    return ResourceRepositoryRelation(
        ResourceKey.from_native(service, "repository", provider),
        "represents_repository",
        FieldClock("original-mapping", 10),
        canonical(repository),
        provenance(label),
        11,
    )


def scope(repositories, resources=(), sources=(), objects=()):
    return ExchangeSelectionScope(
        repository_uuidv4s=tuple(repositories),
        object_oids=tuple(objects),
        resource_keys=tuple(resources),
        source_uuidv4s=tuple(sources),
    )


def rows(path, table):
    with Context.snapshot(path) as ctx:
        return tuple(ctx.db.execute("SELECT * FROM " + table + " ORDER BY 1,2"))


def receiver(path):
    seed, instance = init_catalog_stores(
        path, stores=("core", "context", "operational")
    )
    return seed, instance


def receive(path, package, repositories):
    return ExchangeService(path).import_package(
        encode_package(package),
        request=RequestIdentity(
            package.sender_catalog_instance_uuidv4, package.package_id
        ),
        new_request=True,
        permitted_repository_uuidv4s=tuple(repositories),
    )


def producer(path):
    r1, _ = receiver(path)
    r2, service = str(uuid4()), str(uuid4())
    core = GitCore(path / "core.sqlite3")
    core.admit_repository(r2)
    core.close()
    claims = (
        claim(service, "1", r1, "A"),
        claim(service, "2", r2, "B"),
        claim(service, "3", r1, "C1"),
        claim(service, "3", r2, "C2"),
    )
    acq = ProviderAcquisition(path)
    acq.admit_batch(
        ProviderIntakeBatch(
            service,
            providers=(ProviderRegistration(service),),
            repositories=(RepositoryRegistration(r1), RepositoryRegistration(r2)),
            mapping_claims=claims,
            issues=(
                ProviderIssueIntake(
                    {
                        "id": 7,
                        "repository": {"id": 1},
                        "updated_at": "2026-10-19T01:00:00Z",
                    },
                    50,
                    provenance("old-owner"),
                ),
                ProviderIssueIntake(
                    {"id": 10, "repository": {"id": 1}}, 50, provenance("owner")
                ),
                ProviderIssueIntake(
                    {"id": 11, "repository": None}, 50, provenance("null")
                ),
                ProviderIssueIntake({"id": 12}, None, provenance("missing")),
                ProviderIssueIntake(
                    {"id": 13, "repository": {"id": 3}}, 50, provenance("conflict")
                ),
                ProviderIssueIntake(
                    {
                        "id": "I_node",
                        "databaseId": 14,
                        "repository": {"id": "R_node", "databaseId": 1},
                    },
                    50,
                    provenance("node"),
                    graphql=True,
                ),
            ),
            pull_requests=(
                ProviderPullRequestIntake(
                    {"id": 9, "base": {"repo": {"id": 1}}, "head": {"repo": {"id": 2}}},
                    50,
                    provenance("PR"),
                ),
            ),
        )
    )
    # The latest Provider owner is unresolved; older Core evidence is retained.
    acq.admit_batch(
        ProviderIntakeBatch(
            service,
            issues=(
                ProviderIssueIntake(
                    {
                        "id": 7,
                        "repository": {"id": 99},
                        "updated_at": "2026-10-19T02:00:00Z",
                    },
                    60,
                    provenance("new-owner"),
                ),
            ),
        )
    )
    return service, r1, r2, claims


def test_current_roles_namespaces_clocks_and_conflicts_across_seeds(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    service, r1, r2, claims = producer(a)
    seed, instance = receiver(b)
    keys = tuple(
        ResourceKey.from_native(service, "issue", str(i))
        for i in (7, 10, 11, 12, 13, 14)
    ) + (ResourceKey.from_native(service, "pull_request", "9"),)
    package = ExchangeService(a).export_package(selection=scope((r1, r2), keys))
    receive(b, package, (r1, r2))
    core = GitCore(b / "core.sqlite3")
    assert core.catalog_identity() == (seed, instance)
    assert {r[0] for r in core.sql("SELECT repository_uuidv4 FROM repositories")} == {
        seed,
        r1,
        r2,
    }
    core.close()
    with Context.snapshot(a) as sender, Context.snapshot(b) as ctx:
        for key in keys:
            assert ctx.provider_repository_roles(
                key
            ) == sender.provider_repository_roles(key)
        (current,) = ctx.provider_repository_roles(keys[0])
        assert current.state == "unresolved_provider_only"
        assert current.scope.provider_repository_id == encode_identity("99")
        assert current.scope.observed_at_us == 60
        assert current.provenance_json == provenance("new-owner")
        assert not current.resolved_candidates
        assert ctx.repository_relations(keys[0])[0].target_repository_uuidv4 == r1
        assert ctx.provider_repository_roles(keys[2])[0].state == "explicit_null"
        assert not ctx.provider_repository_roles(keys[3])
        (conflict,) = ctx.provider_repository_roles(keys[4])
        assert conflict.state == "conflict"
        assert {
            k for support in conflict.supports for k in support.supporting_claims
        } == {claims[2].claim_key, claims[3].claim_key}
        (node,) = ctx.provider_repository_roles(keys[5])
        assert node.scope.provider_repository_id == github_repository_id(
            {"id": "R_node", "databaseId": 1}, graphql=True
        )
        assert (
            node.state == "unresolved_provider_only"
        )  # decimal 1 cannot supply Node support
        roles = {
            q.scope.relation_kind: q for q in ctx.provider_repository_roles(keys[6])
        }
        for role, mapping in (
            ("base_repository", claims[0]),
            ("head_repository", claims[1]),
        ):
            assert roles[role].supports[0].supporting_claims == (mapping.claim_key,)
            assert roles[role].scope.observed_at_us == 50
        assert not ctx.repository_relations(keys[6], relation_kind="owning_repository")
    assert not (b / "access.sqlite3").exists()


@pytest.mark.parametrize("kind", ["withdraw", "correct", "dispute"])
def test_received_dispositions_need_receiver_evidence_and_preserve_keys(tmp_path, kind):
    a, b = tmp_path / "a", tmp_path / "b"
    service, r1, r2, claims = producer(a)
    replacement = claim(service, "1", r2, "replacement")
    disposition = MappingDisposition(
        claims[0].claim_key,
        kind,
        FieldClock("operation", 20),
        provenance(kind),
        21,
        replacement.claim_key if kind == "correct" else None,
    )
    ProviderAcquisition(a).admit_batch(
        ProviderIntakeBatch(
            service,
            mapping_claims=(replacement,) if kind == "correct" else (),
            mapping_dispositions=(disposition,),
        )
    )
    key = ResourceKey.from_native(service, "issue", "10")
    evidence = MappingOperationEvidence(frozenset({disposition.disposition_key}))
    receiver(b)
    package = ExchangeService(a).export_package(selection=scope((r1, r2), (key,)))
    receive(b, package, (r1, r2))
    before = rows(b, "repository_mapping_dispositions")
    with Context.snapshot(a) as sender, Context.snapshot(b) as ctx:
        assert ctx.mapping_dispositions(claims[0].claim_key) == (disposition,)
        ordinary = ctx.provider_repository_roles(key)
        qualified = ctx.provider_repository_roles(key, evidence=evidence)
        assert ordinary == sender.provider_repository_roles(key)
        assert qualified == sender.provider_repository_roles(key, evidence=evidence)
        assert (
            ordinary[0].mapping.unconfirmed_dispositions
            or ordinary[0].mapping.disputed_dispositions
        )
        assert (ordinary != qualified) == (kind != "dispute")
        assert claims[0].claim_key in tuple(
            r.claim_key for r in ctx.repository_relations(claims[0].resource)
        )
    assert rows(b, "repository_mapping_dispositions") == before


@pytest.mark.parametrize(
    "endpoints,states",
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
            {"from_repository": {"id": 98}, "to_repository": {"id": 99}},
            ("unresolved_provider_only", "unresolved_provider_only"),
        ),
    ],
)
def test_genuine_transfer_event_report_is_preserved_whole(tmp_path, endpoints, states):
    a, b = tmp_path / "a", tmp_path / "b"
    service, r1, r2, _ = producer(a)
    ProviderAcquisition(a).admit_batch(
        ProviderIntakeBatch(
            service,
            timeline_events=(
                ProviderTimelineIntake(
                    "issue",
                    7,
                    100,
                    {
                        "id": 100,
                        "event": "transferred",
                        "created_at": "2026-10-19T01:00:00Z",
                        **endpoints,
                    },
                    70,
                    provenance("transfer"),
                ),
            ),
        )
    )
    with Context.snapshot(a) as ctx:
        (original,) = ctx.transfer_event_reports()
    receiver(b)
    package = ExchangeService(a).export_package(
        selection=scope((r1, r2), (original.event_resource,))
    )
    receive(b, package, (r1, r2))
    with Context.snapshot(b) as ctx:
        assert ctx.transfer_event_reports() == (original,)
        (received,) = ctx.transfer_event_reports()
        assert received.report_key == original.report_key
        assert (received.from_state, received.to_state) == states
        assert received.observed_at_us == 70
        assert received.event_type == "transferred"
    if states == ("resolved", "resolved"):
        c = tmp_path / "c"
        seed, _ = receiver(c)
        report = receive(c, package, (r1,))
        assert report.omissions
        with Context.snapshot(c) as ctx:
            assert (
                not ctx.transfer_event_reports()
            )  # never invent an original one-sided report
            assert not ctx.db.execute(
                "SELECT 1 FROM repository_context WHERE repository_uuidv4=?", (r2,)
            ).fetchone()
        core = GitCore(c / "core.sqlite3")
        assert {
            r[0] for r in core.sql("SELECT repository_uuidv4 FROM repositories")
        } == {seed, r1}
        core.close()


def test_i2_source_coverage_and_native_capture_notes_survive_i3(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    r1, source = str(uuid4()), str(uuid4())
    oids = _setup_source_catalog(a, r1)
    with Context.snapshot(a) as ctx:
        service = ctx.db.execute(
            "SELECT service_instance_uuidv4 FROM providers"
        ).fetchone()[0]
    original_scope = canonical(
        {"coverage_kind": "repositories", "service_instance_uuidv4": service}
    )
    inventory = SourceInventory(
        source, original_scope, 80, "complete", True, (r1,), provenance("inventory")
    )
    coverage = CoverageClaim(
        CoverageScope.source_inventory(source, original_scope, "repositories"),
        80,
        "complete",
    )
    ProviderAcquisition(a).admit_batch(
        ProviderIntakeBatch(
            service,
            sources=(
                SourceRegistration(source, service, associated_repositories=(r1,)),
            ),
            source_inventories=(inventory,),
            source_inventory_proofs=((coverage, inventory),),
        )
    )
    seed, instance = receiver(b)
    # All domain objects really are intended in this preservation test.
    package = ExchangeService(a).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )
    assert package.core["retained_notes"] and package.core["captures"]
    report = receive(b, package, (r1,))
    assert report.linked_core_references >= 2
    for table in (
        "source_inventory_evidence",
        "source_coverage_proofs",
        "coverage_claims",
        "core_references",
        "resource_relations",
    ):
        assert rows(a, table) == rows(b, table)
    ca, cb = GitCore(a / "core.sqlite3"), GitCore(b / "core.sqlite3")
    try:
        assert cb.catalog_identity() == (seed, instance)
        assert cb.read_metadata(oids["commit2"]) == ca.read_metadata(oids["commit2"])
    finally:
        ca.close()
        cb.close()
    da, db = connect(a / "core.sqlite3", "core"), connect(b / "core.sqlite3", "core")
    try:
        for table in (
            "captures",
            "notes_claims",
            "notes_groups",
            "note_roles",
            "retained_notes",
        ):
            assert (
                da.execute("SELECT * FROM " + table).fetchall()
                == db.execute("SELECT * FROM " + table).fetchall()
            )
    finally:
        da.close()
        db.close()
    onward = ExchangeService(b).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )
    for section in ("note_roles", "retained_notes"):
        assert onward.core[section] == package.core[section]
    assert not (a / "access.sqlite3").exists() and not (b / "access.sqlite3").exists()
    assert "credential" not in encode_package(
        package
    ) and "approval" not in encode_package(package)


def test_domain_exchange_neither_transports_nor_changes_real_access_grants(tmp_path):
    from repo_catalog.adapters.sqlite.access_connections import AccessConnections
    from repo_catalog.adapters.sqlite.access_schema import initialize
    from repo_catalog.domain.access_connections import (
        AssignmentKey,
        ConnectionConfiguration,
        LocatorConnection,
        RepositoryBinding,
        ScopeExecutionContext,
    )
    from repo_catalog.domain.access_registry import (
        AccessScope,
        ScopeLocatorRegistration,
    )

    a, b = tmp_path / "a", tmp_path / "b"
    service, r1, r2, _ = producer(a)
    receiver(b)
    snapshots = []
    for path in (a, b):
        access = path / "access.sqlite3"
        initialize(access)
        scope_id = str(uuid4())
        key = AssignmentKey(
            scope_id, "https://git.example.test/i23.git", "private-i23-profile"
        )
        with AccessConnections(access, writable=True) as store:
            store.register_scope(AccessScope(scope_id, "i23-local"))
            route = ScopeLocatorRegistration(scope_id, 1, "file:///i23-private-route")
            store.register_locator(route)
            store.set_locator_enabled(route, True)
            store.configure_scope(
                ScopeExecutionContext(
                    scope_id,
                    canonical(
                        {
                            "version": 1,
                            "executor_kind": "local",
                            "executor_ref": "private-i23-executor",
                            "identity_view": "owner",
                            "path_dialect": "posix",
                        }
                    ),
                    True,
                )
            )
            store.bind_repository(
                RepositoryBinding(scope_id, key.locator_text, r1, True)
            )
            store.configure_connection(
                ConnectionConfiguration(
                    scope_id,
                    key.configuration_name,
                    canonical(
                        {
                            "version": 1,
                            "transport": "https",
                            "credential_ref": {
                                "kind": "credential-helper",
                                "name": "private-i23-credential",
                            },
                        }
                    ),
                    True,
                )
            )
            store.assign_connection(LocatorConnection(key, True))
            grant = store.record_local_approval(store.review_plan(r1, scope_id), 20)
        snapshots.append((access.read_bytes(), scope_id, key, grant))
    package = ExchangeService(a).export_package(
        selection=scope((r1, r2), (ResourceKey.from_native(service, "issue", "10"),))
    )
    wire = encode_package(package)
    assert all(
        canary not in wire
        for canary in ("private-i23", "credential_ref", "local_access_grants")
    )
    receive(b, package, (r1, r2))
    for path, (original, scope_id, key, grant) in zip((a, b), snapshots, strict=True):
        assert (path / "access.sqlite3").read_bytes() == original
        with AccessConnections(path / "access.sqlite3") as store:
            assert store.current_grant(r1, scope_id, assignment=key) == grant


@pytest.mark.parametrize("mutation", ["bad_role", "wrong_observation", "wrong_members"])
@pytest.mark.parametrize("hidden", [False, True])
def test_invalid_i2_provider_scope_rejected_before_binding_and_core_commit(
    tmp_path, mutation, hidden
):
    """Independent-review counterexamples: generic relation construction is insufficient."""
    a, b = tmp_path / "a", tmp_path / "b"
    _, r1, r2, _ = producer(a)
    receiver(b)
    package = ExchangeService(a).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )
    row = next(
        r
        for r in package.context["resource_relations"]
        if r["relation_kind"] == "provider_repository_roles"
    )
    original_scope = json.loads(row["scope_json"])
    if mutation == "bad_role":
        original_scope["repository_roles"] = {
            "transfer_to_repository": next(
                iter(original_scope["repository_roles"].values())
            )
        }
        message = "Transfer roles require"
    elif mutation == "wrong_observation":
        for entry in original_scope["repository_roles"].values():
            entry["observed_at_us"] = 999
        message = "original observation mismatch"
    else:
        row["members_json"] = "[]"
        message = "members do not match"
    row["scope_json"] = canonical(original_scope)
    # Public v4 encoder recomputes a valid checksum; this exercises typed preflight.
    package = replace(package, digest_sha256=None)
    core = GitCore(b / "core.sqlite3")
    before = core.sql("SELECT repository_uuidv4 FROM repositories")
    core.close()
    with pytest.raises(ValueError, match=message):
        ExchangeService(b).import_package(
            package,
            new_request=True,
            permitted_repository_uuidv4s=(r1, r2),
            selection=ExchangeSelectionScope(
                repository_uuidv4s=(),
                object_oids=(),
                resource_keys=(),
                source_uuidv4s=(),
                include_context=False,
            )
            if hidden
            else None,
        )
    core = GitCore(b / "core.sqlite3")
    assert core.sql("SELECT repository_uuidv4 FROM repositories") == before
    core.close()
    assert not rows(b, "resources")
    db = connect(b / "operational.sqlite3", "operational")
    try:
        assert not any(
            "adr0030-package-binding" in row[0]
            for row in db.execute(
                "SELECT continuation_scope_json FROM request_continuations"
            )
        )
    finally:
        db.close()
    assert not (b / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "reference_empty",
        "reference_bad_oid",
        "reference_empty_role",
        "provider_kind_empty",
        "provider_kind_integer",
        "relation_kind_integer",
    ],
)
@pytest.mark.parametrize("hidden", [False, True])
def test_writer_semantic_subtypes_cannot_commit_or_coerce_before_preflight(
    tmp_path, mutation, hidden
):
    """Additional exact-head reviewer counterexamples, with valid v4 checksums."""
    a, b = tmp_path / "a", tmp_path / "b"
    _, r1, r2, _ = producer(a)
    seed, _ = receiver(b)
    package = ExchangeService(a).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )
    if mutation.startswith("reference_"):
        package.context["field_candidates"].append(
            {
                **package.context["resources"][0],
                "field_name": "reported_core_reference:"
                if mutation == "reference_empty_role"
                else "reported_core_reference:head",
                "value_json": "[]"
                if mutation == "reference_empty"
                else canonical(
                    ["sha1", "not-a-valid-oid"]
                    if mutation == "reference_bad_oid"
                    else ["sha1", "1" * 40]
                ),
                "clock_domain": "provider",
                "clock_ts_us": 10,
                "provenance_json": provenance("reference"),
                "observed_at_us": 11,
            }
        )
    elif mutation.startswith("provider_kind_"):
        package.context["providers"][0]["provider_kind"] = (
            "" if mutation == "provider_kind_empty" else 7
        )
    else:
        package.context["resource_relations"].append(
            {
                **package.context["resources"][0],
                "relation_kind": 7,
                "members_json": "[]",
                "provenance_json": provenance("relation"),
                "scope_json": "{}",
                "observed_at_us": 11,
            }
        )
    package = package.to_dict()
    package["digest_sha256"] = hashlib.sha256(
        canonical(
            {key: value for key, value in package.items() if key != "digest_sha256"}
        ).encode()
    ).hexdigest()
    with pytest.raises(ValueError):
        ExchangeService(b).import_package(
            package,
            new_request=True,
            permitted_repository_uuidv4s=(r1, r2),
            selection=ExchangeSelectionScope(
                repository_uuidv4s=(),
                object_oids=(),
                resource_keys=(),
                source_uuidv4s=(),
                include_context=False,
            )
            if hidden
            else None,
        )
    core = GitCore(b / "core.sqlite3")
    assert {r[0] for r in core.sql("SELECT repository_uuidv4 FROM repositories")} == {
        seed
    }
    core.close()
    assert not rows(b, "providers") and not rows(b, "resources")
    db = connect(b / "operational.sqlite3", "operational")
    try:
        assert not any(
            "adr0030-package-binding" in row[0]
            for row in db.execute(
                "SELECT continuation_scope_json FROM request_continuations"
            )
        )
    finally:
        db.close()
    assert not (b / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize(
    "case", ["genuine_collection", "absent_collection", "existing_collection"]
)
def test_collection_coverage_uses_exact_owner_and_admission_order(tmp_path, case):
    from repo_catalog.domain.production_context import CollectionObservation

    a, b = tmp_path / "a", tmp_path / "b"
    service, r1, r2, _ = producer(a)
    receiver(b)
    key = ResourceKey.from_native(service, "issue", "10")
    coverage_scope = CoverageScope.collection(
        key, "comments", provenance("collection"), "comments"
    )
    collection = CollectionObservation(
        key, "comments", provenance("collection"), "{}", 80, "complete", ()
    )
    if case != "absent_collection":
        with Context.transaction(a) as ctx:
            ctx.collection(collection)
            ctx.scope(coverage_scope)
            ctx.admit_coverage(CoverageClaim(coverage_scope, 80, "partial"))
    package = ExchangeService(a).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )
    if case == "absent_collection":
        package.context["coverage_scopes"].append(
            {
                "owner_kind": coverage_scope.owner_kind,
                "owner_coordinates_json": coverage_scope.encoded,
            }
        )
        package.context["coverage_claims"].append(
            {
                "owner_kind": coverage_scope.owner_kind,
                "owner_coordinates_json": coverage_scope.encoded,
                "observed_at_us": 80,
                "coverage_state": "partial",
                "details_json": None,
            }
        )
    if case == "existing_collection":
        ProviderAcquisition(b).admit_batch(
            ProviderIntakeBatch(
                service,
                providers=(ProviderRegistration(service),),
                issues=(
                    ProviderIssueIntake({"id": 10}, 40, provenance("receiver-parent")),
                ),
            )
        )
        with Context.transaction(b) as ctx:
            ctx.collection(collection)
        package.context["collections"] = []
    package = replace(package, digest_sha256=None)
    report = receive(b, package, (r1, r2))
    with Context.snapshot(b) as ctx:
        actual = ctx.db.execute(
            "SELECT owner_kind,owner_coordinates_json FROM coverage_scopes WHERE owner_kind='collection'"
        ).fetchall()
        if case == "absent_collection":
            assert actual == [] and report.omissions
            assert ctx.db.execute(
                "SELECT 1 FROM resources WHERE resource_kind='issue'"
            ).fetchone()
        else:
            assert actual == [(coverage_scope.owner_kind, coverage_scope.encoded)]
            assert (
                ctx.db.execute(
                    "SELECT coverage_state FROM coverage_claims WHERE owner_kind='collection'"
                ).fetchone()[0]
                == "partial"
            )
    assert not (b / "p1-recovery-stop.json").exists()


def test_source_coverage_permission_cut_keeps_independent_i2_facts(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    service, r1, r2, _ = producer(a)
    seed, _ = receiver(b)
    source = str(uuid4())
    ProviderAcquisition(a).admit_batch(
        ProviderIntakeBatch(
            service,
            sources=(
                SourceRegistration(source, service, associated_repositories=(r1, r2)),
            ),
        )
    )
    coverage_scope = CoverageScope.source(source, r2, "commits")
    with Context.transaction(a) as ctx:
        ctx.scope(coverage_scope)
        ctx.admit_coverage(CoverageClaim(coverage_scope, 80, "partial"))
    package = ExchangeService(a).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )
    report = receive(b, package, (r1,))
    assert any(item["section"] == "coverage_scopes" for item in report.omissions)
    with Context.snapshot(b) as ctx:
        assert ctx.source_repositories(source) == (r1,)
        assert not ctx.db.execute(
            "SELECT 1 FROM coverage_scopes WHERE owner_kind='source'"
        ).fetchone()
        assert ctx.db.execute(
            "SELECT 1 FROM resources WHERE resource_kind='issue'"
        ).fetchone()
        assert not ctx.db.execute(
            "SELECT 1 FROM repository_context WHERE repository_uuidv4=?", (r2,)
        ).fetchone()
    core = GitCore(b / "core.sqlite3")
    assert {r[0] for r in core.sql("SELECT repository_uuidv4 FROM repositories")} == {
        seed,
        r1,
    }
    core.close()
    assert not (b / "p1-recovery-stop.json").exists()


def test_existing_receiver_source_pair_can_support_partial_package_coverage(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    service, r1, r2, _ = producer(a)
    receiver(b)
    source = str(uuid4())
    source_registration = SourceRegistration(
        source, service, associated_repositories=(r1,)
    )
    ProviderAcquisition(a).admit_batch(
        ProviderIntakeBatch(service, sources=(source_registration,))
    )
    ProviderAcquisition(b).admit_batch(
        ProviderIntakeBatch(
            service,
            providers=(ProviderRegistration(service),),
            repositories=(RepositoryRegistration(r1),),
            sources=(source_registration,),
        )
    )
    coverage_scope = CoverageScope.source(source, r1, "commits")
    with Context.transaction(a) as ctx:
        ctx.scope(coverage_scope)
        ctx.admit_coverage(CoverageClaim(coverage_scope, 80, "partial"))
    package = ExchangeService(a).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )
    package.context["source_repositories"] = []
    package = replace(package, digest_sha256=None)
    receive(b, package, (r1, r2))
    with Context.snapshot(b) as ctx:
        assert ctx.source_repositories(source) == (r1,)
        assert (
            ctx.db.execute(
                "SELECT coverage_state FROM coverage_claims WHERE owner_kind='source'"
            ).fetchone()[0]
            == "partial"
        )
    assert not (b / "p1-recovery-stop.json").exists()
