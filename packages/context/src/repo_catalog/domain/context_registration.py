"""Domain-only Context registration metadata; never executable Access settings.

The finite vocabulary is shared by Python admission, SQLite CHECKs, readers and
Exchange. A descriptive field is not execution authority. This is not secret/DLP
recognition for content deliberately disguised as prose or original provenance.
No input is moved, normalized into a route, resolved, or silently discarded.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from repo_catalog.domain.p1_context import canonical
from repo_catalog.domain.time import validate_observation_us

RegistrationKind = Literal["provider", "repository", "source", "membership"]
MAX_BYTES = 65536
MAX_DEPTH = 12
MAX_ELEMENTS = 2048

# Declarative domain values only. Names are descriptions, not executor selectors.
FIELD_TYPES = {
    "provider": {
        "name": "text",
        "display_name": "text",
        "description": "text",
        "tier": "text",
        "evidence": "evidence",
        "created_at_us": "time",
    },
    "repository": {
        "name": "text",
        "display_name": "text",
        "description": "text",
        "full_name": "text",
        "default_branch": "text",
        "private": "bool",
        "archived": "bool",
        "visibility": "visibility",
        "evidence": "evidence",
        "created_at_us": "time",
    },
    "source": {
        "name": "text",
        "display_name": "text",
        "description": "text",
        "discovery_kind": "text",
        "owner": "text",
        "org": "text",
        "evidence": "evidence",
        "created_at_us": "time",
    },
    "membership": {
        "source": "text",
        "evidence": "evidence",
        "name": "text",
        "label": "text",
        "first_seen_us": "time",
        "last_seen_us": "time",
        "discovery_reason": "text",
        "parser_module": "text",
        "parser_version": "text",
    },
}

# Routing diagnostics, NOT executable configuration schemas. Unknown keys fail too.
ACCESS_FIELDS = frozenset(
    {
        "url",
        "endpoint",
        "api_url",
        "api_base_url",
        "rest_base_url",
        "web_base_url",
        "graphql_url",
        "clone_url",
        "ssh_url",
        "git_url",
        "host",
        "hostname",
        "port",
        "username",
        "user",
        "transport",
        "git_path",
        "local_path",
        "path",
        "ssh_profile",
        "ssh_profile_ref",
        "credential_ref",
        "token_env_var",
        "scope_uuidv4",
        "scope_locator_uri",
        "configuration_name",
        "preferred_repository_endpoint_id",
        "proxy",
        "proxy_url",
        "proxycommand",
        "tls_verify",
        "verify_tls",
        "known_hosts_file",
        "identity_file",
        "executor_ref",
        "identity_view",
        "query",
    }
)
EXECUTION_FIELDS = frozenset(
    {
        "poll_interval_s",
        "timeout",
        "timeout_s",
        "retry_count",
        "not_before_us",
        "cache_dir",
        "cursor",
        "page_number",
        "work_limits",
    }
)
SECRET_FIELDS = frozenset(
    {
        "token",
        "access_token",
        "password",
        "secret",
        "authorization",
        "cookie",
        "client_secret",
        "private_key",
        "passphrase",
        "api_key",
    }
)


class RegistrationError(ValueError):
    """No caller-controlled values/unknown field names in printable diagnostics."""

    def __init__(self, code: str, kind: str):
        self.code = code
        self.kind = (
            kind if isinstance(kind, str) and kind in FIELD_TYPES else "registration"
        )
        super().__init__(f"{self.kind}:{code}")


def _parse(kind: str, encoded: str) -> dict:
    if not isinstance(kind, str) or kind not in FIELD_TYPES:
        raise RegistrationError("REGISTRATION_KIND", "registration")
    if type(encoded) is not str or len(encoded) > MAX_BYTES:
        raise RegistrationError("REGISTRATION_INPUT_LIMIT", kind)
    try:
        if len(encoded.encode("utf-8")) > MAX_BYTES:
            raise RegistrationError("REGISTRATION_INPUT_LIMIT", kind)
        # Bound nesting before calling the recursive JSON decoder.
        depth = 0
        quoted = escaped = False
        for char in encoded:
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "[{":
                depth += 1
                if depth > MAX_DEPTH:
                    raise RegistrationError("REGISTRATION_INPUT_LIMIT", kind)
            elif char in "]}":
                depth -= 1

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise RegistrationError("REGISTRATION_DUPLICATE_KEY", kind)
                result[key] = value
            return result

        def constant(_value):
            raise RegistrationError("REGISTRATION_VALUE", kind)

        data = json.loads(encoded, object_pairs_hook=unique, parse_constant=constant)
        if type(data) is not dict:
            raise RegistrationError("REGISTRATION_OBJECT", kind)
        pending, count = [data], 0
        while pending:
            value = pending.pop()
            count += 1
            if count > MAX_ELEMENTS:
                raise RegistrationError("REGISTRATION_INPUT_LIMIT", kind)
            if isinstance(value, dict):
                pending.extend(value.values())
                pending.extend(value.keys())
            elif isinstance(value, list):
                pending.extend(value)
            elif isinstance(value, str):
                value.encode("utf-8")  # reject escaped isolated surrogates too
        if canonical(data) != encoded:
            raise RegistrationError("REGISTRATION_NONCANONICAL", kind)
        return data
    except RegistrationError:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError, OverflowError):
        raise RegistrationError("REGISTRATION_JSON", kind) from None


def _route(kind: str, key: str) -> str:
    if key in FIELD_TYPES[kind]:
        return "context"
    normalized = key.lower()
    if normalized in SECRET_FIELDS:
        return "external_secret"
    if normalized in ACCESS_FIELDS:
        return "access_review"
    if normalized in EXECUTION_FIELDS:
        return "execution_policy_review"
    return "unclassified"


def _field(kind: str, name: str, value: object) -> None:
    grammar = FIELD_TYPES[kind][name]
    valid = True
    if grammar == "text":
        valid = value is None or type(value) is str
    elif grammar == "bool":
        valid = value is None or type(value) is bool
    elif grammar == "time":
        try:
            validate_observation_us(value)
        except (TypeError, ValueError, OverflowError):
            valid = False
    elif grammar == "visibility":
        valid = value is None or (
            type(value) is str and value in ("public", "private", "internal")
        )
    elif grammar == "evidence":
        # Actual source coordinates are domain data, never permission or options.
        # Preserve structured provenance rather than inventing a new issuer/clock.
        valid = value is not None
    if not valid:
        raise RegistrationError("REGISTRATION_FIELD_TYPE", kind)


def registration_json(kind: RegistrationKind, encoded: str) -> dict:
    """Validate canonical metadata without stripping or rewriting any value."""
    data = _parse(kind, encoded)
    for key, value in data.items():
        route = _route(kind, key)
        if route != "context":
            codes = {
                "access_review": "REGISTRATION_ACCESS_SETTINGS",
                "external_secret": "REGISTRATION_SECRET",
                "execution_policy_review": "REGISTRATION_EXECUTION_SETTINGS",
                "unclassified": "REGISTRATION_UNKNOWN_FIELD",
            }
            raise RegistrationError(codes[route], kind)
        _field(kind, key, value)
    if kind == "membership" and (("source" in data) != ("evidence" in data)):
        raise RegistrationError("REGISTRATION_PROVENANCE", kind)
    if kind == "membership" and "source" in data and not data["source"]:
        raise RegistrationError("REGISTRATION_PROVENANCE", kind)
    return data


@dataclass(frozen=True)
class RegistrationClassification:
    """Dry-run key counts only, never an extracted configuration or secret value."""

    kind: str
    context_fields: tuple[str, ...]
    access_fields: tuple[str, ...]
    execution_fields: tuple[str, ...]
    secret_count: int
    unknown_count: int
    valid_domain: bool


def classify_registration(
    kind: RegistrationKind, encoded: str
) -> RegistrationClassification:
    data = _parse(kind, encoded)
    routes = {key: _route(kind, key) for key in data}
    valid = True
    try:
        registration_json(kind, encoded)
    except RegistrationError:
        valid = False
    return RegistrationClassification(
        kind,
        tuple(sorted(k for k, r in routes.items() if r == "context")),
        tuple(sorted(k.lower() for k, r in routes.items() if r == "access_review")),
        tuple(
            sorted(
                k.lower() for k, r in routes.items() if r == "execution_policy_review"
            )
        ),
        sum(r == "external_secret" for r in routes.values()),
        sum(r == "unclassified" for r in routes.values()),
        valid,
    )


# Exact registration envelopes prohibit an executable sibling field being ignored.
EXCHANGE_REGISTRATIONS = {
    "providers": (
        "provider",
        "configuration_json",
        {"service_instance_uuidv4", "provider_kind", "configuration_json"},
    ),
    "repositories": (
        "repository",
        "configuration_json",
        {"repository_uuidv4", "configuration_json"},
    ),
    "sources": (
        "source",
        "configuration_json",
        {"source_registration_uuidv4", "service_instance_uuidv4", "configuration_json"},
    ),
    "source_repositories": (
        "membership",
        "attributes_json",
        {"source_registration_uuidv4", "repository_uuidv4", "attributes_json"},
    ),
}


def validate_exchange_registrations(context: dict) -> None:
    for section, (kind, column, keys) in EXCHANGE_REGISTRATIONS.items():
        for row in context[section]:
            if type(row) is not dict or set(row) != keys:
                raise RegistrationError("REGISTRATION_ENVELOPE", kind)
            registration_json(kind, row[column])
