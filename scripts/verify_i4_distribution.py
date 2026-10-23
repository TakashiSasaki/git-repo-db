"""Build frozen direct/sdist wheels and execute I4 outside checkout with the environment SQLite.

The installed SQL lane explicitly drops only the two I2 fences in disposable DBs.
Unchanged Access smoke failures remain failures; the orchestrator returns nonzero.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import installed_test_harness as harness  # noqa: E402
from scripts import verify_i5_offline as evidence  # noqa: E402


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    records = []
    with evidence.sqlite3.connect(":memory:") as db:
        write(out / "runtime-before-checks.json", evidence.runtime_metadata(db))
    wheelhouse, wheel_manifest = evidence.verified_wheelhouse()
    write(out / "wheelhouse-binding.json", wheel_manifest)

    def run(name, argv, cwd=out, env=None):
        with (out / (name + ".log")).open("w") as stream:
            proc = subprocess.run(
                list(map(str, argv)),
                cwd=cwd,
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
            )
        record = {
            "name": name,
            "argv": list(map(str, argv)),
            "cwd": str(cwd),
            "exit_code": proc.returncode,
        }
        records.append(record)
        write(out / "processes.json", records)
        return proc.returncode

    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
    ).strip()
    assert not subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT
    )
    archive = out / "source.tar"
    assert run("archive", ["git", "archive", head, "-o", archive], ROOT) == 0
    source = out / "source"
    source.mkdir()
    with tarfile.open(archive) as tar:
        tar.extractall(source, filter="data")
    assert (
        run(
            "build-direct",
            [sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-t", "sdist"],
            source,
        )
        == 0
    )
    wheel = next((source / "dist").glob("*.whl"))
    sdist = next((source / "dist").glob("*.tar.gz"))
    unpack = out / "from-sdist"
    unpack.mkdir()
    with tarfile.open(sdist) as tar:
        tar.extractall(unpack, filter="data")
    derived = next(unpack.iterdir())
    assert (
        run(
            "build-sdist-wheel",
            [sys.executable, "-m", "hatchling", "build", "-t", "wheel"],
            derived,
        )
        == 0
    )
    swheel = next((derived / "dist").glob("*.whl"))
    write(
        out / "build-binding.json",
        {
            "head": head,
            "tree": tree,
            "archive_sha256": sha(archive),
            "direct_wheel": {"sha256": sha(wheel), "bytes": wheel.stat().st_size},
            "sdist": {"sha256": sha(sdist), "bytes": sdist.stat().st_size},
            "sdist_wheel": {"sha256": sha(swheel), "bytes": swheel.stat().st_size},
        },
    )
    external = tempfile.TemporaryDirectory(prefix="repo-catalog-installed-tests-")
    outside = Path(external.name)
    support_binding = harness.stage_support(source, outside)
    write(out / "test-support-binding.json", support_binding)
    guard = outside / "network_guard"
    guard.mkdir()
    shutil.copyfile(
        source / "tests/support/network_guard/sitecustomize.py",
        guard / "sitecustomize.py",
    )
    shutil.copyfile(
        source / "tests/integration/p3/test_transfer_sql.py",
        outside / "test_installed_i4.py",
    )
    for probe in ("verify_i2_distribution.py", "verify_i3_distribution.py"):
        shutil.copyfile(source / "scripts" / probe, outside / probe)
    smoke_ast = ast.parse(
        (source / "scripts/verify_access_distribution.py").read_text()
    )
    smoke = next(
        ast.literal_eval(n.value)
        for n in smoke_ast.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "SMOKE" for t in n.targets)
    )
    (outside / "original_access_smoke.py").write_text(smoke)
    (outside / "measure.py").write_text("""import hashlib,json,sqlite3,sys
from pathlib import Path
from repo_catalog.adapters.sqlite import p1_schema
import repo_catalog
origin=Path(repo_catalog.__file__).resolve()
assert origin.is_relative_to(Path(sys.prefix).resolve()), origin
db=sqlite3.connect(':memory:')
actual=db.execute('SELECT sqlite_version(),sqlite_source_id()').fetchone()
Path(sys.argv[1]).write_text(json.dumps({'sqlite':actual,'python':sys.version,'executable':sys.executable,'origin':str(origin),'compile_options':db.execute('PRAGMA compile_options').fetchall()},indent=2)+'\\n')
p1_schema._open(':memory:',fresh=True).close()
p1_schema.verify_declared()
p1_schema.register_functions(db); p1_schema.configure(db)
db.executescript(p1_schema.compose('context'))
root=origin.parent
files={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and p.suffix in ('.py','.sql','.json')}
result={'sqlite':actual,'python':sys.version,'executable':sys.executable,'origin':str(origin),'compile_options':db.execute('PRAGMA compile_options').fetchall(),'pragmas':{n:db.execute('PRAGMA '+n).fetchall() for n in p1_schema.REQUIRED_PRAGMAS},'functions':[r for r in db.execute('PRAGMA function_list') if r[0].startswith('p1_')],'fingerprint':p1_schema.fingerprint('context'),'schema':p1_schema.schema_rows(db),'installed_files':files}
Path(sys.argv[1]).write_text(json.dumps(result,indent=2)+'\\n')
""")
    for tag, artifact in [("direct", wheel), ("sdist", swheel)]:
        venv = out / (tag + "-venv")
        assert (
            run(tag + "-venv", [sys.executable, "-m", "venv", "--without-pip", venv])
            == 0
        )
        py = venv / "bin/python"
        wanted = {"pytest", "pluggy", "packaging", "iniconfig", "pygments"}
        dependencies = [
            record for record in wheel_manifest["wheels"] if record["name"] in wanted
        ]
        if {record["name"] for record in dependencies} != wanted:
            raise ValueError("locked wheelhouse lacks installed-test dependencies")
        requirements = out / (tag + "-requirements.txt")
        requirements.write_text(
            f"repo-catalog @ {artifact.as_uri()} --hash=sha256:{sha(artifact)}\n"
            + "".join(
                f"{record['name']} @ {(wheelhouse / record['file']).as_uri()} --hash=sha256:{record['sha256']}\n"
                for record in dependencies
            )
        )
        assert (
            run(
                tag + "-install",
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    py,
                    "--offline",
                    "--no-index",
                    "--find-links",
                    wheelhouse,
                    "--no-deps",
                    "--require-hashes",
                    "-r",
                    requirements,
                ],
            )
            == 0
        )
        label = tag
        env = dict(
            os.environ,
            PYTHONPATH=str(guard),
            GIT_ALLOW_PROTOCOL="file",
            REPO_CATALOG_SMOKE_AUTHORITY=str(
                outside / "tests/support/context_admission.py"
            ),
            PATH=str(venv / "bin") + os.pathsep + os.environ["PATH"],
        )
        for credential in ("GH_TOKEN", "GITHUB_TOKEN"):
            env.pop(credential, None)
        measured_exit = run(
            label + "-measure",
            [
                py,
                outside / "measure.py",
                out / (label + "-runtime.json"),
            ],
            outside,
            env,
        )
        if measured_exit:
            write(
                out / (label + "-unexecuted.json"),
                {
                    "reason": "installed runtime/schema measurement failed; see measured runtime and log",
                    "checks": ["I2", "I3", "I4", "I5", "Access"]
                    if "test_installed_i5.py" in {p.name for p in outside.iterdir()}
                    else ["I2", "I3", "I4", "Access"],
                },
            )
            continue
        measured = json.loads((out / (label + "-runtime.json")).read_text())
        with zipfile.ZipFile(artifact) as z:
            assert not any(n.startswith(("tests/", "scripts/")) for n in z.namelist())
            expected = {
                n.removeprefix("repo_catalog/"): hashlib.sha256(z.read(n)).hexdigest()
                for n in z.namelist()
                if n.startswith("repo_catalog/")
                and Path(n).suffix in (".py", ".sql", ".json")
            }
        assert expected == measured["installed_files"]
        harness.bind_artifact(outside, expected)
        for test_stage in (4,):
            verified = harness.execute_tests(
                run, label, test_stage, py, outside, out, env
            )
            records.append(
                {
                    "name": f"{label}-i{test_stage}-reconciliation",
                    "exit_code": 0 if verified else 1,
                }
            )
            write(out / "processes.json", records)
        for stage in ("i2", "i3"):
            run(
                label + "-" + stage,
                [
                    py,
                    outside / ("verify_" + stage + "_distribution.py"),
                    "--output",
                    out / (label + "-" + stage + ".json"),
                ],
                outside,
                env,
            )
        run(
            label + "-access",
            [py, outside / "original_access_smoke.py"],
            outside,
            env,
        )
    write(
        out / "summary.json",
        {"author_verification": True, "full_acceptance": False, "processes": records},
    )
    # Actual failures (including unchanged original Access refusal) are not hidden.
    raise SystemExit(int(any(r["exit_code"] for r in records)))


if __name__ == "__main__":
    main()
