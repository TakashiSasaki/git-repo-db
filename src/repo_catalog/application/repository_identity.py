"""Repository identity is independent of access URLs and discovery sources."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.time import now_us

PROVIDERS = ("github", "gitlab", "gitea", "forgejo", "gitolite", "git", "other")


def source(store, selector):
    """Resolve only local IDs or registration UUIDs; never display names."""
    if selector.startswith("local:"):
        sql, values = "source_id=?", (selector[6:],)
    elif selector.startswith("registration:"):
        sql, values = "source_registration_uuidv4=?", (selector[13:],)
    else:
        sql, values = (
            "source_id=? OR source_registration_uuidv4=?",
            (selector, selector),
        )
    rows = store.all("SELECT * FROM sources WHERE " + sql, values)
    if len(rows) != 1:
        raise CatalogError(
            "NOT_FOUND" if not rows else "INVALID_ARGUMENT",
            "Select one source using local:ID or registration:UUID",
        )
    return rows[0]


def source_settings(src):
    """Validate operational configuration before acquiring any evidence."""
    if src["settings"] is None:
        raise CatalogError(
            "SOURCE_UNCONFIGURED", "Source has no local operational settings"
        )
    settings = json.loads(src["settings"])
    required = "url" if src["discovery_kind"] == "manual_git" else "owner"
    if (
        not isinstance(settings, dict)
        or not isinstance(settings.get(required), str)
        or not settings[required].strip()
    ):
        raise CatalogError(
            "SOURCE_INVALID_SETTINGS", "Source acquisition settings are incomplete"
        )
    if required == "url":
        git_url(settings[required])
    return settings


def transport(url):
    scheme = urlsplit(url).scheme
    if scheme in ("file", "https", "ssh"):
        return scheme
    if "://" not in url and re.match(r"^[^/\s:]+:.+", url):
        return "ssh"
    return "other" if scheme else "file"


def git_url(value):
    if not value or value != value.strip() or value.startswith("-"):
        raise CatalogError(
            "INVALID_ARGUMENT",
            "Git URL must be nonempty and have no surrounding whitespace",
        )
    parsed = urlsplit(value)
    if parsed.password or parsed.scheme in ("http", "https") and parsed.username:
        raise CatalogError(
            "INVALID_ARGUMENT",
            "Use external credentials, not credentials embedded in a URL",
        )
    if transport(value) == "file" and not parsed.scheme:
        # Capture caller-relative paths once; Git fetch runs inside the cache.
        return Path(value).expanduser().absolute().as_uri()
    return value


def instance(store, selector):
    # A portable UUID is authoritative even if another instance uses its text
    # as a display name. Names are local, non-unique selectors only.
    exact = store.one(
        "SELECT * FROM service_instances WHERE service_instance_uuidv4=?",
        (selector,),
    )
    if exact is not None:
        return exact
    rows = store.all(
        "SELECT * FROM service_instances WHERE name=?",
        (selector,),
    )
    if len(rows) != 1:
        raise CatalogError(
            "NOT_FOUND" if not rows else "INVALID_ARGUMENT",
            "Select one service instance by UUID; display name is absent or ambiguous",
        )
    return rows[0]


def add_instance(store, service_kind, name, web_base_url=None, api_base_url=None):
    if service_kind not in PROVIDERS or not name or not name.strip():
        raise CatalogError(
            "INVALID_ARGUMENT", "Provider kind and instance name are required"
        )
    for url in (web_base_url, api_base_url):
        if url:
            p = urlsplit(url)
            if (
                p.scheme not in ("https", "http")
                or not p.hostname
                or p.username
                or p.password
                or p.query
                or p.fragment
            ):
                raise CatalogError(
                    "INVALID_ARGUMENT",
                    "Instance URL must be an HTTP(S) base URL without credentials, query or fragment",
                )
            if p.scheme == "http" and p.hostname not in (
                "127.0.0.1",
                "localhost",
                "::1",
            ):
                raise CatalogError(
                    "INVALID_ARGUMENT", "Remote API and web base URLs require HTTPS"
                )
    ident = str(uuid.uuid4())
    store.execute(
        "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,web_base_url,api_base_url,metadata,created_at_us) VALUES(?,?,?,?,?,?,?)",
        (ident, service_kind, name, web_base_url, api_base_url, "{}", now_us()),
    )
    return ident


def default_github_instance(store):
    rows = store.all(
        "SELECT * FROM service_instances WHERE name='github.com' AND service_kind='github'"
    )
    if len(rows) > 1:
        raise CatalogError(
            "INVALID_ARGUMENT",
            "Ambiguous default GitHub instance; specify --instance UUID",
        )
    if rows:
        return rows[0]["service_instance_uuidv4"]
    return add_instance(
        store,
        "github",
        "github.com",
        "https://github.com",
        store.config["github"]["rest_base_url"],
    )


def bind(
    store, repository_uuidv4, service_instance_uuidv4, provider_repository_id=None
):
    current = store.one(
        "SELECT * FROM repository_bindings WHERE repository_uuidv4=? AND service_instance_uuidv4=?",
        (repository_uuidv4, service_instance_uuidv4),
    )
    if provider_repository_id is not None:
        provider_repository_id = str(provider_repository_id)
        if not provider_repository_id.strip():
            raise CatalogError(
                "INVALID_ARGUMENT", "Provider repository ID must be nonempty"
            )
        other = store.one(
            "SELECT repository_uuidv4 FROM repository_bindings WHERE service_instance_uuidv4=? AND provider_repository_id=?",
            (service_instance_uuidv4, provider_repository_id),
        )
        if other and other[0] != repository_uuidv4:
            raise CatalogError(
                "IDENTITY_CONFLICT",
                "Provider identity is already bound to another repository",
                {"repository_uuidv4": other[0]},
            )
        if current and current["provider_repository_id"] not in (
            None,
            provider_repository_id,
        ):
            raise CatalogError(
                "IDENTITY_CONFLICT",
                "Repository already has a different identity in this instance",
            )
    if current:
        if (
            provider_repository_id is not None
            and current["provider_repository_id"] is None
        ):
            store.execute(
                "UPDATE repository_bindings SET provider_repository_id=? WHERE repository_uuidv4=? AND service_instance_uuidv4=?",
                (provider_repository_id, repository_uuidv4, service_instance_uuidv4),
            )
        return
    store.execute(
        "INSERT INTO repository_bindings(repository_binding_id,repository_uuidv4,service_instance_uuidv4,provider_repository_id,metadata,created_at_us) VALUES(?,?,?,?,?,?)",
        (
            str(uuid.uuid4()),
            repository_uuidv4,
            service_instance_uuidv4,
            provider_repository_id,
            "{}",
            now_us(),
        ),
    )


def prefer_endpoint(store, repository_uuidv4, repository_endpoint_id):
    row = store.one(
        "SELECT * FROM repository_endpoints WHERE repository_endpoint_id=? AND repository_uuidv4=?",
        (repository_endpoint_id, repository_uuidv4),
    )
    if not row:
        raise CatalogError("NOT_FOUND", "Endpoint not found in selected repository")
    store.execute(
        "UPDATE repositories SET preferred_repository_endpoint_id=? WHERE repository_uuidv4=?",
        (repository_endpoint_id, repository_uuidv4),
    )


def add_endpoint(
    store, repository_uuidv4, url, label=None, preferred=False, *, normalize=True
):
    url = git_url(url) if normalize else url
    row = store.one(
        "SELECT repository_endpoint_id FROM repository_endpoints WHERE repository_uuidv4=? AND url=?",
        (repository_uuidv4, url),
    )
    if row:
        ident = row[0]
    else:
        ident = str(uuid.uuid4())
        store.execute(
            "INSERT INTO repository_endpoints(repository_endpoint_id,repository_uuidv4,url,transport,label,metadata,created_at_us) VALUES(?,?,?,?,?,?,?)",
            (ident, repository_uuidv4, url, transport(url), label, "{}", now_us()),
        )
    if preferred or not store.one(
        "SELECT 1 FROM repositories WHERE repository_uuidv4=? AND preferred_repository_endpoint_id IS NOT NULL",
        (repository_uuidv4,),
    ):
        prefer_endpoint(store, repository_uuidv4, ident)
    return ident


def endpoint(store, repository_uuidv4, repository_endpoint_id=None):
    row = store.one(
        "SELECT * FROM repository_endpoints WHERE repository_uuidv4=? AND "
        + (
            "repository_endpoint_id=?"
            if repository_endpoint_id
            else "repository_endpoint_id=(SELECT preferred_repository_endpoint_id FROM repositories WHERE repositories.repository_uuidv4=repository_endpoints.repository_uuidv4)"
        ),
        (repository_uuidv4, repository_endpoint_id)
        if repository_endpoint_id
        else (repository_uuidv4,),
    )
    if not row:
        raise CatalogError("NOT_FOUND", "Repository endpoint not found")
    return row


def link_source(store, source_id, repository_uuidv4):
    stamp = now_us()
    current = store.one(
        "SELECT last_seen_us FROM source_repositories WHERE source_id=? AND repository_uuidv4=?",
        (source_id, repository_uuidv4),
    )
    if current:
        # Preserve the imported aggregate if the source recorded a later time.
        store.execute(
            "UPDATE source_repositories SET last_seen_us=CASE WHEN last_seen_us IS NULL OR last_seen_us<? THEN ? ELSE last_seen_us END WHERE source_id=? AND repository_uuidv4=?",
            (stamp, stamp, source_id, repository_uuidv4),
        )
    else:
        store.execute(
            "INSERT INTO source_repositories(source_id,repository_uuidv4,first_seen_us,last_seen_us) VALUES(?,?,?,?)",
            (source_id, repository_uuidv4, stamp, stamp),
        )


def repository_row(store, row):
    """Build the small collector/selector projection from catalog3 identity facts."""
    value = dict(row)
    selected = store.one(
        "SELECT url FROM repository_endpoints WHERE repository_endpoint_id=? AND repository_uuidv4=?",
        (value["preferred_repository_endpoint_id"], value["repository_uuidv4"]),
    )
    source = store.one(
        "SELECT source_id FROM source_repositories WHERE repository_uuidv4=? ORDER BY first_seen_us,source_id LIMIT 1",
        (value["repository_uuidv4"],),
    )
    binding = store.one(
        "SELECT b.provider_repository_id,i.name,i.web_base_url FROM repository_bindings b JOIN service_instances i ON i.service_instance_uuidv4=b.service_instance_uuidv4 WHERE b.repository_uuidv4=? ORDER BY i.name LIMIT 1",
        (value["repository_uuidv4"],),
    )
    value.update(
        url=selected[0] if selected else None,
        source_id=source[0] if source else None,
        provider_repository_id=binding["provider_repository_id"] if binding else None,
        provider_host=(urlsplit(binding["web_base_url"]).hostname or binding["name"])
        if binding
        else "local",
    )
    return value


def github_config(store, src):
    config = dict(store.config["github"])
    if src["service_instance_uuidv4"]:
        value = instance(store, src["service_instance_uuidv4"])
        if value["service_kind"] != "github":
            raise CatalogError(
                "PROVIDER_UNSUPPORTED", "This source requires a GitHub instance"
            )
        if value["api_base_url"]:
            config["rest_base_url"] = value["api_base_url"]
        # Default SaaS config remains configurable for synthetic/older states.
        if value["name"] == "github.com":
            config["rest_base_url"] = store.config["github"]["rest_base_url"]
        else:
            api, web = value["api_base_url"], value["web_base_url"]
            if not api and not web:
                raise CatalogError(
                    "INVALID_ARGUMENT",
                    "GitHub API source requires an instance base URL",
                )
            api = (api or web.rstrip("/") + "/api/v3").rstrip("/")
            config["rest_base_url"] = api
            config["graphql_url"] = (
                api.removesuffix("/v3") + "/graphql"
                if api.endswith("/api/v3")
                else api + "/graphql"
            )
    config.update(source_settings(src).get("api_settings", {}))
    return config


def pr_source(store, repository_uuidv4, requested_source=None):
    if (
        store.one(
            "SELECT count(*) FROM repository_bindings b JOIN service_instances i ON i.service_instance_uuidv4=b.service_instance_uuidv4 WHERE b.repository_uuidv4=? AND i.service_kind='github'",
            (repository_uuidv4,),
        )[0]
        > 1
    ):
        raise CatalogError(
            "PROVIDER_UNSUPPORTED",
            "PR namespaces for multiple GitHub instances on one Repo ID are not supported",
        )
    if requested_source:
        chosen = store.one(
            "SELECT discovery_kind FROM sources WHERE source_id=?", (requested_source,)
        )
        if chosen and chosen[0] != "github_inventory":
            requested_source = None
    params = (
        (repository_uuidv4, requested_source)
        if requested_source
        else (repository_uuidv4,)
    )
    row = store.one(
        "SELECT s.*,b.provider_repository_id,i.web_base_url FROM source_repositories m JOIN sources s ON s.source_id=m.source_id JOIN service_instances i ON i.service_instance_uuidv4=s.service_instance_uuidv4 JOIN repository_bindings b ON b.repository_uuidv4=m.repository_uuidv4 AND b.service_instance_uuidv4=i.service_instance_uuidv4 WHERE m.repository_uuidv4=? AND s.discovery_kind='github_inventory'"
        + (" AND s.source_id=?" if requested_source else "")
        + " ORDER BY m.first_seen_us,s.source_id LIMIT 1",
        params,
    )
    return row


def pr_applicable(store, repository_uuidv4):
    return bool(
        store.one(
            "SELECT 1 FROM repository_bindings b JOIN service_instances i ON i.service_instance_uuidv4=b.service_instance_uuidv4 WHERE b.repository_uuidv4=? AND i.service_kind NOT IN ('git','gitolite') LIMIT 1",
            (repository_uuidv4,),
        )
    )
