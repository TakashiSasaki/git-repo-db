"""Schemas for authored JSON and typed dependency admission.

Provider projections are deliberately opaque. Authored evidence recursively uses
the reference vocabulary below; unknown identity-looking keys fail closed. A
future decision UUID in Git derivation is a declaration, never a dependency.
The packaged SQL guards are generated from this same registry.
"""

from __future__ import annotations

import base64
import json
import re
import uuid
from dataclasses import dataclass

from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.time import validate_epoch_us


@dataclass(frozen=True)
class JsonSchema:
    category: str
    shape: str = "object"
    nullable: bool = False


JSON_REGISTRY = {}


def _register(category, fields, *, shape="object", nullable=False):
    for field in fields.split():
        table, column = field.split(".")
        JSON_REGISTRY[table, column] = JsonSchema(category, shape, nullable)


_register(
    "authored",
    """
service_instances.metadata repositories.metadata repository_bindings.metadata
repository_endpoints.metadata git_acquisitions.request resume_scopes.request_context
fetch_occurrences.request incremental_scans.evidence completion_markers.evidence
code_observations.details source_input_observations.request_context_json
parsed_results.derivation_json identity_relations.evidence_json
identity_relation_cancellations.evidence_json repository_name_observations.provenance_json
""",
)
_register("authored", "coverage_claims.details_json", nullable=True)
_register("git-roots", "git_acquisitions.roots_manifest", shape="array", nullable=True)
_register(
    "git-object-manifest",
    "git_acquisition_publications.object_manifest_json",
    shape="array",
)
_register("git-roots", "git_acquisition_publications.root_manifest_json", shape="array")
_register(
    "provider",
    """
change_request_observations.payload document_observations.metadata
change_request_events.payload code_commits.payload code_file_changes.payload
review_thread_observations.payload repository_inventory_observations.metadata_json
issue_resources.metadata review_resources.metadata
""",
)
_register("decoded-headers", "commits.metadata")
_register(
    "authored",
    "review_resources.acquisition_scope_json",
)
_register("current-acquisition", "issue_resources.acquisition_scope_json")
_register(
    "current-field-evidence",
    "issue_resources.field_evidence_json review_resources.field_evidence_json",
)
_register("current-members", "current_collection_pages.members", shape="array")
_register(
    "operational",
    """
jobs.request job_attempts.checkpoint inventory_observations.scope
search_documents.metadata local_parser_profile_verification_trust.rationale_json
payload_admission_staging.context_json exchange_source_provenance.definition_json
""",
)
_register(
    "operational", "sources.settings unresolved_payloads.diagnostic_json", nullable=True
)
_register(
    "definition",
    "parser_profiles.definition_json parser_profile_verifications.criteria_json parser_profile_verifications.evidence_json",
)
_register("input-manifest", "parsed_results.input_manifest_json", shape="array")
_register(
    "fact-manifest", "parsed_result_publications.fact_manifest_json", shape="array"
)
_register(
    "predecessor-manifest",
    "parser_profile_selection_decisions.predecessor_manifest_json fact_selection_decisions.predecessor_manifest_json",
    shape="array",
)
_register(
    "staging-envelope",
    "exchange_admissions.record_json exchange_staging.record_json parser_profile_selection_staging.record_json fact_selection_staging.record_json identity_relation_staging.record_json",
)
_register(
    "local-key",
    "exchange_admissions.local_key_json exchange_local_identities.local_key_json",
)

# Each reference key means exactly one target type. This vocabulary also applies
# in nested evidence objects; no inference from a UUID's mere existence is used.
REFERENCE_TARGETS = {
    "repository_uuidv4": ("repositories", "repository_uuidv4"),
    "service_instance_uuidv4": ("service_instances", "service_instance_uuidv4"),
    "source_registration_uuidv4": ("sources", "source_registration_uuidv4"),
    "parsed_result_uuidv4": ("parsed_results", "parsed_result_uuidv4"),
    "parser_profile_uuidv4": ("parser_profiles", "parser_profile_uuidv4"),
    "parser_profile_verification_uuidv4": (
        "parser_profile_verifications",
        "parser_profile_verification_uuidv4",
    ),
    "change_request_observation_uuidv4": (
        "change_request_observations",
        "change_request_observation_uuidv4",
    ),
    "document_observation_uuidv4": (
        "document_observations",
        "document_observation_uuidv4",
    ),
    "code_observation_uuidv4": ("code_observations", "code_observation_uuidv4"),
    "fetch_occurrence_uuidv4": ("fetch_occurrences", "fetch_occurrence_uuidv4"),
    "source_input_uuidv4": ("source_input_observations", "source_input_uuidv4"),
    "completion_marker_uuidv4": ("completion_markers", "completion_marker_uuidv4"),
    "relation_uuidv4": ("identity_relations", "relation_uuidv4"),
    "git_acquisition_id": ("git_acquisitions", "git_acquisition_id"),
    "fetch_collection_id": ("fetch_collections", "fetch_collection_id"),
    "parent_fetch_collection_id": ("fetch_collections", "fetch_collection_id"),
    "change_request_id": ("change_requests", "change_request_id"),
    "resume_scope_id": ("resume_scopes", "resume_scope_id"),
    "stable_scope": ("resume_scopes", "resume_scope_id"),
    "repository_binding_id": ("repository_bindings", "repository_binding_id"),
    "repository_endpoint_id": ("repository_endpoints", "repository_endpoint_id"),
    "selection_decision_uuidv4": (
        "fact_selection_decisions",
        "fact_selection_decision_uuidv4",
    ),
}
REFERENCE_LISTS = {
    "change_request_ids": "change_request_id",
    "parsed_result_uuidv4s": "parsed_result_uuidv4",
    "fetch_occurrence_uuidv4s": "fetch_occurrence_uuidv4",
    "fetch_collection_ids": "fetch_collection_id",
    "git_acquisition_ids": "git_acquisition_id",
    "completion_marker_uuidv4s": "completion_marker_uuidv4",
    "selection_predecessors": "selection_decision_uuidv4",
}
LOCAL_REFERENCE_KEYS = {
    "fetch_occurrence_id",
    "change_request_observation_id",
    "document_observation_id",
    "code_observation_id",
    "git_object_id",
    "content_id",
    "source_id",
    "acquisition_root_id",
    "text_body_id",
    "completion_marker_id",
}
SHA = re.compile(r"[0-9a-f]{64}\Z")


class JsonContractError(CatalogError):
    def __init__(self, message):
        super().__init__("INVALID_JSON_REFERENCE", message)


class MissingJsonDependencies(CatalogError):
    def __init__(self, dependencies):
        self.dependencies = dependencies
        super().__init__(
            "JSON_DEPENDENCY_MISSING", "Authored JSON dependencies are missing"
        )


def _load(value, schema, field):
    if value is None and schema.nullable:
        return None
    if isinstance(value, str):

        def unique(pairs):
            result = {}
            for key, item in pairs:
                if key in result:
                    raise JsonContractError(
                        f"Duplicate JSON property in {field}: {key}"
                    )
                result[key] = item
            return result

        try:
            value = json.loads(
                value,
                object_pairs_hook=None if schema.category == "provider" else unique,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
            )
        except (ValueError, TypeError) as cause:
            raise JsonContractError(f"Malformed JSON in {field}") from cause
    if not isinstance(value, dict if schema.shape == "object" else list):
        raise JsonContractError(f"{field} requires a JSON {schema.shape}")
    return value


def _identity(key, value):
    if not isinstance(value, str) or not value or "\0" in value:
        raise JsonContractError(f"{key} requires a nonempty text identity")
    if "uuidv4" in key:
        try:
            parsed = uuid.UUID(value)
        except (ValueError, AttributeError) as cause:
            raise JsonContractError(f"{key} requires canonical UUIDv4") from cause
        if parsed.version != 4 or str(parsed) != value:
            raise JsonContractError(f"{key} requires canonical UUIDv4")


def _dependency(key, value):
    _identity(key, value)
    table, column = REFERENCE_TARGETS[key]
    return {"table": table, "columns": (column,), "values": (value,)}


_CAPTURE_KEYS = {
    "repository_uuidv4",
    "repository_binding_id",
    "service_instance_uuidv4",
    "source_registration_uuidv4",
}
_EVIDENCE_KEYS = {
    "provider_updated_at_us",
    "provider_clock_scope",
    "observed_at_us",
    "parsed_at_us",
    "parser_profile_uuidv4",
    "acquisition_scope",
}
_EVIDENCE_FIELDS = {
    "body",
    "title",
    "state",
    "author",
    "url",
    "deleted",
    "metadata",
    "submitted_at_us",
    "target_commit_oid",
    "original_commit_oid",
    "original_position",
    "current_position",
    "raw_path",
    "diff_hunk",
    "review_provider_resource_id",
    "in_reply_to_provider_resource_id",
    "review_thread_provider_resource_id",
}
_ISSUE_EVIDENCE_FIELDS = {
    "body",
    "title",
    "state",
    "author",
    "url",
    "deleted",
    "metadata",
}
_REVIEW_EVIDENCE_FIELDS = _EVIDENCE_FIELDS - {"title"}


def _acquisition_shape(scope, service):
    if not isinstance(scope, dict):
        raise JsonContractError("Acquisition scope must be an object")
    for name in (
        "repository_uuidv4",
        "repository_binding_id",
        "service_instance_uuidv4",
    ):
        _identity(name, scope.get(name))
    if "source_registration_uuidv4" in scope:
        _identity("source_registration_uuidv4", scope["source_registration_uuidv4"])
    if scope["service_instance_uuidv4"] != service:
        raise JsonContractError("Acquisition service differs from resource service")
    endpoint = scope.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint or "\x00" in endpoint:
        raise JsonContractError("Acquisition endpoint requires nonempty text")
    # Validate every authored identity, including captured identifiers that are
    # snapshots rather than transport dependencies after an Issue transfer.
    _walk(scope)


def _detached_acquisition(data, scope):
    return data.get("kind") == "issue-comment" and scope.get(
        "repository_uuidv4"
    ) != data.get("repository_uuidv4")


def _check_schema(table, column, value, data):
    if (table, column) == ("issue_resources", "acquisition_scope_json"):
        _acquisition_shape(value, data.get("service_instance_uuidv4"))
        if not _detached_acquisition(data, value) and any(
            value.get(name) != data.get(name)
            for name in ("repository_uuidv4", "repository_binding_id")
        ):
            raise JsonContractError("Acquisition scope differs from typed owner")
        return
    if column == "field_evidence_json":
        allowed = (
            _ISSUE_EVIDENCE_FIELDS
            if table == "issue_resources"
            else _REVIEW_EVIDENCE_FIELDS
        )
        for encoded_path, evidence in value.items():
            try:
                path = json.loads(encoded_path)
            except (ValueError, TypeError):
                raise JsonContractError("Invalid current field evidence path") from None
            if (
                not isinstance(path, list)
                or not path
                or any(not isinstance(part, str) for part in path)
                or path[0] not in allowed
                or (len(path) > 1 and path[0] != "metadata")
                or json.dumps(path, ensure_ascii=False, separators=(",", ":"))
                != encoded_path
                or not isinstance(evidence, dict)
                or evidence.keys() != _EVIDENCE_KEYS
            ):
                raise JsonContractError("Invalid current field evidence entry")
            if path[0] == "metadata":
                item = data.get("metadata", {})
                if isinstance(item, str):
                    item = _load(
                        item, JSON_REGISTRY[table, "metadata"], "Current metadata"
                    )
                for depth, part in enumerate(path[1:], 1):
                    ancestor = json.dumps(
                        path[:depth], ensure_ascii=False, separators=(",", ":")
                    )
                    if ancestor not in value:
                        raise JsonContractError(
                            "Metadata field evidence requires object ancestor proofs"
                        )
                    if not isinstance(item, dict) or part not in item:
                        raise JsonContractError(
                            "Current field evidence refers to absent metadata"
                        )
                    item = item[part]
            elif path[0] == "body":
                if not {"body", "body_status", "text_body_sha256"} & data.keys():
                    raise JsonContractError(
                        "Current field evidence refers to absent body"
                    )
            elif path[0] not in data:
                raise JsonContractError("Current field evidence refers to absent field")
            for name in ("provider_updated_at_us", "observed_at_us", "parsed_at_us"):
                if evidence[name] is not None:
                    try:
                        validate_epoch_us(evidence[name])
                    except (TypeError, ValueError) as exc:
                        raise JsonContractError(
                            "Current field evidence requires signed int64 timestamps"
                        ) from exc
            if evidence["observed_at_us"] is None or evidence["parsed_at_us"] is None:
                raise JsonContractError("Current field evidence requires capture times")
            clock = evidence["provider_clock_scope"]
            expected = {
                "issue": "github-issue-updated-at",
                "issue-comment": "github-issue-comment-updated-at",
                "review-comment": "github-review-comment-updated-at",
            }.get(data.get("kind"))
            if clock is not None and clock != expected:
                raise JsonContractError(
                    "Current field evidence has invalid provider clock"
                )
            if (
                data.get("kind") == "review"
                and evidence["provider_updated_at_us"] is not None
            ):
                raise JsonContractError(
                    "Review field evidence cannot claim an update clock"
                )
            _identity("parser_profile_uuidv4", evidence["parser_profile_uuidv4"])
            _acquisition_shape(
                evidence["acquisition_scope"], data.get("service_instance_uuidv4")
            )
            scope = evidence["acquisition_scope"]
            if table == "review_resources":
                if any(
                    scope.get(name) != data.get(name)
                    for name in (
                        "repository_uuidv4",
                        "repository_binding_id",
                        "change_request_id",
                    )
                ):
                    raise JsonContractError(
                        "Review field capture differs from typed owner"
                    )
            elif "change_request_id" in scope:
                raise JsonContractError(
                    "Ordinary Issue field capture cannot claim a change request"
                )
            if (
                "parser_profile_uuidv4" in scope
                and scope["parser_profile_uuidv4"] != evidence["parser_profile_uuidv4"]
            ):
                raise JsonContractError(
                    "Field parser attribution differs from captured parser"
                )
        return
    if (table, column) == ("current_collection_pages", "members"):
        keys = set()
        for item in value:
            if not isinstance(item, dict):
                raise JsonContractError(
                    "Current collection member requires a typed object"
                )
            family = item.get("family")
            if family == "issue":
                fields = {
                    "family",
                    "service_instance_uuidv4",
                    "kind",
                    "provider_resource_id",
                    "state_digest",
                }
                kinds = {"issue", "issue-comment"}
                identity = "provider_resource_id"
                owner = "service_instance_uuidv4"
            elif family == "review":
                fields = {
                    "family",
                    "change_request_id",
                    "kind",
                    "provider_change_request_document_id",
                    "state_digest",
                }
                kinds = {"review", "review-comment"}
                identity = "provider_change_request_document_id"
                owner = "change_request_id"
            else:
                raise JsonContractError("Unknown current collection member family")
            if set(item) != fields or item.get("kind") not in kinds:
                raise JsonContractError(
                    "Current collection member has wrong fields or kind"
                )
            provider = item[identity]
            if not isinstance(provider, str) or not re.fullmatch(
                r"[1-9][0-9]*", provider
            ):
                raise JsonContractError(
                    "Current collection provider identity requires canonical positive decimal text"
                )
            _identity(owner, item[owner])
            if not isinstance(item["state_digest"], str) or not SHA.fullmatch(
                item["state_digest"]
            ):
                raise JsonContractError(
                    "Current member state digest requires canonical SHA-256"
                )
            key = family, item[owner], item["kind"], provider
            if key in keys:
                raise JsonContractError(
                    "Duplicate current collection resource identity"
                )
            keys.add(key)
        return
    if (table, column) == (
        "completion_markers",
        "evidence",
    ) and "current_page_collections" in value:
        manifest = value["current_page_collections"]
        if not isinstance(manifest, list):
            raise JsonContractError(
                "Current page collection manifest requires an array"
            )
        identities = set()
        for item in manifest:
            if not isinstance(item, dict) or set(item) != {
                "fetch_collection_id",
                "page_ordinals",
            }:
                raise JsonContractError(
                    "Current page manifest requires exact collection and ordinal fields"
                )
            _identity("fetch_collection_id", item["fetch_collection_id"])
            ordinals = item["page_ordinals"]
            if (
                not isinstance(ordinals, list)
                or not ordinals
                or any(
                    type(ordinal) is not int or ordinal != i
                    for i, ordinal in enumerate(ordinals)
                )
            ):
                raise JsonContractError(
                    "Current page manifest requires contiguous integer ordinals"
                )
            if item["fetch_collection_id"] in identities:
                raise JsonContractError(
                    "Duplicate current page collection manifest identity"
                )
            identities.add(item["fetch_collection_id"])
    if (table, column) == ("completion_markers", "evidence") and value.get(
        "kind"
    ) == "current-resource-pages-v1":
        ordinals = value.get("page_ordinals")
        if (
            set(value) != {"kind", "page_ordinals", "terminal"}
            or value.get("terminal") is not True
            or not isinstance(ordinals, list)
            or not ordinals
            or any(type(n) is not int or n != i for i, n in enumerate(ordinals))
        ):
            raise JsonContractError(
                "Current completion requires exact ordered page ordinals and terminal evidence"
            )
        return
    if (table, column) == ("git_acquisitions", "roots_manifest"):
        fields = {"name", "name_b64", "oid", "type", "peeled"}
        optional = {"role", "number", "expected"}
        object_format = data.get("object_format")
        width = (
            {"sha1": 40, "sha256": 64}.get(object_format)
            if isinstance(object_format, str)
            else None
        )
        for item in value:
            if (
                not isinstance(item, dict)
                or not fields <= item.keys()
                or item.keys() - fields - optional
            ):
                raise JsonContractError(
                    "Captured Git ref requires name, name_b64, oid, type and peeled"
                )
            for field in ("name", "name_b64"):
                if (
                    not isinstance(item[field], str)
                    or not item[field]
                    or "\0" in item[field]
                ):
                    raise JsonContractError(
                        "Captured Git ref names require nonempty text"
                    )
            try:
                raw_name = base64.b64decode(item["name_b64"], validate=True)
            except (ValueError, UnicodeError) as cause:
                raise JsonContractError(
                    "Captured Git ref name requires canonical base64"
                ) from cause
            if (
                not raw_name
                or base64.b64encode(raw_name).decode() != item["name_b64"]
                or raw_name.decode("utf8", "backslashreplace") != item["name"]
            ):
                raise JsonContractError(
                    "Captured Git ref raw and displayed names disagree"
                )
            if not isinstance(item["type"], str) or item["type"] not in {
                "commit",
                "tree",
                "blob",
                "tag",
            }:
                raise JsonContractError("Captured Git ref target type is invalid")
            for field in ("oid", "peeled", "expected"):
                if field not in item or (field == "peeled" and item[field] is None):
                    continue
                if (
                    width is None
                    or not isinstance(item[field], str)
                    or not re.fullmatch(r"[0-9a-f]{" + str(width) + r"}", item[field])
                ):
                    raise JsonContractError(
                        "Captured Git ref OID disagrees with acquisition object format"
                    )
            if item.keys() & optional:
                if (
                    not optional <= item.keys()
                    or not isinstance(item["role"], str)
                    or not item["role"]
                    or "\0" in item["role"]
                    or type(item["number"]) is not int
                    or item["number"] <= 0
                    or item["expected"] != item["oid"]
                ):
                    raise JsonContractError(
                        "Captured PR ref requires exact role, positive number and expected OID"
                    )
        return
    if table == "git_acquisition_publications":
        fields = (
            {"object_format", "oid", "payload"}
            if column == "object_manifest_json"
            else {"object_format", "oid", "role"}
        )
        if any(not isinstance(item, dict) or set(item) != fields for item in value):
            raise JsonContractError(
                "Git acquisition manifest requires exact typed members"
            )
        for item in value:
            expected = (
                {"sha1": 40, "sha256": 64}.get(item["object_format"])
                if isinstance(item["object_format"], str)
                else None
            )
            if (
                not expected
                or not isinstance(item["oid"], str)
                or not re.fullmatch(r"[0-9a-f]{" + str(expected) + r"}", item["oid"])
            ):
                raise JsonContractError(
                    "Git acquisition object identity requires canonical format and OID"
                )
            if column == "object_manifest_json" and (
                not isinstance(item["payload"], dict)
                or item["payload"].get("representation") != "git-object-raw-v1"
            ):
                raise JsonContractError(
                    "Git acquisition bytes require git-object-raw-v1"
                )
            if column == "root_manifest_json" and (
                not isinstance(item["role"], str) or not item["role"]
            ):
                raise JsonContractError(
                    "Git acquisition root role requires nonempty text"
                )
        return
    if not isinstance(value, dict):
        return
    if (table, column) == ("code_observations", "details"):
        object_format = data.get("object_format")
        width = (
            {"sha1": 40, "sha256": 64}.get(object_format)
            if isinstance(object_format, str)
            else None
        )

        def valid_oid(oid):
            return (
                width is not None
                and isinstance(oid, str)
                and re.fullmatch(r"[0-9a-f]{" + str(width) + r"}", oid)
            )

        def valid_role(role):
            return isinstance(role, str) and (
                role in {"head", "base", "merge", "test-merge"}
                or (role.startswith("review-target:") and valid_oid(role[14:]))
            )

        for field in ("api_head_base_stable", "code_inputs_complete"):
            if field in value and not isinstance(value[field], bool):
                raise JsonContractError(f"Code derivation {field} requires a boolean")
        if "expected_roles" in value:
            roles = value["expected_roles"]
            if not isinstance(roles, dict) or any(
                not valid_role(role)
                or not valid_oid(oid)
                or (role.startswith("review-target:") and role[14:] != oid)
                for role, oid in roles.items()
            ):
                raise JsonContractError(
                    "Expected code roles require supported role names and canonical Git OIDs"
                )
        if "missing_roles" in value and (
            not isinstance(value["missing_roles"], list)
            or any(not valid_role(role) for role in value["missing_roles"])
        ):
            raise JsonContractError(
                "Missing code roles require a supported role-name array"
            )
        if "provider_limits" in value:
            limits = value["provider_limits"]
            if not isinstance(limits, dict) or any(
                key not in {"commits", "files"}
                or type(bound) is not int
                or not 0 < bound <= 9223372036854775807
                for key, bound in limits.items()
            ):
                raise JsonContractError(
                    "Provider code limits require positive int64 commits/files bounds"
                )
        if "merge" in value:
            merge = value["merge"]
            if not isinstance(merge, dict) or any(
                role not in {"merge", "test-merge"}
                or (oid is not None and not valid_oid(oid))
                for role, oid in merge.items()
            ):
                raise JsonContractError(
                    "Merge code declarations require canonical merge/test-merge Git OIDs or null"
                )
    if (table, column) == ("parsed_results", "derivation_json"):
        for field in ("parser", "kind", "decoder"):
            if field in value and (
                not isinstance(value[field], str) or not value[field]
            ):
                raise JsonContractError(f"Derivation {field} requires nonempty text")
    if (table, column) in {
        ("fetch_occurrences", "request"),
        ("resume_scopes", "request_context"),
    }:
        for field in (
            "thread",
            "review_thread_provider_resource_id",
            "query",
            "url",
            "method",
        ):
            if field in value and (
                not isinstance(value[field], str) or not value[field]
            ):
                raise JsonContractError(
                    f"Acquisition context {field} requires nonempty text"
                )
        if "variables" in value:
            variables = value["variables"]
            if not isinstance(variables, dict):
                raise JsonContractError("GraphQL variables require an object")
            for field in ("thread", "owner", "name"):
                if field in variables and (
                    not isinstance(variables[field], str) or not variables[field]
                ):
                    raise JsonContractError(
                        f"GraphQL variable {field} requires nonempty text"
                    )
            for field in ("cursor", "commentCursor"):
                if (
                    field in variables
                    and variables[field] is not None
                    and not isinstance(variables[field], str)
                ):
                    raise JsonContractError(
                        f"GraphQL variable {field} requires text or null"
                    )
            for field in ("number", "pageSize"):
                if field in variables and (
                    type(variables[field]) is not int
                    or not 0 < variables[field] <= 9223372036854775807
                ):
                    raise JsonContractError(
                        f"GraphQL variable {field} requires a positive int64"
                    )
    if (table, column) in {
        ("completion_markers", "evidence"),
        ("fetch_occurrences", "request"),
    }:
        for field in ("terminal", "context_proven", "operational_only"):
            if field in value and not isinstance(value[field], bool):
                raise JsonContractError(f"HTTP evidence {field} requires a boolean")
        if "status" in value and (
            type(value["status"]) is not int or not 100 <= value["status"] <= 599
        ):
            raise JsonContractError(
                "HTTP evidence status requires an integer in 100..599"
            )
        if "response" in value:
            response = value["response"]
            if (
                not isinstance(response, dict)
                or set(response) != {"status", "headers"}
                or type(response["status"]) is not int
                or not 100 <= response["status"] <= 599
            ):
                raise JsonContractError(
                    "HTTP response evidence requires status and headers"
                )
            if not isinstance(response["headers"], dict) or any(
                k != "etag" or not isinstance(v, str)
                for k, v in response["headers"].items()
            ):
                raise JsonContractError(
                    "Historical response headers permit only text ETag"
                )
    if (table, column) == ("completion_markers", "evidence") and value.get(
        "status"
    ) == 304:
        if (
            not {
                "change_request_observation_uuidv4",
                "parsed_result_uuidv4",
                "fetch_occurrence_uuidv4",
                "payload",
            }
            <= value.keys()
        ):
            raise JsonContractError(
                "304 requires exact original observation, result, fetch and payload evidence"
            )


def _walk(value, *, declaration=False, digests=False, path=()):
    dependencies = []
    if isinstance(value, list):
        for index, item in enumerate(value):
            dependencies.extend(
                _walk(
                    item, declaration=declaration, digests=digests, path=(*path, index)
                )
            )
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in LOCAL_REFERENCE_KEYS:
                raise JsonContractError(
                    f"Local identity {key} is forbidden in portable authored JSON"
                )
            if key in REFERENCE_TARGETS:
                _identity(key, item)
                if not (
                    declaration and path == () and key == "selection_decision_uuidv4"
                ):
                    dependencies.append(_dependency(key, item))
            elif key in REFERENCE_LISTS:
                if not isinstance(item, list):
                    raise JsonContractError(f"{key} requires an identity array")
                for ident in item:
                    dependencies.append(_dependency(REFERENCE_LISTS[key], ident))
            elif key == "payload":
                if not isinstance(item, dict) or set(item) != {
                    "representation",
                    "sha256",
                }:
                    raise JsonContractError(
                        "Payload reference requires exactly representation and sha256"
                    )
                digest = item["sha256"]
                if not isinstance(digest, str) or not SHA.fullmatch(digest):
                    raise JsonContractError(
                        "Payload SHA-256 requires canonical lowercase hex"
                    )
                if not isinstance(item["representation"], str) or item[
                    "representation"
                ] not in {
                    "decoded_api",
                    "legacy_normalized",
                    "git-object-raw-v1",
                }:
                    raise JsonContractError("Unknown payload representation")
                dependencies.append(
                    {
                        "table": "payloads",
                        "columns": ("representation", "sha256"),
                        "values": (item["representation"], bytes.fromhex(digest)),
                    }
                )
            elif digests and (key == "sha256" or key.endswith("_sha256")):
                if not isinstance(item, str) or not SHA.fullmatch(item):
                    raise JsonContractError(
                        "Definition/evidence digest requires canonical lowercase SHA-256"
                    )
            elif (
                key.endswith("_uuidv4")
                or key.endswith("_uuidv4s")
                or key.endswith("_sha256")
                or key in {"representation", "sha256", "references"}
            ):
                raise JsonContractError(f"Unregistered reference encoding: {key}")
            else:
                dependencies.extend(
                    _walk(
                        item,
                        declaration=declaration,
                        digests=digests,
                        path=(*path, key),
                    )
                )
    return dependencies


def reference_dependencies(table, data):
    """Typed natural keys, suitable for exact exchange dependency closure."""
    dependencies = []
    for (registered, column), schema in JSON_REGISTRY.items():
        if registered != table or column not in data:
            continue
        value = _load(data[column], schema, f"{table}.{column}")
        if value is None:
            continue
        _check_schema(table, column, value, data)
        if schema.category == "current-field-evidence":
            # Each capture is a historical context snapshot, not an ownership
            # assertion or a request to export another repository's records.
            dependencies.extend(
                _walk(
                    {
                        path: {
                            k: v
                            for k, v in evidence.items()
                            if k != "acquisition_scope"
                        }
                        for path, evidence in value.items()
                    }
                )
            )
            continue
        if schema.category in {
            "authored",
            "current-acquisition",
            "current-members",
            "input-manifest",
            "git-roots",
            "git-object-manifest",
            "definition",
        }:
            if schema.category == "input-manifest":
                if not value or any(
                    not isinstance(i, dict)
                    or len(i) != 1
                    or next(iter(i))
                    not in {
                        "fetch_occurrence_uuidv4",
                        "git_acquisition_id",
                        "source_input_uuidv4",
                    }
                    for i in value
                ):
                    raise JsonContractError("Invalid typed input manifest")
            authored = (
                {k: v for k, v in value.items() if k not in {"head", "base"}}
                if (table, column) == ("resume_scopes", "request_context")
                else value
            )
            if schema.category == "current-acquisition" and _detached_acquisition(
                data, value
            ):
                authored = {k: v for k, v in authored.items() if k not in _CAPTURE_KEYS}
            dependencies.extend(
                _walk(
                    authored,
                    declaration=(table, column) == ("parsed_results", "derivation_json")
                    and value.get("kind") == "git",
                    digests=schema.category == "definition",
                )
            )
            if schema.category == "git-object-manifest":
                dependencies.extend(
                    {
                        "table": "git_objects",
                        "columns": ("object_format", "oid"),
                        "values": (item["object_format"], bytes.fromhex(item["oid"])),
                    }
                    for item in value
                )
        elif schema.category == "predecessor-manifest":
            target = (
                "parser_profile_selection_decisions"
                if table.startswith("parser_profile")
                else "fact_selection_decisions"
            )
            key = (
                "selection_decision_uuidv4"
                if target.startswith("parser_profile")
                else "fact_selection_decision_uuidv4"
            )
            for ident in value:
                _identity(key, ident)
                dependencies.append(
                    {"table": target, "columns": (key,), "values": (ident,)}
                )
            if len(value) != len(set(value)):
                raise JsonContractError("Duplicate predecessor identity")
    # Exact duplicates have set semantics; preserve deterministic first order.
    seen = set()
    return [
        d
        for d in dependencies
        if not (
            (key := (d["table"], d["columns"], d["values"])) in seen or seen.add(key)
        )
    ]


def _row(db, table, columns, values):
    cursor = db.execute(
        f"SELECT * FROM {table} WHERE " + " AND ".join(f"{c}=?" for c in columns),
        values,
    )
    result = cursor.fetchone()
    return (
        dict(zip((c[0] for c in cursor.description), result))
        if result is not None
        else None
    )


def _owner(db, table, data):
    if data.get("owner_source_registration_uuidv4"):
        return None, data["owner_source_registration_uuidv4"]
    repository = data.get("owner_repository_uuidv4") or data.get("repository_uuidv4")
    source = data.get("owner_source_registration_uuidv4") or data.get(
        "source_registration_uuidv4"
    )
    if repository or source:
        return repository, source
    for column, parent in (
        ("fetch_collection_id", "fetch_collections"),
        ("coverage_scope_id", "coverage_scopes"),
        ("resume_scope_id", "resume_scopes"),
        ("selection_scope_uuidv4", "parser_profile_selection_scopes"),
        ("fact_selection_scope_uuidv4", "fact_selection_scopes"),
    ):
        if data.get(column):
            row = _row(db, parent, (column,), (data[column],))
            if row:
                return row.get("repository_uuidv4"), row.get(
                    "source_registration_uuidv4"
                )
    return None, None


def validate_acquisition_scope(
    db,
    scope,
    *,
    service_instance_uuidv4,
    repository_uuidv4=None,
    repository_binding_id=None,
    allow_snapshot=False,
):
    """Check a capture against known registrations without fabricating owners.

    A detached historical capture may lack its original repository on a
    per-repository receiver. Existing registrations still have to agree.
    Live acquisition requires every captured registration and membership.
    """
    _acquisition_shape(scope, service_instance_uuidv4)
    if (
        repository_uuidv4 is not None
        and scope["repository_uuidv4"] != repository_uuidv4
    ):
        raise JsonContractError("Acquisition repository differs from current owner")
    if (
        repository_binding_id is not None
        and scope["repository_binding_id"] != repository_binding_id
    ):
        raise JsonContractError("Acquisition binding differs from current owner")
    captured_repository = scope["repository_uuidv4"]
    repository = _row(
        db, "repositories", ("repository_uuidv4",), (captured_repository,)
    )
    binding = _row(
        db,
        "repository_bindings",
        ("repository_binding_id",),
        (scope["repository_binding_id"],),
    )
    missing = []
    if binding is not None:
        if (
            binding["repository_uuidv4"] != captured_repository
            or binding["service_instance_uuidv4"] != service_instance_uuidv4
        ):
            raise JsonContractError(
                "Captured binding has different repository or service"
            )
    elif not allow_snapshot or repository is not None:
        missing.append(
            {
                "table": "repository_bindings",
                "columns": ("repository_binding_id",),
                "values": (scope["repository_binding_id"],),
            }
        )
    source_id = scope.get("source_registration_uuidv4")
    if source_id:
        source = _row(db, "sources", ("source_registration_uuidv4",), (source_id,))
        if source is None:
            if not allow_snapshot:
                missing.append(
                    {
                        "table": "sources",
                        "columns": ("source_registration_uuidv4",),
                        "values": (source_id,),
                    }
                )
        elif source["service_instance_uuidv4"] not in (None, service_instance_uuidv4):
            raise JsonContractError("Captured Source has different service")
        elif (repository is not None or not allow_snapshot) and not db.execute(
            "SELECT 1 FROM source_repositories WHERE source_id=? AND repository_uuidv4=?",
            (source["source_id"], captured_repository),
        ).fetchone():
            raise JsonContractError(
                "Captured Source does not own captured repository membership"
            )
    return missing


def validate_field_evidence(db, evidence, candidate):
    """Validate the bounded current-value attribution map, never a history."""
    if not isinstance(evidence, dict):
        raise JsonContractError("Current field evidence must be an object")
    table = (
        "issue_resources"
        if candidate["kind"] in {"issue", "issue-comment"}
        else "review_resources"
    )
    _check_schema(table, "field_evidence_json", evidence, candidate)
    pending = []
    fact_kind = (
        "ordinary-issue-comment"
        if candidate["kind"] == "issue-comment"
        else candidate["kind"]
    )
    captures, profiles = {}, set()
    for entry in evidence.values():
        scope = entry["acquisition_scope"]
        captures.setdefault(
            json.dumps(scope, sort_keys=True, ensure_ascii=False), scope
        )
        profiles.add(entry["parser_profile_uuidv4"])
    for scope in captures.values():
        pending.extend(
            validate_acquisition_scope(
                db,
                scope,
                service_instance_uuidv4=candidate["service_instance_uuidv4"],
                allow_snapshot=True,
            )
        )
    for profile_id in profiles:
        profile = _row(db, "parser_profiles", ("parser_profile_uuidv4",), (profile_id,))
        if profile is None:
            pending.append(
                {
                    "table": "parser_profiles",
                    "columns": ("parser_profile_uuidv4",),
                    "values": (profile_id,),
                }
            )
            continue
        declared = json.loads(profile["definition_json"]).get("capabilities", [])
        if {"owner_kind": "repository", "fact_kind": fact_kind} not in declared:
            raise JsonContractError(
                "Field parser profile does not declare resource capability"
            )
        if not db.execute(
            "SELECT 1 FROM parser_profile_capabilities WHERE parser_profile_uuidv4=? AND owner_kind='repository' AND fact_kind=?",
            (profile_id, fact_kind),
        ).fetchone():
            pending.append(
                {
                    "table": "parser_profile_capabilities",
                    "columns": ("parser_profile_uuidv4", "owner_kind", "fact_kind"),
                    "values": (profile_id, "repository", fact_kind),
                }
            )
    return pending


def _owned_payload(db, representation, digest, repository, source):
    if repository:
        if db.execute(
            "SELECT 1 FROM fetch_occurrences WHERE repository_uuidv4=? AND payload_representation=? AND payload_sha256=?",
            (repository, representation, digest),
        ).fetchone():
            return True
        if representation == "git-object-raw-v1":
            return bool(
                db.execute(
                    "SELECT 1 FROM git_object_payloads p JOIN repository_object_sources o USING(git_object_id) JOIN git_acquisitions a USING(git_acquisition_id) WHERE a.repository_uuidv4=? AND p.payload_representation=? AND p.payload_sha256=?",
                    (repository, representation, digest),
                ).fetchone()
            )
        return False
    if source:
        return bool(
            db.execute(
                "SELECT 1 FROM source_input_observations WHERE source_registration_uuidv4=? AND payload_representation=? AND payload_sha256=?",
                (source, representation, digest),
            ).fetchone()
        )
    return True


def validate_record(db, table, data, *, allow_missing=False):
    """Reject malformed/foreign references; report absent valid targets separately.

    Identity relations explicitly connect two owners and have no exclusive owner.
    Source-owned inventory names instead use the result's Source owner.
    """
    dependencies = reference_dependencies(table, data)
    repository, source = _owner(db, table, data)
    missing = []
    unowned_payloads = []
    if table == "issue_resources" and "acquisition_scope_json" in data:
        scope = _load(
            data["acquisition_scope_json"],
            JSON_REGISTRY[table, "acquisition_scope_json"],
            "Issue acquisition scope",
        )
        detached = _detached_acquisition(data, scope)
        missing.extend(
            validate_acquisition_scope(
                db,
                scope,
                service_instance_uuidv4=data["service_instance_uuidv4"],
                repository_uuidv4=None if detached else data["repository_uuidv4"],
                repository_binding_id=None
                if detached
                else data["repository_binding_id"],
                allow_snapshot=detached,
            )
        )
        repository = scope["repository_uuidv4"]
    if (
        table in {"issue_resources", "review_resources"}
        and "field_evidence_json" in data
    ):
        evidence = _load(
            data["field_evidence_json"],
            JSON_REGISTRY[table, "field_evidence_json"],
            "Current field evidence",
        )
        missing.extend(validate_field_evidence(db, evidence, data))
    if table == "current_collection_pages" and "members" in data:
        members = _load(
            data["members"],
            JSON_REGISTRY[table, "members"],
            "Current collection members",
        )
        collection = _row(
            db,
            "fetch_collections",
            ("fetch_collection_id",),
            (data["fetch_collection_id"],),
        )
        if collection:
            scope = _row(
                db,
                "resume_scopes",
                ("resume_scope_id",),
                (collection["resume_scope_id"],),
            )
            binding = (
                _row(
                    db,
                    "repository_bindings",
                    ("repository_binding_id",),
                    (scope.get("repository_binding_id"),),
                )
                if scope
                else None
            )
            for item in members:
                if item["family"] == "issue" and (
                    binding is None
                    or binding["service_instance_uuidv4"]
                    != item["service_instance_uuidv4"]
                ):
                    raise JsonContractError(
                        "Current Issue member has a different acquisition service"
                    )
                if (
                    item["family"] == "review"
                    and collection["change_request_id"] is not None
                    and item["change_request_id"] != collection["change_request_id"]
                ):
                    raise JsonContractError(
                        "Current review member has a different acquisition parent"
                    )
                if item["family"] == "review":
                    parent = _row(
                        db,
                        "change_requests",
                        ("change_request_id",),
                        (item["change_request_id"],),
                    )
                    if parent is not None and (
                        binding is None
                        or parent["repository_binding_id"]
                        != binding["repository_binding_id"]
                    ):
                        raise JsonContractError(
                            "Current review member has a different acquisition binding"
                        )
    if table == "git_acquisition_publications" and "object_manifest_json" in data:
        manifest = _load(
            data["object_manifest_json"],
            JSON_REGISTRY[table, "object_manifest_json"],
            "Git object manifest",
        )
        for item in manifest:
            obj = _row(
                db,
                "git_objects",
                ("object_format", "oid"),
                (item["object_format"], bytes.fromhex(item["oid"])),
            )
            if obj is None:
                continue
            mapping = _row(
                db, "git_object_payloads", ("git_object_id",), (obj["git_object_id"],)
            )
            if mapping is None:
                missing.append(
                    {
                        "table": "git_object_payloads",
                        "columns": ("git_object_id",),
                        "values": (obj["git_object_id"],),
                    }
                )
            elif (
                mapping["payload_representation"],
                mapping["payload_sha256"].hex(),
            ) != (item["payload"]["representation"], item["payload"]["sha256"]):
                raise JsonContractError(
                    "Git manifest payload disagrees with authoritative object bytes"
                )
            membership = (repository, obj["git_object_id"], data["git_acquisition_id"])
            if (
                _row(
                    db,
                    "repository_object_sources",
                    ("repository_uuidv4", "git_object_id", "git_acquisition_id"),
                    membership,
                )
                is None
            ):
                missing.append(
                    {
                        "table": "repository_object_sources",
                        "columns": (
                            "repository_uuidv4",
                            "git_object_id",
                            "git_acquisition_id",
                        ),
                        "values": membership,
                    }
                )
    for dependency in dependencies:
        target = _row(
            db, dependency["table"], dependency["columns"], dependency["values"]
        )
        if target is None:
            # A UUID registered under a different object type is a forgery, not
            # a delayed dependency. Portable identities have distinct domains.
            ident = dependency["values"][0]
            if isinstance(ident, str) and "uuidv4" in dependency["columns"][0]:
                for other_table, column in set(REFERENCE_TARGETS.values()):
                    if (
                        other_table != dependency["table"]
                        and "uuidv4" in column
                        and _row(db, other_table, (column,), (ident,))
                    ):
                        raise JsonContractError(
                            "Reference UUID belongs to the wrong object kind"
                        )
            missing.append(dependency)
            continue
        if dependency["table"] == "payloads":
            if not _owned_payload(db, *dependency["values"], repository, source):
                unowned_payloads.append(dependency)
            continue
        target_repository, target_source = _owner(db, dependency["table"], target)
        if repository and target_repository and repository != target_repository:
            raise JsonContractError("Embedded reference crosses repository ownership")
        if source and target_source and source != target_source:
            raise JsonContractError("Embedded reference crosses Source ownership")
        if (
            source
            and target_repository
            and not db.execute(
                "SELECT 1 FROM source_repositories m JOIN sources s USING(source_id) WHERE m.repository_uuidv4=? AND s.source_registration_uuidv4=?",
                (target_repository, source),
            ).fetchone()
        ):
            raise JsonContractError(
                "Embedded repository is outside the Source membership"
            )
        if (
            repository
            and target_source
            and not db.execute(
                "SELECT 1 FROM source_repositories m JOIN sources s USING(source_id) WHERE m.repository_uuidv4=? AND s.source_registration_uuidv4=?",
                (repository, target_source),
            ).fetchone()
        ):
            raise JsonContractError(
                "Embedded Source does not own repository membership"
            )
        if (
            dependency["table"] == "service_instances"
            and repository
            and not db.execute(
                "SELECT 1 FROM repository_bindings WHERE repository_uuidv4=? AND service_instance_uuidv4=?",
                (repository, dependency["values"][0]),
            ).fetchone()
        ):
            raise JsonContractError("Embedded service has no owner binding")
    if unowned_payloads and not any(
        d["table"]
        in {
            "fetch_occurrences",
            "git_acquisitions",
            "source_input_observations",
            "parsed_results",
            "git_objects",
            "git_object_payloads",
            "repository_object_sources",
        }
        for d in missing
    ):
        raise JsonContractError("Payload reference has no acquisition under its owner")
    if missing and not allow_missing:
        raise MissingJsonDependencies(missing)
    return missing


def inventory(db):
    """Discover CHECK-backed JSON columns; adding one requires classification."""
    discovered = set()
    json_names = {column for _, column in JSON_REGISTRY}
    for table, ddl in db.execute(
        "SELECT name,sql FROM sqlite_schema WHERE type='table' AND sql IS NOT NULL"
    ):
        for column in re.findall(r"json_valid\(\s*(\w+)\s*\)", ddl):
            discovered.add((table, column))
        # New authored fields cannot evade the inventory by omitting their JSON
        # CHECK. Conventional JSON column names still require registration.
        for info in db.execute(f"PRAGMA table_info({table})"):
            if info[1].endswith("_json") or info[1] in json_names:
                discovered.add((table, info[1]))
    unknown = discovered - JSON_REGISTRY.keys()
    if unknown:
        raise JsonContractError(f"Unclassified JSON fields: {sorted(unknown)}")
    return [
        {
            "table": t,
            "column": c,
            "category": JSON_REGISTRY[t, c].category,
            "shape": JSON_REGISTRY[t, c].shape,
            "nullable": JSON_REGISTRY[t, c].nullable,
        }
        for t, c in sorted(discovered)
    ]


def validate_catalog(db):
    """Read-only exhaustive authored JSON audit for explicit maintenance checks."""
    fields = inventory(db)
    tables = sorted(
        {
            f["table"]
            for f in fields
            if f["category"]
            in {
                "authored",
                "current-acquisition",
                "current-field-evidence",
                "current-members",
                "input-manifest",
                "git-roots",
                "git-object-manifest",
                "definition",
                "predecessor-manifest",
                "fact-manifest",
            }
        }
    )
    checked = 0
    for table in tables:
        cursor = db.execute(f"SELECT * FROM {table}")
        columns = [c[0] for c in cursor.description]
        for row in cursor:
            validate_record(db, table, dict(zip(columns, row)))
            checked += 1
    return {"classified_fields": len(fields), "checked_records": checked}


def _sql_owner(table):
    direct = {
        "service_instances": ("NULL", "NULL"),
        "repositories": ("NEW.repository_uuidv4", "NULL"),
        "repository_bindings": ("NEW.repository_uuidv4", "NULL"),
        "repository_endpoints": ("NEW.repository_uuidv4", "NULL"),
        "git_acquisitions": ("NEW.repository_uuidv4", "NULL"),
        "git_acquisition_publications": ("NEW.repository_uuidv4", "NULL"),
        "resume_scopes": ("NEW.repository_uuidv4", "NULL"),
        "fetch_occurrences": ("NEW.repository_uuidv4", "NULL"),
        "code_observations": ("NEW.repository_uuidv4", "NULL"),
        "issue_resources": ("NEW.repository_uuidv4", "NULL"),
        "review_resources": ("NEW.repository_uuidv4", "NULL"),
        "source_input_observations": ("NULL", "NEW.source_registration_uuidv4"),
        "parsed_results": ("NEW.repository_uuidv4", "NEW.source_registration_uuidv4"),
        "repository_name_observations": (
            "CASE WHEN NEW.owner_source_registration_uuidv4 IS NULL THEN NEW.repository_uuidv4 END",
            "NEW.owner_source_registration_uuidv4",
        ),
        "identity_relations": ("NULL", "NULL"),
        "identity_relation_cancellations": ("NULL", "NULL"),
    }
    if table in direct:
        return direct[table]
    if table in {"incremental_scans", "completion_markers", "current_collection_pages"}:
        return (
            "(SELECT repository_uuidv4 FROM fetch_collections WHERE fetch_collection_id=NEW.fetch_collection_id)",
            "NULL",
        )
    if table == "coverage_claims":
        return (
            "(SELECT repository_uuidv4 FROM coverage_scopes WHERE coverage_scope_id=NEW.coverage_scope_id)",
            "NULL",
        )
    return "NULL", "NULL"


def _sql_uuid(value):
    return f"(length({value})=36 AND length(CAST({value} AS BLOB))=36 AND substr({value},9,1)='-' AND substr({value},14,1)='-' AND substr({value},19,1)='-' AND substr({value},24,1)='-' AND length(replace({value},'-',''))=32 AND replace({value},'-','') NOT GLOB '*[^0-9a-f]*' AND substr({value},15,1)='4' AND substr({value},20,1) IN ('8','9','a','b'))"


def _sql_hex(value, width):
    # SQLite TEXT length and GLOB stop at NUL; byte width alone would permit a
    # hidden nonhex suffix. Both widths are required for every canonical digest.
    return f"(typeof({value})='text' AND length({value})=({width}) AND length(CAST({value} AS BLOB))=({width}) AND {value} NOT GLOB '*[^0-9a-f]*')"


def _sql_target_owner(table, alias="t"):
    if table in {
        "repositories",
        "repository_bindings",
        "repository_endpoints",
        "git_acquisitions",
        "fetch_collections",
        "resume_scopes",
        "change_requests",
        "change_request_observations",
        "document_observations",
        "code_observations",
        "fetch_occurrences",
        "parsed_results",
    }:
        repository = f"{alias}.repository_uuidv4"
    elif table == "fact_selection_decisions":
        repository = f"{alias}.repository_uuidv4"
    elif table == "completion_markers":
        repository = f"(SELECT repository_uuidv4 FROM fetch_collections WHERE fetch_collection_id={alias}.fetch_collection_id)"
    else:
        repository = "NULL"
    source = (
        f"{alias}.source_registration_uuidv4"
        if table
        in {
            "sources",
            "parsed_results",
            "source_input_observations",
            "fact_selection_decisions",
        }
        else "NULL"
    )
    return repository, source


def _sql_owner_predicate(repository, source, target_repository, target_source):
    owner = f"({repository} IS NULL OR {target_repository} IS NULL OR {repository}={target_repository}) AND ({source} IS NULL OR {target_source} IS NULL OR {source}={target_source})"
    if target_source != "NULL":
        owner += f" AND ({repository} IS NULL OR {target_source} IS NULL OR EXISTS(SELECT 1 FROM source_repositories m JOIN sources s USING(source_id) WHERE m.repository_uuidv4={repository} AND s.source_registration_uuidv4={target_source}))"
    if target_repository != "NULL":
        owner += f" AND ({source} IS NULL OR {target_repository} IS NULL OR EXISTS(SELECT 1 FROM source_repositories m JOIN sources s USING(source_id) WHERE m.repository_uuidv4={target_repository} AND s.source_registration_uuidv4={source}))"
    return owner


def _sql_code_role(role, oid_width):
    suffix = _sql_hex(f"substr({role},15)", oid_width)
    return f"({role} IN ('head','base','merge','test-merge') OR (substr({role},1,14)='review-target:' AND {suffix}))"


def _sql_capture_conditions(doc, service):
    repository = f"json_extract({doc},'$.repository_uuidv4')"
    binding = f"json_extract({doc},'$.repository_binding_id')"
    captured_service = f"json_extract({doc},'$.service_instance_uuidv4')"
    source = f"json_extract({doc},'$.source_registration_uuidv4')"
    return [
        f"coalesce(json_type({doc}),'')<>'object'",
        f"coalesce(json_type({doc},'$.repository_uuidv4'),'')<>'text' OR NOT {_sql_uuid(repository)}",
        f"coalesce(json_type({doc},'$.service_instance_uuidv4'),'')<>'text' OR NOT {_sql_uuid(captured_service)} OR {captured_service} IS NOT {service}",
        f"coalesce(json_type({doc},'$.repository_binding_id'),'')<>'text' OR length({binding})=0 OR instr({binding},char(0))>0",
        f"coalesce(json_type({doc},'$.endpoint'),'')<>'text' OR length(json_extract({doc},'$.endpoint'))=0 OR instr(json_extract({doc},'$.endpoint'),char(0))>0",
        f"(json_type({doc},'$.source_registration_uuidv4') IS NOT NULL AND (json_type({doc},'$.source_registration_uuidv4')<>'text' OR NOT {_sql_uuid(source)}))",
        f"EXISTS(SELECT 1 FROM repository_bindings b WHERE b.repository_binding_id={binding} AND (b.repository_uuidv4 IS NOT {repository} OR b.service_instance_uuidv4 IS NOT {service}))",
        f"(EXISTS(SELECT 1 FROM repositories r WHERE r.repository_uuidv4={repository}) AND NOT EXISTS(SELECT 1 FROM repository_bindings b WHERE b.repository_binding_id={binding} AND b.repository_uuidv4={repository} AND b.service_instance_uuidv4={service}))",
        f"EXISTS(SELECT 1 FROM sources s WHERE s.source_registration_uuidv4={source} AND ((s.service_instance_uuidv4 IS NOT NULL AND s.service_instance_uuidv4 IS NOT {service}) OR (EXISTS(SELECT 1 FROM repositories r WHERE r.repository_uuidv4={repository}) AND NOT EXISTS(SELECT 1 FROM source_repositories m WHERE m.source_id=s.source_id AND m.repository_uuidv4={repository}))))",
    ]


def _sql_snapshot_conditions(doc, repository, source):
    """Validate one distinct capture snapshot, without traversing its owners."""
    allowed = set(REFERENCE_TARGETS) | set(REFERENCE_LISTS)
    known = ",".join(f"'{key}'" for key in sorted(allowed))
    local = ",".join(f"'{key}'" for key in sorted(LOCAL_REFERENCE_KEYS))
    uuid_keys = ",".join(
        f"'{key}'" for key in sorted(REFERENCE_TARGETS) if "uuidv4" in key
    )
    text_keys = ",".join(
        f"'{key}'" for key in sorted(REFERENCE_TARGETS) if "uuidv4" not in key
    )
    conditions = [
        f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE typeof(j.key)='text' GROUP BY j.parent,j.key HAVING count(*)>1)",
        f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE j.key IN ({local}) OR ((j.key GLOB '*_uuidv4' OR j.key GLOB '*_uuidv4s' OR j.key GLOB '*_sha256' OR j.key IN ('sha256','representation','references')) AND j.key NOT IN ({known}) AND NOT EXISTS(SELECT 1 FROM json_tree({doc}) p WHERE p.id=j.parent AND p.key='payload')))",
        f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE (j.key IN ({uuid_keys}) AND (j.type<>'text' OR NOT {_sql_uuid('j.value')})) OR (j.key IN ({text_keys}) AND (j.type<>'text' OR length(j.value)=0 OR instr(j.value,char(0))>0)))",
    ]
    # These encodings were never non-owning scalar capture identifiers. Preserve
    # their authored shape and owner checks if present in an explicit context.
    for key, target_key in sorted(REFERENCE_LISTS.items()):
        target, identity = REFERENCE_TARGETS[target_key]
        target_repository, target_source = _sql_target_owner(target)
        owner = _sql_owner_predicate(
            repository, source, target_repository, target_source
        )
        canonical = (
            _sql_uuid("e.value")
            if "uuidv4" in target_key
            else "(length(e.value)>0 AND instr(e.value,char(0))=0)"
        )
        conditions.append(
            f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE j.key='{key}' AND (j.type<>'array' OR EXISTS(SELECT 1 FROM json_each(j.value) e WHERE e.type<>'text' OR NOT {canonical} OR NOT EXISTS(SELECT 1 FROM {target} t WHERE t.{identity}=e.value AND {owner}))))"
        )
    payload_shape = (
        "coalesce(json_type(j.value,'$.representation'),'')<>'text' OR coalesce(json_type(j.value,'$.sha256'),'')<>'text' OR (SELECT count(*) FROM json_each(j.value))<>2 OR json_extract(j.value,'$.representation') NOT IN ('decoded_api','legacy_normalized','git-object-raw-v1') OR NOT "
        + _sql_hex("json_extract(j.value,'$.sha256')", 64)
    )
    payload_owner = f"({repository} IS NULL OR EXISTS(SELECT 1 FROM fetch_occurrences f WHERE f.repository_uuidv4={repository} AND f.payload_representation=p.representation AND f.payload_sha256=p.sha256) OR EXISTS(SELECT 1 FROM git_object_payloads g JOIN repository_object_sources o USING(git_object_id) JOIN git_acquisitions a USING(git_acquisition_id) WHERE a.repository_uuidv4={repository} AND g.payload_representation=p.representation AND g.payload_sha256=p.sha256)) AND ({source} IS NULL OR EXISTS(SELECT 1 FROM source_input_observations i WHERE i.source_registration_uuidv4={source} AND i.payload_representation=p.representation AND i.payload_sha256=p.sha256))"
    conditions.append(
        f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE j.key='payload' AND (j.type<>'object' OR {payload_shape} OR NOT EXISTS(SELECT 1 FROM payloads p WHERE p.representation=json_extract(j.value,'$.representation') AND lower(hex(p.sha256))=json_extract(j.value,'$.sha256') AND {payload_owner})))"
    )
    return conditions


def guard_sql():
    """Generate standalone SQLite guards, requiring no connection callbacks."""
    output = [
        "-- Generated from json_contracts.JSON_REGISTRY; edit the registry and regenerate.\n"
    ]
    for (table, column), schema in sorted(JSON_REGISTRY.items()):
        if schema.category not in {
            "authored",
            "current-acquisition",
            "current-field-evidence",
            "current-members",
            "input-manifest",
            "git-roots",
            "git-object-manifest",
            "definition",
        }:
            continue
        doc = f"NEW.{column}"
        repository, source = _sql_owner(table)
        if schema.category == "current-acquisition":
            repository = f"json_extract({doc},'$.repository_uuidv4')"
        conditions = [
            # Object keys are TEXT; array indices are INTEGER. Filtering keys
            # therefore preserves nested duplicate detection without rewalking
            # the entire tree for every parent in a quadratic self-join.
            f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE typeof(j.key)='text' GROUP BY j.parent,j.key HAVING count(*)>1)",
        ]
        if schema.category == "current-acquisition":
            conditions.extend(
                _sql_capture_conditions(doc, "NEW.service_instance_uuidv4")
            )
        if schema.category == "current-field-evidence":
            conditions = [
                f"EXISTS(SELECT 1 FROM json_each({doc}) e GROUP BY e.key HAVING count(*)>1)"
            ]
            allowed = (
                _ISSUE_EVIDENCE_FIELDS
                if table == "issue_resources"
                else _REVIEW_EVIDENCE_FIELDS
            )
            fields = ",".join(f"'{name}'" for name in sorted(allowed))
            keys = ",".join(f"'{name}'" for name in sorted(_EVIDENCE_KEYS))
            conditions.append(
                f"EXISTS(SELECT 1 FROM json_each({doc}) e WHERE CASE WHEN NOT json_valid(e.key) THEN 1 WHEN json_type(e.key)<>'array' THEN 1 ELSE (json_array_length(e.key)=0 OR json(e.key)<>e.key OR (json_array_length(e.key)=1 AND json_array(json_extract(e.key,'$[0]'))<>e.key) OR EXISTS(SELECT 1 FROM json_each(e.key) p WHERE p.type<>'text') OR json_extract(e.key,'$[0]') NOT IN ({fields}) OR (json_array_length(e.key)>1 AND json_extract(e.key,'$[0]')<>'metadata')) END)"
            )
            conditions.append(
                f"EXISTS(WITH RECURSIVE metadata_paths(path,value,type) AS (SELECT json_array('metadata'),NEW.metadata,'object' UNION ALL SELECT json_insert(p.path,'$[#]',j.key),j.value,j.type FROM metadata_paths p JOIN json_each(CASE WHEN p.type='object' THEN p.value ELSE '{{}}' END) j WHERE p.type='object') SELECT 1 FROM json_each({doc}) e WHERE json_extract(e.key,'$[0]')='metadata' AND NOT EXISTS(SELECT 1 FROM metadata_paths p WHERE p.path=e.key))"
            )
            conditions.append(
                f"EXISTS(SELECT 1 FROM json_each({doc}) e JOIN json_each(e.key) depth WHERE json_extract(e.key,'$[0]')='metadata' AND CAST(depth.key AS INTEGER)>0 AND NOT EXISTS(SELECT 1 FROM json_each({doc}) ancestor WHERE ancestor.key=(SELECT json_group_array(prefix.value) FROM json_each(e.key) prefix WHERE CAST(prefix.key AS INTEGER)<CAST(depth.key AS INTEGER))))"
            )
            invalid = [
                f"(SELECT count(*) FROM json_each(e.value))<>{len(_EVIDENCE_KEYS)}",
                f"EXISTS(SELECT 1 FROM json_each(e.value) p WHERE p.key NOT IN ({keys}))",
                "coalesce(json_type(e.value,'$.observed_at_us'),'')<>'integer' OR typeof(json_extract(e.value,'$.observed_at_us'))<>'integer'",
                "coalesce(json_type(e.value,'$.parsed_at_us'),'')<>'integer' OR typeof(json_extract(e.value,'$.parsed_at_us'))<>'integer'",
                "coalesce(json_type(e.value,'$.provider_updated_at_us'),'') NOT IN ('integer','null')",
                "(json_type(e.value,'$.provider_updated_at_us')='integer' AND typeof(json_extract(e.value,'$.provider_updated_at_us'))<>'integer')",
                "coalesce(json_type(e.value,'$.provider_clock_scope'),'') NOT IN ('text','null')",
                "(json_type(e.value,'$.provider_clock_scope')='text' AND json_extract(e.value,'$.provider_clock_scope') IS NOT CASE NEW.kind WHEN 'issue' THEN 'github-issue-updated-at' WHEN 'issue-comment' THEN 'github-issue-comment-updated-at' WHEN 'review-comment' THEN 'github-review-comment-updated-at' END)",
                "(NEW.kind='review' AND json_type(e.value,'$.provider_updated_at_us')<>'null')",
                "coalesce(json_type(e.value,'$.parser_profile_uuidv4'),'')<>'text'",
                f"NOT {_sql_uuid("json_extract(e.value,'$.parser_profile_uuidv4')")}",
                "coalesce(json_type(e.value,'$.acquisition_scope'),'')<>'object'",
            ]
            capture_invalid = _sql_capture_conditions(
                "capture.scope", "NEW.service_instance_uuidv4"
            )
            capture_invalid.extend(
                _sql_snapshot_conditions("capture.scope", repository, source)
            )
            if table == "review_resources":
                capture_invalid.extend(
                    f"json_extract(capture.scope,'$.{name}') IS NOT NEW.{name}"
                    for name in (
                        "repository_uuidv4",
                        "repository_binding_id",
                        "change_request_id",
                    )
                )
            else:
                capture_invalid.append(
                    "json_type(capture.scope,'$.change_request_id') IS NOT NULL"
                )
            invalid.append(
                "(json_type(e.value,'$.acquisition_scope.parser_profile_uuidv4') IS NOT NULL AND json_extract(e.value,'$.acquisition_scope.parser_profile_uuidv4') IS NOT json_extract(e.value,'$.parser_profile_uuidv4'))"
            )
            fact_kind = "CASE NEW.kind WHEN 'issue-comment' THEN 'ordinary-issue-comment' ELSE NEW.kind END"
            conditions.append(
                f"EXISTS(SELECT 1 FROM (SELECT DISTINCT json_extract(e.value,'$.parser_profile_uuidv4') AS profile FROM json_each({doc}) e) evidence WHERE NOT EXISTS(SELECT 1 FROM parser_profile_capabilities p WHERE p.parser_profile_uuidv4=evidence.profile AND p.owner_kind='repository' AND p.fact_kind=({fact_kind})))"
            )
            conditions.append(
                f"EXISTS(SELECT 1 FROM (SELECT DISTINCT json_extract(e.value,'$.acquisition_scope') AS scope FROM json_each({doc}) e) capture WHERE "
                + " OR ".join(capture_invalid)
                + ")"
            )
            conditions.append(
                f"EXISTS(SELECT 1 FROM json_each({doc}) e WHERE CASE WHEN e.type<>'object' THEN 1 ELSE ("
                + " OR ".join(invalid)
                + ") END)"
            )
            for operation in ("INSERT", "UPDATE"):
                output.append(
                    f"CREATE TRIGGER json_{table}_{column}_{operation.lower()} BEFORE {operation} ON {table}\nWHEN {doc} IS NOT NULL AND CASE WHEN NOT json_valid({doc}) THEN 1 WHEN json_type({doc})<>'{schema.shape}' THEN 1 ELSE (\n "
                    + "\n OR ".join(conditions)
                    + f"\n) END BEGIN SELECT RAISE(ABORT,'JSON reference schema, dependency or ownership violation: {table}.{column}'); END;\n"
                )
            continue
        if (table, column) == ("current_collection_pages", "members"):
            ident = "CASE json_extract(m.value,'$.family') WHEN 'issue' THEN json_extract(m.value,'$.provider_resource_id') ELSE json_extract(m.value,'$.provider_change_request_document_id') END"
            canonical_provider = f"(typeof(({ident}))='text' AND length(({ident}))>0 AND length(CAST(({ident}) AS BLOB))=length(({ident})) AND substr(({ident}),1,1) BETWEEN '1' AND '9' AND ({ident}) NOT GLOB '*[^0-9]*')"
            member_digest = _sql_hex("json_extract(m.value,'$.state_digest')", 64)
            conditions.append(
                f"EXISTS(SELECT 1 FROM json_each({doc}) m WHERE CASE WHEN m.type<>'object' THEN 1 ELSE ((SELECT count(*) FROM json_each(m.value))<>5 OR coalesce(json_type(m.value,'$.family'),'')<>'text' OR coalesce(json_extract(m.value,'$.family'),'') NOT IN ('issue','review') OR NOT {canonical_provider} OR NOT {member_digest} OR (json_extract(m.value,'$.family')='issue' AND (coalesce(json_extract(m.value,'$.kind'),'') NOT IN ('issue','issue-comment') OR coalesce(json_type(m.value,'$.service_instance_uuidv4'),'')<>'text' OR NOT EXISTS(SELECT 1 FROM fetch_collections c JOIN resume_scopes s USING(resume_scope_id) JOIN repository_bindings b ON b.repository_binding_id=s.repository_binding_id WHERE c.fetch_collection_id=NEW.fetch_collection_id AND b.repository_uuidv4=c.repository_uuidv4 AND b.service_instance_uuidv4=json_extract(m.value,'$.service_instance_uuidv4')))) OR (json_extract(m.value,'$.family')='review' AND (coalesce(json_extract(m.value,'$.kind'),'') NOT IN ('review','review-comment') OR coalesce(json_type(m.value,'$.change_request_id'),'')<>'text' OR NOT EXISTS(SELECT 1 FROM fetch_collections c JOIN resume_scopes s USING(resume_scope_id) JOIN change_requests r ON r.change_request_id=json_extract(m.value,'$.change_request_id') AND r.repository_uuidv4=c.repository_uuidv4 AND r.repository_binding_id=s.repository_binding_id WHERE c.fetch_collection_id=NEW.fetch_collection_id) OR EXISTS(SELECT 1 FROM fetch_collections c WHERE c.fetch_collection_id=NEW.fetch_collection_id AND c.change_request_id IS NOT NULL AND c.change_request_id<>json_extract(m.value,'$.change_request_id'))))) END)"
            )
            conditions.append(
                f"EXISTS(SELECT 1 FROM json_each({doc}) m GROUP BY json_extract(m.value,'$.family'),coalesce(json_extract(m.value,'$.service_instance_uuidv4'),json_extract(m.value,'$.change_request_id')),json_extract(m.value,'$.kind'),coalesce(json_extract(m.value,'$.provider_resource_id'),json_extract(m.value,'$.provider_change_request_document_id')) HAVING count(*)>1)"
            )
        if (table, column) == ("completion_markers", "evidence"):
            manifest = f"{doc},'$.current_page_collections'"
            conditions.append(
                f"(json_type({manifest}) IS NOT NULL AND (json_type({manifest})<>'array' OR EXISTS(SELECT 1 FROM json_each({manifest}) m WHERE CASE WHEN m.type<>'object' THEN 1 ELSE ((SELECT count(*) FROM json_each(m.value))<>2 OR coalesce(json_type(m.value,'$.fetch_collection_id'),'')<>'text' OR coalesce(json_type(m.value,'$.page_ordinals'),'')<>'array' OR coalesce(json_array_length(m.value,'$.page_ordinals'),0)=0 OR EXISTS(SELECT 1 FROM json_each(m.value,'$.page_ordinals') e WHERE e.type<>'integer' OR e.value<>CAST(e.key AS INTEGER))) END) OR EXISTS(SELECT 1 FROM json_each({manifest}) m GROUP BY CASE WHEN m.type='object' THEN json_extract(m.value,'$.fetch_collection_id') END HAVING count(*)>1)))"
            )
        if (table, column) == ("git_acquisitions", "roots_manifest"):
            oid_width = "CASE NEW.object_format WHEN 'sha1' THEN 40 WHEN 'sha256' THEN 64 ELSE -1 END"
            invalid = [
                "m.type<>'object'",
                "EXISTS(SELECT 1 FROM json_each(m.value) k WHERE k.key NOT IN ('name','name_b64','oid','type','peeled','role','number','expected'))",
            ]
            for field in ("name", "name_b64", "oid", "type"):
                invalid.append(
                    f"coalesce(json_type(m.value,'$.{field}'),'')<>'text' OR length(json_extract(m.value,'$.{field}'))=0 OR instr(json_extract(m.value,'$.{field}'),char(0))>0"
                )
            invalid += [
                "coalesce(json_type(m.value,'$.peeled'),'') NOT IN ('null','text')",
                "json_extract(m.value,'$.type') NOT IN ('commit','tree','blob','tag')",
                f"NOT {_sql_hex("json_extract(m.value,'$.oid')", oid_width)}",
                f"(json_type(m.value,'$.peeled')='text' AND NOT {_sql_hex("json_extract(m.value,'$.peeled')", oid_width)})",
                "length(json_extract(m.value,'$.name_b64'))%4<>0 OR json_extract(m.value,'$.name_b64') GLOB '*[^A-Za-z0-9+/=]*' OR length(rtrim(json_extract(m.value,'$.name_b64'),'='))<length(json_extract(m.value,'$.name_b64'))-2 OR instr(rtrim(json_extract(m.value,'$.name_b64'),'='),'=')>0",
                "((json_type(m.value,'$.role') IS NOT NULL OR json_type(m.value,'$.number') IS NOT NULL OR json_type(m.value,'$.expected') IS NOT NULL) AND (coalesce(json_type(m.value,'$.role'),'')<>'text' OR length(json_extract(m.value,'$.role'))=0 OR instr(json_extract(m.value,'$.role'),char(0))>0 OR coalesce(json_type(m.value,'$.number'),'')<>'integer' OR json_extract(m.value,'$.number')<=0 OR coalesce(json_type(m.value,'$.expected'),'')<>'text' OR json_extract(m.value,'$.expected')<>json_extract(m.value,'$.oid')))",
            ]
            conditions.append(
                f"EXISTS(SELECT 1 FROM json_each({doc}) m WHERE CASE WHEN m.type<>'object' THEN 1 ELSE ("
                + " OR ".join(invalid)
                + ") END)"
            )
        if (table, column) == ("parsed_results", "derivation_json"):
            for field in ("parser", "kind", "decoder"):
                conditions.append(
                    f"(json_type({doc},'$.{field}') IS NOT NULL AND (json_type({doc},'$.{field}')<>'text' OR length(json_extract({doc},'$.{field}'))=0))"
                )
        if (table, column) == ("code_observations", "details"):
            width = "(CASE NEW.object_format WHEN 'sha1' THEN 40 WHEN 'sha256' THEN 64 ELSE -1 END)"
            for field in ("api_head_base_stable", "code_inputs_complete"):
                conditions.append(
                    f"(json_type({doc},'$.{field}') IS NOT NULL AND json_type({doc},'$.{field}') NOT IN ('true','false'))"
                )
            role = _sql_code_role("e.key", width)
            conditions.append(
                f"(json_type({doc},'$.expected_roles') IS NOT NULL AND (json_type({doc},'$.expected_roles')<>'object' OR EXISTS(SELECT 1 FROM json_each({doc},'$.expected_roles') e WHERE NOT {role} OR e.type<>'text' OR NOT {_sql_hex('e.value', width)} OR (substr(e.key,1,14)='review-target:' AND substr(e.key,15)<>e.value))))"
            )
            role = _sql_code_role("e.value", width)
            conditions.append(
                f"(json_type({doc},'$.missing_roles') IS NOT NULL AND (json_type({doc},'$.missing_roles')<>'array' OR EXISTS(SELECT 1 FROM json_each({doc},'$.missing_roles') e WHERE e.type<>'text' OR NOT {role})))"
            )
            conditions.append(
                f"(json_type({doc},'$.provider_limits') IS NOT NULL AND (json_type({doc},'$.provider_limits')<>'object' OR EXISTS(SELECT 1 FROM json_each({doc},'$.provider_limits') e WHERE e.key NOT IN ('commits','files') OR e.type<>'integer' OR e.value<=0 OR e.value>9223372036854775807)))"
            )
            conditions.append(
                f"(json_type({doc},'$.merge') IS NOT NULL AND (json_type({doc},'$.merge')<>'object' OR EXISTS(SELECT 1 FROM json_each({doc},'$.merge') e WHERE e.key NOT IN ('merge','test-merge') OR (e.type<>'null' AND (e.type<>'text' OR NOT {_sql_hex('e.value', width)})))))"
            )
        if (table, column) in {
            ("fetch_occurrences", "request"),
            ("resume_scopes", "request_context"),
        }:
            for field in (
                "thread",
                "review_thread_provider_resource_id",
                "query",
                "url",
                "method",
            ):
                conditions.append(
                    f"(json_type({doc},'$.{field}') IS NOT NULL AND (json_type({doc},'$.{field}')<>'text' OR length(json_extract({doc},'$.{field}'))=0))"
                )
            conditions.append(
                f"(json_type({doc},'$.variables') IS NOT NULL AND json_type({doc},'$.variables')<>'object')"
            )
            for field in ("thread", "owner", "name"):
                conditions.append(
                    f"(json_type({doc},'$.variables.{field}') IS NOT NULL AND (json_type({doc},'$.variables.{field}')<>'text' OR length(json_extract({doc},'$.variables.{field}'))=0))"
                )
            for field in ("cursor", "commentCursor"):
                conditions.append(
                    f"(json_type({doc},'$.variables.{field}') IS NOT NULL AND json_type({doc},'$.variables.{field}') NOT IN ('text','null'))"
                )
            for field in ("number", "pageSize"):
                conditions.append(
                    f"(json_type({doc},'$.variables.{field}') IS NOT NULL AND (json_type({doc},'$.variables.{field}')<>'integer' OR json_extract({doc},'$.variables.{field}')<=0 OR json_extract({doc},'$.variables.{field}')>9223372036854775807))"
                )
        if (table, column) in {
            ("completion_markers", "evidence"),
            ("fetch_occurrences", "request"),
        }:
            for field in ("terminal", "context_proven", "operational_only"):
                conditions.append(
                    f"(json_type({doc},'$.{field}') IS NOT NULL AND json_type({doc},'$.{field}') NOT IN ('true','false'))"
                )
            conditions.append(
                f"(json_type({doc},'$.status') IS NOT NULL AND (json_type({doc},'$.status')<>'integer' OR json_extract({doc},'$.status') NOT BETWEEN 100 AND 599))"
            )
            conditions.append(
                f"(json_type({doc},'$.response') IS NOT NULL AND (json_type({doc},'$.response')<>'object' OR (SELECT count(*) FROM json_each({doc},'$.response'))<>2 OR coalesce(json_type({doc},'$.response.status'),'')<>'integer' OR json_extract({doc},'$.response.status') NOT BETWEEN 100 AND 599 OR coalesce(json_type({doc},'$.response.headers'),'')<>'object' OR EXISTS(SELECT 1 FROM json_each({doc},'$.response.headers') h WHERE h.key<>'etag' OR h.type<>'text')))"
            )
        if (table, column) == ("completion_markers", "evidence"):
            conditions.append(
                f"(json_extract({doc},'$.kind')='current-resource-pages-v1' AND ((SELECT count(*) FROM json_each({doc}))<>3 OR coalesce(json_type({doc},'$.terminal'),'')<>'true' OR coalesce(json_type({doc},'$.page_ordinals'),'')<>'array' OR json_array_length({doc},'$.page_ordinals')=0 OR EXISTS(SELECT 1 FROM json_each({doc},'$.page_ordinals') e WHERE e.type<>'integer' OR e.value<>CAST(e.key AS INTEGER))))"
            )
            conditions.append(
                f"(json_extract({doc},'$.status')=304 AND (coalesce(json_type({doc},'$.change_request_observation_uuidv4'),'')<>'text' OR coalesce(json_type({doc},'$.parsed_result_uuidv4'),'')<>'text' OR coalesce(json_type({doc},'$.fetch_occurrence_uuidv4'),'')<>'text' OR coalesce(json_type({doc},'$.payload'),'')<>'object'))"
            )
        allowed = set(REFERENCE_TARGETS) | set(REFERENCE_LISTS)
        known = ",".join(f"'{k}'" for k in sorted(allowed))
        local = ",".join(f"'{k}'" for k in sorted(LOCAL_REFERENCE_KEYS))
        digest_exemption = (
            " AND j.key<>'sha256' AND j.key NOT GLOB '*_sha256'"
            if schema.category == "definition"
            else ""
        )
        conditions.append(
            f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE j.key IN ({local}) OR ((j.key GLOB '*_uuidv4' OR j.key GLOB '*_uuidv4s' OR j.key GLOB '*_sha256' OR j.key IN ('sha256','representation','references')) AND j.key NOT IN ({known}){digest_exemption} AND NOT EXISTS(SELECT 1 FROM json_tree({doc}) p WHERE p.id=j.parent AND p.key='payload')))"
        )
        if schema.category == "definition":
            conditions.append(
                f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE (j.key='sha256' OR j.key GLOB '*_sha256') AND NOT EXISTS(SELECT 1 FROM json_tree({doc}) p WHERE p.id=j.parent AND p.key='payload') AND (j.type<>'text' OR NOT {_sql_hex('j.value', 64)}))"
            )
        for key, (target, identity) in sorted(REFERENCE_TARGETS.items()):
            declaration = ""
            if schema.category == "current-acquisition" and key in _CAPTURE_KEYS:
                declaration += f" AND NOT (j.path='$' AND NEW.kind='issue-comment' AND json_extract({doc},'$.repository_uuidv4')<>NEW.repository_uuidv4)"
            if (table, column, key) == (
                "parsed_results",
                "derivation_json",
                "selection_decision_uuidv4",
            ):
                declaration = f" AND NOT (j.path='$' AND coalesce(json_extract({doc},'$.kind'),'')='git')"
            canonical = (
                _sql_uuid("j.value")
                if "uuidv4" in key
                else "(length(j.value)>0 AND instr(j.value,char(0))=0)"
            )
            conditions.append(
                f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE j.key='{key}' AND (j.type<>'text' OR NOT {canonical}))"
            )
            target_repository, target_source = _sql_target_owner(target)
            owner = _sql_owner_predicate(
                repository, source, target_repository, target_source
            )
            if target == "service_instances":
                owner += f" AND ({repository} IS NULL OR EXISTS(SELECT 1 FROM repository_bindings b WHERE b.repository_uuidv4={repository} AND b.service_instance_uuidv4=t.{identity}))"
            conditions.append(
                f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE j.key='{key}'{declaration} AND NOT EXISTS(SELECT 1 FROM {target} t WHERE t.{identity}=j.value AND {owner}))"
            )
        for key, target_key in sorted(REFERENCE_LISTS.items()):
            target, identity = REFERENCE_TARGETS[target_key]
            target_repository, target_source = _sql_target_owner(target)
            canonical = (
                _sql_uuid("e.value")
                if "uuidv4" in target_key
                else "(length(e.value)>0 AND instr(e.value,char(0))=0)"
            )
            owner = _sql_owner_predicate(
                repository, source, target_repository, target_source
            )
            conditions.append(
                f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE j.key='{key}' AND (j.type<>'array' OR EXISTS(SELECT 1 FROM json_each(j.value) e WHERE e.type<>'text' OR NOT {canonical} OR NOT EXISTS(SELECT 1 FROM {target} t WHERE t.{identity}=e.value AND {owner}))))"
            )
        payload_shape = (
            "coalesce(json_type(j.value,'$.representation'),'')<>'text' OR coalesce(json_type(j.value,'$.sha256'),'')<>'text' OR (SELECT count(*) FROM json_each(j.value))<>2 OR json_extract(j.value,'$.representation') NOT IN ('decoded_api','legacy_normalized','git-object-raw-v1') OR NOT "
            + _sql_hex("json_extract(j.value,'$.sha256')", 64)
        )
        payload_owner = f"({repository} IS NULL OR EXISTS(SELECT 1 FROM fetch_occurrences f WHERE f.repository_uuidv4={repository} AND f.payload_representation=p.representation AND f.payload_sha256=p.sha256) OR EXISTS(SELECT 1 FROM git_object_payloads g JOIN repository_object_sources o USING(git_object_id) JOIN git_acquisitions a USING(git_acquisition_id) WHERE a.repository_uuidv4={repository} AND g.payload_representation=p.representation AND g.payload_sha256=p.sha256)) AND ({source} IS NULL OR EXISTS(SELECT 1 FROM source_input_observations i WHERE i.source_registration_uuidv4={source} AND i.payload_representation=p.representation AND i.payload_sha256=p.sha256))"
        conditions.append(
            f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE j.key='payload' AND (j.type<>'object' OR {payload_shape} OR NOT EXISTS(SELECT 1 FROM payloads p WHERE p.representation=json_extract(j.value,'$.representation') AND lower(hex(p.sha256))=json_extract(j.value,'$.sha256') AND {payload_owner})))"
        )
        for operation in ("INSERT", "UPDATE"):
            effective = (
                f"json_remove({doc},'$.head','$.base')"
                if (table, column) == ("resume_scopes", "request_context")
                else doc
            )
            guarded = "\n OR ".join(conditions).replace(doc, effective)
            output.append(
                f"CREATE TRIGGER json_{table}_{column}_{operation.lower()} BEFORE {operation} ON {table}\nWHEN {doc} IS NOT NULL AND CASE WHEN NOT json_valid({doc}) THEN 1 WHEN json_type({doc})<>'{schema.shape}' THEN 1 ELSE (\n "
                + guarded
                + f"\n) END BEGIN SELECT RAISE(ABORT,'JSON reference schema, dependency or ownership violation: {table}.{column}'); END;\n"
            )
    return "\n".join(output)
