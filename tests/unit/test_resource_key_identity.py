"""ADR 0031 I1 native/serialized boundaries, independent of later Resource DDL."""

import base64
import copy
import hashlib
import json
from dataclasses import asdict

import pytest

from repo_catalog.domain.exchange import (
    ExchangeError,
    ExchangePackage,
    ExchangeSelectionScope,
    _canonical_content,
)
from repo_catalog.domain.p1_context import (
    CoverageScope,
    EventReportKey,
    FieldClock,
    MappingClaimKey,
    MappingSupport,
    ProviderRepositoryRoleScope,
    ResourceKey,
    canonical,
    encode_mapping_provenance,
    validate_timeline_event_coordinates,
)
from repo_catalog.domain.production_query import (
    PaginationCursor,
    QueryError,
    SnapshotFenceToken,
    canonical_json,
)
from repo_catalog.domain.resource_identity import encode_identity, parse_identity

SERVICE = "11111111-1111-4111-8111-111111111111"
OTHER_SERVICE = "22222222-2222-4222-8222-222222222222"
REPOSITORY = "33333333-3333-4333-8333-333333333333"
PACKAGE = "44444444-4444-4444-8444-444444444444"
CLOCK = FieldClock("provider:update", 1)
PROVENANCE = encode_mapping_provenance("provider.test", "original-report")


@pytest.mark.parametrize("endpoint", ["context_resources", "paired_resources"])
@pytest.mark.parametrize("identity", ['"731"', "731", '"\\u0037"'])
def test_rechecksummed_resource_cursor_still_requires_canonical_identity(
    endpoint, identity
):
    token = SnapshotFenceToken(
        mode="paired",
        repository_uuidv4=REPOSITORY,
        catalog_instance_uuidv4=PACKAGE,
        core_sha256="a" * 64,
        context_sha256="b" * 64,
    ).encode()
    payload = {
        "v": 1,
        "endpoint_kind": endpoint,
        "filter_digest": "c" * 64,
        "snapshot_token": token,
        "last_key": [SERVICE, "issue", identity],
    }
    checksum = hashlib.sha256(
        f"p6-cursor-v1:{canonical_json(payload)}".encode()
    ).hexdigest()
    raw = base64.urlsafe_b64encode(
        canonical_json(
            {
                "checksum_sha256": checksum,
                "payload": payload,
            }
        ).encode()
    ).decode()
    if identity == '"731"':
        assert PaginationCursor.decode(
            raw,
            expected_endpoint=endpoint,
            expected_filter_digest="c" * 64,
            current_snapshot_token=token,
        ).last_key == (SERVICE, "issue", identity)
    else:
        with pytest.raises(QueryError, match="INVALID_CURSOR"):
            PaginationCursor.decode(
                raw,
                expected_endpoint=endpoint,
                expected_filter_digest="c" * 64,
                current_snapshot_token=token,
            )


@pytest.mark.parametrize("native", ["", [], [""], [[]], "731", ["731"], ["a", ["b"]]])
def test_constructor_receives_exact_serialized_text(native):
    text = encode_identity(native)
    key = ResourceKey(SERVICE, "vendor.resource", text)
    assert key.coordinates() == (SERVICE, "vendor.resource", text)
    assert ResourceKey(*key.coordinates()) == key
    assert ResourceKey.from_native(SERVICE, "vendor.resource", native) == key


@pytest.mark.parametrize(
    "text",
    ["731", "plain-id", '"\\u0037"', ' "731"', '["731"]\n', "null", "{}", "[false]"],
)
def test_serialized_constructor_rejects_plain_noncanonical_and_forbidden_ids(text):
    with pytest.raises(ValueError):
        ResourceKey(SERVICE, "vendor.resource", text)


@pytest.mark.parametrize("value", [None, 731, True, b'"731"', ("731",)])
def test_serialized_constructor_never_coerces_native_objects(value):
    with pytest.raises(TypeError):
        ResourceKey(SERVICE, "vendor.resource", value)


def test_native_json_looking_string_is_never_guessed_as_serialized_or_composite():
    string_key = ResourceKey.from_native(SERVICE, "issue", '["project","731"]')
    composite_key = ResourceKey.from_native(SERVICE, "issue", ["project", "731"])
    serialized_key = ResourceKey(SERVICE, "issue", '["project","731"]')
    assert composite_key == serialized_key
    assert string_key != composite_key
    assert parse_identity(string_key.provider_resource_id) == '["project","731"]'


def test_native_namespaces_and_all_three_key_components_remain_distinct():
    values = ["731", ["731"], ["decimal", "731"], ["node", "731"], "00731"]
    keys = {ResourceKey.from_native(SERVICE, "issue", value) for value in values}
    assert len(keys) == len(values)
    key = ResourceKey.from_native(SERVICE, "issue", "731")
    assert ResourceKey.from_native(OTHER_SERVICE, "issue", "731") != key
    assert ResourceKey.from_native(SERVICE, "repository", "731") != key


@pytest.mark.parametrize("namespace", ["PR731", ["project", "PR731"], "", [], [[], ""]])
@pytest.mark.parametrize("local_id", ["D731", ["node", "D731"], "", []])
def test_scoped_document_preserves_every_pr_coordinate_as_namespace_text(
    namespace, local_id
):
    parent = ResourceKey.from_native(SERVICE, "pull_request", namespace)
    key = ResourceKey.document(parent, "document", "body", local_id)
    expected = ["pull_request", encode_identity(namespace), "body", local_id]
    assert key.provider_resource_id == encode_identity(expected)
    assert parse_identity(key.provider_resource_id) == expected
    assert key.scoped_document_coordinates() == tuple(expected)
    assert key != ResourceKey.document(parent, "document", "title", local_id)
    assert key != ResourceKey.document(parent, "document", "body", [local_id])
    assert ResourceKey(*key.coordinates()) == key


@pytest.mark.parametrize("resource_kind", ["review", "comment", "thread"])
@pytest.mark.parametrize(
    "native",
    [
        "opaque",
        [],
        ["pull_request", ["project", "731"], "body", "1"],
        ["pull_request", "731", "body", "1"],
    ],
)
def test_known_scoped_kinds_cannot_retry_invalid_input_as_opaque(resource_kind, native):
    # The same generic grammar is valid for a new kind; the reserved kind must
    # still apply its known identification contract and refuse it.
    ResourceKey.from_native(SERVICE, "vendor.resource", native)
    with pytest.raises(ValueError):
        ResourceKey.from_native(SERVICE, resource_kind, native)


def test_scoped_and_global_document_contracts_are_explicit_without_parent_inference():
    parent = ResourceKey.from_native(SERVICE, "pull_request", "PR731")
    scoped = ResourceKey.document(parent, "document", "body", "D731")
    global_key = ResourceKey.global_document(SERVICE, ["project", "D731"])
    assert global_key.resource_kind == scoped.resource_kind == "document"
    assert global_key.provider_resource_id == '["project","D731"]'
    assert global_key != scoped
    with pytest.raises(ValueError):
        global_key.scoped_document_coordinates()
    with pytest.raises(ValueError):
        ResourceKey.document(None, "document", "body", "D731")
    with pytest.raises(ValueError):
        ResourceKey.document(parent, "vendor.resource", "body", "D731")
    with pytest.raises(ValueError):
        ResourceKey.document(parent, "document", "", "D731")


def test_namespace_text_profile_cannot_alias_decoded_namespace_profile():
    native_namespace = ["project", "PR731"]
    parent = ResourceKey.from_native(SERVICE, "pull_request", native_namespace)
    good = ResourceKey.document(parent, "review", "review", "R731")
    wrong_text = encode_identity(["pull_request", native_namespace, "review", "R731"])
    assert good.provider_resource_id != wrong_text
    with pytest.raises(ValueError):
        ResourceKey(SERVICE, "review", wrong_text)
    string_parent = ResourceKey.from_native(
        SERVICE, "pull_request", parent.provider_resource_id
    )
    assert ResourceKey.document(string_parent, "review", "review", "R731") != good


def test_global_array_shaped_like_scoped_identity_keeps_explicit_contract():
    parent = ResourceKey.from_native(SERVICE, "pull_request", "PR731")
    scoped = ResourceKey.document(parent, "document", "body", "D731")
    native = parse_identity(scoped.provider_resource_id)
    for global_key in (
        ResourceKey.global_document(SERVICE, native),
        ResourceKey.from_native(SERVICE, "document", native),
    ):
        # Contract intent adds no key coordinate, tag, hash or equality rule.
        assert global_key == scoped
        assert hash(global_key) == hash(scoped)
        assert global_key.coordinates() == scoped.coordinates()
        assert asdict(global_key) == dict(
            zip(
                ("service_instance_uuidv4", "resource_kind", "provider_resource_id"),
                scoped.coordinates(),
            )
        )
        with pytest.raises(ValueError, match="Explicit global Document"):
            global_key.scoped_document_coordinates()


@pytest.mark.parametrize("event_id", ["731", ["github:node_id", "EV731"], "", []])
def test_timeline_event_retains_exact_issue_namespace_and_native_local_id(event_id):
    issue = ResourceKey.from_native(SERVICE, "issue", ["project", "I731"])
    event = ResourceKey.timeline_event(issue, event_id)
    assert validate_timeline_event_coordinates(event.provider_resource_id) == (
        issue.provider_resource_id,
        event_id,
    )
    report_key = EventReportKey(event, CLOCK, PROVENANCE)
    assert report_key.issue_parent == issue
    with pytest.raises(ValueError):
        ResourceKey.timeline_event(
            ResourceKey.from_native(SERVICE, "pull_request", "731"), event_id
        )


@pytest.mark.parametrize("native", ["731", ["project", "731"], "日本😀", [], ""])
def test_exchange_selection_roundtrip_keeps_identity_text_as_a_string(native):
    key = ResourceKey.from_native(SERVICE, "vendor.resource", native)
    scope = ExchangeSelectionScope(resource_keys=(key,))
    encoded_scope = scope.to_dict()
    assert encoded_scope["resource_keys"] == [list(key.coordinates())]
    wire = json.dumps(encoded_scope, ensure_ascii=False)
    decoded_scope = ExchangeSelectionScope.from_dict(json.loads(wire))
    assert decoded_scope.resource_keys == (key,)
    assert decoded_scope.to_dict() == encoded_scope
    broken = copy.deepcopy(encoded_scope)
    broken["resource_keys"][0][2] = "plain-id"
    with pytest.raises(ExchangeError, match="INVALID_SELECTION"):
        ExchangeSelectionScope.from_dict(broken)


@pytest.mark.parametrize(
    "owner_kind, suffix",
    [
        ("resource", ("complete",)),
        ("field", ("title", "complete")),
        ("collection", ("comments", "{}", "complete")),
    ],
)
def test_coverage_owner_reconstruction_enforces_serialized_resource_identity(
    owner_kind, suffix
):
    key = ResourceKey.from_native(SERVICE, "issue", ["project", "731"])
    scope = CoverageScope(owner_kind, (*key.coordinates(), *suffix))
    assert json.loads(scope.encoded)[:3] == list(key.coordinates())
    with pytest.raises(ValueError):
        CoverageScope(owner_kind, (SERVICE, "issue", "731", *suffix))


@pytest.mark.parametrize("state", ["unresolved_provider_only", "resolved"])
def test_nested_provider_scope_id_is_serialized_without_fallback(state):
    provider_id = encode_identity(["github:node_id", "731"])
    kwargs = {"repository_uuidv4": REPOSITORY} if state == "resolved" else {}
    scope = ProviderRepositoryRoleScope(
        "owning_repository", CLOCK, state, provider_id, **kwargs
    )
    assert scope.to_dict()["provider_repository_id"] == provider_id
    with pytest.raises(ValueError):
        ProviderRepositoryRoleScope("owning_repository", CLOCK, state, "731", **kwargs)


def test_nested_mapping_support_reconstruction_requires_exact_serialized_ids():
    provider = ResourceKey.from_native(SERVICE, "repository", ["node", "731"])
    claim = MappingClaimKey.for_repository(
        provider, REPOSITORY, clock=CLOCK, provenance_json=PROVENANCE
    )
    support = MappingSupport(provider, (claim,))
    encoded = support.to_dict()
    assert MappingSupport.from_dict(encoded) == support
    assert encoded["provider_repository_id"] == provider.provider_resource_id
    broken = copy.deepcopy(encoded)
    broken["provider_repository_id"] = "731"
    broken["supporting_claims"][0]["provider_resource_id"] = "731"
    with pytest.raises(ValueError):
        MappingSupport.from_dict(broken)


def test_generic_json_and_exchange_envelope_keep_their_independent_profiles():
    assert (
        canonical({"value": [None, 1, True, "é"]})
        == '{"value":[null,1,true,"\\u00e9"]}'
    )
    key = ResourceKey.from_native(SERVICE, "vendor.resource", "é")
    package = ExchangePackage(
        PACKAGE,
        1,
        SERVICE,
        REPOSITORY,
        selection_scope=ExchangeSelectionScope(resource_keys=(key,)),
        selection_report={"label": "é"},
    )
    content = _canonical_content(package)
    assert b'"label":"\xc3\xa9"' in content
    assert b'"label":"\\u00e9"' not in content
    # Inner canonical TEXT keeps its backslashes under the outer UTF-8 profile.
    decoded = json.loads(content)
    assert decoded["selection_scope"]["resource_keys"][0][2] == '"\\u00e9"'
    assert "digest_sha256" not in decoded
    assert package.digest_sha256 == hashlib.sha256(content).hexdigest()
