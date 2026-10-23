"""Rebuild in a backend-only venv with no installed product and no Git on PATH."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

source, measurement, wheelhouse, out = map(Path, sys.argv[1:5])
out.mkdir(exist_ok=False)
manifest = json.loads((wheelhouse / "manifest.json").read_text())
assert (
    manifest["lock_sha256"]
    == hashlib.sha256((source / "uv.lock").read_bytes()).hexdigest()
)
records = []


def run(name, argv, cwd, env=None):
    p = subprocess.run(
        list(map(str, argv)), cwd=cwd, env=env, capture_output=True, text=True
    )
    (out / (name + ".log")).write_text(p.stdout + p.stderr)
    records.append(
        {
            "name": name,
            "argv": list(map(str, argv)),
            "cwd": str(cwd),
            "exit_code": p.returncode,
        }
    )
    (out / "processes.json").write_text(json.dumps(records, indent=2) + "\n")
    assert p.returncode == 0, records[-1]


venv = out / "backend-venv"
run("venv", [sys.executable, "-m", "venv", "--without-pip", venv], out)
wanted = {"hatchling", "packaging", "pathspec", "pluggy", "trove-classifiers"}
deps = [r for r in manifest["wheels"] if r["name"] in wanted]
assert {r["name"] for r in deps} == wanted
for r in deps:
    assert (
        hashlib.sha256((wheelhouse / r["file"]).read_bytes()).hexdigest() == r["sha256"]
    )
req = out / "requirements.txt"
req.write_text(
    "".join(
        r["name"]
        + " @ "
        + (wheelhouse / r["file"]).resolve().as_uri()
        + " --hash=sha256:"
        + r["sha256"]
        + "\n"
        for r in deps
    )
)
run(
    "install",
    [
        "uv",
        "pip",
        "install",
        "--python",
        venv / "bin/python",
        "--offline",
        "--no-index",
        "--no-deps",
        "--require-hashes",
        "-r",
        req,
    ],
    out,
    {**os.environ, "UV_CACHE_DIR": "/workspace/.uv-cache"},
)
guard = out / "network_guard"
guard.mkdir()
shutil.copyfile(
    source / "tests/support/network_guard/sitecustomize.py", guard / "sitecustomize.py"
)
env = {
    **os.environ,
    "PATH": str((venv / "bin").resolve()),
    "PYTHONPATH": str(guard.resolve()),
    "GIT_ALLOW_PROTOCOL": "file",
}
for name in ("GH_TOKEN", "GITHUB_TOKEN", "PYTHONHOME"):
    env.pop(name, None)
run(
    "verify-no-product-git",
    [
        venv / "bin/python",
        "-c",
        "import importlib.util,shutil,json; assert importlib.util.find_spec('repo_catalog') is None; assert shutil.which('git') is None; print(json.dumps({'product_importable':False,'git_on_path':False}))",
    ],
    out,
    env,
)
root = next((measurement / "extracted").iterdir())
run(
    "rebuild",
    [
        venv / "bin/python",
        "-m",
        "hatchling",
        "build",
        "-t",
        "wheel",
        "-d",
        out / "dist",
    ],
    root,
    env,
)
new = next((out / "dist").glob("*.whl"))
expected = next((measurement / "after-dist").glob("*.whl"))
with zipfile.ZipFile(new) as a, zipfile.ZipFile(expected) as b:
    assert {n: a.read(n) for n in a.namelist()} == {n: b.read(n) for n in b.namelist()}
(out / "result.json").write_text(
    json.dumps(
        {
            "status": "passed",
            "product_importable": False,
            "git_on_path": False,
            "wheel_sha256": hashlib.sha256(new.read_bytes()).hexdigest(),
            "expected_sha256": hashlib.sha256(expected.read_bytes()).hexdigest(),
            "complete_wheel_contents_equal": True,
        },
        indent=2,
    )
    + "\n"
)
