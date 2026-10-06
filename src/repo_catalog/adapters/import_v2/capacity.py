import shutil

from .common import ConversionError


def estimate(db, tables, source_bytes, metadata_bytes=0):
    # Exact payload size + row/column overhead; conservative multiplicative
    # allowance for B-trees, indices, rollback journal/temp and the sealed copy.
    rows, values, payload = 0, 0, 0
    for table in tables:
        columns = list(db.execute(f'PRAGMA table_xinfo("{table}")'))
        expressions = "+".join(
            f'coalesce(length(CAST("{c["name"]}" AS BLOB)),0)' for c in columns
        )
        count, byte_count = db.execute(
            f'SELECT count(*),coalesce(sum({expressions}),0) FROM "{table}"'
        ).fetchone()
        rows += count
        values += count * len(columns)
        payload += byte_count
    archive = payload + values * 256 + rows * 512
    required = source_bytes + 4 * archive + 4 * metadata_bytes + 64 * 1024 * 1024
    return {
        "source_bytes": source_bytes,
        "rows": rows,
        "values": values,
        "payload_bytes": payload,
        "archive_estimate": archive,
        "metadata_bytes": metadata_bytes,
        "required_free_bytes": required,
        "assumptions": "sealed copy + 4*(payload + 256/column + 512/row + seal/cache metadata) + 64MiB DDL/journal/temp reserve; cache objects not copied; normalized rows and journal reserve included",
    }


def preflight(path, estimate, *, free_bytes=None):
    free = shutil.disk_usage(path).free if free_bytes is None else free_bytes
    if free < estimate["required_free_bytes"]:
        raise ConversionError("INSUFFICIENT_SPACE")
    return {**estimate, "available_free_bytes": free}
