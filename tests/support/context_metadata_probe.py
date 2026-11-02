"""Installed-only adversarial Provider/Source/Coverage read checks; synthetic state."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from dataclasses import replace
from unittest.mock import patch


def exercise_metadata(root, metadata, fresh, refuses):
    from repo_catalog.adapters.sqlite.catalog_runtime import (
        SnapshotReadLimits,
        persist_catalog_stop,
    )
    from repo_catalog.adapters.sqlite.p1_schema import connect
    from repo_catalog.adapters.sqlite.production_context import Context
    from repo_catalog.application.context_query import ContextQueryService
    from repo_catalog.domain.p1_context import CoverageScope

    checks = []
    catalog = fresh("metadata")
    query = ContextQueryService(catalog, mode="context_only")
    scopes = tuple(
        CoverageScope(v["owner_kind"], tuple(v["owner_coordinates"]))
        for v in metadata["coverage"]
    )
    operations = {
        "providers": lambda service: service.list_providers(),
        "sources": lambda service: service.list_source_views(),
        "coverage": lambda service: service.get_context_coverage(scopes[0]),
    }
    assert [v.to_dict() for v in query.list_providers()] == metadata["providers"]
    assert [v.to_dict() for v in query.list_source_views()] == metadata["sources"]
    assert [v.service_instance_uuidv4 for v in query.list_providers()] == sorted(
        v.service_instance_uuidv4 for v in query.list_providers()
    )
    assert [v.source_registration_uuidv4 for v in query.list_source_views()] == sorted(
        v.source_registration_uuidv4 for v in query.list_source_views()
    )
    for provider in metadata["providers"]:
        service = provider["service_instance_uuidv4"]
        expected = [
            v for v in metadata["sources"] if v["service_instance_uuidv4"] == service
        ]
        assert [v.to_dict() for v in query.list_source_views(service)] == expected
    assert query.list_source_views("99999999-9999-4999-8999-999999999999") == ()
    checks.append("metadata_provider_source_values_order_filter_original_provenance")

    populated = next(
        v
        for v in query.list_source_views()
        if v.service_instance_uuidv4 == metadata["service"]
    )
    assert list(populated.repositories) == metadata["positive_repositories"]
    assert any(v.state == "complete" for v in populated.inventories)
    assert any(
        v.state == "partial" and len(v.repositories) == 1 for v in populated.inventories
    )
    assert (
        len(populated.repositories) == 2
    )  # partial inventory never deletes a positive association
    assert all(
        v.to_dict().get("available_in_core") is None for v in query.list_source_views()
    )
    checks.append(
        "metadata_partial_inventory_keeps_known_positive_roster_no_core_claims"
    )

    coverage = [query.get_context_coverage(scope).to_dict() for scope in scopes]
    assert coverage == metadata["coverage"]
    assert [v["state"] for v in coverage] == [
        "partial",
        "conflict",
        "complete",
        "complete",
        "unknown",
    ]
    assert [v["known_empty"] for v in coverage] == [False, False, False, True, False]
    assert len(coverage[1]["claims"]) == 2
    assert {v["state"] for v in coverage[1]["claims"]} == {"partial", "not_applicable"}
    checks.append("metadata_coverage_latest_set_conflict_no_fallback_empty_unknown")

    empty = ContextQueryService(root / "empty", mode="context_only")
    assert empty.list_providers() == () and empty.list_source_views() == ()
    assert empty.get_context_coverage(scopes[-1]).state == "unknown"
    opaque = ContextQueryService(root / "opaque", mode="context_only")
    assert [v.to_dict() for v in opaque.list_providers()] == metadata["providers"]
    assert [v.to_dict() for v in opaque.list_source_views()] == metadata["sources"]
    for name, operation in operations.items():
        for mode in ("auto", "paired", "core_only"):
            refuses(
                lambda: operation(ContextQueryService(root / "opaque", mode=mode)),
                {"MISSING_CAPABILITY"},
            )
    checks.append("metadata_empty_and_opaque_core_explicit_topology_no_downgrade")

    class HostileString(str):
        def __eq__(self, other):
            raise json.JSONDecodeError("caller", "", 0)

        def __ne__(self, other):
            raise json.JSONDecodeError("caller", "", 0)

    for value in (object(), "bad", HostileString(metadata["service"])):
        refuses(lambda: query.list_source_views(value), {"INVALID_INPUT"})
    for field, value in (
        ("owner_kind", "bad"),
        ("owner_kind", HostileString("source_inventory")),
        ("coordinates", ("[",)),
        ("coordinates", list(scopes[0].coordinates)),
    ):
        scope = replace(scopes[0])
        object.__setattr__(scope, field, value)
        refuses(lambda: query.get_context_coverage(scope), {"INVALID_INPUT"})
    refuses(lambda: query.get_context_coverage(object()), {"INVALID_INPUT"})
    assert not (catalog / "p1-recovery-stop.json").exists()
    bad_authority = root / "metadata-invalid-authority"
    bad_authority.mkdir()
    (bad_authority / "context.sqlite3").write_bytes(b"not sqlite")
    bad_query = ContextQueryService(bad_authority, mode="context_only")
    refuses(lambda: bad_query.get_context_coverage(object()), {"INVALID_INPUT"})
    refuses(lambda: bad_query.list_source_views(object()), {"INVALID_INPUT"})
    assert not (bad_authority / "p1-recovery-stop.json").exists()
    checks.append("metadata_caller_scope_filter_errors_precede_stored_classifiers")

    for name, operation in operations.items():
        budgeted = ContextQueryService(
            catalog,
            mode="context_only",
            read_limits=SnapshotReadLimits(max_total_rows=1),
        )
        refuses(lambda: operation(budgeted), {"QUERY_BUDGET"})
    assert not (catalog / "p1-recovery-stop.json").exists()
    checks.append("metadata_budget_exhaustion_without_corruption")

    original_snapshot = Context.snapshot
    for name, operation in operations.items():
        for timing in ("prior", "during", "after"):
            dest = fresh("metadata-stop-" + name + "-" + timing)
            service = ContextQueryService(dest, mode="context_only")
            if timing == "prior":
                persist_catalog_stop(dest, "synthetic metadata prior stop")
                refuses(
                    lambda: operation(service), {"RECOVERY_STOP", "RECOVERY_REQUIRED"}
                )
                continue
            if timing == "during":
                method = {
                    "providers": "_providers_in_snapshot",
                    "sources": "_sources_in_snapshot",
                    "coverage": "_coverage_in_snapshot",
                }[name]
                original = getattr(ContextQueryService, method)

                def after_read(self, *args):
                    result = original(self, *args)
                    persist_catalog_stop(dest, "synthetic metadata in-flight stop")
                    return result

                target = patch.object(ContextQueryService, method, after_read)
            else:

                @contextmanager
                def after_snapshot(*args, **kwargs):
                    with original_snapshot(*args, **kwargs) as current:
                        yield current
                    persist_catalog_stop(dest, "synthetic metadata final stop")

                target = patch.object(Context, "snapshot", after_snapshot)
            with target:
                refuses(
                    lambda: operation(service), {"RECOVERY_STOP", "RECOVERY_REQUIRED"}
                )
    checks.append("metadata_all_entries_prior_during_post_cleanup_completion_fences")

    for name, table, sql, operation in (
        (
            "provider-config",
            "providers",
            'UPDATE providers SET configuration_json=\'{"credential":"forbidden"}\'',
            operations["providers"],
        ),
        (
            "source-config",
            "sources",
            'UPDATE sources SET configuration_json=\'{"credential":"forbidden"}\'',
            operations["sources"],
        ),
        (
            "inventory-members",
            "source_inventory_evidence",
            "UPDATE source_inventory_evidence SET members_json='{}'",
            operations["sources"],
        ),
        (
            "inventory-terminal",
            "source_inventory_evidence",
            "UPDATE source_inventory_evidence SET terminal=2",
            operations["sources"],
        ),
        (
            "inventory-clock",
            "source_inventory_evidence",
            "UPDATE source_inventory_evidence SET observed_at_us=0",
            operations["sources"],
        ),
        (
            "coverage-state",
            "coverage_claims",
            "UPDATE coverage_claims SET coverage_state='bogus' WHERE coverage_state='partial'",
            operations["coverage"],
        ),
    ):
        dest = fresh("metadata-corrupt-" + name)
        path = dest / "context.sqlite3"
        with connect(path, "context") as db:
            db.execute("PRAGMA foreign_keys=OFF")
            db.execute("PRAGMA ignore_check_constraints=ON")
            triggers = db.execute(
                "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name=?",
                (table,),
            ).fetchall()
            for trigger, _ in triggers:
                db.execute('DROP TRIGGER "' + trigger + '"')
            db.execute(sql)
            for _, definition in triggers:
                db.execute(definition)
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        refuses(
            lambda: operation(ContextQueryService(dest, mode="context_only")),
            {"AUTHORITATIVE_CORRUPTION"},
        )
        assert (dest / "p1-recovery-stop.json").exists()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before
        refuses(
            lambda: operation(ContextQueryService(dest, mode="context_only")),
            {"RECOVERY_STOP", "RECOVERY_REQUIRED"},
        )
    checks.append(
        "metadata_real_registration_inventory_coverage_corruption_stops_no_repair"
    )

    assert not any(
        p.name
        in {"core.sqlite3", "access.sqlite3", "operational.sqlite3", "search.sqlite3"}
        for p in catalog.glob("*.sqlite3")
    )
    assert query.snapshot_token().core_sha256 is None
    checks.append("metadata_minimum_no_optional_database_creation")
    return checks
