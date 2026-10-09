"""Freeze acquisition identities and non-secret settings at job creation."""

from __future__ import annotations

import copy
import json
import os
from urllib.parse import parse_qsl, urlsplit

from repo_catalog.application import repository_identity as identity
from repo_catalog.domain.models import CatalogError


def freeze_source(store, source, *, require_credentials=True):
    row = dict(source)
    settings = identity.source_settings(row)
    # Supported settings contain credential references, never credential values.
    reject_secrets(settings)
    row["settings"] = json.dumps(settings, sort_keys=True, allow_nan=False)
    if row["discovery_kind"] == "github_inventory":
        row["github_config"] = identity.github_config(store, row)
        reject_secrets(row["github_config"])
    if require_credentials:
        check_credentials(row)
    return row


def reject_secrets(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in {
                "token",
                "access_token",
                "password",
                "secret",
                "authorization",
                "cookie",
                "client_secret",
                "private_key",
            }:
                raise CatalogError(
                    "SOURCE_INVALID_SETTINGS",
                    "Store credential references, not secrets",
                )
            reject_secrets(child)
    elif isinstance(value, list):
        for child in value:
            reject_secrets(child)
    elif isinstance(value, str) and "://" in value:
        try:
            parsed = urlsplit(value)
            secret_query = any(
                key.lower()
                in {
                    "token",
                    "access_token",
                    "password",
                    "secret",
                    "api_key",
                    "key",
                    "auth",
                }
                for key, _ in parse_qsl(parsed.query)
            )
            if (
                parsed.password
                or (parsed.scheme in ("http", "https") and parsed.username)
                or secret_query
            ):
                raise CatalogError(
                    "SOURCE_INVALID_SETTINGS",
                    "Credential-bearing URLs cannot be saved in a job plan",
                )
        except ValueError as cause:
            raise CatalogError(
                "SOURCE_INVALID_SETTINGS", "Invalid acquisition URL"
            ) from cause


def check_credentials(source):
    if source["discovery_kind"] == "github_inventory":
        name = source["github_config"].get("token_env_var")
        if not name or not os.environ.get(name):
            raise CatalogError(
                "SOURCE_CREDENTIAL_UNAVAILABLE",
                "Source credential reference is unavailable",
            )


def freeze_config(store):
    config = {
        key: copy.deepcopy(store.config[key]) for key in ("collection", "preservation")
    }
    reject_secrets(config)
    return config


def activate(store, plan):
    """Restore only the frozen acquisition configuration, not local DB/cache policy."""
    for key, values in plan["acquisition_config"].items():
        store.config[key] = copy.deepcopy(values)
    store.frozen_source_settings = {
        source["source_id"]: json.loads(source["settings"])
        for source in plan["sources"]
    }


def check_registration(store, frozen):
    actual = store.one(
        "SELECT source_registration_uuidv4 FROM sources WHERE source_id=?",
        (frozen["source_id"],),
    )
    if actual is None or actual[0] != frozen["source_registration_uuidv4"]:
        raise CatalogError(
            "SOURCE_IDENTITY_CHANGED",
            "Frozen source registration is no longer available",
        )
    check_credentials(frozen)
