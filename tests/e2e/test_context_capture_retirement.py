"""Real HTTP origins survive affiliation changes and detached selective Exchange."""

import json
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest

from repo_catalog.adapters.github.production_intake import make_document_key
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.context_admission import (
    AdmissionSelection,
    DependencySet,
)
from repo_catalog.domain.exchange import (
    ExchangeSelectionScope,
    decode_package,
    encode_package,
)
from repo_catalog.domain.p1_context import ResourceKey
from tests.e2e.test_separated_cli import document, init, run
from tests.e2e.test_separated_cli_provider_regressions import (
    _http_response,
    _network_cli,
    provider_case,
)
from tests.support.context_admission import fixture_transaction

__all__ = ["provider_case"]


def fetch_request(case, source, repository, sections):
    return {
        "operation": "sync",
        "service_instance_uuidv4": case.service,
        "source_registration_uuidv4": source,
        "request_identity": [str(uuid4()), str(uuid4())],
        "new_request": True,
        "owner": "owner",
        "repository": repository,
        "sections": sections,
        "max_pages": 10,
        "response_bytes": 8192,
        "rest_base_url": "https://api.example.test",
        "graphql_url": "https://api.example.test/graphql",
    }


def admit_package(
    directory, package, grants, selection, tmp_path, capsys, *, expected=0
):
    # Exercise the ordinary CLI's full finite authority-file factory. Source
    # selection permits detached A, but the packet has no A registration row.
    authority_file = document(
        tmp_path,
        "exchange-authority.json",
        {
            "grants": grants,
            "selection": AdmissionSelection(
                resource_keys=grants.resources,
                repository_uuidv4s=frozenset(),
                source_uuidv4s=grants.sources,
                object_oids=frozenset(),
                include_repository=False,
            ),
        },
    )
    selection_file = document(tmp_path, "receive-selection.json", selection)
    package_file = tmp_path / "original-capture-package.json"
    package_file.write_text(encode_package(package))
    return run(
        capsys,
        "exchange",
        "import",
        "--catalog",
        directory,
        "--selection",
        selection_file,
        "--input",
        package_file,
        "--authority",
        authority_file,
        "--new-request",
        expected=expected,
    )


@pytest.mark.parametrize(
    "refreshed_body",
    ["captured in A", "edited in B"],
    ids=["same-value-new-origin", "edited-value-new-origin"],
)
def test_http_original_producer_survives_new_owner_and_detached_exchange_until_real_refresh(
    provider_case,
    tmp_path,
    capsys,
    monkeypatch,
    refreshed_body,
):
    case = provider_case
    second_source, foreign_service = str(uuid4()), str(uuid4())
    repo_a = case.keys["repository"]
    repo_b = ResourceKey.from_native(case.service, "repository", "11")
    issue = case.keys["issue"]
    comment = make_document_key(issue, "issue_comment", "comment", "9")
    # Declared before any response/package: original A may remain an unresolved
    # provenance dependency without registering its Source or Repository later.
    exchange_grants = DependencySet(
        resources={repo_a, repo_b, issue, comment},
        sources={case.source, second_source},
        provider_registrations={case.service},
    )
    # Finite explicit authority is declared before any original HTTP admission.
    case.authority = document(
        tmp_path,
        "capture-authority.json",
        {
            "grants": DependencySet(
                resources={*case.keys.values(), repo_b, comment},
                sources={case.source, second_source},
                provider_registrations={case.service},
            ),
            "selection": AdmissionSelection(all_selected=True),
        },
    )
    stamp = [10_000_000]

    def handle(request):
        path = request.url.path
        repository = "A" if "/owner/A" in path else "B"
        if path == f"/repos/owner/{repository}":
            payload = {
                "id": 10 if repository == "A" else 11,
                "full_name": f"owner/{repository}",
            }
        elif path.endswith("/issues"):
            payload = [
                {
                    "id": 100,
                    "number": 7,
                    "title": "issue",
                    "updated_at": f"2026-10-0{1 if repository == 'A' else 2}T10:00:00Z",
                }
            ]
        elif path.endswith("/pulls"):
            payload = []
        elif path.endswith("/issues/7/comments"):
            payload = [
                {
                    "id": 9,
                    "body": "captured in A" if repository == "A" else refreshed_body,
                    "updated_at": f"2026-10-0{1 if repository == 'A' else 2}T10:00:00Z",
                }
            ]
        else:
            raise AssertionError(path)
        return _http_response(request, payload)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        original_request = fetch_request(
            case, case.source, "A", ["issues", "issue_comments"]
        )
        first, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            original_request,
            clock_us=lambda: stamp[0],
        )
        assert first["status"] == "complete"
        with Context.snapshot(case.directory) as context:
            original = context.candidates(comment, "text_body_sha256")
            assert len(original) == 1
            assert (
                context.read_text(json.loads(original[0].value_json)) == "captured in A"
            )
        evidence = json.loads(original[0].provenance_json)["evidence"]
        assert evidence["source_registration_uuidv4"] == case.source
        assert evidence["service_instance_uuidv4"] == case.service
        assert evidence["resource_path"] == "/repos/owner/A/issues/7/comments"
        assert evidence["request_identity"] == original_request["request_identity"]
        assert evidence["read_origin"]
        assert original[0].observed_at_us == stamp[0]
        # A genuinely later Issue affiliation is not a new read of its child.
        stamp[0] = 20_000_000
        moved, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            fetch_request(case, second_source, "B", ["issues"]),
            clock_us=lambda: stamp[0],
        )
        assert moved["status"] == "complete"
        with Context.snapshot(case.directory) as context:
            assert context.candidates(comment, "text_body_sha256") == original
            roles = context.provider_repository_roles(issue)
            assert {role.scope.provider_repository_id for role in roles} == {
                repo_b.provider_resource_id
            }

        # Omit original Source and Provider Repository registrations deliberately:
        # the captured typed identifiers in provenance remain unresolved reports.
        selection = ExchangeSelectionScope(
            include_repository=False,
            repository_uuidv4s=(),
            object_oids=(),
            resource_keys=(repo_b, issue, comment),
            source_uuidv4s=(second_source,),
            max_depth=0,
        )
        package = ExchangeService(case.directory).export_package(selection=selection)
        package = decode_package(encode_package(package))
        assert package.context is not None
        assert all(
            row["source_registration_uuidv4"] != case.source
            for row in package.context["sources"]
        )
        assert all(
            row["provider_resource_id"] != repo_a.provider_resource_id
            for row in package.context["resources"]
            if row["resource_kind"] == "repository"
        )
        receiver, onward, wrong_source = (
            tmp_path / name for name in ("receiver", "onward", "wrong-source")
        )
        for directory in (receiver, onward, wrong_source):
            init(capsys, directory, "context")
            init(capsys, directory, "operational")
        receive_scope = replace(selection, source_uuidv4s=(case.source, second_source))
        denied = admit_package(
            receiver,
            package,
            replace(exchange_grants, sources=frozenset({second_source})),
            receive_scope,
            tmp_path,
            capsys,
            expected=2,
        )
        assert denied["code"] == "PERMISSION_DENIED"
        with Context.snapshot(receiver) as context:
            assert context.resources() == ()
            assert context.db.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
        admit_package(
            receiver, package, exchange_grants, receive_scope, tmp_path, capsys
        )
        forwarded = ExchangeService(receiver).export_package(selection=selection)
        admit_package(
            onward,
            decode_package(encode_package(forwarded)),
            exchange_grants,
            receive_scope,
            tmp_path,
            capsys,
        )
        # Absence may remain unresolved, but a known incompatible Source row
        # must never be treated as belonging to the captured service.
        with fixture_transaction(
            wrong_source,
            DependencySet(
                sources={case.source},
                provider_registrations={foreign_service},
            ),
        ) as context:
            context.provider(foreign_service, "github")
            context.source(case.source, foreign_service)
        invalid = admit_package(
            wrong_source,
            package,
            exchange_grants,
            receive_scope,
            tmp_path,
            capsys,
            expected=2,
        )
        assert invalid["code"] in {"SOURCE_SERVICE", "UNQUALIFIED_MAPPING"}
        with Context.snapshot(wrong_source) as context:
            assert context.resources() == ()
            assert tuple(
                context.db.execute(
                    "SELECT service_instance_uuidv4 FROM sources WHERE source_registration_uuidv4=?",
                    (case.source,),
                ).fetchone()
            ) == (foreign_service,)
        assert not (wrong_source / "p1-recovery-stop.json").exists()
        for directory in (receiver, onward):
            with Context.snapshot(directory) as context:
                assert context.candidates(comment, "text_body_sha256") == original
                assert (
                    context.read_text(json.loads(original[0].value_json))
                    == "captured in A"
                )
                assert repo_a not in context.resources()
                assert not context.db.execute(
                    "SELECT 1 FROM sources WHERE source_registration_uuidv4=?",
                    (case.source,),
                ).fetchone()
            assert not (directory / "repository.sqlite3").exists()

        stamp[0] = 30_000_000
        refresh_request = fetch_request(
            case, second_source, "B", ["issues", "issue_comments"]
        )
        refreshed, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            refresh_request,
            clock_us=lambda: stamp[0],
        )
        assert refreshed["status"] == "complete"
        with Context.snapshot(case.directory) as context:
            current = context.candidates(comment, "text_body_sha256")
            assert len(current) == 1
            assert (
                context.read_text(json.loads(current[0].value_json)) == refreshed_body
            )
        actual = json.loads(current[0].provenance_json)["evidence"]
        assert actual["source_registration_uuidv4"] == second_source
        assert actual["resource_path"] == "/repos/owner/B/issues/7/comments"
        assert actual["request_identity"] == refresh_request["request_identity"]
        assert actual["read_origin"] != evidence["read_origin"]
        assert current[0].observed_at_us == 30_000_000
        assert current[0].clock.at_us > original[0].clock.at_us
        # Original facts exported above are never reissued with destination origin.
        for directory in (receiver, onward):
            with Context.snapshot(directory) as context:
                assert context.candidates(comment, "text_body_sha256") == original
