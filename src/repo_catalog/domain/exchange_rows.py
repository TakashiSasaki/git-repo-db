"""Exact v5 row envelopes. No legacy row aliases or opaque extra fields."""

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
                "event_report_members_json",
                "event_report_scope_json",
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
            (
                "document_kind",
                "identifier_namespace_id",
                "identifier_namespace_kind",
                "provider_document_id",
                "provider_resource_id",
                "resource_kind",
                "service_instance_uuidv4",
            ),
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
    from repo_catalog.domain.exchange import ExchangeError, _parse_json
    from repo_catalog.domain.p1_context import CoverageScope, ResourceKey
    from repo_catalog.domain.resource_identification import ResourceIdentification
    from repo_catalog.domain.time import (
        validate_observation_us,
        validate_required_observation_us,
    )

    for store, data in (("core", core), ("context", context)):
        if data is None:
            continue
        for section, rows in data.items():
            for row in rows:
                if tuple(sorted(row)) not in ROW_KEYS[store][section]:
                    raise ExchangeError(
                        "MALFORMED_ROW", [store, section], "exact v5 keys required"
                    )
                if store == "context" and section == "resources":
                    if core is not None and row.get("resource_kind") in (
                        "review",
                        "thread",
                        "comment",
                        "document",
                    ):
                        # Staged identification for paired packages is deferred to
                        # preflight_i2_resources so Core-only selection succeeds.
                        pass
                    else:
                        try:
                            ResourceIdentification.from_wire(row)
                        except (TypeError, ValueError) as error:
                            raise ExchangeError(
                                "INVALID_IDENTIFICATION", section
                            ) from error
                for key, value in row.items():
                    if store == "context" and key in (
                        "observed_at_us",
                        "clock_ts_us",
                        "terminal_observed_at_us",
                    ):
                        validator = (
                            validate_required_observation_us
                            if key == "terminal_observed_at_us"
                            or (
                                key == "observed_at_us"
                                and section
                                in (
                                    "collections",
                                    "source_inventories",
                                    "coverage_claims",
                                    "coverage_proofs",
                                )
                            )
                            else validate_observation_us
                        )
                        try:
                            validator(value)
                        except (ValueError, TypeError) as error:
                            raise ExchangeError(
                                "MALFORMED_ROW",
                                [store, section, key],
                                "observation time required",
                            ) from error
                    if (
                        store == "context"
                        and key == "terminal"
                        and type(value) is not bool
                    ):
                        raise ExchangeError(
                            "MALFORMED_ROW",
                            [store, section, key],
                            "strict boolean required",
                        )
                    # Context wire columns are text except explicit time/boolean
                    # coordinates. SQLite TEXT affinity must not rewrite input.
                    if store == "context" and key not in (
                        "observed_at_us",
                        "clock_ts_us",
                        "terminal_observed_at_us",
                        "terminal",
                    ):
                        nullable = key in (
                            "identifier_namespace_kind",
                            "identifier_namespace_id",
                            "document_kind",
                            "provider_document_id",
                            "event_report_members_json",
                            "event_report_scope_json",
                            "details_json",
                            "replacement_clock_json",
                            "replacement_target_json",
                            "replacement_provenance_json",
                        )
                        if not (type(value) is str or (nullable and value is None)):
                            raise ExchangeError(
                                "MALFORMED_ROW", [store, section, key], "text required"
                            )
                    if key.endswith("_json") and value is not None:
                        if (
                            not isinstance(value, str)
                            or encode(_parse_json(value)) != value
                        ):
                            raise ExchangeError(
                                "NONCANONICAL_ROW", [store, section, key]
                            )
                if store == "context":
                    try:
                        resource_columns = (
                            "service_instance_uuidv4",
                            "resource_kind",
                            "provider_resource_id",
                        )
                        if all(name in row for name in resource_columns):
                            ResourceKey(*(row[name] for name in resource_columns))
                        if "owner_coordinates_json" in row:
                            coordinates = _parse_json(row["owner_coordinates_json"])
                            if type(coordinates) is not list:
                                raise ValueError(
                                    "typed Coverage coordinate array required"
                                )
                            CoverageScope(row["owner_kind"], coordinates)
                        if section in ("resource_relations", "collections") or (
                            section == "coverage_proofs"
                            and row["proof_kind"] == "collection"
                        ):
                            _resource_members(row["members_json"])
                        if section == "resource_repository_relations":
                            refs = (
                                row["event_report_members_json"],
                                row["event_report_scope_json"],
                            )
                            if row["relation_kind"] in (
                                "transfer_from_repository",
                                "transfer_to_repository",
                            ):
                                if any(type(value) is not str for value in refs):
                                    raise ExchangeError(
                                        "INCOMPLETE_ORIGINAL_REPORT", section
                                    )
                                _resource_members(refs[0])
                                _transfer_scope_references(row, _parse_json(refs[1]))
                            elif any(value is not None for value in refs):
                                raise ValueError(
                                    "non-Transfer report references must be null"
                                )
                        if (
                            section == "resource_relations"
                            and row["relation_kind"] == "transfer_event_report"
                        ):
                            _transfer_scope_references(
                                row, _parse_json(row["scope_json"])
                            )
                    except ExchangeError:
                        raise
                    except (ValueError, TypeError, IndexError, KeyError) as error:
                        raise ExchangeError(
                            "MALFORMED_ROW", [store, section], "invalid typed reference"
                        ) from error
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


def _resource_members(text):
    from repo_catalog.domain.exchange import _parse_json
    from repo_catalog.domain.p1_context import ResourceKey

    members = _parse_json(text)
    if type(members) is not list or any(
        type(member) is not list
        or len(member) != 3
        or any(type(value) is not str for value in member)
        for member in members
    ):
        raise ValueError("exact ResourceKey member arrays required")
    for member in members:
        ResourceKey(*member)


def _transfer_scope_references(row, scope):
    from repo_catalog.domain.p1_context import ResourceKey

    if type(scope) is not dict:
        raise ValueError("Transfer scope object required")
    if "parent_members_json" in scope:
        _resource_members(scope["parent_members_json"])
    for name in ("from_provider_repository_id", "to_provider_repository_id"):
        if scope.get(name) is not None:
            ResourceKey(row["service_instance_uuidv4"], "repository", scope[name])


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


# Direct immutable identities, using the v4 names of the actual PK coordinates.
# Other row types have their entire asserted value in the key; authority flags
# are payload, so contradictory sender annotations do not get an arrival winner.
IDENTITY_KEYS = {
    "core": {
        "captures": ("capture_origin_uuidv4", "capture_uuidv4"),
        "git_observations": (
            "capture_origin_uuidv4",
            "capture_uuidv4",
            "repository_uuidv4",
            "kind",
            "scope_json",
            "provenance_json",
        ),
        "repository_claims": ("repository_uuidv4", "field", "provenance_json"),
        "scalar_claims": (
            "object_format",
            "full_oid",
            "field",
            "provenance_json",
            "authority",
        ),
        "relation_groups": (
            "object_format",
            "full_oid",
            "relation",
            "scope",
            "provenance_json",
            "authority",
        ),
        "notes_claims": (
            "capture_origin_uuidv4",
            "capture_uuidv4",
            "object_format",
            "target",
            "provenance_json",
        ),
        "notes_groups": (
            "capture_origin_uuidv4",
            "capture_uuidv4",
            "object_format",
            "scope",
            "provenance_json",
            "authority",
        ),
        "retained_metadata": ("object_format", "full_oid", "physical_copy_uuidv4"),
        "retained_notes": ("object_format", "full_oid", "physical_copy_uuidv4"),
    },
    "context": {
        "providers": ("service_instance_uuidv4",),
        "repositories": ("repository_uuidv4",),
        "sources": ("source_registration_uuidv4",),
        "source_repositories": ("source_registration_uuidv4", "repository_uuidv4"),
        "text_bodies": ("sha256",),
        "resources": (
            "service_instance_uuidv4",
            "resource_kind",
            "provider_resource_id",
        ),
        "field_candidates": (
            "service_instance_uuidv4",
            "resource_kind",
            "provider_resource_id",
            "field_name",
            "clock_domain",
            "clock_ts_us",
            "value_json",
            "provenance_json",
        ),
        "resource_relations": (
            "service_instance_uuidv4",
            "resource_kind",
            "provider_resource_id",
            "relation_kind",
            "members_json",
            "provenance_json",
            "scope_json",
        ),
        "resource_repository_relations": (
            "service_instance_uuidv4",
            "resource_kind",
            "provider_resource_id",
            "relation_kind",
            "clock_json",
            "target_json",
            "provenance_json",
        ),
        "repository_mapping_dispositions": (
            "service_instance_uuidv4",
            "resource_kind",
            "provider_resource_id",
            "relation_kind",
            "claim_clock_json",
            "claim_target_json",
            "claim_provenance_json",
            "disposition_kind",
            "disposition_clock_json",
            "disposition_provenance_json",
        ),
    },
}


def validate_replay_consistency(core, context):
    from repo_catalog.domain.exchange import ExchangeError
    from repo_catalog.domain.p1_core import _performed

    for store, data in (("core", core), ("context", context)):
        if data is None:
            continue
        for section, rows in data.items():
            seen = {}
            collection_scopes = {}
            for row in rows:
                _performed("metadata_units", 1)
                if store == "context" and section == "collections":
                    collection_key = encode(
                        [
                            row[k]
                            for k in (
                                "service_instance_uuidv4",
                                "resource_kind",
                                "provider_resource_id",
                                "collection_kind",
                                "provenance_json",
                            )
                        ]
                    )
                    if (
                        collection_key in collection_scopes
                        and collection_scopes[collection_key] != row["scope_json"]
                    ):
                        raise ExchangeError(
                            "IMMUTABLE_REPLAY_CONFLICT", [store, section]
                        )
                    collection_scopes[collection_key] = row["scope_json"]
                columns = IDENTITY_KEYS[store].get(
                    section, tuple(sorted(k for k in row if k != "authority"))
                )
                key = encode([row[k] for k in columns])
                payload = encode(row)
                if key in seen and seen[key] != payload:
                    raise ExchangeError("IMMUTABLE_REPLAY_CONFLICT", [store, section])
                seen[key] = payload
