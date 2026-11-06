"""Verified Windows Python and native SQLite checks for independent local catalogs.

Only ``install`` runs with bootstrap Python. ``probe`` must run with the selected
whole interpreter or a venv based on it. No rich catalog, Access or POSIX runtime
implementation is imported. The existing Linux bootstrap remains unchanged.
"""

from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import os
import platform
import re
import sqlite3
import sys
import tarfile
import tempfile
from contextlib import closing
from pathlib import Path
from urllib.parse import urlparse

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import ci_python_runtime as runtime

WINDOWS_TRIPLE = "x86_64-pc-windows-msvc"
SCHEMA = "repo-catalog-local-runtime/1"
UNWANTED_MODULES = (
    "repo_catalog.adapters.sqlite.git_core",
    "repo_catalog.adapters.sqlite.production_context",
    "repo_catalog.adapters.sqlite.access_schema",
    "repo_catalog.adapters.sqlite.catalog_runtime",
)


def windows_distribution(manifest):
    if platform.system() != "Windows" or platform.machine().lower() not in {
        "amd64",
        "x86_64",
    }:
        raise runtime.UnsupportedPlatform(
            "This installer selects Windows x86_64 only; use setup-local-python.sh on Linux"
        )
    entry = manifest.get("additional_platforms", {}).get(WINDOWS_TRIPLE)
    if entry is None:
        raise ValueError("No pinned Windows Python distribution")
    if not runtime.SHA256.fullmatch(str(entry.get("sha256", ""))):
        raise ValueError("Invalid distribution SHA-256")
    if urlparse(str(entry.get("url", ""))).scheme != "https":
        raise ValueError("Distribution URL must use HTTPS")
    return {
        **{key: manifest[key] for key in ("distribution", "release", "python")},
        "platform": WINDOWS_TRIPLE,
        "url": entry["url"],
        "sha256": entry["sha256"],
    }


def check_windows_archive(archive):
    """Add native path checks before using the existing bounded safe extractor."""
    reserved = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?", re.I)
    names = set()
    with tarfile.open(archive) as source:
        for member in source:
            name = runtime._contained(member.name)
            if not (member.isreg() or member.isdir()):
                raise ValueError("Windows distribution cannot contain archive links")
            parts = name.split("/")
            if any(
                any(character in '<>:"|?*' or ord(character) < 32 for character in part)
                or part.endswith((" ", "."))
                or reserved.fullmatch(part)
                for part in parts
            ):
                raise ValueError(f"Unsafe Windows archive path: {member.name!r}")
            # Windows extraction must not silently overwrite differently cased names.
            folded = name.casefold()
            if folded in names:
                raise ValueError(f"Duplicate Windows archive path: {member.name!r}")
            names.add(folded)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def install(destination, receipt):
    selection = windows_distribution(json.loads(runtime.MANIFEST.read_text()))
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    result = {"schema": SCHEMA, "status": "failed", "selection": selection}
    try:
        with tempfile.TemporaryDirectory() as temporary:
            archive = runtime.download_verified(selection, temporary)
            check_windows_archive(archive)
            runtime.safe_extract(archive, destination)
        distribution = destination / "python"
        executable = distribution / "python.exe"
        identity = runtime.smoke(executable)
        if identity["python"] != selection["python"]:
            raise RuntimeError(
                "Selected Python version differs from the pinned distribution"
            )
        if Path(identity["base"]).resolve() != executable.resolve():
            raise RuntimeError(
                "Selected interpreter reports a different base executable"
            )
        result.update(
            status="installed",
            directory=str(distribution),
            executable=str(executable),
            executable_sha256=runtime.sha256_file(executable),
            tree=runtime.tree_digest(distribution),
        )
        write_json(receipt, result)
        if path := os.environ.get("GITHUB_ENV"):
            with Path(path).open("a", encoding="utf-8") as stream:
                stream.write(f"CI_PRODUCT_PYTHON={executable}\n")
                stream.write(f"UV_PYTHON={executable}\nUV_PYTHON_DOWNLOADS=never\n")
                stream.write("PYTHONDONTWRITEBYTECODE=1\n")
        print(f"Pinned Windows Python installed; receipt: {receipt}")
        return result
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
        write_json(receipt, result)
        raise


def sqlite_mappings():
    if os.name != "nt":
        maps = Path("/proc/self/maps")
        if not maps.is_file():
            raise RuntimeError(
                "No supported native library inspection on this platform"
            )
        return sorted(
            {
                line.split()[-1]
                for line in maps.read_text().splitlines()
                if "sqlite" in line.lower()
            }
        )
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    process = kernel.GetCurrentProcess
    process.argtypes = []
    process.restype = wintypes.HANDLE
    enumerate_modules = kernel.K32EnumProcessModules
    enumerate_modules.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.HMODULE),
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    enumerate_modules.restype = wintypes.BOOL
    module_path = kernel.GetModuleFileNameW
    module_path.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    module_path.restype = wintypes.DWORD
    modules = (wintypes.HMODULE * 4096)()
    needed = wintypes.DWORD()
    if not enumerate_modules(
        process(), modules, ctypes.sizeof(modules), ctypes.byref(needed)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    if needed.value > ctypes.sizeof(modules):
        raise RuntimeError("Native module inventory exceeds the bounded buffer")
    result = set()
    for module in modules[: needed.value // ctypes.sizeof(wintypes.HMODULE)]:
        buffer = ctypes.create_unicode_buffer(32768)
        length = module_path(module, buffer, len(buffer))
        if not length or length >= len(buffer):
            raise ctypes.WinError(ctypes.get_last_error())
        if "sqlite" in Path(buffer.value).name.lower():
            result.add(str(Path(buffer.value).resolve()))
    if not result:
        raise RuntimeError(
            "Native SQLite module was not found in the process inventory"
        )
    return sorted(result)


def identity():
    import _sqlite3

    with closing(sqlite3.connect(":memory:")) as db:
        source = db.execute("SELECT sqlite_source_id()").fetchone()[0]
        options = sorted(row[0] for row in db.execute("PRAGMA compile_options"))
    module = Path(_sqlite3.__file__).resolve()
    base = Path(sys._base_executable).resolve()
    mappings = sqlite_mappings()
    return {
        "python": platform.python_version(),
        "executable": sys.executable,
        "base_executable": str(base),
        "base_executable_sha256": runtime.sha256_file(base),
        "sqlite_version": sqlite3.sqlite_version,
        "sqlite_source_id": source,
        "sqlite_threadsafety": sqlite3.threadsafety,
        "sqlite_module": str(module),
        "sqlite_module_sha256": runtime.sha256_file(module),
        "compile_options": options,
        "sqlite_mappings": {name: runtime.sha256_file(name) for name in mappings},
    }


def check_selected(measured, installed):
    if installed.get("schema") != SCHEMA or installed.get("status") != "installed":
        raise RuntimeError(
            "Installation receipt is not a verified Windows installation"
        )
    current = json.loads(runtime.MANIFEST.read_text())
    if installed["selection"] != windows_distribution(current):
        raise RuntimeError("Installation no longer matches the pinned manifest")
    distribution = Path(installed["directory"]).resolve()
    if runtime.tree_digest(distribution) != installed["tree"]:
        raise RuntimeError("Selected distribution contents changed")
    if measured["base_executable"] != str(Path(installed["executable"]).resolve()):
        raise RuntimeError("This interpreter is not based on the selected Python")
    if measured["base_executable_sha256"] != installed["executable_sha256"]:
        raise RuntimeError("Selected base executable changed")
    if measured["python"] != installed["selection"]["python"]:
        raise RuntimeError("Python version differs from the installation receipt")
    paths = [measured["sqlite_module"], *measured["sqlite_mappings"]]
    if any(not Path(path).resolve().is_relative_to(distribution) for path in paths):
        raise RuntimeError(
            "SQLite extension or native library is outside selected Python"
        )


def check_reference(measured, original):
    if original.get("status") != "passed":
        raise RuntimeError("Reference runtime probe did not pass")
    for field in (
        "python",
        "base_executable",
        "base_executable_sha256",
        "sqlite_version",
        "sqlite_source_id",
        "sqlite_threadsafety",
        "sqlite_module",
        "sqlite_module_sha256",
        "compile_options",
        "sqlite_mappings",
    ):
        if measured[field] != original["runtime"][field]:
            raise RuntimeError(f"Runtime changed within this invocation: {field}")


def check_capabilities(directory):
    # Preserve the existing WAL safety floor, without selecting a SQLite build.
    if sqlite3.sqlite_version_info < (3, 51, 3) or sqlite3.threadsafety == 0:
        raise RuntimeError("SQLite >= 3.51.3 with mutexes is required")
    with closing(
        sqlite3.connect(directory / "probe.sqlite3", isolation_level=None)
    ) as db:
        if db.execute("PRAGMA journal_mode=WAL").fetchone() != ("wal",):
            raise RuntimeError("SQLite WAL is unavailable")
        db.execute("CREATE TABLE t(value INTEGER) STRICT")
        try:
            db.execute("INSERT INTO t VALUES ('not an integer')")
        except sqlite3.IntegrityError:
            pass
        else:
            raise RuntimeError("SQLite STRICT type checking failed")
        if db.execute("SELECT json_extract('{\"value\":7}','$.value')").fetchone() != (
            7,
        ):
            raise RuntimeError("SQLite JSON capability failed")
        db.execute(
            "CREATE VIRTUAL TABLE f USING fts5(body,tokenize='trigram case_sensitive 1')"
        )
        db.execute("INSERT INTO f VALUES ('repository')")
        if db.execute("SELECT rowid FROM f WHERE f MATCH 'osi'").fetchall() != [(1,)]:
            raise RuntimeError("SQLite FTS5 trigram capability failed")
        db.execute("BEGIN")
        db.execute("INSERT INTO t VALUES (1)")
        db.execute("ROLLBACK")
        if db.execute("SELECT count(*) FROM t").fetchone() != (0,):
            raise RuntimeError("SQLite rollback failed")
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise RuntimeError("SQLite integrity check failed")
    return [
        "minimum_version",
        "mutexes",
        "wal",
        "strict",
        "json",
        "fts5_trigram",
        "rollback",
        "integrity",
    ]


def check_factories(directory):
    from repo_catalog.filesystem import FilesystemCatalog
    from repo_catalog.worktrees import WorktreeCatalog

    result = {}
    for name, factory in (
        ("filesystem", FilesystemCatalog),
        ("worktrees", WorktreeCatalog),
    ):
        with factory.initialize(directory / f"{name}.sqlite3") as catalog:
            result[name] = catalog.verify()
    for name in UNWANTED_MODULES:
        try:
            present = importlib.util.find_spec(name) is not None
        except ModuleNotFoundError:
            present = False
        if present:
            raise RuntimeError(f"Unwanted implementation is installed: {name}")
    return result


def probe(installation, output, *, reference=None, factories=False):
    result = {"schema": SCHEMA, "status": "failed"}
    try:
        if any(
            os.environ.get(name) for name in (*runtime.LOADER_VARIABLES, "PYTHONHOME")
        ):
            raise RuntimeError("Unexpected Python or native loader override")
        installed = json.loads(Path(installation).read_text(encoding="utf-8"))
        measured = identity()
        result["runtime"] = measured
        check_selected(measured, installed)
        if reference:
            check_reference(
                measured, json.loads(Path(reference).read_text(encoding="utf-8"))
            )
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            result["capabilities"] = check_capabilities(directory)
            if factories:
                result["factories"] = check_factories(directory)
        result["installation"] = installed
        result["repository"] = runtime.repository_identity()
        result["status"] = "passed"
        write_json(output, result)
        print(f"Native local-catalog runtime passed; receipt: {output}")
        return result
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
        write_json(output, result)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("install")
    create.add_argument("--destination", required=True, type=Path)
    create.add_argument("--receipt", required=True, type=Path)
    inspect = commands.add_parser("probe")
    inspect.add_argument("--installation", required=True, type=Path)
    inspect.add_argument("--output", required=True, type=Path)
    inspect.add_argument("--reference", type=Path)
    inspect.add_argument("--factories", action="store_true")
    args = parser.parse_args()
    if args.command == "install":
        install(args.destination, args.receipt)
    else:
        probe(
            args.installation,
            args.output,
            reference=args.reference,
            factories=args.factories,
        )


if __name__ == "__main__":
    main()
