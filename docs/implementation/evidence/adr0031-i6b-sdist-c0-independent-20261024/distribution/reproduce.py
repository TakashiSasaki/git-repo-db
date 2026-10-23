"""Independent published-PR155 archive review. Run with stdlib Python.

No production function is replaced. The checker is the subject under test;
independent member/ZIP/RECORD comparisons below are the build oracles.
"""

import argparse
import base64
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import os
import random
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def run(argv, cwd, out, name, env=None):
    proc = subprocess.run(argv, cwd=cwd, env=env, capture_output=True)
    (out / (name + ".stdout")).write_bytes(proc.stdout)
    (out / (name + ".stderr")).write_bytes(proc.stderr)
    save(out / (name + ".execution.json"), {
        "argv": list(map(str, argv)), "cwd": str(cwd), "exit": proc.returncode,
        "stdout_bytes": len(proc.stdout), "stdout_sha256": sha(proc.stdout),
        "stderr_bytes": len(proc.stderr), "stderr_sha256": sha(proc.stderr),
    })
    return proc


def module(path):
    spec = importlib.util.spec_from_file_location("published_checker", path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def zip_inventory(path):
    result, contents = {}, {}
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        for i in z.infolist():
            assert i.filename not in result and not i.is_dir()
            raw = z.read(i)
            contents[i.filename] = raw
            result[i.filename] = {
                "bytes": len(raw), "sha256": sha(raw),
                **{k: getattr(i, k) for k in (
                    "compress_type", "create_system", "create_version",
                    "extract_version", "flag_bits", "volume", "internal_attr",
                    "external_attr", "CRC", "compress_size", "header_offset",
                    "date_time",
                )}, "extra_hex": i.extra.hex(), "comment_hex": i.comment.hex(),
            }
        record = next(n for n in contents if n.endswith(".dist-info/RECORD"))
        seen = set()
        for name, digest, size in csv.reader(io.StringIO(contents[record].decode())):
            assert name in contents and name not in seen
            seen.add(name)
            expected = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(contents[name]).digest()).rstrip(b"=").decode()
            assert (digest == expected and size == str(len(contents[name]))) if name != record else (not digest and not size)
        assert seen == set(contents)
    return result, contents


def builds(root, out, python):
    names = subprocess.check_output(["git", "ls-files", "-z", "src/repo_catalog"], cwd=root).decode().split("\0")[:-1]
    names += ["pyproject.toml", "README.md", ".gitignore"]
    source = {n: {"bytes": len((root/n).read_bytes()), "sha256": sha((root/n).read_bytes())} for n in names}
    save(out / "source-inventory.json", source)
    direct = out / "direct"
    direct.mkdir(exist_ok=True)
    p = run([python, "-m", "hatchling", "build", "-t", "wheel", "-t", "sdist", "-d", str(direct)], root, out, "direct-build")
    assert p.returncode == 0
    sdist = next(direct.glob("*.tar.gz"))
    wheel = next(direct.glob("*.whl"))
    checker = module(root / "scripts/check_sdist_contract.py")
    checked = checker.check_sdist(sdist, root)
    save(out / "published-checker-receipt.json", checked)
    raw_tar = gzip.decompress(sdist.read_bytes())
    # This comparison reads all members independently of source_inventory/check_sdist.
    with tarfile.open(fileobj=io.BytesIO(raw_tar), mode="r:") as tar:
        members = tar.getmembers()
        content = {i.name.split("/", 1)[1]: tar.extractfile(i).read() for i in members if i.isfile()}
        assert len(members) == len(content) == len(source) + 1
        assert set(content) == set(source) | {"PKG-INFO"}
        for n in source:
            assert content[n] == (root/n).read_bytes()
        assert all(i.type in (tarfile.REGTYPE, tarfile.AREGTYPE) for i in members)
        assert len(sdist.read_bytes()) <= 2097152 and len(members) <= 512
        assert sum(map(len, content.values())) <= 8388608
    extracted = out / "backend-only-source"
    extracted.mkdir(exist_ok=True)
    for name, raw in content.items():
        p = extracted / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
    # Build entrypoint invokes only the installed backend: PATH cannot find Git.
    runner = out / "backend_build.py"
    runner.write_text("import hatchling.build,sys; print(hatchling.build.build_wheel(sys.argv[1]))\n")
    derived = out / "derived"
    derived.mkdir(exist_ok=True)
    env = {**os.environ, "PATH": str(Path(python).parent), "PYTHONPATH": "", "GIT_CONFIG_NOSYSTEM": "1"}
    p = run([python, str(runner), str(derived)], extracted, out, "backend-only-build", env)
    assert p.returncode == 0 and not (extracted/".git").exists()
    derived_wheel = next(derived.glob("*.whl"))
    left, lc = zip_inventory(wheel)
    right, rc = zip_inventory(derived_wheel)
    assert left == right and lc == rc
    assert wheel.read_bytes() == derived_wheel.read_bytes()
    assert content["PKG-INFO"] == next(raw for n, raw in lc.items() if n.endswith(".dist-info/METADATA"))
    for n in names:
        if n.startswith("src/"):
            assert lc[n[4:]] == (root/n).read_bytes()
    save(out / "wheel-members.json", left)
    result = {
        "sdist": {"bytes": sdist.stat().st_size, "sha256": sha(sdist.read_bytes()), "regular_bytes": sum(map(len,content.values())), "members": len(members), "tar_bytes": len(raw_tar)},
        "wheel": {"bytes": wheel.stat().st_size, "sha256": sha(wheel.read_bytes()), "members": len(left)},
        "product": {"files": len(names)-3, "bytes": sum(v["bytes"] for n,v in source.items() if n.startswith("src/")), "suffix_counts": {s: sum(n.endswith(s) for n in names if n.startswith("src/")) for s in (".py", ".sql", ".json", ".graphql")}},
        "equal_full_zip_bytes_metadata_record": True,
        "backend_without_git_on_PATH": shutil.which("git", path=env["PATH"]) is None,
    }
    save(out / "build-measurements.json", result)
    return sdist, extracted


def attacks(root, out, sdist, source):
    checker = module(root / "scripts/check_sdist_contract.py")
    raw = gzip.decompress(sdist.read_bytes())
    good = sdist.read_bytes()
    cases = {}
    cases["crc"] = good[:-8] + bytes([good[-8] ^ 1]) + good[-7:]
    cases["isize"] = good[:-4] + bytes([good[-4] ^ 1]) + good[-3:]
    cases["missing-trailer"] = good[:-8]
    cases["truncated-deflate"] = good[:-50]
    cases["trailing-zero"] = good + b"\0"
    cases["concatenation"] = good + gzip.compress(b"separate hidden stream")
    cases["malformed-second-gzip"] = good + b"\x1f\x8b\x08"
    cases["tar-tail-hidden"] = gzip.compress(raw + b"x" * 512)
    cases["tar-stream-overflow"] = gzip.compress(b"\0" * (checker.MAX_TAR_STREAM + 512))
    cases["compressed-overflow"] = random.Random(155).randbytes(2097153)
    for kind in (tarfile.XHDTYPE, tarfile.XGLTYPE, tarfile.GNUTYPE_LONGNAME, tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE):
        info = tarfile.TarInfo("PaxHeaders/hidden")
        info.type = kind
        info.size = 1024
        cases["raw-header-"+kind.hex()] = gzip.compress(info.tobuf(format=tarfile.USTAR_FORMAT) + b"x" * 1024 + raw)
    # Rebuild malformed logical archives independently, preserving all other data.
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        originals = [(i, tar.extractfile(i).read()) for i in tar.getmembers()]
    def modified(name, transform):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as t:
            for info, data in transform(originals):
                t.addfile(info, io.BytesIO(data))
        cases[name] = gzip.compress(stream.getvalue())
    for n, bad in (("traversal","../escape"),("absolute","/absolute"),("backslash","x\\y"),("duplicate",originals[0][0].name)):
        info = tarfile.TarInfo(bad)
        info.size = 1
        modified(n, lambda rows, i=info: rows + [(i,b"x")])
    for n, data in (("metadata-duplicate-name",b"Metadata-Version: 2.4\nName: repo-catalog\nName: repo-catalog\nVersion: 0.2.0\n\n"),("metadata-bad-version",b"Metadata-Version: malformed\nName: repo-catalog\nVersion: 0.2.0\n\n"),("metadata-wrong-identity",b"Metadata-Version: 2.4\nName: other\nVersion: 0.2.0\n\n")):
        def replacement(rows, d=data):
            result=[]
            for i,b in rows:
                if i.name.endswith("/PKG-INFO"):
                    i=tarfile.TarInfo(i.name);i.size=len(d);b=d
                result.append((i,b))
            return result
        modified(n,replacement)
    results=[]
    specimens=out/"attacks";specimens.mkdir(exist_ok=True)
    for name, data in cases.items():
        path=specimens/(name+".tar.gz");path.write_bytes(data)
        try:
            checker.check_sdist(path, source)
            error=None
        except ValueError as e:
            error=str(e)
        results.append({"name":name,"compressed_bytes":len(data),"sha256":sha(data),"rejected":error is not None,"error":error})
    save(out/"adversarial-results.json",results)
    assert all(c["rejected"] for c in results)


def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--out",type=Path,required=True);p.add_argument("--build-python",required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    save(a.out/"source-binding.json",{"head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=a.root,text=True).strip(),"tree":subprocess.check_output(["git","rev-parse","HEAD^{tree}"],cwd=a.root,text=True).strip(),"checker_sha256":sha((a.root/"scripts/check_sdist_contract.py").read_bytes()),"driver_sha256":sha(Path(__file__).read_bytes())})
    sdist,source=builds(a.root,a.out,a.build_python)
    attacks(a.root,a.out,sdist,source)
    print("build equivalence and independent adversarial vectors passed")


if __name__ == "__main__":
    main()
