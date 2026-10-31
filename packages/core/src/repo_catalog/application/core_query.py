"""Core-only authoritative Query with bounded reads and persistent completion fences."""

from __future__ import annotations

import hashlib
import heapq
import json
import sqlite3
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeVar

from repo_catalog.adapters.sqlite.core_coordination import (
    CoreCoordinator,
    SnapshotReadLimits,
    catalog_completion,
    persist_catalog_stop,
)
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.domain.core_query import (
    GitObjectView,
    GitObservationView,
    GitRepositoryView,
    RefNotesTargetView,
    validate_cursor_key,
)
from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.p1_core import (
    OID,
    CoreCoverageScope,
    CoreFailure,
    GitObservation,
    Provenance,
    RepositoryClaim,
    ScalarField,
    encode,
)
from repo_catalog.domain.query_contracts import (
    ByteReadResult,
    CatalogReadMode,
    CoverageView,
    PageRequest,
    PageResult,
    PaginationCursor,
    QueryError,
    SnapshotFenceToken,
    filter_digest,
)
from repo_catalog.domain.query_work import UnlimitedWorkBudget
from repo_catalog.domain.ref_observation import NotesMapping, RefObservationKey

if TYPE_CHECKING:
    from repo_catalog.domain.ports.p1_core import WorkBudget
    from repo_catalog.domain.ref_observation import (
        NotesMappingProjection,
        RefEnumerationResult,
        RefNotesInventoryProjection,
        RefObservationClaim,
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
class PinnedCoreSnapshot:
    mode: CatalogReadMode
    token: SnapshotFenceToken
    core: GitCore | None = None


def _paginate_items(
    items: Iterable[T],
    *,
    key_fn: Callable[[T], tuple],
    page: PageRequest,
    endpoint_kind: str,
    filters: dict[str, object],
    snapshot_token: str,
    cursor_validator: Callable[[str, tuple], None] = validate_cursor_key,
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
            validate_key=cursor_validator,
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
        position = key_fn(sliced[-1])
        try:
            cursor_validator(endpoint_kind, position)
        except Exception as error:
            raise QueryError(
                "INVALID_CURSOR", "pagination", "invalid endpoint key"
            ) from error
        next_cursor = PaginationCursor(
            endpoint_kind=endpoint_kind,
            filter_digest=f_digest,
            snapshot_token=snapshot_token,
            last_key=position,
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


class CoreQueryService:
    """Core initialization's corresponding read API; optional features are absent."""

    def __init__(
        self,
        directory: Path | str,
        *,
        mode: CatalogReadMode | Literal["auto"] = "auto",
        read_limits: SnapshotReadLimits = SnapshotReadLimits(),
    ):
        self.directory = Path(directory)
        if not isinstance(read_limits, SnapshotReadLimits):
            raise QueryError(
                "INVALID_LIMIT", "query", "finite SnapshotReadLimits required"
            )
        if mode not in ("auto", "core_only", "context_only", "paired"):
            raise QueryError("INVALID_MODE", "query", str(mode))
        self.read_limits = read_limits
        self.last_costs_ns: dict[str, int] = {}
        self._requested_mode = mode

    def detect_mode(self) -> CatalogReadMode:
        self._check_stop()
        if self._requested_mode in ("context_only", "paired"):
            raise QueryError(
                "MISSING_CAPABILITY",
                self._requested_mode,
                "Context/paired Query capability is not installed",
            )
        if (
            self._requested_mode == "auto"
            and (self.directory / "context.sqlite3").is_file()
        ):
            raise QueryError(
                "MISSING_CAPABILITY",
                "query",
                "auto topology requires Context/paired Query capability; select core_only explicitly",
            )
        if not (self.directory / "core.sqlite3").is_file():
            raise QueryError(
                "STORE_UNAVAILABLE", "core_only", "core_only mode requires core.sqlite3"
            )
        return "core_only"

    @contextmanager
    def _open_snapshot(self, *, required_store="any") -> Iterator[PinnedCoreSnapshot]:
        self._check_stop()
        self.detect_mode()
        if required_store not in ("any", "core"):
            raise QueryError(
                "MISSING_CAPABILITY", required_store, "Core-only Query capability"
            )
        coordinator = CoreCoordinator(
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
                yield PinnedCoreSnapshot(mode="core_only", token=token, core=core)
            with catalog_completion(self.directory):
                self._check_stop()

    def _check_stop(self) -> None:
        if (self.directory / "p1-recovery-stop.json").exists():
            raise CoreFailure(
                "RECOVERY_STOP", "catalog", "normal catalog operation stopped"
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

    def _ref_notes_targets_in_snapshot(self, core, object_oid, work=None):
        work = work if work is not None else UnlimitedWorkBudget()
        # Group-only reports do not create standalone Mapping rows. Discover
        # bounded headers first, then let the checked exact-Claim reader validate
        # memberships before deciding whether this target is actually related.
        candidates = (
            "WITH candidates AS ("
            "SELECT c.observation_origin_uuidv4,c.ref_observation_uuidv7,m.interpretation_kind,m.interpretation_version,m.interpretation_scope "
            "FROM ref_observation_claims c JOIN notes_mappings m ON m.object_format=c.root_format AND m.root_object_oid=c.root_object_oid "
            "WHERE m.object_format=? AND m.annotated_object_oid=? "
            "UNION SELECT observation_origin_uuidv4,ref_observation_uuidv7,interpretation_kind,interpretation_version,interpretation_scope "
            "FROM notes_mapping_groups WHERE object_format=? "
            "ORDER BY 1,2,3,4,5 LIMIT 10001) "
        )
        parameters = (*object_oid.key, object_oid.object_format)
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
                    claim.root_object_oid is None
                    or claim.root_object_oid.object_format != object_oid.object_format
                ):
                    continue
                projection = core.notes_mapping_projection(
                    claim, object_oid, *row[2:], work
                )
                if (
                    projection.claims
                    or projection.evidence
                    or any(
                        target == object_oid.object_oid
                        for group in projection.groups
                        for target, _, _ in group.members
                    )
                ):
                    views.append(RefNotesTargetView(observation, projection))
        return tuple(views)

    def get_git_object(
        self,
        object_oid: OID,
        *,
        include_bytes: bool = False,
    ) -> GitObjectView:
        with self.open_snapshot(required_store="core") as snap:
            assert snap.core is not None
            return self._git_object_in_snapshot(
                snap.core,
                object_oid,
                include_bytes=include_bytes,
            )

    def _git_object_in_snapshot(
        self,
        core: GitCore,
        object_oid: OID,
        *,
        include_bytes: bool = False,
        ref_work=None,
    ) -> GitObjectView:
        exists = core.sql(
            "SELECT 1 FROM git_objects WHERE object_format=? AND object_oid=?",
            object_oid.key,
        )
        if not exists:
            raise QueryError(
                "OBJECT_NOT_FOUND", object_oid, f"Git object {object_oid} not in Core"
            )

        field_rows = core.sql(
            "SELECT DISTINCT field FROM scalar_claims WHERE object_format=? AND object_oid=? ORDER BY field",
            object_oid.key,
        )
        present_fields = {row[0] for row in field_rows} | {"type", "size"}
        scalars = {
            field: core.scalar(object_oid, field)
            for field in ALL_SCALAR_FIELDS
            if field in present_fields
        }

        rel_rows = core.sql(
            "SELECT DISTINCT relation FROM relation_groups WHERE object_format=? AND object_oid=? ORDER BY relation",
            object_oid.key,
        )
        present_rels = {row[0] for row in rel_rows}
        relations = {
            rel: core.relations(object_oid, rel)
            for rel in ALL_RELATIONS
            if rel in present_rels
        }

        retained_row = core.sql(
            "SELECT size,digest_sha256 FROM retained_metadata WHERE object_format=? AND object_oid=? ORDER BY physical_copy_uuidv4 LIMIT 1",
            object_oid.key,
        )
        metadata_retained = bool(retained_row)
        retained_bytes: ByteReadResult | None = None
        if include_bytes:
            retained_bytes = self._read_metadata_bytes_in_snapshot(core, object_oid)

        return GitObjectView(
            object_oid=object_oid,
            scalars=scalars,
            relations=relations,
            metadata_retained=metadata_retained,
            retained_bytes=retained_bytes,
            ref_notes_targets=self._ref_notes_targets_in_snapshot(
                core, object_oid, ref_work
            ),
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
                "SELECT object_format,object_oid FROM git_objects "
                "WHERE (? IS NULL OR object_format=?) "
                "ORDER BY object_format,object_oid",
                (object_format, object_format),
            )

            ref_work = UnlimitedWorkBudget()

            def views():
                for row in rows:
                    object_oid = self._stored(OID, row[0], row[1])
                    view = self._git_object_in_snapshot(
                        snap.core, object_oid, ref_work=ref_work
                    )
                    if native_type is not None and view.native_type != native_type:
                        continue
                    yield view

            return _paginate_items(
                views(),
                key_fn=lambda v: v.object_oid.key,
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

    def read_metadata_bytes(self, object_oid: OID) -> ByteReadResult:
        with self.open_snapshot(required_store="core") as snap:
            assert snap.core is not None
            return self._read_metadata_bytes_in_snapshot(snap.core, object_oid)

    def _read_metadata_bytes_in_snapshot(
        self, core: GitCore, object_oid: OID
    ) -> ByteReadResult:
        try:
            body = core.read_metadata(object_oid)
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
