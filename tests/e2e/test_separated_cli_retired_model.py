"""Explicit model CLI replacements and retired parser paths stay side-effect free."""

import json
from contextlib import closing
from uuid import uuid4

import httpx
import pytest

from repo_catalog.cli.main import main
from tests.e2e.test_separated_cli import document, run, seed_metadata


@pytest.mark.parametrize(
    "action", ["register", "verify", "trust", "select", "invalidate"]
)
def test_retired_decoder_profile_commands_never_initialize_a_catalog(
    tmp_path, capsys, action
):
    catalog = tmp_path / "absent-catalog"
    with pytest.raises(SystemExit) as failure:
        main(["parser", action, "retired-profile", "--catalog", str(catalog)])
    assert failure.value.code == 2
    capsys.readouterr()
    assert not catalog.exists()
    assert list(tmp_path.iterdir()) == []


def test_retired_http_reparse_never_reads_network_or_changes_existing_authorities(
    tmp_path, capsys, monkeypatch
):
    catalog, *_ = seed_metadata(tmp_path, capsys)
    before = {
        str(path.relative_to(catalog)): path.read_bytes()
        for path in catalog.rglob("*")
        if path.is_file()
    }

    def forbidden(*args, **kwargs):
        pytest.fail("Retired HTTP replay must not perform a network request")

    monkeypatch.setattr(httpx.Client, "request", forbidden)
    with pytest.raises(SystemExit) as failure:
        main(
            [
                "parser",
                "reparse",
                "http-response:" + str(uuid4()),
                "--catalog",
                str(catalog),
            ]
        )
    assert failure.value.code == 2
    capsys.readouterr()
    assert {
        str(path.relative_to(catalog)): path.read_bytes()
        for path in catalog.rglob("*")
        if path.is_file()
    } == before


def test_normal_cli_cancellation_before_repository_assertion_never_activates_an_edge(
    tmp_path, capsys
):
    from repo_catalog.adapters.sqlite.git_repository import GitRepositoryStore
    from repo_catalog.domain.p1_repository import Provenance

    catalog, identity, *_ = seed_metadata(tmp_path, capsys)
    other, relation_id = str(uuid4()), str(uuid4())
    with closing(
        GitRepositoryStore(catalog / "repository.sqlite3")
    ) as repository_store:
        repository_store.admit_repository(other)
    record = {
        "relation_uuidv4": relation_id,
        "entity_kind": "repository",
        "left_repository_uuidv4": identity["repository_uuidv4"],
        "right_repository_uuidv4": other,
        "left_service_instance_uuidv4": None,
        "right_service_instance_uuidv4": None,
        "evidence_json": json.dumps({"reported": "exact assertion"}),
        "asserted_at_us": 100,
    }
    cancellation = {
        "cancellation_uuidv4": str(uuid4()),
        "relation_uuidv4": relation_id,
        "evidence_json": json.dumps({"reported": "cancel first"}),
        "asserted_at_us": 100,
    }

    def admit(kind, value, *, expected=0):
        path = document(
            tmp_path,
            "identity.json",
            {
                "record": value,
                "provenance": Provenance(
                    "reported-local-input", "original-" + kind, "identity", "json", "1"
                ),
            },
        )
        options = ["--entity-kind", "repository"] if kind == "cancellation" else []
        return run(
            capsys,
            "identity",
            kind,
            "--catalog",
            catalog,
            "--scope",
            "repository",
            "--input",
            path,
            *options,
            expected=expected,
        )

    # Invalid observation-shaped report times cannot turn into staged evidence.
    for invalid in (-1, 0):
        refused = admit(
            "cancellation", {**cancellation, "asserted_at_us": invalid}, expected=2
        )
        assert refused["code"] in {"INVALID_INPUT", "INVALID_ARGUMENT"}
    assert admit("cancellation", cancellation) == "accepted"
    status = run(
        capsys, "identity", "status", "--catalog", catalog, "--scope", "repository"
    )
    assert not status["identity_relations"]
    assert len(status["identity_relation_cancellations"]) == 1
    assert not status["active_identity_relations"]
    assert admit("relation", record) == "accepted"
    status = run(
        capsys, "identity", "status", "--catalog", catalog, "--scope", "repository"
    )
    assert len(status["identity_relations"]) == 1
    assert len(status["identity_relation_cancellations"]) == 1
    assert not status["active_identity_relations"]
    assert status["repository_equivalence_closure"] == []
    assert not (catalog / "context.sqlite3").exists()
    assert not (catalog / "access.sqlite3").exists()
