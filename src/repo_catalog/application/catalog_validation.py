"""Ordinary catalog validation independent of historical import workspaces."""

from repo_catalog.adapters.git.parsing import verify_git_object_structure
from repo_catalog.domain.document import text_body_sha256
from repo_catalog.domain.models import CatalogError


def check_catalog(store, *, full=False):
    issues = [dict(row) for row in store.all("PRAGMA foreign_key_check")]
    integrity = [row[0] for row in store.all("PRAGMA quick_check")]
    if integrity != ["ok"]:
        issues.append({"code": "SQLITE_STRUCTURAL_CORRUPTION", "details": integrity})
    from repo_catalog.adapters.sqlite.json_contracts import inventory, validate_catalog

    try:
        if full:
            validate_catalog(store.connection)
        else:
            inventory(store.connection)
    except CatalogError as error:
        issues.append({"code": error.code, "message": str(error)})
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
    if full:
        for row in store.execute(
            "SELECT g.git_object_id,g.object_format,g.oid,g.type,g.size,b.body "
            "FROM git_objects g JOIN git_object_payloads p USING(git_object_id) "
            "JOIN stored_bytes b ON b.sha256=p.payload_sha256 "
            "WHERE NOT EXISTS(SELECT 1 FROM payload_quarantine q WHERE q.sha256=b.sha256)"
        ):
            try:
                verify_git_object_structure(store.connection, row["git_object_id"])
            except CatalogError as error:
                issues.append(
                    {"code": error.code, "git_object_id": row["git_object_id"]}
                )
    return issues
