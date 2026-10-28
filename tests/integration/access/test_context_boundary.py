"""Real P1/P3/P5/P6 boundaries: Context facts survive; Access input does not."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.acquisition import ProviderAcquisition
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.acquisition import (
    ProviderIntakeBatch,
    ProviderRegistration,
    RepositoryRegistration,
    SourceRegistration,
)
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.context_registration import (
    RegistrationError,
)
from repo_catalog.domain.exchange import (
    ExchangeError,
    ExchangeSelectionScope,
    decode_package,
)
from repo_catalog.domain.p1_context import (
    FieldCandidate,
    FieldClock,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.p1_core import Provenance, RepositoryClaim
from repo_catalog.domain.production_context import ContextError
from tests.support.context_admission import fixture_transaction

REPO = "750e8400-e29b-41d4-a716-446655440000"
SERVICE = "550e8400-e29b-41d4-a716-446655440000"
SOURCE = "650e8400-e29b-41d4-a716-446655440000"
PROV = canonical({"source": "provider.example", "evidence": "observation-1"})


def registration_grants(*resources):
    """Only the synthetic catalog registration coordinates and named Resources."""
    return DependencySet(
        resources=resources,
        repositories={REPO},
        sources={SOURCE},
        source_repository_pairs={(SOURCE, REPO)},
        provider_registrations={SERVICE},
    )


def catalog(path, *, core=True, context=True):
    path.mkdir()
    instance = str(uuid4())
    for role in (
        (("core",) if core else ())
        + (("context",) if context else ())
        + ("operational",)
    ):
        p1_schema.initialize(path / f"{role}.sqlite3", role, REPO, instance)
    if context:
        with fixture_transaction(path, registration_grants()) as ctx:
            ctx.provider(SERVICE, "github", canonical({"tier": "enterprise"}))
            ctx.repository(REPO, canonical({"name": "app", "private": False}))
            ctx.source(SOURCE, SERVICE, canonical({"org": "example"}))
            ctx.associate_source(SOURCE, REPO, PROV)
    return path


@pytest.fixture
def directory(tmp_path):
    return catalog(tmp_path / "catalog")


def raw(path):
    db = sqlite3.connect(path, isolation_level=None)
    p1_schema.register_functions(db)
    db.execute("PRAGMA foreign_keys=ON")
    return db


ROWS = {
    "provider": ("providers", "configuration_json", "service_instance_uuidv4", SERVICE),
    "repository": (
        "repository_context",
        "configuration_json",
        "repository_uuidv4",
        REPO,
    ),
    "source": ("sources", "configuration_json", "source_registration_uuidv4", SOURCE),
    "membership": (
        "source_repositories",
        "attributes_json",
        "source_registration_uuidv4",
        SOURCE,
    ),
}


def write(ctx, kind, data):
    return {
        "provider": lambda: ctx.provider(SERVICE, "github", data),
        "repository": lambda: ctx.repository(REPO, data),
        "source": lambda: ctx.source(SOURCE, SERVICE, data),
        "membership": lambda: ctx.associate_source(SOURCE, REPO, data),
    }[kind]()


@pytest.mark.parametrize("kind", ROWS)
@pytest.mark.parametrize(
    "key",
    [
        "api_url",
        "credential_ref",
        "scope_uuidv4",
        "token",
        "poll_interval_s",
        "metadata",
    ],
)
def test_typed_and_sql_writes_reject_without_mutation_or_stop(directory, kind, key):
    value = canonical({key: "SECRET-CANARY"})
    table, column, identity, key_value = ROWS[kind]
    with fixture_transaction(directory, registration_grants()) as ctx:
        prior = ctx.db.execute(f"SELECT * FROM {table}").fetchall()
        with pytest.raises(RegistrationError):
            write(ctx, kind, value)
        assert ctx.db.execute(f"SELECT * FROM {table}").fetchall() == prior
    db = raw(directory / "context.sqlite3")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                f"UPDATE {table} SET {column}=? WHERE {identity}=?", (value, key_value)
            )
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        db.close()
    assert not (directory / "p1-recovery-stop.json").exists()
    assert not (directory / "access.sqlite3").exists()


@pytest.mark.parametrize("kind", ROWS)
def test_stored_transport_input_stops_on_read_before_repair(directory, kind):
    table, column, identity, key_value = ROWS[kind]
    db = raw(directory / "context.sqlite3")
    db.execute("PRAGMA ignore_check_constraints=ON")
    db.execute(
        f"UPDATE {table} SET {column}=? WHERE {identity}=?",
        (canonical({"token": "SECRET-CANARY"}), key_value),
    )
    db.close()
    with pytest.raises(ContextError, match="AUTHORITATIVE_CORRUPTION") as error:
        with fixture_transaction(directory, registration_grants()) as ctx:
            write(ctx, kind, "{}")
    assert "SECRET-CANARY" not in str(error.value)
    marker = (directory / "p1-recovery-stop.json").read_text()
    assert "SECRET-CANARY" not in marker
    db = raw(directory / "context.sqlite3")
    assert "SECRET-CANARY" in db.execute(f"SELECT {column} FROM {table}").fetchone()[0]
    db.close()


def test_registration_dataclasses_and_tampered_batch_preflight(directory):
    for factory in (
        lambda value: ProviderRegistration(SERVICE, "github", value),
        lambda value: RepositoryRegistration(REPO, value),
        lambda value: SourceRegistration(SOURCE, SERVICE, value),
    ):
        with pytest.raises(RegistrationError):
            factory(canonical({"url": "https://private.example"}))
    other = str(uuid4())
    good = ProviderRegistration(other, "github")
    bad = RepositoryRegistration(REPO)
    object.__setattr__(bad, "configuration_json", canonical({"token": "SECRET"}))
    batch = ProviderIntakeBatch(SERVICE, providers=(good,), repositories=(bad,))
    with fixture_transaction(directory, registration_grants()) as ctx:
        with pytest.raises(RegistrationError):
            ProviderAcquisition(directory).admit_batch(batch, context=ctx)
        assert (
            ctx.db.execute(
                "SELECT 1 FROM providers WHERE service_instance_uuidv4=?", (other,)
            ).fetchone()
            is None
        )


def _resign(data):
    payload = {k: v for k, v in data.items() if k != "digest_sha256"}
    data["digest_sha256"] = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return data


@pytest.mark.parametrize(
    "section", ["providers", "repositories", "sources", "source_repositories"]
)
@pytest.mark.parametrize("mode", ["inside-json", "extra-envelope"])
@pytest.mark.parametrize("context_selected", [True, False])
def test_resigned_exchange_rejects_registration_leaks_before_core_admission(
    directory, section, mode, context_selected
):
    pkg = ExchangeService(directory).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )
    data = pkg.to_dict()
    candidate = "a" * 40
    data["core"]["git_objects"].append({"object_format": "sha1", "full_oid": candidate})
    field = (
        "attributes_json" if section == "source_repositories" else "configuration_json"
    )
    if mode == "inside-json":
        data["context"][section][0][field] = canonical(
            {"credential_ref": "SECRET-CANARY"}
        )
    else:
        data["context"][section][0]["token"] = "SECRET-CANARY"
    data["selection_scope"]["include_context"] = context_selected
    _resign(data)
    with pytest.raises(ExchangeError, match="CONTEXT_REGISTRATION") as error:
        ExchangeService(directory).import_package(
            data, new_request=True, permitted_repository_uuidv4s=(REPO,)
        )
    assert "SECRET-CANARY" not in str(error.value)
    with closing(GitCore(directory / "core.sqlite3")) as core:
        assert not core.sql("SELECT 1 FROM git_objects WHERE full_oid=?", (candidate,))
    assert not (directory / "p1-recovery-stop.json").exists()
    assert not (directory / "access.sqlite3").exists()


def test_reported_urls_and_historical_core_provenance_survive_exchange(
    directory, tmp_path
):
    key = ResourceKey.from_native(SERVICE, "endpoint", "actual-provider-coordinate")
    observed = FieldCandidate(
        key,
        "url",
        canonical("https://reported.example/api"),
        FieldClock("provider.clock", 11),
        PROV,
        12,
    )
    with fixture_transaction(directory, registration_grants(key)) as ctx:
        ctx.resource(key)
        ctx.admit_field(observed)
    with closing(GitCore(directory / "core.sqlite3")) as core:
        core.admit_repository_claim(
            RepositoryClaim(
                REPO,
                "endpoint",
                "ssh://historical.example/repo",
                Provenance("original", "event-1", "endpoint", "decoder", "1"),
            )
        )
    package = ExchangeService(directory).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )
    assert package.format == "git-repo-db/adr0031-exchange-v5"
    target = catalog(tmp_path / "target")
    ExchangeService(target).import_package(
        package,
        new_request=True,
        permitted_repository_uuidv4s=(REPO,),
        grants=registration_grants(key),
    )
    with Context.snapshot(target) as ctx:
        assert ctx.candidates(key, "url") == (observed,)
        assert ctx.source_repositories(SOURCE) == (REPO,)
    with closing(GitCore(target / "core.sqlite3")) as core:
        assert core.sql("SELECT value FROM repository_claims")[0][0] == canonical(
            "ssh://historical.example/repo"
        )
    again = ExchangeService(target).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )
    assert again.context["providers"] == package.context["providers"]
    assert (
        again.context["source_repositories"] == package.context["source_repositories"]
    )
    assert not (target / "access.sqlite3").exists()


@pytest.mark.parametrize("operation", ["export", "providers", "sources"])
def test_read_outputs_recheck_instead_of_sanitizing_invalid_registration(
    directory, operation
):
    db = raw(directory / "context.sqlite3")
    db.execute("PRAGMA ignore_check_constraints=ON")
    db.execute(
        "UPDATE providers SET configuration_json=?",
        (canonical({"api_url": "https://private.example"}),),
    )
    db.close()
    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        if operation == "export":
            ExchangeService(directory).export_package(
                selection=ExchangeSelectionScope(all_selected=True)
            )
        elif operation == "providers":
            ProductionQueryService(directory).list_providers()
        else:
            ProductionQueryService(directory).list_source_views()
    assert (directory / "p1-recovery-stop.json").exists()


def test_context_only_round_trip_and_core_only_paths_need_no_access(tmp_path):
    left = catalog(tmp_path / "left", core=False)
    right = catalog(tmp_path / "right", core=False)
    package = ExchangeService(left).export_package(
        selection=ExchangeSelectionScope(all_selected=True, include_core=False)
    )
    ExchangeService(right).import_package(
        package,
        new_request=True,
        permitted_repository_uuidv4s=(REPO,),
        grants=registration_grants(),
    )
    assert ProductionQueryService(right).list_providers()[0].configuration == {
        "tier": "enterprise"
    }
    with Context.snapshot(right) as ctx:
        assert ctx.source_repositories(SOURCE) == (REPO,)
    core_only = catalog(tmp_path / "core-only", context=False)
    assert (
        ExchangeService(core_only)
        .export_package(selection=ExchangeSelectionScope(all_selected=True))
        .context
        is None
    )
    assert not list(tmp_path.glob("*/access.sqlite3"))


def test_old_wire_version_is_not_reinterpreted(directory):
    raw_package = (
        ExchangeService(directory)
        .export_package(selection=ExchangeSelectionScope(all_selected=True))
        .to_dict()
    )
    raw_package["format"] = "git-repo-db/p5-exchange-v2"
    with pytest.raises(ExchangeError, match="UNSUPPORTED_"):
        decode_package(_resign(raw_package))


def test_no_normalization_no_network_no_settings_import_side_effect(
    directory, monkeypatch
):
    import socket
    import subprocess

    def fail(*args, **kwargs):
        raise AssertionError("unexpected external action")

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    sentinel = directory / "access.sqlite3"
    sentinel.write_bytes(b"must not open or replace an Access store")
    with fixture_transaction(directory, registration_grants()) as ctx:
        ctx.repository(
            REPO,
            canonical({"name": "app", "description": "SSH hosts are discussed here"}),
        )
    ExchangeService(directory).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )
    assert sentinel.read_bytes() == b"must not open or replace an Access store"


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "a"),
        ("name", ""),
        ("git_path", "/srv/日本語/repo"),
        ("endpoint", "https://historical.example/repo"),
        ("object_format", "sha256"),
        ("observation_us", None),
        ("observation_us", 17),
        ("identity_assertion", REPO),
        ("identity_cancellation", REPO),
    ],
)
def test_repository_claim_direct_values_round_trip_without_scalar_tag_decode(
    tmp_path, field, value
):
    left = catalog(tmp_path / "left", context=False)
    right = catalog(tmp_path / "right", context=False)
    claim = RepositoryClaim(
        REPO, field, value, Provenance("reporter", "event", "field", "decoder", "1")
    )
    with closing(GitCore(left / "core.sqlite3")) as core:
        core.admit_repository_claim(claim)
    package = ExchangeService(left).export_package(
        selection=ExchangeSelectionScope(all_selected=True, include_context=False)
    )
    ExchangeService(right).import_package(
        package,
        new_request=True,
        permitted_repository_uuidv4s=(REPO,),
        grants=registration_grants(),
    )
    ExchangeService(right).import_package(
        package,
        new_request=True,
        permitted_repository_uuidv4s=(REPO,),
        grants=registration_grants(),
    )
    with closing(GitCore(right / "core.sqlite3")) as core:
        assert [tuple(row) for row in core.sql("SELECT * FROM repository_claims")] == [
            claim.key
        ]
    reverse = ExchangeService(right).export_package(
        selection=ExchangeSelectionScope(all_selected=True, include_context=False)
    )
    assert reverse.core["repository_claims"] == package.core["repository_claims"]


def test_current_p1_routes_are_explicitly_overridden_and_schema_guarded():
    from scripts.audit_context_registration import check

    assert check()[0] == 25


def test_core_only_export_still_stops_for_invalid_coexisting_context(directory):
    db = raw(directory / "context.sqlite3")
    db.execute("PRAGMA ignore_check_constraints=ON")
    db.execute(
        "UPDATE providers SET configuration_json=?",
        (canonical({"api_url": "https://private.example"}),),
    )
    db.close()
    scope = ExchangeSelectionScope(all_selected=True, include_context=False)
    with pytest.raises(ContextError, match="AUTHORITATIVE_CORRUPTION"):
        ExchangeService(directory).export_package(selection=scope)
    assert (directory / "p1-recovery-stop.json").exists()
    with pytest.raises(Exception, match="RECOVERY_REQUIRED"):
        ExchangeService(directory).export_package(selection=scope)
