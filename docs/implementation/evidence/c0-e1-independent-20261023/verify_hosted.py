"""Strictly validate actual timestamped receipt records and optional artifact."""

import argparse
import base64
import hashlib
import io
import json
import re
import subprocess
import zipfile
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify(log, run, head, base, artifact=None):
    pattern = r"^\d{4}-\d\d-\d\dT\S+ (CI_RECEIPTS_(?:BEGIN|DATA|END)_V1 .+)$"
    records = re.findall(pattern, log.read_text(), re.M)
    assert records and records[0].startswith("CI_RECEIPTS_BEGIN_V1 ")
    assert records[-1].startswith("CI_RECEIPTS_END_V1 ")
    _, digest, length = records[0].split()
    assert records[-1].split() == ["CI_RECEIPTS_END_V1", digest]
    chunks = []
    for record in records[1:-1]:
        marker, chunk = record.split()
        assert marker == "CI_RECEIPTS_DATA_V1" and len(chunk) <= 120
        chunks.append(chunk)
    body = base64.b64decode("".join(chunks), validate=True)
    assert sha(body) == digest and len(body) == int(length) <= 2_097_152
    root = Path.cwd()

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()

    tree = git("rev-parse", f"{head}^{{tree}}")
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(set(z.namelist()))
        index = json.loads(z.read("receipt-index.json"))
        assert set(index) == set(z.namelist()) - {"receipt-index.json"}
        for name, meta in index.items():
            data = z.read(name)
            assert meta == {"bytes": len(data), "sha256": sha(data)}
        binding = json.loads(z.read("receipt-binding.json"))
        manifest = json.loads(z.read("validation-manifest.json"))
        assert binding["run_id"] == str(run) and binding["run_attempt"] == "1"
        assert binding["feature_sha"] == head and binding["tree"] == tree
        checkout = binding["head"]
        assert git("rev-parse", f"{checkout}^{{tree}}") == tree
        parents = git("show", "-s", "--format=%P", checkout).split()
        assert parents == [base, head]
        c = manifest["context"]
        assert c["run_id"] == str(run) and c["run_attempt"] == "1"
        assert c["tested_sha"] == checkout and c["feature_sha"] == head
        assert c["base_sha"] == base and manifest["tree_sha"] == tree
        assert manifest["acceptance_status"] == "development_checks_passed"
        assert manifest["full_acceptance"] is False
        assert manifest["coverage"]["executed"] == 0
        shared = []
        if artifact:
            raw = artifact.read_bytes()
            with zipfile.ZipFile(io.BytesIO(raw)) as a:
                assert a.testzip() is None
                for name in index:
                    if name == "receipt-binding.json":
                        continue
                    assert a.read("ci-profile/" + name) == z.read(name)
                    shared.append(name)
                artifact_result = {
                    "bytes": len(raw),
                    "sha256": sha(raw),
                    "members": len(a.namelist()),
                    "identical_shared_members": shared,
                }
        else:
            artifact_result = None
    return {
        "run_id": run,
        "head": head,
        "tree": tree,
        "checkout": checkout,
        "parents": parents,
        "receipt_bytes": len(body),
        "receipt_sha256": sha(body),
        "verified_indexed_members": len(index),
        "binding": binding,
        "acceptance_status": manifest["acceptance_status"],
        "full_acceptance": False,
        "hosted_product_pytest_executed": manifest["coverage"]["executed"],
        "unexecuted_required_files": len(manifest["coverage"]["required_files"]),
        "runtime": manifest["runtime"],
        "artifact": artifact_result,
        "exit_code": 0,
    }, body


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--log", type=Path, required=True)
    p.add_argument("--run", type=int, required=True)
    p.add_argument("--head", required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--artifact", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result, body = verify(args.log, args.run, args.head, args.base, args.artifact)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    args.output.with_suffix(".zip").write_bytes(body)
    print(json.dumps(result, indent=2))
