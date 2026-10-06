"""Lookup stable source-owned typed ID mappings committed by the importer."""

from .common import ConversionError


def lookup(db, record_id, table, relation="identity"):
    rows = db.execute(
        "SELECT target_key FROM id_mappings WHERE record_id=? AND target_table=? AND relation=?",
        (record_id, table, relation),
    ).fetchall()
    if len(rows) > 1:
        raise ConversionError("ID_MAPPING_CONFLICT")
    return rows[0][0] if rows else None
