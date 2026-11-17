"""Check/render the canonical separated-store class mapping without opening catalogs.

DDL owns columns, ordered keys and physical foreign keys. The JSON owns logical
class assignments, observed Python type bindings and explicitly bounded gaps.
Dedicated row types are generated from DDL; inputs/projections remain separate.
This is structural correspondence checking, not admission/semantic proof.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter
from pathlib import Path

# Support both `python scripts/persistence_model.py` and import in focused tests.
ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.schema_catalog import build_catalog, validate_catalog  # noqa: E402

MODEL = ROOT / "docs/architecture/persistence-model.json"
TARGET_FORMATS = {
    "core": "p1.core",
    "context": "p1.context",
    "access": "access",
    "operational": "p1.operational",
    "search": "p1.search",
    "filesystem": "filesystem",
    "worktrees": "worktrees",
}
ROW_KINDS = {"entity", "association", "infrastructure", "projection"}
TYPE_KINDS = {"abstract", "value", "dto", "query"}
IDENTIFIER = re.compile(r"[A-Z][A-Za-z0-9]*\.[A-Z][A-Za-z0-9]*\Z")


def row_type_binding(record: dict) -> dict[str, str]:
    """The declared per-domain module and logical short name own the row type."""
    domain = record["domain"]
    prefix = f"packages/{domain}/src/repo_catalog/"
    path = (
        prefix + f"{domain}/rows.py"
        if domain in {"filesystem", "worktrees"}
        else prefix + f"adapters/sqlite/{domain}_rows.py"
    )
    return {"path": path, "symbol": record["id"].split(".")[1] + "Row"}


def load_model(path: Path = MODEL) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_model(
    model: dict,
    catalog: dict,
    root: Path = ROOT,
    *,
    inspect_row_types: bool = True,
) -> list[str]:
    """Validate finite design/DDL coverage and symbol presence, never live rows."""
    errors = validate_catalog(catalog)
    if not isinstance(model, dict) or model.get("schema_version") != 2:
        return [*errors, "unsupported persistence model/version"]
    domains = model.get("domains")
    if not isinstance(domains, dict) or set(domains) != set(TARGET_FORMATS):
        return [*errors, "domain coverage must match the seven separated roles"]
    for domain, store in TARGET_FORMATS.items():
        record = domains[domain]
        if not isinstance(record, dict) or record.get("store") != store:
            errors.append(domain + ": wrong target format (normal is not a target)")
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("responsibility"), str)
            or not record["responsibility"].strip()
        ):
            errors.append(domain + ": responsibility description is required")
        if catalog["stores"].get(store, {}).get("authority_domains") != [domain]:
            errors.append(domain + ": DDL responsibility ownership differs")

    classes, types = model.get("classes"), model.get("nonpersistent_types")
    if not isinstance(classes, list) or not isinstance(types, list):
        return [*errors, "classes and nonpersistent_types must be lists"]
    identities, rows, by_table = {}, Counter(), {}
    parsed_sources: dict[str, set[str]] = {}

    def binding(record, persistent, field="python"):
        observed = record.get(field)
        if observed is None:
            if field == "row_type":
                errors.append(record.get("id", "?") + ": row_type binding is required")
            return
        ident = record.get("id", "?")
        if not isinstance(observed, dict):
            errors.append(ident + ": invalid Python binding")
            return
        expected_fields = (
            {"path", "symbol", "role"}
            if persistent and field == "python"
            else {"path", "symbol"}
        )
        if set(observed) != expected_fields:
            errors.append(ident + ": unexpected/missing Python binding fields")
        if (
            persistent
            and field == "python"
            and (
                not isinstance(observed.get("role"), str)
                or observed["role"] not in {"row-input", "projection"}
            )
        ):
            errors.append(ident + ": Python role must be row-input or projection")
        source, symbol = observed.get("path"), observed.get("symbol")
        if not isinstance(source, str) or not isinstance(symbol, str):
            errors.append(ident + ": Python binding needs path and symbol")
            return
        path = Path(source)
        if (
            path.is_absolute()
            or ".." in path.parts
            or path.as_posix() != source
            or path.suffix != ".py"
            or not (root / path).resolve().is_relative_to(root.resolve())
        ):
            errors.append(ident + ": Python source must be a repository-relative file")
            return
        if source not in catalog["source_ownership"]:
            errors.append(
                ident + ": Python source is not owned by a product distribution"
            )
            return
        try:
            if source not in parsed_sources:
                tree = ast.parse((root / path).read_text(encoding="utf-8"))
                parsed_sources[source] = {
                    node.name for node in tree.body if isinstance(node, ast.ClassDef)
                }
            if symbol not in parsed_sources[source]:
                errors.append(ident + ": Python class not found: " + symbol)
        except (OSError, SyntaxError, UnicodeError) as exc:
            errors.append(ident + ": cannot inspect Python source: " + str(exc))

    for persistent, records in ((True, classes), (False, types)):
        for record in records:
            if not isinstance(record, dict):
                errors.append("class/type record must be an object")
                continue
            ident = record.get("id")
            if not isinstance(ident, str) or not IDENTIFIER.fullmatch(ident):
                errors.append("invalid qualified class identity: " + str(ident))
                continue
            if ident in identities:
                errors.append(ident + ": duplicate class identity")
            identities[ident] = record
            domain = record.get("domain")
            if (
                not isinstance(domain, str)
                or domain not in domains
                or ident.split(".")[0] != domain.title()
            ):
                errors.append(ident + ": class responsibility ownership differs")
                continue
            allowed = {
                "id",
                "domain",
                "kind",
                "python",
                "note",
                "table" if persistent else "sources",
            }
            if persistent:
                allowed.add("row_type")
            if set(record) != allowed:
                errors.append(
                    ident
                    + ": unexpected/missing fields (DDL columns and keys must be derived)"
                )
            if not isinstance(record.get("note"), str) or not record["note"].strip():
                errors.append(ident + ": explanatory note is required")
            binding(record, persistent)
            if persistent:
                binding_fields = record.get("row_type")
                if binding_fields != row_type_binding(record):
                    errors.append(
                        ident + ": row_type must match its dedicated domain module/name"
                    )
                if inspect_row_types:
                    binding(record, True, "row_type")
                table = record.get("table")
                if (
                    not isinstance(record.get("kind"), str)
                    or record["kind"] not in ROW_KINDS
                ):
                    errors.append(ident + ": invalid persistent class kind")
                if not isinstance(table, str) or domain not in TARGET_FORMATS:
                    errors.append(ident + ": row class requires one target table")
                    continue
                pair = TARGET_FORMATS[domain], table
                rows[pair] += 1
                by_table[pair] = ident
            else:
                if (
                    not isinstance(record.get("kind"), str)
                    or record["kind"] not in TYPE_KINDS
                    or "table" in record
                ):
                    errors.append(ident + ": nonpersistent type cannot own a table")
                if not isinstance(record.get("sources"), list):
                    errors.append(ident + ": nonpersistent sources must be a list")

    expected = {
        (store, table)
        for store in TARGET_FORMATS.values()
        for table in catalog["stores"].get(store, {}).get("tables", {})
    }
    for pair in sorted(expected | set(rows)):
        if pair not in expected:
            errors.append("unknown target table: " + ".".join(pair))
        elif rows[pair] != 1:
            errors.append("table needs exactly one class: " + ".".join(pair))
    for record in types:
        if isinstance(record, dict) and isinstance(record.get("sources"), list):
            for ident in record["sources"]:
                if not isinstance(ident, str) or ident not in identities:
                    errors.append(
                        str(record.get("id")) + ": unknown source class " + str(ident)
                    )
                elif ident not in by_table.values():
                    errors.append(
                        str(record.get("id")) + ": source must be a persistent class"
                    )

    declared = model.get("external_references")
    if not isinstance(declared, list):
        errors.append("external reference bindings must be a list")
        declared = []
    reference_ids = [
        r["id"]
        for r in declared
        if isinstance(r, dict) and isinstance(r.get("id"), str)
    ]
    registry = {r["id"]: r for r in catalog["optional_references"]}
    if len(reference_ids) != len(declared) or Counter(reference_ids) != Counter(
        registry.keys()
    ):
        errors.append("registered external reference coverage differs")
    for record in declared:
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("id"), str)
            or record["id"] not in registry
        ):
            continue
        ref = registry[record["id"]]
        if set(record) != {"id", "source", "target"}:
            errors.append(ref["id"] + ": unexpected/missing external binding fields")
        source = by_table.get((ref["source_store"], ref["source_table"]))
        target_domain = ref.get("target_domain")
        target_id = record.get("target")
        target = identities.get(target_id, {}) if isinstance(target_id, str) else {}
        if record.get("source") != source:
            errors.append(ref["id"] + ": external source class differs")
        if "target_store" in ref:
            if record.get("target") != by_table.get(
                (ref["target_store"], ref["target_table"])
            ):
                errors.append(ref["id"] + ": external target class differs")
        elif (
            target.get("domain") != target_domain or target_id not in by_table.values()
        ):
            errors.append(
                ref["id"] + ": external claim target must be in its declared domain"
            )

    gaps, phases = model.get("gaps"), model.get("roadmap")
    for name, records in (("gaps", gaps), ("roadmap", phases)):
        if not isinstance(records, list) or not records:
            errors.append(name + ": nonempty records are required")
            continue
        if any(
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not isinstance(item.get("detail"), str)
            for item in records
        ):
            errors.append(name + ": records require id and detail strings")
    return errors


def physical_references(catalog: dict, store: str, table: str) -> list[dict]:
    """Resolve implicit SQLite REFERENCES target keys in their actual order."""
    tables = catalog["stores"][store]["tables"]
    return [
        {
            "source_columns": fk["from_columns"],
            "target_table": fk["target_table"],
            "target_columns": (
                tables[fk["target_table"]]["primary_key"]
                if all(column is None for column in fk["to_columns"])
                else fk["to_columns"]
            ),
        }
        for fk in tables[table]["foreign_keys"]
    ]


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _python(record: dict) -> str:
    binding = record.get("python")
    if binding is None:
        return "no Python input/projection recorded"
    return f"{binding.get('role', record['kind'])}: `{binding['symbol']}` ({binding['path']})"


def render_markdown(model: dict, catalog: dict) -> str:
    """Render only from a validated mapping and the actual source-bound DDL IR."""
    lines = [
        "# Separated persistence class mapping",
        "",
        (
            "Ordinary CLI composition uses the separated stores. "
            if model.get("scope", {}).get("normal_runtime_changed")
            else "Accepted target correspondence; normal startup remains unchanged. "
        )
        + "DDL-derived fields/keys are implementation facts. Dedicated row types "
        "are generated separately from observed Python inputs/projections; "
        "AST presence does not prove row serialization or admission correctness.",
        "",
        "Seven responsibility roles do not require seven initialized/open DBs. "
        "Operational retains required durable work/recovery state; row kind "
        "does not determine durability or authority. No retained DB is read.",
        "",
        "Coverage: registered separated product-table definitions; SQLite internals "
        "and runtime-created virtual/shadow tables are outside this mapping.",
    ]
    by_table = {
        (TARGET_FORMATS[row["domain"]], row["table"]): row["id"]
        for row in model["classes"]
    }
    for domain, config in model["domains"].items():
        store = config["store"]
        schema = catalog["stores"][store]
        lines.extend(
            [
                "",
                f"## {domain.title()} — `{store}`",
                "",
                config["responsibility"],
                "",
                f"Composition: `{schema['composition_entrypoint']}` "
                f"({schema['composition_distribution']}). This is not table-source ownership.",
                "",
                f"DDL SHA-256: `{schema['ddl_sha256']}`; format: `{schema['format_id']}`; "
                f"schema version: `{schema['schema_version']}`.",
                "",
                "DDL contributions: "
                + "; ".join(
                    f"`{item['path']}` ({item['distribution']})"
                    for item in schema["definition_sources"]
                ),
                "",
                "| Persistent class | Kind | Table | Ordered primary key | Generated row type | Python input/projection |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in model["classes"]:
            if row["domain"] != domain:
                continue
            table = schema["tables"][row["table"]]
            key = ", ".join(table["primary_key"]) or "(none)"
            lines.append(
                "| "
                + " | ".join(
                    map(
                        _cell,
                        [
                            row["id"],
                            row["kind"],
                            f"`{row['table']}`",
                            f"`({key})`",
                            f"`{row['row_type']['symbol']}` ({row['row_type']['path']})",
                            _python(row),
                        ],
                    )
                )
                + " |"
            )
        lines.extend(["", "### Row details and same-file physical FKs", ""])
        for row in model["classes"]:
            if row["domain"] != domain:
                continue
            table = schema["tables"][row["table"]]
            columns = ", ".join(
                f"{col['name']} {col['type']}" for col in table["columns"]
            )
            lines.extend([f"- **{row['id']}**: {row['note']} Fields: `{columns}`."])
            for ref in physical_references(catalog, store, row["table"]):
                target = by_table[(store, ref["target_table"])]
                lines.append(
                    f"  - physical FK: `({', '.join(ref['source_columns'])})` → "
                    f"{target} `({', '.join(ref['target_columns'])})`."
                )
    lines.extend(
        [
            "",
            "## Registered optional external references",
            "",
            "This section covers the schema catalogue's explicit optional-reference registry, "
            "not all domain associations or operation preconditions. Missing optional "
            "instance targets remain unresolved. These are not cross-DB physical FKs.",
            "",
        ]
    )
    registry = {r["id"]: r for r in catalog["optional_references"]}
    for binding in model["external_references"]:
        ref = registry[binding["id"]]
        columns = ", ".join(ref["source_columns"])
        target = (
            ", ".join(ref.get("target_columns", []))
            or "domain claim; no target-row verification"
        )
        lines.append(
            f"- {ref['kind']}: {binding['source']} `({columns})` → "
            f"{binding['target']} ({target}); missing target: {ref['missing_target']}."
        )
    lines.extend(
        [
            "",
            "## Nonpersistent types and query derivations",
            "",
            "An empty source list denotes a value/abstraction, not a missing table. "
            "Source lists describe derivation/use, not FKs or one-to-one row encodings.",
            "",
        ]
    )
    for record in model["nonpersistent_types"]:
        observed = (
            _python(record) if record.get("python") else "no Python class claimed"
        )
        lines.append(
            f"- **{record['id']}** ({record['kind']}): {record['note']} "
            f"Sources/use: {', '.join(record['sources']) or 'value/abstraction'}. {observed}."
        )
    for field, heading in (
        ("gaps", "Gaps and redesign candidates"),
        ("roadmap", "Future implementation and retirement sequence"),
    ):
        lines.extend(["", "## " + heading, ""])
        for record in model[field]:
            lines.append(f"- **{record['id']}**: {record['detail']}")
    lines.extend(
        [
            "",
            "Structural coverage and symbol checks do not prove SQL CHECK/trigger semantics, "
            "admission/recovery correctness, input/projection serialization, "
            "instance validity or formal semantic consistency.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--check", action="store_true", help="check structural correspondence (default)"
    )
    action.add_argument(
        "--format", choices=["markdown"], help="render checked correspondence to stdout"
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=MODEL,
        help="read an alternate mapping (no files are written)",
    )
    args = parser.parse_args(argv)
    try:
        model, catalog = load_model(args.model), build_catalog()
        errors = validate_model(model, catalog)
        if not errors:
            from scripts.generate_persistence_rows import check_generated

            errors = check_generated(model, catalog)
    except (OSError, ValueError, TypeError) as exc:
        print("Persistence mapping failed: " + str(exc), file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print("Persistence mapping: " + error, file=sys.stderr)
        return 1
    if args.format == "markdown":
        print(render_markdown(model, catalog), end="")
    else:
        counts = Counter(row["domain"] for row in model["classes"])
        print(
            f"Persistence mapping OK: {len(counts)} roles, {sum(counts.values())} DDL tables/classes; "
            "structural coverage and Python symbol presence only."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
