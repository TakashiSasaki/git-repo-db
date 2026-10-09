"""Supplementary HTTP message capture, separate from the domain datastore.

Bodies are exact HTTP content-decoded bytes returned by the transport. This is
not a wire capture: request bodies are omitted and metadata uses a whitelist.
Entries have no retention policy and are never prerequisites for domain reads.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from repo_catalog.domain.time import validate_epoch_us

MAX_BODY_BYTES = 32 * 1024 * 1024
MAX_METADATA_BYTES = 64 * 1024
BODY_REPRESENTATION = "http-content-decoded-v1"
_REQUEST_HEADERS = frozenset(
    {
        "accept",
        "user-agent",
        "x-github-api-version",
        "if-none-match",
        "if-modified-since",
    }
)
_RESPONSE_HEADERS = frozenset(
    {
        "content-type",
        "content-encoding",
        "content-length",
        "etag",
        "last-modified",
        "date",
        "x-github-request-id",
        "x-github-api-version-selected",
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-used",
        "x-ratelimit-reset",
        "x-ratelimit-resource",
        "retry-after",
    }
)
_URL_PARAMETERS = frozenset({"page", "per_page", "state", "sort", "direction", "since"})
_HINTS = frozenset(
    {
        "provider_request_kind",
        "owner",
        "repository",
        "pr_number",
        "issue_number",
        "collection_scope",
        "service_instance_uuidv4",
        "repository_uuidv4",
    }
)


class RecordingError(Exception):
    """Expected capture/read failure that cannot invalidate domain data."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class MessageRecorder(Protocol):
    def record_exchange(self, context: Mapping, body: bytes | None) -> str | None: ...


class DisabledRecorder:
    def record_exchange(self, context, body):
        return None


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate archive metadata key")
        result[key] = value
    return result


def _headers(values, allowed):
    if not isinstance(values, Mapping):
        raise RecordingError("ARCHIVE_FORMAT", "Header context must be a mapping")
    result = {}
    redacted = False
    for name, value in values.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise RecordingError("ARCHIVE_FORMAT", "Header context must contain text")
        if name.lower() in allowed:
            result[name.lower()] = value
        else:
            redacted = True
    return result, redacted


def _url(value):
    if not isinstance(value, str):
        raise RecordingError("ARCHIVE_FORMAT", "Request URL must be text")
    try:
        parsed = urlsplit(value)
        # Accessing port also validates the parsed authority.
        port = parsed.port
        hostname = parsed.hostname
        if parsed.scheme not in ("http", "https") or not hostname:
            raise ValueError()
        authority = "[" + hostname + "]" if ":" in hostname else hostname
        if port is not None:
            authority += ":" + str(port)
        redacted = bool(parsed.username or parsed.password or parsed.fragment)
        parameters = []
        for name, text in parse_qsl(parsed.query, keep_blank_values=True):
            if name in _URL_PARAMETERS:
                parameters.append((name, text))
            else:
                parameters.append((name, "[REDACTED]"))
                redacted = True
        return urlunsplit(
            (parsed.scheme, authority, parsed.path, urlencode(parameters), "")
        ), redacted
    except ValueError as error:
        raise RecordingError("ARCHIVE_FORMAT", "Invalid request URL") from error


def safe_exchange_context(context):
    """Drop unlisted metadata; mark redaction without changing response bytes."""
    if not isinstance(context, Mapping):
        raise RecordingError("ARCHIVE_FORMAT", "Exchange context must be a mapping")
    try:
        observed = validate_epoch_us(context["observed_at_us"])
        attempt = context["attempt"]
        if type(attempt) is not int or attempt < 1:
            raise ValueError()
        method = context["method"]
        if method not in ("GET", "POST"):
            raise ValueError()
        url, url_redacted = _url(context["url"])
        request_headers, request_redacted = _headers(
            context.get("request_headers", {}), _REQUEST_HEADERS
        )
        response_headers, response_redacted = _headers(
            context.get("response_headers", {}), _RESPONSE_HEADERS
        )
        result = {
            "observed_at_us": observed,
            "attempt": attempt,
            "method": method,
            "url": url,
            "request_headers": request_headers,
            "response_headers": response_headers,
            "metadata_redacted": url_redacted or request_redacted or response_redacted,
        }
        if "metadata_redacted" in context:
            if type(context["metadata_redacted"]) is not bool:
                raise ValueError()
            result["metadata_redacted"] |= context["metadata_redacted"]
        status = context.get("response_status")
        if status is not None:
            if type(status) is not int or not 100 <= status <= 599:
                raise ValueError()
            result["response_status"] = status
        failure = context.get("failure_code")
        if failure is not None:
            if failure not in (
                "API_NETWORK",
                "API_RESPONSE_LIMIT",
                "CANCELLED",
                "API_PROTOCOL",
            ):
                raise ValueError()
            result["failure_code"] = failure
        if status is None and failure is None:
            raise ValueError()
        hints = context.get("provider_context", {})
        if not isinstance(hints, Mapping):
            raise ValueError()
        accepted = {}
        for key in _HINTS & hints.keys():
            value = hints[key]
            if key in ("pr_number", "issue_number"):
                if type(value) is not int or not 1 <= value < 1 << 63:
                    raise ValueError()
            elif not isinstance(value, str) or len(value) > 4096:
                raise ValueError()
            accepted[key] = value
        if accepted:
            result["provider_context"] = accepted
        return result
    except (KeyError, TypeError, ValueError) as error:
        raise RecordingError("ARCHIVE_FORMAT", "Invalid exchange context") from error


def recorder_from_config(config, state_dir):
    """Engineering default: disabled; enabled captures use a local subdirectory."""
    if not config.get("record_messages", False):
        return DisabledRecorder()
    return LocalFileRecorder(Path(state_dir) / "transport-archive")


class LocalFileRecorder:
    """Append private files, publishing metadata only after durable body writes."""

    def __init__(self, path):
        self.path = Path(path)

    def record_exchange(self, context, body):
        context = safe_exchange_context(context)
        if body is None and "failure_code" not in context:
            raise RecordingError(
                "ARCHIVE_FORMAT", "Absent body requires a transport failure"
            )
        if body is not None and (
            not isinstance(body, bytes) or len(body) > MAX_BODY_BYTES
        ):
            raise RecordingError(
                "ARCHIVE_LIMIT", "Capture exceeds the bounded body limit"
            )
        reference = str(uuid.uuid4())
        envelope = {
            "archive_version": 1,
            "reference": reference,
            "body_representation": BODY_REPRESENTATION,
            "context": context,
            "body_length": len(body) if body is not None else None,
            "body_sha256": hashlib.sha256(body).hexdigest()
            if body is not None
            else None,
        }
        encoded = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
        if len(encoded) > MAX_METADATA_BYTES:
            raise RecordingError("ARCHIVE_LIMIT", "Capture metadata exceeds its limit")
        try:
            self.path.mkdir(mode=0o700, parents=True, exist_ok=True)
            if body is not None:
                self._write(self.path / (reference + ".body"), body)
            temporary = self.path / (reference + ".json.tmp")
            self._write(temporary, encoded)
            # Metadata is the publication marker. A failed write never replaces
            # an existing entry; incomplete local files have no valid reference.
            os.link(temporary, self.path / (reference + ".json"))
            temporary.unlink()
            directory_fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as error:
            raise RecordingError(
                "ARCHIVE_IO", "Cannot persist supplementary capture"
            ) from error
        return reference

    @staticmethod
    def _write(path, data):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())


@dataclass(frozen=True)
class ArchivedExchange:
    reference: str
    context: dict
    body: bytes | None
    body_representation: str = BODY_REPRESENTATION


class MessageArchiveReader(Protocol):
    def read(
        self, reference: str, *, max_body_bytes=MAX_BODY_BYTES
    ) -> ArchivedExchange: ...


class LocalArchiveReader:
    """Read one explicitly selected message with fixed memory and integrity bounds."""

    def __init__(self, path):
        self.path = Path(path)

    def read(self, reference, *, max_body_bytes=MAX_BODY_BYTES):
        try:
            if (
                str(uuid.UUID(reference)) != reference
                or uuid.UUID(reference).version != 4
            ):
                raise ValueError()
            if (
                type(max_body_bytes) is not int
                or not 0 <= max_body_bytes <= MAX_BODY_BYTES
            ):
                raise ValueError()
        except (ValueError, TypeError, AttributeError) as error:
            raise RecordingError(
                "ARCHIVE_ARGUMENT", "Invalid archive reference or read bound"
            ) from error
        try:
            metadata = self._read_file(reference + ".json", MAX_METADATA_BYTES)
            envelope = json.loads(metadata, object_pairs_hook=_unique_json_object)
            if (
                not isinstance(envelope, dict)
                or set(envelope)
                != {
                    "archive_version",
                    "reference",
                    "body_representation",
                    "context",
                    "body_length",
                    "body_sha256",
                }
                or type(envelope.get("archive_version")) is not int
                or envelope["archive_version"] != 1
                or envelope.get("reference") != reference
                or envelope.get("body_representation") != BODY_REPRESENTATION
            ):
                raise ValueError()
            context = envelope["context"]
            try:
                safe = safe_exchange_context(context)
            except RecordingError as error:
                raise RecordingError(
                    "ARCHIVE_CORRUPT", "Archived exchange context is invalid"
                ) from error
            # Stored redaction is a permanent label, even when rechecking the
            # already-filtered context no longer sees the removed metadata.
            if type(context.get("metadata_redacted")) is not bool:
                raise ValueError()
            safe["metadata_redacted"] = context["metadata_redacted"]
            if safe != context:
                raise ValueError()
            length, digest = envelope["body_length"], envelope["body_sha256"]
            if length is None:
                if digest is not None or "failure_code" not in context:
                    raise ValueError()
                body = None
            else:
                if type(length) is not int or length < 0:
                    raise ValueError()
                if length > max_body_bytes:
                    raise RecordingError(
                        "ARCHIVE_LIMIT", "Archived body exceeds the read bound"
                    )
                body = self._read_file(reference + ".body", max_body_bytes)
                if len(body) != length or hashlib.sha256(body).hexdigest() != digest:
                    raise ValueError()
            return ArchivedExchange(reference, context, body)
        except FileNotFoundError as error:
            raise RecordingError(
                "ARCHIVE_MISSING", "Supplementary message is unavailable"
            ) from error
        except OSError as error:
            raise RecordingError(
                "ARCHIVE_IO", "Cannot read supplementary message"
            ) from error
        except (
            ValueError,
            KeyError,
            TypeError,
            UnicodeDecodeError,
            RecursionError,
        ) as error:
            raise RecordingError(
                "ARCHIVE_CORRUPT", "Supplementary message failed validation"
            ) from error

    def _read_file(self, name, limit):
        fd = os.open(self.path / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise RecordingError(
                    "ARCHIVE_CORRUPT", "Archive entry is not a regular file"
                )
            content = stream.read(limit + 1)
            if len(content) > limit:
                raise RecordingError(
                    "ARCHIVE_LIMIT", "Archive entry exceeds the read bound"
                )
            return content
