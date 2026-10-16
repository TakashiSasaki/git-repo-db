"""Installed opt-in P4 acquisition from wheel and wheel built from sdist."""

import sys

import pytest

from tests.packaging.test_p1_distribution import p1_distributions, run  # noqa: F401


@pytest.mark.parametrize("variant", [0, 1], ids=["wheel", "sdist-wheel"])
@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_p4_installed_notes(p1_distributions, tmp_path, variant, fmt):  # noqa: F811
    env, wheels = p1_distributions
    outside = tmp_path / "outside"
    outside.mkdir()
    venv = tmp_path / "venv"
    run(["uv", "venv", venv, "--python", sys.executable, "--offline"], outside, env)
    python = venv / "bin/python"
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            python,
            "--offline",
            "--no-deps",
            wheels[variant],
        ],
        outside,
        env,
    )
    script = r"""
import subprocess
from pathlib import Path
from uuid import uuid4
from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.git.notes import GitNotesSource
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.notes import NotesProgress
from repo_catalog.adapters.sqlite.p1_coordination import WorkLedger, NotesWorkBudget
from repo_catalog.adapters.sqlite.p1_schema import initialize, connect, verify_declared
from repo_catalog.application.notes import NotesAcquisition
from repo_catalog.domain.p1_core import OID, Capture, encode
from repo_catalog.domain.p1_coordination import RequestIdentity, NotesLimits
assert "site-packages" in str(Path(__import__("repo_catalog.application.notes",fromlist=["x"]).__file__))
verify_declared()
repo, instance, origin = (str(uuid4()) for _ in range(3))
for name in ("core", "operational"):
    initialize(Path(name+".sqlite3"), name, repo, instance)
subprocess.run(["git","init","--bare","--object-format=FORMAT","git"],check=True,capture_output=True)
def write(kind, body):
    return subprocess.run(["git","-C","git","hash-object","-w","-t",kind,"--stdin"],input=body,check=True,capture_output=True).stdout.strip().decode()
body=b"\0\xffexact\r\n"
note=write("blob",body)
target="a"*(40 if "FORMAT"=="sha1" else 64)
root=write("tree",b"100644 "+target.encode()+b"\0"+bytes.fromhex(note))
subprocess.run(["git","-C","git","update-ref","refs/notes/nested/p4",root],check=True)
core=GitCore(Path("core.sqlite3"))
db=connect(Path("operational.sqlite3"),"operational")
ledger=WorkLedger(db)
request=RequestIdentity(origin,str(uuid4()))
ledger.new_request(request,encode([repo,instance,"installed"]),NotesLimits().work_limits())
attempt=str(uuid4())
ledger.attempt(request,attempt)
work=NotesWorkBudget(ledger,request,attempt,NotesLimits())
app=NotesAcquisition(core,GitNotesSource(GitNativeSource(Path("git"))),work,NotesProgress(work))
found=app.discover(repo,"installed-local",origin,str(uuid4()),123)
assert found.observation.value["enumeration_state"]=="complete"
capture=found.captures[0]
result=app.acquire_note(capture,OID("FORMAT",target))
assert result.body_retained
assert core.read_note(capture,OID("FORMAT",target),OID("FORMAT",note))==body
assert app.inventory(capture).status=="complete"
assert not Path("context.sqlite3").exists()
core.close(); db.close()
""".replace("FORMAT", fmt)
    run([python, "-c", script], outside, env)
