"""Portable single-repository exchange without acquisition or local policy changes."""

import json
from pathlib import Path

from repo_catalog.adapters.filesystem.locks import FileLock
from repo_catalog.adapters.sqlite.exchange import Graph, canonical
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.domain.models import CatalogError, Result


class ExchangeService:
    def __init__(self, state_dir):
        self.path = Path(state_dir)

    def export_repository(
        self,
        repository_uuidv4,
        output_path,
        *,
        fetch_occurrence_uuidv4s=None,
        fetch_collection_id=None,
    ):
        destination = Path(output_path)
        with FileLock(self.path / "locks" / "writer.lock"), Store(self.path) as store:
            try:
                with store.transaction():
                    unit = Graph(store.connection).export(
                        repository_uuidv4,
                        fetch_occurrence_uuidv4s=fetch_occurrence_uuidv4s,
                        fetch_collection_id=fetch_collection_id,
                    )
            except CatalogError as exc:
                if exc.code == "PAYLOAD_CORRUPTION" and exc.details.get("sha256"):
                    from repo_catalog.adapters.sqlite.cas_integrity import (
                        diagnose_corruption,
                    )

                    diagnose_corruption(
                        store.connection, bytes.fromhex(exc.details["sha256"])
                    )
                raise
            try:
                with destination.open("x", encoding="utf-8") as handle:
                    handle.write(canonical(unit) + "\n")
            except FileExistsError as exc:
                raise CatalogError(
                    "ALREADY_EXISTS", "Exchange destination already exists"
                ) from exc
            return Result(
                {
                    "path": str(destination),
                    "repository_uuidv4": repository_uuidv4,
                    "records": len(unit["records"]),
                },
                catalog=store.revision(),
            )

    def import_file(self, input_path):
        try:
            unit = json.loads(Path(input_path).read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise CatalogError("INVALID_EXCHANGE", "Invalid exchange JSON") from exc
        with FileLock(self.path / "locks" / "writer.lock"), Store(self.path) as store:
            with store.transaction():
                result = Graph(store.connection).receive(unit)
                if result["received_records"] or result["admitted_records"]:
                    store.publish()
            response = Result(
                result,
                catalog=store.revision(),
                status="partial"
                if result["staged_records"] or result["rejected_records"]
                else "complete",
            )
            if result["staged_records"]:
                response.coverage.add(
                    "exchange", "unresolved_records", count=result["staged_records"]
                )
            if result["rejected_records"]:
                response.coverage.add(
                    "exchange",
                    "rejected_invalid_bytes_and_dependencies",
                    count=result["rejected_records"],
                )
            return response

    def staging(self):
        with Store(self.path, readonly=True) as store:
            rows = [
                dict(row)
                for row in store.all(
                    "SELECT record_key,table_name,repository_uuidv4,reason FROM exchange_staging ORDER BY record_key,content_sha256"
                )
            ]
            return Result(rows, catalog=store.revision())
