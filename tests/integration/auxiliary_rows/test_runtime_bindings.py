"""Dedicated row encoders participate in real supported store operations."""

from contextlib import closing
from dataclasses import replace
from uuid import uuid4

import pytest


def observe_inserts(monkeypatch, row_types):
    records = {}
    for table, row_type in row_types.items():
        original = row_type.insert_bindings

        def observe(cls, record, *, table=table, original=original):
            result = original(record)
            records.setdefault(table, []).append(dict(record))
            return result

        monkeypatch.setattr(row_type, "insert_bindings", classmethod(observe))
    return records


def test_access_rows_keep_exact_approval_and_aba_revocation(tmp_path, monkeypatch):
    from repo_catalog.adapters.sqlite import access_rows, access_schema
    from repo_catalog.adapters.sqlite.access_connections import AccessConnections
    from repo_catalog.domain.access_connections import AccessPreference
    from repo_catalog.domain.access_registry import AccessRegistryError
    from tests.integration.access.test_connections import (
        KEY,
        R1,
        ROUTE,
        S1,
    )
    from tests.integration.access.test_connections import (
        path as configured_path,
    )

    records = observe_inserts(monkeypatch, access_rows.ROW_TYPES)
    # Reuse the existing representative route setup, including real local controls.
    path = configured_path.__wrapped__(tmp_path)
    with AccessConnections(path, writable=True) as store:
        store.set_preference(AccessPreference(R1, KEY))
        plan = store.review_plan(R1, S1, registration=ROUTE)
        assert store.record_local_approval(plan, 20) == store.current_grant(R1, S1)
        prior = store.assignment(KEY)
        disabled = replace(prior, enabled=False)
        store.assign_connection(disabled, expected=prior)
        store.assign_connection(prior, expected=disabled)
        with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
            store.current_grant(R1, S1)
        assert store.history(S1).registrations == (ROUTE,)
    with closing(access_schema._connect(path, writable=False)) as db:
        access_schema.validate(db)
    assert set(records) == set(access_rows.ROW_TYPES)
    assert (
        records["local_access_grants"][0]["registered_at_us"] == ROUTE.registered_at_us
    )
    assert records["scope_locator_controls"][0]["enabled"] == 0


def test_filesystem_rows_preserve_raw_paths_and_independent_interruption(
    tmp_path, monkeypatch
):
    import os

    from repo_catalog.filesystem import FilesystemCatalog, FilesystemError, rows, store

    records = observe_inserts(monkeypatch, rows.ROW_TYPES)
    root = tmp_path / "files"
    root.mkdir()
    raw_name = b"raw-\xff" if os.name == "posix" else b"raw-file"
    with open(os.fsencode(root) + b"/" + raw_name, "wb") as stream:
        stream.write(b"metadata and digest")
    database = tmp_path / "filesystem.db"
    with FilesystemCatalog.initialize(database) as catalog:
        first = catalog.scan(root)
        assert raw_name in {
            e.relative_path for e in catalog.iter_entries(first.scan_uuid)
        }
        walk = store.walk

        def interrupted(*args):
            yield next(iter(walk(*args)))
            raise RuntimeError("stop after one admitted entry")

        monkeypatch.setattr(store, "walk", interrupted)
        with pytest.raises(RuntimeError, match="stop after"):
            catalog.scan(root)
        scans = catalog.list_scans()
        assert [s.status for s in scans] == ["complete", "interrupted"]
        assert scans[1].entries == 1
        assert first.scan_uuid != scans[1].scan_uuid
        with pytest.raises(FilesystemError, match="allow_partial"):
            catalog.export_efu(scans[1].scan_uuid, tmp_path / "partial.efu")
        if os.name == "posix":
            with pytest.raises(FilesystemError, match="skip_non_utf8"):
                catalog.export_efu(
                    scans[1].scan_uuid, tmp_path / "partial.efu", allow_partial=True
                )
        report = catalog.export_efu(
            scans[1].scan_uuid,
            tmp_path / "partial.efu",
            allow_partial=True,
            skip_non_utf8=True,
        )
        assert report.skipped == (1 if os.name == "posix" else 0)
        namespace = catalog.namespace_uuid
    with FilesystemCatalog.open(database, readonly=True) as reopened:
        assert reopened.get_scan(first.scan_uuid).status == "complete"
        assert reopened.verify()["integrity"] == "ok"
    assert set(records) == set(rows.ROW_TYPES)
    entry = next(r for r in records["entries"] if r["relative_path"] == raw_name)
    assert rows.ROW_TYPES["entries"].from_record(entry).key_values() == (
        namespace,
        first.scan_uuid,
        raw_name,
    )


def test_worktree_rows_keep_observation_keys_and_unresolved_external_links(
    tmp_path, monkeypatch
):
    from repo_catalog.worktrees import WorktreeCatalog, catalog, rows
    from repo_catalog.worktrees.models import (
        DiscoveryResult,
        WorktreeEntry,
        native_path,
        observation_uuid,
    )

    records = observe_inserts(monkeypatch, rows.ROW_TYPES)
    root = native_path(tmp_path / "raw") + b"-\xff"
    common = native_path(tmp_path / "common")

    def discover(*_args, **_kwargs):
        return DiscoveryResult(
            None,
            observation_uuid(),
            root,
            common,
            (WorktreeEntry(root, common, common, branch=b"refs/heads/raw-\xff"),),
            "complete",
            (),
            100,
        )

    monkeypatch.setattr(catalog, "discover_topology", discover)
    with WorktreeCatalog.initialize(tmp_path / "worktrees.db") as store:
        first = store.discover(tmp_path)
        second = store.discover(tmp_path)
        assert first.observation_uuid != second.observation_uuid
        fs_namespace, fs_scan = str(uuid4()), observation_uuid()
        store.record_scan_reference(first.observation_uuid, root, fs_namespace, fs_scan)
        # External targets need not exist; the full qualified reference survives.
        refs = store.scan_references(fs_namespace, fs_scan)
        assert refs == (
            {
                "observation_uuid": first.observation_uuid,
                "root_path": root,
                "filesystem_namespace_uuid": fs_namespace,
                "filesystem_scan_uuid": fs_scan,
            },
        )
        repository = str(uuid4())
        store.link_repository(common, repository)
        assert store.repository_links(common) == (repository,)
        assert (
            store.get_discovery(first.observation_uuid).entries[0].branch
            == b"refs/heads/raw-\xff"
        )
        assert store.verify()["status"] == "complete"
    assert set(records) == set(rows.ROW_TYPES)
    keys = [
        rows.ROW_TYPES["worktrees"].from_record(r).key_values()
        for r in records["worktrees"]
    ]
    assert keys == [(first.observation_uuid, root), (second.observation_uuid, root)]


def test_operational_rows_preserve_reservations_resume_binding_and_loss(
    tmp_path, monkeypatch
):
    from repo_catalog.adapters.sqlite import operational_rows
    from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
    from repo_catalog.adapters.sqlite.operational_coordination import WorkLedger
    from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
    from repo_catalog.domain.exchange import ExchangeError
    from repo_catalog.domain.p1_coordination import (
        CoordinationError,
        NotesLimits,
        RequestIdentity,
    )

    records = observe_inserts(monkeypatch, operational_rows.ROW_TYPES)
    path = tmp_path / "operational.sqlite3"
    initialize(path, "operational", str(uuid4()), str(uuid4()))
    request = RequestIdentity(str(uuid4()), str(uuid4()))
    with closing(connect(path, "operational")) as db:
        work = WorkLedger(db)
        work.new_request(
            request, "{}", {kind: 10 for kind in NotesLimits.work_limits()}
        )
        attempt = str(uuid4())
        work.attempt(request, attempt)
        permit = work.reserve(request, attempt, "input_bytes", "read:1", 8)
        work.finish(permit, 3)
        # A never-settled reservation continues to count against the same request.
        work.reserve(request, attempt, "input_bytes", "read:2", 4)
        ledger = OperationalAcquisitionLedger(work)
        assert ledger.save_continuation(request, ["scan"], {"cursor": 2}) == {
            "cursor": 2
        }
        ledger.record_retry_state(["retry"], not_before_us=100, request=request)
        assert (
            ledger.get_retry_state(["retry"], request=request)["not_before_us"] == 100
        )
        ledger.record_cache_locator(["object"], "cache://local")
        assert ledger.get_cache_locator(["object"])["locator"] == "cache://local"
        sender, package = str(uuid4()), str(uuid4())
        assert work.bind_exchange_package(request, sender, package, "a" * 64)
        with pytest.raises(ExchangeError, match="PACKAGE_KEY_REBOUND"):
            work.bind_exchange_package(request, sender, package, "b" * 64)
    with closing(connect(path, "operational")) as db:
        work = WorkLedger(db)
        assert work.usage(request)["input_bytes"] == 7
        assert OperationalAcquisitionLedger(work).load_continuation(
            request, ["scan"]
        ) == {"cursor": 2}
        db.execute("DELETE FROM work_accounting WHERE work_coordinate='read:2'")
        with pytest.raises(CoordinationError, match="CONTINUATION_UNAVAILABLE"):
            work.validate_continuation(request)
    assert set(records) >= set(operational_rows.ROW_TYPES) - {"store_identity"}
    assert "spent_or_reserved" not in records["request_budgets"][0]
    assert records["work_accounting"][0]["actual"] is None


def test_search_rows_keep_projection_derivative_and_authority_fallback(
    tmp_path, monkeypatch
):
    from repo_catalog.adapters.sqlite import search_rows
    from repo_catalog.adapters.sqlite.p1_schema import connect
    from repo_catalog.application.production_query import ProductionQueryService
    from repo_catalog.domain.production_query import SearchQuery
    from tests.integration.p6.conftest import populate_rich_catalog

    records = observe_inserts(monkeypatch, search_rows.ROW_TYPES)
    directory = tmp_path / "catalog"
    populate_rich_catalog(directory, fmt="sha1")
    service = ProductionQueryService(directory)
    query = SearchQuery(query_text="p6")
    baseline = service.search(query)
    service.rebuild_search()
    indexed = service.search(query)
    assert indexed.backend == "verified_projection_scan"
    assert indexed.hits == baseline.hits
    with closing(connect(directory / "search.sqlite3", "search")) as db:
        db.execute("DELETE FROM search_documents WHERE projection_kind='git_metadata'")
    fallback = service.search(query)
    assert fallback.backends_by_kind["git_metadata"] == "authority_scan"
    assert fallback.hits == baseline.hits
    assert set(records) >= {"search_projections", "search_documents"}
    assert all(record["snapshot_token_json"] for record in records["search_documents"])
