"""Catalog3 API facts and restart boundaries, shared by REST and GraphQL."""

from __future__ import annotations

import hashlib
import json
import uuid

from repo_catalog.domain.models import CatalogError, now

PARSER = "catalog3-github/1"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def oid_context(value):
    head = (value.get("head") or {}).get("sha")
    base = (value.get("base") or {}).get("sha")
    present = [item for item in (head, base) if item is not None]
    if not present:
        return None, None, None
    algorithm = "sha256" if len(present[0]) == 64 else "sha1"
    from repo_catalog.domain.models import GitOid

    result = []
    for item in (head, base):
        if item is None:
            result.append(None)
        else:
            parsed = GitOid.parse(algorithm + ":" + item)
            result.append(parsed.value)
    return algorithm, *result


class ApiFacts:
    def __init__(self, store, config):
        self.s, self.cfg = store, config
        self.principal = None
        self.permissions = None

    def fence(self, job):
        row = self.s.one(
            "SELECT j.current_attempt,a.state FROM jobs j JOIN job_attempts a "
            "ON a.job_id=j.id AND a.attempt=j.current_attempt WHERE j.id=?",
            (job,),
        )
        if (
            not row
            or row["state"] != "running"
            or (
                getattr(self.s, "expected_attempt", None) is not None
                and row["current_attempt"] != self.s.expected_attempt
            )
        ):
            raise CatalogError("STALE_ATTEMPT", "Refusing obsolete API publication")
        return row["current_attempt"]

    def scope(self, repo, endpoint, context=None):
        binding = self.s.one(
            "SELECT b.id FROM repository_bindings b JOIN sources s ON s.instance_id=b.instance_id "
            "WHERE b.repo_id=? AND s.id=?",
            (repo["id"], repo["source_id"]),
        )
        if not binding:
            raise CatalogError(
                "IDENTITY_CONFLICT", "API source has no repository binding"
            )
        context = {
            "provider_repo_id": repo["provider_repo_id"],
            "accept": "application/vnd.github+json",
            "rest_page_size": self.cfg["rest_page_size"],
            "graphql_page_size": self.cfg["graphql_page_size"],
            **(context or {}),
        }
        if self.permissions is not None:
            context["permissions"] = self.permissions
        row = [
            repo["id"],
            binding[0],
            repo["source_id"],
            self.principal,
            self.cfg["rest_api_version"],
            endpoint,
            canonical(context),
            PARSER,
            self.s.config["preservation"]["profile"],
            "proven",
        ]
        if not isinstance(row[-2], str):
            row[-2] = canonical(row[-2])
        ident = "api:" + hashlib.sha256(canonical(row).encode()).hexdigest()
        existing = self.s.all(
            "SELECT id,request_context FROM resume_scopes WHERE repo_id=? AND binding_id=? AND source_id=? "
            "AND principal_ref IS ? AND api_version IS ? AND endpoint IS ? AND parser_version=? AND profile_version=? AND confidence='proven'",
            (*row[:6], row[7], row[8]),
        )
        for scope in existing:
            if json.loads(scope["request_context"]) == context:
                return scope["id"]
        if not self.s.one("SELECT 1 FROM resume_scopes WHERE id=?", (ident,)):
            self.s.execute(
                "INSERT INTO resume_scopes VALUES(?,?,?,?,?,?,?,?,?,?,?)", (ident, *row)
            )
        return ident

    def begin(self, repo, pr, kind, job, endpoint, context=None, *, reuse=False):
        scope = self.scope(repo, endpoint, context)
        previous = self.s.one(
            "SELECT f.*,p.state,p.cursor,p.reason FROM fetch_collections f JOIN collection_progress p "
            "ON p.collection_id=f.id WHERE f.scope_id=? AND f.change_request_id IS ? AND f.kind=? "
            "AND p.job_id=? ORDER BY f.observed_at DESC,f.id DESC LIMIT 1",
            (scope, pr, kind, job),
        )
        if not previous and reuse:
            previous = self.s.one(
                "SELECT f.*,p.state,p.cursor,p.reason FROM fetch_collections f JOIN collection_progress p "
                "ON p.collection_id=f.id WHERE f.scope_id=? AND f.change_request_id IS ? AND f.kind=? "
                "AND p.state='complete' ORDER BY f.observed_at DESC,f.id DESC LIMIT 1",
                (scope, pr, kind),
            )
        if previous:
            if previous["state"] != "complete":
                self.s.execute(
                    "UPDATE collection_progress SET attempt=?,state='running',reason=NULL WHERE collection_id=?",
                    (self.fence(job), previous["id"]),
                )
            return dict(previous)
        ident = str(uuid.uuid4())
        self.s.execute(
            "INSERT INTO fetch_collections VALUES(?,?,?,?,?,?,?)",
            (ident, repo["id"], pr, repo["source_id"], kind, scope, now()),
        )
        self.s.execute(
            "INSERT INTO collection_progress VALUES(?,?,?,'running',NULL,NULL)",
            (ident, job, self.fence(job)),
        )
        return {
            "id": ident,
            "scope_id": scope,
            "state": "running",
            "cursor": None,
            "change_request_id": pr,
            "kind": kind,
        }

    def payload(self, raw):
        digest = hashlib.sha256(raw).digest()
        row = self.s.one(
            "SELECT id FROM payloads WHERE sha256=? AND body=?", (digest, raw)
        )
        if row:
            return row[0]
        return self.s.execute(
            "INSERT INTO payloads(sha256,body,byte_length,representation) VALUES(?,?,?,'decoded_api')",
            (digest, raw, len(raw)),
        ).lastrowid

    def page(self, collection, response, request, next_cursor, *, advance=True):
        ordinal = self.s.one(
            "SELECT coalesce(max(ordinal),-1)+1 FROM fetch_occurrences WHERE collection_id=?",
            (collection["id"],),
        )[0]
        timestamp = now()
        ident = self.s.execute(
            "INSERT INTO fetch_occurrences(collection_id,ordinal,payload_id,request,next_cursor,observed_at,parsed_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                collection["id"],
                ordinal,
                self.payload(response.content),
                canonical(request),
                next_cursor,
                timestamp,
                timestamp,
            ),
        ).lastrowid
        if advance:
            self.s.execute(
                "UPDATE collection_progress SET cursor=? WHERE collection_id=?",
                (next_cursor, collection["id"]),
            )
        return ident, ordinal, timestamp

    def finish(self, collection, *, evidence=None):
        self.s.execute(
            "UPDATE collection_progress SET state='complete',cursor=NULL,reason=NULL WHERE collection_id=?",
            (collection["id"],),
        )
        self.s.execute(
            "INSERT INTO completion_markers(scope_id,collection_id,asserted_state,evidence,observed_at) VALUES(?,?,'complete',?,?)",
            (
                collection["scope_id"],
                collection["id"],
                canonical(evidence or {"parser": PARSER, "terminal": True}),
                now(),
            ),
        )

    def partial(self, collection, reason):
        self.s.execute(
            "UPDATE collection_progress SET state='partial',reason=? WHERE collection_id=?",
            (reason, collection["id"]),
        )

    def origin(self, collection, occurrence, position):
        return f"api:{collection['id']}:{occurrence}:{position}"

    def document(
        self,
        pr,
        kind,
        provider,
        body,
        value,
        collection,
        occurrence,
        position,
        observed_at,
        *,
        thread=None,
    ):
        if not isinstance(body, str):
            raise CatalogError("API_SCHEMA", "Expected document text")
        node = value.get("node_id") or (
            value.get("id") if isinstance(value.get("id"), str) else None
        )
        found = self.s.one(
            "SELECT id,current_version_id FROM documents WHERE change_request_id=? AND kind=? AND provider_id=?",
            (pr, kind, str(provider)),
        )
        if not found and node:
            found = self.s.one(
                "SELECT id,current_version_id FROM documents WHERE change_request_id=? AND kind=? AND node_id=?",
                (pr, kind, node),
            )
        ident = found[0] if found else f"{pr}:{kind}:{provider}"
        origin = self.origin(collection, occurrence, position)
        if found and self.s.one(
            "SELECT 1 FROM document_observations WHERE document_id=? AND origin_key=?",
            (ident, origin),
        ):
            # Reparse of an admitted response cannot move the current projection
            # backward or create a second version/remote observation.
            return ident
        author = value.get("user") or value.get("author") or {}
        metadata = {
            key: item
            for key, item in value.items()
            if key not in ("body", "title", "user", "author")
        }
        if thread:
            metadata["thread_id"] = thread
        if found:
            self.s.execute(
                "UPDATE documents SET node_id=coalesce(?,node_id),author=?,url=?,metadata=?,deleted=0 WHERE id=?",
                (
                    node,
                    author.get("login"),
                    value.get("html_url") or value.get("url"),
                    canonical(metadata),
                    ident,
                ),
            )
        else:
            self.s.execute(
                "INSERT INTO documents VALUES(?,?,?,?,NULL,0,?,?,?,?)",
                (
                    ident,
                    pr,
                    kind,
                    str(provider),
                    node,
                    author.get("login"),
                    value.get("html_url") or value.get("url"),
                    canonical(metadata),
                ),
            )
        raw = body.encode("utf-8")
        digest = hashlib.sha256(raw).digest()
        stored = self.s.one(
            "SELECT id FROM text_bodies WHERE sha256=? AND body=?", (digest, body)
        )
        body_id = (
            stored[0]
            if stored
            else self.s.execute(
                "INSERT INTO text_bodies(body,byte_length,sha256) VALUES(?,?,?)",
                (body, len(raw), digest),
            ).lastrowid
        )
        version = self.s.one(
            "SELECT id FROM document_versions WHERE document_id=? AND id=? AND body_id=?",
            (ident, found["current_version_id"] if found else None, body_id),
        )
        version_id = (
            version[0]
            if version
            else self.s.execute(
                "INSERT INTO document_versions(document_id,body_id) VALUES(?,?)",
                (ident, body_id),
            ).lastrowid
        )
        # The replay guard above returned before any writes. This caller holds
        # the SQLite writer transaction, so repeating that lookup after creating
        # the version cannot reveal another writer's observation.
        owner_occurrence = (
            occurrence if collection.get("change_request_id") == pr else None
        )
        self.s.execute(
            "INSERT INTO document_observations(document_id,version_id,observed_at,parsed_at,origin_key,occurrence_id,metadata) VALUES(?,?,?,?,?,?,?)",
            (
                ident,
                version_id,
                observed_at,
                now(),
                origin,
                owner_occurrence,
                canonical(metadata),
            ),
        )
        self.s.execute(
            "UPDATE documents SET current_version_id=? WHERE id=?", (version_id, ident)
        )
        if collection.get("change_request_id") == pr and not self.s.one(
            "SELECT 1 FROM collection_memberships WHERE collection_id=? AND document_id=?",
            (collection["id"], ident),
        ):
            self.s.execute(
                "INSERT INTO collection_memberships VALUES(?,?,?)",
                (collection["id"], ident, position),
            )
        if kind == "review":
            if self.s.one("SELECT 1 FROM reviews WHERE id=?", (ident,)):
                self.s.execute(
                    "UPDATE reviews SET payload=? WHERE id=?", (canonical(value), ident)
                )
            else:
                self.s.execute(
                    "INSERT INTO reviews VALUES(?,?,?,?)",
                    (ident, pr, ident, canonical(value)),
                )
        if kind == "review-comment":
            if self.s.one(
                "SELECT 1 FROM review_comments WHERE document_id=?", (ident,)
            ):
                self.s.execute(
                    "UPDATE review_comments SET thread_id=coalesce(?,thread_id),payload=? WHERE document_id=?",
                    (thread, canonical(value), ident),
                )
            else:
                self.s.execute(
                    "INSERT INTO review_comments VALUES(?,?,?,?)",
                    (ident, pr, thread, canonical(value)),
                )
        return ident
