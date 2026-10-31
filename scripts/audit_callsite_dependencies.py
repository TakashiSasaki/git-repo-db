"""Reproduce the baseline lexical dependency index; see its limits in the report."""

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


# This explicit list is the isolated P1 target, not the normal Schema 21 runtime.
# Do not expand it to a filename-prefix ignore: newly integrated runtime paths
# must enter the baseline source audit when P8 switches the application.
ISOLATED_P1_MODULES = frozenset(
    owned_source(relative)
    for relative in (
        "adapters/sqlite/p1_schema.py",
        "adapters/sqlite/p1_core.py",
        "adapters/sqlite/p1_context.py",
        "adapters/sqlite/p1_coordination.py",
        "adapters/sqlite/core_coordination.py",
        "domain/shared_values.py",
        "domain/query_work.py",
        "domain/p1_core.py",
        "domain/ref_observation.py",
        "domain/ref_coverage.py",
        "domain/p1_context.py",
        "domain/p1_coverage.py",
        "domain/p1_coordination.py",
        "domain/ports/p1_core.py",
        "domain/ports/p1_context.py",
        "domain/ports/p1_coordination.py",
    )
)

# These explicit optional paths belong to the opt-in P2/P3/P4/P5/P6/P7 implementations.
# A sibling branch need not contain the other stage's modules. Their presence
# does not change the historical Schema 21 call-site inventory or activate them.
ISOLATED_NEXT_STAGE_MODULES = frozenset(
    owned_source(relative)
    for relative in (
        "adapters/git/native.py",
        "adapters/sqlite/git_core.py",
        "domain/git_native.py",
        "adapters/sqlite/production_context.py",
        "domain/production_context.py",
        "domain/resource_identification.py",
        "domain/parent_report.py",
        "domain/transfer_sql.py",
        "domain/resource_stage.py",
        "domain/context_registration.py",
        # I6-A is part of the same opt-in target; classify exact modules, never
        # hide future similarly named public-runtime files by a prefix rule.
        "domain/context_admission.py",
        "domain/ports/context_authorization.py",
        "adapters/sqlite/context_admission.py",
        "domain/ports/production_context.py",
        "domain/notes.py",
        "domain/ports/notes.py",
        "application/notes.py",
        "application/ref_observations.py",
        "adapters/git/notes.py",
        "adapters/sqlite/notes.py",
        "domain/acquisition.py",
        "domain/exchange.py",
        "domain/ref_exchange.py",
        "domain/selective_exchange.py",
        "domain/exchange_rows.py",
        # I6-B pure codecs/plans remain in the same explicit opt-in boundary.
        "domain/context_wire.py",
        "domain/context_dependencies.py",
        "domain/ports/acquisition.py",
        "application/acquisition.py",
        "application/exchange.py",
        "application/ref_exchange.py",
        "adapters/github/production_intake.py",
        "adapters/sqlite/acquisition.py",
        "domain/production_query.py",
        "domain/ports/production_query.py",
        "application/production_query.py",
        "adapters/sqlite/production_search.py",
        "application/core_query.py",
        "application/query_encoding.py",
        "domain/core_query.py",
        "domain/query_contracts.py",
        "domain/ports/core_query.py",
        "cli/production_query.py",
        "cli/query_features.py",
        "domain/recovery.py",
        "domain/ports/recovery.py",
        "application/recovery.py",
        "adapters/sqlite/recovery.py",
        "adapters/sqlite/recovery_budget.py",
        "adapters/sqlite/recovery_validation.py",
        "adapters/sqlite/ref_salvage.py",
        # A1a Access registry is explicit opt-in, not a default/P1 activation.
        "domain/access_backup.py",
        "domain/ports/access_backup.py",
        "adapters/sqlite/access_backup.py",
        "application/access_maintenance.py",
        "cli/access_maintenance.py",
        "domain/access_registry.py",
        "domain/access_connections.py",
        "domain/native_acquisition.py",
        "application/access_acquisition.py",
        "cli/access_acquisition.py",
        "adapters/git/access_native.py",
        "domain/access_workflow.py",
        "domain/ports/access_workflow.py",
        "application/access_workflow.py",
        "adapters/filesystem/access_executor.py",
        "cli/access_workflow.py",
        "domain/ports/access_connections.py",
        "adapters/sqlite/access_connections.py",
        "domain/ports/access_registry.py",
        "adapters/sqlite/access_schema.py",
        "adapters/sqlite/access_registry.py",
    )
)
ISOLATED_TARGET_MODULES = ISOLATED_P1_MODULES | ISOLATED_NEXT_STAGE_MODULES


def isolated_runtime_imports(source: str, package: str) -> set[str]:
    """Find direct imports of isolated targets, including relative/from forms."""
    targets = {
        source_relative(ROOT / path).as_posix().removesuffix(".py").replace("/", ".")
        for path in ISOLATED_TARGET_MODULES
    }
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
    return imported & targets


def is_baseline_source(path: Path) -> bool:
    module = source_relative(path).as_posix()
    return module not in {
        source_relative(ROOT / relative).as_posix()
        for relative in ISOLATED_TARGET_MODULES
    }


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
    modules, isolated_modules, references, revisions = [], [], [], []
    paths = source_files() + sorted(resources.glob("*.sql"))
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
        entry = {
            "path": relative,
            "owner": source_owner(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "functions": [
                {"name": name, "line": start, "end_line": end}
                for start, end, name in sorted(definitions)
            ],
        }
        if not is_baseline_source(path):
            # Retain syntax validation and complete ownership/hash coverage;
            # opt-in functions do not duplicate the normal-runtime lexical index.
            entry.pop("functions")
            isolated_modules.append(entry)
            continue
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
        "method": "All distribution source roots: syntax-checked owner/hash inventory separates explicit opt-in modules from the normal-runtime AST/function lexical index; all packaged resource owners/hashes are retained. Literal baseline table/view vocabulary is not proof of runtime reachability. Manual semantic interpretation is in callsite-dependencies.md and legacy-operations.md.",
        "source_roots": {
            source.relative_to(ROOT).as_posix(): owner
            for source, owner in SOURCE_OWNERS.items()
        },
        "isolated_modules": isolated_modules,
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
