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
""",
)
_register("decoded-headers", "commits.metadata")
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


def _check_schema(table, column, value, data):
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
        if schema.category in {
            "authored",
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
    if table in {"incremental_scans", "completion_markers"}:
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


def guard_sql():
    """Generate standalone SQLite guards, requiring no connection callbacks."""
    output = [
        "-- Generated from json_contracts.JSON_REGISTRY; edit the registry and regenerate.\n"
    ]
    for (table, column), schema in sorted(JSON_REGISTRY.items()):
        if schema.category not in {
            "authored",
            "input-manifest",
            "git-roots",
            "git-object-manifest",
            "definition",
        }:
            continue
        doc = f"NEW.{column}"
        repository, source = _sql_owner(table)
        conditions = [
            # Object keys are TEXT; array indices are INTEGER. Filtering keys
            # therefore preserves nested duplicate detection without rewalking
            # the entire tree for every parent in a quadratic self-join.
            f"EXISTS(SELECT 1 FROM json_tree({doc}) j WHERE typeof(j.key)='text' GROUP BY j.parent,j.key HAVING count(*)>1)",
        ]
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
