"""Stdlib-only installed Search consumer, copied outside the checkout."""

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
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch


def refuses(callback, codes):
    try:
        callback()
    except Exception as error:
        assert getattr(error, "code", None) in codes, (type(error), str(error), codes)
        return error
    raise AssertionError("operation unexpectedly succeeded")


def mutate(path, table, assignment):
    with sqlite3.connect(path) as db:
        triggers = db.execute(
            "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name=?",
            (table,),
        ).fetchall()
        for name, _ in triggers:
            db.execute('DROP TRIGGER "' + name + '"')
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("UPDATE " + table + " SET " + assignment)
        for _, sql in triggers:
            db.execute(sql)


def main(output):
    root = Path(__file__).resolve().parent
    runpy.run_path(str(root / "sitecustomize.py"))
    os.environ["PYTHONPATH"] = str(root)
    spec = json.loads((root / "fixture.json").read_text())
    role, kinds = spec["role"], tuple(spec["kinds"])
    other = "context" if role == "core" else "core"
    mode = role + "_only"
    module = importlib.import_module("repo_catalog.application." + role + "_search")
    Service = getattr(module, role.title() + "SearchService")
    from repo_catalog.adapters.sqlite import production_search as index
    from repo_catalog.adapters.sqlite.catalog_runtime import (
        SnapshotReadLimits,
        persist_catalog_stop,
    )
    from repo_catalog.adapters.sqlite.p1_schema import connect
    from repo_catalog.domain.search_query import SearchQuery

    installed = Path(sysconfig.get_path("purelib")).resolve()
    distributions = {
        d.metadata["Name"]: d
        for d in importlib.metadata.distributions()
        if d.metadata["Name"].startswith("repo-catalog")
    }
    assert set(distributions) == {
        "repo-catalog-contracts",
        "repo-catalog-runtime",
        "repo-catalog-search",
        "repo-catalog-" + role,
    }
    owners = {}
    for name, distribution in distributions.items():
        for member in distribution.files:
            if str(member).startswith("repo_catalog/"):
                assert str(member) not in owners, member
                owners[str(member)] = name
    for suffix in (
        "domain.p1_" + other,
        "application." + other + "_query",
        "adapters.sqlite." + ("git_core" if other == "core" else "production_context"),
        "application.paired_query",
        "application.production_query",
        "application.acquisition",
        "application.exchange",
        "application.recovery",
        "adapters.sqlite.access_schema",
        "adapters.sqlite.p1_coordination",
        "cli.main",
    ):
        assert importlib.util.find_spec("repo_catalog." + suffix) is None, suffix
    assert importlib.util.find_spec("httpx") is None
    checks = ["resolved_four_owners_optional_concrete_absence"]
    catalog = root / "fixture"
    path = catalog / (role + ".sqlite3")
    service = Service(catalog, mode=mode)
    query = SearchQuery("e", kinds, limit=1000)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    response = service.search(query)
    assert response.to_dict() == spec["expected"]
    assert response.hits and response.backend == "authority_scan"
    assert not (catalog / "search.sqlite3").exists()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    checks.append("absent_index_authority_parity_no_creation")

    def cli(*args, command="search", target=catalog, expected=0):
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-m",
                "repo_catalog.cli.production_query",
                command,
                "--catalog",
                str(target),
                "--mode",
                mode,
                *args,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == expected, result.stderr
        return json.loads(result.stdout if expected == 0 else result.stderr)

    assert (
        cli("--query", "e", "--kinds", ",".join(kinds), "--limit", "1000")
        == response.to_dict()
    )
    help_output = subprocess.run(
        [sys.executable, "-I", "-m", "repo_catalog.cli.production_query", "--help"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "search-rebuild" in help_output and "paired-resource" not in help_output
    assert ("context-resources" in help_output) == (role == "context")
    checks.append("cli_capability_and_api_parity")

    # Page ordering/counts remain identical across continuation and rebuild.
    page = service.search(SearchQuery("e", kinds, limit=1))
    token = page.snapshot_token
    all_hits = list(page.hits)
    while page.has_more:
        page = service.search(
            SearchQuery(
                "e", kinds, limit=1, cursor=page.next_cursor, expected_token=token
            )
        )
        assert page.total_count == response.total_count
        all_hits.extend(page.hits)
    assert tuple(all_hits) == response.hits
    first = service.search(SearchQuery("e", kinds, limit=1))
    assert first.next_cursor
    refuses(
        lambda: service.search(
            SearchQuery("different", kinds, cursor=first.next_cursor)
        ),
        {"INVALID_CURSOR"},
    )
    refuses(
        lambda: service.search(SearchQuery("e", kinds, cursor="invalid")),
        {"INVALID_CURSOR"},
    )
    refuses(
        lambda: service.search(SearchQuery("e", kinds, expected_token="invalid")),
        {"INVALID_TOKEN", "SNAPSHOT_MISMATCH"},
    )
    refuses(lambda: service.search(object()), {"INVALID_QUERY"})
    broken = replace(query)
    object.__setattr__(broken, "projection_kinds", iter(kinds))
    refuses(lambda: service.search(broken), {"INVALID_PROJECTION_KIND"})
    for needle in ("日本語", "\0", "%_", "P6"):
        # Literal Python and SQLite matching agree, including NUL and Unicode.
        expected = service.search(SearchQuery(needle, kinds, limit=1000))
        service.rebuild_search(kinds)
        actual = service.search(SearchQuery(needle, kinds, limit=1000))
        assert actual.hits == expected.hits
    checks.append("pagination_counts_cursor_and_literal_query_inputs")

    counts = service.rebuild_search(kinds)
    assert counts and sum(counts.values()) >= response.total_count
    indexed = service.search(query)
    assert (
        indexed.hits == response.hits and indexed.backend == "verified_projection_scan"
    )
    assert (
        cli("--query", "e", "--kinds", ",".join(kinds), "--limit", "1000")
        == indexed.to_dict()
    )
    assert (
        cli("--kinds", ",".join(kinds), command="search-rebuild")["indexed_counts"]
        == counts
    )
    checks.append("explicit_rebuild_verified_index_cli")

    search_path = catalog / "search.sqlite3"
    for fault in (
        "stale",
        "incomplete",
        "poisoned",
        "wrong_key",
        "oversize",
        "corrupt_file",
    ):
        service.rebuild_search(kinds)
        if fault == "corrupt_file":
            search_path.write_bytes(b"synthetic corrupt derivative")
        else:
            with connect(search_path, "search") as db:
                if fault == "stale":
                    db.execute("DELETE FROM search_documents")
                    db.execute("DELETE FROM search_projections")
                elif fault == "incomplete":
                    db.execute(
                        "DELETE FROM search_documents WHERE (projection_kind,snapshot_token_json,document_key_json) IN (SELECT projection_kind,snapshot_token_json,document_key_json FROM search_documents LIMIT 1)"
                    )
                elif fault == "poisoned":
                    db.execute(
                        "UPDATE search_documents SET searchable_text='e forged candidate'"
                    )
                elif fault == "wrong_key":
                    db.execute(
                        "UPDATE search_documents SET document_key_json='[\"forged\"]' WHERE (projection_kind,snapshot_token_json,document_key_json) IN (SELECT projection_kind,snapshot_token_json,document_key_json FROM search_documents LIMIT 1)"
                    )
                else:
                    db.execute(
                        "UPDATE search_documents SET searchable_text=?",
                        ("e" * (index.BoundedDocuments.max_document_bytes + 1),),
                    )
        before = search_path.read_bytes()
        fallback = service.search(query)
        assert fallback.hits == response.hits, fault
        assert "authority_scan" in fallback.backends_by_kind.values(), fault
        assert search_path.read_bytes() == before
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        assert not (catalog / "p1-recovery-stop.json").exists()
    checks.append("stale_incomplete_forged_oversize_corrupt_index_fallback_no_repair")

    service.rebuild_search(kinds)
    real_open = index._open_index_read

    def disappeared(filename):
        Path(filename).unlink()
        return real_open(filename)

    with patch.object(index, "_open_index_read", disappeared):
        assert service.search(query).hits == response.hits
    assert not search_path.exists()
    checks.append("read_only_open_disappearance_no_creation")

    marker = json.JSONDecodeError("external derivative port", "", 0)

    class BrokenIndex:
        def query_candidates(self, *args, **kwargs):
            raise marker

        def replace_projection(self, *args, **kwargs):
            raise marker

    service.search_adapter = BrokenIndex()
    for call in (lambda: service.search(query), lambda: service.rebuild_search(kinds)):
        try:
            call()
        except json.JSONDecodeError as error:
            assert error is marker
        else:
            raise AssertionError("external index exception swallowed")
    service.search_adapter = None
    refuses(
        lambda: Service(
            catalog, mode=mode, read_limits=SnapshotReadLimits(max_total_rows=1)
        ).search(query),
        {"QUERY_BUDGET"},
    )
    assert not (catalog / "p1-recovery-stop.json").exists()
    checks.append("port_exception_identity_budget_not_authority_corruption")

    def fresh(name):
        destination = root / name
        destination.mkdir()
        shutil.copy2(path, destination / path.name)
        return destination

    changed = fresh("changed-authority")
    changing = Service(changed, mode=mode)
    old = changing.search(SearchQuery("e", kinds, limit=1))

    def write_change():
        with connect(changed / path.name, role) as db:
            if role == "context":
                db.execute(
                    'UPDATE providers SET configuration_json=\'{"name":"changed"}\''
                )
            else:
                row = db.execute(
                    "SELECT repository_uuidv4,provenance FROM repository_claims WHERE field='name' LIMIT 1"
                ).fetchone()
                provenance = json.loads(row[1])
                provenance[2] += ".search-installed-change"
                db.execute(
                    "INSERT INTO repository_claims VALUES(?,?,?,?)",
                    (
                        row[0],
                        "name",
                        '"changed"',
                        json.dumps(provenance, separators=(",", ":")),
                    ),
                )

    original_extract = changing._extract_documents
    modified = False

    def pinned(*args, **kwargs):
        nonlocal modified
        if not modified:
            modified = True
            write_change()
        return original_extract(*args, **kwargs)

    with patch.object(changing, "_extract_documents", pinned):
        assert changing.search(query).hits == response.hits
    assert changing.snapshot_token().encode() != old.snapshot_token
    with patch.object(
        changing,
        "_extract_documents",
        side_effect=AssertionError("stale cursor read authority"),
    ):
        refuses(
            lambda: changing.search(SearchQuery("e", kinds, cursor=old.next_cursor)),
            {"SNAPSHOT_MISMATCH"},
        )
    checks.append("pinned_concurrent_authority_and_early_stale_cursor")

    if role == "core":
        notes = Service(root / "exact-notes", mode=mode)
        body = SearchQuery("needle-only-one-claim", ("notes",))
        exact = notes.search(body)
        assert exact.total_count == 1
        assert (
            exact.hits[0].authoritative_summary["claim"]["provenance"]["coordinate"]
            == spec["notes_coordinate"]
        )
        reports = notes.search(SearchQuery(spec["notes_target"], ("notes",)))
        assert reports.total_count == 2
        assert (
            sum(hit.authoritative_summary["note_retained"] for hit in reports.hits) == 1
        )
        notes.rebuild_search(("notes",))
        assert notes.search(body).hits == exact.hits
        damaged = root / "bad-notes"
        shutil.copytree(root / "exact-notes", damaged)
        mutate(
            damaged / "core.sqlite3",
            "ref_retained_notes",
            "body=zeroblob(length(body))",
        )
        refuses(
            lambda: Service(damaged, mode=mode).search(body),
            {"AUTHORITATIVE_CORRUPTION"},
        )
        assert (damaged / "p1-recovery-stop.json").exists()
        checks.append("exact_claim_notes_index_and_corruption")
    else:
        from repo_catalog.domain.p1_context import ResourceKey

        resource = service.get_context_resource(
            ResourceKey(*spec["resource"]), include_text=True
        )
        assert resource.repository_relations and resource.core_dependencies
        assert all(
            not dependency.available for dependency in resource.core_dependencies
        )
        assert all(hit.authoritative_summary for hit in response.hits)
        checks.append("context_provenance_unresolved_core_references")

    damaged = fresh("damaged-authority")
    mutate(
        damaged / path.name,
        "scalar_claims" if role == "core" else "text_bodies",
        "value='not-json'" if role == "core" else "text_value='tampered'",
    )
    damage_hash = hashlib.sha256((damaged / path.name).read_bytes()).hexdigest()
    damaged_service = Service(damaged, mode=mode)
    refuses(lambda: damaged_service.search(object()), {"INVALID_QUERY"})
    assert not (damaged / "p1-recovery-stop.json").exists()
    refuses(lambda: damaged_service.search(query), {"AUTHORITATIVE_CORRUPTION"})
    assert (damaged / "p1-recovery-stop.json").exists()
    assert hashlib.sha256((damaged / path.name).read_bytes()).hexdigest() == damage_hash
    refuses(
        lambda: damaged_service.search(query),
        {"RECOVERY_STOP", "RECOVERY_REQUIRED", "AUTHORITATIVE_CORRUPTION"},
    )
    checks.append("caller_before_corruption_durable_catalog_stop_no_repair")

    # Stop after authority reconstruction, and after all snapshot cleanup.
    for phase in ("during", "cleanup"):
        stopped = fresh("stop-" + phase)
        target = Service(stopped, mode=mode)
        if phase == "during":
            original = target._extract_documents

            def stopping(*args, **kwargs):
                result = original(*args, **kwargs)
                persist_catalog_stop(stopped, "synthetic search in-flight stop")
                return result

            fence = patch.object(target, "_extract_documents", stopping)
        else:
            original = target._open_snapshot

            @contextmanager
            def stopping(*args, **kwargs):
                with original(*args, **kwargs) as snapshot:
                    yield snapshot
                persist_catalog_stop(stopped, "synthetic search cleanup stop")

            fence = patch.object(target, "_open_snapshot", stopping)
        with fence:
            refuses(
                lambda: target.search(query),
                {"RECOVERY_STOP", "RECOVERY_REQUIRED", "AUTHORITATIVE_CORRUPTION"},
            )
    checks.append("inflight_and_post_cleanup_completion_fences")

    # Explicit single authority ignores opaque other files; auto/paired refuse
    # unavailable necessary integration instead of silently downgrading.
    opaque = fresh("opaque-other")
    (opaque / (other + ".sqlite3")).write_bytes(b"opaque optional authority")
    assert Service(opaque, mode=mode).search(query).hits == response.hits
    refuses(lambda: Service(opaque).search(query), {"MISSING_CAPABILITY"})
    refuses(
        lambda: Service(catalog, mode="paired").search(query), {"MISSING_CAPABILITY"}
    )
    checks.append("explicit_scope_opaque_other_and_paired_refusal")

    wrong_modules = (
        "repo_catalog.application." + other + "_query",
        "repo_catalog.application." + other + "_search",
        "repo_catalog.adapters.sqlite.search_" + other,
        "repo_catalog.domain.p1_" + other,
        "repo_catalog.application.paired_search",
    )
    assert not any(name in sys.modules for name in wrong_modules), wrong_modules
    origins = {}
    for name, module in tuple(sys.modules.items()):
        if name == "repo_catalog" or name.startswith("repo_catalog."):
            for location in getattr(module, "__path__", ()):
                assert Path(location).resolve().is_relative_to(installed), (
                    name,
                    location,
                )
            filename = getattr(module, "__file__", None)
            if filename:
                origin = Path(filename).resolve()
                assert origin.is_relative_to(installed), (name, origin)
                relative = origin.relative_to(installed).as_posix()
                assert relative in owners, relative
                origins[name] = {"path": str(origin), "owner": owners[relative]}
    checks.append("all_loaded_origins_single_owner_no_wrong_authority_imports")
    Path(output).write_text(
        json.dumps(
            {
                "result": "passed",
                "checks": checks,
                "role": role,
                "installed_distributions": sorted(distributions),
                "origins": origins,
                "authority_sha256": digest,
                "python": sys.version,
                "sqlite": sqlite3.sqlite_version,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main(sys.argv[1])
