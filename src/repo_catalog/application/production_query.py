"""Production authoritative query, pagination, snapshot fencing, and Search service (P6).

Supports three explicit catalog topologies without requiring unused stores on disk:
- `core_only`: `core.sqlite3` without `context.sqlite3`
- `context_only`: `context.sqlite3` without `core.sqlite3`
- `paired`: `core.sqlite3` + `context.sqlite3` pinned via `PairCoordinator.snapshots()`

Every read checks `p1-recovery-stop.json` before and after execution.
Every byte read (`read_metadata_bytes`, `read_note_bytes`, `read_context_text`)
runs full integrity verification on the stored representation, immediately
persisting `p1-recovery-stop.json` and raising `AUTHORITATIVE_CORRUPTION` if
tampered.
Every Search response validates derivative candidates against the pinned
authoritative snapshot and falls back transparently to `authority_scan` if
`search.sqlite3` is missing, stale, incomplete, or corrupt without stopping the
catalog.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import sqlite3
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeVar

from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_coordination import (
    PairCoordinator,
    PairedSnapshot,
    SnapshotReadLimits,
    catalog_completion,
    persist_catalog_stop,
)
from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.p1_core import (
    OID,
    Capture,
    CoreCoverageScope,
    CoreFailure,
    GitObservation,
    Provenance,
    RepositoryClaim,
    ScalarField,
    encode,
)
from repo_catalog.domain.production_query import (
    SEARCH_PROJECTION_KINDS,
    ByteReadResult,
    CatalogReadMode,
    ContextResourceView,
    CoverageView,
    GitObjectView,
    GitObservationView,
    GitRepositoryView,
    NotesCaptureView,
    NotesInventoryView,
    NotesTargetView,
    PageRequest,
    PageResult,
    PaginationCursor,
    PairedCoreResolution,
    PairedResourceView,
    ProviderView,
    QueryError,
    RefNotesTargetView,
    SearchHit,
    SearchQuery,
    SearchResponse,
    SnapshotFenceToken,
    SourceView,
    filter_digest,
)
from repo_catalog.domain.ref_observation import RefObservationKey

if TYPE_CHECKING:
    from repo_catalog.adapters.sqlite.production_context import Context
    from repo_catalog.domain.p1_context import (
        CoverageScope,
        MappingOperationEvidence,
        ResourceKey,
    )
    from repo_catalog.domain.ports.p1_core import WorkBudget
    from repo_catalog.domain.production_context import (
        ResourceRelation,
    )
    from repo_catalog.domain.ref_observation import (
        NotesMapping,
        NotesMappingProjection,
        RefEnumerationResult,
        RefNotesInventoryProjection,
        RefObservationClaim,
        RefObservationKey,
        RefObservationProjection,
    )

T = TypeVar("T")

ALL_SCALAR_FIELDS: tuple[ScalarField, ...] = (
    "type",
    "size",
    "message",
    "author",
    "committer",
    "encoding",
    "supplied_digest",
    "parent_count",
    "tree_count",
    "raw_name_hex",
    "decoded_name",
    "decoder_settings",
    "author_name",
    "author_email",
    "author_time_us",
    "committer_name",
    "committer_email",
    "committer_time_us",
    "tag_name",
    "tagger",
    "header_data",
)

ALL_RELATIONS: tuple[str, ...] = (
    "commit_tree",
    "commit_parents",
    "tree_entries",
    "tag_target",
)


@dataclass
class PinnedCatalogSnapshot:
    """An open, consistent read-only snapshot across the active catalog topology."""

    mode: CatalogReadMode
    token: SnapshotFenceToken
    core: GitCore | None = None
    context: Context | None = None
    pair: PairedSnapshot | None = None


def _paginate_items(
    items: Iterable[T],
    *,
    key_fn: Callable[[T], tuple],
    page: PageRequest,
    endpoint_kind: str,
    filters: dict[str, object],
    snapshot_token: str,
) -> PageResult[T]:
    if page.expected_token is not None and page.expected_token != snapshot_token:
        raise QueryError(
            "SNAPSHOT_MISMATCH",
            endpoint_kind,
            "expected_token does not match current pinned snapshot",
        )
    f_digest = filter_digest(endpoint_kind, filters)
    last_key = None
    if page.cursor is not None:
        last_key = PaginationCursor.decode(
            page.cursor,
            expected_endpoint=endpoint_kind,
            expected_filter_digest=f_digest,
            current_snapshot_token=snapshot_token,
        ).last_key
    total_count = 0
    remaining_count = 0

    def eligible():
        nonlocal total_count, remaining_count
        for item in items:
            total_count += 1
            if last_key is None or key_fn(item) > last_key:
                remaining_count += 1
                yield item

    # Exact total_count still requires a bounded scan; keep only limit+1 views.
    selected = heapq.nsmallest(page.limit + 1, eligible(), key=key_fn)
    sliced = tuple(selected[: page.limit])
    has_more = remaining_count > len(sliced)
    next_cursor = None
    if has_more and sliced:
        next_cursor = PaginationCursor(
            endpoint_kind=endpoint_kind,
            filter_digest=f_digest,
            snapshot_token=snapshot_token,
            last_key=key_fn(sliced[-1]),
        ).encode()

    return PageResult(
        items=sliced,
        snapshot_token=snapshot_token,
        next_cursor=next_cursor,
        has_more=has_more,
        total_count=total_count,
    )


def _stored_view(method):
    """Fence complete fixed stored-row reconstruction, including argument unpacking."""

    @wraps(method)
    def call(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except QueryError:
            raise
        except (ValueError, TypeError, AttributeError, KeyError, IndexError) as error:
            if getattr(error, "code", None) in {
                "CAPABILITY_EXPIRED",
                "RECOVERY_STOP",
                "RECOVERY_REQUIRED",
                "RESOURCE_NOT_FOUND",
                "OBJECT_NOT_FOUND",
                "TEXT_UNAVAILABLE",
            }:
                raise
            persist_catalog_stop(
                self.directory, "invalid stored projection: " + str(error)
            )
            raise CoreFailure(
                "AUTHORITATIVE_CORRUPTION", method.__name__, str(error)
            ) from error

    return call


class _QueryWorkError(Exception):
    def __init__(self, original):
        super().__init__()
        self.original = original


class _QueryWorkLimits:
    def __init__(self, work):
        self.work = work

    @property
    def note_bytes(self):
        return self.work._invoke(lambda: self.work.inner.limits.note_bytes)


class _QueryWorkBoundary:
    """Carry callback exceptions beyond snapshot corruption classifiers."""

    def __init__(self, inner):
        self.inner = inner
        self.limits = _QueryWorkLimits(self)

    def _invoke(self, callback):
        try:
            return callback()
        except Exception as error:
            raise _QueryWorkError(error) from error

    def require(self, unit, amount=1):
        return self._invoke(lambda: self.inner.require(unit, amount))

    def charge(self, unit, amount):
        return self._invoke(lambda: self.inner.charge(unit, amount))

    def __getattr__(self, name):
        if name != "abandon":
            raise AttributeError(name)
        method = self._invoke(lambda: getattr(self.inner, name, None))
        if method is None:
            raise AttributeError(name)
        return lambda unit: self._invoke(lambda: method(unit))


class ProductionQueryService:
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
        self.directory = Path(directory)
        if not isinstance(read_limits, SnapshotReadLimits):
            raise QueryError(
                "INVALID_LIMIT", "query", "finite SnapshotReadLimits required"
            )
        self.read_limits = read_limits
        self.last_costs_ns: dict[str, int] = {}
        if mode not in ("auto", "core_only", "context_only", "paired"):
            raise QueryError("INVALID_MODE", "query", str(mode))
        self._requested_mode = mode
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

    def _check_stop(self) -> None:
        if (self.directory / "p1-recovery-stop.json").exists():
            raise CoreFailure(
                "RECOVERY_STOP", "catalog", "normal catalog operation stopped"
            )

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
    def open_snapshot(self, *, required_store="any"):
        started = time.perf_counter_ns()
        self.last_costs_ns = {}
        try:
            with self._open_snapshot(required_store=required_store) as snapshot:
                self.last_costs_ns["snapshot_total"] = time.perf_counter_ns() - started
                yield snapshot
        except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as error:
            persist_catalog_stop(
                self.directory, "stored typed data decoding: " + str(error)
            )
            raise CoreFailure(
                "AUTHORITATIVE_CORRUPTION", "query", str(error)
            ) from error
        except sqlite3.OperationalError as error:
            if str(error).startswith("Could not decode to UTF-8 column"):
                persist_catalog_stop(self.directory, str(error))
                raise CoreFailure(
                    "AUTHORITATIVE_CORRUPTION", "query", str(error)
                ) from error
            if getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT:
                raise QueryError(
                    "QUERY_BUDGET", "snapshot", "SQLite VM step limit"
                ) from error
            raise
        except CoordinationError as error:
            if error.code == "QUERY_BUDGET":
                raise QueryError("QUERY_BUDGET", "snapshot", str(error)) from error
            raise

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
            coordinator = PairCoordinator(
                self.directory, read_limits=self.read_limits, metadata_only=True
            )
            with coordinator.core_snapshot() as core_read:
                identity_started = time.perf_counter_ns()
                repo_id, inst_id = core_read.identity("core")
                self.last_costs_ns["authority_identity_validation"] = (
                    time.perf_counter_ns() - identity_started
                )
                token_started = time.perf_counter_ns()
                core_hash = core_read.fingerprint(metadata_only=True)
                self.last_costs_ns["snapshot_token_generation"] = (
                    time.perf_counter_ns() - token_started
                )
                token = SnapshotFenceToken(
                    mode="core_only",
                    repository_uuidv4=repo_id,
                    catalog_instance_uuidv4=inst_id,
                    core_sha256=core_hash,
                    context_sha256=None,
                )
                with GitCore.for_snapshot(core_read, self.directory) as core:
                    yield PinnedCatalogSnapshot(
                        mode="core_only",
                        token=token,
                        core=core,
                    )
                with catalog_completion(self.directory):
                    self._check_stop()
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

    def _stored(self, constructor, *args, **kwargs):
        """Domain reconstruction concerns persisted rows, never caller input."""
        try:
            return constructor(*args, **kwargs)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
            persist_catalog_stop(
                self.directory,
                "invalid stored " + constructor.__name__ + ": " + str(error),
            )
            raise CoreFailure(
                "AUTHORITATIVE_CORRUPTION", constructor.__name__, str(error)
            ) from error

    def snapshot_token(self) -> SnapshotFenceToken:
        with self.open_snapshot() as snap:
            return snap.token

    # ------------------------------------------------------------------
    # Git Core Authoritative Queries
    # ------------------------------------------------------------------

    def get_ref_observation(
        self,
        key: RefObservationKey,
        work: WorkBudget,
        *,
        max_claims: int = 10_000,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> RefObservationProjection:
        """Return the immutable subject, its original claims and derived conflict."""
        with self.open_snapshot(required_store="core") as snap:
            assert snap.core is not None
            return snap.core.ref_observation(
                key, work, max_claims=max_claims, max_bytes=max_bytes
            )

    def get_ref_enumeration(
        self,
        origin_uuidv4: str,
        enumeration_uuidv7: str,
        work: WorkBudget,
        *,
        max_links: int = 200_000,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> RefEnumerationResult | None:
        """Return one original scan and its exact bounded membership."""
        with self.open_snapshot(required_store="core") as snap:
            assert snap.core is not None
            return snap.core.ref_enumeration(
                origin_uuidv4,
                enumeration_uuidv7,
                work,
                max_links=max_links,
                max_bytes=max_bytes,
            )

    def get_notes_mapping(
        self,
        claim: RefObservationClaim,
        target: OID,
        interpretation_kind: str,
        interpretation_version: str,
        interpretation_scope: str,
        work: WorkBudget,
        *,
        max_units: int = 10_000,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> NotesMappingProjection:
        """Keep reports and checked evidence attached to their exact Claim."""
        with self.open_snapshot(required_store="core") as snap:
            assert snap.core is not None
            return snap.core.notes_mapping_projection(
                claim,
                target,
                interpretation_kind,
                interpretation_version,
                interpretation_scope,
                work,
                max_units=max_units,
                max_bytes=max_bytes,
            )

    def list_ref_notes_inventories(
        self,
        claim: RefObservationClaim,
        work: WorkBudget,
        *,
        max_groups: int = 10_000,
        max_members: int = 100_000,
        max_bytes: int = 64 * 1024 * 1024,
        max_proofs: int = 1_000,
        max_structures: int = 100_000,
    ) -> RefNotesInventoryProjection:
        """List original Groups and current exact-Claim receiver checks."""
        try:
            with self.open_snapshot(required_store="core") as snap:
                assert snap.core is not None
                return snap.core.ref_notes_inventory_projection(
                    claim,
                    _QueryWorkBoundary(work),
                    max_groups=max_groups,
                    max_members=max_members,
                    max_bytes=max_bytes,
                    max_proofs=max_proofs,
                    max_structures=max_structures,
                )
        except _QueryWorkError as error:
            raise error.original from None

    def read_ref_note_bytes(
        self,
        claim: RefObservationClaim,
        mapping: NotesMapping,
        work: WorkBudget,
        *,
        max_proof_bytes: int = 64 * 1024 * 1024,
        max_metadata_bytes: int = 64 * 1024 * 1024,
    ) -> ByteReadResult:
        """Return only locally revalidated bytes for this Claim and mapping."""
        with self.open_snapshot(required_store="core") as snap:
            assert snap.core is not None
            try:
                body = snap.core.read_ref_note(
                    claim,
                    mapping,
                    work,
                    max_proof_bytes=max_proof_bytes,
                    max_metadata_bytes=max_metadata_bytes,
                )
            except CoreFailure as error:
                if error.code == "NOTES_ROLE_UNAVAILABLE":
                    return ByteReadResult(available=False, verified=False)
                raise
            # This digest is computed for the returned view, in addition to the
            # typed reader's body verification, so the actual hash is charged.
            work.require("verification_bytes", len(body))
            try:
                digest = hashlib.sha256(body).hexdigest()
            except BaseException:
                abandon = getattr(work, "abandon", None)
                if abandon is not None:
                    abandon("verification_bytes")
                else:
                    work.charge("verification_bytes", len(body))
                raise
            work.charge("verification_bytes", len(body))
            return ByteReadResult(
                available=True,
                verified=True,
                body_bytes=body,
                declared_size=len(body),
                digest_sha256=digest,
            )

    def get_repository_view(self) -> GitRepositoryView:
        with self.open_snapshot(required_store="core") as snap:
            assert snap.core is not None
            return self._repository_view_in_snapshot(snap.core)

    @_stored_view
    def _repository_view_in_snapshot(self, core: GitCore) -> GitRepositoryView:
        repo_id, inst_id = core.catalog_identity()
        rows = core.sql(
            "SELECT repository_uuidv4,field,value,provenance FROM repository_claims "
            "WHERE repository_uuidv4=? ORDER BY field,value,provenance",
            (repo_id,),
        )
        claims_by_field: dict[str, list[RepositoryClaim]] = {}
        for row in rows:
            prov = self._stored(Provenance, *json.loads(row[3]))
            claim = self._stored(
                RepositoryClaim, row[0], row[1], json.loads(row[2]), prov
            )
            claims_by_field.setdefault(row[1], []).append(claim)
        return GitRepositoryView(
            repository_uuidv4=repo_id,
            catalog_instance_uuidv4=inst_id,
            claims={k: tuple(v) for k, v in claims_by_field.items()},
        )

    def list_ref_observations(self, page: PageRequest = PageRequest(), *, work=None):
        """Page original subjects with every Claim, including rootless results."""
        work = work if work is not None else UnlimitedWorkBudget()
        guarded = _QueryWorkBoundary(work)
        try:
            with self.open_snapshot(required_store="core") as snap:
                core = snap.core
                assert core is not None
                rows = core.sql(
                    "SELECT observation_origin_uuidv4,ref_observation_uuidv7 FROM ref_observations ORDER BY observation_origin_uuidv4,ref_observation_uuidv7 LIMIT 10001"
                )
                if len(rows) > 10000:
                    raise QueryError(
                        "QUERY_BUDGET",
                        "ref-observations",
                        "finite observation scope exceeded",
                    )
                return _paginate_items(
                    (
                        core.ref_observation(
                            self._stored(RefObservationKey, *row), guarded
                        )
                        for row in rows
                    ),
                    key_fn=lambda v: v.ref_observation.ref_observation_key.key,
                    page=page,
                    endpoint_kind="ref_observations",
                    filters={},
                    snapshot_token=snap.token.encode(),
                )
        except _QueryWorkError as error:
            raise error.original from None

    def _ref_notes_targets_in_snapshot(self, core, oid, work=None):
        work = work if work is not None else UnlimitedWorkBudget()
        # Group-only reports do not create standalone Mapping rows. Discover
        # bounded headers first, then let the checked exact-Claim reader validate
        # memberships before deciding whether this target is actually related.
        candidates = (
            "WITH candidates AS ("
            "SELECT c.observation_origin_uuidv4,c.ref_observation_uuidv7,m.interpretation_kind,m.interpretation_version,m.interpretation_scope "
            "FROM ref_observation_claims c JOIN notes_mappings m ON m.object_format=c.root_format AND m.root_oid=c.root_oid "
            "WHERE m.object_format=? AND m.annotated_object_oid=? "
            "UNION SELECT observation_origin_uuidv4,ref_observation_uuidv7,interpretation_kind,interpretation_version,interpretation_scope "
            "FROM notes_mapping_groups WHERE object_format=? "
            "ORDER BY 1,2,3,4,5 LIMIT 10001) "
        )
        parameters = (*oid.key, oid.object_format)
        count, size = core.sql(
            candidates
            + "SELECT count(*),coalesce(sum(octet_length(observation_origin_uuidv4)+octet_length(ref_observation_uuidv7)+octet_length(interpretation_kind)+octet_length(interpretation_version)+octet_length(interpretation_scope)),0) FROM candidates",
            parameters,
        )[0]
        if count > 10000 or size > 64 * 1024 * 1024:
            raise QueryError(
                "QUERY_BUDGET", "ref-notes-targets", "finite association scope exceeded"
            )
        work.require("metadata_units", count)
        work.charge("metadata_units", count)
        work.require("input_bytes", size)
        work.charge("input_bytes", size)
        rows = core.sql(
            candidates + "SELECT * FROM candidates ORDER BY 1,2,3,4,5", parameters
        )
        views = []
        for row in rows:
            observation = core.ref_observation(
                self._stored(RefObservationKey, row[0], row[1]), work
            )
            for claim in observation.claims:
                if (
                    claim.root_oid is None
                    or claim.root_oid.object_format != oid.object_format
                ):
                    continue
                projection = core.notes_mapping_projection(claim, oid, *row[2:], work)
                if (
                    projection.claims
                    or projection.evidence
                    or any(
                        target == oid.full_oid
                        for group in projection.groups
                        for target, _, _ in group.members
                    )
                ):
                    views.append(RefNotesTargetView(observation, projection))
        return tuple(views)

    def get_git_object(
        self,
        oid: OID,
        *,
        include_bytes: bool = False,
        note_captures: Sequence[Capture] = (),
    ) -> GitObjectView:
        with self.open_snapshot(required_store="core") as snap:
            assert snap.core is not None
            return self._git_object_in_snapshot(
                snap.core,
                oid,
                include_bytes=include_bytes,
                note_captures=note_captures,
            )

    def _git_object_in_snapshot(
        self,
        core: GitCore,
        oid: OID,
        *,
        include_bytes: bool = False,
        note_captures: Sequence[Capture] = (),
        ref_work=None,
    ) -> GitObjectView:
        exists = core.sql(
            "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
            oid.key,
        )
        if not exists:
            raise QueryError("OBJECT_NOT_FOUND", oid, f"Git object {oid} not in Core")

        field_rows = core.sql(
            "SELECT DISTINCT field FROM scalar_claims WHERE object_format=? AND full_oid=? ORDER BY field",
            oid.key,
        )
        present_fields = {row[0] for row in field_rows} | {"type", "size"}
        scalars = {
            field: core.scalar(oid, field)
            for field in ALL_SCALAR_FIELDS
            if field in present_fields
        }

        rel_rows = core.sql(
            "SELECT DISTINCT relation FROM relation_groups WHERE object_format=? AND full_oid=? ORDER BY relation",
            oid.key,
        )
        present_rels = {row[0] for row in rel_rows}
        relations = {
            rel: core.relations(oid, rel)
            for rel in ALL_RELATIONS
            if rel in present_rels
        }

        retained_row = core.sql(
            "SELECT size,digest_sha256 FROM retained_metadata WHERE object_format=? AND full_oid=? ORDER BY physical_copy_uuidv4 LIMIT 1",
            oid.key,
        )
        metadata_retained = bool(retained_row)
        retained_bytes: ByteReadResult | None = None
        if include_bytes:
            retained_bytes = self._read_metadata_bytes_in_snapshot(core, oid)

        captures_to_check = list(note_captures)
        if not captures_to_check:
            all_captures = self._all_captures_in_snapshot(core)
            captures_to_check = [
                c for c in all_captures if c.root.object_format == oid.object_format
            ]

        notes_views: list[NotesTargetView] = []
        for cap in captures_to_check:
            if cap.root.object_format != oid.object_format:
                continue
            target_view = self._notes_target_in_snapshot(
                core, cap, oid, include_bytes=include_bytes
            )
            if (
                target_view.canonical is not None
                or target_view.alternatives
                or target_view.reported_conflict
            ):
                notes_views.append(target_view)

        return GitObjectView(
            oid=oid,
            scalars=scalars,
            relations=relations,
            metadata_retained=metadata_retained,
            retained_bytes=retained_bytes,
            notes_targets=tuple(notes_views),
            ref_notes_targets=self._ref_notes_targets_in_snapshot(core, oid, ref_work),
        )

    def list_git_objects(
        self,
        page: PageRequest = PageRequest(),
        *,
        object_format: str | None = None,
        native_type: str | None = None,
    ) -> PageResult[GitObjectView]:
        with self.open_snapshot(required_store="core") as snap:
            assert snap.core is not None
            token_str = snap.token.encode()
            rows = snap.core.sql(
                "SELECT object_format,full_oid FROM git_objects "
                "WHERE (? IS NULL OR object_format=?) "
                "ORDER BY object_format,full_oid",
                (object_format, object_format),
            )

            ref_work = UnlimitedWorkBudget()

            def views():
                for row in rows:
                    oid = self._stored(OID, row[0], row[1])
                    view = self._git_object_in_snapshot(
                        snap.core, oid, ref_work=ref_work
                    )
                    if native_type is not None and view.native_type != native_type:
                        continue
                    yield view

            return _paginate_items(
                views(),
                key_fn=lambda v: v.oid.key,
                page=page,
                endpoint_kind="git_objects",
                filters={
                    "native_type": native_type,
                    "object_format": object_format,
                },
                snapshot_token=token_str,
            )

    def list_git_observations(
        self,
        page: PageRequest = PageRequest(),
        *,
        observation_kind: str | None = None,
        ref_prefix: str | None = None,
    ) -> PageResult[GitObservationView]:
        with self.open_snapshot(required_store="core") as snap:
            assert snap.core is not None
            token_str = snap.token.encode()
            rows = snap.core.sql(
                "SELECT capture_origin_uuidv4,capture_uuidv4,repository_uuidv4,kind,scope,value,provenance "
                "FROM git_observations "
                "WHERE (? IS NULL OR kind=?) "
                "ORDER BY kind,scope,capture_origin_uuidv4,capture_uuidv4,provenance",
                (observation_kind, observation_kind),
            )

            def views():
                for row in rows:
                    view = self._observation_from_row(row)
                    if ref_prefix is not None:
                        ref_val = view.observation.value.get("ref")
                        if not isinstance(ref_val, str) or not ref_val.startswith(
                            ref_prefix
                        ):
                            continue
                    yield view

            return _paginate_items(
                views(),
                key_fn=lambda v: (
                    v.observation.kind,
                    encode(v.observation.scope),
                    v.observation.capture_origin_uuidv4,
                    v.observation.capture_uuidv4,
                    v.observation.provenance.encoded,
                ),
                page=page,
                endpoint_kind="git_observations",
                filters={
                    "observation_kind": observation_kind,
                    "ref_prefix": ref_prefix,
                },
                snapshot_token=token_str,
            )

    @_stored_view
    def _observation_from_row(self, row):
        return GitObservationView(
            GitObservation(
                row[0],
                row[1],
                row[2],
                row[3],
                tuple(json.loads(row[4])),
                json.loads(row[5]),
                Provenance(*json.loads(row[6])),
            )
        )

    @_stored_view
    def _all_captures_in_snapshot(self, core: GitCore) -> tuple[Capture, ...]:
        rows = core.sql(
            "SELECT capture_origin_uuidv4,capture_uuidv4,repository_uuidv4,source,ref,object_format,root "
            "FROM captures ORDER BY ref,capture_origin_uuidv4,capture_uuidv4"
        )
        captures: list[Capture] = []
        for row in rows:
            raw_ref = bytes.fromhex(json.loads(row[4])[1]).decode(
                "utf-8", "surrogateescape"
            )
            captures.append(
                self._stored(
                    Capture,
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    raw_ref,
                    self._stored(OID, row[5], row[6]),
                )
            )
        return tuple(captures)

    def list_notes_captures(
        self,
        page: PageRequest = PageRequest(),
        *,
        notes_ref: str | None = None,
    ) -> PageResult[NotesCaptureView]:
        with self.open_snapshot(required_store="core") as snap:
            assert snap.core is not None
            token_str = snap.token.encode()
            all_captures = self._all_captures_in_snapshot(snap.core)

            def views():
                for cap in all_captures:
                    if notes_ref is not None and cap.ref != notes_ref:
                        continue
                    fmt = cap.root.object_format
                    target_hexes: set[str] = set()
                    for r in snap.core.sql(
                        "SELECT DISTINCT target FROM notes_claims WHERE capture_origin_uuidv4=? AND capture_uuidv4=?",
                        cap.pair,
                    ):
                        target_hexes.add(r[0])
                    for r in snap.core.sql(
                        "SELECT DISTINCT target FROM note_roles WHERE capture_origin_uuidv4=? AND capture_uuidv4=?",
                        cap.pair,
                    ):
                        target_hexes.add(r[0])
                    for r in snap.core.sql(
                        "SELECT membership FROM notes_groups WHERE capture_origin_uuidv4=? AND capture_uuidv4=?",
                        cap.pair,
                    ):
                        for m in json.loads(r[0]):
                            target_hexes.add(m[0])
                    targets = tuple(
                        self._stored(OID, fmt, h) for h in sorted(target_hexes)
                    )
                    inventories = self._notes_inventories_in_snapshot(snap.core, cap)
                    yield NotesCaptureView(
                        capture=cap,
                        targets=targets,
                        inventories=inventories,
                    )

            return _paginate_items(
                views(),
                key_fn=lambda v: v.semantic_key,
                page=page,
                endpoint_kind="notes_captures",
                filters={"notes_ref": notes_ref},
                snapshot_token=token_str,
            )

    def get_notes_target(
        self,
        capture: Capture,
        target: OID,
        *,
        include_bytes: bool = False,
    ) -> NotesTargetView:
        with self.open_snapshot(required_store="core") as snap:
            assert snap.core is not None
            return self._notes_target_in_snapshot(
                snap.core, capture, target, include_bytes=include_bytes
            )

    def _notes_target_in_snapshot(
        self,
        core: GitCore,
        capture: Capture,
        target: OID,
        *,
        include_bytes: bool = False,
    ) -> NotesTargetView:
        proj = core.notes_projection(capture, target)
        role_verified = proj.canonical is not None
        note_retained = False
        note_bytes: ByteReadResult | None = None
        if proj.canonical is not None:
            retained_rows = core.sql(
                "SELECT n.size,n.digest_sha256 FROM retained_notes n JOIN note_roles r "
                "ON r.object_format=n.object_format AND r.note=n.full_oid "
                "WHERE r.capture_origin_uuidv4=? AND r.capture_uuidv4=? "
                "AND r.object_format=? AND r.target=? AND r.note=? "
                "ORDER BY n.physical_copy_uuidv4 LIMIT 1",
                (
                    *capture.pair,
                    target.object_format,
                    target.full_oid,
                    proj.canonical.full_oid,
                ),
            )
            note_retained = bool(retained_rows)
            if include_bytes:
                note_bytes = self._read_note_bytes_in_snapshot(
                    core, capture, target, proj.canonical
                )

        return NotesTargetView(
            capture=capture,
            target=target,
            canonical=proj.canonical,
            alternatives=proj.alternatives,
            reported_conflict=proj.reported_conflict,
            checked_scope=proj.checked_scope,
            role_verified=role_verified,
            note_retained=note_retained,
            note_bytes=note_bytes,
        )

    def list_notes_inventories(
        self, capture: Capture
    ) -> tuple[NotesInventoryView, ...]:
        with self.open_snapshot(required_store="core") as snap:
            assert snap.core is not None
            return self._notes_inventories_in_snapshot(snap.core, capture)

    @_stored_view
    def _notes_inventories_in_snapshot(
        self, core: GitCore, capture: Capture
    ) -> tuple[NotesInventoryView, ...]:
        # Validate receiver-intrinsic inventories via GitCore.notes_inventories
        verified_inventories = core.notes_inventories(capture)
        views: list[NotesInventoryView] = []
        for inv in verified_inventories:
            diag = (
                (inv.failure.code, str(inv.failure))
                if inv.failure is not None
                else None
            )
            prov = self._stored(
                Provenance,
                "receiver-intrinsic",
                encode(capture.key),
                "inventory",
                "git-native-notes-inventory",
                "1",
                "receiver_intrinsic",
            )
            views.append(
                NotesInventoryView(
                    capture=capture,
                    scope="all-notes-mappings",
                    status=inv.status,
                    members=inv.members,
                    provenance=prov,
                    receiver_verified=True,
                    diagnostic=diag,
                )
            )
        # Also include reported notes_groups
        previous = getattr(core, "_checked_byte_read", False)
        core._checked_byte_read = True
        try:
            rows = core.sql(
                "SELECT scope,status,membership,provenance FROM notes_groups "
                "WHERE capture_origin_uuidv4=? AND capture_uuidv4=? AND object_format=? "
                "ORDER BY scope,status,membership,provenance",
                (*capture.pair, capture.root.object_format),
            )
        finally:
            core._checked_byte_read = previous

        for row in rows:
            prov = self._stored(Provenance, *json.loads(row[3]))
            if prov.qualification == "receiver_intrinsic":
                continue
            members = tuple(tuple(m) for m in json.loads(row[2]))
            views.append(
                NotesInventoryView(
                    capture=capture,
                    scope=row[0],
                    status=row[1],
                    members=members,
                    provenance=prov,
                    receiver_verified=False,
                    diagnostic=None,
                )
            )
        return tuple(views)

    def read_metadata_bytes(self, oid: OID) -> ByteReadResult:
        with self.open_snapshot(required_store="core") as snap:
            assert snap.core is not None
            return self._read_metadata_bytes_in_snapshot(snap.core, oid)

    def _read_metadata_bytes_in_snapshot(
        self, core: GitCore, oid: OID
    ) -> ByteReadResult:
        try:
            body = core.read_metadata(oid)
        except CoreFailure as error:
            if error.code == "BYTES_UNAVAILABLE":
                return ByteReadResult(available=False, verified=False)
            raise
        digest = hashlib.sha256(body).hexdigest()
        return ByteReadResult(
            available=True,
            verified=True,
            body_bytes=body,
            text_value=body.decode("utf-8", "surrogateescape"),
            declared_size=len(body),
            digest_sha256=digest,
        )

    def read_note_bytes(
        self, capture: Capture, target: OID, note_oid: OID
    ) -> ByteReadResult:
        with self.open_snapshot(required_store="core") as snap:
            assert snap.core is not None
            return self._read_note_bytes_in_snapshot(
                snap.core, capture, target, note_oid
            )

    def _read_note_bytes_in_snapshot(
        self, core: GitCore, capture: Capture, target: OID, note_oid: OID
    ) -> ByteReadResult:
        try:
            body = core.read_note(capture, target, note_oid)
        except CoreFailure as error:
            if error.code == "NOTES_ROLE_UNAVAILABLE":
                return ByteReadResult(available=False, verified=False)
            raise
        digest = hashlib.sha256(body).hexdigest()
        return ByteReadResult(
            available=True,
            verified=True,
            body_bytes=body,
            text_value=body.decode("utf-8", "surrogateescape"),
            declared_size=len(body),
            digest_sha256=digest,
        )

    def get_core_coverage(
        self,
        scope: CoreCoverageScope,
        *,
        work: WorkBudget | None = None,
        max_proofs: int = 1_000,
        max_bytes: int = 64 * 1024 * 1024,
        max_structures: int = 100_000,
        max_claims: int = 10_000,
    ) -> CoverageView:
        try:
            with self.open_snapshot(required_store="core") as snap:
                assert snap.core is not None
                proj = snap.core.coverage(
                    scope,
                    work=None if work is None else _QueryWorkBoundary(work),
                    max_proofs=max_proofs,
                    max_bytes=max_bytes,
                    max_structures=max_structures,
                    max_claims=max_claims,
                )
                return CoverageView(
                    scope=scope,
                    state=proj.state,
                    known_empty=proj.known_empty,
                    latest_observed_at_us=proj.observed_at_us,
                    claims=proj.claims,
                )
        except _QueryWorkError as error:
            raise error.original from None

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
                            "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
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
                            "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
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

        def check_in_core(fmt: str, full_oid: str) -> bool:
            return bool(
                core.sql(
                    "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
                    (fmt, full_oid),
                )
            )

        ctx_view = self._context_resource_in_snapshot(
            context,
            resource_key,
            include_text=include_text,
            validate_core=check_in_core,
        )
        all_captures = self._all_captures_in_snapshot(core)

        resolutions: list[PairedCoreResolution] = []
        for dep in ctx_view.core_dependencies:
            oid = dep.reference.oid
            obj_view: GitObjectView | None = None
            notes_targets: tuple[NotesTargetView, ...] = ()
            if dep.available:
                obj_view = self._git_object_in_snapshot(
                    core,
                    oid,
                    include_bytes=include_core_bytes,
                    note_captures=all_captures,
                    ref_work=ref_work,
                )
                notes_targets = obj_view.notes_targets
            resolutions.append(
                PairedCoreResolution(
                    reference=dep.reference,
                    available_in_core=dep.available,
                    core_required=dep.required,
                    object_view=obj_view,
                    notes_targets=notes_targets,
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

    @_stored_view
    def _extract_documents(self, snapshot, kind):
        from repo_catalog.adapters.sqlite.production_search import (
            ProductionSearchAdapter,
        )

        if kind == "git_metadata":
            return ProductionSearchAdapter.extract_git_metadata_documents(snapshot.core)
        if kind == "notes":
            return ProductionSearchAdapter.extract_notes_documents(snapshot.core)
        return ProductionSearchAdapter.extract_context_documents(
            snapshot.context, evidence=self.mapping_evidence
        )

    def rebuild_search(
        self,
        projection_kinds: Sequence[str] = SEARCH_PROJECTION_KINDS,
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
                docs, _ = self._extract_documents(snap, kind)

                counts[kind] = self.search_adapter.replace_projection(
                    kind,
                    token_str,
                    docs,
                    repository_uuidv4=snap.token.repository_uuidv4,
                    catalog_instance_uuidv4=snap.token.catalog_instance_uuidv4,
                )
            return counts

    def search(self, query: SearchQuery) -> SearchResponse:
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
                auth_docs, auth_summaries = self._extract_documents(snap, kind)

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
