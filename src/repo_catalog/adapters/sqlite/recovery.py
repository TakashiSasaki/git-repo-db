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
from dataclasses import replace
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
from repo_catalog.adapters.sqlite.p1_schema import _resource as _p1_resource
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
from repo_catalog.adapters.sqlite.recovery_budget import (
    _invalid_constant,
    _unique_object,
    canonical_request_id,
    recovery_request,
)
from repo_catalog.adapters.sqlite.recovery_budget import (
    _read as _read_recovery_state,
)
from repo_catalog.adapters.sqlite.recovery_budget import (
    _write as _write_recovery_state,
)
from repo_catalog.adapters.sqlite.recovery_validation import (
    RefValidationBudgetError,
    StoredContextInvariantError,
    StoredRefInvariantError,
    bounded_domain_exists,
    charge_ref_integrity_inputs,
    validate_stored_admission_guards,
    validate_stored_checks,
    validate_stored_ref_authority,
    validate_stored_text_encoding,
    verify_existing_context_text,
)
from repo_catalog.domain.git_native import parse_metadata
from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.p1_core import (
    OID,
    CoreFailure,
    NativeObject,
    account_verification,
    native_oid,
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

_REF_OBSERVATION_TABLES = frozenset(
    {
        "ref_observations",
        "ref_enumeration_observations",
        "ref_enumeration_links",
        "ref_observation_claims",
        "notes_mappings",
        "notes_mapping_claims",
        "notes_mapping_groups",
        "notes_mapping_evidence",
        "ref_coverage_proofs",
        "ref_retained_notes",
    }
)

# Independent ceilings allow the two simultaneously open forensic readers to
# reserve their SQLite VM work without sharing a pending reservation. The
# reservation is durable before stepping SQLite and settled on clean return.
_FORENSIC_VM_LIMIT = 10_000_000
_FORENSIC_VM_UNITS = ("legacy_source_vm_steps", "ref_source_vm_steps")


AT_FDCWD = -100
RENAME_NOREPLACE = 1


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


def _read_restored_baseline(
    directory: Path, *, directory_fd: int | None = None, work=None
) -> dict:
    """Read the bounded receipt published with a validated fresh restore."""
    directory_fd = (
        _open_directory_nofollow(directory)
        if directory_fd is None
        else os.dup(directory_fd)
    )
    try:
        fd = _open_regular_at(directory_fd, "p1-restored-baseline.json")
        try:
            expected_size = os.fstat(fd).st_size
            if expected_size > 4096:
                raise RecoveryError("Restored baseline receipt exceeds finite limit")
            if work is not None:
                work.require("input_bytes", expected_size + 1)
            try:
                # A racing writer may grow the receipt after fstat. Never read
                # more than the amount reserved for this particular read.
                os.lseek(fd, 0, os.SEEK_SET)
                raw = os.read(fd, expected_size + 1)
                if len(raw) != expected_size:
                    raise RecoveryError(
                        "Restored baseline receipt changed while reading"
                    )
            except BaseException:
                if work is not None:
                    work.abandon("input_bytes")
                raise
            if work is not None:
                work.charge("input_bytes", len(raw))
        finally:
            os.close(fd)
    finally:
        os.close(directory_fd)
    try:
        value = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        if (
            type(value) is not dict
            or set(value)
            != {
                "version",
                "backup_id",
                "scope",
                "repository_uuidv4",
                "catalog_instance_uuidv4",
                "manifest_sha256",
            }
            or type(value["version"]) is not int
            or value["version"] != 1
            or value["scope"]
            not in (BackupScope.GIT_ONLY.value, BackupScope.PAIRED.value)
            or not uuid4(value["backup_id"])
            or not uuid4(value["repository_uuidv4"])
            or not uuid4(value["catalog_instance_uuidv4"])
            or type(value["manifest_sha256"]) is not str
            or len(value["manifest_sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in value["manifest_sha256"])
        ):
            raise ValueError("invalid restored baseline receipt")
        return value
    except (ValueError, TypeError, KeyError, UnicodeDecodeError) as error:
        raise RecoveryError("Invalid restored baseline receipt") from error


def _context_identity_for_salvage(conn, core, work):
    """Read only fixed-size Context identity fields before using that store."""
    work.require("identity_read_rows", 2)
    try:
        work.require("identity_read_bytes", 144)
    except BaseException:
        work.abandon("identity_read_rows")
        raise
    try:
        rows = conn.execute(
            "SELECT store_role='context', "
            "CASE WHEN typeof(repository_uuidv4)='text' "
            "AND octet_length(repository_uuidv4)=36 "
            "THEN CAST(repository_uuidv4 AS BLOB) END, "
            "CASE WHEN typeof(catalog_instance_uuidv4)='text' "
            "AND octet_length(catalog_instance_uuidv4)=36 "
            "THEN CAST(catalog_instance_uuidv4 AS BLOB) END "
            "FROM store_identity LIMIT 2"
        ).fetchall()
    except BaseException:
        work.abandon("identity_read_rows")
        work.abandon("identity_read_bytes")
        raise
    work.charge("identity_read_rows", len(rows))
    work.charge(
        "identity_read_bytes",
        sum(len(value) for row in rows for value in row[1:] if value is not None),
    )
    try:
        if len(rows) != 1 or rows[0][0] != 1:
            raise ValueError("one Context identity is required")
        identity = tuple(value.decode("ascii") for value in rows[0][1:])
        if not all(uuid4(value) for value in identity):
            raise ValueError("canonical Context identity is required")
        return identity
    except (ValueError, TypeError, AttributeError, UnicodeDecodeError) as error:
        core._integrity_stop(("Context identity", str(error)))


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


def _encode_salvage_line(record: dict, work, maximum: int, max_depth: int = 16) -> str:
    """Reserve traversal and JSON expansion before serializing a candidate."""
    bound = 2
    stack = [(record, 1)]
    scheduled = 1
    while stack:
        work.require("metadata_units", 1)
        value, depth = stack.pop()
        work.charge("metadata_units", 1)
        if depth > max_depth:
            raise CoreFailure("BUDGET", "salvage", "finite candidate nesting limit")
        bound += 8
        if isinstance(value, dict):
            scheduled += 2 * len(value)
            if scheduled > 8000:
                raise CoreFailure("BUDGET", "salvage", "finite candidate element limit")
            work.require("metadata_units", 2 * len(value))
            work.charge("metadata_units", 2 * len(value))
            stack.extend((key, depth + 1) for key in value)
            stack.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, (list, tuple)):
            scheduled += len(value)
            if scheduled > 8000:
                raise CoreFailure("BUDGET", "salvage", "finite candidate element limit")
            work.require("metadata_units", len(value))
            work.charge("metadata_units", len(value))
            stack.extend((child, depth + 1) for child in value)
        elif isinstance(value, str):
            work.require("input_bytes", len(value))
            try:
                size = sum(
                    12
                    if ord(char) > 0xFFFF
                    else 6
                    if ord(char) > 0x7F or ord(char) < 0x20
                    else 2
                    if char in ('"', "\\")
                    else 1
                    for char in value
                )
            except BaseException:
                work.abandon("input_bytes")
                raise
            work.charge("input_bytes", len(value))
            bound += size + 2
        elif value is None or type(value) in (bool, int, float):
            bound += 32
        else:
            raise ValueError("unsupported salvage candidate value")
        if bound > maximum:
            raise CoreFailure("BUDGET", "salvage", "finite candidate output limit")
    work.require("input_bytes", bound)
    try:
        line = json.dumps(record, ensure_ascii=True, allow_nan=False) + "\n"
        if len(line) > bound:
            raise ValueError("salvage JSON reservation underestimated")
    except BaseException:
        work.abandon("input_bytes")
        raise
    work.charge("input_bytes", len(line))
    return line


def _encode_salvage_base64(raw: bytes, work) -> str:
    size = 4 * ((len(raw) + 2) // 3)
    work.require("input_bytes", size)
    try:
        value = base64.b64encode(raw).decode("ascii")
    except BaseException:
        work.abandon("input_bytes")
        raise
    work.charge("input_bytes", len(value))
    return value


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
        # Unbuffered input keeps every kernel read within the amount reserved
        # by the bounded JSONL reader, including the last short read.
        return os.fdopen(fd, "rb", buffering=0)
    except BaseException:
        os.close(fd)
        raise


def _copy_forensic_files(
    catalog_dir: Path, forensic_dir: Path, max_bytes: int, work=None
) -> None:
    """Bound actual streamed bytes, not only a racy preflight stat estimate."""
    copied = 0
    for name in ("core.sqlite3", "context.sqlite3"):
        for suffix in ("", "-wal", "-shm", "-journal"):
            source = catalog_dir / (name + suffix)
            if source.is_symlink():
                raise SalvageError(f"Refusing symlink source evidence: {source.name}")
            if not source.exists():
                continue
            flags = (
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0)
            )
            # BufferedReader may prefetch beyond the reserved byte count on a
            # short read (notably the one-byte growth probe).
            with os.fdopen(os.open(source, flags), "rb", buffering=0) as src:
                before = os.fstat(src.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise SalvageError("Source evidence must be a regular file")
                if before.st_size > max_bytes - copied:
                    raise SalvageError("Suspect catalog exceeds recovery copy budget")
                with (forensic_dir / source.name).open("xb") as dest:
                    remaining_file = before.st_size
                    while remaining_file:
                        amount = min(65536, remaining_file, max_bytes - copied)
                        if work is not None:
                            work.require("input_scan_bytes", amount)
                        try:
                            block = src.read(amount)
                        except BaseException:
                            if work is not None:
                                work.abandon("input_scan_bytes")
                            raise
                        if work is not None:
                            work.charge("input_scan_bytes", len(block))
                        if not block:
                            raise SalvageError(
                                "Source evidence shrank during forensic copy"
                            )
                        dest.write(block)
                        copied += len(block)
                        remaining_file -= len(block)
                    # One bounded probe detects growth without copying the suffix.
                    if work is not None:
                        work.require("input_scan_bytes", 1)
                    try:
                        growth = src.read(1)
                    except BaseException:
                        if work is not None:
                            work.abandon("input_scan_bytes")
                        raise
                    if work is not None:
                        work.charge("input_scan_bytes", len(growth))
                    if growth:
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
        self._max.update(
            {
                unit: _FORENSIC_VM_LIMIT
                for unit in _FORENSIC_VM_UNITS
                if initial_usage is None or reserve is None or unit in initial_usage
            }
        )
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
        if isinstance(current, RefValidationBudgetError):
            return None
        if isinstance(current, (StoredContextInvariantError, StoredRefInvariantError)):
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

    def __init__(self, *, validation_budget: RecoveryBudget | None = None):
        if validation_budget is not None and not isinstance(
            validation_budget, RecoveryBudget
        ):
            raise ValueError("RecoveryBudget required")
        budget = validation_budget or RecoveryBudget()
        self.validation_budget = replace(
            budget, max_work_units=dict(budget.max_work_units)
        )

    def _ref_validation_work(self):
        from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget

        return UnlimitedWorkBudget(
            note_bytes=self.validation_budget.max_payload_bytes,
            work_limits=dict(self.validation_budget.max_work_units),
        )

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

            # Deep Domain and Retained-Byte Validation outside writer lock.
            # Source diagnosis, if needed, uses the same cumulative allowance.
            validation_work = self._ref_validation_work()
            try:
                core_summary = self._validate_and_summarize_core(
                    staged_core, work=validation_work
                )
            except RefValidationBudgetError:
                # A finite limit is not evidence of catalog corruption.
                raise
            except (BackupValidationError, sqlite3.Error) as e:
                self._diagnose_and_stop_if_source_corrupt(
                    catalog_dir, core_db_path, "core", e, work=validation_work
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
                manifest_version=2,
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
        *,
        work=None,
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
                            evidence / source_db_path.name, work=work
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

    def _validate_and_summarize_core(
        self, core_db: Path, *, work=None
    ) -> RetainedByteSummary:
        conn = sqlite3.connect(f"file:{core_db.resolve()}?mode=ro", uri=True)
        if work is None:
            work = self._ref_validation_work()
        vm_remaining = getattr(
            work,
            "_ref_backup_vm_remaining",
            self.validation_budget.max_work_units.get(
                "metadata_units", NotesLimits.work_limits()["metadata_units"]
            )
            * 100,
        )
        vm_exhausted = False

        def progress():
            nonlocal vm_remaining, vm_exhausted
            vm_remaining -= 100
            work._ref_backup_vm_remaining = vm_remaining
            vm_exhausted = vm_remaining < 0
            return int(vm_exhausted)

        conn.set_progress_handler(progress, 100)
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

            ref_notes, ref_bytes = validate_stored_ref_authority(
                conn, work, self.validation_budget
            )
            validate_stored_text_encoding(conn, "core", work=work)
            with account_verification(work):
                validate_stored_checks(conn, "core", retained_bytes=False, work=work)

            # PRAGMA integrity_check
            charge_ref_integrity_inputs(conn, work)
            with account_verification(work):
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

            total_bytes = ref_bytes
            commits = 0
            trees = 0
            tags = 0
            notes = ref_notes

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

            with account_verification(work):
                validate_stored_checks(conn, "core", retained_bytes=True, work=work)
                validate_stored_admission_guards(conn, "core", work=work)

            return RetainedByteSummary(
                commit_count=commits,
                tree_count=trees,
                tag_count=tags,
                notes_body_count=notes,
                total_retained_bytes=total_bytes,
            )
        except CoreFailure as e:
            if e.code in ("BUDGET", "QUERY_BUDGET"):
                raise RefValidationBudgetError(str(e)) from e
            raise
        except sqlite3.Error as e:
            if vm_exhausted:
                raise RefValidationBudgetError("finite backup SQLite work limit") from e
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
        request_id: str | None = None,
    ) -> SalvageReceipt:
        catalog_dir, output_file = (
            Path(catalog_dir).absolute(),
            Path(output_file).absolute(),
        )
        if output_file.resolve().is_relative_to(catalog_dir.resolve()):
            raise SalvageError(
                "Salvage output must be outside preserved source catalog"
            )
        if output_file.exists() or output_file.is_symlink():
            raise SalvageError("Salvage output already exists; no-overwrite required")
        b = budget or RecoveryBudget()
        for name, value in (("max_records", max_records), ("max_bytes", max_bytes)):
            if value is not None and (type(value) is not int or value <= 0):
                raise ValueError(f"{name} must be a positive integer")
        b = replace(
            b,
            max_input_records=min(
                max_records or b.max_input_records, b.max_input_records
            ),
            max_input_bytes=min(max_bytes or b.max_input_bytes, b.max_input_bytes),
        )
        output_fd = _open_directory_nofollow(output_file.parent, create=True)
        try:
            source_fd = _open_directory_nofollow(catalog_dir)
        except BaseException:
            os.close(output_fd)
            raise
        try:
            source_stat, output_stat = os.fstat(source_fd), os.fstat(output_fd)
            if (source_stat.st_dev, source_stat.st_ino) == (
                output_stat.st_dev,
                output_stat.st_ino,
            ):
                raise SalvageError(
                    "Salvage output must be outside preserved source catalog"
                )
            source = Path(f"/proc/self/fd/{source_fd}")
            output_dir = Path(f"/proc/self/fd/{output_fd}")
            output = output_dir / output_file.name
            token = (
                canonical_request_id(request_id)
                if request_id is not None
                else str(output_file)
            )
            request_key = (
                "extract-" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:40]
            )
            limits = dict(NotesLimits.work_limits())
            limits.update(dict.fromkeys(_FORENSIC_VM_UNITS, _FORENSIC_VM_LIMIT))
            limits.update(b.max_work_units)
            limits.setdefault("json_decode_bytes", b.max_input_bytes * 3)
            limits.setdefault(
                "pending_candidate_bytes",
                min(b.max_input_bytes, b.max_payload_bytes * 8 + 8192),
            )
            limits.setdefault("identity_read_rows", b.max_input_records * 2)
            limits.setdefault("identity_read_bytes", b.max_input_records * 144)
            limits.update(
                input_scan_bytes=b.max_input_bytes, input_records=b.max_input_records
            )
            # Bind the durable request ledger to the stopped source, not the
            # chosen output directory: moving a continuation's output must not
            # silently reset its accumulated budget. These sidecars do not
            # modify the preserved database, WAL, SHM, or rollback journal.
            with recovery_request(source, request_key, b, limits) as request:
                binding_path = request.path.with_suffix(".source.json")
                binding = {
                    "version": 1,
                    "source": str(catalog_dir),
                    "device": source_stat.st_dev,
                    "inode": source_stat.st_ino,
                }
                if binding_path.exists() or binding_path.is_symlink():
                    if _read_recovery_state(binding_path) != binding:
                        raise SalvageError("Recovery request source binding changed")
                elif any(request.usage.values()):
                    raise SalvageError("Recovery request source binding missing")
                else:
                    _write_recovery_state(binding_path, binding)
                work = RecoveryWorkBudget(
                    note_bytes=b.max_payload_bytes,
                    work_limits=limits,
                    initial_usage=request.usage,
                    reserve=request.reserve,
                    settle=request.settle,
                )
                try:
                    result = self._extract_salvage_request(
                        source, output, budget=b, work=work, output_parent_fd=output_fd
                    )
                    try:
                        _assert_directory_identity(
                            catalog_dir, source_fd, label="Salvage source"
                        )
                        _assert_directory_identity(
                            output_file.parent, output_fd, label="Salvage output parent"
                        )
                    except ActivationError as error:
                        raise SalvageError(
                            "Salvage publication location is uncertain"
                        ) from error
                    return replace(
                        result,
                        catalog_path=str(catalog_dir),
                        output_file=str(output_file),
                    )
                finally:
                    request.mark_exhausted(work.is_exhausted())
        finally:
            os.close(source_fd)
            os.close(output_fd)

    def _extract_salvage_request(
        self,
        catalog_dir: Path,
        output_file: Path,
        max_records: int | None = None,
        max_bytes: int | None = None,
        budget: RecoveryBudget | None = None,
        *,
        work,
        output_parent_fd: int,
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
                _copy_forensic_files(catalog_dir, forensic_dir, limit_bytes, work)

                temp_out = (
                    output_file.parent / f"{output_file.name}.tmp.{uuid.uuid4().hex}"
                )
                with temp_out.open("x", encoding="utf-8") as out_f:
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
                            max_json_depth=b.max_json_depth,
                            records_offset=total_records,
                            bytes_offset=total_bytes,
                            work=work,
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
                                max_json_depth=b.max_json_depth,
                                records_offset=total_records,
                                bytes_offset=total_bytes,
                                work=work,
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
                try:
                    os.link(
                        temp_out.name,
                        output_file.name,
                        src_dir_fd=output_parent_fd,
                        dst_dir_fd=output_parent_fd,
                        follow_symlinks=False,
                    )
                    os.unlink(temp_out.name, dir_fd=output_parent_fd)
                    os.fsync(output_parent_fd)
                except OSError as error:
                    raise SalvageError(
                        f"Salvage publication failed or durability uncertain: {error}"
                    ) from error

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
        work=None,
        max_json_depth: int = 16,
    ) -> tuple[int, int, list[str], int, int, int, bool]:
        from repo_catalog.adapters.sqlite.ref_salvage import _validate_source_shape

        if work is None:
            work = RecoveryWorkBudget(work_limits={"input_records": max_records})
        unreadable: list[str] = []
        clean = 0
        partial = 0
        corrupt = 0
        written_records = 0
        written_bytes = 0
        stopped_due_to_limits = False

        conn = None
        vm_reserved = False
        vm_steps = [0]
        vm_allowance = 0
        try:
            try:
                conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
                register_functions(conn)
                remaining = work._max["input_bytes"] - work.usage["input_bytes"]
                conn.setlimit(
                    sqlite3.SQLITE_LIMIT_LENGTH,
                    max(65536, min(max_payload_bytes * 4, max(65536, remaining))),
                )
                conn.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 512)
                conn.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 256 * 1024)

                def authorizer(action, _arg1, arg2, _database, origin):
                    # Context's legitimate schema contains generated columns
                    # using application functions that Python cannot mark
                    # SQLITE_INNOCUOUS. Inspect their descriptors but never
                    # invoke those expressions, views, triggers or UDFs.
                    if origin is not None:
                        return sqlite3.SQLITE_DENY
                    if action == sqlite3.SQLITE_FUNCTION and arg2 not in (
                        "typeof",
                        "octet_length",
                        "like",
                    ):
                        return sqlite3.SQLITE_DENY
                    return sqlite3.SQLITE_OK

                conn.set_authorizer(authorizer)
                unit = "legacy_source_vm_steps"
                vm_allowance = work._max[unit] - work.usage[unit]
                if vm_allowance <= 0:
                    raise CoreFailure("BUDGET", unit, "finite SQLite VM budget")
                work.require(unit, vm_allowance)
                vm_reserved = True

                def progress():
                    vm_steps[0] += 1
                    return int(vm_steps[0] > vm_allowance)

                conn.set_progress_handler(progress, 1)
                conn.execute("PRAGMA query_only=ON")
                if store_name == "core":
                    conn.execute("PRAGMA trusted_schema=OFF")
                # Names come from the packaged P1 manifest, never from the
                # recovered schema. Arbitrary tables have no typed retention
                # purpose and must not become a generic body archive.
                known_tables = frozenset(
                    json.loads(_p1_resource("fingerprints.json"))["stores"][store_name][
                        "tables"
                    ]
                )
                remaining_bytes = work._max["input_bytes"] - work.usage["input_bytes"]
                remaining_units = (
                    work._max["metadata_units"] - work.usage["metadata_units"]
                )
                listing_limit = min(
                    max_records + 1, remaining_bytes // 288, remaining_units
                )
                if listing_limit <= 0:
                    raise CoreFailure(
                        "BUDGET", "sqlite_schema", "finite table listing budget"
                    )
                work.require("metadata_units", listing_limit)
                try:
                    work.require("input_bytes", listing_limit * 288)
                except BaseException:
                    work.abandon("metadata_units")
                    raise
                try:
                    listed = conn.execute(
                        "SELECT CASE WHEN octet_length(name)<=256 THEN name END, type "
                        "FROM pragma_table_list WHERE schema='main' AND name NOT LIKE 'sqlite_%' LIMIT ?",
                        (listing_limit,),
                    ).fetchall()
                except BaseException:
                    work.abandon("metadata_units")
                    work.abandon("input_bytes")
                    raise
                work.charge("metadata_units", len(listed))
                work.charge(
                    "input_bytes",
                    sum(
                        len((name or "").encode("utf-8")) + len(kind.encode("utf-8"))
                        for name, kind in listed
                    ),
                )
                tables = []
                for name, kind in listed:
                    if name is None or kind not in ("table", "view"):
                        unreadable.append(
                            f"{store_name}:unsupported or oversized source table"
                        )
                    elif kind == "table":
                        if name in known_tables:
                            tables.append(name)
                        else:
                            unreadable.append(
                                f"{store_name}:{name} (unrecognized source table omitted)"
                            )
                if len(listed) == listing_limit:
                    stopped_due_to_limits = True
            except Exception as e:
                unreadable.append(
                    f"{store_name}:sqlite_schema (enumeration incomplete: {e})"
                )
                confirmed = int(
                    isinstance(e, sqlite3.DatabaseError)
                    and getattr(e, "sqlite_errorcode", None)
                    in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB)
                )
                limited = (
                    isinstance(e, CoreFailure) and e.code in ("BUDGET", "QUERY_BUDGET")
                ) or getattr(e, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT
                return 0, 0, unreadable, 0, 0, confirmed, limited

            if len(tables) > max_records:
                tables = tables[:max_records]
                stopped_due_to_limits = True

            if store_name == "core" and any(
                t in _REF_OBSERVATION_TABLES for t in tables
            ):
                from repo_catalog.adapters.sqlite.ref_salvage import scan_ref_units

                ref_conn = sqlite3.connect(
                    f"file:{db_path.resolve()}?mode=ro", uri=True
                )
                try:
                    ref_scan = scan_ref_units(
                        ref_conn,
                        work,
                        max_records=max_records - records_offset - written_records,
                        max_row_bytes=max_payload_bytes,
                    )
                finally:
                    ref_conn.close()
                unreadable.extend(ref_scan.omissions)
                if ref_scan.exhausted:
                    stopped_due_to_limits = True
                for candidate in ref_scan.candidates:
                    if records_offset + written_records >= max_records:
                        stopped_due_to_limits = True
                        break
                    try:
                        line = _encode_salvage_line(
                            candidate,
                            work,
                            max_payload_bytes * 8 + 8192,
                            max_json_depth,
                        )
                    except CoreFailure as error:
                        if error.code != "BUDGET":
                            raise
                        stopped_due_to_limits = True
                        unreadable.append(
                            "core:RefObservation candidate output exceeds finite budget"
                        )
                        break
                    if bytes_offset + written_bytes + len(line) > max_bytes:
                        stopped_due_to_limits = True
                        break
                    out_f.write(line)
                    written_records += 1
                    written_bytes += len(line)
                    clean += 1

            for table in tables:
                if store_name == "core" and table in _REF_OBSERVATION_TABLES:
                    continue
                if (records_offset + written_records) >= max_records:
                    stopped_due_to_limits = True
                    break
                if (bytes_offset + written_bytes) >= max_bytes:
                    stopped_due_to_limits = True
                    break

                try:
                    quoted_table = '"' + table.replace('"', '""') + '"'
                    # table_info omits generated columns; xinfo inspects every
                    # descriptor before any recovered expression is projected.
                    columns = _validate_source_shape(
                        conn, table, work, allow_generated=store_name == "context"
                    )
                    quoted_columns = ['"' + c.replace('"', '""') + '"' for c in columns]
                    row_size = " + ".join(
                        f"CASE WHEN typeof({c}) IN ('text','blob') THEN octet_length({c}) "
                        f"WHEN {c} IS NULL THEN 0 ELSE 8 END"
                        for c in quoted_columns
                    )
                    projection = ", ".join(
                        f"CASE WHEN ({row_size}) > ? THEN NULL ELSE {c} END AS {c}"
                        for c in quoted_columns
                    )
                    query = f"SELECT {projection}, ({row_size}) FROM {quoted_table} NOT INDEXED LIMIT 1 OFFSET ?"
                    offset = 0
                    while True:
                        if (records_offset + written_records) >= max_records:
                            stopped_due_to_limits = True
                            break
                        if (bytes_offset + written_bytes) >= max_bytes:
                            stopped_due_to_limits = True
                            break
                        available = work._max["input_bytes"] - work.usage["input_bytes"]
                        allowance = min(max_payload_bytes, available)
                        if allowance <= 0:
                            raise CoreFailure(
                                "BUDGET", table, "finite salvage row budget"
                            )
                        scan_cost = offset + 1 + len(columns) * len(columns)
                        work.require("metadata_units", scan_cost)
                        try:
                            work.require("input_bytes", allowance)
                        except BaseException:
                            work.abandon("metadata_units")
                            raise
                        try:
                            work.require("input_records", 1)
                        except BaseException:
                            work.abandon("metadata_units")
                            work.abandon("input_bytes")
                            raise
                        try:
                            row = conn.execute(
                                query, (allowance,) * len(columns) + (offset,)
                            ).fetchone()
                        except BaseException:
                            work.abandon("metadata_units")
                            work.abandon("input_bytes")
                            work.abandon("input_records")
                            raise
                        work.charge("metadata_units", scan_cost)
                        work.charge("input_records", int(row is not None))
                        if row is None:
                            work.charge("input_bytes", 0)
                            break
                        offset += 1
                        row_bytes = row[-1]
                        if type(row_bytes) is not int or row_bytes < 0:
                            work.abandon("input_bytes")
                            raise ValueError("Invalid stored row size")
                        work.charge(
                            "input_bytes", row_bytes if row_bytes <= allowance else 0
                        )
                        if row_bytes > conn.getlimit(sqlite3.SQLITE_LIMIT_LENGTH):
                            unreadable.append(
                                f"{store_name}:{table} (source row too big for finite SQLite limit)"
                            )
                            break
                        if row_bytes > allowance and allowance < max_payload_bytes:
                            raise CoreFailure(
                                "BUDGET", table, "finite salvage input budget"
                            )
                        row_dict = dict(zip(columns, row[:-1], strict=True))
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
                            line = _encode_salvage_line(
                                cand_record,
                                work,
                                max_payload_bytes * 8 + 8192,
                                max_json_depth,
                            )
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
                        withheld_reason = None
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
                                line = _encode_salvage_line(
                                    cand_record,
                                    work,
                                    max_payload_bytes * 8 + 8192,
                                    max_json_depth,
                                )
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
                            }
                            try:
                                if row_dict.get("native_type") not in (
                                    "commit",
                                    "tree",
                                    "tag",
                                ) or not uuid4(row_dict.get("physical_copy_uuidv4")):
                                    raise ValueError("unsupported native type or copy")
                                with account_verification(work):
                                    NativeObject(
                                        OID(
                                            row_dict["object_format"],
                                            row_dict["full_oid"],
                                        ),
                                        row_dict["native_type"],
                                        raw_body,
                                        row_dict["size"],
                                        row_dict["digest_sha256"],
                                    ).validate()
                                    parse_metadata(
                                        row_dict["object_format"],
                                        row_dict["native_type"],
                                        raw_body,
                                    )
                            except CoreFailure as error:
                                if error.code in ("BUDGET", "QUERY_BUDGET"):
                                    raise
                                withheld_reason = (
                                    "Unverified structural metadata body omitted"
                                )
                            except (ValueError, TypeError, KeyError, AttributeError):
                                withheld_reason = (
                                    "Unverified structural metadata body omitted"
                                )
                            if withheld_reason is None:
                                payload["body_base64"] = _encode_salvage_base64(
                                    raw_body, work
                                )
                        if store_name == "context" and table == "text_bodies":
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
                            elif isinstance(row_dict.get("provenance"), str):
                                orig_provenance = {"value": row_dict["provenance"]}

                            for k, v in row_dict.items():
                                if isinstance(v, bytes):
                                    # Unknown binary columns have no typed role
                                    # or proof. Do not stage them as bodies.
                                    withheld_reason = "Untyped binary fields omitted"
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
                            "extraction_status": (
                                ExtractionStatus.PARTIAL.value
                                if withheld_reason is not None
                                else ExtractionStatus.CLEAN.value
                            ),
                            "error": (withheld_reason),
                        }

                        line = _encode_salvage_line(
                            cand_record,
                            work,
                            max_payload_bytes * 8 + 8192,
                            max_json_depth,
                        )
                        line_bytes = len(line.encode("utf-8"))

                        if (bytes_offset + written_bytes + line_bytes) > max_bytes:
                            stopped_due_to_limits = True
                            break

                        out_f.write(line)
                        written_records += 1
                        written_bytes += line_bytes
                        if withheld_reason is not None:
                            partial += 1
                            unreadable.append(
                                f"{store_name}:{table} ({withheld_reason})"
                            )
                        else:
                            clean += 1
                except CoreFailure as error:
                    if error.code in ("BUDGET", "QUERY_BUDGET"):
                        unreadable.append(
                            f"{store_name}:{table} (finite salvage work budget)"
                        )
                        stopped_due_to_limits = True
                        break
                    raise
                except Exception as e:
                    unreadable.append(
                        f"{store_name}:{table} (enumeration incomplete: {e})"
                    )
                    if isinstance(e, sqlite3.DatabaseError) and getattr(
                        e, "sqlite_errorcode", None
                    ) in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB):
                        corrupt += 1
                    if getattr(e, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT:
                        stopped_due_to_limits = True
                        break
        finally:
            if conn:
                conn.set_progress_handler(None, 0)
                conn.close()
            if vm_reserved:
                work.charge("legacy_source_vm_steps", min(vm_steps[0], vm_allowance))

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
                or manifest_data.get("manifest_version") != 2
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

                baseline = {
                    "version": 1,
                    "backup_id": manifest_data["backup_id"],
                    "scope": scope.value,
                    "repository_uuidv4": core_repo_uuid,
                    "catalog_instance_uuidv4": core_inst_uuid,
                    "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                }
                with (staging_dir / "p1-restored-baseline.json").open("xb") as receipt:
                    receipt.write(
                        (
                            json.dumps(baseline, sort_keys=True, separators=(",", ":"))
                            + "\n"
                        ).encode("utf-8")
                    )
                    receipt.flush()
                    os.fsync(receipt.fileno())
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
        if table != "retained_metadata":
            raise ValueError("metadata copy reader requires retained_metadata")
        with catalog_gate(directory, exclusive=True):
            assert_catalog_not_stopped(directory)
            conn = p1_connect(directory / "core.sqlite3", "core")
            try:
                conn.execute("BEGIN")
                work.require("metadata_units", 1)
                size_row = conn.execute(
                    "SELECT length(body) FROM retained_metadata WHERE object_format=? AND full_oid=? AND physical_copy_uuidv4=?",
                    key,
                ).fetchone()
                work.charge("metadata_units", 1)
                if size_row is None:
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
                row = conn.execute(
                    "SELECT CASE WHEN length(native_type)<=6 THEN native_type END,body,size,CASE WHEN length(digest_sha256)=64 THEN digest_sha256 END FROM retained_metadata WHERE object_format=? AND full_oid=? AND physical_copy_uuidv4=?",
                    key,
                ).fetchone()
                native_type, body, size, digest = row
                work.charge("input_bytes", sum(size_row))
                try:
                    native = NativeObject(
                        OID(key[0], key[1]), native_type, body, size, digest
                    )
                    with account_verification(work):
                        native.validate()
                        parse_metadata(key[0], native_type, body)
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
        fresh_destination_dir = Path(fresh_destination_dir).absolute()
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
        limits.setdefault("json_decode_bytes", b.max_input_bytes * 3)
        limits.setdefault(
            "pending_candidate_bytes",
            min(b.max_input_bytes, b.max_payload_bytes * 8 + 8192),
        )
        limits.setdefault("identity_read_rows", b.max_input_records * 2)
        limits.setdefault("identity_read_bytes", b.max_input_records * 144)
        limits.update(
            input_scan_bytes=b.max_input_bytes, input_records=b.max_input_records
        )
        directory_fd = _open_directory_nofollow(fresh_destination_dir)
        try:
            for name in ("core.sqlite3", "context.sqlite3"):
                try:
                    info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                except FileNotFoundError:
                    if name == "core.sqlite3":
                        raise RecoveryError(
                            "Fresh destination is missing Core"
                        ) from None
                    continue
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise RecoveryError(
                        "Fresh authority file must be regular without aliases"
                    )
            pinned = Path(f"/proc/self/fd/{directory_fd}")
            with recovery_request(pinned, request_id, b, limits) as request:
                result = self._merge_salvage_request(
                    pinned,
                    salvage_file,
                    b,
                    request,
                    directory_fd=directory_fd,
                    authorization=authorization,
                    admission=admission,
                    fault_stage=fault_stage,
                )
            _assert_directory_identity(
                fresh_destination_dir, directory_fd, label="Recovery destination"
            )
            return replace(result, destination_path=str(fresh_destination_dir))
        finally:
            os.close(directory_fd)

    def _merge_salvage_request(
        self,
        fresh_destination_dir,
        salvage_file,
        b,
        request,
        *,
        directory_fd,
        authorization=None,
        admission=None,
        fault_stage=None,
    ):
        work_budget = RecoveryWorkBudget(
            note_bytes=b.max_payload_bytes,
            work_limits={
                "json_decode_bytes": b.max_input_bytes * 3,
                "pending_candidate_bytes": min(
                    b.max_input_bytes, b.max_payload_bytes * 8 + 8192
                ),
                "identity_read_rows": b.max_input_records * 2,
                "identity_read_bytes": b.max_input_records * 144,
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
        ref_baseline_checked = False
        pending_candidates = []

        # Connect to fresh core via GitCore production admission interface
        core_db = fresh_destination_dir / "core.sqlite3"
        core = GitCore(core_db)

        # Connect to fresh context if present
        ctx_db = fresh_destination_dir / "context.sqlite3"
        ctx_store = None
        ctx_conn = None
        ctx_identity = None
        ctx_auth = authorization
        ctx_admission = admission
        if ctx_db.exists() and not budget_already_exhausted:
            ctx_conn = p1_connect(ctx_db, "context")
            try:
                ctx_identity = _context_identity_for_salvage(
                    ctx_conn, core, work_budget
                )
            except BaseException:
                ctx_conn.close()
                core.close()
                raise
            if ctx_auth is None or ctx_admission is None:
                repo_id = ctx_identity[0]
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

        def _defer_candidate(candidate_id, kind, raw):
            nonlocal budget_exhausted, unprocessed
            try:
                work_budget.require("pending_candidate_bytes", len(raw))
                work_budget.charge("pending_candidate_bytes", len(raw))
            except CoreFailure as error:
                budget_exhausted = True
                unprocessed += 1
                rejections.append(
                    {
                        "candidate_id": candidate_id,
                        "reason": f"Work budget exhausted: {error}",
                    }
                )
                return
            pending_candidates.append((candidate_id, kind, raw))

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
                    decode_work = 3 * len(line)
                    try:
                        work_budget.require("json_decode_bytes", decode_work)
                    except CoreFailure as error:
                        settle_input("input_records", 1)
                        budget_exhausted = True
                        unprocessed += 1
                        rejections.append({"reason": f"Input incomplete: {error}"})
                        break
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
                        work_budget.charge("json_decode_bytes", decode_work)
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

                    # Ref units contain their original dependencies and are
                    # rechecked at the destination, independently of line order.
                    if c_type in (
                        "ref_subject",
                        "ref_claim",
                        "ref_enumeration",
                        "ref_mapping_content",
                        "ref_mapping",
                        "ref_group",
                        "ref_evidence",
                        "ref_note",
                        "ref_coverage",
                        "ref_coverage_proof",
                    ):
                        from repo_catalog.adapters.sqlite.ref_salvage import (
                            admit_ref_unit_atomic,
                        )

                        try:
                            if not ref_baseline_checked:
                                try:
                                    baseline = _read_restored_baseline(
                                        fresh_destination_dir,
                                        directory_fd=directory_fd,
                                        work=work_budget,
                                    )
                                except (
                                    OSError,
                                    RecoveryError,
                                    RestoreValidationError,
                                ) as error:
                                    raise RecoveryError(
                                        "Ref salvage requires a validated fresh backup restore"
                                    ) from error
                                work_budget.require("metadata_units", 2)
                                work_budget.charge("metadata_units", 2)
                                work_budget.require("input_bytes", 72)
                                try:
                                    repo, instance = core.catalog_identity()
                                except BaseException:
                                    work_budget.abandon("input_bytes")
                                    raise
                                work_budget.charge("input_bytes", 72)
                                if (repo, instance) != (
                                    baseline["repository_uuidv4"],
                                    baseline["catalog_instance_uuidv4"],
                                ):
                                    raise RecoveryError(
                                        "Restored baseline identity differs from destination"
                                    )
                                if (
                                    baseline["scope"] == BackupScope.PAIRED.value
                                ) != ctx_db.exists():
                                    raise RecoveryError(
                                        "Restored baseline scope differs from destination"
                                    )
                                if ctx_identity is not None and ctx_identity != (
                                    repo,
                                    instance,
                                ):
                                    core._integrity_stop(
                                        "Core and Context identities differ"
                                    )
                                ref_baseline_checked = True
                            was_replay = admit_ref_unit_atomic(
                                fresh_destination_dir, c_type, payload, work_budget
                            )
                            if was_replay is None:
                                _defer_candidate(cand_id, c_type, line)
                            elif was_replay:
                                replayed += 1
                            else:
                                admitted += 1
                        except CoreFailure as error:
                            if error.code in (
                                "AUTHORITATIVE_CORRUPTION",
                                "RECOVERY_STOP",
                            ):
                                raise
                            if error.code in ("BUDGET", "QUERY_BUDGET"):
                                budget_exhausted = True
                                unprocessed += 1
                                rejections.append(
                                    {
                                        "candidate_id": cand_id,
                                        "reason": f"Work budget exhausted: {error}",
                                    }
                                )
                            elif error.code in (
                                "MISSING_DEPENDENCY",
                                "OBSERVATION_UNAVAILABLE",
                            ):
                                _defer_candidate(cand_id, c_type, line)
                            else:
                                rejected += 1
                                rejections.append(
                                    {
                                        "candidate_id": cand_id,
                                        "reason": f"Ref admission error: {error}",
                                    }
                                )
                        except (
                            ValueError,
                            TypeError,
                            KeyError,
                            sqlite3.IntegrityError,
                        ) as error:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": f"Invalid ref candidate: {error}",
                                }
                            )
                        continue

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
                    if c_type in (
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

                    # 6. Admitting Git Metadata Objects (repositories, git_objects)
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
            # Each successful candidate leaves the queue permanently. Retry
            # until a whole pass makes no progress; every reparse and admission
            # is charged to the same durable request budget.
            pending = pending_candidates
            while pending:
                remaining = []
                progressed = False
                for candidate_id, kind, raw in pending:
                    if budget_exhausted:
                        remaining.append((candidate_id, kind, raw))
                        continue
                    decode_work = 3 * len(raw)
                    try:
                        work_budget.require("json_decode_bytes", decode_work)
                        try:
                            delayed = _bounded_json_loads(raw, b)
                        finally:
                            work_budget.charge("json_decode_bytes", decode_work)
                        was_replay = admit_ref_unit_atomic(
                            fresh_destination_dir, kind, delayed["payload"], work_budget
                        )
                        if was_replay is None:
                            remaining.append((candidate_id, kind, raw))
                        else:
                            progressed = True
                            if was_replay:
                                replayed += 1
                            else:
                                admitted += 1
                    except CoreFailure as error:
                        if error.code in ("AUTHORITATIVE_CORRUPTION", "RECOVERY_STOP"):
                            raise
                        if error.code in ("BUDGET", "QUERY_BUDGET"):
                            budget_exhausted = True
                            unprocessed += 1
                            rejections.append(
                                {
                                    "candidate_id": candidate_id,
                                    "reason": f"Work budget exhausted: {error}",
                                }
                            )
                        elif error.code in (
                            "MISSING_DEPENDENCY",
                            "OBSERVATION_UNAVAILABLE",
                        ):
                            remaining.append((candidate_id, kind, raw))
                        else:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": candidate_id,
                                    "reason": f"Ref admission error: {error}",
                                }
                            )
                    except (
                        ValueError,
                        TypeError,
                        KeyError,
                        sqlite3.IntegrityError,
                    ) as error:
                        rejected += 1
                        rejections.append(
                            {
                                "candidate_id": candidate_id,
                                "reason": f"Invalid ref candidate: {error}",
                            }
                        )
                if budget_exhausted or not progressed:
                    deferred += len(remaining)
                    reason = (
                        "Dependency retry not attempted after budget exhaustion"
                        if budget_exhausted
                        else "Original dependency remains unavailable"
                    )
                    rejections.extend(
                        {"candidate_id": candidate_id, "reason": reason}
                        for candidate_id, _, _ in remaining
                    )
                    break
                pending = remaining
        finally:
            try:
                _save_budget_state()
            finally:
                if ctx_conn:
                    ctx_conn.close()
                core.close()

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

            try:
                baseline = _read_restored_baseline(
                    advertised_catalog_dir, directory_fd=directory_fd
                )
            except (OSError, RecoveryError, RestoreValidationError) as error:
                raise ActivationError(
                    "A validated fresh backup restore is required"
                ) from error

            for database in (core_db, fresh_catalog_dir / "context.sqlite3"):
                if database.is_symlink() or (
                    database.exists() and database.stat().st_nlink != 1
                ):
                    raise ActivationError(
                        "Authoritative file symlink/hardlink forbidden"
                    )
            # Validation failures cannot publish a locator. Only confirmed
            # stored corruption persists the target stop, not a work limit or
            # an environmental failure.
            try:
                self._validate_and_summarize_core(core_db)
                repo_uuid, inst_uuid = self._extract_identities(core_db, "core")
            except (BackupValidationError, SchemaError, sqlite3.DatabaseError) as error:
                classification = _confirmed_integrity_failure(error)
                if classification:
                    stop_catalog(
                        fresh_catalog_dir,
                        str(error),
                        details={"store": "core", "classification": classification},
                    )
                raise ActivationError("Fresh Core validation failed") from error
            if (repo_uuid, inst_uuid) != (
                baseline["repository_uuidv4"],
                baseline["catalog_instance_uuidv4"],
            ):
                raise ActivationError("Restored baseline identity differs from catalog")

            if fault_stage == "between_core_and_context":
                raise ActivationError("Injected failure between core and context")

            # Validate context if present
            ctx_db = fresh_catalog_dir / "context.sqlite3"
            if (baseline["scope"] == BackupScope.PAIRED.value) != ctx_db.exists():
                raise ActivationError("Restored baseline scope differs from catalog")
            if ctx_db.exists():
                try:
                    self._validate_and_summarize_context(ctx_db)
                    ctx_repo_uuid, ctx_inst_uuid = self._extract_identities(
                        ctx_db, "context"
                    )
                except (
                    BackupValidationError,
                    SchemaError,
                    sqlite3.DatabaseError,
                ) as error:
                    classification = _confirmed_integrity_failure(error)
                    if classification:
                        stop_catalog(
                            fresh_catalog_dir,
                            str(error),
                            details={
                                "store": "context",
                                "classification": classification,
                            },
                        )
                    raise ActivationError("Fresh Context validation failed") from error
                if repo_uuid != ctx_repo_uuid or inst_uuid != ctx_inst_uuid:
                    stop_catalog(
                        fresh_catalog_dir,
                        "Core and Context identities differ",
                        details={
                            "store": "core+context",
                            "classification": "authoritative_data",
                        },
                    )
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
                source_backup_id=baseline["backup_id"],
                reconstructed_stores=["operational", "search"],
                timestamp_us=int(time.time() * 1_000_000),
                clean_operational=True,
                search_derivative_state="initialized_empty",
            )
