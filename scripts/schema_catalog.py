"""Read-only, all-format schema catalog; not a semantic reasoner or DB validator.

The registry identifies composition entry points, not one distribution owning all
tables in a composed schema. Source ownership is checked separately against the
workspace's declared wheel source layout. See schema-model-inventory.md.
"""

from __future__ import annotations

import hashlib
import sqlite3
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQLITE = "repo_catalog/adapters/sqlite/"
P1_FACTORY = "packages/runtime/src/" + SQLITE + "p1_schema.py"
NORMAL_FACTORY = "src/" + SQLITE + "schema.py"
ACCESS_FACTORY = "packages/access/src/" + SQLITE + "access_schema.py"
FILESYSTEM_FACTORY = "packages/filesystem/src/repo_catalog/filesystem/store.py"
WORKTREES_FACTORY = "packages/worktrees/src/repo_catalog/worktrees/catalog.py"

# These are implementation entry points and applicable accepted design domains.
# Normal Catalog3 is mixed; its historical name "core" is not a domain claim.
STORE_LAYOUT = {
    "normal.core": (NORMAL_FACTORY, ["core", "context", "access"]),
    "normal.operational": (NORMAL_FACTORY, ["operational"]),
    "normal.search": (NORMAL_FACTORY, ["search"]),
    "p1.core": (P1_FACTORY, ["core"]),
    "p1.context": (P1_FACTORY, ["context"]),
    "p1.operational": (P1_FACTORY, ["operational"]),
    "p1.search": (P1_FACTORY, ["search"]),
    "access": (ACCESS_FACTORY, ["access"]),
    "filesystem": (FILESYSTEM_FACTORY, ["filesystem"]),
    "worktrees": (WORKTREES_FACTORY, ["worktrees"]),
}

DOMAIN_DISTRIBUTIONS = {
    name: "repo-catalog-" + name
    for name in (
        "core",
        "context",
        "access",
        "operational",
        "search",
        "filesystem",
        "worktrees",
    )
}


def workspace_sources(root: Path = ROOT) -> tuple[dict, dict]:
    """Read declared source-layout ownership; do not claim installed-wheel proof."""
    root_config = tomllib.loads((root / "pyproject.toml").read_text())
    members = root_config["tool"]["uv"]["workspace"]["members"]
    distributions, owners, installed = {}, {}, {}
    for directory in [".", *members]:
        if any(char in directory for char in "*?[]"):
            raise ValueError(
                "Workspace glob needs explicit inventory support: " + directory
            )
        base = root / directory
        config = tomllib.loads((base / "pyproject.toml").read_text())
        project = config["project"]
        name = project["name"]
        if name in distributions:
            raise ValueError("Duplicate distribution: " + name)
        wheel = config["tool"]["hatch"]["build"]["targets"]["wheel"]
        if wheel != {"packages": ["src/repo_catalog"]}:
            raise ValueError("Unsupported wheel source layout: " + name)
        distributions[name] = {
            "pyproject": (base / "pyproject.toml").relative_to(root).as_posix(),
            "version": project["version"],
            "dependency_requirements": project.get("dependencies", []),
            "optional_dependency_requirements": project.get(
                "optional-dependencies", {}
            ),
        }
        for path in sorted((base / "src/repo_catalog").rglob("*")):
            if "__pycache__" in path.parts or not path.is_file():
                continue
            if path.is_symlink():
                raise ValueError("Linked distribution source refused: " + str(path))
            source = path.relative_to(root).as_posix()
            install_path = path.relative_to(base / "src").as_posix()
            if install_path in installed:
                raise ValueError(
                    f"Duplicate installed source path {install_path}: {installed[install_path]}, {name}"
                )
            installed[install_path] = name
            owners[source] = name
    return dict(sorted(distributions.items())), dict(sorted(owners.items()))


def _prepare_p1(store):
    from repo_catalog.adapters.sqlite import p1_schema

    def prepare(db):
        p1_schema.register_functions(db, store)
        p1_schema.configure(db, store)

    return prepare


def _prepare_local(db: sqlite3.Connection):
    db.execute("PRAGMA trusted_schema=OFF")


def _prepare_worktrees(db: sqlite3.Connection):
    _prepare_local(db)
    db.execute("PRAGMA recursive_triggers=ON")


def build_catalog() -> dict:
    from repo_catalog.adapters.sqlite import access_schema, p1_schema
    from repo_catalog.filesystem import store as filesystem
    from repo_catalog.worktrees import catalog as worktrees
    from scripts.schema_inventory import introspect_all, introspect_store

    distributions, owners = workspace_sources()
    normal = introspect_all(include_runtime_details=True)
    stores = {}
    sources = {}
    for role, store in normal["stores"].items():
        key = "normal." + role
        store["slug"] = key
        for table in store["tables"].values():
            table["store"] = key
            table.pop("logical_incoming", None)
            table.pop("logical_outgoing", None)
        stores[key] = store
        resources = (
            [
                "catalog3",
                "git_domain",
                "git_facts",
                "cas_integrity",
                "exchange",
                "identity_relations",
                "current_resources",
                "current_api",
                "current_collections",
                "json_contracts",
            ]
            if role == "core"
            else [role]
        )
        sources[key] = [
            NORMAL_FACTORY,
            *["src/repo_catalog/resources/" + name + ".sql" for name in resources],
        ]

    # Compare the committed P1 manifest as well as inspecting the actual DDL.
    p1_schema.verify_declared()
    for role in p1_schema.STORES:
        key = "p1." + role
        stores[key] = introspect_store(
            key,
            "P1 " + role.title(),
            role + ".sqlite3",
            p1_schema.FORMAT,
            None,
            bytes.fromhex(p1_schema.fingerprint(role)),
            p1_schema.compose(role),
            {},
            prepare=_prepare_p1(role),
            include_runtime_details=True,
        )
        sources[key] = [P1_FACTORY, f"packages/{role}/src/{SQLITE}p1_ddl/{role}.sql"]
        if role in {"core", "context"}:
            sources[key].append(
                "packages/contracts/src/" + SQLITE + "p1_ddl/coverage.sql"
            )

    stores["access"] = introspect_store(
        "access",
        "Access",
        "access.sqlite3",
        access_schema.FORMAT,
        access_schema.SCHEMA_VERSION,
        bytes.fromhex(access_schema.fingerprint()),
        access_schema.schema_sql(),
        {},
        prepare=access_schema.register_functions,
        include_runtime_details=True,
    )
    sources["access"] = [
        ACCESS_FACTORY,
        *[
            "packages/access/src/" + SQLITE + "access_ddl/" + name + ".sql"
            for name in ("registry", "connections")
        ],
    ]
    stores["filesystem"] = introspect_store(
        "filesystem",
        "Filesystem",
        "filesystem.sqlite3",
        None,
        filesystem.SCHEMA_VERSION,
        hashlib.sha256(filesystem.DDL.encode()).digest(),
        filesystem.DDL,
        {},
        prepare=_prepare_local,
        include_runtime_details=True,
    )
    sources["filesystem"] = [FILESYSTEM_FACTORY]
    stores["worktrees"] = introspect_store(
        "worktrees",
        "Worktrees",
        "worktrees.sqlite3",
        worktrees.FORMAT,
        None,
        bytes.fromhex(worktrees.FINGERPRINT),
        worktrees.SCHEMA,
        {},
        prepare=_prepare_worktrees,
        include_runtime_details=True,
    )
    sources["worktrees"] = [WORKTREES_FACTORY]

    for key, store in stores.items():
        entrypoint, domains = STORE_LAYOUT[key]
        store.update(
            authority_domains=domains,
            composition_entrypoint=entrypoint,
            composition_distribution=owners[entrypoint],
            definition_sources=[
                {"path": path, "distribution": owners[path]} for path in sources[key]
            ],
            version_representation=(
                "schema_version"
                if store["schema_version"] is not None
                else "format_id_only"
            ),
        )

    normal_relationships = [
        {
            **rel,
            "source_store": "normal." + rel["source_store"],
            "target_store": "normal." + rel["target_store"],
        }
        for rel in normal["logical_dependencies"]
    ]
    return {
        "inventory_schema_version": 1,
        "profile": "all",
        "authority_domains": {
            domain: {"independent_distribution": distribution}
            for domain, distribution in DOMAIN_DISTRIBUTIONS.items()
        },
        "configurations": {
            "normal": {
                "kind": "normal-cli-schema-family",
                "stores": ["normal.core", "normal.operational", "normal.search"],
            },
            "p1": {
                "kind": "opt-in-factory-schema-family",
                "stores": ["p1." + role for role in p1_schema.STORES],
            },
            "access": {"kind": "independent-store", "stores": ["access"]},
            "filesystem": {"kind": "independent-store", "stores": ["filesystem"]},
            "worktrees": {"kind": "independent-store", "stores": ["worktrees"]},
            "local": {
                "kind": "optional-composition",
                "stores": ["filesystem", "worktrees"],
                "owned_stores": [],
            },
        },
        "distributions": distributions,
        "source_ownership": owners,
        "stores": stores,
        "normal_logical_dependencies": normal_relationships,
        "optional_references": [
            {
                "id": "worktrees.filesystem-scan",
                "kind": "qualified-external-reference",
                "source_store": "worktrees",
                "source_table": "scan_references",
                "source_columns": ["filesystem_namespace_uuid", "filesystem_scan_uuid"],
                "target_store": "filesystem",
                "target_table": "scans",
                "target_columns": ["namespace_uuid", "scan_uuid"],
                "missing_target": "unresolved",
                "physical_foreign_key": False,
                "contract": "docs/architecture/local-catalog-contract.md",
            },
            {
                "id": "worktrees.repository-claim",
                "kind": "external-domain-claim",
                "source_store": "worktrees",
                "source_table": "repository_links",
                "source_columns": ["repository_uuid"],
                "target_domain": "core",
                "missing_target": "unresolved",
                "physical_foreign_key": False,
                "contract": "docs/adr/0039-independent-filesystem-and-worktree-catalogs.md",
            },
        ],
        "scope": {
            "instances_read": 0,
            "ownership_basis": "declared-wheel-source-layout-not-installed-artifact",
            "configurations_are_required_startup_sets": False,
            "unformalized": [
                "SQL CHECK and trigger semantics, including NULL",
                "Python admission, validation and recovery behavior",
                "operation prerequisites and state transitions",
                "runtime-created virtual tables and retained instance contents",
                "per-table semantic authority within the mixed normal catalog",
            ],
            "connection_details": "extraction settings and registered UDFs only; not persistent-DB runtime requirements",
        },
        "summary": {
            "store_formats": len(stores),
            "authority_domains": len(DOMAIN_DISTRIBUTIONS),
            "distributions": len(distributions),
            "table_definitions": sum(store["table_count"] for store in stores.values()),
        },
    }


def validate_catalog(catalog: dict) -> list[str]:
    """Check structural coverage. Never equate absent instance data with corruption."""
    errors = []
    stores = catalog.get("stores", {})
    if catalog.get("profile") != "all" or catalog.get("inventory_schema_version") != 1:
        errors.append("unsupported catalog profile/version")
    if set(stores) != set(STORE_LAYOUT):
        errors.append("schema coverage differs from registered formats")
    domains = catalog.get("authority_domains", {})
    if set(domains) != set(DOMAIN_DISTRIBUTIONS):
        errors.append("authority-domain coverage differs")
    for domain, distribution in DOMAIN_DISTRIBUTIONS.items():
        if domains.get(domain, {}).get("independent_distribution") != distribution:
            errors.append(domain + ": independent distribution mismatch")
    distributions, owners = workspace_sources()
    if (
        catalog.get("distributions") != distributions
        or catalog.get("source_ownership") != owners
    ):
        errors.append(
            "distribution/source ownership differs from the selected workspace"
        )
    for key, store in stores.items():
        if key not in STORE_LAYOUT:
            continue
        entrypoint, expected_domains = STORE_LAYOUT[key]
        if (
            store.get("composition_entrypoint") != entrypoint
            or store.get("composition_distribution") != owners.get(entrypoint)
            or store.get("authority_domains") != expected_domains
        ):
            errors.append(key + ": composition ownership/domain mismatch")
        definitions = store.get("definition_sources", [])
        if not definitions or entrypoint not in [item["path"] for item in definitions]:
            errors.append(key + ": missing composition source")
        for item in definitions:
            if owners.get(item["path"]) != item["distribution"]:
                errors.append(key + ": unowned definition source " + item["path"])
        tables = store.get("tables", {})
        if not tables or store.get("table_count") != len(tables):
            errors.append(key + ": missing tables/count mismatch")
        represented = {
            (kind, name)
            for kind, field in (
                ("table", "tables"),
                ("view", "views"),
                ("index", "explicit_indexes"),
                ("trigger", "triggers"),
            )
            for name in store.get(field, {})
        }
        extracted = {
            (item["type"], item["name"]) for item in store.get("extracted_objects", [])
        }
        if not extracted or represented != extracted:
            errors.append(key + ": schema object coverage differs from extraction")
        for name, table in tables.items():
            columns = {col["name"] for col in table["columns"]}
            if len(table["columns"]) != table.get("column_count") or len(
                columns
            ) != len(table["columns"]):
                errors.append(f"{key}.{name}: column coverage differs")
            if table["store"] != key or not set(table["primary_key"]) <= columns:
                errors.append(f"{key}.{name}: invalid table scope/primary key")
            for fk in table["foreign_keys"]:
                target = tables.get(fk["target_table"])
                # SQLite permits omitted target column names, meaning target PK.
                target_columns = fk["to_columns"]
                if target and all(col is None for col in target_columns):
                    target_columns = target["primary_key"]
                if (
                    not target
                    or not set(fk["from_columns"]) <= columns
                    or len(fk["from_columns"]) != len(target_columns)
                    or not set(target_columns)
                    <= {col["name"] for col in target["columns"]}
                ):
                    errors.append(f"{key}.{name}: invalid physical FK endpoint")
    for name, config in catalog.get("configurations", {}).items():
        if not set(config["stores"]) <= set(stores):
            errors.append(name + ": unknown configured format")
    if not catalog.get("configurations"):
        errors.append("configuration coverage missing")
    else:
        expected_configs = {
            "normal": [key for key in STORE_LAYOUT if key.startswith("normal.")],
            "p1": [key for key in STORE_LAYOUT if key.startswith("p1.")],
            **{key: [key] for key in ("access", "filesystem", "worktrees")},
            "local": ["filesystem", "worktrees"],
        }
        if {
            name: config["stores"] for name, config in catalog["configurations"].items()
        } != expected_configs:
            errors.append("configuration coverage differs")
        if catalog["configurations"].get("local", {}).get("owned_stores") != []:
            errors.append("Local composition must not own a store")
    if len(catalog.get("optional_references", [])) != 2 or {
        ref["id"] for ref in catalog.get("optional_references", [])
    } != {
        "worktrees.filesystem-scan",
        "worktrees.repository-claim",
    }:
        errors.append("optional-reference coverage differs")
    for ref in catalog.get("optional_references", []):
        source = (
            stores.get(ref["source_store"], {})
            .get("tables", {})
            .get(ref["source_table"], {})
        )
        if not set(ref["source_columns"]) <= {
            c["name"] for c in source.get("columns", [])
        }:
            errors.append(ref["id"] + ": missing reference source")
        if (
            ref.get("physical_foreign_key") is not False
            or ref.get("missing_target") != "unresolved"
        ):
            errors.append(ref["id"] + ": optional reference misclassified")
        if "target_store" in ref:
            target = (
                stores.get(ref["target_store"], {})
                .get("tables", {})
                .get(ref["target_table"], {})
            )
            if ref["target_columns"] != target.get("primary_key") or len(
                ref["source_columns"]
            ) != len(ref["target_columns"]):
                errors.append(ref["id"] + ": incomplete qualified reference")
    return errors
