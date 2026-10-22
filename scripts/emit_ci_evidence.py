"""Emit bounded, indexed CI receipts when artifact blob access is unavailable."""

import base64
import hashlib
import io
import json
import os
import subprocess
import textwrap
import zipfile
from pathlib import Path


def main():
    files = {}
    for root in (Path("artifacts/access-registry"), Path("artifacts/runtime")):
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root)
            if any(
                part in {"source", "from-sdist", "outside"} or part.endswith("-venv")
                for part in relative.parts
            ):
                continue
            if path.is_file() and path.suffix in {
                ".json",
                ".jsonl",
                ".xml",
                ".txt",
                ".log",
                ".md",
            }:
                files[str(path)] = path.read_bytes()
    files["receipt-binding.json"] = (
        json.dumps(
            {
                "head": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], text=True
                ).strip(),
                "tree": subprocess.check_output(
                    ["git", "rev-parse", "HEAD^{tree}"], text=True
                ).strip(),
                "run_id": os.environ["GITHUB_RUN_ID"],
                "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
            },
            sort_keys=True,
        )
        + "\n"
    ).encode()
    files["receipt-index.json"] = (
        json.dumps(
            {
                name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                for name, data in files.items()
            },
            sort_keys=True,
        )
        + "\n"
    ).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    body = buffer.getvalue()
    if len(body) > 4 * 1024 * 1024:
        raise SystemExit("CI receipt exceeds 4 MiB; retrieve the uploaded artifact")
    digest = hashlib.sha256(body).hexdigest()
    print(f"CI_RECEIPTS_BEGIN_V1 {digest} {len(body)}")
    for line in textwrap.wrap(base64.b64encode(body).decode("ascii"), 120):
        print("CI_RECEIPTS_DATA_V1 " + line)
    print("CI_RECEIPTS_END_V1 " + digest)


if __name__ == "__main__":
    main()
