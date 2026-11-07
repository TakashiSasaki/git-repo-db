"""Core-specific Search integration and exact-Claim Notes authority reads."""

from __future__ import annotations

from repo_catalog.application.core_query import CoreQueryService
from repo_catalog.application.query_encoding import encode_metered
from repo_catalog.application.search_query import SearchReader
from repo_catalog.domain.core_query import ref_projection_json
from repo_catalog.domain.p1_core import OID, CoreFailure
from repo_catalog.domain.query_contracts import QueryError
from repo_catalog.domain.ref_observation import NotesMapping, RefObservationKey


class CoreSearchReader:
    def _extract_ref_notes_documents(self, core, work):
        from repo_catalog.adapters.sqlite.production_search import BoundedDocuments

        docs = BoundedDocuments()
        summaries = {}
        summary_bytes = 0
        keys = core.sql(
            "SELECT observation_origin_uuidv4,ref_observation_uuidv7 FROM ref_observations ORDER BY 1,2 LIMIT 10001"
        )
        if len(keys) > 10000:
            raise QueryError(
                "QUERY_BUDGET", "ref-notes-search", "finite observation scope"
            )
        for key in keys:
            observed = core.ref_observation(self._stored(RefObservationKey, *key), work)
            subject = observed.ref_observation
            for claim in observed.claims:
                if claim.root_object_oid is None:
                    continue
                inventory = core.ref_notes_inventory_projection(claim, work)
                provenance = encode_metered(work, claim.provenance.key, 1024 * 1024)
                claim_coordinates = (*claim.ref_observation_key.key, provenance)
                coordinates = {}

                def coordinate(values):
                    encoded = encode_metered(work, values, 1024 * 1024)
                    work.require("input_bytes", len(encoded))
                    coordinates[encoded] = values
                    work.charge("input_bytes", len(encoded))

                for reported in inventory.groups:
                    group = reported.group
                    for target, _, _ in group.members:
                        work.require("metadata_units", 1)
                        work.charge("metadata_units", 1)
                        coordinate(
                            (
                                claim.root_object_oid.object_format,
                                target,
                                group.interpretation_kind,
                                group.interpretation_version,
                                group.interpretation_scope,
                            )
                        )
                for table in ("notes_mapping_claims", "notes_mapping_evidence"):
                    where = " WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND ref_claim_provenance=?"
                    columns = "object_format,annotated_object_oid,interpretation_kind,interpretation_version,interpretation_scope"
                    select = (
                        "SELECT "
                        + columns
                        + " FROM "
                        + table
                        + where
                        + " ORDER BY 1,2,3,4,5 LIMIT 10001"
                    )
                    count, size = core.sql(
                        "SELECT count(*),coalesce(sum(octet_length(object_format)+octet_length(annotated_object_oid)+octet_length(interpretation_kind)+octet_length(interpretation_version)+octet_length(interpretation_scope)),0) FROM ("
                        + select
                        + ")",
                        claim_coordinates,
                    )[0]
                    if count > 10000 or size > 1024 * 1024:
                        raise QueryError(
                            "QUERY_BUDGET", "ref-notes-search", "finite header scope"
                        )
                    work.require("input_bytes", size)
                    work.charge("input_bytes", size)
                    work.require("metadata_units", count)
                    work.charge("metadata_units", count)
                    for row in core.sql(select, claim_coordinates):
                        coordinate(tuple(row))
                for fmt, target, kind, version, scope in coordinates.values():
                    projection = core.notes_mapping_projection(
                        claim,
                        self._stored(OID, fmt, target),
                        kind,
                        version,
                        scope,
                        work,
                    )
                    mappings = {}
                    sources = {}
                    verified = set()

                    def remember(mapping, source, checked=False):
                        values = [
                            *mapping.root_object_oid.key,
                            mapping.interpretation_kind,
                            mapping.interpretation_version,
                            mapping.interpretation_scope,
                            mapping.annotated_object_oid.object_oid,
                            mapping.note_object_oid.object_oid,
                            mapping.mapping_path,
                        ]
                        identity = encode_metered(work, values, 1024 * 1024)
                        work.require("input_bytes", len(identity))
                        mappings[identity] = mapping
                        sources.setdefault(identity, []).append(source)
                        if checked:
                            verified.add(identity)
                        work.charge("input_bytes", len(identity))

                    for reported in projection.claims:
                        remember(reported.mapping, ("claim", reported.provenance))
                    for evidence in projection.evidence:
                        remember(
                            evidence.mapping, ("receiver", evidence.provenance), True
                        )
                    for group in projection.groups:
                        for member_target, note, path in group.members:
                            work.require("metadata_units", 1)
                            work.charge("metadata_units", 1)
                            if member_target == target:
                                remember(
                                    self._stored(
                                        NotesMapping,
                                        claim.root_object_oid,
                                        kind,
                                        version,
                                        scope,
                                        self._stored(OID, fmt, target),
                                        self._stored(OID, fmt, note),
                                        path,
                                    ),
                                    (
                                        "group",
                                        group.provenance,
                                        group.group_scope,
                                        group.status,
                                    ),
                                )
                    for identity, mapping in mappings.items():
                        retained = False
                        raw = b""
                        try:
                            raw = core.read_ref_note(claim, mapping, work)
                            retained = True
                        except CoreFailure as error:
                            if error.code != "NOTES_ROLE_UNAVAILABLE":
                                raise

                        def text(raw):
                            work.require("input_bytes", 4 * len(raw))
                            try:
                                value = raw.decode("utf-8", "backslashreplace")
                            except BaseException:
                                work.abandon("input_bytes")
                                raise
                            work.charge("input_bytes", len(value.encode("utf-8")))
                            return value

                        body = text(raw)
                        ref = text(subject.ref_name_bytes)
                        doc_key = encode_metered(
                            work,
                            [
                                "ref-notes",
                                *claim.ref_observation_key.key,
                                provenance,
                                identity,
                            ],
                            1024 * 1024,
                        )
                        # Leave room for the JSON/checksum/base64 cursor envelope.
                        # Keep the full semantic key; never replace it by a hash.
                        if len(doc_key) > 16384:
                            raise QueryError(
                                "QUERY_BUDGET",
                                "ref-notes-search",
                                "finite cursor key limit",
                            )
                        copy_bytes = 2 * (
                            len(subject.ref_name_bytes)
                            + len(claim.symbolic_target_ref_name or b"")
                        ) + len(identity)
                        work.require("input_bytes", copy_bytes)
                        observed_json = ref_projection_json(subject)
                        claim_json = ref_projection_json(claim)
                        mapping_json = ref_projection_json(mapping)
                        role_verified = identity in verified
                        work.charge("input_bytes", copy_bytes)
                        source_work = 8 * len(sources[identity])
                        work.require("metadata_units", source_work)
                        source_json = ref_projection_json(sources[identity])
                        work.charge("metadata_units", source_work)
                        summary = {
                            "kind": "ref_notes_mapping",
                            "observation": observed_json,
                            "claim": claim_json,
                            "mapping": mapping_json,
                            "sources": source_json,
                            "ref_conflict": observed.conflict,
                            "inventory_coverage": inventory.coverage.state,
                            "role_verified": role_verified,
                            "note_retained": retained,
                            "note_text": body if retained else None,
                        }
                        encoded = encode_metered(work, summary, 1024 * 1024)
                        summary_bytes += len(encoded)
                        if summary_bytes > BoundedDocuments.max_total_bytes:
                            raise QueryError(
                                "QUERY_BUDGET",
                                "ref-notes-search",
                                "finite summary scope",
                            )
                        upper = (
                            len(doc_key)
                            + 4 * (len(ref) + len(body))
                            + len(fmt)
                            + len(target)
                            + len(mapping.note_object_oid.object_oid)
                            + 4
                        )
                        work.require("input_bytes", upper)
                        try:
                            searchable = f"{ref} {fmt} {target} {mapping.note_object_oid.object_oid} {body}"
                            docs[doc_key] = searchable
                        except BaseException:
                            work.abandon("input_bytes")
                            raise
                        work.charge(
                            "input_bytes",
                            len(doc_key) + len(searchable.encode("utf-8")),
                        )
                        summaries[doc_key] = summary
        return docs, summaries


class CoreSearchService(CoreSearchReader, SearchReader, CoreQueryService):
    """Core Search; explicit core_only mode ignores any Context sibling."""
