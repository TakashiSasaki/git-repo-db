"""Current review-family proofs survive selective Exchange and fresh root reads."""

from uuid import uuid4

import pytest

from repo_catalog.application.exchange import ExchangeService
from repo_catalog.application.pr_assessment import PRQueryService
from repo_catalog.domain.context_admission import (
    AdmissionSelection,
    create_local_admission_service,
)
from repo_catalog.domain.exchange import ExchangeSelectionScope
from repo_catalog.domain.p1_context import canonical
from repo_catalog.domain.provider_acquisition import (
    ProviderReviewCommentIntake,
    ProviderReviewIntake,
    ProviderReviewThreadIntake,
    make_provenance,
)
from tests.integration.p5.conftest import init_catalog_stores
from tests.integration.p5.test_pr_assessment import Fixture


def thread_fixture(path):
    fixture = Fixture(path, core=False)
    original = make_provenance(
        "actual-document-fixture", {"traversal_attempt_uuidv4": str(uuid4())}
    )
    fixture.admit(
        review_threads=(
            ProviderReviewThreadIntake(100, {"id": "THREAD-0"}, 300, original),
        ),
        review_comments=(
            ProviderReviewCommentIntake(
                100,
                {"id": 300, "body": "exact reply"},
                300,
                original,
                thread_id="THREAD-0",
            ),
        ),
    )
    fixture.observation(
        fixture.parent,
        "review_threads",
        original,
        canonical({}),
        300,
        "complete",
        fixture.threads[:1],
    )
    fixture.observation(
        fixture.threads[0],
        "review_thread_comments",
        original,
        canonical({}),
        300,
        "complete",
        fixture.comments[:1],
    )
    return fixture


def test_new_observed_empty_root_never_borrows_old_selected_thread_terminal(tmp_path):
    fixture = thread_fixture(tmp_path)
    query = PRQueryService(tmp_path)
    assert (
        query.get_pr_documents(fixture.parent, thread_id="THREAD-0").state == "complete"
    )
    fresh = make_provenance(
        "actual-document-fixture", {"traversal_attempt_uuidv4": str(uuid4())}
    )
    fixture.observation(
        fixture.parent, "review_threads", fresh, canonical({}), 400, "partial", ()
    )
    result = query.get_pr_documents(fixture.parent, thread_id="THREAD-0")
    assert result.state != "complete" and result.page.items == ()
    assert result.coverage["missing"][0]["reason"] == "selected_thread_root_unavailable"


def test_same_clock_root_progress_selects_final_real_prefix_without_borrowing_other_traversal_child(
    tmp_path,
):
    fixture = thread_fixture(tmp_path)
    query = PRQueryService(tmp_path)
    traversal = str(uuid4())

    def original(ordinal):
        return make_provenance(
            "actual-document-fixture",
            {
                "traversal_attempt_uuidv4": traversal,
                "terminal_report": {"ordinal": ordinal},
            },
        )

    fixture.observation(
        fixture.parent, "review_threads", original(1), canonical({}), 400, "partial", ()
    )
    assert (
        query.get_pr_documents(fixture.parent, thread_id="THREAD-0").state != "complete"
    )
    fixture.observation(
        fixture.parent,
        "review_threads",
        original(2),
        canonical({}),
        400,
        "complete",
        fixture.threads[:1],
    )
    assert (
        query.get_pr_documents(fixture.parent, thread_id="THREAD-0").state != "complete"
    )
    fixture.observation(
        fixture.threads[0],
        "review_thread_comments",
        original(2),
        canonical({}),
        400,
        "complete",
        fixture.comments[:1],
    )
    result = query.get_pr_documents(fixture.parent, thread_id="THREAD-0")
    assert result.state == "complete" and result.page.total_count == 1


def test_document_metadata_filters_use_actual_identified_thread_producers_and_never_hide_unknown_or_conflict(
    tmp_path,
):
    fixture = thread_fixture(tmp_path)
    query = PRQueryService(tmp_path)
    original = make_provenance("actual-thread-metadata", {"read": "resolved"})
    fixture.admit(
        review_threads=(
            ProviderReviewThreadIntake(
                100,
                {"id": "THREAD-0", "isResolved": True, "isOutdated": False},
                400,
                original,
            ),
        )
    )
    result = query.get_pr_documents(
        fixture.parent,
        thread_id="THREAD-0",
        metadata_filters={"resolved": True, "outdated": False},
    )
    assert result.state == "complete" and result.page.total_count == 1
    different = query.get_pr_documents(
        fixture.parent, thread_id="THREAD-0", metadata_filters={"resolved": False}
    )
    assert different.state == "complete" and different.page.total_count == 0
    unknown = query.get_pr_documents(
        fixture.parent, thread_id="THREAD-0", metadata_filters={"author": "unobserved"}
    )
    assert unknown.state != "complete" and unknown.page.total_count == 0
    fixture.admit(
        review_threads=(
            ProviderReviewThreadIntake(
                100,
                {"id": "THREAD-0", "isResolved": False},
                400,
                make_provenance(
                    "actual-thread-metadata", {"read": "independent-conflict"}
                ),
            ),
        )
    )
    conflict = query.get_pr_documents(
        fixture.parent, thread_id="THREAD-0", metadata_filters={"resolved": True}
    )
    assert conflict.state == "conflict" and conflict.page.total_count == 0
    assert conflict.coverage["missing"][0]["reason"] == "filter_field_unresolved"


def test_numeric_thread_flag_does_not_equal_a_typed_boolean_filter(tmp_path):
    fixture = thread_fixture(tmp_path)
    fixture.admit(
        review_threads=(
            ProviderReviewThreadIntake(
                100,
                {"id": "THREAD-0", "isResolved": 1},
                400,
                make_provenance("actual-thread-metadata", {"read": "malformed-flag"}),
            ),
        )
    )
    result = PRQueryService(tmp_path).get_pr_documents(
        fixture.parent, thread_id="THREAD-0", metadata_filters={"resolved": True}
    )
    assert result.state != "complete" and result.page.total_count == 0
    assert result.coverage["missing"][0]["reason"] == "filter_field_invalid"


@pytest.mark.parametrize("gap", ["missing-body", "conflict"])
def test_current_review_body_missing_or_equal_clock_conflict_remains_visible_under_complete_listing(
    tmp_path, gap
):
    fixture = Fixture(tmp_path, core=False)
    first = make_provenance("actual-review-body", {"read": "original"})
    fixture.admit(
        reviews=(
            ProviderReviewIntake(100, {"id": 200, "body": "original body"}, 300, first),
        )
    )
    fixture.observation(
        fixture.parent,
        "reviews",
        first,
        canonical({}),
        300,
        "complete",
        fixture.reviews[:1],
    )
    assert (
        PRQueryService(tmp_path)
        .get_pr_documents(fixture.parent, kinds=("reviews",))
        .state
        == "complete"
    )
    fixture.admit(
        reviews=(
            ProviderReviewIntake(
                100,
                {
                    "id": 200,
                    "body": None
                    if gap == "missing-body"
                    else "independent actual body",
                },
                400 if gap == "missing-body" else 300,
                make_provenance("actual-review-body", {"read": gap}),
            ),
        )
    )
    result = PRQueryService(tmp_path).get_pr_documents(
        fixture.parent, kinds=("reviews",)
    )
    assert (
        result.state != "complete"
        and not result.coverage["complete_for_requested_scope"]
    )
    assert any(
        item["reason"]
        == ("body_unavailable" if gap == "missing-body" else "body_conflict")
        for item in result.coverage["missing"]
    )


@pytest.mark.parametrize("kind", ["reviews", "review_comments"])
def test_real_current_review_family_exchange_retains_original_fields_exact_bodies_and_scope(
    tmp_path, kind
):
    fixture = Fixture(tmp_path / "sender", core=False)
    original = make_provenance("untrusted-reported-producer", {"capture": str(uuid4())})
    if kind == "reviews":
        fixture.admit(
            reviews=(
                ProviderReviewIntake(
                    100,
                    {"id": 200, "body": "exact review\n\x00tail", "state": "APPROVED"},
                    300,
                    original,
                ),
            )
        )
        member = fixture.reviews[0]
    else:
        fixture.admit(
            review_comments=(
                ProviderReviewCommentIntake(
                    100,
                    {"id": 300, "body": "exact comment\n\x00tail", "path": "a.txt"},
                    300,
                    original,
                ),
            )
        )
        member = fixture.comments[0]
    fixture.observation(
        fixture.parent, kind, original, canonical({}), 300, "complete", (member,)
    )
    before = PRQueryService(fixture.path).get_pr_documents(
        fixture.parent, kinds=(kind,)
    )
    assert before.state == "complete"
    package = ExchangeService(fixture.path).export_package(
        selection=ExchangeSelectionScope(all_selected=True, include_core=False)
    )
    target = tmp_path / "receiver"
    init_catalog_stores(
        target, repository_uuidv4=fixture.repository, stores=("context", "operational")
    )
    auth, admission, _ = create_local_admission_service(
        "exchange_import",
        grants=fixture.grants,
        selection=AdmissionSelection(all_selected=True),
    )
    importer = ExchangeService(target, authorization=auth, admission=admission)
    assert importer.import_package(package, new_request=True).context_imported
    assert importer.import_package(package).idempotent_replay
    after = PRQueryService(target).get_pr_documents(fixture.parent, kinds=(kind,))
    assert after.state == "complete" and after.coverage == before.coverage
    assert after.page.items == before.page.items
    assert after.page.items[0].fields["text_body_sha256"][0].provenance_json == original
    assert "\x00tail" in next(iter(after.page.items[0].resolved_texts.values()))
    assert not (target / "core.sqlite3").exists()
    if kind == "reviews":
        filtered = PRQueryService(target).get_pr_documents(
            fixture.parent, kinds=(kind,), metadata_filters={"state": "APPROVED"}
        )
        assert filtered.state == "complete" and filtered.page.items == after.page.items
