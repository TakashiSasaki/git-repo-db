from __future__ import annotations

import math
import os
import tomllib
from pathlib import Path

from repo_catalog.domain.models import CatalogError

DEFAULTS = {
    "config_version": 1,
    "database": {
        "filename": "catalog.sqlite3",
        "journal_mode": "delete",
        "busy_timeout_ms": 5000,
    },
    "collection": {
        "git_workers": 1,
        "git_transfer_timeout_seconds": 300,
        "api_workers": 1,
        "write_batch_rows": 1000,
        "write_batch_bytes": 8388608,
        "blob_chunk_bytes": 1048576,
    },
    "cache": {"high_water_ratio": 0.8, "low_water_ratio": 0.6, "ttl_seconds": 604800},
    "preservation": {
        "profile": "catalog-text-v1",
        "text_policy_id": "utf8-literal-v1",
        "max_text_blob_bytes": 8388608,
    },
    "github": {
        "rest_base_url": "https://api.github.com",
        "graphql_url": "https://api.github.com/graphql",
        "token_env_var": "GH_TOKEN",
        "rest_api_version": "2026-03-10",
        "rest_page_size": 100,
        "graphql_page_size": 100,
        "connect_timeout_seconds": 10,
        "read_timeout_seconds": 60,
        "max_attempts": 5,
        "record_messages": False,
    },
    "search": {
        "backend": "auto",
        "default_limit": 100,
        "max_limit": 1000,
        "timeout_seconds": 30,
    },
}


def state_path(value=None):
    return (
        Path(
            value
            or Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
            / "repo-catalog"
        )
        .expanduser()
        .resolve()
    )


def validate(config):
    if config.get("config_version") != 1:
        raise CatalogError("CONFIG_ERROR", "Unsupported configuration version")
    if config["preservation"]["profile"] != "catalog-text-v1":
        raise CatalogError("PROFILE_UNSUPPORTED", "Only catalog-text-v1 is implemented")
    c = config["cache"]
    git_timeout = config["collection"].get("git_transfer_timeout_seconds", 300)
    if not math.isfinite(git_timeout) or git_timeout <= 0:
        raise CatalogError("CONFIG_ERROR", "Git transfer timeout must be positive")
    if (
        c.get("max_bytes", 0) <= 0
        or c.get("min_free_bytes", -1) < 0
        or not 0 <= c["low_water_ratio"] < c["high_water_ratio"] <= 1
        or c["ttl_seconds"] < 0
    ):
        raise CatalogError("CONFIG_ERROR", "Invalid cache budgets or watermarks")
    if config["database"]["journal_mode"] not in ("delete", "wal"):
        raise CatalogError("CONFIG_ERROR", "Unknown journal mode")
    if type(config["github"].get("record_messages", False)) is not bool:
        raise CatalogError("CONFIG_ERROR", "github.record_messages must be a boolean")
    if (
        config["preservation"]["max_text_blob_bytes"] != 8388608
        or config["preservation"]["text_policy_id"] != "utf8-literal-v1"
    ):
        raise CatalogError(
            "PROFILE_UNSUPPORTED", "utf8-literal-v1 has a fixed 8 MiB boundary"
        )
    for section, keys in {
        "collection": (
            "git_workers",
            "api_workers",
            "blob_chunk_bytes",
            "write_batch_rows",
            "write_batch_bytes",
        ),
        "github": (
            "rest_page_size",
            "graphql_page_size",
            "connect_timeout_seconds",
            "read_timeout_seconds",
            "max_attempts",
        ),
        "search": ("default_limit", "max_limit", "timeout_seconds"),
    }.items():
        if any(
            not math.isfinite(config[section][k]) or config[section][k] <= 0
            for k in keys
        ):
            raise CatalogError("CONFIG_ERROR", f"{section} limits must be positive")
    return config


def load(path):
    file = Path(path) / "catalog.toml"
    if not file.is_file():
        raise CatalogError("NOT_INITIALIZED", "Run init with explicit capacity budgets")
    try:
        with file.open("rb") as stream:
            return validate(tomllib.load(stream))
    except (ValueError, KeyError, TypeError, tomllib.TOMLDecodeError) as e:
        raise CatalogError(
            "CONFIG_ERROR", f"Invalid configuration: {type(e).__name__}"
        ) from e


def serialize(config):
    lines = ["config_version = 1"]
    import json

    for section, values in config.items():
        if isinstance(values, dict):
            lines.append(f"\n[{section}]")
            for key, value in values.items():
                lines.append(f"{key} = {json.dumps(value)}")
    return "\n".join(lines) + "\n"
