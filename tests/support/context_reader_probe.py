"""Copied outside checkout: exercise the real installed API/CLI against producer state."""

from __future__ import annotations

import hashlib
import importlib
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
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit


def refuses(callback, codes):
    try:
        callback()
    except Exception as error:
        assert getattr(error, "code", None) in codes, (type(error), str(error))
        return error
    raise AssertionError("unexpected success")


def main(output):
    root = Path(__file__).resolve().parent
    runpy.run_path(str(root / "sitecustomize.py"))
    os.environ["PYTHONPATH"] = str(root)
    from repo_catalog.adapters.sqlite.catalog_runtime import (
        SnapshotReadLimits,
        persist_catalog_stop,
    )
    from repo_catalog.adapters.sqlite.production_context import Context
    from repo_catalog.application.context_query import ContextQueryService
    from repo_catalog.domain.p1_context import ResourceKey

    checks = []
    installed = Path(sysconfig.get_path("purelib")).resolve()
    distributions = {
        d.metadata["Name"]: d
        for d in importlib.metadata.distributions()
        if d.metadata["Name"].startswith("repo-catalog")
    }
    assert set(distributions) == {
        "repo-catalog-context",
        "repo-catalog-runtime",
        "repo-catalog-contracts",
    }
    owners = {}
    for name, distribution in distributions.items():
        for member in distribution.files:
            if str(member).startswith("repo_catalog/"):
                assert str(member) not in owners, str(member)
                owners[str(member)] = name
    for suffix in (
        "adapters.sqlite.git_core",
        "adapters.sqlite.core_schema_functions",
        "adapters.sqlite.core_coordination",
        "adapters.sqlite.p1_coordination",
        "adapters.sqlite.access_schema",
        "adapters.sqlite.production_search",
        "application.core_query",
        "application.core_recovery",
        "application.production_query",
        "application.acquisition",
        "application.exchange",
        "domain.p1_core",
        "domain.core_query",
        "domain.production_query",
        "cli.query_features",
        "cli.main",
    ):
        assert importlib.util.find_spec("repo_catalog." + suffix) is None, suffix
    assert importlib.util.find_spec("httpx") is None
    checks.append("physical_absence_unique_owners")

    data = json.loads((root / "fixture.json").read_text())
    fixture = root / "fixture"
    assert (
        hashlib.sha256((fixture / "context.sqlite3").read_bytes()).hexdigest()
        == data["context_sha256"]
    )
    key = ResourceKey(*data["resource"])
    touched = []

    def audit(event, args):
        if event == "sqlite3.connect":
            path = str(args[0])
            if path.startswith("file:"):
                uri = urlsplit(path)
                assert uri.netloc == "" and uri.query == "mode=rw", path
                path = unquote(uri.path)
            if path != ":memory:":
                assert Path(path).name == "context.sqlite3", path
                touched.append(path)

    sys.addaudithook(audit)

    def fresh(name):
        return Path(shutil.copytree(fixture, root / name))

    catalog = fresh("ordinary")
    service = ContextQueryService(catalog, mode="context_only")
    assert (
        json.loads(
            json.dumps(service.get_context_resource(key, include_text=True).to_dict())
        )
        == data["expected"]
    )
    assert all(
        not dep.available for dep in service.get_context_resource(key).core_dependencies
    )
    result = service.read_context_text(data["digest"])
    assert result.available and result.verified
    assert (
        result.body_bytes == data["text"].encode()
        and result.digest_sha256 == data["digest"]
    )
    assert touched
    assert sorted(p.name for p in catalog.glob("*.sqlite3")) == ["context.sqlite3"]
    assert service.snapshot_token().core_sha256 is None
    checks.append("resource_provenance_relations_unresolved_refs_exact_verified_text")

    def cli(directory, *extra):
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "repo_catalog.cli.production_query",
                "context-resource",
                "--catalog",
                str(directory),
                "--mode",
                "context_only",
                "--service",
                key.service_instance_uuidv4,
                "--kind",
                key.resource_kind,
                "--id",
                key.provider_resource_id,
                *extra,
            ],
            cwd=root,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
            timeout=30,
        )

    response = cli(catalog)
    assert response.returncode == 0, response.stderr
    assert json.loads(response.stdout) == data["expected"]
    checks.append("existing_cli_same_meaning")

    opaque = fresh("opaque")
    core = opaque / "core.sqlite3"
    core.write_bytes(b"opaque-not-a-sqlite-database")
    core.chmod(0)
    assert (
        json.loads(
            json.dumps(
                ContextQueryService(opaque, mode="context_only")
                .get_context_resource(key)
                .to_dict()
            )
        )
        == data["expected"]
    )
    assert cli(opaque).returncode == 0
    core.chmod(0o600)
    assert core.read_bytes() == b"opaque-not-a-sqlite-database"
    assert sorted(p.name for p in opaque.glob("*.sqlite3")) == [
        "context.sqlite3",
        "core.sqlite3",
    ]
    refuses(
        lambda: ContextQueryService(opaque).get_context_resource(key),
        {"MISSING_CAPABILITY"},
    )
    checks.append("opaque_coexisting_core_untouched_auto_refuses")

    for mode in ("paired", "core_only"):
        refuses(
            lambda: ContextQueryService(catalog, mode=mode).get_context_resource(key),
            {"MISSING_CAPABILITY"},
        )
    for name in (
        "get_git_object",
        "get_paired_resource",
        "search",
    ):
        assert not hasattr(service, name), name
    help_result = subprocess.run(
        [sys.executable, "-m", "repo_catalog.cli.production_query", "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert help_result.returncode == 0
    assert (
        "paired-resource" not in help_result.stdout
        and "git-object" not in help_result.stdout
        and "search-rebuild" not in help_result.stdout
    )
    checks.append("missing_capabilities_no_downgrade_or_false_stop")

    stopped = fresh("stopped")
    persist_catalog_stop(stopped, "synthetic prior stop")
    refuses(
        lambda: ContextQueryService(stopped).get_context_resource(key),
        {"RECOVERY_STOP", "RECOVERY_REQUIRED"},
    )
    response = cli(stopped)
    assert response.returncode == 2 and json.loads(response.stderr)["code"] in {
        "RECOVERY_STOP",
        "RECOVERY_REQUIRED",
    }
    checks.append("persistent_stop_api_cli")

    mid = fresh("mid-read")
    original = Context.read_text

    def stop_after_text(self, digest):
        result = original(self, digest)
        persist_catalog_stop(self.directory, "synthetic during-read stop")
        return result

    with patch.object(Context, "read_text", stop_after_text):
        refuses(
            lambda: ContextQueryService(mid, mode="context_only").get_context_resource(
                key
            ),
            {"RECOVERY_STOP", "RECOVERY_REQUIRED"},
        )
    checks.append("during_read_completion_fence")

    # Stop after Context's own snapshot capability has completed: the outer
    # Query completion fence must still refuse publishing its result.
    late = fresh("late-completion")
    from contextlib import contextmanager

    original_snapshot = Context.snapshot

    @contextmanager
    def stop_after_snapshot(*args, **kwargs):
        with original_snapshot(*args, **kwargs) as context:
            yield context
        persist_catalog_stop(late, "synthetic final completion stop")

    with patch.object(Context, "snapshot", stop_after_snapshot):
        refuses(
            lambda: ContextQueryService(late, mode="context_only").read_context_text(
                data["digest"]
            ),
            {"RECOVERY_STOP", "RECOVERY_REQUIRED"},
        )
    checks.append("outer_completion_fence")

    assert not service.read_context_text("0" * 64).available
    assert not (catalog / "p1-recovery-stop.json").exists()
    refuses(lambda: ContextQueryService(catalog, mode="bad"), {"INVALID_MODE"})
    absent = root / "absent"
    absent.mkdir()
    refuses(
        lambda: ContextQueryService(absent).read_context_text(data["digest"]),
        {"STORE_UNAVAILABLE"},
    )
    assert not list(absent.iterdir())
    refuses(
        lambda: ContextQueryService(
            catalog, read_limits=SnapshotReadLimits(max_total_rows=1)
        ).get_context_resource(key),
        {"QUERY_BUDGET"},
    )
    assert not (catalog / "p1-recovery-stop.json").exists()
    refuses(lambda: service.get_context_resource(object()), {"INVALID_INPUT"})
    bad_key = ResourceKey(*data["resource"])
    object.__setattr__(bad_key, "provider_resource_id", "[")
    refuses(lambda: service.get_context_resource(bad_key), {"INVALID_INPUT"})
    refuses(lambda: service.read_context_text(object()), {"INVALID_INPUT"})
    assert not (catalog / "p1-recovery-stop.json").exists()
    assert service.get_context_resource(key).resource == key
    checks.append("unavailable_input_budget_capability_not_corruption")

    for fault in ("text", "provenance"):
        damaged = fresh("damaged-" + fault)
        path = damaged / "context.sqlite3"
        with sqlite3.connect(path) as db:
            table = "text_bodies" if fault == "text" else "field_candidates"
            triggers = db.execute(
                "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name=?",
                (table,),
            ).fetchall()
            for name, _ in triggers:
                db.execute('DROP TRIGGER "' + name + '"')
            db.execute("PRAGMA ignore_check_constraints=ON")
            db.execute(
                "UPDATE text_bodies SET text_value='tampered'"
                if fault == "text"
                else "UPDATE field_candidates SET provenance_json='[]'"
            )
            for _, sql in triggers:
                db.execute(sql)
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        refuses(
            lambda: ContextQueryService(
                damaged, mode="context_only"
            ).get_context_resource(key),
            {"AUTHORITATIVE_CORRUPTION"},
        )
        assert (damaged / "p1-recovery-stop.json").is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before
        response = cli(damaged)
        assert response.returncode == 2
    checks.append("corrupt_text_and_stored_structure_stop_without_authority_write")

    # OP-03B: the same installed minimum now exposes Resource enumeration.
    from dataclasses import replace

    from repo_catalog.domain.query_contracts import PageRequest, SnapshotFenceToken

    listed = service.list_context_resources(PageRequest(limit=100))
    assert [json.loads(json.dumps(v.to_dict())) for v in listed.items] == data[
        "listing"
    ]
    assert listed.total_count == len(data["listing"]) and not listed.has_more
    empty = ContextQueryService(
        root / "empty", mode="context_only"
    ).list_context_resources()
    assert (
        empty.items == ()
        and empty.total_count == 0
        and not empty.has_more
        and empty.next_cursor is None
    )
    collected, cursor = [], None
    while True:
        part = service.list_context_resources(
            PageRequest(limit=1, cursor=cursor, expected_token=listed.snapshot_token)
        )
        assert part.total_count == listed.total_count and len(part.items) == 1
        collected.extend(v.semantic_key for v in part.items)
        if not part.has_more:
            assert part.next_cursor is None
            break
        assert part.next_cursor and part.next_cursor != cursor
        cursor = part.next_cursor
    assert collected == sorted(v.semantic_key for v in listed.items)
    checks.append("enumeration_empty_populated_complete_key_pages_counts")

    for filters in (
        {"service_instance_uuidv4": key.service_instance_uuidv4},
        {"service_instance_uuidv4": "11111111-1111-4111-8111-111111111111"},
        {"resource_kind": key.resource_kind},
        {"repository_uuidv4": data["repository"]},
        {"identifier_namespace": key},
    ):
        expected = [
            v
            for v in listed.items
            if (
                "service_instance_uuidv4" not in filters
                or v.resource.service_instance_uuidv4
                == filters["service_instance_uuidv4"]
            )
            and (
                "resource_kind" not in filters
                or v.resource.resource_kind == filters["resource_kind"]
            )
            and (
                "repository_uuidv4" not in filters
                or v.matches_repository(filters["repository_uuidv4"])
            )
            and (
                "identifier_namespace" not in filters
                or v.identifier_namespace == filters["identifier_namespace"]
            )
        ]
        actual = service.list_context_resources(**filters)
        assert actual.items == tuple(expected) and actual.total_count == len(expected)
    checks.append("enumeration_service_kind_repository_namespace_filters")

    command = [
        sys.executable,
        "-I",
        "-m",
        "repo_catalog.cli.production_query",
        "context-resources",
        "--catalog",
        str(catalog),
        "--mode",
        "context_only",
        "--limit",
        "1",
    ]
    response = subprocess.run(
        command, cwd=root, capture_output=True, text=True, timeout=30
    )
    assert response.returncode == 0, response.stderr
    first = json.loads(response.stdout)
    assert (
        first["items"] == data["listing"][:1]
        and first["total_count"] == listed.total_count
    )
    response = subprocess.run(
        command
        + [
            "--cursor",
            first["next_cursor"],
            "--expected-token",
            first["snapshot_token"],
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert (
        response.returncode == 0
        and json.loads(response.stdout)["items"] == data["listing"][1:2]
    )
    assert "context-resources" in help_result.stdout
    assert (
        ContextQueryService(opaque, mode="context_only")
        .list_context_resources()
        .total_count
        == listed.total_count
    )
    refuses(
        lambda: ContextQueryService(opaque).list_context_resources(),
        {"MISSING_CAPABILITY"},
    )
    refuses(
        lambda: ContextQueryService(catalog, mode="paired").list_context_resources(),
        {"MISSING_CAPABILITY"},
    )
    checks.append("enumeration_cli_continuation_capability_opaque_core")

    # Page/filter/cursor failures are caller errors even if stored rows are bad.
    small = service.list_context_resources(PageRequest(limit=1))
    for bad_filters in (
        {"repository_uuidv4": object()},
        {"service_instance_uuidv4": "wrong"},
        {"resource_kind": []},
        {"identifier_namespace": bad_key},
        {"parent": bad_key},
    ):
        refuses(
            lambda: service.list_context_resources(**bad_filters), {"INVALID_INPUT"}
        )
    refuses(
        lambda: service.list_context_resources(parent=key),
        {"I2_PARENT_QUERY_UNSUPPORTED"},
    )
    for field, value, code in (
        ("limit", True, "INVALID_LIMIT"),
        ("cursor", 12, "INVALID_CURSOR"),
        ("expected_token", "bad", "INVALID_TOKEN"),
    ):
        bad_page = replace(PageRequest())
        object.__setattr__(bad_page, field, value)
        refuses(lambda: service.list_context_resources(bad_page), {code})
    refuses(lambda: service.list_context_resources(object()), {"INVALID_INPUT"})
    refuses(
        lambda: service.list_context_resources(PageRequest(cursor="invalid")),
        {"INVALID_CURSOR"},
    )
    refuses(
        lambda: service.list_context_resources(
            PageRequest(cursor=small.next_cursor), resource_kind="issue"
        ),
        {"INVALID_CURSOR"},
    )
    token = replace(
        SnapshotFenceToken.parse(listed.snapshot_token), context_sha256="0" * 64
    ).encode()
    refuses(
        lambda: service.list_context_resources(PageRequest(expected_token=token)),
        {"SNAPSHOT_MISMATCH"},
    )
    assert not (catalog / "p1-recovery-stop.json").exists()
    corrupt = ContextQueryService(root / "damaged-provenance", mode="context_only")
    refuses(
        lambda: corrupt.list_context_resources(PageRequest(cursor="invalid")),
        {"INVALID_CURSOR"},
    )
    checks.append("enumeration_input_cursor_filter_token_errors_not_corruption")

    # Authentic cursor encoding with wrong endpoint or Context position is refused.
    import base64

    envelope = json.loads(base64.urlsafe_b64decode(small.next_cursor))
    for endpoint, position in (
        ("paired_resources", list(key.coordinates())),
        ("context_resources", [key.service_instance_uuidv4, "issue", "["]),
    ):
        payload = dict(envelope["payload"], endpoint_kind=endpoint, last_key=position)

        def canonical(value):
            return json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )

        changed = canonical(
            {
                "payload": payload,
                "checksum_sha256": hashlib.sha256(
                    ("p6-cursor-v1:" + canonical(payload)).encode()
                ).hexdigest(),
            }
        )
        encoded = base64.urlsafe_b64encode(changed.encode()).decode()
        refuses(
            lambda: service.list_context_resources(PageRequest(cursor=encoded)),
            {"INVALID_CURSOR"},
        )
    checks.append("enumeration_wrong_endpoint_and_semantic_cursor_key")

    changed = fresh("changed-authority")
    original_service = ContextQueryService(changed, mode="context_only")
    previous = original_service.list_context_resources(PageRequest(limit=1))
    from repo_catalog.adapters.sqlite.p1_schema import connect

    with connect(changed / "context.sqlite3", "context") as db:
        db.execute("UPDATE providers SET configuration_json='{}'")
    refuses(
        lambda: original_service.list_context_resources(
            PageRequest(cursor=previous.next_cursor)
        ),
        {"SNAPSHOT_MISMATCH"},
    )
    refuses(
        lambda: original_service.list_context_resources(
            PageRequest(expected_token=previous.snapshot_token)
        ),
        {"SNAPSHOT_MISMATCH"},
    )
    assert not (changed / "p1-recovery-stop.json").exists()
    checks.append("enumeration_changed_authority_stale_cursor_fence")

    # Reconstruction scans metadata first, resolves checked text only for emitted rows.
    reads = []

    def count_text(self, digest):
        reads.append(digest)
        return original(self, digest)

    with patch.object(Context, "read_text", count_text):
        single = service.list_context_resources(PageRequest(limit=1))
    expected_digests = {
        digest for v in single.items for digest in v.resolved_texts if len(digest) == 64
    }
    assert set(reads) == expected_digests
    refuses(
        lambda: ContextQueryService(
            catalog, read_limits=SnapshotReadLimits(max_total_rows=1)
        ).list_context_resources(),
        {"QUERY_BUDGET"},
    )
    assert not (catalog / "p1-recovery-stop.json").exists()
    checks.append("enumeration_two_phase_text_and_budget_not_corruption")

    for timing in ("during", "after"):
        dest = fresh("enumeration-" + timing)
        if timing == "during":

            def stop_list(self, digest):
                value = original(self, digest)
                persist_catalog_stop(dest, "synthetic enumeration stop")
                return value

            target = patch.object(Context, "read_text", stop_list)
        else:

            @contextmanager
            def stop_snapshot(*args, **kwargs):
                with original_snapshot(*args, **kwargs) as current:
                    yield current
                persist_catalog_stop(dest, "synthetic post-cleanup enumeration stop")

            target = patch.object(Context, "snapshot", stop_snapshot)
        with target:
            refuses(
                lambda: ContextQueryService(
                    dest, mode="context_only"
                ).list_context_resources(),
                {"RECOVERY_STOP", "RECOVERY_REQUIRED"},
            )
    refuses(
        lambda: ContextQueryService(stopped).list_context_resources(),
        {"RECOVERY_STOP", "RECOVERY_REQUIRED"},
    )
    checks.append("enumeration_persistent_during_final_completion_stop")

    for fault in ("text", "provenance"):
        dest = fresh("enumeration-damaged-" + fault)
        with sqlite3.connect(dest / "context.sqlite3") as db:
            table = "text_bodies" if fault == "text" else "field_candidates"
            triggers = db.execute(
                "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name=?",
                (table,),
            ).fetchall()
            for name, _ in triggers:
                db.execute('DROP TRIGGER "' + name + '"')
            db.execute("PRAGMA ignore_check_constraints=ON")
            db.execute(
                "UPDATE text_bodies SET text_value='tampered'"
                if fault == "text"
                else "UPDATE field_candidates SET provenance_json='[]'"
            )
            for _, sql in triggers:
                db.execute(sql)
        before = hashlib.sha256((dest / "context.sqlite3").read_bytes()).hexdigest()
        refuses(
            lambda: ContextQueryService(
                dest, mode="context_only"
            ).list_context_resources(),
            {"AUTHORITATIVE_CORRUPTION"},
        )
        assert (dest / "p1-recovery-stop.json").exists()
        assert (
            hashlib.sha256((dest / "context.sqlite3").read_bytes()).hexdigest()
            == before
        )
    checks.append("enumeration_real_text_structure_corruption_persists_stop_no_repair")

    from repo_catalog.domain.p1_context import (
        FieldClock,
        MappingClaimKey,
        MappingDispositionKey,
        MappingOperationEvidence,
    )

    mapping = json.loads((root / "mapping.json").read_text())
    keys = frozenset(
        MappingDispositionKey(
            MappingClaimKey(
                ResourceKey(*d[:3]), d[3], FieldClock.from_json(d[4]), d[5], d[6]
            ),
            d[7],
            FieldClock.from_json(d[8]),
            d[9],
        )
        for d in mapping["dispositions"]
    )
    plain = ContextQueryService(root / "mapping", mode="context_only")
    qualified = ContextQueryService(
        root / "mapping",
        mode="context_only",
        mapping_evidence=MappingOperationEvidence(keys),
    )
    for query_service, expected in (
        (plain, mapping["plain"]),
        (qualified, mapping["qualified"]),
    ):
        result = query_service.list_context_resources()
        assert json.loads(json.dumps([v.to_dict() for v in result.items])) == expected
        by_id = {
            v.resource.provider_resource_id: v
            for v in result.items
            if v.resource.resource_kind == "issue"
        }
        assert by_id['"7"'].repository_roles[0].state == "unresolved_provider_only"
        assert by_id['"11"'].repository_roles[0].state == "explicit_null"
        assert by_id['"12"'].repository_roles == ()
        expected_targets = (
            set(mapping["repositories"])
            if query_service is plain
            else {mapping["repositories"][1]}
        )
        assert (
            set(by_id['"13"'].repository_roles[0].mapping.active_repository_uuidv4s)
            == expected_targets
        )
        for repository in mapping["repositories"]:
            page = query_service.list_context_resources(repository_uuidv4=repository)
            assert page.items == tuple(
                v for v in result.items if v.matches_repository(repository)
            )
    page = plain.list_context_resources(PageRequest(limit=1))
    refuses(
        lambda: qualified.list_context_resources(PageRequest(cursor=page.next_cursor)),
        {"INVALID_CURSOR"},
    )
    assert plain.get_context_resource(
        ResourceKey.from_native(mapping["service"], "issue", "10")
    ).matches_repository(mapping["repositories"][0])
    assert not qualified.get_context_resource(
        ResourceKey.from_native(mapping["service"], "issue", "10")
    ).matches_repository(mapping["repositories"][0])
    checks.append(
        "enumeration_qualified_mapping_alternatives_missing_null_unresolved_evidence_bound_cursor"
    )

    metadata_probe = runpy.run_path(str(root / "context_metadata_probe.py"))
    checks.extend(
        metadata_probe["exercise_metadata"](root, data["metadata"], fresh, refuses)
    )

    origins = {}
    for name, module in list(sys.modules.items()):
        if name.startswith("repo_catalog.") and getattr(module, "__file__", None):
            path = Path(module.__file__).resolve()
            assert path.is_relative_to(installed), (name, path)
            assert path.relative_to(installed).as_posix() in owners
            origins[name] = str(path)
    checks.append("installed_runtime_closure_origins")
    assert not any(
        p.name in {"access.sqlite3", "operational.sqlite3", "search.sqlite3"}
        for p in root.rglob("*.sqlite3")
    )
    checks.append("no_implicit_optional_databases")
    output.write_text(
        json.dumps(
            {
                "result": "passed",
                "checks": checks,
                "installed_distributions": sorted(distributions),
                "owners": owners,
                "origins": origins,
                "fixture_sha256": data["context_sha256"],
                "sqlite": sqlite3.sqlite_version,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
