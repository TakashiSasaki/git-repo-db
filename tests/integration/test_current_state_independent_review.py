"""Independent counterexamples at mutable-state and immutable-proof boundaries."""

import json
import sqlite3
import uuid
from dataclasses import dataclass

import httpx
import pytest

from repo_catalog.adapters.github import current_parser
from repo_catalog.adapters.github.transport import GitHubTransport
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.current_resources import CurrentResources
from repo_catalog.adapters.sqlite.parser_model import ParserModel
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.adapters.sqlite.text_bodies import intern_text_body
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.parser_service import ParserService
from repo_catalog.application.query_service import QueryService
from repo_catalog.application.repository_identity import add_instance, bind
from repo_catalog.config import DEFAULTS
from repo_catalog.domain.models import CancellationToken


@dataclass
class ReviewCatalog:
    state: object
    store: Store
    model: ParserModel
    owners: list[dict]
    profile: str
    verification: str

    def scope(self, owner, *, review=False):
        fields = {
            key: owner[key]
            for key in (
                "repository_uuidv4",
                "repository_binding_id",
                "service_instance_uuidv4",
            )
        }
        if review:
            fields["change_request_id"] = owner["change_request_id"]
        return {**fields, "endpoint": "https://synthetic.invalid/resources"}

    def row(self, kind, ident, owner=0, **changes):
        context = self.owners[owner]
        review = kind in ("review", "review-comment")
        fields = {
            key: context[key]
            for key in (
                "repository_uuidv4",
                "repository_binding_id",
                "service_instance_uuidv4",
            )
        }
        fields.update(
            kind=kind,
            text_body_sha256=intern_text_body(self.store.connection, "preserved body"),
            observed_at_us=0,
            parsed_at_us=0,
            parser_profile_uuidv4=self.profile,
            metadata="{}",
            acquisition_scope_json=json.dumps(self.scope(context, review=review)),
        )
        if review:
            fields.update(
                change_request_id=context["change_request_id"],
                provider_change_request_document_id=ident,
            )
        else:
            fields.update(provider_resource_id=ident, provider_issue_number=1)
        return {**fields, **changes}

    def insert(self, row):
        table = (
            "issue_resources" if row["kind"].startswith("issue") else "review_resources"
        )
        columns = ",".join(row)
        placeholders = ",".join("?" for _ in row)
        self.store.execute(
            f"INSERT INTO {table}({columns}) VALUES({placeholders})",
            tuple(row.values()),
        )

    def collection(self, *, owner=0, parent=True):
        context = self.owners[owner]
        scope, collection = str(uuid.uuid4()), str(uuid.uuid4())
        self.store.execute(
            "INSERT INTO resume_scopes(resume_scope_id,repository_uuidv4,"
            "repository_binding_id,endpoint,request_context,parser_version,"
            "profile_version,confidence) VALUES(?,?,?,'synthetic','{}','test','test','proven')",
            (scope, context["repository_uuidv4"], context["repository_binding_id"]),
        )
        self.store.execute(
            "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,"
            "change_request_id,kind,resume_scope_id) VALUES(?,?,?,'review-comment',?)",
            (
                collection,
                context["repository_uuidv4"],
                context["change_request_id"] if parent else None,
                scope,
            ),
        )
        return collection


@pytest.fixture
def reviewed_catalog(tmp_path):
    state = tmp_path / "independent-review-state"
    MaintenanceService(state).init("catalog-text-v1", 32 * 1024 * 1024, 0)
    with Store(state) as store:
        model = ParserModel(store.connection)
        with store.transaction():
            owners = []
            for number in range(3):
                # Owner 2 shares a repository with owner 0, but uses another
                # service/binding: repository equality alone cannot prove scope.
                repository = (
                    owners[0]["repository_uuidv4"] if number == 2 else str(uuid.uuid4())
                )
                service = add_instance(store, "github", f"independent-{number}")
                if number != 2:
                    store.execute(
                        "INSERT INTO repositories(repository_uuidv4,name,metadata) "
                        "VALUES(?,?,'{}')",
                        (repository, f"independent/repo-{number}"),
                    )
                bind(store, repository, service, str(number + 1))
                binding = store.one(
                    "SELECT repository_binding_id FROM repository_bindings "
                    "WHERE repository_uuidv4=? AND service_instance_uuidv4=?",
                    (repository, service),
                )[0]
                request = str(uuid.uuid4())
                store.execute(
                    "INSERT INTO change_requests VALUES(?,?,?,'pull_request',1)",
                    (request, repository, binding),
                )
                owners.append(
                    {
                        "repository_uuidv4": repository,
                        "repository_binding_id": binding,
                        "service_instance_uuidv4": service,
                        "change_request_id": request,
                    }
                )
            capabilities = [
                {"owner_kind": "repository", "fact_kind": kind}
                for kind in (
                    "issue",
                    "ordinary-issue-comment",
                    "review",
                    "review-comment",
                )
            ]
            definition = {
                "implementation": {"independent-test": "typed current resources"},
                "settings": {},
                "output_schema": {},
                "capabilities": capabilities,
            }
            profile = model.register_profile(definition)
            verification = model.verify_profile(
                profile,
                criteria={"independent": True},
                evidence={
                    "definition": definition,
                    "capabilities": [
                        {
                            **capability,
                            "outcome": "passed",
                            "checks": ["synthetic fixture"],
                        }
                        for capability in capabilities
                    ],
                },
            )
            model.trust_verification(verification)
            for repository in {owner["repository_uuidv4"] for owner in owners}:
                for capability in capabilities:
                    model.select_profile(
                        profile,
                        verification,
                        repository_uuidv4=repository,
                        fact_kind=capability["fact_kind"],
                    )
        yield ReviewCatalog(state, store, model, owners, profile, verification)
        assert not store.all("PRAGMA foreign_key_check")
        assert store.one("PRAGMA integrity_check")[0] == "ok"


@pytest.mark.parametrize("kind", ["issue", "review", "review-comment"])
@pytest.mark.parametrize("ident", [None, "0", "01", "1\x00hidden", "１２３", "1 "])
def test_provider_identity_cannot_hide_noncanonical_suffix_in_sql(
    reviewed_catalog, kind, ident
):
    with pytest.raises(sqlite3.IntegrityError), reviewed_catalog.store.transaction():
        reviewed_catalog.insert(reviewed_catalog.row(kind, ident))


@pytest.mark.parametrize("column", ["target_commit_oid", "original_commit_oid"])
def test_review_target_oid_rejects_hidden_nul_suffix(reviewed_catalog, column):
    with pytest.raises(sqlite3.IntegrityError), reviewed_catalog.store.transaction():
        reviewed_catalog.insert(
            reviewed_catalog.row(
                "review-comment", "7", **{column: "a" * 40 + "\x00hidden"}
            )
        )


def test_parent_thread_update_cannot_make_existing_reply_inconsistent(reviewed_catalog):
    catalog = reviewed_catalog
    owner = catalog.owners[0]
    with catalog.store.transaction():
        for thread in ("thread-one", "thread-two"):
            catalog.store.execute(
                "INSERT INTO review_threads VALUES(?,?)",
                (owner["change_request_id"], thread),
            )
        catalog.insert(
            catalog.row(
                "review-comment", "10", review_thread_provider_resource_id="thread-one"
            )
        )
        catalog.insert(
            catalog.row(
                "review-comment",
                "11",
                review_thread_provider_resource_id="thread-one",
                in_reply_to_provider_resource_id="10",
            )
        )
    with pytest.raises(sqlite3.IntegrityError), catalog.store.transaction():
        catalog.store.execute(
            "UPDATE review_resources SET review_thread_provider_resource_id='thread-two' "
            "WHERE change_request_id=? AND provider_change_request_document_id='10'",
            (owner["change_request_id"],),
        )


def review_member(catalog, owner=0):
    return {
        "family": "review",
        "kind": "review-comment",
        "change_request_id": catalog.owners[owner]["change_request_id"],
        "provider_change_request_document_id": "123",
        "state_digest": "a" * 64,
    }


def test_repo_wide_receipt_rejects_member_from_another_binding(reviewed_catalog):
    catalog = reviewed_catalog
    collection = catalog.collection(parent=False)
    with pytest.raises(sqlite3.IntegrityError):
        catalog.store.execute(
            "INSERT INTO current_collection_pages VALUES(?,0,0,NULL,?,200,?)",
            (
                collection,
                json.dumps([review_member(catalog, owner=2)]),
                catalog.profile,
            ),
        )


@pytest.mark.parametrize(
    "attack",
    [
        "null-digest",
        "uppercase-digest",
        "extra-key",
        "duplicate",
        "duplicate-key",
        "wrong-parent",
        "nul-provider",
    ],
)
def test_current_receipts_reject_malformed_members_via_direct_sql(
    reviewed_catalog, attack
):
    catalog = reviewed_catalog
    collection = catalog.collection()
    member = review_member(catalog)
    if attack == "null-digest":
        member["state_digest"] = None
    elif attack == "uppercase-digest":
        member["state_digest"] = "A" * 64
    elif attack == "extra-key":
        member["unregistered"] = True
    elif attack == "wrong-parent":
        member["change_request_id"] = catalog.owners[1]["change_request_id"]
    elif attack == "nul-provider":
        member["provider_change_request_document_id"] = "123\x00hidden"
    encoded = json.dumps([member, member] if attack == "duplicate" else [member])
    if attack == "duplicate-key":
        encoded = encoded.replace(
            '"kind": "review-comment"',
            '"kind": "review-comment", "kind": "review-comment"',
        )
    with pytest.raises(sqlite3.IntegrityError):
        catalog.store.execute(
            "INSERT INTO current_collection_pages VALUES(?,0,0,NULL,?,200,?)",
            (collection, encoded, catalog.profile),
        )


def test_member_receipt_survives_later_current_body_edit(reviewed_catalog):
    catalog = reviewed_catalog
    collection = catalog.collection()
    proof = CurrentCollectionProof(catalog.store.connection)
    with catalog.store.transaction():
        catalog.insert(catalog.row("review-comment", "123"))
        proof.page(
            collection,
            0,
            0,
            None,
            [review_member(catalog)],
            parser_profile_uuidv4=catalog.profile,
        )
    original = proof.pages(collection)
    with catalog.store.transaction():
        digest = intern_text_body(catalog.store.connection, "edited resource body")
        catalog.store.execute(
            "UPDATE review_resources SET text_body_sha256=? WHERE provider_change_request_document_id='123'",
            (digest,),
        )
    assert proof.pages(collection) == original
    assert proof.evidence(collection) == {
        "kind": "current-resource-pages-v1",
        "page_ordinals": [0],
        "terminal": True,
    }


def candidate(catalog, body, *, updated=10, observed=0, **changes):
    row = catalog.row("issue", "100", title="ordinary issue", state="open")
    row.pop("text_body_sha256")
    row["metadata"] = {"labels": ["retained"], "nested": {"retained": True}}
    row["acquisition_scope"] = json.loads(row.pop("acquisition_scope_json"))
    row.update(
        body=body,
        provider_updated_at_us=updated,
        provider_clock_scope="github-issue-updated-at",
        observed_at_us=observed,
    )
    return {**row, **changes}


def visible_issues(catalog, **options):
    return QueryService(catalog.state).query(
        "issue list",
        {
            "repo": catalog.owners[0]["repository_uuidv4"],
            **options,
        },
    )


def test_sparse_update_preserves_exact_body_and_nested_known_fields(reviewed_catalog):
    catalog = reviewed_catalog
    store = CurrentResources(catalog.store)
    initial = candidate(catalog, "exact\nbody\x00with suffix", updated=10)
    assert store.admit(initial, source="import").status == "accepted"
    sparse = {
        key: value
        for key, value in initial.items()
        if key not in {"body", "title", "metadata"}
    }
    sparse.update(provider_updated_at_us=20, metadata={"nested": {"new": 2}})
    assert store.admit(sparse, source="import").status == "accepted"
    row = visible_issues(catalog).data["items"][0]
    assert row["body"] == initial["body"]
    assert row["title"] == initial["title"]
    assert row["metadata"] == {
        "labels": ["retained"],
        "nested": {"retained": True, "new": 2},
    }
    assert catalog.store.one("SELECT count(*) FROM issue_resources")[0] == 1
    assert catalog.store.one("SELECT count(*) FROM document_observations")[0] == 0


def test_untrusted_other_parser_cannot_evict_or_expose_trusted_incumbent(
    reviewed_catalog,
):
    catalog = reviewed_catalog
    resources = CurrentResources(catalog.store)
    initial = candidate(catalog, "trusted body", updated=10)
    assert resources.admit(initial, source="import").status == "accepted"
    definition = {
        "implementation": {"independent-test": "untrusted alternative"},
        "settings": {},
        "output_schema": {},
        "capabilities": [{"owner_kind": "repository", "fact_kind": "issue"}],
    }
    with catalog.store.transaction():
        other = catalog.model.register_profile(definition)
    result = resources.admit(
        candidate(catalog, "untrusted body", updated=20, parser_profile_uuidv4=other),
        source="import",
    )
    assert result.status == "missing_dependency"
    assert [row["body"] for row in visible_issues(catalog).data["items"]] == [
        "trusted body"
    ]
    assert visible_issues(catalog, parser_profile=other).data["items"] == []


def test_tied_provider_clock_has_no_incumbent_public_winner(reviewed_catalog):
    catalog = reviewed_catalog
    resources = CurrentResources(catalog.store)
    first = candidate(catalog, "one", updated=20)
    second = candidate(catalog, "two", updated=20, observed=2**60)
    assert resources.admit(first, source="import").status == "accepted"
    assert resources.admit(second, source="import").status == "conflict"
    assert resources.admit(first, source="import").status == "conflict"
    public = visible_issues(catalog)
    assert public.data["items"] == []
    assert public.status == "partial"
    assert any(
        entry["reason"] == "current_resource_unresolved"
        for entry in public.coverage.missing
    )
    assert catalog.store.one("SELECT count(*) FROM issue_resources")[0] == 1
    assert (
        resources.admit(candidate(catalog, "three", updated=30), source="import").status
        == "accepted"
    )
    assert [row["body"] for row in visible_issues(catalog).data["items"]] == ["three"]


def test_replay_does_not_claim_live_authority_from_current_revision(reviewed_catalog):
    catalog = reviewed_catalog
    resources = CurrentResources(catalog.store)
    first = candidate(catalog, "one", updated=None)
    assert resources.admit(first, source="import").status == "accepted"
    replay = candidate(catalog, "two", updated=None, observed=2**60)
    result = resources.admit(
        replay,
        source="replay",
        base_revision=catalog.store.revision(),
        scope_context=replay["acquisition_scope"],
    )
    assert result.status == "conflict"
    assert visible_issues(catalog).data["items"] == []


def test_missing_clock_does_not_become_zero_or_use_large_observation_time(
    reviewed_catalog,
):
    catalog = reviewed_catalog
    resources = CurrentResources(catalog.store)
    assert (
        resources.admit(candidate(catalog, "known", updated=0), source="import").status
        == "accepted"
    )
    assert (
        resources.admit(
            candidate(catalog, "unknown", updated=None, observed=2**60), source="import"
        ).status
        == "conflict"
    )
    assert visible_issues(catalog).data["items"] == []


@pytest.mark.parametrize("error_type", [ValueError, httpx.ConnectError])
def test_unexpected_recorder_failure_is_reported_without_blocking_current_admission(
    reviewed_catalog, error_type
):
    catalog = reviewed_catalog
    calls = []
    secret = "synthetic-private-recorder-secret"

    class BrokenRecorder:
        def record_exchange(self, context, body):
            raise error_type(secret)

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "id": 100,
                    "number": 1,
                    "title": "saved issue",
                    "body": "domain survives recorder bug",
                    "state": "open",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            ],
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        http = GitHubTransport(
            DEFAULTS["github"],
            CancellationToken(),
            client=client,
            recorder=BrokenRecorder(),
        )
        with pytest.warns(RuntimeWarning, match="ARCHIVE_FAILURE") as warnings:
            response = http.request(
                "GET", "https://api.github.com/repos/test/project/issues"
            )
    assert len(calls) == 1
    assert response.extensions["repo_catalog_archive_ref"] is None
    assert (
        response.extensions["repo_catalog_recording_diagnostics"][0]["code"]
        == "ARCHIVE_FAILURE"
    )
    assert secret not in str(warnings[0].message)
    assert secret not in json.dumps(
        response.extensions["repo_catalog_recording_diagnostics"]
    )
    context = {
        **catalog.owners[0],
        "acquisition_scope": catalog.scope(catalog.owners[0]),
        "parser_profile_uuidv4": catalog.profile,
    }
    context.pop("change_request_id")
    projection = current_parser.issue(
        response.json()[0], context, response.extensions["catalog_observed_at_us"]
    )
    projection["parsed_at_us"] = 0
    assert (
        CurrentResources(catalog.store).admit(projection, source="import").status
        == "accepted"
    )
    assert [row["body"] for row in visible_issues(catalog).data["items"]] == [
        "domain survives recorder bug"
    ]


@pytest.mark.parametrize(
    "attack",
    [
        "null-parent",
        "wrong-kind-parent",
        "cross-service-parent",
        "wrong-number",
        "null-scope-service",
    ],
)
def test_issue_parent_constraints_resist_direct_sql_bypass(reviewed_catalog, attack):
    catalog = reviewed_catalog
    with catalog.store.transaction():
        catalog.insert(catalog.row("issue", "100", title="parent", state="open"))
        catalog.insert(
            catalog.row("issue-comment", "101", parent_provider_resource_id="100")
        )
    incoming = catalog.row("issue-comment", "102", parent_provider_resource_id="100")
    if attack == "null-parent":
        incoming["parent_provider_resource_id"] = None
    elif attack == "wrong-kind-parent":
        incoming["parent_provider_resource_id"] = "101"
    elif attack == "cross-service-parent":
        incoming = catalog.row(
            "issue-comment", "102", owner=2, parent_provider_resource_id="100"
        )
    elif attack == "wrong-number":
        incoming["provider_issue_number"] = 2
    else:
        scope = json.loads(incoming["acquisition_scope_json"])
        scope["service_instance_uuidv4"] = None
        incoming["acquisition_scope_json"] = json.dumps(scope)
    with pytest.raises(sqlite3.IntegrityError), catalog.store.transaction():
        catalog.insert(incoming)


def test_explicit_profile_selection_promotes_waiting_newer_current_state(
    reviewed_catalog, tmp_path
):
    catalog = reviewed_catalog
    resources = CurrentResources(catalog.store)
    assert (
        resources.admit(
            candidate(catalog, "first parser", updated=10), source="import"
        ).status
        == "accepted"
    )
    definition = {
        "implementation": {"independent-test": "explicit replacement parser"},
        "settings": {},
        "output_schema": {},
        "capabilities": [{"owner_kind": "repository", "fact_kind": "issue"}],
    }
    with catalog.store.transaction():
        profile = catalog.model.register_profile(definition)
        verification = catalog.model.verify_profile(
            profile,
            criteria={"synthetic": True},
            evidence={
                "definition": definition,
                "capabilities": [
                    {
                        **definition["capabilities"][0],
                        "outcome": "passed",
                        "checks": ["synthetic explicit-profile test"],
                    }
                ],
            },
        )
        catalog.model.trust_verification(verification)
    assert (
        resources.admit(
            candidate(
                catalog, "replacement parser", updated=20, parser_profile_uuidv4=profile
            ),
            source="import",
        ).status
        == "missing_dependency"
    )
    request = tmp_path / "select-current-profile.json"
    request.write_text(
        json.dumps(
            {
                "profile_uuid": profile,
                "verification_uuid": verification,
                "repository_uuidv4": catalog.owners[0]["repository_uuidv4"],
                "fact_kind": "issue",
            }
        )
    )
    ParserService(catalog.state).execute("select-profile", {"input": str(request)})
    assert [row["body"] for row in visible_issues(catalog).data["items"]] == [
        "replacement parser"
    ]
    assert (
        catalog.store.one("SELECT count(*) FROM current_resource_diagnostics")[0] == 0
    )
