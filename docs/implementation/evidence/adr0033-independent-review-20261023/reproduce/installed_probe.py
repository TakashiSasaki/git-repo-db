"""Independent installed-product probe; invoke with isolated Python outside source."""

import hashlib
import json
import pathlib
import runpy
import sqlite3
import subprocess
import sys
import uuid

out = pathlib.Path(sys.argv[1])
runpy.run_path(sys.argv[2])
import repo_catalog  # noqa: E402 - install the offline guard before product import
from repo_catalog.adapters.sqlite import access_schema, p1_schema  # noqa: E402
from repo_catalog.adapters.sqlite.json_contracts import guard_sql  # noqa: E402

package = pathlib.Path(repo_catalog.__file__).resolve().parent
assert package.is_relative_to(pathlib.Path(sys.prefix).resolve())
assert "site-packages" in package.parts
access_schema.require_runtime()
p1_schema._open(":memory:", fresh=True).close()
p1_schema.verify_declared()
assert (package / "resources/json_contracts.sql").read_text() == guard_sql()
stores = {}
for store in p1_schema.STORES:
    path = pathlib.Path.cwd() / (store + ".sqlite3")
    p1_schema.initialize(path, store, str(uuid.uuid4()), str(uuid.uuid4()))
    with p1_schema.connect(path, store) as db:
        assert [tuple(row) for row in db.execute("PRAGMA integrity_check")] == [("ok",)]
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        stores[store] = {"ddl": p1_schema.fingerprint(store), "integrity": "ok"}
commands = []
for argv in (
    [
        str(pathlib.Path(sys.prefix) / "bin/repo-catalog"),
        "--state-dir",
        str(pathlib.Path.cwd() / "cli-state"),
        "--format",
        "json",
        "doctor",
    ],
    [sys.executable, "-I", "-m", "repo_catalog", "--help"],
):
    p = subprocess.run(argv, capture_output=True, text=True)
    commands.append(
        {
            "argv": argv,
            "exit_code": p.returncode,
            "stdout": p.stdout,
            "stderr": p.stderr,
        }
    )
    assert p.returncode == 0, commands[-1]
try:
    import socket

    socket.getaddrinfo("example.com", 443)
except PermissionError:
    network_guard = "external DNS refused"
else:
    raise AssertionError("network guard inactive")
with sqlite3.connect(":memory:") as db:
    runtime = {
        "sqlite": db.execute("SELECT sqlite_version(),sqlite_source_id()").fetchone(),
        "compile_options": db.execute("PRAGMA compile_options").fetchall(),
    }
files = {
    p.relative_to(package).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in package.rglob("*")
    if p.is_file() and p.suffix in {".py", ".sql", ".json", ".graphql"}
}
out.write_text(
    json.dumps(
        {
            "python": sys.version,
            "executable": sys.executable,
            "origin": str(package),
            "runtime": runtime,
            "files": files,
            "stores": stores,
            "json_guard_equal": True,
            "network_guard": network_guard,
            "commands": commands,
        },
        indent=2,
    )
    + "\n"
)
