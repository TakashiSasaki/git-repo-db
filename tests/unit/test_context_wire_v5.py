"""I6-B Author vectors: exact v5 grammar preserves reports, never grants admission."""

import copy
import hashlib
import json

import pytest

from repo_catalog.domain.context_wire import decode_context_v5, encode_context_v5
from repo_catalog.domain.exchange import (
    ExchangeError,
    ExchangePackage,
    ExchangeSelectionScope,
    decode_package,
    empty_context_section,
    encode_package,
)
from repo_catalog.domain.p1_context import ResourceKey, canonical
from repo_catalog.domain.resource_identification import ResourceIdentification as RI
from repo_catalog.domain.resource_identity import encode_identity

SERVICE = "11111111-1111-4111-8111-111111111111"
REPOSITORY = "22222222-2222-4222-8222-222222222222"
PACKAGE = "33333333-3333-4333-8333-333333333333"
SOURCE = "44444444-4444-4444-8444-444444444444"
PROVENANCE = canonical({"source": "fixture", "evidence": "C"})
RESOURCE_COLUMNS = (
    "service_instance_uuidv4",
    "resource_kind",
    "provider_resource_id",
    "identifier_namespace_kind",
    "identifier_namespace_id",
    "document_kind",
    "provider_document_id",
)


def resource_row(declaration):
    return dict(
        zip(
            RESOURCE_COLUMNS,
            (*declaration.resource.coordinates(), *declaration.columns),
            strict=True,
        )
    )


def context_with(*declarations):
    data = empty_context_section()
    data["providers"] = [
        {
            "service_instance_uuidv4": SERVICE,
            "provider_kind": "fixture",
            "configuration_json": "{}",
        }
    ]
    data["resources"] = [resource_row(d) for d in declarations]
    return data


def owner_row(key):
    return dict(zip(RESOURCE_COLUMNS[:3], key.coordinates(), strict=True))


def relation_row(
    owner, members, *, kind="links", provenance=PROVENANCE, observed=200, scope="{}"
):
    return {
        **owner_row(owner),
        "relation_kind": kind,
        "members_json": canonical([m.coordinates() for m in members]),
        "provenance_json": provenance,
        "scope_json": scope,
        "observed_at_us": observed,
    }


def collection_row(
    owner, members, *, state="complete", observed=203, provenance=PROVENANCE, scope="{}"
):
    row = relation_row(
        owner,
        members,
        kind="related",
        provenance=provenance,
        observed=observed,
        scope=scope,
    )
    row["collection_kind"] = row.pop("relation_kind")
    row["terminal_state"] = state
    return row


def transfer_context(*, two_sided=False, provider_only=False):
    """V02–V07 exact originals with independent Parent and Event clocks."""
    issue = ResourceKey.from_native(SERVICE, "issue", "I7")
    event = ResourceKey.document(issue, "comment", "timeline_event", "E")
    data = context_with(
        RI.unscoped(issue), RI.scoped(event, issue, "timeline_event", "E")
    )
    parent = relation_row(
        event,
        [issue],
        kind="parent",
        provenance=canonical({"evidence": "P", "source": "fixture-provider"}),
        scope=canonical(
            {
                "clock": {"at_us": 50, "domain": "provider"},
                "document_kind": "timeline_event",
                "state": "complete",
            }
        ),
        observed=51,
    )
    roles = (
        ["transfer_from_repository", "transfer_to_repository"]
        if two_sided
        else ["transfer_to_repository"]
    )
    scope = {
        "clock": {"at_us": 100, "domain": "provider"},
        "endpoints": [[r, "null"] for r in roles],
        "event_type": "transferred",
        "from_provider_repository_id": None,
        "parent_members_json": parent["members_json"],
        "parent_provenance_json": parent["provenance_json"],
        "parent_scope_json": parent["scope_json"],
        "provided_roles": roles,
        "to_provider_repository_id": None,
    }
    members = []
    if provider_only:
        provider = ResourceKey.from_native(SERVICE, "repository", "R")
        data["resources"].append(resource_row(RI.unscoped(provider)))
        members = [provider]
        scope["endpoints"] = []
        scope["to_provider_repository_id"] = provider.provider_resource_id
    report = relation_row(
        event,
        members,
        kind="transfer_event_report",
        provenance=canonical({"evidence": "E", "source": "fixture-provider"}),
        scope=canonical(scope),
        observed=101,
    )
    data["resource_relations"] = [parent, report]
    data["resource_repository_relations"] = [
        {
            **owner_row(event),
            "relation_kind": role,
            "clock_json": canonical(scope["clock"]),
            "target_json": target,
            "provenance_json": report["provenance_json"],
            "observed_at_us": 101,
            "event_report_members_json": report["members_json"],
            "event_report_scope_json": report["scope_json"],
        }
        for role, target in scope["endpoints"]
    ]
    return data


def package_dict(context=None):
    return ExchangePackage(
        PACKAGE,
        1,
        SERVICE,
        REPOSITORY,
        ExchangeSelectionScope(all_selected=True),
        context=context,
    ).to_dict()


def rechecksum(data):
    content = {k: v for k, v in data.items() if k != "digest_sha256"}
    data["digest_sha256"] = hashlib.sha256(
        json.dumps(
            content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return data


@pytest.mark.parametrize(
    "native", ["", [], [""], [[]], ["p", []], "é😀", ["e\u0301", "é"]]
)
@pytest.mark.parametrize("contract", ["global", "scoped", "opaque"])
def test_T01_T02_V01_V02_identity_and_all_seven_named_columns(native, contract):
    namespace = ResourceKey.from_native(SERVICE, "pull_request", ["org", "7"])
    if contract == "global":
        key = ResourceKey.global_document(SERVICE, native)
        declaration = RI.global_document(key)
    elif contract == "scoped":
        key = ResourceKey.document(namespace, "document", "body", native)
        declaration = RI.scoped(key, namespace, "body", native)
    else:
        key = ResourceKey.from_native(SERVICE, "x-widget", native)
        declaration = RI.unscoped(key)
    original = context_with(declaration)
    decoded = decode_context_v5(encode_context_v5(original))
    assert decoded == original
    assert tuple(decoded["resources"][0][k] for k in RESOURCE_COLUMNS) == (
        *key.coordinates(),
        *declaration.columns,
    )
    assert decoded["resource_relations"] == []
    assert decoded["resource_repository_relations"] == []
    assert not any(
        r["provider_resource_id"] == namespace.provider_resource_id
        for r in decoded["resources"]
    )
    assert RI.from_wire(declaration.to_wire()) == declaration


@pytest.mark.parametrize(
    "value",
    [
        ' "D" ',
        '"\\u0044"',
        '"é"',
        "D",
        "7",
        "true",
        "null",
        "[1]",
        "{}",
        7,
        True,
        None,
        [],
        {},
    ],
)
def test_T01_V08_noncanonical_or_wrong_type_identity_is_rejected(value):
    key = ResourceKey.global_document(SERVICE, "D")
    data = context_with(RI.global_document(key))
    data["resources"][0]["provider_resource_id"] = value
    with pytest.raises(ExchangeError):
        decode_context_v5(data)


@pytest.mark.parametrize("field", RESOURCE_COLUMNS)
def test_T02_V08_every_resource_column_is_mandatory(field):
    data = context_with(RI.global_document(ResourceKey.global_document(SERVICE, "D")))
    del data["resources"][0][field]
    with pytest.raises(ExchangeError):
        decode_context_v5(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider_document_id", None),
        ("identifier_namespace_kind", "issue"),
        ("document_kind", "body"),
        ("verified", True),
    ],
)
def test_T02_V08_malformed_known_identification_has_no_dispatch_fallback(field, value):
    data = context_with(RI.global_document(ResourceKey.global_document(SERVICE, "D")))
    data["resources"][0][field] = value
    with pytest.raises(ExchangeError):
        decode_context_v5(data)


def test_T01_V08_scoped_namespace_must_reconstruct_same_binary_identity():
    data = transfer_context()
    data["resources"][1]["identifier_namespace_id"] = '"I8"'
    with pytest.raises(ExchangeError):
        decode_context_v5(data)


@pytest.mark.parametrize(
    "format",
    ["git-repo-db/adr0030-exchange-v4", "git-repo-db/adr0031-exchange-v6", "", None, 5],
)
def test_T10_V08_v5_reader_rejects_other_versions_even_with_correct_checksum(format):
    data = package_dict()
    data["format"] = format
    with pytest.raises(ExchangeError) as error:
        decode_package(rechecksum(data))
    assert error.value.code == "UNSUPPORTED_WIRE_VERSION"


def test_T10_V08_missing_version_is_not_inferred():
    data = package_dict()
    del data["format"]
    with pytest.raises(ExchangeError) as error:
        decode_package(rechecksum(data))
    assert error.value.code == "UNSUPPORTED_WIRE_VERSION"


@pytest.mark.parametrize(
    "field",
    ["include_core", "include_context", "include_retained_bytes", "all_selected"],
)
@pytest.mark.parametrize("value", [0, 1, "true", None])
def test_T10_selection_flags_are_not_boolean_coercions(field, value):
    data = package_dict()
    data["selection_scope"][field] = value
    with pytest.raises(ExchangeError):
        decode_package(rechecksum(data))


def test_T10_checksum_is_recomputed_over_outer_utf8_content():
    data = package_dict(
        context_with(RI.unscoped(ResourceKey.from_native(SERVICE, "x-é", "é")))
    )
    encoded = encode_package(decode_package(data))
    assert "x-é" in encoded
    assert data["digest_sha256"] == rechecksum(copy.deepcopy(data))["digest_sha256"]
    data["context"]["resources"][0]["resource_kind"] = "x-other"
    with pytest.raises(ExchangeError) as error:
        decode_package(data)
    assert error.value.code == "DIGEST_MISMATCH"
    corrected = rechecksum(data)
    assert (
        decode_package(corrected).context["resources"][0]["resource_kind"] == "x-other"
    )


@pytest.mark.parametrize(
    "raw",
    [
        b"\xff",
        b'{"resources":[],"resources":[]}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":"\\ud800"}',
        b'{"x":"\\udfff"}',
    ],
)
def test_T10_V08_strict_json_utf8_duplicates_nonfinite_and_surrogates(raw):
    with pytest.raises(ExchangeError):
        decode_context_v5(raw)


def test_T10_duplicate_embedded_key_is_rejected_before_roundtrip_repair():
    data = transfer_context()
    data["resource_relations"][0]["provenance_json"] = (
        '{"source":"fixture","evidence":"P","evidence":"P"}'
    )
    with pytest.raises(ExchangeError):
        decode_context_v5(data)


def test_T10_cyclic_caller_input_stops_finitely_without_recursion_escape():
    data = empty_context_section()
    data["resources"].append(data)
    with pytest.raises(ExchangeError):
        decode_context_v5(data)


@pytest.mark.parametrize(
    "two_sided,provider_only", [(False, False), (True, False), (False, True)]
)
def test_T03_T05_T06_V03_V07_original_parent_endpoint_semantics(
    two_sided, provider_only
):
    original = transfer_context(two_sided=two_sided, provider_only=provider_only)
    decoded = decode_context_v5(encode_context_v5(original))
    assert decoded == original
    parent, event = decoded["resource_relations"]
    assert parent["observed_at_us"] == 51
    assert json.loads(parent["scope_json"])["clock"]["at_us"] == 50
    assert event["observed_at_us"] == 101
    assert json.loads(event["scope_json"])["clock"]["at_us"] == 100
    assert parent["provenance_json"] != event["provenance_json"]
    assert json.loads(event["scope_json"])["parent_scope_json"] == parent["scope_json"]
    assert len(decoded["resource_repository_relations"]) == (
        0 if provider_only else 2 if two_sided else 1
    )
    for endpoint in decoded["resource_repository_relations"]:
        assert endpoint["event_report_members_json"] == event["members_json"]
        assert endpoint["event_report_scope_json"] == event["scope_json"]
        assert endpoint["target_json"] == "null"


@pytest.mark.parametrize(
    "field",
    [
        "parent_members_json",
        "parent_provenance_json",
        "parent_scope_json",
        "endpoints",
        "provided_roles",
    ],
)
@pytest.mark.parametrize("mutation", ["omit", "null"])
def test_T05_T10_V08_incomplete_original_never_borrows_event_or_surviving_rows(
    field, mutation
):
    data = transfer_context()
    event = data["resource_relations"][1]
    scope = json.loads(event["scope_json"])
    if mutation == "omit":
        del scope[field]
    else:
        scope[field] = None
    event["scope_json"] = canonical(scope)
    data["resource_repository_relations"][0]["event_report_scope_json"] = event[
        "scope_json"
    ]
    with pytest.raises(ExchangeError):
        decode_context_v5(data)


def test_T05_V05_truncated_two_sided_report_is_not_one_sided():
    data = transfer_context(two_sided=True)
    data["resource_repository_relations"].pop(0)
    with pytest.raises(ExchangeError) as error:
        decode_context_v5(data)
    assert error.value.code == "INCOMPLETE_ENDPOINT_SET"


def test_T03_V08_complete_parent_key_requires_its_actual_original_row():
    data = transfer_context()
    data["resource_relations"].pop(0)
    with pytest.raises(ExchangeError) as error:
        decode_context_v5(data)
    assert error.value.code == "MISSING_DEPENDENCY"


def test_T03_T27_event_does_not_choose_other_parent_provenance():
    data = transfer_context()
    different = copy.deepcopy(data["resource_relations"][0])
    different["provenance_json"] = canonical(
        {"source": "fixture-provider", "evidence": "other-P"}
    )
    data["resource_relations"][0] = different
    with pytest.raises(ExchangeError) as error:
        decode_context_v5(data)
    assert error.value.code == "MISSING_DEPENDENCY"


@pytest.mark.parametrize(
    "field", ["event_report_members_json", "event_report_scope_json"]
)
def test_T05_V08_endpoint_complete_reference_field_cannot_be_omitted(field):
    data = transfer_context()
    del data["resource_repository_relations"][0][field]
    with pytest.raises(ExchangeError):
        decode_context_v5(data)


@pytest.mark.parametrize("observed", [True, 1.0, "101", 0, -1, 2**63])
def test_T10_V08_times_reject_wrong_types_and_range_before_affinity(observed):
    data = transfer_context()
    data["resource_relations"][0]["observed_at_us"] = observed
    with pytest.raises(ExchangeError):
        decode_context_v5(data)


def test_T11_T12_T27_V09_generic_order_alternatives_and_real_terminals_survive():
    # Global Documents may own generic children without a semantic Parent report.
    owner = ResourceKey.global_document(SERVICE, "D")
    child = ResourceKey.from_native(SERVICE, "x-child", "C")
    widget = ResourceKey.from_native(SERVICE, "x-widget", ["p", []])
    data = context_with(
        RI.global_document(owner), RI.unscoped(child), RI.unscoped(widget)
    )
    data["resource_relations"] = [
        relation_row(owner, [child, widget]),
        relation_row(owner, [widget, child]),
    ]
    data["collections"] = [
        collection_row(owner, [], observed=200),
        collection_row(owner, [], state="partial", observed=201),
        collection_row(owner, [child], state="unknown", observed=202),
        collection_row(owner, [child, widget]),
        collection_row(owner, [child], state="partial", observed=204),
        collection_row(owner, [child, widget], observed=205),
        collection_row(owner, [widget, child], observed=205),
    ]
    decoded = decode_context_v5(encode_context_v5(data))
    assert decoded == data
    assert (
        decoded["resource_relations"][0]["members_json"]
        != decoded["resource_relations"][1]["members_json"]
    )
    assert [
        (r["terminal_state"], json.loads(r["members_json"]))
        for r in decoded["collections"][:3]
    ] == [("complete", []), ("partial", []), ("unknown", [list(child.coordinates())])]
    assert (
        decoded["collections"][-1]["members_json"]
        != decoded["collections"][-2]["members_json"]
    )
    assert not any(
        r["relation_kind"] == "parent" for r in decoded["resource_relations"]
    )


@pytest.mark.parametrize(
    "mutation", ["duplicate", "no-time", "scope-rebind", "bad-state"]
)
def test_T12_T27_V09_malformed_collection_not_repaired(mutation):
    owner = ResourceKey.global_document(SERVICE, "D")
    child = ResourceKey.from_native(SERVICE, "x-child", "C")
    data = context_with(RI.global_document(owner), RI.unscoped(child))
    row = collection_row(owner, [child])
    data["collections"] = [row]
    if mutation == "duplicate":
        row["members_json"] = canonical([child.coordinates(), child.coordinates()])
    elif mutation == "no-time":
        row["observed_at_us"] = None
    elif mutation == "scope-rebind":
        data["collections"].append(
            {**row, "observed_at_us": 204, "scope_json": '{"changed":true}'}
        )
    else:
        row["terminal_state"] = "empty"
    with pytest.raises(ExchangeError):
        decode_context_v5(data)


def test_T27_same_original_report_key_changed_observation_is_conflict():
    data = transfer_context()
    original = data["resource_relations"][0]
    data["resource_relations"].append({**original, "observed_at_us": 52})
    with pytest.raises(ExchangeError) as error:
        decode_context_v5(data)
    assert error.value.code == "IMMUTABLE_REPLAY_CONFLICT"


@pytest.mark.parametrize("boundary", ["bytes", "depth", "nodes"])
def test_T01_identity_limits_include_exact_boundary_and_refuse_plus_one(boundary):
    if boundary == "bytes":
        accepted, refused = "a" * (262144 - 2), "a" * (262144 - 1)
    elif boundary == "nodes":
        accepted, refused = [""] * 4095, [""] * 4096
    else:
        accepted = "x"
        for _ in range(32):
            accepted = [accepted]
        refused = [accepted]
    assert encode_identity(accepted)
    with pytest.raises((TypeError, ValueError)):
        encode_identity(refused)


def source_context(*, partial=False, terminal=True):
    """R07/V09 originals; inventory set order is independent of arrival order."""
    from repo_catalog.domain.p1_context import CoverageScope

    second = "55555555-5555-4555-8555-555555555555"
    scope = canonical(
        {"coverage_kind": "repositories", "service_instance_uuidv4": SERVICE}
    )
    data = context_with()
    data["repositories"] = [
        {"repository_uuidv4": r, "configuration_json": "{}"}
        for r in (REPOSITORY, second)
    ]
    data["sources"] = [
        {
            "source_registration_uuidv4": SOURCE,
            "service_instance_uuidv4": SERVICE,
            "configuration_json": "{}",
        }
    ]
    data["source_repositories"] = [
        {
            "source_registration_uuidv4": SOURCE,
            "repository_uuidv4": r,
            "attributes_json": "{}",
        }
        for r in (REPOSITORY, second)
    ]
    inventory = {
        "source_registration_uuidv4": SOURCE,
        "scope_json": scope,
        "observed_at_us": 40,
        "coverage_state": "partial" if partial else "complete",
        "terminal": terminal,
        "members_json": canonical([REPOSITORY] if partial else [REPOSITORY, second]),
        "provenance_json": PROVENANCE,
    }
    data["source_inventories"] = [inventory]
    if not partial and terminal:
        owner = CoverageScope.source_inventory(SOURCE, scope, "repositories")
        coordinates = canonical(owner.coordinates)
        scope_row = {
            "owner_kind": "source_inventory",
            "owner_coordinates_json": coordinates,
        }
        data["coverage_scopes"] = [scope_row]
        data["coverage_claims"] = [
            {
                **scope_row,
                "observed_at_us": 40,
                "coverage_state": "complete",
                "details_json": None,
            }
        ]
        data["coverage_proofs"] = [
            {
                **scope_row,
                "observed_at_us": 40,
                "coverage_state": "complete",
                "proof_kind": "source_inventory",
                "source_registration_uuidv4": SOURCE,
                "scope_json": scope,
                "provenance_json": PROVENANCE,
                "terminal_observed_at_us": 40,
                "terminal_state": "complete",
                "terminal": True,
                "members_json": inventory["members_json"],
            }
        ]
    return data


def resolved_transfer_context():
    """V07: exact MappingClaimKey in original provenance, never a sender grant."""
    from repo_catalog.domain.p1_context import (
        FieldClock,
        MappingClaimKey,
        MappingSupport,
        encode_transfer_supported_provenance,
    )

    data = transfer_context(provider_only=True)
    provider = ResourceKey.from_native(SERVICE, "repository", "R")
    claim = MappingClaimKey(
        provider,
        "represents_repository",
        FieldClock("provider", 80),
        canonical(REPOSITORY),
        canonical({"source": "fixture-provider", "evidence": "M"}),
    )
    support = MappingSupport(provider, (claim,))
    provenance = encode_transfer_supported_provenance(
        "fixture-provider", "E", [("transfer_to_repository", support)]
    )
    data["repositories"] = [
        {"repository_uuidv4": REPOSITORY, "configuration_json": "{}"}
    ]
    event = data["resource_relations"][1]
    event["provenance_json"] = provenance
    scope = json.loads(event["scope_json"])
    scope["endpoints"] = [["transfer_to_repository", canonical(REPOSITORY)]]
    event["scope_json"] = canonical(scope)
    mapping = {
        **owner_row(provider),
        "relation_kind": "represents_repository",
        "clock_json": claim.clock_json,
        "target_json": claim.target_json,
        "provenance_json": claim.provenance_json,
        "observed_at_us": 81,
        "event_report_members_json": None,
        "event_report_scope_json": None,
    }
    endpoint = {
        **owner_row(ResourceKey(*[event[k] for k in RESOURCE_COLUMNS[:3]])),
        "relation_kind": "transfer_to_repository",
        "clock_json": canonical(scope["clock"]),
        "target_json": canonical(REPOSITORY),
        "provenance_json": provenance,
        "observed_at_us": 101,
        "event_report_members_json": event["members_json"],
        "event_report_scope_json": event["scope_json"],
    }
    data["resource_repository_relations"] = [mapping, endpoint]
    return data


def test_T06_T10_V07_exact_mapping_support_and_endpoint_originals_survive():
    data = resolved_transfer_context()
    assert decode_context_v5(encode_context_v5(data)) == data
    mapping, endpoint = data["resource_repository_relations"]
    evidence = json.loads(endpoint["provenance_json"])["evidence"]
    assert mapping["clock_json"] != endpoint["clock_json"]
    assert evidence
    assert (
        endpoint["event_report_scope_json"]
        == data["resource_relations"][1]["scope_json"]
    )
    assert (
        endpoint["event_report_members_json"]
        == data["resource_relations"][1]["members_json"]
    )


@pytest.mark.parametrize(
    "field", ["target_json", "event_report_scope_json", "event_report_members_json"]
)
def test_T10_V08_resolved_endpoint_cannot_rebind_scope_or_target(field):
    data = resolved_transfer_context()
    data["resource_repository_relations"][1][field] = (
        "null" if field == "target_json" else "{}"
    )
    with pytest.raises(ExchangeError):
        decode_context_v5(data)


def test_T12_T13_V09_partial_inventory_preserves_known_positive_pairs():
    original = source_context(partial=True, terminal=False)
    decoded = decode_context_v5(encode_context_v5(original))
    assert decoded == original
    assert len(decoded["source_repositories"]) == 2
    assert json.loads(decoded["source_inventories"][0]["members_json"]) == [REPOSITORY]
    assert decoded["source_inventories"][0]["terminal"] is False
    assert decoded["source_inventories"][0]["coverage_state"] == "partial"
    assert decoded["coverage_claims"] == []


def test_T12_T13_V09_complete_inventory_and_five_column_coverage_are_lossless():
    data = source_context()
    assert decode_context_v5(encode_context_v5(data)) == data
    assert len(data["coverage_claims"][0]) == 5
    assert data["coverage_claims"][0]["coverage_state"] == "complete"


@pytest.mark.parametrize(
    "field,value",
    [
        ("terminal", False),
        ("terminal_state", "partial"),
        ("members_json", "[]"),
        ("terminal_observed_at_us", 39),
        ("provenance_json", canonical({"source": "fixture", "evidence": "other"})),
    ],
)
def test_T13_coverage_proof_must_quote_every_original_terminal_coordinate(field, value):
    data = source_context()
    data["coverage_proofs"][0][field] = value
    with pytest.raises(ExchangeError) as error:
        decode_context_v5(data)
    assert error.value.code == "INVALID_COVERAGE_PROOF"


def test_T13_cross_service_source_scope_is_rejected():
    data = source_context(partial=True)
    data["source_inventories"][0]["scope_json"] = canonical(
        {"service_instance_uuidv4": REPOSITORY}
    )
    with pytest.raises(ExchangeError) as error:
        decode_context_v5(data)
    assert error.value.code == "SOURCE_SERVICE"


def test_T13_source_inventory_is_a_canonical_set_and_terminal_is_strict_bool():
    data = source_context(partial=True)
    data["source_inventories"][0]["terminal"] = 1
    with pytest.raises(ExchangeError):
        decode_context_v5(data)
    data = source_context()
    members = json.loads(data["source_inventories"][0]["members_json"])
    data["source_inventories"][0]["members_json"] = canonical(members[::-1])
    with pytest.raises(ExchangeError):
        decode_context_v5(data)


@pytest.mark.parametrize(
    "section", ["resource_relations", "field_candidates", "coverage_scopes"]
)
def test_T10_rechecksummed_package_revalidates_every_embedded_resource_key(section):
    owner = ResourceKey.from_native(SERVICE, "issue", "I7")
    data = context_with(RI.unscoped(owner))
    if section == "resource_relations":
        data[section] = [relation_row(owner, [owner])]
    elif section == "field_candidates":
        data[section] = [
            {
                **owner_row(owner),
                "field_name": "title",
                "value_json": '"title"',
                "clock_domain": "provider",
                "clock_ts_us": 100,
                "observed_at_us": 101,
                "provenance_json": PROVENANCE,
            }
        ]
    else:
        from repo_catalog.domain.p1_context import CoverageScope

        coverage = CoverageScope.resource(owner, "related")
        data[section] = [
            {
                "owner_kind": coverage.owner_kind,
                "owner_coordinates_json": canonical(coverage.coordinates),
            }
        ]
    package = package_dict(data)
    if section == "resource_relations":
        package["context"][section][0]["members_json"] = canonical(
            [[SERVICE, "issue", ' "I7" ']]
        )
    elif section == "field_candidates":
        package["context"][section][0]["provider_resource_id"] = ' "I7" '
    else:
        coordinates = json.loads(
            package["context"][section][0]["owner_coordinates_json"]
        )
        coordinates[2] = ' "I7" '
        package["context"][section][0]["owner_coordinates_json"] = canonical(
            coordinates
        )
    with pytest.raises(ExchangeError):
        decode_package(rechecksum(package))


def test_T10_rechecksummed_package_rejects_unknown_top_level_and_row_fields():
    package = package_dict(
        context_with(RI.unscoped(ResourceKey.from_native(SERVICE, "issue", "I7")))
    )
    package["context"]["resources"][0]["verified"] = True
    with pytest.raises(ExchangeError):
        decode_package(rechecksum(package))
    package = package_dict()
    package["verified"] = True
    with pytest.raises(ExchangeError):
        decode_package(rechecksum(package))


def test_T01_T10_decoded_container_and_string_subclasses_are_not_json_primitives():
    class CallerString(str):
        pass

    class CallerDict(dict):
        pass

    for value in (
        CallerDict(empty_context_section()),
        tuple(empty_context_section().values()),
    ):
        with pytest.raises(ExchangeError):
            decode_context_v5(value)
    data = context_with(RI.unscoped(ResourceKey.from_native(SERVICE, "issue", "I7")))
    data["resources"][0]["provider_resource_id"] = CallerString('"I7"')
    with pytest.raises(ExchangeError):
        decode_context_v5(data)


def test_T01_T11_outer_byte_limit_is_inclusive_using_real_canonical_bytes():
    from repo_catalog.domain.exchange import MAX_PACKAGE_BYTES, _bounded_json

    overhead = len(b'{"x":""}')
    exact = {"x": "a" * (MAX_PACKAGE_BYTES - overhead)}
    assert len(json.dumps(exact, separators=(",", ":")).encode()) == MAX_PACKAGE_BYTES
    assert _bounded_json(exact)[1] == MAX_PACKAGE_BYTES
    exact["x"] += "a"
    with pytest.raises(ExchangeError) as error:
        _bounded_json(exact)
    assert error.value.code == "INPUT_LIMIT"


def test_T01_T11_outer_size_measurement_matches_actual_nested_delimiters():
    from repo_catalog.domain.exchange import _bounded_json

    data = {"a": [{}, [], "é", {"c": [True, None, 42]}], "z": {"nested": "value"}}
    assert _bounded_json(data)[1] == len(
        json.dumps(
            data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    )


def test_T01_T11_identity_decoding_counts_toward_aggregate_element_limit():
    # Each identity is independently valid at the 4,096-value cap. Transport must
    # also charge its decoded values against the enclosing 200,000-value cap.
    declarations = [
        RI.unscoped(
            ResourceKey.from_native(SERVICE, "x-widget", [str(i), *([""] * 4094)])
        )
        for i in range(49)
    ]
    accepted = context_with(*declarations[:48])
    assert decode_context_v5(accepted) == accepted
    with pytest.raises(ExchangeError) as error:
        decode_context_v5(context_with(*declarations))
    assert error.value.code == "INPUT_LIMIT"


def test_T01_T11_identity_depth_counts_toward_enclosing_json_depth_limit():
    value = "leaf"
    for _ in range(32):
        value = [value]
    # The identity authority accepts 32 arrays by itself; its enclosing Resource
    # row/section consumes additional depth, so this unit cannot be transported.
    declaration = RI.unscoped(ResourceKey.from_native(SERVICE, "x-widget", value))
    with pytest.raises(ExchangeError) as error:
        decode_context_v5(context_with(declaration))
    assert error.value.code == "INPUT_LIMIT"


@pytest.mark.parametrize("location", ["selection", "relation-member", "coverage-owner"])
def test_T01_T10_aggregate_identity_depth_is_checked_at_every_reference_location(
    location,
):
    value = "leaf"
    for _ in range(32):
        value = [value]
    deep = ResourceKey.from_native(SERVICE, "x-widget", value)
    owner = ResourceKey.from_native(SERVICE, "issue", "I7")
    data = package_dict(context_with(RI.unscoped(owner)))
    if location == "selection":
        data["selection_scope"]["resource_keys"] = [list(deep.coordinates())]
    elif location == "relation-member":
        data["context"]["resource_relations"] = [relation_row(owner, [deep])]
    else:
        from repo_catalog.domain.p1_context import CoverageScope

        coverage = CoverageScope.resource(deep, "related")
        data["context"]["coverage_scopes"] = [
            {
                "owner_kind": coverage.owner_kind,
                "owner_coordinates_json": canonical(coverage.coordinates),
            }
        ]
    with pytest.raises(ExchangeError) as error:
        decode_package(rechecksum(data))
    assert error.value.code == "INPUT_LIMIT"


def test_T01_T11_decoded_identity_values_are_charged_to_actual_wire_work():
    from repo_catalog.domain.exchange import _WIRE_WORK

    key = ResourceKey.from_native(SERVICE, "x-widget", [""] * 1000)
    data = context_with(RI.unscoped(key))
    measurement = {"metadata_units": 0, "verification_bytes": 0}
    token = _WIRE_WORK.set(measurement)
    try:
        assert decode_context_v5(data) == data
    finally:
        _WIRE_WORK.reset(token)
    assert measurement["metadata_units"] >= 1001


@pytest.mark.parametrize(
    "section", ["resource_relations", "collections", "field_candidates"]
)
@pytest.mark.parametrize(
    "nested", [False, True], ids=["provenance-fields", "nested-evidence"]
)
def test_T10_attributed_evidence_resembling_resource_fields_remains_opaque(
    section, nested
):
    owner = ResourceKey.from_native(SERVICE, "issue", "I7")
    raw_evidence = {
        "service_instance_uuidv4": "attributed non-UUID text",
        "resource_kind": "attributed kind",
        "provider_resource_id": "raw noncanonical native text",
        "resource_keys": [[SERVICE, "x-widget", "raw-id"]],
    }
    provenance = (
        {"source": "fixture", "evidence": raw_evidence}
        if nested
        else {"source": "fixture", "evidence": "attributed report", **raw_evidence}
    )
    encoded_provenance = canonical(provenance)
    data = context_with(RI.unscoped(owner))
    if section == "resource_relations":
        row = relation_row(owner, [], provenance=encoded_provenance)
    elif section == "collections":
        row = collection_row(owner, [], provenance=encoded_provenance)
    else:
        row = {
            **owner_row(owner),
            "field_name": "title",
            "value_json": '"title"',
            "clock_domain": "provider",
            "clock_ts_us": 100,
            "observed_at_us": 101,
            "provenance_json": encoded_provenance,
        }
    data[section] = [row]
    assert decode_context_v5(encode_context_v5(data)) == data
    package = decode_package(package_dict(data))
    assert package.context == data
    assert json.loads(package.context[section][0]["provenance_json"]) == provenance


@pytest.mark.parametrize("failure", ["malformed", "depth", "elements"])
def test_T01_T11_failed_wire_scan_preserves_actual_work_charge(failure):
    from repo_catalog.domain.exchange import _WIRE_WORK, _bounded_json

    if failure == "malformed":
        data = {"value": object()}
    elif failure == "depth":
        data = "leaf"
        for _ in range(33):
            data = [data]
    else:
        data = [None] * 200001
    measurement = {"metadata_units": 0, "verification_bytes": 0}
    token = _WIRE_WORK.set(measurement)
    try:
        with pytest.raises(ExchangeError):
            _bounded_json(data)
    finally:
        _WIRE_WORK.reset(token)
    assert measurement["metadata_units"] > 0
