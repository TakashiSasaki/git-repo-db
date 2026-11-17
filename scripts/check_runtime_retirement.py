"""Check named legacy-test replacements before separated-runtime retirement.

This validates source references and optional collected node IDs. It does not
prove that two tests assert equivalent behavior or that any test passed.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/implementation/separated-runtime-test-map.json"
DISPOSITIONS = {"pending", "retained", "replaced", "excluded-by-adr"}


def _node_parts(node: str) -> tuple[str, tuple[str, ...]]:
    if not isinstance(node, str) or "\0" in node:
        raise ValueError("test node must be a string")
    pieces = node.split("[", 1)[0].split("::")
    path = Path(pieces[0])
    if (
        len(pieces) < 2
        or not pieces[-1].startswith("test_")
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != pieces[0]
        or not path.parts
        or path.parts[0] != "tests"
        or path.suffix != ".py"
    ):
        raise ValueError("invalid repository test node: " + node)
    return pieces[0], tuple(pieces[1:])


def _symbols(path: Path) -> set[tuple[str, ...]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()

    def visit(body, prefix=()):
        for node in body:
            if isinstance(node, ast.ClassDef):
                visit(node.body, (*prefix, node.name))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found.add((*prefix, node.name))
            elif isinstance(node, ast.ImportFrom):
                # Parameterized imported tests are checked by actual collection
                # when supplied; do not execute arbitrary imports in this audit.
                found.update(
                    (*prefix, alias.asname or alias.name) for alias in node.names
                )

    visit(tree.body)
    return found


def check(
    data: dict, root: Path = ROOT, *, complete=False, collected=None
) -> list[str]:
    errors = []
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        return ["unsupported retirement map version"]
    baseline = data.get("baseline_commit")
    records = data.get("obligations")
    if not isinstance(baseline, str) or not re.fullmatch(r"[a-f0-9]{40}", baseline):
        return ["baseline must be an exact Git commit"]
    if not isinstance(records, list) or not records:
        return ["nonempty retirement obligations are required"]
    seen, symbols, blobs = set(), {}, {}

    def exists(node):
        source, qualified = _node_parts(node)
        if source not in symbols:
            path = root / source
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("linked test escapes checkout: " + source)
            try:
                symbols[source] = _symbols(path)
            except FileNotFoundError:
                symbols[source] = set()
        return qualified in symbols[source]

    for record in records:
        if not isinstance(record, dict):
            errors.append("obligation must be an object")
            continue
        node = record.get("legacy_node")
        try:
            source, _ = _node_parts(node)
            if node in seen:
                errors.append("duplicate legacy node: " + node)
            seen.add(node)
            if source not in blobs:
                result = subprocess.run(
                    ["git", "rev-parse", "--verify", f"{baseline}:{source}"],
                    cwd=root,
                    text=True,
                    capture_output=True,
                )
                blobs[source] = (
                    result.stdout.strip() if result.returncode == 0 else None
                )
            if not blobs[source] or record.get("legacy_blob") != blobs[source]:
                errors.append(node + ": baseline blob mismatch")
            disposition = record.get("disposition")
            replacements = record.get("replacement_nodes")
            if disposition not in DISPOSITIONS:
                errors.append(node + ": invalid disposition")
                continue
            if (
                not isinstance(record.get("reason"), str)
                or not record["reason"].strip()
            ):
                errors.append(node + ": concrete behavior/authority reason required")
            if not isinstance(replacements, list):
                errors.append(node + ": replacement_nodes must be a list")
                continue
            if disposition == "pending":
                if complete or not exists(node):
                    errors.append(node + ": pending obligation cannot be retired")
                continue
            if not replacements:
                errors.append(node + ": a named replacement/control is required")
            for target in replacements:
                if not exists(target):
                    errors.append(node + ": replacement source missing: " + target)
                elif collected is not None and target not in collected:
                    errors.append(
                        node + ": replacement not actually collected: " + target
                    )
            if disposition == "retained" and not exists(node):
                errors.append(node + ": retained test is absent")
        except (ValueError, TypeError, OSError, SyntaxError) as error:
            errors.append(str(node) + ": " + str(error))
    if complete:
        retired_modules = data.get("retired_modules")
        if not isinstance(retired_modules, list) or not retired_modules:
            errors.append("complete retirement requires explicit obsolete module paths")
            retired_modules = []
        for source in retired_modules:
            path = Path(source)
            if path.is_absolute() or ".." in path.parts or path.as_posix() != source:
                errors.append("invalid retired module path: " + source)
            elif (root / path).exists():
                errors.append("retired module remains: " + source)
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument(
        "--complete",
        action="store_true",
        help="require no pending obligations or obsolete modules",
    )
    parser.add_argument(
        "--collected-nodes",
        type=Path,
        help="actual pytest collection output, never a pass receipt",
    )
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
        collected = None
        if args.collected_nodes:
            lines = args.collected_nodes.read_text(encoding="utf-8").splitlines()
            collected = Counter(
                line.strip() for line in lines if re.match(r"^tests/[^\s]+\.py::", line)
            )
            if not collected or any(count != 1 for count in collected.values()):
                raise ValueError("collection must contain unique actual test node IDs")
        errors = check(data, complete=args.complete, collected=collected)
    except (ValueError, OSError, TypeError) as error:
        print("Retirement map: " + str(error), file=sys.stderr)
        return 1
    if errors:
        for error in errors[:30]:
            print("Retirement map: " + error, file=sys.stderr)
        if len(errors) > 30:
            print(f"Retirement map: {len(errors) - 30} further errors", file=sys.stderr)
        return 1
    counts = Counter(record["disposition"] for record in data["obligations"])
    print(
        "Retirement map references OK: "
        + ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
