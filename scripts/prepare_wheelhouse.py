"""Online preparation only: copy compatible, SHA-256-pinned uv.lock wheels.

Offline builds/installations use --no-index --find-links against this directory,
so registry resolver metadata and the machine's pre-existing uv cache are irrelevant.
"""

import argparse
import hashlib
import json
import tomllib
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename


def prepare(lock, output):
    raw = lock.read_bytes()
    packages = tomllib.loads(raw.decode())["package"]
    tags = list(sys_tags())
    ranks = {tag: rank for rank, tag in enumerate(tags)}
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for package in packages:
        if "registry" not in package["source"]:
            continue
        compatible = []
        for wheel in package.get("wheels", []):
            name = Path(urlsplit(wheel["url"]).path).name
            wheel_tags = parse_wheel_filename(name)[3]
            rank = min((ranks[t] for t in wheel_tags if t in ranks), default=None)
            if rank is not None:
                compatible.append((rank, name, wheel))
        if not compatible:
            raise ValueError(f"No locked wheel for this interpreter: {package['name']}")
        _, name, wheel = min(compatible)
        expected = wheel["hash"].removeprefix("sha256:")
        path = output / name
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            with urllib.request.urlopen(wheel["url"], timeout=60) as response:
                body = response.read()
            if hashlib.sha256(body).hexdigest() != expected:
                raise ValueError(f"Wheel hash mismatch: {name}")
            temporary = output / (name + ".part")
            temporary.write_bytes(body)
            temporary.replace(path)
        records.append({"name": package["name"], "file": name, "sha256": expected})
    selected = {r["file"] for r in records}
    extra = {p.name for p in output.glob("*.whl")} - selected
    if extra:
        raise ValueError("Use an empty wheelhouse: unexpected wheels present")
    (output / "manifest.json").write_text(
        json.dumps(
            {"lock_sha256": hashlib.sha256(raw).hexdigest(), "wheels": records},
            indent=2,
        )
        + "\n"
    )
    return len(records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=Path("uv.lock"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/wheelhouse"))
    args = parser.parse_args()
    print(f"Prepared {prepare(args.lock, args.output)} locked wheels")
