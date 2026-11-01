"""Typed original Ref/Claim/Enumeration reconstruction, without orchestration."""

from repo_catalog.domain.p1_core import CoreFailure, _performed
from repo_catalog.domain.ref_exchange import (
    claim_from_wire,
    enumeration_from_wire,
    link_from_wire,
    observation_from_wire,
)


def decode_ref_units(section):
    """Reconstruct original subject/claim/event units before any ref write."""
    observations = {}
    claims = {}
    coordinates = {}
    events = {}
    links = {}
    for row in section["ref_observations"]:
        _performed("metadata_units", 1)
        observation = observation_from_wire(row)
        prior = observations.setdefault(
            observation.ref_observation_key.key, observation
        )
        if prior != observation:
            raise CoreFailure(
                "INCOMPATIBLE_REPLAY",
                observation.ref_observation_key,
                "immutable subject changed",
            )
    for row in section["ref_observation_claims"]:
        _performed("metadata_units", 1)
        claim = claim_from_wire(row)
        observation = observations.get(claim.ref_observation_key.key)
        if observation is None:
            raise CoreFailure(
                "OBSERVATION_UNAVAILABLE",
                claim.ref_observation_key,
                "claim subject missing",
            )
        absence = claim.absence_evidence
        if absence is not None and (
            absence.ref_name_bytes,
            absence.source_attribution,
            absence.visibility_scope,
        ) != (
            observation.ref_name_bytes,
            observation.source_attribution,
            observation.visibility_scope,
        ):
            raise CoreFailure(
                "ABSENCE", claim.ref_observation_key, "absence subject changed"
            )
        coordinate = (*claim.ref_observation_key.key, *claim.provenance.key[:3])
        prior = coordinates.setdefault(coordinate, claim)
        if prior != claim:
            raise CoreFailure(
                "INCOMPATIBLE_REPLAY",
                coordinate,
                "original evidence coordinate rebound",
            )
        claims[claim.identity] = claim
    for row in section["ref_enumeration_observations"]:
        _performed("metadata_units", 1)
        event = enumeration_from_wire(row)
        prior = events.setdefault(event.identity, event)
        if prior != event:
            raise CoreFailure(
                "INCOMPATIBLE_REPLAY", event.identity, "enumeration changed"
            )
    for row in section["ref_enumeration_links"]:
        _performed("metadata_units", 1)
        event_key = (row["enumeration_origin_uuidv4"], row["enumeration_uuidv7"])
        observation_key = (
            row["observation_origin_uuidv4"],
            row["ref_observation_uuidv7"],
        )
        claim_key = (*observation_key, row["claim_provenance_json"])
        if (
            event_key not in events
            or observation_key not in observations
            or claim_key not in claims
        ):
            raise CoreFailure(
                "ENUMERATION", event_key, "enumeration dependency missing"
            )
        link = link_from_wire(
            row, events[event_key], observations[observation_key], claims[claim_key]
        )
        bucket = links.setdefault(event_key, {})
        if link.position in bucket and bucket[link.position] != link:
            raise CoreFailure(
                "INCOMPATIBLE_REPLAY", event_key, "enumeration position rebound"
            )
        bucket[link.position] = link
    for key, event in events.items():
        bucket = links.get(key, {})
        if len(bucket) != event.link_count or sorted(bucket) != list(
            range(event.link_count)
        ):
            raise CoreFailure("ENUMERATION", key, "whole original enumeration required")
    return observations, claims, events, links
