"""Immutable request plans containing explicit non-secret credential references.

References are never resolved here and do not grant transport consent. This
validator recognizes declared secret fields/URLs; it is not a prose DLP filter.
"""

from __future__ import annotations

import json
import re
from contextlib import ExitStack, contextmanager
from urllib.parse import parse_qsl, urlsplit

from repo_catalog.adapters.sqlite.catalog_runtime import (
    catalog_completion,
    catalog_gate,
)
from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.shared_values import encode, uuid4_value

_SCOPE = encode(["frozen-acquisition-plan", 1])
_REFERENCE_KINDS = {"environment", "credential-helper", "local-profile"}
_SECRET_KEYS = {
    "token",
    "password",
    "secret",
    "authorization",
    "cookie",
    "accesstoken",
    "refreshtoken",
    "credential",
    "credentials",
    "apikey",
    "clientsecret",
    "privatekey",
    "privatekeyfile",
    "identityfile",
    "sslkey",
    "clientkey",
    # Transport configuration is executable/configurable credential plumbing,
    # not source metadata. Callers must use the explicit reference channel.
    "gitconfig",
    "transportconfig",
    "headers",
    "httpheaders",
    "extraheader",
    "sshcommand",
}


def _key(value):
    return "".join(char.lower() for char in value if char.isalnum())


def _secret_key(value):
    normalized = _key(value)
    return normalized in _SECRET_KEYS or normalized.endswith(
        ("extraheader", "sshcommand", "privatekey", "clientsecret")
    )


def _safe_metadata(value, counts, max_bytes, depth=0):
    counts[0] += 1
    if depth > 12 or counts[0] > 10000:
        raise ValueError("finite plan structure limit")
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str or _secret_key(key):
                raise ValueError("secret-bearing plan settings are forbidden")
            counts[1] += len(key)
            _safe_metadata(child, counts, max_bytes, depth + 1)
    elif type(value) is list:
        for child in value:
            _safe_metadata(child, counts, max_bytes, depth + 1)
    elif value is not None and type(value) not in (str, int, bool):
        raise ValueError("typed plan metadata required")
    elif type(value) is str:
        counts[1] += len(value)
        parsed = urlsplit(value) if "://" in value else None
        if parsed and (
            parsed.username is not None
            or parsed.password is not None
            or any(_secret_key(key) for key, _ in parse_qsl(parsed.query))
        ):
            raise ValueError("secret-bearing transport URL is forbidden")
    if counts[1] > max_bytes:
        raise ValueError("finite plan text limit")


class FrozenAcquisitionPlan:
    def __init__(self, ledger, *, max_bytes=1024 * 1024, max_sources=1000):
        for value in (max_bytes, max_sources):
            if type(value) is not int or value <= 0:
                raise ValueError("positive finite plan bounds required")
        self.ledger, self.max_bytes, self.max_sources = ledger, max_bytes, max_sources
        self.directory = ledger.work_ledger._path.parent

    def _validate(self, sources, credential_refs):
        if type(sources) is not list or not sources or len(sources) > self.max_sources:
            raise ValueError("a finite nonempty ordered source list is required")
        seen, counts = set(), [0, 0]
        for source in sources:
            if type(source) is not dict or set(source) != {
                "source_registration_uuidv4",
                "kind",
                "settings",
            }:
                raise ValueError("exact typed source plan required")
            ident = uuid4_value(source["source_registration_uuidv4"])
            if (
                ident in seen
                or type(source["kind"]) is not str
                or not source["kind"]
                or type(source["settings"]) is not dict
            ):
                raise ValueError("distinct source registrations and settings required")
            seen.add(ident)
            _safe_metadata(source["settings"], counts, self.max_bytes)
        if type(credential_refs) is not dict or not set(credential_refs) <= seen:
            raise ValueError(
                "credential references must name selected source registrations"
            )
        for reference in credential_refs.values():
            if (
                type(reference) is not dict
                or set(reference) != {"kind", "name"}
                or reference["kind"] not in _REFERENCE_KINDS
                or type(reference["name"]) is not str
            ):
                raise ValueError("explicit credential reference kind/name required")
            pattern = (
                r"[A-Za-z_][A-Za-z0-9_]{0,127}"
                if reference["kind"] == "environment"
                else r"[A-Za-z_][A-Za-z0-9_.:-]{0,127}"
            )
            if not re.fullmatch(pattern, reference["name"]):
                raise ValueError("credible named credential reference required")
        raw = encode({"sources": sources, "credential_refs": credential_refs})
        if len(raw) > self.max_bytes:
            raise ValueError("finite frozen plan byte limit")
        return raw

    def _stop(self):
        if (self.directory / "p1-recovery-stop.json").exists():
            raise CoordinationError("RECOVERY_REQUIRED", "catalog")

    @contextmanager
    def _checked(self, request, *, write=False):
        self._stop()
        with catalog_gate(self.directory, exclusive=write), ExitStack() as completion:
            with self.ledger.work_ledger._checked(request, write=write) as checkpoint:
                yield checkpoint
                completion.enter_context(catalog_completion(self.directory))
                self._stop()
                work = self.ledger.work_ledger
                if work._stat_identity() != work._file_identity:
                    raise CoordinationError("CONTINUATION_UNAVAILABLE", "plan")

    def _stored(self, request):
        row = self.ledger.db.execute(
            "SELECT octet_length(cursor_json) FROM request_continuations WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json=?",
            (*request.values(), _SCOPE),
        ).fetchone()
        if row is None:
            return None
        if type(row[0]) is not int or not 0 <= row[0] <= self.max_bytes:
            raise CoordinationError("CONTINUATION_UNAVAILABLE", "plan")
        raw = self.ledger.db.execute(
            "SELECT cursor_json FROM request_continuations WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json=?",
            (*request.values(), _SCOPE),
        ).fetchone()[0]
        try:
            plan = json.loads(raw)
            if (
                type(plan) is not dict
                or set(plan) != {"sources", "credential_refs"}
                or self._validate(plan["sources"], plan["credential_refs"]) != raw
            ):
                raise ValueError("invalid frozen plan")
            return plan
        except (ValueError, TypeError, KeyError) as error:
            raise CoordinationError("CONTINUATION_UNAVAILABLE", "plan") from error

    def freeze(self, request, sources, credential_refs):
        """Keep the first canonical plan, across attempts/resume and caller edits."""
        raw = self._validate(sources, credential_refs)
        with self._checked(request, write=True) as checkpoint:
            previous = self._stored(request)
            if previous is not None:
                return previous
            self.ledger.work_ledger._put_continuation(request, checkpoint, _SCOPE, raw)
            return json.loads(raw)

    def load(self, request):
        with self._checked(request):
            value = self._stored(request)
            if value is None:
                raise CoordinationError("CONTINUATION_UNAVAILABLE", "plan")
            return value
