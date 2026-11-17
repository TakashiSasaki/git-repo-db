"""Source-owned Provider inventory members remain typed and portable."""

import copy
import json
from contextlib import closing
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.application.provider_acquisition import ProviderAcquisition
from repo_catalog.domain.context_admission import (
    AdmissionRefused,
    AdmissionSelection,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.exchange import (
    ExchangeError,
    ExchangeSelectionScope,
    decode_package,
    encode_package,
)
from repo_catalog.domain.p1_context import CoverageScope, ResourceKey, canonical
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.production_context import SourceInventory
from repo_catalog.domain.provider_acquisition import (
    ProviderIntakeBatch,
    ProviderRegistration,
    ProviderRepositoryIntake,
    SourceRegistration,
    make_provenance,
)
from tests.integration.p5.conftest import init_catalog_stores


def authority(operation, service, source, members):
    return create_local_admission_service(
        operation,
        grants=DependencySet(
            resources=members, sources={source}, provider_registrations={service}
        ),
        selection=AdmissionSelection(all_selected=True),
    )[:2]


def fixture(path, *, empty=False):
    seed, _ = init_catalog_stores(path, stores=("context", "operational"))
    service, source = str(uuid4()), str(uuid4())
    members = (
        ()
        if empty
        else tuple(
            ResourceKey.from_native(service, "repository", str(number))
            for number in (10, 11)
        )
    )
    auth, admission = authority("provider_intake", service, source, members)
    scope = canonical(
        {
            "coverage_kind": "provider_repositories",
            "service_instance_uuidv4": service,
            "source_registration_uuidv4": source,
            "query_kind": "explicit-fixture-inventory",
        }
    )
    provenance = make_provenance("actual-fixture-observation", {"read": str(uuid4())})
    inventory = SourceInventory(
        source,
        scope,
        100,
        "complete",
        True,
        (),
        provenance,
        provider_repositories=members,
    )
    claim = CoverageClaim(
        CoverageScope.source_inventory(source, scope, "provider_repositories"),
        100,
        "complete",
    )
    ProviderAcquisition(path, authorization=auth, admission=admission).admit_batch(
        ProviderIntakeBatch(
            service,
            providers=(ProviderRegistration(service),),
            sources=(SourceRegistration(source, service),),
            provider_repositories=tuple(
                ProviderRepositoryIntake(
                    {"id": number, "full_name": "owner/repo-" + str(number)},
                    100,
                    provenance,
                )
                for number in (() if empty else (10, 11))
            ),
            source_inventory_proofs=((claim, inventory),),
        )
    )
    package = ExchangeService(path).export_package(
        selection=ExchangeSelectionScope(all_selected=True, include_core=False),
        exported_at_us=200,
    )
    return seed, service, source, members, claim, package


@pytest.mark.parametrize("empty", [False, True])
def test_provider_inventory_roundtrip_proves_typed_members_without_git_uuid_inference(
    tmp_path, empty
):
    source_path, target = tmp_path / "source", tmp_path / "target"
    seed, service, source, members, claim, package = fixture(source_path, empty=empty)
    expected = canonical(sorted([list(member.coordinates()) for member in members]))
    assert package.core is None
    assert package.context["source_inventories"][0]["members_json"] == "[]"
    assert (
        package.context["source_inventories"][0]["provider_repositories_json"]
        == expected
    )
    proofs = [
        proof
        for proof in package.context["coverage_proofs"]
        if proof["proof_kind"] == "source_inventory"
    ]
    assert len(proofs) == 1 and proofs[0]["provider_repositories_json"] == expected
    decoded = decode_package(encode_package(package))
    assert decoded.digest_sha256 == package.digest_sha256
    init_catalog_stores(
        target, repository_uuidv4=seed, stores=("context", "operational")
    )
    auth, admission = authority("exchange_import", service, source, members)
    importer = ExchangeService(target, authorization=auth, admission=admission)
    assert importer.import_package(decoded, new_request=True).context_imported
    assert importer.import_package(decoded).idempotent_replay
    with Context.snapshot(target) as context:
        projected = context.coverage(claim.scope)
        assert projected.state == "complete"
        assert projected.known_empty is empty
        assert (
            context.db.execute(
                "SELECT provider_repositories_json FROM source_inventory_evidence"
            ).fetchone()[0]
            == expected
        )
        assert (
            context.db.execute("SELECT count(*) FROM repository_context").fetchone()[0]
            == 0
        )
        assert (
            context.db.execute("SELECT count(*) FROM source_repositories").fetchone()[0]
            == 0
        )
    assert not (target / "core.sqlite3").exists()


def test_selective_export_withholds_entire_inventory_and_proof_without_trimming_members(
    tmp_path,
):
    _, _, source, members, _, package = fixture(tmp_path / "source")
    partial = ExchangeService(tmp_path / "source").export_package(
        selection=ExchangeSelectionScope(
            include_core=False,
            all_selected=False,
            repository_uuidv4s=(),
            object_oids=(),
            resource_keys=(members[0],),
            source_uuidv4s=(source,),
        )
    )
    assert len(partial.context["resources"]) == 1
    assert not partial.context["source_inventories"]
    assert not partial.context["coverage_proofs"]
    assert not partial.context["coverage_claims"]
    assert any(
        row["section"] == "source_inventories"
        for row in partial.selection_report["omissions"]
    )
    # Source package original typed terminal remains unchanged.
    assert (
        len(
            json.loads(
                package.context["source_inventories"][0]["provider_repositories_json"]
            )
        )
        == 2
    )


def test_provider_inventory_receive_requires_each_exact_resource_and_source_grant(
    tmp_path,
):
    seed, service, source, members, _, package = fixture(tmp_path / "source")
    target = tmp_path / "target"
    init_catalog_stores(
        target, repository_uuidv4=seed, stores=("context", "operational")
    )
    auth, admission = authority("exchange_import", service, source, members[:1])
    with pytest.raises(AdmissionRefused):
        ExchangeService(target, authorization=auth, admission=admission).import_package(
            package, new_request=True
        )
    with closing(connect(target / "context.sqlite3", "context")) as db:
        assert (
            db.execute("SELECT count(*) FROM source_inventory_evidence").fetchone()[0]
            == 0
        )


def test_provider_inventory_proof_members_cannot_substitute_another_typed_terminal(
    tmp_path,
):
    seed, service, source, members, _, package = fixture(tmp_path / "source")
    altered = copy.deepcopy(package.context)
    proof = next(
        row
        for row in altered["coverage_proofs"]
        if row["proof_kind"] == "source_inventory"
    )
    proof["provider_repositories_json"] = canonical([list(members[0].coordinates())])
    malformed = replace(package, context=altered, digest_sha256=None)
    target = tmp_path / "target"
    init_catalog_stores(
        target, repository_uuidv4=seed, stores=("context", "operational")
    )
    auth, admission = authority("exchange_import", service, source, members)
    with pytest.raises(ExchangeError) as refusal:
        ExchangeService(target, authorization=auth, admission=admission).import_package(
            malformed, new_request=True
        )
    assert refusal.value.code == "INVALID_COVERAGE_PROOF"
    assert not (target / "p1-recovery-stop.json").exists()


def test_foreign_service_inventory_members_are_refused_even_when_scope_unselected(
    tmp_path,
):
    seed, _, source, _, _, package = fixture(tmp_path / "source")
    altered = copy.deepcopy(package.context)
    foreign = ResourceKey.from_native(str(uuid4()), "repository", "10")
    foreign_set = canonical([list(foreign.coordinates())])
    altered["source_inventories"][0]["provider_repositories_json"] = foreign_set
    for proof in altered["coverage_proofs"]:
        if proof["proof_kind"] == "source_inventory":
            proof["provider_repositories_json"] = foreign_set
    malformed = replace(package, context=altered, digest_sha256=None)
    target = tmp_path / "target"
    init_catalog_stores(
        target, repository_uuidv4=seed, stores=("context", "operational")
    )
    with pytest.raises(ExchangeError) as refusal:
        ExchangeService(target).import_package(
            malformed,
            new_request=True,
            permitted_repository_uuidv4s=(seed,),
            selection=ExchangeSelectionScope(all_selected=True, include_context=False),
        )
    assert refusal.value.code == "SOURCE_SERVICE"
    assert source


def test_inventory_wire_member_shape_and_canonical_set_are_strict(tmp_path):
    _, _, _, members, _, package = fixture(tmp_path / "source")
    for value in (
        canonical([list(members[0].coordinates())] * 2),
        canonical([list(reversed(members[0].coordinates()))]),
        canonical([[members[0].service_instance_uuidv4, "issue", '"10"']]),
    ):
        altered = copy.deepcopy(package.context)
        altered["source_inventories"][0]["provider_repositories_json"] = value
        with pytest.raises(ExchangeError):
            replace(package, context=altered, digest_sha256=None)
