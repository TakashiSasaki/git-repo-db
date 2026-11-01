"""Execute installed production native adapters from wheel and sdist-wheel."""

import sys

import pytest

from tests.packaging.test_p1_distribution import p1_distributions, run  # noqa: F401


@pytest.mark.parametrize("variant", [0, 1], ids=["wheel", "sdist-wheel"])
@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_p2_installed_native_git_round_trip(p1_distributions, tmp_path, variant, fmt):  # noqa: F811
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
            *wheels[variant],
        ],
        outside,
        env,
    )
    script = """
import hashlib
import subprocess
from pathlib import Path
from uuid import uuid4
from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.domain.p1_core import OID
assert "site-packages" in str(Path(__import__("repo_catalog.domain.git_native", fromlist=["x"]).__file__))
class Work:
    def require(self, unit, amount): pass
    def charge(self, unit, amount): pass
repo, instance = str(uuid4()), str(uuid4())
initialize(Path("core.sqlite3"), "core", repo, instance)
subprocess.run(["git", "init", "--bare", "--object-format=FORMAT", "git"], check=True, capture_output=True)
body = b""
result = subprocess.run(["git", "-C", "git", "hash-object", "-w", "-t", "tree", "--stdin"], input=body, check=True, capture_output=True)
oid = OID("FORMAT", result.stdout.strip().decode())
source = GitNativeSource(Path("git"))
native = source.metadata(oid)
core = GitCore(Path("core.sqlite3"))
core.admit_metadata(native, str(uuid4()), Work())
assert core.read_metadata(oid) == body
assert core.relations(oid, "tree_entries").canonical == ["known_empty", []]
assert not Path("context.sqlite3").exists()
core.close()
""".replace("FORMAT", fmt)
    run([python, "-c", script], outside, env)
