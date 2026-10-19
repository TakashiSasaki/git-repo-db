"""Finite non-executing Access configuration and approval values.

These values describe local settings, not authenticated executor observations.
References are names in a separately controlled local credential/executor registry;
no supplied value is a shell command, raw key, token, or permission to execute.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from repo_catalog.domain.access_registry import (
    AccessRegistryError,
    ScopeLocatorRegistration,
    registration_time,
    scope_locator,
    scope_uuid,
)

Transport = Literal["file", "https", "ssh"]
MAX_JSON_BYTES = 16384


def _fail(code: str) -> None:
    raise AccessRegistryError(code, "invalid or unsupported Access connection value")


def name(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value
    ):
        _fail("NAME")
    return value


def enabled_value(value: object) -> bool:
    if type(value) is not bool:
        _fail("TYPE")
    return value


def canonical(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (ValueError, TypeError, RecursionError):
        _fail("OPTIONS")


def _document(value: object) -> dict:
    if not isinstance(value, str) or len(value) > MAX_JSON_BYTES:
        _fail("OPTIONS")
    try:
        parsed = json.loads(value)
        if not isinstance(parsed, dict) or canonical(parsed) != value:
            _fail("OPTIONS")
    except (ValueError, TypeError, RecursionError):
        _fail("OPTIONS")
    if type(parsed.get("version")) is not int or parsed["version"] != 1:
        _fail("OPTIONS")
    return parsed


def _reference(value: object, kinds: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != {"kind", "name"}:
        _fail("REFERENCE")
    if not isinstance(value["kind"], str) or value["kind"] not in kinds:
        _fail("REFERENCE")
    name(value["name"])


def profile_options(value: object) -> str:
    """Validate exact canonical version-1 settings; TLS/host checks cannot be disabled.

    Finite subset only: file paths use a POSIX executor; HTTPS credentials are
    named helper references; SSH uses an agent/key reference and optional approved
    local profile reference. This stores settings; it does not implement helpers.
    """
    data = _document(value)
    kind = data.get("transport")
    if kind == "file":
        if (
            set(data) != {"version", "transport", "path_dialect"}
            or data["path_dialect"] != "posix"
        ):
            _fail("OPTIONS")
    elif kind == "https":
        if set(data) - {"version", "transport", "credential_ref"}:
            _fail("OPTIONS")
        if "credential_ref" in data:
            _reference(data["credential_ref"], {"credential-helper"})
    elif kind == "ssh":
        if set(data) - {"version", "transport", "credential_ref", "ssh_profile_ref"}:
            _fail("OPTIONS")
        if "credential_ref" in data:
            _reference(data["credential_ref"], {"ssh-agent", "ssh-key"})
        if "ssh_profile_ref" in data:
            name(data["ssh_profile_ref"])
    else:
        _fail("OPTIONS")
    return value


def execution_context(value: object) -> str:
    """Locally declared execution context, never a remote attestation."""
    data = _document(value)
    if set(data) != {
        "version",
        "executor_kind",
        "executor_ref",
        "identity_view",
        "path_dialect",
    }:
        _fail("CONTEXT")
    if (
        data["executor_kind"] not in ("local", "ssh", "container")
        or data["path_dialect"] != "posix"
    ):
        _fail("CONTEXT")
    name(data["executor_ref"])
    name(data["identity_view"])
    return value


def repository_locator(value: object) -> Transport:
    """Return the finite Git addressing kind without rewriting or touching a path.

    Absolute POSIX paths and scp-style relative paths supplement A1a URI grammar.
    Windows/UNC/relative caller paths, helpers and queries remain unsupported;
    explicit rejection does not claim those forms are universally invalid Git.
    """
    if not isinstance(value, str) or not 1 <= len(value) <= 4096:
        _fail("REPOSITORY_LOCATOR")
    if any(ord(c) <= 32 or ord(c) >= 127 for c in value) or any(
        c in value for c in "\\?#"
    ):
        _fail("REPOSITORY_LOCATOR")
    if "://" in value:
        scope_locator(value)
        return urlsplit(value).scheme
    if value.startswith("/") and not value.startswith("//"):
        if not re.fullmatch(r"/[A-Za-z0-9._~/-]+", value):
            _fail("REPOSITORY_LOCATOR")
        return "file"
    match = re.fullmatch(
        r"(?:[A-Za-z0-9._~-]+@)?([A-Za-z0-9][A-Za-z0-9.-]*):([A-Za-z0-9._~/-]+)", value
    )
    if match and len(match[1]) > 1 and not match[2].startswith(("-", "~")):
        # A synthetic parse validates authority only; preserve relative remote path.
        scope_locator("ssh://" + value.split(":", 1)[0] + "/" + match[2])
        return "ssh"
    _fail("REPOSITORY_LOCATOR")


@dataclass(frozen=True)
class ScopeExecutionContext:
    scope_uuidv4: str
    context_json: str
    enabled: bool = False

    def __post_init__(self) -> None:
        scope_uuid(self.scope_uuidv4)
        execution_context(self.context_json)
        enabled_value(self.enabled)

    @property
    def row(self) -> tuple:
        return self.scope_uuidv4, self.context_json, int(self.enabled)


@dataclass(frozen=True)
class RepositoryBinding:
    scope_uuidv4: str
    locator_text: str
    repository_uuidv4: str
    enabled: bool = False

    def __post_init__(self) -> None:
        scope_uuid(self.scope_uuidv4)
        repository_locator(self.locator_text)
        scope_uuid(self.repository_uuidv4)
        enabled_value(self.enabled)

    @property
    def key(self) -> tuple[str, str]:
        return self.scope_uuidv4, self.locator_text

    @property
    def row(self) -> tuple:
        return *self.key, self.repository_uuidv4, int(self.enabled)


@dataclass(frozen=True)
class ConnectionConfiguration:
    scope_uuidv4: str
    configuration_name: str
    options_json: str
    enabled: bool = False

    def __post_init__(self) -> None:
        scope_uuid(self.scope_uuidv4)
        name(self.configuration_name)
        profile_options(self.options_json)
        enabled_value(self.enabled)

    @property
    def key(self) -> tuple[str, str]:
        return self.scope_uuidv4, self.configuration_name

    @property
    def row(self) -> tuple:
        return *self.key, self.options_json, int(self.enabled)


@dataclass(frozen=True)
class AssignmentKey:
    scope_uuidv4: str
    locator_text: str
    configuration_name: str
    purpose: str = "git-read"

    def __post_init__(self) -> None:
        scope_uuid(self.scope_uuidv4)
        repository_locator(self.locator_text)
        name(self.configuration_name)
        if self.purpose != "git-read":
            _fail("PURPOSE")

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (
            self.scope_uuidv4,
            self.locator_text,
            self.configuration_name,
            self.purpose,
        )


@dataclass(frozen=True)
class LocatorConnection:
    assignment: AssignmentKey
    enabled: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.assignment, AssignmentKey):
            _fail("TYPE")
        AssignmentKey(*self.assignment.key)
        enabled_value(self.enabled)

    @property
    def key(self) -> tuple:
        return self.assignment.key

    @property
    def row(self) -> tuple:
        return *self.key, int(self.enabled)


@dataclass(frozen=True)
class AccessPreference:
    repository_uuidv4: str
    assignment: AssignmentKey

    def __post_init__(self) -> None:
        scope_uuid(self.repository_uuidv4)
        if not isinstance(self.assignment, AssignmentKey):
            _fail("TYPE")
        AssignmentKey(*self.assignment.key)

    @property
    def key(self) -> tuple:
        return (
            self.repository_uuidv4,
            self.assignment.scope_uuidv4,
            self.assignment.purpose,
        )

    @property
    def row(self) -> tuple:
        return (
            *self.key,
            self.assignment.locator_text,
            self.assignment.configuration_name,
        )


@dataclass(frozen=True)
class AccessReviewPlan:
    assignment: AssignmentKey
    repository_uuidv4: str
    registration: ScopeLocatorRegistration
    options_json: str
    context_json: str

    def __post_init__(self) -> None:
        if not isinstance(self.assignment, AssignmentKey) or not isinstance(
            self.registration, ScopeLocatorRegistration
        ):
            _fail("TYPE")
        AssignmentKey(*self.assignment.key)
        ScopeLocatorRegistration(*self.registration.key)
        scope_uuid(self.repository_uuidv4)
        profile_options(self.options_json)
        execution_context(self.context_json)
        if self.assignment.scope_uuidv4 != self.registration.scope_uuidv4:
            _fail("SCOPE_MISMATCH")
        if (
            repository_locator(self.assignment.locator_text)
            != json.loads(self.options_json)["transport"]
        ):
            _fail("TRANSPORT_MISMATCH")

    @property
    def row(self) -> tuple:
        return (
            *self.assignment.key,
            self.repository_uuidv4,
            self.registration.registered_at_us,
            self.registration.scope_locator_uri,
            self.options_json,
            self.context_json,
        )


@dataclass(frozen=True)
class LocalAccessGrant:
    plan: AccessReviewPlan
    approved_at_us: int

    def __post_init__(self) -> None:
        if not isinstance(self.plan, AccessReviewPlan):
            _fail("TYPE")
        AccessReviewPlan(
            self.plan.assignment,
            self.plan.repository_uuidv4,
            self.plan.registration,
            self.plan.options_json,
            self.plan.context_json,
        )
        registration_time(self.approved_at_us)
