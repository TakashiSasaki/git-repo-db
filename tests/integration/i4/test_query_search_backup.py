"""I4 adversarial projections and paired domain preservation on actual I2 data."""

import hashlib
import json

import pytest

from repo_catalog.adapters.sqlite.p1_coordination import SnapshotReadLimits
from repo_catalog.adapters.sqlite.p1_schema import connect, validate
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.acquisition import ProviderAcquisition
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.acquisition import ProviderIntakeBatch, ProviderTimelineIntake
from repo_catalog.domain.p1_context import (
    FieldClock,
    MappingDisposition,
    MappingOperationEvidence,
    ProviderRepositoryRoleScope,
    ProviderRepositoryScope,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.p1_core import CoreFailure
from repo_catalog.domain.production_context import ResourceRelation
from repo_catalog.domain.production_query import PageRequest, QueryError, SearchQuery
from repo_catalog.domain.recovery import (
    BackupScope,
    CorruptionDetectedError,
    RestoreValidationError,
)
from tests.integration.i23.test_provider_exchange import claim, producer, provenance


def query(text, **kwargs):
    return SearchQuery(text, projection_kinds=("context_text",), **kwargs)


def test_current_provider_roles_never_fall_back_to_old_core_target(tmp_path):
    service, r1, r2, claims = producer(tmp_path)
    q = ProductionQueryService(tmp_path)
    key = ResourceKey(service, "issue", "7")
    view = q.get_context_resource(key)
    assert view.repository_uuidv4 is None
    assert view.repository_relations[0].target_repository_uuidv4 == r1
    (current,) = view.repository_roles
    assert current.state == "unresolved_provider_only"
    assert current.scope.provider_repository_id == "99"
    assert current.scope.observed_at_us == 60
    assert current.provenance_json == provenance("new-owner")
    assert not view.matches_repository(r1)
    assert key not in {
        v.resource for v in q.list_context_resources(repository_uuidv4=r1).items
    }
    assert key not in {
        v.resource for v in q.list_paired_resources(repository_uuidv4=r1).items
    }
    pr = q.get_context_resource(ResourceKey(service, "pull_request", "9"))
    assert {
        v.resource.provider_resource_id
        for v in q.list_context_resources(
            repository_uuidv4=r1, resource_kind="repository"
        ).items
    } == {"1", "3"}
    assert pr.repository_uuidv4 == r1
    assert pr.matches_repository(r1) and pr.matches_repository(r2)
    assert {r.scope.relation_kind for r in pr.repository_roles} == {
        "base_repository",
        "head_repository",
    }
    assert {c for r in pr.repository_roles for c in r.mapping.active_claims} == {
        claims[0].claim_key,
        claims[1].claim_key,
    }
    assert (
        q.get_context_resource(ResourceKey(service, "issue", "11"))
        .repository_roles[0]
        .state
        == "explicit_null"
    )
    assert (
        q.get_context_resource(ResourceKey(service, "issue", "12")).repository_roles
        == ()
    )
    conflict = q.get_context_resource(ResourceKey(service, "issue", "13"))
    assert conflict.repository_uuidv4 is None
    assert conflict.repository_roles[0].state == "conflict"
    assert conflict.matches_repository(r1) and conflict.matches_repository(r2)
    # Serialization contains original keys/clock/provenance, never a retired field shim.
    data = conflict.to_dict()
    assert "repository_candidates" not in data
    assert "repository_uuidv4" not in data["fields"]
    assert {
        c["provenance_json"]
        for c in data["repository_roles"][0]["mapping"]["active_claims"]
    } == {claims[2].provenance_json, claims[3].provenance_json}


@pytest.mark.parametrize("same_provenance", [False, True])
@pytest.mark.parametrize(
    "domain,at_us", [("provider", 100), ("different", 100), ("provider", None)]
)
def test_equal_incomparable_and_unknown_clocks_keep_all_provider_candidates(
    tmp_path, domain, at_us, same_provenance
):
    service, r1, r2, _ = producer(tmp_path)
    key = ResourceKey(service, "issue", "80")
    with Context.transaction(tmp_path) as ctx:
        ctx.resource(key)
        for provider_id, clock, label in (
            ("1", FieldClock("provider", 100), "first"),
            ("2", FieldClock(domain, at_us), "second"),
        ):
            provider = ResourceKey(service, "repository", provider_id)
            scope = ProviderRepositoryScope(
                {
                    "owning_repository": ProviderRepositoryRoleScope(
                        "owning_repository",
                        clock,
                        "unresolved_provider_only",
                        provider_id,
                        observed_at_us=101,
                    )
                }
            )
            ctx.relation(
                ResourceRelation(
                    key,
                    "provider_repository_roles",
                    (provider,),
                    provenance("same" if same_provenance else label),
                    scope.encoded,
                    101,
                )
            )
    q = ProductionQueryService(tmp_path)
    view = q.get_context_resource(key)
    assert len(view.repository_roles) == 2
    assert view.repository_uuidv4 is None
    assert view.matches_repository(r1) and view.matches_repository(r2)
    q.rebuild_search(("context_text",))
    hits = q.search(query("owning_repository")).hits
    own = [
        h
        for h in hits
        if h.authoritative_summary.get("kind") == "current_provider_repository_role"
        and h.authoritative_summary["resource"] == list(key.coordinates())
    ]
    assert len(own) == 2


@pytest.mark.parametrize("kind", ["withdraw", "correct", "dispute"])
def test_dispositions_are_reports_and_qualification_is_per_operation(tmp_path, kind):
    service, r1, r2, claims = producer(tmp_path)
    replacement = claim(service, "1", r2, "replacement")
    disp = MappingDisposition(
        claims[0].claim_key,
        kind,
        FieldClock("operation", 20),
        provenance(kind),
        21,
        replacement.claim_key if kind == "correct" else None,
    )
    ProviderAcquisition(tmp_path).admit_batch(
        ProviderIntakeBatch(
            service,
            mapping_claims=(replacement,) if kind == "correct" else (),
            mapping_dispositions=(disp,),
        )
    )
    plain = ProductionQueryService(tmp_path)
    evidence = MappingOperationEvidence(frozenset({disp.disposition_key}))
    qualified = ProductionQueryService(tmp_path, mapping_evidence=evidence)
    key = ResourceKey(service, "issue", "10")
    before = plain.get_context_resource(key)
    after = qualified.get_context_resource(key)
    assert (
        before.repository_roles[0].mapping.unconfirmed_dispositions
        or before.repository_roles[0].mapping.disputed_dispositions
    )
    assert (before.repository_roles != after.repository_roles) == (kind != "dispute")
    if kind == "withdraw":
        assert not after.matches_repository(r1)
    if kind == "correct":
        assert after.repository_uuidv4 == r2
    # Derived text produced under one qualification cannot override another read.
    plain.rebuild_search(("context_text",))
    expected = qualified.search(query("owning_repository"))
    qualified.rebuild_search(("context_text",))
    rebuilt = qualified.search(query("owning_repository"))
    assert rebuilt.backend == "verified_projection_scan"
    assert rebuilt.hits == expected.hits
    assert before == plain.get_context_resource(key)
    # Cursor filters bind transient evidence as well as the authoritative snapshot.
    page = plain.list_context_resources(PageRequest(limit=1), resource_kind="issue")
    with pytest.raises(QueryError) as error:
        qualified.list_context_resources(
            PageRequest(limit=1, cursor=page.next_cursor), resource_kind="issue"
        )
    assert error.value.code == "INVALID_CURSOR"


@pytest.mark.parametrize("damage", ["missing", "stale", "text", "delete", "garbage"])
def test_search_rebuild_fallback_and_current_historical_summary(tmp_path, damage):
    service, r1, _, _ = producer(tmp_path)
    q = ProductionQueryService(tmp_path)
    q.rebuild_search(("context_text",))
    before = q.search(query("repository"))
    assert before.backend == "verified_projection_scan"
    old = [
        h
        for h in before.hits
        if h.authoritative_summary.get("kind") == "stored_core_target_relation"
    ]
    assert old
    current = q.search(query("99"))
    assert any(
        h.authoritative_summary["state"] == "unresolved_provider_only"
        for h in current.hits
        if h.authoritative_summary.get("kind") == "current_provider_repository_role"
    )
    path = tmp_path / "search.sqlite3"
    if damage in ("missing", "garbage"):
        path.unlink()
        if damage == "garbage":
            path.write_bytes(b"invalid sqlite")
    else:
        with connect(path, "search") as db:
            if damage == "stale":
                db.execute("DELETE FROM search_documents")
                db.execute("UPDATE search_projections SET snapshot_token_json='{}'")
            elif damage == "text":
                db.execute(
                    "UPDATE search_documents SET searchable_text='fabricated repository authority'"
                )
            else:
                db.execute("DELETE FROM search_documents")
    fallback = q.search(query("repository"))
    assert fallback.backend == "authority_scan"
    assert fallback.hits == before.hits
    assert not (tmp_path / "p1-recovery-stop.json").exists()
    q.rebuild_search(("context_text",))
    assert q.search(query("repository")).hits == before.hits
    assert q.search(query("repository")).backend == "verified_projection_scan"
    # No retained historical edge revives current membership.
    assert not q.get_context_resource(
        ResourceKey(service, "issue", "7")
    ).matches_repository(r1)


def test_query_search_pagination_snapshot_budget_and_stop(tmp_path):
    service, _, _, _ = producer(tmp_path)
    q = ProductionQueryService(tmp_path)
    q.rebuild_search(("context_text",))
    full = q.search(query("repository"))
    items, cursor = [], None
    while True:
        page = q.search(query("repository", limit=2, cursor=cursor))
        items.extend(page.hits)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert tuple(items) == full.hits
    first = q.search(query("repository", limit=1))
    with q.open_snapshot() as snap:
        key = ResourceKey(service, "issue", "10")
        before = q._context_resource_in_snapshot(snap.context, key)
        with Context.transaction(tmp_path) as ctx:
            ctx.resource(ResourceKey(service, "issue", "1000"))
        assert q._context_resource_in_snapshot(snap.context, key) == before
    with pytest.raises(QueryError) as error:
        q.search(query("repository", cursor=first.next_cursor))
    assert error.value.code == "SNAPSHOT_MISMATCH"
    bounded = ProductionQueryService(
        tmp_path, read_limits=SnapshotReadLimits(max_sql_vm_steps=1)
    )
    with pytest.raises(QueryError) as error:
        bounded.search(query("repository"))
    assert error.value.code == "QUERY_BUDGET"
    assert not (tmp_path / "p1-recovery-stop.json").exists()
    (tmp_path / "p1-recovery-stop.json").write_text("{}")
    for operation in (
        lambda: q.get_context_resource(key),
        lambda: q.search(query("repository")),
        q.rebuild_search,
    ):
        with pytest.raises(CoreFailure) as error:
            operation()
        assert error.value.code == "RECOVERY_STOP"
    with pytest.raises(Exception):
        RecoveryService().create_consistent_backup(
            tmp_path, tmp_path.parent / "stopped-backup"
        )


def all_context_rows(path):
    with Context.snapshot(path) as ctx:
        tables = [
            r[0]
            for r in ctx.db.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
            )
        ]
        return {
            table: sorted(
                ctx.db.execute('SELECT * FROM "' + table + '"').fetchall(), key=repr
            )
            for table in tables
        }


def test_paired_restore_preserves_all_keys_dependencies_and_excludes_other_stores(
    tmp_path,
):
    source, backup, restored = (tmp_path / n for n in ("source", "backup", "restored"))
    service, r1, r2, claims = producer(source)
    disp = MappingDisposition(
        claims[0].claim_key,
        "correct",
        FieldClock("operation", 20),
        provenance("correction"),
        21,
        claim(service, "1", r2, "replacement").claim_key,
    )
    acq = ProviderAcquisition(source)
    acq.admit_batch(
        ProviderIntakeBatch(
            service,
            mapping_claims=(claim(service, "1", r2, "replacement"),),
            mapping_dispositions=(disp,),
            timeline_events=(
                ProviderTimelineIntake(
                    "issue",
                    7,
                    100,
                    {
                        "id": 100,
                        "event": "transferred",
                        "from_repository": {"id": 1},
                        "to_repository": {"id": 2},
                    },
                    70,
                    provenance("transfer"),
                ),
            ),
        )
    )
    # Add real Source/Coverage/text/notes via the existing paired fixture in a
    # separate regression below; here every current table is compared in full.
    ProductionQueryService(source).rebuild_search(("context_text",))
    (source / "access.sqlite3").write_bytes(b"independent access configuration canary")
    before = all_context_rows(source)
    recovery = RecoveryService()
    receipt = recovery.create_consistent_backup(source, backup)
    assert receipt.verified_clean and receipt.scope == BackupScope.PAIRED
    assert set(receipt.manifest.stores) == {"core", "context"}
    assert {p.name for p in (backup / "stores").iterdir()} == {
        "core.sqlite3",
        "context.sqlite3",
    }
    result = recovery.restore_backup(backup, restored, r1)
    assert result.revalidated_clean
    assert all_context_rows(restored) == before
    assert not any(
        (restored / (name + ".sqlite3")).exists()
        for name in ("operational", "search", "access")
    )
    for role in ("core", "context"):
        with connect(restored / f"{role}.sqlite3", role) as db:
            validate(db, role)
            assert not db.execute("PRAGMA foreign_key_check").fetchall()
    with Context.snapshot(source) as original, Context.snapshot(restored) as copy:
        assert copy.transfer_event_reports() == original.transfer_event_reports()
        assert copy.mapping_dispositions(claims[0].claim_key) == (disp,)
    q = ProductionQueryService(restored)
    assert (
        q.get_context_resource(ResourceKey(service, "issue", "10"))
        .repository_roles[0]
        .state
        == "conflict"
    )
    q.rebuild_search(("context_text",))
    assert q.search(query("repository")).backend == "verified_projection_scan"


def test_paired_restore_coverage_source_text_and_git_only_boundary(tmp_path):
    from tests.integration.p6.conftest import REPOSITORY, populate_rich_catalog

    source, backup, restored = (tmp_path / n for n in ("source", "backup", "restored"))
    fixtures = populate_rich_catalog(source)
    before = all_context_rows(source)
    assert (
        before["coverage_claims"]
        and before["source_repositories"]
        and before["text_bodies"]
    )
    r = RecoveryService()
    r.create_consistent_backup(source, backup)
    r.restore_backup(backup, restored, REPOSITORY)
    assert all_context_rows(restored) == before
    assert (
        ProductionQueryService(restored)
        .get_context_resource(fixtures["pr_key"])
        .repository_uuidv4
        == REPOSITORY
    )
    git = tmp_path / "git-only"
    r.create_consistent_backup(source, git, scope=BackupScope.GIT_ONLY)
    target = tmp_path / "git-restored"
    r.restore_backup(git, target, REPOSITORY)
    assert not (target / "context.sqlite3").exists()
    assert ProductionQueryService(target).detect_mode() == "core_only"


def rehash_backup(backup):
    manifest_path = backup / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for store in manifest["stores"].values():
        raw = (backup / store["path"]).read_bytes()
        store["sha256"] = hashlib.sha256(raw).hexdigest()
        store["bytes"] = len(raw)
    manifest["overall_sha256"] = hashlib.sha256(
        "".join(
            manifest["stores"][s]["sha256"] for s in sorted(manifest["stores"])
        ).encode()
    ).hexdigest()
    raw = (json.dumps(manifest, indent=2) + "\n").encode()
    manifest_path.write_bytes(raw)
    (backup / "manifest.json.sha256").write_text(
        hashlib.sha256(raw).hexdigest() + "  manifest.json\n"
    )


@pytest.mark.parametrize("damage", ["member", "clock", "role", "support"])
def test_forged_backup_with_valid_checksums_fails_semantic_restore(tmp_path, damage):
    source, backup, restored = (tmp_path / n for n in ("source", "backup", "restored"))
    service, r1, _, _ = producer(source)
    r = RecoveryService()
    r.create_consistent_backup(source, backup)
    # Fault injection in disposable backup; trusted schema is restored unchanged.
    with connect(backup / "stores/context.sqlite3", "context") as db:
        triggers = db.execute(
            "SELECT name,sql FROM sqlite_schema WHERE type='trigger'"
        ).fetchall()
        for name, _ in triggers:
            db.execute('DROP TRIGGER "' + name + '"')
        row = db.execute(
            "SELECT scope_json,provenance_json FROM resource_relations WHERE relation_kind='provider_repository_roles' AND provider_resource_id='10'"
        ).fetchone()
        scope = json.loads(row[0])
        if damage == "member":
            scope["repository_roles"]["owning_repository"]["provider_repository_id"] = (
                "2"
            )
        elif damage == "clock":
            scope["repository_roles"]["owning_repository"]["observed_at_us"] = 999
        elif damage == "role":
            scope["repository_roles"]["transfer_to_repository"] = scope[
                "repository_roles"
            ].pop("owning_repository")
        if damage == "support":
            db.execute("PRAGMA ignore_check_constraints=ON")
            db.execute(
                "DELETE FROM resource_repository_relations WHERE relation_kind='represents_repository'"
            )
        else:
            db.execute(
                "UPDATE resource_relations SET scope_json=? WHERE relation_kind='provider_repository_roles' AND provider_resource_id='10'",
                (canonical(scope),),
            )
        for _, sql in triggers:
            db.execute(sql)
    rehash_backup(backup)
    with pytest.raises(RestoreValidationError):
        r.restore_backup(backup, restored, r1)
    assert not restored.exists()
    assert not (source / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("operation", ["query", "search", "rebuild", "backup"])
def test_invalid_authoritative_provider_scope_stops_service(tmp_path, operation):
    source = tmp_path / "source"
    service, _, _, _ = producer(source)
    key = ResourceKey(service, "issue", "90")
    with Context.transaction(source) as ctx:
        ctx.resource(key)
        # Raw fault injection passes structural SQL checks but contradicts the
        # declared Provider member. It must fail stored semantic verification.
        scope = ProviderRepositoryScope(
            {
                "owning_repository": ProviderRepositoryRoleScope(
                    "owning_repository",
                    FieldClock("provider", 10),
                    "unresolved_provider_only",
                    "2",
                    observed_at_us=10,
                )
            }
        )
        ctx.db.execute(
            "INSERT INTO resource_relations VALUES(?,?,?,?,?,?,?,?)",
            (
                *key.coordinates(),
                "provider_repository_roles",
                canonical([ResourceKey(service, "repository", "1").coordinates()]),
                provenance("corrupt-scope"),
                scope.encoded,
                10,
            ),
        )
    q = ProductionQueryService(source)
    operations = {
        "query": lambda: q.get_context_resource(key),
        "search": lambda: q.search(query("repository")),
        "rebuild": q.rebuild_search,
        "backup": lambda: RecoveryService().create_consistent_backup(
            source, tmp_path / "backup"
        ),
    }
    expected_error = CorruptionDetectedError if operation == "backup" else CoreFailure
    with pytest.raises(expected_error):
        operations[operation]()
    assert (source / "p1-recovery-stop.json").exists()
    assert not (tmp_path / "backup").exists()
    with pytest.raises(CoreFailure) as error:
        q.get_context_resource(key)
    assert error.value.code == "RECOVERY_STOP"
