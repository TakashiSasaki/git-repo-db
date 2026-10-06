"""Repository identity is independent of access URLs and discovery sources."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from repo_catalog.domain.models import CatalogError, now

PROVIDERS = ("github", "gitlab", "gitea", "forgejo", "gitolite", "git", "other")


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
    rows = store.all(
        "SELECT * FROM service_instances WHERE id=? OR name=?", (selector, selector)
    )
    if len(rows) != 1:
        raise CatalogError(
            "NOT_FOUND" if not rows else "INVALID_ARGUMENT",
            "Select one service instance",
        )
    return rows[0]


def add_instance(store, kind, name, web_base_url=None, api_base_url=None):
    if kind not in PROVIDERS or not name or not name.strip():
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
    if store.one("SELECT 1 FROM service_instances WHERE name=?", (name,)):
        raise CatalogError("IDENTITY_CONFLICT", "Instance name already exists")
    ident = str(uuid.uuid4())
    store.execute(
        "INSERT INTO service_instances VALUES(?,?,?,?,?,?,?)",
        (ident, kind, name, web_base_url, api_base_url, "{}", now()),
    )
    return ident


def default_github_instance(store):
    row = store.one(
        "SELECT * FROM service_instances WHERE name='github.com' AND kind='github'"
    )
    if row:
        return row["id"]
    return add_instance(
        store,
        "github",
        "github.com",
        "https://github.com",
        store.config["github"]["rest_base_url"],
    )


def bind(store, repo_id, instance_id, provider_repo_id=None):
    current = store.one(
        "SELECT * FROM repository_bindings WHERE repo_id=? AND instance_id=?",
        (repo_id, instance_id),
    )
    if provider_repo_id is not None:
        provider_repo_id = str(provider_repo_id)
        if not provider_repo_id.strip():
            raise CatalogError(
                "INVALID_ARGUMENT", "Provider repository ID must be nonempty"
            )
        other = store.one(
            "SELECT repo_id FROM repository_bindings WHERE instance_id=? AND provider_repo_id=?",
            (instance_id, provider_repo_id),
        )
        if other and other[0] != repo_id:
            raise CatalogError(
                "IDENTITY_CONFLICT",
                "Provider identity is already bound to another repository",
                {"repo_id": other[0]},
            )
        if current and current["provider_repo_id"] not in (None, provider_repo_id):
            raise CatalogError(
                "IDENTITY_CONFLICT",
                "Repository already has a different identity in this instance",
            )
    if current:
        if provider_repo_id is not None and current["provider_repo_id"] is None:
            store.execute(
                "UPDATE repository_bindings SET provider_repo_id=? WHERE repo_id=? AND instance_id=?",
                (provider_repo_id, repo_id, instance_id),
            )
        return
    store.execute(
        "INSERT INTO repository_bindings VALUES(?,?,?,?,?,?)",
        (str(uuid.uuid4()), repo_id, instance_id, provider_repo_id, "{}", now()),
    )


def prefer_endpoint(store, repo_id, endpoint_id):
    row = store.one(
        "SELECT * FROM repository_endpoints WHERE id=? AND repo_id=?",
        (endpoint_id, repo_id),
    )
    if not row:
        raise CatalogError("NOT_FOUND", "Endpoint not found in selected repository")
    store.execute(
        "UPDATE repositories SET preferred_endpoint_id=? WHERE id=?",
        (endpoint_id, repo_id),
    )


def add_endpoint(store, repo_id, url, label=None, preferred=False, *, normalize=True):
    url = git_url(url) if normalize else url
    row = store.one(
        "SELECT id FROM repository_endpoints WHERE repo_id=? AND url=?", (repo_id, url)
    )
    if row:
        ident = row[0]
    else:
        ident = str(uuid.uuid4())
        store.execute(
            "INSERT INTO repository_endpoints VALUES(?,?,?,?,?,?,?)",
            (ident, repo_id, url, transport(url), label, "{}", now()),
        )
    if preferred or not store.one(
        "SELECT 1 FROM repositories WHERE id=? AND preferred_endpoint_id IS NOT NULL",
        (repo_id,),
    ):
        prefer_endpoint(store, repo_id, ident)
    return ident


def endpoint(store, repo_id, endpoint_id=None):
    row = store.one(
        "SELECT * FROM repository_endpoints WHERE repo_id=? AND "
        + (
            "id=?"
            if endpoint_id
            else "id=(SELECT preferred_endpoint_id FROM repositories WHERE id=repo_id)"
        ),
        (repo_id, endpoint_id) if endpoint_id else (repo_id,),
    )
    if not row:
        raise CatalogError("NOT_FOUND", "Repository endpoint not found")
    return row


def link_source(store, source_id, repo_id):
    stamp = now()
    current = store.one(
        "SELECT last_seen FROM source_repositories WHERE source_id=? AND repo_id=?",
        (source_id, repo_id),
    )
    if current:
        # Preserve the imported aggregate if the source recorded a later time.
        store.execute(
            "UPDATE source_repositories SET last_seen=CASE WHEN last_seen IS NULL OR julianday(last_seen)<julianday(?) THEN ? ELSE last_seen END WHERE source_id=? AND repo_id=?",
            (stamp, stamp, source_id, repo_id),
        )
    else:
        store.execute(
            "INSERT INTO source_repositories VALUES(?,?,?,?)",
            (source_id, repo_id, stamp, stamp),
        )


def repository_row(store, row):
    """Build the small collector/selector projection from catalog3 identity facts."""
    value = dict(row)
    selected = store.one(
        "SELECT url FROM repository_endpoints WHERE id=? AND repo_id=?",
        (value["preferred_endpoint_id"], value["id"]),
    )
    source = store.one(
        "SELECT source_id FROM source_repositories WHERE repo_id=? ORDER BY first_seen,source_id LIMIT 1",
        (value["id"],),
    )
    binding = store.one(
        "SELECT b.provider_repo_id,i.name,i.web_base_url FROM repository_bindings b JOIN service_instances i ON i.id=b.instance_id WHERE b.repo_id=? ORDER BY i.name LIMIT 1",
        (value["id"],),
    )
    value.update(
        url=selected[0] if selected else None,
        source_id=source[0] if source else None,
        provider_repo_id=binding["provider_repo_id"] if binding else None,
        provider_host=(urlsplit(binding["web_base_url"]).hostname or binding["name"])
        if binding
        else "local",
        current_snapshot=value["current_snapshot_id"],
    )
    return value


def github_config(store, src):
    config = dict(store.config["github"])
    if src["instance_id"]:
        value = instance(store, src["instance_id"])
        if value["kind"] != "github":
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
    config.update(json.loads(src["settings"]).get("api_settings", {}))
    return config


def pr_source(store, repo_id, requested_source=None):
    if (
        store.one(
            "SELECT count(*) FROM repository_bindings b JOIN service_instances i ON i.id=b.instance_id WHERE b.repo_id=? AND i.kind='github'",
            (repo_id,),
        )[0]
        > 1
    ):
        raise CatalogError(
            "PROVIDER_UNSUPPORTED",
            "PR namespaces for multiple GitHub instances on one Repo ID are not supported",
        )
    if requested_source:
        chosen = store.one(
            "SELECT discovery_kind FROM sources WHERE id=?", (requested_source,)
        )
        if chosen and chosen[0] != "github_inventory":
            requested_source = None
    params = (repo_id, requested_source) if requested_source else (repo_id,)
    row = store.one(
        "SELECT s.*,b.provider_repo_id,i.web_base_url FROM source_repositories m JOIN sources s ON s.id=m.source_id JOIN service_instances i ON i.id=s.instance_id JOIN repository_bindings b ON b.repo_id=m.repo_id AND b.instance_id=i.id WHERE m.repo_id=? AND s.discovery_kind='github_inventory'"
        + (" AND s.id=?" if requested_source else "")
        + " ORDER BY m.first_seen,s.id LIMIT 1",
        params,
    )
    return row


def pr_applicable(store, repo_id):
    return bool(
        store.one(
            "SELECT 1 FROM repository_bindings b JOIN service_instances i ON i.id=b.instance_id WHERE b.repo_id=? AND i.kind NOT IN ('git','gitolite') LIMIT 1",
            (repo_id,),
        )
    )
