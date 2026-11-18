"""Natural Collection selection carries whole originals without sibling expansion."""

import json
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.application.pr_assessment import PRQueryService
from repo_catalog.domain.context_admission import (
    AdmissionRefused,
    AdmissionSelection,
    create_local_admission_service,
)
from repo_catalog.domain.exchange import (
    ExchangeError,
    ExchangeSelectionScope,
    decode_package,
    encode_package,
)
from repo_catalog.domain.p1_context import CoverageScope, canonical
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.production_context import CollectionObservation
from repo_catalog.domain.provider_acquisition import (
    ProviderFileContextIntake,
    ProviderReviewIntake,
    SourceRegistration,
    make_provenance,
)
from tests.integration.p5.conftest import init_catalog_stores
from tests.integration.p5.test_pr_assessment import Fixture
from tests.integration.p5.test_selected_exchange_work import measured_export
from tests.support.context_admission import fixture_transaction


def setup(path, *, repository_store=False):
    fixture = Fixture(path, repository_store=repository_store)
    fixture.code(patch="original file patch")
    source = str(uuid4())
    fixture.grants = replace(fixture.grants, sources={source})
    # Reissue explicit fixture authority before Source registration/admission.
    from repo_catalog.application.provider_acquisition import ProviderAcquisition
    from tests.support.context_admission import fixture_context, fixture_service

    fixture.auth, _ = fixture_service(fixture.grants)
    fixture.admission = fixture_context(fixture.auth)
    fixture.api = ProviderAcquisition(
        path, authorization=fixture.auth, admission=fixture.admission
    )
    fixture.admit(
        sources=(SourceRegistration(source, fixture.service),),
        reviews=(
            ProviderReviewIntake(
                100,
                {"id": 200, "body": "UNSELECTED-SIBLING-BODY"},
                400,
                make_provenance("selection-fixture", {"read": "sibling"}),
            ),
        ),
        pr_files=(
            ProviderFileContextIntake(
                100,
                {"filename": "a.txt", "patch": "competing current patch"},
                500,
                make_provenance("selection-fixture", {"read": "competing-file"}),
            ),
        ),
    )
    original = fixture.query(require_git=False)
    files = next(row for row in original.collections if row["kind"] == "pr_files")
    scope = {
        **json.loads(files["alternatives"][0]["scope_json"]),
        "source_registration_uuidv4": source,
    }
    provenance = make_provenance(
        "selection-fixture", {"read": "selected-whole-listing"}
    )
    fixture.observation(
        fixture.parent,
        "pr_files",
        provenance,
        canonical(scope),
        600,
        "complete",
        fixture.files[:2],
    )
    key = (*fixture.parent.coordinates(), "pr_files", provenance)
    selection = ExchangeSelectionScope(
        include_repository=False,
        repository_uuidv4s=(),
        object_oids=(),
        source_uuidv4s=(source,),
        resource_keys=(),
        collection_keys=(key,),
    )
    return fixture, selection, key


def test_exact_collection_preserves_whole_proof_conflicting_member_originals_reopen_repeat_and_onward_without_siblings(
    tmp_path,
):
    fixture, selection, key = setup(tmp_path / "sender")
    package = ExchangeService(fixture.path).export_package(selection=selection)
    package = decode_package(encode_package(package))
    assert package.selection_scope.collection_keys == (key,)
    assert (
        len(package.context["collections"])
        == len(package.context["coverage_proofs"])
        == 1
    )
    assert {
        tuple(
            row[name]
            for name in (
                "service_instance_uuidv4",
                "resource_kind",
                "provider_resource_id",
            )
        )
        for row in package.context["resources"]
    } == {
        fixture.parent.coordinates(),
        *(member.coordinates() for member in fixture.files[:2]),
    }
    assert "UNSELECTED-SIBLING-BODY" not in encode_package(package)
    assert (
        package.context["sources"][0]["source_registration_uuidv4"]
        == selection.source_uuidv4s[0]
    )
    original_rows = {
        name: package.context[name]
        for name in (
            "collections",
            "coverage_proofs",
            "field_candidates",
            "text_bodies",
        )
    }
    for label in ("receiver", "onward"):
        target = tmp_path / label
        init_catalog_stores(
            target,
            repository_uuidv4=fixture.repository,
            stores=("context", "operational"),
        )
        auth, admission, _ = create_local_admission_service(
            "exchange_import",
            grants=fixture.grants,
            selection=AdmissionSelection(all_selected=True),
        )
        service = ExchangeService(target, authorization=auth, admission=admission)
        service.import_package(package, new_request=True)
        assert service.import_package(package).idempotent_replay
        # A new service/snapshot after delivery observes actual preserved facts.
        captured = PRQueryService(target, mode="context_only").get_pr_code_capture(
            fixture.parent, "pr_files", key[4]
        )
        assert captured.state == "complete" and captured.page.total_count == 2
        with Context.snapshot(target) as context:
            patches = {
                json.loads(candidate.value_json)
                for candidate in context.candidates(fixture.files[0], "patch")
            }
            assert patches == {"original file patch", "competing current patch"}
            assert (
                context.coverage(
                    CoverageScope.collection(
                        fixture.parent, "pr_files", key[4], "pr_files"
                    )
                ).state
                == "complete"
            )
        package = ExchangeService(target).export_package(selection=selection)
        for name, rows in original_rows.items():
            assert package.context[name] == rows


def test_selected_collection_sql_work_ignores_unrelated_same_owner_collection_history(
    tmp_path,
):
    fixture, selection, _ = setup(tmp_path)
    before, before_sql = measured_export(tmp_path, selection)
    broad_scope = CoverageScope.resource(fixture.parent, "pr-body")
    with fixture_transaction(tmp_path, fixture.grants) as context:
        context.scope(broad_scope)
        for index in range(1500):
            provenance = make_provenance(
                "selection-fixture", {"read": f"unrelated-{index}"}
            )
            observation = CollectionObservation(
                fixture.parent, "pr_files", provenance, "{}", 100, "complete", ()
            )
            context.collection(observation)
            context.prove_collection(
                CoverageClaim(
                    CoverageScope.collection(
                        fixture.parent, "pr_files", provenance, "pr_files"
                    ),
                    100,
                    "complete",
                ),
                observation,
                required_scope_json="{}",
            )
            context.admit_coverage(CoverageClaim(broad_scope, 1000 + index, "partial"))
    after, after_sql = measured_export(tmp_path, selection)
    assert after.context == before.context
    assert after_sql <= before_sql * 1.2 + 4000
    assert (
        after.selection_report["work"] <= before.selection_report["work"] * 1.2 + 4000
    )
    bounded = ExchangeService(tmp_path).export_package(
        selection=replace(
            selection, max_work=before.selection_report["work"] * 2 + 6000
        )
    )
    assert bounded.context == before.context
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def test_selected_collection_keeps_whole_unit_under_limits_and_requires_explicit_member_authority(
    tmp_path,
):
    fixture, selection, _ = setup(tmp_path / "sender")
    package = ExchangeService(fixture.path).export_package(selection=selection)
    limited = ExchangeService(fixture.path).export_package(
        selection=replace(selection, max_units=1)
    )
    assert limited.context["collections"] == limited.context["coverage_proofs"] == []
    target = tmp_path / "receiver"
    init_catalog_stores(
        target, repository_uuidv4=fixture.repository, stores=("context", "operational")
    )
    auth, admission, _ = create_local_admission_service(
        "exchange_import",
        grants=replace(
            fixture.grants, resources=fixture.grants.resources - {fixture.files[0]}
        ),
        selection=AdmissionSelection(all_selected=True),
    )
    with pytest.raises(AdmissionRefused):
        ExchangeService(target, authorization=auth, admission=admission).import_package(
            package, new_request=True
        )
    with Context.snapshot(target) as context:
        assert context.db.execute("SELECT count(*) FROM resources").fetchone() == (0,)
        assert context.db.execute(
            "SELECT count(*) FROM coverage_proofs"
        ).fetchone() == (0,)
    assert not (target / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("mutation", ["duplicate", "wrong-width", "bad-provenance"])
def test_collection_selection_wire_refuses_noncanonical_or_invalid_natural_keys(
    tmp_path, mutation
):
    _, selection, key = setup(tmp_path)
    value = selection.to_dict()
    value["collection_keys"] = {
        "duplicate": [list(key), list(key)],
        "wrong-width": [list(key[:4])],
        "bad-provenance": [[*key[:4], "not-json"]],
    }[mutation]
    with pytest.raises((ExchangeError, ValueError)):
        ExchangeSelectionScope.from_dict(value)


def test_later_claim_on_the_exact_original_scope_is_retained_without_rewriting_its_terminal(
    tmp_path,
):
    fixture, selection, key = setup(tmp_path)
    before = ExchangeService(tmp_path).export_package(selection=selection)
    exact_scope = CoverageScope.collection(
        fixture.parent, "pr_files", key[4], "pr_files"
    )
    with fixture_transaction(tmp_path, fixture.grants) as context:
        assert (
            context.admit_coverage(CoverageClaim(exact_scope, 700, "partial"))
            == "insert"
        )
    after = ExchangeService(tmp_path).export_package(selection=selection)
    assert after.context["collections"] == before.context["collections"]
    assert after.context["coverage_proofs"] == before.context["coverage_proofs"]
    assert {
        (row["observed_at_us"], row["coverage_state"])
        for row in after.context["coverage_claims"]
    } == {(600, "complete"), (700, "partial")}
    captured = PRQueryService(tmp_path, mode="context_only").get_pr_code_capture(
        fixture.parent, "pr_files", key[4]
    )
    assert captured.state == "partial" and captured.page.total_count == 2
    assert captured.collections[0]["alternatives"][0]["observed_at_us"] == 600
    assert captured.coverage["current_provider_state_asserted"] is False


def test_collection_import_shorthand_uses_only_explicit_local_target_grants_and_keeps_root_selection(
    tmp_path,
):
    fixture, selection, key = setup(tmp_path / "sender")
    package = ExchangeService(fixture.path).export_package(selection=selection)
    target = tmp_path / "receiver"
    init_catalog_stores(
        target, repository_uuidv4=fixture.repository, stores=("context", "operational")
    )
    # The separately supplied local grant set includes a sibling. That does not
    # add the sibling to the Collection-rooted wire selection.
    service = ExchangeService(target, grants=fixture.grants)
    service.import_package(package, new_request=True)
    assert service.import_package(package).idempotent_replay
    captured = PRQueryService(target, mode="context_only").get_pr_code_capture(
        fixture.parent, "pr_files", key[4]
    )
    assert captured.state == "complete" and captured.page.total_count == 2
    with Context.snapshot(target) as context:
        assert context.db.execute("SELECT count(*) FROM resources").fetchone() == (3,)
        assert (
            context.db.execute(
                "SELECT 1 FROM resources WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
                fixture.reviews[0].coordinates(),
            ).fetchone()
            is None
        )
    denied = tmp_path / "denied"
    init_catalog_stores(
        denied, repository_uuidv4=fixture.repository, stores=("context", "operational")
    )
    with pytest.raises(AdmissionRefused):
        ExchangeService(denied).import_package(package, new_request=True)
    with Context.snapshot(denied) as context:
        assert context.db.execute("SELECT count(*) FROM resources").fetchone() == (0,)
