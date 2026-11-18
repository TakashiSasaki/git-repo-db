"""Current PR scope assessment uses captured Context and actual Git evidence."""

from contextlib import closing
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.github.production_intake import make_document_key
from repo_catalog.adapters.sqlite.git_repository import GitRepositoryStore
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.application.git_acquisition import GitAcquisition
from repo_catalog.application.pr_assessment import PRQueryService
from repo_catalog.application.provider_acquisition import ProviderAcquisition
from repo_catalog.domain.context_admission import (
    AdmissionSelection,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.exchange import ExchangeSelectionScope
from repo_catalog.domain.git_acquisition import GitNativeAcquisitionRequest
from repo_catalog.domain.p1_context import CoverageScope, ResourceKey, canonical
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.p1_repository import OID
from repo_catalog.domain.pr_assessment import anchored_code_scope
from repo_catalog.domain.production_context import CollectionObservation
from repo_catalog.domain.provider_acquisition import (
    ProviderCommitContextIntake,
    ProviderFileContextIntake,
    ProviderIntakeBatch,
    ProviderPullRequestIntake,
    ProviderRegistration,
    ProviderReviewCommentIntake,
    ProviderReviewIntake,
    ProviderReviewThreadIntake,
    make_provenance,
)
from repo_catalog.domain.query_contracts import PageRequest, QueryError
from tests.integration.p5.conftest import build_sample_git_repo, init_catalog_stores
from tests.support.context_admission import fixture_context, fixture_service


class Fixture:
    def __init__(self, path, *, repository_store=True, retain=True):
        self.path = path
        self.repository, _ = init_catalog_stores(
            path,
            stores=("repository", "context", "operational")
            if repository_store
            else ("context", "operational"),
        )
        self.service = str(uuid4())
        self.parent = ResourceKey.from_native(self.service, "pull_request", "100")
        self.objects = build_sample_git_repo(path / "input.git")
        self.head, self.base = self.objects["commit2"], self.objects["commit1"]
        if repository_store:
            GitAcquisition(path, operational=path).acquire_from_native(
                GitNativeSource(path / "input.git"),
                GitNativeAcquisitionRequest(
                    self.repository,
                    str(uuid4()),
                    str(uuid4()),
                    "actual-fixture-git",
                    1_700_000_000_000_000,
                    select_object_oids=(self.head, self.base, self.objects["tree"]),
                    include_refs=False,
                    retain_bytes=retain,
                ),
                new_request=True,
            )
        self.files = [
            make_document_key(self.parent, "pr_file", "pr_file", name)
            for name in ("a.txt", "b.txt", "c.txt")
        ]
        self.commit = make_document_key(
            self.parent, "pr_commit", "pr_commit", self.head.object_oid
        )
        self.reviews = [
            make_document_key(self.parent, "review", "review_summary", str(number))
            for number in (200, 201)
        ]
        self.threads = [
            make_document_key(self.parent, "review_thread", "thread", name)
            for name in ("THREAD-0", "THREAD-1")
        ]
        self.comments = [
            make_document_key(
                self.parent, "review_comment", "review_comment", str(number)
            )
            for number in (300, 301)
        ]
        self.grants = DependencySet(
            resources={
                self.parent,
                self.commit,
                *self.files,
                *self.reviews,
                *self.threads,
                *self.comments,
            },
            provider_registrations={self.service},
            repositories={self.repository},
            object_oids={self.head, self.base, OID("sha1", "a" * 40)},
        )
        self.auth, _ = fixture_service(self.grants)
        self.admission = fixture_context(self.auth)
        self.api = ProviderAcquisition(
            path,
            repository_store=path if repository_store else None,
            authorization=self.auth,
            admission=self.admission,
        )
        self.anchor = make_provenance(
            "actual-fixture-api", {"read": "initial-pr-detail"}
        )
        self.payload = {
            "id": 100,
            "head": {"sha": self.head.object_oid},
            "base": {"sha": self.base.object_oid},
            "updated_at": "2026-01-01T00:00:00Z",
            "commits": 1,
            "changed_files": 2,
        }
        self.admit(
            pull_requests=(ProviderPullRequestIntake(self.payload, 100, self.anchor),)
        )

    def admit(self, **sections):
        self.api.admit_batch(
            ProviderIntakeBatch(
                self.service,
                providers=(ProviderRegistration(self.service),),
                **sections,
            )
        )

    def observation(self, parent, kind, provenance, scope, observed, state, members):
        observation = CollectionObservation(
            parent, kind, provenance, scope, observed, state, tuple(members)
        )
        claim = CoverageClaim(
            CoverageScope.collection(parent, kind, provenance, kind), observed, state
        )
        self.admit(collection_proofs=((claim, observation, scope),))

    def code(
        self,
        *,
        observed=300,
        file_count=2,
        patch="original",
        state="complete",
        anchored=True,
        capture=None,
        ordinal=None,
    ):
        capture = capture or str(uuid4())
        provenance = make_provenance("actual-fixture-api", {"capture": capture})
        originals = [provenance]
        commits = (
            ProviderCommitContextIntake(
                100, {"sha": self.head.object_oid}, observed, provenance
            ),
        )
        files = tuple(
            ProviderFileContextIntake(
                100, {"filename": name, "patch": patch}, observed, provenance
            )
            for name in ("a.txt", "b.txt", "c.txt")[:file_count]
        )
        self.admit(pr_commits=commits, pr_files=files)
        for kind, members, expected in (
            ("pr_commits", (self.commit,), 1),
            ("pr_files", self.files[:file_count], 2),
        ):
            scope = (
                anchored_code_scope(
                    {},
                    head=self.head,
                    base=self.base,
                    anchor_provenance_json=self.anchor,
                    member_provenance_jsons=originals,
                    expected_count=expected,
                )
                if anchored
                else canonical({"resource_path": "unanchored"})
            )
            terminal = make_provenance(
                "actual-fixture-api", {"capture": capture, "kind": kind}
            )
            if ordinal is not None:
                terminal = make_provenance(
                    "actual-fixture-api",
                    {
                        "traversal_attempt_uuidv4": capture,
                        "terminal_report": {"ordinal": ordinal},
                    },
                )
            self.observation(
                self.parent, kind, terminal, scope, observed, state, members
            )

    def query(self, **options):
        return PRQueryService(self.path).get_pr_code(self.parent, **options)


def test_exact_current_code_pagination_and_verified_metadata_reuse(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.code()
    first = fixture.query(page=PageRequest(limit=1))
    assert first.state == "complete"
    assert first.git_metadata["verified_objects"] >= 3
    assert first.page.total_count == 3
    second = fixture.query(page=PageRequest(limit=1, cursor=first.page.next_cursor))
    assert second.coverage == first.coverage
    assert second.anchors == first.anchors
    assert second.page.snapshot_token == first.page.snapshot_token
    assert second.page.items != first.page.items
    with closing(
        GitRepositoryStore(tmp_path / "repository.sqlite3")
    ) as repository_store:
        retained = repository_store.sql(
            "SELECT object_oid,digest_sha256 FROM retained_metadata ORDER BY object_oid"
        )
    assert fixture.query().state == "complete"
    with closing(
        GitRepositoryStore(tmp_path / "repository.sqlite3")
    ) as repository_store:
        assert (
            repository_store.sql(
                "SELECT object_oid,digest_sha256 FROM retained_metadata ORDER BY object_oid"
            )
            == retained
        )


@pytest.mark.parametrize("equivalent", [True, False])
def test_equal_clock_code_alternatives_compare_actual_captured_fields(
    tmp_path, equivalent
):
    fixture = Fixture(tmp_path)
    fixture.code(observed=300)
    fixture.code(
        observed=300, patch="original" if equivalent else "different actual diff"
    )
    result = fixture.query()
    assert result.state == ("complete" if equivalent else "conflict")
    if not equivalent:
        assert result.page.items == ()
    # A stale capture cannot settle the conflict; a genuinely newer one can.
    fixture.code(observed=275)
    assert fixture.query().state == result.state
    fixture.code(observed=400)
    assert fixture.query().state == "complete"


def test_new_current_pr_detail_requires_own_exact_comparison(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.code()
    newer = make_provenance("actual-fixture-api", {"read": "newer-pr-detail"})
    fixture.admit(
        pull_requests=(
            ProviderPullRequestIntake(
                {**fixture.payload, "updated_at": "2026-02-01T00:00:00Z"}, 400, newer
            ),
        )
    )
    result = fixture.query()
    assert result.state != "complete"
    assert any(
        gap["reason"] == "matching_listing_unavailable"
        for gap in result.coverage["missing"]
    )
    fixture.anchor = newer
    fixture.code(observed=500)
    assert fixture.query().state == "complete"


@pytest.mark.parametrize("repository_store,retain", [(False, False), (True, False)])
def test_context_counts_and_nominal_git_oids_do_not_prove_role_metadata(
    tmp_path, repository_store, retain
):
    fixture = Fixture(tmp_path, repository_store=repository_store, retain=retain)
    fixture.code()
    result = fixture.query()
    assert result.state == "partial"
    assert result.git_metadata["state"] in {"partial", "unknown"}
    assert fixture.query(require_git=False).state == "complete"
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def test_unanchored_and_newer_incomplete_listings_never_inherit_complete(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.code(anchored=False)
    assert fixture.query().state != "complete"
    fixture.code(observed=300)
    assert fixture.query().state == "complete"
    fixture.code(observed=400, file_count=1, state="partial")
    result = fixture.query(page=PageRequest(limit=1))
    assert result.state == "partial"
    assert any(gap["kind"] == "pr_files" for gap in result.coverage["missing"])


def test_progress_prefix_terminal_with_same_clock_is_one_coherent_traversal(tmp_path):
    fixture = Fixture(tmp_path)
    traversal = str(uuid4())
    fixture.code(
        observed=300, file_count=1, state="partial", capture=traversal, ordinal=1
    )
    fixture.code(
        observed=300, file_count=2, state="complete", capture=traversal, ordinal=2
    )
    assert fixture.query().state == "complete"


def test_budget_and_cursor_filter_refusal_issue_no_partial_success(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.code()
    first = fixture.query(page=PageRequest(limit=1))
    with pytest.raises(QueryError) as failure:
        fixture.query(max_work=1)
    assert failure.value.code == "QUERY_BUDGET"
    with pytest.raises(QueryError):
        fixture.query(
            require_git=False, page=PageRequest(limit=1, cursor=first.page.next_cursor)
        )
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def test_code_assessment_roundtrip_preserves_equal_clock_alternatives(tmp_path):
    fixture = Fixture(tmp_path / "source")
    fixture.code(observed=300)
    fixture.code(observed=300, patch="actual alternative")
    package = ExchangeService(fixture.path).export_package(
        selection=ExchangeSelectionScope(all_selected=True)
    )
    target = tmp_path / "receiver"
    init_catalog_stores(target, repository_uuidv4=fixture.repository)
    auth, admission, _ = create_local_admission_service(
        "exchange_import",
        grants=fixture.grants,
        selection=AdmissionSelection(all_selected=True),
    )
    ExchangeService(target, authorization=auth, admission=admission).import_package(
        package, new_request=True, permitted_repository_uuidv4s=(fixture.repository,)
    )
    result = PRQueryService(target).get_pr_code(fixture.parent)
    assert result.state == "conflict"
    assert result.page.items == ()


def test_document_scope_ignores_code_and_timeline_gaps_but_checks_bodies_beyond_page(
    tmp_path,
):
    fixture = Fixture(tmp_path, repository_store=False)
    provenance = make_provenance("actual-fixture-api", {"read": "reviews"})
    fixture.admit(
        reviews=(
            ProviderReviewIntake(
                100, {"id": 200, "body": "known body"}, 300, provenance
            ),
            ProviderReviewIntake(100, {"id": 201}, 300, provenance),
        )
    )
    fixture.observation(
        fixture.parent,
        "reviews",
        provenance,
        canonical({}),
        300,
        "complete",
        fixture.reviews,
    )
    result = PRQueryService(tmp_path).get_pr_documents(
        fixture.parent, kinds=("reviews",), page=PageRequest(limit=1)
    )
    assert result.state == "partial"
    assert result.page.total_count == 2
    assert any(
        gap["reason"] == "body_unavailable" for gap in result.coverage["missing"]
    )
    assert not any(
        gap["kind"] in {"git_metadata", "timeline", "pr_files"}
        for gap in result.coverage["missing"]
    )
    without_bodies = PRQueryService(tmp_path).get_pr_documents(
        fixture.parent, kinds=("reviews",), require_text=False
    )
    assert without_bodies.state == "complete"


def test_selected_thread_does_not_borrow_another_root_or_unrelated_sibling_gap(
    tmp_path,
):
    fixture = Fixture(tmp_path, repository_store=False)
    first = str(uuid4())
    root = make_provenance("actual-fixture-api", {"traversal_attempt_uuidv4": first})
    fixture.admit(
        review_threads=tuple(
            ProviderReviewThreadIntake(100, {"id": name}, 300, root)
            for name in ("THREAD-0", "THREAD-1")
        ),
        review_comments=(
            ProviderReviewCommentIntake(
                100, {"id": 300, "body": "reply"}, 300, root, thread_id="THREAD-0"
            ),
        ),
    )
    fixture.observation(
        fixture.parent,
        "review_threads",
        root,
        canonical({}),
        300,
        "partial",
        fixture.threads,
    )
    fixture.observation(
        fixture.threads[0],
        "review_thread_comments",
        root,
        canonical({}),
        300,
        "complete",
        fixture.comments[:1],
    )
    query = PRQueryService(tmp_path)
    assert (
        query.get_pr_documents(fixture.parent, thread_id="THREAD-0").state == "complete"
    )
    assert (
        query.get_pr_documents(fixture.parent, kinds=("review_threads",)).state
        == "partial"
    )
    second = make_provenance(
        "actual-fixture-api", {"traversal_attempt_uuidv4": str(uuid4())}
    )
    fixture.observation(
        fixture.parent,
        "review_threads",
        second,
        canonical({}),
        400,
        "partial",
        fixture.threads,
    )
    selected = query.get_pr_documents(fixture.parent, thread_id="THREAD-0")
    assert selected.state != "complete"
    assert selected.page.items == ()


def test_exact_document_path_filter_requires_code_scope_even_when_no_results(tmp_path):
    fixture = Fixture(tmp_path, repository_store=False)
    provenance = make_provenance("actual-fixture-api", {"read": "reviews"})
    fixture.observation(
        fixture.parent, "reviews", provenance, canonical({}), 300, "complete", ()
    )
    result = PRQueryService(tmp_path).get_pr_documents(
        fixture.parent, kinds=("reviews",), path="missing.py"
    )
    assert result.page.items == ()
    assert result.state == "partial"
    assert any(gap["kind"] == "code_selector" for gap in result.coverage["missing"])
