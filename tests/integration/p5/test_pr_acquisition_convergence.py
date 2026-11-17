"""Late actual Git evidence converges without rewriting original Provider reads."""

from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.application.git_acquisition import GitAcquisition
from repo_catalog.application.pr_assessment import PRQueryService
from repo_catalog.domain.context_admission import (
    AdmissionSelection,
    create_local_admission_service,
)
from repo_catalog.domain.exchange import ExchangeSelectionScope
from repo_catalog.domain.git_acquisition import GitNativeAcquisitionRequest
from repo_catalog.domain.provider_acquisition import (
    ProviderReviewIntake,
    make_provenance,
)
from tests.integration.p5.conftest import init_catalog_stores
from tests.integration.p5.test_pr_assessment import Fixture


@pytest.mark.parametrize("review_target", [False, True])
def test_partial_portable_code_scope_converges_after_actual_native_evidence_without_retiming_provider_originals(
    tmp_path, review_target
):
    fixture = Fixture(tmp_path / "sender", retain=False)
    fixture.code()
    if review_target:
        fixture.admit(
            reviews=(
                ProviderReviewIntake(
                    100,
                    {"id": 200, "commit_id": fixture.base.object_oid},
                    300,
                    make_provenance(
                        "actual-convergence-fixture", {"read": "review-target"}
                    ),
                ),
            )
        )
    before = fixture.query()
    assert (
        before.state == "partial"
        and before.git_metadata["reason"] == "role_metadata_unavailable"
    )
    partial = ExchangeService(fixture.path).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )
    native = GitNativeAcquisitionRequest(
        fixture.repository,
        str(uuid4()),
        str(uuid4()),
        "actual-late-metadata-fixture",
        1_700_000_600_000_000,
        select_object_oids=(fixture.head, fixture.base, fixture.objects["tree"]),
        include_refs=False,
    )
    report = GitAcquisition(fixture.path, operational=fixture.path).acquire_from_native(
        GitNativeSource(fixture.path / "input.git"), native, new_request=True
    )
    assert report.status == "complete"
    complete = ExchangeService(fixture.path).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )
    after = fixture.query()
    assert after.state == "complete" and after.anchors == before.anchors
    assert after.collections == before.collections
    if review_target:
        assert any(role.startswith("review_target:") for role in after.anchors)
    for order in ((partial, complete), (complete, partial)):
        target = tmp_path / ("receiver-" + str(order[0] is partial))
        init_catalog_stores(target, repository_uuidv4=fixture.repository)
        auth, admission, _ = create_local_admission_service(
            "exchange_import",
            grants=fixture.grants,
            selection=AdmissionSelection(all_selected=True),
        )
        importer = ExchangeService(target, authorization=auth, admission=admission)
        for package in order:
            importer.import_package(package, new_request=True)
        assert importer.import_package(partial).idempotent_replay
        assert importer.import_package(complete).idempotent_replay
        received = PRQueryService(target).get_pr_code(fixture.parent)
        assert received.state == "complete"
        assert (
            received.anchors == before.anchors
            and received.collections == before.collections
        )
