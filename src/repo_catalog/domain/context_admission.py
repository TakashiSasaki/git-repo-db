"""Service-issued local Context admission authority and pure dependency discovery.

Neither these values nor provenance attest Provider authenticity. The service is
trusted composition infrastructure; input callers receive only issued contexts.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field, fields, is_dataclass, replace
from threading import RLock
from typing import TYPE_CHECKING
from uuid import UUID
from weakref import ref

if TYPE_CHECKING:
    from repo_catalog.domain.ports.context_authorization import AuthorizationPolicy

OPERATIONS = frozenset(
    {"provider_intake", "exchange_import", "exchange_export", "salvage_merge"}
)
_DIMENSIONS = (
    "resources",
    "repositories",
    "sources",
    "source_repository_pairs",
    "mapping_claims",
    "dispositions",
    "provider_registrations",
    "object_oids",
)


class AdmissionRefused(ValueError):
    """Stable refusal with no caller or existence-bearing diagnostic content."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        super().__init__(code)


def _finite(value):
    if type(value) is not int or not 0 <= value <= 100_000_000:
        raise AdmissionRefused("INPUT_LIMIT")


def _uuid(value):
    try:
        parsed = UUID(value) if type(value) is str else None
        if parsed is None or parsed.version != 4 or str(parsed) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise AdmissionRefused("INVALID_DEPENDENCY") from None
    return value


@dataclass(frozen=True)
class DependencySet:
    resources: frozenset = frozenset()
    repositories: frozenset[str] = frozenset()
    sources: frozenset[str] = frozenset()
    source_repository_pairs: frozenset[tuple[str, str]] = frozenset()
    mapping_claims: frozenset = frozenset()
    dispositions: frozenset = frozenset()
    provider_registrations: frozenset[str] = frozenset()
    object_oids: frozenset = frozenset()

    def __post_init__(self):
        # Local imports avoid a cycle with mandatory-original constructors.
        from repo_catalog.domain.p1_context import (
            MappingClaimKey,
            MappingDispositionKey,
            ResourceKey,
        )
        from repo_catalog.domain.p1_core import OID

        for name in _DIMENSIONS:
            object.__setattr__(self, name, frozenset(getattr(self, name)))
        for name, cls in (
            ("resources", ResourceKey),
            ("mapping_claims", MappingClaimKey),
            ("dispositions", MappingDispositionKey),
            ("object_oids", OID),
        ):
            if any(not isinstance(value, cls) for value in getattr(self, name)):
                raise AdmissionRefused("INVALID_DEPENDENCY")
        for name in ("repositories", "sources", "provider_registrations"):
            for value in getattr(self, name):
                _uuid(value)
        for pair in self.source_repository_pairs:
            if type(pair) is not tuple or len(pair) != 2:
                raise AdmissionRefused("INVALID_DEPENDENCY")
            for value in pair:
                _uuid(value)

    def __or__(self, other):
        if not isinstance(other, DependencySet):
            return NotImplemented
        return DependencySet(
            **{name: getattr(self, name) | getattr(other, name) for name in _DIMENSIONS}
        )

    def issubset(self, other):
        return all(getattr(self, name) <= getattr(other, name) for name in _DIMENSIONS)

    def __len__(self):
        return sum(len(getattr(self, name)) for name in _DIMENSIONS)


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    subject: str
    session_id: str

    def __post_init__(self):
        if any(
            type(value) is not str or not value
            for value in (self.subject, self.session_id)
        ):
            raise AdmissionRefused("PERMISSION_DENIED")


@dataclass(frozen=True)
class AdmissionSelection:
    resource_keys: frozenset | None = None
    repository_uuidv4s: frozenset[str] | None = None
    source_uuidv4s: frozenset[str] | None = None
    object_oids: frozenset | None = None
    all_selected: bool = False
    include_dependencies: bool = False
    max_depth: int = 8
    max_units: int = 10_000
    max_bytes: int = 16 * 1024 * 1024
    max_work: int = 10_000_000
    include_core: bool = True
    include_context: bool = True
    include_retained_bytes: bool = True

    def __post_init__(self):
        for name in (
            "all_selected",
            "include_dependencies",
            "include_core",
            "include_context",
            "include_retained_bytes",
        ):
            if type(getattr(self, name)) is not bool:
                raise AdmissionRefused("INVALID_SELECTION")
        for name in ("max_depth", "max_units", "max_bytes", "max_work"):
            _finite(getattr(self, name))
        for name in (
            "resource_keys",
            "repository_uuidv4s",
            "source_uuidv4s",
            "object_oids",
        ):
            value = getattr(self, name)
            if value is None:
                if not self.all_selected:
                    raise AdmissionRefused("OMITTED_BY_SELECTION")
            else:
                object.__setattr__(self, name, frozenset(value))
        DependencySet(
            resources=self.resource_keys or (),
            repositories=self.repository_uuidv4s or (),
            sources=self.source_uuidv4s or (),
            object_oids=self.object_oids or (),
        )

    @classmethod
    def from_scope(cls, scope):
        from repo_catalog.domain.exchange import ExchangeSelectionScope

        if type(scope) is cls:
            return scope
        if type(scope) is not ExchangeSelectionScope:
            raise AdmissionRefused("INVALID_SELECTION")
        return cls(
            **{
                item.name: getattr(scope, item.name)
                for item in fields(cls)
                if hasattr(scope, item.name)
            }
        )

    def check(self, deps):
        if not self.include_context and any(
            getattr(deps, name) for name in _DIMENSIONS if name != "object_oids"
        ):
            raise AdmissionRefused("OMITTED_BY_SELECTION")
        if not self.include_core and (deps.repositories or deps.object_oids):
            raise AdmissionRefused("OMITTED_BY_SELECTION")
        for selected, required in (
            (self.resource_keys, deps.resources),
            (self.repository_uuidv4s, deps.repositories),
            (self.source_uuidv4s, deps.sources),
            (self.object_oids, deps.object_oids),
        ):
            if selected is not None and not required <= selected:
                raise AdmissionRefused("OMITTED_BY_SELECTION")
        if len(deps) > self.max_units:
            raise AdmissionRefused("INPUT_LIMIT")


@dataclass(frozen=True)
class AdmissionBudget:
    """Request-scoped actual work; failed or rolled-back work is never refunded."""

    work_limit: int = 10_000_000
    bytes_limit: int = 16 * 1024 * 1024
    dependency_limit: int = 100_000
    depth_limit: int = 12
    _usage: list[int] = field(
        default_factory=lambda: [0, 0, 0], init=False, repr=False, compare=False
    )
    _lock: object = field(default_factory=RLock, init=False, repr=False, compare=False)

    def __post_init__(self):
        for value in (
            self.work_limit,
            self.bytes_limit,
            self.dependency_limit,
            self.depth_limit,
        ):
            _finite(value)

    @property
    def used_work(self):
        return self._usage[0]

    @property
    def used_bytes(self):
        return self._usage[1]

    @property
    def used_dependencies(self):
        return self._usage[2]

    def charge(self, *, work=0, bytes_=0, dependencies=0):
        increments = (work, bytes_, dependencies)
        for value in increments:
            _finite(value)
        with self._lock:
            for index, value in enumerate(increments):
                self._usage[index] += value
            if any(
                used > limit
                for used, limit in zip(
                    self._usage,
                    (self.work_limit, self.bytes_limit, self.dependency_limit),
                )
            ):
                raise AdmissionRefused("INPUT_LIMIT")


@dataclass(frozen=True)
class AdmissionContext:
    principal: object
    operation: str
    selection: AdmissionSelection
    budget: AdmissionBudget


def _selection_state(selection):
    result = []
    for member in fields(AdmissionSelection):
        value = getattr(selection, member.name)
        if value is not None and member.name == "resource_keys":
            value = frozenset(key.coordinates() for key in value)
        elif value is not None and member.name == "object_oids":
            value = frozenset(oid.key for oid in value)
        result.append(value)
    return tuple(result)


def _principal_state(principal):
    if type(principal) is AuthenticatedPrincipal:
        return principal.subject, principal.session_id
    return principal


def _budget_limits(budget):
    return (
        budget.work_limit,
        budget.bytes_limit,
        budget.dependency_limit,
        budget.depth_limit,
    )


class ContextAdmissionService:
    """Trusted local service; possession of a constructed dataclass grants nothing."""

    def __init__(self, policy: AuthorizationPolicy, authenticate: Callable):
        if not callable(getattr(policy, "lease", None)) or not callable(authenticate):
            raise AdmissionRefused("PERMISSION_DENIED")
        self._policy, self._authenticate = policy, authenticate
        self._issued = {}
        self._lock = RLock()

    def context(self, credential, operation, selection, budget):
        if type(operation) is not str or operation not in OPERATIONS:
            raise AdmissionRefused("PERMISSION_DENIED")
        try:
            principal = self._authenticate(credential)
        except Exception:
            raise AdmissionRefused("PERMISSION_DENIED") from None
        if not (
            (type(principal) is str and principal)
            or type(principal) is AuthenticatedPrincipal
        ):
            raise AdmissionRefused("PERMISSION_DENIED")
        selection = AdmissionSelection.from_scope(selection)
        if type(budget) is not AdmissionBudget:
            raise AdmissionRefused("INPUT_LIMIT")
        context = AdmissionContext(principal, operation, selection, budget)
        key = id(context)

        def discard(issued):
            with self._lock:
                current = self._issued.get(key)
                if current is not None and current[0] is issued:
                    self._issued.pop(key)

        with self._lock:
            self._issued[key] = (
                ref(context, discard),
                principal,
                operation,
                selection,
                budget,
                _principal_state(principal),
                _selection_state(selection),
                _budget_limits(budget),
            )
        return context

    def validate_context(self, context):
        with self._lock:
            original = self._issued.get(id(context))
            if (
                type(context) is not AdmissionContext
                or original is None
                or original[0]() is not context
                or context.principal is not original[1]
                or context.operation != original[2]
                or context.selection is not original[3]
                or context.budget is not original[4]
                or _principal_state(context.principal) != original[5]
                or _selection_state(context.selection) != original[6]
                or _budget_limits(context.budget) != original[7]
            ):
                raise AdmissionRefused("PERMISSION_DENIED")
        return context

    def charge_input(self, context, unit):
        """Charge bounded actual traversal/UTF-8 input before validation and lookup."""
        context = self.validate_context(context)
        pending = [(unit, 0)]
        while pending:
            item, depth = pending.pop()
            context.budget.charge(work=1)
            if depth > context.budget.depth_limit:
                raise AdmissionRefused("INPUT_LIMIT")
            if type(item) is str:
                for offset in range(0, len(item), 4096):
                    try:
                        size = len(item[offset : offset + 4096].encode("utf-8"))
                    except UnicodeError:
                        raise AdmissionRefused("INVALID_PROVENANCE") from None
                    context.budget.charge(work=1, bytes_=size)
            elif is_dataclass(item):
                pending.extend(
                    (getattr(item, member.name), depth + 1) for member in fields(item)
                )
            elif isinstance(item, (tuple, list, frozenset)):
                if len(item) > context.budget.work_limit:
                    raise AdmissionRefused("INPUT_LIMIT")
                pending.extend((child, depth + 1) for child in item)
            elif type(item) is dict:
                if len(item) > context.budget.work_limit:
                    raise AdmissionRefused("INPUT_LIMIT")
                pending.extend((child, depth + 1) for child in item.values())
                pending.extend((child, depth + 1) for child in item.keys())
            if (
                context.budget.used_work > context.selection.max_work
                or context.budget.used_bytes > context.selection.max_bytes
            ):
                raise AdmissionRefused("INPUT_LIMIT")

    @contextmanager
    def authorize(self, context, deps):
        context = self.validate_context(context)
        if type(deps) is not DependencySet:
            raise AdmissionRefused("INVALID_DEPENDENCY")
        context.budget.charge(work=1 + len(deps), dependencies=len(deps))
        # Policy denial precedes selection omission and every existence lookup.
        with self._policy.lease(context.principal, context.operation, deps) as lease:
            if not callable(getattr(lease, "check_current", None)):
                raise AdmissionRefused("PERMISSION_DENIED")
            lease.check_current()
            context.selection.check(deps)
            if (
                context.budget.used_work > context.selection.max_work
                or context.budget.used_bytes > context.selection.max_bytes
            ):
                raise AdmissionRefused("INPUT_LIMIT")
            yield lease
            lease.check_current()

    @staticmethod
    def dependencies(unit):
        return dependencies(unit)


def _provenance_value(encoded):
    """Bound before decoding, reject noncanonical/duplicate keys and constants."""
    if type(encoded) is not str or len(encoded) > 65_536:
        raise AdmissionRefused("INPUT_LIMIT")
    try:
        if len(encoded.encode("utf-8")) > 65_536:
            raise AdmissionRefused("INPUT_LIMIT")
        depth = 0
        quoted = escaped = False
        for char in encoded:
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "[{":
                depth += 1
                if depth > 12:
                    raise AdmissionRefused("INPUT_LIMIT")
            elif char in "]}":
                depth -= 1

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError
                result[key] = value
            return result

        def constant(_):
            raise ValueError

        value = json.loads(encoded, object_pairs_hook=unique, parse_constant=constant)
        pending, count = [value], 0
        while pending:
            item = pending.pop()
            count += 1
            if count > 2048:
                raise AdmissionRefused("INPUT_LIMIT")
            if type(item) is dict:
                pending.extend(item.values())
                pending.extend(item.keys())
            elif type(item) is list:
                pending.extend(item)
            elif type(item) is str:
                item.encode("utf-8")
        if (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
            != encoded
        ):
            raise ValueError
        return value
    except AdmissionRefused:
        raise
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
        raise AdmissionRefused("INVALID_PROVENANCE") from None


def extract_provenance_sources(encoded):
    """Only explicit Source-registration coordinates are local Source references.

    A source attribution string, claimed issuer or UUID-looking text is not one.
    """
    pending = [_provenance_value(encoded)]
    sources = set()
    while pending:
        item = pending.pop()
        if type(item) is dict:
            if "source_registration_uuidv4" in item:
                value = item["source_registration_uuidv4"]
                if value is not None:
                    sources.add(_uuid(value))
            pending.extend(item.values())
        elif type(item) is list:
            pending.extend(item)
    return frozenset(sources)


def dependencies(unit):
    """Enumerate typed inputs only; no SQL, current checks or authority inference.

    Structural writers with multiple positional coordinates construct their own
    DependencySet. Composite units may be tuples of these supported domain types.
    """
    from repo_catalog.domain.p1_context import (
        CoverageScope,
        EventReportKey,
        FieldCandidate,
        MappingClaimKey,
        MappingDispositionKey,
        MappingSupport,
        ResourceKey,
        TransferEventReport,
    )
    from repo_catalog.domain.p1_core import OID

    values = {name: set() for name in _DIMENSIONS}
    pending = [(unit, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > 12 or count > 2048:
            raise AdmissionRefused("INPUT_LIMIT")
        if item is None or type(item) in (str, int, bool, float):
            if depth == 0:
                raise AdmissionRefused("INVALID_DEPENDENCY")
            continue
        if isinstance(item, DependencySet):
            for name in _DIMENSIONS:
                values[name].update(getattr(item, name))
            continue
        if isinstance(item, ResourceKey):
            values["resources"].add(item)
            values["provider_registrations"].add(item.service_instance_uuidv4)
            continue
        if isinstance(item, OID):
            values["object_oids"].add(item)
            continue
        if isinstance(item, (tuple, list, frozenset)):
            pending.extend((child, depth + 1) for child in item)
            continue
        if not is_dataclass(item) or type(item).__module__ not in {
            "repo_catalog.domain.p1_context",
            "repo_catalog.domain.production_context",
            "repo_catalog.domain.parent_report",
            "repo_catalog.domain.resource_identification",
        }:
            raise AdmissionRefused("INVALID_DEPENDENCY")
        if isinstance(item, FieldCandidate) and item.field_name.startswith(
            "reported_core_reference:"
        ):
            from repo_catalog.domain.production_context import (
                validate_reported_core_reference,
            )

            validate_reported_core_reference(item)
            values["object_oids"].add(OID(*_provenance_value(item.value_json)))
        if isinstance(item, CoverageScope):
            coords = item.coordinates
            if item.owner_kind in {"resource", "field", "collection"}:
                pending.append((ResourceKey(*coords[:3]), depth + 1))
                if item.relation_repository_uuidv4 is not None:
                    values["repositories"].add(_uuid(item.relation_repository_uuidv4))
                if item.owner_kind == "collection":
                    values["sources"].update(extract_provenance_sources(coords[4]))
            elif item.owner_kind == "repository":
                values["repositories"].add(_uuid(coords[0]))
            elif item.owner_kind in {"source", "source_inventory"}:
                values["sources"].add(_uuid(coords[0]))
                if item.owner_kind == "source":
                    values["repositories"].add(_uuid(coords[1]))
                    values["source_repository_pairs"].add((coords[0], coords[1]))
        repository = getattr(item, "repository_uuidv4", None)
        if repository is not None:
            values["repositories"].add(_uuid(repository))
        if isinstance(item, MappingClaimKey):
            values["mapping_claims"].add(item)
        if isinstance(item, MappingDispositionKey):
            values["dispositions"].add(item)
        if isinstance(item, EventReportKey):
            # The native I7 is a real dependency, independent of reported Parent.
            pending.append((item.issue_parent, depth + 1))
        if isinstance(item, TransferEventReport):
            # Parent membership is an original semantic key, not an ID namespace.
            for coords in _provenance_value(item.parent_members_json):
                pending.append((ResourceKey(*coords), depth + 1))
        target = getattr(item, "target_repository_uuidv4", None)
        if target is not None:
            values["repositories"].add(_uuid(target))
        source = getattr(item, "source_registration_uuidv4", None)
        if source is not None:
            values["sources"].add(_uuid(source))
            for repository in getattr(item, "repositories", ()):
                values["repositories"].add(_uuid(repository))
                values["source_repository_pairs"].add((source, repository))
        for member in fields(item):
            child = getattr(item, member.name)
            if member.name.endswith("provenance_json") and child is not None:
                values["sources"].update(extract_provenance_sources(child))
                provenance = _provenance_value(child)
                nested = [provenance]
                while nested:
                    value = nested.pop()
                    if type(value) is dict:
                        if "mapping_support" in value:
                            pending.append(
                                (
                                    MappingSupport.from_dict(value["mapping_support"]),
                                    depth + 1,
                                )
                            )
                        nested.extend(value.values())
                    elif type(value) is list:
                        nested.extend(value)
            elif member.name == "scope_json" and child is not None:
                values["sources"].update(extract_provenance_sources(child))
                scope = _provenance_value(child)
                if type(scope) is dict and "repository_roles" in scope:
                    from repo_catalog.domain.p1_context import ProviderRepositoryScope

                    roles = ProviderRepositoryScope.from_json(child)
                    owner = getattr(item, "resource", None)
                    for role in roles.roles.values():
                        if role.repository_uuidv4 is not None:
                            values["repositories"].add(_uuid(role.repository_uuidv4))
                        if role.provider_repository_id is not None and isinstance(
                            owner, ResourceKey
                        ):
                            pending.append(
                                (
                                    ResourceKey(
                                        owner.service_instance_uuidv4,
                                        "repository",
                                        role.provider_repository_id,
                                    ),
                                    depth + 1,
                                )
                            )
            elif member.name == "members_json" and child is not None:
                # ParentReportKey stores the complete Resource member list.
                for coords in _provenance_value(child):
                    pending.append((ResourceKey(*coords), depth + 1))
            elif is_dataclass(child) or isinstance(child, (tuple, list, frozenset)):
                pending.append((child, depth + 1))
    return DependencySet(**values)


def validate_originals(unit):
    """Pure validation entry point; never reconstruct originals from stored rows."""
    from repo_catalog.domain.p1_context import TransferEventReport
    from repo_catalog.domain.parent_report import validate_parent_report
    from repo_catalog.domain.production_context import ResourceRelation

    if isinstance(unit, TransferEventReport):
        # Constructors and their complete original declarations are authoritative.
        replace(unit)
    elif isinstance(unit, ResourceRelation) and unit.relation_kind == "parent":
        validate_parent_report(
            *unit.resource.coordinates(),
            unit.members_json,
            unit.provenance_json,
            unit.scope_json,
            unit.observed_at_us,
        )
    elif isinstance(unit, (tuple, list)):
        for member in unit:
            validate_originals(member)
    else:
        dependencies(unit)
