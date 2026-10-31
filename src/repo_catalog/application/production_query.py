"""Production authoritative query, pagination, snapshot fencing, and Search service (P6).

Supports three explicit catalog topologies without requiring unused stores on disk:
- `core_only`: `core.sqlite3` without `context.sqlite3`
- `context_only`: `context.sqlite3` without `core.sqlite3`
- `paired`: `core.sqlite3` + `context.sqlite3` pinned via `PairCoordinator.snapshots()`

Every read checks `p1-recovery-stop.json` before and after execution.
Every byte read (`read_metadata_bytes`, `read_ref_note_bytes`, `read_context_text`)
runs full integrity verification on the stored representation, immediately
persisting `p1-recovery-stop.json` and raising `AUTHORITATIVE_CORRUPTION` if
tampered.
Every Search response validates derivative candidates against the pinned
authoritative snapshot and falls back transparently to `authority_scan` if
`search.sqlite3` is missing, stale, incomplete, or corrupt without stopping the
catalog.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeVar

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_coordination import (
    PairCoordinator,
    PairedSnapshot,
    SnapshotReadLimits,
    catalog_completion,
)
from repo_catalog.application.core_query import (
    CoreQueryService,
    PinnedCoreSnapshot,
    _paginate_items,
    _QueryWorkBoundary,
    _QueryWorkError,
    _stored_view,
)
from repo_catalog.application.query_encoding import encode_metered
from repo_catalog.domain.p1_core import (
    OID,
    CoreFailure,
)
from repo_catalog.domain.production_query import (
    SEARCH_PROJECTION_KINDS,
    ByteReadResult,
    CatalogReadMode,
    ContextResourceView,
    CoverageView,
    GitObjectView,
    PageRequest,
    PageResult,
    PairedCoreResolution,
    PairedResourceView,
    ProviderView,
    QueryError,
    SearchHit,
    SearchQuery,
    SearchResponse,
    SnapshotFenceToken,
    SourceView,
    ref_projection_json,
    validate_cursor_key,
)
from repo_catalog.domain.query_work import UnlimitedWorkBudget
from repo_catalog.domain.ref_observation import NotesMapping, RefObservationKey

if TYPE_CHECKING:
    from repo_catalog.adapters.sqlite.production_context import Context
    from repo_catalog.domain.p1_context import (
        CoverageScope,
        MappingOperationEvidence,
        ResourceKey,
    )
    from repo_catalog.domain.production_context import (
        ResourceRelation,
    )
    from repo_catalog.domain.ref_observation import (
        NotesMapping,
        RefObservationKey,
    )

T = TypeVar("T")


@dataclass
class PinnedCatalogSnapshot(PinnedCoreSnapshot):
    """An open, consistent read-only snapshot across the active catalog topology."""

    context: Context | None = None
    pair: PairedSnapshot | None = None


class ProductionQueryService(CoreQueryService):
    """Authoritative query, pagination, byte-verification, and Search service."""

    def transfer_event_reports(self, *args, **kwargs):
        from repo_catalog.domain.resource_stage import UnsupportedResourceStage

        raise UnsupportedResourceStage("query Transfer events")

    def __init__(
        self,
        directory: Path | str,
        *,
        mode: CatalogReadMode | Literal["auto"] = "auto",
        read_limits: SnapshotReadLimits = SnapshotReadLimits(),
        mapping_evidence: MappingOperationEvidence | None = None,
    ):
        if mapping_evidence is not None:
            from repo_catalog.domain.p1_context import MappingOperationEvidence

            if not isinstance(mapping_evidence, MappingOperationEvidence):
                raise ValueError("MappingOperationEvidence required")
        self.mapping_evidence = mapping_evidence
        super().__init__(directory, mode=mode, read_limits=read_limits)
        self._search_adapter = None

    @property
    def search_adapter(self):
        if self._search_adapter is None:
            from repo_catalog.adapters.sqlite.production_search import (
                ProductionSearchAdapter,
            )

            self._search_adapter = ProductionSearchAdapter(self.directory)
        return self._search_adapter

    @search_adapter.setter
    def search_adapter(self, adapter):
        self._search_adapter = adapter

    def _mapping_filter(self) -> dict[str, object]:
        from repo_catalog.domain.p1_context import MappingOperationEvidence

        evidence = self.mapping_evidence or MappingOperationEvidence()
        return {
            "confirmed": sorted(
                k.coordinates() for k in evidence.confirmed_disposition_keys
            ),
            "contradicted": sorted(
                k.coordinates() for k in evidence.contradicted_disposition_keys
            ),
        }

    def detect_mode(self) -> CatalogReadMode:
        self._check_stop()
        has_core = (self.directory / "core.sqlite3").is_file()
        has_context = (self.directory / "context.sqlite3").is_file()
        if self._requested_mode != "auto":
            if self._requested_mode == "paired" and not (has_core and has_context):
                raise QueryError(
                    "STORE_UNAVAILABLE",
                    "paired",
                    "paired mode requires both core.sqlite3 and context.sqlite3",
                )
            if self._requested_mode == "core_only" and not has_core:
                raise QueryError(
                    "STORE_UNAVAILABLE",
                    "core_only",
                    "core_only mode requires core.sqlite3",
                )
            if self._requested_mode == "context_only" and not has_context:
                raise QueryError(
                    "STORE_UNAVAILABLE",
                    "context_only",
                    "context_only mode requires context.sqlite3",
                )
            return self._requested_mode
        if has_core and has_context:
            return "paired"
        if has_core:
            return "core_only"
        if has_context:
            return "context_only"
        raise QueryError(
            "STORE_UNAVAILABLE",
            "catalog",
            f"no authoritative store found in {self.directory}",
        )

    @contextmanager
    def _open_snapshot(
        self,
        *,
        required_store: Literal["core", "context", "paired", "any"] = "any",
    ) -> Iterator[PinnedCatalogSnapshot]:
        """Pin a read-only snapshot across the active catalog stores."""
        self._check_stop()
        mode = self.detect_mode()
        if required_store == "paired" and mode != "paired":
            raise QueryError(
                "STORE_UNAVAILABLE",
                "paired",
                f"paired query requires paired catalog mode (current: {mode})",
            )
        if required_store == "core" and mode == "context_only":
            raise QueryError(
                "STORE_UNAVAILABLE",
                "core",
                "Core query requires core.sqlite3",
            )
        if required_store == "context" and mode == "core_only":
            raise QueryError(
                "STORE_UNAVAILABLE",
                "context",
                "Context query requires context.sqlite3",
            )

        if mode == "paired":
            from repo_catalog.adapters.sqlite.production_context import Context

            coordinator = PairCoordinator(
                self.directory, read_limits=self.read_limits, metadata_only=True
            )
            with coordinator.snapshots() as pair:
                self.last_costs_ns.update(coordinator.last_read_costs_ns)
                token = SnapshotFenceToken.from_pair_token(pair.token)
                with (
                    GitCore.for_snapshot(pair.core, self.directory) as core,
                    Context.for_snapshot(pair.context, self.directory) as context,
                ):
                    yield PinnedCatalogSnapshot(
                        mode="paired",
                        token=token,
                        core=core,
                        context=context,
                        pair=pair,
                    )
                with catalog_completion(self.directory):
                    self._check_stop()
        elif mode == "core_only":
            with super()._open_snapshot(required_store=required_store) as snapshot:
                yield PinnedCatalogSnapshot(
                    mode=snapshot.mode, token=snapshot.token, core=snapshot.core
                )
        else:
            from repo_catalog.adapters.sqlite.production_context import Context

            with Context.snapshot(
                self.directory, read_limits=self.read_limits
            ) as context:
                identity_started = time.perf_counter_ns()
                repo_id, inst_id = context.snapshot_identity()
                self.last_costs_ns["authority_identity_validation"] = (
                    time.perf_counter_ns() - identity_started
                )
                token_started = time.perf_counter_ns()
                ctx_hash = context.snapshot_fingerprint()
                self.last_costs_ns["snapshot_token_generation"] = (
                    time.perf_counter_ns() - token_started
                )
                token = SnapshotFenceToken(
                    mode="context_only",
                    repository_uuidv4=repo_id,
                    catalog_instance_uuidv4=inst_id,
                    core_sha256=None,
                    context_sha256=ctx_hash,
                )
                yield PinnedCatalogSnapshot(
                    mode="context_only",
                    token=token,
                    context=context,
                )
                with catalog_completion(self.directory):
                    self._check_stop()

    # ------------------------------------------------------------------
    # Git Core Authoritative Queries
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Context Authoritative Queries
    # ------------------------------------------------------------------

    def list_providers(self) -> tuple[ProviderView, ...]:
        with self.open_snapshot(required_store="context") as snap:
            assert snap.context is not None
            rows = snap.context.db.execute(
                "SELECT service_instance_uuidv4,provider_kind,configuration_json "
                "FROM providers ORDER BY service_instance_uuidv4"
            ).fetchall()
            return tuple(
                ProviderView(
                    service_instance_uuidv4=r[0],
                    provider_kind=r[1],
                    configuration=snap.context.registration_metadata("provider", r[2]),
                )
                for r in rows
            )

    def list_source_views(
        self, service_instance_uuidv4: str | None = None
    ) -> tuple[SourceView, ...]:
        from repo_catalog.domain.production_context import SourceInventory

        with self.open_snapshot(required_store="context") as snap:
            assert snap.context is not None
            rows = snap.context.db.execute(
                "SELECT source_registration_uuidv4,service_instance_uuidv4,configuration_json "
                "FROM sources WHERE (? IS NULL OR service_instance_uuidv4=?) "
                "ORDER BY source_registration_uuidv4",
                (service_instance_uuidv4, service_instance_uuidv4),
            ).fetchall()
            views: list[SourceView] = []
            for s_id, svc_id, cfg_json in rows:
                repos = snap.context.source_repositories(s_id)
                inv_rows = snap.context.db.execute(
                    "SELECT scope_json,observed_at_us,coverage_state,terminal,members_json,provenance_json "
                    "FROM source_inventory_evidence WHERE source_registration_uuidv4=? "
                    "ORDER BY observed_at_us,scope_json,provenance_json",
                    (s_id,),
                ).fetchall()
                inventories = tuple(
                    SourceInventory(
                        source_registration_uuidv4=s_id,
                        scope_json=ir[0],
                        observed_at_us=ir[1],
                        state=ir[2],
                        terminal=bool(ir[3]),
                        repositories=tuple(json.loads(ir[4])),
                        provenance_json=ir[5],
                    )
                    for ir in inv_rows
                )
                views.append(
                    SourceView(
                        source_registration_uuidv4=s_id,
                        service_instance_uuidv4=svc_id,
                        configuration=snap.context.registration_metadata(
                            "source", cfg_json
                        ),
                        repositories=repos,
                        inventories=inventories,
                    )
                )
            return tuple(views)

    def get_context_resource(
        self,
        resource_key: ResourceKey,
        *,
        include_text: bool = True,
    ) -> ContextResourceView:
        with self.open_snapshot(required_store="context") as snap:
            assert snap.context is not None
            validate_core = None
            if snap.core is not None:
                core_ref = snap.core

                def _check_core(fmt: str, oid_hex: str) -> bool:
                    return bool(
                        core_ref.sql(
                            "SELECT 1 FROM git_objects WHERE object_format=? AND object_oid=?",
                            (fmt, oid_hex),
                        )
                    )

                validate_core = _check_core
            return self._context_resource_in_snapshot(
                snap.context,
                resource_key,
                include_text=include_text,
                validate_core=validate_core,
            )

    @_stored_view
    def _context_resource_in_snapshot(
        self,
        context: Context,
        resource_key: ResourceKey,
        *,
        include_text: bool = True,
        validate_core: Callable[[str, str], bool] | None = None,
    ) -> ContextResourceView:
        from repo_catalog.domain.p1_context import ResourceKey
        from repo_catalog.domain.production_context import CollectionObservation

        row = context.db.execute(
            "SELECT identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id "
            "FROM resources WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
            resource_key.coordinates(),
        ).fetchone()
        if row is None:
            raise QueryError(
                "RESOURCE_NOT_FOUND",
                resource_key,
                f"Context resource {resource_key} not found",
            )
        identification = context.identification(resource_key)
        identifier_namespace = (
            self._stored(
                ResourceKey,
                resource_key.service_instance_uuidv4,
                identification.identifier_namespace_kind,
                identification.identifier_namespace_id,
            )
            if identification.identifier_namespace_kind is not None
            else None
        )
        document_kind = identification.document_kind
        provider_document_id = identification.provider_document_id

        field_names = [
            r[0]
            for r in context.db.execute(
                "SELECT DISTINCT field_name FROM field_candidates "
                "WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? "
                "ORDER BY field_name",
                resource_key.coordinates(),
            ).fetchall()
        ]
        fields: dict[str, tuple] = {}
        for fname in field_names:
            fields[fname] = context.candidates(resource_key, fname)

        repo_roles = context.provider_repository_roles(
            resource_key, evidence=self.mapping_evidence
        )
        repo_relations = context.repository_relations(
            resource_key, evidence=self.mapping_evidence
        )
        primary_kind = {
            "issue": "owning_repository",
            "pull_request": "base_repository",
        }.get(resource_key.resource_kind)
        primary = tuple(r for r in repo_roles if r.scope.relation_kind == primary_kind)
        # Convenience projection only when every current report agrees on one
        # undisputed Mapping candidate. Full qualified alternatives remain below.
        targets = {
            target
            for role in primary
            if role.mapping is not None
            for target in role.mapping.active_repository_uuidv4s
        }
        repo_uuid = (
            next(iter(targets))
            if len(targets) == 1
            and primary
            and all(r.state == "single_candidate" for r in primary)
            else None
        )

        resolved_texts: dict[str, str | None] = {}
        if include_text and "text_body_sha256" in fields:
            for cand in fields["text_body_sha256"]:
                digest = json.loads(cand.value_json)
                if digest is None:
                    resolved_texts[cand.provenance_json] = None
                elif isinstance(digest, str):
                    resolved_texts[digest] = context.read_text(digest)

        rel_kinds = [
            r[0]
            for r in context.db.execute(
                "SELECT DISTINCT relation_kind FROM resource_relations "
                "WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? "
                "ORDER BY relation_kind",
                resource_key.coordinates(),
            ).fetchall()
        ]
        all_relations: list[ResourceRelation] = []
        for rkind in rel_kinds:
            all_relations.extend(context.relations(resource_key, rkind))

        col_rows = context.db.execute(
            "SELECT c.collection_kind,c.provenance_json,c.scope_json,"
            "t.observed_at_us,t.terminal_state,t.members_json "
            "FROM collections c JOIN collection_terminals t "
            "ON c.service_instance_uuidv4=t.service_instance_uuidv4 "
            "AND c.resource_kind=t.resource_kind "
            "AND c.provider_resource_id=t.provider_resource_id "
            "AND c.collection_kind=t.collection_kind "
            "AND c.provenance_json=t.provenance_json "
            "WHERE c.service_instance_uuidv4=? AND c.resource_kind=? AND c.provider_resource_id=? "
            "ORDER BY c.collection_kind,t.observed_at_us,c.provenance_json",
            resource_key.coordinates(),
        ).fetchall()
        collections = tuple(
            self._stored(
                CollectionObservation,
                resource=resource_key,
                collection_kind=cr[0],
                provenance_json=cr[1],
                scope_json=cr[2],
                observed_at_us=cr[3],
                state=cr[4],
                members=tuple(self._stored(ResourceKey, *m) for m in json.loads(cr[5])),
            )
            for cr in col_rows
        )

        core_deps = context.core_dependencies(resource_key, validate=validate_core)

        return ContextResourceView(
            resource=resource_key,
            repository_uuidv4=repo_uuid,
            repository_roles=repo_roles,
            repository_relations=repo_relations,
            identification=identification,
            identifier_namespace=identifier_namespace,
            document_kind=document_kind,
            provider_document_id=provider_document_id,
            fields=fields,
            resolved_texts=resolved_texts,
            relations=tuple(all_relations),
            collections=collections,
            core_dependencies=core_deps,
        )

    def list_context_resources(
        self,
        page: PageRequest = PageRequest(),
        *,
        service_instance_uuidv4: str | None = None,
        resource_kind: str | None = None,
        repository_uuidv4: str | None = None,
        identifier_namespace: ResourceKey | None = None,
        parent: ResourceKey | None = None,
    ) -> PageResult[ContextResourceView]:
        if parent is not None:
            raise QueryError(
                "I2_PARENT_QUERY_UNSUPPORTED",
                "parent",
                "semantic Parent queries require I3",
            )
        with self.open_snapshot(required_store="context") as snap:
            assert snap.context is not None
            token_str = snap.token.encode()
            validate_core = None
            if snap.core is not None:
                core_ref = snap.core

                def _check_core_list(fmt: str, oid_hex: str) -> bool:
                    return bool(
                        core_ref.sql(
                            "SELECT 1 FROM git_objects WHERE object_format=? AND object_oid=?",
                            (fmt, oid_hex),
                        )
                    )

                validate_core = _check_core_list
            keys = snap.context.resources(kind=resource_kind)

            def views():
                for key in keys:
                    if (
                        service_instance_uuidv4 is not None
                        and key.service_instance_uuidv4 != service_instance_uuidv4
                    ):
                        continue
                    view = self._context_resource_in_snapshot(
                        snap.context,
                        key,
                        include_text=False,
                        validate_core=validate_core,
                    )
                    if repository_uuidv4 is not None and not view.matches_repository(
                        repository_uuidv4
                    ):
                        continue
                    if (
                        identifier_namespace is not None
                        and view.identifier_namespace != identifier_namespace
                    ):
                        continue
                    yield view

            selected = _paginate_items(
                views(),
                cursor_validator=validate_cursor_key,
                key_fn=lambda v: v.semantic_key,
                page=page,
                endpoint_kind="context_resources",
                filters={
                    "identifier_namespace": list(identifier_namespace.coordinates())
                    if identifier_namespace
                    else None,
                    "mapping_evidence": self._mapping_filter(),
                    "repository_uuidv4": repository_uuidv4,
                    "resource_kind": resource_kind,
                    "service_instance_uuidv4": service_instance_uuidv4,
                },
                snapshot_token=token_str,
            )

            return replace(
                selected,
                items=tuple(
                    self._context_resource_in_snapshot(
                        snap.context,
                        view.resource,
                        include_text=True,
                        validate_core=validate_core,
                    )
                    for view in selected.items
                ),
            )

    def read_context_text(self, text_sha256: str) -> ByteReadResult:
        from repo_catalog.domain.production_context import ContextError

        with self.open_snapshot(required_store="context") as snap:
            assert snap.context is not None
            try:
                text_val = snap.context.read_text(text_sha256)
            except ContextError as error:
                if error.code == "TEXT_UNAVAILABLE":
                    return ByteReadResult(available=False, verified=False)
                raise
            raw = text_val.encode("utf-8")
            return ByteReadResult(
                available=True,
                verified=True,
                body_bytes=raw,
                text_value=text_val,
                declared_size=len(raw),
                digest_sha256=text_sha256,
            )

    def get_context_coverage(self, scope: CoverageScope) -> CoverageView:
        with self.open_snapshot(required_store="context") as snap:
            assert snap.context is not None
            proj = snap.context.coverage(scope)
            return CoverageView(
                scope=scope,
                state=proj.state,
                known_empty=proj.known_empty,
                latest_observed_at_us=proj.observed_at_us,
                claims=proj.claims,
            )

    # ------------------------------------------------------------------
    # Paired Cross-Store Queries
    # ------------------------------------------------------------------

    def get_paired_resource(
        self,
        resource_key: ResourceKey,
        *,
        include_text: bool = True,
        include_core_bytes: bool = False,
    ) -> PairedResourceView:
        with self.open_snapshot(required_store="paired") as snap:
            assert snap.core is not None and snap.context is not None
            return self._paired_resource_in_snapshot(
                snap.core,
                snap.context,
                snap.token.encode(),
                resource_key,
                include_text=include_text,
                include_core_bytes=include_core_bytes,
            )

    def _paired_resource_in_snapshot(
        self,
        core: GitCore,
        context: Context,
        token_str: str,
        resource_key: ResourceKey,
        *,
        include_text: bool = True,
        include_core_bytes: bool = False,
        ref_work=None,
    ) -> PairedResourceView:
        ref_work = ref_work if ref_work is not None else UnlimitedWorkBudget()

        def check_in_core(fmt: str, object_oid: str) -> bool:
            return bool(
                core.sql(
                    "SELECT 1 FROM git_objects WHERE object_format=? AND object_oid=?",
                    (fmt, object_oid),
                )
            )

        ctx_view = self._context_resource_in_snapshot(
            context,
            resource_key,
            include_text=include_text,
            validate_core=check_in_core,
        )

        resolutions: list[PairedCoreResolution] = []
        for dep in ctx_view.core_dependencies:
            object_oid = dep.reference.object_oid
            obj_view: GitObjectView | None = None
            if dep.available:
                obj_view = self._git_object_in_snapshot(
                    core,
                    object_oid,
                    include_bytes=include_core_bytes,
                    ref_work=ref_work,
                )
            resolutions.append(
                PairedCoreResolution(
                    reference=dep.reference,
                    available_in_core=dep.available,
                    core_required=dep.required,
                    object_view=obj_view,
                    ref_notes_targets=obj_view.ref_notes_targets
                    if obj_view is not None
                    else (),
                )
            )

        return PairedResourceView(
            context_resource=ctx_view,
            core_resolutions=tuple(resolutions),
            snapshot_token=token_str,
        )

    def list_paired_resources(
        self,
        page: PageRequest = PageRequest(),
        *,
        resource_kind: str | None = None,
        repository_uuidv4: str | None = None,
    ) -> PageResult[PairedResourceView]:
        with self.open_snapshot(required_store="paired") as snap:
            assert snap.core is not None and snap.context is not None
            token_str = snap.token.encode()
            keys = snap.context.resources(kind=resource_kind)

            ref_work = UnlimitedWorkBudget()

            def views():
                for key in keys:
                    paired_view = self._paired_resource_in_snapshot(
                        snap.core,
                        snap.context,
                        token_str,
                        key,
                        include_text=False,
                        ref_work=ref_work,
                    )
                    if (
                        repository_uuidv4 is not None
                        and not paired_view.context_resource.matches_repository(
                            repository_uuidv4
                        )
                    ):
                        continue
                    yield paired_view

            selected = _paginate_items(
                views(),
                cursor_validator=validate_cursor_key,
                key_fn=lambda v: v.resource.coordinates(),
                page=page,
                endpoint_kind="paired_resources",
                filters={
                    "mapping_evidence": self._mapping_filter(),
                    "repository_uuidv4": repository_uuidv4,
                    "resource_kind": resource_kind,
                },
                snapshot_token=token_str,
            )

            return replace(
                selected,
                items=tuple(
                    self._paired_resource_in_snapshot(
                        snap.core,
                        snap.context,
                        token_str,
                        view.resource,
                        ref_work=ref_work,
                    )
                    for view in selected.items
                ),
            )

    # ------------------------------------------------------------------
    # Derivative Search Rebuild and Verification-Aware Querying
    # ------------------------------------------------------------------

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

    @_stored_view
    def _extract_documents(self, snapshot, kind, work=None):
        from repo_catalog.adapters.sqlite.production_search import (
            ProductionSearchAdapter,
        )

        if kind == "git_metadata":
            return ProductionSearchAdapter.extract_git_metadata_documents(snapshot.core)
        if kind == "notes":
            try:
                return self._extract_ref_notes_documents(snapshot.core, work)
            except CoreFailure as error:
                if error.code in ("BUDGET", "QUERY_BUDGET"):
                    raise QueryError(
                        "QUERY_BUDGET", "ref-notes-search", str(error)
                    ) from error
                raise
        return ProductionSearchAdapter.extract_context_documents(
            snapshot.context, evidence=self.mapping_evidence
        )

    def rebuild_search(
        self, projection_kinds: Sequence[str] = SEARCH_PROJECTION_KINDS, *, work=None
    ):
        guarded = _QueryWorkBoundary(
            work if work is not None else UnlimitedWorkBudget()
        )
        try:
            return self._rebuild_search(projection_kinds, guarded)
        except _QueryWorkError as error:
            raise error.original from None

    def _rebuild_search(
        self,
        projection_kinds: Sequence[str],
        work,
    ) -> dict[str, int]:
        """Rebuild requested Search projections from a single pinned snapshot."""
        for kind in projection_kinds:
            if kind not in SEARCH_PROJECTION_KINDS:
                raise QueryError("INVALID_PROJECTION_KIND", "search", str(kind))

        with self.open_snapshot() as snap:
            token_str = snap.token.encode()
            counts: dict[str, int] = {}
            for kind in projection_kinds:
                if kind in ("git_metadata", "notes") and snap.core is None:
                    continue
                if kind == "context_text" and snap.context is None:
                    continue
                docs, _ = self._extract_documents(snap, kind, work)

                counts[kind] = self.search_adapter.replace_projection(
                    kind,
                    token_str,
                    docs,
                    repository_uuidv4=snap.token.repository_uuidv4,
                    catalog_instance_uuidv4=snap.token.catalog_instance_uuidv4,
                )
            return counts

    def search(self, query: SearchQuery, *, work=None) -> SearchResponse:
        guarded = _QueryWorkBoundary(
            work if work is not None else UnlimitedWorkBudget()
        )
        try:
            return self._search(query, guarded)
        except _QueryWorkError as error:
            raise error.original from None

    def _search(self, query: SearchQuery, work) -> SearchResponse:
        """Execute a verified search across the pinned snapshot with automatic fallback."""
        with self.open_snapshot() as snap:
            token_str = snap.token.encode()
            if query.expected_token is not None and query.expected_token != token_str:
                raise QueryError(
                    "SNAPSHOT_MISMATCH",
                    "search",
                    "expected_token does not match current pinned snapshot",
                )

            all_hits: list[SearchHit] = []
            backends_by_kind: dict[str, str] = {}

            for kind in query.projection_kinds:
                if kind in ("git_metadata", "notes") and snap.core is None:
                    continue
                if kind == "context_text" and snap.context is None:
                    continue

                authority_started = time.perf_counter_ns()
                auth_docs, auth_summaries = self._extract_documents(snap, kind, work)

                expected_matches = {
                    doc_key: text
                    for doc_key, text in auth_docs.items()
                    if query.query_text in text
                }

                self.last_costs_ns["authority_search_validation:" + kind] = (
                    time.perf_counter_ns() - authority_started
                )
                projection_started = time.perf_counter_ns()
                candidates = self.search_adapter.query_candidates(
                    kind,
                    token_str,
                    query.query_text,
                    expected_doc_count=len(auth_docs),
                )
                self.last_costs_ns["projection_scan:" + kind] = (
                    time.perf_counter_ns() - projection_started
                )
                if candidates is not None and candidates == expected_matches:
                    backends_by_kind[kind] = "verified_projection_scan"
                    verified_matches = candidates
                else:
                    backends_by_kind[kind] = "authority_scan"
                    verified_matches = expected_matches

                for doc_key_json, matched_text in verified_matches.items():
                    all_hits.append(
                        SearchHit(
                            projection_kind=kind,
                            document_key=tuple(json.loads(doc_key_json)),
                            matched_text=matched_text,
                            authoritative_summary=auth_summaries[doc_key_json],
                            snapshot_token=token_str,
                        )
                    )

            overall_backend = (
                "verified_projection_scan"
                if backends_by_kind
                and all(
                    b == "verified_projection_scan" for b in backends_by_kind.values()
                )
                else "authority_scan"
            )

            page_result = _paginate_items(
                all_hits,
                cursor_validator=validate_cursor_key,
                key_fn=lambda h: h.semantic_key,
                page=PageRequest(
                    limit=query.limit,
                    cursor=query.cursor,
                    expected_token=query.expected_token,
                ),
                endpoint_kind="search",
                filters={
                    "projection_kinds": list(query.projection_kinds),
                    "query_text": query.query_text,
                    "mapping_evidence": self._mapping_filter(),
                },
                snapshot_token=token_str,
            )

            return SearchResponse(
                hits=page_result.items,
                backend=overall_backend,
                backends_by_kind=backends_by_kind,
                snapshot_token=token_str,
                next_cursor=page_result.next_cursor,
                has_more=page_result.has_more,
                total_count=page_result.total_count,
            )
