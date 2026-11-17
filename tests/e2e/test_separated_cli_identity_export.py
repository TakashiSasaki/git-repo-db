"""Service identity Exchange requires an explicit, separate read authority."""

import json
from uuid import uuid4

import pytest

from repo_catalog.domain.context_admission import AdmissionSelection, DependencySet
from repo_catalog.domain.exchange import ExchangeSelectionScope
from repo_catalog.domain.shared_values import Provenance
from tests.e2e.test_separated_cli import document, init, run


@pytest.fixture
def service_identity(tmp_path, capsys):
    source = tmp_path / "source"
    init(capsys, source, "context")
    init(capsys, source, "operational")
    left, right, relation = str(uuid4()), str(uuid4()), str(uuid4())
    grants = DependencySet(
        provider_registrations=frozenset({left, right}),
        identity_assertions=frozenset({relation}),
    )
    credential = document(
        tmp_path,
        "exact-authority.json",
        {"grants": grants, "selection": AdmissionSelection(all_selected=True)},
    )
    for endpoint in (left, right):
        payload = document(tmp_path, "provider.json", {"args": [endpoint, "github"]})
        run(
            capsys,
            "context",
            "provider",
            "--catalog",
            source,
            "--input",
            payload,
            "--authority",
            credential,
        )
    record = {
        "relation_uuidv4": relation,
        "entity_kind": "service",
        "left_repository_uuidv4": None,
        "right_repository_uuidv4": None,
        "left_service_instance_uuidv4": left,
        "right_service_instance_uuidv4": right,
        "evidence_json": '{"kind":"explicit-reported-equivalence"}',
        "asserted_at_us": 10,
    }
    payload = document(
        tmp_path,
        "identity.json",
        {
            "record": record,
            "provenance": Provenance(
                "explicit-input", relation, "service-identity", "typed-json", "1"
            ),
        },
    )
    assert (
        run(
            capsys,
            "identity",
            "relation",
            "--catalog",
            source,
            "--scope",
            "context",
            "--input",
            payload,
            "--authority",
            credential,
        )
        == "accepted"
    )
    selection = document(
        tmp_path,
        "selection.json",
        ExchangeSelectionScope(include_core=False, all_selected=True),
    )
    return source, credential, selection, record, grants


@pytest.mark.parametrize("missing", ["authority", "target", "endpoint", "local-write"])
def test_normal_cli_service_identity_export_refuses_missing_read_grants(
    service_identity, tmp_path, capsys, monkeypatch, missing
):
    source, exact, selection, record, grants = service_identity
    options = []
    if missing == "local-write":
        import repo_catalog.application.identity_export as export
        from repo_catalog.domain.context_admission import create_local_admission_service

        def wrong_authority(**kwargs):
            return create_local_admission_service("exchange_export", **kwargs)

        monkeypatch.setattr(export, "create_identity_export_authority", wrong_authority)
        options = ["--authority", exact]
    elif missing != "authority":
        denied = DependencySet(
            provider_registrations=grants.provider_registrations
            if missing == "target"
            else frozenset({record["left_service_instance_uuidv4"]}),
            identity_assertions=frozenset()
            if missing == "target"
            else grants.identity_assertions,
        )
        options = [
            "--authority",
            document(
                tmp_path,
                "denied-authority.json",
                {"grants": denied, "selection": AdmissionSelection(all_selected=True)},
            ),
        ]
    output = tmp_path / "denied-package.json"
    error = run(
        capsys,
        "exchange",
        "export",
        "--catalog",
        source,
        "--selection",
        selection,
        "--output",
        output,
        *options,
        expected=2,
    )
    assert error["code"] == "PERMISSION_DENIED"
    assert not output.exists()
    assert not (source / "core.sqlite3").exists()
    assert not (source / "p1-recovery-stop.json").exists()


def test_normal_cli_service_identity_read_authority_exports_and_imports_originals(
    service_identity, tmp_path, capsys
):
    source, credential, selection, record, grants = service_identity
    output = tmp_path / "package.json"
    result = run(
        capsys,
        "exchange",
        "export",
        "--catalog",
        source,
        "--selection",
        selection,
        "--authority",
        credential,
        "--output",
        output,
    )
    assert result["package_id"] and output.is_file()
    original = run(
        capsys, "identity", "status", "--scope", "context", "--catalog", source
    )
    target = tmp_path / "target"
    init(capsys, target, "context")
    init(capsys, target, "operational")
    run(
        capsys,
        "exchange",
        "import",
        "--catalog",
        target,
        "--selection",
        selection,
        "--authority",
        credential,
        "--input",
        output,
        "--new-request",
    )
    received = run(
        capsys, "identity", "status", "--scope", "context", "--catalog", target
    )
    for key in (
        "identity_relations",
        "active_identity_relations",
        "service_equivalence_closure",
    ):
        assert received[key] == original[key]
    assert not (target / "core.sqlite3").exists()
    assert record["relation_uuidv4"] in json.dumps(received)
