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


class SourceIntegrityIndeterminateError(BackupValidationError):
    """Source integrity could not be established; corruption is not proven."""


class RestoreValidationError(RecoveryError):
    """Raised when restore baseline fails validation."""


class SalvageError(RecoveryError):
    """Raised when untrusted salvage extraction encounters an unrecoverable fault."""


class ActivationError(RecoveryError):
    """Raised when fresh catalog activation fails validation or no-overwrite guards."""


class CandidateDisposition(str, enum.Enum):
    ADMITTED = "admitted"
    REPLAYED = "replayed"
    OBSERVATION = "observation"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    UNPROCESSED = "unprocessed"


@dataclass(frozen=True)
class RecoveryBudget:
    max_input_records: int = 100_000
    max_input_bytes: int = 512 * 1024 * 1024  # 512 MB
    max_payload_bytes: int = 16 * 1024 * 1024  # 16 MB
    max_json_depth: int = 16
    max_work_units: Mapping[str, int] = field(
        default_factory=lambda: {
            "input_bytes": 256 * 1024 * 1024,
            "verification_bytes": 2 * 1024 * 1024 * 1024,
            "metadata_units": 1_000_000,
            "proof_steps": 100_000,
        }
    )

    def __post_init__(self):
        for field_name, value in [
            ("max_input_records", self.max_input_records),
            ("max_input_bytes", self.max_input_bytes),
            ("max_payload_bytes", self.max_payload_bytes),
            ("max_json_depth", self.max_json_depth),
        ]:
            if type(value) is not int or value <= 0:
                raise ValueError(
                    f"{field_name} must be a positive integer, got {type(value).__name__}: {value}"
                )
        for k, v in self.max_work_units.items():
            if type(v) is not int or v <= 0:
                raise ValueError(
                    f"max_work_units['{k}'] must be a positive integer, got {type(v).__name__}: {v}"
                )


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
    extraction_provenance: Mapping[str, Any]
    payload: Mapping[str, Any]
    extraction_status: ExtractionStatus
    provenance: Mapping[str, Any] | None = None
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
    partial: bool = False


@dataclass(frozen=True)
class MergeReceipt:
    destination_path: str
    candidates_processed: int
    admitted_units: int
    rejected_units: int
    replayed_units: int = 0
    observation_units: int = 0
    deferred_units: int = 0
    unprocessed_units: int = 0
    rejections: list[Mapping[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ActivationReceipt:
    activated_catalog_path: str
    source_backup_id: str
    reconstructed_stores: list[str]
    timestamp_us: int
    clean_operational: bool
    search_derivative_state: str = "initialized_empty"
