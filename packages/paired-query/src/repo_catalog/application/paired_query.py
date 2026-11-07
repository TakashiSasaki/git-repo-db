"""Core + Context Query integration, without Search/acquisition/Exchange."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from repo_catalog.adapters.sqlite.catalog_runtime import (
    SnapshotReadLimits,
    catalog_completion,
)
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.paired_coordination import (
    PairedSnapshot,
    PairSnapshotCoordinator,
)
from repo_catalog.application.context_query import ContextQueryService, ContextReader
from repo_catalog.application.core_query import CoreQueryService, PinnedCoreSnapshot
from repo_catalog.application.query_pagination import (
    _paginate_items,
    validate_page_request,
)
from repo_catalog.domain.core_query import GitObjectView
from repo_catalog.domain.paired_query import (
    PairedCoreResolution,
    PairedResourceView,
    validate_cursor_key,
)
from repo_catalog.domain.query_contracts import (
    CatalogReadMode,
    PageRequest,
    PageResult,
    QueryError,
    SnapshotFenceToken,
)
from repo_catalog.domain.query_work import UnlimitedWorkBudget
from repo_catalog.domain.shared_values import uuid4_value

if TYPE_CHECKING:
    from repo_catalog.adapters.sqlite.production_context import Context
    from repo_catalog.domain.p1_context import MappingOperationEvidence, ResourceKey


@dataclass
class PinnedCatalogSnapshot(PinnedCoreSnapshot):
    """An open, consistent read-only snapshot across the active catalog topology."""

    context: Context | None = None
    pair: PairedSnapshot | None = None


class PairedQueryService(ContextReader, CoreQueryService):
    """Explicit paired and single-authority Query composition."""

    def _context_core_resolver(self, snapshot):
        """Core schema access belongs to explicit paired composition."""
        if snapshot.core is None:
            return None

        def resolve(object_format, object_oid):
            return bool(
                snapshot.core.sql(
                    "SELECT 1 FROM git_objects WHERE object_format=? AND object_oid=?",
                    (object_format, object_oid),
                )
            )

        return resolve

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

            coordinator = PairSnapshotCoordinator(
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
            with ContextQueryService._open_snapshot(
                self, required_store=required_store
            ) as snapshot:
                yield PinnedCatalogSnapshot(
                    mode=snapshot.mode, token=snapshot.token, context=snapshot.context
                )

    def get_paired_resource(
        self,
        resource_key: ResourceKey,
        *,
        include_text: bool = True,
        include_core_bytes: bool = False,
    ) -> PairedResourceView:
        if type(include_text) is not bool or type(include_core_bytes) is not bool:
            raise QueryError(
                "INVALID_INPUT", "paired-resource", "bool options required"
            )
        resource_key = self._checked_resource_key(resource_key, "paired-resource")
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
        try:
            if resource_kind is not None and (
                type(resource_kind) is not str or not resource_kind
            ):
                raise ValueError("resource_kind must be a nonempty string")
            if repository_uuidv4 is not None:
                if type(repository_uuidv4) is not str:
                    raise ValueError("canonical UUIDv4 string required")
                uuid4_value(repository_uuidv4)
        except (ValueError, TypeError, AttributeError) as error:
            raise QueryError("INVALID_INPUT", "paired-resources", str(error)) from error
        filters = {
            "mapping_evidence": self._mapping_filter(),
            "repository_uuidv4": repository_uuidv4,
            "resource_kind": resource_kind,
        }
        page = validate_page_request(
            page,
            endpoint_kind="paired_resources",
            filters=filters,
            cursor_validator=validate_cursor_key,
        )
        with self.open_snapshot(required_store="paired") as snap:
            assert snap.core is not None and snap.context is not None
            token_str = snap.token.encode()

            ref_work = UnlimitedWorkBudget()

            def views():
                for key in snap.context.resources(kind=resource_kind):
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
                filters=filters,
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
