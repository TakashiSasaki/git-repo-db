"""Selection and typed reconstruction of opt-in ref Exchange units."""

from __future__ import annotations

from dataclasses import replace

from repo_catalog.application.query_encoding import encode_metered
from repo_catalog.application.ref_reconstruction import decode_ref_units
from repo_catalog.domain.p1_coordination import NotesLimits
from repo_catalog.domain.p1_core import CoreFailure, Provenance, _performed, encode
from repo_catalog.domain.query_work import UnlimitedWorkBudget
from repo_catalog.domain.ref_exchange import (
    claim_to_wire,
    enumeration_to_wire,
    link_to_wire,
    mapping_claim_from_wire,
    mapping_claim_to_wire,
    mapping_evidence_from_wire,
    mapping_evidence_to_wire,
    mapping_group_from_wire,
    observation_to_wire,
    ref_note_from_wire,
)
from repo_catalog.domain.ref_observation import RefObservationKey


def _export_ref_notes(core, section, claim, work, scope):
    """Export reported groups and locally checked claim-specific proofs."""
    if claim.root_object_oid is None:
        return set()
    identity = claim.identity
    maximum, max_bytes = max(1, scope.max_units), max(1, scope.max_bytes)
    oids = set()
    common = {
        "observation_origin_uuidv4": identity[0],
        "ref_observation_uuidv7": identity[1],
        "ref_claim_provenance_json": identity[2],
    }
    group_columns = (
        "object_format",
        "root_object_oid",
        "interpretation_kind",
        "interpretation_version",
        "interpretation_scope",
        "group_scope",
        "status",
        "membership",
        "provenance",
    )
    for values in core.ref_exchange_rows(
        "groups", identity, work, maximum=maximum, max_bytes=max_bytes
    ):
        row = dict(zip(group_columns, values, strict=True))
        wire = {
            **common,
            **{k: v for k, v in row.items() if k not in ("membership", "provenance")},
            "membership_json": row["membership"],
            "provenance_json": row["provenance"],
        }
        group = core._stored(claim.identity, mapping_group_from_wire, wire, claim)
        for target, note, _ in group.members:
            for object_oid in (target, note):
                work.require("metadata_units", 1)
                work.charge("metadata_units", 1)
                if not core.sql(
                    "SELECT 1 FROM git_objects WHERE object_format=? AND object_oid=?",
                    (claim.root_object_oid.object_format, object_oid),
                ):
                    core._integrity_stop(
                        (claim.identity, "missing-mapping-group-object", object_oid)
                    )
                from repo_catalog.domain.p1_core import OID

                oids.add(OID(claim.root_object_oid.object_format, object_oid))
        section["notes_mapping_groups"].append(wire)

    mapping_columns = (
        "object_format",
        "root_object_oid",
        "interpretation_kind",
        "interpretation_version",
        "interpretation_scope",
        "annotated_object_oid",
        "note_object_oid",
        "mapping_path_json",
        "provenance",
    )
    for values in core.ref_exchange_rows(
        "mappings", identity, work, maximum=maximum, max_bytes=max_bytes
    ):
        row = dict(zip(mapping_columns, values, strict=True))
        wire = {
            **common,
            **{k: v for k, v in row.items() if k != "provenance"},
            "provenance_json": row["provenance"],
        }
        mapping_claim = core._stored(
            claim.identity, mapping_claim_from_wire, wire, claim
        )
        core._assert_stored_mapping(mapping_claim.mapping, claim.identity)
        oids.update(
            (
                mapping_claim.mapping.root_object_oid,
                mapping_claim.mapping.annotated_object_oid,
                mapping_claim.mapping.note_object_oid,
            )
        )
        section["notes_mapping_claims"].append(mapping_claim_to_wire(mapping_claim))

    evidence_columns = (
        "object_format",
        "root_object_oid",
        "interpretation_kind",
        "interpretation_version",
        "interpretation_scope",
        "annotated_object_oid",
    )
    for values in core.ref_exchange_rows(
        "evidence", identity, work, maximum=maximum, max_bytes=max_bytes
    ):
        row = dict(zip(evidence_columns, values, strict=True))
        from repo_catalog.domain.p1_core import OID

        if (row["object_format"], row["root_object_oid"]) != claim.root_object_oid.key:
            core._integrity_stop((claim.identity, "wrong-evidence-root"))
        target = core._stored(
            claim.identity, OID, row["object_format"], row["annotated_object_oid"]
        )
        projection = core.notes_mapping_projection(
            claim,
            target,
            row["interpretation_kind"],
            row["interpretation_version"],
            row["interpretation_scope"],
            work,
            max_units=maximum,
            max_bytes=max_bytes,
        )
        for record in projection.evidence:
            oids.update(
                (
                    record.mapping.root_object_oid,
                    record.mapping.annotated_object_oid,
                    record.mapping.note_object_oid,
                )
            )
            section["notes_mapping_evidence"].append(
                mapping_evidence_to_wire(claim, record)
            )

    if scope.include_retained_bytes:
        for fmt, object_oid, copy in core.ref_exchange_rows(
            "copies", identity, work, maximum=maximum, max_bytes=max_bytes
        ):
            from repo_catalog.domain.p1_core import OID

            object_oid = core._stored(claim.identity, OID, fmt, object_oid)
            stored_claim, record, native = core.read_ref_note_copy(
                object_oid,
                copy,
                work,
                max_metadata_bytes=max_bytes,
                max_proof_bytes=max_bytes,
            )
            if stored_claim != claim:
                core._integrity_stop((claim.identity, "wrong-physical-copy-claim"))
            wire = mapping_evidence_to_wire(claim, record)
            work.require("input_bytes", 2 * len(native.body))
            try:
                body_hex = native.body.hex()
            except BaseException:
                work.abandon("input_bytes")
                raise
            work.charge("input_bytes", len(body_hex))
            wire.update(
                physical_copy_uuidv4=copy,
                body_hex=body_hex,
                size=native.declared_size,
                digest_sha256=native.digest_sha256,
            )
            section["ref_retained_notes"].append(wire)
            oids.update(
                (
                    record.mapping.root_object_oid,
                    record.mapping.annotated_object_oid,
                    record.mapping.note_object_oid,
                )
            )
    return oids


def _pairs(core, selector, parameters, work, maximum):
    return core.ref_exchange_rows(
        selector, parameters, work, maximum=maximum, max_bytes=72 * maximum
    )


class _ExportWork:
    """Share the selection's work ceiling with the SQL progress handler."""

    def __init__(self, inner, counters, limit):
        self._inner = inner
        self._counters = counters
        self._limit = limit
        self._reserved = {}

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def require(self, unit, amount=1):
        tracked = unit in ("metadata_units", "proof_steps")
        if tracked:
            if self._counters["work"] + amount > self._limit:
                raise CoreFailure(
                    "QUERY_BUDGET", "ref-exchange", "finite cumulative export work"
                )
            self._counters["work"] += amount
        try:
            self._inner.require(unit, amount)
        except BaseException:
            if tracked:
                self._counters["work"] -= amount
            raise
        if tracked:
            self._reserved[unit] = amount

    def charge(self, unit, amount):
        self._inner.charge(unit, amount)
        if unit in self._reserved:
            self._counters["work"] -= self._reserved.pop(unit) - amount

    def abandon(self, unit):
        self._inner.abandon(unit)
        self._reserved.pop(unit, None)


def ref_export_work(scope, counters):
    inner = UnlimitedWorkBudget(
        note_bytes=max(NotesLimits().note_bytes, scope.max_bytes),
        work_limits={
            # max_bytes bounds emitted output; it must not prohibit the
            # finite accounting work needed to identify and omit a larger
            # complete unit. The underlying NotesLimits supplies independent
            # finite input/verification ceilings.
            "metadata_units": max(1, scope.max_work),
            "proof_steps": max(1, scope.max_work),
        },
    )
    return _ExportWork(inner, counters, scope.max_work)


def export_ref_units(core, section, scope, work, omissions):
    """Select original observations and complete original enumeration events.

    Selecting an event member includes its entire original event and sibling
    members as dependencies; an event is never emitted with a truncated set.
    Object-only selection starts from an actually claimed root, not rootless
    observations. A direct ref key is independent of an object selector.
    """
    maximum = scope.max_units
    if maximum == 0:
        return set()
    chosen = set(scope.ref_observation_keys or ())
    pending_events = set()
    with core._snapshot():
        if scope.object_oids is None and scope.ref_observation_keys is None:
            pairs = _pairs(
                core,
                "observations",
                (),
                work,
                maximum,
            )
            chosen.update(RefObservationKey(*pair) for pair in pairs)
            if scope.notes_refs is None:
                pending_events.update(
                    _pairs(
                        core,
                        "enumerations",
                        (),
                        work,
                        maximum,
                    )
                )
        elif scope.object_oids is not None:
            for object_oid in scope.object_oids:
                pairs = _pairs(
                    core,
                    "root_claims",
                    object_oid.key,
                    work,
                    maximum,
                )
                chosen.update(RefObservationKey(*pair) for pair in pairs)

        pending = set(chosen)
        expand_event_members = (
            scope.ref_observation_keys is not None or scope.object_oids is None
        )
        visited = set()
        required_members = set()
        events = {}
        projections = {}
        while pending or pending_events:
            if (
                len(visited) + len(pending) + len(events) + len(pending_events)
                > maximum
            ):
                raise CoreFailure(
                    "QUERY_BUDGET", "ref-exchange", "finite dependency limit"
                )
            while pending:
                key = min(pending)
                pending.remove(key)
                if key in visited:
                    continue
                visited.add(key)
                try:
                    projection = core.ref_observation(
                        key,
                        work,
                        max_claims=max(1, maximum),
                        max_bytes=max(1, scope.max_bytes),
                    )
                except CoreFailure as error:
                    if error.code == "OBSERVATION_UNAVAILABLE" and key in chosen:
                        omissions.append(
                            {
                                "section": "ref_observations",
                                "unit": list(key.key),
                                "reason": "selected_observation_unavailable",
                            }
                        )
                        continue
                    raise
                if (
                    scope.repository_uuidv4s is not None
                    and projection.ref_observation.repository_uuidv4
                    not in scope.repository_uuidv4s
                ):
                    if key in chosen:
                        omissions.append(
                            {
                                "section": "ref_observations",
                                "unit": list(key.key),
                                "reason": "repository_not_selected",
                            }
                        )
                    continue
                if (
                    key in chosen
                    and key not in required_members
                    and scope.notes_refs is not None
                ):
                    work.require(
                        "input_bytes", len(projection.ref_observation.ref_name_bytes)
                    )
                    try:
                        ref_name = projection.ref_observation.ref_name_bytes.decode(
                            "utf-8", "surrogateescape"
                        )
                    except BaseException:
                        work.abandon("input_bytes")
                        raise
                    work.charge(
                        "input_bytes", len(projection.ref_observation.ref_name_bytes)
                    )
                    if ref_name not in scope.notes_refs:
                        # It can still be added later as a dependency of a
                        # selected member's whole original enumeration.
                        visited.remove(key)
                        continue
                projections[key.key] = projection
                pending_events.update(
                    _pairs(
                        core,
                        "links",
                        key.key,
                        work,
                        maximum,
                    )
                )
            if pending_events:
                identity = min(pending_events)
                pending_events.remove(identity)
                if identity in events:
                    continue
                event = core.ref_enumeration(
                    *identity,
                    work,
                    max_links=max(1, maximum),
                    max_bytes=max(1, scope.max_bytes),
                )
                if event is None:
                    core._integrity_stop((identity, "missing selected enumeration"))
                if (
                    scope.repository_uuidv4s is not None
                    and event.event.repository_uuidv4 not in scope.repository_uuidv4s
                ):
                    continue
                if not expand_event_members and any(
                    link.observation.ref_observation_key.key not in projections
                    for link in event.links
                ):
                    # An object-only request does not turn unrelated or rootless
                    # event members into object matches. The event is omitted as
                    # a whole rather than publishing a truncated enumeration.
                    omissions.append(
                        {
                            "section": "ref_enumeration_observations",
                            "unit": list(identity),
                            "reason": "whole_enumeration_not_selected",
                        }
                    )
                    continue
                events[identity] = event
                required_members.update(
                    link.observation.ref_observation_key for link in event.links
                )
                pending.update(
                    link.observation.ref_observation_key
                    for link in event.links
                    if link.observation.ref_observation_key not in visited
                )

        oids = set()
        for key in sorted(projections):
            projection = projections[key]
            section["ref_observations"].append(
                observation_to_wire(projection.ref_observation)
            )
            for claim in projection.claims:
                section["ref_observation_claims"].append(claim_to_wire(claim))
                oids.update(
                    object_oid
                    for object_oid in (
                        claim.direct_target_object_oid,
                        claim.resolved_target_object_oid,
                        claim.peeled_target_object_oid,
                        claim.root_object_oid,
                    )
                    if object_oid is not None
                )
                oids.update(_export_ref_notes(core, section, claim, work, scope))
        for identity in sorted(events):
            event = events[identity]
            section["ref_enumeration_observations"].append(
                enumeration_to_wire(event.event)
            )
            section["ref_enumeration_links"].extend(
                link_to_wire(link) for link in event.links
            )
        return oids


def import_ref_units(core, section, work):
    observations, claims, events, links = decode_ref_units(section)
    for key in sorted(observations):
        core.admit_ref_observation(observations[key])
    for key in sorted(claims):
        core.admit_ref_observation_claim(claims[key])
    for key in sorted(events):
        bucket = links.get(key, {})
        core.admit_ref_enumeration(
            events[key], tuple(bucket[position] for position in sorted(bucket)), work
        )
    return claims


def import_ref_notes(core, section, claims, work, receiver_instance):
    """Recheck imported structures and bodies, binding local verification anew."""

    def owner(row):
        identity = (
            row["observation_origin_uuidv4"],
            row["ref_observation_uuidv7"],
            row["ref_claim_provenance_json"],
        )
        if identity not in claims:
            raise CoreFailure("NOTES_ROLE", identity, "original result claim missing")
        return claims[identity]

    def local_evidence(evidence):
        # The sender's verification coordinate is retained as attribution in
        # the new local check; only this actual receiver's recheck is authority.
        original = _original_lineage(evidence.provenance, "source-evidence", work)
        claim = evidence.ref_claim
        mapping = evidence.mapping
        provenance = Provenance(
            "exchange-receiver:" + receiver_instance,
            encode_metered(work, ["source-evidence", *original.key]),
            encode_metered(
                work,
                [
                    "claim",
                    *claim.ref_observation_key.key,
                    list(claim.provenance.key),
                    "mapping",
                    *mapping.root_object_oid.key,
                    mapping.interpretation_kind,
                    mapping.interpretation_version,
                    mapping.interpretation_scope,
                    *mapping.annotated_object_oid.key,
                    *mapping.note_object_oid.key,
                    mapping.mapping_path,
                ],
            ),
            "native-notes",
            "1",
            "receiver_intrinsic",
        )
        return replace(evidence, provenance=provenance)

    for row in section["notes_mapping_claims"]:
        _performed("metadata_units", 1)
        core.admit_notes_mapping_claim(mapping_claim_from_wire(row, owner(row)))
    for row in section["notes_mapping_groups"]:
        _performed("metadata_units", 1)
        core.admit_notes_mapping_group(mapping_group_from_wire(row, owner(row)), work)
    for row in section["notes_mapping_evidence"]:
        _performed("metadata_units", 1)
        evidence = mapping_evidence_from_wire(row, owner(row))
        # Preserve the original evidence coordinate, but only after validating
        # its structure here; separately record this receiver's actual check.
        core.admit_notes_mapping_evidence(evidence, work)
        core.admit_notes_mapping_evidence(local_evidence(evidence), work)
    for row in section["ref_retained_notes"]:
        _performed("metadata_units", 1)
        evidence = mapping_evidence_from_wire(row, owner(row))
        native, copy = ref_note_from_wire(row, evidence)
        # Constructor-only preflight must check the body even though it has no DB.
        native.validate()
        core.admit_ref_note(evidence, native, copy, work)
        core.admit_notes_mapping_evidence(local_evidence(evidence), work)


def _original_lineage(provenance, label, work):
    """Keep our own transfer checks from recursively nesting on onward replay."""
    import json

    if not provenance.source.startswith("exchange-receiver:"):
        return provenance
    _performed("input_bytes", len(provenance.observation))
    try:
        value = json.loads(provenance.observation)
        if type(value) is not list or len(value) != 7 or value[0] != label:
            return provenance
        original = Provenance(*value[1:])
        if encode_metered(work, value) != provenance.observation:
            return provenance
        return original
    except (TypeError, ValueError):
        return provenance


def import_ref_coverage(core, section, claims, work, receiver_instance):
    """Recompute complete inventories; sender completeness flags grant no proof."""
    import json

    from repo_catalog.application.ref_observations import encode_metered
    from repo_catalog.domain.p1_core import CoreCoverageScope
    from repo_catalog.domain.p1_coverage import CoverageClaim
    from repo_catalog.domain.ref_coverage import (
        RefNotesInventoryCoverageProof,
        deserialize_structures,
        verify_ref_notes_inventory,
    )
    from repo_catalog.domain.ref_exchange import _provenance

    for row in section["ref_coverage_proofs"]:
        _performed("metadata_units", 1)
        _performed("input_bytes", len(row["group_json"]))
        group_row = json.loads(row["group_json"])
        if type(group_row) is not dict or encode(group_row) != row["group_json"]:
            raise CoreFailure(
                "REF_COVERAGE_PROOF", "group", "canonical original group required"
            )
        identity = (
            group_row["observation_origin_uuidv4"],
            group_row["ref_observation_uuidv7"],
            group_row["ref_claim_provenance_json"],
        )
        if identity not in claims:
            raise CoreFailure(
                "REF_COVERAGE_PROOF", identity, "original result claim missing"
            )
        group = mapping_group_from_wire(group_row, claims[identity])
        scope = CoreCoverageScope(
            row["owner_kind"], tuple(json.loads(row["owner_coordinates_json"]))
        )
        coverage = CoverageClaim(scope, row["observed_at_us"], row["coverage_state"])
        structures = deserialize_structures(
            row["structures_json"],
            work,
            max_structures=100_000,
            max_bytes=64 * 1024 * 1024,
        )
        proof = RefNotesInventoryCoverageProof(
            coverage,
            group,
            _provenance(row["verification_provenance_json"]),
            structures,
        )
        # The constructor-only preflight has no Core writer, so re-run the
        # complete traversal here as well as in the actual admission boundary.
        verify_ref_notes_inventory(
            proof, work, max_structures=100_000, max_bytes=64 * 1024 * 1024
        )
        core.admit_ref_coverage_proof(proof, work)
        local = replace(
            proof,
            verification_provenance=Provenance(
                "exchange-receiver:" + receiver_instance,
                encode_metered(
                    work,
                    [
                        "source-inventory-evidence",
                        *_original_lineage(
                            proof.verification_provenance,
                            "source-inventory-evidence",
                            work,
                        ).key,
                    ],
                ),
                encode_metered(
                    work,
                    [
                        "claim",
                        *group.ref_claim.ref_observation_key.key,
                        list(group.ref_claim.provenance.key),
                        "group",
                        *group.ref_claim.root_object_oid.key,
                        group.interpretation_kind,
                        group.interpretation_version,
                        group.interpretation_scope,
                        group.group_scope,
                        list(group.provenance.key),
                    ],
                ),
                "git-native-notes-inventory",
                "1",
                "receiver_intrinsic",
            ),
        )
        core.admit_ref_coverage_proof(local, work)
