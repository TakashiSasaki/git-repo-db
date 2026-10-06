import hashlib
import struct


def identifier(value):
    return '"' + value.replace('"', '""') + '"'


def archive_bytes(storage_type, value):
    """TEXT/BLOB inputs are exact bytes obtained with SQLite CAST(value AS BLOB)."""
    if storage_type == "null":
        if value is not None:
            raise ValueError("NULL type mismatch")
        return b""
    if storage_type == "integer":
        if type(value) is not int or not -(2**63) <= value < 2**63:
            raise ValueError("INTEGER type mismatch")
        return str(value).encode("ascii")
    if storage_type == "real":
        if type(value) is not float:
            raise ValueError("REAL type mismatch")
        return struct.pack(">d", value)
    if storage_type in ("text", "blob"):
        if not isinstance(value, bytes):
            raise ValueError("Use exact CAST bytes")
        return value
    raise ValueError("Unknown SQLite storage type")


def tagged_key(values):
    """PK-order (typeof, value) pairs; type tag + uint64 length + exact bytes."""
    tags = {"null": b"N", "integer": b"I", "real": b"R", "text": b"T", "blob": b"B"}
    encoded = []
    for kind, value in values:
        raw = archive_bytes(kind, value)
        encoded.append(tags[kind] + len(raw).to_bytes(8, "big") + raw)
    return b"".join(encoded)


def row_digest(values):
    """Schema column-order (name, typeof, value); name length/name + tagged value."""
    material = []
    for name, kind, value in values:
        raw_name = name.encode("utf-8")
        material.append(
            len(raw_name).to_bytes(8, "big") + raw_name + tagged_key([(kind, value)])
        )
    return hashlib.sha256(b"".join(material)).digest()


JSON_COLUMNS = {
    "sources": ("settings",),
    "inventory_runs": ("scope",),
    "repositories": ("metadata",),
    "jobs": ("request", "checkpoint"),
    "collection_runs": ("request", "roots_manifest"),
    "commits": ("metadata",),
    "coverage_components": ("details",),
    "pr_observations": ("payload",),
    "pr_documents": ("metadata",),
    "resource_observations": ("metadata",),
    "pr_reviews": ("payload",),
    "review_threads": ("payload",),
    "review_comments": ("payload",),
    "pr_events": ("payload",),
    "pr_code_observations": ("details",),
    "pr_commits": ("payload",),
    "pr_file_changes": ("payload",),
    "collections": ("scope",),
    "collection_pages": ("request",),
    "sync_checkpoints": ("value",),
    "search_documents": ("metadata",),
    "service_instances": ("metadata",),
    "repository_bindings": ("metadata",),
    "repository_endpoints": ("metadata",),
}
BOOLEAN_COLUMNS = {
    "preservation_obligations": (
        "roots_fixed",
        "structure_done",
        "digest_done",
        "text_done",
        "published",
    ),
    "snapshots": ("published",),
    "acquisition_roots": ("published",),
    "git_objects": ("verified",),
    "root_manifests": ("complete",),
    "pr_observations": ("published",),
    "pr_documents": ("deleted",),
    "repository_endpoints": ("is_preferred",),
}
ORDINAL_COLUMNS = {
    "commit_parents": ("parent_ordinal",),
    "pr_events": ("ordinal",),
    "pr_commits": ("ordinal",),
    "pr_file_changes": ("ordinal",),
    "collection_pages": ("ordinal",),
    "collection_memberships": ("ordinal",),
}
STATE_VALUES = {
    "jobs": (
        "queued",
        "running",
        "waiting",
        "complete",
        "failed",
        "interrupted",
        "cancelled",
    ),
    "inventory_runs": ("running", "complete", "partial"),
    "collection_runs": ("planned", "fetching", "refs_captured", "published"),
    "cache_entries": ("available", "evicting", "evicted"),
    "collections": ("running", "partial", "complete"),
    "pr_code_observations": ("pending", "partial", "complete"),
    "index_generations": ("building", "ready", "retired", "removed", "unavailable"),
    "content_locations": ("available", "unavailable"),
}
