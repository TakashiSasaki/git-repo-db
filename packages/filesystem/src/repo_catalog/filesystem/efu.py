"""Streaming EFU-compatible CSV; independent of stores and live files."""

from __future__ import annotations

import base64
import csv
from collections.abc import Callable, Iterable, Mapping
from typing import TextIO

from .models import ExportResult, FileEntry, FilesystemError

STANDARD_COLUMNS = (
    "Filename",
    "Size",
    "Date Modified",
    "Date Created",
    "Attributes",
    "SHA256",
)
EXTRA_COLUMNS = (
    "RepoCatalog.Namespace",
    "RepoCatalog.Scan",
    "RepoCatalog.Kind",
    "RepoCatalog.RelativePathBase64",
    "RepoCatalog.HashStatus",
    "RepoCatalog.Error",
    "RepoCatalog.Mode",
    "RepoCatalog.ModifiedNanoseconds",
    "RepoCatalog.CreatedNanoseconds",
    "RepoCatalog.OriginalPath",
    "RepoCatalog.OriginalPathBase64",
    "RepoCatalog.LinkTargetBase64",
    "RepoCatalog.ObservedMicroseconds",
)


def _filetime(value):
    if value is None:
        return ""
    result = value // 100 + 116444736000000000
    if not 0 <= result < 1 << 64:
        raise FilesystemError("native timestamp cannot be represented by FILETIME")
    return result


def export_efu(
    entries: Iterable[FileEntry],
    output: TextIO,
    *,
    extra_columns: Iterable[str] = (),
    row_enricher: Callable[[FileEntry], Mapping[str, object]] | None = None,
    skip_non_utf8: bool = False,
    path_map: tuple[str, str] | None = None,
) -> ExportResult:
    """Serialize selected observations without accessing original files.

    Caller owns atomic output publication. Arbitrary custom columns require a
    row_enricher; standard columns can never be overridden by enrichment.
    """
    columns = tuple(extra_columns)
    if len(set(STANDARD_COLUMNS + columns)) != len(STANDARD_COLUMNS + columns):
        raise FilesystemError("duplicate or reserved EFU column")
    if any(not isinstance(c, str) or not c or "\x00" in c for c in columns):
        raise FilesystemError("invalid EFU column")
    if row_enricher is None and any(c not in EXTRA_COLUMNS for c in columns):
        raise FilesystemError("unknown EFU metadata column")
    if path_map is not None and (
        len(path_map) != 2 or not path_map[0] or not path_map[1]
    ):
        raise FilesystemError(
            "path mapping requires nonempty source and destination roots"
        )
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(STANDARD_COLUMNS + columns)
    seen: set[str] = set()
    written = skipped = 0
    for entry in entries:
        try:
            filename = entry.absolute_path.decode("utf-8", errors="strict")
            if "\0" in filename:
                raise FilesystemError("NUL is not a valid filename character")
        except UnicodeError as exc:
            if skip_non_utf8:
                skipped += 1
                continue
            raise FilesystemError(
                "filename is not representable; use explicit skip_non_utf8"
            ) from exc
        if path_map is not None:
            source_original, target = path_map
            source = source_original.rstrip("/\\") or source_original
            if filename.rstrip("/\\") == source.rstrip("/\\"):
                filename = target
            elif filename.startswith(source.rstrip("/\\") + "/") or filename.startswith(
                source.rstrip("/\\") + "\\"
            ):
                suffix = filename[len(source.rstrip("/\\")) + 1 :]
                separator = (
                    "\\"
                    if "\\" in target or (len(target) >= 2 and target[1] == ":")
                    else "/"
                )
                if "\\" in source or (len(source) >= 2 and source[1] == ":"):
                    suffix = suffix.replace("\\", separator)
                else:
                    suffix = suffix.replace("/", separator)
                filename = target.rstrip("/\\") + separator + suffix
            else:
                raise FilesystemError("path is outside the explicit mapping source")
        if filename in seen:
            raise FilesystemError("duplicate EFU filename")
        seen.add(filename)
        attrs = entry.attributes
        if attrs is None:
            attrs = (
                16
                if entry.kind == "directory"
                else 1024
                if entry.kind == "symlink"
                else 0
            )
        if entry.kind == "directory":
            attrs |= 16
        metadata = {
            "RepoCatalog.Namespace": entry.namespace_uuid,
            "RepoCatalog.Scan": entry.scan_uuid,
            "RepoCatalog.Kind": entry.kind,
            "RepoCatalog.RelativePathBase64": base64.b64encode(
                entry.relative_path
            ).decode("ascii"),
            "RepoCatalog.HashStatus": entry.hash_status,
            "RepoCatalog.Error": entry.error,
            "RepoCatalog.Mode": entry.mode,
            "RepoCatalog.ModifiedNanoseconds": entry.mtime_ns,
            "RepoCatalog.CreatedNanoseconds": entry.birthtime_ns,
            "RepoCatalog.OriginalPath": entry.absolute_path.decode("utf-8"),
            "RepoCatalog.OriginalPathBase64": base64.b64encode(
                entry.absolute_path
            ).decode("ascii"),
            "RepoCatalog.LinkTargetBase64": base64.b64encode(entry.link_target).decode(
                "ascii"
            )
            if entry.link_target is not None
            else None,
            "RepoCatalog.ObservedMicroseconds": entry.observed_us,
        }
        if row_enricher is not None:
            extra = row_enricher(entry)
            if set(extra) & set(STANDARD_COLUMNS):
                raise FilesystemError("enrichment cannot replace standard columns")
            metadata.update(extra)
        writer.writerow(
            [
                filename,
                entry.size,
                _filetime(entry.mtime_ns),
                _filetime(entry.birthtime_ns),
                attrs,
                entry.sha256,
            ]
            + [metadata.get(c) for c in columns]
        )
        written += 1
    return ExportResult(written, skipped)
