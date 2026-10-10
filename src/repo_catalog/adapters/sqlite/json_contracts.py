"""Closed authored JSON, current field evidence and typed enumeration members.

The registry is the shared Python/standalone-SQL contract. Transport originals,
parser authority and local operation IDs cannot become domain dependencies.
"""

from __future__ import annotations

import base64
import json
import re
import uuid
from dataclasses import dataclass
from functools import lru_cache

from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.time import validate_epoch_us

JSON_REGISTRY = {}


@dataclass(frozen=True)
class JsonSchema:
    category: str
    shape: str = "object"
    nullable: bool = False


def _register(category, fields, *, shape="object", nullable=False):
    for field in fields.split():
        table, column = field.split(".")
        JSON_REGISTRY[table, column] = JsonSchema(category, shape, nullable)


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
                object_pairs_hook=unique,
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


def _acquisition_shape(scope, service):
    validate_capture_shape(scope)
    required = {
        "repository_uuidv4",
        "repository_binding_id",
        "service_instance_uuidv4",
    }
    if not required <= scope.keys():
        raise JsonContractError("Acquisition scope requires typed owner identities")
    if scope["service_instance_uuidv4"] != service:
        raise JsonContractError("Acquisition service differs from resource service")
    endpoint = scope.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint or "\x00" in endpoint:
        raise JsonContractError("Acquisition endpoint requires nonempty text")

    for name in ("parser_module", "parser_version"):
        if name in scope:
            _identity(name, scope[name])
    _walk(scope)


def _detached_acquisition(data, scope):
    return data.get("kind") == "issue-comment" and scope.get(
        "repository_uuidv4"
    ) != data.get("repository_uuidv4")


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
            missing.append(
                {
                    "table": "source_repositories",
                    "columns": ("source_id", "repository_uuidv4"),
                    "values": (source["source_id"], captured_repository),
                }
            )
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


def _sql_uuid(value):
    return f"(length({value})=36 AND length(CAST({value} AS BLOB))=36 AND substr({value},9,1)='-' AND substr({value},14,1)='-' AND substr({value},19,1)='-' AND substr({value},24,1)='-' AND length(replace({value},'-',''))=32 AND replace({value},'-','') NOT GLOB '*[^0-9a-f]*' AND substr({value},15,1)='4' AND substr({value},20,1) IN ('8','9','a','b'))"


def _sql_hex(value, width):
    # SQLite TEXT length and GLOB stop at NUL; byte width alone would permit a
    # hidden nonhex suffix. Both widths are required for every canonical digest.
    return f"(typeof({value})='text' AND length({value})=({width}) AND length(CAST({value} AS BLOB))=({width}) AND {value} NOT GLOB '*[^0-9a-f]*')"


def _sql_capture_conditions(doc, service):
    repository = f"json_extract({doc},'$.repository_uuidv4')"
    binding = f"json_extract({doc},'$.repository_binding_id')"
    captured_service = f"json_extract({doc},'$.service_instance_uuidv4')"
    source = f"json_extract({doc},'$.source_registration_uuidv4')"
    forbidden = ",".join(
        f"'{key}'" for key in sorted(_CURRENT_FORBIDDEN_REFERENCE_KEYS)
    )
    conditions = [
        *_sql_scope_conditions(doc),
        f"coalesce(json_type({doc}),'')<>'object'",
        f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE j.key IN ({forbidden}))",
        *[
            f"(json_type({doc},'$.{name}') IS NOT NULL AND (json_type({doc},'$.{name}')<>'text' OR length(json_extract({doc},'$.{name}'))=0 OR instr(json_extract({doc},'$.{name}'),char(0))>0))"
            for name in ("parser_module", "parser_version")
        ],
        f"coalesce(json_type({doc},'$.repository_uuidv4'),'')<>'text' OR NOT {_sql_uuid(repository)}",
        f"coalesce(json_type({doc},'$.service_instance_uuidv4'),'')<>'text' OR NOT {_sql_uuid(captured_service)} OR {captured_service} IS NOT {service}",
        f"coalesce(json_type({doc},'$.repository_binding_id'),'')<>'text' OR length({binding})=0 OR instr({binding},char(0))>0",
        f"coalesce(json_type({doc},'$.endpoint'),'')<>'text' OR length(json_extract({doc},'$.endpoint'))=0 OR instr(json_extract({doc},'$.endpoint'),char(0))>0",
        f"(json_type({doc},'$.source_registration_uuidv4') IS NOT NULL AND (json_type({doc},'$.source_registration_uuidv4')<>'text' OR NOT {_sql_uuid(source)}))",
        f"EXISTS(SELECT 1 FROM repository_bindings b WHERE b.repository_binding_id={binding} AND (b.repository_uuidv4 IS NOT {repository} OR b.service_instance_uuidv4 IS NOT {service}))",
        f"(EXISTS(SELECT 1 FROM repositories r WHERE r.repository_uuidv4={repository}) AND NOT EXISTS(SELECT 1 FROM repository_bindings b WHERE b.repository_binding_id={binding} AND b.repository_uuidv4={repository} AND b.service_instance_uuidv4={service}))",
        f"EXISTS(SELECT 1 FROM sources s WHERE s.source_registration_uuidv4={source} AND ((s.service_instance_uuidv4 IS NOT NULL AND s.service_instance_uuidv4 IS NOT {service}) OR (EXISTS(SELECT 1 FROM repositories r WHERE r.repository_uuidv4={repository}) AND NOT EXISTS(SELECT 1 FROM source_repositories m WHERE m.source_id=s.source_id AND m.repository_uuidv4={repository}))))",
    ]
    known = ",".join(
        "'" + key + "'" for key in sorted(set(REFERENCE_TARGETS) | set(REFERENCE_LISTS))
    )
    conditions.append(
        f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE (j.key GLOB '*_uuidv4' OR j.key GLOB '*_uuidv4s') AND j.key NOT IN ({known}))"
    )
    for key in sorted(REFERENCE_TARGETS):
        canonical = (
            _sql_uuid("j.value")
            if "uuidv4" in key
            else "(length(j.value)>0 AND instr(j.value,char(0))=0)"
        )
        conditions.append(
            f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE j.key='{key}' AND j.type<>'null' AND (j.type<>'text' OR NOT {canonical}))"
        )
    return conditions


_register(
    "authored",
    "service_instances.metadata repositories.metadata repository_bindings.metadata repository_endpoints.metadata git_acquisitions.request resume_scopes.request_context incremental_scans.evidence completion_markers.evidence identity_relations.evidence_json identity_relation_cancellations.evidence_json repository_names.provenance_json fetch_collections.scope_json code_assessments.details_json source_repositories.scope_json source_inventory_assessments.scope_json",
)
_register("authored", "coverage_claims.details_json", nullable=True)
_register("git-roots", "git_acquisitions.roots_manifest", shape="array", nullable=True)
_register(
    "provider",
    "issue_resources.metadata review_resources.metadata change_request_state.metadata document_state.metadata review_thread_state.metadata code_commits.metadata code_file_changes.metadata change_request_events.metadata source_repositories.metadata_json",
)
_register("decoded-headers", "git_commit_facts.metadata")
_register(
    "current-acquisition",
    "issue_resources.acquisition_scope_json review_resources.acquisition_scope_json change_request_state.acquisition_scope_json document_state.acquisition_scope_json review_thread_state.acquisition_scope_json",
)
_register(
    "current-field-evidence",
    "issue_resources.field_evidence_json review_resources.field_evidence_json change_request_state.field_evidence_json document_state.field_evidence_json review_thread_state.field_evidence_json source_repositories.field_evidence_json",
)
_register("current-members", "current_collection_pages.members", shape="array")
_register(
    "inventory-members", "source_inventory_assessments.members_json", shape="array"
)
_register(
    "operational",
    "jobs.request job_attempts.checkpoint search_documents.metadata payload_admission_staging.context_json unresolved_payloads.diagnostic_json",
)
_register("operational", "sources.settings", nullable=True)
_register(
    "staging-envelope",
    "exchange_staging.record_json identity_relation_staging.record_json",
)
_register(
    "local-key",
    "exchange_admissions.local_key_json exchange_local_identities.local_key_json",
)
REFERENCE_TARGETS = {
    "change_request_event_uuidv4": (
        "change_request_events",
        "change_request_event_uuidv4",
    ),
    "repository_uuidv4": ("repositories", "repository_uuidv4"),
    "service_instance_uuidv4": ("service_instances", "service_instance_uuidv4"),
    "source_registration_uuidv4": ("sources", "source_registration_uuidv4"),
    "completion_marker_uuidv4": ("completion_markers", "completion_marker_uuidv4"),
    "relation_uuidv4": ("identity_relations", "relation_uuidv4"),
    "git_acquisition_id": ("git_acquisitions", "git_acquisition_id"),
    "fetch_collection_id": ("fetch_collections", "fetch_collection_id"),
    "parent_fetch_collection_id": ("fetch_collections", "fetch_collection_id"),
    "child_fetch_collection_id": ("fetch_collections", "fetch_collection_id"),
    "change_request_id": ("change_requests", "change_request_id"),
    "repository_binding_id": ("repository_bindings", "repository_binding_id"),
    "repository_endpoint_id": ("repository_endpoints", "repository_endpoint_id"),
    "code_assessment_id": ("code_assessments", "code_assessment_id"),
    "code_listing_id": ("code_listings", "code_listing_id"),
}
REFERENCE_LISTS = {
    "change_request_ids": "change_request_id",
    "fetch_collection_ids": "fetch_collection_id",
    "git_acquisition_ids": "git_acquisition_id",
    "completion_marker_uuidv4s": "completion_marker_uuidv4",
}
LOCAL_REFERENCE_KEYS = {
    "git_object_id",
    "content_id",
    "source_id",
    "acquisition_root_id",
    "text_body_id",
    "completion_marker_id",
    "resume_scope_id",
    "stable_scope",
}
SHA = re.compile(r"[0-9a-f]{64}\Z")
_EVIDENCE_KEYS = {
    "provider_updated_at_us",
    "provider_clock_scope",
    "observed_at_us",
    "parsed_at_us",
    "parser_module",
    "parser_version",
    "acquisition_scope",
}
_CURRENT_FORBIDDEN_REFERENCE_KEYS = {
    "parser_profile_uuidv4",
    "parser_profile_verification_uuidv4",
    "parsed_result_uuidv4",
    "parsed_result_uuidv4s",
    "fetch_occurrence_uuidv4",
    "fetch_occurrence_uuidv4s",
    "source_input_uuidv4",
    "payload",
    "selection_decision_uuidv4",
    "selection_predecessors",
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
_API_EVIDENCE_FIELDS = {
    "change_request_state": {
        "state",
        "draft",
        "merged",
        "locked",
        "author",
        "url",
        "object_format",
        "head_oid",
        "base_oid",
        "merge_oid",
        "head_ref",
        "base_ref",
        "head_repository_binding_id",
        "base_repository_binding_id",
        "created_at_us",
        "closed_at_us",
        "merged_at_us",
        "metadata",
    },
    "document_state": {"body", "author", "url", "deleted", "metadata"},
    "review_thread_state": {
        "resolved",
        "outdated",
        "raw_path",
        "line",
        "start_line",
        "original_line",
        "original_start_line",
        "side",
        "start_side",
        "object_format",
        "commit_oid",
        "original_commit_oid",
        "diff_hunk",
        "metadata",
    },
    "source_repositories": {"name", "metadata"},
}
_CLOCKS = {
    "issue": "github-issue-updated-at",
    "issue-comment": "github-issue-comment-updated-at",
    "review-comment": "github-review-comment-updated-at",
    "change-request": "github-pr-updated-at",
    "pr-title": "github-pr-updated-at",
    "pr-body": "github-pr-updated-at",
}


def _evidence_table(candidate):
    if "provider_change_request_document_id" in candidate and candidate["kind"] not in {
        "review",
        "review-comment",
    }:
        return "document_state"
    return {
        "change-request": "change_request_state",
        "review-thread": "review_thread_state",
    }.get(
        candidate.get("kind"),
        "issue_resources"
        if candidate.get("kind") in {"issue", "issue-comment"}
        else "review_resources",
    )


def _allowed_fields(table):
    return (
        _ISSUE_EVIDENCE_FIELDS
        if table == "issue_resources"
        else _REVIEW_EVIDENCE_FIELDS
        if table == "review_resources"
        else _API_EVIDENCE_FIELDS[table]
    )


def _walk(value, **options):
    dependencies = []

    def visit(item):
        if isinstance(item, dict):
            for key, child in item.items():
                if (
                    key in _CURRENT_FORBIDDEN_REFERENCE_KEYS
                    or key in LOCAL_REFERENCE_KEYS
                ):
                    raise JsonContractError(
                        "Retired or local reference cannot own authored evidence"
                    )
                if key in REFERENCE_TARGETS and child is not None:
                    dependencies.append(_dependency(key, child))
                elif key in REFERENCE_LISTS:
                    if not isinstance(child, list):
                        raise JsonContractError("Reference list requires array")
                    dependencies.extend(
                        _dependency(REFERENCE_LISTS[key], entry) for entry in child
                    )
                elif key.endswith(("_uuidv4", "_uuidv4s")):
                    raise JsonContractError("Unknown typed identity reference")
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return list(
        {
            (item["table"], item["columns"], item["values"]): item
            for item in dependencies
        }.values()
    )


def _check_schema(table, column, value, data, *, check_owner=True):
    if table == "exchange_staging" and column == "record_json":
        _validate_staging_record(value, data)
    if (table, column) in _EVIDENCE_SCHEMAS:
        _check_metadata(_EVIDENCE_SCHEMAS[table, column], value)
    if (table, column) in _METADATA_SCHEMAS:
        _check_metadata(_METADATA_SCHEMAS[table, column], value)
    if (table, column) in _SCOPE_COLUMNS:
        validate_capture_shape(value)
    if (table, column) == ("source_inventory_assessments", "members_json"):
        for member in value:
            _identity("repository_uuidv4", member)
        if len(set(value)) != len(value):
            raise JsonContractError("Duplicate Source inventory member")
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
    if (table, column) == ("code_assessments", "details_json"):
        if value.keys() - {
            "race",
            "code_inputs_complete",
            "missing",
            "expected_roles",
            "api_head_base_stable",
            "missing_roles",
            "provider_limits",
            "merge",
        }:
            raise JsonContractError("Unknown code assessment evidence fields")
        if "race" in value and type(value["race"]) is not bool:
            raise JsonContractError("Code race evidence requires boolean")
        if "missing" in value:
            _check_metadata(_MISSING, value["missing"])
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
    if (table, column) == (
        "fetch_collections",
        "scope_json",
    ) and "request_context" in value:
        context = value["request_context"]
        if (
            not isinstance(context, dict)
            or "variables" in context
            and not isinstance(context["variables"], dict)
        ):
            raise JsonContractError(
                "Collection request context and variables require objects"
            )
    if column == "acquisition_scope_json":
        _acquisition_shape(
            value,
            data.get("service_instance_uuidv4")
            if check_owner
            else value.get("service_instance_uuidv4"),
        )
        if (
            check_owner
            and not _detached_acquisition(data, value)
            and any(
                value.get(name) != data.get(name)
                for name in ("repository_uuidv4", "repository_binding_id")
            )
        ):
            raise JsonContractError("Capture differs from typed owner")
        if (
            check_owner
            and table != "issue_resources"
            and value.get("change_request_id") != data.get("change_request_id")
        ):
            raise JsonContractError("Capture differs from typed parent")
        if table == "issue_resources" and "change_request_id" in value:
            raise JsonContractError("Ordinary Issue capture cannot claim PR")
    if table == "source_repositories" and column == "field_evidence_json":
        for encoded_path, evidence in value.items():
            try:
                path = json.loads(encoded_path)
            except (ValueError, TypeError):
                raise JsonContractError("Invalid Source field path") from None
            if (
                not isinstance(path, list)
                or not path
                or path[0] not in {"name", "metadata"}
                or any(not isinstance(part, str) for part in path)
                or (len(path) > 1 and path[0] != "metadata")
                or json.dumps(path, ensure_ascii=False, separators=(",", ":"))
                != encoded_path
                or not isinstance(evidence, dict)
                or evidence.keys() != _EVIDENCE_KEYS
            ):
                raise JsonContractError("Invalid Source field evidence")
            for name in ("observed_at_us", "parsed_at_us"):
                try:
                    validate_epoch_us(evidence[name])
                except (TypeError, ValueError) as error:
                    raise JsonContractError(
                        "Source capture requires actual timestamps"
                    ) from error
            if (
                evidence["provider_updated_at_us"] is not None
                or evidence["provider_clock_scope"] is not None
            ):
                raise JsonContractError(
                    "Source inventory has no comparable provider clock"
                )
            for name in ("parser_module", "parser_version"):
                _identity(name, evidence[name])
            scope = evidence["acquisition_scope"]
            if not isinstance(scope, dict) or "source_registration_uuidv4" not in scope:
                raise JsonContractError("Source capture requires typed Source identity")
            validate_capture_shape(scope)
            _walk(scope)
        return
    if column == "field_evidence_json":
        allowed = _allowed_fields(table)
        for encoded_path, evidence in value.items():
            try:
                path = json.loads(encoded_path)
            except (ValueError, TypeError):
                raise JsonContractError("Invalid field evidence path") from None
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
                raise JsonContractError("Invalid field evidence entry")
            if path[0] == "metadata":
                item = data.get("metadata", {})
                if isinstance(item, str):
                    item = _load(item, JsonSchema("provider"), "metadata")
                for depth, part in enumerate(path[1:], 1):
                    if (
                        json.dumps(
                            path[:depth], ensure_ascii=False, separators=(",", ":")
                        )
                        not in value
                        or not isinstance(item, dict)
                        or part not in item
                    ):
                        raise JsonContractError(
                            "Metadata evidence requires present value and ancestors"
                        )
                    item = item[part]
            elif path[0] == "body":
                if not {"body", "body_status", "text_body_sha256"} & data.keys():
                    raise JsonContractError("Evidence refers to absent body")
            elif path[0] not in data:
                raise JsonContractError("Evidence refers to absent value")
            for name in ("provider_updated_at_us", "observed_at_us", "parsed_at_us"):
                if evidence[name] is not None:
                    try:
                        validate_epoch_us(evidence[name])
                    except (ValueError, TypeError) as error:
                        raise JsonContractError(
                            "Evidence timestamp requires signed int64"
                        ) from error
            if evidence["observed_at_us"] is None or evidence["parsed_at_us"] is None:
                raise JsonContractError("Evidence needs capture times")
            if evidence["provider_clock_scope"] is not None and evidence[
                "provider_clock_scope"
            ] != _CLOCKS.get(data.get("kind")):
                raise JsonContractError("Invalid provider clock")
            if (
                data.get("kind") in {"review", "review-thread"}
                and evidence["provider_updated_at_us"] is not None
            ):
                raise JsonContractError("Resource has no verified update clock")
            for name in ("parser_module", "parser_version"):
                _identity(name, evidence[name])
            scope = evidence["acquisition_scope"]
            _acquisition_shape(
                scope,
                data.get("service_instance_uuidv4")
                if check_owner
                else scope.get("service_instance_uuidv4"),
            )
            if (
                check_owner
                and table != "issue_resources"
                and any(
                    scope.get(name) != data.get(name)
                    for name in (
                        "repository_uuidv4",
                        "repository_binding_id",
                        "change_request_id",
                    )
                )
            ):
                raise JsonContractError("Field capture differs from typed owner")
            if table == "issue_resources" and "change_request_id" in scope:
                raise JsonContractError("Ordinary Issue field capture cannot claim PR")
            if any(
                name in scope and scope[name] != evidence[name]
                for name in ("parser_module", "parser_version")
            ):
                raise JsonContractError("Producer differs from captured parser")
    if column == "members" and table == "current_collection_pages":
        _check_members(value)


_MEMBER_FIELDS = {
    "issue": (
        {
            "family",
            "service_instance_uuidv4",
            "kind",
            "provider_resource_id",
            "state_digest",
        },
        {"issue", "issue-comment"},
    ),
    "review": (
        {
            "family",
            "change_request_id",
            "kind",
            "provider_change_request_document_id",
            "state_digest",
        },
        {"review", "review-comment"},
    ),
    "document": (
        {
            "family",
            "change_request_id",
            "kind",
            "provider_change_request_document_id",
            "state_digest",
        },
        {"pr-title", "pr-body", "issue-comment"},
    ),
    "change-request": ({"family", "change_request_id", "state_digest"}, None),
    "thread": (
        {"family", "change_request_id", "provider_resource_id", "state_digest"},
        None,
    ),
    "code-commit": ({"family", "code_listing_id", "position", "state_digest"}, None),
    "code-file": ({"family", "code_listing_id", "position", "state_digest"}, None),
    "event": (
        {"family", "change_request_id", "change_request_event_uuidv4", "state_digest"},
        None,
    ),
}


def _check_members(value):
    seen = set()
    for member in value:
        if not isinstance(member, dict) or member.get("family") not in _MEMBER_FIELDS:
            raise JsonContractError("Unknown typed member family")
        fields, kinds = _MEMBER_FIELDS[member["family"]]
        if (
            member.keys() != fields
            or kinds is not None
            and member.get("kind") not in kinds
        ):
            raise JsonContractError("Typed member has wrong fields or kind")
        if not isinstance(member["state_digest"], str) or not SHA.fullmatch(
            member["state_digest"]
        ):
            raise JsonContractError("Member needs canonical SHA256")
        for name, item in member.items():
            if name in {"provider_resource_id", "provider_change_request_document_id"}:
                if (
                    not isinstance(item, str)
                    or not item
                    or (
                        member["family"] != "thread"
                        and not (
                            re.fullmatch(r"[0-9]+", item) and item.strip("0")
                            if member["family"] == "document"
                            else re.fullmatch(r"[1-9][0-9]*", item)
                        )
                    )
                ):
                    raise JsonContractError("Invalid provider identity")
            elif name == "position" and (type(item) is not int or item < 0):
                raise JsonContractError("Invalid entry position")
            elif name in REFERENCE_TARGETS or name == "change_request_event_uuidv4":
                _identity(name, item)
        key = json.dumps(
            {name: item for name, item in member.items() if name != "state_digest"},
            sort_keys=True,
        )
        if key in seen:
            raise JsonContractError("Duplicate typed member identity")
        seen.add(key)


def validate_field_evidence(db, evidence, candidate):
    if not isinstance(evidence, dict):
        raise JsonContractError("Field evidence requires object")
    _check_schema(
        _evidence_table(candidate), "field_evidence_json", evidence, candidate
    )
    pending = []
    seen = set()
    for entry in evidence.values():
        scope = entry["acquisition_scope"]
        token = json.dumps(scope, sort_keys=True)
        if token not in seen:
            seen.add(token)
            pending.extend(
                validate_acquisition_scope(
                    db,
                    scope,
                    service_instance_uuidv4=candidate["service_instance_uuidv4"],
                    allow_snapshot=True,
                )
            )
    return pending


def reference_dependencies(table, data):
    result = []
    for (owner, column), schema in JSON_REGISTRY.items():
        if owner != table or column not in data or data[column] is None:
            continue
        value = _load(data[column], schema, table + "." + column)
        _check_schema(table, column, value, data)
        if schema.category in {
            "authored",
            "git-roots",
            "current-members",
            "inventory-members",
        }:
            result.extend(_walk(value))
    return list(
        {
            (item["table"], item["columns"], item["values"]): item for item in result
        }.values()
    )


def validate_record(db, table, data, *, allow_missing=False):
    missing = []
    for dependency in reference_dependencies(table, data):
        if (
            _row(db, dependency["table"], dependency["columns"], dependency["values"])
            is None
        ):
            missing.append(dependency)
    if table == "source_inventory_assessments":
        owner = _row(db, "sources", ("source_id",), (data["source_id"],))
        scope = _load(data["scope_json"], JsonSchema("authored"), "Source scope")
        if (
            owner is None
            or scope.get("source_registration_uuidv4")
            != owner["source_registration_uuidv4"]
            or (
                owner["service_instance_uuidv4"] is not None
                and scope.get("service_instance_uuidv4")
                != owner["service_instance_uuidv4"]
            )
        ):
            raise JsonContractError(
                "Source inventory scope differs from registered Source"
            )
        if data["state"] == "complete":
            if data["terminal"] != 1:
                raise JsonContractError(
                    "Complete inventory requires observed termination"
                )
        members = _load(
            data["members_json"],
            JsonSchema("inventory-members", "array"),
            "Source members",
        )
        for member in members:
            if (
                _row(
                    db,
                    "source_repositories",
                    ("source_id", "repository_uuidv4"),
                    (data["source_id"], member),
                )
                is None
            ):
                raise JsonContractError(
                    "Inventory member lacks its known positive Source pair"
                )
    if (
        table == "current_collection_pages"
        and "fetch_collection_id" in data
        and "members" in data
    ):
        collection = _row(
            db,
            "fetch_collections",
            ("fetch_collection_id",),
            (data["fetch_collection_id"],),
        )
        if collection:
            scope = json.loads(collection["scope_json"])
            if collection["change_request_id"] is not None:
                owner = _row(
                    db,
                    "change_requests",
                    ("change_request_id",),
                    (collection["change_request_id"],),
                )
                if owner:
                    scope.setdefault(
                        "repository_binding_id", owner["repository_binding_id"]
                    )
                    binding = _row(
                        db,
                        "repository_bindings",
                        ("repository_binding_id",),
                        (owner["repository_binding_id"],),
                    )
                    if binding:
                        scope.setdefault(
                            "service_instance_uuidv4",
                            binding["service_instance_uuidv4"],
                        )
            members = _load(
                data["members"], JsonSchema("current-members", "array"), "members"
            )
            for member in members:
                if member["family"] == "issue":
                    if member["service_instance_uuidv4"] != scope.get(
                        "service_instance_uuidv4"
                    ):
                        raise JsonContractError(
                            "Member belongs to a different collection service"
                        )
                    continue
                if member["family"] in {"code-commit", "code-file"}:
                    listing = _row(
                        db,
                        "code_listings",
                        ("code_listing_id",),
                        (member["code_listing_id"],),
                    )
                    parent = listing.get("change_request_id") if listing else None
                else:
                    parent = member["change_request_id"]
                resource = (
                    _row(db, "change_requests", ("change_request_id",), (parent,))
                    if parent
                    else None
                )
                if resource is None:
                    missing.append(
                        {
                            "table": "change_requests",
                            "columns": ("change_request_id",),
                            "values": (parent,),
                        }
                    )
                elif (
                    resource["repository_uuidv4"] != collection["repository_uuidv4"]
                    or resource["repository_binding_id"]
                    != scope.get("repository_binding_id")
                    or collection["change_request_id"] is not None
                    and parent != collection["change_request_id"]
                ):
                    raise JsonContractError(
                        "Member differs from exact collection parent or binding"
                    )
    if table in {
        "issue_resources",
        "review_resources",
        "change_request_state",
        "document_state",
        "review_thread_state",
    }:
        if "acquisition_scope_json" in data:
            scope = _load(
                data["acquisition_scope_json"],
                JsonSchema("current-acquisition"),
                "capture",
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
        if "field_evidence_json" in data:
            missing.extend(
                validate_field_evidence(
                    db,
                    _load(
                        data["field_evidence_json"],
                        JsonSchema("current-field-evidence"),
                        "evidence",
                    ),
                    data,
                )
            )
    if missing and not allow_missing:
        raise MissingJsonDependencies(missing)
    return missing


def validate_catalog(db):
    fields = inventory(db)
    checked = 0
    for table in sorted({field["table"] for field in fields}):
        cur = db.execute("SELECT * FROM " + table)
        columns = [column[0] for column in cur.description]
        for row in cur:
            validate_record(db, table, dict(zip(columns, row, strict=True)))
            checked += 1
    return {"json_columns": len(fields), "records_checked": checked}


def guard_sql():
    """Generate standalone constraints from the same closed vocabulary."""
    output = ["-- Generated from json_contracts.JSON_REGISTRY.\n"]
    for (table, column), schema in sorted(JSON_REGISTRY.items()):
        doc = "NEW." + column
        conditions = [
            f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE typeof(j.key)='text' GROUP BY j.parent,j.key HAVING count(*)>1)"
        ]
        if (table, column) in _METADATA_SCHEMAS:
            conditions.append(
                _metadata_conditions(
                    _METADATA_SCHEMAS[table, column], doc, f"json_type({doc})"
                )
            )
        if (table, column) in _EVIDENCE_SCHEMAS:
            conditions.append(
                _metadata_conditions(
                    _EVIDENCE_SCHEMAS[table, column], doc, f"json_type({doc})"
                )
            )
        if table == "exchange_staging" and column == "record_json":
            conditions.extend(_staging_conditions(doc))
        if (table, column) in _SCOPE_COLUMNS:
            conditions.extend(_sql_scope_conditions(doc))
        if (table, column) == ("source_inventory_assessments", "scope_json"):
            conditions += [
                f"NOT EXISTS(SELECT 1 FROM sources s WHERE s.source_id=NEW.source_id AND s.source_registration_uuidv4=json_extract({doc},'$.source_registration_uuidv4') AND (s.service_instance_uuidv4 IS NULL OR s.service_instance_uuidv4=json_extract({doc},'$.service_instance_uuidv4')))",
                "(NEW.state='complete' AND NEW.terminal<>1)",
            ]
        if schema.category == "inventory-members":
            conditions += [
                f"EXISTS(SELECT 1 FROM json_each({doc}) m WHERE m.type<>'text' OR NOT {_sql_uuid('m.value')} OR NOT EXISTS(SELECT 1 FROM source_repositories r WHERE r.source_id=NEW.source_id AND r.repository_uuidv4=m.value))",
                f"EXISTS(SELECT 1 FROM json_each({doc}) m GROUP BY m.value HAVING count(*)>1)",
            ]
        if schema.category == "current-acquisition":
            conditions += _sql_capture_conditions(doc, "NEW.service_instance_uuidv4")
            conditions.append(
                f"json_extract({doc},'$.change_request_id') IS NOT NEW.change_request_id"
                if table != "issue_resources"
                else f"json_type({doc},'$.change_request_id') IS NOT NULL"
            )
        elif (
            schema.category == "current-field-evidence"
            and table != "source_repositories"
        ):
            fields = ",".join(
                "'" + name + "'" for name in sorted(_allowed_fields(table))
            )
            keys = ",".join("'" + name + "'" for name in sorted(_EVIDENCE_KEYS))
            conditions = [
                f"EXISTS(SELECT 1 FROM json_each({doc}) e GROUP BY e.key HAVING count(*)>1)"
            ]
            conditions += [
                f"EXISTS(SELECT 1 FROM json_each({doc}) e WHERE CASE WHEN NOT json_valid(e.key) THEN 1 WHEN json_type(e.key)<>'array' THEN 1 ELSE (json_array_length(e.key)=0 OR (SELECT json_group_array(p.value) FROM json_each(e.key) p)<>e.key OR EXISTS(SELECT 1 FROM json_each(e.key) p WHERE p.type<>'text') OR json_extract(e.key,'$[0]') NOT IN ({fields}) OR (json_array_length(e.key)>1 AND json_extract(e.key,'$[0]')<>'metadata')) END)",
                f"EXISTS(WITH RECURSIVE paths(path,value,type) AS (SELECT json_array('metadata'),NEW.metadata,'object' UNION ALL SELECT json_insert(p.path,'$[#]',j.key),j.value,j.type FROM paths p JOIN json_each(CASE WHEN p.type='object' THEN p.value ELSE '{{}}' END) j WHERE p.type='object') SELECT 1 FROM json_each({doc}) e WHERE json_extract(e.key,'$[0]')='metadata' AND NOT EXISTS(SELECT 1 FROM paths p WHERE p.path=e.key))",
                f"EXISTS(SELECT 1 FROM json_each({doc}) e JOIN json_each(e.key) depth WHERE json_extract(e.key,'$[0]')='metadata' AND CAST(depth.key AS INTEGER)>0 AND NOT EXISTS(SELECT 1 FROM json_each({doc}) a WHERE a.key=(SELECT json_group_array(p.value) FROM json_each(e.key) p WHERE CAST(p.key AS INTEGER)<CAST(depth.key AS INTEGER))))",
            ]
            invalid = [
                f"(SELECT count(*) FROM json_each(e.value))<>{len(_EVIDENCE_KEYS)}",
                f"EXISTS(SELECT 1 FROM json_each(e.value) p WHERE p.key NOT IN ({keys}))",
                "coalesce(json_type(e.value,'$.observed_at_us'),'')<>'integer' OR typeof(json_extract(e.value,'$.observed_at_us'))<>'integer'",
                "coalesce(json_type(e.value,'$.parsed_at_us'),'')<>'integer' OR typeof(json_extract(e.value,'$.parsed_at_us'))<>'integer'",
                "coalesce(json_type(e.value,'$.provider_updated_at_us'),'') NOT IN ('integer','null')",
                "(json_type(e.value,'$.provider_updated_at_us')='integer' AND typeof(json_extract(e.value,'$.provider_updated_at_us'))<>'integer')",
                "coalesce(json_type(e.value,'$.provider_clock_scope'),'') NOT IN ('text','null')",
                "(json_type(e.value,'$.provider_clock_scope')='text' AND json_extract(e.value,'$.provider_clock_scope') IS NOT CASE NEW.kind WHEN 'issue' THEN 'github-issue-updated-at' WHEN 'issue-comment' THEN 'github-issue-comment-updated-at' WHEN 'review-comment' THEN 'github-review-comment-updated-at' WHEN 'change-request' THEN 'github-pr-updated-at' WHEN 'pr-title' THEN 'github-pr-updated-at' WHEN 'pr-body' THEN 'github-pr-updated-at' END)",
                "(NEW.kind IN ('review','review-thread') AND json_type(e.value,'$.provider_updated_at_us')<>'null')",
                *[
                    f"coalesce(json_type(e.value,'$.{name}'),'')<>'text' OR length(json_extract(e.value,'$.{name}'))=0 OR instr(json_extract(e.value,'$.{name}'),char(0))>0"
                    for name in ("parser_module", "parser_version")
                ],
                "coalesce(json_type(e.value,'$.acquisition_scope'),'')<>'object'",
            ]
            capture = _sql_capture_conditions(
                "capture.scope", "NEW.service_instance_uuidv4"
            )
            if table != "issue_resources":
                capture += [
                    f"json_extract(capture.scope,'$.{name}') IS NOT NEW.{name}"
                    for name in (
                        "repository_uuidv4",
                        "repository_binding_id",
                        "change_request_id",
                    )
                ]
            else:
                capture.append(
                    "json_type(capture.scope,'$.change_request_id') IS NOT NULL"
                )
            conditions.append(
                f"EXISTS(SELECT 1 FROM (SELECT DISTINCT json_extract(e.value,'$.acquisition_scope') AS scope FROM json_each({doc}) e) capture WHERE "
                + " OR ".join(capture)
                + ")"
            )
            invalid += [
                f"(json_type(e.value,'$.acquisition_scope.{name}') IS NOT NULL AND json_extract(e.value,'$.acquisition_scope.{name}') IS NOT json_extract(e.value,'$.{name}'))"
                for name in ("parser_module", "parser_version")
            ]
            conditions.append(
                f"EXISTS(SELECT 1 FROM json_each({doc}) e WHERE CASE WHEN e.type<>'object' THEN 1 ELSE ("
                + " OR ".join(invalid)
                + ") END)"
            )
        elif schema.category == "current-members":
            cases = []
            for family, (fields, kinds) in _MEMBER_FIELDS.items():
                names = ",".join("'" + name + "'" for name in sorted(fields))
                invalid = [
                    f"(SELECT count(*) FROM json_each(m.value))<>{len(fields)}",
                    f"EXISTS(SELECT 1 FROM json_each(m.value) p WHERE p.key NOT IN ({names}))",
                ]
                if kinds:
                    invalid.append(
                        "json_extract(m.value,'$.kind') NOT IN ("
                        + ",".join("'" + kind + "'" for kind in sorted(kinds))
                        + ")"
                    )
                for name in sorted(
                    fields - {"family", "kind", "state_digest", "position"}
                ):
                    invalid.append(
                        f"coalesce(json_type(m.value,'$.{name}'),'')<>'text' OR length(json_extract(m.value,'$.{name}'))=0"
                    )
                if "position" in fields:
                    invalid.append(
                        "coalesce(json_type(m.value,'$.position'),'')<>'integer' OR typeof(json_extract(m.value,'$.position'))<>'integer' OR json_extract(m.value,'$.position')<0"
                    )
                cases.append(f"WHEN '{family}' THEN (" + " OR ".join(invalid) + ")")
            conditions.append(
                f"EXISTS(SELECT 1 FROM json_each({doc}) m WHERE CASE WHEN m.type<>'object' THEN 1 ELSE (CASE json_extract(m.value,'$.family') "
                + " ".join(cases)
                + " ELSE 1 END OR coalesce(json_type(m.value,'$.state_digest'),'')<>'text' OR length(json_extract(m.value,'$.state_digest'))<>64 OR json_extract(m.value,'$.state_digest') GLOB '*[^0-9a-f]*') END)"
            )
            conditions.append(
                f"EXISTS(SELECT 1 FROM json_each({doc}) m JOIN fetch_collections c ON c.fetch_collection_id=NEW.fetch_collection_id WHERE (json_extract(m.value,'$.family')='issue' AND json_extract(m.value,'$.service_instance_uuidv4') IS NOT coalesce(json_extract(c.scope_json,'$.service_instance_uuidv4'),(SELECT b.service_instance_uuidv4 FROM change_requests r JOIN repository_bindings b USING(repository_binding_id) WHERE r.change_request_id=c.change_request_id))) OR (json_extract(m.value,'$.family') IN ('review','document','thread','change-request','event') AND NOT EXISTS(SELECT 1 FROM change_requests r WHERE r.change_request_id=json_extract(m.value,'$.change_request_id') AND r.repository_uuidv4=c.repository_uuidv4 AND r.repository_binding_id=coalesce(json_extract(c.scope_json,'$.repository_binding_id'),(SELECT repository_binding_id FROM change_requests WHERE change_request_id=c.change_request_id)) AND (c.change_request_id IS NULL OR c.change_request_id=r.change_request_id))) OR (json_extract(m.value,'$.family') IN ('code-commit','code-file') AND NOT EXISTS(SELECT 1 FROM code_listings l JOIN change_requests r USING(change_request_id) WHERE l.code_listing_id=json_extract(m.value,'$.code_listing_id') AND r.repository_uuidv4=c.repository_uuidv4 AND r.repository_binding_id=coalesce(json_extract(c.scope_json,'$.repository_binding_id'),(SELECT repository_binding_id FROM change_requests WHERE change_request_id=c.change_request_id)) AND (c.change_request_id IS NULL OR c.change_request_id=r.change_request_id))))"
            )
            ident = "coalesce(json_extract(m.value,'$.provider_change_request_document_id'),json_extract(m.value,'$.provider_resource_id'))"
            conditions.append(
                f"EXISTS(SELECT 1 FROM json_each({doc}) m WHERE json_extract(m.value,'$.family') IN ('issue','review','document') AND (typeof({ident})<>'text' OR length(CAST({ident} AS BLOB))<>length({ident}) OR instr({ident},char(0))>0 OR length({ident})=0 OR {ident} GLOB '*[^0-9]*' OR CASE WHEN json_extract(m.value,'$.family')='document' THEN length(ltrim({ident},'0'))=0 ELSE substr({ident},1,1) NOT BETWEEN '1' AND '9' END))"
            )
            conditions.append(
                f"EXISTS(SELECT 1 FROM json_each({doc}) m GROUP BY json_extract(m.value,'$.family'),coalesce(json_extract(m.value,'$.service_instance_uuidv4'),json_extract(m.value,'$.change_request_id'),json_extract(m.value,'$.code_listing_id')),json_extract(m.value,'$.kind'),coalesce(json_extract(m.value,'$.provider_resource_id'),json_extract(m.value,'$.provider_change_request_document_id'),json_extract(m.value,'$.position'),json_extract(m.value,'$.change_request_event_uuidv4')) HAVING count(*)>1)"
            )
        elif schema.category in {"authored", "git-roots", "inventory-members"}:
            forbidden = ",".join(
                "'" + key + "'"
                for key in sorted(
                    _CURRENT_FORBIDDEN_REFERENCE_KEYS | LOCAL_REFERENCE_KEYS
                )
            )
            conditions.append(
                f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE j.key IN ({forbidden}))"
            )
            known = ",".join(
                "'" + key + "'"
                for key in sorted(set(REFERENCE_TARGETS) | set(REFERENCE_LISTS))
            )
            conditions.append(
                f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE (j.key GLOB '*_uuidv4' OR j.key GLOB '*_uuidv4s') AND j.key NOT IN ({known}))"
            )
            # Stable typed references, never arbitrary sender requires hints.
            for key, (target, identity) in REFERENCE_TARGETS.items():
                canonical = (
                    _sql_uuid("j.value")
                    if "uuidv4" in key
                    else "(length(j.value)>0 AND instr(j.value,char(0))=0)"
                )
                conditions.append(
                    f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE j.key='{key}' AND j.type<>'null' AND (j.type<>'text' OR NOT {canonical} OR NOT EXISTS(SELECT 1 FROM {target} t WHERE t.{identity}=j.value)))"
                )
        if (table, column) == ("fetch_collections", "scope_json"):
            conditions.append(
                f"(json_type({doc},'$.request_context') IS NOT NULL AND json_type({doc},'$.request_context')<>'object') OR (json_type({doc},'$.request_context.variables') IS NOT NULL AND json_type({doc},'$.request_context.variables')<>'object')"
            )
        if (table, column) == ("source_repositories", "field_evidence_json"):
            conditions.extend(_source_evidence_conditions(doc))
        conditions.extend(_special_conditions(table, column, doc))
        for operation in ("INSERT", "UPDATE"):
            output.append(
                f"CREATE TRIGGER json_{table}_{column}_{operation.lower()} BEFORE {operation} ON {table}\nWHEN {doc} IS NOT NULL AND CASE WHEN NOT json_valid({doc}) THEN 1 WHEN json_type({doc})<>'{schema.shape}' THEN 1 ELSE (\n"
                + "\n OR ".join(conditions)
                + f"\n) END BEGIN SELECT RAISE(ABORT,'JSON contract violation: {table}.{column}'); END;\n"
            )
    output.append(_staging_guard_sql())
    return "".join(output)


# Named metadata keeps observable domain attributes with a closed inner
# vocabulary. Scalar slots cannot conceal an object or response envelope.
_TEXT = {"string"}
_NUMBER = {"integer"}
_FLAG = {"boolean"}
_MISSING = [{"kind": _TEXT, "reason": _TEXT, "role": _TEXT, "roles": [_TEXT]}]
_EVIDENCE_SCHEMAS = {
    ("coverage_claims", "details_json"): {
        "fetch_collection_ids": [_TEXT],
        "completion_marker_uuidv4s": [_TEXT],
        "code_assessment_ids": [_TEXT],
        "git_acquisition_id": _TEXT,
        "snapshot_id": _TEXT,
        "reason": _TEXT,
        "missing": _MISSING,
    },
}

# Captures describe a specific request/visibility/parent/target question. Every
# object slot has an interpreted shape; none is an extension/provider envelope.
_SCOPE_CONTEXT = {
    **{
        name: _TEXT
        for name in (
            "provider_repository_id",
            "provider_issue_id",
            "owner",
            "name",
            "kind",
            "state",
            "sort",
            "direction",
            "incremental_endpoint",
            "query_kind",
            "provider_resource_id",
            "parent_fetch_collection_id",
            "completion_marker_uuidv4",
            "object_format",
            "head_oid",
            "base_oid",
        )
    },
    **{
        name: _NUMBER
        for name in (
            "rest_page_size",
            "graphql_page_size",
            "number",
            "provider_issue_number",
            "reported_count",
            "parent_observed_at_us",
        )
    },
    "permissions": [_TEXT],
    "head": {"sha": _TEXT},
    "base": {"sha": _TEXT},
}
_CAPTURE_SCOPE = {
    **{
        name: _TEXT
        for name in (
            "repository_uuidv4",
            "repository_binding_id",
            "service_instance_uuidv4",
            "source_registration_uuidv4",
            "change_request_id",
            "endpoint",
            "principal_ref",
            "api_version",
            "preservation_profile",
            "parser_module",
            "parser_version",
            "owner",
            "visibility",
            "query_kind",
            "kind",
        )
    },
    "observed_permissions": [_TEXT],
    "selected_repositories": [_TEXT],
    "request_context": _SCOPE_CONTEXT,
}
_SCOPE_COLUMNS = {
    ("fetch_collections", "scope_json"),
    ("source_repositories", "scope_json"),
    ("source_inventory_assessments", "scope_json"),
}
_SCOPE_ENUMS = {
    "$.kind": {"manual_git"},
    "$.visibility": {"all", "public", "private", "internal"},
    "$.query_kind": {
        "owner-repositories",
        "selected-repositories",
        "organization-repositories",
        "verified-repository-redirect",
    },
    "$.request_context.query_kind": {"review-thread-root"},
    "$.request_context.object_format": {"sha1", "sha256"},
    "$.request_context.state": {"all", "open", "closed"},
    "$.request_context.sort": {"updated", "created"},
    "$.request_context.direction": {"asc", "desc"},
}


def validate_capture_shape(scope):
    if not isinstance(scope, dict):
        raise JsonContractError("Capture scope requires a modeled object")
    _check_metadata(_CAPTURE_SCOPE, scope)
    if "request_context" in scope and not isinstance(scope["request_context"], dict):
        raise JsonContractError("Request context requires a modeled object")
    _walk(scope)

    def visit(value):
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, str) and (not value or "\0" in value):
            raise JsonContractError(
                "Capture text requires a nonempty interpreted value"
            )
        elif type(value) is int:
            validate_epoch_us(value)

    visit(scope)
    for path, allowed in _SCOPE_ENUMS.items():
        value = scope
        for key in path[2:].split("."):
            value = value.get(key) if isinstance(value, dict) else None
        if value is not None and value not in allowed:
            raise JsonContractError("Unsupported capture query context")
    context = scope.get("request_context", {})
    for key in (
        "rest_page_size",
        "graphql_page_size",
        "number",
        "provider_issue_number",
    ):
        if context.get(key) is not None and context[key] <= 0:
            raise JsonContractError("Capture count requires a positive integer")
    if context.get("reported_count") is not None and context["reported_count"] < 0:
        raise JsonContractError("Reported count cannot be negative")
    for key in ("provider_repository_id", "provider_issue_id"):
        if context.get(key) is not None and not (
            re.fullmatch(r"[0-9]+", context[key]) and context[key].strip("0")
        ):
            raise JsonContractError(
                "Capture provider identity requires exact positive decimal text"
            )
    width = {"sha1": 40, "sha256": 64}.get(context.get("object_format"))
    for oid in [
        context.get("head_oid"),
        context.get("base_oid"),
        *[(context.get(role) or {}).get("sha") for role in ("head", "base")],
    ]:
        if oid is not None and (
            len(oid) not in ({width} if width else {40, 64})
            or re.fullmatch(r"[0-9a-f]+", oid) is None
        ):
            raise JsonContractError("Capture target requires a canonical Git OID")


def _sql_scope_conditions(doc):
    conditions = [
        _metadata_conditions(_CAPTURE_SCOPE, doc, f"json_type({doc})"),
        f"(json_type({doc},'$.request_context') IS NOT NULL AND json_type({doc},'$.request_context')<>'object')",
        f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE (j.type='text' AND (length(j.value)=0 OR instr(j.value,char(0))>0)) OR (j.type='integer' AND typeof(j.value)<>'integer'))",
    ]
    for path, values in _SCOPE_ENUMS.items():
        allowed = ",".join("'" + value + "'" for value in sorted(values))
        conditions.append(
            f"(json_type({doc},'{path}') NOT IN ('null') AND json_extract({doc},'{path}') NOT IN ({allowed}))"
        )
    for key in (
        "rest_page_size",
        "graphql_page_size",
        "number",
        "provider_issue_number",
    ):
        conditions.append(f"json_extract({doc},'$.request_context.{key}')<=0")
    conditions.append(f"json_extract({doc},'$.request_context.reported_count')<0")
    for key in ("provider_repository_id", "provider_issue_id"):
        value = f"json_extract({doc},'$.request_context.{key}')"
        conditions.append(
            f"(json_type({doc},'$.request_context.{key}')='text' AND ({value} GLOB '*[^0-9]*' OR length(ltrim({value},'0'))=0))"
        )
    for key in ("head_oid", "base_oid", "head.sha", "base.sha"):
        value = f"json_extract({doc},'$.request_context.{key}')"
        expected = f"CASE json_extract({doc},'$.request_context.object_format') WHEN 'sha1' THEN 40 WHEN 'sha256' THEN 64 ELSE length({value}) END"
        conditions.append(
            f"(json_type({doc},'$.request_context.{key}')='text' AND (length({value}) NOT IN (40,64) OR NOT {_sql_hex(value, expected)}))"
        )
    return conditions


_ACTOR = {"id": _NUMBER, "login": _TEXT, "type": _TEXT, "html_url": _TEXT}
_LABEL = {
    "id": _NUMBER,
    "name": _TEXT,
    "color": _TEXT,
    "description": _TEXT,
    "default": _FLAG,
}
_TEAM = {name: _TEXT for name in ("name", "slug", "description", "privacy", "html_url")}
_TEAM["id"] = _NUMBER
_MILESTONE = {
    name: _TEXT
    for name in (
        "title",
        "description",
        "state",
        "due_on",
        "created_at",
        "updated_at",
        "closed_at",
        "html_url",
    )
}
_MILESTONE.update(
    {name: _NUMBER for name in ("id", "number", "open_issues", "closed_issues")}
)
_MILESTONE["creator"] = _ACTOR
_REACTIONS = {
    name: _NUMBER
    for name in (
        "total_count",
        "+1",
        "-1",
        "laugh",
        "confused",
        "heart",
        "hooray",
        "eyes",
        "rocket",
    )
}
_SHARED_METADATA = {
    "labels": [_LABEL],
    "assignees": [_ACTOR],
    "requested_reviewers": [_ACTOR],
    "requested_teams": [_TEAM],
    "milestone": _MILESTONE,
    "reactions": _REACTIONS,
}
_PR_METADATA = {
    **_SHARED_METADATA,
    "node_id": _TEXT,
    **{
        name: _TEXT
        for name in ("author_association", "active_lock_reason", "mergeable_state")
    },
    **{name: _FLAG for name in ("mergeable", "rebaseable", "maintainer_can_modify")},
    **{
        name: _NUMBER
        for name in (
            "comments",
            "review_comments",
            "commits",
            "changed_files",
            "additions",
            "deletions",
        )
    },
    "merged_by": _ACTOR,
    "auto_merge": {
        "merge_method": _TEXT,
        "commit_title": _TEXT,
        "commit_message": _TEXT,
        "enabled_by": _ACTOR,
    },
}
_TARGET = {
    "label": _TEXT,
    "user": _ACTOR,
    "repository": {
        "id": _NUMBER,
        "name": _TEXT,
        "full_name": _TEXT,
        "html_url": _TEXT,
        "private": _FLAG,
        "default_branch": _TEXT,
    },
}
_PR_METADATA["targets"] = {"head": _TARGET, "base": _TARGET}
_REPOSITORY_METADATA = {
    name: _TEXT
    for name in (
        "name",
        "full_name",
        "html_url",
        "ssh_url",
        "git_url",
        "visibility",
        "default_branch",
        "description",
        "homepage",
        "language",
        "created_at",
        "updated_at",
        "pushed_at",
    )
}
_REPOSITORY_METADATA.update(
    {
        name: _FLAG
        for name in (
            "private",
            "archived",
            "disabled",
            "fork",
            "has_issues",
            "has_projects",
            "has_wiki",
            "has_pages",
            "has_downloads",
            "has_discussions",
            "allow_forking",
            "is_template",
        )
    }
)
_REPOSITORY_METADATA.update(
    {
        name: _NUMBER
        for name in (
            "size",
            "stargazers_count",
            "watchers_count",
            "forks_count",
            "open_issues_count",
        )
    }
)
_REPOSITORY_METADATA.update(
    {
        "topics": [_TEXT],
        "owner": _ACTOR,
        "parent": {"id": _NUMBER, "full_name": _TEXT, "html_url": _TEXT},
        "source": {"id": _NUMBER, "full_name": _TEXT, "html_url": _TEXT},
        "license": {"key": _TEXT, "name": _TEXT, "spdx_id": _TEXT},
        "permissions": {
            name: _FLAG for name in ("admin", "maintain", "push", "triage", "pull")
        },
        "security_and_analysis": {
            name: {"status": _TEXT}
            for name in (
                "advanced_security",
                "secret_scanning",
                "secret_scanning_push_protection",
                "dependabot_security_updates",
            )
        },
    }
)
_EVENT_METADATA = {
    **_SHARED_METADATA,
    **{
        name: _TEXT
        for name in (
            "event",
            "created_at",
            "submitted_at",
            "state",
            "message",
            "author_association",
            "commit_id",
            "before",
            "after",
            "lock_reason",
        )
    },
    **{name: _ACTOR for name in ("actor", "user", "assignee", "assigner", "reviewer")},
    "label": _LABEL,
    "rename": {"from": _TEXT, "to": _TEXT},
    "requested_team": {"id": _NUMBER, "name": _TEXT, "slug": _TEXT},
    "id": _NUMBER,
    "pull_request_review_id": _NUMBER,
    "dismissed_review": {
        "state": _TEXT,
        "review_id": _NUMBER,
        "dismissal_message": _TEXT,
        "dismissal_commit_id": _TEXT,
    },
}
_CODE_COMMIT_METADATA = {
    "html_url": _TEXT,
    "author": _ACTOR,
    "committer": _ACTOR,
    "commit": {
        "message": _TEXT,
        "author": {"name": _TEXT, "email": _TEXT, "date": _TEXT},
        "committer": {"name": _TEXT, "email": _TEXT, "date": _TEXT},
        "tree": {"sha": _TEXT},
        "verification": {
            "verified": _FLAG,
            "reason": _TEXT,
            "signature": _TEXT,
            "payload": _TEXT,
            "verified_at": _TEXT,
        },
    },
    "parents": [{"sha": _TEXT}],
}
_METADATA_SCHEMAS = {
    ("issue_resources", "metadata"): {
        **_SHARED_METADATA,
        **{
            name: _TEXT
            for name in (
                "state_reason",
                "created_at",
                "closed_at",
                "active_lock_reason",
            )
        },
        "locked": _FLAG,
        "comments": _NUMBER,
    },
    ("review_resources", "metadata"): {
        "node_id": _TEXT,
        "_links": {name: {"href": _TEXT} for name in ("self", "html", "pull_request")},
        **{
            name: _TEXT for name in ("side", "start_side", "subject_type", "created_at")
        },
        **{
            name: _NUMBER
            for name in ("line", "original_line", "start_line", "original_start_line")
        },
    },
    ("change_request_state", "metadata"): _PR_METADATA,
    ("document_state", "metadata"): {
        **_SHARED_METADATA,
        "created_at": _TEXT,
        "author_association": _TEXT,
        "node_id": _TEXT,
    },
    ("review_thread_state", "metadata"): {},
    ("source_repositories", "metadata_json"): _REPOSITORY_METADATA,
    ("code_commits", "metadata"): _CODE_COMMIT_METADATA,
    ("code_file_changes", "metadata"): {
        name: _TEXT for name in ("blob_url", "raw_url", "contents_url")
    },
    ("change_request_events", "metadata"): _EVENT_METADATA,
}


def _check_metadata(spec, value):
    if value is None:
        return
    if isinstance(spec, dict):
        if not isinstance(value, dict) or value.keys() - spec.keys():
            raise JsonContractError("Unknown or malformed modeled domain metadata")
        for name, item in value.items():
            _check_metadata(spec[name], item)
    elif isinstance(spec, list):
        if not isinstance(value, list):
            raise JsonContractError("Modeled membership field requires array")
        for item in value:
            _check_metadata(spec[0], item)
    else:
        kind = (
            "boolean"
            if type(value) is bool
            else "integer"
            if type(value) is int
            else "string"
            if isinstance(value, str)
            else "number"
            if isinstance(value, float)
            else None
        )
        if kind not in spec:
            raise JsonContractError("Modeled domain metadata has wrong scalar type")


def _metadata_conditions(spec, doc, type_expr):
    """Flat tree predicates preserve the modeled shape on bounded SQLite parsers.

    Each modeled path has an independent check. Arrays match exactly the number
    of index segments, so an array wildcard cannot also consume descendants.
    Neither provider object depth nor model depth nests generated SQL queries.
    """
    types = {
        "string": {"text"},
        "integer": {"integer"},
        "boolean": {"true", "false"},
        "number": {"integer", "real"},
    }

    def allowed(item):
        if isinstance(item, dict):
            return {"null", "object"}
        if isinstance(item, list):
            return {"null", "array"}
        return {"null"} | {name for kind in item for name in types[kind]}

    def quoted(values):
        return ",".join("'" + value + "'" for value in sorted(values))

    root = f"{type_expr} NOT IN ({quoted(allowed(spec))})"
    if not isinstance(spec, (dict, list)):
        return root
    pending = [("$", 0, spec)]
    checks = []
    while pending:
        path, arrays, item = pending.pop()
        match = (
            "md_node.fullkey=" + repr(path)
            if not arrays
            else "md_node.fullkey GLOB "
            + repr(path)
            + f" AND length(md_node.fullkey)-length(replace(md_node.fullkey,'[',''))={arrays}"
        )
        invalid = [f"md_node.type NOT IN ({quoted(allowed(item))})"]
        if isinstance(item, dict):
            names = quoted(item) or "''"
            invalid.append(
                "(md_node.type='object' AND EXISTS(SELECT 1 FROM "
                "json_each(CASE WHEN md_node.type='object' THEN md_node.value ELSE '{}' END) "
                f"md_child WHERE md_child.key NOT IN ({names})))"
            )
            for name, child in sorted(item.items()):
                label = (
                    name
                    if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", name)
                    else json.dumps(name)
                )
                pending.append((path + "." + label, arrays, child))
        elif isinstance(item, list):
            pending.append((path + "[[]*[]]", arrays + 1, item[0]))
        checks.append("(" + match + " AND (" + " OR ".join(invalid) + "))")
    tree = f"CASE WHEN {type_expr} IN ('object','array') THEN {doc} ELSE 'null' END"
    return (
        "("
        + root
        + f" OR EXISTS(SELECT 1 FROM json_tree({tree}) md_node WHERE "
        + " OR ".join(checks)
        + "))"
    )


def _special_conditions(table, column, doc):
    conditions = []
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
    if (table, column) == ("code_assessments", "details_json"):
        conditions += [
            f"EXISTS(SELECT 1 FROM json_each({doc}) e WHERE e.key NOT IN ('race','code_inputs_complete','missing','expected_roles','api_head_base_stable','missing_roles','provider_limits','merge'))",
            f"(json_type({doc},'$.race') IS NOT NULL AND json_type({doc},'$.race') NOT IN ('true','false'))",
            _metadata_conditions(
                _MISSING,
                f"json_extract({doc},'$.missing')",
                f"json_type({doc},'$.missing')",
            ),
        ]
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
    return conditions


def _sql_code_role(role, oid_width):
    suffix = _sql_hex(f"substr({role},15)", oid_width)
    return f"({role} IN ('head','base','merge','test-merge') OR (substr({role},1,14)='review-target:' AND {suffix}))"


def _source_evidence_conditions(doc):
    keys = ",".join("'" + name + "'" for name in sorted(_EVIDENCE_KEYS))
    forbidden = ",".join(
        "'" + key + "'"
        for key in sorted(_CURRENT_FORBIDDEN_REFERENCE_KEYS | LOCAL_REFERENCE_KEYS)
    )
    invalid = [
        *_sql_scope_conditions("json_extract(e.value,'$.acquisition_scope')"),
        f"(SELECT count(*) FROM json_each(e.value))<>{len(_EVIDENCE_KEYS)}",
        f"EXISTS(SELECT 1 FROM json_each(e.value) p WHERE p.key NOT IN ({keys}))",
        "coalesce(json_type(e.value,'$.provider_updated_at_us'),'')<>'null' OR coalesce(json_type(e.value,'$.provider_clock_scope'),'')<>'null'",
        "coalesce(json_type(e.value,'$.observed_at_us'),'')<>'integer' OR typeof(json_extract(e.value,'$.observed_at_us'))<>'integer'",
        "coalesce(json_type(e.value,'$.parsed_at_us'),'')<>'integer' OR typeof(json_extract(e.value,'$.parsed_at_us'))<>'integer'",
        *[
            f"coalesce(json_type(e.value,'$.{name}'),'')<>'text' OR length(json_extract(e.value,'$.{name}'))=0 OR instr(json_extract(e.value,'$.{name}'),char(0))>0"
            for name in ("parser_module", "parser_version")
        ],
        "coalesce(json_type(e.value,'$.acquisition_scope'),'')<>'object'",
        "NOT EXISTS(SELECT 1 FROM sources s WHERE s.source_id=NEW.source_id AND s.source_registration_uuidv4=json_extract(e.value,'$.acquisition_scope.source_registration_uuidv4') AND (s.service_instance_uuidv4 IS NULL OR s.service_instance_uuidv4=json_extract(e.value,'$.acquisition_scope.service_instance_uuidv4')))",
        f"EXISTS(SELECT 1 FROM json_tree(e.value,'$.acquisition_scope') j WHERE j.key IN ({forbidden}))",
    ]
    return [
        f"EXISTS(SELECT 1 FROM json_each({doc}) e WHERE CASE WHEN NOT json_valid(e.key) THEN 1 WHEN json_type(e.key)<>'array' THEN 1 ELSE (json_array_length(e.key)=0 OR (SELECT json_group_array(p.value) FROM json_each(e.key) p)<>e.key OR json_extract(e.key,'$[0]') NOT IN ('name','metadata') OR (json_array_length(e.key)>1 AND json_extract(e.key,'$[0]')<>'metadata') OR EXISTS(SELECT 1 FROM json_each(e.key) p WHERE p.type<>'text')) END)",
        f"EXISTS(SELECT 1 FROM json_each({doc}) e WHERE CASE WHEN e.type<>'object' THEN 1 ELSE ("
        + " OR ".join(invalid)
        + ") END)",
        f"EXISTS(WITH RECURSIVE paths(path,value,type) AS (SELECT json_array('metadata'),NEW.metadata_json,'object' UNION ALL SELECT json_insert(p.path,'$[#]',j.key),j.value,j.type FROM paths p JOIN json_each(CASE WHEN p.type='object' THEN p.value ELSE '{{}}' END) j WHERE p.type='object') SELECT 1 FROM json_each({doc}) e WHERE json_extract(e.key,'$[0]')='metadata' AND NOT EXISTS(SELECT 1 FROM paths p WHERE p.path=e.key))",
        f"EXISTS(SELECT 1 FROM json_each({doc}) e JOIN json_each(e.key) depth WHERE json_extract(e.key,'$[0]')='metadata' AND CAST(depth.key AS INTEGER)>0 AND NOT EXISTS(SELECT 1 FROM json_each({doc}) a WHERE a.key=(SELECT json_group_array(p.value) FROM json_each(e.key) p WHERE CAST(p.key AS INTEGER)<CAST(depth.key AS INTEGER))))",
    ]


@lru_cache(maxsize=1)
def _wire_graph():
    """Read the composed domain table contract without requiring any parents."""
    import sqlite3

    from .exchange import Graph
    from .schema import schema_sql

    db = sqlite3.connect(":memory:")
    db.executescript(schema_sql())
    return Graph(db, persist_identities=False)


def _candidate_spec(table):
    from .current_api import _CONTEXT, _FIELDS
    from .current_resources import _COMMON, _ISSUE, _REVIEW

    if table == "issue_resources":
        fields = _COMMON | _ISSUE
    elif table == "review_resources":
        fields = (_COMMON | _REVIEW) - {"title"}
    elif table == "source_repositories":
        fields = {
            "kind",
            "source_id",
            "repository_uuidv4",
            "first_seen_us",
            "last_seen_us",
            "name",
            "metadata",
            "acquisition_scope",
            "field_evidence",
            "parser_module",
            "parser_version",
            "observed_at_us",
            "parsed_at_us",
            "provider_updated_at_us",
            "provider_clock_scope",
        }
    else:
        fields = _CONTEXT | _FIELDS[table]
    spec = {name: _TEXT for name in fields - {"field_evidence"}}
    for name in fields:
        if name.endswith("_at_us") or name in {
            "first_seen_us",
            "last_seen_us",
            "provider_issue_number",
            "submitted_at_us",
            "original_position",
            "current_position",
            "line",
            "start_line",
            "original_line",
            "original_start_line",
        }:
            spec[name] = _NUMBER
        elif name in {"deleted", "draft", "merged", "locked", "resolved", "outdated"}:
            spec[name] = {"boolean", "integer"}
    spec["metadata"] = _METADATA_SCHEMAS[
        table, "metadata_json" if table == "source_repositories" else "metadata"
    ]
    spec["acquisition_scope"] = _CAPTURE_SCOPE
    return spec


_STAGED_KINDS = {
    "issue_resources": {"issue", "issue-comment"},
    "review_resources": {"review", "review-comment"},
    "change_request_state": {"change-request"},
    "document_state": {"pr-title", "pr-body", "issue-comment"},
    "review_thread_state": {"review-thread"},
    "source_repositories": {"source-repository"},
}


def _candidate_required(table, kind):
    if table == "source_repositories":
        return {
            "kind",
            "source_id",
            "repository_uuidv4",
            "first_seen_us",
            "last_seen_us",
            "parser_module",
            "parser_version",
            "acquisition_scope",
        }
    fields = {
        "kind",
        "repository_uuidv4",
        "repository_binding_id",
        "service_instance_uuidv4",
        "observed_at_us",
        "parsed_at_us",
        "parser_module",
        "parser_version",
        "acquisition_scope",
    }
    if table == "issue_resources":
        fields |= {"provider_resource_id", "provider_issue_number"}
        if kind == "issue-comment":
            fields.add("parent_provider_resource_id")
    else:
        fields.add("change_request_id")
        if table in {"document_state", "review_resources"}:
            fields.add("provider_change_request_document_id")
        if table == "review_thread_state":
            fields.add("provider_resource_id")
    return fields


def validate_current_candidate_shape(table, candidate):
    """Require a typed candidate before any unavailable parent may defer it.

    This validates only authored identity and capture correlations. It neither
    resolves a dependency nor treats an absent registration as an invalid one.
    """
    kind = candidate.get("kind")
    if table not in _STAGED_KINDS or kind not in _STAGED_KINDS[table]:
        raise JsonContractError("Current candidate kind differs from table")
    if "metadata" in candidate and not isinstance(candidate["metadata"], dict):
        raise JsonContractError("Current metadata requires modeled object")
    for name, value in candidate.items():
        if name.endswith("_us") and value is not None:
            try:
                validate_epoch_us(value)
            except (TypeError, ValueError) as cause:
                raise JsonContractError(
                    "Candidate timestamp requires signed int64"
                ) from cause
    for name in _candidate_required(table, kind) - {"acquisition_scope"}:
        if name.endswith("_us") or name == "provider_issue_number":
            try:
                validate_epoch_us(candidate.get(name))
            except (TypeError, ValueError) as cause:
                raise JsonContractError(
                    "Candidate requires actual integer " + name
                ) from cause
        else:
            _identity(name, candidate.get(name))
    scope = candidate.get("acquisition_scope")
    _candidate_capture_shape(table, scope, candidate, candidate)
    if candidate.get("provider_clock_scope") is not None and candidate[
        "provider_clock_scope"
    ] != _CLOCKS.get(kind):
        raise JsonContractError("Invalid candidate provider clock")
    if (
        kind in {"review", "review-thread", "source-repository"}
        and candidate.get("provider_updated_at_us") is not None
    ):
        raise JsonContractError("Candidate has no comparable provider update clock")
    if table == "issue_resources" and candidate["provider_issue_number"] <= 0:
        raise JsonContractError("Issue number requires positive integer")
    evidence = candidate.get("field_evidence", {})
    if not isinstance(evidence, dict):
        raise JsonContractError("Candidate field evidence requires object")
    _check_schema(table, "field_evidence_json", evidence, candidate)
    if any(json.loads(path)[0] not in candidate for path in evidence):
        raise JsonContractError("Candidate evidence refers to omitted field")
    if table == "source_repositories":
        for origin in evidence.values():
            _candidate_capture_shape(
                table, origin["acquisition_scope"], candidate, origin, field_origin=True
            )


def _candidate_capture_shape(table, scope, owner, producer, *, field_origin=False):
    if table == "source_repositories":
        validate_capture_shape(scope)
        _identity("source_registration_uuidv4", scope.get("source_registration_uuidv4"))
        if (
            field_origin
            and scope["source_registration_uuidv4"]
            != owner["acquisition_scope"]["source_registration_uuidv4"]
        ):
            raise JsonContractError(
                "Source field capture differs from candidate Source"
            )
    else:
        _acquisition_shape(scope, owner["service_instance_uuidv4"])
        if table == "issue_resources":
            if "change_request_id" in scope:
                raise JsonContractError("Ordinary Issue capture cannot claim PR")
            correlate = not field_origin and not _detached_acquisition(owner, scope)
        else:
            _identity("change_request_id", scope.get("change_request_id"))
            if scope["change_request_id"] != owner["change_request_id"]:
                raise JsonContractError("Capture differs from candidate parent")
            correlate = True
        if correlate and any(
            scope.get(name) != owner[name]
            for name in ("repository_uuidv4", "repository_binding_id")
        ):
            raise JsonContractError("Capture differs from candidate owner")
    if any(
        name in scope and scope[name] != producer.get(name)
        for name in ("parser_module", "parser_version")
    ):
        raise JsonContractError("Candidate producer differs from capture")


def _validate_staging_record(value, data):
    table = data.get("table_name")
    if data.get("reason", "").startswith("current_state:"):
        if table not in _STAGED_KINDS or not isinstance(value, dict):
            raise JsonContractError("Invalid staged current resource family")
        if value.get("kind") not in _STAGED_KINDS[table]:
            raise JsonContractError("Staged current kind differs from table")
        _check_metadata(
            _candidate_spec(table),
            {k: v for k, v in value.items() if k != "field_evidence"},
        )
        validate_current_candidate_shape(table, value)
        if value["repository_uuidv4"] != data.get("repository_uuidv4"):
            raise JsonContractError("Staging repository differs from candidate owner")
        prefix = (
            "source-current:" if table == "source_repositories" else "current-state:"
        )
        if (
            not isinstance(data.get("record_key"), str)
            or re.fullmatch(re.escape(prefix) + "[0-9a-f]{64}", data["record_key"])
            is None
        ):
            raise JsonContractError("Invalid typed current staging key")
        for field in {"deleted", "draft", "merged", "locked", "resolved", "outdated"}:
            if value.get(field) is not None and value[field] not in (False, True):
                raise JsonContractError("Staged current flag requires boolean or 0/1")
        if "acquisition_scope" in value:
            validate_capture_shape(value["acquisition_scope"])
        evidence = value.get("field_evidence", {})
        if not isinstance(evidence, dict):
            raise JsonContractError("Staged field evidence requires object")
        for key, origin in evidence.items():
            try:
                path = json.loads(key)
            except (ValueError, TypeError):
                raise JsonContractError("Invalid staged field path") from None
            if (
                not isinstance(path, list)
                or not path
                or any(not isinstance(part, str) for part in path)
                or path[0] not in _allowed_fields(table)
                or (len(path) > 1 and path[0] != "metadata")
                or json.dumps(path, ensure_ascii=False, separators=(",", ":")) != key
            ):
                raise JsonContractError("Invalid staged field path")
            _check_metadata(_ORIGIN_SPEC, origin)
            if set(origin) != _EVIDENCE_KEYS:
                raise JsonContractError("Staged field evidence has incomplete origin")
            validate_capture_shape(origin["acquisition_scope"])
        return
    if not isinstance(value, dict) or value.get("table") != table:
        raise JsonContractError("Staged envelope differs from typed table")
    try:
        _wire_graph().validate_record(value)
    except CatalogError as cause:
        raise JsonContractError("Invalid staged domain envelope") from cause


_ORIGIN_SPEC = {
    "provider_updated_at_us": _NUMBER,
    "provider_clock_scope": _TEXT,
    "observed_at_us": _NUMBER,
    "parsed_at_us": _NUMBER,
    "parser_module": _TEXT,
    "parser_version": _TEXT,
    "acquisition_scope": _CAPTURE_SCOPE,
}


def _staged_evidence_conditions(doc, fields, *, table=None, owner_doc=None):
    names = ",".join("'" + name + "'" for name in sorted(fields))
    origin = _metadata_conditions(_ORIGIN_SPEC, "se.value", "se.type")
    scope = "json_extract(se.value,'$.acquisition_scope')"
    invalid = [
        origin,
        f"(SELECT count(*) FROM json_each(se.value))<>{len(_EVIDENCE_KEYS)}",
        *_sql_scope_conditions(scope),
    ]
    if table is not None:
        invalid += _candidate_capture_conditions(
            table, scope, owner_doc, "se.value", field_origin=True
        )
        invalid += [
            f"coalesce(json_type(se.value,'$.{name}'),'')<>'integer' OR typeof(json_extract(se.value,'$.{name}'))<>'integer'"
            for name in ("observed_at_us", "parsed_at_us")
        ]
        invalid.append(
            "(json_type(se.value,'$.provider_updated_at_us')='integer' AND typeof(json_extract(se.value,'$.provider_updated_at_us'))<>'integer')"
        )
        invalid += [
            f"coalesce(json_type(se.value,'$.{name}'),'')<>'text' OR length(json_extract(se.value,'$.{name}'))=0 OR instr(json_extract(se.value,'$.{name}'),char(0))>0"
            for name in ("parser_module", "parser_version")
        ]
        clock = (
            "CASE json_extract("
            + owner_doc
            + ",'$.kind') "
            + " ".join(
                f"WHEN '{kind}' THEN '{value}'"
                for kind, value in sorted(_CLOCKS.items())
            )
            + " END"
        )
        invalid += [
            f"(json_type(se.value,'$.provider_clock_scope')<>'null' AND json_extract(se.value,'$.provider_clock_scope') IS NOT {clock})",
            f"(json_extract({owner_doc},'$.kind') IN ('review','review-thread','source-repository') AND json_type(se.value,'$.provider_updated_at_us')<>'null')",
        ]
    result = [
        f"(json_type({doc}) IS NOT NULL AND json_type({doc})<>'object')",
        f"EXISTS(SELECT 1 FROM json_each({doc}) se WHERE CASE WHEN NOT json_valid(se.key) THEN 1 WHEN json_type(se.key)<>'array' THEN 1 ELSE (json_array_length(se.key)=0 OR (SELECT json_group_array(p.value) FROM json_each(se.key) p)<>se.key OR EXISTS(SELECT 1 FROM json_each(se.key) p WHERE p.type<>'text') OR json_extract(se.key,'$[0]') NOT IN ({names}) OR (json_array_length(se.key)>1 AND json_extract(se.key,'$[0]')<>'metadata')) END)",
        f"EXISTS(SELECT 1 FROM json_each({doc}) se WHERE CASE WHEN se.type<>'object' THEN 1 ELSE ("
        + " OR ".join(invalid)
        + ") END)",
    ]
    if owner_doc is not None:
        result += [
            f"EXISTS(SELECT 1 FROM json_each({doc}) se WHERE CASE WHEN NOT json_valid(se.key) THEN 1 WHEN json_type(se.key)<>'array' THEN 1 ELSE NOT EXISTS(SELECT 1 FROM json_each({owner_doc}) field WHERE field.key=json_extract(se.key,'$[0]')) END)",
            f"EXISTS(WITH RECURSIVE paths(path,value,type) AS (SELECT json_array('metadata'),json_extract({owner_doc},'$.metadata'),'object' UNION ALL SELECT json_insert(p.path,'$[#]',j.key),j.value,j.type FROM paths p JOIN json_each(CASE WHEN p.type='object' THEN p.value ELSE '{{}}' END) j WHERE p.type='object') SELECT 1 FROM json_each({doc}) se WHERE CASE WHEN NOT json_valid(se.key) THEN 1 ELSE json_extract(se.key,'$[0]')='metadata' AND NOT EXISTS(SELECT 1 FROM paths p WHERE p.path=se.key) END)",
            f"EXISTS(SELECT 1 FROM json_each({doc}) se JOIN json_each(CASE WHEN json_valid(se.key) THEN se.key ELSE '[]' END) depth WHERE json_extract(se.key,'$[0]')='metadata' AND CAST(depth.key AS INTEGER)>0 AND NOT EXISTS(SELECT 1 FROM json_each({doc}) ancestor WHERE ancestor.key=(SELECT json_group_array(p.value) FROM json_each(se.key) p WHERE CAST(p.key AS INTEGER)<CAST(depth.key AS INTEGER))))",
        ]
    return result


def _candidate_capture_conditions(table, scope, owner, producer, *, field_origin=False):
    result = []
    # Check authored reference spelling without requiring its parent to exist.
    for name in sorted(REFERENCE_TARGETS):
        valid = (
            _sql_uuid("captured.value")
            if "uuidv4" in name
            else "(length(captured.value)>0 AND instr(captured.value,char(0))=0)"
        )
        null = "" if "uuidv4" in name else " AND captured.type<>'null'"
        result.append(
            f"EXISTS(SELECT 1 FROM json_tree({scope}) captured WHERE captured.key='{name}'{null} AND (captured.type<>'text' OR NOT {valid}))"
        )
    required = (
        {"source_registration_uuidv4"}
        if table == "source_repositories"
        else {
            "repository_uuidv4",
            "repository_binding_id",
            "service_instance_uuidv4",
            "endpoint",
        }
    )
    if table not in {"issue_resources", "source_repositories"}:
        required.add("change_request_id")
    for name in sorted(required):
        value = f"json_extract({scope},'$.{name}')"
        valid = (
            _sql_uuid(value)
            if "uuidv4" in name
            else f"(length({value})>0 AND instr({value},char(0))=0)"
        )
        result.append(
            f"coalesce(json_type({scope},'$.{name}'),'')<>'text' OR NOT {valid}"
        )
    if table == "source_repositories":
        if field_origin:
            result.append(
                f"json_extract({scope},'$.source_registration_uuidv4') IS NOT json_extract({owner},'$.acquisition_scope.source_registration_uuidv4')"
            )
    else:
        result.append(
            f"json_extract({scope},'$.service_instance_uuidv4') IS NOT json_extract({owner},'$.service_instance_uuidv4')"
        )
        if table == "issue_resources":
            result.append(f"json_type({scope},'$.change_request_id') IS NOT NULL")
            if not field_origin:
                different = " OR ".join(
                    f"json_extract({scope},'$.{name}') IS NOT json_extract({owner},'$.{name}')"
                    for name in ("repository_uuidv4", "repository_binding_id")
                )
                result.append(
                    f"((json_extract({owner},'$.kind')<>'issue-comment' OR json_extract({scope},'$.repository_uuidv4') IS json_extract({owner},'$.repository_uuidv4')) AND ({different}))"
                )
        else:
            result += [
                f"json_extract({scope},'$.{name}') IS NOT json_extract({owner},'$.{name}')"
                for name in (
                    "repository_uuidv4",
                    "repository_binding_id",
                    "change_request_id",
                )
            ]
    result += [
        f"(json_type({scope},'$.{name}') IS NOT NULL AND json_extract({scope},'$.{name}') IS NOT json_extract({producer},'$.{name}'))"
        for name in ("parser_module", "parser_version")
    ]
    return result


def _candidate_conditions(table, doc):
    result = [
        f"json_extract({doc},'$.repository_uuidv4') IS NOT NEW.repository_uuidv4",
        f"(json_type({doc},'$.metadata') IS NOT NULL AND json_type({doc},'$.metadata')<>'object')",
    ]
    kinds = _STAGED_KINDS[table]
    result += [
        f"(json_type({doc},'$.{name}')='integer' AND typeof(json_extract({doc},'$.{name}'))<>'integer')"
        for name in sorted(_candidate_spec(table))
        if name.endswith("_us")
    ]
    for kind in sorted(kinds):
        invalid = []
        for name in sorted(_candidate_required(table, kind) - {"acquisition_scope"}):
            value = f"json_extract({doc},'$.{name}')"
            if name.endswith("_us") or name == "provider_issue_number":
                invalid.append(
                    f"coalesce(json_type({doc},'$.{name}'),'')<>'integer' OR typeof({value})<>'integer'"
                )
            else:
                valid = (
                    _sql_uuid(value)
                    if "uuidv4" in name
                    else f"(length({value})>0 AND instr({value},char(0))=0)"
                )
                invalid.append(
                    f"coalesce(json_type({doc},'$.{name}'),'')<>'text' OR NOT {valid}"
                )
        result.append(
            f"(json_extract({doc},'$.kind')='{kind}' AND ("
            + " OR ".join(invalid)
            + "))"
        )
    scope = f"json_extract({doc},'$.acquisition_scope')"
    result += [f"coalesce(json_type({doc},'$.acquisition_scope'),'')<>'object'"]
    result += _candidate_capture_conditions(table, scope, doc, doc)
    result += [
        f"(json_type({doc},'$.provider_clock_scope') NOT IN ('null') AND json_extract({doc},'$.provider_clock_scope') IS NOT CASE json_extract({doc},'$.kind') "
        + " ".join(
            f"WHEN '{kind}' THEN '{clock}'" for kind, clock in sorted(_CLOCKS.items())
        )
        + " END)"
    ]
    result.append(
        f"(json_extract({doc},'$.kind') IN ('review','review-thread','source-repository') AND json_type({doc},'$.provider_updated_at_us') NOT IN ('null'))"
    )
    if table == "issue_resources":
        result.append(f"json_extract({doc},'$.provider_issue_number')<=0")
    prefix = "source-current:" if table == "source_repositories" else "current-state:"
    suffix = f"substr(NEW.record_key,{len(prefix) + 1})"
    result.append(
        f"substr(NEW.record_key,1,{len(prefix)})<>'{prefix}' OR NOT {_sql_hex(suffix, '64')}"
    )
    return result


def _staged_json_conditions(table, column, doc):
    schema = JSON_REGISTRY[table, column]
    conditions = [
        f"json_type({doc})<>'{schema.shape}'",
        f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE typeof(j.key)='text' GROUP BY j.parent,j.key HAVING count(*)>1)",
    ]
    if (table, column) in _METADATA_SCHEMAS:
        conditions.append(
            _metadata_conditions(
                _METADATA_SCHEMAS[table, column], doc, f"json_type({doc})"
            )
        )
    if (table, column) in _EVIDENCE_SCHEMAS:
        conditions.append(
            _metadata_conditions(
                _EVIDENCE_SCHEMAS[table, column], doc, f"json_type({doc})"
            )
        )
    if (table, column) in _SCOPE_COLUMNS or schema.category == "current-acquisition":
        conditions.extend(_sql_scope_conditions(doc))
    if schema.category == "current-field-evidence":
        conditions.extend(_staged_evidence_conditions(doc, _allowed_fields(table)))
    if table == "code_assessments" and column == "details_json":
        conditions += [
            condition.replace(
                "NEW.object_format",
                "json_extract(NEW.record_json,'$.values.object_format')",
            )
            for condition in _special_conditions(table, column, doc)
        ]
    return conditions


def _staging_conditions(doc):
    names = ",".join("'" + name + "'" for name in sorted(_wire_graph().columns))
    current = ",".join("'" + name + "'" for name in sorted(_STAGED_KINDS))
    return [
        f"NEW.table_name NOT IN ({names})",
        f"(NEW.reason LIKE 'current_state:%' AND NEW.table_name NOT IN ({current}))",
        f"CASE WHEN NEW.reason LIKE 'current_state:%' THEN 0 ELSE (json_extract({doc},'$.table') IS NOT NEW.table_name OR coalesce(json_type({doc},'$.key'),'')<>'text' OR substr(json_extract({doc},'$.key'),1,length(NEW.table_name)+1)<>NEW.table_name||':' OR coalesce(json_type({doc},'$.values'),'')<>'object' OR EXISTS(SELECT 1 FROM json_each({doc}) sk WHERE sk.key NOT IN ('key','table','values','requires')) OR (SELECT count(*) FROM json_each({doc})) NOT IN (3,4) OR (json_type({doc},'$.requires') IS NOT NULL AND (NEW.table_name NOT IN ('completion_markers','coverage_claims') OR json_type({doc},'$.requires')<>'array' OR EXISTS(SELECT 1 FROM json_each({doc},'$.requires') r WHERE r.type<>'text') OR EXISTS(SELECT 1 FROM json_each({doc},'$.requires') r GROUP BY r.value HAVING count(*)>1)))) END",
    ]


def _staging_guard_sql():
    """Independent table/column guards avoid nesting a domain-wide CASE tree."""
    graph = _wire_graph()
    output = []
    doc = "NEW.record_json"

    def emit(name, table, current, conditions):
        reason = "LIKE" if current else "NOT LIKE"
        for operation in ("INSERT", "UPDATE"):
            output.append(
                f"CREATE TRIGGER json_exchange_staging_{name}_{operation.lower()} BEFORE {operation} ON exchange_staging\n"
                f"WHEN NEW.table_name='{table}' AND NEW.reason {reason} 'current_state:%' AND CASE WHEN NOT json_valid({doc}) THEN 1 WHEN json_type({doc})<>'object' THEN 1 ELSE (\n"
                + "\n OR ".join(conditions)
                + ") END BEGIN SELECT RAISE(ABORT,'JSON contract violation: exchange_staging.record_json'); END;\n"
            )

    for table, kinds in sorted(_STAGED_KINDS.items()):
        candidate = _candidate_spec(table)
        body = f"json_remove({doc},'$.field_evidence')"
        conditions = [
            _metadata_conditions(candidate, body, f"json_type({body})"),
            f"coalesce(json_extract({doc},'$.kind'),'') NOT IN ("
            + ",".join("'" + kind + "'" for kind in sorted(kinds))
            + ")",
            *_sql_scope_conditions(f"json_extract({doc},'$.acquisition_scope')"),
            *_candidate_conditions(table, doc),
        ]
        conditions += [
            f"(json_type({doc},'$.{field}')='integer' AND json_extract({doc},'$.{field}') NOT IN (0,1))"
            for field in sorted(
                {"deleted", "draft", "merged", "locked", "resolved", "outdated"}
            )
            if field in candidate
        ]
        emit("candidate_" + table, table, True, conditions)
        emit(
            "origins_" + table,
            table,
            True,
            _staged_evidence_conditions(
                f"json_extract({doc},'$.field_evidence')",
                _allowed_fields(table),
                table=table,
                owner_doc=doc,
            ),
        )
    for table in sorted(graph.columns):
        columns = graph.expected_columns(table)
        fields = ",".join("'" + name + "'" for name in sorted(columns))
        values = f"json_extract({doc},'$.values')"
        conditions = [
            f"(SELECT count(*) FROM json_each({values}))<>{len(columns)}",
            f"EXISTS(SELECT 1 FROM json_each({values}) sv WHERE sv.key NOT IN ({fields}))",
        ]
        object_cases = []
        for column in sorted(columns):
            allowed = []
            for parent, child_cols, parent_cols in graph.foreign[table]:
                if column in child_cols:
                    parent_col = parent_cols[child_cols.index(column)]
                    allowed.append(
                        f"((SELECT count(*) FROM json_each(sv.value))=2 AND json_type(sv.value,'$.\"$ref\"')='text' AND substr(json_extract(sv.value,'$.\"$ref\"'),1,{len(parent) + 1})='{parent}:' AND json_extract(sv.value,'$.column')='{parent_col}')"
                    )
            if graph.columns[table][column] == "BLOB":
                allowed += [
                    "((SELECT count(*) FROM json_each(sv.value))=1 AND json_type(sv.value,'$.\"$bytes\"')='text')",
                    "((SELECT count(*) FROM json_each(sv.value))=1 AND json_type(sv.value,'$.\"$sha256\"')='text' AND length(json_extract(sv.value,'$.\"$sha256\"'))=64 AND json_extract(sv.value,'$.\"$sha256\"') NOT GLOB '*[^0-9a-f]*')",
                ]
            object_cases.append(
                "WHEN '" + column + "' THEN NOT (" + " OR ".join(allowed or ["0"]) + ")"
            )
            if (table, column) in JSON_REGISTRY:
                inner = f"json_extract({doc},'$.values.{column}')"
                checks = _staged_json_conditions(table, column, inner)
                emit(
                    "value_" + table + "_" + column,
                    table,
                    False,
                    [
                        f"CASE WHEN json_type({doc},'$.values.{column}')='null' THEN 0 WHEN json_type({doc},'$.values.{column}')<>'text' OR NOT json_valid({inner}) THEN 1 ELSE ("
                        + " OR ".join(checks)
                        + ") END"
                    ],
                )
        conditions.append(
            f"EXISTS(SELECT 1 FROM json_each({values}) sv WHERE CASE WHEN sv.type='array' THEN 1 WHEN sv.type<>'object' THEN 0 ELSE CASE sv.key "
            + " ".join(object_cases)
            + " ELSE 1 END END)"
        )
        emit("envelope_" + table, table, False, conditions)
    return "".join(output)
