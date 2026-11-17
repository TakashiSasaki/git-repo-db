"""Live HTTP originals/recording are independent of separated domain authority."""

import shutil
from contextlib import closing

import httpx
import pytest

from repo_catalog.adapters.github.transport import GitHubTransport
from repo_catalog.adapters.recording import LocalFileRecorder
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.adapters.sqlite.recovery import SQLiteRecoveryAdapter
from repo_catalog.application import provider_fetch
from repo_catalog.application.context_query import ContextQueryService
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.exchange import ExchangeSelectionScope, encode_package
from repo_catalog.domain.p1_context import ResourceKey, canonical
from repo_catalog.domain.recovery import BackupScope
from tests.integration.p5.conftest import init_catalog_stores
from tests.integration.p5.test_separated_github_fetch import response, setup

OPAQUE = "unmodeled-original-response-sentinel-must-not-enter-domain-authority"
BODY = "modeled Context body\r\nexact text"


@pytest.mark.parametrize(
    "recording", ["disabled", "failing", "archive-all", "archive-selective"]
)
def test_actual_http_intake_and_restoration_do_not_depend_on_original_recording(
    tmp_path, monkeypatch, recording
):
    directory = tmp_path / "catalog"
    document, authorization, admission = setup(directory)
    archive = tmp_path / "optional-original-recording"
    instances, calls, recorded = [], [], []

    class FailingRecorder:
        def record_exchange(self, context, body):
            recorded.append(True)
            raise OSError(OPAQUE)

    def transport(*args, **kwargs):
        if recording == "failing":
            kwargs["recorder"] = FailingRecorder()
        elif recording.startswith("archive-"):
            kwargs["recorder"] = LocalFileRecorder(archive)
        value = GitHubTransport(*args, **kwargs)
        instances.append(value)
        return value

    monkeypatch.setattr(provider_fetch, "GitHubTransport", transport)

    def handle(request):
        calls.append(request.url.path)
        if request.url.path == "/repos/owner/repo":
            return response(
                request,
                {
                    "id": 10,
                    "full_name": "owner/repo",
                    "unmodeled_transport_original": OPAQUE,
                },
            )
        assert request.url.path == "/repos/owner/repo/issues"
        return response(
            request,
            [
                {
                    "id": 20,
                    "number": 1,
                    "title": "modeled title",
                    "body": BODY,
                    "unmodeled_transport_original": OPAQUE,
                    "raw_original": {"body": OPAQUE},
                }
            ],
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        if recording == "failing":
            with pytest.warns(RuntimeWarning, match="recording failed"):
                report = provider_fetch.acquire_github(
                    directory,
                    document,
                    authorization=authorization,
                    admission=admission,
                    client=client,
                )
        else:
            report = provider_fetch.acquire_github(
                directory,
                document,
                authorization=authorization,
                admission=admission,
                client=client,
            )
    assert report.status == "complete" and report.http_attempts == len(calls) == 2
    assert not (directory / "core.sqlite3").exists()
    assert not (directory / "p1-recovery-stop.json").exists()
    if recording == "failing":
        assert len(recorded) == 2
        assert instances[0].recording_diagnostics
        assert all(
            item["code"] == "ARCHIVE_FAILURE"
            for item in instances[0].recording_diagnostics
        )
        assert OPAQUE not in repr(instances[0].recording_diagnostics)
    with closing(connect(directory / "context.sqlite3", "context")) as db:
        identity = tuple(
            db.execute(
                "SELECT repository_uuidv4,catalog_instance_uuidv4 FROM store_identity"
            ).fetchone()
        )
        tables = [
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        assert not {
            "source_inputs",
            "fetch_occurrences",
            "parsed_results",
            "parser_profiles",
            "stored_bytes",
            "payloads",
        } & set(tables)
        for table in tables:
            for row in db.execute(f'SELECT * FROM "{table}"'):
                for value in row:
                    if isinstance(value, str):
                        assert OPAQUE not in value
                    elif isinstance(value, bytes):
                        assert OPAQUE.encode() not in value
        assert db.execute("SELECT count(*) FROM text_bodies").fetchone()[0] == 1
    key = ResourceKey.from_native(document["service_instance_uuidv4"], "issue", "20")
    before = ContextQueryService(directory, mode="context_only").get_context_resource(
        key
    )
    assert before.fields["title"][0].value_json == canonical("modeled title")
    assert set(before.resolved_texts.values()) == {BODY}
    if not recording.startswith("archive-"):
        assert not archive.exists()
        return
    assert list(archive.glob("*.body"))
    shutil.rmtree(archive)
    assert (
        ContextQueryService(directory, mode="context_only").get_context_resource(key)
        == before
    )

    scope = (
        ExchangeSelectionScope(
            include_core=False,
            repository_uuidv4s=(identity[0],),
            object_oids=(),
            resource_keys=(key,),
            source_uuidv4s=(),
        )
        if recording == "archive-selective"
        else ExchangeSelectionScope(include_core=False, all_selected=True)
    )
    package = ExchangeService(directory).export_package(
        selection=scope, exported_at_us=20
    )
    assert package.context is not None and package.core is None
    if recording == "archive-selective":
        assert not scope.all_selected
        assert not package.context["sources"]
        assert not package.context["source_repositories"]
        assert not package.context["source_inventories"]
        assert any(
            ResourceKey(
                row["service_instance_uuidv4"],
                row["resource_kind"],
                row["provider_resource_id"],
            )
            == key
            for row in package.context["resources"]
        )
    assert OPAQUE not in encode_package(package)
    receiver = tmp_path / "receiver"
    init_catalog_stores(
        receiver, repository_uuidv4=identity[0], stores=("context", "operational")
    )
    imported = ExchangeService(receiver).import_package(
        package,
        new_request=True,
        permitted_repository_uuidv4s=(identity[0],),
        authorization=authorization,
        admission=admission,
    )
    assert imported.context_imported
    received = ContextQueryService(receiver, mode="context_only").get_context_resource(
        key
    )
    assert (
        received.fields == before.fields
        and received.resolved_texts == before.resolved_texts
    )

    # Paired backup is explicitly initialized only for this later operation.
    initialize(directory / "core.sqlite3", "core", *identity)
    adapter = SQLiteRecoveryAdapter()
    backup = tmp_path / "verified-backup"
    assert adapter.create_consistent_backup(
        directory, backup, BackupScope.PAIRED
    ).verified_clean
    restored = tmp_path / "restored"
    assert adapter.restore_backup(backup, restored, identity[0]).revalidated_clean
    recovered = ContextQueryService(restored, mode="context_only").get_context_resource(
        key
    )
    assert (
        recovered.fields == before.fields
        and recovered.resolved_texts == before.resolved_texts
    )
    assert not (restored / archive.name).exists()
