"""Compose independent catalogs without a cross-database transaction or owner."""

from __future__ import annotations

import json
import ntpath
import os
import posixpath
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from repo_catalog.filesystem import FilesystemCatalog, ScanResult, export_efu
from repo_catalog.worktrees import DiscoveryResult, WorktreeCatalog

GIT_COLUMNS = (
    "RepoCatalog.Worktree",
    "RepoCatalog.GitDir",
    "RepoCatalog.CommonDir",
    "RepoCatalog.Branch",
    "RepoCatalog.HeadOID",
    "RepoCatalog.Repository",
    "RepoCatalog.TopologyObservation",
    "RepoCatalog.TopologyStatus",
)


@dataclass(frozen=True)
class LocalScanResult:
    """Independent committed observations; a failure never rolls them all back."""

    discoveries: tuple[DiscoveryResult, ...]
    scans: tuple[ScanResult, ...]
    errors: tuple[str, ...]

    @property
    def status(self) -> str:
        return (
            "partial"
            if self.errors
            or any(scan.status != "complete" for scan in self.scans)
            or any(d.status not in {"complete", "not_git"} for d in self.discoveries)
            else "complete"
        )


def _path(value: str | bytes | os.PathLike) -> Path:
    return Path(os.path.abspath(os.fsdecode(value)))


def _key(value: str | bytes | os.PathLike) -> bytes:
    # Preserve case: Windows can contain directories with case-sensitive names.
    return os.fsencode(_path(value))


def _within(child: bytes, parent: bytes, *, dialect: str | None = None) -> bool:
    paths = ntpath if dialect == "nt" else posixpath if dialect == "posix" else os.path
    try:
        return paths.commonpath((child, parent)) == parent
    except ValueError:
        return False


def _display(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="backslashreplace")
    return value


def _physical_key(path: Path):
    """Deduplicate observed aliases without rewriting their recorded spelling."""
    try:
        metadata = path.stat()
        if metadata.st_ino:
            return ("inode", metadata.st_dev, metadata.st_ino)
    except OSError:
        pass
    return ("path", _key(path))


def _git_marker(root: bytes, git_dir: bytes | None) -> bytes | None:
    """Recognize an actual directory/pointer; '.git' is otherwise ordinary data."""
    if git_dir is None:
        return None
    marker = _path(root) / ".git"
    actual = _path(git_dir)
    try:
        if marker.is_dir() and _physical_key(marker) == _physical_key(actual):
            return _key(marker)
        if marker.is_file():
            with marker.open("rb") as stream:
                pointer = stream.read(65537)
            if len(pointer) <= 65536 and pointer.startswith(b"gitdir: "):
                target = Path(os.fsdecode(pointer[8:].rstrip(b"\r\n")))
                if not target.is_absolute():
                    target = marker.parent / target
                if _physical_key(target) == _physical_key(actual):
                    return _key(marker)
    except OSError:
        pass
    return None


def _root_exclusions(paths: set[bytes], root: Path) -> set[bytes]:
    """Map known artifacts through a selected root's aliased ancestor path."""
    root_key = _key(root)
    physical_root = os.fsencode(os.path.realpath(root))
    result = set()
    for path in paths:
        if path != root_key and _within(path, root_key):
            result.add(path)
        physical_path = os.fsencode(os.path.realpath(path))
        if physical_path != physical_root and _within(physical_path, physical_root):
            result.add(
                os.path.join(root_key, os.path.relpath(physical_path, physical_root))
            )
    return result


class LocalCatalog:
    """Optional application service over two separately initialized stores."""

    def __init__(
        self, filesystem: FilesystemCatalog, worktrees: WorktreeCatalog | None = None
    ) -> None:
        self.filesystem = filesystem
        self.worktrees = worktrees

    @classmethod
    def initialize(
        cls,
        filesystem_database: Path,
        worktree_database: Path,
        *,
        namespace_uuid: str | None = None,
    ) -> LocalCatalog:
        filesystem_database = Path(filesystem_database)
        worktree_database = Path(worktree_database)
        if _key(filesystem_database) == _key(worktree_database):
            raise ValueError("Filesystem and worktree databases must be distinct")
        # Check both destinations before the first independent initialization.
        if filesystem_database.exists() or worktree_database.exists():
            raise FileExistsError("Initialization requires two fresh database paths")
        filesystem = FilesystemCatalog.initialize(
            filesystem_database, namespace_uuid=namespace_uuid
        )
        try:
            worktrees = WorktreeCatalog.initialize(
                worktree_database, namespace_uuid=filesystem.namespace_uuid
            )
        except BaseException:
            filesystem.close()
            # A valid first store is preserved rather than deleted on failure.
            raise
        return cls(filesystem, worktrees)

    @classmethod
    def open(
        cls,
        filesystem_database: Path,
        worktree_database: Path | None = None,
        *,
        readonly: bool = False,
    ) -> LocalCatalog:
        filesystem = FilesystemCatalog.open(filesystem_database, readonly=readonly)
        try:
            worktrees = (
                WorktreeCatalog.open(worktree_database, readonly=readonly)
                if worktree_database is not None
                else None
            )
        except BaseException:
            filesystem.close()
            raise
        return cls(filesystem, worktrees)

    def close(self) -> None:
        try:
            self.filesystem.close()
        finally:
            if self.worktrees is not None:
                self.worktrees.close()

    def __enter__(self) -> LocalCatalog:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def _catalog_paths(self) -> set[bytes]:
        paths: set[bytes] = set()
        for catalog in (self.filesystem, self.worktrees):
            if catalog is not None:
                db = os.fsdecode(catalog.database)
                paths.update(
                    _key(db + suffix) for suffix in ("", "-wal", "-shm", "-journal")
                )
        return paths

    def scan(
        self, roots: Iterable[Path], *, include_git_admin: bool = False
    ) -> LocalScanResult:
        if self.worktrees is None:
            raise ValueError("Worktree discovery requires an explicitly opened catalog")
        roots = tuple(roots)
        if not roots:
            raise ValueError("Select at least one filesystem root")
        discoveries: list[DiscoveryResult] = []
        scans: list[ScanResult] = []
        errors: list[str] = []
        targets: dict[bytes, Path] = {}
        target_identities = set()
        inspected_paths: set[bytes] = set()
        inspected_roots: set[tuple] = set()
        admin_paths: set[bytes] = set()
        always_exclude = self._catalog_paths()

        def add_target(root: Path) -> None:
            identity = _physical_key(root)
            if identity not in target_identities:
                targets[_key(root)] = root
                target_identities.add(identity)

        def discover(path: Path, *, expand: bool) -> DiscoveryResult | None:
            try:
                result = self.worktrees.discover(path, expand=expand)
            except OSError as error:
                errors.append(f"topology:{path!s}:{type(error).__name__}:{error}")
                return None
            discoveries.append(result)
            inspected_paths.add(_key(path))
            for entry in result.entries:
                # Expanded entries with no error were inspected by Git already.
                # Do not suppress retries for unavailable or changed worktrees.
                if entry.error is None:
                    inspected_roots.add(_physical_key(_path(entry.root_path)))
                if entry.git_dir:
                    admin_paths.add(_key(entry.git_dir))
                if entry.common_dir:
                    admin_paths.add(_key(entry.common_dir))
                if not entry.bare:
                    marker = _git_marker(entry.root_path, entry.git_dir)
                    if marker is not None:
                        admin_paths.add(marker)
            return result

        for requested in roots:
            root = _path(requested)
            result = discover(root, expand=True)
            if result is None or not result.entries:
                add_target(root)
                continue
            for entry in result.entries:
                if not entry.bare:
                    add_target(_path(entry.root_path))

        for root_key, root in targets.items():
            # Metadata-only traversal discovers separate nested Git directories.
            # It never follows symlink/junction directories or reads file bodies.
            def walk_error(error: OSError) -> None:
                errors.append(f"topology-walk:{error.filename}:{type(error).__name__}")

            for directory, dirnames, filenames in os.walk(
                root, followlinks=False, onerror=walk_error
            ):
                current = _path(directory)
                if ".git" in dirnames or ".git" in filenames:
                    if (
                        _key(current) not in inspected_paths
                        and _physical_key(current) not in inspected_roots
                    ):
                        discover(current, expand=False)
                excluded = _root_exclusions(always_exclude | admin_paths, root)
                dirnames[:] = [
                    name
                    for name in dirnames
                    if not (current / name).is_symlink()
                    and not (current / name).is_junction()
                    and not any(_within(_key(current / name), p) for p in excluded)
                ]
            excludes = _root_exclusions(
                always_exclude | (set() if include_git_admin else admin_paths), root
            )
            try:
                scan = self.filesystem.scan(
                    root, exclude_paths=tuple(_path(path) for path in sorted(excludes))
                )
            except OSError as error:
                errors.append(f"scan:{root!s}:{type(error).__name__}:{error}")
                continue
            scans.append(scan)
            for discovery in discoveries:
                for entry in discovery.entries:
                    if entry.bare or not _within(_key(entry.root_path), root_key):
                        continue
                    try:
                        self.worktrees.record_scan_reference(
                            discovery.observation_uuid,
                            entry.root_path,
                            scan.namespace_uuid,
                            scan.scan_uuid,
                        )
                    except OSError as error:
                        errors.append(
                            f"scan-reference:{scan.scan_uuid}:{type(error).__name__}:{error}"
                        )
        return LocalScanResult(tuple(discoveries), tuple(scans), tuple(errors))

    def export_efu(
        self,
        scan_uuids: Iterable[str],
        destination: Path,
        *,
        allow_partial: bool = False,
        extra_columns: Iterable[str] = (),
        skip_non_utf8: bool = False,
        path_map: tuple[str, str] | None = None,
    ):
        """Export stored facts only; topology is optional immutable enrichment."""
        selected = tuple(dict.fromkeys(scan_uuids))
        if not selected:
            raise ValueError("Select at least one filesystem scan")
        destination = _path(destination)
        for protected in self._catalog_paths():
            if _key(destination) == protected or (
                destination.exists()
                and _path(protected).exists()
                and os.path.samefile(destination, _path(protected))
            ):
                raise ValueError(
                    "An export cannot overwrite a catalog or SQLite sidecar"
                )
        overlays = {}
        for scan_uuid in selected:
            scan = self.filesystem.get_scan(scan_uuid)
            if scan.status != "complete" and not allow_partial:
                raise ValueError(
                    f"Scan {scan_uuid} is {scan.status}; select allow_partial"
                )
            observations = []
            if self.worktrees is not None:
                references = self.worktrees.scan_references(
                    scan.namespace_uuid, scan.scan_uuid
                )
                for reference in references:
                    discovery = self.worktrees.get_discovery(
                        reference["observation_uuid"]
                    )
                    for entry in discovery.entries:
                        if entry.root_path == reference["root_path"]:
                            observations.append((discovery, entry))
            overlays[scan_uuid] = observations

        def enrich(entry):
            candidates = [
                (discovery, topology)
                for discovery, topology in overlays[entry.scan_uuid]
                if _within(
                    entry.absolute_path,
                    topology.root_path,
                    dialect=self.worktrees.path_dialect if self.worktrees else None,
                )
            ]
            if not candidates:
                return {}
            # Nested checkouts own their metadata; conflicting observations for
            # the same root remain alternatives, never an invented current HEAD.
            depth = max(len(topology.root_path) for _, topology in candidates)
            candidates = [
                pair for pair in candidates if len(pair[1].root_path) == depth
            ]

            def values(field):
                choices = sorted(
                    {_display(getattr(topology, field)) for _, topology in candidates}
                )
                return (
                    choices[0]
                    if len(choices) == 1
                    else json.dumps(choices, ensure_ascii=True)
                )

            repositories = set()
            for _, topology in candidates:
                if self.worktrees is not None and topology.common_dir:
                    repositories.update(
                        self.worktrees.repository_links(topology.common_dir)
                    )
            differing = any(
                len({getattr(topology, field) for _, topology in candidates}) > 1
                for field in ("git_dir", "common_dir", "branch", "head_oid")
            )
            return {
                "RepoCatalog.Worktree": values("root_path"),
                "RepoCatalog.GitDir": values("git_dir"),
                "RepoCatalog.CommonDir": values("common_dir"),
                "RepoCatalog.Branch": values("branch"),
                "RepoCatalog.HeadOID": values("head_oid"),
                "RepoCatalog.Repository": ";".join(sorted(repositories)),
                "RepoCatalog.TopologyObservation": ";".join(
                    sorted({d.observation_uuid for d, _ in candidates})
                ),
                "RepoCatalog.TopologyStatus": "conflict" if differing else "observed",
            }

        def entries():
            for scan_uuid in selected:
                yield from self.filesystem.iter_entries(scan_uuid)

        columns = tuple(extra_columns) + (
            GIT_COLUMNS if self.worktrees is not None else ()
        )
        fd, temporary = tempfile.mkstemp(prefix=".efu-", dir=destination.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
                result = export_efu(
                    entries(),
                    stream,
                    extra_columns=columns,
                    row_enricher=enrich,
                    skip_non_utf8=skip_non_utf8,
                    path_map=path_map,
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            return result
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
