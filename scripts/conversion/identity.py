"""P3B identity recipes: immutable source facts, bounded atomic output and proofs.

These helpers are synthetic component boundaries. Operational entry goes through
identity_phase and the guarded worker. No recipe reads a URL, mount or cache.
"""

import json
import re
import uuid
from collections import Counter
from datetime import datetime
from urllib.parse import urlsplit

from scripts.schema_audit import identifier
from scripts.schema_contract import archive_bytes, row_digest, tagged_key

from . import archive, batch, mapping
from .common import ConversionError, canonical, digest, now, strict_json

VERSION = "P3B identity/1"
RECIPES = (
    "service_instances",
    "sources",
    "repositories",
    "repository_bindings",
    "repository_endpoints",
    "repository_name_assertions",
    "source_repositories",
    "repository_preferences",
)
TABLES = RECIPES[:-1]
SOURCE_TABLES = {
    "repository_name_assertions": "repository_names",
    "repository_preferences": "repositories",
}
KEYS = {
    "repository_name_assertions": ("repo_id", "name"),
    "source_repositories": ("source_id", "repo_id"),
}
COLUMNS = {
    "service_instances": (
        "id",
        "kind",
        "name",
        "web_base_url",
        "api_base_url",
        "metadata",
        "created_at",
    ),
    "sources": ("id", "instance_id", "discovery_kind", "name", "settings"),
    "repositories": (
        "id",
        "name",
        "preferred_endpoint_id",
        "current_snapshot_id",
        "metadata",
    ),
    "repository_bindings": (
        "id",
        "repo_id",
        "instance_id",
        "provider_repo_id",
        "metadata",
        "created_at",
    ),
    "repository_endpoints": (
        "id",
        "repo_id",
        "url",
        "transport",
        "label",
        "metadata",
        "created_at",
    ),
    "repository_name_assertions": ("repo_id", "name", "observed_at"),
    "source_repositories": ("source_id", "repo_id", "first_seen", "last_seen"),
}


def identity_contract():
    """Executable phase specification, pinned before phase initialization."""
    source_keys = {
        "repository_bindings": ["repo_id", "instance_id"],
        "repository_name_assertions": ["repo_id", "name"],
        "source_repositories": ["source_id", "repo_id"],
    }
    dependencies = {
        "service_instances": [],
        "sources": ["service_instances"],
        "repositories": [],
        "repository_bindings": ["repositories", "service_instances"],
        "repository_endpoints": ["repositories"],
        "repository_name_assertions": ["repositories"],
        "source_repositories": [
            "sources",
            "repositories",
            "repository_bindings for github_inventory",
        ],
        "repository_preferences": ["repositories", "repository_endpoints"],
    }
    transforms = {
        "service_instances": "preserve id/kind/name/base URLs/exact object metadata/nullable created_at; reject duplicate names and unsupported kinds",
        "sources": "preserve id/instance/name/exact object settings; local-git->manual_git, github->github_inventory; github requires one valid github instance",
        "repositories": "preserve id/name/exact object metadata; both pointers NULL; verify and reuse existing P2 representative map only if original P2 projection succeeded",
        "repository_bindings": "preserve repo/instance/native ID/exact object metadata/nullable created_at; allocate UUIDv4 once against full archived composite source key; reject conflicting (instance,native) owners; NULL native permitted",
        "repository_endpoints": "preserve id/repo/URL/transport/nullable label/exact object metadata/nullable created_at; no path/URL rewriting; is_preferred remains archived evidence for later pointer recipe",
        "repository_name_assertions": "copy repository_names repo/name/nullable observed_at exactly; do not fabricate historical names or timestamps",
        "source_repositories": "preserve source/repo and exact nullable first_seen/last_seen bounds; strict RFC3339 ordering and target julianday representability; settings.repo_id must identify same owner; github membership requires exact valid repo/instance binding",
        "repository_preferences": "NULL->one eligible endpoint ID with source is_preferred=1, exact same repository and exact legacy repository.url; no preference/ambiguity stays NULL with diagnostic",
    }
    diagnostics = {
        "service_instances": ["INSTANCE_NAME_CONFLICT", "UNKNOWN_KIND", "INVALID_TIME"],
        "sources": [
            "MISSING_REFERENCE",
            "UNSAFE_DEPENDENCY",
            "UNKNOWN_KIND",
            "MISSING_INSTANCE",
            "INSTANCE_KIND_CONFLICT",
        ],
        "repositories": [
            "LEGACY_MEMBERSHIP_MISSING",
            "LEGACY_BINDING_MISSING",
            "LEGACY_NATIVE_CONFLICT",
            "LEGACY_NATIVE_UNRESOLVED",
            "LEGACY_HOST_CONFLICT",
            "LEGACY_HOST_UNRESOLVED",
            "MISSING_REFERENCE",
            "UNSAFE_DEPENDENCY",
        ],
        "repository_bindings": [
            "NATIVE_CONFLICT",
            "MISSING_REFERENCE",
            "UNSAFE_DEPENDENCY",
            "INVALID_TIME",
        ],
        "repository_endpoints": [
            "ENDPOINT_CONFLICT",
            "UNKNOWN_KIND",
            "INVALID_PREFERENCE",
            "MISSING_REFERENCE",
            "UNSAFE_DEPENDENCY",
            "INVALID_TIME",
        ],
        "repository_name_assertions": [
            "MISSING_REFERENCE",
            "UNSAFE_DEPENDENCY",
            "INVALID_TIME",
        ],
        "source_repositories": [
            "SOURCE_OWNER_CONFLICT",
            "MISSING_REFERENCE",
            "UNSAFE_DEPENDENCY",
            "INVALID_TIME",
            "REVERSED_BOUNDS",
        ],
        "repository_preferences": [
            "PREFERENCE_MISSING",
            "PREFERENCE_AMBIGUOUS",
            "UNSAFE_PREFERENCE",
            "ENDPOINT_OWNER_CONFLICT",
            "LEGACY_URL_CONFLICT",
        ],
    }
    return {
        "protocol": "p3b-identity/1",
        "recipe_version": VERSION,
        "implementation": "scripts.conversion.identity",
        "recipes": [
            {
                "recipe": recipe,
                "source_table": SOURCE_TABLES.get(recipe, recipe),
                "source_key": source_keys.get(recipe, ["id"]),
                "target_table": "repositories"
                if recipe == "repository_preferences"
                else recipe,
                "target_key": list(KEYS.get(recipe, ("id",))),
                "dependencies": [
                    "verified complete typed archive",
                    *dependencies[recipe],
                ],
                "transformation_and_lookup": transforms[recipe],
                "operation": "source_owned_null_to_preferred"
                if recipe == "repository_preferences"
                else "preserve_or_allocate_identity",
                "ownership": "source record/key; attributed atomic P3B batch",
                "diagnostics": [
                    "IDENTITY_" + code
                    for code in [
                        "INVALID_TYPE",
                        "MALFORMED_TEXT",
                        "INVALID_KEY",
                        "INVALID_JSON",
                        *diagnostics[recipe],
                    ]
                ],
                "diagnostic_location": "legacy record_id + original column + recipe; archived exact typed value",
                "on_invalid": "archive_only and blocking diagnostic; preference missing/ambiguous partial; legacy conflicts retain safe repository projection",
                "validation": "independent source-derived exact values/keys/relations/decisions; complete table and map/diagnostic ownership; committed output proof plus target FK/CHECK/trigger enforcement",
            }
            for recipe in RECIPES
        ],
        "batch": "domain rows/maps/diagnostics/source decisions/output proof/progress commit atomically",
        "allocation": "UUIDv4 only for archived repository_bindings composite (repo_id,instance_id); committed typed map is stable within workspace",
        "representatives": "verified exact P2 IDs/bytes are reused; original proof retains NULL pointers; source-derived preferred pointer has separate P3B proof",
        "metadata": "strict JSON object; exact source text including spacing; malformed/null required metadata omitted and archived with blocking diagnostic",
        "timestamps": "nullable timezone-aware RFC3339, microsecond precision at most; exact source spelling; membership min/max bounds are aggregates",
        "legacy": "normalized v2 bindings/endpoints/membership authoritative; legacy repository columns remain archived assertions; GitHub native/host contradictions block readiness; local source IDs are not native provider IDs; nonempty legacy GitHub assertions without normalized native/host evidence remain partial and attributed",
        "preferences": "only one eligible source endpoint with is_preferred=1, same repo, exact legacy URL; otherwise NULL with diagnostic",
        "pointers": "current_snapshot_id and all publication/current pointers remain NULL; lifecycle building",
        "dependencies": "missing/unsafe instance/repository/source/binding omits dependent row deterministically",
        "verification": "recompute every processed source decision and output relation independently of mutable stored output hashes; reject unattributed output",
        "inventory_observations": "deferred exact inventory_runs typed archive; aggregate membership does not require fabricated individual observations",
    }


REVIEWED_BASE_CONTRACT_SHA256 = (
    "be7c782dd31e55cff7ab006b5076b79febbcfe74c771aa668b058f212c98d141"
)


def validate_contract(spec):
    original = {key: value for key, value in spec.items() if key != "p3b_identity"}
    if (
        spec.get("p3b_identity") != identity_contract()
        or digest(canonical(original).encode()) != REVIEWED_BASE_CONTRACT_SHA256
    ):
        raise ConversionError("INVALID_P3B_IDENTITY_CONTRACT")


def no_fault(point, **context):
    pass


class Invalid(ValueError):
    def __init__(self, code, column):
        self.code, self.column = code, column


def text(record, column, *, nullable=False, nonempty=False, encoding="UTF-8"):
    kind, raw = record.value(column)
    if kind == "null" and nullable:
        return None
    if kind != "text":
        raise Invalid("IDENTITY_INVALID_TYPE", column)
    try:
        value = raw.decode(encoding)
    except UnicodeError:
        raise Invalid("IDENTITY_MALFORMED_TEXT", column) from None
    if nonempty and not value.strip():
        raise Invalid("IDENTITY_INVALID_KEY", column)
    return value


def instant(value):
    if not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])",
        value,
    ):
        raise ValueError()
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError()
    return parsed


class Context:
    """Small schema cache; source lookups do not materialize an identity graph."""

    def __init__(self, db, src, run, encoding="UTF-8", *, verifying=False):
        self.db, self.src, self.run = db, src, run
        self.encoding, self.verifying = encoding, verifying
        self.schemas = {}
        self.parent_maps = any(
            strict_json(parent[0]).get("map_repositories", False)
            for parent in db.execute(
                "SELECT manifest FROM conversion_runs WHERE parser_version='p2-archive/1'"
            )
        )

    def t(self, record, column, **options):
        return text(record, column, encoding=self.encoding, **options)

    def metadata(self, record, column="metadata"):
        value = self.t(record, column)
        try:
            if not isinstance(strict_json(value), dict):
                raise ValueError()
        except ValueError:
            raise Invalid("IDENTITY_INVALID_JSON", column) from None
        return value

    def timestamp(self, record, column):
        value = self.t(record, column, nullable=True)
        if value is not None:
            try:
                instant(value)
            except ValueError:
                raise Invalid("IDENTITY_INVALID_TIME", column) from None
        return value

    def schema(self, table):
        if table not in self.schemas:
            columns = list(self.src.execute(f"PRAGMA table_xinfo({identifier(table)})"))
            primary = sorted((c for c in columns if c["pk"]), key=lambda c: c["pk"])
            expressions = []
            for c in columns:
                name = identifier(c["name"])
                expressions += [
                    f"typeof({name})",
                    f"CASE WHEN typeof({name}) IN ('text','blob') THEN CAST({name} AS BLOB) ELSE {name} END",
                ]
            self.schemas[table] = columns, primary, ",".join(expressions)
        return self.schemas[table]

    def lookup(self, table, *values):
        columns, primary, expressions = self.schema(table)
        predicate = " AND ".join(f"{identifier(c['name'])}=?" for c in primary)
        row = self.src.execute(
            f"SELECT {expressions} FROM {identifier(table)} WHERE {predicate}", values
        ).fetchone()
        if row is None:
            return None
        raw = [(c["name"], row[i * 2], row[i * 2 + 1]) for i, c in enumerate(columns)]
        by_name = {name: (kind, value) for name, kind, value in raw}
        return archive.Record(
            table,
            tagged_key([by_name[c["name"]] for c in primary]),
            row_digest(raw),
            tuple(
                (name, kind, archive_bytes(kind, value)) for name, kind, value in raw
            ),
        )

    def require(self, table, *values):
        record = self.lookup(table, *values)
        if record is None:
            raise Invalid("IDENTITY_MISSING_REFERENCE", table)
        try:
            self.project(table, record, allocate=False)
        except Invalid:
            raise Invalid("IDENTITY_UNSAFE_DEPENDENCY", table) from None
        return record

    def record_id(self, record):
        saved = self.db.execute(
            "SELECT id,row_sha256 FROM legacy_records WHERE source_id=? AND source_table=? AND source_key=?",
            (self.run["source_id"], record.table, record.key),
        ).fetchone()
        if saved is None or saved["row_sha256"] != record.row_sha256:
            raise ConversionError("ARCHIVE_SOURCE_MISMATCH")
        return saved["id"]

    def binding_id(self, record):
        record_id = self.record_id(record)
        key = mapping.lookup(self.db, record_id, "repository_bindings")
        if key is None:
            if self.verifying:
                raise ConversionError("IDENTITY_MAPPING_MISSING")
            return str(uuid.uuid4())
        elements = archive.decode_key(key)
        if len(elements) != 1 or elements[0][0] != "text":
            raise ConversionError("IDENTITY_MAPPING_MISMATCH")
        try:
            value = elements[0][1].decode("utf-8")
            parsed = uuid.UUID(value)
            if str(parsed) != value or parsed.version != 4:
                raise ValueError()
            return value
        except (ValueError, UnicodeError):
            raise ConversionError("IDENTITY_MAPPING_MISMATCH") from None

    def project(self, recipe, record, *, allocate=True):
        t = self.t
        if recipe == "service_instances":
            ident, kind = t(record, "id", nonempty=True), t(record, "kind")
            if kind not in (
                "github",
                "gitlab",
                "gitea",
                "forgejo",
                "gitolite",
                "git",
                "other",
            ):
                raise Invalid("IDENTITY_UNKNOWN_KIND", "kind")
            name = t(record, "name", nonempty=True)
            if (
                self.src.execute(
                    "SELECT count(*) FROM service_instances WHERE name=?", (name,)
                ).fetchone()[0]
                != 1
            ):
                raise Invalid("IDENTITY_INSTANCE_NAME_CONFLICT", "name")
            return [
                ident,
                kind,
                name,
                t(record, "web_base_url", nullable=True),
                t(record, "api_base_url", nullable=True),
                self.metadata(record),
                self.timestamp(record, "created_at"),
            ]
        if recipe == "sources":
            ident, instance = (
                t(record, "id", nonempty=True),
                t(record, "instance_id", nullable=True, nonempty=True),
            )
            kind = t(record, "kind")
            if kind not in ("local-git", "github"):
                raise Invalid("IDENTITY_UNKNOWN_KIND", "kind")
            if instance is not None:
                owner = self.require("service_instances", instance)
                if kind == "github" and t(owner, "kind") != "github":
                    raise Invalid("IDENTITY_INSTANCE_KIND_CONFLICT", "instance_id")
            elif kind == "github":
                raise Invalid("IDENTITY_MISSING_INSTANCE", "instance_id")
            return [
                ident,
                instance,
                {"local-git": "manual_git", "github": "github_inventory"}[kind],
                t(record, "name"),
                self.metadata(record, "settings"),
            ]
        if recipe == "repositories":
            return [
                t(record, "id", nonempty=True),
                t(record, "name"),
                None,
                None,
                self.metadata(record),
            ]
        if recipe == "repository_bindings":
            repo, instance = (
                t(record, "repo_id", nonempty=True),
                t(record, "instance_id", nonempty=True),
            )
            self.require("repositories", repo)
            self.require("service_instances", instance)
            native = t(record, "provider_repo_id", nullable=True, nonempty=True)
            if (
                native is not None
                and self.src.execute(
                    "SELECT count(*) FROM repository_bindings WHERE instance_id=? AND provider_repo_id=?",
                    (instance, native),
                ).fetchone()[0]
                != 1
            ):
                raise Invalid("IDENTITY_NATIVE_CONFLICT", "provider_repo_id")
            return [
                self.binding_id(record) if allocate else None,
                repo,
                instance,
                native,
                self.metadata(record),
                self.timestamp(record, "created_at"),
            ]
        if recipe == "repository_endpoints":
            repo = t(record, "repo_id", nonempty=True)
            self.require("repositories", repo)
            transport = t(record, "transport")
            if transport not in ("file", "https", "ssh", "other"):
                raise Invalid("IDENTITY_UNKNOWN_KIND", "transport")
            preferred_kind, preferred_raw = record.value("is_preferred")
            if preferred_kind != "integer" or preferred_raw not in (b"0", b"1"):
                raise Invalid("IDENTITY_INVALID_PREFERENCE", "is_preferred")
            url = t(record, "url", nonempty=True)
            if (
                self.src.execute(
                    "SELECT count(*) FROM repository_endpoints WHERE repo_id=? AND url=?",
                    (repo, url),
                ).fetchone()[0]
                != 1
            ):
                raise Invalid("IDENTITY_ENDPOINT_CONFLICT", "url")
            return [
                t(record, "id", nonempty=True),
                repo,
                url,
                transport,
                t(record, "label", nullable=True),
                self.metadata(record),
                self.timestamp(record, "created_at"),
            ]
        if recipe == "repository_name_assertions":
            repo = t(record, "repo_id", nonempty=True)
            self.require("repositories", repo)
            return [repo, t(record, "name"), self.timestamp(record, "observed_at")]
        if recipe == "source_repositories":
            source, repo = (
                t(record, "source_id", nonempty=True),
                t(record, "repo_id", nonempty=True),
            )
            discovery = self.require("sources", source)
            self.require("repositories", repo)
            settings = strict_json(t(discovery, "settings"))
            if settings.get("repo_id") is not None and settings["repo_id"] != repo:
                raise Invalid("IDENTITY_SOURCE_OWNER_CONFLICT", "source_id")
            instance = t(discovery, "instance_id", nullable=True)
            if t(discovery, "kind") == "github":
                self.require("repository_bindings", repo, instance)
            first, last = (
                self.timestamp(record, "first_seen"),
                self.timestamp(record, "last_seen"),
            )
            for column, value in (("first_seen", first), ("last_seen", last)):
                if (
                    value is not None
                    and self.db.execute("SELECT julianday(?)", (value,)).fetchone()[0]
                    is None
                ):
                    raise Invalid("IDENTITY_INVALID_TIME", column)
            if (
                first is not None
                and last is not None
                and instant(first) > instant(last)
            ):
                raise Invalid("IDENTITY_REVERSED_BOUNDS", "last_seen")
            return [source, repo, first, last]
        raise ConversionError("UNKNOWN_IDENTITY_RECIPE")

    def legacy_issues(self, record):
        """v2 normalized facts win; contradictory old projections remain explicit."""
        issues = []
        try:
            repo, source_id = (
                self.t(record, "id", nonempty=True),
                self.t(record, "source_id", nonempty=True),
            )
            discovery = self.require("sources", source_id)
            if self.lookup("source_repositories", source_id, repo) is None:
                issues.append(
                    ("IDENTITY_LEGACY_MEMBERSHIP_MISSING", "blocking", "source_id")
                )
            instance = self.t(discovery, "instance_id", nullable=True)
            if instance is not None and self.t(discovery, "kind") == "github":
                binding = self.lookup("repository_bindings", repo, instance)
                if binding is None:
                    issues.append(
                        (
                            "IDENTITY_LEGACY_BINDING_MISSING",
                            "blocking",
                            "provider_repo_id",
                        )
                    )
                else:
                    native = self.t(binding, "provider_repo_id", nullable=True)
                    legacy = self.t(record, "provider_repo_id")
                    if native is None and legacy:
                        issues.append(
                            (
                                "IDENTITY_LEGACY_NATIVE_UNRESOLVED",
                                "partial",
                                "provider_repo_id",
                            )
                        )
                    if native is not None and legacy and legacy != native:
                        issues.append(
                            (
                                "IDENTITY_LEGACY_NATIVE_CONFLICT",
                                "blocking",
                                "provider_repo_id",
                            )
                        )
                owner = self.lookup("service_instances", instance)
                base = self.t(owner, "web_base_url", nullable=True) or self.t(
                    owner, "api_base_url", nullable=True
                )
                host = None
                if base:
                    try:
                        host = urlsplit(base).hostname
                    except ValueError:
                        pass
                legacy_host = self.t(record, "provider_host")
                if legacy_host and host is None:
                    issues.append(
                        ("IDENTITY_LEGACY_HOST_UNRESOLVED", "partial", "provider_host")
                    )
                elif host is not None and legacy_host != host:
                    issues.append(
                        ("IDENTITY_LEGACY_HOST_CONFLICT", "blocking", "provider_host")
                    )
        except Invalid as exc:
            issues.append((exc.code, "blocking", exc.column))
        return issues

    def preference(self, record):
        base = self.project("repositories", record)
        repo = base[0]
        preferred = []
        for (ident,) in self.src.execute(
            "SELECT CAST(id AS BLOB) FROM repository_endpoints WHERE repo_id=? AND is_preferred=1 ORDER BY id",
            (repo,),
        ):
            try:
                endpoint = self.lookup(
                    "repository_endpoints", ident.decode(self.encoding)
                )
                row = self.project("repository_endpoints", endpoint)
                if row[1] != repo:
                    raise Invalid("IDENTITY_ENDPOINT_OWNER_CONFLICT", "repo_id")
                preferred.append(row)
            except (Invalid, UnicodeError):
                raise Invalid(
                    "IDENTITY_UNSAFE_PREFERENCE", "preferred_endpoint_id"
                ) from None
        if len(preferred) != 1:
            raise Invalid(
                "IDENTITY_PREFERENCE_AMBIGUOUS"
                if preferred
                else "IDENTITY_PREFERENCE_MISSING",
                "preferred_endpoint_id",
            )
        if self.t(record, "url") != preferred[0][2]:
            raise Invalid("IDENTITY_LEGACY_URL_CONFLICT", "url")
        base[2] = preferred[0][0]
        return base


def batches(db, src, run, receipt, batch_size):
    if batch_size < 1:
        raise ConversionError("INVALID_BATCH_SIZE")
    for recipe in RECIPES:
        index, pending = 0, []
        for record in archive.rows(src, SOURCE_TABLES.get(recipe, recipe)):
            pending.append(record)
            if len(pending) == batch_size:
                records = tuple(pending)
                yield recipe, index, records, input_digest(run, recipe, index, records)
                index, pending = index + 1, []
        if pending or index == 0:
            records = tuple(pending)
            yield recipe, index, records, input_digest(run, recipe, index, records)


def input_digest(run, recipe, index, records):
    return digest(
        canonical(
            {
                "protocol": VERSION,
                "source_id": run["source_id"],
                "recipe": recipe,
                "index": index,
                "records": [
                    {"key": r.key.hex(), "sha256": r.row_sha256.hex()} for r in records
                ],
            }
        ).encode()
    )


def target_key(table, row):
    columns = COLUMNS[table]
    return tagged_key(
        [
            ("text", row[columns.index(key)].encode("utf-8"))
            for key in KEYS.get(table, ("id",))
        ]
    )


def prepare(db, src, run, recipe, index, records, *, encoding="UTF-8", verifying=False):
    context = Context(db, src, run, encoding, verifying=verifying)
    output = {"operations": [], "mappings": [], "diagnostics": [], "decisions": []}
    for record in records:
        record_id = context.record_id(record)
        issues, row = [], None
        try:
            row = (
                context.preference(record)
                if recipe == "repository_preferences"
                else context.project(recipe, record)
            )
        except Invalid as exc:
            issues.append(
                (
                    exc.code,
                    "partial"
                    if exc.code
                    in ("IDENTITY_PREFERENCE_MISSING", "IDENTITY_PREFERENCE_AMBIGUOUS")
                    else "blocking",
                    exc.column,
                )
            )
        if recipe == "repositories":
            issues.extend(context.legacy_issues(record))
        if row is not None:
            table = "repositories" if recipe == "repository_preferences" else recipe
            operation = "preference" if recipe == "repository_preferences" else "insert"
            known = mapping.lookup(db, record_id, table)
            key = target_key(table, row)
            parent_projected = False
            if recipe == "repositories" and context.parent_maps:
                try:
                    mapping.repository_projection(record)
                    parent_projected = True
                except ConversionError:
                    pass
            if recipe == "repositories" and parent_projected:
                if known != key:
                    raise ConversionError("IDENTITY_MAPPING_MISMATCH")
                operation = "reuse"
            output["operations"].append(
                {
                    "record_id": record_id,
                    "table": table,
                    "operation": operation,
                    "row": row,
                }
            )
            if recipe != "repository_preferences" and operation != "reuse":
                output["mappings"].append(
                    [
                        record_id,
                        table,
                        key.hex(),
                        "identity",
                        f"{VERSION}; {recipe}; exact archived source key",
                    ]
                )
        output["decisions"].append(
            {
                "record_id": record_id,
                "source_key": record.key.hex(),
                "source_sha256": record.row_sha256.hex(),
                "disposition": "normalized" if row is not None else "archive_only",
            }
        )
        output["diagnostics"].extend(
            [
                "I31",
                code,
                severity,
                canonical({"record_id": record_id, "column": column, "recipe": recipe}),
            ]
            for code, severity, column in sorted(set(issues))
        )
    return output


def commit(db, run, recipe, index, input_sha256, output, fault=no_fault):
    owners = list(
        db.execute(
            "SELECT * FROM conversion_runs WHERE parser_version='p3b-identity/1'"
        )
    )
    if len(owners) != 1 or owners[0]["id"] != run["id"]:
        raise ConversionError("P3B_OWNER_REQUIRED")
    material = {**output, "mapping_ids": [], "diagnostic_ids": []}
    mapping_id, diagnostic_id = (
        batch.next_id(db, "id_mappings"),
        batch.next_id(db, "validation_results"),
    )
    material["mapping_ids"] = list(
        range(mapping_id, mapping_id + len(output["mappings"]))
    )
    material["diagnostic_ids"] = list(
        range(diagnostic_id, diagnostic_id + len(output["diagnostics"]))
    )
    committed_at = now()
    material["observed_at"] = committed_at
    proof = canonical(
        {
            "protocol": VERSION,
            "recipe": recipe,
            "index": index,
            "output": material,
            "output_sha256": batch.proof_digest(material),
        }
    )
    fault("before_insert", table=recipe, index=index)
    try:
        db.execute("BEGIN IMMEDIATE")
        for op in output["operations"]:
            table, row = op["table"], op["row"]
            if op["operation"] == "insert":
                db.execute(
                    f"INSERT INTO {table} VALUES({','.join('?' for _ in row)})", row
                )
            elif op["operation"] == "preference":
                before = db.execute(
                    "SELECT * FROM repositories WHERE id=?", (row[0],)
                ).fetchone()
                if before is None or list(before) != [
                    row[0],
                    row[1],
                    None,
                    None,
                    row[4],
                ]:
                    raise ConversionError("IDENTITY_BEFORE_IMAGE_MISMATCH")
                db.execute(
                    "UPDATE repositories SET preferred_endpoint_id=? WHERE id=?",
                    (row[2], row[0]),
                )
            elif op["operation"] == "reuse":
                if (
                    list(
                        db.execute(
                            "SELECT * FROM repositories WHERE id=?", (row[0],)
                        ).fetchone()
                        or ()
                    )
                    != row
                ):
                    raise ConversionError("IDENTITY_BEFORE_IMAGE_MISMATCH")
            else:
                raise ConversionError("INVALID_IDENTITY_OPERATION")
        fault("after_data", table=recipe, index=index)
        for ident, mapped in zip(
            material["mapping_ids"], output["mappings"], strict=True
        ):
            record_id, table, key, relation, reason = mapped
            mapping.persist(db, record_id, table, bytes.fromhex(key), reason)
            actual = db.execute(
                "SELECT id FROM id_mappings WHERE record_id=? AND target_table=? AND relation=?",
                (record_id, table, relation),
            ).fetchone()
            if actual is None or actual[0] != ident:
                raise ConversionError("IDENTITY_MAPPING_ALLOCATION_MISMATCH")
        fault("after_mapping", table=recipe, index=index)
        for ident, diagnostic in zip(
            material["diagnostic_ids"], output["diagnostics"], strict=True
        ):
            invariant, code, severity, details = diagnostic
            db.execute(
                "INSERT INTO validation_results VALUES(?,?,?,?,?,?,?)",
                (ident, run["id"], invariant, code, severity, committed_at, details),
            )
        db.execute(
            "INSERT INTO conversion_batches VALUES(?,?,?,?,?,?)",
            (
                batch.next_id(db, "conversion_batches"),
                run["id"],
                recipe,
                bytes.fromhex(input_sha256),
                committed_at,
                proof,
            ),
        )
        db.execute(
            "UPDATE conversion_runs SET state='building',ended_at=NULL WHERE id=?",
            (run["id"],),
        )
        fault("before_commit", table=recipe, index=index)
        db.execute("COMMIT")
    except BaseException:
        if db.in_transaction:
            db.rollback()
        raise
    fault("after_commit", table=recipe, index=index)


def _find(db, table, row):
    columns = COLUMNS[table]
    keys = KEYS.get(table, ("id",))
    return db.execute(
        f"SELECT * FROM {table} WHERE " + " AND ".join(f"{key}=?" for key in keys),
        [row[columns.index(key)] for key in keys],
    ).fetchone()


def validate_output(db, src, run, receipt, *, require_complete=False, fault=no_fault):
    """Re-run recipes from immutable source; hashes alone cannot prove values."""
    previous = db.execute(
        "SELECT * FROM conversion_batches WHERE run_id=? ORDER BY id", (run["id"],)
    )
    expected = batches(db, src, run, receipt, receipt["batch_size"])
    expected_rows = Counter()
    known_keys = {table: set() for table in TABLES}
    mapping_ids, diagnostic_ids = set(), set()
    count = 0
    for committed in previous:
        descriptor = next(expected, None)
        if descriptor is None:
            raise ConversionError("UNEXPECTED_COMMITTED_BATCH")
        recipe, index, records, input_sha256 = descriptor
        try:
            manifest = strict_json(committed["output_manifest"])
            saved = manifest["output"]
            if (
                set(manifest)
                != {"protocol", "recipe", "index", "output", "output_sha256"}
                or manifest["protocol"] != VERSION
                or manifest["recipe"] != recipe
                or manifest["index"] != index
                or committed["source_table"] != recipe
                or committed["input_sha256"].hex() != input_sha256
                or manifest["output_sha256"] != batch.proof_digest(saved)
            ):
                raise ValueError()
        except (KeyError, ValueError, TypeError):
            raise ConversionError("IDENTITY_BATCH_PROOF_MISMATCH") from None
        recomputed = prepare(
            db,
            src,
            run,
            recipe,
            index,
            records,
            encoding=receipt.get("encoding", "UTF-8"),
            verifying=True,
        )
        if {name: saved.get(name) for name in recomputed} != recomputed:
            raise ConversionError("IDENTITY_SOURCE_MISMATCH")
        if (
            set(saved) != {*recomputed, "mapping_ids", "diagnostic_ids", "observed_at"}
            or saved["observed_at"] != committed["committed_at"]
        ):
            raise ConversionError("IDENTITY_BATCH_PROOF_MISMATCH")
        for op in recomputed["operations"]:
            table, row = op["table"], op["row"]
            actual = _find(db, table, row)
            if actual is None:
                raise ConversionError("IDENTITY_OUTPUT_MISSING")
            value = list(actual)
            # Base repository proof retains the original NULL pointer. The
            # only permitted subsequent change is independently sourced below.
            if table == "repositories" and recipe != "repository_preferences":
                value[2] = None
            if value != row:
                raise ConversionError("IDENTITY_SOURCE_MISMATCH")
            known_keys[table].add(target_key(table, row))
        if len(saved["mapping_ids"]) != len(recomputed["mappings"]) or len(
            saved["diagnostic_ids"]
        ) != len(recomputed["diagnostics"]):
            raise ConversionError("IDENTITY_BATCH_PROOF_MISMATCH")
        for ident, mapped in zip(
            saved["mapping_ids"], recomputed["mappings"], strict=True
        ):
            if ident in mapping_ids:
                raise ConversionError("IDENTITY_MAPPING_MISMATCH")
            mapping_ids.add(ident)
            record_id, table, key, relation, reason = mapped
            actual = db.execute(
                "SELECT * FROM id_mappings WHERE id=?", (ident,)
            ).fetchone()
            if actual is None or tuple(actual) != (
                ident,
                record_id,
                table,
                bytes.fromhex(key),
                relation,
                reason,
            ):
                raise ConversionError("IDENTITY_MAPPING_MISMATCH")
        for ident, diagnostic in zip(
            saved["diagnostic_ids"], recomputed["diagnostics"], strict=True
        ):
            if ident in diagnostic_ids:
                raise ConversionError("IDENTITY_DIAGNOSTIC_MISMATCH")
            diagnostic_ids.add(ident)
            invariant, code, severity, details = diagnostic
            actual = db.execute(
                "SELECT * FROM validation_results WHERE id=?", (ident,)
            ).fetchone()
            if actual is None or tuple(actual) != (
                ident,
                run["id"],
                invariant,
                code,
                severity,
                committed["committed_at"],
                details,
            ):
                raise ConversionError("IDENTITY_DIAGNOSTIC_MISMATCH")
        count += 1
        fault("during_resume", table=recipe, index=index)
    complete = next(expected, None) is None
    if require_complete and not complete:
        raise ConversionError("IDENTITY_CONVERSION_INCOMPLETE")
    # Every preferred pointer must be owned by an already committed preference
    # batch; no early pointer publication or unrelated current pointer is valid.
    preferred_records = set()
    for committed in db.execute(
        "SELECT * FROM conversion_batches WHERE run_id=? ORDER BY id", (run["id"],)
    ):
        value = json.loads(committed["output_manifest"])
        if value["recipe"] == "repository_preferences":
            preferred_records.update(
                op["row"][0] for op in value["output"]["operations"]
            )
    parent_map_ids = set()
    parent_repo_keys = set()
    for parent_batch in db.execute(
        "SELECT output_manifest FROM conversion_batches WHERE run_id!=?", (run["id"],)
    ):
        proof = json.loads(parent_batch[0]).get("proof", {})
        parent_map_ids.update(row["key"][0] for row in proof.get("id_mappings", []))
        parent_repo_keys.update(
            tagged_key([("text", row["key"][0].encode())])
            for row in proof.get("repositories", [])
        )
    context = Context(db, src, run, receipt.get("encoding", "UTF-8"), verifying=True)
    for table in TABLES:
        actual_keys = set()
        for actual in db.execute(f"SELECT * FROM {table}"):
            row = list(actual)
            actual_keys.add(target_key(table, row))
            expected_rows[table] += 1
            if table == "repositories":
                record = context.lookup("repositories", row[0])
                if record is None:
                    raise ConversionError("IDENTITY_SOURCE_MISMATCH")
                try:
                    base = context.project("repositories", record)
                except Invalid:
                    raise ConversionError("IDENTITY_SOURCE_MISMATCH") from None
                current_base = [row[0], row[1], None, row[3], row[4]]
                if current_base != base:
                    raise ConversionError("IDENTITY_SOURCE_MISMATCH")
            if table == "repositories" and (
                row[3] is not None
                or row[2] is not None
                and row[0] not in preferred_records
            ):
                raise ConversionError("IDENTITY_UNOWNED_POINTER")
        allowed = known_keys[table] | (
            parent_repo_keys if table == "repositories" else set()
        )
        if actual_keys != allowed:
            raise ConversionError("IDENTITY_UNLEDGERED_OUTPUT")
    if {
        row[0] for row in db.execute("SELECT id FROM id_mappings")
    } != mapping_ids | parent_map_ids:
        raise ConversionError("IDENTITY_UNLEDGERED_MAPPING")
    if db.execute(
        "SELECT 1 FROM validation_results WHERE run_id NOT IN (?,?) LIMIT 1",
        (run["id"], receipt["parent"]["p2_run_id"]),
    ).fetchone():
        raise ConversionError("IDENTITY_UNLEDGERED_DIAGNOSTIC")
    if {
        row[0]
        for row in db.execute(
            "SELECT id FROM validation_results WHERE run_id=?", (run["id"],)
        )
    } != diagnostic_ids:
        raise ConversionError("IDENTITY_UNLEDGERED_DIAGNOSTIC")
    return {
        "committed_batches": count,
        "complete": complete,
        "normalized_rows": dict(expected_rows),
        "diagnostics": dict(
            db.execute(
                "SELECT severity,count(*) FROM validation_results WHERE run_id=? GROUP BY severity",
                (run["id"],),
            )
        ),
    }
