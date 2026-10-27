"""Check pinned documentation/product/IR input consistency, not acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath


class EvidenceError(ValueError):
    """Required input evidence is missing, malformed or inconsistent."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(repository: Path, *args: str) -> bytes:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repository), *args], stderr=subprocess.PIPE
        )
    except subprocess.CalledProcessError as exc:
        raise EvidenceError("Required committed input is unavailable") from exc


def source_identity(repository: Path, commit: str) -> dict[str, str]:
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise EvidenceError("Explicit full commit SHA required")
    if git(repository, "cat-file", "-t", commit).strip() != b"commit":
        raise EvidenceError("Source must identify a commit")
    tree = git(repository, "rev-parse", commit + "^{tree}").decode().strip()
    return {"commit": commit, "tree": tree}


def checked_blob(repository: Path, commit: str, path: str) -> bytes:
    if (
        not isinstance(path, str)
        or not path
        or "\\" in path
        or PurePosixPath(path).is_absolute()
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        raise EvidenceError("Input path must be a normalized repository-relative file")
    entry = git(repository, "ls-tree", "-z", commit, "--", path).split(b"\0")
    if len(entry) != 2 or not entry[0]:
        raise EvidenceError("Exactly one committed input file required")
    metadata, actual = entry[0].split(b"\t", 1)
    if actual.decode() != path or metadata.split()[0] not in {b"100644", b"100755"}:
        raise EvidenceError("Input must be a regular committed file")
    return git(repository, "cat-file", "blob", commit + ":" + path)


def read_manifest(path: Path) -> tuple[dict, str]:
    try:
        raw = path.read_bytes()
        manifest = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise EvidenceError("Producer manifest is missing or malformed") from exc
    if not isinstance(manifest, dict):
        raise EvidenceError("Producer manifest must be an object")
    return manifest, digest(raw)


def input_record(
    repository: Path,
    documentation_source: str,
    product_source: str,
    manifest_path: Path,
    ir_path: Path,
) -> dict:
    documentation = source_identity(repository, documentation_source)
    product = source_identity(repository, product_source)
    manifest, manifest_hash = read_manifest(manifest_path)
    if (
        type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != 1
        or manifest.get("product_source") != product
    ):
        raise EvidenceError("Producer selected product identity does not match")
    try:
        ir_bytes = ir_path.read_bytes()
        ir = json.loads(ir_bytes)
    except (OSError, ValueError) as exc:
        raise EvidenceError("Neutral IR is missing or malformed") from exc
    if not isinstance(ir, dict) or not ir:
        raise EvidenceError("Neutral IR must be a nonempty object")
    ir_hash = digest(ir_bytes)
    if manifest.get("ir_sha256") != ir_hash:
        raise EvidenceError("Neutral IR digest does not match")
    inputs = manifest.get("input_sha256")
    if not isinstance(inputs, dict) or not inputs:
        raise EvidenceError("Nonempty producer input hashes required")
    for path, expected in inputs.items():
        if (
            not isinstance(expected, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected)
            or digest(checked_blob(repository, product_source, path)) != expected
        ):
            raise EvidenceError("Producer input hash does not match")
    return {
        "schema_version": 1,
        "scope": "documentation-input-consistency-only",
        "documentation_source": documentation,
        "selected_product_source": product,
        "neutral_ir_sha256": ir_hash,
        "producer_manifest_sha256": manifest_hash,
        "producer_input_sha256": dict(sorted(inputs.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--documentation-source", required=True)
    parser.add_argument("--product-source", required=True)
    parser.add_argument("--producer-manifest", type=Path, required=True)
    parser.add_argument("--ir", type=Path, required=True)
    args = parser.parse_args()
    try:
        record = input_record(
            args.repository,
            args.documentation_source,
            args.product_source,
            args.producer_manifest,
            args.ir,
        )
    except EvidenceError as exc:
        parser.exit(2, f"input provenance refused: {exc}\n")
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
