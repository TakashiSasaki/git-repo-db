"""Domain types, contracts, and invariants for P7 production recovery under ADR 0026."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Mapping


class BackupScope(str, enum.Enum):
    GIT_ONLY = "git_only"
    PAIRED = "paired"


class CandidateType(str, enum.Enum):
    GIT_METADATA = "git_metadata"
    RETAINED_BODY = "retained_body"
    NOTES_MAPPING = "notes_mapping"
    CONTEXT_RESOURCE = "context_resource"
    CONTEXT_DOCUMENT = "context_document"


class ExtractionStatus(str, enum.Enum):
    CLEAN = "clean"
    PARTIAL = "partial"
    CORRUPT_BOUNDARY = "corrupt_boundary"


class RecoveryError(Exception):
    """Base error for all P7 recovery operations."""


class CorruptionDetectedError(RecoveryError):
    """Raised when authoritative stored corruption is detected."""


class CatalogStoppedError(RecoveryError):
    """Raised when an operation is attempted on a stopped suspect catalog."""


class BackupValidationError(RecoveryError):
    """Raised when backup data or manifest fails validation."""


class RestoreValidationError(RecoveryError):
    """Raised when restore baseline fails validation."""


class SalvageError(RecoveryError):
    """Raised when untrusted salvage extraction encounters an unrecoverable fault."""


class ActivationError(RecoveryError):
    """Raised when fresh catalog activation fails validation or no-overwrite guards."""


@dataclass(frozen=True)
class StoreManifest:
    path: str
    bytes: int
    sha256: str
    schema_fingerprint: str


@dataclass(frozen=True)
class RetainedByteSummary:
    commit_count: int = 0
    tree_count: int = 0
    tag_count: int = 0
    notes_body_count: int = 0
    total_retained_bytes: int = 0


@dataclass(frozen=True)
class BackupManifest:
    manifest_version: int
    backup_id: str
    created_at_us: int
    repository_uuidv4: str
    catalog_instance_uuidv4: str
    scope: BackupScope
    stores: Mapping[str, StoreManifest]
    retained_byte_summary: RetainedByteSummary
    overall_sha256: str


@dataclass(frozen=True)
class BackupReceipt:
    backup_id: str
    backup_path: str
    scope: BackupScope
    manifest: BackupManifest
    overall_sha256: str
    verified_retained_bytes: int
    verified_clean: bool


@dataclass(frozen=True)
class RestoreReceipt:
    backup_id: str
    destination_path: str
    scope: BackupScope
    revalidated_stores: list[str]
    revalidated_retained_bytes: int
    revalidated_clean: bool


@dataclass(frozen=True)
class SalvageCandidate:
    candidate_id: str
    candidate_type: CandidateType
    capture_origin_uuidv4: str | None
    capture_uuidv4: str | None
    provenance: Mapping[str, Any]
    payload: Mapping[str, Any]
    extraction_status: ExtractionStatus
    error: str | None = None


@dataclass(frozen=True)
class SalvageReceipt:
    catalog_path: str
    candidate_count: int
    clean_count: int
    partial_count: int
    corrupt_count: int
    unreadable_scope: list[str]
    output_file: str


@dataclass(frozen=True)
class MergeReceipt:
    destination_path: str
    candidates_processed: int
    admitted_units: int
    rejected_units: int
    rejections: list[Mapping[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ActivationReceipt:
    activated_catalog_path: str
    source_backup_id: str
    reconstructed_stores: list[str]
    timestamp_us: int
    clean_operational: bool
