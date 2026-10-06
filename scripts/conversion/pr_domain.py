"""Streaming stored API/PR conversion; no acquisition or current-pointer writes.

Each recipe is a source-owned decision. Saved-page replay repairs only supported
normalization gaps and keeps the page's observation time separate from parsing.
"""

import hashlib
import math
import re
import struct
import uuid
from urllib.parse import urlsplit

from scripts.schema_contract import tagged_key

from . import identity
from .common import ConversionError, canonical, strict_json

VERSION = "integrated-pr/1"
# Match the operational HTTP transport decoded-response limit without importing
# application code into the guarded converter. This bounds decoder input, not
# Python object or derived-operation memory. Exact source bytes remain admitted.
MAX_SAVED_REPLAY_BYTES = 32 * 1024 * 1024
RECIPES = (
    "jobs",
    "inventory_observations",
    "payloads",
    "change_requests",
    "resume_scopes",
    "fetch_collections",
    "fetch_occurrences",
    "change_request_observations",
    "documents",
    "document_versions",
    "document_observations",
    "saved_pr_document_repair",
    "reviews",
    "review_threads",
    "review_comments",
    "change_request_events",
    "collection_memberships",
    "saved_document_repair",
    "sync_checkpoints",
    "code_listings",
    "code_commits",
    "code_file_changes",
    "saved_listing_repair",
    "code_listing_completion",
    "code_observations",
    "code_acquisitions",
)
SOURCE_TABLES = {
    "inventory_observations": "inventory_runs",
    "payloads": "api_responses",
    "change_requests": "pull_requests",
    "resume_scopes": "collections",
    "fetch_collections": "collections",
    "fetch_occurrences": "collection_pages",
    "change_request_observations": "pr_observations",
    "documents": "pr_documents",
    "document_observations": "resource_observations",
    "saved_pr_document_repair": "pr_observations",
    "reviews": "pr_reviews",
    "change_request_events": "pr_events",
    "saved_document_repair": "collection_pages",
    "code_listings": "pr_code_observations",
    "code_commits": "pr_commits",
    "code_file_changes": "pr_file_changes",
    "saved_listing_repair": "collection_pages",
    "code_listing_completion": "pr_code_observations",
    "code_observations": "pr_code_observations",
    "code_acquisitions": "pr_git_links",
}
COLUMNS = {
    "jobs": ("id", "kind", "request", "current_attempt", "created_at"),
    "job_attempts": (
        "job_id",
        "attempt",
        "state",
        "created_at",
        "updated_at",
        "not_before",
        "checkpoint",
        "reason",
    ),
    "inventory_observations": (
        "id",
        "source_id",
        "asserted_state",
        "scope",
        "observed_at",
        "reason",
    ),
    "payloads": ("id", "sha256", "body", "byte_length", "representation"),
    "change_requests": (
        "id",
        "repo_id",
        "binding_id",
        "request_kind",
        "number",
        "current_observation_id",
        "node_id",
    ),
    "resume_scopes": (
        "id",
        "repo_id",
        "binding_id",
        "source_id",
        "principal_ref",
        "api_version",
        "endpoint",
        "request_context",
        "parser_version",
        "profile_version",
        "confidence",
    ),
    "fetch_collections": (
        "id",
        "repo_id",
        "change_request_id",
        "source_id",
        "kind",
        "scope_id",
        "observed_at",
    ),
    "collection_progress": (
        "collection_id",
        "job_id",
        "attempt",
        "state",
        "cursor",
        "reason",
    ),
    "fetch_occurrences": (
        "id",
        "collection_id",
        "ordinal",
        "payload_id",
        "request",
        "next_cursor",
        "observed_at",
        "parsed_at",
    ),
    "change_request_observations": (
        "id",
        "change_request_id",
        "observed_at",
        "published",
        "payload",
        "origin_key",
        "parsed_at",
        "origin_occurrence_id",
    ),
    "text_bodies": ("id", "body", "byte_length", "sha256"),
    "documents": (
        "id",
        "change_request_id",
        "kind",
        "provider_id",
        "current_version_id",
        "deleted",
        "node_id",
        "author",
        "url",
        "metadata",
    ),
    "document_versions": ("id", "document_id", "body_id", "legacy_body_sha256"),
    "document_observations": (
        "id",
        "document_id",
        "version_id",
        "observed_at",
        "parsed_at",
        "origin_key",
        "occurrence_id",
        "metadata",
    ),
    "reviews": ("id", "change_request_id", "document_id", "payload"),
    "review_threads": ("id", "change_request_id", "payload", "observed_at"),
    "review_comments": ("document_id", "change_request_id", "thread_id", "payload"),
    "change_request_events": (
        "id",
        "change_request_id",
        "origin_key",
        "ordinal",
        "provider_id",
        "payload",
        "observed_at",
    ),
    "collection_memberships": ("collection_id", "document_id", "ordinal"),
    "unresolved_payloads": ("id", "payload_id", "legacy_record_id", "reason"),
    "validators": ("scope_id", "validator_key", "etag", "payload_id", "validated_at"),
    "incremental_scans": (
        "id",
        "scope_id",
        "collection_id",
        "scan_started_at",
        "safe_watermark",
        "evidence",
    ),
    "resume_cursors": ("scope_id", "scan_id", "next_cursor", "reusable"),
    "completion_markers": (
        "id",
        "scope_id",
        "collection_id",
        "asserted_state",
        "evidence",
        "observed_at",
    ),
    "code_listings": (
        "id",
        "change_request_id",
        "collection_id",
        "kind",
        "scope_id",
        "object_format",
        "head_oid",
        "base_oid",
    ),
    "code_listing_progress": (
        "listing_id",
        "state",
        "terminal",
        "page_count",
        "context_proven",
    ),
    "code_commits": (
        "listing_id",
        "occurrence_id",
        "position",
        "object_format",
        "oid",
        "payload",
    ),
    "code_file_changes": (
        "listing_id",
        "occurrence_id",
        "position",
        "raw_path",
        "payload",
    ),
    "code_observations": (
        "id",
        "change_request_id",
        "observation_id",
        "commit_listing_id",
        "file_listing_id",
        "state",
        "object_format",
        "head_oid",
        "base_oid",
        "details",
    ),
    "code_acquisitions": (
        "code_observation_id",
        "role",
        "object_format",
        "oid",
        "root_id",
    ),
}
KEYS = {
    "job_attempts": ("job_id", "attempt"),
    "collection_progress": ("collection_id",),
    "review_comments": ("document_id",),
    "collection_memberships": ("collection_id", "document_id"),
    "validators": ("scope_id", "validator_key"),
    "resume_cursors": ("scope_id",),
    "code_listing_progress": ("listing_id",),
    "code_commits": ("listing_id", "occurrence_id", "position"),
    "code_file_changes": ("listing_id", "occurrence_id", "position"),
    "code_acquisitions": ("code_observation_id", "role"),
}
DOCUMENT_KINDS = {
    "comments": "issue-comment",
    "issue-comments": "issue-comment",
    "issue-comment": "issue-comment",
    "issue-comment-incremental": "issue-comment",
    "review-comments": "review-comment",
    "review-comment": "review-comment",
    "review-comment-incremental": "review-comment",
    "reviews": "review",
    "review": "review",
}


def stable_id(namespace, *parts, integer=False):
    encoded = canonical([VERSION, namespace, list(parts)])
    if integer:
        return (
            int.from_bytes(hashlib.sha256(encoded.encode()).digest()[:8], "big")
            & ((1 << 62) - 1)
        ) + (1 << 62)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, encoded))


def target_key(table, row):
    cells = [row[COLUMNS[table].index(key)] for key in KEYS.get(table, ("id",))]
    return tagged_key(
        [
            ("integer", value)
            if isinstance(value, int)
            else ("blob", value)
            if isinstance(value, bytes)
            else ("text", value.encode("utf-8"))
            for value in cells
        ]
    )


def selected_text_ranges(value, fields):
    """Locate only final selected top-level string tokens without a JSON DOM."""
    selected, depth, key, expect_key, offset = {}, 0, None, False, 0
    maximum_key = 2 + 6 * max(map(len, fields))
    while offset < len(value):
        char = value[offset]
        if char == '"':
            end = value.find('"', offset + 1)
            while end >= 0:
                previous = end - 1
                while previous >= offset and value[previous] == "\\":
                    previous -= 1
                if (end - previous - 1) % 2 == 0:
                    break
                end = value.find('"', end + 1)
            if end < 0:
                raise ValueError("Validated JSON string has no end")
            if depth == 1:
                if expect_key:
                    parsed = (
                        strict_json(value[offset : end + 1])
                        if end + 1 - offset <= maximum_key
                        else None
                    )
                    key = parsed if parsed in fields else None
                    if key is not None:
                        selected[key] = None
                    expect_key = False
                elif key is not None:
                    selected[key] = (offset + 1, end)
                    key = None
            offset = end + 1
            continue
        if char in "[{":
            depth += 1
            if depth == 1:
                expect_key = True
        elif char in "]}":
            depth -= 1
            if depth == 1:
                key = None
        elif char == "," and depth == 1:
            expect_key, key = True, None
        offset += 1
    return selected


def paired_unicode_escapes(value, start, end):
    """Accept escaped backslashes and paired surrogates; reject lone units."""
    offset = start
    while (offset := value.find("\\", offset, end)) >= 0:
        if value[offset + 1] != "u":
            offset += 2
            continue
        unit = int(value[offset + 2 : offset + 6], 16)
        if 0xD800 <= unit <= 0xDBFF:
            if offset + 12 > end or value[offset + 6 : offset + 8] != "\\u":
                return False
            low = int(value[offset + 8 : offset + 12], 16)
            if not 0xDC00 <= low <= 0xDFFF:
                return False
            offset += 12
        elif 0xDC00 <= unit <= 0xDFFF:
            return False
        else:
            offset += 6
    return True


class Invalid(identity.Invalid):
    def __init__(self, code, column):
        super().__init__("PR_" + code.removeprefix("PR_"), column)


class Context(identity.Context):
    def __init__(self, db, src, run, encoding="UTF-8", *, verifying=False):
        super().__init__(db, src, run, encoding, verifying=verifying)
        self.parsed_at = run["started_at"]
        self._attribution_page = None
        self._attribution = {}
        self._attribution_error = None

    def metadata(self, record, column="metadata"):
        storage, raw = record.value(column)
        if storage != "text" or len(raw) <= MAX_SAVED_REPLAY_BYTES:
            try:
                return super().metadata(record, column)
            except RecursionError:
                # A source object within SQLite's accepted JSON depth can
                # exceed the Python decoder's depth in the current call stack.
                # Keep that direct fact; semantic replay remains bounded below.
                pass
        # Direct normalized facts still preserve a large, valid object exactly.
        # SQLite validates shape without constructing a Python JSON graph.
        value = self.t(record, column)
        valid = self.src.execute(
            "SELECT CASE WHEN json_valid(?) THEN json_type(?)='object' ELSE 0 END",
            (value, value),
        ).fetchone()[0]
        if not valid:
            raise Invalid("INVALID_JSON", column)
        return value

    def selected_metadata(self, record, column, fields):
        """Extract needed scalars with json.loads' last duplicate-key behavior.

        json_extract chooses the first duplicate. json_each exposes keys in
        source order; retain the last selected key and only materialize text.
        Object/array/numeric values retain a type tag for semantic validation.
        """
        value = self.metadata(record, column)
        if self.encoding.upper().startswith("UTF-16"):
            for span in selected_text_ranges(value, fields).values():
                if span is not None and not paired_unicode_escapes(value, *span):
                    raise Invalid("MALFORMED_TEXT", column)
        selected = {}
        placeholders = ",".join("?" for _ in fields)
        for key, kind, scalar in self.src.execute(
            "SELECT key,type,CASE WHEN type='text' THEN CAST(atom AS BLOB) ELSE NULL END "
            f"FROM json_each(?) WHERE key IN ({placeholders}) ORDER BY id",
            (value, *fields),
        ):
            selected[key] = (kind, scalar)
        for key, (kind, scalar) in selected.items():
            if kind == "text":
                try:
                    scalar = scalar.decode(self.encoding)
                except UnicodeError:
                    raise Invalid("MALFORMED_TEXT", column) from None
                selected[key] = (kind, scalar)
        return value, selected

    def decoded_metadata(self, record, column="metadata"):
        storage, raw = record.value(column)
        if storage == "text" and len(raw) > MAX_SAVED_REPLAY_BYTES:
            raise Invalid("REPLAY_BUDGET_EXCEEDED", column)
        value = self.t(record, column)
        try:
            parsed = strict_json(value)
            if not isinstance(parsed, dict):
                raise ValueError()
        except RecursionError:
            raise Invalid("JSON_DEPTH_UNSUPPORTED", column) from None
        except ValueError:
            raise Invalid("INVALID_JSON", column) from None
        return parsed

    def i(self, record, column, *, minimum=None, choices=None):
        kind, raw = record.value(column)
        if kind != "integer":
            raise Invalid("INVALID_TYPE", column)
        value = int(raw)
        if (
            minimum is not None
            and value < minimum
            or choices is not None
            and value not in choices
        ):
            raise Invalid("INVALID_VALUE", column)
        return value

    def blob(self, record, column, *, length=None):
        kind, raw = record.value(column)
        if kind != "blob" or length is not None and len(raw) != length:
            raise Invalid("INVALID_BLOB", column)
        return raw

    def ref(self, source_table, *key):
        value = self.lookup(source_table, *key)
        if value is None:
            raise Invalid("MISSING_REFERENCE", source_table)
        return value

    def ensure_repo(self, repo):
        row = self.ref("repositories", repo)
        identity.Context.project(self, "repositories", row)
        return row

    def binding(self, repo):
        row = self.ensure_repo(repo)
        source = self.ref("sources", self.t(row, "source_id"))
        instance = self.t(source, "instance_id", nullable=True)
        if instance is None:
            raise Invalid("MISSING_BINDING", "repo_id")
        record = self.ref("repository_bindings", repo, instance)
        # The previous owner allocated and proved this identity. Require its
        # immutable mapping rather than choosing a target row by current values.
        identity.Context.project(self, "repository_bindings", record, allocate=False)
        return self.binding_id(record)

    def pr(self, ident):
        record = self.ref("pull_requests", ident)
        return self.pr_row(record)

    def pr_row(self, record):
        repo = self.t(record, "repo_id", nonempty=True)
        return (
            self.t(record, "id", nonempty=True),
            repo,
            self.binding(repo),
            "pull_request",
            self.i(record, "number", minimum=1),
            None,
            self.t(record, "node_id", nullable=True),
        )

    def source(self, repo):
        return self.t(self.ensure_repo(repo), "source_id")

    def scope_id(self, collection):
        return stable_id("scope", self.t(collection, "id"))

    def occurrence_id(self, collection, ordinal):
        return stable_id("occurrence", collection, ordinal, integer=True)

    def page_data(self, page):
        response = self.ref("api_responses", self.i(page, "response_id", minimum=1))
        raw = self.blob(response, "body")
        if len(raw) > MAX_SAVED_REPLAY_BYTES:
            raise Invalid("REPLAY_BUDGET_EXCEEDED", "response_id")
        if hashlib.sha256(raw).digest() != self.blob(
            response, "payload_sha256", length=32
        ):
            raise Invalid("PAYLOAD_DIGEST_MISMATCH", "payload_sha256")
        try:
            return strict_json(raw.decode("utf-8"))
        except RecursionError:
            raise Invalid("JSON_DEPTH_UNSUPPORTED", "response_id") from None
        except (ValueError, UnicodeError):
            raise Invalid("MALFORMED_PAYLOAD", "body") from None

    def pages(self, collection):
        for row in self.src.execute(
            "SELECT ordinal FROM collection_pages WHERE collection_id=? ORDER BY ordinal",
            (collection,),
        ):
            yield self.ref("collection_pages", collection, row[0])

    def scope_row(self, collection):
        repo = self.t(collection, "repo_id")
        source = self.source(repo)
        scope_text, scope = self.selected_metadata(
            collection, "scope", ("repo_id", "principal", "api_version")
        )
        if "repo_id" in scope and scope["repo_id"] != ("text", repo):
            raise Invalid("SCOPE_OWNER_MISMATCH", "scope")
        pr = self.t(collection, "pr_id", nullable=True)
        binding = self.pr(pr)[2] if pr else None
        endpoint, parser = None, "legacy_unknown"
        first = next(self.pages(self.t(collection, "id")), None)
        if first:
            _, request = self.selected_metadata(
                first, "request", ("url", "parser_version")
            )
            url_kind, url = request.get("url", ("null", None))
            parser_kind, parser_value = request.get("parser_version", ("null", None))
            endpoint = url if url_kind == "text" else None
            parser = parser_value if parser_kind == "text" else parser
        principal_kind, principal = scope.get("principal", ("null", None))
        version_kind, version = scope.get("api_version", ("null", None))
        if principal_kind not in ("text", "null") or version_kind not in (
            "text",
            "null",
        ):
            raise Invalid("INVALID_SCOPE", "scope")
        return (
            self.scope_id(collection),
            repo,
            binding,
            source,
            principal,
            version,
            endpoint,
            scope_text,
            parser,
            "legacy_unknown",
            "legacy_unknown",
        )

    def job_rows(self, record):
        ident, attempt = self.t(record, "id"), self.i(record, "attempt", minimum=1)
        kind = self.t(record, "kind")
        if kind not in ("discover", "sync", "hydrate", "index", "legacy"):
            kind = "legacy"
        state = self.t(record, "state")
        if state not in (
            "queued",
            "running",
            "waiting",
            "complete",
            "failed",
            "interrupted",
            "cancelled",
            "unknown",
        ):
            state = "unknown"
        storage, raw = record.value("not_before")
        if storage == "null":
            not_before = None
        elif storage == "real":
            not_before = struct.unpack(">d", raw)[0]
        elif storage == "integer":
            not_before = float(int(raw))
        else:
            raise Invalid("INVALID_TYPE", "not_before")
        if not_before is not None and (
            not math.isfinite(not_before) or not 0 <= not_before < 1e308
        ):
            raise Invalid("INVALID_VALUE", "not_before")
        created, updated = (
            self.timestamp(record, "created_at"),
            self.timestamp(record, "updated_at"),
        )
        return (
            (ident, kind, self.metadata(record, "request"), None, created),
            (
                ident,
                attempt,
                state,
                created,
                updated,
                not_before,
                self.metadata(record, "checkpoint"),
                self.t(record, "reason", nullable=True),
            ),
        )

    def collection_row(self, record):
        repo = self.t(record, "repo_id")
        self.scope_row(record)
        pr = self.t(record, "pr_id", nullable=True)
        if pr and self.pr(pr)[1] != repo:
            raise Invalid("OWNER_MISMATCH", "pr_id")
        return (
            self.t(record, "id"),
            repo,
            pr,
            self.source(repo),
            self.t(record, "kind"),
            self.scope_id(record),
            self.timestamp(record, "observed_at"),
        )

    def occurrence_row(self, record, *, collection_id=None, occurrence_id=None):
        cid, ordinal = (
            self.t(record, "collection_id"),
            self.i(record, "ordinal", minimum=0),
        )
        self.collection_row(self.ref("collections", cid))
        response = self.ref("api_responses", self.i(record, "response_id", minimum=1))
        raw = self.blob(response, "body")
        if hashlib.sha256(raw).digest() != self.blob(
            response, "payload_sha256", length=32
        ):
            raise Invalid("PAYLOAD_DIGEST_MISMATCH", "response_id")
        return (
            occurrence_id or self.occurrence_id(cid, ordinal),
            collection_id or cid,
            ordinal,
            self.i(record, "response_id"),
            self.metadata(record, "request"),
            self.t(record, "next_cursor", nullable=True),
            self.timestamp(record, "observed_at"),
            self.parsed_at,
        )

    def document_row(self, record):
        pr = self.t(record, "pr_id")
        self.pr(pr)
        return (
            self.t(record, "id"),
            pr,
            self.t(record, "kind", nonempty=True),
            self.t(record, "provider_id", nonempty=True),
            None,
            self.i(record, "deleted", choices=(0, 1)),
            self.t(record, "node_id", nullable=True),
            self.t(record, "author", nullable=True),
            self.t(record, "url", nullable=True),
            self.metadata(record),
        )

    def version_row(self, record):
        document = self.t(record, "document_id")
        self.document_row(self.ref("pr_documents", document))
        body, legacy_sha = (
            self.t(record, "body"),
            self.blob(record, "body_sha256", length=32),
        )
        return (
            self.i(record, "id", minimum=1),
            document,
            stable_id("body", body, integer=True),
            legacy_sha,
        )

    def body_row(self, body):
        raw = body.encode("utf-8")
        return (
            stable_id("body", body, integer=True),
            body,
            len(raw),
            hashlib.sha256(raw).digest(),
        )

    def thread_identity(self, pr, provider):
        existing = self.lookup("review_threads", provider)
        if existing and self.t(existing, "pr_id") == pr:
            return provider
        found = []
        for saved in self.src.execute(
            "SELECT id FROM review_threads WHERE pr_id=?", (pr,)
        ):
            record = self.ref("review_threads", saved[0])
            try:
                if self.decoded_metadata(record, "payload").get("id") == provider:
                    found.append(saved[0])
            except identity.Invalid:
                continue
        if len(found) > 1:
            raise Invalid("THREAD_IDENTITY_CONFLICT", "body")
        return found[0] if found else f"{pr}:thread:{provider}"

    def first_saved_thread_snapshot(self, pr, provider):
        for saved in self.src.execute(
            "SELECT id FROM collections WHERE pr_id=? AND kind='threads' ORDER BY id",
            (pr,),
        ):
            for page in self.pages(saved[0]):
                try:
                    self.occurrence_row(page)
                    payload = self.page_data(page)
                    if not isinstance(payload, dict):
                        continue
                    data = payload.get("data") or {}
                    connection = (
                        (data.get("repository") or {}).get("pullRequest") or {}
                    ).get("reviewThreads") or {}
                    nodes = connection.get("nodes") or []
                    node = data.get("node")
                    if isinstance(node, dict) and node.get("id") == provider:
                        nodes = [*nodes, node]
                    for thread in nodes:
                        if isinstance(thread, dict) and thread.get("id") == provider:
                            return canonical(
                                {
                                    key: value
                                    for key, value in thread.items()
                                    if key != "comments"
                                }
                            ), self.timestamp(page, "observed_at")
                except (identity.Invalid, ValueError, TypeError, KeyError):
                    continue
        raise Invalid("THREAD_REFERENCE_UNRESOLVED", "response_id")

    def page_documents(self, page):
        collection = self.ref("collections", self.t(page, "collection_id"))
        kind, pr = (
            self.t(collection, "kind"),
            self.t(collection, "pr_id", nullable=True),
        )
        payload = self.page_data(page)
        if kind == "threads":
            if not isinstance(payload, dict):
                raise Invalid("MALFORMED_PAYLOAD", "body")
            data = payload.get("data") or {}
            request = self.decoded_metadata(page, "request")
            variables = request.get("variables") or {}
            threads = ((data.get("repository") or {}).get("pullRequest") or {}).get(
                "reviewThreads"
            ) or {}
            for thread in threads.get("nodes") or []:
                provider = thread.get("id")
                if not isinstance(provider, str):
                    raise Invalid("INVALID_SAVED_IDENTITY", "body")
                tid = self.thread_identity(pr, provider)
                for position, value in enumerate(
                    (thread.get("comments") or {}).get("nodes") or []
                ):
                    yield pr, "review-comment", value, position, tid
            if "node" in data and "thread" in variables:
                provider = variables["thread"]
                tid = self.thread_identity(pr, provider)
                for position, value in enumerate(
                    (data.get("node") or {}).get("comments", {}).get("nodes") or []
                ):
                    yield pr, "review-comment", value, position, tid
        elif kind in DOCUMENT_KINDS:
            if not isinstance(payload, list):
                raise Invalid("MALFORMED_PAYLOAD", "body")
            for position, value in enumerate(payload):
                owner = pr
                if not owner and isinstance(value, dict):
                    parent = value.get("issue_url") or value.get("pull_request_url")
                    try:
                        number = int(urlsplit(parent).path.rsplit("/", 1)[-1])
                    except (ValueError, TypeError):
                        raise Invalid("INVALID_SAVED_IDENTITY", "body") from None
                    match = self.src.execute(
                        "SELECT id FROM pull_requests WHERE repo_id=? AND number=?",
                        (self.t(collection, "repo_id"), number),
                    ).fetchone()
                    owner = match[0] if match else None
                if owner:
                    yield owner, DOCUMENT_KINDS[kind], value, position, None

    def saved_document(self, pr, kind, value, thread=None):
        self.pr(pr)
        if not isinstance(value, dict):
            raise Invalid("MALFORMED_PAYLOAD", "body")
        provider = value.get("fullDatabaseId") or value.get("id")
        if provider is None or isinstance(provider, (list, dict, bool)):
            raise Invalid("INVALID_SAVED_IDENTITY", "body")
        provider = str(provider)
        found = self.src.execute(
            "SELECT id FROM pr_documents WHERE pr_id=? AND kind=? AND provider_id=?",
            (pr, kind, provider),
        ).fetchone()
        ident = found[0] if found else f"{pr}:{kind}:{provider}"
        if "body" not in value:
            raise Invalid("MISSING_SAVED_BODY", "body")
        body = value["body"]
        if body is not None and not isinstance(body, str):
            raise Invalid("INVALID_SAVED_BODY", "body")
        metadata = {
            k: v
            for k, v in value.items()
            if k not in ("body", "title", "user", "author")
        }
        if thread:
            metadata["thread_id"] = thread
        author = value.get("user") or value.get("author") or {}
        if not isinstance(author, dict):
            raise Invalid("MALFORMED_PAYLOAD", "body")
        row = (
            ident,
            pr,
            kind,
            provider,
            None,
            0,
            value.get("node_id")
            or (value.get("id") if isinstance(value.get("id"), str) else None),
            author.get("login"),
            value.get("html_url") or value.get("url"),
            canonical(metadata),
        )
        for cell in row[6:9]:
            if cell is not None and not isinstance(cell, str):
                raise Invalid("MALFORMED_PAYLOAD", "body")
        return row, body

    def first_saved_document_fact(self, pr, document):
        # Document metadata is one stable source fact. Later page observations
        # retain their own metadata and must not overwrite this initial row.
        for saved in self.src.execute(
            "SELECT id FROM collections WHERE pr_id=? OR pr_id IS NULL ORDER BY id",
            (pr,),
        ):
            for page in self.pages(saved[0]):
                try:
                    self.occurrence_row(page)
                    for owner, kind, value, _, thread in self.page_documents(page):
                        row, _ = self.saved_document(owner, kind, value, thread)
                        if owner == pr and row[0] == document:
                            return row, value, thread
                except identity.Invalid:
                    continue
        raise Invalid("SAVED_DOCUMENT_ORIGIN_MISSING", "response_id")

    def first_saved_document_row(self, pr, document):
        return self.first_saved_document_fact(pr, document)[0]

    def _page_attribution(self, page):
        """Index one immutable source page's valid prefix for this prepare call.

        Body strings belong only to the current bounded decoded page. Evict
        them before decoding another page; no target fact or global payload
        cache participates in attribution or independent verification.
        """
        key = page.table, page.key, page.row_sha256
        if key == self._attribution_page:
            return self._attribution
        self._attribution_page = None
        self._attribution = {}
        self._attribution_error = None
        try:
            self.occurrence_row(page)
            for pr, kind, value, position, thread in self.page_documents(page):
                row, body = self.saved_document(pr, kind, value, thread)
                self._attribution.setdefault(row[0], []).append((body, position))
        except identity.Invalid:
            # Original scans could return a valid early match before a later
            # malformed/dependent item stopped that page. Keep exactly that
            # valid prefix; subsequent items cannot establish an origin.
            pass
        except (
            ValueError,
            TypeError,
            KeyError,
            UnicodeError,
            AttributeError,
            RecursionError,
        ) as exc:
            # Eager indexing must preserve an original early return even when
            # a later malformed item raises a parser error. A lookup without
            # a prefix match still raises that error, as the original scan did.
            # Store no traceback/frame that could retain the decoded page.
            self._attribution_error = type(exc), exc.args
        self._attribution_page = key
        return self._attribution

    def _page_has_body(self, page, document, body):
        # Keep page-owned body references inside this short scope so advancing
        # the outer page scan cannot retain the previous page through locals.
        found = any(
            candidate == body
            for candidate, _ in self._page_attribution(page).get(document, ())
        )
        if not found and self._attribution_error:
            kind, args = self._attribution_error
            raise kind(*args)
        return found

    def _page_document_position(self, page, document):
        entries = self._page_attribution(page).get(document)
        if entries:
            return entries[0][1]
        if self._attribution_error:
            kind, args = self._attribution_error
            raise kind(*args)
        return None

    def first_source_page(self, collection, document, body):
        for page in self.pages(collection):
            if self._page_has_body(page, document, body):
                return self.i(page, "ordinal")
        return None

    def first_document_position(self, collection, document):
        for page in self.pages(collection):
            position = self._page_document_position(page, document)
            if position is not None:
                return self.i(page, "ordinal"), position
        return None

    def code_context(self, record):
        pr = self.t(record, "pr_id")
        self.pr(pr)
        obs = self.ref("pr_observations", self.i(record, "observation_id", minimum=1))
        if self.t(obs, "pr_id") != pr:
            raise Invalid("OWNER_MISMATCH", "observation_id")
        head, base = (
            self.t(record, "head_oid", nullable=True),
            self.t(record, "base_oid", nullable=True),
        )
        parsed = [
            self.oid(value, column)
            for value, column in ((head, "head_oid"), (base, "base_oid"))
        ]
        formats = {item[0] for item in parsed if item[0]}
        if not formats:
            for item in self.src.execute(
                "SELECT oid FROM pr_commits WHERE code_observation=?",
                (self.i(record, "id"),),
            ):
                formats.add(self.oid(item[0], "oid")[0])
            for item in self.src.execute(
                "SELECT object_format FROM pr_git_links WHERE code_observation=?",
                (self.i(record, "id"),),
            ):
                if item[0] not in ("sha1", "sha256"):
                    raise Invalid("OBJECT_FORMAT_MISMATCH", "object_format")
                formats.add(item[0])
        if len(formats) > 1:
            raise Invalid("OBJECT_FORMAT_MISMATCH", "base_oid")
        return (
            pr,
            self.i(record, "observation_id"),
            next(iter(formats), None),
            parsed[0][1],
            parsed[1][1],
        )

    def oid(self, value, column):
        if value is None:
            return None, None
        if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", value):
            raise Invalid("INVALID_OID", column)
        return ("sha1" if len(value) == 40 else "sha256"), bytes.fromhex(value)

    def code_collection(self, code, kind):
        observation = self.ref("pr_observations", self.i(code, "observation_id"))
        matches = list(
            self.src.execute(
                "SELECT id FROM collections WHERE pr_id=? AND job_id=? AND kind=? ORDER BY id",
                (self.t(code, "pr_id"), self.t(observation, "job_id"), "pr-" + kind),
            )
        )
        if len(matches) != 1:
            raise Invalid("LISTING_COLLECTION_UNRESOLVED", kind)
        result = self.ref("collections", matches[0][0])
        self.collection_row(result)
        return result

    def listing_id(self, code, kind):
        return stable_id("listing", self.i(code, "id"), kind)

    def listing_collection_id(self, code, kind):
        return stable_id("listing-collection", self.i(code, "id"), kind)

    def listing_occurrence_id(self, code, kind, ordinal):
        return stable_id(
            "listing-occurrence", self.i(code, "id"), kind, ordinal, integer=True
        )

    def listing_state(self, code, kind):
        collection = self.code_collection(code, kind)
        cid = self.t(collection, "id")
        count, terminal, contiguous, valid = 0, False, True, True
        _, _, fmt, head, base = self.code_context(code)
        previous_cursor, seen_urls = None, set()
        for page in self.pages(cid):
            ordinal = self.i(page, "ordinal", minimum=0)
            if ordinal != count:
                contiguous = False
            count += 1
            _, request = self.selected_metadata(page, "request", ("url",))
            url_kind, url = request.get("url", ("null", None))
            if url_kind not in ("text", "null"):
                contiguous = False
                url = None
            if count > 1 and (previous_cursor is None or url != previous_cursor):
                contiguous = False
            if url in seen_urls:
                contiguous = False
            seen_urls.add(url)
            previous_cursor = self.t(page, "next_cursor", nullable=True)
            terminal = previous_cursor is None
            try:
                values = self.page_data(page)
                if not isinstance(values, list):
                    raise Invalid("MALFORMED_PAYLOAD", "body")
                for position, value in enumerate(values):
                    if not isinstance(value, dict):
                        raise Invalid("MALFORMED_PAYLOAD", "body")
                    if kind == "commits":
                        item_fmt, item_oid = self.oid(value.get("sha"), "oid")
                        if item_fmt is None or item_fmt != fmt:
                            raise Invalid("OBJECT_FORMAT_MISMATCH", "oid")
                        stored = self.lookup(
                            "pr_commits", self.i(code, "id"), ordinal * 10000 + position
                        )
                        if stored and self.oid(self.t(stored, "oid"), "oid") != (
                            item_fmt,
                            item_oid,
                        ):
                            valid = False
                    else:
                        if not isinstance(value.get("filename"), str):
                            raise Invalid("INVALID_SAVED_PATH", "body")
                        stored = self.lookup(
                            "pr_file_changes",
                            self.i(code, "id"),
                            ordinal * 10000 + position,
                        )
                        if stored and self.t(stored, "path") != value["filename"]:
                            valid = False
                    if stored and self.decoded_metadata(stored, "payload") != value:
                        valid = False
            except (identity.Invalid, ValueError, TypeError):
                valid = False
        source_table = "pr_commits" if kind == "commits" else "pr_file_changes"
        for item in self.src.execute(
            f"SELECT ordinal FROM {source_table} WHERE code_observation=?",
            (self.i(code, "id"),),
        ):
            page = self.lookup("collection_pages", cid, item[0] // 10000)
            if page is None:
                valid = False
            else:
                try:
                    values = self.page_data(page)
                    if not isinstance(values, list) or not 0 <= item[0] % 10000 < len(
                        values
                    ):
                        valid = False
                except identity.Invalid:
                    valid = False
        _, details = self.selected_metadata(code, "details", ("api_head_base_stable",))
        proven = bool(
            fmt
            and head
            and base
            and details.get("api_head_base_stable", ("null", None))[0] == "true"
            and valid
        )
        complete = (
            self.t(collection, "state") == "complete"
            and terminal
            and contiguous
            and proven
        )
        return (
            self.listing_id(code, kind),
            "complete" if complete else "partial",
            int(terminal and contiguous),
            count,
            int(proven),
        )

    def item_page(self, code, kind, ordinal):
        collection = self.code_collection(code, kind)
        page = self.ref("collection_pages", self.t(collection, "id"), ordinal // 10000)
        self.occurrence_row(page)
        return page

    def projection(self, recipe, record, emit, issue):
        t, i = self.t, self.i
        if recipe == "jobs":
            row, attempt = self.job_rows(record)
            emit("jobs", row)
            emit("job_attempts", attempt, relation="split")
            if row[1] != t(record, "kind") or attempt[2] != t(record, "state"):
                issue("LEGACY_OPERATIONAL_STATE", "state", "partial")
        elif recipe == "inventory_observations":
            source = t(record, "source_id")
            identity.Context.project(self, "sources", self.ref("sources", source))
            state = t(record, "state")
            if state not in ("complete", "partial", "unknown"):
                issue("UNKNOWN_STATE", "state", "partial")
                state = "unknown"
            emit(
                recipe,
                (
                    t(record, "id"),
                    source,
                    state,
                    self.metadata(record, "scope"),
                    self.timestamp(record, "observed_at"),
                    t(record, "reason", nullable=True),
                ),
            )
        elif recipe == "payloads":
            body, sha = (
                self.blob(record, "body"),
                self.blob(record, "payload_sha256", length=32),
            )
            if hashlib.sha256(body).digest() != sha:
                raise Invalid("PAYLOAD_DIGEST_MISMATCH", "payload_sha256")
            emit(
                recipe,
                (i(record, "id", minimum=1), sha, body, len(body), "decoded_api"),
            )
        elif recipe == "change_requests":
            emit(recipe, self.pr_row(record))
        elif recipe == "resume_scopes":
            emit(recipe, self.scope_row(record), relation="derived")
            issue("LEGACY_SCOPE_INCOMPLETE", "scope", "partial")
        elif recipe == "fetch_collections":
            row = self.collection_row(record)
            job = self.ref("jobs", t(record, "job_id"))
            _, job_attempt = self.job_rows(job)
            attempt = job_attempt[1]
            state = t(record, "state")
            if state not in (
                "running",
                "partial",
                "complete",
                "failed",
                "interrupted",
                "unknown",
            ):
                issue("UNKNOWN_STATE", "state", "partial")
                state = "unknown"
            emit(recipe, row)
            emit(
                "collection_progress",
                (
                    row[0],
                    t(record, "job_id"),
                    attempt,
                    state,
                    t(record, "cursor", nullable=True),
                    t(record, "reason", nullable=True),
                ),
                relation="split",
            )
            asserted = state if state in ("partial", "complete") else "unknown"
            emit(
                "completion_markers",
                (
                    stable_id("completion", row[0], integer=True),
                    row[5],
                    row[0],
                    asserted,
                    canonical(
                        {
                            "legacy_state": t(record, "state"),
                            "scope_confidence": "legacy_unknown",
                        }
                    ),
                    row[6],
                ),
                relation="split",
            )
            emit(
                "resume_cursors",
                (row[5], None, t(record, "cursor", nullable=True), 0),
                relation="split",
            )
        elif recipe == "fetch_occurrences":
            emit(recipe, self.occurrence_row(record), relation="derived")
        elif recipe == "change_request_observations":
            pr = t(record, "pr_id")
            self.pr(pr)
            i(record, "published", choices=(0, 1))
            emit(
                recipe,
                (
                    i(record, "id", minimum=1),
                    pr,
                    self.timestamp(record, "observed_at"),
                    0,
                    self.metadata(record, "payload"),
                    t(record, "job_id"),
                    self.parsed_at,
                    None,
                ),
            )
        elif recipe == "documents":
            emit(recipe, self.document_row(record))
        elif recipe == "document_versions":
            row = self.version_row(record)
            body = t(record, "body")
            emit("text_bodies", self.body_row(body), relation="merge")
            emit(recipe, row)
            if self.body_row(body)[3] != row[3]:
                issue("LEGACY_BODY_DIGEST_MISMATCH", "body_sha256", "partial")
        elif recipe == "document_observations":
            document, version = (
                t(record, "document_id"),
                i(record, "version_id", minimum=1),
            )
            self.document_row(self.ref("pr_documents", document))
            source_version = self.ref("document_versions", version)
            if self.version_row(source_version)[1] != document:
                raise Invalid("OWNER_MISMATCH", "version_id")
            origin = t(record, "collection_run")
            occurrence = None
            collection = self.lookup("collections", origin)
            if collection and self.t(collection, "pr_id", nullable=True) == self.t(
                self.ref("pr_documents", document), "pr_id"
            ):
                ordinal = self.first_source_page(
                    origin, document, t(source_version, "body")
                )
                if ordinal is not None:
                    occurrence = self.occurrence_id(origin, ordinal)
            emit(
                recipe,
                (
                    i(record, "id", minimum=1),
                    document,
                    version,
                    self.timestamp(record, "observed_at"),
                    self.parsed_at,
                    origin,
                    occurrence,
                    self.metadata(record),
                ),
            )
        elif recipe == "saved_pr_document_repair":
            self.repair_pr_documents(record, emit, issue)
        elif recipe == "reviews":
            pr, document = t(record, "pr_id"), t(record, "document_id")
            if self.document_row(self.ref("pr_documents", document))[1] != pr:
                raise Invalid("OWNER_MISMATCH", "document_id")
            emit(
                recipe,
                (t(record, "id"), pr, document, self.metadata(record, "payload")),
            )
        elif recipe == "review_threads":
            pr = t(record, "pr_id")
            self.pr(pr)
            emit(
                recipe,
                (
                    t(record, "id"),
                    pr,
                    self.metadata(record, "payload"),
                    self.timestamp(record, "observed_at"),
                ),
            )
        elif recipe == "review_comments":
            document, thread = (
                t(record, "document_id"),
                t(record, "thread_id", nullable=True),
            )
            pr = self.document_row(self.ref("pr_documents", document))[1]
            if thread and self.t(self.ref("review_threads", thread), "pr_id") != pr:
                raise Invalid("OWNER_MISMATCH", "thread_id")
            emit(recipe, (document, pr, thread, self.metadata(record, "payload")))
        elif recipe == "change_request_events":
            pr, origin, ordinal = (
                t(record, "pr_id"),
                t(record, "run_id"),
                i(record, "ordinal", minimum=0),
            )
            self.pr(pr)
            page = self.lookup("collection_pages", origin, ordinal // 10000)
            observed = self.timestamp(page, "observed_at") if page else None
            emit(
                recipe,
                (
                    i(record, "id", minimum=1),
                    pr,
                    origin,
                    ordinal,
                    t(record, "provider_id", nullable=True),
                    self.metadata(record, "payload"),
                    observed,
                ),
            )
        elif recipe == "collection_memberships":
            cid, resource = t(record, "collection_id"), t(record, "resource_id")
            collection = self.ref("collections", cid)
            self.collection_row(collection)
            document = self.lookup("pr_documents", resource)
            if document is None:
                issue("MEMBERSHIP_NOT_DOCUMENT", "resource_id", "info")
                return
            if self.document_row(document)[1] != t(collection, "pr_id", nullable=True):
                issue("MEMBERSHIP_SCOPE_UNRESOLVED", "resource_id", "partial")
                return
            emit(recipe, (cid, resource, i(record, "ordinal", minimum=0)))
        elif recipe == "saved_document_repair":
            self.repair_documents(record, emit, issue)
        elif recipe == "sync_checkpoints":
            self.checkpoint(record, emit, issue)
        elif recipe == "code_listings":
            pr, _, fmt, head, base = self.code_context(record)
            for kind in ("commits", "files"):
                try:
                    collection = self.code_collection(record, kind)
                    lid, cid = (
                        self.listing_id(record, kind),
                        self.listing_collection_id(record, kind),
                    )
                    base_row = self.collection_row(collection)
                    emit(
                        "fetch_collections",
                        (cid, *base_row[1:4], "pr-" + kind, base_row[5], base_row[6]),
                        relation="derived",
                    )
                    emit(
                        recipe,
                        (lid, pr, cid, kind, base_row[5], fmt, head, base),
                        relation="split",
                    )
                    emit(
                        "code_listing_progress",
                        (lid, "partial", 0, 0, 0),
                        relation="split",
                    )
                    for page in self.pages(t(collection, "id")):
                        ordinal = i(page, "ordinal")
                        emit(
                            "fetch_occurrences",
                            self.occurrence_row(
                                page,
                                collection_id=cid,
                                occurrence_id=self.listing_occurrence_id(
                                    record, kind, ordinal
                                ),
                            ),
                            relation="split",
                        )
                except Invalid as exc:
                    issue(exc.code, exc.column, "partial")
        elif recipe in ("code_commits", "code_file_changes"):
            code = self.ref(
                "pr_code_observations", i(record, "code_observation", minimum=1)
            )
            self.code_context(code)
            kind = "commits" if recipe == "code_commits" else "files"
            ordinal = i(record, "ordinal", minimum=0)
            page = self.item_page(code, kind, ordinal)
            occurrence = self.listing_occurrence_id(code, kind, i(page, "ordinal"))
            payload = self.metadata(record, "payload")
            if kind == "commits":
                fmt, oid = self.oid(t(record, "oid"), "oid")
                if self.code_context(code)[2] not in (None, fmt):
                    raise Invalid("OBJECT_FORMAT_MISMATCH", "oid")
                emit(
                    recipe,
                    (
                        self.listing_id(code, kind),
                        occurrence,
                        ordinal % 10000,
                        fmt,
                        oid,
                        payload,
                    ),
                )
            else:
                emit(
                    recipe,
                    (
                        self.listing_id(code, kind),
                        occurrence,
                        ordinal % 10000,
                        t(record, "path").encode("utf-8"),
                        payload,
                    ),
                )
        elif recipe == "saved_listing_repair":
            self.repair_listing(record, emit, issue)
        elif recipe == "code_listing_completion":
            self.code_context(record)
            for kind in ("commits", "files"):
                try:
                    final = self.listing_state(record, kind)
                    emit(
                        "code_listing_progress",
                        final,
                        operation="update",
                        before=(final[0], "partial", 0, 0, 0),
                        relation="derived",
                    )
                except Invalid as exc:
                    issue(exc.code, exc.column, "partial")
        elif recipe == "code_observations":
            pr, observation, fmt, head, base = self.code_context(record)
            listings, complete = [], True
            for kind in ("commits", "files"):
                try:
                    state = self.listing_state(record, kind)
                    listings.append(state[0])
                    complete = complete and state[1] == "complete"
                except Invalid:
                    listings.append(None)
                    complete = False
            state = t(record, "state")
            if state not in ("pending", "partial", "complete", "unknown"):
                state = "unknown"
                issue("UNKNOWN_STATE", "state", "partial")
            if state == "complete" and not complete:
                state = "partial"
                issue("LISTING_COMPLETENESS_UNPROVEN", "state", "partial")
            emit(
                recipe,
                (
                    i(record, "id", minimum=1),
                    pr,
                    observation,
                    *listings,
                    state,
                    fmt,
                    head,
                    base,
                    self.metadata(record, "details"),
                ),
            )
        elif recipe == "code_acquisitions":
            code = self.ref(
                "pr_code_observations", i(record, "code_observation", minimum=1)
            )
            pr = self.code_context(code)[0]
            role, fmt, oid = (
                t(record, "role"),
                t(record, "object_format"),
                self.blob(record, "oid"),
            )
            if role not in ("head", "base", "merge"):
                issue("UNSUPPORTED_ACQUISITION_ROLE", "role", "partial")
                return
            if fmt not in ("sha1", "sha256") or len(oid) != (
                20 if fmt == "sha1" else 32
            ):
                raise Invalid("INVALID_OID", "oid")
            root_kind, root_raw = record.value("acquisition_id")
            root = int(root_raw) if root_kind == "integer" else None
            if root_kind not in ("integer", "null"):
                raise Invalid("INVALID_TYPE", "acquisition_id")
            if root is not None:
                source_root = self.ref("acquisition_roots", root)
                if (
                    t(source_root, "repo_id") != self.pr(pr)[1]
                    or t(source_root, "role") != role
                    or t(source_root, "object_format") != fmt
                    or self.blob(source_root, "oid") != oid
                ):
                    raise Invalid("ROOT_OWNER_CONTEXT_MISMATCH", "acquisition_id")
            if (
                self.src.execute(
                    "SELECT count(*) FROM pr_git_links WHERE code_observation=? AND role=?",
                    (i(code, "id"), role),
                ).fetchone()[0]
                != 1
            ):
                raise Invalid("ACQUISITION_ROLE_CONFLICT", "role")
            emit(recipe, (i(code, "id"), role, fmt, oid, root))
        else:
            raise ConversionError("UNKNOWN_PR_RECIPE")

    def repair_documents(self, page, emit, issue):
        cid, ordinal = self.t(page, "collection_id"), self.i(page, "ordinal")
        collection = self.ref("collections", cid)
        self.collection_row(collection)
        if (
            self.t(collection, "kind") not in DOCUMENT_KINDS
            and self.t(collection, "kind") != "threads"
        ):
            return
        occurrence = self.occurrence_row(page)[0]
        repaired_threads = set()
        thread_snapshots = {}
        if self.t(collection, "kind") == "threads":
            data = self.page_data(page)
            if isinstance(data, dict):
                nodes = (
                    ((data.get("data") or {}).get("repository") or {}).get(
                        "pullRequest"
                    )
                    or {}
                ).get("reviewThreads") or {}
                for thread_value in nodes.get("nodes") or []:
                    if not isinstance(thread_value, dict) or not isinstance(
                        thread_value.get("id"), str
                    ):
                        raise Invalid("INVALID_SAVED_IDENTITY", "body")
                    pr = self.t(collection, "pr_id", nullable=True)
                    self.pr(pr)
                    tid = self.thread_identity(pr, thread_value["id"])
                    thread_snapshots[tid] = {
                        key: value
                        for key, value in thread_value.items()
                        if key != "comments"
                    }
                    if self.lookup("review_threads", tid) is None:
                        payload, observed = self.first_saved_thread_snapshot(
                            pr, thread_value["id"]
                        )
                        emit(
                            "review_threads",
                            (tid, pr, payload, observed),
                            relation="derived",
                        )
                        repaired_threads.add(tid)
        for pr, kind, value, position, thread in self.page_documents(page):
            row, body = self.saved_document(pr, kind, value, thread)
            document = row[0]
            source_document = self.lookup("pr_documents", document)
            if source_document is None:
                emit(
                    "documents",
                    self.first_saved_document_row(pr, document),
                    relation="derived",
                )
            else:
                self.document_row(source_document)
            if body is None:
                if (
                    self.t(collection, "pr_id", nullable=True) == pr
                    and self.lookup("collection_memberships", cid, document) is None
                    and self.first_document_position(cid, document)
                    == (ordinal, position)
                ):
                    emit(
                        "collection_memberships",
                        (cid, document, ordinal * 10000 + position),
                        relation="derived",
                    )
                emit(
                    "unresolved_payloads",
                    (
                        stable_id(
                            "null-saved-body",
                            cid,
                            ordinal,
                            position,
                            document,
                            integer=True,
                        ),
                        self.i(page, "response_id"),
                        self.record_id(page),
                        "saved document body is NULL; original occurrence retained",
                    ),
                    relation="derived",
                )
                issue("NULL_SAVED_BODY", "response_id", "info")
                continue
            # A v2 resource observation represents only its first matching saved
            # page. Later A->B->A occurrences get their own version/observation.
            observed = self.src.execute(
                "SELECT o.id FROM resource_observations o JOIN document_versions v ON v.id=o.version_id WHERE o.document_id=? AND o.collection_run=? AND v.body=? ORDER BY o.id LIMIT 1",
                (document, cid, body),
            ).fetchone()
            covered = (
                observed and self.first_source_page(cid, document, body) == ordinal
            )
            if not covered:
                version = stable_id(
                    "saved-version", cid, ordinal, position, document, integer=True
                )
                obs = stable_id(
                    "saved-observation", cid, ordinal, position, document, integer=True
                )
                emit("text_bodies", self.body_row(body), relation="merge")
                emit(
                    "document_versions",
                    (version, document, self.body_row(body)[0], None),
                    relation="derived",
                )
                emit(
                    "document_observations",
                    (
                        obs,
                        document,
                        version,
                        self.timestamp(page, "observed_at"),
                        self.parsed_at,
                        cid,
                        occurrence
                        if self.t(collection, "pr_id", nullable=True) == pr
                        else None,
                        canonical(
                            {
                                **strict_json(row[9]),
                                "saved_payload_repair": True,
                                "position": position,
                                **(
                                    {"thread_payload": thread_snapshots[thread]}
                                    if thread in thread_snapshots
                                    else {}
                                ),
                            }
                        ),
                    ),
                    relation="derived",
                )
                issue("SAVED_DOCUMENT_RECONSTRUCTED", "response_id", "info")
            if self.t(collection, "pr_id", nullable=True) == pr:
                member = self.lookup("collection_memberships", cid, document)
                if member is None and self.first_document_position(cid, document) == (
                    ordinal,
                    position,
                ):
                    emit(
                        "collection_memberships",
                        (cid, document, ordinal * 10000 + position),
                        relation="derived",
                    )
            if (
                kind == "review"
                and self.src.execute(
                    "SELECT 1 FROM pr_reviews WHERE document_id=?", (document,)
                ).fetchone()
                is None
            ):
                emit(
                    "reviews",
                    (
                        document,
                        pr,
                        document,
                        canonical(self.first_saved_document_fact(pr, document)[1]),
                    ),
                    relation="derived",
                )
            if (
                kind == "review-comment"
                and self.lookup("review_comments", document) is None
            ):
                if (
                    thread
                    and thread not in repaired_threads
                    and self.lookup("review_threads", thread) is None
                ):
                    issue("THREAD_REFERENCE_UNRESOLVED", "response_id", "partial")
                    thread = None
                emit(
                    "review_comments",
                    (
                        document,
                        pr,
                        thread,
                        canonical(self.first_saved_document_fact(pr, document)[1]),
                    ),
                    relation="derived",
                )

    def pr_document(self, record, kind):
        pr = self.t(record, "pr_id")
        payload = self.decoded_metadata(record, "payload")
        owner = self.pr(pr)
        if payload.get("number") != owner[4]:
            raise Invalid("PAYLOAD_OWNER_MISMATCH", "payload")
        body = payload.get("title") if kind == "pr-title" else payload.get("body")
        if kind == "pr-body" and "body" not in payload:
            raise Invalid("MISSING_SAVED_BODY", "payload")
        if not isinstance(body, str) and not (kind == "pr-body" and body is None):
            raise Invalid("INVALID_SAVED_BODY", "payload")
        return self.saved_document(pr, kind, {**payload, "body": body})

    def repair_pr_documents(self, record, emit, issue):
        for kind in ("pr-title", "pr-body"):
            row, body = self.pr_document(record, kind)
            document, pr = row[0], row[1]
            source_document = self.lookup("pr_documents", document)
            if source_document is None:
                # The smallest source observation key owns the initial
                # document row even when the later payload metadata changes.
                first_row = None
                for saved in self.src.execute(
                    "SELECT id FROM pr_observations WHERE pr_id=? ORDER BY id", (pr,)
                ):
                    first = self.ref("pr_observations", saved[0])
                    try:
                        candidate, _ = self.pr_document(first, kind)
                    except identity.Invalid:
                        continue
                    if candidate[0] == document:
                        first_row = candidate
                        break
                if first_row is None:
                    raise Invalid("SAVED_DOCUMENT_ORIGIN_MISSING", "payload")
                emit("documents", first_row, relation="derived")
            else:
                self.document_row(source_document)
            if body is None:
                emit(
                    "unresolved_payloads",
                    (
                        stable_id(
                            "null-pr-body", self.i(record, "id"), document, integer=True
                        ),
                        None,
                        self.record_id(record),
                        "saved PR body is NULL; original observation retained",
                    ),
                    relation="derived",
                )
                issue("NULL_SAVED_BODY", "payload", "info")
                continue
            job = self.t(record, "job_id")
            existing = self.src.execute(
                "SELECT 1 FROM resource_observations o JOIN document_versions v ON v.id=o.version_id WHERE o.document_id=? AND o.collection_run=? AND v.body=? LIMIT 1",
                (document, job, body),
            ).fetchone()
            covered = False
            if existing:
                for saved in self.src.execute(
                    "SELECT id FROM pr_observations WHERE pr_id=? AND job_id=? ORDER BY id",
                    (pr, job),
                ):
                    try:
                        candidate, candidate_body = self.pr_document(
                            self.ref("pr_observations", saved[0]), kind
                        )
                    except identity.Invalid:
                        continue
                    if candidate[0] == document and candidate_body == body:
                        covered = saved[0] == self.i(record, "id")
                        break
            if not covered:
                ident = self.i(record, "id")
                version = stable_id("pr-saved-version", ident, document, integer=True)
                emit("text_bodies", self.body_row(body), relation="merge")
                emit(
                    "document_versions",
                    (version, document, self.body_row(body)[0], None),
                    relation="derived",
                )
                emit(
                    "document_observations",
                    (
                        stable_id(
                            "pr-saved-observation", ident, document, integer=True
                        ),
                        document,
                        version,
                        self.timestamp(record, "observed_at"),
                        self.parsed_at,
                        f"pr-observation:{ident}",
                        None,
                        canonical(
                            {**strict_json(row[9]), "source_pr_observation_id": ident}
                        ),
                    ),
                    relation="derived",
                )
                issue("SAVED_PR_DOCUMENT_RECONSTRUCTED", "payload", "info")

    def checkpoint(self, record, emit, issue):
        scope, value = (
            self.t(record, "scope"),
            self.decoded_metadata(record, "value"),
        )
        stamp = self.timestamp(record, "updated_at")
        if scope.startswith("pending-comment:"):
            repo = value.get("repo_id")
            self.ensure_repo(repo)
            found = self.src.execute(
                "SELECT id FROM pull_requests WHERE repo_id=? AND number=?",
                (repo, value.get("number")),
            ).fetchone()
            payload, kind = value.get("payload"), value.get("kind")
            if (
                found
                and kind in ("issue-comment", "review-comment")
                and isinstance(payload, dict)
            ):
                row, body = self.saved_document(found[0], kind, payload)
                source_document = self.lookup("pr_documents", row[0])
                if source_document is None:
                    try:
                        initial = self.first_saved_document_row(found[0], row[0])
                    except identity.Invalid:
                        initial = row
                    emit("documents", initial, relation="derived")
                if body is None:
                    emit(
                        "unresolved_payloads",
                        (
                            stable_id("null-pending-body", scope, integer=True),
                            None,
                            self.record_id(record),
                            "pending document body is NULL; original observation retained",
                        ),
                        relation="derived",
                    )
                    issue("NULL_SAVED_BODY", "value", "info")
                    return
                version = stable_id("pending-version", scope, integer=True)
                emit("text_bodies", self.body_row(body), relation="merge")
                emit(
                    "document_versions",
                    (version, row[0], self.body_row(body)[0], None),
                    relation="derived",
                )
                emit(
                    "document_observations",
                    (
                        stable_id("pending-observation", scope, integer=True),
                        row[0],
                        version,
                        stamp,
                        self.parsed_at,
                        scope,
                        None,
                        canonical({"saved_pending_resource": True}),
                    ),
                    relation="derived",
                )
            else:
                emit(
                    "unresolved_payloads",
                    (
                        stable_id("pending-unresolved", scope, integer=True),
                        None,
                        self.record_id(record),
                        "pending resource parent unresolved",
                    ),
                    relation="derived",
                )
                issue("PENDING_PARENT_UNRESOLVED", "value", "partial")
        elif scope.startswith("etag:"):
            if len(scope.encode("utf-8")) > MAX_SAVED_REPLAY_BYTES:
                raise Invalid("REPLAY_BUDGET_EXCEEDED", "scope")
            try:
                assertion = strict_json(scope[5:])
            except RecursionError:
                raise Invalid("JSON_DEPTH_UNSUPPORTED", "scope") from None
            except ValueError:
                raise Invalid("INVALID_SCOPE", "scope") from None
            source, native = assertion.get("source"), assertion.get("repo")
            candidates = list(
                self.src.execute(
                    "SELECT r.id FROM repositories r JOIN source_repositories s ON s.repo_id=r.id WHERE s.source_id=? AND r.provider_repo_id=?",
                    (source, native),
                )
            )
            if (
                len(candidates) != 1
                or not isinstance(value.get("etag"), str)
                or type(value.get("response_id")) is not int
            ):
                raise Invalid("VALIDATOR_SCOPE_UNRESOLVED", "value")
            repo = candidates[0][0]
            response = self.ref("api_responses", value["response_id"])
            if hashlib.sha256(self.blob(response, "body")).digest() != self.blob(
                response, "payload_sha256", length=32
            ):
                raise Invalid("PAYLOAD_DIGEST_MISMATCH", "response_id")
            sid = stable_id("validator-scope", scope)
            endpoint = assertion.get("url")
            principal, version = assertion.get("principal"), assertion.get("version")
            if any(
                x is not None and not isinstance(x, str)
                for x in (principal, version, endpoint)
            ):
                raise Invalid("INVALID_SCOPE", "scope")
            emit(
                "resume_scopes",
                (
                    sid,
                    repo,
                    self.binding(repo),
                    source,
                    principal,
                    version,
                    endpoint,
                    canonical(assertion),
                    "v1",
                    "legacy_unknown",
                    "legacy_unknown",
                ),
                relation="derived",
            )
            emit(
                "validators",
                (sid, scope, value["etag"], value["response_id"], stamp),
                relation="derived",
            )
        else:
            # Cursors, PR-complete claims and watermarks remain exact typed
            # archive input. They are not promoted to reusable scopes by guess.
            emit(
                "unresolved_payloads",
                (
                    stable_id("checkpoint", scope, integer=True),
                    None,
                    self.record_id(record),
                    "legacy operational checkpoint retained; scope not proven",
                ),
                relation="archive",
            )
            issue("CHECKPOINT_SCOPE_DEFERRED", "scope", "info")

    def repair_listing(self, page, emit, issue):
        collection = self.ref("collections", self.t(page, "collection_id"))
        kind = self.t(collection, "kind")
        if kind not in ("pr-commits", "pr-files"):
            return
        values = self.page_data(page)
        if not isinstance(values, list):
            raise Invalid("MALFORMED_PAYLOAD", "body")
        listing_kind = kind.removeprefix("pr-")
        codes = self.src.execute(
            "SELECT c.id FROM pr_code_observations c JOIN pr_observations o ON o.id=c.observation_id WHERE c.pr_id=? AND o.job_id=? ORDER BY c.id",
            (self.t(collection, "pr_id"), self.t(collection, "job_id")),
        )
        for saved in codes:
            code = self.ref("pr_code_observations", saved[0])
            self.code_context(code)
            if self.t(self.code_collection(code, listing_kind), "id") != self.t(
                collection, "id"
            ):
                continue
            ordinal = self.i(page, "ordinal")
            occurrence = self.listing_occurrence_id(code, listing_kind, ordinal)
            for pos, value in enumerate(values):
                if not isinstance(value, dict):
                    raise Invalid("MALFORMED_PAYLOAD", "body")
                source_table = (
                    "pr_commits" if listing_kind == "commits" else "pr_file_changes"
                )
                if self.lookup(source_table, saved[0], ordinal * 10000 + pos):
                    continue
                if listing_kind == "commits":
                    fmt, oid = self.oid(value.get("sha"), "oid")
                    if fmt is None or self.code_context(code)[2] not in (None, fmt):
                        raise Invalid("INVALID_OID", "body")
                    emit(
                        "code_commits",
                        (
                            self.listing_id(code, listing_kind),
                            occurrence,
                            pos,
                            fmt,
                            oid,
                            canonical(value),
                        ),
                        relation="derived",
                    )
                else:
                    path = value.get("filename")
                    if not isinstance(path, str):
                        raise Invalid("INVALID_SAVED_PATH", "body")
                    emit(
                        "code_file_changes",
                        (
                            self.listing_id(code, listing_kind),
                            occurrence,
                            pos,
                            path.encode("utf-8"),
                            canonical(value),
                        ),
                        relation="derived",
                    )
                issue("SAVED_LISTING_ITEM_RECONSTRUCTED", "response_id", "info")


def prepare(db, src, run, recipe, index, records, *, encoding="UTF-8", verifying=False):
    context = Context(db, src, run, encoding, verifying=verifying)
    output = {"operations": [], "mappings": [], "diagnostics": [], "decisions": []}
    for record in records:
        record_id = context.record_id(record)
        operations, mappings, issues = [], [], []

        def emit(table, row, *, operation="insert", relation="identity", before=None):
            op = {
                "record_id": record_id,
                "table": table,
                "operation": operation,
                "row": tuple(row),
            }
            if before is not None:
                op["before"] = tuple(before)
            operations.append(op)
            mappings.append(
                [
                    record_id,
                    table,
                    target_key(table, row).hex(),
                    relation,
                    f"{VERSION}; {recipe}; source-derived exact key",
                ]
            )

        def issue(code, column, severity):
            issues.append(
                (
                    "PR_" + code.removeprefix("PR_").removeprefix("IDENTITY_"),
                    severity,
                    column,
                )
            )

        try:
            context.projection(recipe, record, emit, issue)
        except identity.Invalid as exc:
            operations.clear()
            mappings.clear()
            issue(
                exc.code,
                exc.column,
                "partial"
                if exc.code
                in ("PR_REPLAY_BUDGET_EXCEEDED", "PR_JSON_DEPTH_UNSUPPORTED")
                else "blocking",
            )
        except (ValueError, TypeError, KeyError, UnicodeError):
            operations.clear()
            mappings.clear()
            issue("MALFORMED_VALUE", "source_value", "blocking")
        output["operations"].extend(operations)
        output["mappings"].extend(mappings)
        output["decisions"].append(
            {
                "record_id": record_id,
                "source_key": record.key.hex(),
                "source_sha256": record.row_sha256.hex(),
                "disposition": "normalized" if operations else "archive_only",
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
