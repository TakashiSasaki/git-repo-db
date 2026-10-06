"""Source-owned identity recipes for the guarded v2 salvage importer."""

import re
import uuid
from datetime import datetime
from urllib.parse import urlsplit

from . import archive, mapping
from .common import ConversionError, canonical, strict_json
from .types import archive_bytes, identifier, row_digest, tagged_key

VERSION = "offline-v2 identity/1"
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
    "repository_name_assertions": ("repository_id", "name"),
    "source_repositories": ("source_id", "repository_id"),
    "service_instances": ("service_instance_uuidv4",),
    "sources": ("source_id",),
    "repositories": ("repository_id",),
    "repository_bindings": ("repository_binding_id",),
    "repository_endpoints": ("repository_endpoint_id",),
}
COLUMNS = {
    "service_instances": (
        "service_instance_uuidv4",
        "service_kind",
        "name",
        "web_base_url",
        "api_base_url",
        "metadata",
        "created_at",
    ),
    "sources": (
        "source_id",
        "service_instance_uuidv4",
        "discovery_kind",
        "name",
        "settings",
    ),
    "repositories": (
        "repository_id",
        "name",
        "preferred_repository_endpoint_id",
        "current_snapshot_id",
        "metadata",
    ),
    "repository_bindings": (
        "repository_binding_id",
        "repository_id",
        "service_instance_uuidv4",
        "provider_repository_id",
        "metadata",
        "created_at",
    ),
    "repository_endpoints": (
        "repository_endpoint_id",
        "repository_id",
        "url",
        "transport",
        "label",
        "metadata",
        "created_at",
    ),
    "repository_name_assertions": ("repository_id", "name", "observed_at"),
    "source_repositories": ("source_id", "repository_id", "first_seen", "last_seen"),
}


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

    def legacy_record_id(self, record):
        saved = self.db.execute(
            "SELECT legacy_record_id,row_sha256 FROM legacy_records WHERE conversion_source_id=? AND source_table=? AND source_key=?",
            (self.run["conversion_source_id"], record.table, record.key),
        ).fetchone()
        if saved is None or saved["row_sha256"] != record.row_sha256:
            raise ConversionError("ARCHIVE_SOURCE_MISMATCH")
        return saved["legacy_record_id"]

    def binding_id(self, record):
        legacy_record_id = self.legacy_record_id(record)
        key = mapping.lookup(self.db, legacy_record_id, "repository_bindings")
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
            # Never derive a service namespace from a URL/name or silently replace
            # an invalid source namespace. The original is retained in the archive.
            try:
                parsed = uuid.UUID(ident)
                if (
                    str(parsed) != ident
                    or parsed.version != 4
                    or parsed.variant != uuid.RFC_4122
                ):
                    raise ValueError()
            except ValueError:
                raise Invalid("IDENTITY_INVALID_SERVICE_UUIDV4", "id") from None
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
            settings = self.metadata(record, "settings")
            # Raw settings remain in legacy_values; current source registration
            # consumes only the catalog3 identity names in its target projection.
            for old, new in (
                ("repo_id", "repository_id"),
                ("provider_repo_id", "provider_repository_id"),
            ):
                if (
                    self.src.execute(
                        "SELECT json_type(?,?)", (settings, "$." + old)
                    ).fetchone()[0]
                    is not None
                ):
                    settings = self.src.execute(
                        "SELECT json_set(json_remove(?,?),?,json_extract(?,?))",
                        (settings, "$." + old, "$." + new, settings, "$." + old),
                    ).fetchone()[0]
            return [
                ident,
                instance,
                {"local-git": "manual_git", "github": "github_inventory"}[kind],
                t(record, "name"),
                settings,
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


def target_key(table, row):
    columns = COLUMNS[table]
    return tagged_key(
        [("text", row[columns.index(key)].encode("utf-8")) for key in KEYS[table]]
    )


def prepare(db, src, run, recipe, index, records, *, encoding="UTF-8", verifying=False):
    context = Context(db, src, run, encoding, verifying=verifying)
    output = {"operations": [], "mappings": [], "diagnostics": [], "decisions": []}
    for record in records:
        legacy_record_id = context.legacy_record_id(record)
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
            key = target_key(table, row)
            output["operations"].append(
                {
                    "legacy_record_id": legacy_record_id,
                    "table": table,
                    "operation": operation,
                    "row": row,
                }
            )
            if recipe != "repository_preferences":
                output["mappings"].append(
                    [
                        legacy_record_id,
                        table,
                        key.hex(),
                        "identity",
                        f"{VERSION}; {recipe}; exact archived source key",
                    ]
                )
        output["decisions"].append(
            {
                "legacy_record_id": legacy_record_id,
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
                canonical(
                    {
                        "legacy_record_id": legacy_record_id,
                        "column": column,
                        "recipe": recipe,
                    }
                ),
            ]
            for code, severity, column in sorted(set(issues))
        )
    return output
