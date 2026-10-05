"""Prepare hashes before BEGIN; SQL-only writes under an OS writer lock."""

import json

from . import diagnostics, mapping
from .common import ConversionError, canonical, digest, now


def encode(rows):
    return [
        [{"blob": v.hex()} if isinstance(v, bytes) else v for v in row] for row in rows
    ]


def proof_digest(output):
    return digest(canonical(output).encode())


def row_proof(name, row):
    key = row[:2] if name == "legacy_values" else row[:1]
    return {"key": encode([key])[0], "sha256": proof_digest(encode([row]))}


def next_id(db, table):
    return db.execute(f"SELECT coalesce(max(id),0)+1 FROM {table}").fetchone()[0]


def prepare(db, source_id, run_id, records, *, map_repositories, encoding):
    output = {
        name: []
        for name in (
            "legacy_records",
            "legacy_values",
            "repositories",
            "id_mappings",
            "validation_results",
        )
    }
    record_id, mapping_id, diagnostic_id = (
        next_id(db, table)
        for table in ("legacy_records", "id_mappings", "validation_results")
    )
    for record in records:
        output["legacy_records"].append(
            [record_id, source_id, record.table, record.key, record.row_sha256]
        )
        output["legacy_values"].extend([[record_id, *value] for value in record.values])
        issues = diagnostics.classify(record, encoding)
        if map_repositories and record.table == "repositories":
            try:
                projected = mapping.repository_projection(record)
                key = mapping.allocate(db, record_id, "repositories", projected["id"])
                if (
                    db.execute(
                        "SELECT 1 FROM repositories WHERE id=?", (projected["id"],)
                    ).fetchone()
                    or db.execute(
                        "SELECT 1 FROM id_mappings WHERE target_table='repositories' AND target_key=?",
                        (key,),
                    ).fetchone()
                ):
                    raise ConversionError("ID_MAPPING_COLLISION")
                output["repositories"].append(
                    [
                        projected["id"],
                        projected["name"],
                        None,
                        None,
                        projected["metadata"],
                    ]
                )
                output["id_mappings"].append(
                    [
                        mapping_id,
                        record_id,
                        "repositories",
                        key,
                        "identity",
                        "P2 representative repository; preserve local ID",
                    ]
                )
                mapping_id += 1
            except ConversionError as exc:
                issues.append((exc.code, "blocking", "id"))
        for code, severity, column in issues:
            output["validation_results"].append(
                [
                    diagnostic_id,
                    run_id,
                    "I31",
                    code,
                    severity,
                    now(),
                    canonical({"record_id": record_id, "column": column}),
                ]
            )
            diagnostic_id += 1
        record_id += 1
    return output


def commit(db, run, table, index, input_sha256, output, fault):
    proof = {
        name: [row_proof(name, row) for row in rows] for name, rows in output.items()
    }
    manifest = canonical(
        {"index": index, "proof": proof, "output_sha256": proof_digest(proof)}
    )
    batch_id = next_id(db, "conversion_batches")
    committed_at = now()
    fault("before_insert")
    try:
        db.execute("BEGIN IMMEDIATE")
        for name in (
            "legacy_records",
            "legacy_values",
            "repositories",
            "validation_results",
        ):
            rows = output[name]
            if rows:
                db.executemany(
                    f"INSERT INTO {name} VALUES({','.join('?' for _ in rows[0])})", rows
                )
        fault("after_data")
        for row in output["id_mappings"]:
            # Validate both directions rather than trusting missing SQL UNIQUE.
            mapping.persist(db, row[1], row[2], row[3], row[5])
        fault("after_mapping")
        db.execute(
            "INSERT INTO conversion_batches VALUES(?,?,?,?,?,?)",
            (
                batch_id,
                run["id"],
                table,
                bytes.fromhex(input_sha256),
                committed_at,
                manifest,
            ),
        )
        db.execute(
            "UPDATE conversion_runs SET state='building',ended_at=NULL WHERE id=?",
            (run["id"],),
        )
        fault("before_commit")
        db.execute("COMMIT")
    except BaseException:
        if db.in_transaction:
            db.rollback()
        raise
    fault("after_commit")
    return batch_id


def validate_output(db, batch):
    manifest = json.loads(batch["output_manifest"])
    actual = {}
    for name, rows in manifest["proof"].items():
        if name not in {
            "legacy_records",
            "legacy_values",
            "repositories",
            "id_mappings",
            "validation_results",
        }:
            raise ConversionError("INVALID_BATCH_MANIFEST")
        result = []
        for row in rows:
            key = row["key"]
            first = (
                bytes.fromhex(key[0]["blob"]) if isinstance(key[0], dict) else key[0]
            )
            if name == "legacy_values":
                found = db.execute(
                    "SELECT * FROM legacy_values WHERE record_id=? AND column_name=?",
                    (first, key[1]),
                ).fetchone()
            else:
                found = db.execute(
                    f"SELECT * FROM {name} WHERE id=?", (first,)
                ).fetchone()
            if found is None:
                raise ConversionError("COMMITTED_OUTPUT_MISSING")
            result.append(row_proof(name, tuple(found)))
        actual[name] = result
    if actual != manifest["proof"] or proof_digest(actual) != manifest["output_sha256"]:
        raise ConversionError("COMMITTED_OUTPUT_MISMATCH")
    return manifest
