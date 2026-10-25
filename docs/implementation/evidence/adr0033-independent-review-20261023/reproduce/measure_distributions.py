"""Independent direct/sdist build, complete ZIP/RECORD equality and installed probes.
Usage: selected-python measure_distributions.py SOURCE BASELINE OUTPUT WHEELHOUSE
Online dependencies must already be prepared. No dependency acquisition here.
"""

import base64
import collections
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

source, baseline, out, wheelhouse = map(lambda x: Path(x).resolve(), sys.argv[1:5])
out.mkdir(exist_ok=False)
records = []
env = {
    **os.environ,
    "UV_CACHE_DIR": "/workspace/.uv-cache",
    "PYTHONPATH": str(source / "tests/support/network_guard"),
    "GIT_ALLOW_PROTOCOL": "file",
}
for key in ("GH_TOKEN", "GITHUB_TOKEN", "PYTHONHOME"):
    env.pop(key, None)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def save(name, obj):
    (out / name).write_text(json.dumps(obj, indent=2) + "\n")


def run(name, cmd, cwd, environment=env):
    with (out / (name + ".log")).open("w") as f:
        p = subprocess.run(
            list(map(str, cmd)),
            cwd=cwd,
            env=environment,
            stdout=f,
            stderr=subprocess.STDOUT,
        )
    records.append(
        {
            "name": name,
            "command": list(map(str, cmd)),
            "cwd": str(cwd),
            "exit_code": p.returncode,
        }
    )
    save("processes.json", records)
    assert p.returncode == 0, records[-1]


for tag, root in (("before", baseline), ("after", source)):
    for target in ("wheel", "sdist"):
        run(
            tag + "-" + target,
            [
                sys.executable,
                "-m",
                "hatchling",
                "build",
                "-t",
                target,
                "-d",
                out / (tag + "-dist"),
            ],
            root,
        )
archives = {
    t: next((out / (t + "-dist")).glob("*.tar.gz")) for t in ("before", "after")
}
wheels = {t: next((out / (t + "-dist")).glob("*.whl")) for t in ("before", "after")}
sys.path.insert(0, str(source))
from scripts.check_sdist_contract import check_sdist  # noqa: E402

contract = check_sdist(archives["after"], source)
save("sdist-contract.json", contract)
extracted = out / "extracted"
extracted.mkdir()
with tarfile.open(archives["after"]) as tar:
    tar.extractall(extracted, filter="data")
rebuild_source = next(extracted.iterdir())
assert not (rebuild_source / ".git").exists()
assert not any(
    (rebuild_source / n).exists() for n in ("tests", "docs", "scripts", "uv.lock")
)
run(
    "rebuild-wheel",
    [
        sys.executable,
        "-m",
        "hatchling",
        "build",
        "-t",
        "wheel",
        "-d",
        out / "rebuilt-dist",
    ],
    rebuild_source,
)
wheels["rebuilt"] = next((out / "rebuilt-dist").glob("*.whl"))


def wheel_inventory(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        assert len(names) == len(set(names))
        content = {n: z.read(n) for n in names}
    recs = [n for n in names if n.endswith(".dist-info/RECORD")]
    assert len(recs) == 1
    record = recs[0]
    rows = list(csv.reader(io.StringIO(content[record].decode())))
    assert collections.Counter(row[0] for row in rows) == collections.Counter(names)
    for name, digest, size in rows:
        if name == record:
            assert not digest and not size
        else:
            assert digest == "sha256=" + base64.urlsafe_b64encode(
                hashlib.sha256(content[name]).digest()
            ).decode().rstrip("=")
            assert size == str(len(content[name]))
    return content


contents = {t: wheel_inventory(p) for t, p in wheels.items()}
assert contents["before"] == contents["after"] == contents["rebuilt"]
metadata = [
    b for n, b in contents["after"].items() if n.endswith(".dist-info/METADATA")
]
assert len(metadata) == 1
assert sha(metadata[0]) == contract["members"]["PKG-INFO"]["sha256"]
products = {
    n.removeprefix("src/"): item["sha256"]
    for n, item in contract["source_files"].items()
    if n.startswith("src/repo_catalog/")
}
assert len(products) == 155
assert products == {
    n: sha(b) for n, b in contents["after"].items() if n.startswith("repo_catalog/")
}
measurements = {}
for tag, archive in archives.items():
    with tarfile.open(archive) as tar:
        members = [
            {
                "name": m.name,
                "size": m.size,
                "type": m.type.decode(),
                "sha256": sha(tar.extractfile(m).read()) if m.isfile() else None,
            }
            for m in tar
        ]
    save(tag + "-members.json", members)
    measurements[tag] = {
        "bytes": archive.stat().st_size,
        "sha256": sha(archive.read_bytes()),
        "members": len(members),
        "unpacked_regular_bytes": sum(
            m["size"] for m in members if m["type"] in ("0", "")
        ),
    }
manifest = json.loads((wheelhouse / "manifest.json").read_text())
assert manifest["lock_sha256"] == sha((source / "uv.lock").read_bytes())
for r in manifest["wheels"]:
    assert sha((wheelhouse / r["file"]).read_bytes()) == r["sha256"]
# Install only locked runtime dependencies, including all transitive dependencies.
wanted = {"anyio", "certifi", "h11", "httpcore", "httpx", "idna", "typing-extensions"}
deps = [r for r in manifest["wheels"] if r["name"] in wanted]
assert {r["name"] for r in deps} == wanted
probe = Path(__file__).with_name("installed_probe.py")
for tag in ("after", "rebuilt"):
    venv = out / (tag + "-venv")
    py = venv / "bin/python"
    outside = out / (tag + "-outside")
    outside.mkdir()
    run(tag + "-venv", [sys.executable, "-m", "venv", "--without-pip", venv], out)
    req = out / (tag + "-requirements.txt")
    req.write_text(
        "repo-catalog @ "
        + wheels[tag].as_uri()
        + " --hash=sha256:"
        + sha(wheels[tag].read_bytes())
        + "\n"
        + "".join(
            r["name"]
            + " @ "
            + (wheelhouse / r["file"]).as_uri()
            + " --hash=sha256:"
            + r["sha256"]
            + "\n"
            for r in deps
        )
    )
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
            "--no-deps",
            "--require-hashes",
            "-r",
            req,
        ],
        out,
    )
    penv = {**env, "PATH": str(venv / "bin") + os.pathsep + os.environ["PATH"]}
    run(
        tag + "-probe",
        [
            py,
            "-I",
            probe,
            out / (tag + "-installed.json"),
            source / "tests/support/network_guard/sitecustomize.py",
        ],
        outside,
        penv,
    )
    installed = json.loads((out / (tag + "-installed.json")).read_text())
    assert installed["files"] == {
        n.removeprefix("repo_catalog/"): v for n, v in products.items()
    }
    measurements[tag + "-installed"] = {
        "exit_code": 0,
        "product_files": len(installed["files"]),
        "origin": installed["origin"],
        "runtime": installed["runtime"],
    }
measurements.update(
    reduction_percent=100
    * (1 - measurements["after"]["bytes"] / measurements["before"]["bytes"]),
    wheel_all_member_contents_equal=True,
    wheel_record_all_rows_verified=True,
    wheel_members=len(contents["after"]),
    product_inputs_by_suffix=dict(
        collections.Counter(Path(n).suffix for n in products)
    ),
    wheels={
        t: {"bytes": p.stat().st_size, "sha256": sha(p.read_bytes())}
        for t, p in wheels.items()
    },
)
save("measurements.json", measurements)
print(
    json.dumps(
        {k: v for k, v in measurements.items() if not k.endswith("-installed")},
        indent=2,
    )
)
