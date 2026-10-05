"""Online dependency preparation: CPython audit-capable SQLite 3.46.1 lane.

pysqlite3-binary lacks CPython's sqlite3.connect audit event. Build the standard
CPython 3.12 binding with the pinned SQLite amalgamation instead. No application
dependency/provider is changed. Fresh CI runners require no warm cache.
"""

import hashlib
import io
import json
import subprocess
import sys
import sysconfig
import tarfile
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

INPUTS = {
    "python": (
        "https://www.python.org/ftp/python/3.12.14/Python-3.12.14.tar.xz",
        "5c8462af5790baf43a321a1559dbe0db06d1be4300fb85fb53c40060668e548a",
    ),
    "sqlite": (
        "https://www.sqlite.org/2024/sqlite-amalgamation-3460100.zip",
        "77823cb110929c2bcb0f5d48e4833b5c59a8a6e40cdea3936b99e199dbbe5784",
    ),
}


def download(item):
    name, (url, checksum) = item
    cache = Path("artifacts/sqlite-min/downloads")
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / name
    if path.exists():
        raw = path.read_bytes()
    else:
        with urllib.request.urlopen(url, timeout=60) as response:
            raw = response.read()
    if hashlib.sha256(raw).hexdigest() != checksum:
        raise ValueError("Minimum SQLite preparation input SHA mismatch")
    if not path.exists():
        path.write_bytes(raw)
    return name, raw


def main():
    if sys.version_info[:2] != (3, 12) or sys.platform != "linux":
        raise ValueError("This CI preparation lane requires Linux CPython 3.12")
    root = Path("artifacts/sqlite-min").resolve()
    build, output = root / "build", root / "cpython"
    build.mkdir(parents=True, exist_ok=True)
    output.mkdir(exist_ok=True)
    with ThreadPoolExecutor(2) as pool:
        inputs = dict(pool.map(download, INPUTS.items()))
    with tarfile.open(fileobj=io.BytesIO(inputs["python"])) as archive:
        for item in archive.getmembers():
            if (
                item.isfile()
                and item.name.startswith("Python-3.12.14/Modules/_sqlite/")
                and item.name.endswith((".c", ".h"))
            ):
                destination = build / Path(item.name).relative_to(
                    "Python-3.12.14/Modules/_sqlite"
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.extractfile(item).read())
    with zipfile.ZipFile(io.BytesIO(inputs["sqlite"])) as archive:
        for name in ("sqlite3.c", "sqlite3.h"):
            (build / name).write_bytes(
                archive.read("sqlite-amalgamation-3460100/" + name)
            )
    target = output / ("_sqlite3" + sysconfig.get_config_var("EXT_SUFFIX"))
    subprocess.run(
        [
            "cc",
            "-shared",
            "-fPIC",
            "-O1",
            "-DPy_BUILD_CORE_MODULE",
            "-DPY_SQLITE_ENABLE_LOAD_EXTENSION",
            "-DSQLITE_ENABLE_FTS5",
            "-DSQLITE_ENABLE_COLUMN_METADATA",
            "-I" + sysconfig.get_path("include"),
            "-I" + str(build),
            "-Wl,-Bsymbolic",
            *map(str, sorted(build.glob("*.c"))),
            "-o",
            str(target),
        ],
        check=True,
    )
    # Fresh process, before sqlite3/_sqlite3 can already be imported by a tool.
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "inputs": {k: {"url": v[0], "sha256": v[1]} for k, v in INPUTS.items()},
                "extension_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "sqlite": "3.46.1",
                "binding": "CPython 3.12.14 stdlib with audit events",
            },
            indent=2,
        )
    )
    check = "from scripts.sqlite_minimum import activate;activate();import sqlite3,sys;events=[];sys.addaudithook(lambda e,a:events.append(e));sqlite3.connect(':memory:');assert 'sqlite3.connect' in events;print(sqlite3.sqlite_version)"
    subprocess.run([sys.executable, "-c", check], check=True)


if __name__ == "__main__":
    main()
