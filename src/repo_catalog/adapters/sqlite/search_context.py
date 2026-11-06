"""Context-authority Search extraction, loaded only for Context projections."""

from __future__ import annotations

import json

from repo_catalog.adapters.sqlite.production_search import BoundedDocuments
from repo_catalog.domain.context_query import (
    provider_role_summary,
    repository_relation_summary,
)
from repo_catalog.domain.p1_context import FieldCandidate, FieldClock, ResourceKey
from repo_catalog.domain.query_contracts import canonical_json


def extract_context_documents(
    context,
    *,
    evidence=None,
) -> tuple[dict[str, str], dict[str, dict[str, object]]]:
    """Extract searchable `context_text` documents and summaries from a pinned Context snapshot.

    Resolves `text_body_sha256` via the verification-aware `read_verified_text`
    callable, and indexes current string `field_candidates` while excluding explicit
    JSON `"null"`.
    """
    context._validate_stage()
    documents: dict[str, str] = BoundedDocuments()
    summaries: dict[str, dict[str, object]] = {}

    rows = context.db.execute(
        "SELECT service_instance_uuidv4,resource_kind,provider_resource_id,field_name,"
        "clock_json,value_json,provenance_json,observed_at_us "
        "FROM field_candidates "
        "ORDER BY service_instance_uuidv4,resource_kind,provider_resource_id,field_name,clock_json,value_json,provenance_json"
    ).fetchall()
    for row in rows:
        (
            service_id,
            r_kind,
            r_id,
            field_name,
            clock_json,
            value_json,
            prov_json,
            obs_at,
        ) = row
        parsed_clock = json.loads(clock_json)
        clock = FieldClock(parsed_clock["domain"], parsed_clock["at_us"])
        if clock.encode() != clock_json:
            raise ValueError("invalid stored canonical clock")
        FieldCandidate(
            ResourceKey(service_id, r_kind, r_id),
            field_name,
            value_json,
            clock,
            prov_json,
            obs_at,
        )
        decoded_val = json.loads(value_json)
        if decoded_val is None:
            continue
        if field_name == "text_body_sha256":
            if not isinstance(decoded_val, str):
                continue
            text_val = context.read_text(decoded_val)
        elif isinstance(decoded_val, str):
            text_val = decoded_val
        else:
            continue

        doc_key = canonical_json(
            [
                service_id,
                r_kind,
                r_id,
                field_name,
                clock_json,
                value_json,
                prov_json,
            ]
        )
        documents[doc_key] = text_val
        summaries[doc_key] = {
            "clock": json.loads(clock_json),
            "field_name": field_name,
            "observed_at_us": obs_at,
            "provenance": json.loads(prov_json),
            "provider_resource_id": r_id,
            "resource_kind": r_kind,
            "service_instance_uuidv4": service_id,
            "repository_roles": [
                provider_role_summary(role)
                for role in context.provider_repository_roles(
                    ResourceKey(service_id, r_kind, r_id), evidence=evidence
                )
            ],
        }

    for resource in context.resources():
        for role in context.provider_repository_roles(resource, evidence=evidence):
            key = canonical_json(
                [
                    "provider_repository_role",
                    *resource.coordinates(),
                    role.scope.relation_kind,
                    canonical_json(role.scope.to_dict()),
                    role.provenance_json,
                ]
            )
            targets = (
                role.mapping.active_repository_uuidv4s
                if role.mapping is not None
                else ()
            )
            documents[key] = " ".join(
                (
                    role.scope.relation_kind,
                    role.scope.provider_repository_id or "null",
                    *targets,
                )
            )
            summaries[key] = {
                "kind": "current_provider_repository_role",
                **provider_role_summary(role),
            }
        for relation in context.repository_relations(resource, evidence=evidence):
            key = canonical_json(
                ["repository_relation", *relation.claim_key.coordinates()]
            )
            documents[key] = " ".join(
                (
                    relation.relation_kind,
                    relation.relation.target_repository_uuidv4 or "null",
                )
            )
            summaries[key] = {
                "kind": "stored_core_target_relation",
                **repository_relation_summary(relation),
            }

    return documents, summaries
