"""Ordinary command entry exercises separated authorities without legacy Stores."""

import base64
import dataclasses
import hashlib
import json
from uuid import uuid4

import pytest

from repo_catalog.cli.main import main


def wire(value):
    if dataclasses.is_dataclass(value):
        return {
            "$type": type(value).__name__,
            "fields": {
                f.name: wire(getattr(value, f.name))
                for f in dataclasses.fields(value)
                if f.init and not f.name.startswith("_")
            },
        }
    if isinstance(value, bytes):
        return {"$bytes": base64.b64encode(value).decode()}
    if isinstance(value, (tuple, list, frozenset)):
        return [wire(v) for v in value]
    if isinstance(value, dict):
        return {k: wire(v) for k, v in value.items()}
    return value


def document(tmp_path, name, value):
    path = tmp_path / name
    path.write_text(json.dumps(wire(value)))
    return str(path)


def run(capsys, *args, expected=0):
    result = main([str(arg) for arg in args])
    captured = capsys.readouterr()
    assert result == expected, captured
    return json.loads(captured.out if result == 0 else captured.err)


def init(capsys, catalog, scope="core", repository=None):
    options = [] if repository is None else ["--repository", repository]
    return run(capsys, "init", "--scope", scope, "--catalog", catalog, *options)


def test_init_requires_explicit_role_and_does_not_create_defaults(tmp_path, capsys):
    catalog = tmp_path / "catalog"
    with pytest.raises(SystemExit) as failure:
        main(["init", "--catalog", str(catalog)])
    assert failure.value.code == 2
    assert not catalog.exists()
    capsys.readouterr()
    result = init(capsys, catalog)
    assert result["created"] == ["core"]
    assert sorted(path.name for path in catalog.glob("*.sqlite3")) == ["core.sqlite3"]
    before = (catalog / "core.sqlite3").read_bytes()
    assert init(capsys, catalog)["reused"] == ["core"]
    assert (catalog / "core.sqlite3").read_bytes() == before
    assert init(capsys, catalog, "paired")["created"] == ["context"]
    assert not (catalog / "operational.sqlite3").exists()
    assert not (catalog / "search.sqlite3").exists()


@pytest.mark.parametrize("old_format", ["not_sqlite", "sqlite_wrong_schema"])
def test_init_rejects_existing_legacy_or_mismatched_identity_unchanged(
    tmp_path, capsys, old_format
):
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    path = catalog / "core.sqlite3"
    if old_format == "not_sqlite":
        path.write_bytes(b"not a separated SQLite database")
    else:
        import sqlite3

        db = sqlite3.connect(path)
        try:
            db.execute("CREATE TABLE legacy_data(value TEXT)")
            db.execute("INSERT INTO legacy_data VALUES('preserve old data')")
            db.commit()
        finally:
            db.close()
    before = path.read_bytes()
    # Invalid DB errors are structured and must never become a conversion.
    assert run(capsys, "init", "--scope", "paired", "--catalog", catalog, expected=2)
    assert path.read_bytes() == before
    assert not (catalog / "context.sqlite3").exists()


def seed_metadata(tmp_path, capsys):
    from repo_catalog.domain.git_acquisition import GitMetadataInput
    from repo_catalog.domain.p1_core import OID, NativeObject, native_object_oid

    catalog = tmp_path / "catalog"
    identity = init(capsys, catalog)
    init(capsys, catalog, "operational")
    fmt = "sha1"
    tree_body = b"100644 file\0" + bytes.fromhex("1" * 40)
    tree = OID(fmt, native_object_oid(fmt, "tree", tree_body))
    commit_body = (
        f"tree {tree.object_oid}\nauthor Test <test@example.test> 0 +0000\ncommitter Test <test@example.test> 0 +0000\n\nmessage\n"
    ).encode()
    commit = OID(fmt, native_object_oid(fmt, "commit", commit_body))
    unit = GitMetadataInput(
        identity["repository_uuidv4"],
        str(uuid4()),
        str(uuid4()),
        "local-test",
        1,
        native_objects=tuple(
            NativeObject(oid, kind, body, len(body), hashlib.sha256(body).hexdigest())
            for oid, kind, body in (
                (tree, "tree", tree_body),
                (commit, "commit", commit_body),
            )
        ),
    )
    input_path = document(tmp_path, "metadata.json", unit)
    result = run(
        capsys,
        "acquire",
        "git-metadata",
        "--catalog",
        catalog,
        "--input",
        input_path,
        "--new-request",
    )
    assert result["retained_objects"]
    return catalog, identity, tree, commit, unit


def test_acquire_history_tree_diff_raw_paths_and_search(tmp_path, capsys):
    catalog, _, tree, commit, _ = seed_metadata(tmp_path, capsys)
    result = run(
        capsys, "query", "log", "--catalog", catalog, "--object-oid", commit.object_oid
    )
    assert result["status"] == "complete"
    assert result["items"][0]["object_oid"] == list(commit.key)
    result = run(
        capsys, "query", "tree", "--catalog", catalog, "--object-oid", tree.object_oid
    )
    assert result["items"][0]["path"] == {"$bytes": "ZmlsZQ=="}
    assert result["items"][0]["object_oid"] == "1" * 40
    result = run(
        capsys,
        "query",
        "path",
        "--catalog",
        catalog,
        "--object-oid",
        commit.object_oid,
        "--path-b64",
        "ZmlsZQ==",
    )
    assert len(result["items"]) == 1
    assert (
        run(
            capsys,
            "query",
            "diff",
            "--catalog",
            catalog,
            "--left",
            commit.object_oid,
            "--right",
            tree.object_oid,
        )["items"]
        == []
    )
    result = run(
        capsys,
        "query",
        "git-object",
        "--catalog",
        catalog,
        "--format",
        "sha1",
        "--object-oid",
        commit.object_oid,
        "--include-bytes",
    )
    assert result["retained_bytes"]["verified"]
    run(capsys, "query", "search", "--catalog", catalog, "--query", "message")
    assert not (catalog / "search.sqlite3").exists()


def test_backup_stop_salvage_fresh_restore_and_activation(tmp_path, capsys):
    catalog, identity, _, _, _ = seed_metadata(tmp_path, capsys)
    backup = tmp_path / "backup"
    result = run(
        capsys,
        "recovery",
        "backup",
        "--scope",
        "git_only",
        "--catalog",
        catalog,
        "--output",
        backup,
    )
    assert result["verified_clean"]
    run(
        capsys,
        "recovery",
        "stop",
        "--scope",
        "git_only",
        "--catalog",
        catalog,
        "--reason",
        "operator diagnosis",
    )
    assert run(
        capsys, "recovery", "status", "--scope", "git_only", "--catalog", catalog
    )["stopped"]
    run(capsys, "query", "status", "--catalog", catalog, expected=2)
    salvage = tmp_path / "salvage.jsonl"
    run(
        capsys,
        "recovery",
        "salvage",
        "--scope",
        "git_only",
        "--catalog",
        catalog,
        "--output",
        salvage,
    )
    fresh = tmp_path / "fresh"
    assert run(
        capsys,
        "recovery",
        "restore",
        "--scope",
        "git_only",
        "--catalog",
        fresh,
        "--input",
        backup,
        "--repository",
        identity["repository_uuidv4"],
    )["revalidated_clean"]
    run(
        capsys,
        "recovery",
        "merge",
        "--scope",
        "git_only",
        "--catalog",
        fresh,
        "--input",
        salvage,
    )
    locator = tmp_path / "active.json"
    run(
        capsys,
        "recovery",
        "activate",
        "--scope",
        "git_only",
        "--catalog",
        fresh,
        "--output",
        locator,
    )
    assert locator.is_symlink()
    assert locator.resolve() == fresh.resolve()
    assert not (fresh / "operational.sqlite3").exists()
    assert not (fresh / "search.sqlite3").exists()


def test_context_registration_requires_finite_authority_and_access_is_separate(
    tmp_path, capsys
):
    from repo_catalog.domain.access_registry import AccessScope
    from repo_catalog.domain.context_admission import AdmissionSelection, DependencySet

    service = str(uuid4())
    context = tmp_path / "context"
    init(capsys, context, "context")
    grant = document(
        tmp_path,
        "authority.json",
        {
            "grants": DependencySet(provider_registrations=frozenset({service})),
            "selection": AdmissionSelection(all_selected=True),
        },
    )
    payload = document(tmp_path, "provider.json", {"args": [service, "github", "{}"]})
    run(
        capsys,
        "context",
        "provider",
        "--catalog",
        context,
        "--authority",
        grant,
        "--input",
        payload,
    )
    access = tmp_path / "access"
    init(capsys, access, "access")
    scope = AccessScope(str(uuid4()), "local")
    payload = document(tmp_path, "scope.json", {"args": [scope]})
    run(
        capsys,
        "access",
        "register-scope",
        "--access-db",
        access / "access.sqlite3",
        "--input",
        payload,
    )
    assert not (context / "access.sqlite3").exists()
    assert not (access / "context.sqlite3").exists()


def test_exchange_core_roundtrip_has_explicit_selection(tmp_path, capsys):
    from repo_catalog.domain.exchange import ExchangeSelectionScope

    catalog, identity, _, commit, _ = seed_metadata(tmp_path, capsys)
    scope = document(
        tmp_path,
        "selection.json",
        ExchangeSelectionScope(all_selected=True, include_context=False),
    )
    package = tmp_path / "package.json"
    run(
        capsys,
        "exchange",
        "export",
        "--catalog",
        catalog,
        "--selection",
        scope,
        "--output",
        package,
    )
    receiver = tmp_path / "receiver"
    init(capsys, receiver, repository=identity["repository_uuidv4"])
    init(capsys, receiver, "operational")
    run(
        capsys,
        "exchange",
        "import",
        "--catalog",
        receiver,
        "--selection",
        scope,
        "--input",
        package,
        "--new-request",
        "--permit-repository",
        identity["repository_uuidv4"],
    )
    result = run(
        capsys,
        "query",
        "git-object",
        "--catalog",
        receiver,
        "--format",
        "sha1",
        "--object-oid",
        commit.object_oid,
    )
    assert result["metadata_retained"]


def test_operations_cancel_resume_preserves_existing_work_and_reparse(tmp_path, capsys):
    from dataclasses import replace

    catalog, _, _, commit, unit = seed_metadata(tmp_path, capsys)
    request_origin, request = str(uuid4()), str(uuid4())
    payload = document(
        tmp_path,
        "reparse.json",
        {"unit": replace(unit, native_objects=()), "objects": [commit]},
    )
    result = run(
        capsys,
        "reparse",
        "--catalog",
        catalog,
        "--input",
        payload,
        "--request-origin",
        request_origin,
        "--request",
        request,
        "--new-request",
    )
    assert result["admitted_objects"]
    before = run(capsys, "operations", "list", "--catalog", catalog)
    stopped = run(
        capsys,
        "operations",
        "cancel",
        "--catalog",
        catalog,
        "--request-origin",
        request_origin,
        "--request",
        request,
    )
    assert stopped["state"] == "stopped"
    resumed = run(
        capsys,
        "operations",
        "resume",
        "--catalog",
        catalog,
        "--request-origin",
        request_origin,
        "--request",
        request,
    )
    assert resumed["state"] == "open"
    after = run(capsys, "operations", "list", "--catalog", catalog)
    assert len(before["requests"]) == len(after["requests"])


def test_no_ordinary_file_archive_or_legacy_fallback(tmp_path, capsys):
    with pytest.raises(SystemExit) as failure:
        main(["content", "read", "--content-id", "1"])
    assert failure.value.code == 2
    assert not list(tmp_path.iterdir())


def test_cache_gc_preserves_resumable_work_and_never_follows_links(tmp_path, capsys):
    catalog, _, _, _, _ = seed_metadata(tmp_path, capsys)
    cache = catalog / "cache"
    cache.mkdir()
    protected = cache / "protected.cache"
    protected.write_bytes(b"permitted metadata cache")
    policy = ["--max-cache-bytes", 1024 * 1024, "--cache-ttl-seconds", 0]
    result = run(
        capsys, "operations", "cache-gc", "--catalog", catalog, *policy, "--apply"
    )
    assert result["protected_requests"] > 0
    assert protected.is_file()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "evidence").write_bytes(b"must survive")
    (cache / "outside").symlink_to(outside, target_is_directory=True)
    listed = run(capsys, "operations", "list", "--catalog", catalog)
    original = listed["requests"][0]
    request_options = [
        "--request-origin",
        original["request_origin_uuidv4"],
        "--request",
        original["request_uuidv4"],
    ]
    details = run(capsys, "operations", "show", "--catalog", catalog, *request_options)
    exact = [
        *request_options,
        "--attempt",
        details["attempt_records"][0]["attempt_uuidv4"],
    ]
    managed = cache / "managed.git"
    managed.mkdir()
    (managed / "HEAD").write_bytes(b"ref: refs/heads/main\n")
    path_hex = b"managed.git".hex()
    registered = run(
        capsys,
        "operations",
        "cache-register",
        "--catalog",
        catalog,
        *policy,
        *exact,
        "--cache-path-hex",
        path_hex,
        "--last-used-us",
        1,
    )
    assert registered["path_hex"] == path_hex
    reserved = run(
        capsys,
        "operations",
        "cache-reserve",
        "--catalog",
        catalog,
        *policy,
        *exact,
        "--reservation-bytes",
        1024,
    )
    assert reserved["reserved_bytes"] == 1024
    assert (
        run(
            capsys, "operations", "cache-monitor", "--catalog", catalog, *policy, *exact
        )["reserved_bytes"]
        == 1024
    )
    run(capsys, "operations", "cache-release", "--catalog", catalog, *policy, *exact)
    assert (
        run(
            capsys,
            "operations",
            "cache-reuse",
            "--catalog",
            catalog,
            *policy,
            "--cache-path-hex",
            path_hex,
        )["availability"]
        == "reuse_candidate"
    )
    active = run(
        capsys, "operations", "cache-gc", "--catalog", catalog, *policy, "--apply"
    )
    assert active["protected_requests"] and managed.is_dir()
    for request in listed["requests"]:
        run(
            capsys,
            "operations",
            "complete",
            "--catalog",
            catalog,
            "--request-origin",
            request["request_origin_uuidv4"],
            "--request",
            request["request_uuidv4"],
        )
    preview = run(capsys, "operations", "cache-gc", "--catalog", catalog, *policy)
    assert path_hex in preview["candidates"] and preview["removed"] == []
    assert managed.is_dir()
    run(capsys, "operations", "cache-gc", "--catalog", catalog, *policy, "--apply")
    assert not managed.exists()
    assert protected.is_file()  # Unregistered/orphan input is preserved.
    assert (outside / "evidence").read_bytes() == b"must survive"


def test_provider_intake_and_paired_filtering_preserve_documents(tmp_path, capsys):
    from repo_catalog.domain.acquisition import make_provenance
    from repo_catalog.domain.context_admission import AdmissionSelection, DependencySet
    from repo_catalog.domain.p1_context import ResourceKey
    from repo_catalog.domain.provider_acquisition import (
        ProviderIntakeBatch,
        ProviderIssueIntake,
        ProviderRegistration,
    )

    catalog = tmp_path / "catalog"
    init(capsys, catalog, "paired")
    init(capsys, catalog, "operational")
    service = str(uuid4())
    issue = ResourceKey.from_native(service, "issue", "1001")
    grants = DependencySet(
        resources=frozenset({issue}), provider_registrations=frozenset({service})
    )
    auth = document(
        tmp_path,
        "authority.json",
        {"grants": grants, "selection": AdmissionSelection(all_selected=True)},
    )
    batch = ProviderIntakeBatch(
        service,
        providers=(ProviderRegistration(service),),
        issues=(
            ProviderIssueIntake(
                {
                    "id": 1001,
                    "title": "Query bug",
                    "state": "open",
                    "body": "Preserved document",
                },
                1,
                make_provenance("local-provider", "issue-one"),
            ),
        ),
    )
    payload = document(tmp_path, "batch.json", batch)
    run(
        capsys,
        "acquire",
        "provider",
        "--catalog",
        catalog,
        "--input",
        payload,
        "--authority",
        auth,
    )
    request = document(
        tmp_path,
        "filter.json",
        {
            "kwargs": {
                "resource_kind": "issue",
                "field_filters": {"state": "open"},
                "text_literal": "Preserved",
            }
        },
    )
    result = run(capsys, "query", "resources", "--catalog", catalog, "--input", request)
    assert len(result["items"]) == 1
    assert "Preserved document" in result["items"][0]["resolved_texts"].values()
    payload = document(tmp_path, "paired.json", {"provider_batch": batch})
    run(
        capsys,
        "acquire",
        "paired",
        "--catalog",
        catalog,
        "--input",
        payload,
        "--authority",
        auth,
    )
    result = run(
        capsys,
        "query",
        "paired-resource",
        "--catalog",
        catalog,
        "--service",
        service,
        "--kind",
        "issue",
        "--id",
        issue.provider_resource_id,
    )
    assert result


def test_metadata_digest_uses_actual_permitted_bytes(tmp_path, capsys):
    catalog, _, _, commit, unit = seed_metadata(tmp_path, capsys)
    body = next(item.body for item in unit.native_objects if item.object_oid == commit)
    result = run(
        capsys,
        "query",
        "digest",
        "--catalog",
        catalog,
        "--algorithm",
        "raw-sha256",
        "--digest",
        hashlib.sha256(body).hexdigest(),
    )
    assert result["items"] == [
        {
            "object_oid": list(commit.key),
            "algorithm": "raw-sha256",
            "digest": hashlib.sha256(body).hexdigest(),
            "byte_length": len(body),
            "verified": True,
        }
    ]
    assert (
        run(
            capsys,
            "query",
            "digest",
            "--catalog",
            catalog,
            "--algorithm",
            "raw-sha1",
            "--digest",
            commit.object_oid,
        )["items"]
        == []
    )


def test_metadata_only_paths_remain_attributed_and_do_not_invent_byte_verification(
    tmp_path, capsys
):
    from repo_catalog.domain.git_acquisition import GitMetadataInput
    from repo_catalog.domain.p1_core import (
        OID,
        Provenance,
        RelationGroup,
        RelationMember,
        ScalarClaim,
    )

    catalog = tmp_path / "catalog"
    identity = init(capsys, catalog)
    init(capsys, catalog, "operational")
    tree, target = OID("sha1", "2" * 40), OID("sha1", "1" * 40)
    provenance = Provenance(
        "reported-source", "original-observation", "tree", "decoder", "1"
    )
    unit = GitMetadataInput(
        identity["repository_uuidv4"],
        str(uuid4()),
        str(uuid4()),
        "reported-source",
        1,
        nominal_objects=(tree, target),
        scalar_claims=(ScalarClaim(tree, "type", "tree", provenance),),
        relation_groups=(
            RelationGroup(
                tree,
                "tree_entries",
                "reported-tree",
                "complete",
                (RelationMember(("100644", "66696c65"), target),),
                provenance,
            ),
        ),
    )
    payload = document(tmp_path, "reported.json", unit)
    run(
        capsys,
        "acquire",
        "git-metadata",
        "--catalog",
        catalog,
        "--input",
        payload,
        "--new-request",
    )
    result = run(
        capsys, "query", "tree", "--catalog", catalog, "--object-oid", tree.object_oid
    )
    assert result["status"] == "partial"
    assert result["items"][0]["qualification"] == "reported"
    assert result["items"][0]["path"] == {"$bytes": "ZmlsZQ=="}


def test_doctor_verifies_permitted_bytes_without_initializing_optional_stores(
    tmp_path, capsys
):
    catalog, _, _, _, _ = seed_metadata(tmp_path, capsys)
    result = run(
        capsys,
        "doctor",
        "--catalog",
        catalog,
        "--verify-retained",
        "--scope",
        "git_only",
    )
    assert result["retained_authority"]["verified_clean"]
    assert not (catalog / "context.sqlite3").exists()
    assert not (catalog / "search.sqlite3").exists()


def test_notes_reparse_requires_current_receiver_role_proof(tmp_path, capsys):
    from dataclasses import replace

    from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
    from repo_catalog.adapters.sqlite.git_core import GitCore
    from repo_catalog.domain.p1_core import OID, NativeObject, native_object_oid
    from tests.support.ref_notes import admit_fixture_note

    catalog, identity, _, commit, unit = seed_metadata(tmp_path, capsys)
    note_body = b"Reviewed-by: Test\n"
    note = NativeObject(
        OID("sha1", native_object_oid("sha1", "blob", note_body)),
        "blob",
        note_body,
        len(note_body),
        hashlib.sha256(note_body).hexdigest(),
    )
    tree_body = (
        b"100644 "
        + commit.object_oid.encode()
        + b"\0"
        + bytes.fromhex(note.object_oid.object_oid)
    )
    tree = NativeObject(
        OID("sha1", native_object_oid("sha1", "tree", tree_body)),
        "tree",
        tree_body,
        len(tree_body),
        hashlib.sha256(tree_body).hexdigest(),
    )
    core = GitCore(catalog / "core.sqlite3")
    try:
        claim, mapping = admit_fixture_note(
            core,
            identity["repository_uuidv4"],
            tree,
            commit,
            note,
            UnlimitedWorkBudget(),
        )
    finally:
        core.close()
    payload = document(
        tmp_path,
        "note-reparse.json",
        {"unit": replace(unit, native_objects=()), "notes": [[claim, mapping]]},
    )
    run(
        capsys,
        "reparse",
        "--catalog",
        catalog,
        "--input",
        payload,
        "--request-origin",
        str(uuid4()),
        "--request",
        str(uuid4()),
        "--new-request",
    )
    result = run(
        capsys,
        "query",
        "git-object",
        "--catalog",
        catalog,
        "--format",
        "sha1",
        "--object-oid",
        note.object_oid.object_oid,
    )
    assert any(
        c["value"] == ["known", "Reviewed-by: Test\n"]
        for c in result["scalars"]["message"]["alternatives"]
    )
    payload = document(
        tmp_path,
        "unproven-note.json",
        {
            "unit": replace(unit, native_objects=()),
            "notes": [[claim, replace(mapping, note_object_oid=OID("sha1", "1" * 40))]],
        },
    )
    run(
        capsys,
        "reparse",
        "--catalog",
        catalog,
        "--input",
        payload,
        "--request-origin",
        str(uuid4()),
        "--request",
        str(uuid4()),
        "--new-request",
        expected=2,
    )


def test_access_route_configuration_remains_unapproved_and_backup_is_scoped(
    tmp_path, capsys
):
    from repo_catalog.domain.access_connections import (
        AccessPreference,
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

    directory = tmp_path / "access"
    init(capsys, directory, "access")
    database = directory / "access.sqlite3"
    scope, repository = str(uuid4()), str(uuid4())
    native = tmp_path / "native"
    native.mkdir()
    registration = ScopeLocatorRegistration(scope, 1, native.as_uri())
    assignment = AssignmentKey(scope, str(native), "local-file")
    configurations = (
        ("register-scope", AccessScope(scope, "local execution")),
        ("register-locator", registration),
        (
            "configure-scope",
            ScopeExecutionContext(
                scope,
                json.dumps(
                    {
                        "version": 1,
                        "executor_kind": "local",
                        "executor_ref": "local",
                        "identity_view": "user",
                        "path_dialect": "posix",
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                True,
            ),
        ),
        ("bind-repository", RepositoryBinding(scope, str(native), repository, True)),
        (
            "configure-connection",
            ConnectionConfiguration(
                scope,
                "local-file",
                '{"path_dialect":"posix","transport":"file","version":1}',
                True,
            ),
        ),
        ("assign-connection", LocatorConnection(assignment, True)),
        ("set-preference", AccessPreference(repository, assignment)),
    )
    for index, (operation, value) in enumerate(configurations):
        payload = document(tmp_path, f"access-{index}.json", {"args": [value]})
        run(capsys, "access", operation, "--access-db", database, "--input", payload)
    payload = document(tmp_path, "enable-locator.json", {"args": [registration, True]})
    run(
        capsys,
        "access",
        "set-locator-enabled",
        "--access-db",
        database,
        "--input",
        payload,
    )
    result = run(
        capsys,
        "access",
        "review",
        "--access-db",
        database,
        "--repository",
        repository,
        "--scope",
        scope,
    )
    assert result["status"] == "review-only"
    denied = run(
        capsys,
        "access",
        "approve",
        "--access-db",
        database,
        "--repository",
        repository,
        "--scope",
        scope,
        expected=2,
    )
    assert denied["code"] == "LOCAL_TTY_REQUIRED"
    bundle = tmp_path / "access-backup"
    run(capsys, "access", "backup", "--access-db", database, "--destination", bundle)
    result = run(capsys, "access", "inspect", "--bundle", bundle)
    assert result["status"] == "ok"
    assert not (directory / "core.sqlite3").exists()


def test_context_browse_cursor_binds_extra_filters_and_snapshot(tmp_path, capsys):
    from repo_catalog.domain.acquisition import make_provenance
    from repo_catalog.domain.context_admission import AdmissionSelection, DependencySet
    from repo_catalog.domain.p1_context import ResourceKey
    from repo_catalog.domain.provider_acquisition import (
        ProviderIntakeBatch,
        ProviderIssueIntake,
        ProviderRegistration,
    )
    from repo_catalog.domain.query_contracts import PageRequest

    catalog = tmp_path / "context"
    init(capsys, catalog, "context")
    service = str(uuid4())
    keys = frozenset(
        ResourceKey.from_native(service, "issue", str(value)) for value in (1001, 1002)
    )
    auth = document(
        tmp_path,
        "authority.json",
        {
            "grants": DependencySet(
                resources=keys, provider_registrations=frozenset({service})
            ),
            "selection": AdmissionSelection(all_selected=True),
        },
    )
    batch = ProviderIntakeBatch(
        service,
        providers=(ProviderRegistration(service),),
        issues=tuple(
            ProviderIssueIntake(
                {"id": value, "state": "open"},
                value,
                make_provenance("local-provider", str(value)),
            )
            for value in (1001, 1002)
        ),
    )
    payload = document(tmp_path, "batch.json", batch)
    run(
        capsys,
        "acquire",
        "provider",
        "--catalog",
        catalog,
        "--input",
        payload,
        "--authority",
        auth,
    )
    payload = document(
        tmp_path,
        "browse.json",
        {
            "kwargs": {
                "resource_kind": "issue",
                "field_filters": {"state": "open"},
                "page": PageRequest(limit=1),
            }
        },
    )
    result = run(capsys, "query", "resources", "--catalog", catalog, "--input", payload)
    assert result["scan_has_more"]
    payload = document(
        tmp_path,
        "changed-filter.json",
        {
            "kwargs": {
                "resource_kind": "issue",
                "field_filters": {"state": "closed"},
                "page": PageRequest(limit=1, cursor=result["next_cursor"]),
            }
        },
    )
    rejected = run(
        capsys,
        "query",
        "resources",
        "--catalog",
        catalog,
        "--input",
        payload,
        expected=2,
    )
    assert rejected["code"] == "INVALID_CURSOR"
    payload = document(
        tmp_path,
        "next-page.json",
        {
            "kwargs": {
                "resource_kind": "issue",
                "field_filters": {"state": "open"},
                "page": PageRequest(limit=1, cursor=result["next_cursor"]),
            }
        },
    )
    result = run(capsys, "query", "resources", "--catalog", catalog, "--input", payload)
    assert len(result["items"]) == 1
    assert not result["scan_has_more"]


def test_init_refuses_mismatched_identities_before_creating_any_role(tmp_path, capsys):
    from repo_catalog.adapters.sqlite.p1_schema import initialize

    catalog = tmp_path / "catalog"
    init(capsys, catalog)
    before = (catalog / "core.sqlite3").read_bytes()
    run(
        capsys,
        "init",
        "--scope",
        "operational",
        "--catalog",
        catalog,
        "--repository",
        str(uuid4()),
        expected=2,
    )
    assert not (catalog / "operational.sqlite3").exists()
    initialize(catalog / "context.sqlite3", "context", str(uuid4()), str(uuid4()))
    context_before = (catalog / "context.sqlite3").read_bytes()
    run(capsys, "init", "--scope", "paired", "--catalog", catalog, expected=2)
    assert (catalog / "core.sqlite3").read_bytes() == before
    assert (catalog / "context.sqlite3").read_bytes() == context_before
    assert not (catalog / "search.sqlite3").exists()


@pytest.mark.parametrize("role", ["filesystem", "worktrees"])
def test_independent_role_init_only_reuses_its_own_database(tmp_path, capsys, role):
    catalog = tmp_path / role
    init(capsys, catalog, role)
    before = (catalog / (role + ".sqlite3")).read_bytes()
    init(capsys, catalog, role)
    assert (catalog / (role + ".sqlite3")).read_bytes() == before
    assert sorted(path.name for path in catalog.glob("*.sqlite3")) == [
        role + ".sqlite3"
    ]


def test_query_budgets_and_cursor_errors_do_not_enter_recovery(tmp_path, capsys):
    catalog, _, _, _, _ = seed_metadata(tmp_path, capsys)
    result = run(
        capsys,
        "query",
        "git-objects",
        "--catalog",
        catalog,
        "--cursor",
        "malformed",
        expected=2,
    )
    assert result["code"] == "INVALID_CURSOR"
    result = run(
        capsys,
        "query",
        "status",
        "--catalog",
        catalog,
        "--max-sql-steps",
        1,
        expected=2,
    )
    assert result["code"] == "QUERY_BUDGET"
    run(
        capsys,
        "query",
        "status",
        "--catalog",
        catalog,
        "--timeout-seconds",
        "nan",
        expected=2,
    )
    assert not (catalog / "p1-recovery-stop.json").exists()
    assert not (catalog / "search.sqlite3").exists()
