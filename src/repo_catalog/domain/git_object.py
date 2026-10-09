"""Authoritative Git object identity validation, independent of decoding profiles."""

import hashlib

from repo_catalog.domain.models import CatalogError


def validate_git_object(object_format, oid, object_type, size, body, sha256=None):
    if (
        object_format not in ("sha1", "sha256")
        or object_type not in ("blob", "tree", "commit", "tag")
        or type(size) is not int
        or size < 0
        or not isinstance(body, bytes)
    ):
        raise CatalogError("GIT_OBJECT_IDENTITY", "Malformed Git object identity")
    digest = hashlib.new(object_format)
    digest.update(f"{object_type} {len(body)}\0".encode("ascii"))
    digest.update(body)
    if (
        size != len(body)
        or digest.digest() != oid
        or (sha256 is not None and hashlib.sha256(body).digest() != sha256)
    ):
        raise CatalogError(
            "GIT_OBJECT_IDENTITY",
            "Raw bytes do not match the declared Git object identity",
        )
