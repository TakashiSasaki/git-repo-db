"""The single packaged catalog3 format contract."""

import hashlib
from importlib.resources import files

FORMAT_ID = "repo-catalog/catalog3"
SCHEMA_VERSION = 21

OPERATIONAL_FORMAT_ID = "repo-catalog/operational1"
OPERATIONAL_SCHEMA_VERSION = 1

SEARCH_FORMAT_ID = "repo-catalog/search1"
SEARCH_SCHEMA_VERSION = 1


def schema_sql():
    return "\n".join(
        files("repo_catalog").joinpath("resources", name).read_text()
        for name in (
            "catalog3.sql",
            "git_domain.sql",
            "git_facts.sql",
            "cas_integrity.sql",
            "exchange.sql",
            "identity_relations.sql",
            "current_resources.sql",
            "current_api.sql",
            "current_collections.sql",
            "json_contracts.sql",
        )
    )


def operational_schema_sql():
    return files("repo_catalog").joinpath("resources", "operational.sql").read_text()


def search_schema_sql():
    return files("repo_catalog").joinpath("resources", "search.sql").read_text()


DDL_SHA256 = hashlib.sha256(schema_sql().encode()).digest()
OPERATIONAL_DDL_SHA256 = hashlib.sha256(operational_schema_sql().encode()).digest()
SEARCH_DDL_SHA256 = hashlib.sha256(search_schema_sql().encode()).digest()
