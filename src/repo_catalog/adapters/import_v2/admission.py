"""Read-only operational v2 admission; derived bytes are never original content.

Only the application's exact FTS definition and a locally demonstrated SQLite
layout are recognized. The capability DB runs fixed converter DDL, never SQL
obtained from the source. All source queries remain read-only.
"""

import json
import re
import sqlite3
from itertools import zip_longest

from .common import DESIGN, ConversionError, canonical, digest
from .types import identifier

ADMISSION_VERSION = "operational-v2/1"
FTS_OPTIONS = "fts5(body, tokenize='trigram case_sensitive 1',content='',detail=full)"
FTS_NAME = re.compile(r"catalog_fts_([1-9][0-9]*)\Z")
KINDS = {"code", "pr", "commits"}
STATES = {"building", "ready", "retired", "removed", "unavailable"}


class SourceAdmissionError(ConversionError):
    def __init__(self, report):
        self.report = report
        super().__init__("SOURCE_SCHEMA_MISMATCH")


def _table(db, name):
    indexes = []
    for index in db.execute(f"PRAGMA index_list({identifier(name)})"):
        sql = db.execute(
            "SELECT sql FROM sqlite_schema WHERE type='index' AND name=?",
            (index["name"],),
        ).fetchone()
        indexes.append(
            {
                **dict(index),
                "columns": [
                    dict(c)
                    for c in db.execute(
                        f"PRAGMA index_xinfo({identifier(index['name'])})"
                    )
                ],
                "sql": sql[0] if sql else None,
            }
        )
    return {
        "columns": [
            dict(c) for c in db.execute(f"PRAGMA table_xinfo({identifier(name)})")
        ],
        "foreign_keys": [
            dict(f) for f in db.execute(f"PRAGMA foreign_key_list({identifier(name)})")
        ],
        "indexes": indexes,
    }


def inventory(db):
    """Include internal/automatic objects and physical root pages.

    Unknown virtual modules are not instantiated to discover their columns.
    Their exact stored definition is still in the inventory and blocks admission.
    """
    objects = []
    for row in db.execute(
        "SELECT type,name,tbl_name,rootpage,sql FROM sqlite_schema ORDER BY type,name"
    ):
        item = dict(row)
        if item["type"] == "table":
            sql = item["sql"] or ""
            virtual = bool(re.match(r"\s*CREATE\s+VIRTUAL\s+TABLE\b", sql, re.I))
            fixed_fts = (
                sql == f"CREATE VIRTUAL TABLE {item['name']} USING {FTS_OPTIONS}"
            )
            if virtual and not (FTS_NAME.fullmatch(item["name"]) and fixed_fts):
                item["columns"] = []
                item["introspection"] = "unsupported_virtual_module_or_definition"
            else:
                try:
                    item.update(_table(db, item["name"]))
                except sqlite3.Error:
                    item["columns"] = []
                    item["introspection"] = "unreadable_table_metadata"
        objects.append(item)
    return objects


def _shape(item):
    return {k: v for k, v in item.items() if k != "rootpage"}


def _rename(value, before, after):
    if isinstance(value, str):
        return value.replace(before, after)
    if isinstance(value, list):
        return [_rename(v, before, after) for v in value]
    if isinstance(value, dict):
        return {k: _rename(v, before, after) for k, v in value.items()}
    return value


def capabilities():
    """Demonstrate supported FTS behavior and ANALYZE layouts in memory.

    Evidence intentionally excludes the runtime version string. Identical source
    layouts remain identifiable on the selected working binding. No version
    threshold replaces the demonstrated source layout and audit capabilities.
    """
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    fts = []
    supported = True
    try:
        db.enable_load_extension(False)
        try:
            db.execute(f"CREATE VIRTUAL TABLE catalog_fts_1 USING {FTS_OPTIONS}")
            db.execute("INSERT INTO catalog_fts_1(rowid,body) VALUES(7,'Abc def')")
            db.commit()
            # Exercise exactly the read-only interface used against the source.
            db.execute("PRAGMA query_only=ON")
            db.execute("PRAGMA trusted_schema=OFF")
            supported = supported and [
                tuple(r) for r in db.execute("SELECT rowid,body FROM catalog_fts_1")
            ] == [(7, None)]
            supported = supported and [
                r[0]
                for r in db.execute(
                    "SELECT rowid FROM catalog_fts_1 WHERE catalog_fts_1 MATCH 'Abc'"
                )
            ] == [7]
            supported = (
                supported
                and not db.execute(
                    "SELECT rowid FROM catalog_fts_1 WHERE catalog_fts_1 MATCH 'abc'"
                ).fetchone()
            )
            fts = [_shape(i) for i in inventory(db)] if supported else []
        except sqlite3.Error:
            supported = False
        db.execute("PRAGMA query_only=OFF")
        db.execute("CREATE TABLE capability_sample(id INTEGER PRIMARY KEY, value TEXT)")
        db.execute("CREATE INDEX capability_value ON capability_sample(value)")
        db.executemany(
            "INSERT INTO capability_sample VALUES(?,?)",
            [(n, str(n % 4)) for n in range(16)],
        )
        db.execute("ANALYZE")
        stats = {
            i["name"]: _shape(i)
            for i in inventory(db)
            if i["name"] in {"sqlite_stat1", "sqlite_stat4"}
        }
        evidence = {
            "minimum_sqlite": "3.46.1",
            "fts5_contentless_trigram_case_sensitive": bool(supported),
            "fts_layout_sha256": digest(canonical(fts).encode()) if fts else None,
            "statistics_layouts": {
                name: digest(canonical(shape).encode()) for name, shape in stats.items()
            },
        }
        return evidence, fts, stats
    finally:
        db.close()


def _generations(db, objects, expected_fts, diagnostics):
    known, generations = {}, []
    # Read names as bytes: malformed text is still archiveable core evidence.
    rows = db.execute(
        "SELECT id,CAST(kind AS BLOB),CAST(state AS BLOB),CAST(table_name AS BLOB),"
        "target_max_id,CAST(created_at AS BLOB) FROM index_generations ORDER BY id"
    )
    for row in rows:
        ident, raw_kind, raw_state, raw_name, maximum, raw_created = tuple(row)
        try:
            name = raw_name.decode("utf-8")
        except (AttributeError, UnicodeError):
            # This registry row grants no authority to a derived table.
            continue
        if not FTS_NAME.fullmatch(name):
            continue
        matching = [
            i for i in objects if i["name"] == name or i["name"].startswith(name + "_")
        ]
        try:
            kind, state = raw_kind.decode("utf-8"), raw_state.decode("utf-8")
            valid = (
                type(ident) is int
                and 0 < ident <= 9223372036854775807
                and name == f"catalog_fts_{ident}"
                and kind in KINDS
                and state in STATES
                and type(maximum) is int
                and maximum >= 0
                and bool(raw_created and raw_created.decode("utf-8"))
            )
        except (AttributeError, UnicodeError):
            valid = False
        if not valid:
            diagnostics.append({"code": "FTS_REGISTRY_INVALID", "object": name})
            continue
        if not matching:
            if state not in {"removed", "unavailable"}:
                diagnostics.append({"code": "FTS_GENERATION_MISSING", "object": name})
            elif (
                state == "removed"
                and db.execute(
                    "SELECT 1 FROM index_membership WHERE generation_id=? LIMIT 1",
                    (ident,),
                ).fetchone()
            ):
                diagnostics.append(
                    {"code": "FTS_REMOVED_HAS_MEMBERSHIP", "object": name}
                )
            else:
                generations.append(
                    {
                        "id": ident,
                        "kind": kind,
                        "state": state,
                        "table": name,
                        "coverage": "excluded_missing",
                        "rebuild_from": "search_documents",
                    }
                )
            continue
        expected = [_rename(i, "catalog_fts_1", name) for i in expected_fts]
        if (
            state == "removed"
            or not expected
            or sorted(
                [_shape(i) for i in matching], key=lambda i: (i["type"], i["name"])
            )
            != sorted(expected, key=lambda i: (i["type"], i["name"]))
        ):
            diagnostics.append({"code": "FTS_LAYOUT_UNSUPPORTED", "object": name})
            continue
        # Provenance is a relation, not a prefix: row IDs, membership version,
        # document kind and the fixed generation bound must agree exactly.
        invalid = db.execute(
            "SELECT 1 FROM index_membership m LEFT JOIN search_documents d "
            "ON d.id=m.document_id WHERE m.generation_id=? AND "
            "(d.id IS NULL OR d.id<=0 OR d.kind!=? OR d.id>? OR m.input_version!='utf8-literal-v1') LIMIT 1",
            (ident, kind, maximum),
        ).fetchone()
        try:
            indexed = db.execute(f"SELECT rowid FROM {identifier(name)} ORDER BY rowid")
            membership = db.execute(
                "SELECT document_id FROM index_membership WHERE generation_id=? ORDER BY document_id",
                (ident,),
            )
            members, matches = 0, True
            for actual, claimed in zip_longest(indexed, membership):
                if actual is None or claimed is None or actual[0] != claimed[0]:
                    matches = False
                    break
                members += 1
            config = [
                tuple(r)
                for r in db.execute(
                    f"SELECT k,v FROM {identifier(name + '_config')} ORDER BY k LIMIT 2"
                )
            ]
        except sqlite3.Error:
            diagnostics.append({"code": "FTS_READ_UNSUPPORTED", "object": name})
            continue
        if invalid or not matches or config != [("version", 4)]:
            diagnostics.append({"code": "FTS_PROVENANCE_MISMATCH", "object": name})
            continue
        expected_count, latest = db.execute(
            "SELECT sum(id<=?),coalesce(max(id),0) FROM search_documents WHERE kind=?",
            (maximum, kind),
        ).fetchone()
        coverage = "incomplete" if members != (expected_count or 0) else "complete"
        stale = latest > maximum
        generations.append(
            {
                "id": ident,
                "kind": kind,
                "state": state,
                "table": name,
                "coverage": coverage,
                "stale": stale,
                "members": members,
                "target_max_id": maximum,
                "rebuild_from": "search_documents",
            }
        )
        for item in matching:
            known[item["name"]] = ("application_fts", name)
    return known, generations


def _statistics_valid(db, name, objects):
    tables = {i["name"] for i in objects if i["type"] == "table"}
    indexes = {i["name"]: i["tbl_name"] for i in objects if i["type"] == "index"}
    # ANALYZE names a WITHOUT ROWID table's primary B-tree after the table;
    # SQLite does not create a separate sqlite_schema index for that B-tree.
    indexes.update(
        {
            i["name"]: i["name"]
            for i in objects
            if i["type"] == "table"
            and (i["sql"] or "").endswith("WITHOUT ROWID")
            and any(c["pk"] for c in i.get("columns", []))
        }
    )
    try:
        rows = db.execute(f"SELECT * FROM {identifier(name)}")
        for row in rows:
            table, index = row[0], row[1]
            if table not in tables or (
                index is not None and indexes.get(index) != table
            ):
                return False
            if name == "sqlite_stat1":
                # SQLite also emits the documented optional trailing flags.
                if not isinstance(row[2], str) or not re.fullmatch(
                    r"[0-9]+(?: [0-9]+)*(?: (?:unordered|noskipscan|sz=[0-9]+))*",
                    row[2],
                ):
                    return False
            elif (
                index is None
                or any(
                    not isinstance(row[n], str)
                    or not re.fullmatch(r"[0-9]+(?: [0-9]+)*", row[n])
                    for n in (2, 3, 4)
                )
                or not isinstance(row[5], bytes)
            ):
                return False
        return True
    except (sqlite3.Error, UnicodeError):
        return False


def classify(db):
    """Return a complete reviewable inventory even when admission is blocked."""
    spec = json.loads((DESIGN / "conversion-contract.json").read_bytes())
    core_names = {c["table"] for c in spec["source_columns"]}
    objects = inventory(db)
    core_tables = [
        {
            "name": i["name"],
            "sql": i["sql"],
            **{k: i.get(k, []) for k in ("columns", "foreign_keys", "indexes")},
        }
        for i in objects
        if i["type"] == "table" and i["name"] in core_names
    ]
    core_triggers = [
        {k: i[k] for k in ("name", "tbl_name", "sql")}
        for i in objects
        if i["type"] == "trigger" and i["tbl_name"] in core_names
    ]
    core_sha = digest(
        json.dumps(
            {"tables": core_tables, "triggers": core_triggers}, sort_keys=True
        ).encode()
    )
    core_valid = core_sha == spec["source_schema_sha256"]
    diagnostics = [] if core_valid else [{"code": "STRICT_CORE_SCHEMA_MISMATCH"}]
    evidence, fts, stats = capabilities()
    fts_required = any(
        i["type"] == "table" and FTS_NAME.fullmatch(i["name"]) for i in objects
    )
    evidence = {
        **evidence,
        "fts_required": fts_required,
        "fts5_contentless_trigram_case_sensitive": (
            evidence["fts5_contentless_trigram_case_sensitive"]
            if fts_required
            else None
        ),
        "fts_layout_sha256": evidence["fts_layout_sha256"] if fts_required else None,
        "statistics_layouts": {
            name: value
            for name, value in evidence["statistics_layouts"].items()
            if any(i["name"] == name for i in objects)
        },
    }
    known, generations = (
        _generations(db, objects, fts, diagnostics) if core_valid else ({}, [])
    )
    dispositions = []
    for item in objects:
        name = item["name"]
        if item["tbl_name"] in core_names and core_valid:
            classification, preservation, rebuild = (
                "strict_v2_core",
                "exact_typed_archive"
                if item["type"] == "table"
                else "sealed_bytes_rebuild_excluded",
                None if item["type"] == "table" else "reviewed target DDL",
            )
        elif name in known:
            classification, preservation, rebuild = (
                "application_fts",
                "sealed_bytes_rebuild_excluded",
                "search_documents",
            )
        elif (
            name in stats
            and _shape(item) == stats[name]
            and _statistics_valid(db, name, objects)
        ):
            classification, preservation, rebuild = (
                "sqlite_statistics",
                "sealed_bytes_rebuild_excluded",
                "ANALYZE over rebuilt target indexes",
            )
        else:
            classification, preservation, rebuild = (
                "unsupported",
                "blocking_unsupported",
                None,
            )
            diagnostics.append(
                {
                    "code": "UNSUPPORTED_SCHEMA_OBJECT",
                    "object": name,
                    "type": item["type"],
                }
            )
        dispositions.append(
            {
                "object": name,
                "type": item["type"],
                "classification": classification,
                "preservation": preservation,
                "rebuild_from": rebuild,
                "columns": [
                    {"column": c["name"], "preservation": preservation}
                    for c in item.get("columns", [])
                ],
                "normalized_input": classification == "strict_v2_core"
                and item["type"] == "table",
            }
        )
    return {
        "admission_version": ADMISSION_VERSION,
        "accepted": not diagnostics,
        "core_schema_sha256": core_sha,
        "source_schema_sha256": digest(canonical(objects).encode()),
        "source_inventory": objects,
        "preservation_dispositions": dispositions,
        "derived_generations": generations,
        "capabilities": evidence,
        "diagnostics": diagnostics,
    }
