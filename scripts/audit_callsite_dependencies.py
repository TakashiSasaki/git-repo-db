"""Index every current distribution source with explicit lexical-analysis limits."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/implementation/callsite-dependencies.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.check_sdist_contract import distribution_workspace  # noqa: E402

PROJECTS = distribution_workspace(ROOT)[1]
SOURCE_ROOTS = tuple(project / "src" for project in PROJECTS)
SOURCE_OWNERS = {
    project / "src": tomllib.loads((project / "pyproject.toml").read_text())["project"][
        "name"
    ]
    for project in PROJECTS
}


def source_relative(path: Path, roots=None) -> Path:
    """One installed namespace path, independent of its distribution's root."""
    for source in SOURCE_ROOTS if roots is None else roots:
        if path.is_relative_to(source):
            return path.relative_to(source)
    raise ValueError(f"Unrecognized product source owner: {path}")


def owned_source(relative: str) -> str:
    matches = [
        source / "repo_catalog" / relative
        for source in SOURCE_ROOTS
        if (source / "repo_catalog" / relative).is_file()
    ]
    if len(matches) > 1:
        raise ValueError(f"Overlapping installed source ownership: {relative}")
    # Optional later-stage paths may be absent in an isolated stage checkout.
    return (
        (matches[0] if matches else SOURCE_ROOTS[0] / "repo_catalog" / relative)
        .relative_to(ROOT)
        .as_posix()
    )


def source_files(suffixes=(".py",), *, roots=None) -> list[Path]:
    """Scan every owner; refuse two owners for any installed product file."""
    roots = SOURCE_ROOTS if roots is None else roots
    result, owners = [], {}
    for source in roots:
        for path in sorted((source / "repo_catalog").rglob("*")):
            if path.suffix not in suffixes or not path.is_file():
                continue
            relative = source_relative(path, roots).as_posix()
            if relative in owners:
                raise ValueError(f"Overlapping installed source ownership: {relative}")
            owners[relative] = path
            result.append(path)
    return sorted(result)


def source_owner(path: Path) -> str:
    return next(
        owner for source, owner in SOURCE_OWNERS.items() if path.is_relative_to(source)
    )


def product_imports(source: str, package: str) -> set[str]:
    """Direct namespace imports only; dynamic loading is not a reachability proof."""
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = importlib.util.resolve_name("." * node.level + module, package)
            imported.add(module)
            imported.update(module + "." + alias.name for alias in node.names)
    return {name for name in imported if name.startswith("repo_catalog.")}


def build():
    from scripts.schema_inventory import introspect_all

    schemas = introspect_all()["stores"]
    vocabulary = {}
    for role, schema in schemas.items():
        for name in [*schema["tables"], *schema["views"]]:
            vocabulary.setdefault(name, []).append(role)
    names = sorted(vocabulary)
    pattern = re.compile(r"\b(?:" + "|".join(names) + r")\b")
    modules, references, revisions = [], [], []
    paths = source_files() + source_files((".sql",))
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
        entry = {
            "path": relative,
            "owner": source_owner(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "direct_product_imports": sorted(
                product_imports(text, ".".join(source_relative(path).parent.parts))
            )
            if path.suffix == ".py"
            else [],
            "functions": [
                {"name": name, "line": start, "end_line": end}
                for start, end, name in sorted(definitions)
            ],
        }
        modules.append(entry)
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
                    "repository_revision_fence",
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
        "format": "resource-atlas/implementation-callsite-audit-v2",
        "status": "current-separated-source-index",
        "method": "Every declared distribution source is syntax-checked, hashed and indexed. Table/view vocabulary comes from current in-memory schema factories. Literal references and direct imports do not prove dynamic runtime reachability or SQL authority.",
        "source_roots": {
            source.relative_to(ROOT).as_posix(): owner
            for source, owner in SOURCE_OWNERS.items()
        },
        "packaged_resources": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "owner": source_owner(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in source_files((".sql", ".json", ".graphql"))
        ],
        "limits": [
            "Lexical references include declarations, comments and vocabulary, not proven executed SQL.",
            "Dynamic SQL variable substitutions are traced manually by module and function in the companion report; this index cannot prove dynamic reachability or absence of an indirect byte path.",
            "No runtime tracing, live collection, production catalog reads or real-data migration performed.",
        ],
        "modules": modules,
        "table_and_view_vocabulary": names,
        "schema_owners": vocabulary,
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
