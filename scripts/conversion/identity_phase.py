"""Exact P3B ownership, bounded reviewed upgrade and frozen parent proofs.

The identity receipt is immutable. Domain progress belongs to attributed batches;
P2/P3A rows retain their original bytes, while an explicit parent view verifies
original representative rows independently from the enriched current projection.
"""

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from . import archive, batch, capacity, mapping, phase, source, target
from .common import DESIGN, PARSER_VERSION, ConversionError, canonical, digest, now

PROTOCOL_VERSION = "p3b-identity/1"
REVIEWED_P3A_REVISION = "e40430e3f38d3339d67017a04262445f9415a8ec"
REVIEWED_P3A_CONVERTER = (
    "f7aa4b38bf91e95173a7c832b016c7add6c46334a9854e652fdea3a39b458362"
)
REVIEWED_P3A_CONTRACT = (
    "9c07453cb9aa4a72e93f7990487933e0c8a55096890be986e9870ad48846bd58"
)
REVIEWED_INVARIANT_CONTRACT = (
    "6a348e9b3509733affdcb1ba43a7ba7c5776583d97b54688c9dded582655c21b"
)
REVIEWED_P3A_DDL = "fd39297f3b73abc190aa82a28164f2d496048d773cbbcc9039a54972046a5709"
IDENTITY_TABLES = (
    "service_instances",
    "sources",
    "repositories",
    "repository_bindings",
    "repository_endpoints",
    "repository_name_assertions",
    "source_repositories",
)


def no_fault(point, **context):
    pass


def resources(ddl=None, contract=None):
    from . import identity

    ddl_bytes, spec, signatures = target.resources(ddl, contract)
    identity.validate_contract(spec)
    invariant_bytes = (DESIGN / "invariant-contract.json").read_bytes()
    try:
        invariants = json.loads(invariant_bytes)["invariants"]
        ids = [row["id"] for row in invariants]
        expected = sqlite3.connect(":memory:")
        try:
            expected.executescript(ddl_bytes.decode())
            tables = {
                row[0]
                for row in expected.execute(
                    "SELECT name FROM sqlite_schema WHERE type='table'"
                )
            }
        finally:
            expected.close()
        if (
            len(ids) != 31
            or set(ids) != {f"I{number:02d}" for number in range(1, 32)}
            or any(
                not isinstance(row["ddl_tables"], list)
                or not row["ddl_tables"]
                or not set(row["ddl_tables"]) <= tables
                for row in invariants
            )
            or digest(invariant_bytes) != REVIEWED_INVARIANT_CONTRACT
        ):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise ConversionError("INVALID_INVARIANT_CONTRACT") from None
    return (
        ddl_bytes,
        spec,
        {
            **signatures,
            "invariant_contract_sha256": digest(invariant_bytes),
        },
    )


class _Rows:
    """Small cursor boundary for rows filtered by immutable parent ownership."""

    def __init__(self, rows):
        self.rows = iter(rows)

    def __iter__(self):
        return self.rows

    def fetchone(self):
        return next(self.rows, None)

    def fetchall(self):
        return list(self.rows)


class ParentView:
    """Read-only proof view, without copying the archived payload into memory.

    Only known parent-verifier queries are projected. Everything else reads the
    actual target. Parent map IDs come from immutable P2 committed proof keys,
    never an editable reason prefix. Original repository values come from the
    sealed source and must still match the historical P2 output proof.
    """

    def __init__(self, db, src, parent):
        self.db, self.parent = db, parent
        self.map_ids = set()
        for row in db.execute(
            "SELECT output_manifest FROM conversion_batches WHERE run_id=?",
            (parent["id"],),
        ):
            manifest = json.loads(row[0])
            self.map_ids.update(
                proof["key"][0] for proof in manifest["proof"]["id_mappings"]
            )
        self.repositories = {}
        if json.loads(parent["manifest"])["map_repositories"]:
            for record in archive.rows(src, "repositories"):
                try:
                    value = mapping.repository_projection(record)
                except ConversionError:
                    continue
                self.repositories[value["id"]] = (
                    value["id"],
                    value["name"],
                    None,
                    None,
                    value["metadata"],
                )

    def execute(self, sql, parameters=()):
        normalized = " ".join(sql.split())
        if normalized == "SELECT * FROM conversion_runs ORDER BY id":
            return self.db.execute(
                "SELECT * FROM conversion_runs WHERE parser_version!=? ORDER BY id",
                (PROTOCOL_VERSION,),
            )
        if normalized == "SELECT * FROM repositories WHERE id=?":
            row = self.repositories.get(parameters[0])
            return _Rows([] if row is None else [row])
        if normalized == "SELECT * FROM repositories":
            return _Rows(self.repositories.values())
        if normalized == "SELECT count(*) FROM repositories":
            return _Rows([(len(self.repositories),)])
        if normalized in {
            "SELECT * FROM id_mappings",
            "SELECT * FROM id_mappings ORDER BY id",
        }:
            rows = self.db.execute(sql, parameters)
            return _Rows(row for row in rows if row["id"] in self.map_ids)
        if normalized == "SELECT count(*) FROM id_mappings":
            return _Rows([(len(self.map_ids),)])
        if normalized in {
            "SELECT * FROM validation_results",
            "SELECT * FROM validation_results ORDER BY id",
        }:
            return self.db.execute(
                "SELECT * FROM validation_results WHERE run_id NOT IN "
                "(SELECT id FROM conversion_runs WHERE parser_version=?) ORDER BY id",
                (PROTOCOL_VERSION,),
            )
        if normalized == "SELECT count(*) FROM validation_results":
            return self.db.execute(
                "SELECT count(*) FROM validation_results WHERE run_id NOT IN "
                "(SELECT id FROM conversion_runs WHERE parser_version=?)",
                (PROTOCOL_VERSION,),
            )
        if normalized == "SELECT * FROM conversion_batches ORDER BY id":
            return self.db.execute(
                "SELECT * FROM conversion_batches WHERE run_id=? ORDER BY id",
                (self.parent["id"],),
            )
        if normalized == "SELECT 1 FROM conversion_batches WHERE run_id!=?":
            return self.db.execute(
                "SELECT 1 FROM conversion_batches WHERE run_id!=? AND run_id NOT IN "
                "(SELECT id FROM conversion_runs WHERE parser_version=?)",
                (parameters[0], PROTOCOL_VERSION),
            )
        if normalized in {
            f'SELECT 1 FROM "{table}" LIMIT 1' for table in IDENTITY_TABLES
        }:
            return _Rows([])
        return self.db.execute(sql, parameters)


def _owners(db, *, require_identity=False):
    rows = db.execute("SELECT * FROM conversion_runs ORDER BY id").fetchall()
    parents = [row for row in rows if row["parser_version"] == PARSER_VERSION]
    handoffs = [row for row in rows if row["parser_version"] == phase.PROTOCOL_VERSION]
    identities = [row for row in rows if row["parser_version"] == PROTOCOL_VERSION]
    if (
        len(parents) != 1
        or len(handoffs) != 1
        or len(identities) > 1
        or len(rows) != 2 + len(identities)
    ):
        raise ConversionError("PHASE_OWNERSHIP_MISMATCH")
    if require_identity and not identities:
        raise ConversionError("IDENTITY_PHASE_NOT_COMMITTED")
    return parents[0], handoffs[0], identities[0] if identities else None


def _parent_signatures(handoff, signatures):
    """Admit exactly one reviewed P3A code/contract pair at the upgrade boundary."""
    original = json.loads(handoff["manifest"])["signatures"]
    signatures = {
        key: value
        for key, value in signatures.items()
        if key != "invariant_contract_sha256"
    }
    if original == signatures:
        return signatures
    reviewed = {
        **signatures,
        "ddl_sha256": REVIEWED_P3A_DDL,
        "contract_sha256": REVIEWED_P3A_CONTRACT,
        "converter_sha256": REVIEWED_P3A_CONVERTER,
    }
    if original != reviewed or signatures["ddl_sha256"] != REVIEWED_P3A_DDL:
        raise ConversionError("UNSUPPORTED_P3A_PREDECESSOR")
    return reviewed


def check_parent(db, src, sealed, spec, signatures):
    parent, handoff, identity_run = _owners(db)
    prior_signatures = _parent_signatures(handoff, signatures)
    view = ParentView(db, src, parent) if identity_run else db
    receipt, _ = phase._check(
        view, src, sealed, spec, prior_signatures, require_phase=True
    )
    return parent, handoff, receipt, prior_signatures, view


def _ownership():
    return {
        "owner": PROTOCOL_VERSION,
        "initialization": "one phase receipt INSERT in conversion_runs",
        "immutable_parent": [
            "database_identity",
            "conversion_sources",
            "conversion_runs:P2/P3A",
            "conversion_batches:P2",
            "legacy_records",
            "legacy_values",
            "id_mappings:P2-proof-ids",
            "validation_results:P2",
        ],
        "normalized_writes": {table: ["INSERT"] for table in IDENTITY_TABLES},
        "repository_enrichment": {
            "scope": "same repository ID, exact archived name and metadata",
            "operation": "UPDATE preferred_endpoint_id from NULL to one source-proven same-owner endpoint",
            "current_snapshot_id": "must remain NULL",
            "prior_proof": "unchanged P2 batch repository proof; rederived from sealed source",
        },
        "phase_evidence": {
            "conversion_batches": "INSERT for this run only",
            "id_mappings": "INSERT source-record-linked typed keys not owned by P2",
            "validation_results": "INSERT for this run only",
            "conversion_runs": "UPDATE own state/ended_at only; manifest immutable",
        },
    }


def _receipt(
    db,
    sealed,
    signatures,
    parent,
    handoff,
    prior,
    prior_signatures,
    *,
    stamp,
    batch_size,
):
    from . import identity

    value = {
        "phase_protocol": PROTOCOL_VERSION,
        "state": "committed",
        "committed_at": stamp,
        "source": prior["source"],
        "parent": {
            "run_id": handoff["id"],
            "parser_version": phase.PROTOCOL_VERSION,
            "receipt_sha256": digest(handoff["manifest"].encode()),
            "run_sha256": batch.proof_digest(batch.encode([tuple(handoff)])),
            "p2_run_id": parent["id"],
            "proof_sha256": prior["parent"]["proof_sha256"],
            "diagnostics": prior["diagnostics"],
            "signatures": prior_signatures,
            "reviewed_predecessor_revision": REVIEWED_P3A_REVISION
            if prior_signatures["converter_sha256"] == REVIEWED_P3A_CONVERTER
            else None,
        },
        "target": prior["target"],
        "signatures": signatures,
        "write_ownership": _ownership(),
        "batch_size": batch_size,
        "encoding": sealed["encoding"],
        "recipes": list(identity.RECIPES),
        "activation_permitted": False,
    }
    value["transition_id"] = "p3b:" + digest(canonical(value).encode())
    return value


def _check_identity(
    db, sealed, signatures, verified_parent, *, require_identity=True, batch_size=None
):
    parent, handoff, prior, prior_signatures = verified_parent
    _, _, run = _owners(db, require_identity=require_identity)
    if not run:
        return None, None
    saved = json.loads(run["manifest"])
    receipt = _receipt(
        db,
        sealed,
        signatures,
        parent,
        handoff,
        prior,
        prior_signatures,
        stamp=run["started_at"],
        batch_size=saved.get("batch_size"),
    )
    if (
        run["id"] != receipt["transition_id"]
        or run["source_id"] != parent["source_id"]
        or run["state"] not in {"building", "paused"}
        or not run["started_at"]
        or run["ended_at"] not in {None, run["started_at"]}
        or saved.get("batch_size") is None
        or not isinstance(saved["batch_size"], int)
        or isinstance(saved["batch_size"], bool)
        or saved["batch_size"] < 1
        or run["manifest"] != canonical(receipt)
    ):
        raise ConversionError("IDENTITY_PHASE_RECEIPT_MISMATCH")
    if batch_size is not None and batch_size != receipt["batch_size"]:
        raise ConversionError("RESUME_OPTIONS_MISMATCH")
    return run, receipt


def check(db, src, sealed, spec, signatures, *, require_identity=True, batch_size=None):
    verified_parent = check_parent(db, src, sealed, spec, signatures)[:4]
    return _check_identity(
        db,
        sealed,
        signatures,
        verified_parent,
        require_identity=require_identity,
        batch_size=batch_size,
    )


def _result(receipt, *, created=False):
    return {
        "phase": PROTOCOL_VERSION,
        "transition_id": receipt["transition_id"],
        "parent_proof_sha256": receipt["parent"]["proof_sha256"],
        "parent_diagnostics": receipt["parent"]["diagnostics"],
        "identity_ready": False,
        "phase_committed": True,
        "new_phase": created,
        "archive_complete": True,
        "lifecycle": "building",
        "activation_permitted": False,
    }


def _status_result(receipt, status, *, created=False, new_batches=0):
    parent_counts = receipt["parent"]["diagnostics"]
    phase_counts = status["diagnostics"]
    return {
        **_result(receipt, created=created),
        **status,
        "new_batches": new_batches,
        "identity_ready": bool(
            status["complete"]
            and not parent_counts.get("blocking", 0)
            and not phase_counts.get("blocking", 0)
        ),
        "combined_diagnostics": {
            severity: parent_counts.get(severity, 0) + phase_counts.get(severity, 0)
            for severity in ("blocking", "partial", "info")
        },
    }


def _destination(workspace):
    path = workspace / "target.sqlite3"
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ConversionError("DESTINATION_MISSING_OR_NOT_REGULAR")
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(str(path) + suffix)
        if sidecar.exists() or sidecar.is_symlink():
            if (
                sidecar.is_symlink()
                or not sidecar.is_file()
                or sidecar.stat().st_nlink != 1
            ):
                raise ConversionError("TARGET_SIDECAR_ALIAS_UNSUPPORTED")
            if suffix != "-journal":
                raise ConversionError("TARGET_SIDECAR_UNSUPPORTED")
    return path


def _hot_journal(path):
    with path.open("rb") as stream:
        return path.stat().st_size > 512 and stream.read(8) == bytes.fromhex(
            "d9d505f920a163d7"
        )


def _pending(db, sealed, spec, signatures):
    """Authorize only recognized P3A/P3B state before target journal recovery.

    Spilled domain pages are not read here. Recovery is followed by complete
    source-derived parent/output verification before success or new writes.
    """
    rows = db.execute(
        "SELECT id,source_id,started_at,ended_at,parser_version,state FROM conversion_runs"
    ).fetchall()
    parents = [row for row in rows if row["parser_version"] == PARSER_VERSION]
    handoffs = [row for row in rows if row["parser_version"] == phase.PROTOCOL_VERSION]
    identities = [row for row in rows if row["parser_version"] == PROTOCOL_VERSION]
    if (
        len(parents) != 1
        or len(handoffs) != 1
        or len(identities) > 1
        or len(rows) != 2 + len(identities)
    ):
        raise ConversionError("PHASE_OWNERSHIP_MISMATCH")
    parent = parents[0]
    handoff = db.execute(
        "SELECT * FROM conversion_runs WHERE id=?", (handoffs[0]["id"],)
    ).fetchone()
    prior_signatures = _parent_signatures(handoff, signatures)
    prior = json.loads(handoff["manifest"])
    transition_id = prior.pop("transition_id", None)
    predecessor = prior.get("parent", {}).get("converter_sha256")
    identity = db.execute("SELECT * FROM database_identity").fetchone()
    sources = db.execute("SELECT * FROM conversion_sources").fetchall()
    if (
        parent["state"] != "paused"
        or handoff["state"] != "paused"
        or handoff["source_id"] != parent["source_id"]
        or handoff["started_at"] != handoff["ended_at"]
        or prior.get("committed_at") != handoff["started_at"]
        or prior.get("signatures") != prior_signatures
        or prior.get("phase_protocol") != phase.PROTOCOL_VERSION
        or prior.get("state") != "committed"
        or prior.get("parent", {}).get("run_id") != parent["id"]
        or prior.get("parent", {}).get("parser_version") != PARSER_VERSION
        or predecessor
        not in {prior_signatures["converter_sha256"], *target.REVIEWED_P2_CONVERTERS}
        or prior.get("source", {}).get("source_id") != parent["source_id"]
        or prior.get("source", {}).get("physical_sha256") != sealed["sealed"]["sha256"]
        or prior.get("source", {}).get("core_schema_sha256") != sealed["schema_sha256"]
        or prior.get("source", {}).get("seal_sha256")
        != digest(canonical(sealed).encode())
        or transition_id != handoff["id"]
        or transition_id != "p3a:" + digest(canonical(prior).encode())
        or identity is None
        or identity["format_id"] != "repo-catalog/catalog3-p1"
        or identity["schema_version"] != 3
        or identity["lifecycle"] != "building"
        or identity["publication_seq"] != 0
        or identity["ddl_sha256"].hex() != signatures["ddl_sha256"]
        or prior.get("target")
        != {
            "db_instance_id": identity["db_instance_id"],
            "format_id": identity["format_id"],
            "schema_version": identity["schema_version"],
            "lifecycle": "building",
        }
        or len(sources) != 1
        or sources[0]["id"] != parent["source_id"]
        or sources[0]["source_sha256"].hex() != sealed["sealed"]["sha256"]
        or sources[0]["schema_sha256"].hex() != sealed["schema_sha256"]
        or sources[0]["source_db_instance_id"] != sealed["db_instance_id"]
        or sources[0]["format_id"] != sealed["format_id"]
        or sources[0]["source_catalog"] != canonical(sealed["catalog"]).encode()
        or sources[0]["source_migrations"] != canonical(sealed["migrations"]).encode()
        or target.schema_fingerprint(db) != signatures["target_schema_sha256"]
    ):
        raise ConversionError("PHASE_RECEIPT_MISMATCH")
    phase._require_predecessor_layout({"converter_sha256": predecessor}, sealed)
    target.require_internal_schema(db)
    if identities:
        run = db.execute(
            "SELECT * FROM conversion_runs WHERE id=?", (identities[0]["id"],)
        ).fetchone()
        saved = json.loads(run["manifest"])
        receipt = _receipt(
            db,
            sealed,
            signatures,
            parent,
            handoff,
            prior,
            prior_signatures,
            stamp=run["started_at"],
            batch_size=saved.get("batch_size"),
        )
        if (
            run["id"] != receipt["transition_id"]
            or run["source_id"] != parent["source_id"]
            or run["state"] not in {"building", "paused"}
            or run["ended_at"] not in {None, run["started_at"]}
            or not isinstance(saved.get("batch_size"), int)
            or isinstance(saved.get("batch_size"), bool)
            or saved["batch_size"] < 1
            or run["manifest"] != canonical(receipt)
        ):
            raise ConversionError("IDENTITY_PHASE_RECEIPT_MISMATCH")


@dataclass(frozen=True)
class _VerifiedEntry:
    """Proof material scoped to one unchanged, writer-locked invocation."""

    parent: tuple
    run: sqlite3.Row | None
    receipt: dict | None
    status: dict | None


def _verify_entry(db, src, sealed, spec, signatures, *, batch_size, fault):
    from . import identity

    verified_parent = check_parent(db, src, sealed, spec, signatures)[:4]
    run, receipt = _check_identity(
        db,
        sealed,
        signatures,
        verified_parent,
        require_identity=False,
        batch_size=batch_size,
    )
    status = (
        identity.validate_output(db, src, run, receipt, fault=fault) if run else None
    )
    return _VerifiedEntry(verified_parent, run, receipt, status)


def _file_state(path):
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def _open(workspace, src, sealed, spec, signatures, *, batch_size=None, fault=no_fault):
    """Verify entry once; recovery or changed native-open state invalidates it."""
    path = _destination(workspace)
    journal = Path(str(path) + "-journal")
    before = _file_state(path)
    verified = None
    with target.readonly_destination(path) as existing:
        if journal.exists() and _hot_journal(journal):
            _pending(existing, sealed, spec, signatures)
        else:
            verified = _verify_entry(
                existing,
                src,
                sealed,
                spec,
                signatures,
                batch_size=batch_size,
                fault=fault,
            )
    if _file_state(_destination(workspace)) != before:
        raise ConversionError("DESTINATION_CHANGED_DURING_VERIFICATION")
    db = target.connect(path)
    try:
        if verified is None or _file_state(path) != before:
            verified = _verify_entry(
                db,
                src,
                sealed,
                spec,
                signatures,
                batch_size=batch_size,
                fault=fault,
            )
        return db, verified
    except BaseException:
        db.close()
        raise


def _initialize(
    db, workspace, sealed, signatures, verified, *, batch_size, free_bytes, fault
):
    if verified.run:
        return verified.run, verified.receipt, False
    parent, handoff, prior, prior_signatures = verified.parent
    receipt = _receipt(
        db,
        sealed,
        signatures,
        parent,
        handoff,
        prior,
        prior_signatures,
        stamp=now(),
        batch_size=batch_size,
    )
    capacity.preflight(
        workspace,
        {
            "required_free_bytes": 4 * len(canonical(receipt).encode())
            + 64 * 1024 * 1024
        },
        free_bytes=free_bytes,
    )
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "INSERT INTO conversion_runs VALUES(?,?,?,?,?,'paused',?)",
            (
                receipt["transition_id"],
                parent["source_id"],
                receipt["committed_at"],
                receipt["committed_at"],
                PROTOCOL_VERSION,
                canonical(receipt),
            ),
        )
        fault("before_identity_init_commit", transition_id=receipt["transition_id"])
        db.execute("COMMIT")
    except BaseException:
        if db.in_transaction:
            db.rollback()
        raise
    fault("after_identity_init_commit", transition_id=receipt["transition_id"])
    run = db.execute(
        "SELECT * FROM conversion_runs WHERE id=?", (receipt["transition_id"],)
    ).fetchone()
    return run, receipt, True


def _options(batch_size, max_batches=None):
    if (
        not isinstance(batch_size, int)
        or isinstance(batch_size, bool)
        or batch_size < 1
        or (
            max_batches is not None
            and (
                not isinstance(max_batches, int)
                or isinstance(max_batches, bool)
                or max_batches < 0
            )
        )
    ):
        raise ConversionError("INVALID_BATCH_OPTIONS")


def initialize(
    workspace,
    *,
    batch_size=100,
    ddl=None,
    contract=None,
    free_bytes=None,
    fault=no_fault,
):
    _options(batch_size)
    workspace = Path(workspace)
    _, spec, signatures = resources(ddl, contract)
    with target.writer_lock(workspace):
        sealed = source.verify_seal(workspace, allow_legacy=True)
        with source.readonly(workspace / "source.sqlite3") as src:
            db, verified = _open(
                workspace, src, sealed, spec, signatures, batch_size=batch_size
            )
            try:
                _, receipt, created = _initialize(
                    db,
                    workspace,
                    sealed,
                    signatures,
                    verified,
                    batch_size=batch_size,
                    free_bytes=free_bytes,
                    fault=fault,
                )
                return _result(receipt, created=created)
            finally:
                if db.in_transaction:
                    db.rollback()
                db.close()


def convert(
    workspace,
    *,
    batch_size=100,
    max_batches=None,
    ddl=None,
    contract=None,
    free_bytes=None,
    fault=no_fault,
):
    from . import identity

    _options(batch_size, max_batches)
    workspace = Path(workspace)
    _, spec, signatures = resources(ddl, contract)
    with target.writer_lock(workspace):
        sealed = source.verify_seal(workspace, allow_legacy=True)
        with source.readonly(workspace / "source.sqlite3") as src:
            db, verified = _open(
                workspace,
                src,
                sealed,
                spec,
                signatures,
                batch_size=batch_size,
                fault=fault,
            )
            try:
                run, receipt, created = _initialize(
                    db,
                    workspace,
                    sealed,
                    signatures,
                    verified,
                    batch_size=batch_size,
                    free_bytes=free_bytes,
                    fault=fault,
                )
                status = verified.status
                if status is None:
                    status = identity.validate_output(
                        db, src, run, receipt, fault=fault
                    )
                completed, committed = status["committed_batches"], 0
                for position, (recipe, index, records, input_sha256) in enumerate(
                    identity.batches(db, src, run, receipt, batch_size)
                ):
                    if position < completed:
                        continue
                    if max_batches is not None and committed >= max_batches:
                        break
                    output = identity.prepare(
                        db,
                        src,
                        run,
                        recipe,
                        index,
                        records,
                        encoding=sealed["encoding"],
                    )
                    identity.commit(
                        db,
                        run,
                        recipe,
                        index,
                        input_sha256,
                        output,
                        lambda point, **context: fault(
                            point, **{**context, "table": recipe, "index": index}
                        ),
                    )
                    committed += 1
                source.verify_seal(workspace, allow_legacy=True)
                # Recheck immutable parents and independently rederive every
                # committed identity output once at this invocation boundary.
                run, receipt = check(
                    db, src, sealed, spec, signatures, batch_size=batch_size
                )
                status = identity.validate_output(db, src, run, receipt)
                return _status_result(
                    receipt, status, created=created, new_batches=committed
                )
            finally:
                if db.in_transaction:
                    db.rollback()
                db.close()


def verify(workspace, *, ddl=None, contract=None):
    from . import identity

    workspace = Path(workspace)
    _, spec, signatures = resources(ddl, contract)
    with target.writer_lock(workspace):
        sealed = source.verify_seal(workspace, allow_legacy=True)
        with (
            source.readonly(workspace / "source.sqlite3") as src,
            source.readonly(_destination(workspace)) as db,
        ):
            run, receipt = check(db, src, sealed, spec, signatures)
            status = identity.validate_output(db, src, run, receipt)
            return _status_result(receipt, status)
