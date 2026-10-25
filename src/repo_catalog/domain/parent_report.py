"""ADR 0031 I3 singleton Parent reports in resource_relations.

The seven existing PK coordinates identify a report. Observation time is an
immutable attribute, not a newly issued identity. Namespace metadata never
creates a report and a different reported Parent ID is lawful evidence.
"""

from dataclasses import dataclass

from repo_catalog.domain.p1_context import (
    FieldClock,
    ResourceKey,
    _parse_canonical_json,
    canonical,
    validate_mapping_provenance,
)
from repo_catalog.domain.resource_identification import SCOPED_NAMESPACES
from repo_catalog.domain.time import validate_observation_us


def validate_parent_report(
    service, kind, identity, members, provenance, scope, observed
):
    child = ResourceKey(service, kind, identity)
    values = _parse_canonical_json(members)
    details = _parse_canonical_json(scope)
    validate_mapping_provenance(provenance)
    validate_observation_us(observed)
    if type(values) is not list or len(values) != 1:
        raise ValueError("Parent report requires one complete ResourceKey member")
    if type(values[0]) is not list or len(values[0]) != 3:
        raise ValueError("Parent member requires the exact ResourceKey triple")
    parent = ResourceKey(*values[0])
    if parent.service_instance_uuidv4 != child.service_instance_uuidv4:
        raise ValueError("Parent report must remain in the service namespace")
    if type(details) is not dict or set(details) != {"clock", "document_kind", "state"}:
        raise ValueError("Parent scope requires clock, document_kind and state")
    FieldClock.from_json(canonical(details["clock"]))
    if details["state"] != "complete":
        raise ValueError("Typed singleton Parent report must be complete")
    subtype = details["document_kind"]
    if subtype is None:
        if kind in SCOPED_NAMESPACES and kind != "document":
            raise ValueError("Known scoped child requires its actual subtype")
    elif type(subtype) is not str or not subtype or kind not in SCOPED_NAMESPACES:
        raise ValueError("Invalid child subtype assertion")
    elif parent.resource_kind not in SCOPED_NAMESPACES[kind]:
        raise ValueError("Known scoped Parent kind contract")
    return parent, subtype


@dataclass(frozen=True)
class ParentReportKey:
    """Complete direct reference; never just (child, clock) or (child, Parent)."""

    resource: ResourceKey
    members_json: str
    provenance_json: str
    scope_json: str

    def __post_init__(self):
        if not isinstance(self.resource, ResourceKey):
            raise ValueError("ParentReportKey requires a ResourceKey")
        validate_parent_report(
            *self.resource.coordinates(),
            self.members_json,
            self.provenance_json,
            self.scope_json,
            None,
        )

    def coordinates(self) -> tuple[str, ...]:
        return (
            *self.resource.coordinates(),
            "parent",
            self.members_json,
            self.provenance_json,
            self.scope_json,
        )


@dataclass(frozen=True)
class ParentObservation:
    """An exact original Parent key and its independent immutable observation.

    NULL is a valid original observation, but callers must supply it explicitly.
    The observation is payload: it never adds a coordinate to the seven-part key.
    """

    report_key: ParentReportKey
    observed_at_us: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.report_key, ParentReportKey):
            raise ValueError("ParentObservation requires a complete ParentReportKey")
        validate_observation_us(self.observed_at_us)

    @property
    def resource(self) -> ResourceKey:
        return self.report_key.resource

    @property
    def members_json(self) -> str:
        return self.report_key.members_json

    @property
    def provenance_json(self) -> str:
        return self.report_key.provenance_json

    @property
    def scope_json(self) -> str:
        return self.report_key.scope_json


def parent_report_sql(*args):
    """Total, bounded, row-local predicate; no connection or database reads."""
    try:
        validate_parent_report(*args)
        return 1
    except (ValueError, TypeError, OverflowError, RecursionError):
        return 0
