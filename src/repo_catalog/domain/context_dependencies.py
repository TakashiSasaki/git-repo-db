"""Pure finite Context dependency planning; selection supplies no authorization.

The input is a decoded, validated v5 Context section. Plans contain independent
registrations and whole original reports. They neither issue receiver grants nor
persist withheld payloads; callers must still perform current admission checks.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass

from repo_catalog.domain.context_admission import extract_provenance_sources
from repo_catalog.domain.exchange import (
    CONTEXT_SECTION_KEYS,
    MAX_ELEMENTS,
    ExchangeError,
    ExchangeSelectionScope,
    _bounded_json,
)
from repo_catalog.domain.exchange_rows import IDENTITY_KEYS
from repo_catalog.domain.p1_context import (
    EventReportKey,
    FieldClock,
    ProviderRepositoryScope,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.selective_exchange import (
    explicit_scope,
    relation,
    resource,
    terminal_slot,
)


@dataclass(frozen=True)
class ContextSemanticUnit:
    key: tuple
    rows: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class DependencyOmission:
    """Input-row coordinates are diagnostic offsets, never domain identities.

    Withheld original report bodies/keys are not copied into diagnostics.
    """

    unit_key: tuple
    section: str
    reason: str


@dataclass(frozen=True)
class ContextDependencyPlan:
    context: dict
    selected_units: tuple[ContextSemanticUnit, ...]
    omissions: tuple[DependencyOmission, ...]
    work_units: int
    emitted_units: int
    emitted_payload_bytes: int
    selected_resources: frozenset[ResourceKey]


def plan_context_dependencies(
    data: dict,
    scope: ExchangeSelectionScope,
    *,
    prior_work: int = 0,
    max_nodes: int | None = None,
    max_edges: int | None = None,
) -> ContextDependencyPlan:
    """Select whole units within inclusive limits, retaining original row order.

    ``prior_work`` carries actual work already spent by the same request. Work
    reserves visited values, queued references and examined Unicode codepoints
    before scanning/parsing, then row/member/dependency checks, including refused
    and repeated work. A failed reservation costs one fixed unit and performs no
    refused operation; thus a stop adds at most one unit to the remaining budget.
    Work is not refunded on omission.
    Optional node/edge limits may tighten the outer finite element ceiling.
    Depth counts explicit Resource member edges, never namespace coordinates.
    """
    if not isinstance(scope, ExchangeSelectionScope):
        raise ExchangeError("INVALID_SELECTION", "planner")
    explicit_scope(scope)
    for value in (prior_work, max_nodes, max_edges):
        if value is not None and (
            type(value) is not int or not 0 <= value <= 100000000
        ):
            raise ExchangeError("INVALID_SELECTION", "planner_bounds")
    if any(
        value is not None and value > MAX_ELEMENTS for value in (max_nodes, max_edges)
    ):
        raise ExchangeError("INVALID_SELECTION", "planner_hard_caps")
    node_cap = min(
        MAX_ELEMENTS, scope.max_units, MAX_ELEMENTS if max_nodes is None else max_nodes
    )
    edge_cap = min(MAX_ELEMENTS, MAX_ELEMENTS if max_edges is None else max_edges)
    if type(data) is not dict or set(data) != set(CONTEXT_SECTION_KEYS):
        raise ExchangeError("MALFORMED_SECTION", "context")
    if any(type(rows) is not list for rows in data.values()):
        raise ExchangeError("MALFORMED_SECTION", "context")
    # Fixed-envelope inspection only: len(list) never visits or queues rows.
    # Root, section keys/lists and even one value per row already establish this
    # hard lower bound. Preserve INPUT_LIMIT precedence without an input scan,
    # including when no configurable work remains.
    if 1 + 2 * len(data) + sum(map(len, data.values())) > MAX_ELEMENTS:
        raise ExchangeError("INPUT_LIMIT", "context", "JSON elements")
    work = prior_work

    class WorkLimit(Exception):
        pass

    def spend(amount=1):
        nonlocal work
        # One fixed unit records the failed reservation; the refused operation
        # does not run and is not charged as if it had. No retry refunds work.
        if amount > scope.max_work - work:
            work += 1
            raise WorkLimit
        work += amount
        return True

    empty = {key: [] for key in CONTEXT_SECTION_KEYS}
    omissions: list[DependencyOmission] = []

    def result(context=empty, selected=(), units=0, bytes_=0, chosen=frozenset()):
        return ContextDependencyPlan(
            context,
            tuple(selected),
            tuple(omissions),
            work,
            units,
            bytes_,
            frozenset(chosen),
        )

    if not scope.include_context:
        omissions.append(
            DependencyOmission(("context",), "context", "section_not_selected")
        )
        return result()
    try:
        # The same hard-cap/cycle/identity scanner as the codec, with request
        # reservations before traversal, queue growth, escaping and embedded
        # parsing. The element count is distinct from character-inclusive work.
        _bounded_json(data, root="context", spend=spend)
    except WorkLimit:
        omissions.append(DependencyOmission(("context",), "context", "work_limit"))
        return result()

    completed_rows: dict[tuple[str, int], dict] = {}
    completed_units: dict[tuple, ContextSemanticUnit] = {}
    completed_sizes: dict[tuple[str, int], int] = {}
    completed_resources: set[ResourceKey] = set()

    def charge_value(value):
        # One unit per visited value plus Unicode codepoints examined in strings.
        # Charge before queue extension/string serialization, including retries.
        pending = [value]
        while pending:
            spend()
            item = pending.pop()
            if type(item) is dict:
                spend(len(item))
                pending.extend(item.keys())
                pending.extend(item.values())
            elif type(item) in (tuple, list):
                spend(len(item))
                pending.extend(item)
            elif type(item) is str:
                spend(len(item))

    def read_json(text):
        # Already codec-validated text: character work is reserved before the
        # decoder allocates any embedded arrays/objects.
        spend(1 + len(text))
        return json.loads(text)

    def checked_resource(row):
        for name in (
            "service_instance_uuidv4",
            "resource_kind",
            "provider_resource_id",
        ):
            spend(1 + len(row[name]))
        return resource(row)

    def checked_relation(row):
        charge_value(row)
        return relation(row)

    def encoded_key(key):
        charge_value(key)
        return canonical(key)

    def completed_result():
        context = {section: [] for section in CONTEXT_SECTION_KEYS}
        for (section, _), row in sorted(completed_rows.items()):
            context[section].append(row)
        units = tuple(sorted(completed_units.values(), key=lambda unit: min(unit.rows)))
        return result(
            context,
            units,
            len(completed_rows),
            sum(completed_sizes.values()),
            completed_resources,
        )

    def run():
        # Resource identity is validated by the existing authority. Namespace has no
        # registration dependency, permitting complete children before their parents.
        available = {checked_resource(row) for row in data["resources"]}
        seeds = (
            available
            if scope.resource_keys is None
            else available.intersection(scope.resource_keys)
        )
        chosen: set[ResourceKey] = set()
        blocked: dict[ResourceKey, str] = {}
        for key in sorted(seeds, key=lambda key: key.coordinates()):
            if not spend():
                blocked[key] = "work_limit"
            elif len(chosen) >= node_cap:
                blocked[key] = "node_limit"
            else:
                chosen.add(key)
        edges: dict[ResourceKey, set[ResourceKey]] = {}
        edge_count = 0
        blocked_rows: dict[tuple[str, int], str] = {}
        for section in ("resource_relations", "collections"):
            for index, row in enumerate(data[section]):
                owner = checked_resource(row)
                for coordinates in read_json(row["members_json"]):
                    target = ResourceKey(*coordinates)
                    if not spend():
                        blocked.setdefault(target, "work_limit")
                        blocked_rows[section, index] = "work_limit"
                        continue
                    if edge_count >= edge_cap:
                        blocked.setdefault(target, "edge_limit")
                        blocked_rows[section, index] = "edge_limit"
                        continue
                    edge_count += 1
                    edges.setdefault(owner, set()).add(target)
        # Mapping support is an explicit actual reference, not a guessed native edge.
        for index, row in enumerate(data["resource_repository_relations"]):
            rel = checked_relation(row)
            if rel.embedded_support is not None:
                target = rel.embedded_support.provider_repository
                if not spend():
                    blocked.setdefault(target, "work_limit")
                    blocked_rows["resource_repository_relations", index] = "work_limit"
                elif edge_count >= edge_cap:
                    blocked.setdefault(target, "edge_limit")
                    blocked_rows["resource_repository_relations", index] = "edge_limit"
                else:
                    edge_count += 1
                    edges.setdefault(rel.resource, set()).add(target)
        frontier = chosen.copy()
        for depth in range(scope.max_depth + 1):
            added = set()
            for owner in sorted(frontier, key=lambda key: key.coordinates()):
                for target in sorted(
                    edges.get(owner, ()), key=lambda key: key.coordinates()
                ):
                    if not spend():
                        blocked.setdefault(target, "work_limit")
                    elif target in chosen:
                        continue
                    elif target not in available:
                        blocked.setdefault(target, "missing_dependency")
                    elif depth == scope.max_depth:
                        blocked.setdefault(target, "depth_limit")
                    elif len(chosen) >= node_cap:
                        blocked.setdefault(target, "node_limit")
                    else:
                        chosen.add(target)
                        added.add(target)
            frontier = added
            if not frontier:
                break

        groups: dict[tuple, list[tuple[str, int]]] = {}
        lookup: dict[tuple[str, int], tuple] = {}
        for section, rows in data.items():
            for index, row in enumerate(rows):
                charge_value(row)
                columns = IDENTITY_KEYS["context"].get(section, tuple(sorted(row)))
                key = (section, *(row[column] for column in columns))
                if section == "resources":
                    key = (section, *checked_resource(row).coordinates())
                elif section == "collections":
                    key = terminal_slot(row, "collection")
                elif section == "source_inventories":
                    key = terminal_slot(row, "source_inventory")
                elif section in {"coverage_claims", "coverage_proofs"}:
                    key = (
                        "coverage",
                        row["owner_kind"],
                        row["owner_coordinates_json"],
                        row["observed_at_us"],
                        row["coverage_state"],
                    )
                elif (
                    section == "resource_relations"
                    and row["relation_kind"] == "transfer_event_report"
                ):
                    details = read_json(row["scope_json"])
                    key = (
                        "transfer",
                        *checked_resource(row).coordinates(),
                        canonical(details["clock"]),
                        row["provenance_json"],
                    )
                elif section == "resource_repository_relations" and row[
                    "relation_kind"
                ].startswith("transfer_"):
                    key = (
                        "transfer",
                        *checked_resource(row).coordinates(),
                        row["clock_json"],
                        row["provenance_json"],
                    )
                groups.setdefault(key, []).append((section, index))
                lookup[section, index] = key

        # Union real terminal alternatives with all Coverage claims/proofs referencing
        # their slot; removing one alternative cannot launder false completeness.
        parent = {key: key for key in groups}

        def root(key):
            while parent[key] != key:
                spend()
                parent[key] = parent[parent[key]]
                key = parent[key]
            return key

        for index, row in enumerate(data["coverage_proofs"]):
            spend()
            key = lookup["coverage_proofs", index]
            target = terminal_slot(row, row["proof_kind"])
            if target in parent:
                parent[root(target)] = root(key)
        merged: dict[tuple, list[tuple[str, int]]] = {}
        for key, values in groups.items():
            spend(1 + len(values))
            merged.setdefault(root(key), []).extend(values)
        groups = merged
        spend(len(groups) + sum(len(values) for values in groups.values()))
        lookup = {
            coordinate: key for key, values in groups.items() for coordinate in values
        }
        group_order = {key: index for index, key in enumerate(groups)}

        def indexed(section):
            for index, row in enumerate(data[section]):
                charge_value(row)
                yield index, row

        resources = {
            checked_resource(row): lookup["resources", index]
            for index, row in indexed("resources")
        }
        providers = {
            row["service_instance_uuidv4"]: lookup["providers", index]
            for index, row in indexed("providers")
        }
        repos = {
            row["repository_uuidv4"]: lookup["repositories", index]
            for index, row in indexed("repositories")
        }
        sources = {
            row["source_registration_uuidv4"]: lookup["sources", index]
            for index, row in indexed("sources")
        }
        pairs = {
            (row["source_registration_uuidv4"], row["repository_uuidv4"]): lookup[
                "source_repositories", index
            ]
            for index, row in indexed("source_repositories")
        }
        claims = {
            checked_relation(row).claim_key: lookup[
                "resource_repository_relations", index
            ]
            for index, row in indexed("resource_repository_relations")
            if not row["relation_kind"].startswith("transfer_")
        }
        parents = {
            (
                checked_resource(row),
                row["members_json"],
                row["provenance_json"],
                row["scope_json"],
            ): lookup["resource_relations", index]
            for index, row in indexed("resource_relations")
            if row["relation_kind"] == "parent"
        }
        texts = {
            row["sha256"]: lookup["text_bodies", index]
            for index, row in indexed("text_bodies")
        }
        scopes = {
            (row["owner_kind"], row["owner_coordinates_json"]): lookup[
                "coverage_scopes", index
            ]
            for index, row in indexed("coverage_scopes")
        }
        spend(len(chosen))
        required_services = {key.service_instance_uuidv4 for key in chosen} | {
            row["service_instance_uuidv4"]
            for _, row in indexed("sources")
            if scope.source_uuidv4s is None
            or row["source_registration_uuidv4"] in scope.source_uuidv4s
        }
        spend(len(groups))
        dependencies: dict[tuple, set[tuple]] = {key: set() for key in groups}
        failures: dict[tuple, str] = {}

        def need(key, target):
            if not spend():
                failures.setdefault(key, "work_limit")
            elif target is None:
                failures.setdefault(key, "missing_dependency")
            elif target != key:
                dependencies[key].add(target)

        def need_resource(key, target):
            if target not in chosen:
                failures.setdefault(key, blocked.get(target, "resource_not_selected"))
            need(key, resources.get(target))

        def need_repo(key, repo):
            if (
                scope.repository_uuidv4s is not None
                and repo not in scope.repository_uuidv4s
            ):
                failures.setdefault(key, "repository_not_selected")
            need(key, repos.get(repo))

        def need_source(key, source):
            if scope.source_uuidv4s is not None and source not in scope.source_uuidv4s:
                failures.setdefault(key, "source_not_selected")
            need(key, sources.get(source))

        for key, coordinates in groups.items():
            for section, index in coordinates:
                row = data[section][index]
                if (section, index) in blocked_rows:
                    failures.setdefault(key, blocked_rows[section, index])
                if not spend():
                    failures.setdefault(key, "work_limit")
                if (
                    section == "providers"
                    and (
                        scope.resource_keys is not None
                        or scope.source_uuidv4s is not None
                    )
                    and row["service_instance_uuidv4"] not in required_services
                ):
                    failures.setdefault(
                        key, "provider_not_required_by_selected_context"
                    )
                if "resource_kind" in row:
                    owner = checked_resource(row)
                    if section == "resources":
                        if owner not in chosen:
                            failures.setdefault(
                                key, blocked.get(owner, "resource_not_selected")
                            )
                        need(key, providers.get(owner.service_instance_uuidv4))
                    else:
                        need_resource(key, owner)
                if section in {"resource_relations", "collections"}:
                    for member in read_json(row["members_json"]):
                        need_resource(key, ResourceKey(*member))
                    if (
                        section == "resource_relations"
                        and row["relation_kind"] == "transfer_event_report"
                    ):
                        details = read_json(row["scope_json"])
                        native = EventReportKey(
                            checked_resource(row),
                            FieldClock.from_json(canonical(details["clock"])),
                            row["provenance_json"],
                        ).issue_parent
                        need_resource(key, native)
                        need(
                            key,
                            parents.get(
                                (
                                    checked_resource(row),
                                    *(
                                        details[name]
                                        for name in (
                                            "parent_members_json",
                                            "parent_provenance_json",
                                            "parent_scope_json",
                                        )
                                    ),
                                )
                            ),
                        )
                if (
                    section == "resource_relations"
                    and row["relation_kind"] == "provider_repository_roles"
                ):
                    roles = ProviderRepositoryScope.from_json(row["scope_json"])
                    for role in roles.roles.values():
                        if role.repository_uuidv4 is not None:
                            need_repo(key, role.repository_uuidv4)
                        if role.provider_repository_id is not None:
                            need_resource(
                                key,
                                ResourceKey(
                                    checked_resource(row).service_instance_uuidv4,
                                    "repository",
                                    role.provider_repository_id,
                                ),
                            )
                if section == "resource_repository_relations":
                    rel = checked_relation(row)
                    if rel.target_repository_uuidv4 is not None:
                        need_repo(key, rel.target_repository_uuidv4)
                    if rel.embedded_support is not None:
                        need_resource(key, rel.embedded_support.provider_repository)
                        for claim in rel.embedded_support.supporting_claims:
                            need(key, claims.get(claim))
                if section == "repository_mapping_dispositions":
                    from repo_catalog.domain.selective_exchange import disposition

                    parsed = disposition(row)
                    need(key, claims.get(parsed.claim_key))
                    if parsed.replacement_claim_key is not None:
                        need(key, claims.get(parsed.replacement_claim_key))
                if section == "sources":
                    if (
                        scope.source_uuidv4s is not None
                        and row["source_registration_uuidv4"]
                        not in scope.source_uuidv4s
                    ):
                        failures.setdefault(key, "source_not_selected")
                    need(key, providers.get(row["service_instance_uuidv4"]))
                if (
                    section == "repositories"
                    and scope.repository_uuidv4s is not None
                    and row["repository_uuidv4"] not in scope.repository_uuidv4s
                ):
                    failures.setdefault(key, "repository_not_selected")
                if section in {"source_repositories", "source_inventories"}:
                    source = row["source_registration_uuidv4"]
                    need_source(key, source)
                    members = (
                        [row["repository_uuidv4"]]
                        if section == "source_repositories"
                        else read_json(row["members_json"])
                    )
                    for repo in members:
                        need_repo(key, repo)
                        if section == "source_inventories":
                            need(key, pairs.get((source, repo)))
                for name, value in row.items():
                    if value is not None and (
                        name.endswith("provenance_json") or name == "scope_json"
                    ):
                        spend(1 + len(value))
                        for source in extract_provenance_sources(value):
                            need_source(key, source)
                if section == "collections":
                    attributes = read_json(row["scope_json"])
                    if (
                        type(attributes) is dict
                        and attributes.get("source_registration_uuidv4") is not None
                    ):
                        source = attributes["source_registration_uuidv4"]
                        if attributes.get("repository_uuidv4") is not None:
                            repo = attributes["repository_uuidv4"]
                            need_repo(key, repo)
                            need(key, pairs.get((source, repo)))
                if (
                    section == "field_candidates"
                    and row["field_name"] == "text_body_sha256"
                ):
                    digest = read_json(row["value_json"])
                    if digest is not None:
                        need(key, texts.get(digest))
                if section.startswith("coverage_"):
                    coords = read_json(row["owner_coordinates_json"])
                    if section in {"coverage_claims", "coverage_proofs"}:
                        need(
                            key,
                            scopes.get(
                                (row["owner_kind"], row["owner_coordinates_json"])
                            ),
                        )
                    if row["owner_kind"] == "collection":
                        slot = ("collection", *coords[:5])
                        need(key, root(slot) if slot in parent else None)
                    if row["owner_kind"] == "repository":
                        need_repo(key, coords[0])
                    elif row["owner_kind"] in {"source", "source_inventory"}:
                        need_source(key, coords[0])
                        if row["owner_kind"] == "source":
                            need_repo(key, coords[1])
                            need(key, pairs.get((coords[0], coords[1])))
                    else:
                        need_resource(key, ResourceKey(*coords[:3]))
                    if section == "coverage_proofs":
                        target = terminal_slot(row, row["proof_kind"])
                        need(key, root(target) if target in parent else None)

        # Build reverse edges once; each failed unit and dependency edge is visited
        # at most once. A budget stop leaves all not-yet-selected units withheld.
        spend(len(groups))
        reverse: dict[tuple, set[tuple]] = {key: set() for key in groups}
        for key, required in dependencies.items():
            spend()
            for target in required:
                spend()
                reverse[target].add(key)
        spend(len(failures))
        pending_failures = list(failures)
        propagated = set()
        while pending_failures:
            spend()
            failed = pending_failures.pop()
            if failed in propagated:
                continue
            propagated.add(failed)
            for dependent in reverse[failed]:
                spend()
                if dependent not in failures:
                    failures[dependent] = "missing_dependency"
                    pending_failures.append(dependent)
        kept: set[tuple] = set()
        emitted = payload_bytes = 0
        priority = {
            "providers": 0,
            "repositories": 0,
            "sources": 1,
            "resources": 2,
            "source_repositories": 3,
        }
        ordered = sorted(
            groups,
            key=lambda key: (
                min(priority.get(section, 4) for section, _ in groups[key]),
                encoded_key(key),
            ),
        )
        resource_by_unit = {unit: key for key, unit in resources.items()}
        for key in ordered:
            spend()
            if key in failures or key in kept:
                continue
            if all(section == "text_bodies" for section, _ in groups[key]):
                # Text is reachable only through a selected field candidate.
                continue
            pending = [key]
            closure: set[tuple] = set()
            while pending:
                spend()
                candidate = pending.pop()
                if candidate in closure or candidate in kept:
                    continue
                closure.add(candidate)
                spend(len(dependencies[candidate]))
                for target in sorted(
                    dependencies[candidate], key=group_order.__getitem__
                ):
                    spend()
                    pending.append(target)
            rows = []
            spend(len(closure))
            for candidate in sorted(closure, key=group_order.__getitem__):
                spend()
                for coordinate in groups[candidate]:
                    spend()
                    rows.append(coordinate)
            row_sizes = {}
            for section, index in rows:
                row = data[section][index]
                charge_value(row)
                size = len(
                    json.dumps(
                        row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                    ).encode("utf-8")
                )
                row_sizes[section, index] = size
            size = sum(row_sizes.values())
            if emitted + len(rows) > scope.max_units:
                failures[key] = "unit_limit"
            elif payload_bytes + size > scope.max_bytes:
                failures[key] = "byte_limit"
            elif any(candidate in failures for candidate in closure):
                failures[key] = "missing_dependency"
            else:
                prepared = {}
                # Reserve copy/output work before allocating copies. Nothing from an
                # unfinished closure is visible in completed_rows.
                for section, index in rows:
                    charge_value(data[section][index])
                    prepared[section, index] = copy.deepcopy(data[section][index])
                completed_rows.update(prepared)
                completed_sizes.update(row_sizes)
                for candidate in sorted(closure, key=group_order.__getitem__):
                    if candidate in resource_by_unit:
                        completed_resources.add(resource_by_unit[candidate])
                    completed_units[candidate] = ContextSemanticUnit(
                        candidate, tuple(groups[candidate])
                    )
                kept.update(closure)
                emitted += len(rows)
                payload_bytes += size
        for key in ordered:
            if key not in kept:
                omissions.append(
                    DependencyOmission(
                        ("context_input_rows", *groups[key]),
                        groups[key][0][0],
                        failures.get(key, "missing_dependency"),
                    )
                )
        return completed_result()

    try:
        return run()
    except WorkLimit:
        # Bounded diagnostic only: do not scan dependencies, serialize originals,
        # or allocate unfinished units after work exhaustion.
        omissions.append(DependencyOmission(("context",), "context", "work_limit"))
        return completed_result()
