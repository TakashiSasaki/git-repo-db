"""Core-owned SQLite validators and initial repository admission."""

import json
from uuid import UUID

from repo_catalog.adapters.sqlite.p1_schema import canonical
from repo_catalog.domain.p1_core import register_functions as register_core
from repo_catalog.domain.ref_observation import valid_ref_absence


def register_functions(db):
    def uuid7(value):
        try:
            parsed = UUID(value)
            return (
                isinstance(value, str) and str(parsed) == value and parsed.version == 7
            )
        except (ValueError, TypeError, AttributeError):
            return False

    def mapping_path(value):
        try:
            decoded = json.loads(value)
            return canonical(decoded) == value and (
                decoded is None or isinstance(decoded, str) and bool(decoded)
            )
        except (ValueError, TypeError, RecursionError):
            return False

    def result_formats(*values):
        known = [value for value in values if value is not None]
        return len(set(known)) <= 1

    db.create_function("p1_uuid7", 1, uuid7, deterministic=True)
    db.create_function("p1_ref_absence", 1, valid_ref_absence, deterministic=True)
    db.create_function("p1_mapping_path", 1, mapping_path, deterministic=True)
    db.create_function("p1_ref_result_formats", 4, result_formats, deterministic=True)
    register_core(db)


def initialize_repository(db, repository_uuidv4):
    db.execute("INSERT INTO repositories VALUES(?)", (repository_uuidv4,))
