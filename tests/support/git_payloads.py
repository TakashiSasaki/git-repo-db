"""Real synthetic Git blob identities for shared physical-integrity scenarios."""

import hashlib

from repo_catalog.adapters.sqlite.payloads import intern_payload


def register_git_blob(db, body, *, object_format="sha1"):
    """Map raw bytes to the blob OID computed from their exact Git object header."""
    oid = hashlib.new(object_format, f"blob {len(body)}\0".encode() + body).digest()
    reference = intern_payload(db, body, representation="git-object-raw-v1")
    found = db.execute(
        "SELECT git_object_id FROM git_objects WHERE object_format=? AND oid=?",
        (object_format, oid),
    ).fetchone()
    if found:
        return reference
    object_id = db.execute(
        "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES(?,?,'blob',?,1)",
        (object_format, oid, len(body)),
    ).lastrowid
    db.execute(
        "INSERT INTO git_object_payloads(git_object_id,payload_representation,payload_sha256) VALUES(?,?,?)",
        (object_id, *reference.parameters()),
    )
    return reference
