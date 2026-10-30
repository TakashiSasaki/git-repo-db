"""Disposable production catalogs and real local Git in both native formats."""

import subprocess
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.git.notes import GitNotesSource
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.notes import NotesProgress
from repo_catalog.adapters.sqlite.p1_coordination import NotesWorkBudget, WorkLedger
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.application.notes import NotesAcquisition
from repo_catalog.domain.p1_coordination import NotesLimits, RequestIdentity
from repo_catalog.domain.p1_core import OID
from repo_catalog.domain.ports.notes import request_scope


def git(path, *args, data=None, env=None):
    return subprocess.run(
        ["git", "-C", str(path), *args],
        input=data,
        capture_output=True,
        check=True,
        env=env,
    ).stdout


def write(path, fmt, kind, body, literal=False):
    args = ["hash-object", "-w", "-t", kind, "--stdin"]
    if literal:
        args.append("--literally")
    return OID(fmt, git(path, *args, data=body).strip().decode())


def entry(mode, name, target):
    return mode + b" " + name + b"\0" + bytes.fromhex(target.full_oid)


@pytest.fixture(
    params=[("sha1", True), ("sha256", True), ("sha1", False), ("sha256", False)]
)
def acquisition(tmp_path, request):
    fmt, bare = request.param
    path = tmp_path / "git"
    path.mkdir()
    git(path, "init", *(["--bare"] if bare else []), "--object-format=" + fmt)
    repository, instance, origin = (str(uuid4()) for _ in range(3))
    core_path, op_path = tmp_path / "core.sqlite3", tmp_path / "operational.sqlite3"
    initialize(core_path, "core", repository, instance)
    initialize(op_path, "operational", repository, instance)
    core = GitCore(core_path)
    db = connect(op_path, "operational")
    ledger = WorkLedger(db)
    req = RequestIdentity(origin, str(uuid4()))
    source = GitNotesSource(GitNativeSource(path))
    ledger.new_request(
        req,
        request_scope(repository, instance, "local-test", source.scope),
        NotesLimits().work_limits(),
    )
    attempt = str(uuid4())
    ledger.attempt(req, attempt)
    work = NotesWorkBudget(ledger, req, attempt, NotesLimits())
    app = NotesAcquisition(
        core, source, work, NotesProgress(work), source_attribution="local-test"
    )
    yield app, path, fmt, repository, origin, core_path, op_path
    core.close()
    db.close()


def fixture_note(acquisition, body=b"\0\xffbinary\r\n", *, fanout=0, commit=False):
    app, path, fmt, repository, origin, *_ = acquisition
    note = write(path, fmt, "blob", body)
    target = OID(fmt, "a" * (40 if fmt == "sha1" else 64))
    suffix = target.full_oid[2 * fanout :]
    root = write(path, fmt, "tree", entry(b"100644", suffix.encode(), note))
    for index in range(fanout - 1, -1, -1):
        root = write(
            path,
            fmt,
            "tree",
            entry(b"40000", target.full_oid[2 * index : 2 * index + 2].encode(), root),
        )
    if commit:
        root = write(
            path,
            fmt,
            "commit",
            b"tree "
            + root.full_oid.encode()
            + b"\nauthor A <a@invalid> 1 +0000\ncommitter A <a@invalid> 1 +0000\n\nnotes\n",
        )
    git(path, "update-ref", "refs/notes/nested/review", root.full_oid)
    from types import SimpleNamespace

    captured_root = SimpleNamespace(root=root, ref="refs/notes/nested/review")
    return captured_root, target, note
