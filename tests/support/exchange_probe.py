"""Stdlib driver executed outside checkout in actual Exchange installations."""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import importlib.util
import json
import runpy
import sqlite3
import sys
import sysconfig
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit
from uuid import uuid4


def refuses(call, codes):
    try:
        call()
    except Exception as error:
        assert getattr(error, "code", None) in codes, (type(error), str(error), codes)
        return error
    raise AssertionError("operation unexpectedly succeeded")


def main(output):
    root = Path(__file__).resolve().parent
    runpy.run_path(str(root / "sitecustomize.py"))
    fixture = json.loads((root / "fixture.json").read_text())
    receive, repository = fixture["receive"], fixture["repository"]
    from repo_catalog.adapters.sqlite.catalog_runtime import persist_catalog_stop
    from repo_catalog.adapters.sqlite.git_core import GitCore
    from repo_catalog.adapters.sqlite.p1_schema import initialize
    from repo_catalog.application.core_query import CoreQueryService
    from repo_catalog.application.exchange import ExchangeService
    from repo_catalog.domain.exchange import (
        ExchangePackage,
        ExchangeSelectionScope,
        _canonical_dictionary,
        decode_package,
        empty_context_section,
        empty_core_section,
        encode_package,
    )
    from repo_catalog.domain.p1_coordination import RequestIdentity
    from repo_catalog.domain.p1_core import Provenance
    from repo_catalog.domain.query_work import UnlimitedWorkBudget
    from repo_catalog.domain.ref_exchange import claim_from_wire, mapping_from_wire

    expected = {
        "repo-catalog-exchange",
        "repo-catalog-core",
        "repo-catalog-runtime",
        "repo-catalog-contracts",
    }
    if receive:
        expected.add("repo-catalog-operational")
    distributions = {
        d.metadata["Name"]: d
        for d in importlib.metadata.distributions()
        if d.metadata["Name"].startswith("repo-catalog")
    }
    assert set(distributions) == expected, set(distributions)
    owners = {}
    installed = Path(sysconfig.get_path("purelib")).resolve()
    for name, distribution in distributions.items():
        for member in distribution.files:
            if str(member).startswith("repo_catalog/"):
                assert str(member) not in owners
                owners[str(member)] = name
    for suffix in (
        "domain.p1_context",
        "application.paired_query",
        "application.search_query",
        "application.git_acquisition",
        "application.acquisition",
        "adapters.sqlite.p1_coordination",
        "adapters.sqlite.paired_admission",
        "adapters.sqlite.access_connections",
    ):
        assert importlib.util.find_spec("repo_catalog." + suffix) is None, suffix
    assert owners["repo_catalog/application/exchange.py"] == "repo-catalog-exchange"
    opened = []

    def audit(event, args):
        if event != "sqlite3.connect" or str(args[0]) == ":memory:":
            return
        value = str(args[0])
        if value.startswith("file:"):
            uri = urlsplit(value)
            assert not uri.netloc and uri.query in {"mode=rw", "mode=ro"}
            value = unquote(uri.path)
        name = Path(value).name
        assert name in {
            "core.sqlite3",
            *(("operational.sqlite3",) if receive else ()),
        }, name
        opened.append(name)

    sys.addaudithook(audit)
    checks = ["resolved_owners_and_actual_optional_absence"]
    source = root / "source"
    scope = ExchangeSelectionScope(all_selected=True, include_context=False)
    package = ExchangeService(source).export_package(
        selection=scope, exported_at_us=1700000500000000
    )
    assert package.context is None and package.core["git_objects"]
    assert package.core["ref_observations"] and package.core["notes_mapping_groups"]
    assert package.core["ref_retained_notes"]
    wire = encode_package(package)
    assert decode_package(wire).digest_sha256 == package.digest_sha256
    assert not (source / "operational.sqlite3").exists()
    checks.append("canonical_metadata_original_refs_notes_export_without_O")

    note_row = package.core["ref_retained_notes"][0]
    mapping = mapping_from_wire(note_row)
    claim = next(
        c
        for c in map(claim_from_wire, package.core["ref_observation_claims"])
        if c.identity
        == (
            note_row["observation_origin_uuidv4"],
            note_row["ref_observation_uuidv7"],
            note_row["ref_claim_provenance_json"],
        )
    )
    reader = CoreQueryService(source)
    body = reader.read_ref_note_bytes(claim, mapping, UnlimitedWorkBudget())
    assert body.available and body.verified and body.body_bytes
    other = replace(
        claim, provenance=replace(claim.provenance, coordinate="other-synthetic-report")
    )
    with closing(GitCore(source / "core.sqlite3")) as core:
        core.admit_ref_observation_claim(other)
    unavailable = reader.read_ref_note_bytes(other, mapping, UnlimitedWorkBudget())
    assert not unavailable.available and not unavailable.verified
    checks.append("exact_claim_notes_body_no_cross_claim_borrowing")

    opaque = source / "context.sqlite3"
    opaque.write_bytes(
        b"opaque optional Context must never be opened without its validator"
    )
    before = opaque.read_bytes()
    refuses(
        lambda: ExchangeService(source).export_package(selection=scope),
        {"MISSING_CAPABILITY"},
    )
    assert (
        opaque.read_bytes() == before
        and not (source / "p1-recovery-stop.json").exists()
    )
    opaque.unlink()
    refuses(
        lambda: ExchangeService(source).export_transfer_events(), {"MISSING_CAPABILITY"}
    )
    checks.append("coexisting_context_and_unsupported_feature_capability_refusal")

    def target(name, *, operational=False):
        directory = root / name
        directory.mkdir()
        instance = str(uuid4())
        initialize(directory / "core.sqlite3", "core", repository, instance)
        if operational:
            initialize(
                directory / "operational.sqlite3", "operational", repository, instance
            )
        return directory, instance

    no_ledger, _ = target("no-ledger")
    refuses(
        lambda: ExchangeService(no_ledger).import_package(
            package, new_request=True, permitted_repository_uuidv4s=(repository,)
        ),
        {"CONTINUATION_UNAVAILABLE"} if receive else {"MISSING_CAPABILITY"},
    )
    assert not (no_ledger / "operational.sqlite3").exists()
    assert not (no_ledger / "p1-recovery-stop.json").exists()
    checks.append("reception_requires_installed_explicit_durable_O")

    if receive:
        from repo_catalog.adapters.sqlite.acquisition import (
            OperationalAcquisitionLedger,
        )

        destination, instance = target("receiver", operational=True)
        service = ExchangeService(destination)

        def accept(value, **kwargs):
            return service.import_package(
                value, permitted_repository_uuidv4s=(repository,), **kwargs
            )

        result = accept(
            wire,
            request=RequestIdentity(
                package.sender_catalog_instance_uuidv4, package.package_id
            ),
            new_request=True,
        )
        assert (
            result.core_imported
            and result.core_checkpoint
            and not result.context_imported
        )
        replay = accept(package)
        assert replay.idempotent_replay
        verified = CoreQueryService(destination).read_ref_note_bytes(
            claim, mapping, UnlimitedWorkBudget()
        )
        assert (
            verified.available
            and verified.verified
            and verified.body_bytes == body.body_bytes
        )
        checks.append("receiver_local_admission_notes_and_exact_resend")

        opaque = destination / "context.sqlite3"
        opaque.write_bytes(b"opaque coexisting receiver Context")
        before = opaque.read_bytes()
        witnesses = sorted((destination / "p5-request-witnesses").glob("*/*"))
        refuses(lambda: accept(package), {"MISSING_CAPABILITY"})
        assert opaque.read_bytes() == before
        assert sorted((destination / "p5-request-witnesses").glob("*/*")) == witnesses
        assert not (destination / "p1-recovery-stop.json").exists()
        opaque.unlink()
        checks.append("receiver_coexisting_context_checked_before_accounting")

        partial, _ = target("partial", operational=True)
        unknown = str(uuid4())
        section = empty_core_section()
        section["git_objects"] = [{"object_format": "sha1", "object_oid": "b" * 40}]
        section["repository_claims"] = [
            {
                "repository_uuidv4": unknown,
                "field": "name",
                "value_json": '"example"',
                "provenance_json": Provenance(
                    "reporter", "event", "field", "decoder", "1"
                ).encoded,
            }
        ]
        independent = ExchangePackage(
            str(uuid4()), None, str(uuid4()), repository, scope, core=section
        )
        outcome = ExchangeService(partial).import_package(
            independent,
            new_request=True,
            permitted_repository_uuidv4s=(unknown,),
        )
        assert any(
            row["section"] == "repository_claims"
            and row["reason"] == "missing_required_dependency"
            for row in outcome.omissions
        )
        with closing(GitCore(partial / "core.sqlite3")) as core:
            assert len(core.sql("SELECT * FROM git_objects")) == 1
            assert not core.sql("SELECT * FROM repository_claims")
        checks.append("missing_dependency_withholds_unit_preserves_independent_fact")

        changed = replace(package, exported_at_us=1700000500000001, digest_sha256=None)
        refuses(
            lambda: accept(
                changed,
                request=RequestIdentity(str(uuid4()), str(uuid4())),
                new_request=True,
            ),
            {"PACKAGE_KEY_REBOUND"},
        )
        assert not (destination / "p1-recovery-stop.json").exists()
        checks.append("package_key_digest_conflict_is_not_corruption")

        for context in (
            empty_context_section(),
            {**empty_context_section(), "resources": [{"invalid": "supplied"}]},
        ):
            supplied = package.to_dict()
            supplied["context"] = context
            supplied["digest_sha256"] = hashlib.sha256(
                _canonical_dictionary(supplied)
            ).hexdigest()
            refuses(
                lambda: accept(
                    supplied,
                    request=RequestIdentity(str(uuid4()), str(uuid4())),
                    new_request=True,
                    selection=scope,
                ),
                {"MISSING_CAPABILITY"},
            )
        assert not (destination / "context.sqlite3").exists()
        checks.append("all_supplied_context_requires_validator_even_unselected")

        refuses(
            lambda: accept(
                package,
                request=RequestIdentity(str(uuid4()), str(uuid4())),
                new_request=True,
                selection=replace(scope, max_work=0),
            ),
            {"BUDGET"},
        )
        bad = package.to_dict()
        bad["core"] = copy.deepcopy(bad["core"])
        bad["core"]["git_objects"][0]["object_oid"] = "invalid"
        bad["digest_sha256"] = hashlib.sha256(_canonical_dictionary(bad)).hexdigest()
        refuses(
            lambda: accept(
                bad,
                request=RequestIdentity(str(uuid4()), str(uuid4())),
                new_request=True,
            ),
            {"IDENTITY"},
        )
        assert not (destination / "p1-recovery-stop.json").exists()
        checks.append("bounded_processing_and_caller_error_do_not_stop")

        request = RequestIdentity(str(uuid4()), str(uuid4()))
        accept(package, request=request, new_request=True)
        (destination / "operational.sqlite3").unlink()
        refuses(lambda: accept(package, request=request), {"CONTINUATION_UNAVAILABLE"})
        initialize(
            destination / "operational.sqlite3", "operational", repository, instance
        )
        refuses(
            lambda: accept(package, request=request, new_request=True),
            {"CONTINUATION_UNAVAILABLE"},
        )
        accept(
            package,
            request=RequestIdentity(str(uuid4()), str(uuid4())),
            new_request=True,
        )
        checks.append("O_loss_cannot_reset_old_request_new_issuance_only")

        final, _ = target("cleanup", operational=True)
        original = OperationalAcquisitionLedger.close

        def stopped(ledger):
            original(ledger)
            persist_catalog_stop(final, "synthetic installed post-cleanup stop")

        with patch.object(OperationalAcquisitionLedger, "close", stopped):
            refuses(
                lambda: ExchangeService(final).import_package(
                    package,
                    new_request=True,
                    permitted_repository_uuidv4s=(repository,),
                ),
                {"RECOVERY_REQUIRED"},
            )
        checks.append("owned_accounting_cleanup_final_stop_fence")

    origins = {}
    for name, module in list(sys.modules.items()):
        if name.startswith("repo_catalog.") and getattr(module, "__file__", None):
            path = Path(module.__file__).resolve()
            assert path.is_relative_to(installed), (name, path)
            relative = path.relative_to(installed).as_posix()
            assert relative in owners, (name, relative)
            origins[name] = {"path": str(path), "owner": owners[relative]}
    output.write_text(
        json.dumps(
            {
                "result": "passed",
                "receive": receive,
                "checks": checks,
                "distributions": sorted(distributions),
                "owners": owners,
                "origins": origins,
                "opened": opened,
                "python": sys.version,
                "sqlite": sqlite3.sqlite_version,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
