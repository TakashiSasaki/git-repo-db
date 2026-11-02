"""Authoritative Context reads without concrete Core or paired code."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, replace

from repo_catalog.adapters.sqlite.catalog_runtime import catalog_completion
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.query_pagination import (
    _paginate_items,
    validate_page_request,
)
from repo_catalog.application.query_runtime import QueryReader, _stored_view
from repo_catalog.domain.context_query import (
    ContextResourceView,
    ProviderView,
    SourceView,
    validate_cursor_key,
)
from repo_catalog.domain.p1_context import CoverageScope, ResourceKey
from repo_catalog.domain.production_context import ResourceRelation
from repo_catalog.domain.query_contracts import (
    ByteReadResult,
    CoverageView,
    PageRequest,
    PageResult,
    QueryError,
    SnapshotFenceToken,
)
from repo_catalog.domain.shared_values import CoreFailure, uuid4_value


@dataclass
class PinnedContextSnapshot:
    mode: str
    token: SnapshotFenceToken
    context: Context
    core: object = None


class ContextReader:
    def list_providers(self) -> tuple[ProviderView, ...]:
        with self.open_snapshot(required_store="context") as snap:
            return self._providers_in_snapshot(snap.context)

    @_stored_view
    def _providers_in_snapshot(self, context: Context) -> tuple[ProviderView, ...]:
        rows = context.db.execute(
            "SELECT service_instance_uuidv4,provider_kind,configuration_json "
            "FROM providers ORDER BY service_instance_uuidv4"
        ).fetchall()
        views = []
        for service, kind, configuration in rows:
            uuid4_value(service)
            if type(kind) is not str or not kind:
                raise ValueError("stored Provider kind must be a nonempty string")
            views.append(
                ProviderView(
                    service,
                    kind,
                    context.registration_metadata("provider", configuration),
                )
            )
        return tuple(views)

    def list_source_views(
        self, service_instance_uuidv4: str | None = None
    ) -> tuple[SourceView, ...]:
        if service_instance_uuidv4 is not None:
            try:
                if type(service_instance_uuidv4) is not str:
                    raise ValueError("canonical UUIDv4 string required")
                uuid4_value(service_instance_uuidv4)
            except (ValueError, TypeError, AttributeError) as error:
                raise QueryError(
                    "INVALID_INPUT", "context-sources", str(error)
                ) from error
        with self.open_snapshot(required_store="context") as snap:
            return self._sources_in_snapshot(snap.context, service_instance_uuidv4)

    @_stored_view
    def _sources_in_snapshot(
        self, context: Context, service: str | None
    ) -> tuple[SourceView, ...]:
        from repo_catalog.domain.production_context import SourceInventory

        rows = context.db.execute(
            "SELECT source_registration_uuidv4,service_instance_uuidv4,configuration_json "
            "FROM sources WHERE (? IS NULL OR service_instance_uuidv4=?) "
            "ORDER BY source_registration_uuidv4",
            (service, service),
        ).fetchall()
        views = []
        for source, provider, configuration in rows:
            uuid4_value(source)
            uuid4_value(provider)
            repositories = context.source_repositories(source)
            for repository in repositories:
                uuid4_value(repository)
            inventories = []
            for (
                scope,
                observed,
                state,
                terminal,
                members_json,
                provenance,
            ) in context.db.execute(
                "SELECT scope_json,observed_at_us,coverage_state,terminal,members_json,provenance_json "
                "FROM source_inventory_evidence WHERE source_registration_uuidv4=? "
                "ORDER BY observed_at_us,scope_json,provenance_json",
                (source,),
            ).fetchall():
                members = json.loads(members_json)
                if (
                    type(members) is not list
                    or type(terminal) is not int
                    or terminal not in (0, 1)
                ):
                    raise ValueError("invalid stored Source inventory shape")
                for member in members:
                    uuid4_value(member)
                inventories.append(
                    SourceInventory(
                        source,
                        scope,
                        observed,
                        state,
                        bool(terminal),
                        tuple(members),
                        provenance,
                    )
                )
            views.append(
                SourceView(
                    source,
                    provider,
                    context.registration_metadata("source", configuration),
                    repositories,
                    tuple(inventories),
                )
            )
        return tuple(views)

    def get_context_coverage(self, scope: CoverageScope) -> CoverageView:
        # Rebuild typed caller values before any Context stored-row classifier.
        try:
            if (
                type(scope) is not CoverageScope
                or type(scope.owner_kind) is not str
                or type(scope.coordinates) is not tuple
            ):
                raise ValueError("CoverageScope with tuple coordinates required")
            scope = CoverageScope(scope.owner_kind, scope.coordinates)
        except (ValueError, TypeError, AttributeError, RecursionError) as error:
            raise QueryError("INVALID_INPUT", "context-coverage", str(error)) from error
        with self.open_snapshot(required_store="context") as snap:
            return self._coverage_in_snapshot(snap.context, scope)

    @_stored_view
    def _coverage_in_snapshot(
        self, context: Context, scope: CoverageScope
    ) -> CoverageView:
        projection = context.coverage(scope)
        return CoverageView(
            scope,
            projection.state,
            projection.known_empty,
            projection.observed_at_us,
            projection.claims,
        )

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
        # Canonicalize caller values before opening the stored-data boundary.
        if type(page) is not PageRequest:
            raise QueryError(
                "INVALID_INPUT", "context-resources", "PageRequest required"
            )
        try:
            for value in (service_instance_uuidv4, repository_uuidv4):
                if value is not None:
                    if type(value) is not str:
                        raise ValueError("canonical UUIDv4 string required")
                    uuid4_value(value)
            if resource_kind is not None and (
                type(resource_kind) is not str or not resource_kind
            ):
                raise ValueError("resource_kind must be a nonempty string")

            def checked_key(value):
                if value is None:
                    return None
                if type(value) is not ResourceKey:
                    raise ValueError("ResourceKey required")
                return ResourceKey(
                    value.service_instance_uuidv4,
                    value.resource_kind,
                    value.provider_resource_id,
                )

            identifier_namespace = checked_key(identifier_namespace)
            parent = checked_key(parent)
        except (
            CoreFailure,
            ValueError,
            TypeError,
            AttributeError,
            RecursionError,
        ) as error:
            raise QueryError(
                "INVALID_INPUT", "context-resources", str(error)
            ) from error
        if parent is not None:
            raise QueryError(
                "I2_PARENT_QUERY_UNSUPPORTED",
                "parent",
                "semantic Parent queries require I3",
            )
        filters = {
            "identifier_namespace": list(identifier_namespace.coordinates())
            if identifier_namespace
            else None,
            "mapping_evidence": self._mapping_filter(),
            "repository_uuidv4": repository_uuidv4,
            "resource_kind": resource_kind,
            "service_instance_uuidv4": service_instance_uuidv4,
        }
        page = validate_page_request(
            page,
            endpoint_kind="context_resources",
            filters=filters,
            cursor_validator=validate_cursor_key,
        )
        with self.open_snapshot(required_store="context") as snap:
            assert snap.context is not None
            token_str = snap.token.encode()
            validate_core = self._context_core_resolver(snap)

            def views():
                for key in snap.context.resources(kind=resource_kind):
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
                filters=filters,
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

    def get_context_resource(
        self,
        resource_key: ResourceKey,
        *,
        include_text: bool = True,
    ) -> ContextResourceView:
        # Caller values must be checked outside stored-data classifiers. Rebuild
        # the canonical value so instance overrides cannot become stored faults.
        if type(resource_key) is not ResourceKey or type(include_text) is not bool:
            raise QueryError(
                "INVALID_INPUT", "context-resource", "ResourceKey and bool required"
            )
        try:
            resource_key = ResourceKey(
                resource_key.service_instance_uuidv4,
                resource_key.resource_kind,
                resource_key.provider_resource_id,
            )
        except (
            CoreFailure,
            ValueError,
            TypeError,
            AttributeError,
            RecursionError,
        ) as error:
            raise QueryError("INVALID_INPUT", "context-resource", str(error)) from error
        with self.open_snapshot(required_store="context") as snap:
            assert snap.context is not None
            return self._context_resource_in_snapshot(
                snap.context,
                resource_key,
                include_text=include_text,
                validate_core=self._context_core_resolver(snap),
            )

    def _context_core_resolver(self, snapshot):
        """No Core facts can be resolved by the standalone Context reader."""
        return None

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

    def read_context_text(self, text_sha256: str) -> ByteReadResult:
        if (
            type(text_sha256) is not str
            or len(text_sha256) != 64
            or any(c not in "0123456789abcdef" for c in text_sha256)
        ):
            raise QueryError(
                "INVALID_INPUT", "context-text", "lowercase SHA256 required"
            )
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


class ContextQueryService(ContextReader, QueryReader):
    """Pilot: Context Resource/text reads only; paired/Core/Search APIs are absent."""

    def __init__(self, *args, mapping_evidence=None, **kwargs):
        if mapping_evidence is not None:
            from repo_catalog.domain.p1_context import MappingOperationEvidence

            if not isinstance(mapping_evidence, MappingOperationEvidence):
                raise ValueError("MappingOperationEvidence required")
        self.mapping_evidence = mapping_evidence
        super().__init__(*args, **kwargs)

    def detect_mode(self):
        self._check_stop()
        if self._requested_mode in ("paired", "core_only") or (
            self._requested_mode == "auto"
            and (self.directory / "core.sqlite3").is_file()
        ):
            raise QueryError(
                "MISSING_CAPABILITY",
                "query",
                "Core/paired Query capability is not installed; select context_only explicitly",
            )
        if not (self.directory / "context.sqlite3").is_file():
            raise QueryError(
                "STORE_UNAVAILABLE", "context_only", "context.sqlite3 is required"
            )
        return "context_only"

    @contextmanager
    def _open_snapshot(self, *, required_store="any"):
        self.detect_mode()
        if required_store not in ("any", "context"):
            raise QueryError(
                "MISSING_CAPABILITY", required_store, "Context reader capability only"
            )
        with Context.snapshot(self.directory, read_limits=self.read_limits) as context:
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
            yield PinnedContextSnapshot(
                mode="context_only",
                token=token,
                context=context,
            )
            with catalog_completion(self.directory):
                self._check_stop()
