"""Independent ADR 0030 acceptance: native intake, wire, query and fresh restore.

Only the Git-object builder/store initializer are reused from earlier stages.
All Provider payloads, scenario choices and acceptance assertions belong to I5.
Every Catalog and Access configuration is synthetic and temporary.
"""

import hashlib
import shutil
from contextlib import closing
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import connect, validate
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.acquisition import GitAcquisition, ProviderAcquisition
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.acquisition import (
    GitNativeAcquisitionRequest,
    NotesAcquisitionSpec,
    ProviderIntakeBatch,
    ProviderIssueIntake,
    ProviderPullRequestIntake,
    ProviderRegistration,
    ProviderTimelineIntake,
    RepositoryRegistration,
    SourceRegistration,
    make_provenance,
)
from repo_catalog.domain.exchange import (
    ExchangeError,
    ExchangeSelectionScope,
    encode_package,
)
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
from repo_catalog.domain.production_context import (
    CollectionObservation,
    SourceInventory,
)
from repo_catalog.domain.production_query import SearchQuery
from repo_catalog.domain.recovery import BackupScope
from tests.integration.p5.conftest import build_sample_git_repo, init_catalog_stores


def prov(label):
    return make_provenance("i5-synthetic-provider", {"original": label})


def mapping(service, provider, target, label):
    return ResourceRepositoryRelation(
        ResourceKey(service, "repository", provider),
        "represents_repository",
        FieldClock("i5-original-mapping", 7),
        canonical(target),
        prov(label),
        8,
    )


def selection(repositories=(), objects=(), resources=(), sources=(), **kwargs):
    return ExchangeSelectionScope(
        repository_uuidv4s=tuple(repositories),
        object_oids=tuple(objects),
        resource_keys=tuple(resources),
        source_uuidv4s=tuple(sources),
        **kwargs,
    )


def receive(path, package, permitted, **kwargs):
    return ExchangeService(path).import_package(
        encode_package(package),
        request=RequestIdentity(
            package.sender_catalog_instance_uuidv4, package.package_id
        ),
        new_request=True,
        permitted_repository_uuidv4s=tuple(permitted),
        **kwargs,
    )


def core_repositories(path):
    with connect(path / "core.sqlite3", "core") as db:
        return {r[0] for r in db.execute("SELECT repository_uuidv4 FROM repositories")}


def context_rows(path):
    """All columns, including generated FK columns, and explicit full PKs."""
    with Context.snapshot(path) as ctx:
        tables = [
            row[0]
            for row in ctx.db.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
            )
        ]
        result = {}
        for table in tables:
            columns = ctx.db.execute(f'PRAGMA table_xinfo("{table}")').fetchall()
            result[table] = {
                "columns": tuple(tuple(row) for row in columns),
                "primary_key": tuple(
                    row[1] for row in sorted(columns, key=lambda row: row[5]) if row[5]
                ),
                "rows": sorted(
                    (tuple(row) for row in ctx.db.execute(f'SELECT * FROM "{table}"')),
                    key=repr,
                ),
            }
        assert len(result) == 19
        return result


def search(text):
    return SearchQuery(text, projection_kinds=("context_text",))


@pytest.fixture(scope="module")
def assembled_template(tmp_path_factory):
    """Two repositories share genuine Git OIDs; two Sources remain distinct."""
    source = tmp_path_factory.mktemp("i5-template") / "sender"
    r1, _ = init_catalog_stores(source)
    r2, service, s1, s2 = (str(uuid4()) for _ in range(4))
    native = source / "synthetic.git"
    oids = build_sample_git_repo(native)
    for repo in (r1, r2):
        GitAcquisition(source, operational=source).acquire_from_native(
            GitNativeSource(native),
            GitNativeAcquisitionRequest(
                repo,
                str(uuid4()),
                str(uuid4()),
                "i5-native-synthetic",
                100,
                select_oids=(oids["commit2"], oids["tree"]),
                retain_bytes=True,
                notes=NotesAcquisitionSpec(
                    discover_notes=True,
                    acquire_inventories=True,
                    target_oids=(oids["commit2"],),
                    retain_note_bodies=True,
                ),
            ),
            new_request=True,
        )
    claims = (
        mapping(service, "101", r1, "map-A"),
        mapping(service, "202", r2, "map-B"),
        mapping(service, "303", r1, "conflict-A"),
        mapping(service, "303", r2, "conflict-B"),
    )
    issue = ResourceKey(service, "issue", "501")
    pr = ResourceKey(service, "pull_request", "601")
    inventory_scope = canonical(
        {"coverage_kind": "repositories", "service_instance_uuidv4": service}
    )
    inventories = tuple(
        SourceInventory(s, inventory_scope, 110, "complete", True, (r,), prov(s))
        for s, r in ((s1, r1), (s2, r2))
    )
    collection_scope = canonical(
        {"coverage_kind": "comments", "service_instance_uuidv4": service}
    )
    empty = CollectionObservation(
        issue, "comments", prov("empty terminal"), collection_scope, 120, "complete", ()
    )
    batch = ProviderIntakeBatch(
        service,
        providers=(ProviderRegistration(service, "github"),),
        repositories=(RepositoryRegistration(r1), RepositoryRegistration(r2)),
        mapping_claims=claims,
        sources=tuple(
            SourceRegistration(s, service, associated_repositories=(r,))
            for s, r in ((s1, r1), (s2, r2))
        ),
        source_inventories=inventories,
        source_inventory_proofs=tuple(
            (
                CoverageClaim(
                    CoverageScope.source_inventory(
                        inv.source_registration_uuidv4, inventory_scope, "repositories"
                    ),
                    110,
                    "complete",
                ),
                inv,
            )
            for inv in inventories
        ),
        issues=(
            ProviderIssueIntake(
                {
                    "id": 501,
                    "title": "i5 admission needle",
                    "body": "original issue body",
                    "repository": {"id": 101},
                    "updated_at": "2026-10-19T01:00:00Z",
                },
                130,
                prov("owner before migration"),
            ),
            ProviderIssueIntake(
                {"id": 502, "repository": {"id": 303}}, 130, prov("conflicted issue")
            ),
            ProviderIssueIntake(
                {"id": 503, "repository": None}, 130, prov("explicit NULL")
            ),
            ProviderIssueIntake({"id": 504}, None, prov("owner absent")),
            ProviderIssueIntake(
                {"id": 505, "repository": {"id": 101}}, 130, prov("stable owner")
            ),
        ),
        pull_requests=(
            ProviderPullRequestIntake(
                {
                    "id": 601,
                    "title": "i5 pull request needle",
                    "body": "independent PR document",
                    "head": {"repo": {"id": 202}, "sha": oids["commit2"].full_oid},
                    "base": {"repo": {"id": 101}, "sha": oids["commit2"].full_oid},
                },
                140,
                prov("forked PR with shared oid"),
            ),
        ),
        timeline_events=(
            ProviderTimelineIntake(
                "issue",
                501,
                701,
                {
                    "id": 701,
                    "event": "transferred",
                    "from_repository": {"id": 101},
                    "to_repository": {"id": 202},
                },
                150,
                prov("two endpoint transfer"),
            ),
        ),
        collections=(empty,),
        collection_proofs=(
            (
                CoverageClaim(
                    CoverageScope.collection(
                        issue, "comments", empty.provenance_json, "comments"
                    ),
                    120,
                    "complete",
                ),
                empty,
                collection_scope,
            ),
        ),
    )
    ProviderAcquisition(source).admit_batch(batch)
    # Observing affiliation change alone must never invent a Transfer Event.
    ProviderAcquisition(source).admit_batch(
        ProviderIntakeBatch(
            service,
            issues=(
                ProviderIssueIntake(
                    {
                        "id": 501,
                        "repository": {"id": 909},
                        "updated_at": "2026-10-19T02:00:00Z",
                    },
                    160,
                    prov("new unresolved owner"),
                ),
            ),
        )
    )
    return source, service, r1, r2, s1, s2, oids, claims, issue, pr


@pytest.fixture
def assembled(tmp_path, assembled_template):
    # Copy closed, immutable synthetic stores; scenarios never share mutation.
    source = tmp_path / "sender"
    shutil.copytree(assembled_template[0], source)
    return (source, *assembled_template[1:])


@pytest.mark.parametrize("roots", ["R", "O", "C", "RO", "RC", "OC", "ROC", "empty"])
def test_independent_selection_does_not_turn_dependencies_into_permission(
    tmp_path, assembled, roots
):
    source, service, r1, r2, _, _, oids, _, _, pr = assembled
    recipient = tmp_path / "receiver"
    seed, instance = init_catalog_stores(recipient)
    selected = selection(
        repositories=(r1,) if "R" in roots else (),
        objects=(oids["commit2"],) if "O" in roots else (),
        resources=(pr,) if "C" in roots else (),
    )
    package = ExchangeService(source).export_package(selection=selected)
    receive(recipient, package, (r1, r2))
    assert core_repositories(recipient) == ({seed, r1} if "R" in roots else {seed})
    with closing(GitCore(recipient / "core.sqlite3")) as core:
        assert core.catalog_identity() == (seed, instance)
        present = core.sql(
            "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
            oids["commit2"].key,
        )
        assert bool(present) == ("O" in roots)
    with Context.snapshot(recipient) as ctx:
        resources = {
            r[0] for r in ctx.db.execute("SELECT provider_resource_id FROM resources")
        }
        assert (pr.provider_resource_id in resources) == ("C" in roots)
        assert not ctx.db.execute(
            "SELECT 1 FROM repository_context WHERE repository_uuidv4=?", (r2,)
        ).fetchone()
    assert not (recipient / "access.sqlite3").exists()
    if "C" in roots:
        view = ProductionQueryService(recipient).get_context_resource(pr)
        assert not view.matches_repository(r2)
        assert view.repository_uuidv4 == (r1 if "R" in roots else None)


def test_omitted_selection_needs_explicit_all_and_empty_overrides_all(assembled):
    source, _, r1, _, _, _, _, _, _, _ = assembled
    with pytest.raises(ExchangeError) as error:
        ExchangeService(source).export_package(selection=ExchangeSelectionScope())
    assert error.value.code == "SELECTION_REQUIRED"
    all_package = ExchangeService(source).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )
    assert all_package.context["resources"]
    empty_package = ExchangeService(source).export_package(
        selection=selection(all_selected=True)
    )
    assert not empty_package.context["resources"]
    assert not empty_package.core["git_objects"]
    assert r1 not in [
        r["repository_uuidv4"] for r in empty_package.core["repositories"]
    ]


@pytest.mark.parametrize("kind", ["withdraw", "correct", "dispute"])
def test_mapping_effect_stays_local_across_exchange_search_and_restore(
    tmp_path, assembled, kind
):
    source, service, r1, r2, _, _, _, claims, issue, _ = assembled
    replacement = mapping(service, "101", r2, "replacement")
    disposition = MappingDisposition(
        claims[0].claim_key,
        kind,
        FieldClock("i5-real-operation", 170),
        prov("actual " + kind),
        171,
        replacement.claim_key if kind == "correct" else None,
    )
    ProviderAcquisition(source).admit_batch(
        ProviderIntakeBatch(
            service,
            mapping_claims=(replacement,) if kind == "correct" else (),
            mapping_dispositions=(disposition,),
        )
    )
    receiver = tmp_path / "receiver"
    seed, _ = init_catalog_stores(receiver)
    package = ExchangeService(source).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )
    receive(receiver, package, (r1, r2))
    key = ResourceKey(service, "issue", "505")
    evidence = MappingOperationEvidence(frozenset({disposition.disposition_key}))
    ordinary = ProductionQueryService(receiver)
    qualified = ProductionQueryService(receiver, mapping_evidence=evidence)
    sender = ProductionQueryService(source, mapping_evidence=evidence)
    assert qualified.get_context_resource(key) == sender.get_context_resource(key)
    plain = ordinary.get_context_resource(key)
    checked = qualified.get_context_resource(key)
    assert (plain != checked) == (kind != "dispute")
    conflict = ordinary.get_context_resource(ResourceKey(service, "issue", "502"))
    assert conflict.repository_roles[0].state == "conflict"
    assert {
        claim
        for support in conflict.repository_roles[0].supports
        for claim in support.supporting_claims
    } == {claims[2].claim_key, claims[3].claim_key}
    assert (
        ordinary.get_context_resource(ResourceKey(service, "issue", "503"))
        .repository_roles[0]
        .state
        == "explicit_null"
    )
    assert (
        ordinary.get_context_resource(
            ResourceKey(service, "issue", "504")
        ).repository_roles
        == ()
    )
    with Context.snapshot(receiver) as ctx:
        assert ctx.mapping_dispositions(claims[0].claim_key) == (disposition,)
        assert claims[0].claim_key in {
            r.claim_key for r in ctx.repository_relations(claims[0].resource)
        }
    qualified.rebuild_search(("context_text",))
    # Reading an index built with sender-style qualification cannot grant it locally.
    expected = ordinary.search(search("owning_repository")).hits
    ordinary.rebuild_search(("context_text",))
    assert ordinary.search(search("owning_repository")).hits == expected
    migrated = ordinary.get_context_resource(issue)
    assert migrated.repository_uuidv4 is None
    assert migrated.repository_relations[0].target_repository_uuidv4 == r1
    assert not migrated.matches_repository(r1)
    assert migrated.repository_roles[0].scope.provider_repository_id == "909"
    assert issue not in {
        item.resource
        for item in ordinary.list_context_resources(repository_uuidv4=r1).items
    }
    backup, restored = tmp_path / "backup", tmp_path / "restored"
    RecoveryService().create_consistent_backup(receiver, backup)
    RecoveryService().restore_backup(backup, restored, seed)
    assert context_rows(restored) == context_rows(receiver)
    assert ProductionQueryService(restored).get_context_resource(key) == plain
    assert not (restored / "access.sqlite3").exists()


@pytest.mark.parametrize("damage", ["missing", "garbage", "stale", "text", "row_key"])
def test_received_search_is_disposable_and_rebuild_preserves_authority(
    tmp_path, assembled, damage
):
    source, _, r1, r2, _, _, _, _, _, _ = assembled
    receiver = tmp_path / "receiver"
    init_catalog_stores(receiver)
    package = ExchangeService(source).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )
    receive(receiver, package, (r1, r2))
    q = ProductionQueryService(receiver)
    authority = context_rows(receiver)
    baseline = q.search(search("repository")).hits
    q.rebuild_search(("context_text",))
    assert q.search(search("repository")).hits == baseline
    path = receiver / "search.sqlite3"
    if damage in {"missing", "garbage"}:
        path.unlink()
        if damage == "garbage":
            path.write_bytes(b"I5 synthetic broken derivative")
    else:
        with connect(path, "search") as db:
            if damage == "stale":
                db.execute("DELETE FROM search_documents")
                db.execute("UPDATE search_projections SET snapshot_token_json='{}'")
            elif damage == "text":
                db.execute(
                    "UPDATE search_documents SET searchable_text='forged repository'"
                )
            else:
                key = db.execute(
                    "SELECT projection_kind,snapshot_token_json,document_key_json FROM search_documents WHERE instr(searchable_text,'repository')>0 LIMIT 1"
                ).fetchone()
                count = db.execute("SELECT count(*) FROM search_documents").fetchone()[
                    0
                ]
                db.execute(
                    "UPDATE search_documents SET document_key_json=? WHERE projection_kind=? AND snapshot_token_json=? AND document_key_json=?",
                    ('["i5-forged-key"]', *key),
                )
                assert (
                    db.execute("SELECT count(*) FROM search_documents").fetchone()[0]
                    == count
                )
    fallback = q.search(search("repository"))
    assert fallback.backend == "authority_scan"
    assert fallback.hits == baseline
    q.rebuild_search(("context_text",))
    assert q.search(search("repository")).backend == "verified_projection_scan"
    assert q.search(search("repository")).hits == baseline
    assert context_rows(receiver) == authority
    assert not (receiver / "p1-recovery-stop.json").exists()


def test_received_paired_backup_preserves_complete_rows_keys_provenance_and_oid_refs(
    tmp_path, assembled
):
    source, service, r1, r2, s1, s2, oids, claims, _, _ = assembled
    replacement = mapping(service, "101", r2, "paired backup replacement")
    disposition = MappingDisposition(
        claims[0].claim_key,
        "correct",
        FieldClock("i5-backup-operation", 190),
        prov("paired backup correction"),
        191,
        replacement.claim_key,
    )
    ProviderAcquisition(source).admit_batch(
        ProviderIntakeBatch(
            service,
            mapping_claims=(replacement,),
            mapping_dispositions=(disposition,),
        )
    )
    receiver = tmp_path / "receiver"
    seed, _ = init_catalog_stores(receiver)
    package = ExchangeService(source).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )
    receive(receiver, package, (r1, r2))
    before = context_rows(receiver)
    for table, values in before.items():
        assert values["rows"], table  # all 19 tables contain real round-tripped rows
    assert {row[0] for row in before["source_repositories"]["rows"]} == {s1, s2}
    # Operational continuation and derivative Search deliberately exist at backup.
    ProductionQueryService(receiver).rebuild_search(("context_text",))
    (receiver / "access.sqlite3").write_bytes(
        b"i5 separate non-executable access canary"
    )
    backup, restored = tmp_path / "backup", tmp_path / "restored"
    recovery = RecoveryService()
    receipt = recovery.create_consistent_backup(receiver, backup)
    assert receipt.scope == BackupScope.PAIRED and receipt.verified_clean
    assert set(receipt.manifest.stores) == {"core", "context"}
    result = recovery.restore_backup(backup, restored, seed)
    assert result.revalidated_clean
    assert context_rows(restored) == before
    for role in ("core", "context"):
        with connect(restored / f"{role}.sqlite3", role) as db:
            validate(db, role)
            assert not db.execute("PRAGMA foreign_key_check").fetchall()
    for table in (
        "captures",
        "notes_claims",
        "notes_groups",
        "note_roles",
        "retained_notes",
    ):
        with (
            connect(receiver / "core.sqlite3", "core") as a,
            connect(restored / "core.sqlite3", "core") as b,
        ):
            assert sorted(
                (tuple(row) for row in a.execute(f'SELECT * FROM "{table}"')), key=repr
            ) == sorted(
                (tuple(row) for row in b.execute(f'SELECT * FROM "{table}"')), key=repr
            )
    with closing(GitCore(restored / "core.sqlite3")) as core:
        assert core.read_metadata(oids["commit2"])
    assert not any(
        (restored / f"{role}.sqlite3").exists()
        for role in ("operational", "search", "access")
    )
    assert core_repositories(restored) == {seed, r1, r2}
    assert all(
        b"i5 separate non-executable access canary" not in p.read_bytes()
        for p in backup.rglob("*")
        if p.is_file()
    )
    assert (
        hashlib.sha256((receiver / "access.sqlite3").read_bytes()).digest()
        == hashlib.sha256(b"i5 separate non-executable access canary").digest()
    )


def test_transfer_reports_never_mix_across_observations_or_identifier_namespaces(
    tmp_path, assembled
):
    source, service, r1, r2, _, _, _, _, _, _ = assembled
    base = {"id": 702, "event": "transferred"}
    observations = (
        ProviderTimelineIntake(
            "issue",
            501,
            702,
            {**base, "from_repository": {"id": 101}},
            180,
            prov("from-only"),
        ),
        ProviderTimelineIntake(
            "issue",
            501,
            702,
            {**base, "to_repository": {"id": 202}},
            181,
            prov("to-only"),
        ),
        ProviderTimelineIntake(
            "issue",
            501,
            703,
            {
                "id": 703,
                "event": "labeled",
                "from_repository": {"id": 101},
                "to_repository": {"id": 202},
            },
            182,
            prov("not transfer"),
        ),
        ProviderTimelineIntake(
            "issue",
            501,
            "EV_node",
            {
                "id": "EV_node",
                "__typename": "TransferredEvent",
                "fromRepository": {"id": "R_node", "databaseId": 101},
                "toRepository": None,
            },
            183,
            prov("opaque Node endpoint"),
            graphql=True,
        ),
    )
    ProviderAcquisition(source).admit_batch(
        ProviderIntakeBatch(service, timeline_events=observations)
    )
    with Context.snapshot(source) as ctx:
        original = ctx.transfer_event_reports()
    # One pre-existing two-sided event, two genuine one-sided reports, one Node report.
    assert len(original) == 4
    split = [
        r
        for r in original
        if r.event_resource
        == ResourceKey.timeline_event(ResourceKey(service, "issue", "501"), "702")
    ]
    assert {(r.from_state, r.to_state) for r in split} == {
        ("resolved", "absent"),
        ("absent", "resolved"),
    }
    assert len({r.report_key for r in split}) == 2
    node = next(
        r
        for r in original
        if r.from_provider_repository is not None
        and r.from_provider_repository.provider_resource_id != "101"
    )
    assert node.from_state == "unresolved_provider_only"
    assert node.to_state == "explicit_null"
    assert node.from_provider_repository.provider_resource_id != "101"
    receiver = tmp_path / "receiver"
    init_catalog_stores(receiver)
    package = ExchangeService(source).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )
    receive(receiver, package, (r1, r2))
    with Context.snapshot(receiver) as ctx:
        assert ctx.transfer_event_reports() == original
    restricted = tmp_path / "restricted"
    seed, _ = init_catalog_stores(restricted)
    report = receive(restricted, package, (r1,))
    assert report.omissions
    assert core_repositories(restricted) == {seed, r1}
    with Context.snapshot(restricted) as ctx:
        # The two-sided report cannot be rewritten into an apparently original one-sided report.
        assert not any(
            r.event_resource
            == ResourceKey.timeline_event(ResourceKey(service, "issue", "501"), "701")
            for r in ctx.transfer_event_reports()
        )
        assert not any(
            r.event_resource
            == ResourceKey.timeline_event(ResourceKey(service, "issue", "501"), "703")
            for r in ctx.transfer_event_reports()
        )
        assert not any(
            r.event_resource
            == ResourceKey.timeline_event(ResourceKey(service, "issue", "501"), "702")
            and r.from_state == r.to_state == "resolved"
            for r in ctx.transfer_event_reports()
        )


def test_selected_source_inventory_cannot_expand_repository_registration(
    tmp_path, assembled
):
    source, _, r1, r2, s1, s2, _, _, _, _ = assembled
    recipient = tmp_path / "receiver"
    seed, _ = init_catalog_stores(recipient)
    package = ExchangeService(source).export_package(
        selection=selection(repositories=(r1,), sources=(s1, s2))
    )
    report = receive(recipient, package, (r1, r2))
    assert report.omissions or package.selection_report["omissions"]
    assert core_repositories(recipient) == {seed, r1}
    with Context.snapshot(recipient) as ctx:
        assert not ctx.db.execute(
            "SELECT 1 FROM source_repositories WHERE repository_uuidv4=?", (r2,)
        ).fetchone()
        assert ctx.db.execute(
            "SELECT 1 FROM source_repositories WHERE source_registration_uuidv4=? AND repository_uuidv4=?",
            (s1, r1),
        ).fetchone()
        assert not ctx.db.execute(
            "SELECT 1 FROM source_coverage_proofs WHERE source_registration_uuidv4=?",
            (s2,),
        ).fetchone()
