"""Copied outside checkout: paired Query against only five installed distributions."""

from __future__ import annotations

import base64
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import runpy
import shutil
import sqlite3
import subprocess
import sys
import sysconfig
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch


def refuses(callback, codes):
    try:
        callback()
    except Exception as error:
        assert getattr(error, "code", None) in codes, (type(error).__name__, str(error))
        return error
    raise AssertionError("unexpected success")


def normalized(value):
    return json.loads(json.dumps(value))


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def main(output):
    root = Path(__file__).resolve().parent
    runpy.run_path(str(root / "sitecustomize.py"))
    # Only the external network guard is added; no checkout source is available.
    os.environ["PYTHONPATH"] = str(root)
    os.environ["PYTHONNOUSERSITE"] = "1"
    from repo_catalog.adapters.sqlite.catalog_runtime import (
        SnapshotReadLimits,
        catalog_gate,
        persist_catalog_stop,
    )
    from repo_catalog.adapters.sqlite.p1_schema import connect
    from repo_catalog.adapters.sqlite.paired_coordination import PairSnapshotCoordinator
    from repo_catalog.adapters.sqlite.production_context import Context
    from repo_catalog.application.paired_query import PairedQueryService
    from repo_catalog.domain.p1_context import (
        FieldClock,
        MappingClaimKey,
        MappingDispositionKey,
        MappingOperationEvidence,
        ResourceKey,
    )
    from repo_catalog.domain.query_contracts import PageRequest, SnapshotFenceToken
    from repo_catalog.domain.shared_values import OID

    checks = []
    installed = Path(sysconfig.get_path("purelib")).resolve()
    products = {
        d.metadata["Name"]: d
        for d in importlib.metadata.distributions()
        if d.metadata["Name"].startswith("repo-catalog")
    }
    assert set(products) == {
        "repo-catalog-paired-query",
        "repo-catalog-core",
        "repo-catalog-context",
        "repo-catalog-runtime",
        "repo-catalog-contracts",
    }
    owners = {}
    for name, distribution in products.items():
        for member in distribution.files:
            if str(member).startswith("repo_catalog/"):
                assert str(member) not in owners
                owners[str(member)] = name
    for suffix in (
        "adapters.sqlite.p1_coordination",
        "adapters.sqlite.production_search",
        "adapters.sqlite.access_schema",
        "application.production_query",
        "application.acquisition",
        "application.exchange",
        "application.recovery",
        "domain.production_query",
        "domain.acquisition",
        "domain.exchange",
        "cli.query_features",
        "cli.main",
    ):
        assert importlib.util.find_spec("repo_catalog." + suffix) is None, suffix
    assert importlib.util.find_spec("httpx") is None
    assert not hasattr(PairSnapshotCoordinator, "admit")
    assert not hasattr(PairedQueryService, "search")
    checks.append("physical_five_product_closure_no_optional_implementations")

    data = json.loads((root / "fixture.json").read_text())
    key = ResourceKey(*data["key"])
    oid = OID(*data["oid"])
    fixture = root / "fixture"
    for role, digest in data["files"].items():
        assert (
            hashlib.sha256((fixture / (role + ".sqlite3")).read_bytes()).hexdigest()
            == digest
        )
    opened = []

    def audit(event, args):
        if event == "sqlite3.connect" and str(args[0]) != ":memory:":
            path = Path(str(args[0]))
            assert path.name in {"core.sqlite3", "context.sqlite3"}, path
            opened.append(path.name)

    sys.addaudithook(audit)

    def fresh(name):
        return Path(shutil.copytree(fixture, root / name))

    catalog = fresh("ordinary")
    query = PairedQueryService(catalog)
    assert query.detect_mode() == "paired"
    for mode in ("auto", "paired"):
        result = PairedQueryService(catalog, mode=mode).get_paired_resource(
            key, include_core_bytes=True
        )
        assert normalized(result.to_dict()) == data["paired"]
        by_role = {v.reference.role: v for v in result.core_resolutions}
        assert by_role["head"].available_in_core and by_role["head"].core_required
        assert by_role["head"].object_view.object_oid == oid
        assert len(by_role["head"].ref_notes_targets) == 1
        assert (
            not by_role["base"].available_in_core and not by_role["base"].core_required
        )
        assert by_role["base"].object_view is None
    checks.append("paired_identity_semantic_core_and_report_only_resolution")

    logical = query.get_paired_resource(key)
    head = next(v for v in logical.core_resolutions if v.reference.role == "head")
    assert head.available_in_core and head.object_view.metadata_retained
    assert head.object_view.retained_bytes is None
    checked = next(
        v for v in result.core_resolutions if v.reference.role == "head"
    ).object_view.retained_bytes
    assert (
        checked.available
        and checked.verified
        and checked.body_bytes.hex() == data["body_hex"]
    )
    checks.append("nominal_availability_distinct_from_selected_verified_bytes")

    assert (
        normalized(
            PairedQueryService(catalog, mode="context_only")
            .get_context_resource(key)
            .to_dict()
        )
        == data["context_only"]
    )
    assert query.get_git_object(oid).object_oid == oid
    assert query.read_metadata_bytes(oid).body_bytes.hex() == data["body_hex"]
    assert query.list_providers() and query.list_source_views()
    token = SnapshotFenceToken.parse(query.snapshot_token().encode())
    assert token.mode == "paired" and token.core_sha256 and token.context_sha256
    checks.append("canonical_core_context_apis_and_paired_snapshot_token")

    def cli(command, directory=catalog, *extra):
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "repo_catalog.cli.production_query",
                command,
                "--catalog",
                str(directory),
                "--mode",
                "paired",
                *extra,
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )

    response = cli(
        "paired-resource",
        catalog,
        "--service",
        key.service_instance_uuidv4,
        "--kind",
        key.resource_kind,
        "--id",
        key.provider_resource_id,
        "--include-core-bytes",
    )
    assert response.returncode == 0, response.stderr
    assert json.loads(response.stdout) == data["paired"]
    response = cli("paired-resources", catalog, "--limit", "1")
    assert response.returncode == 0, response.stderr
    first = json.loads(response.stdout)
    assert first["items"] == data["listing"][:1]
    response = cli(
        "paired-resources",
        catalog,
        "--limit",
        "1",
        "--cursor",
        first["next_cursor"],
        "--expected-token",
        first["snapshot_token"],
    )
    assert (
        response.returncode == 0
        and json.loads(response.stdout)["items"] == data["listing"][1:2]
    )
    help_result = subprocess.run(
        [sys.executable, "-m", "repo_catalog.cli.production_query", "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert (
        help_result.returncode == 0
        and "paired-resource" in help_result.stdout
        and "git-object" in help_result.stdout
        and "context-resource" in help_result.stdout
    )
    assert "search-rebuild" not in help_result.stdout
    checks.append("existing_api_cli_json_parity_and_truthful_commands")

    all_items, cursor, snapshot = [], None, None
    while True:
        part = query.list_paired_resources(
            PageRequest(limit=1, cursor=cursor, expected_token=snapshot)
        )
        snapshot = snapshot or part.snapshot_token
        assert (
            part.total_count == len(data["listing"]) and part.snapshot_token == snapshot
        )
        all_items.extend(v.to_dict() for v in part.items)
        if not part.has_more:
            assert part.next_cursor is None
            break
        assert part.next_cursor and part.next_cursor != cursor
        cursor = part.next_cursor
    assert normalized(all_items) == data["listing"]
    keys = [
        tuple(
            v["context_resource"][k]
            for k in (
                "service_instance_uuidv4",
                "resource_kind",
                "provider_resource_id",
            )
        )
        for v in all_items
    ]
    assert keys == sorted(keys)
    checks.append("complete_semantic_order_count_deterministic_continuation")

    full = query.list_paired_resources()
    for filters in (
        {"resource_kind": key.resource_kind},
        {"repository_uuidv4": data["repository"]},
        {"repository_uuidv4": "11111111-1111-4111-8111-111111111111"},
    ):
        expected = tuple(
            v
            for v in full.items
            if (
                "resource_kind" not in filters
                or v.resource.resource_kind == filters["resource_kind"]
            )
            and (
                "repository_uuidv4" not in filters
                or v.context_resource.matches_repository(filters["repository_uuidv4"])
            )
        )
        actual = query.list_paired_resources(**filters)
        assert actual.items == expected and actual.total_count == len(expected)
    checks.append("kind_repository_filters_and_empty_results")

    small = query.list_paired_resources(PageRequest(limit=1))
    refuses(
        lambda: query.list_paired_resources(PageRequest(cursor="bad")),
        {"INVALID_CURSOR"},
    )
    refuses(
        lambda: query.list_paired_resources(
            PageRequest(cursor=small.next_cursor), resource_kind="issue"
        ),
        {"INVALID_CURSOR"},
    )
    context_cursor = query.list_context_resources(PageRequest(limit=1)).next_cursor
    refuses(
        lambda: query.list_paired_resources(PageRequest(cursor=context_cursor)),
        {"INVALID_CURSOR"},
    )
    wrong = replace(token, context_sha256="0" * 64).encode()
    refuses(
        lambda: query.list_paired_resources(PageRequest(expected_token=wrong)),
        {"SNAPSHOT_MISMATCH"},
    )
    envelope = json.loads(base64.urlsafe_b64decode(small.next_cursor))
    payload = dict(
        envelope["payload"], last_key=[key.service_instance_uuidv4, "issue", "["]
    )
    forged = canonical(
        {
            "payload": payload,
            "checksum_sha256": hashlib.sha256(
                ("p6-cursor-v1:" + canonical(payload)).encode()
            ).hexdigest(),
        }
    )
    refuses(
        lambda: query.list_paired_resources(
            PageRequest(cursor=base64.urlsafe_b64encode(forged.encode()).decode())
        ),
        {"INVALID_CURSOR"},
    )
    assert not (catalog / "p1-recovery-stop.json").exists()
    checks.append("cursor_endpoint_filter_semantic_key_and_token_refusals")

    d = data["disposition_key"]
    disposition = MappingDispositionKey(
        MappingClaimKey(
            ResourceKey(*d[:3]), d[3], FieldClock.from_json(d[4]), d[5], d[6]
        ),
        d[7],
        FieldClock.from_json(d[8]),
        d[9],
    )
    qualified = PairedQueryService(
        catalog, mapping_evidence=MappingOperationEvidence(frozenset({disposition}))
    )
    assert (
        normalized([v.to_dict() for v in qualified.list_paired_resources().items])
        == data["qualified"]
    )
    assert data["qualified"] != data["listing"]
    refuses(
        lambda: qualified.list_paired_resources(PageRequest(cursor=small.next_cursor)),
        {"INVALID_CURSOR"},
    )
    checks.append(
        "qualified_mapping_alternatives_and_operation_evidence_cursor_binding"
    )

    changed = fresh("changed")
    service = PairedQueryService(changed)
    before = service.list_paired_resources(PageRequest(limit=1))
    with service.open_snapshot(required_store="paired") as pinned:
        old = pinned.context.registration_metadata(
            "provider",
            pinned.context.db.execute(
                "SELECT configuration_json FROM providers WHERE service_instance_uuidv4=?",
                (key.service_instance_uuidv4,),
            ).fetchone()[0],
        )
        with (
            catalog_gate(changed, exclusive=True),
            connect(changed / "context.sqlite3", "context") as db,
        ):
            db.execute('UPDATE providers SET configuration_json=\'{"name":"Changed"}\'')
        current = pinned.context.registration_metadata(
            "provider",
            pinned.context.db.execute(
                "SELECT configuration_json FROM providers WHERE service_instance_uuidv4=?",
                (key.service_instance_uuidv4,),
            ).fetchone()[0],
        )
        assert current == old and pinned.token.encode() == before.snapshot_token
        assert pinned.core.sql(
            "SELECT 1 FROM git_objects WHERE object_format=? AND object_oid=?", oid.key
        )
    refuses(
        lambda: service.list_paired_resources(PageRequest(cursor=before.next_cursor)),
        {"SNAPSHOT_MISMATCH"},
    )
    refuses(
        lambda: service.list_paired_resources(
            PageRequest(expected_token=before.snapshot_token)
        ),
        {"SNAPSHOT_MISMATCH"},
    )
    assert not (changed / "p1-recovery-stop.json").exists()
    checks.append("pinned_pair_retains_authority_while_new_tokens_fence_continuation")

    for selected, opaque_role in (("context_only", "core"), ("core_only", "context")):
        dest = fresh("opaque-" + opaque_role)
        opaque = dest / (opaque_role + ".sqlite3")
        opaque.write_bytes(b"opaque-not-sqlite")
        opaque.chmod(0)
        service = PairedQueryService(dest, mode=selected)
        if selected == "context_only":
            assert (
                normalized(service.get_context_resource(key).to_dict())
                == data["context_only"]
            )
        else:
            assert service.get_git_object(oid).object_oid == oid
        refuses(lambda: service.get_paired_resource(key), {"STORE_UNAVAILABLE"})
        opaque.chmod(0o600)
        assert opaque.read_bytes() == b"opaque-not-sqlite"
    for role in ("core", "context"):
        dest = fresh("missing-" + role)
        (dest / (role + ".sqlite3")).unlink()
        refuses(
            lambda: PairedQueryService(dest, mode="paired").get_paired_resource(key),
            {"STORE_UNAVAILABLE"},
        )
        assert not (dest / "p1-recovery-stop.json").exists()
    checks.append(
        "explicit_single_authority_ignores_opaque_sibling_and_pair_never_downgrades"
    )

    class HostileString(str):
        def __eq__(self, other):
            raise json.JSONDecodeError("caller", "", 0)

        def __ne__(self, other):
            raise json.JSONDecodeError("caller", "", 0)

    bad_key = replace(key)
    object.__setattr__(bad_key, "coordinates", lambda: key.coordinates())
    object.__setattr__(bad_key, "provider_resource_id", "[")
    for callback in (
        lambda: query.get_paired_resource(bad_key),
        lambda: query.get_paired_resource(object()),
        lambda: query.get_paired_resource(key, include_text=1),
        lambda: query.get_paired_resource(key, include_core_bytes="yes"),
        lambda: query.list_paired_resources(
            repository_uuidv4=HostileString(data["repository"])
        ),
        lambda: query.list_paired_resources(resource_kind=object()),
    ):
        refuses(callback, {"INVALID_INPUT"})
    for field, value, code in (
        ("limit", True, "INVALID_LIMIT"),
        ("cursor", HostileString("bad"), "INVALID_CURSOR"),
        ("expected_token", HostileString(small.snapshot_token), "INVALID_TOKEN"),
    ):
        page = PageRequest()
        object.__setattr__(page, field, value)
        refuses(lambda: query.list_paired_resources(page), {code})
    invalid = root / "invalid-authority"
    invalid.mkdir()
    for role in ("core", "context"):
        (invalid / (role + ".sqlite3")).write_bytes(b"not sqlite")
    refuses(
        lambda: PairedQueryService(invalid).list_paired_resources(
            PageRequest(cursor="bad")
        ),
        {"INVALID_CURSOR"},
    )
    refuses(
        lambda: PairedQueryService(invalid).get_paired_resource(bad_key),
        {"INVALID_INPUT"},
    )
    assert (
        not (catalog / "p1-recovery-stop.json").exists()
        and not (invalid / "p1-recovery-stop.json").exists()
    )
    checks.append("caller_key_bool_page_filter_errors_precede_stored_corruption")

    limited = PairedQueryService(
        catalog, read_limits=SnapshotReadLimits(max_total_rows=1)
    )
    refuses(lambda: limited.get_paired_resource(key), {"QUERY_BUDGET"})
    refuses(lambda: limited.list_paired_resources(), {"QUERY_BUDGET"})
    assert not (catalog / "p1-recovery-stop.json").exists()
    checks.append("paired_query_budget_is_not_corruption")

    for field in ("repository_uuidv4", "catalog_instance_uuidv4"):
        dest = fresh("mismatched-" + field)
        for suffix in ("", "-wal", "-shm"):
            target = dest / ("context.sqlite3" + suffix)
            target.unlink(missing_ok=True)
            source = root / "mismatch-fixtures" / field / ("context.sqlite3" + suffix)
            if source.exists():
                shutil.copy2(source, target)
        refuses(
            lambda: PairedQueryService(dest).get_paired_resource(key), {"PAIR_IDENTITY"}
        )
        assert not (dest / "p1-recovery-stop.json").exists()
    checks.append("repository_and_catalog_pair_identity_mismatch_refused")

    missing = fresh("missing-required-reference")
    with connect(missing / "context.sqlite3", "context") as db:
        triggers = db.execute(
            "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name='core_references'"
        ).fetchall()
        for name, _ in triggers:
            db.execute('DROP TRIGGER "' + name + '"')
        db.execute(
            "UPDATE core_references SET object_oid=?", ("0" * len(oid.object_oid),)
        )
        for _, definition in triggers:
            db.execute(definition)
    assert PairedQueryService(missing, mode="context_only").get_context_resource(key)
    refuses(
        lambda: PairedQueryService(missing).get_paired_resource(key),
        {"MISSING_CORE_REFERENCE"},
    )
    assert (missing / "p1-recovery-stop.json").exists()
    refuses(
        lambda: PairedQueryService(missing, mode="context_only").get_context_resource(
            key
        ),
        {"RECOVERY_STOP", "RECOVERY_REQUIRED"},
    )
    checks.append("required_cross_store_dependency_failure_persists_global_stop")

    for role, table, sql, args in (
        (
            "core",
            "retained_metadata",
            "UPDATE retained_metadata SET body=? WHERE object_format=? AND object_oid=?",
            (b"tampered", *oid.key),
        ),
        ("context", "text_bodies", "UPDATE text_bodies SET text_value='tampered'", ()),
    ):
        dest = fresh("corrupt-" + role)
        path = dest / (role + ".sqlite3")
        with connect(path, role) as db:
            db.execute("PRAGMA ignore_check_constraints=ON")
            triggers = db.execute(
                "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name=?",
                (table,),
            ).fetchall()
            for name, _ in triggers:
                db.execute('DROP TRIGGER "' + name + '"')
            db.execute(sql, args)
            for _, definition in triggers:
                db.execute(definition)
        before_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        refuses(
            lambda: PairedQueryService(dest).get_paired_resource(
                key, include_core_bytes=True
            ),
            {"AUTHORITATIVE_CORRUPTION"},
        )
        assert (dest / "p1-recovery-stop.json").exists() and hashlib.sha256(
            path.read_bytes()
        ).hexdigest() == before_hash
    checks.append(
        "actual_selected_core_and_context_corruption_stops_without_authority_repair"
    )

    original_snapshots = PairSnapshotCoordinator.snapshots
    original_text = Context.read_text
    for operation_name in ("single", "list"):
        for when in ("prior", "during", "after"):
            dest = fresh("stop-" + operation_name + "-" + when)
            service = PairedQueryService(dest)
            operation = (
                (lambda: service.get_paired_resource(key))
                if operation_name == "single"
                else service.list_paired_resources
            )
            if when == "prior":
                persist_catalog_stop(dest, "synthetic prior paired stop")
                refuses(operation, {"RECOVERY_STOP", "RECOVERY_REQUIRED"})
                continue
            if when == "during":

                def during(self, digest):
                    value = original_text(self, digest)
                    persist_catalog_stop(dest, "synthetic during paired read")
                    return value

                target = patch.object(Context, "read_text", during)
            else:

                @contextmanager
                def after(*args, **kwargs):
                    with original_snapshots(*args, **kwargs) as pair:
                        yield pair
                    persist_catalog_stop(dest, "synthetic after pair cleanup")

                target = patch.object(PairSnapshotCoordinator, "snapshots", after)
            with target:
                refuses(operation, {"RECOVERY_STOP", "RECOVERY_REQUIRED"})
    checks.append("prior_inflight_and_final_post_cleanup_paired_completion_fences")

    origins = {}
    for name, module in tuple(sys.modules.items()):
        if name.startswith("repo_catalog.") and getattr(module, "__file__", None):
            path = Path(module.__file__).resolve()
            assert path.is_relative_to(installed), (name, path)
            assert path.relative_to(installed).as_posix() in owners
            origins[name] = str(path)
    assert opened and set(opened) == {"core.sqlite3", "context.sqlite3"}
    assert not any(
        p.name in {"access.sqlite3", "operational.sqlite3", "search.sqlite3"}
        for p in root.rglob("*.sqlite3")
    )
    output.write_text(
        json.dumps(
            {
                "result": "passed",
                "checks": checks,
                "installed_distributions": sorted(products),
                "owners": owners,
                "origins": origins,
                "sqlite": sqlite3.sqlite_version,
                "opened_authority_roles": sorted(set(opened)),
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
