"""Four authority-owned identity families survive selective unauthenticated Exchange."""

from contextlib import closing
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.application.identity_export import create_identity_export_authority
from repo_catalog.domain.context_admission import (
    AdmissionRefused,
    AdmissionSelection,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.exchange import (
    ExchangeError,
    ExchangePackage,
    ExchangeSelectionScope,
    decode_package,
    empty_context_section,
    empty_core_section,
    encode_package,
)
from repo_catalog.domain.identity_assertions import identity_record
from repo_catalog.domain.p1_coordination import RequestIdentity
from repo_catalog.domain.p1_core import CoreFailure, Provenance, encode
from tests.integration.p5.conftest import init_catalog_stores


def assertion(kind, endpoints, ident=None):
    value = dict(
        relation_uuidv4=ident or str(uuid4()),
        entity_kind=kind,
        left_repository_uuidv4=None,
        right_repository_uuidv4=None,
        left_service_instance_uuidv4=None,
        right_service_instance_uuidv4=None,
        evidence_json='{ "original whitespace": true }',
        asserted_at_us=None,
    )
    suffix = "repository_uuidv4" if kind == "repository" else "service_instance_uuidv4"
    value["left_" + suffix], value["right_" + suffix] = endpoints
    return value


def cancellation(record):
    return dict(
        cancellation_uuidv4=str(uuid4()),
        relation_uuidv4=record["relation_uuidv4"],
        evidence_json='{"reported":"cancel"}',
        asserted_at_us=42,
    )


def provenance(record):
    return Provenance(
        "original-fixture-issuer",
        record.get("cancellation_uuidv4", record["relation_uuidv4"]),
        "identity-evidence",
        "fixture",
        "1",
    )


def wire(kind, record):
    row = dict(
        relation_uuidv4=record["relation_uuidv4"],
        record_json=identity_record(kind, record),
        provenance=provenance(record).encoded,
    )
    if kind == "cancellation":
        row["cancellation_uuidv4"] = record["cancellation_uuidv4"]
    return row


def authority(operation, endpoints=(), targets=()):
    grants = DependencySet(
        provider_registrations=endpoints, identity_assertions=targets
    )
    if operation == "exchange_export":
        auth, admission, _ = create_identity_export_authority(
            grants=grants, selection=AdmissionSelection(all_selected=True)
        )
        return auth, admission
    auth, admission, _ = create_local_admission_service(
        operation,
        grants=grants,
        selection=AdmissionSelection(all_selected=True),
    )
    return auth, admission


def populate(directory, entity_kind, *, include_assertion=True, variant=False):
    role = "core" if entity_kind == "repository" else "context"
    seed, _ = init_catalog_stores(directory, stores=(role, "operational"))
    endpoints = (str(uuid4()), str(uuid4()))
    record = assertion(entity_kind, endpoints)
    cancelled = cancellation(record)
    originals = [("cancellation", cancelled)]
    if include_assertion:
        originals.append(("relation", record))
    if variant:
        originals.append(
            ("relation", {**record, "evidence_json": '{"other":"original"}'})
        )
    if role == "core":
        with closing(GitCore(directory / "core.sqlite3")) as core:
            for endpoint in endpoints:
                core.admit_repository(endpoint)
            for kind, value in originals:
                core.admit_identity_evidence(
                    kind, identity_record(kind, value), provenance(value)
                )
    else:
        auth, adm = authority("provider_intake", endpoints, {record["relation_uuidv4"]})
        with Context.transaction(
            directory, authorization=auth, admission=adm
        ) as context:
            for endpoint in endpoints:
                context.provider(endpoint, "fixture")
            for kind, value in originals:
                context.admit_identity_evidence(
                    kind, identity_record(kind, value), provenance(value).encoded
                )
    return seed, endpoints, record, cancelled


def export(directory, entity_kind, endpoints, target, **selection):
    auth, adm = authority("exchange_export", endpoints, {target})
    return ExchangeService(directory, authorization=auth, admission=adm).export_package(
        selection=ExchangeSelectionScope(
            all_selected=True,
            include_core=entity_kind == "repository",
            include_context=entity_kind == "service",
            **selection,
        ),
        exported_at_us=100,
    )


@pytest.mark.parametrize("entity_kind", ["repository", "service"])
def test_identity_roundtrip_original_bytes_collisions_and_idempotent_replay(
    tmp_path, entity_kind
):
    source, target = tmp_path / "source", tmp_path / "target"
    seed, endpoints, record, cancelled = populate(source, entity_kind, variant=True)
    package = export(source, entity_kind, endpoints, record["relation_uuidv4"])
    package = decode_package(encode_package(package))
    role, prefix = (
        ("core", "repository")
        if entity_kind == "repository"
        else ("context", "service")
    )
    section = package.core if role == "core" else package.context
    assert len(section[prefix + "_identity_assertions"]) == 2
    assert section[prefix + "_identity_cancellations"] == [
        wire("cancellation", cancelled)
    ]
    assert any(
        row["record_json"] == identity_record("relation", record)
        for row in section[prefix + "_identity_assertions"]
    )
    init_catalog_stores(target, repository_uuidv4=seed, stores=(role, "operational"))
    auth, adm = authority("exchange_import", endpoints, {record["relation_uuidv4"]})
    service = ExchangeService(target, authorization=auth, admission=adm)
    first = service.import_package(
        package,
        new_request=True,
        permitted_repository_uuidv4s=endpoints if role == "core" else (),
    )
    repeated = service.import_package(
        package,
        new_request=False,
        permitted_repository_uuidv4s=endpoints if role == "core" else (),
    )
    assert first.core_imported if role == "core" else first.context_imported
    assert repeated.idempotent_replay
    with closing(connect(target / (role + ".sqlite3"), role)) as db:
        rows = db.execute(
            "SELECT record_json,provenance FROM "
            + prefix
            + "_identity_assertions ORDER BY record_json"
        ).fetchall()
        assert len(rows) == 2
        assert {row[0] for row in rows} == {
            row["record_json"] for row in section[prefix + "_identity_assertions"]
        }
    assert not (
        target / ("context.sqlite3" if role == "core" else "core.sqlite3")
    ).exists()


@pytest.mark.parametrize("entity_kind", ["repository", "service"])
def test_cancellation_before_assertion_is_independent_selected_unit(
    tmp_path, entity_kind
):
    source, target = tmp_path / "source", tmp_path / "target"
    seed, endpoints, record, cancelled = populate(
        source, entity_kind, include_assertion=False
    )
    package = export(
        source,
        entity_kind,
        endpoints,
        record["relation_uuidv4"],
        identity_assertion_uuidv4s=(record["relation_uuidv4"],),
    )
    role, prefix = (
        ("core", "repository")
        if entity_kind == "repository"
        else ("context", "service")
    )
    section = package.core if role == "core" else package.context
    assert section[prefix + "_identity_assertions"] == []
    assert section[prefix + "_identity_cancellations"] == [
        wire("cancellation", cancelled)
    ]
    # A cancellation does not infer/register a missing target assertion or any endpoint.
    if role == "context":
        section["providers"].clear()
        package = replace(package, digest_sha256=None)
    init_catalog_stores(target, repository_uuidv4=seed, stores=(role, "operational"))
    auth, adm = authority("exchange_import", (), {record["relation_uuidv4"]})
    result = ExchangeService(target, authorization=auth, admission=adm).import_package(
        package,
        new_request=True,
        permitted_repository_uuidv4s=endpoints if role == "core" else (),
    )
    assert result.core_imported if role == "core" else result.context_imported
    with closing(connect(target / (role + ".sqlite3"), role)) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM " + prefix + "_identity_cancellations"
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT count(*) FROM " + prefix + "_identity_assertions"
            ).fetchone()[0]
            == 0
        )


def test_selective_identity_targets_and_repository_endpoint_permission(tmp_path):
    seed, endpoints, record, _ = populate(tmp_path, "repository")
    package = export(
        tmp_path,
        "repository",
        endpoints,
        record["relation_uuidv4"],
        repository_uuidv4s=(endpoints[0],),
        identity_assertion_uuidv4s=(record["relation_uuidv4"],),
    )
    assert package.core["repository_identity_assertions"] == []
    assert len(package.core["repository_identity_cancellations"]) == 1
    assert any(
        o["section"] == "repository_identity_assertions"
        for o in package.selection_report["omissions"]
    )
    omitted = export(
        tmp_path,
        "repository",
        endpoints,
        record["relation_uuidv4"],
        identity_assertion_uuidv4s=(),
    )
    assert not omitted.core["repository_identity_assertions"]
    assert not omitted.core["repository_identity_cancellations"]


def test_service_identity_export_and_import_need_exact_target_and_endpoint_grants(
    tmp_path,
):
    source, target = tmp_path / "source", tmp_path / "target"
    seed, endpoints, record, _ = populate(source, "service")
    with pytest.raises(AdmissionRefused):
        ExchangeService(source).export_package(
            selection=ExchangeSelectionScope(all_selected=True)
        )
    denied_auth, denied_adm = authority("exchange_export", endpoints, ())
    with pytest.raises(AdmissionRefused):
        ExchangeService(
            source, authorization=denied_auth, admission=denied_adm
        ).export_package(selection=ExchangeSelectionScope(all_selected=True))
    denied_auth, denied_adm = authority(
        "exchange_export", (endpoints[0],), {record["relation_uuidv4"]}
    )
    with pytest.raises(AdmissionRefused):
        ExchangeService(
            source, authorization=denied_auth, admission=denied_adm
        ).export_package(selection=ExchangeSelectionScope(all_selected=True))
    package = export(source, "service", endpoints, record["relation_uuidv4"])
    init_catalog_stores(
        target, repository_uuidv4=seed, stores=("context", "operational")
    )
    for grants_endpoints, grants_targets in (
        (endpoints, ()),
        ((endpoints[0],), (record["relation_uuidv4"],)),
    ):
        auth, adm = authority("exchange_import", grants_endpoints, grants_targets)
        with pytest.raises(AdmissionRefused):
            ExchangeService(target, authorization=auth, admission=adm).import_package(
                package,
                request=RequestIdentity(str(uuid4()), str(uuid4())),
                new_request=True,
            )
    with closing(connect(target / "context.sqlite3", "context")) as db:
        assert (
            db.execute("SELECT count(*) FROM service_identity_assertions").fetchone()[0]
            == 0
        )


def test_supplied_service_identity_requires_context_capability_even_when_unselected(
    tmp_path,
):
    source, target = tmp_path / "source", tmp_path / "target"
    seed, endpoints, record, _ = populate(source, "service")
    package = export(source, "service", endpoints, record["relation_uuidv4"])
    init_catalog_stores(target, repository_uuidv4=seed, stores=("core", "operational"))
    with pytest.raises(ExchangeError, match="CONTEXT_UNAVAILABLE"):
        ExchangeService(target).import_package(
            package,
            new_request=True,
            permitted_repository_uuidv4s=(seed,),
            selection=ExchangeSelectionScope(all_selected=True, include_context=False),
        )


def test_all_supplied_identity_rows_validate_before_selection_and_digest_binding(
    tmp_path,
):
    seed, _ = init_catalog_stores(tmp_path, stores=("core", "operational"))
    endpoints = (str(uuid4()), str(uuid4()))
    record = assertion("repository", endpoints)
    core = empty_core_section()
    core["repository_identity_assertions"] = [wire("relation", record)]
    package = ExchangePackage(
        package_id=str(uuid4()),
        exported_at_us=100,
        sender_catalog_instance_uuidv4=str(uuid4()),
        repository_uuidv4=seed,
        selection_scope=ExchangeSelectionScope(all_selected=True),
        core=core,
    )
    raw = package.to_dict()
    raw["core"]["repository_identity_assertions"][0]["relation_uuidv4"] = str(uuid4())
    import hashlib

    from repo_catalog.domain.exchange import _canonical_dictionary

    raw["digest_sha256"] = hashlib.sha256(_canonical_dictionary(raw)).hexdigest()
    with pytest.raises(ExchangeError, match="INVALID_IDENTITY_EVIDENCE"):
        ExchangeService(tmp_path).import_package(
            raw,
            new_request=True,
            selection=ExchangeSelectionScope(all_selected=True, include_core=False),
            permitted_repository_uuidv4s=(),
        )
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def test_identity_unit_budget_and_conflicting_package_key_are_not_corruption(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    seed, endpoints, record, _ = populate(source, "repository")
    small = export(
        source, "repository", endpoints, record["relation_uuidv4"], max_bytes=1
    )
    assert not small.core["repository_identity_assertions"]
    assert any(
        o["reason"] in {"byte_limit", "resource_limit"}
        for o in small.selection_report["omissions"]
    )
    package = export(source, "repository", endpoints, record["relation_uuidv4"])
    init_catalog_stores(target, repository_uuidv4=seed, stores=("core", "operational"))
    service = ExchangeService(target)
    service.import_package(
        package, new_request=True, permitted_repository_uuidv4s=endpoints
    )
    changed_core = {key: list(rows) for key, rows in package.core.items()}
    changed_record = {**record, "evidence_json": '{"conflicting":"package"}'}
    changed_core["repository_identity_assertions"] = [wire("relation", changed_record)]
    conflicting = replace(package, core=changed_core, digest_sha256=None)
    with pytest.raises((ExchangeError, CoreFailure)) as refusal:
        service.import_package(
            conflicting,
            request=RequestIdentity(str(uuid4()), str(uuid4())),
            new_request=True,
            permitted_repository_uuidv4s=endpoints,
        )
    assert refusal.value.code == "PACKAGE_KEY_REBOUND"
    assert not (target / "p1-recovery-stop.json").exists()


def test_optional_identity_sections_preserve_pre_extension_v8_canonical_digest():
    core, context = empty_core_section(), empty_context_section()
    for key in ("repository_identity_assertions", "repository_identity_cancellations"):
        core.pop(key)
    for key in ("service_identity_assertions", "service_identity_cancellations"):
        context.pop(key)
    package = ExchangePackage(
        package_id=str(uuid4()),
        exported_at_us=100,
        sender_catalog_instance_uuidv4=str(uuid4()),
        repository_uuidv4=str(uuid4()),
        selection_scope=ExchangeSelectionScope(all_selected=True),
        core=core,
        context=context,
    )
    assert "identity_assertion_uuidv4s" not in package.selection_scope.to_dict()
    assert (
        decode_package(encode_package(package)).digest_sha256 == package.digest_sha256
    )
    assert encode(decode_package(encode_package(package)).to_dict()) == encode(
        package.to_dict()
    )


def test_core_identity_roundtrip_never_imports_context_implementation(tmp_path):
    from tests.integration.p5.test_exchange_core_import_independence import guarded

    source, target = tmp_path / "source", tmp_path / "target"
    seed, endpoints, record, _ = populate(source, "repository")
    init_catalog_stores(target, repository_uuidv4=seed, stores=("core", "operational"))
    guarded(
        """
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.exchange import ExchangeSelectionScope, encode_package, decode_package
source, target, left, right = sys.argv[1:]
package = ExchangeService(source).export_package(selection=ExchangeSelectionScope(all_selected=True,include_context=False))
assert len(package.core['repository_identity_assertions']) == 1
assert package.context is None
result = ExchangeService(target).import_package(decode_package(encode_package(package)),new_request=True,permitted_repository_uuidv4s=(left,right))
assert result.core_imported
""",
        source,
        target,
        *endpoints,
    )


def test_provided_service_identity_refuses_missing_context_module(
    tmp_path, monkeypatch
):
    import importlib.util

    _, endpoints, record, _ = populate(tmp_path, "service")
    package = export(tmp_path, "service", endpoints, record["relation_uuidv4"])
    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *args, **kwargs: (
            None
            if name == "repo_catalog.domain.p1_context"
            else real(name, *args, **kwargs)
        ),
    )
    with pytest.raises(ExchangeError, match="MISSING_CAPABILITY"):
        decode_package(package)


def test_identity_export_capability_is_separate_from_local_write_and_revocable(
    tmp_path,
):
    _, endpoints, record, _ = populate(tmp_path, "service")
    grants = DependencySet(
        provider_registrations=endpoints,
        identity_assertions={record["relation_uuidv4"]},
    )
    # The old local policy's write-only restriction remains unchanged.
    local, local_admission, _ = create_local_admission_service(
        "exchange_export",
        grants=grants,
        selection=AdmissionSelection(all_selected=True),
    )
    with pytest.raises(AdmissionRefused):
        ExchangeService(
            tmp_path, authorization=local, admission=local_admission
        ).export_package(selection=ExchangeSelectionScope(all_selected=True))
    auth, admission, policy = create_identity_export_authority(
        grants=grants, selection=AdmissionSelection(all_selected=True)
    )
    with pytest.raises(AdmissionRefused):
        with Context.transaction(
            tmp_path, authorization=auth, admission=admission
        ) as context:
            context.provider(endpoints[0], "fixture")
    assert (
        ExchangeService(tmp_path, authorization=auth, admission=admission)
        .export_package(selection=ExchangeSelectionScope(all_selected=True))
        .context["service_identity_assertions"]
    )
    policy.revoke()
    with pytest.raises(AdmissionRefused):
        ExchangeService(
            tmp_path, authorization=auth, admission=admission
        ).export_package(selection=ExchangeSelectionScope(all_selected=True))
