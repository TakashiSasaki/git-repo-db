"""Computed canonical Git predicates for ordinary SQLite readers."""

import base64
import hashlib
import json

from repo_catalog.domain.git_decoding import validate_decoded_value
from repo_catalog.domain.git_intrinsic import (
    _oid,
    commit_structure,
    tag_structure,
    tree_structure,
)
from repo_catalog.domain.models import CatalogError


def _oid_bytes(fmt, value):
    try:
        return _oid(fmt, value.encode("ascii"))
    except (CatalogError, AttributeError, UnicodeError, TypeError):
        return None


def _content_digest_valid(body, algorithm, digest):
    try:
        if algorithm not in ("md5", "sha1", "sha256"):
            return 0
        return int(hashlib.new(algorithm, body).digest() == digest)
    except (ValueError, TypeError):
        return 0


def _commit_valid(fmt, body, tree_oid, tree_offset, parent_count, headers, message):
    try:
        actual = commit_structure(fmt, body)
        return int(
            actual["tree_oid"] == tree_oid
            and actual["tree_header_offset"] == tree_offset
            and len(actual["parents"]) == parent_count
            and actual["raw_headers"] == headers
            and actual["raw_message"] == message
        )
    except (CatalogError, TypeError, ValueError):
        return 0


def _tree_valid(fmt, body):
    try:
        tree_structure(fmt, body)
        return 1
    except (CatalogError, TypeError, ValueError):
        return 0


def _tag_valid(fmt, body, target_oid, target_type):
    try:
        actual = tag_structure(fmt, body)
        return int(
            actual["target_oid"] == target_oid and actual["target_type"] == target_type
        )
    except (CatalogError, TypeError, ValueError):
        return 0


def _ref_capture_valid(fmt, roots_json, observed_json):
    try:
        if fmt not in ("sha1", "sha256"):
            return 0
        roots, observations = json.loads(roots_json), json.loads(observed_json)
        if not isinstance(roots, list) or not isinstance(observations, list):
            return 0
        expected = {}
        for ref in roots:
            name = base64.b64decode(ref["name_b64"], validate=True)
            if not name or name in expected:
                return 0
            expected[name] = (
                fmt,
                bytes.fromhex(ref["oid"]),
                bytes.fromhex(ref["peeled"]) if ref.get("peeled") else None,
                ref["type"],
            )
        actual = {}
        for ref in observations:
            name = bytes.fromhex(ref["name_hex"])
            if name in actual:
                return 0
            actual[name] = (
                ref["object_format"],
                bytes.fromhex(ref["oid_hex"]),
                bytes.fromhex(ref["peeled_hex"])
                if ref["peeled_hex"] is not None
                else None,
                ref["type"],
            )
        return int(expected == actual)
    except (KeyError, ValueError, TypeError):
        return 0


def _decoded_value_valid(
    family, fmt, body, key, settings_json, subject, value, metadata
):
    try:
        validate_decoded_value(
            family, fmt, body, key, json.loads(settings_json), subject, value, metadata
        )
        return 1
    except (
        CatalogError,
        TypeError,
        ValueError,
        KeyError,
        AttributeError,
        UnicodeError,
    ):
        return 0


def _metadata_equal(left, right):
    try:
        return int(json.loads(left) == json.loads(right))
    except (ValueError, TypeError):
        return 0


def _name_subject_valid(fmt, body, name, offset, length, mode, oid):
    try:
        # Work on this exact bounded entry span, preserving linear installation
        # for large trees. Whole-object availability checks the complete tree.
        entries = tree_structure(fmt, body[offset : offset + length])
        return int(
            offset >= 0
            and len(entries) == 1
            and entries[0]
            == {
                "raw_name": name,
                "entry_offset": 0,
                "entry_length": length,
                "mode": mode,
                "child_oid": oid,
            }
        )
    except (CatalogError, TypeError, ValueError):
        return 0


def register_git_intrinsic_sql_functions(db):
    """Install pure byte predicates; existing registrations remain undisturbed."""
    present = {row[0] for row in db.execute("PRAGMA function_list")}
    for name, arity, predicate in (
        ("repo_catalog_git_oid_bytes", 2, _oid_bytes),
        ("repo_catalog_git_content_digest_valid", 3, _content_digest_valid),
        ("repo_catalog_git_commit_shape_valid", 7, _commit_valid),
        ("repo_catalog_git_tree_shape_valid", 2, _tree_valid),
        ("repo_catalog_git_tag_shape_valid", 4, _tag_valid),
        ("repo_catalog_git_ref_capture_valid", 3, _ref_capture_valid),
        ("repo_catalog_git_decoded_value_valid", 8, _decoded_value_valid),
        ("repo_catalog_git_metadata_equal", 2, _metadata_equal),
        ("repo_catalog_git_name_subject_valid", 7, _name_subject_valid),
    ):
        if name not in present:
            db.create_function(name, arity, predicate, deterministic=True)
