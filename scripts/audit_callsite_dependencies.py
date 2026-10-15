"""Reproduce the baseline lexical dependency index; see its limits in the report."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/implementation/callsite-dependencies.json"


def build():
    source = ROOT / "src/repo_catalog"
    resources = source / "resources"
    vocabulary = set()
    for path in sorted(resources.glob("*.sql")):
        vocabulary.update(
            re.findall(
                r"CREATE\s+(?:TABLE|VIEW)\s+(\w+)", path.read_text(), re.IGNORECASE
            )
        )
    names = sorted(vocabulary)
    pattern = re.compile(r"\b(?:" + "|".join(names) + r")\b")
    modules, references, revisions = [], [], []
    paths = sorted(source.rglob("*.py")) + sorted(resources.glob("*.sql"))
    # Prototypes deliberately do not become baseline production dependencies.
    paths = [
        p for p in paths if "spikes" not in p.parts and "experimental" not in p.parts
    ]
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        text = path.read_text()
        definitions = []
        if path.suffix == ".py":
            definitions = [
                (node.lineno, node.end_lineno, node.name)
                for node in ast.walk(ast.parse(text))
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
        modules.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "functions": [
                    {"name": name, "line": start, "end_line": end}
                    for start, end, name in sorted(definitions)
                ],
            }
        )
        for number, line in enumerate(text.splitlines(), 1):
            enclosing = sorted(
                (end - start, name)
                for start, end, name in definitions
                if start <= number <= end
            )
            tables = sorted(set(pattern.findall(line)))
            if tables:
                references.append(
                    {
                        "path": relative,
                        "line": number,
                        "function": enclosing[0][1] if enclosing else None,
                        "subjects": tables,
                        "sql_operations": sorted(
                            set(
                                re.findall(
                                    r"\b(?:SELECT|INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|JOIN|REFERENCES)\b",
                                    line.upper(),
                                )
                            )
                        ),
                    }
                )
            if any(
                token in line
                for token in (
                    "local_revision",
                    "advance_local_revision",
                    "core_revision_fence",
                    ".revision()",
                )
            ):
                revisions.append(
                    {
                        "path": relative,
                        "line": number,
                        "function": enclosing[0][1] if enclosing else None,
                        "source": line.strip(),
                    }
                )
    return {
        "format": "git-repo-db/implementation-callsite-audit-v1",
        "baseline_main": "57de60b65c2ef29420a885b0c2102dc90e11fa75",
        "status": "baseline-source-index-not-target-implementation",
        "method": "All production Python and packaged SQL; AST enclosing functions and literal table/view vocabulary. Source SHA-256 detects drift. Manual semantic interpretation is in callsite-dependencies.md and legacy-operations.md.",
        "limits": [
            "Lexical references include declarations, comments and vocabulary, not proven executed SQL.",
            "Dynamic SQL variable substitutions are traced manually by module and function in the companion report; this index cannot prove dynamic reachability or absence of an indirect byte path.",
            "No runtime tracing, live collection, production catalog reads or real-data migration performed.",
        ],
        "modules": modules,
        "table_and_view_vocabulary": names,
        "references": references,
        "revision_dependencies": revisions,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    options = parser.parse_args()
    serialized = json.dumps(build(), indent=2, ensure_ascii=False) + "\n"
    if options.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != serialized:
            raise SystemExit(
                "Call-site index drift: regenerate and review changed sources"
            )
        print("Call-site dependency source index matches")
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(serialized)
        print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
