"""ADR 0030 v4 selection and lossless Context report codecs.

This module uses only the frozen I1 contract. It does not fetch Provider data or
assign Repository mappings. Selection never grants Repository permission.
"""

from __future__ import annotations

import json

from repo_catalog.domain.exchange import ExchangeError, ExchangeSelectionScope
from repo_catalog.domain.p1_context import (
    EventReportKey,
    FieldClock,
    MappingClaimKey,
    MappingDisposition,
    ResourceKey,
    ResourceRepositoryRelation,
    TransferEventReport,
)


def resource(row: dict) -> ResourceKey:
    return ResourceKey(
        *(
            row[k]
            for k in (
                "service_instance_uuidv4",
                "resource_kind",
                "provider_resource_id",
            )
        )
    )


def relation(row: dict) -> ResourceRepositoryRelation:
    return ResourceRepositoryRelation(
        resource(row),
        row["relation_kind"],
        FieldClock.from_json(row["clock_json"]),
        row["target_json"],
        row["provenance_json"],
        row["observed_at_us"],
    )


def disposition(row: dict) -> MappingDisposition:
    if row["relation_kind"] != "represents_repository":
        raise ExchangeError("INVALID_DISPOSITION", "relation_kind")
    if row["replacement_clock_json"] is None and (
        row["replacement_target_json"] is not None
        or row["replacement_provenance_json"] is not None
    ):
        raise ExchangeError("INVALID_DISPOSITION", "replacement")

    def key(prefix):
        return MappingClaimKey(
            resource(row),
            "represents_repository",
            FieldClock.from_json(row[prefix + "clock_json"]),
            row[prefix + "target_json"],
            row[prefix + "provenance_json"],
        )

    return MappingDisposition(
        key("claim_"),
        row["disposition_kind"],
        FieldClock.from_json(row["disposition_clock_json"]),
        row["disposition_provenance_json"],
        row["observed_at_us"],
        None if row["replacement_clock_json"] is None else key("replacement_"),
    )


def transfer_reports(data: dict) -> list[TransferEventReport]:
    endpoints = [
        relation(r)
        for r in data["resource_repository_relations"]
        if r["relation_kind"].startswith("transfer_")
    ]
    result = []
    for row in data["resource_relations"]:
        if row["relation_kind"] != "transfer_event_report":
            continue
        clock = FieldClock.from_json(
            json.dumps(
                json.loads(row["scope_json"])["clock"],
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        key = EventReportKey(resource(row), clock, row["provenance_json"])
        selected = tuple(
            r
            for r in endpoints
            if r.resource == key.event_resource
            and r.clock == clock
            and r.provenance_json == key.provenance_json
        )
        result.append(
            TransferEventReport.from_stored_scope(
                key,
                selected,
                row["scope_json"],
                row["members_json"],
                row["observed_at_us"],
            )
        )
    covered = {
        r.claim_key
        for report in result
        for r in (*report.from_relations, *report.to_relations)
    }
    if any(r.claim_key not in covered for r in endpoints):
        raise ExchangeError("INCOMPLETE_TRANSFER_REPORT", "context")
    return result


def explicit_scope(scope: ExchangeSelectionScope) -> None:
    if not scope.all_selected and any(
        value is None
        for value in (
            scope.repository_uuidv4s,
            scope.object_oids,
            scope.resource_keys,
            scope.source_uuidv4s,
        )
    ):
        raise ExchangeError(
            "SELECTION_REQUIRED",
            "R/O/C",
            "omitted selection requires explicit all_selected opt-in",
        )


def filter_sections(core, context, scope, *, permitted=None):
    """Recompute selection from typed facts; a wire report grants no authority."""
    from repo_catalog.domain.git_native import parse_metadata

    omissions = []
    for name, data, enabled in (
        ("core", core, scope.include_core),
        ("context", context, scope.include_context),
    ):
        if data is not None and not enabled:
            omissions.append(
                {
                    "section": name,
                    "reason": "section_not_selected",
                    "unit_count": sum(map(len, data.values())),
                }
            )
            for values in data.values():
                values.clear()
    if core is not None and not scope.include_retained_bytes:
        for name in ("retained_metadata", "retained_notes"):
            if core[name]:
                omissions.append(
                    {
                        "section": name,
                        "reason": "retained_bytes_not_selected",
                        "unit_count": len(core[name]),
                    }
                )
            core[name] = []
    repos = None if scope.repository_uuidv4s is None else set(scope.repository_uuidv4s)
    if permitted is not None:
        repos = set(permitted) if repos is None else repos.intersection(permitted)

    def allowed(value):
        return repos is None or value in repos

    def retain(data, key, predicate, reason):
        retained = []
        for index, row in enumerate(data[key]):
            if predicate(row):
                retained.append(row)
            else:
                omissions.append(
                    {"section": key, "unit_index": index, "reason": reason}
                )
        data[key] = retained

    if core is not None:
        available = {(r["object_format"], r["full_oid"]) for r in core["git_objects"]}
        chosen = (
            available.copy()
            if scope.object_oids is None
            else {o.key for o in scope.object_oids}.intersection(available)
        )
        frontier = chosen.copy()
        edges = {}
        for row in core["relation_groups"]:
            edges.setdefault((row["object_format"], row["full_oid"]), set()).update(
                (m[1], m[2]) for m in json.loads(row["membership_json"])
            )
        for depth in range(scope.max_depth):
            added = set()
            for owner in sorted(frontier):
                for member in sorted(edges.get(owner, ())):
                    if (
                        member in available
                        and member not in chosen
                        and len(chosen) < scope.max_units
                    ):
                        chosen.add(member)
                        added.add(member)
            frontier = added
            if not frontier:
                break

        def oid_selected(r):
            return (r["object_format"], r["full_oid"]) in chosen

        retain(core, "git_objects", oid_selected, "object_not_selected")
        retain(core, "scalar_claims", oid_selected, "object_not_selected")
        retain(
            core,
            "relation_groups",
            lambda r: (
                oid_selected(r)
                and all(
                    (m[1], m[2]) in chosen for m in json.loads(r["membership_json"])
                )
            ),
            "whole_group_depth_or_selection_limit",
        )

        def metadata_selected(r):
            if not oid_selected(r):
                return False
            parsed = parse_metadata(
                r["object_format"], r["native_type"], bytes.fromhex(r["body_hex"])
            )
            return all(
                (m[1], m[2]) in chosen
                for values in parsed.relations.values()
                for m in values
            )

        retain(
            core,
            "retained_metadata",
            metadata_selected,
            "whole_metadata_dependency_not_selected",
        )
        for key in (
            "repositories",
            "repository_claims",
            "git_observations",
            "captures",
        ):
            retain(
                core,
                key,
                lambda r: (
                    allowed(r["repository_uuidv4"])
                    and (key != "captures" or (r["object_format"], r["root"]) in chosen)
                ),
                "repository_or_capture_not_selected_or_permitted",
            )
        if scope.notes_refs is not None:
            retain(
                core,
                "captures",
                lambda r: r["ref"] in scope.notes_refs,
                "notes_ref_not_selected",
            )
        captures = {
            (r["capture_origin_uuidv4"], r["capture_uuidv4"]) for r in core["captures"]
        }
        for key in (
            "notes_claims",
            "notes_groups",
            "notes_inventories",
            "note_roles",
            "retained_notes",
        ):

            def selected(r):
                if (r["capture_origin_uuidv4"], r["capture_uuidv4"]) not in captures:
                    return False
                fmt = r.get("object_format")
                if key == "notes_groups":
                    return all(
                        (fmt, m[0]) in chosen and (fmt, m[1]) in chosen
                        for m in json.loads(r["membership_json"])
                    )
                if key == "notes_inventories":
                    cap = next(
                        c
                        for c in core["captures"]
                        if (c["capture_origin_uuidv4"], c["capture_uuidv4"])
                        == (r["capture_origin_uuidv4"], r["capture_uuidv4"])
                    )
                    return all(
                        (cap["object_format"], m[0]) in chosen
                        and (cap["object_format"], m[1]) in chosen
                        for m in r["members"]
                    )
                return (fmt, r["target"]) in chosen and (
                    fmt,
                    r.get("note", r.get("full_oid")),
                ) in chosen

            retain(core, key, selected, "whole_notes_unit_not_selected_or_permitted")
        denied_claims = set()

        def core_scope_selected(r):
            coords = json.loads(r["owner_coordinates_json"])
            if r["owner_kind"] == "repository":
                return allowed(coords[0])
            if r["owner_kind"] == "capture":
                return tuple(coords[:2]) in captures
            return tuple(coords[:2]) in chosen

        def proof_selected(r):
            ok = core_scope_selected(r) and all(
                tuple(m) in chosen for m in json.loads(r["members_json"])
            )
            if not ok:
                denied_claims.add(
                    (
                        r["owner_kind"],
                        r["owner_coordinates_json"],
                        r["observed_at_us"],
                        r["coverage_state"],
                    )
                )
            return ok

        retain(
            core,
            "coverage_proofs",
            proof_selected,
            "whole_coverage_proof_dependency_not_selected",
        )
        retain(
            core,
            "coverage_claims",
            lambda r: (
                core_scope_selected(r)
                and (
                    r["owner_kind"],
                    r["owner_coordinates_json"],
                    r["observed_at_us"],
                    r["coverage_state"],
                )
                not in denied_claims
            ),
            "whole_coverage_unit_not_selected",
        )
        retain(
            core, "coverage_scopes", core_scope_selected, "coverage_owner_not_selected"
        )
    if context is not None:
        resources = [resource(r).coordinates() for r in context["resources"]]
        relations = [
            tuple(
                r[k]
                for k in (
                    "service_instance_uuidv4",
                    "resource_kind",
                    "provider_resource_id",
                    "relation_kind",
                    "members_json",
                    "provenance_json",
                    "scope_json",
                    "observed_at_us",
                )
            )
            for r in context["resource_relations"]
        ]
        collections = [
            tuple(
                r[k]
                for k in (
                    "service_instance_uuidv4",
                    "resource_kind",
                    "provider_resource_id",
                    "collection_kind",
                    "provenance_json",
                    "scope_json",
                    "observed_at_us",
                    "terminal_state",
                    "members_json",
                )
            )
            for r in context["collections"]
        ]
        chosen, _, _ = expand_resources(
            resources,
            relations,
            collections,
            scope,
            context["resource_repository_relations"],
        )
        reports = transfer_reports(context)
        denied = {
            p.report_key
            for p in reports
            if p.event_resource not in chosen
            or any(
                r.target_repository_uuidv4 is not None
                and not allowed(r.target_repository_uuidv4)
                for r in (*p.from_relations, *p.to_relations)
            )
            or any(
                p is not None and p not in chosen
                for p in (p.from_provider_repository, p.to_provider_repository)
            )
        }
        for key in (
            "resources",
            "field_candidates",
            "core_references",
            "resource_relations",
            "collections",
            "resource_repository_relations",
        ):

            def selected(r):
                if resource(r) not in chosen:
                    return False
                if "members_json" in r and not all(
                    ResourceKey(*m) in chosen for m in json.loads(r["members_json"])
                ):
                    return False
                if key == "resource_repository_relations":
                    rel = relation(r)
                    if rel.target_repository_uuidv4 is not None and not allowed(
                        rel.target_repository_uuidv4
                    ):
                        return False
                    if (
                        rel.relation_kind.startswith("transfer_")
                        and EventReportKey(rel.resource, rel.clock, rel.provenance_json)
                        in denied
                    ):
                        return False
                if r.get("relation_kind") == "transfer_event_report":
                    clock = FieldClock.from_json(
                        json.dumps(
                            json.loads(r["scope_json"])["clock"],
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    )
                    if (
                        EventReportKey(resource(r), clock, r["provenance_json"])
                        in denied
                    ):
                        return False
                return True

            retain(
                context,
                key,
                selected,
                "whole_unit_context_selection_or_repository_permission",
            )
        keys = {relation(r).claim_key for r in context["resource_repository_relations"]}
        retain(
            context,
            "repository_mapping_dispositions",
            lambda r: (
                disposition(r).claim_key in keys
                and (
                    disposition(r).replacement_claim_key is None
                    or disposition(r).replacement_claim_key in keys
                )
            ),
            "exact_mapping_claim_not_selected",
        )
        source_ids = None if scope.source_uuidv4s is None else set(scope.source_uuidv4s)
        retain(
            context,
            "sources",
            lambda r: (
                source_ids is None or r["source_registration_uuidv4"] in source_ids
            ),
            "source_not_selected",
        )
        source_ids = {r["source_registration_uuidv4"] for r in context["sources"]}
        retain(
            context,
            "repositories",
            lambda r: allowed(r["repository_uuidv4"]),
            "repository_not_permitted_or_selected",
        )
        retain(
            context,
            "source_repositories",
            lambda r: (
                r["source_registration_uuidv4"] in source_ids
                and allowed(r["repository_uuidv4"])
            ),
            "membership_source_or_repository_not_selected",
        )
        retain(
            context,
            "source_inventories",
            lambda r: (
                r["source_registration_uuidv4"] in source_ids
                and all(allowed(v) for v in json.loads(r["members_json"]))
            ),
            "whole_inventory_dependency_not_selected",
        )
        inventories = {
            (r["source_registration_uuidv4"], r["scope_json"], r["observed_at_us"])
            for r in context["source_inventories"]
        }
        collections = {
            (
                resource(r),
                r["collection_kind"],
                r["provenance_json"],
                r["observed_at_us"],
            )
            for r in context["collections"]
        }
        denied_claims = set()

        def owner_selected(r):
            coords = json.loads(r["owner_coordinates_json"])
            if r["owner_kind"] == "repository":
                return allowed(coords[0])
            return (
                coords[0] in source_ids
                if r["owner_kind"] in ("source", "source_inventory")
                else ResourceKey(*coords[:3]) in chosen
            )

        def proof_selected(r):
            ok = (
                (
                    r["source_registration_uuidv4"],
                    r["scope_json"],
                    r["terminal_observed_at_us"],
                )
                in inventories
                if r["proof_kind"] == "source_inventory"
                else (
                    resource(r),
                    r["collection_kind"],
                    r["provenance_json"],
                    r["terminal_observed_at_us"],
                )
                in collections
            )
            if not ok:
                denied_claims.add(
                    (
                        r["owner_kind"],
                        r["owner_coordinates_json"],
                        r["observed_at_us"],
                        r["coverage_state"],
                    )
                )
            return ok and owner_selected(r)

        retain(
            context, "coverage_proofs", proof_selected, "whole_terminal_not_selected"
        )
        retain(
            context, "coverage_scopes", owner_selected, "coverage_owner_not_selected"
        )
        retain(
            context,
            "coverage_claims",
            lambda r: (
                owner_selected(r)
                and (
                    r["owner_kind"],
                    r["owner_coordinates_json"],
                    r["observed_at_us"],
                    r["coverage_state"],
                )
                not in denied_claims
            ),
            "whole_coverage_unit_not_selected",
        )
        # Providers are non-executable domain registrations, retained as original
        # supplied facts. Access fields remain rejected by the registration codec.
        if scope.resource_keys is not None or scope.source_uuidv4s is not None:
            services = {r["service_instance_uuidv4"] for r in context["resources"]} | {
                r["service_instance_uuidv4"] for r in context["sources"]
            }
            retain(
                context,
                "providers",
                lambda r: r["service_instance_uuidv4"] in services,
                "provider_not_required_by_selected_context",
            )
        digests = {
            json.loads(r["value_json"])
            for r in context["field_candidates"]
            if r["field_name"] == "text_body_sha256"
        }
        retain(
            context,
            "text_bodies",
            lambda r: r["sha256"] in digests,
            "text_not_referenced_by_selected_resource",
        )
    return omissions


def expand_resources(rows, relations, collections, scope, repository_relations=()):
    """Cycle-safe traversal over actual resources only, with explicit depth."""
    available = {ResourceKey(*r) for r in rows}
    chosen = (
        available.copy()
        if scope.resource_keys is None
        else set(scope.resource_keys).intersection(available)
    )
    reasons = []
    omissions = []
    edges = {r: set() for r in available}
    for r in available:
        if r.resource_kind in ("review", "thread", "comment", "document"):
            coords = json.loads(r.provider_resource_id)
            parent = ResourceKey(r.service_instance_uuidv4, *coords[:2])
            if parent in available:
                edges[r].add(parent)
    for row in relations:
        owner = ResourceKey(*row[:3])
        edges.setdefault(owner, set()).update(
            ResourceKey(*m) for m in json.loads(row[4])
        )
    for row in collections:
        edges.setdefault(ResourceKey(*row[:3]), set()).update(
            ResourceKey(*m) for m in json.loads(row[8])
        )
    for row in repository_relations:
        rel = relation(row)
        if rel.embedded_support is not None:
            edges.setdefault(rel.resource, set()).add(
                rel.embedded_support.provider_repository
            )
    frontier = chosen.copy()
    for depth in range(scope.max_depth):
        added = set()
        for owner in sorted(frontier, key=lambda r: r.coordinates()):
            for member in sorted(edges.get(owner, ()), key=lambda r: r.coordinates()):
                if member in chosen:
                    continue
                if member not in available:
                    omissions.append(
                        {
                            "section": "resources",
                            "unit": list(member.coordinates()),
                            "reason": "missing_sender_resource",
                        }
                    )
                elif len(chosen) >= scope.max_units:
                    omissions.append(
                        {
                            "section": "resources",
                            "unit": list(member.coordinates()),
                            "reason": "unit_limit",
                        }
                    )
                else:
                    chosen.add(member)
                    added.add(member)
                    reasons.append(
                        {
                            "from": list(owner.coordinates()),
                            "to": list(member.coordinates()),
                            "depth": depth + 1,
                        }
                    )
        frontier = added
        if not frontier:
            break
    for owner in frontier:
        for member in edges.get(owner, ()):
            if member not in chosen:
                omissions.append(
                    {
                        "section": "resources",
                        "unit": list(member.coordinates()),
                        "reason": "depth_limit",
                    }
                )
    return chosen, reasons, omissions


def validate_context(data):
    from repo_catalog.domain.p1_context import (
        CoverageClaim,
        CoverageScope,
        FieldCandidate,
    )
    from repo_catalog.domain.p1_core import OID, uuid4_value
    from repo_catalog.domain.production_context import (
        CollectionObservation,
        CoreReference,
        ResourceRelation,
        SourceInventory,
    )

    for row in data["providers"]:
        uuid4_value(row["service_instance_uuidv4"])
    for row in data["repositories"]:
        uuid4_value(row["repository_uuidv4"])
    for row in data["sources"]:
        uuid4_value(row["source_registration_uuidv4"])
        uuid4_value(row["service_instance_uuidv4"])
    for row in data["source_repositories"]:
        uuid4_value(row["source_registration_uuidv4"])
        uuid4_value(row["repository_uuidv4"])
    for row in data["resources"]:
        resource(row)
    for row in data["field_candidates"]:
        FieldCandidate(
            resource(row),
            row["field_name"],
            row["value_json"],
            FieldClock(row["clock_domain"], row["clock_ts_us"]),
            row["provenance_json"],
            row["observed_at_us"],
        )
    for row in data["resource_repository_relations"]:
        relation(row)
    for row in data["repository_mapping_dispositions"]:
        disposition(row)
    transfer_reports(data)
    for row in data["resource_relations"]:
        if row["relation_kind"] != "transfer_event_report":
            ResourceRelation(
                resource(row),
                row["relation_kind"],
                tuple(ResourceKey(*m) for m in json.loads(row["members_json"])),
                row["provenance_json"],
                row["scope_json"],
                row["observed_at_us"],
            )
    for row in data["collections"]:
        CollectionObservation(
            resource(row),
            row["collection_kind"],
            row["provenance_json"],
            row["scope_json"],
            row["observed_at_us"],
            row["terminal_state"],
            tuple(ResourceKey(*m) for m in json.loads(row["members_json"])),
        )
    for row in data["source_inventories"]:
        SourceInventory(
            row["source_registration_uuidv4"],
            row["scope_json"],
            row["observed_at_us"],
            row["coverage_state"],
            row["terminal"],
            tuple(json.loads(row["members_json"])),
            row["provenance_json"],
        )
    for row in data["core_references"]:
        CoreReference(
            resource(row),
            row["role"],
            OID(row["object_format"], row["full_oid"]),
            row["provenance_json"],
        )
    for key in ("coverage_scopes", "coverage_claims", "coverage_proofs"):
        for row in data[key]:
            scope = CoverageScope(
                row["owner_kind"], json.loads(row["owner_coordinates_json"])
            )
            if key != "coverage_scopes":
                CoverageClaim(
                    scope,
                    row["observed_at_us"],
                    row["coverage_state"],
                    row.get("details_json"),
                )


class CorePreflight:
    """Constructor-only sink for the same typed wire decoder used at admission.

    No SQLite connection, retained payload staging or fictitious domain facts.
    The caller separately verifies every native representation and notes proof.
    """

    def sql(self, *_):
        return [(0,)]

    def __getattr__(self, name):
        if not name.startswith("admit_"):
            raise AttributeError(name)

        def check(value, *args, **kwargs):
            from repo_catalog.domain.p1_core import CoreFailure, uuid4_value

            if name == "admit_repository":
                uuid4_value(value)
            if name in ("admit_metadata", "admit_note"):
                uuid4_value(args[0] if name == "admit_metadata" else args[1])
            if (
                name
                in (
                    "admit_claim",
                    "admit_group",
                    "admit_repository_claim",
                    "admit_observation",
                    "admit_notes_claim",
                    "admit_notes_group",
                )
                and value.provenance.qualification != "reported"
            ):
                raise CoreFailure("UNTRUSTED_VERIFICATION", name)
            if hasattr(value, "key"):
                _ = value.key
            if hasattr(value, "validate"):
                value.validate()

        return check


def bound_sections(core, context, scope):
    """Budget complete wire units before emission; facts are never truncated.

    Coverage claim/proof sets, original inventory terminals, and Transfer reports
    share units. Registrations and nominal objects remain independent units.
    """
    groups = {}
    for store, data in (("core", core), ("context", context)):
        if data is None:
            continue
        for section, rows in data.items():
            for index, row in enumerate(rows):
                unit = (store, section, index)
                if section in ("coverage_claims", "coverage_proofs"):
                    unit = (
                        store,
                        "coverage",
                        row["owner_kind"],
                        row["owner_coordinates_json"],
                        row["observed_at_us"],
                        row["coverage_state"],
                    )
                if store == "context" and section == "source_inventories":
                    unit = (
                        store,
                        "inventory",
                        row["source_registration_uuidv4"],
                        row["scope_json"],
                        row["observed_at_us"],
                    )
                if (
                    store == "context"
                    and section == "resource_relations"
                    and row["relation_kind"] == "transfer_event_report"
                ):
                    unit = (
                        store,
                        "transfer",
                        *resource(row).coordinates(),
                        json.dumps(
                            json.loads(row["scope_json"])["clock"],
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        row["provenance_json"],
                    )
                if (
                    store == "context"
                    and section == "resource_repository_relations"
                    and row["relation_kind"].startswith("transfer_")
                ):
                    unit = (
                        store,
                        "transfer",
                        *resource(row).coordinates(),
                        row["clock_json"],
                        row["provenance_json"],
                    )
                if store == "core" and section in (
                    "captures",
                    "notes_claims",
                    "notes_groups",
                    "notes_inventories",
                    "note_roles",
                    "retained_notes",
                ):
                    unit = (
                        store,
                        "capture",
                        row["capture_origin_uuidv4"],
                        row["capture_uuidv4"],
                    )
                if store == "context" and section == "text_bodies":
                    unit = (store, "text", row["sha256"])
                if (
                    store == "context"
                    and section == "field_candidates"
                    and row["field_name"] == "text_body_sha256"
                    and json.loads(row["value_json"]) is not None
                ):
                    unit = (store, "text", json.loads(row["value_json"]))
                if store == "context" and section == "collections":
                    unit = (
                        store,
                        "collection",
                        *resource(row).coordinates(),
                        row["collection_kind"],
                        row["provenance_json"],
                        row["observed_at_us"],
                    )
                groups.setdefault(unit, []).append((store, section, index, row))
    # Merge evidence with its actual terminal so dropping either cannot leave a
    # complete assertion about a newly smaller inventory or collection.
    for key in list(groups):
        if len(key) < 3 or key[1] != "coverage":
            continue
        values = groups[key]
        proofs = [r for _, section, _, r in values if section == "coverage_proofs"]
        targets = set()
        if key[0] == "core" and key[2] == "capture":
            coords = json.loads(key[3])
            targets.add(("core", "capture", *coords[:2]))
        if key[0] == "context":
            for row in proofs:
                if row["proof_kind"] == "source_inventory":
                    targets.add(
                        (
                            "context",
                            "inventory",
                            row["source_registration_uuidv4"],
                            row["scope_json"],
                            row["terminal_observed_at_us"],
                        )
                    )
                else:
                    targets.add(
                        (
                            "context",
                            "collection",
                            *resource(row).coordinates(),
                            row["collection_kind"],
                            row["provenance_json"],
                            row["terminal_observed_at_us"],
                        )
                    )
        for target in targets:
            values.extend(groups.pop(target, []))
    kept = set()
    omissions = []
    units = byte_count = 0
    # Stable foundation-first order. Domain row order within each unit survives.
    priority = {
        "repositories": 0,
        "providers": 0,
        "sources": 1,
        "git_objects": 1,
        "resources": 2,
        "source_repositories": 3,
    }
    ordered = sorted(
        groups.items(),
        key=lambda item: (
            min(priority.get(section, 4) for _, section, _, _ in item[1]),
            str(item[0]),
        ),
    )
    for key, values in ordered:
        size = sum(
            len(
                json.dumps(
                    row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode()
            )
            for _, _, _, row in values
        )
        if units + len(values) > scope.max_units or byte_count + size > scope.max_bytes:
            omissions.append(
                {
                    "section": key[0],
                    "unit_kind": key[1],
                    "reason": "unit_limit"
                    if units + len(values) > scope.max_units
                    else "byte_limit",
                    "unit_count": len(values),
                }
            )
            continue
        units += len(values)
        byte_count += size
        kept.update((store, section, index) for store, section, index, _ in values)
    for store, data in (("core", core), ("context", context)):
        if data is not None:
            for section, rows in data.items():
                data[section] = [
                    row
                    for index, row in enumerate(rows)
                    if (store, section, index) in kept
                ]
    return omissions, {"emitted_units": units, "emitted_payload_bytes": byte_count}
