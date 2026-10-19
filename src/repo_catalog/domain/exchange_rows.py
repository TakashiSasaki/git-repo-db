"""Exact v4 row envelopes. No legacy row aliases or opaque extra fields."""

import json

from repo_catalog.domain.p1_core import encode

ROW_KEYS = {
    "context": {
        "collections": (
            (
                "collection_kind",
                "members_json",
                "observed_at_us",
                "provenance_json",
                "provider_resource_id",
                "resource_kind",
                "scope_json",
                "service_instance_uuidv4",
                "terminal_state",
            ),
        ),
        "core_references": (
            (
                "full_oid",
                "object_format",
                "provenance_json",
                "provider_resource_id",
                "resource_kind",
                "role",
                "service_instance_uuidv4",
            ),
        ),
        "coverage_claims": (
            (
                "coverage_state",
                "details_json",
                "observed_at_us",
                "owner_coordinates_json",
                "owner_kind",
            ),
        ),
        "coverage_proofs": (
            (
                "collection_kind",
                "coverage_state",
                "members_json",
                "observed_at_us",
                "owner_coordinates_json",
                "owner_kind",
                "proof_kind",
                "provenance_json",
                "provider_resource_id",
                "resource_kind",
                "service_instance_uuidv4",
                "terminal_observed_at_us",
                "terminal_state",
            ),
            (
                "coverage_state",
                "members_json",
                "observed_at_us",
                "owner_coordinates_json",
                "owner_kind",
                "proof_kind",
                "provenance_json",
                "scope_json",
                "source_registration_uuidv4",
                "terminal",
                "terminal_observed_at_us",
                "terminal_state",
            ),
        ),
        "coverage_scopes": (("owner_coordinates_json", "owner_kind"),),
        "field_candidates": (
            (
                "clock_domain",
                "clock_ts_us",
                "field_name",
                "observed_at_us",
                "provenance_json",
                "provider_resource_id",
                "resource_kind",
                "service_instance_uuidv4",
                "value_json",
            ),
        ),
        "providers": (
            ("configuration_json", "provider_kind", "service_instance_uuidv4"),
        ),
        "repositories": (("configuration_json", "repository_uuidv4"),),
        "repository_mapping_dispositions": (
            (
                "claim_clock_json",
                "claim_provenance_json",
                "claim_target_json",
                "disposition_clock_json",
                "disposition_kind",
                "disposition_provenance_json",
                "observed_at_us",
                "provider_resource_id",
                "relation_kind",
                "replacement_clock_json",
                "replacement_provenance_json",
                "replacement_target_json",
                "resource_kind",
                "service_instance_uuidv4",
            ),
        ),
        "resource_relations": (
            (
                "members_json",
                "observed_at_us",
                "provenance_json",
                "provider_resource_id",
                "relation_kind",
                "resource_kind",
                "scope_json",
                "service_instance_uuidv4",
            ),
        ),
        "resource_repository_relations": (
            (
                "clock_json",
                "observed_at_us",
                "provenance_json",
                "provider_resource_id",
                "relation_kind",
                "resource_kind",
                "service_instance_uuidv4",
                "target_json",
            ),
        ),
        "resources": (
            ("provider_resource_id", "resource_kind", "service_instance_uuidv4"),
        ),
        "source_inventories": (
            (
                "coverage_state",
                "members_json",
                "observed_at_us",
                "provenance_json",
                "scope_json",
                "source_registration_uuidv4",
                "terminal",
            ),
        ),
        "source_repositories": (
            ("attributes_json", "repository_uuidv4", "source_registration_uuidv4"),
        ),
        "sources": (
            (
                "configuration_json",
                "service_instance_uuidv4",
                "source_registration_uuidv4",
            ),
        ),
        "text_bodies": (("sha256", "text_value"),),
    },
    "core": {
        "captures": (
            (
                "capture_origin_uuidv4",
                "capture_uuidv4",
                "object_format",
                "ref",
                "repository_uuidv4",
                "root",
                "source",
            ),
        ),
        "coverage_claims": (
            (
                "coverage_state",
                "details_json",
                "observed_at_us",
                "owner_coordinates_json",
                "owner_kind",
            ),
        ),
        "coverage_proofs": (
            (
                "coverage_state",
                "members_json",
                "observed_at_us",
                "owner_coordinates_json",
                "owner_kind",
                "provenance_json",
            ),
        ),
        "coverage_scopes": (("owner_coordinates_json", "owner_kind"),),
        "git_objects": (("full_oid", "object_format"),),
        "git_observations": (
            (
                "capture_origin_uuidv4",
                "capture_uuidv4",
                "kind",
                "provenance_json",
                "repository_uuidv4",
                "scope_json",
                "value_json",
            ),
        ),
        "note_roles": (
            (
                "capture_origin_uuidv4",
                "capture_uuidv4",
                "note",
                "object_format",
                "path",
                "proof_bundle_json",
                "root",
                "target",
            ),
        ),
        "notes_claims": (
            (
                "capture_origin_uuidv4",
                "capture_uuidv4",
                "note",
                "object_format",
                "provenance_json",
                "target",
            ),
        ),
        "notes_groups": (
            (
                "authority",
                "capture_origin_uuidv4",
                "capture_uuidv4",
                "membership_json",
                "object_format",
                "provenance_json",
                "scope",
                "status",
            ),
        ),
        "notes_inventories": (
            (
                "capture_origin_uuidv4",
                "capture_uuidv4",
                "failure",
                "members",
                "status",
                "structures",
            ),
        ),
        "relation_groups": (
            (
                "authority",
                "full_oid",
                "membership_json",
                "object_format",
                "provenance_json",
                "relation",
                "scope",
                "status",
            ),
        ),
        "repositories": (("repository_uuidv4",),),
        "repository_claims": (
            ("field", "provenance_json", "repository_uuidv4", "value_json"),
        ),
        "retained_metadata": (
            (
                "body_hex",
                "digest_sha256",
                "full_oid",
                "native_type",
                "object_format",
                "physical_copy_uuidv4",
                "size",
            ),
        ),
        "retained_notes": (
            (
                "body_hex",
                "capture_origin_uuidv4",
                "capture_uuidv4",
                "digest_sha256",
                "full_oid",
                "object_format",
                "path",
                "physical_copy_uuidv4",
                "proof_bundle_json",
                "root",
                "size",
                "target",
            ),
        ),
        "scalar_claims": (
            (
                "authority",
                "field",
                "full_oid",
                "object_format",
                "provenance_json",
                "value_json",
            ),
        ),
    },
}


def validate_rows(core, context):
    # Local import keeps envelope validation independent of application services.
    from repo_catalog.domain.exchange import ExchangeError

    for store, data in (("core", core), ("context", context)):
        if data is None:
            continue
        for section, rows in data.items():
            for row in rows:
                if tuple(sorted(row)) not in ROW_KEYS[store][section]:
                    raise ExchangeError(
                        "MALFORMED_ROW", [store, section], "exact v4 keys required"
                    )
                for key, value in row.items():
                    if key.endswith("_json") and value is not None:
                        if (
                            not isinstance(value, str)
                            or encode(json.loads(value)) != value
                        ):
                            raise ExchangeError(
                                "NONCANONICAL_ROW", [store, section, key]
                            )
                if store == "core" and section == "coverage_proofs":
                    members = json.loads(row["members_json"])
                    if not isinstance(members, list) or any(
                        not isinstance(m, list) or len(m) != 2 for m in members
                    ):
                        raise ExchangeError(
                            "MALFORMED_ROW", ["core", section, "typed_members"]
                        )
                if store == "core" and section == "captures":
                    decode_native_ref(row["ref"])
                if "authority" in row and row["authority"] not in (
                    "reported",
                    "intrinsic",
                ):
                    raise ExchangeError("MALFORMED_ROW", [store, section, "authority"])


def decode_native_ref(value):
    from repo_catalog.domain.exchange import ExchangeError

    try:
        pair = json.loads(value)
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or pair[0] != "native-ref"
            or type(pair[1]) is not str
            or len(pair[1]) % 2
            or any(c not in "0123456789abcdef" for c in pair[1])
            or encode(pair) != value
        ):
            raise ValueError("canonical native-ref hex required")
        ref = bytes.fromhex(pair[1]).decode("utf-8", "surrogateescape")
        if not ref.startswith("refs/") or "\x00" in ref:
            raise ValueError("full native ref required")
        return ref
    except (ValueError, TypeError) as error:
        raise ExchangeError("INVALID_NATIVE_REF", "captures") from error
