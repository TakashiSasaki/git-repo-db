"""Bounded P3B admission and an immutable parent view for integrated writes.

Only the exact current P3B identity or the reviewed P3B implementation is an
accepted predecessor. The new receipt binds a streaming proof of authenticated
parent evidence; it never embeds another copy of archived or normalized bytes.
"""

import hashlib
import re

from . import batch, identity, identity_phase, phase
from .common import PARSER_VERSION, ConversionError, canonical, digest, strict_json

PROTOCOL_VERSION = "p3-integrated/1"
REVIEWED_P3B_REVISION = "94b838d685a075ec4bc5117ef4a09448f9a71945"
REVIEWED_P3B_DDL = "fd39297f3b73abc190aa82a28164f2d496048d773cbbcc9039a54972046a5709"
REVIEWED_P3B_CONTRACT = (
    "8b020200aec824ed57788df73b9107bb9deed042ce87e0d198e0c5a7515ecb60"
)
REVIEWED_P3B_CONVERTER = (
    "bc539be4fd5f83810162fdd8161644a03a2f689c8d9869aa313803a48495fd75"
)
REVIEWED_P3B_INVARIANTS = (
    "6a348e9b3509733affdcb1ba43a7ba7c5776583d97b54688c9dded582655c21b"
)
SIGNATURE_KEYS = (
    "ddl_sha256",
    "contract_sha256",
    "contract_version",
    "parser_version",
    "converter_sha256",
    "target_schema_sha256",
    "invariant_contract_sha256",
)
PARENT_TABLES = (
    "database_identity",
    "conversion_sources",
    "conversion_runs",
    "conversion_batches",
    "legacy_records",
    "legacy_values",
    "id_mappings",
    "validation_results",
    *identity.TABLES,
)


def _json(value, code):
    try:
        result = strict_json(value)
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (ValueError, TypeError):
        raise ConversionError(code) from None


def _tables(domain_tables):
    result = frozenset(domain_tables)
    if not result or any(
        not isinstance(name, str)
        or not re.fullmatch(r"[a-z][a-z0-9_]*", name)
        or name in {*PARENT_TABLES, "legacy_records", "legacy_values"}
        for name in result
    ):
        raise ConversionError("INVALID_INTEGRATED_OWNERSHIP")
    return result


def _owners(db):
    # Manifests may use overflow pages. Recovery admission first reads only the
    # small headers, then the two bounded phase receipts, never domain pages.
    headers = list(
        db.execute(
            "SELECT id,source_id,started_at,ended_at,parser_version,state "
            "FROM conversion_runs ORDER BY id"
        )
    )
    expected = (PARSER_VERSION, phase.PROTOCOL_VERSION, identity_phase.PROTOCOL_VERSION)
    owners = []
    for protocol in expected:
        found = [row for row in headers if row["parser_version"] == protocol]
        if len(found) != 1:
            raise ConversionError("PHASE_OWNERSHIP_MISMATCH")
        owners.append(found[0])
    own = [row for row in headers if row["parser_version"] == PROTOCOL_VERSION]
    if len(own) > 1 or len(headers) != 3 + len(own):
        raise ConversionError("PHASE_OWNERSHIP_MISMATCH")
    return (*owners, own[0] if own else None)


def _parent_signatures(run, signatures):
    original = _json(run["manifest"], "IDENTITY_PHASE_RECEIPT_MISMATCH").get(
        "signatures"
    )
    try:
        current = {key: signatures[key] for key in SIGNATURE_KEYS}
    except KeyError:
        raise ConversionError("UNSUPPORTED_P3B_PREDECESSOR") from None
    if original == current:
        return current
    reviewed = {
        **current,
        "ddl_sha256": REVIEWED_P3B_DDL,
        "contract_sha256": REVIEWED_P3B_CONTRACT,
        "converter_sha256": REVIEWED_P3B_CONVERTER,
        "invariant_contract_sha256": REVIEWED_P3B_INVARIANTS,
    }
    if (
        original != reviewed
        or current["ddl_sha256"] != REVIEWED_P3B_DDL
        or current["invariant_contract_sha256"] != REVIEWED_P3B_INVARIANTS
    ):
        raise ConversionError("UNSUPPORTED_P3B_PREDECESSOR")
    return reviewed


def _own_receipt(db, own, parent, signatures, prior_signatures, domain_tables):
    if own is None:
        return None
    run = db.execute(
        "SELECT * FROM conversion_runs WHERE id=?", (own["id"],)
    ).fetchone()
    saved = _json(run["manifest"], "INTEGRATED_PHASE_RECEIPT_MISMATCH")
    receipt = {key: value for key, value in saved.items() if key != "transition_id"}
    prior = receipt.get("parent", {})
    if (
        set(saved)
        != {
            "protocol",
            "committed_at",
            "source_id",
            "parent",
            "signatures",
            "batch_size",
            "encoding",
            "recipes",
            "write_ownership",
            "activation_permitted",
            "transition_id",
        }
        or receipt.get("protocol") != PROTOCOL_VERSION
        or receipt.get("signatures") != signatures
        or receipt.get("source_id") != parent["source_id"]
        or not isinstance(prior, dict)
        or prior.get("run_id") != parent["id"]
        or prior.get("parser_version") != identity_phase.PROTOCOL_VERSION
        or prior.get("signatures") != prior_signatures
        or prior.get("identity_complete") is not True
        or not isinstance(prior.get("diagnostics"), dict)
        or any(
            not isinstance(prior.get(key), str)
            or not re.fullmatch(r"[0-9a-f]{64}", prior[key])
            for key in ("receipt_sha256", "run_sha256", "proof_sha256")
        )
        or not isinstance(receipt.get("batch_size"), int)
        or isinstance(receipt["batch_size"], bool)
        or receipt["batch_size"] < 1
        or not isinstance(receipt.get("encoding"), str)
        or not isinstance(receipt.get("recipes"), list)
        or not receipt["recipes"]
        or any(not isinstance(value, str) for value in receipt["recipes"])
        or receipt.get("write_ownership")
        != {
            "tables": sorted(domain_tables),
            "operations": ["insert", "reuse", "update_listing_progress"],
        }
        or receipt.get("activation_permitted") is not False
        or not run["started_at"]
        or run["started_at"] != receipt.get("committed_at")
        or run["ended_at"] not in {None, run["started_at"]}
        or run["state"] not in {"building", "paused"}
        or run["source_id"] != parent["source_id"]
        or saved.get("transition_id") != run["id"]
        or run["id"] != "p3:" + digest(canonical(receipt).encode())
        or run["manifest"] != canonical(saved)
    ):
        raise ConversionError("INTEGRATED_PHASE_RECEIPT_MISMATCH")
    return saved


class ParentView:
    """Filter only explicit integrated ownership, leaving unknown rows visible.

    The map projection uses the immutable own-batch mapping IDs in SQLite, so
    the view does not accumulate a second complete mapping-ID set in memory.
    Before full proof reads those batch envelopes and IDs are validated; after
    recovery the identity verifier still sees every unclaimed mapping.
    """

    def __init__(self, db, own, domain_tables, *, validate_batches=True):
        self.db, self.own = db, own
        self.domain_tables = domain_tables
        if own and validate_batches:
            self._batches()

    def _batches(self):
        for committed in self.db.execute(
            "SELECT * FROM conversion_batches WHERE run_id=? ORDER BY id",
            (self.own["id"],),
        ):
            value = _json(
                committed["output_manifest"], "INTEGRATED_BATCH_PROOF_MISMATCH"
            )
            output = value.get("output")
            if (
                set(value) != {"protocol", "recipe", "index", "output", "output_sha256"}
                or value.get("protocol") != PROTOCOL_VERSION
                or not isinstance(output, dict)
                or not isinstance(output.get("mapping_ids"), list)
                or value.get("output_sha256") != batch.proof_digest(output)
                or output.get("observed_at") != committed["committed_at"]
            ):
                raise ConversionError("INTEGRATED_BATCH_PROOF_MISMATCH")
            ids = output["mapping_ids"]
            if any(
                not isinstance(ident, int) or isinstance(ident, bool) or ident < 1
                for ident in ids
            ) or len(ids) != len(set(ids)):
                raise ConversionError("INTEGRATED_MAPPING_OWNERSHIP_MISMATCH")
            for ident in ids:
                row = self.db.execute(
                    "SELECT target_table FROM id_mappings WHERE id=?", (ident,)
                ).fetchone()
                if row is None or row[0] not in self.domain_tables:
                    raise ConversionError("INTEGRATED_MAPPING_OWNERSHIP_MISMATCH")
        duplicate = self.db.execute(
            "SELECT value FROM conversion_batches AS b, "
            "json_each(b.output_manifest,'$.output.mapping_ids') "
            "WHERE b.run_id=? GROUP BY value HAVING count(*)!=1 LIMIT 1",
            (self.own["id"],),
        ).fetchone()
        if duplicate:
            raise ConversionError("INTEGRATED_MAPPING_OWNERSHIP_MISMATCH")

    def execute(self, sql, parameters=()):
        normalized = " ".join(sql.split())
        if self.own is None:
            return self.db.execute(sql, parameters)
        if normalized in {
            f'SELECT 1 FROM "{table}" LIMIT 1' for table in self.domain_tables
        }:
            return identity_phase._Rows([])
        # IDs are receipt hashes; quote defensively rather than altering the
        # caller's positional parameters when a filtered table is nested.
        owner = "'" + self.own["id"].replace("'", "''") + "'"
        if not normalized.upper().startswith("SELECT "):
            return self.db.execute(sql, parameters)
        filtered = {
            "conversion_runs": f"SELECT * FROM conversion_runs WHERE id!={owner}",
            "conversion_batches": f"SELECT * FROM conversion_batches WHERE run_id!={owner}",
            "validation_results": f"SELECT * FROM validation_results WHERE run_id!={owner}",
            "id_mappings": "SELECT * FROM id_mappings WHERE id NOT IN "
            "(SELECT value FROM conversion_batches AS b, "
            "json_each(b.output_manifest,'$.output.mapping_ids') "
            f"WHERE b.run_id={owner})",
        }
        # One pass avoids recursively rewriting the trusted subqueries.
        pattern = r"\bFROM\s+(conversion_runs|conversion_batches|validation_results|id_mappings)\b"
        sql = re.sub(
            pattern,
            lambda match: (
                f"FROM ({filtered[match.group(1).lower()]}) AS {match.group(1)}"
            ),
            sql,
            flags=re.IGNORECASE,
        )
        return self.db.execute(sql, parameters)


def _proof(view):
    """Frame and hash parent rows one at a time, without a payload manifest."""
    result = hashlib.sha256(b"integrated-parent-proof/1\0")
    for table in PARENT_TABLES:
        result.update(table.encode() + b"\0")
        # Stable primary-key order also covers composite identity keys.
        columns = list(view.execute(f'PRAGMA table_xinfo("{table}")'))
        primary = sorted(
            (column for column in columns if column["pk"]), key=lambda c: c["pk"]
        )
        order = ",".join('"' + column["name"] + '"' for column in primary)
        count = 0
        for row in view.execute(f"SELECT * FROM {table} ORDER BY {order}"):
            result.update(b"row\0" + len(row).to_bytes(8, "big"))
            for value in row:
                if isinstance(value, bytes):
                    tag, raw = b"blob\0", value
                elif isinstance(value, str):
                    tag, raw = b"text\0", value.encode("utf-8")
                else:
                    tag, raw = b"scalar\0", canonical(value).encode()
                result.update(tag + len(raw).to_bytes(8, "big"))
                result.update(raw)
            count += 1
        result.update(b"\0" + count.to_bytes(8, "big"))
    return result.hexdigest()


def check_parent(db, src, sealed, spec, signatures, domain_tables):
    """Authenticate complete immutable P3B, then return its compact binding.

    Return (P3B run, P3B receipt, source-derived identity status, parent proof).
    The caller owns the lock and invocation cache and verifies integrated output
    separately; this function does not write or authorize activation.
    """
    tables = _tables(domain_tables)
    _, _, parent, own = _owners(db)
    parent_run = db.execute(
        "SELECT * FROM conversion_runs WHERE id=?", (parent["id"],)
    ).fetchone()
    selected = _parent_signatures(parent_run, signatures)
    saved = _own_receipt(db, own, parent, signatures, selected, tables)
    view = ParentView(db, own, tables)
    run, receipt = identity_phase.check(view, src, sealed, spec, selected)
    status = identity.validate_output(view, src, run, receipt, require_complete=True)
    proof = {
        "run_id": run["id"],
        "parser_version": identity_phase.PROTOCOL_VERSION,
        "receipt_sha256": digest(run["manifest"].encode()),
        "run_sha256": batch.proof_digest(batch.encode([tuple(run)])),
        "proof_sha256": _proof(view),
        "signatures": selected,
        "reviewed_predecessor_revision": REVIEWED_P3B_REVISION
        if selected["converter_sha256"] == REVIEWED_P3B_CONVERTER
        else None,
        "diagnostics": {
            severity: status["diagnostics"].get(severity, 0)
            + receipt["parent"]["diagnostics"].get(severity, 0)
            for severity in ("blocking", "partial", "info")
        },
        "identity_complete": True,
    }
    if saved and saved["parent"] != proof:
        raise ConversionError("INTEGRATED_PARENT_PROOF_MISMATCH")
    return run, receipt, status, proof


def pending(db, sealed, spec, signatures, domain_tables):
    """Recognize bounded headers/receipts before recovering a target journal.

    Domain/batch/map pages deliberately remain unread until SQLite recovery.
    A successful return requires a complete check_parent on the recovered
    connection before any new write or a successful result.
    """
    tables = _tables(domain_tables)
    _, _, parent, own = _owners(db)
    run = db.execute(
        "SELECT * FROM conversion_runs WHERE id=?", (parent["id"],)
    ).fetchone()
    selected = _parent_signatures(run, signatures)
    saved = _own_receipt(db, own, parent, signatures, selected, tables)
    view = ParentView(db, own, tables, validate_batches=False)
    identity_phase._pending(view, sealed, spec, selected)
    if saved and (
        saved["parent"]["receipt_sha256"] != digest(run["manifest"].encode())
        or saved["parent"]["run_sha256"]
        != batch.proof_digest(batch.encode([tuple(run)]))
    ):
        raise ConversionError("INTEGRATED_PARENT_PROOF_MISMATCH")
    return {"parent_run_id": parent["id"], "signatures": selected}
