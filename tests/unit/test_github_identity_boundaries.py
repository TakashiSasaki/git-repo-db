"""GitHub adapters cross native/serialized identity boundaries explicitly."""

import pytest

from repo_catalog.adapters.github.production_intake import (
    canonical_database_id,
    github_repository_id,
    github_resource_id,
    github_timeline_input_id,
    normalize_issue,
    normalize_issue_comment,
    normalize_pr_commit,
    normalize_pr_file,
    normalize_pull_request,
    normalize_repository_fields,
    normalize_review,
    normalize_review_comment,
    normalize_review_thread,
    normalize_timeline_event,
)
from repo_catalog.domain.acquisition import AcquisitionError, make_provenance
from repo_catalog.domain.p1_context import ProviderRepositoryScope, ResourceKey
from repo_catalog.domain.resource_identity import encode_identity, parse_identity

SERVICE = "11111111-1111-4111-8111-111111111111"
PROVENANCE = make_provenance("synthetic://identity-tests", {"observation": "one"})


@pytest.mark.parametrize("value", [731, "731", 123456789012345678901234567890])
def test_database_normalization_is_explicit_and_lossless(value):
    native = canonical_database_id(value)
    assert native == str(value)
    assert github_resource_id({"id": value}, graphql=False) == encode_identity(native)
    assert github_timeline_input_id(value, graphql=False) == encode_identity(native)


@pytest.mark.parametrize(
    "value", [True, False, None, 1.0, 0, -1, "00731", " 731", [], {}]
)
def test_database_native_contract_refuses_other_values(value):
    with pytest.raises(AcquisitionError):
        canonical_database_id(value)


def test_helpers_return_only_canonical_text_without_namespace_aliasing():
    decimal = github_resource_id({"id": 731}, graphql=False)
    node = github_resource_id({"id": "731"}, graphql=True)
    assert parse_identity(decimal) == "731"
    assert parse_identity(node) == ["github:node_id", "731"]
    assert decimal != node
    assert github_timeline_input_id("731", graphql=True) == node
    assert github_timeline_input_id(731, graphql=True) == decimal
    assert github_resource_id({"id": "731", "databaseId": 731}, graphql=True) == decimal
    assert github_repository_id({"id": "731", "databaseId": 731}, graphql=True) == node


@pytest.mark.parametrize(
    "normalizer,kind",
    [(normalize_repository_fields, "repository"), (normalize_issue, "issue")],
)
def test_top_level_decimal_resource_is_encoded_once(normalizer, kind):
    key = normalizer(SERVICE, {"id": 731}, 1, PROVENANCE).primary_resource
    assert key == ResourceKey.from_native(SERVICE, kind, "731")


@pytest.mark.parametrize("graphql,repo_id", [(False, 731), (True, "731")])
def test_repository_role_member_and_scope_share_exact_serialized_identity(
    graphql, repo_id
):
    unit = normalize_issue(
        SERVICE,
        {"id": 9 if not graphql else "I_node", "repository": {"id": repo_id}},
        1,
        PROVENANCE,
        graphql=graphql,
    )
    (relation,) = unit.relations
    (member,) = relation.members
    assert member.provider_resource_id == github_repository_id(
        {"id": repo_id}, graphql=graphql
    )
    assert member.resource_kind == "repository"
    scope = ProviderRepositoryScope.from_json(relation.scope_json)
    assert (
        scope.roles["owning_repository"].provider_repository_id
        == member.provider_resource_id
    )


@pytest.mark.parametrize(
    "payload,graphql,native",
    [
        ({"id": 731}, False, "731"),
        ({"id": "PR_node"}, True, ["github:node_id", "PR_node"]),
    ],
)
def test_pr_title_and_body_preserve_native_local_and_namespace_coordinates(
    payload, graphql, native
):
    unit = normalize_pull_request(
        SERVICE,
        {**payload, "title": "title", "body": "body"},
        1,
        PROVENANCE,
        graphql=graphql,
    )
    assert parse_identity(unit.primary_resource.provider_resource_id) == native
    docs = [
        row.resource
        for row in unit.observations
        if row.resource != unit.primary_resource
    ]
    assert {parse_identity(doc.provider_resource_id)[2] for doc in docs} == {
        "pr_title",
        "pr_body",
    }
    for key in docs:
        coords = parse_identity(key.provider_resource_id)
        assert coords[0] == "pull_request"
        assert coords[1] == encode_identity(native)
        assert coords[3] == native


@pytest.mark.parametrize(
    "normalizer,args,subtype,native",
    [
        (normalize_review, (731, {"id": 9}), "review_summary", "9"),
        (
            normalize_review_thread,
            (731, {"id": "thread_node"}),
            "thread",
            "thread_node",
        ),
        (normalize_review_comment, (731, {"id": 9}), "comment", "9"),
        (normalize_pr_commit, (731, {"sha": "a" * 40}), "pr_commit", "a" * 40),
        (normalize_pr_file, (731, {"filename": "a/日本.txt"}), "pr_file", "a/日本.txt"),
    ],
)
def test_known_pr_scoped_producers_encode_namespace_once(
    normalizer, args, subtype, native
):
    key = normalizer(SERVICE, *args, 1, PROVENANCE).primary_resource
    assert parse_identity(key.provider_resource_id) == [
        "pull_request",
        '"731"',
        subtype,
        native,
    ]


def test_issue_comment_uses_native_local_id():
    key = normalize_issue_comment(
        SERVICE, "issue", 731, {"id": 9}, 1, PROVENANCE
    ).primary_resource
    assert parse_identity(key.provider_resource_id) == [
        "issue",
        '"731"',
        "comment",
        "9",
    ]


@pytest.mark.parametrize(
    "graphql,parent,event", [(False, 731, 9), (True, "I_node", "E_node")]
)
def test_timeline_local_identity_is_native_and_namespace_is_text(
    graphql, parent, event
):
    key = normalize_timeline_event(
        SERVICE, "issue", parent, event, {"id": event}, 1, PROVENANCE, graphql=graphql
    ).primary_resource
    assert parse_identity(key.provider_resource_id) == [
        "issue",
        github_timeline_input_id(parent, graphql=graphql),
        "timeline_event",
        parse_identity(github_timeline_input_id(event, graphql=graphql)),
    ]


def test_observed_node_and_database_aliases_require_actual_issue_payload():
    parent = ResourceKey.from_native(SERVICE, "issue", "731")
    unit = normalize_timeline_event(
        SERVICE,
        "issue",
        "I_node",
        "E_node",
        {"id": "E_node", "issue": {"id": "I_node", "databaseId": 731}},
        1,
        PROVENANCE,
        graphql=True,
        parent_resource=parent,
    )
    assert (
        parse_identity(unit.primary_resource.provider_resource_id)[1]
        == parent.provider_resource_id
    )
    with pytest.raises(AcquisitionError, match="EVENT_PARENT_MISMATCH"):
        normalize_timeline_event(
            SERVICE,
            "issue",
            "other_node",
            "E_node",
            {"id": "E_node", "issue": {"id": "I_node", "databaseId": 731}},
            1,
            PROVENANCE,
            graphql=True,
            parent_resource=parent,
        )


@pytest.mark.parametrize("thread", [42, True, [], {}, "", " "])
def test_review_thread_reference_cannot_implicitly_stringify(thread):
    with pytest.raises(AcquisitionError, match="THREAD_ID_REQUIRED"):
        normalize_review_comment(
            SERVICE, 731, {"id": 9, "review_thread_id": thread}, 1, PROVENANCE
        )


def test_timeline_unknown_parent_kind_cannot_bypass_known_contract():
    with pytest.raises(AcquisitionError, match="PARENT_KIND"):
        normalize_timeline_event(SERVICE, "opaque", 731, 9, {"id": 9}, 1, PROVENANCE)
