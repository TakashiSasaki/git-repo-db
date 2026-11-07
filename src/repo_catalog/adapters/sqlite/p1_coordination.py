"""Isolated P1 reference adapters; the normal CLI does not import this module.

Support: cooperating processes on POSIX local filesystems with flock and SQLite
WAL locking. Unsupported platforms fail explicitly. Network filesystems and
hostile/privileged writers are outside this boundary. P7 must implement fresh
restore/activation and complete power-loss durability; this is not that engine.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from contextlib import ExitStack, closing
from dataclasses import dataclass
from pathlib import Path

from repo_catalog.adapters.sqlite.context_transaction import (
    AdmissionTransaction as AdmissionTransaction,
)
from repo_catalog.adapters.sqlite.core_coordination import (
    ReadSnapshot as ReadSnapshot,
)
from repo_catalog.adapters.sqlite.core_coordination import (
    SnapshotReadLimits as SnapshotReadLimits,
)
from repo_catalog.adapters.sqlite.core_coordination import (
    _identity,
    _json,
    _sqlite_corruption,
)
from repo_catalog.adapters.sqlite.core_coordination import (
    apply_snapshot_read_limits as apply_snapshot_read_limits,
)
from repo_catalog.adapters.sqlite.core_coordination import (
    catalog_completion as catalog_completion,
)
from repo_catalog.adapters.sqlite.core_coordination import (
    catalog_gate as catalog_gate,
)
from repo_catalog.adapters.sqlite.core_coordination import (
    persist_catalog_stop as persist_catalog_stop,
)
from repo_catalog.adapters.sqlite.operational_coordination import (
    NotesWorkBudget as NotesWorkBudget,
)
from repo_catalog.adapters.sqlite.operational_coordination import (
    WorkLedger as WorkLedger,
)
from repo_catalog.adapters.sqlite.paired_coordination import (
    PairedSnapshot as PairedSnapshot,
)
from repo_catalog.adapters.sqlite.paired_coordination import PairSnapshotCoordinator
from repo_catalog.adapters.sqlite.paired_coordination import (
    validate_dependencies as validate_dependencies,
)
from repo_catalog.adapters.sqlite.paired_coordination import (
    validate_pair as validate_pair,
)
from repo_catalog.domain.p1_coordination import (
    AdmissionFailure,
    CoordinationError,
    PairAdmission,
    SnapshotToken,
)
from repo_catalog.domain.p1_coordination import (
    NotesLimits as NotesLimits,
)
from repo_catalog.domain.p1_coordination import (
    RequestIdentity as RequestIdentity,
)
from repo_catalog.domain.p1_coordination import (
    WorkMeasurement as WorkMeasurement,
)
from repo_catalog.domain.p1_coordination import (
    WorkPermit as WorkPermit,
)


@dataclass(frozen=True)
class _ContextAdmissionBinding:
    authorization: object
    admission: object
    leases: ExitStack
    live_leases: list

    def check_current(self):
        self.authorization.validate_context(self.admission)
        for lease in self.live_leases:
            lease.check_current()


class PairCoordinator(PairSnapshotCoordinator):
    def __init__(
        self,
        directory: Path,
        *,
        read_limits: SnapshotReadLimits | None = None,
        metadata_only: bool = False,
        authorization=None,
    ):
        if authorization is not None:
            from repo_catalog.domain.context_admission import (
                AdmissionRefused,
                ContextAdmissionService,
            )

            if not isinstance(authorization, ContextAdmissionService):
                raise AdmissionRefused("PERMISSION_DENIED")
        self._authorization = authorization
        self.directory = Path(directory)
        self.read_limits = read_limits
        self.metadata_only = metadata_only
        # Read-only instrumentation, never a freshness proof or domain fact.
        self.last_read_costs_ns: dict[str, int] = {}

    def admit(
        self,
        core_unit: Callable[[AdmissionTransaction], None],
        context_unit: Callable[[AdmissionTransaction], None],
        *,
        cut: Callable[[str], None] = lambda point: None,
        authorization=None,
        admission=None,
    ) -> PairAdmission:
        from repo_catalog.domain.context_admission import (
            AdmissionRefused,
            ContextAdmissionService,
            DependencySet,
        )

        # Authenticate the local handle before catalog or dependency lookups.
        if authorization is not None and authorization is not self._authorization:
            raise AdmissionRefused("PERMISSION_DENIED")
        authorization = self._authorization
        if authorization is not None or admission is not None:
            if not isinstance(authorization, ContextAdmissionService):
                raise AdmissionRefused("PERMISSION_DENIED")
            authorization.validate_context(admission)
            if admission.operation == "exchange_export":
                raise AdmissionRefused("PERMISSION_DENIED")
        self._check_running()
        try:
            with ExitStack() as leases:
                binding = None
                if authorization is not None:
                    lease = leases.enter_context(
                        authorization.authorize(admission, DependencySet())
                    )
                    binding = _ContextAdmissionBinding(
                        authorization, admission, leases, [lease]
                    )
                return self._admit(
                    core_unit, context_unit, cut=cut, context_admission=binding
                )
        except AdmissionFailure as error:
            if getattr(
                error.cause, "code", None
            ) == "AUTHORITATIVE_CORRUPTION" or _sqlite_corruption(error.cause):
                self._record_corruption(error.cause, existing=False)
            raise
        except Exception as error:
            # Opening/validating a damaged database can fail before a local
            # admission transaction exists; the external stop still applies.
            if _sqlite_corruption(error):
                self._record_corruption(error)
            raise

    def _admit(
        self, core_unit, context_unit, *, cut, context_admission=None
    ) -> PairAdmission:
        with catalog_gate(self.directory, exclusive=True), ExitStack() as stack:
            self._check_running()
            core = stack.enter_context(closing(self._open("core")))
            context = stack.enter_context(closing(self._open("context")))
            try:
                if _identity(core, "core") != _identity(context, "context"):
                    raise CoordinationError("PAIR_IDENTITY", "core+context")
            except Exception as error:
                self._record_corruption(error)
                raise
            core_committed, context_committed = False, False
            core_capability = context_capability = None
            try:
                core.execute("BEGIN IMMEDIATE")
                core_capability = AdmissionTransaction(core)
                core_unit(core_capability)
                core.set_authorizer(None)
                cut("before_core_commit")
                with catalog_completion(self.directory):
                    core.commit()
                core_committed = True
                core_capability._expire()
                cut("after_core_commit")
                context.execute("BEGIN IMMEDIATE")
                context_capability = AdmissionTransaction(
                    context, _context_admission=context_admission
                )
                context_unit(context_capability)
                context.set_authorizer(None)
                cut("during_context")
                validate_dependencies(core, context)
                with catalog_completion(self.directory):
                    if context_admission is not None:
                        context_admission.check_current()
                    context.commit()
                context_committed = True
                context_capability._expire()
                cut("after_context_commit")
                self._check_running()
            except Exception as error:
                self._record_corruption(error, existing=False)
                core.set_authorizer(None)
                context.set_authorizer(None)
                core.rollback()
                context.rollback()
                raise AdmissionFailure(
                    PairAdmission(core_committed, context_committed), error
                ) from error
            except BaseException:
                core.set_authorizer(None)
                context.set_authorizer(None)
                core.rollback()
                context.rollback()
                raise
            finally:
                for capability in (core_capability, context_capability):
                    if capability is not None:
                        capability._expire()
        return PairAdmission(True, True)

    def backup_candidate(
        self,
        destination: Path,
        *,
        cut: Callable[[str], None] = lambda point: None,
    ) -> SnapshotToken:
        self._check_running()
        try:
            return self._backup_candidate(destination, cut=cut)
        except Exception as error:
            if (
                self.read_limits is not None
                and getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT
            ):
                raise CoordinationError(
                    "QUERY_BUDGET", "snapshot", "SQLite VM step limit"
                ) from error
            if getattr(error, "code", None) in (
                "CORRUPTION",
                "FOREIGN_KEY",
                "MISSING_CORE_REFERENCE",
            ) or _sqlite_corruption(error):
                self._record_corruption(error)
            raise

    def _backup_candidate(self, destination: Path, *, cut) -> SnapshotToken:
        """Conservative unpublished pair, certified only after candidate checks.

        No overwrite, source mutation, restore or activation. The certificate is
        local process-completion evidence. Full fsync/power-loss protocol is P7.
        """
        destination = Path(destination)
        destination.mkdir()  # Never bless an interrupted/existing destination.
        with catalog_gate(self.directory, exclusive=False):
            self._check_running()
            for role in ("core", "context"):
                with (
                    closing(self._open(role)) as source,
                    closing(sqlite3.connect(destination / f"{role}.sqlite3")) as target,
                ):
                    try:
                        source.backup(target)
                    except Exception as error:
                        self._record_corruption(error)
                        raise
                cut(f"after_{role}_backup")
            try:
                with PairCoordinator(destination).snapshots() as pair:
                    token = pair.token
            except Exception as error:
                self._record_corruption(error)
                raise
            certificate = {
                "scope": "core+context",
                "token": token.__dict__,
                "files": {
                    f"{role}.sqlite3": hashlib.sha256(
                        (destination / f"{role}.sqlite3").read_bytes()
                    ).hexdigest()
                    for role in ("core", "context")
                },
                "power_loss_safe": False,
            }
            cut("before_certificate")
            with catalog_completion(self.directory):
                (destination / "p1-pair-candidate.json").write_text(_json(certificate))
            return token

    @staticmethod
    def validate_backup(destination: Path) -> SnapshotToken:
        candidate = json.loads((destination / "p1-pair-candidate.json").read_text())
        expected = {"core.sqlite3", "context.sqlite3"}
        if candidate["scope"] != "core+context" or set(candidate["files"]) != expected:
            raise CoordinationError("PAIR_CERTIFICATE", "backup")
        for name, digest in candidate["files"].items():
            if hashlib.sha256((destination / name).read_bytes()).hexdigest() != digest:
                raise CoordinationError("PAIR_BYTES", "backup")
        with PairCoordinator(destination).snapshots() as pair:
            if pair.token.__dict__ != candidate["token"]:
                raise CoordinationError("PAIR_CONTENT", "backup")
            return pair.token


class SearchProjection:
    """Discardable authority-derived candidates; None requires authority scan.

    Public builders read actual pinned authority. There is no general text/body
    admission API: P6 owns additional typed projectors, including verified notes.
    """

    def __init__(self, db: sqlite3.Connection | None):
        self.db = db

    @staticmethod
    def context_documents(pair: PairedSnapshot) -> dict[str, str]:
        if validate_pair(pair.core, pair.context) != pair.token:
            raise CoordinationError("SNAPSHOT_CONTENT", "search")
        documents = {}
        for row in pair.context.execute(
            "SELECT c.service_instance_uuidv4,c.resource_kind,c.provider_resource_id,c.field_name,"
            "c.clock_json,c.value_json,c.provenance_json,b.text_value "
            "FROM field_candidates c LEFT JOIN text_bodies b ON c.text_body_sha256=b.sha256"
        ):
            # Only this named local FK denotes retained text. Reported digests
            # remain qualified metadata even if equal bytes happen to be local.
            value = row[7] if row[3] == "text_body_sha256" else json.loads(row[5])
            if isinstance(value, str):
                documents[_json(tuple(row[:7]))] = value
        return documents

    def rebuild_context(self, pair: PairedSnapshot):
        self._replace("context_text", pair.token, self.context_documents(pair))

    def rebuild_git_metadata(self, pair: PairedSnapshot):
        if validate_pair(pair.core, pair.context) != pair.token:
            raise CoordinationError("SNAPSHOT_CONTENT", "search")
        documents = {
            _json(tuple(row)): row[1]
            for row in pair.core.execute(
                "SELECT object_format,object_oid FROM git_objects"
            )
        }
        self._replace("git_metadata", pair.token, documents)

    def _replace(self, kind: str, token: SnapshotToken, documents: dict[str, str]):
        if self.db is None:
            raise CoordinationError("UNAVAILABLE", "search")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                "DELETE FROM search_documents WHERE projection_kind=?", (kind,)
            )
            self.db.execute(
                "DELETE FROM search_projections WHERE projection_kind=?", (kind,)
            )
            self.db.execute(
                "INSERT INTO search_projections VALUES(?,?)", (kind, token.encode())
            )
            self.db.executemany(
                "INSERT INTO search_documents VALUES(?,?,?,?)",
                [(kind, token.encode(), key, text) for key, text in documents.items()],
            )
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def candidates(
        self, kind: str, token: SnapshotToken, needle: str
    ) -> set[str] | None:
        if self.db is None:
            return None
        try:
            self.db.execute("BEGIN")
            if not self.db.execute(
                "SELECT 1 FROM search_projections WHERE projection_kind=? AND snapshot_token_json=?",
                (kind, token.encode()),
            ).fetchone():
                return None
            return {
                row[0]
                for row in self.db.execute(
                    "SELECT document_key_json FROM search_documents WHERE projection_kind=? "
                    "AND snapshot_token_json=? AND instr(searchable_text,?)>0",
                    (kind, token.encode(), needle),
                )
            }
        except sqlite3.DatabaseError:
            return None
        finally:
            self.db.rollback()

    def read(
        self,
        kind: str,
        token: SnapshotToken,
        needle: str,
        authoritative_scan: Callable[[], dict[str, str]],
    ) -> tuple[str, dict[str, str]]:
        candidates = self.candidates(kind, token, needle)
        rows = authoritative_scan()  # caller retains pinned authority snapshot
        expected = {key for key, text in rows.items() if needle in text}
        if candidates is not None and candidates != expected:
            # A matching freshness token alone cannot prove a damaged/truncated
            # projection complete. The conservative P1 adapter verifies against
            # direct authority; optimized completeness proof belongs to P6.
            candidates = None
        return (
            "projection" if candidates is not None else "authority_scan",
            {
                key: text
                for key, text in rows.items()
                if needle in text and (candidates is None or key in candidates)
            },
        )
