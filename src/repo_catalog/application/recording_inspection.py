"""Bounded supplementary message inspection, with no domain admission."""

from repo_catalog.adapters.recording import LocalArchiveReader


def inspect_message(archive_root, reference, *, max_bytes=1024 * 1024):
    recorded = LocalArchiveReader(archive_root).read(
        reference, max_body_bytes=max_bytes
    )
    return {
        "archive_reference": reference,
        "context": recorded.context,
        "body_bytes": len(recorded.body) if recorded.body is not None else None,
        "admitted": False,
    }
