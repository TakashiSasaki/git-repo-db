"""The single packaged catalog3 format contract."""

import hashlib
from importlib.resources import files

FORMAT_ID = "repo-catalog/catalog3"
SCHEMA_VERSION = 8


def schema_sql():
    return files("repo_catalog").joinpath("resources/catalog3.sql").read_text()


DDL_SHA256 = hashlib.sha256(schema_sql().encode()).digest()
