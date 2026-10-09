"""The single packaged catalog3 format contract."""

import hashlib
from importlib.resources import files

FORMAT_ID = "repo-catalog/catalog3"
SCHEMA_VERSION = 12


def schema_sql():
    return "\n".join(
        files("repo_catalog").joinpath("resources", name).read_text()
        for name in (
            "catalog3.sql",
            "cas_integrity.sql",
            "exchange.sql",
            "identity_relations.sql",
        )
    )


DDL_SHA256 = hashlib.sha256(schema_sql().encode()).digest()
