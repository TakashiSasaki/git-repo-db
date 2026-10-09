"""Archive independent, immutable receipts for current-resource collection.

These receipts describe what was observed in an exact collection scope. Their
member digests do not reference mutable current rows; editing a resource cannot
change the meaning of an earlier complete observation.
"""

from __future__ import annotations

import json

from repo_catalog.domain.models import CatalogError

PROOF_KIND = "current-resource-pages-v1"


class CurrentCollectionProof:
    def __init__(self, db):
        self.db = db

    def page(
        self,
        fetch_collection_id,
        ordinal,
        observed_at_us,
        next_cursor,
        members,
        status=200,
        *,
        parser_module,
        parser_version,
    ):
        """Persist one interpreted page without requiring response bytes.

        The caller admits resources and this receipt in the same transaction.
        Failed parsing or admission must not be converted into a receipt.
        """
        from repo_catalog.adapters.sqlite.json_contracts import validate_record

        row = {
            "fetch_collection_id": fetch_collection_id,
            "ordinal": ordinal,
            "observed_at_us": observed_at_us,
            "next_cursor": next_cursor,
            "members": json.dumps(members, sort_keys=True, separators=(",", ":")),
            "status": status,
            "parser_module": parser_module,
            "parser_version": parser_version,
        }
        if (
            type(ordinal) is not int
            or ordinal < 0
            or type(observed_at_us) is not int
            or not -(1 << 63) <= observed_at_us < (1 << 63)
            or type(status) is not int
            or not 200 <= status < 300
            or (next_cursor is not None and not isinstance(next_cursor, str))
        ):
            raise CatalogError("INVALID_COLLECTION_PROOF", "Invalid page receipt")
        validate_record(self.db, "current_collection_pages", row)
        columns = tuple(row)
        self.db.execute(
            "INSERT INTO current_collection_pages("
            + ",".join(columns)
            + ") VALUES("
            + ",".join("?" for _ in columns)
            + ")",
            tuple(row.values()),
        )

    def pages(self, fetch_collection_id):
        cursor = self.db.execute(
            "SELECT * FROM current_collection_pages WHERE fetch_collection_id=? ORDER BY ordinal",
            (fetch_collection_id,),
        )
        columns = tuple(column[0] for column in cursor.description)
        return [dict(zip(columns, row, strict=True)) for row in cursor]

    def members(self, fetch_collection_id):
        return [
            member
            for page in self.pages(fetch_collection_id)
            for member in json.loads(page["members"])
        ]

    def evidence(self, fetch_collection_id):
        pages = self.pages(fetch_collection_id)
        if (
            not pages
            or [page["ordinal"] for page in pages] != list(range(len(pages)))
            or any(page["next_cursor"] is None for page in pages[:-1])
            or pages[-1]["next_cursor"] is not None
        ):
            return None
        return {
            "kind": PROOF_KIND,
            "page_ordinals": [page["ordinal"] for page in pages],
            "terminal": True,
        }

    def observed_at_us(self, fetch_collection_id):
        pages = self.pages(fetch_collection_id)
        return max((page["observed_at_us"] for page in pages), default=None)

    def is_complete_marker(self, marker):
        if marker["asserted_state"] != "complete":
            return False
        try:
            evidence = json.loads(marker["evidence"])
        except (ValueError, TypeError):
            return False
        expected = self.evidence(marker["fetch_collection_id"])
        return (
            expected is not None
            and evidence == expected
            and marker["observed_at_us"]
            == self.observed_at_us(marker["fetch_collection_id"])
        )
