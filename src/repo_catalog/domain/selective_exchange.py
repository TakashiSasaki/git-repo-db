"""Bounded selection and lossless Context report reconstruction.

This module uses only the frozen I1 contract. It does not fetch Provider data or
assign Repository mappings. Selection never grants Repository permission.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from repo_catalog.domain.exchange import ExchangeError, ExchangeSelectionScope

if TYPE_CHECKING:
    from repo_catalog.domain.p1_context import (
        MappingDisposition,
        ResourceKey,
        ResourceRepositoryRelation,
        TransferEventReport,
    )


def resource(row: dict) -> ResourceKey:
    from repo_catalog.domain.p1_context import ResourceKey

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
    from repo_catalog.domain.p1_context import FieldClock, ResourceRepositoryRelation

    return ResourceRepositoryRelation(
        resource(row),
        row["relation_kind"],
        FieldClock.from_json(row["clock_json"]),
        row["target_json"],
        row["provenance_json"],
        row["observed_at_us"],
        row.get("event_report_members_json"),
        row.get("event_report_scope_json"),
    )


def disposition(row: dict) -> MappingDisposition:
    from repo_catalog.domain.p1_context import (
        FieldClock,
        MappingClaimKey,
        MappingDisposition,
    )

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
    """Reconstruct only complete originals, never Event-derived Parent evidence."""
    from repo_catalog.domain.p1_context import (
        EventReportKey,
        FieldClock,
        TransferEventReport,
    )
    from repo_catalog.domain.parent_report import ParentObservation, ParentReportKey

    parents = {}
    for row in data["resource_relations"]:
        if row["relation_kind"] == "parent":
            parent = ParentObservation(
                ParentReportKey(
                    resource(row),
                    row["members_json"],
                    row["provenance_json"],
                    row["scope_json"],
                ),
                row["observed_at_us"],
            )
            if parent.report_key in parents and parents[parent.report_key] != parent:
                raise ExchangeError("IMMUTABLE_REPLAY_CONFLICT", "parent")
            parents[parent.report_key] = parent
    endpoints = [
        relation(r)
        for r in data["resource_repository_relations"]
        if r["relation_kind"].startswith("transfer_")
    ]
    result = []
    for row in data["resource_relations"]:
        if row["relation_kind"] != "transfer_event_report":
            continue
        scope = json.loads(row["scope_json"])
        parent_fields = (
            "parent_members_json",
            "parent_provenance_json",
            "parent_scope_json",
        )
        if type(scope) is not dict or any(
            type(scope.get(k)) is not str for k in parent_fields
        ):
            raise ExchangeError("INCOMPLETE_ORIGINAL_REPORT", "transfer_event_report")
        parent_key = ParentReportKey(resource(row), *(scope[k] for k in parent_fields))
        if parent_key not in parents:
            raise ExchangeError("MISSING_DEPENDENCY", "original_parent_report")
        clock = FieldClock.from_json(
            json.dumps(
                scope["clock"],
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
                parent_report=parents[parent_key],
            )
        )
    original_reports = {}
    for report in result:
        payload = (report.scope_json, report.members_json, report.observed_at_us)
        if (
            report.report_key in original_reports
            and original_reports[report.report_key] != payload
        ):
            raise ExchangeError("IMMUTABLE_REPLAY_CONFLICT", "transfer_event_report")
        original_reports[report.report_key] = payload
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
        for name in ("retained_metadata", "ref_retained_notes"):
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
        from repo_catalog.domain.p1_core import _performed

        retained = []
        for index, row in enumerate(data[key]):
            _performed("metadata_units", 1)
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
        # Ref keys are an independent selection route. Event dependencies are
        # whole original occurrences; an object-only request never discovers a
        # rootless observation through an unrelated event member.
        from repo_catalog.domain.p1_core import _performed

        refs = {
            (r["observation_origin_uuidv4"], r["ref_observation_uuidv7"]): r
            for r in core["ref_observations"]
            if allowed(r["repository_uuidv4"])
        }
        if scope.ref_observation_keys is None and scope.object_oids is None:
            selected_refs = set(refs)
        else:
            selected_refs = {
                k.key for k in (scope.ref_observation_keys or ()) if k.key in refs
            }
            if scope.object_oids is not None:
                roots = {o.key for o in scope.object_oids}
                for row in core["ref_observation_claims"]:
                    _performed("metadata_units", 1)
                    key = (
                        row["observation_origin_uuidv4"],
                        row["ref_observation_uuidv7"],
                    )
                    if (
                        row["root_oid"] is not None
                        and tuple(row["root_oid"]) in roots
                        and key in refs
                    ):
                        selected_refs.add(key)
        if scope.notes_refs is not None:
            names = set(scope.notes_refs)
            selected_refs = {
                key
                for key in selected_refs
                if bytes.fromhex(refs[key]["ref_name_hex"]).decode(
                    "utf-8", "surrogateescape"
                )
                in names
            }
        events = {
            (r["observation_origin_uuidv4"], r["enumeration_uuidv7"]): r
            for r in core["ref_enumeration_observations"]
            if allowed(r["repository_uuidv4"])
        }
        event_links = {}
        links_by_ref = {}
        for row in core["ref_enumeration_links"]:
            _performed("metadata_units", 1)
            event_key = (row["enumeration_origin_uuidv4"], row["enumeration_uuidv7"])
            ref_key = (row["observation_origin_uuidv4"], row["ref_observation_uuidv7"])
            event_links.setdefault(event_key, []).append(row)
            links_by_ref.setdefault(ref_key, set()).add(event_key)
        selected_events = set()
        pending_refs = list(selected_refs)
        expand = scope.ref_observation_keys is not None or scope.object_oids is None
        while pending_refs:
            ref_key = pending_refs.pop()
            for event_key in links_by_ref.get(ref_key, ()):
                _performed("metadata_units", 1)
                if event_key in selected_events or event_key not in events:
                    continue
                linked = event_links[event_key]
                members = {
                    (r["observation_origin_uuidv4"], r["ref_observation_uuidv7"])
                    for r in linked
                }
                if (
                    len(linked) != events[event_key]["link_count"]
                    or not members <= refs.keys()
                ):
                    continue
                if not expand and not members <= selected_refs:
                    continue
                selected_events.add(event_key)
                if expand:
                    new = members - selected_refs
                    selected_refs.update(new)
                    pending_refs.extend(new)
        if (
            scope.object_oids is None
            and scope.ref_observation_keys is None
            and scope.notes_refs is None
        ):
            selected_events.update(
                key
                for key, row in events.items()
                if row["link_count"] == 0 and not event_links.get(key)
            )
        retain(
            core,
            "ref_observations",
            lambda r: (
                (r["observation_origin_uuidv4"], r["ref_observation_uuidv7"])
                in selected_refs
            ),
            "ref_observation_not_selected",
        )
        retain(
            core,
            "ref_observation_claims",
            lambda r: (
                (r["observation_origin_uuidv4"], r["ref_observation_uuidv7"])
                in selected_refs
            ),
            "ref_observation_not_selected",
        )
        ref_claims = {
            (
                r["observation_origin_uuidv4"],
                r["ref_observation_uuidv7"],
                r["provenance_json"],
            )
            for r in core["ref_observation_claims"]
        }
        for row in core["ref_observation_claims"]:
            for field in (
                "direct_target_oid",
                "resolved_target_oid",
                "peeled_target_oid",
                "root_oid",
            ):
                if row[field] is not None and tuple(row[field]) in available:
                    chosen.add(tuple(row[field]))

        def ref_claim_selected(row):
            return (
                row["observation_origin_uuidv4"],
                row["ref_observation_uuidv7"],
                row["ref_claim_provenance_json"],
            ) in ref_claims

        for key in (
            "notes_mapping_claims",
            "notes_mapping_evidence",
            "ref_retained_notes",
        ):
            for row in core[key]:
                _performed("metadata_units", 1)
                if ref_claim_selected(row):
                    for oid in (
                        row["root_oid"],
                        row["annotated_object_oid"],
                        row["note_oid"],
                    ):
                        if (row["object_format"], oid) in available:
                            chosen.add((row["object_format"], oid))
        for row in core["notes_mapping_groups"]:
            _performed("metadata_units", 1)
            if ref_claim_selected(row):
                for target, note, _ in json.loads(row["membership_json"]):
                    for oid in (target, note):
                        if (row["object_format"], oid) in available:
                            chosen.add((row["object_format"], oid))
        for key in (
            "notes_mapping_claims",
            "notes_mapping_evidence",
            "ref_retained_notes",
        ):
            retain(
                core,
                key,
                lambda r: (
                    ref_claim_selected(r)
                    and all(
                        (r["object_format"], oid) in chosen
                        for oid in (
                            r["root_oid"],
                            r["annotated_object_oid"],
                            r["note_oid"],
                        )
                    )
                ),
                "claim_or_mapping_dependency_not_selected",
            )
        retain(
            core,
            "notes_mapping_groups",
            lambda r: (
                ref_claim_selected(r)
                and (r["object_format"], r["root_oid"]) in chosen
                and all(
                    (r["object_format"], oid) in chosen
                    for target, note, _ in json.loads(r["membership_json"])
                    for oid in (target, note)
                )
            ),
            "whole_mapping_group_dependency_not_selected",
        )
        # A removed claim or member also removes its entire event.
        selected_events = {
            key
            for key in selected_events
            if all(
                (
                    r["observation_origin_uuidv4"],
                    r["ref_observation_uuidv7"],
                    r["claim_provenance_json"],
                )
                in ref_claims
                for r in event_links.get(key, ())
            )
        }
        retain(
            core,
            "ref_enumeration_observations",
            lambda r: (
                (r["observation_origin_uuidv4"], r["enumeration_uuidv7"])
                in selected_events
            ),
            "whole_enumeration_not_selected",
        )
        retain(
            core,
            "ref_enumeration_links",
            lambda r: (
                (r["enumeration_origin_uuidv4"], r["enumeration_uuidv7"])
                in selected_events
            ),
            "whole_enumeration_not_selected",
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
        ):
            retain(
                core,
                key,
                lambda r: allowed(r["repository_uuidv4"]),
                "repository_not_selected_or_permitted",
            )
        denied_claims = set()

        def core_scope_selected(r):
            coords = json.loads(r["owner_coordinates_json"])
            if r["owner_kind"] == "repository":
                return allowed(coords[0])
            if r["owner_kind"] == "ref_observation":
                return tuple(coords[:2]) in selected_refs
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
            "coverage_proofs",
            lambda r: (
                (
                    r["owner_kind"],
                    r["owner_coordinates_json"],
                    r["observed_at_us"],
                    r["coverage_state"],
                )
                not in denied_claims
            ),
            "whole_coverage_proof_set_not_selected",
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
        from repo_catalog.domain.p1_core import encode

        original_groups = {encode(row) for row in core["notes_mapping_groups"]}
        terminals = {
            (
                r["owner_kind"],
                r["owner_coordinates_json"],
                r["observed_at_us"],
                r["coverage_state"],
            )
            for r in core["coverage_claims"]
        }
        retain(
            core,
            "ref_coverage_proofs",
            lambda r: (
                (
                    r["owner_kind"],
                    r["owner_coordinates_json"],
                    r["observed_at_us"],
                    r["coverage_state"],
                )
                in terminals
                and r["group_json"] in original_groups
            ),
            "whole_ref_coverage_proof_dependency_not_selected",
        )
    if context is not None:
        from repo_catalog.domain.p1_context import (
            EventReportKey,
            FieldClock,
            ResourceKey,
        )

        original_terminals = [
            ("source_inventory", r) for r in context["source_inventories"]
        ] + [("collection", r) for r in context["collections"]]
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
        denied_resources = {p.event_resource for p in reports if p.report_key in denied}
        chosen.difference_update(denied_resources)
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
        omissions.extend(preserve_context_coverage(context, original_terminals))

        def owner_selected(row):
            coordinates = json.loads(row["owner_coordinates_json"])
            if row["owner_kind"] == "repository":
                return allowed(coordinates[0])
            if row["owner_kind"] == "source":
                return coordinates[0] in source_ids and allowed(coordinates[1])
            if row["owner_kind"] == "source_inventory":
                return coordinates[0] in source_ids
            return ResourceKey(*coordinates[:3]) in chosen

        for key in ("coverage_scopes", "coverage_claims", "coverage_proofs"):
            retain(context, key, owner_selected, "coverage_owner_not_selected")
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
    from repo_catalog.domain.p1_context import ResourceKey

    """Cycle-safe traversal over actual resources only, with explicit depth."""
    available = {ResourceKey(*r[:3]) for r in rows}
    chosen = (
        available.copy()
        if scope.resource_keys is None
        else set(scope.resource_keys).intersection(available)
    )
    reasons = []
    omissions = []
    edges = {r: set() for r in available}
    # Namespace is identification, never an inferred report/dependency edge.
    # Identification declarations never add traversal edges.
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


def preflight_i2_resources(resources):
    from repo_catalog.domain.resource_identification import ResourceIdentification
    from repo_catalog.domain.resource_stage import UnsupportedIdentificationStage

    for item in resources:
        if isinstance(item, dict):
            kind = item.get("resource_kind")
            if kind in {"review", "thread", "comment", "document"}:
                try:
                    ResourceIdentification.from_wire(item)
                except (ValueError, TypeError) as error:
                    raise UnsupportedIdentificationStage() from error


def preflight_i2_context(data):
    from repo_catalog.domain.resource_stage import preflight_transfer

    preflight_transfer(data)
    preflight_i2_resources(data["resources"])


def validate_context(data):
    from repo_catalog.domain.p1_context import (
        CoverageClaim,
        CoverageScope,
        FieldCandidate,
        FieldClock,
        ResourceKey,
        validate_provider_repository_scope,
    )
    from repo_catalog.domain.p1_core import OID, uuid4_value
    from repo_catalog.domain.production_context import (
        CollectionObservation,
        CoreReference,
        ResourceRelation,
        SourceInventory,
        validate_reported_core_reference,
    )

    for row in data["providers"]:
        uuid4_value(row["service_instance_uuidv4"])
        if not row["provider_kind"]:
            raise ExchangeError("INVALID_PROVIDER_KIND", "providers")
    for row in data["repositories"]:
        uuid4_value(row["repository_uuidv4"])
    for row in data["sources"]:
        uuid4_value(row["source_registration_uuidv4"])
        uuid4_value(row["service_instance_uuidv4"])
    for row in data["source_repositories"]:
        uuid4_value(row["source_registration_uuidv4"])
        uuid4_value(row["repository_uuidv4"])
    from repo_catalog.domain.resource_identification import ResourceIdentification

    for row in data["resources"]:
        if row.get("resource_kind") not in {
            "review",
            "thread",
            "comment",
            "document",
        }:
            ResourceIdentification.from_wire(row)
    for row in data["field_candidates"]:
        candidate = FieldCandidate(
            resource(row),
            row["field_name"],
            row["value_json"],
            FieldClock(row["clock_domain"], row["clock_ts_us"]),
            row["provenance_json"],
            row["observed_at_us"],
        )
        validate_reported_core_reference(candidate)
    for row in data["resource_repository_relations"]:
        relation(row)
    for row in data["repository_mapping_dispositions"]:
        disposition(row)
    transfer_reports(data)
    for row in data["resource_relations"]:
        if row["relation_kind"] != "transfer_event_report":
            report = ResourceRelation(
                resource(row),
                row["relation_kind"],
                tuple(ResourceKey(*m) for m in json.loads(row["members_json"])),
                row["provenance_json"],
                row["scope_json"],
                row["observed_at_us"],
            )
            if report.relation_kind == "provider_repository_roles":
                validate_provider_repository_scope(
                    report.resource,
                    report.members,
                    report.provenance_json,
                    report.scope_json,
                    report.observed_at_us,
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
        inventory = SourceInventory(
            row["source_registration_uuidv4"],
            row["scope_json"],
            row["observed_at_us"],
            row["coverage_state"],
            row["terminal"],
            tuple(json.loads(row["members_json"])),
            row["provenance_json"],
        )
        for repository in inventory.repositories:
            uuid4_value(repository)
        if inventory.members_json != row["members_json"]:
            raise ExchangeError("NONCANONICAL_INVENTORY", "source_inventories")
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

    validate_context_proofs(data)
    validate_context_bindings(
        data,
        {
            row["source_registration_uuidv4"]: row["service_instance_uuidv4"]
            for row in data["sources"]
        },
    )


def validate_context_bindings(data, source_services):
    """Check modeled parent and service assertions without manufacturing facts."""
    from repo_catalog.domain.p1_context import ResourceKey
    from repo_catalog.domain.resource_identification import ResourceIdentification

    identifications = {}
    for row in data["resources"]:
        if row.get("resource_kind") in {"review", "thread", "comment", "document"}:
            try:
                identifications[resource(row)] = ResourceIdentification.from_wire(row)
            except (ValueError, TypeError):
                pass
        else:
            identifications[resource(row)] = ResourceIdentification.from_wire(row)
    from repo_catalog.domain.context_admission import extract_provenance_sources

    for section, rows in data.items():
        for row in rows:
            service = row.get("service_instance_uuidv4")
            if service is None and "source_registration_uuidv4" in row:
                service = source_services.get(row["source_registration_uuidv4"])
            if service is None and "owner_kind" in row:
                coordinates = json.loads(row["owner_coordinates_json"])
                if row["owner_kind"] in {"resource", "field", "collection"}:
                    service = coordinates[0]
                elif row["owner_kind"] in {"source", "source_inventory"}:
                    service = source_services.get(coordinates[0])
            for name, value in row.items():
                if value is not None and (
                    name.endswith("provenance_json") or name == "scope_json"
                ):
                    for source in extract_provenance_sources(value):
                        if (
                            service is not None
                            and source in source_services
                            and source_services[source] != service
                        ):
                            raise ExchangeError("SOURCE_SERVICE", section)
    child_kinds = {
        "reviews": "review",
        "comments": "comment",
        "threads": "thread",
        "documents": "document",
    }
    for section, kind_field in (
        ("resource_relations", "relation_kind"),
        ("collections", "collection_kind"),
    ):
        for row in data[section]:
            owner = resource(row)
            child_kind = child_kinds.get(row[kind_field])
            if child_kind is not None:
                for coordinates in json.loads(row["members_json"]):
                    member = ResourceKey(*coordinates)
                    if (
                        member.resource_kind != child_kind
                        or member.service_instance_uuidv4
                        != owner.service_instance_uuidv4
                        or member not in identifications
                        or (
                            identifications[member].identifier_namespace_kind,
                            identifications[member].identifier_namespace_id,
                        )
                        != owner.coordinates()[1:]
                    ):
                        raise ExchangeError("MEMBER_OWNER", section)
            if section == "collections":
                scope = json.loads(row["scope_json"])
                if isinstance(scope, dict):
                    if (
                        scope.get(
                            "service_instance_uuidv4", owner.service_instance_uuidv4
                        )
                        != owner.service_instance_uuidv4
                    ):
                        raise ExchangeError("COLLECTION_SERVICE", section)
                    source = scope.get("source_registration_uuidv4")
                    if (
                        source in source_services
                        and source_services[source] != owner.service_instance_uuidv4
                    ):
                        raise ExchangeError("SOURCE_SERVICE", section)
    for row in data["source_inventories"]:
        scope = json.loads(row["scope_json"])
        source = row["source_registration_uuidv4"]
        if (
            source in source_services
            and isinstance(scope, dict)
            and scope.get("service_instance_uuidv4", source_services[source])
            != source_services[source]
        ):
            raise ExchangeError("SOURCE_SERVICE", "source_inventories")


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


def bound_sections(core, context, scope, *, work=None):
    """Budget complete wire units before emission; facts are never truncated.

    Coverage claim/proof sets, original inventory terminals, and Transfer reports
    share units. Registrations and nominal objects remain independent units.
    """
    groups = {}
    from repo_catalog.domain.p1_core import _performed

    for store, data in (("core", core), ("context", context)):
        if data is None:
            continue
        for section, rows in data.items():
            for index, row in enumerate(rows):
                _performed("metadata_units", 1)
                unit = (store, section, index)
                if section in (
                    "coverage_claims",
                    "coverage_proofs",
                    "ref_coverage_proofs",
                ):
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
                        "source_inventory",
                        row["source_registration_uuidv4"],
                        row["scope_json"],
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
                if store == "core" and section in ():
                    unit = (
                        store,
                        "capture",
                        row["capture_origin_uuidv4"],
                        row["capture_uuidv4"],
                    )
                if store == "core" and section in (
                    "ref_observations",
                    "ref_observation_claims",
                ):
                    unit = (
                        store,
                        "ref-observation",
                        row["observation_origin_uuidv4"],
                        row["ref_observation_uuidv7"],
                    )
                if store == "core" and section in (
                    "ref_enumeration_observations",
                    "ref_enumeration_links",
                ):
                    unit = (
                        store,
                        "ref-enumeration",
                        row.get(
                            "enumeration_origin_uuidv4",
                            row.get("observation_origin_uuidv4"),
                        ),
                        row["enumeration_uuidv7"],
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
                    )
                groups.setdefault(unit, []).append((store, section, index, row))
    # Union all proof/claim groups with every terminal in their logical slot.
    # Retaining one alternative cannot hide a competing current terminal.
    parent = {key: key for key in groups}

    def root(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    for key, values in groups.items():
        if key[0:2] == ("core", "ref-enumeration"):
            for _, section, _, row in values:
                if section == "ref_enumeration_links":
                    target = (
                        "core",
                        "ref-observation",
                        row["observation_origin_uuidv4"],
                        row["ref_observation_uuidv7"],
                    )
                    if target in parent:
                        parent[root(target)] = root(key)
        if len(key) < 3 or key[1] != "coverage":
            continue
        targets = set()
        if key[0] == "core" and key[2] == "ref_observation":
            targets.add(("core", "ref-observation", *json.loads(key[3])[:2]))
        if key[0] == "context":
            for _, section, _, row in values:
                if section == "coverage_proofs":
                    targets.add(("context", *terminal_slot(row, row["proof_kind"])))
        for target in targets:
            if target in parent:
                parent[root(target)] = root(key)
    combined = {}
    for key, values in groups.items():
        combined.setdefault(root(key), []).extend(values)
    groups = combined
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

    def row_size(row):
        if work is None:
            return len(
                json.dumps(
                    row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode()
            )
        from repo_catalog.domain.exchange import _bounded_json

        def spend(amount):
            work.require("metadata_units", amount)
            work.charge("metadata_units", amount)

        _, upper = _bounded_json(row, spend=spend)
        work.require("input_bytes", upper)
        try:
            actual = len(
                json.dumps(
                    row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode()
            )
            if actual > upper:
                raise ExchangeError(
                    "INPUT_LIMIT", "selection", "row exceeded reserved encoding"
                )
        except BaseException:
            abandon = getattr(work, "abandon", None)
            if abandon is not None:
                abandon("input_bytes")
            else:
                work.charge("input_bytes", upper)
            raise
        work.charge("input_bytes", actual)
        return actual

    for key, values in ordered:
        size = sum(row_size(row) for _, _, _, row in values)
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


def terminal_key(row, kind):
    """Full original terminal FK, not its clock-only lookup prefix."""
    proof = "proof_kind" in row
    at = row["terminal_observed_at_us"] if proof else row["observed_at_us"]
    if kind == "source_inventory":
        return (
            kind,
            row["source_registration_uuidv4"],
            row["scope_json"],
            at,
            row["terminal_state"] if proof else row["coverage_state"],
            row["terminal"],
            row["members_json"],
            row["provenance_json"],
        )
    return (
        kind,
        *resource(row).coordinates(),
        row["collection_kind"],
        row["provenance_json"],
        at,
        row["terminal_state"],
        row["members_json"],
    )


def validate_context_proofs(data):
    claims = {
        (
            r["owner_kind"],
            r["owner_coordinates_json"],
            r["observed_at_us"],
            r["coverage_state"],
        )
        for r in data["coverage_claims"]
    }
    terminals = {
        terminal_key(r, "source_inventory") for r in data["source_inventories"]
    } | {terminal_key(r, "collection") for r in data["collections"]}
    collection_scopes = {}
    for row in data["collections"]:
        key = (
            *resource(row).coordinates(),
            row["collection_kind"],
            row["provenance_json"],
        )
        if key in collection_scopes and collection_scopes[key] != row["scope_json"]:
            raise ExchangeError("IMMUTABLE_COLLECTION_SCOPE", "context")
        collection_scopes[key] = row["scope_json"]
    for row in data["coverage_proofs"]:
        from repo_catalog.domain.time import validate_required_observation_us

        validate_required_observation_us(row["terminal_observed_at_us"])
        if row["proof_kind"] not in ("source_inventory", "collection"):
            raise ExchangeError("INVALID_COVERAGE_PROOF", "proof_kind")
        if terminal_key(row, row["proof_kind"]) not in terminals:
            raise ExchangeError(
                "INVALID_COVERAGE_PROOF",
                "original_terminal",
                "proof must match every original immutable terminal field",
            )
        if (
            row["owner_kind"],
            row["owner_coordinates_json"],
            row["observed_at_us"],
            row["coverage_state"],
        ) not in claims:
            raise ExchangeError("INVALID_COVERAGE_PROOF", "original_claim")
        if row["terminal_observed_at_us"] > row["observed_at_us"] or (
            row["coverage_state"] == "complete" and row["terminal_state"] != "complete"
        ):
            raise ExchangeError("INVALID_COVERAGE_PROOF", "terminal_state")
        if row["proof_kind"] == "source_inventory":
            coords = json.loads(row["owner_coordinates_json"])
            if (
                row["terminal"] is not True
                or row["owner_kind"] != "source_inventory"
                or coords[:2] != [row["source_registration_uuidv4"], row["scope_json"]]
            ):
                raise ExchangeError("INVALID_COVERAGE_PROOF", "source_scope")
        else:
            from repo_catalog.domain.p1_context import CoverageScope

            coordinates = json.loads(row["owner_coordinates_json"])
            owner = CoverageScope(row["owner_kind"], coordinates)
            slot = (
                *resource(row).coordinates(),
                row["collection_kind"],
                row["provenance_json"],
            )
            attributes = json.loads(collection_scopes[slot])
            if type(attributes) is not dict:
                raise ExchangeError("INVALID_COVERAGE_PROOF", "collection_scope")
            kind = attributes.get("coverage_kind", row["collection_kind"])
            if owner.base_coverage_kind != kind:
                raise ExchangeError("INVALID_COVERAGE_PROOF", "coverage_kind")
            if owner.owner_kind == "repository":
                valid = attributes.get("repository_uuidv4") == coordinates[0]
            elif owner.owner_kind == "source":
                valid = (
                    attributes.get("source_registration_uuidv4") == coordinates[0]
                    and attributes.get("repository_uuidv4") == coordinates[1]
                )
            elif owner.owner_kind in ("resource", "field", "collection"):
                valid = tuple(coordinates[:3]) == resource(row).coordinates()
                if owner.owner_kind == "field":
                    valid = valid and attributes.get("field_name") == coordinates[3]
                if owner.owner_kind == "collection":
                    valid = valid and coordinates[3:5] == [
                        row["collection_kind"],
                        row["provenance_json"],
                    ]
            else:
                valid = False
            if not valid:
                raise ExchangeError("INVALID_COVERAGE_PROOF", "owner_scope")


def terminal_slot(row, kind):
    if kind == "source_inventory":
        return (kind, row["source_registration_uuidv4"], row["scope_json"])
    return (
        kind,
        *resource(row).coordinates(),
        row["collection_kind"],
        row["provenance_json"],
    )


def preserve_context_coverage(data, original):
    """Withhold completeness if selection removes relevant terminal alternatives."""
    remaining = {
        terminal_key(r, "source_inventory") for r in data["source_inventories"]
    } | {terminal_key(r, "collection") for r in data["collections"]}
    lost_slots = {
        terminal_slot(r, kind)
        for kind, r in original
        if terminal_key(r, kind) not in remaining
    }

    def claim_key(row):
        return (
            row["owner_kind"],
            row["owner_coordinates_json"],
            row["observed_at_us"],
            row["coverage_state"],
        )

    denied = {
        claim_key(r)
        for r in data["coverage_proofs"]
        if terminal_key(r, r["proof_kind"]) not in remaining
        or terminal_slot(r, r["proof_kind"]) in lost_slots
    }
    omissions = []
    for key in ("coverage_proofs", "coverage_claims"):
        kept = []
        for index, row in enumerate(data[key]):
            if claim_key(row) in denied:
                omissions.append(
                    {
                        "section": key,
                        "unit_index": index,
                        "reason": "whole_coverage_terminal_set_not_selected",
                    }
                )
            else:
                kept.append(row)
        data[key] = kept
    return omissions
