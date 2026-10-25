"""Select a complete prebuilt product Python and audit its actual SQLite.

The manifest pins the Python distribution, not a test SQLite release. No SQLite
component is obtained separately. Probe receipts bind children to this invocation.

Two installers share one SHA-256 verified download and one safe extractor:
``install`` serves hosted CI (fixed destination, GitHub environment exports) and
``provision`` serves local development (per-user, content-addressed, locked,
verified, read-only, idempotent). Both need only the standard library.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import posixpath
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path(__file__).with_suffix(".json")

DISTRIBUTION_DIRECTORY = "python"
LEGACY_PLATFORM = "x86_64-unknown-linux-gnu"
READY_SCHEMA = "git-repo-db-python-install/1"
MAX_MEMBERS = 100_000
MAX_UNPACKED_BYTES = 1 << 30
LOADER_VARIABLES = ("LD_LIBRARY_PATH", "LD_PRELOAD", "DYLD_LIBRARY_PATH")
SHA256 = re.compile(r"[0-9a-f]{64}")


class UnsupportedPlatform(RuntimeError):
    """The host has no manifest-pinned complete Python distribution."""


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def host_triple():
    system, machine = platform.system(), platform.machine().lower()
    arch = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64"}.get(machine)
    if system != "Linux" or arch is None:
        raise UnsupportedPlatform(
            f"Host {system}/{platform.machine()} is not supported by the pinned "
            "Python distribution manifest; no other Python or SQLite is substituted"
        )
    return f"{arch}-unknown-linux-gnu"


def select_distribution(manifest):
    """Return the pinned archive for this host, or refuse without substitution."""
    triple = host_triple()
    if triple == manifest.get("platform", LEGACY_PLATFORM):
        entry = manifest
    else:
        entry = manifest.get("additional_platforms", {}).get(triple)
    if entry is None:
        raise UnsupportedPlatform(
            f"Pinned product Python has no {triple} distribution; supported: "
            + ", ".join(
                [manifest.get("platform", LEGACY_PLATFORM)]
                + sorted(manifest.get("additional_platforms", {}))
            )
        )
    if not SHA256.fullmatch(str(entry.get("sha256", ""))):
        raise ValueError("Manifest SHA-256 must be 64 lowercase hexadecimal digits")
    if urllib.parse.urlparse(str(entry.get("url", ""))).scheme != "https":
        raise ValueError("Manifest distribution URL must use https")
    return {
        "distribution": manifest.get("distribution"),
        "release": manifest.get("release"),
        "python": manifest.get("python"),
        "platform": triple,
        "url": entry["url"],
        "sha256": entry["sha256"],
    }


def download_verified(selection, directory):
    """Download the archive and refuse it unless its SHA-256 equals the manifest."""
    archive = Path(directory) / "python.tar.gz"
    urllib.request.urlretrieve(selection["url"], archive)
    if sha256_file(archive) != selection["sha256"]:
        raise ValueError("Python distribution digest mismatch")
    return archive


def _contained(name, link=None):
    """Return a normalized archive path, rejecting absolute and escaping paths."""
    if not name or "\x00" in name or "\\" in name or name.startswith("/"):
        raise ValueError(f"Unsafe archive path: {name!r}")
    if link is not None:
        if not link or "\x00" in link or link.startswith("/"):
            raise ValueError(f"Unsafe archive link target: {name!r} -> {link!r}")
        name = posixpath.join(posixpath.dirname(name), link)
    normalized = posixpath.normpath(name)
    parts = normalized.split("/")
    if ".." in parts or parts[0] != DISTRIBUTION_DIRECTORY:
        raise ValueError(f"Archive path escapes the distribution: {name!r}")
    return normalized


def safe_extract(archive_path, destination):
    """Extract only a contained ``python/`` tree of files, directories and links.

    Every member is validated before anything is written. Hard links are copied;
    devices, FIFOs and other member types are refused. Parents must not be links
    created by the archive, and the finished tree is checked once more.
    """
    destination = Path(destination).resolve()
    with tarfile.open(archive_path) as source:
        members = source.getmembers()
        if not members or len(members) > MAX_MEMBERS:
            raise ValueError("Unexpected archive member count")
        if sum(m.size for m in members if m.isreg()) > MAX_UNPACKED_BYTES:
            raise ValueError("Archive expands beyond the permitted size")
        names, links = {}, set()
        for member in members:
            name = _contained(member.name)
            if name != member.name.rstrip("/"):
                raise ValueError(f"Non-normal archive path: {member.name!r}")
            if not (
                member.isreg() or member.isdir() or member.issym() or member.islnk()
            ):
                raise ValueError(f"Unexpected archive member type: {member.name!r}")
            if name in names and not (member.isdir() and names[name] == "dir"):
                raise ValueError(f"Duplicate archive member: {name!r}")
            parent = posixpath.dirname(name)
            while parent:
                if parent in links:
                    raise ValueError(f"Archive member below a link: {name!r}")
                parent = posixpath.dirname(parent)
            if member.issym():
                _contained(name, member.linkname)
                links.add(name)
            if member.islnk():
                _contained(member.linkname)
            names[name] = "dir" if member.isdir() else "other"
        for member in members:
            target = destination / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.parent.resolve().is_relative_to(destination):
                raise ValueError(
                    f"Archive member escapes the destination: {member.name!r}"
                )
            if member.issym():
                os.symlink(member.linkname, target)
            elif member.islnk():
                origin = destination / member.linkname
                if origin.is_symlink() or not origin.is_file():
                    raise ValueError(f"Hard link target is not a file: {member.name!r}")
                shutil.copyfile(origin, target)
                target.chmod(origin.stat().st_mode & 0o777)
            else:
                mode = 0o755 if member.mode & 0o111 else 0o644
                descriptor = os.open(
                    target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode
                )
                with os.fdopen(descriptor, "wb") as output:
                    shutil.copyfileobj(source.extractfile(member), output)
                target.chmod(mode)
    verify_contained(destination / DISTRIBUTION_DIRECTORY)


def verify_contained(root):
    """Reject any link, in the extracted tree, that resolves outside it."""
    root = Path(root).resolve()
    for current, directories, files in os.walk(root):
        for name in directories + files:
            path = Path(current) / name
            if path.is_symlink() and not Path(os.path.realpath(path)).is_relative_to(
                root
            ):
                raise ValueError(f"Extracted link escapes the distribution: {path}")


def tree_digest(root):
    """Return a deterministic digest of names, types, exec bits, content and links."""
    digest, files, size = hashlib.sha256(), 0, 0

    def walk(path, relative):
        nonlocal files, size
        for entry in sorted(os.scandir(path), key=lambda item: item.name):
            name = f"{relative}/{entry.name}" if relative else entry.name
            mode = entry.stat(follow_symlinks=False).st_mode
            if stat.S_ISLNK(mode):
                record = ("l", name, os.readlink(entry.path))
            elif stat.S_ISDIR(mode):
                digest.update(f"d\0{name}\0\n".encode())
                walk(entry.path, name)
                continue
            elif stat.S_ISREG(mode):
                record = ("fx" if mode & 0o111 else "f-", name, sha256_file(entry.path))
                files += 1
                size += entry.stat(follow_symlinks=False).st_size
            else:
                raise ValueError(f"Special file in distribution: {entry.path}")
            digest.update("\0".join(record).encode() + b"\n")

    walk(Path(root), "")
    return {"sha256": digest.hexdigest(), "files": files, "bytes": size}


def make_read_only(root):
    for current, directories, files in os.walk(root, topdown=False):
        for name in files + directories:
            path = Path(current) / name
            if not path.is_symlink():
                path.chmod(path.stat().st_mode & ~0o222)
    Path(root).chmod(Path(root).stat().st_mode & ~0o222)


def remove_tree(path):
    """Delete a possibly read-only tree that this module itself created."""
    path = Path(path)
    if path.is_symlink() or not path.exists():
        path.unlink(missing_ok=True)
        return
    for current, directories, _files in os.walk(path):
        Path(current).chmod(0o700)
    shutil.rmtree(path)


def clean_environment(base=None):
    environment = dict(os.environ if base is None else base)
    for name in (*LOADER_VARIABLES, "PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP"):
        environment.pop(name, None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def smoke(python):
    """Run the unmodified interpreter and return its self-reported identity."""
    output = subprocess.check_output(
        [
            str(python),
            "-I",
            "-B",
            "-c",
            "import json, platform, sqlite3, sys\n"
            "db = sqlite3.connect(':memory:')\n"
            "print(json.dumps({'python': platform.python_version(),"
            " 'base': sys._base_executable,"
            " 'sqlite_version': sqlite3.sqlite_version}))",
        ],
        env=clean_environment(),
        text=True,
        timeout=120,
    )
    return json.loads(output)


def default_home():
    configured = os.environ.get("GIT_REPO_DB_PYTHON_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    data = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
    return (Path(data).expanduser() / "git-repo-db/python").resolve()


class InstallLock:
    """Exclusive advisory lock so concurrent bootstraps never publish a partial tree."""

    def __init__(self, path, timeout):
        self.path, self.timeout, self.descriptor = path, timeout, None

    def __enter__(self):
        import fcntl

        self.descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fcntl.flock(self.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if time.monotonic() > deadline:
                    os.close(self.descriptor)
                    raise TimeoutError(
                        f"Another bootstrap holds {self.path}; retry when it finishes"
                    ) from None
                time.sleep(0.2)

    def __exit__(self, *exc):
        os.close(self.descriptor)


def require_private(path, what):
    """Trust only directories this user owns and nobody else can modify."""
    status = path.lstat()
    if not stat.S_ISDIR(status.st_mode) or status.st_uid != os.getuid():
        raise RuntimeError(f"{what} {path} must be a directory owned by this user")
    if status.st_mode & 0o022:
        raise RuntimeError(
            f"{what} {path} is writable by other users; run: chmod go-w '{path}'"
        )


def verify_installation(final, selection):
    """Accept an installation only when its ready record and whole tree still match."""
    ready_file = final / "ready.json"
    refusal = (
        f"Refusing the unverified Python installation {final}. It was not replaced. "
        "Inspect it, then remove it explicitly with: chmod -R u+w "
        f"'{final}' && rm -rf '{final}'; rerun the bootstrap to reinstall."
    )
    if final.is_symlink() or not final.is_dir() or not ready_file.is_file():
        raise RuntimeError(f"Incomplete installation. {refusal}")
    require_private(final, "Installation")
    if sorted(item.name for item in final.iterdir()) != sorted(
        ["ready.json", DISTRIBUTION_DIRECTORY]
    ):
        raise RuntimeError(f"Unexpected installation members. {refusal}")
    try:
        ready = json.loads(ready_file.read_text())
    except ValueError:
        raise RuntimeError(f"Unreadable ready record. {refusal}") from None
    if (
        ready.get("schema") != READY_SCHEMA
        or ready.get("archive_sha256") != selection["sha256"]
        or ready.get("platform") != selection["platform"]
    ):
        raise RuntimeError(f"Ready record does not match the manifest. {refusal}")
    measured = tree_digest(final / DISTRIBUTION_DIRECTORY)
    if measured["sha256"] != ready.get("tree_sha256"):
        raise RuntimeError(f"Installed files differ from the verified tree. {refusal}")
    python = final / DISTRIBUTION_DIRECTORY / "bin/python3"
    identity_now = smoke(python)
    if selection.get("python") and identity_now["python"] != selection["python"]:
        raise RuntimeError(
            f"Installed Python {identity_now['python']} is not the manifest's "
            f"{selection['python']}. {refusal}"
        )
    return ready, python


def provision(home=None, *, offline=False, lock_timeout=900.0):
    """Install, or verify and reuse, the complete Python distribution for this user.

    Layout: ``HOME/<archive sha256>/{python/, ready.json}``. The archive is verified
    before extraction, extraction happens in a private staging directory under the
    lock, the staged interpreter and tree digest are verified, files are made
    read-only and only then is the directory renamed into place. An existing
    directory is never overwritten or modified.
    """
    selection = select_distribution(json.loads(MANIFEST.read_text()))
    home = Path(home).resolve() if home else default_home()
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    require_private(home, "Python installation root")
    final = home / selection["sha256"]
    with InstallLock(home / f".lock-{selection['sha256']}", lock_timeout):
        if final.exists() or final.is_symlink():
            ready, python = verify_installation(final, selection)
            return _result(selection, final, python, ready, reused=True)
        if offline:
            raise RuntimeError(
                "Verified Python distribution is not installed and offline mode "
                "forbids downloading it; rerun without --offline once"
            )
        for stale in home.glob(f".staging-{selection['sha256']}-*"):
            remove_tree(stale)  # Safe: concurrent installers hold the lock.
        staging = (
            home / f".staging-{selection['sha256']}-{os.getpid()}-{uuid.uuid4().hex}"
        )
        staging.mkdir(mode=0o700)
        try:
            download = staging / ".download"
            download.mkdir()
            archive = download_verified(selection, download)
            safe_extract(archive, staging)
            shutil.rmtree(download)
            tree = tree_digest(staging / DISTRIBUTION_DIRECTORY)
            python = staging / DISTRIBUTION_DIRECTORY / "bin/python3"
            observed = smoke(python)
            if selection.get("python") and observed["python"] != selection["python"]:
                raise ValueError(
                    f"Distribution reports Python {observed['python']}, "
                    f"expected {selection['python']}"
                )
            ready = {
                "schema": READY_SCHEMA,
                "archive_sha256": selection["sha256"],
                "tree_sha256": tree["sha256"],
                "files": tree["files"],
                "bytes": tree["bytes"],
                "platform": selection["platform"],
                "release": selection["release"],
                "python": selection["python"],
                "url": selection["url"],
                "installed_at": datetime.now(timezone.utc).isoformat(),
                "verified": observed,
            }
            (staging / "ready.json").write_text(json.dumps(ready, indent=2) + "\n")
            make_read_only(staging)
            os.rename(staging, final)
        except BaseException:
            remove_tree(staging)
            raise
        ready, python = verify_installation(final, selection)
        return _result(selection, final, python, ready, reused=False)


def _result(selection, final, python, ready, reused):
    return {
        "selection": selection,
        "directory": str(final),
        "executable": str(python),
        "archive_sha256": selection["sha256"],
        "tree_sha256": ready["tree_sha256"],
        "ready": ready,
        "reused": reused,
    }


def export_environment(python):
    """Persist the selected interpreter for later GitHub Actions steps, if present."""
    if path := os.environ.get("GITHUB_PATH"):
        with Path(path).open("a") as stream:
            stream.write(str(python.parent) + "\n")
    if path := os.environ.get("GITHUB_ENV"):
        with Path(path).open("a") as stream:
            stream.write(f"UV_PYTHON={python}\nUV_PYTHON_DOWNLOADS=never\n")
            stream.write(f"CI_PRODUCT_PYTHON={python}\n")
            stream.write(
                f"CI_RUNTIME_REFERENCE={ROOT}/artifacts/runtime/selected.json\n"
            )


def install(destination):
    manifest = json.loads(MANIFEST.read_text())
    selection = select_distribution(manifest)
    destination.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory() as temporary:
        archive = download_verified(selection, temporary)
        safe_extract(archive, destination)
    python = destination / "python/bin/python3"
    # Persist the selected whole interpreter before any dependency preparation.
    export_environment(python)
    print(json.dumps({"manifest": manifest, "executable": str(python)}, indent=2))


def identity():
    import _sqlite3

    with sqlite3.connect(":memory:") as db:
        version, source = db.execute(
            "SELECT sqlite_version(),sqlite_source_id()"
        ).fetchone()
        options = [list(row) for row in db.execute("PRAGMA compile_options")]
        pragmas = {
            name: db.execute(f"PRAGMA {name}").fetchone()[0]
            for name in (
                "encoding",
                "foreign_keys",
                "journal_mode",
                "page_size",
                "recursive_triggers",
                "synchronous",
                "trusted_schema",
            )
        }
    module = Path(getattr(_sqlite3, "__file__", sys._base_executable)).resolve()
    base = Path(sys._base_executable).resolve()
    return {
        "python": platform.python_version(),
        "executable": sys.executable,
        "base_executable": str(base),
        "base_executable_sha256": sha256_file(base),
        "sqlite_version": version,
        "sqlite_source_id": source,
        "sqlite_threadsafety": sqlite3.threadsafety,
        "sqlite_module": str(module),
        "sqlite_module_origin": _sqlite3.__spec__.origin,
        "sqlite_module_sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
        "compile_options": options,
        "pragmas": pragmas,
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


def repository_identity():
    """Record the commit and effective tree measured by this invocation, if any."""

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    try:
        identity = {
            "commit": git("rev-parse", "HEAD"),
            "tree": git("rev-parse", "HEAD^{tree}"),
            "dirty": bool(git("status", "--porcelain")),
        }
        identity["effective_tree"] = identity["tree"]
        if identity["dirty"]:
            # Tree of the files actually executed, via a private temporary index.
            with tempfile.TemporaryDirectory() as temporary:
                environment = {**os.environ, "GIT_INDEX_FILE": f"{temporary}/index"}
                for step in (["read-tree", "HEAD"], ["add", "-A"]):
                    subprocess.run(
                        ["git", "-C", str(ROOT), *step],
                        env=environment,
                        check=True,
                        capture_output=True,
                    )
                identity["effective_tree"] = subprocess.run(
                    ["git", "-C", str(ROOT), "write-tree"],
                    env=environment,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
        return identity
    except (OSError, subprocess.CalledProcessError):
        return None


def distribution_identity(selected):
    """Bind the receipt to the manifest entry and, locally, the verified install."""
    try:
        selection = select_distribution(json.loads(MANIFEST.read_text()))
    except (UnsupportedPlatform, ValueError):
        selection = None
    ready = None
    if selected:
        parents = Path(selected).resolve().parents
        record = parents[2] / "ready.json" if len(parents) > 2 else None
        if record and record.is_file():
            ready = json.loads(record.read_text())
    return {"manifest_selection": selection, "installation": ready}


def check_confinement(result, selected):
    """Refuse a SQLite extension or library that is not part of the selected Python."""
    root = Path(selected).resolve().parent.parent
    for field in ("sqlite_module",):
        if not Path(result[field]).is_relative_to(root):
            raise RuntimeError(
                f"Unexpected {field} outside the selected distribution: {result[field]}"
            )
    outside = [m for m in result["sqlite_mappings"] if not Path(m).is_relative_to(root)]
    if outside:
        raise RuntimeError(f"Unexpected system SQLite library mapping: {outside}")


def capability_checks(directory):
    """Exercise the real product factories and the capabilities they depend on."""
    from repo_catalog.adapters.sqlite import access_schema, p1_schema

    results = {}

    def check(name, function):
        try:
            function()
            results[name] = "passed"
        except Exception as error:  # Recorded; refusal follows in probe.
            results[name] = f"failed: {type(error).__name__}: {error}"

    def threadsafety():
        assert sqlite3.threadsafety != 0, "SQLite mutexes are disabled"

    def wal():
        with closing(sqlite3.connect(directory / "wal.sqlite3")) as db:
            assert db.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)

    def strict():
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute("CREATE TABLE strict_probe(value INTEGER) STRICT")
            db.execute("INSERT INTO strict_probe VALUES (1)")
            try:
                db.execute("INSERT INTO strict_probe VALUES ('text')")
            except sqlite3.IntegrityError:
                return
            raise AssertionError("STRICT table accepted a mistyped value")

    def json_support():
        with closing(sqlite3.connect(":memory:")) as db:
            assert db.execute("SELECT json_valid('[]')").fetchone() == (1,)
            row = db.execute("SELECT json_extract('{\"a\":[1,2]}','$.a[1]')").fetchone()
            assert row == (2,)

    def fts5_trigram():
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute(
                "CREATE VIRTUAL TABLE f USING fts5(body,tokenize='trigram case_sensitive 1',content='',detail=full)"
            )
            db.execute("INSERT INTO f(rowid, body) VALUES (7, 'repository')")
            assert db.execute("SELECT rowid FROM f WHERE f MATCH 'osi'").fetchall() == [
                (7,)
            ]

    def integrity_and_transaction():
        with closing(
            sqlite3.connect(directory / "tx.sqlite3", isolation_level=None)
        ) as db:
            db.execute("CREATE TABLE t(value INTEGER) STRICT")
            db.execute("BEGIN")
            db.execute("INSERT INTO t VALUES (1)")
            db.execute("ROLLBACK")
            assert db.execute("SELECT count(*) FROM t").fetchone() == (0,)
            db.execute("BEGIN")
            db.execute("INSERT INTO t VALUES (1)")
            db.execute("COMMIT")
            assert db.execute("SELECT count(*) FROM t").fetchone() == (1,)
            assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]

    # Invoke the real factories; their safety predicates remain the authority.
    check("access_runtime_factory", access_schema.require_runtime)
    check("p1_runtime_factory", lambda: p1_schema._open(":memory:", fresh=True).close())
    check(
        "access_initialize",
        lambda: access_schema.initialize(directory / "access.sqlite3"),
    )
    check("thread_safety", threadsafety)
    check("wal", wal)
    check("strict", strict)
    check("json", json_support)
    check("fts5_trigram", fts5_trigram)
    check("integrity_and_transaction", integrity_and_transaction)
    return results, access_schema.__file__


def probe(output, reference=None):
    result = identity()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    verbose = os.environ.get("CI_VERBOSE") == "1" or "--verbose" in sys.argv
    if verbose:
        print(json.dumps(result, indent=2), flush=True)
    else:
        print(
            f"Runtime safety check passed (Python {result.get('python')}, "
            f"SQLite {result.get('sqlite_version')}); receipt: {output}",
            flush=True,
        )
    if any(result["loader_environment"].values()):
        raise RuntimeError("Unexpected dynamic loader override")
    selected = os.environ.get("CI_PRODUCT_PYTHON")
    if selected and result["base_executable"] != str(Path(selected).resolve()):
        raise RuntimeError("Python changed after explicit product runtime selection")
    if selected:
        check_confinement(result, selected)
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
    result["repository"] = repository_identity()
    result["distribution"] = distribution_identity(selected)
    with tempfile.TemporaryDirectory() as temporary:
        capabilities, product_module = capability_checks(Path(temporary))
    result["capabilities"] = capabilities
    result["product_module"] = product_module
    failed = {k: v for k, v in capabilities.items() if v != "passed"}
    result["product_safety_and_capabilities"] = "failed" if failed else "passed"
    output.write_text(json.dumps(result, indent=2) + "\n")
    if failed:
        raise RuntimeError(f"Product safety or capability checks failed: {failed}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("install", help="hosted CI installation")
    setup.add_argument("destination", type=Path)
    local = commands.add_parser(
        "provision", help="verified per-user local installation"
    )
    local.add_argument("--home", type=Path)
    local.add_argument("--offline", action="store_true")
    audit = commands.add_parser("probe")
    audit.add_argument("output", type=Path)
    audit.add_argument("--reference", type=Path)
    args = parser.parse_args()
    if args.command == "install":
        install(args.destination.resolve())
    elif args.command == "provision":
        print(json.dumps(provision(args.home, offline=args.offline), indent=2))
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
        receipt = json.loads(args.output.read_text())
        receipt["child_runtime_identity"] = (
            "passed" if child == identity() else "failed"
        )
        args.output.write_text(json.dumps(receipt, indent=2) + "\n")
        if child != identity():
            raise RuntimeError("Child runtime identity differs")


if __name__ == "__main__":
    main()
