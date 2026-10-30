"""SQLite and filesystem recovery adapters for P7 under ADR 0026."""

from __future__ import annotations

import base64
import ctypes
import errno
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping
from contextlib import ExitStack
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from repo_catalog.domain.context_admission import (
        AdmissionContext,
        ContextAdmissionService,
    )

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.p1_coordination import (
    NotesLimits,
    _file_gate,
    catalog_completion,
    catalog_gate,
    persist_catalog_stop,
)
from repo_catalog.adapters.sqlite.p1_schema import (
    SchemaError,
    expected_schema,
    oid,
    register_functions,
    schema_rows,
    uuid4,
)
from repo_catalog.adapters.sqlite.p1_schema import (
    connect as p1_connect,
)
from repo_catalog.adapters.sqlite.p1_schema import (
    fingerprint as p1_schema_fingerprint,
)
from repo_catalog.adapters.sqlite.p1_schema import (
    initialize as p1_init,
)
from repo_catalog.adapters.sqlite.p1_schema import (
    validate as p1_schema_validate,
)
from repo_catalog.adapters.sqlite.recovery_budget import recovery_request
from repo_catalog.adapters.sqlite.recovery_validation import (
    StoredContextInvariantError,
    bounded_domain_exists,
    validate_stored_admission_guards,
    validate_stored_checks,
    validate_stored_text_encoding,
    verify_existing_context_text,
)
from repo_catalog.domain.git_native import parse_metadata
from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.p1_core import (
    OID,
    Capture,
    CoreFailure,
    NativeObject,
    NotesProof,
    account_verification,
    native_oid,
    valid_note_role,
)
from repo_catalog.domain.recovery import (
    ActivationError,
    ActivationReceipt,
    BackupManifest,
    BackupReceipt,
    BackupScope,
    BackupValidationError,
    CandidateType,
    CatalogStoppedError,
    CorruptionDetectedError,
    ExtractionStatus,
    MergeReceipt,
    RecoveryBudget,
    RecoveryError,
    RestoreReceipt,
    RestoreValidationError,
    RetainedByteSummary,
    SalvageError,
    SalvageReceipt,
    SourceIntegrityIndeterminateError,
    StoreManifest,
)


class RefObservationBackupUnsupported(BackupValidationError):
    """The I3 backup manifest does not yet certify ref-observation data."""


_REF_OBSERVATION_TABLES = frozenset(
    {
        "ref_observations",
        "ref_observation_claims",
        "notes_mappings",
        "notes_mapping_claims",
        "notes_mapping_groups",
        "notes_mapping_evidence",
        "ref_retained_notes",
    }
)


AT_FDCWD = -100
RENAME_NOREPLACE = 1


def _decode_native_ref(raw_ref: str | None) -> str | None:
    if not raw_ref:
        return raw_ref
    if raw_ref.startswith("refs/"):
        return raw_ref
    try:
        parsed = json.loads(raw_ref)
        if isinstance(parsed, list) and len(parsed) == 2 and parsed[0] == "native-ref":
            return bytes.fromhex(parsed[1]).decode("utf-8", "surrogateescape")
    except Exception:
        pass
    return raw_ref


def _open_directory_nofollow(path: Path, *, create: bool = False) -> int:
    """Pin each directory component; never follow a substituted symlink."""
    absolute = Path(os.path.abspath(path))
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in absolute.parts[1:]:
            try:
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError:
                    pass
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _assert_directory_identity(
    path: Path, expected_fd: int, *, label: str = "Validated catalog"
) -> None:
    try:
        named_fd = _open_directory_nofollow(path)
        try:
            named = os.fstat(named_fd)
            pinned = os.fstat(expected_fd)
            if (named.st_dev, named.st_ino) != (pinned.st_dev, pinned.st_ino):
                raise ActivationError(f"{label} directory identity changed")
        finally:
            os.close(named_fd)
    except OSError as error:
        raise ActivationError(f"{label} directory identity unavailable") from error


def _open_regular_at(directory_fd: int, name: str) -> int:
    try:
        fd = os.open(
            name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd
        )
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise RestoreValidationError(f"Symlink store forbidden: {name}") from error
        raise
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        os.close(fd)
        raise RestoreValidationError(f"Nonregular file or hardlink forbidden: {name}")
    return fd


def _bounded_directory_entries(fd: int, maximum: int) -> set[str]:
    entries = set()
    with os.scandir(fd) as iterator:
        for entry in iterator:
            entries.add(entry.name)
            if len(entries) > maximum:
                break
    return entries


def _read_bounded_fd(fd: int, limit: int) -> bytes:
    if os.fstat(fd).st_size > limit:
        raise RestoreValidationError("Manifest input exceeds finite byte limit")
    os.lseek(fd, 0, os.SEEK_SET)
    value = os.read(fd, limit + 1)
    if len(value) > limit:
        raise RestoreValidationError("Manifest input exceeds finite byte limit")
    return value


def _copy_verified_fd(fd: int, target: Path, size: int, digest: str) -> None:
    """Hash exactly the copied bytes; bounded chunks also detect growth."""
    before = os.fstat(fd)
    if before.st_size != size:
        raise RestoreValidationError("Store file size mismatch before copying")
    os.lseek(fd, 0, os.SEEK_SET)
    hasher = hashlib.sha256()
    remaining = size
    with target.open("xb") as output:
        while remaining:
            chunk = os.read(fd, min(1024 * 1024, remaining))
            if not chunk:
                raise RestoreValidationError("Store truncated during copying")
            output.write(chunk)
            hasher.update(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise RestoreValidationError("Store grew during copying")
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) or hasher.hexdigest() != digest:
            raise RestoreValidationError(
                "Store mutation or SHA-256 mismatch during copying"
            )
        output.flush()
        os.fsync(output.fileno())


def _atomic_publish_noreplace(
    staging_dir: Path, destination_path: Path, *, parent_fd: int | None = None
) -> None:
    """Linux local-filesystem renameat2 publication, relative to a pinned parent.

    File and staging-directory fsync must precede this call. A post-rename fsync
    failure is reported as uncertain publication, never as successful durability.
    This is an ordering contract, not a tested physical host power-loss claim.
    """
    staging_dir = Path(os.path.abspath(staging_dir))
    destination_path = Path(os.path.abspath(destination_path))
    if staging_dir == destination_path or (
        parent_fd is None and staging_dir.parent != destination_path.parent
    ):
        raise RecoveryError("Staging and destination must be distinct siblings")
    if os.name != "posix":
        raise RecoveryError("Atomic no-overwrite renameat2 is unavailable")
    parent_fd = (
        _open_directory_nofollow(staging_dir.parent)
        if parent_fd is None
        else os.dup(parent_fd)
    )
    try:
        source_stat = os.stat(staging_dir.name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(source_stat.st_mode):
            raise RecoveryError("Staging must be a real directory")
        libc = ctypes.CDLL(None, use_errno=True)
        if not hasattr(libc, "renameat2"):
            raise RecoveryError("Atomic no-overwrite renameat2 is unavailable")
        libc.renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        libc.renameat2.restype = ctypes.c_int
        result = libc.renameat2(
            parent_fd,
            os.fsencode(staging_dir.name),
            parent_fd,
            os.fsencode(destination_path.name),
            RENAME_NOREPLACE,
        )
        if result:
            error = ctypes.get_errno()
            if error == errno.EEXIST:
                raise BackupValidationError(
                    "Destination already exists; no-overwrite publication"
                )
            raise RecoveryError(f"renameat2 failed: {os.strerror(error)}")
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def _check_json_depth(
    obj: Any,
    current_depth: int = 1,
    max_depth: int = 16,
    max_elements: int = 10_000,
    element_counter: list[int] | None = None,
) -> None:
    if current_depth > max_depth:
        raise _InputLimit(
            f"JSON nesting depth exceeds maximum allowed limit of {max_depth}"
        )
    if element_counter is None:
        element_counter = [0]
    if isinstance(obj, dict):
        element_counter[0] += len(obj)
        if element_counter[0] > max_elements:
            raise _InputLimit(
                f"JSON element count exceeds maximum allowed limit of {max_elements}"
            )
        for v in obj.values():
            _check_json_depth(
                v, current_depth + 1, max_depth, max_elements, element_counter
            )
    elif isinstance(obj, list):
        element_counter[0] += len(obj)
        if element_counter[0] > max_elements:
            raise _InputLimit(
                f"JSON element count exceeds maximum allowed limit of {max_elements}"
            )
        for v in obj:
            _check_json_depth(
                v, current_depth + 1, max_depth, max_elements, element_counter
            )


class _InputLimit(ValueError):
    """Finite input work ended; the unread suffix has deliberately not been scanned."""


def _bounded_json_loads(raw: str | bytes, budget: RecoveryBudget) -> Any:
    """Check lexical depth/elements before json.loads allocates an object tree.

    JSON syntax is still checked by the standard parser. The lexical element
    count deliberately overestimates malformed inputs and object keys.
    """
    if len(raw) > budget.max_payload_bytes * 8 + 8192:
        raise _InputLimit("JSON representation exceeds finite payload envelope")
    depth = 0
    elements = 0
    in_string = False
    escaped = False
    for ch in raw:
        ch = chr(ch) if isinstance(ch, int) else ch
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
            elements += 1
        elif ch in "[{":
            depth += 1
            elements += 1
            if depth > budget.max_json_depth:
                raise _InputLimit("JSON nesting depth exceeds finite limit")
        elif ch in "]}":
            depth -= 1
        elif ch == ",":
            elements += 1
        if elements > 20_000:
            raise _InputLimit("JSON element count exceeds finite limit")
    obj = json.loads(raw)
    _check_json_depth(obj, max_depth=budget.max_json_depth)
    return obj


def _bounded_utf8(value: Any, max_bytes: int, work=None) -> bytes:
    if not isinstance(value, str):
        raise ValueError("Context text_value must be a string")
    if len(value) > max_bytes:
        raise ValueError("Context text exceeds finite payload byte limit")
    size = 0
    for char in value:
        scalar = ord(char)
        if 0xD800 <= scalar <= 0xDFFF:
            raise ValueError("Context text is not exact UTF-8")
        size += (
            1
            if scalar < 0x80
            else 2
            if scalar < 0x800
            else 3
            if scalar < 0x10000
            else 4
        )
        if size > max_bytes:
            raise ValueError("Context text exceeds finite UTF-8 payload byte limit")
    if work is not None:
        work.require("input_bytes", size)
    result = value.encode("utf-8")
    if work is not None:
        work.charge("input_bytes", len(result))
    return result


def _hash_recovery_bytes(body: bytes, work) -> str:
    work.require("verification_bytes", len(body))
    digest = hashlib.sha256(body).hexdigest()
    work.charge("verification_bytes", len(body))
    return digest


def _check_candidate_shape(record: dict, budget: RecoveryBudget) -> None:
    payload = record.get("payload", {})
    for key in ("extraction_provenance", "provenance"):
        if record.get(key) is not None and not isinstance(record[key], dict):
            raise ValueError(f"{key} must be an object when present")
    string_fields = (
        "object_format",
        "full_oid",
        "native_type",
        "physical_copy_uuidv4",
        "repository_uuidv4",
        "capture_origin_uuidv4",
        "capture_uuidv4",
        "source",
        "ref",
        "root",
        "target",
        "path",
        "digest_sha256",
        "sha256",
        "body_base64",
        "proof_bundle",
        "text_value",
    )
    for key in string_fields:
        if (
            key in payload
            and payload[key] is not None
            and not isinstance(payload[key], str)
        ):
            raise ValueError(f"payload.{key} must be a string when present")
        if (
            isinstance(payload.get(key), str)
            and key not in ("body_base64", "proof_bundle", "text_value")
            and len(payload[key]) > budget.max_payload_bytes
        ):
            raise ValueError(f"payload.{key} exceeds finite payload limit")
    for key in ("capture_origin_uuidv4", "capture_uuidv4"):
        if record.get(key) is not None and not isinstance(record[key], str):
            raise ValueError(f"{key} must be a string when present")
    if "size" in payload and (type(payload["size"]) is not int or payload["size"] < 0):
        raise ValueError("payload.size must be a nonnegative integer")


def _decode_bounded_base64(value: Any, max_bytes: int, work=None) -> bytes:
    if not isinstance(value, str) or len(value) > ((max_bytes + 2) // 3) * 4:
        raise ValueError("Base64 payload exceeds finite decoded-byte limit")
    # Padding-aware bound permits an exact finite ceiling for valid input.
    # Invalid input retains this conservative expenditure, including failures.
    padding = 2 if value.endswith("==") else 1 if value.endswith("=") else 0
    upper = (
        len(value) // 4 * 3 - padding
        if len(value) % 4 == 0
        else ((len(value) + 3) // 4) * 3
    )
    upper = max(0, upper)
    if work is not None:
        work.require("input_bytes", upper)
    try:
        result = base64.b64decode(value, validate=True)
    except Exception:
        if work is not None:
            work.charge("input_bytes", upper)
        raise
    if work is not None:
        work.charge("input_bytes", len(result))
    if len(result) > max_bytes:
        raise ValueError("Decoded payload exceeds finite byte limit")
    return result


def _decode_proof_bundle(
    value: Any, budget: RecoveryBudget, object_format: str, work=None
):
    if not isinstance(value, str):
        raise ValueError("Notes proof must be text")
    if len(value) > budget.max_payload_bytes * 2:
        raise _InputLimit("Notes proof exceeds finite payload limit")
    bundle = _bounded_json_loads(value, budget)
    if not isinstance(bundle, list):
        raise ValueError("Notes proof must be a list")
    if len(bundle) > budget.max_work_units.get("proof_steps", 100_000):
        raise _InputLimit("Notes proof exceeds finite proof-step limit")
    structures = []
    total_bytes = 0
    for entry in bundle:
        if (
            not isinstance(entry, list)
            or len(entry) != 3
            or not all(isinstance(v, str) for v in entry)
        ):
            raise ValueError("Malformed notes proof object")
        total_bytes += (len(entry[2]) + 1) // 2
        if total_bytes > budget.max_payload_bytes:
            raise _InputLimit("Notes proof native bytes exceed finite payload limit")
        upper = (len(entry[2]) + 1) // 2
        if work is not None:
            work.require("input_bytes", upper)
        try:
            body = bytes.fromhex(entry[2])
        except Exception:
            if work is not None:
                work.charge("input_bytes", upper)
            raise
        if work is not None:
            work.charge("input_bytes", len(body))
        structures.append(
            NativeObject(
                oid=OID(object_format, entry[0]),
                native_type=entry[1],
                body=body,
                declared_size=len(body),
                digest_sha256=_hash_recovery_bytes(body, work)
                if work is not None
                else hashlib.sha256(body).hexdigest(),
            )
        )
    return tuple(structures)


def _bounded_jsonl_records(
    stream, *, max_line_bytes: int, max_bytes: int, reserve, settle=None, state=None
):
    """Read finite chunks, reserving their upper bound before the actual read.

    No suffix scan is performed to compute a fictitiously precise omitted count.
    The shared state counts only bytes not yet yielded as a candidate; callers
    can report known omissions without inventing a nonexistent suffix at EOF.
    """
    if state is None:
        state = {}
    state.update(buffered_bytes=0, prefetched_bytes=0)
    buffered = bytearray()
    scanned = 0
    while True:
        if scanned >= max_bytes:
            raise _InputLimit("Input scan byte limit reached; unread suffix unknown")
        amount = min(65536, max_bytes - scanned)
        reserve("input_scan_bytes", amount)
        block = stream.read(amount)
        if settle is not None:
            settle("input_scan_bytes", len(block))
        scanned += len(block)
        state["prefetched_bytes"] = len(block)
        if not block:
            if buffered:
                line = bytes(buffered)
                buffered.clear()
                state["buffered_bytes"] = 0
                yield line
            return
        offset = 0
        while offset < len(block):
            newline = block.find(b"\n", offset)
            end = len(block) if newline < 0 else newline + 1
            if len(buffered) + end - offset > max_line_bytes:
                raise _InputLimit(
                    "JSONL line exceeds finite envelope; unread suffix unknown"
                )
            buffered.extend(block[offset:end])
            state["buffered_bytes"] = len(buffered)
            offset = end
            state["prefetched_bytes"] = len(block) - offset
            if newline >= 0:
                line = bytes(buffered)
                buffered.clear()
                state["buffered_bytes"] = 0
                yield line


def _has_known_unread_input(stream, state) -> bool:
    """A lower bound only: do not read an unbounded suffix to count omissions."""
    if state.get("buffered_bytes", 0) or state.get("prefetched_bytes", 0):
        return True
    try:
        return os.fstat(stream.fileno()).st_size > stream.tell()
    except (OSError, AttributeError):
        return False


def _open_salvage_input(path: Path):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise RecoveryError("Salvage input must be a regular file")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def _copy_forensic_files(catalog_dir: Path, forensic_dir: Path, max_bytes: int) -> None:
    """Bound actual streamed bytes, not only a racy preflight stat estimate."""
    copied = 0
    for name in ("core.sqlite3", "context.sqlite3"):
        for suffix in ("", "-wal", "-shm", "-journal"):
            source = catalog_dir / (name + suffix)
            if not source.exists():
                continue
            if source.is_symlink():
                raise SalvageError(f"Refusing symlink source evidence: {source.name}")
            flags = (
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0)
            )
            with os.fdopen(os.open(source, flags), "rb") as src:
                before = os.fstat(src.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise SalvageError("Source evidence must be a regular file")
                if before.st_size > max_bytes - copied:
                    raise SalvageError("Suspect catalog exceeds recovery copy budget")
                with (forensic_dir / source.name).open("xb") as dest:
                    remaining_file = before.st_size
                    while remaining_file:
                        block = src.read(min(65536, remaining_file, max_bytes - copied))
                        if not block:
                            raise SalvageError(
                                "Source evidence shrank during forensic copy"
                            )
                        dest.write(block)
                        copied += len(block)
                        remaining_file -= len(block)
                    # One bounded probe detects growth without copying the suffix.
                    if src.read(1):
                        raise SalvageError("Source evidence grew during forensic copy")
                after = os.fstat(src.fileno())
                current = source.stat(follow_symlinks=False)
                if (
                    before.st_dev,
                    before.st_ino,
                    before.st_size,
                    before.st_mtime_ns,
                ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) or (
                    current.st_dev,
                    current.st_ino,
                ) != (after.st_dev, after.st_ino):
                    raise SalvageError("Source evidence changed during forensic copy")


class RecoveryWorkBudget:
    """Finite work budget enforcing explicit resource limits during recovery merge."""

    def __init__(
        self,
        *,
        note_bytes: int = 16 * 1024 * 1024,
        work_limits: Mapping[str, int] | None = None,
        initial_usage: Mapping[str, int] | None = None,
        reserve: Callable[[dict[str, int]], None] | None = None,
        settle: Callable[[dict[str, int]], None] | None = None,
    ) -> None:
        self.limits = NotesLimits(note_bytes=note_bytes)
        self._max = dict(NotesLimits.work_limits())
        if work_limits is not None:
            self._max.update(work_limits)
        self.usage: dict[str, int] = dict.fromkeys(self._max, 0)
        if initial_usage:
            for k, v in initial_usage.items():
                if k in self.usage and type(v) is int and v >= 0:
                    self.usage[k] = v
        self._pending: dict[str, int] = {}
        self._reserve = reserve
        self._settle = settle

    def is_exhausted(self, unit: str | None = None) -> bool:
        if unit is not None:
            limit = self._max.get(unit)
            return limit is not None and self.usage.get(unit, 0) >= limit
        return any(self.usage[u] >= self._max[u] for u in self._max if u in self.usage)

    def require(self, unit: str, amount: int = 1) -> None:
        if type(amount) is not int or amount < 0:
            raise ValueError("nonnegative integer work amount required")
        limit = self._max.get(unit)
        if limit is None:
            raise ValueError(f"unknown work unit: {unit}")
        if self.usage[unit] + amount > limit:
            raise CoreFailure(
                "BUDGET",
                unit,
                f"finite cumulative recovery work budget exhausted ({unit})",
            )
        if unit in self._pending:
            raise CoordinationError("UNSETTLED_WORK", "recovery", unit)
        updated = dict(self.usage)
        updated[unit] += amount
        if self._reserve is not None:
            self._reserve(updated)
        self.usage = updated
        self._pending[unit] = amount

    def abandon(self, unit: str) -> None:
        if unit not in self._pending:
            raise CoordinationError("UNRESERVED_WORK", "recovery", unit)
        del self._pending[unit]

    def charge(self, unit: str, amount: int) -> None:
        if unit not in self._pending:
            raise CoordinationError("UNRESERVED_WORK", "recovery", unit)
        reserved = self._pending[unit]
        if type(amount) is not int or amount < 0 or amount > reserved:
            raise ValueError("invalid charged work amount")
        updated = dict(self.usage)
        updated[unit] -= reserved - amount
        if self._settle is not None:
            self._settle(updated)
        self.usage = updated
        del self._pending[unit]


def _confirmed_integrity_failure(error: Exception) -> str | None:
    """Only positive integrity evidence can label a source corrupt.

    Validation wrappers retain causes. A lock, IO/permission failure, resource
    exhaustion or unexpected implementation failure anywhere in that chain is
    indeterminate, even when wrapped as BackupValidationError.
    """
    chain: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and current not in chain:
        chain.append(current)
        if isinstance(current, StoredContextInvariantError):
            # Trusted stored relation decoders have already classified their
            # ValueError/TypeError cause as a deterministic data invariant.
            break
        current = current.__cause__
    for cause in chain:
        if isinstance(cause, sqlite3.Error):
            code = getattr(cause, "sqlite_errorcode", 0)
            if code & 255 not in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB):
                return None
        elif isinstance(cause, (OSError, MemoryError, CoordinationError)):
            return None
        elif isinstance(cause, CoreFailure) and cause.code not in (
            "NATIVE_SYNTAX",
            "INVALID_IDENTITY",
            "INVALID_OBJECT",
        ):
            return None
        elif not isinstance(cause, (BackupValidationError, SchemaError, CoreFailure)):
            return None
    if any(isinstance(cause, SchemaError) for cause in chain):
        return "physical_schema"
    if isinstance(error, BackupValidationError) or any(
        isinstance(cause, sqlite3.Error) for cause in chain
    ):
        return "authoritative_data"
    return None


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fsync_file(path: Path) -> None:
    with path.open("rb") as f:
        os.fsync(f.fileno())


def _fsync_dir(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def is_catalog_stopped(catalog_dir: Path) -> bool:
    catalog_dir = Path(catalog_dir)
    return (catalog_dir / "recovery.stop").exists() or (
        catalog_dir / "p1-recovery-stop.json"
    ).exists()


def assert_catalog_not_stopped(catalog_dir: Path) -> None:
    if is_catalog_stopped(catalog_dir):
        raise CatalogStoppedError(
            f"Catalog at {catalog_dir} is in recovery stop mode; normal operations are fenced"
        )


def stop_catalog(catalog_dir: Path, reason: str, details: dict | None = None) -> None:
    catalog_dir = Path(catalog_dir)
    persist_catalog_stop(catalog_dir, reason)
    stop_file = catalog_dir / "recovery.stop"
    payload = {
        "reason": reason,
        "stopped_at_us": int(time.time() * 1_000_000),
        "details": details or {},
    }
    with _file_gate(catalog_dir / "p1-stop-fence.lock", exclusive=True):
        if not stop_file.exists():
            temp_path = catalog_dir / f"recovery.stop.tmp.{uuid.uuid4().hex}"
            temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            _fsync_file(temp_path)
            os.replace(temp_path, stop_file)
            _fsync_dir(catalog_dir)


class SQLiteRecoveryAdapter:
    """Production P7 backup, salvage, restore, and activation adapter under ADR 0026."""

    def create_consistent_backup(
        self,
        catalog_dir: Path,
        destination_path: Path,
        scope: BackupScope = BackupScope.PAIRED,
        *,
        snapshot_cut_callback: Callable[[], None] | None = None,
    ) -> BackupReceipt:
        catalog_dir = Path(catalog_dir)
        destination_path = Path(destination_path)

        assert_catalog_not_stopped(catalog_dir)

        if destination_path.exists() or destination_path.is_symlink():
            raise BackupValidationError(
                f"Destination path {destination_path} already exists; no-overwrite invariant violated"
            )

        core_db_path = catalog_dir / "core.sqlite3"
        context_db_path = catalog_dir / "context.sqlite3"

        if not core_db_path.exists():
            raise BackupValidationError(
                f"Authoritative core database missing at {core_db_path}"
            )

        if scope == BackupScope.PAIRED and not context_db_path.exists():
            raise BackupValidationError(
                f"Paired scope requires context database, but {context_db_path} is missing"
            )

        backup_id = str(uuid.uuid4())
        created_at_us = int(time.time() * 1_000_000)

        staging_dir = (
            destination_path.parent / f"{destination_path.name}.tmp.{backup_id}"
        )
        staging_dir.mkdir(parents=True, exist_ok=False)

        try:
            try:
                with catalog_gate(catalog_dir, exclusive=True):
                    assert_catalog_not_stopped(catalog_dir)

                    stores_dir = staging_dir / "stores"
                    stores_dir.mkdir()

                    # Snapshot Core
                    staged_core = stores_dir / "core.sqlite3"
                    snapshot_source, snapshot_role = core_db_path, "core"
                    self._snapshot_database(core_db_path, staged_core)

                    # Snapshot Context if paired
                    staged_context = None
                    if scope == BackupScope.PAIRED:
                        staged_context = stores_dir / "context.sqlite3"
                        snapshot_source, snapshot_role = context_db_path, "context"
                        self._snapshot_database(context_db_path, staged_context)

                    # Execute cut callback while lock is actively held, if provided
                    if snapshot_cut_callback is not None:
                        snapshot_cut_callback()
            except sqlite3.Error as e:
                self._diagnose_and_stop_if_source_corrupt(
                    catalog_dir, snapshot_source, snapshot_role, e
                )
                raise BackupValidationError(str(e)) from e

            # Deep Domain and Retained-Byte Validation outside writer lock
            try:
                core_summary = self._validate_and_summarize_core(staged_core)
            except RefObservationBackupUnsupported:
                # Unsupported I1 integration is not evidence of corruption.
                raise
            except (BackupValidationError, sqlite3.Error) as e:
                self._diagnose_and_stop_if_source_corrupt(
                    catalog_dir, core_db_path, "core", e
                )
                raise BackupValidationError(str(e)) from e

            context_summary = RetainedByteSummary()
            if staged_context:
                try:
                    context_summary = self._validate_and_summarize_context(
                        staged_context
                    )
                except (BackupValidationError, sqlite3.Error) as e:
                    self._diagnose_and_stop_if_source_corrupt(
                        catalog_dir, context_db_path, "context", e
                    )
                    raise BackupValidationError(str(e)) from e

            total_summary = RetainedByteSummary(
                commit_count=core_summary.commit_count,
                tree_count=core_summary.tree_count,
                tag_count=core_summary.tag_count,
                notes_body_count=core_summary.notes_body_count,
                total_retained_bytes=core_summary.total_retained_bytes
                + context_summary.total_retained_bytes,
            )

            # Extract repository and catalog instance identity
            repo_uuid, inst_uuid = self._extract_identities(staged_core, "core")

            if staged_context:
                ctx_repo_uuid, ctx_inst_uuid = self._extract_identities(
                    staged_context, "context"
                )
                if repo_uuid != ctx_repo_uuid or inst_uuid != ctx_inst_uuid:
                    self._diagnose_and_stop_if_source_corrupt(
                        catalog_dir,
                        core_db_path,
                        "pair",
                        BackupValidationError("Staged paired store identity mismatch"),
                    )
                    raise BackupValidationError(
                        f"Paired store identity mismatch: Core ({repo_uuid}, {inst_uuid}) vs Context ({ctx_repo_uuid}, {ctx_inst_uuid})"
                    )

            # Clean up any transient -wal or -shm sidecars created during read-only validation
            for sidecar in stores_dir.glob("*.sqlite3-*"):
                sidecar.unlink()

            # Build StoreManifests
            core_sha = _sha256_file(staged_core)
            stores_map = {
                "core": StoreManifest(
                    path="stores/core.sqlite3",
                    bytes=staged_core.stat().st_size,
                    sha256=core_sha,
                    schema_fingerprint=self._compute_schema_fingerprint(
                        staged_core, "core"
                    ),
                )
            }

            if staged_context:
                ctx_sha = _sha256_file(staged_context)
                stores_map["context"] = StoreManifest(
                    path="stores/context.sqlite3",
                    bytes=staged_context.stat().st_size,
                    sha256=ctx_sha,
                    schema_fingerprint=self._compute_schema_fingerprint(
                        staged_context, "context"
                    ),
                )

            # Compute overall SHA-256 of payload files in deterministic sorted store order
            overall_hasher = hashlib.sha256()
            for name in sorted(stores_map.keys()):
                overall_hasher.update(stores_map[name].sha256.encode("ascii"))
            overall_sha256 = overall_hasher.hexdigest()

            manifest = BackupManifest(
                manifest_version=1,
                backup_id=backup_id,
                created_at_us=created_at_us,
                repository_uuidv4=repo_uuid,
                catalog_instance_uuidv4=inst_uuid,
                scope=scope,
                stores=stores_map,
                retained_byte_summary=total_summary,
                overall_sha256=overall_sha256,
            )

            # Write manifest.json and manifest.json.sha256
            manifest_path = staging_dir / "manifest.json"
            manifest_json = json.dumps(
                {
                    "manifest_version": manifest.manifest_version,
                    "backup_id": manifest.backup_id,
                    "created_at_us": manifest.created_at_us,
                    "repository_uuidv4": manifest.repository_uuidv4,
                    "catalog_instance_uuidv4": manifest.catalog_instance_uuidv4,
                    "scope": manifest.scope.value,
                    "excluded_stores": ["access", "operational", "search"],
                    "restoration_scope": "Git history/structure/notes and declared Context; no saved access configuration or repository file checkout",
                    "stores": {
                        k: {
                            "path": v.path,
                            "bytes": v.bytes,
                            "sha256": v.sha256,
                            "schema_fingerprint": v.schema_fingerprint,
                        }
                        for k, v in manifest.stores.items()
                    },
                    "retained_byte_summary": {
                        "commit_count": total_summary.commit_count,
                        "tree_count": total_summary.tree_count,
                        "tag_count": total_summary.tag_count,
                        "notes_body_count": total_summary.notes_body_count,
                        "total_retained_bytes": total_summary.total_retained_bytes,
                    },
                    "overall_sha256": manifest.overall_sha256,
                },
                indent=2,
            )
            manifest_path.write_text(manifest_json + "\n", encoding="utf-8")
            _fsync_file(manifest_path)

            manifest_sha_path = staging_dir / "manifest.json.sha256"
            manifest_sha_path.write_text(
                _sha256_file(manifest_path) + "  manifest.json\n", encoding="utf-8"
            )
            _fsync_file(manifest_sha_path)

            _fsync_dir(stores_dir)
            _fsync_dir(staging_dir)

            # Atomic publication with no-overwrite primitive under catalog completion fence
            try:
                with catalog_completion(catalog_dir):
                    assert_catalog_not_stopped(catalog_dir)
                    _atomic_publish_noreplace(staging_dir, destination_path)
            except CoordinationError as ce:
                raise CatalogStoppedError(
                    f"Catalog at {catalog_dir} entered recovery stop; normal backup publication prevented: {ce}"
                ) from ce

            return BackupReceipt(
                backup_id=backup_id,
                backup_path=str(destination_path),
                scope=scope,
                manifest=manifest,
                overall_sha256=overall_sha256,
                verified_retained_bytes=total_summary.total_retained_bytes,
                verified_clean=True,
            )
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

    def _diagnose_and_stop_if_source_corrupt(
        self,
        catalog_dir: Path,
        source_db_path: Path,
        store_role: str,
        staging_error: Exception,
    ) -> None:
        """Distinguish confirmed authoritative source corruption from staging-only copy defects.

        Under ADR 0026: if authoritative source exhibits integrity, schema or retained-data
        corruption, immediately persist catalog recovery stop and fence ordinary operations.
        If source is sound (staging copy defect only), do not stop healthy authoritative catalog.
        """
        if store_role not in ("core", "context", "pair"):
            raise ValueError("unknown authoritative store role")
        with catalog_gate(catalog_dir, exclusive=True):
            assert_catalog_not_stopped(catalog_dir)
            try:
                # Opening even read-only SQLite on the suspect source can create
                # WAL/SHM sidecars. Validate a bounded coherent forensic copy;
                # the cooperating writer cut covers the complete evidence set.
                with tempfile.TemporaryDirectory(prefix="p7-diagnosis-") as temporary:
                    evidence = Path(temporary)
                    _copy_forensic_files(
                        catalog_dir, evidence, RecoveryBudget().max_input_bytes
                    )
                    if store_role == "core":
                        self._validate_and_summarize_core(
                            evidence / source_db_path.name
                        )
                    elif store_role == "context":
                        self._validate_and_summarize_context(
                            evidence / source_db_path.name
                        )
                    else:
                        core_identity = self._extract_identities(
                            evidence / "core.sqlite3", "core"
                        )
                        context_identity = self._extract_identities(
                            evidence / "context.sqlite3", "context"
                        )
                        if core_identity != context_identity:
                            raise BackupValidationError(
                                f"Source paired store identity mismatch: {core_identity} vs {context_identity}"
                            )
            except Exception as source_error:
                category = _confirmed_integrity_failure(source_error)
                if category is None:
                    raise SourceIntegrityIndeterminateError(
                        f"Indeterminate {store_role} source integrity; validation unavailable: {source_error}"
                    ) from source_error
                # Persist the fence before releasing the protected writer cut.
                # A diagnostic write to the suspect database is never required.
                reason = f"Confirmed authoritative {store_role} corruption ({category}): {source_error}"
                stop_catalog(
                    catalog_dir,
                    reason,
                    details={
                        "store": store_role,
                        "classification": category,
                        "staging_error": str(staging_error),
                        "source_error": str(source_error),
                    },
                )
                raise CorruptionDetectedError(reason) from source_error

    def _snapshot_database(self, source_path: Path, target_path: Path) -> None:
        source_uri = f"file:{source_path.resolve()}?mode=ro"
        src_conn = sqlite3.connect(source_uri, uri=True, timeout=1.0)
        try:
            register_functions(src_conn)
            dst_conn = sqlite3.connect(str(target_path))
            try:
                deadline = time.monotonic() + 1.0

                def bounded_progress(status, remaining, total):
                    if (
                        status in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
                        and time.monotonic() >= deadline
                    ):
                        raise sqlite3.OperationalError(
                            "SQLite backup lock wait exceeded finite deadline"
                        )

                # Connection timeout alone does not bound backup() BUSY retries.
                src_conn.backup(
                    dst_conn, pages=128, progress=bounded_progress, sleep=0.01
                )
                dst_conn.execute("PRAGMA journal_mode=DELETE")
            finally:
                dst_conn.close()
        finally:
            src_conn.close()
        _fsync_file(target_path)

    def _extract_identities(
        self, db_path: Path, store: str = "core"
    ) -> tuple[str, str]:
        conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
        try:
            register_functions(conn)
            row = conn.execute(
                "SELECT repository_uuidv4, catalog_instance_uuidv4 FROM store_identity WHERE store_role=?",
                (store,),
            ).fetchone()
            if row:
                repo_id, inst_id = str(row[0]), str(row[1])
                if not uuid4(repo_id) or not uuid4(inst_id):
                    raise BackupValidationError(
                        f"{store} store_identity UUID is not valid canonical UUIDv4"
                    )
                return repo_id, inst_id
            raise BackupValidationError(
                f"{store} store_identity missing or wrong role; cannot extract authoritative identity"
            )
        finally:
            conn.close()

    def _compute_schema_fingerprint(self, db_path: Path, store: str) -> str:
        conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
        try:
            register_functions(conn)
            try:
                from repo_catalog.adapters.sqlite.p1_schema import configure

                configure(conn)
                p1_schema_validate(conn, store)
            except Exception as e:
                raise BackupValidationError(
                    f"Physical schema validation failed for {store}: {e}"
                ) from e
            if schema_rows(conn) != expected_schema(store):
                raise BackupValidationError(
                    f"Physical schema for {store} differs from authoritative target schema"
                )
            return p1_schema_fingerprint(store)
        finally:
            conn.close()

    def _validate_and_summarize_core(self, core_db: Path) -> RetainedByteSummary:
        conn = sqlite3.connect(f"file:{core_db.resolve()}?mode=ro", uri=True)
        try:
            register_functions(conn)
            # Strict P1 schema validation
            try:
                from repo_catalog.adapters.sqlite.p1_schema import configure

                configure(conn)
                p1_schema_validate(conn, "core")
            except Exception as e:
                raise BackupValidationError(f"Core physical schema invalid: {e}") from e
            if schema_rows(conn) != expected_schema("core"):
                raise BackupValidationError(
                    "Core physical schema rows differ from packaged expectation"
                )

            validate_stored_text_encoding(conn, "core")
            validate_stored_checks(conn, "core", retained_bytes=False)

            # PRAGMA integrity_check
            result = conn.execute("PRAGMA integrity_check").fetchall()
            if not result or result[0][0] != "ok":
                raise BackupValidationError(
                    f"Core database integrity check failed: {result}"
                )
            fk_result = conn.execute("PRAGMA foreign_key_check").fetchall()
            if fk_result:
                raise BackupValidationError(
                    f"Core foreign key check failed: {fk_result}"
                )

            # Verify store_identity
            identity_row = conn.execute(
                "SELECT repository_uuidv4, catalog_instance_uuidv4 FROM store_identity WHERE store_role='core'"
            ).fetchone()
            if not identity_row:
                raise BackupValidationError("Core store_identity missing or wrong role")
            repo_uuid, inst_uuid = str(identity_row[0]), str(identity_row[1])
            if not uuid4(repo_uuid) or not uuid4(inst_uuid):
                raise BackupValidationError(
                    "Core repository or catalog instance UUID is not valid UUIDv4"
                )

            total_bytes = 0
            commits = 0
            trees = 0
            tags = 0
            notes = 0

            # 1. Inspect retained_metadata: commits, trees, tags
            cursor = conn.execute(
                "SELECT object_format, full_oid, physical_copy_uuidv4, native_type, body, size, digest_sha256 FROM retained_metadata"
            )
            while row := cursor.fetchone():
                (
                    obj_fmt,
                    full_oid,
                    copy_uuid,
                    ntype,
                    body,
                    size,
                    digest_sha,
                ) = row
                if not uuid4(str(copy_uuid)):
                    raise BackupValidationError(
                        f"Invalid physical copy UUIDv4 in retained_metadata for {full_oid}"
                    )
                if not oid(obj_fmt, full_oid):
                    raise BackupValidationError(
                        f"Invalid native OID format in retained_metadata: {full_oid}"
                    )
                if len(body) != size:
                    raise BackupValidationError(
                        f"Size mismatch in retained_metadata for {full_oid}: expected {size}, got {len(body)}"
                    )
                actual_digest = hashlib.sha256(body).hexdigest()
                if actual_digest != digest_sha:
                    raise BackupValidationError(
                        f"SHA-256 digest mismatch in retained_metadata for {full_oid}: expected {digest_sha}, got {actual_digest}"
                    )
                expected_oid = native_oid(obj_fmt, ntype, body)
                if expected_oid != full_oid:
                    raise BackupValidationError(
                        f"Native OID calculation mismatch in retained_metadata for {full_oid}: expected {expected_oid}"
                    )
                if ntype not in ("commit", "tree", "tag"):
                    raise BackupValidationError(
                        f"Unsupported native_type in retained_metadata: {ntype}"
                    )
                # Verify native grammar
                try:
                    parse_metadata(obj_fmt, ntype, body)
                except Exception as e:
                    raise BackupValidationError(
                        f"Native git {ntype} grammar validation failed for {full_oid}: {e}"
                    ) from e

                total_bytes += len(body)
                if ntype == "commit":
                    commits += 1
                elif ntype == "tree":
                    trees += 1
                elif ntype == "tag":
                    tags += 1

            # 2. Inspect retained_notes: verified notes blob bodies and role proofs
            cursor = conn.execute(
                "SELECT object_format, full_oid, physical_copy_uuidv4, body, size, digest_sha256, capture_origin_uuidv4, capture_uuidv4, root, target, path, proof_bundle FROM retained_notes"
            )
            while row := cursor.fetchone():
                (
                    obj_fmt,
                    full_oid,
                    copy_uuid,
                    body,
                    size,
                    digest_sha,
                    cap_origin,
                    cap_id,
                    root,
                    target,
                    path,
                    proof_bundle,
                ) = row
                if not uuid4(str(copy_uuid)):
                    raise BackupValidationError(
                        f"Invalid physical copy UUIDv4 in retained_notes for {full_oid}"
                    )
                if not uuid4(str(cap_origin)) or not uuid4(str(cap_id)):
                    raise BackupValidationError(
                        f"Invalid capture UUIDv4 pair in retained_notes for {full_oid}"
                    )
                if (
                    not oid(obj_fmt, full_oid)
                    or not oid(obj_fmt, root)
                    or not oid(obj_fmt, target)
                ):
                    raise BackupValidationError(
                        f"Invalid OID in retained_notes for {full_oid}"
                    )
                if len(body) != size:
                    raise BackupValidationError(
                        f"Size mismatch in retained_notes for {full_oid}: expected {size}, got {len(body)}"
                    )
                actual_digest = hashlib.sha256(body).hexdigest()
                if actual_digest != digest_sha:
                    raise BackupValidationError(
                        f"SHA-256 digest mismatch in retained_notes for {full_oid}: expected {digest_sha}, got {actual_digest}"
                    )
                expected_oid = native_oid(obj_fmt, "blob", body)
                if expected_oid != full_oid:
                    raise BackupValidationError(
                        f"Native OID calculation mismatch in retained_notes for {full_oid}: expected {expected_oid}"
                    )

                # Full structural role verification under ADR 0022
                if not valid_note_role(
                    obj_fmt, root, target, full_oid, path, proof_bundle
                ):
                    raise BackupValidationError(
                        f"Retained note {full_oid} failed structural role receiver verification (ADR 0022)"
                    )

                # Verify corresponding note_roles entry exists
                role_check = conn.execute(
                    "SELECT 1 FROM note_roles WHERE capture_origin_uuidv4=? AND capture_uuidv4=? AND object_format=? AND root=? AND target=? AND note=? AND path=? AND proof_bundle=?",
                    (
                        cap_origin,
                        cap_id,
                        obj_fmt,
                        root,
                        target,
                        full_oid,
                        path,
                        proof_bundle,
                    ),
                ).fetchone()
                if not role_check:
                    raise BackupValidationError(
                        f"Retained note {full_oid} lacks valid corresponding role proof in note_roles"
                    )

                notes += 1
                total_bytes += len(body)

            validate_stored_checks(conn, "core", retained_bytes=True)
            validate_stored_admission_guards(conn, "core")

            # The existing manifest's retained-body accounting does not include
            # the I1 ref-observation family. Never certify an incomplete backup.
            for table in _REF_OBSERVATION_TABLES:
                if conn.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone():
                    raise RefObservationBackupUnsupported(
                        "RefObservation backup/restore requires the I3 manifest integration"
                    )

            return RetainedByteSummary(
                commit_count=commits,
                tree_count=trees,
                tag_count=tags,
                notes_body_count=notes,
                total_retained_bytes=total_bytes,
            )
        except sqlite3.Error as e:
            raise BackupValidationError(f"Core database error: {e}") from e
        finally:
            conn.close()

    def _validate_and_summarize_context(self, context_db: Path) -> RetainedByteSummary:
        conn = sqlite3.connect(f"file:{context_db.resolve()}?mode=ro", uri=True)
        try:
            register_functions(conn)
            # Strict P1 schema validation
            try:
                from repo_catalog.adapters.sqlite.p1_schema import configure

                configure(conn)
                p1_schema_validate(conn, "context")
            except Exception as e:
                raise BackupValidationError(
                    f"Context physical schema invalid: {e}"
                ) from e
            if schema_rows(conn) != expected_schema("context"):
                raise BackupValidationError(
                    "Context physical schema rows differ from packaged expectation"
                )

            validate_stored_text_encoding(conn, "context")
            validate_stored_checks(conn, "context", retained_bytes=False)
            validate_stored_admission_guards(conn, "context")

            result = conn.execute("PRAGMA integrity_check").fetchall()
            if not result or result[0][0] != "ok":
                raise BackupValidationError(
                    f"Context database integrity check failed: {result}"
                )
            fk_result = conn.execute("PRAGMA foreign_key_check").fetchall()
            if fk_result:
                raise BackupValidationError(
                    f"Context foreign key check failed: {fk_result}"
                )

            identity_row = conn.execute(
                "SELECT repository_uuidv4, catalog_instance_uuidv4 FROM store_identity WHERE store_role='context'"
            ).fetchone()
            if not identity_row:
                raise BackupValidationError(
                    "Context store_identity missing or wrong role"
                )
            repo_uuid, inst_uuid = str(identity_row[0]), str(identity_row[1])
            if not uuid4(repo_uuid) or not uuid4(inst_uuid):
                raise BackupValidationError(
                    "Context repository or catalog instance UUID is not valid UUIDv4"
                )

            total_bytes = 0
            cursor = conn.execute("SELECT sha256, text_value FROM text_bodies")
            while row := cursor.fetchone():
                expected_sha, text_value = row
                if not isinstance(text_value, str):
                    raise BackupValidationError("Context text body must be a string")
                actual_sha = hashlib.sha256(text_value.encode("utf-8")).hexdigest()
                if actual_sha != expected_sha:
                    raise BackupValidationError(
                        f"Context text body SHA-256 mismatch: recorded {expected_sha}, actual {actual_sha}"
                    )
                total_bytes += len(text_value.encode("utf-8"))

            validate_stored_checks(conn, "context", retained_bytes=True)

            return RetainedByteSummary(total_retained_bytes=total_bytes)
        except sqlite3.Error as e:
            raise BackupValidationError(f"Context database error: {e}") from e
        finally:
            conn.close()

    def extract_salvage(
        self,
        catalog_dir: Path,
        output_file: Path,
        max_records: int | None = None,
        max_bytes: int | None = None,
        budget: RecoveryBudget | None = None,
    ) -> SalvageReceipt:
        catalog_dir = Path(catalog_dir)
        output_file = Path(output_file)
        if output_file.resolve().is_relative_to(catalog_dir.resolve()):
            raise SalvageError(
                "Salvage output must be outside preserved source catalog"
            )

        b = budget or RecoveryBudget()
        limit_records = max_records if max_records is not None else b.max_input_records
        limit_bytes = max_bytes if max_bytes is not None else b.max_input_bytes
        max_payload_bytes = b.max_payload_bytes

        output_file.parent.mkdir(parents=True, exist_ok=True)
        unreadable: list[str] = []
        clean = 0
        partial = 0
        corrupt = 0
        total_records = 0
        total_bytes = 0
        is_partial = False

        if type(limit_records) is not int or limit_records <= 0:
            raise ValueError("max_records must be a positive integer")
        if type(limit_bytes) is not int or limit_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")
        limit_records = min(limit_records, b.max_input_records)
        limit_bytes = min(limit_bytes, b.max_input_bytes)

        # Forensic preservation: create isolated working copy of suspect files
        # Drain writers that began before stop, then fence both writer and stop
        # transitions throughout the cut. Acquiring writer first avoids lock
        # inversion with a writer that must persist an immediate corruption stop.
        with (
            catalog_gate(catalog_dir, exclusive=True),
            _file_gate(catalog_dir / "p1-stop-fence.lock", exclusive=False),
        ):
            with tempfile.TemporaryDirectory() as forensic_tmp:
                forensic_dir = Path(forensic_tmp)
                _copy_forensic_files(catalog_dir, forensic_dir, limit_bytes)

                temp_out = (
                    output_file.parent / f"{output_file.name}.tmp.{uuid.uuid4().hex}"
                )
                with temp_out.open("w", encoding="utf-8") as out_f:
                    core_db = forensic_dir / "core.sqlite3"
                    if core_db.exists():
                        (
                            c_cnt,
                            c_bytes,
                            c_unread,
                            c_cl,
                            c_pt,
                            c_cr,
                            c_stopped,
                        ) = self._salvage_store_stream(
                            core_db,
                            "core",
                            out_f,
                            max_records=limit_records,
                            max_bytes=limit_bytes,
                            max_payload_bytes=max_payload_bytes,
                            records_offset=total_records,
                            bytes_offset=total_bytes,
                        )
                        total_records += c_cnt
                        total_bytes += c_bytes
                        unreadable.extend(c_unread)
                        clean += c_cl
                        partial += c_pt
                        corrupt += c_cr
                        if c_stopped:
                            is_partial = True

                    else:
                        unreadable.append(
                            "core:missing source database; enumeration unknown"
                        )
                        is_partial = True

                    ctx_db = forensic_dir / "context.sqlite3"
                    if ctx_db.exists() and not is_partial:
                        rem_records = limit_records - total_records
                        rem_bytes = limit_bytes - total_bytes
                        if rem_records > 0 and rem_bytes > 0:
                            (
                                cx_cnt,
                                cx_bytes,
                                cx_unread,
                                cx_cl,
                                cx_pt,
                                cx_cr,
                                cx_stopped,
                            ) = self._salvage_store_stream(
                                ctx_db,
                                "context",
                                out_f,
                                max_records=limit_records,
                                max_bytes=limit_bytes,
                                max_payload_bytes=max_payload_bytes,
                                records_offset=total_records,
                                bytes_offset=total_bytes,
                            )
                            total_records += cx_cnt
                            total_bytes += cx_bytes
                            unreadable.extend(cx_unread)
                            clean += cx_cl
                            partial += cx_pt
                            corrupt += cx_cr
                            if cx_stopped:
                                is_partial = True

                _fsync_file(temp_out)
                os.replace(temp_out, output_file)
                _fsync_dir(output_file.parent)

        if partial > 0 or corrupt > 0 or len(unreadable) > 0:
            is_partial = True

        return SalvageReceipt(
            catalog_path=str(catalog_dir),
            candidate_count=total_records,
            clean_count=clean,
            partial_count=partial,
            corrupt_count=corrupt,
            unreadable_scope=unreadable,
            output_file=str(output_file),
            partial=is_partial,
        )

    def _salvage_store_stream(
        self,
        db_path: Path,
        store_name: str,
        out_f,
        max_records: int,
        max_bytes: int,
        max_payload_bytes: int,
        records_offset: int,
        bytes_offset: int,
    ) -> tuple[int, int, list[str], int, int, int, bool]:
        unreadable: list[str] = []
        clean = 0
        partial = 0
        corrupt = 0
        written_records = 0
        written_bytes = 0
        stopped_due_to_limits = False

        conn = None
        try:
            try:
                conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
                register_functions(conn)
                conn.setlimit(
                    sqlite3.SQLITE_LIMIT_LENGTH, max(65536, max_payload_bytes * 4)
                )
                conn.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 512)
                conn.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 256 * 1024)
                vm_work = [0]

                def progress():
                    vm_work[0] += 1000
                    return int(vm_work[0] > max(10000, max_bytes * 4))

                conn.set_progress_handler(progress, 1000)
                tables = [
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT ?",
                        (max_records + 1,),
                    ).fetchall()
                ]
            except Exception as e:
                unreadable.append(
                    f"{store_name}:sqlite_schema (enumeration incomplete: {e})"
                )
                confirmed = int(
                    isinstance(e, sqlite3.DatabaseError)
                    and getattr(e, "sqlite_errorcode", None)
                    in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB)
                )
                return 0, 0, unreadable, 0, 0, confirmed, False

            if len(tables) > max_records:
                tables = tables[:max_records]
                stopped_due_to_limits = True
            for table in tables:
                if (records_offset + written_records) >= max_records:
                    stopped_due_to_limits = True
                    break
                if (bytes_offset + written_bytes) >= max_bytes:
                    stopped_due_to_limits = True
                    break

                try:
                    quoted_table = '"' + table.replace('"', '""') + '"'
                    columns = [
                        r[1]
                        for r in conn.execute(
                            f"PRAGMA table_info({quoted_table})"
                        ).fetchall()
                    ]
                    if not columns or len(columns) > 512:
                        raise ValueError("Unsupported or excessive source column count")
                    quoted_columns = ['"' + c.replace('"', '""') + '"' for c in columns]
                    # The predicate executes inside SQLite, before Python receives
                    # any cell. A huge row becomes one explicit partial candidate.
                    row_size = " + ".join(
                        f"coalesce(length(CAST({c} AS BLOB)), 0)"
                        for c in quoted_columns
                    )
                    projection = ", ".join(
                        f"CASE WHEN ({row_size}) > {max_payload_bytes} THEN NULL ELSE {c} END AS {c}"
                        for c in quoted_columns
                    )
                    cursor = conn.execute(
                        f"SELECT {projection}, ({row_size}) AS __recovery_row_bytes FROM {quoted_table}"
                    )
                    columns = [d[0] for d in cursor.description]

                    while row := cursor.fetchone():
                        if (records_offset + written_records) >= max_records:
                            stopped_due_to_limits = True
                            break
                        if (bytes_offset + written_bytes) >= max_bytes:
                            stopped_due_to_limits = True
                            break

                        row_dict = dict(zip(columns, row))
                        row_bytes = row_dict.pop("__recovery_row_bytes")
                        if row_bytes > max_payload_bytes:
                            cand_record = {
                                "candidate_id": f"{store_name}:{table}:{written_records}",
                                "candidate_type": CandidateType.CONTEXT_RESOURCE.value
                                if store_name == "context"
                                else CandidateType.GIT_METADATA.value,
                                "extraction_provenance": {
                                    "store": store_name,
                                    "table": table,
                                },
                                "payload": {},
                                "provenance": None,
                                "extraction_status": ExtractionStatus.PARTIAL.value,
                                "error": f"Source row size {row_bytes} exceeds finite payload limit {max_payload_bytes}",
                            }
                            line = json.dumps(cand_record) + "\n"
                            line_bytes = len(line.encode("utf-8"))
                            if bytes_offset + written_bytes + line_bytes > max_bytes:
                                stopped_due_to_limits = True
                                break
                            out_f.write(line)
                            written_records += 1
                            written_bytes += line_bytes
                            partial += 1
                            continue

                        if store_name == "core" and table in _REF_OBSERVATION_TABLES:
                            # Until I3 supplies typed recovery, explicitly report
                            # the unsupported candidate and never stage its body
                            # or structural proof as generic Git metadata.
                            cand_record = {
                                "candidate_id": f"{store_name}:{table}:{written_records}",
                                "candidate_type": CandidateType.GIT_METADATA.value,
                                "extraction_provenance": {
                                    "store": store_name,
                                    "table": table,
                                },
                                "payload": {},
                                "provenance": None,
                                "extraction_status": ExtractionStatus.PARTIAL.value,
                                "error": "RefObservation salvage requires I3 typed recovery integration",
                            }
                            line = json.dumps(cand_record) + "\n"
                            line_bytes = len(line.encode("utf-8"))
                            if bytes_offset + written_bytes + line_bytes > max_bytes:
                                stopped_due_to_limits = True
                                break
                            out_f.write(line)
                            written_records += 1
                            written_bytes += line_bytes
                            partial += 1
                            continue

                        # Classify candidate and format payload preserving exact bytes
                        c_type = CandidateType.GIT_METADATA
                        c_id = ""
                        payload: dict = {}
                        cap_origin = None
                        cap_id = None
                        orig_provenance = None
                        extraction_prov = {"store": store_name, "table": table}

                        if store_name == "core" and table == "retained_metadata":
                            c_type = CandidateType.RETAINED_BODY
                            c_id = f"{row_dict.get('object_format')}:{row_dict.get('full_oid')}:{row_dict.get('physical_copy_uuidv4')}"
                            raw_body = row_dict.get("body")
                            body_len = (
                                row_dict.get("size")
                                if row_dict.get("size") is not None
                                else (
                                    len(raw_body) if isinstance(raw_body, bytes) else 0
                                )
                            )
                            if raw_body is None and body_len > max_payload_bytes:
                                cand_record = {
                                    "candidate_id": c_id,
                                    "candidate_type": c_type.value,
                                    "capture_origin_uuidv4": None,
                                    "capture_uuidv4": None,
                                    "extraction_provenance": extraction_prov,
                                    "payload": {
                                        "object_format": row_dict.get("object_format"),
                                        "full_oid": row_dict.get("full_oid"),
                                        "size": row_dict.get("size"),
                                    },
                                    "extraction_status": ExtractionStatus.PARTIAL.value,
                                    "error": f"Payload size {body_len} exceeds limit {max_payload_bytes}",
                                }
                                line = json.dumps(cand_record) + "\n"
                                out_f.write(line)
                                written_records += 1
                                written_bytes += len(line.encode("utf-8"))
                                partial += 1
                                continue

                            payload = {
                                "object_format": row_dict.get("object_format"),
                                "full_oid": row_dict.get("full_oid"),
                                "physical_copy_uuidv4": row_dict.get(
                                    "physical_copy_uuidv4"
                                ),
                                "native_type": row_dict.get("native_type"),
                                "size": row_dict.get("size"),
                                "digest_sha256": row_dict.get("digest_sha256"),
                                "body_base64": base64.b64encode(raw_body).decode(
                                    "ascii"
                                )
                                if isinstance(raw_body, bytes)
                                else None,
                            }
                        elif store_name == "core" and table == "retained_notes":
                            c_type = CandidateType.NOTES_MAPPING
                            c_id = f"{row_dict.get('object_format')}:{row_dict.get('full_oid')}:{row_dict.get('physical_copy_uuidv4')}"
                            cap_origin = (
                                str(row_dict.get("capture_origin_uuidv4"))
                                if row_dict.get("capture_origin_uuidv4")
                                else None
                            )
                            cap_id = (
                                str(row_dict.get("capture_uuidv4"))
                                if row_dict.get("capture_uuidv4")
                                else None
                            )
                            raw_body = row_dict.get("body")
                            body_len = (
                                row_dict.get("size")
                                if row_dict.get("size") is not None
                                else (
                                    len(raw_body) if isinstance(raw_body, bytes) else 0
                                )
                            )
                            if raw_body is None and body_len > max_payload_bytes:
                                cand_record = {
                                    "candidate_id": c_id,
                                    "candidate_type": c_type.value,
                                    "capture_origin_uuidv4": cap_origin,
                                    "capture_uuidv4": cap_id,
                                    "extraction_provenance": extraction_prov,
                                    "payload": {
                                        "object_format": row_dict.get("object_format"),
                                        "full_oid": row_dict.get("full_oid"),
                                        "size": row_dict.get("size"),
                                    },
                                    "extraction_status": ExtractionStatus.PARTIAL.value,
                                    "error": f"Notes body size {body_len} exceeds limit {max_payload_bytes}",
                                }
                                line = json.dumps(cand_record) + "\n"
                                out_f.write(line)
                                written_records += 1
                                written_bytes += len(line.encode("utf-8"))
                                partial += 1
                                continue

                            payload = {
                                "object_format": row_dict.get("object_format"),
                                "full_oid": row_dict.get("full_oid"),
                                "physical_copy_uuidv4": row_dict.get(
                                    "physical_copy_uuidv4"
                                ),
                                "native_type": "blob",
                                "size": row_dict.get("size"),
                                "digest_sha256": row_dict.get("digest_sha256"),
                                "capture_origin_uuidv4": cap_origin,
                                "capture_uuidv4": cap_id,
                                "root": row_dict.get("root"),
                                "target": row_dict.get("target"),
                                "path": row_dict.get("path"),
                                "proof_bundle": row_dict.get("proof_bundle"),
                                "body_base64": base64.b64encode(raw_body).decode(
                                    "ascii"
                                )
                                if isinstance(raw_body, bytes)
                                else None,
                            }
                            # Preserve original Capture source and nominated ref if present in captures table
                            try:
                                cap_row = conn.execute(
                                    "SELECT repository_uuidv4, source, ref FROM captures WHERE capture_origin_uuidv4=? AND capture_uuidv4=? AND object_format=? AND root=? AND length(CAST(repository_uuidv4 AS BLOB)) + length(CAST(source AS BLOB)) + length(CAST(ref AS BLOB)) <= ?",
                                    (
                                        cap_origin,
                                        cap_id,
                                        row_dict.get("object_format"),
                                        row_dict.get("root"),
                                        max_payload_bytes,
                                    ),
                                ).fetchone()
                                if cap_row:
                                    payload["repository_uuidv4"] = cap_row[0]
                                    payload["source"] = cap_row[1]
                                    payload["ref"] = _decode_native_ref(cap_row[2])
                            except Exception:
                                pass
                        elif store_name == "core" and table == "captures":
                            c_type = CandidateType.GIT_METADATA
                            c_id = f"{row_dict.get('capture_origin_uuidv4')}:{row_dict.get('capture_uuidv4')}"
                            cap_origin = (
                                str(row_dict.get("capture_origin_uuidv4"))
                                if row_dict.get("capture_origin_uuidv4")
                                else None
                            )
                            cap_id = (
                                str(row_dict.get("capture_uuidv4"))
                                if row_dict.get("capture_uuidv4")
                                else None
                            )
                            payload = dict(row_dict)
                        elif store_name == "context" and table == "text_bodies":
                            c_type = CandidateType.CONTEXT_DOCUMENT
                            c_id = str(row_dict.get("sha256"))
                            payload = {
                                "sha256": row_dict.get("sha256"),
                                "text_value": row_dict.get("text_value"),
                            }
                        else:
                            if store_name == "context":
                                c_type = CandidateType.CONTEXT_RESOURCE
                            else:
                                c_type = CandidateType.GIT_METADATA

                            c_id = str(uuid.uuid4())
                            if "capture_origin_uuidv4" in row_dict and row_dict.get(
                                "capture_origin_uuidv4"
                            ):
                                cap_origin = str(row_dict.get("capture_origin_uuidv4"))
                            if "capture_uuidv4" in row_dict and row_dict.get(
                                "capture_uuidv4"
                            ):
                                cap_id = str(row_dict.get("capture_uuidv4"))

                            # Extract original domain provenance if available
                            if "provenance_json" in row_dict and row_dict.get(
                                "provenance_json"
                            ):
                                try:
                                    orig_provenance = _bounded_json_loads(
                                        str(row_dict["provenance_json"]),
                                        RecoveryBudget(
                                            max_payload_bytes=max_payload_bytes
                                        ),
                                    )
                                except Exception:
                                    orig_provenance = {
                                        "raw": str(row_dict["provenance_json"])
                                    }
                            elif "provenance" in row_dict and row_dict.get(
                                "provenance"
                            ):
                                orig_provenance = {"value": row_dict["provenance"]}

                            for k, v in row_dict.items():
                                if isinstance(v, bytes):
                                    payload[f"{k}_base64"] = base64.b64encode(v).decode(
                                        "ascii"
                                    )
                                else:
                                    payload[k] = v

                        cand_record = {
                            "candidate_id": c_id,
                            "candidate_type": c_type.value,
                            "capture_origin_uuidv4": cap_origin,
                            "capture_uuidv4": cap_id,
                            "extraction_provenance": extraction_prov,
                            "provenance": orig_provenance,
                            "payload": payload,
                            "extraction_status": ExtractionStatus.CLEAN.value,
                            "error": None,
                        }

                        line = json.dumps(cand_record) + "\n"
                        line_bytes = len(line.encode("utf-8"))

                        if (bytes_offset + written_bytes + line_bytes) > max_bytes:
                            stopped_due_to_limits = True
                            break

                        out_f.write(line)
                        written_records += 1
                        written_bytes += line_bytes
                        clean += 1
                except Exception as e:
                    unreadable.append(
                        f"{store_name}:{table} (enumeration incomplete: {e})"
                    )
                    if isinstance(e, sqlite3.DatabaseError) and getattr(
                        e, "sqlite_errorcode", None
                    ) in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB):
                        corrupt += 1
        finally:
            if conn:
                conn.close()

        return (
            written_records,
            written_bytes,
            unreadable,
            clean,
            partial,
            corrupt,
            stopped_due_to_limits,
        )

    def restore_backup(
        self,
        backup_path: Path,
        destination_dir: Path,
        expected_repository_uuidv4: str,
    ) -> RestoreReceipt:
        backup_path = Path(backup_path)
        destination_dir = Path(destination_dir)

        if not backup_path.exists():
            raise RestoreValidationError(f"Backup path {backup_path} does not exist")

        # Keep source directory/file descriptors pinned until restore completes.
        # A normal backup contains standalone SQLite snapshots, never WAL/SHM.
        with ExitStack() as handles:
            try:
                backup_fd = _open_directory_nofollow(backup_path)
                handles.callback(os.close, backup_fd)
                if _bounded_directory_entries(backup_fd, 3) != {
                    "manifest.json",
                    "manifest.json.sha256",
                    "stores",
                }:
                    raise RestoreValidationError(
                        "Unexpected files in backup root directory"
                    )
                manifest_fd = _open_regular_at(backup_fd, "manifest.json")
                handles.callback(os.close, manifest_fd)
                digest_fd = _open_regular_at(backup_fd, "manifest.json.sha256")
                handles.callback(os.close, digest_fd)
                manifest_bytes = _read_bounded_fd(manifest_fd, 64 * 1024)
                digest_record = _read_bounded_fd(digest_fd, 128).decode("ascii")
                expected_manifest_sha = digest_record.strip().split()
                if (
                    len(expected_manifest_sha) != 2
                    or expected_manifest_sha[1] != "manifest.json"
                ):
                    raise RestoreValidationError("Invalid manifest SHA-256 record")
                if (
                    hashlib.sha256(manifest_bytes).hexdigest()
                    != expected_manifest_sha[0]
                ):
                    raise RestoreValidationError("Manifest SHA-256 mismatch")
                manifest_data = json.loads(manifest_bytes)
                _check_json_depth(manifest_data, max_depth=8, max_elements=128)
                if not isinstance(manifest_data, dict):
                    raise RestoreValidationError("Manifest must be an object")
            except (OSError, ValueError, UnicodeError, RecursionError) as error:
                raise RestoreValidationError(
                    f"Unsafe or unreadable manifest: {error}"
                ) from error

            if (
                type(manifest_data.get("manifest_version")) is not int
                or manifest_data.get("manifest_version") != 1
            ):
                raise RestoreValidationError(
                    f"Unsupported manifest version: {manifest_data.get('manifest_version')}"
                )

            scope_val = manifest_data.get("scope")
            if scope_val not in (BackupScope.GIT_ONLY.value, BackupScope.PAIRED.value):
                raise RestoreValidationError(f"Unsupported backup scope: {scope_val}")
            scope = BackupScope(scope_val)

            repo_uuid = manifest_data.get("repository_uuidv4")
            if repo_uuid != expected_repository_uuidv4:
                raise RestoreValidationError(
                    f"Repository UUID mismatch: expected {expected_repository_uuidv4}, got {repo_uuid}"
                )

            manifest_inst_uuid = manifest_data.get("catalog_instance_uuidv4")
            if not manifest_inst_uuid or not uuid4(str(manifest_inst_uuid)):
                raise RestoreValidationError(
                    f"Invalid or missing catalog_instance_uuidv4 in manifest: {manifest_inst_uuid}"
                )

            stores = manifest_data.get("stores", {})
            if not isinstance(stores, dict):
                raise RestoreValidationError("Manifest stores must be an object")
            if not uuid4(str(manifest_data.get("backup_id", ""))):
                raise RestoreValidationError("Invalid backup identity")
            if not isinstance(manifest_data.get("retained_byte_summary"), dict):
                raise RestoreValidationError("Invalid retained byte summary")
            expected_store_names = (
                {"core"} if scope == BackupScope.GIT_ONLY else {"core", "context"}
            )
            if set(stores.keys()) != expected_store_names:
                raise RestoreValidationError(
                    f"Declared stores {set(stores.keys())} do not match expected scope {scope_val} stores {expected_store_names}"
                )

            store_fds = {}
            try:
                stores_fd = os.open(
                    "stores",
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=backup_fd,
                )
                handles.callback(os.close, stores_fd)
                if _bounded_directory_entries(stores_fd, len(stores)) != {
                    f"{name}.sqlite3" for name in stores
                }:
                    raise RestoreValidationError(
                        "Unexpected or undeclared files or WAL sidecars in stores directory"
                    )
                overall_hasher = hashlib.sha256()
                for name, info in sorted(stores.items()):
                    if isinstance(info, dict) and isinstance(info.get("path"), str):
                        relative = Path(info["path"])
                        if relative.is_absolute() or ".." in relative.parts:
                            raise RestoreValidationError(
                                "Path traversal detected in manifest store path"
                            )
                    if (
                        not isinstance(info, dict)
                        or info.get("path") != f"stores/{name}.sqlite3"
                    ):
                        raise RestoreValidationError(
                            "Invalid canonical store manifest path"
                        )
                    if type(info.get("bytes")) is not int or info["bytes"] < 0:
                        raise RestoreValidationError("Invalid store byte count")
                    for key in ("sha256", "schema_fingerprint"):
                        value = info.get(key)
                        if (
                            not isinstance(value, str)
                            or len(value) != 64
                            or any(c not in "0123456789abcdef" for c in value)
                        ):
                            raise RestoreValidationError(f"Invalid store {key}")
                    if info["schema_fingerprint"] != p1_schema_fingerprint(name):
                        raise RestoreValidationError("Unexpected P1 schema fingerprint")
                    fd = _open_regular_at(stores_fd, f"{name}.sqlite3")
                    handles.callback(os.close, fd)
                    store_fds[name] = fd
                    overall_hasher.update(info["sha256"].encode("ascii"))
            except OSError as error:
                raise RestoreValidationError(f"Unsafe backup store: {error}") from error

            # Verify overall checksum
            recomputed_overall_sha = overall_hasher.hexdigest()
            if recomputed_overall_sha != manifest_data.get("overall_sha256"):
                raise RestoreValidationError(
                    f"Overall backup SHA-256 mismatch: recorded {manifest_data.get('overall_sha256')}, recomputed {recomputed_overall_sha}"
                )

            if destination_dir.resolve().is_relative_to(backup_path.resolve()):
                raise RestoreValidationError(
                    "Restore destination aliases backup evidence"
                )
            if destination_dir.exists() or destination_dir.is_symlink():
                raise RestoreValidationError(
                    f"Destination directory {destination_dir} already exists; no-overwrite invariant requires fresh destination"
                )

            destination_fd = _open_directory_nofollow(
                destination_dir.parent, create=True
            )
            handles.callback(os.close, destination_fd)
            staging_name = f"{destination_dir.name}.tmp.{uuid.uuid4().hex}"
            os.mkdir(staging_name, mode=0o700, dir_fd=destination_fd)
            # All staged I/O remains rooted in the pinned Linux directory fd.
            staging_dir = Path(f"/proc/self/fd/{destination_fd}") / staging_name

            revalidated_stores = []
            try:
                # Copy stores
                dst_core = staging_dir / "core.sqlite3"
                _copy_verified_fd(
                    store_fds["core"],
                    dst_core,
                    stores["core"]["bytes"],
                    stores["core"]["sha256"],
                )
                revalidated_stores.append("core")

                dst_ctx = None
                if "context" in stores:
                    dst_ctx = staging_dir / "context.sqlite3"
                    _copy_verified_fd(
                        store_fds["context"],
                        dst_ctx,
                        stores["context"]["bytes"],
                        stores["context"]["sha256"],
                    )
                    revalidated_stores.append("context")

                # Deep domain revalidation on restored physical databases
                try:
                    core_summary = self._validate_and_summarize_core(dst_core)
                    context_summary = (
                        self._validate_and_summarize_context(dst_ctx)
                        if dst_ctx
                        else RetainedByteSummary()
                    )
                except BackupValidationError as e:
                    raise RestoreValidationError(
                        f"Restored database failed domain validation: {e}"
                    ) from e

                # Verify paired store identity consistency
                core_repo_uuid, core_inst_uuid = self._extract_identities(
                    dst_core, "core"
                )
                if core_repo_uuid != expected_repository_uuidv4:
                    raise RestoreValidationError(
                        f"Restored core repository UUID mismatch: expected {expected_repository_uuidv4}, got {core_repo_uuid}"
                    )
                if core_inst_uuid != manifest_inst_uuid:
                    raise RestoreValidationError(
                        f"Restored core catalog instance UUID mismatch: manifest {manifest_inst_uuid} vs actual {core_inst_uuid}"
                    )
                if dst_ctx:
                    ctx_repo_uuid, ctx_inst_uuid = self._extract_identities(
                        dst_ctx, "context"
                    )
                    if (
                        core_repo_uuid != ctx_repo_uuid
                        or core_inst_uuid != ctx_inst_uuid
                    ):
                        raise RestoreValidationError(
                            f"Paired store identity mismatch: Core ({core_repo_uuid}, {core_inst_uuid}) vs Context ({ctx_repo_uuid}, {ctx_inst_uuid})"
                        )

                total_retained = (
                    core_summary.total_retained_bytes
                    + context_summary.total_retained_bytes
                )

                # Reconcile restored retained byte summary against manifest
                manifest_summary = manifest_data.get("retained_byte_summary", {})
                if (
                    core_summary.commit_count != manifest_summary.get("commit_count")
                    or core_summary.tree_count != manifest_summary.get("tree_count")
                    or core_summary.tag_count != manifest_summary.get("tag_count")
                    or core_summary.notes_body_count
                    != manifest_summary.get("notes_body_count")
                    or total_retained != manifest_summary.get("total_retained_bytes")
                ):
                    raise RestoreValidationError(
                        f"Retained byte summary mismatch: manifest {manifest_summary} vs restored "
                        f"(commits={core_summary.commit_count}, trees={core_summary.tree_count}, "
                        f"tags={core_summary.tag_count}, notes={core_summary.notes_body_count}, "
                        f"total_bytes={total_retained})"
                    )

                _fsync_dir(staging_dir)

                # Atomic publication with no-overwrite primitive
                try:
                    _atomic_publish_noreplace(
                        staging_dir, destination_dir, parent_fd=destination_fd
                    )
                    named_parent = _open_directory_nofollow(destination_dir.parent)
                    try:
                        pinned = os.fstat(destination_fd)
                        named = os.fstat(named_parent)
                        if (pinned.st_dev, pinned.st_ino) != (
                            named.st_dev,
                            named.st_ino,
                        ):
                            raise RestoreValidationError(
                                "Destination parent changed; publication location uncertain"
                            )
                    finally:
                        os.close(named_parent)
                except BackupValidationError as e:
                    raise RestoreValidationError(str(e)) from e

                return RestoreReceipt(
                    backup_id=manifest_data["backup_id"],
                    destination_path=str(destination_dir),
                    scope=scope,
                    revalidated_stores=revalidated_stores,
                    revalidated_retained_bytes=total_retained,
                    revalidated_clean=True,
                )
            finally:
                if staging_dir.exists():
                    shutil.rmtree(staging_dir, ignore_errors=True)

    def _verify_existing_retained_copy(self, directory, table, key, budget, work):
        """Boundedly check one existing physical copy, never a whole catalog.

        Immutable Core rows cannot change under supported writers after this
        writer cut. Only positive stored native/role failures publish a stop;
        resource refusals and environmental read failures do not prove damage.
        """
        with catalog_gate(directory, exclusive=True):
            assert_catalog_not_stopped(directory)
            conn = p1_connect(directory / "core.sqlite3", "core")
            try:
                conn.execute("BEGIN")
                work.require("metadata_units", 1)
                if table == "retained_metadata":
                    size_row = conn.execute(
                        "SELECT length(body) FROM retained_metadata WHERE object_format=? AND full_oid=? AND physical_copy_uuidv4=?",
                        key,
                    ).fetchone()
                else:
                    size_row = conn.execute(
                        "SELECT length(body),length(CAST(proof_bundle AS BLOB)),length(CAST(path AS BLOB)) FROM retained_notes WHERE object_format=? AND full_oid=? AND physical_copy_uuidv4=?",
                        key,
                    ).fetchone()
                work.charge("metadata_units", 1)
                if size_row is None:
                    if table == "retained_metadata":
                        for dependency in ("intrinsic_claims", "intrinsic_groups"):
                            if bounded_domain_exists(
                                conn,
                                f"SELECT 1 FROM {dependency} WHERE object_format=? AND full_oid=? AND physical_copy_uuidv4=? LIMIT 1",
                                key,
                                work,
                                "required_retained_metadata",
                            ):
                                reason = "Confirmed destination Core corruption: required retained metadata copy is missing"
                                stop_catalog(
                                    directory,
                                    reason,
                                    details={
                                        "store": "core",
                                        "classification": "authoritative_data",
                                    },
                                )
                                raise CorruptionDetectedError(reason)
                    return False
                if any(
                    size > budget.max_payload_bytes * (2 if index == 1 else 1)
                    for index, size in enumerate(size_row)
                ):
                    raise CoreFailure(
                        "BUDGET",
                        key,
                        "existing retained copy exceeds finite payload limit",
                    )
                work.require("input_bytes", sum(size_row))
                if table == "retained_metadata":
                    row = conn.execute(
                        "SELECT CASE WHEN length(native_type)<=6 THEN native_type END,body,size,CASE WHEN length(digest_sha256)=64 THEN digest_sha256 END FROM retained_metadata WHERE object_format=? AND full_oid=? AND physical_copy_uuidv4=?",
                        key,
                    ).fetchone()
                    native_type, body, size, digest = row
                else:
                    row = conn.execute(
                        "SELECT body,size,CASE WHEN length(digest_sha256)=64 THEN digest_sha256 END,CASE WHEN length(capture_origin_uuidv4)=36 THEN capture_origin_uuidv4 END,CASE WHEN length(capture_uuidv4)=36 THEN capture_uuidv4 END,CASE WHEN length(root)<=64 THEN root END,CASE WHEN length(target)<=64 THEN target END,path,proof_bundle FROM retained_notes WHERE object_format=? AND full_oid=? AND physical_copy_uuidv4=?",
                        key,
                    ).fetchone()
                    (
                        body,
                        size,
                        digest,
                        origin,
                        capture_id,
                        root,
                        target,
                        path,
                        bundle,
                    ) = row
                    native_type = "blob"
                work.charge("input_bytes", sum(size_row))
                try:
                    native = NativeObject(
                        OID(key[0], key[1]), native_type, body, size, digest
                    )
                    with account_verification(work):
                        native.validate()
                        if table == "retained_metadata":
                            parse_metadata(key[0], native_type, body)
                        else:
                            cap_sizes = conn.execute(
                                "SELECT length(CAST(source AS BLOB)),length(CAST(ref AS BLOB)) FROM captures WHERE capture_origin_uuidv4=? AND capture_uuidv4=?",
                                (origin, capture_id),
                            ).fetchone()
                            if cap_sizes is None:
                                raise ValueError("stored Notes Capture binding missing")
                            if any(
                                size > budget.max_payload_bytes for size in cap_sizes
                            ):
                                raise CoreFailure(
                                    "BUDGET",
                                    key,
                                    "existing Capture binding exceeds finite payload limit",
                                )
                            work.require("input_bytes", sum(cap_sizes))
                            cap_row = conn.execute(
                                "SELECT CASE WHEN length(repository_uuidv4)=36 THEN repository_uuidv4 END,source,ref,CASE WHEN length(object_format)<=6 THEN object_format END,CASE WHEN length(root)<=64 THEN root END FROM captures WHERE capture_origin_uuidv4=? AND capture_uuidv4=?",
                                (origin, capture_id),
                            ).fetchone()
                            work.charge("input_bytes", sum(cap_sizes))
                            cap = Capture(
                                origin,
                                capture_id,
                                cap_row[0],
                                cap_row[1],
                                _decode_native_ref(cap_row[2]),
                                OID(cap_row[3], cap_row[4]),
                            )
                            if cap.root != OID(key[0], root):
                                raise ValueError("stored Notes Capture root mismatch")
                            structures = _decode_proof_bundle(
                                bundle, budget, key[0], work
                            )
                            NotesProof(
                                cap, OID(key[0], target), native.oid, path, structures
                            ).validate()
                            work.require("metadata_units", 1)
                            role = conn.execute(
                                "SELECT 1 FROM note_roles WHERE capture_origin_uuidv4=? AND capture_uuidv4=? AND object_format=? AND root=? AND target=? AND note=? AND path=? AND proof_bundle=?",
                                (
                                    origin,
                                    capture_id,
                                    key[0],
                                    root,
                                    target,
                                    key[1],
                                    path,
                                    bundle,
                                ),
                            ).fetchone()
                            work.charge("metadata_units", 1)
                            if role is None:
                                raise ValueError(
                                    "stored retained Notes role evidence missing"
                                )
                except _InputLimit as error:
                    raise CoreFailure("BUDGET", key, str(error)) from error
                except CoreFailure as error:
                    if error.code == "BUDGET":
                        raise
                    reason = "Confirmed destination Core corruption: " + str(error)
                    stop_catalog(
                        directory,
                        reason,
                        details={
                            "store": "core",
                            "classification": "authoritative_data",
                        },
                    )
                    raise CorruptionDetectedError(reason) from error
                except (ValueError, TypeError, KeyError, IndexError) as error:
                    reason = "Confirmed destination Core corruption: " + str(error)
                    stop_catalog(
                        directory,
                        reason,
                        details={
                            "store": "core",
                            "classification": "authoritative_data",
                        },
                    )
                    raise CorruptionDetectedError(reason) from error
                return True
            finally:
                if conn.in_transaction:
                    conn.rollback()
                conn.close()

    def merge_salvage(
        self,
        fresh_destination_dir: Path,
        salvage_file: Path,
        budget: RecoveryBudget | None = None,
        request_id: str | None = None,
        *,
        authorization: ContextAdmissionService | None = None,
        admission: AdmissionContext | None = None,
        fault_stage: str | None = None,
    ) -> MergeReceipt:
        fresh_destination_dir = Path(fresh_destination_dir)
        salvage_file = Path(salvage_file)

        if not fresh_destination_dir.exists():
            raise RecoveryError(
                f"Fresh destination {fresh_destination_dir} does not exist"
            )
        if not salvage_file.exists():
            raise RecoveryError(f"Salvage file {salvage_file} does not exist")

        b = budget or RecoveryBudget()
        limits = dict(NotesLimits.work_limits())
        limits.update(b.max_work_units)
        limits.update(
            input_scan_bytes=b.max_input_bytes, input_records=b.max_input_records
        )
        with recovery_request(fresh_destination_dir, request_id, b, limits) as request:
            return self._merge_salvage_request(
                fresh_destination_dir,
                salvage_file,
                b,
                request,
                authorization=authorization,
                admission=admission,
                fault_stage=fault_stage,
            )

    def _merge_salvage_request(
        self,
        fresh_destination_dir,
        salvage_file,
        b,
        request,
        *,
        authorization=None,
        admission=None,
        fault_stage=None,
    ):
        work_budget = RecoveryWorkBudget(
            note_bytes=b.max_payload_bytes,
            work_limits={
                **b.max_work_units,
                "input_scan_bytes": b.max_input_bytes,
                "input_records": b.max_input_records,
            },
            initial_usage=request.usage,
            reserve=request.reserve,
            settle=request.settle,
        )
        budget_already_exhausted = request.state["budget_exhausted"]

        processed = 0
        admitted = 0
        replayed = 0
        observation = 0
        rejected = 0
        deferred = 0
        unprocessed = 0
        rejections: list[dict] = []
        budget_exhausted = budget_already_exhausted or work_budget.is_exhausted()

        # Connect to fresh core via GitCore production admission interface
        core_db = fresh_destination_dir / "core.sqlite3"
        core = GitCore(core_db)

        # Connect to fresh context if present
        ctx_db = fresh_destination_dir / "context.sqlite3"
        ctx_store = None
        ctx_conn = None
        ctx_auth = authorization
        ctx_admission = admission
        if ctx_db.exists():
            ctx_conn = p1_connect(ctx_db, "context")
            if ctx_auth is None or ctx_admission is None:
                repo_row = ctx_conn.execute(
                    "SELECT repository_uuidv4 FROM store_identity WHERE store_role='context'"
                ).fetchone()
                repo_id = repo_row[0] if repo_row else None
                repos = {repo_id} if repo_id else set()
                perm_repos = frozenset(repos) if repos else frozenset()
                from repo_catalog.domain.context_admission import (
                    AdmissionBudget,
                    AdmissionSelection,
                    DependencySet,
                    create_local_admission_service,
                )

                ctx_auth, ctx_admission, _ = create_local_admission_service(
                    operation="salvage_merge",
                    grants=DependencySet(repositories=repos),
                    permitted_repositories=perm_repos,
                    selection=AdmissionSelection(
                        all_selected=True,
                        max_work=min(
                            100_000_000,
                            max(
                                10_000_000,
                                b.max_work_units.get("verification_bytes", 10_000_000),
                            ),
                        ),
                        max_bytes=min(
                            100_000_000,
                            max(16 * 1024 * 1024, b.max_payload_bytes * 8),
                        ),
                        max_units=min(
                            100_000_000,
                            max(10_000, b.max_input_records * 4),
                        ),
                    ),
                    budget=AdmissionBudget(
                        work_limit=min(
                            100_000_000,
                            max(
                                10_000_000,
                                b.max_work_units.get("verification_bytes", 10_000_000),
                            ),
                        ),
                        bytes_limit=min(
                            100_000_000,
                            max(16 * 1024 * 1024, b.max_payload_bytes * 8),
                        ),
                        dependency_limit=min(
                            100_000_000,
                            max(100_000, b.max_input_records * 4),
                        ),
                    ),
                    principal="recovery-coordinator",
                    credential="recovery-coordinator",
                )
            else:
                ctx_auth.validate_context(ctx_admission)
            ctx_store = ContextStore(ctx_conn, authorization=ctx_auth)

        def _save_budget_state():
            request.mark_exhausted(budget_exhausted)

        try:

            def reserve_input(unit, amount):
                work_budget.require(unit, amount)

            def settle_input(unit, amount):
                work_budget.charge(unit, amount)

            with _open_salvage_input(salvage_file) as f:
                input_state = {}
                records = _bounded_jsonl_records(
                    f,
                    max_line_bytes=b.max_payload_bytes * 8 + 8192,
                    max_bytes=b.max_input_bytes
                    - work_budget.usage.get("input_scan_bytes", 0),
                    reserve=reserve_input,
                    settle=settle_input,
                    state=input_state,
                )
                while True:
                    if budget_exhausted or processed >= b.max_input_records:
                        unprocessed += int(_has_known_unread_input(f, input_state))
                        break
                    try:
                        line = next(records)
                    except StopIteration:
                        break
                    except (_InputLimit, CoreFailure) as e:
                        budget_exhausted = True
                        unprocessed += int(_has_known_unread_input(f, input_state))
                        rejections.append({"reason": f"Input incomplete: {e}"})
                        break
                    try:
                        reserve_input("input_records", 1)
                    except CoreFailure as e:
                        budget_exhausted = True
                        unprocessed += 1
                        rejections.append({"reason": f"Input incomplete: {e}"})
                        break
                    processed += 1
                    try:
                        record = _bounded_json_loads(line, b)
                        if not isinstance(record, dict) or not isinstance(
                            record.get("payload", {}), dict
                        ):
                            raise ValueError(
                                "Candidate record and payload must be objects"
                            )
                        _check_candidate_shape(record, b)
                    except Exception as e:
                        rejected += 1
                        rejections.append(
                            {
                                "line": processed,
                                "reason": f"JSON parse error or depth: {e}",
                            }
                        )
                        continue
                    finally:
                        settle_input("input_records", 1)

                    c_type = record.get("candidate_type")
                    payload = record.get("payload", {})
                    cand_id = record.get("candidate_id", str(processed))

                    # 1. Reject if candidate has corrupt status; treat partial candidate as qualified observation
                    status_val = record.get("extraction_status")
                    if status_val == ExtractionStatus.CORRUPT_BOUNDARY.value:
                        rejected += 1
                        rejections.append(
                            {
                                "candidate_id": cand_id,
                                "reason": "Corrupt boundary extraction status",
                            }
                        )
                        continue
                    if status_val == ExtractionStatus.PARTIAL.value:
                        observation += 1
                        rejections.append(
                            {
                                "candidate_id": cand_id,
                                "reason": f"Partial extraction candidate ({record.get('error') or 'incomplete'}); admitted only as qualified non-authoritative observation",
                            }
                        )
                        continue

                    if any(
                        record.get(key) is not None
                        and payload.get(key) is not None
                        and record[key] != payload[key]
                        for key in ("capture_origin_uuidv4", "capture_uuidv4")
                    ):
                        rejected += 1
                        rejections.append(
                            {
                                "candidate_id": cand_id,
                                "reason": "Conflicting original Capture coordinates",
                            }
                        )
                        continue

                    # 2. Check for required UUIDv4 format if present
                    if record.get("capture_uuidv4"):
                        try:
                            val = uuid.UUID(str(record["capture_uuidv4"]))
                            if val.version != 4:
                                rejected += 1
                                rejections.append(
                                    {
                                        "candidate_id": cand_id,
                                        "reason": "Capture UUID is not version 4",
                                    }
                                )
                                continue
                        except Exception:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": "Invalid capture UUID format",
                                }
                            )
                            continue

                    # Injected fault stage check after work is performed
                    if fault_stage == "after_partial_work" and processed >= 1:
                        _save_budget_state()
                        raise RecoveryError("Injected failure after partial work")

                    # 3. Admitting Retained Metadata Bodies (commits, trees, tags)
                    if c_type in (
                        CandidateType.RETAINED_BODY.value,
                        "retained_metadata",
                    ):
                        if not payload.get("full_oid") or not payload.get(
                            "native_type"
                        ):
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": "Missing required object_oid or object_type",
                                }
                            )
                            continue

                        b64_body = payload.get("body_base64")
                        if not isinstance(b64_body, str):
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": "Missing body_base64 in retained body candidate",
                                }
                            )
                            continue

                        try:
                            body_bytes = _decode_bounded_base64(
                                b64_body, b.max_payload_bytes, work_budget
                            )
                        except CoreFailure as error:
                            budget_exhausted = True
                            unprocessed += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": f"Work budget exhausted: {error}",
                                }
                            )
                            continue
                        except Exception as e:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": f"Base64 decoding failed: {e}",
                                }
                            )
                            continue

                        digest_sha = payload.get("digest_sha256")
                        try:
                            actual_sha = _hash_recovery_bytes(body_bytes, work_budget)
                        except CoreFailure as error:
                            budget_exhausted = True
                            unprocessed += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": f"Work budget exhausted: {error}",
                                }
                            )
                            continue
                        if digest_sha and digest_sha != actual_sha:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": "Digest SHA-256 mismatch in candidate body",
                                }
                            )
                            continue

                        obj_fmt = payload.get("object_format", "sha1")
                        ntype = payload["native_type"]
                        full_oid = payload["full_oid"]
                        copy_uuid = payload.get("physical_copy_uuidv4")

                        # A replay must pass the same native and immutable-row
                        # checks as a new admission. A digest alone establishes
                        # neither native type/size nor physical-copy identity.
                        if not copy_uuid:
                            observation += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": "Missing original physical copy UUID; withheld from authoritative admission",
                                }
                            )
                            continue
                        exists = core.sql(
                            "SELECT 1 FROM retained_metadata WHERE object_format=? AND full_oid=? AND physical_copy_uuidv4=?",
                            (obj_fmt, full_oid, copy_uuid),
                        )

                        try:
                            native = NativeObject(
                                oid=OID(obj_fmt, full_oid),
                                native_type=ntype,
                                body=body_bytes,
                                declared_size=payload.get("size", len(body_bytes)),
                                digest_sha256=actual_sha,
                            )
                            exists = self._verify_existing_retained_copy(
                                fresh_destination_dir,
                                "retained_metadata",
                                (obj_fmt, full_oid, copy_uuid),
                                b,
                                work_budget,
                            )
                            core.admit_metadata(native, copy_uuid, work_budget)
                            if exists:
                                replayed += 1
                            else:
                                admitted += 1
                        except (CorruptionDetectedError, CatalogStoppedError):
                            raise
                        except CoreFailure as cf:
                            if cf.code == "BUDGET":
                                budget_exhausted = True
                                unprocessed += 1
                                rejections.append(
                                    {
                                        "candidate_id": cand_id,
                                        "reason": f"Work budget exhausted: {cf}",
                                    }
                                )
                            else:
                                rejected += 1
                                rejections.append(
                                    {
                                        "candidate_id": cand_id,
                                        "reason": f"Core admission error: {cf}",
                                    }
                                )
                            continue
                        except Exception as e:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": f"Core admission error: {e}",
                                }
                            )
                            continue

                    # 4. Admitting Retained Notes with Role Proof
                    elif c_type in (CandidateType.NOTES_MAPPING.value, "retained_note"):
                        b64_body = payload.get("body_base64")
                        proof_bundle_str = payload.get("proof_bundle")
                        if not isinstance(b64_body, str) or not proof_bundle_str:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": "Missing required notes role proof or body",
                                }
                            )
                            continue

                        try:
                            body_bytes = _decode_bounded_base64(
                                b64_body, b.max_payload_bytes, work_budget
                            )
                            obj_fmt = payload.get("object_format", "sha1")
                            structures = _decode_proof_bundle(
                                proof_bundle_str, b, obj_fmt, work_budget
                            )
                            cap_orig_id = payload.get(
                                "capture_origin_uuidv4"
                            ) or record.get("capture_origin_uuidv4")
                            cap_val_id = payload.get("capture_uuidv4") or record.get(
                                "capture_uuidv4"
                            )
                            if not cap_orig_id or not cap_val_id:
                                rejected += 1
                                rejections.append(
                                    {
                                        "candidate_id": cand_id,
                                        "reason": "Missing capture UUIDv4 pair in notes candidate",
                                    }
                                )
                                continue

                            # Original domain provenance is independent of the
                            # forensic extraction coordinates. Never substitute
                            # this destination's repository for the issuer's.
                            existing_cap = core.sql(
                                "SELECT repository_uuidv4, source, ref, object_format, root FROM captures WHERE capture_origin_uuidv4=? AND capture_uuidv4=?",
                                (cap_orig_id, cap_val_id),
                            )
                            original = existing_cap[0] if existing_cap else (None,) * 5
                            repo_uuid = payload.get("repository_uuidv4", original[0])
                            orig_source = payload.get("source", original[1])
                            orig_ref = _decode_native_ref(
                                payload.get("ref", original[2])
                            )
                            if not repo_uuid or not orig_source or not orig_ref:
                                observation += 1
                                rejections.append(
                                    {
                                        "candidate_id": cand_id,
                                        "reason": "Cannot establish original Capture binding; withheld from authoritative admission as qualified observation",
                                    }
                                )
                                continue
                            cap = Capture(
                                cap_orig_id,
                                cap_val_id,
                                repo_uuid,
                                orig_source,
                                orig_ref,
                                OID(obj_fmt, payload["root"]),
                            )
                            if existing_cap and (
                                original[0],
                                original[1],
                                _decode_native_ref(original[2]),
                                original[3],
                                original[4],
                            ) != (
                                repo_uuid,
                                orig_source,
                                orig_ref,
                                obj_fmt,
                                payload["root"],
                            ):
                                raise ValueError(
                                    "Conflicting immutable Capture binding"
                                )
                            proof = NotesProof(
                                capture=cap,
                                target=OID(obj_fmt, payload["target"]),
                                note=OID(obj_fmt, payload["full_oid"]),
                                path=payload["path"],
                                structures=structures,
                            )
                            copy_uuid = payload.get("physical_copy_uuidv4")

                            # Missing physical identity cannot be repaired by
                            # matching another copy's bytes or inventing a copy.
                            if not copy_uuid:
                                observation += 1
                                rejections.append(
                                    {
                                        "candidate_id": cand_id,
                                        "reason": "Missing original physical copy UUID; withheld from authoritative admission",
                                    }
                                )
                                continue
                            exists = core.sql(
                                "SELECT 1 FROM retained_notes WHERE object_format=? AND full_oid=? AND physical_copy_uuidv4=?",
                                (obj_fmt, payload["full_oid"], copy_uuid),
                            )
                            native_note = NativeObject(
                                oid=OID(obj_fmt, payload["full_oid"]),
                                native_type=payload.get("native_type", "blob"),
                                body=body_bytes,
                                declared_size=payload.get("size", len(body_bytes)),
                                digest_sha256=payload.get("digest_sha256")
                                or _hash_recovery_bytes(body_bytes, work_budget),
                            )
                            # Production admission checks role + exact bytes,
                            # then inserts Capture/role/body in one transaction.
                            exists = self._verify_existing_retained_copy(
                                fresh_destination_dir,
                                "retained_notes",
                                (obj_fmt, payload["full_oid"], copy_uuid),
                                b,
                                work_budget,
                            )
                            core.admit_note(proof, native_note, copy_uuid, work_budget)
                            if exists:
                                replayed += 1
                            else:
                                admitted += 1
                        except (CorruptionDetectedError, CatalogStoppedError):
                            raise
                        except CoreFailure as cf:
                            if cf.code == "BUDGET":
                                budget_exhausted = True
                                unprocessed += 1
                                rejections.append(
                                    {
                                        "candidate_id": cand_id,
                                        "reason": f"Work budget exhausted: {cf}",
                                    }
                                )
                            else:
                                rejected += 1
                                rejections.append(
                                    {
                                        "candidate_id": cand_id,
                                        "reason": f"Notes admission error: {cf}",
                                    }
                                )
                            continue
                        except Exception as e:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": f"Notes admission error: {e}",
                                }
                            )
                            continue

                    # 5. Admitting Context Text Bodies
                    elif c_type in (
                        CandidateType.CONTEXT_DOCUMENT.value,
                        "context_text",
                    ):
                        if not ctx_store:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": "Context store not present in destination",
                                }
                            )
                            continue

                        text_val = payload.get("text_value")
                        try:
                            text_bytes = _bounded_utf8(
                                text_val, b.max_payload_bytes, work_budget
                            )
                            expected_sha = payload.get("sha256")
                            actual_sha = _hash_recovery_bytes(text_bytes, work_budget)
                            if expected_sha and expected_sha != actual_sha:
                                raise ValueError("Text body SHA-256 mismatch")
                            with ctx_store.transaction(admission=ctx_admission):
                                assert_catalog_not_stopped(fresh_destination_dir)
                                try:
                                    exists = verify_existing_context_text(
                                        ctx_conn,
                                        actual_sha,
                                        text_bytes,
                                        b.max_payload_bytes,
                                        work_budget,
                                    )
                                except BackupValidationError as error:
                                    # Publish the stop while holding the
                                    # writer cut, before any other ordinary
                                    # operation can pass the diagnosed row.
                                    reason = (
                                        "Confirmed destination Context corruption: "
                                        + str(error)
                                    )
                                    stop_catalog(
                                        fresh_destination_dir,
                                        reason,
                                        details={
                                            "store": "context",
                                            "classification": "authoritative_data",
                                        },
                                    )
                                    raise CorruptionDetectedError(reason) from error
                                if not exists:
                                    # ContextStore hashes once; SQLite's
                                    # SHA-256 CHECK hashes the new row again.
                                    cost = len(text_bytes) * 2
                                    work_budget.require("verification_bytes", cost)
                                    ctx_store.text(text_val)
                                    work_budget.charge("verification_bytes", cost)
                                assert_catalog_not_stopped(fresh_destination_dir)
                            if exists:
                                replayed += 1
                            else:
                                admitted += 1
                        except (CorruptionDetectedError, CatalogStoppedError):
                            raise
                        except CoreFailure as error:
                            budget_exhausted = True
                            unprocessed += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": f"Work budget exhausted: {error}",
                                }
                            )
                            continue
                        except Exception as e:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": f"Context admission error: {e}",
                                }
                            )
                            continue

                    elif c_type == CandidateType.CONTEXT_RESOURCE.value:
                        # Recovery currently has no complete typed adapter for
                        # every Context resource/provenance dependency. Preserve
                        # this candidate as an explicitly non-authoritative
                        # observation; never call it an exact replay or write
                        # arbitrary extracted columns into Context.
                        observation += 1
                        rejections.append(
                            {
                                "candidate_id": cand_id,
                                "reason": "Context resource requires typed dependency reconciliation; qualified non-authoritative observation only",
                            }
                        )

                    # 6. Admitting Git Metadata Objects (repositories, git_objects, captures)
                    elif c_type == CandidateType.GIT_METADATA.value:
                        prov_tbl = (record.get("extraction_provenance") or {}).get(
                            "table"
                        ) or (record.get("provenance") or {}).get("table")
                        try:
                            work_budget.require("metadata_units", 1)
                            try:
                                if (
                                    prov_tbl == "repositories"
                                    and "repository_uuidv4" in payload
                                ):
                                    repo_id = payload["repository_uuidv4"]
                                    exists = core.sql(
                                        "SELECT 1 FROM repositories WHERE repository_uuidv4=?",
                                        (repo_id,),
                                    )
                                    core.admit_repository(repo_id)
                                    if exists:
                                        replayed += 1
                                    else:
                                        admitted += 1
                                elif (
                                    prov_tbl == "git_objects" and "full_oid" in payload
                                ):
                                    obj_f = payload.get("object_format", "sha1")
                                    f_oid = payload["full_oid"]
                                    exists = core.sql(
                                        "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
                                        (obj_f, f_oid),
                                    )
                                    core.admit_object(OID(obj_f, f_oid))
                                    if exists:
                                        replayed += 1
                                    else:
                                        admitted += 1
                                elif prov_tbl == "captures":
                                    cap_orig = payload.get("capture_origin_uuidv4")
                                    cap_id = payload.get("capture_uuidv4")
                                    repo_id = payload.get("repository_uuidv4")
                                    src = payload.get("source")
                                    rf = payload.get("ref")
                                    rf = _decode_native_ref(payload.get("ref"))
                                    obj_f = payload.get("object_format", "sha1")
                                    rt = payload.get("root")
                                    if not (
                                        cap_orig
                                        and cap_id
                                        and repo_id
                                        and src
                                        and rf
                                        and rt
                                    ):
                                        rejected += 1
                                        rejections.append(
                                            {
                                                "candidate_id": cand_id,
                                                "reason": "Missing required field in captures candidate",
                                            }
                                        )
                                        continue
                                    cap = Capture(
                                        cap_orig,
                                        cap_id,
                                        repo_id,
                                        src,
                                        rf,
                                        OID(obj_f, rt),
                                    )
                                    existing_cap = core.sql(
                                        "SELECT 1 FROM captures WHERE capture_origin_uuidv4=? AND capture_uuidv4=?",
                                        (cap_orig, cap_id),
                                    )
                                    core.admit_capture(cap)
                                    if existing_cap:
                                        replayed += 1
                                    else:
                                        admitted += 1
                                else:
                                    # Candidate is accepted as a qualified recovery observation without authoritative mutation
                                    observation += 1
                            finally:
                                work_budget.charge("metadata_units", 1)
                        except CoreFailure as error:
                            if error.code == "BUDGET":
                                budget_exhausted = True
                                unprocessed += 1
                                rejections.append(
                                    {
                                        "candidate_id": cand_id,
                                        "reason": f"Work budget exhausted: {error}",
                                    }
                                )
                            else:
                                rejected += 1
                                rejections.append(
                                    {
                                        "candidate_id": cand_id,
                                        "reason": f"Metadata admission error: {error}",
                                    }
                                )
                            continue
                        except Exception as e:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": f"Metadata admission error: {e}",
                                }
                            )
                            continue

                    else:
                        # Unknown or unhandled candidate type
                        rejected += 1
                        rejections.append(
                            {
                                "candidate_id": cand_id,
                                "reason": f"Unknown candidate type: {c_type}",
                            }
                        )
        finally:
            _save_budget_state()
            if ctx_conn:
                ctx_conn.close()

        return MergeReceipt(
            destination_path=str(fresh_destination_dir),
            candidates_processed=processed,
            admitted_units=admitted,
            rejected_units=rejected,
            replayed_units=replayed,
            observation_units=observation,
            deferred_units=deferred,
            unprocessed_units=unprocessed,
            input_complete=not budget_exhausted and processed < b.max_input_records,
            unprocessed_count_exact=not budget_exhausted
            and processed < b.max_input_records,
            rejections=rejections,
        )

    def activate(
        self,
        fresh_catalog_dir: Path,
        target_locator_path: Path,
        *,
        fault_stage: str | None = None,
    ) -> ActivationReceipt:
        fresh_catalog_dir = Path(fresh_catalog_dir)
        target_locator_path = Path(target_locator_path)

        if not fresh_catalog_dir.exists():
            raise ActivationError(
                f"Fresh catalog directory {fresh_catalog_dir} does not exist"
            )

        if fresh_catalog_dir.is_symlink():
            raise ActivationError("Fresh catalog must not be a symlink")
        fresh_catalog_dir = fresh_catalog_dir.absolute()
        if target_locator_path.absolute() == fresh_catalog_dir:
            raise ActivationError("Catalog and locator paths must be distinct")
        advertised_catalog_dir = fresh_catalog_dir
        with ExitStack() as handles:
            directory_fd = _open_directory_nofollow(advertised_catalog_dir)
            handles.callback(os.close, directory_fd)
            # Keep validation, derivative I/O and both permanent gate inodes on
            # the directory actually opened, even across pathname substitution.
            fresh_catalog_dir = Path(f"/proc/self/fd/{directory_fd}")
            assert_catalog_not_stopped(fresh_catalog_dir)
            handles.enter_context(catalog_gate(fresh_catalog_dir, exclusive=True))
            if fault_stage == "before_validation":
                raise ActivationError("Injected failure before validation")

            core_db = fresh_catalog_dir / "core.sqlite3"
            if not core_db.exists():
                raise ActivationError("Fresh catalog is missing core.sqlite3")

            for database in (core_db, fresh_catalog_dir / "context.sqlite3"):
                if database.is_symlink() or (
                    database.exists() and database.stat().st_nlink != 1
                ):
                    raise ActivationError(
                        "Authoritative file symlink/hardlink forbidden"
                    )
            # Validate core
            self._validate_and_summarize_core(core_db)
            repo_uuid, inst_uuid = self._extract_identities(core_db, "core")

            if fault_stage == "between_core_and_context":
                raise ActivationError("Injected failure between core and context")

            # Validate context if present
            ctx_db = fresh_catalog_dir / "context.sqlite3"
            if ctx_db.exists():
                self._validate_and_summarize_context(ctx_db)
                ctx_repo_uuid, ctx_inst_uuid = self._extract_identities(
                    ctx_db, "context"
                )
                if repo_uuid != ctx_repo_uuid or inst_uuid != ctx_inst_uuid:
                    raise ActivationError(
                        f"Catalog activation identity mismatch: Core ({repo_uuid}, {inst_uuid}) vs Context ({ctx_repo_uuid}, {ctx_inst_uuid})"
                    )

            # Initialize empty reconstructible stores. This does not rebuild the
            # full Search projection; its receipt explicitly says initialized_empty.
            # Reconstruct Operational and Search cleanly from compiled P1 DDL
            op_db = fresh_catalog_dir / "operational.sqlite3"
            for path in (op_db, Path(str(op_db) + "-wal"), Path(str(op_db) + "-shm")):
                if path.exists() or path.is_symlink():
                    path.unlink()
            p1_init(op_db, "operational", repo_uuid, inst_uuid)
            _fsync_file(op_db)

            search_db = fresh_catalog_dir / "search.sqlite3"
            for path in (
                search_db,
                Path(str(search_db) + "-wal"),
                Path(str(search_db) + "-shm"),
            ):
                if path.exists() or path.is_symlink():
                    path.unlink()
            p1_init(search_db, "search", repo_uuid, inst_uuid)
            _fsync_file(search_db)

            _fsync_dir(fresh_catalog_dir)
            _assert_directory_identity(advertised_catalog_dir, directory_fd)

            if fault_stage == "after_operational_init":
                raise ActivationError(
                    "Injected failure after operational initialization"
                )

            # Final publication is serialized against Recovery Stop. Pinned parent
            # descriptor prevents a parent-directory substitution redirecting writes.
            parent_fd = _open_directory_nofollow(
                target_locator_path.parent, create=True
            )
            tmp_name = f"{target_locator_path.name}.tmp.{uuid.uuid4().hex}"
            try:
                with catalog_completion(fresh_catalog_dir):
                    _assert_directory_identity(advertised_catalog_dir, directory_fd)
                    _assert_directory_identity(
                        target_locator_path.parent, parent_fd, label="Locator parent"
                    )
                    if fault_stage == "during_locator_replacement":
                        raise ActivationError(
                            "Injected failure during locator replacement"
                        )
                    try:
                        locator_info = os.stat(
                            target_locator_path.name,
                            dir_fd=parent_fd,
                            follow_symlinks=False,
                        )
                    except FileNotFoundError:
                        locator_info = None
                    publication_name = target_locator_path.name
                    if locator_info is not None and stat.S_ISDIR(locator_info.st_mode):
                        publication_name = "active_catalog_instance.json"
                    backup_name = f"{tmp_name}.previous"
                    had_previous = False
                    try:
                        os.link(
                            publication_name,
                            backup_name,
                            src_dir_fd=parent_fd,
                            dst_dir_fd=parent_fd,
                            follow_symlinks=False,
                        )
                        had_previous = True
                    except FileNotFoundError:
                        pass
                    published = False
                    if locator_info is None or stat.S_ISLNK(locator_info.st_mode):
                        os.symlink(
                            str(advertised_catalog_dir), tmp_name, dir_fd=parent_fd
                        )
                        if locator_info is None:
                            # linkat gives atomic creation without replacing a racing locator.
                            os.link(
                                tmp_name,
                                target_locator_path.name,
                                src_dir_fd=parent_fd,
                                dst_dir_fd=parent_fd,
                                follow_symlinks=False,
                            )
                            os.unlink(tmp_name, dir_fd=parent_fd)
                        else:
                            os.replace(
                                tmp_name,
                                target_locator_path.name,
                                src_dir_fd=parent_fd,
                                dst_dir_fd=parent_fd,
                            )
                        activated_catalog_path = str(target_locator_path)
                    else:
                        name = target_locator_path.name
                        if stat.S_ISDIR(locator_info.st_mode):
                            name = "active_catalog_instance.json"
                        elif not stat.S_ISREG(locator_info.st_mode):
                            raise ActivationError("Unsupported locator file type")
                        locator_data = {
                            "active_catalog_path": str(advertised_catalog_dir),
                            "activated_at_us": int(time.time() * 1_000_000),
                            "repository_uuidv4": repo_uuid,
                            "catalog_instance_uuidv4": inst_uuid,
                        }
                        fd = os.open(
                            tmp_name,
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                            0o600,
                            dir_fd=parent_fd,
                        )
                        with os.fdopen(fd, "w") as output:
                            output.write(json.dumps(locator_data, indent=2) + "\n")
                            output.flush()
                            os.fsync(output.fileno())
                        os.replace(
                            tmp_name, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd
                        )
                        activated_catalog_path = str(advertised_catalog_dir)
                    published = True
                    try:
                        os.fsync(parent_fd)
                        _assert_directory_identity(advertised_catalog_dir, directory_fd)
                        _assert_directory_identity(
                            target_locator_path.parent,
                            parent_fd,
                            label="Locator parent",
                        )
                    except BaseException:
                        # A stale pathname must not remain as the active locator.
                        # Preserve the preceding locator on a detected swap.
                        if had_previous:
                            os.replace(
                                backup_name,
                                publication_name,
                                src_dir_fd=parent_fd,
                                dst_dir_fd=parent_fd,
                            )
                        elif published:
                            os.unlink(publication_name, dir_fd=parent_fd)
                        os.fsync(parent_fd)
                        raise
            finally:
                try:
                    os.unlink(f"{tmp_name}.previous", dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
                try:
                    os.unlink(tmp_name, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
                os.close(parent_fd)

            return ActivationReceipt(
                activated_catalog_path=activated_catalog_path,
                source_backup_id="restored",
                reconstructed_stores=["operational", "search"],
                timestamp_us=int(time.time() * 1_000_000),
                clean_operational=True,
                search_derivative_state="initialized_empty",
            )
