"""Select a complete prebuilt product Python and audit its actual SQLite.

The manifest pins the Python distribution, not a test SQLite release. No SQLite
component is obtained separately. Probe receipts bind children to this invocation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path(__file__).with_suffix(".json")


def install(destination):
    manifest = json.loads(MANIFEST.read_text())
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("Pinned product Python requires Linux x86_64")
    destination.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / "python.tar.gz"
        urllib.request.urlretrieve(manifest["url"], archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != manifest["sha256"]:
            raise ValueError("Python distribution digest mismatch")
        with tarfile.open(archive) as source:
            source.extractall(destination, filter="data")
    python = destination / "python/bin/python3"
    # Persist the selected whole interpreter before any dependency preparation.
    with Path(os.environ["GITHUB_PATH"]).open("a") as stream:
        stream.write(str(python.parent) + "\n")
    with Path(os.environ["GITHUB_ENV"]).open("a") as stream:
        stream.write(f"UV_PYTHON={python}\nUV_PYTHON_DOWNLOADS=never\n")
        stream.write(f"CI_PRODUCT_PYTHON={python}\n")
        stream.write(f"CI_RUNTIME_REFERENCE={ROOT}/artifacts/runtime/selected.json\n")
    print(json.dumps({"manifest": manifest, "executable": str(python)}, indent=2))


def identity():
    import _sqlite3

    with sqlite3.connect(":memory:") as db:
        version, source = db.execute(
            "SELECT sqlite_version(),sqlite_source_id()"
        ).fetchone()
        options = [list(row) for row in db.execute("PRAGMA compile_options")]
    module = Path(getattr(_sqlite3, "__file__", sys._base_executable)).resolve()
    return {
        "python": platform.python_version(),
        "executable": sys.executable,
        "base_executable": str(Path(sys._base_executable).resolve()),
        "sqlite_version": version,
        "sqlite_source_id": source,
        "sqlite_module": str(module),
        "sqlite_module_origin": _sqlite3.__spec__.origin,
        "sqlite_module_sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
        "compile_options": options,
        "loader_environment": {
            name: os.environ.get(name)
            for name in ("LD_LIBRARY_PATH", "LD_PRELOAD", "DYLD_LIBRARY_PATH")
        },
        "sqlite_mappings": sorted(
            {
                line.split()[-1]
                for line in Path("/proc/self/maps").read_text().splitlines()
                if "sqlite" in line.lower()
            }
        ),
    }


def probe(output, reference=None):
    result = identity()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    if any(result["loader_environment"].values()):
        raise RuntimeError("Unexpected dynamic loader override")
    selected = os.environ.get("CI_PRODUCT_PYTHON")
    if selected and result["base_executable"] != str(Path(selected).resolve()):
        raise RuntimeError("Python changed after explicit product runtime selection")
    if reference:
        original = json.loads(reference.read_text())
        for field in (
            "base_executable",
            "sqlite_version",
            "sqlite_source_id",
            "sqlite_module",
            "sqlite_module_sha256",
            "compile_options",
            "sqlite_mappings",
        ):
            if result[field] != original[field]:
                raise RuntimeError(f"Runtime changed within this invocation: {field}")
    if importlib.util.find_spec("repo_catalog") is None:
        sys.path.insert(0, str(ROOT / "src"))
    from repo_catalog.adapters.sqlite import access_schema, p1_schema

    # Invoke the real factories; their safety predicates remain the authority.
    access_schema.require_runtime()
    p1_schema._open(":memory:", fresh=True).close()
    with tempfile.TemporaryDirectory() as temporary:
        access_schema.initialize(Path(temporary) / "access.sqlite3")
        with sqlite3.connect(Path(temporary) / "capabilities.sqlite3") as db:
            db.execute("CREATE TABLE strict_probe(value INTEGER) STRICT")
            assert db.execute("SELECT json_valid('[]')").fetchone() == (1,)
            db.execute(
                "CREATE VIRTUAL TABLE f USING fts5(body,tokenize='trigram case_sensitive 1',content='',detail=full)"
            )
            assert db.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
    result["product_safety_and_capabilities"] = "passed"
    result["product_module"] = access_schema.__file__
    output.write_text(json.dumps(result, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("install")
    setup.add_argument("destination", type=Path)
    audit = commands.add_parser("probe")
    audit.add_argument("output", type=Path)
    audit.add_argument("--reference", type=Path)
    args = parser.parse_args()
    if args.command == "install":
        install(args.destination.resolve())
    else:
        probe(args.output, args.reference)
        # Verify subprocess resolution as well as the invoking process.
        child = json.loads(
            subprocess.check_output(
                [
                    sys.executable,
                    "-c",
                    "import json,runpy; m=runpy.run_path("
                    + repr(str(Path(__file__).resolve()))
                    + "); print(json.dumps(m['identity']()))",
                ],
                text=True,
            )
        )
        if child != identity():
            raise RuntimeError("Child runtime identity differs")


if __name__ == "__main__":
    main()
