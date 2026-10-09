"""Ordinary catalog validation independent of historical import workspaces."""

from repo_catalog.domain.document import text_body_sha256


def check_catalog(store):
    issues = [dict(row) for row in store.all("PRAGMA foreign_key_check")]
    integrity = [row[0] for row in store.all("PRAGMA quick_check")]
    if integrity != ["ok"]:
        issues.append({"code": "SQLITE_STRUCTURAL_CORRUPTION", "details": integrity})
    for row in store.execute(
        "SELECT text_body_id,body,byte_length,sha256 FROM text_bodies"
    ):
        try:
            valid = (
                text_body_sha256(row["body"]) == row["sha256"]
                and len(row["body"].encode("utf-8")) == row["byte_length"]
            )
        except (TypeError, UnicodeError):
            valid = False
        if not valid:
            issues.append(
                {
                    "code": "TEXT_BODY_DIGEST_MISMATCH",
                    "text_body_id": row["text_body_id"],
                }
            )
    return issues
