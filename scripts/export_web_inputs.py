"""Export source-bound website inputs in the verified product interpreter."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.schema_inventory import ROOT, export_inventory  # noqa: E402
from scripts.verification_outputs import write_private_json  # noqa: E402


def export(output: Path, source: str) -> dict:
    policy_path = "docs/web-source-policy.json"
    policy_bytes = (ROOT / policy_path).read_bytes()
    committed = subprocess.check_output(
        ["git", "show", source + ":" + policy_path], cwd=ROOT
    )
    if policy_bytes != committed:
        raise ValueError("Publication policy differs from selected product source")
    policy = json.loads(policy_bytes)
    paths = [
        policy_path,
        policy["canonical_index"],
        *policy["public_adrs"],
        *policy["support"],
    ]
    hashes = {}
    for name in paths:
        relative = Path(name)
        path = ROOT / relative
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative.parts[0] != "docs"
        ):
            raise ValueError("Invalid canonical source path")
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("Linked canonical source refused")
        raw = subprocess.check_output(["git", "show", source + ":" + name], cwd=ROOT)
        if path.read_bytes() != raw:
            raise ValueError("Canonical source differs from selected commit: " + name)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    producer = export_inventory(output, source)
    handoff = {
        "schema_version": 1,
        "product_source": producer["product_source"],
        "ir_sha256": producer["ir_sha256"],
        "canonical_sources": hashes,
    }
    write_private_json(ROOT, output / "source-manifest.json", handoff)
    return handoff


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = export(args.output.resolve(), args.source)
    print(
        json.dumps(
            {
                "product_source": result["product_source"],
                "canonical_sources": len(result["canonical_sources"]),
                "ir_sha256": result["ir_sha256"],
            }
        )
    )


if __name__ == "__main__":
    main()
