"""Catalog3 API facts and restart boundaries, shared by REST and GraphQL."""

from __future__ import annotations

import hashlib
import json
import uuid

from repo_catalog.adapters.sqlite.text_bodies import intern_text_body
from repo_catalog.domain.document import DocumentKey
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.time import now_us

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
            "SELECT j.current_attempt,a.state FROM jobs j JOIN job_attempts a ON a.job_id=j.job_id AND a.attempt=j.current_attempt WHERE j.job_id=?",
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
            "SELECT b.repository_binding_id FROM repository_bindings b JOIN sources s ON s.service_instance_uuidv4=b.service_instance_uuidv4 WHERE b.repository_uuidv4=? AND s.source_id=?",
            (repo["repository_uuidv4"], repo["source_id"]),
        )
        if not binding:
            raise CatalogError(
                "IDENTITY_CONFLICT", "API source has no repository binding"
            )
        context = {
            "provider_repository_id": repo["provider_repository_id"],
            "accept": "application/vnd.github+json",
            "rest_page_size": self.cfg["rest_page_size"],
            "graphql_page_size": self.cfg["graphql_page_size"],
            **(context or {}),
        }
        if self.permissions is not None:
            context["permissions"] = self.permissions
        row = [
            repo["repository_uuidv4"],
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
            "SELECT resume_scope_id,request_context FROM resume_scopes WHERE repository_uuidv4=? AND repository_binding_id=? AND source_id=? AND principal_ref IS ? AND api_version IS ? AND endpoint IS ? AND parser_version=? AND profile_version=? AND confidence='proven'",
            (*row[:6], row[7], row[8]),
        )
        for scope in existing:
            if json.loads(scope["request_context"]) == context:
                return scope["resume_scope_id"]
        if not self.s.one(
            "SELECT 1 FROM resume_scopes WHERE resume_scope_id=?", (ident,)
        ):
            self.s.execute(
                "INSERT INTO resume_scopes(resume_scope_id,repository_uuidv4,repository_binding_id,source_id,principal_ref,api_version,endpoint,request_context,parser_version,profile_version,confidence) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (ident, *row),
            )
        return ident

    def begin(self, repo, pr, kind, job, endpoint, context=None, *, reuse=False):
        scope = self.scope(repo, endpoint, context)
        previous = self.s.one(
            "SELECT f.*,p.state,p.cursor,p.reason FROM fetch_collections f JOIN collection_progress p ON p.fetch_collection_id=f.fetch_collection_id WHERE f.resume_scope_id=? AND f.change_request_id IS ? AND f.kind=? AND p.job_id=? ORDER BY f.observed_at_us DESC,f.fetch_collection_id DESC LIMIT 1",
            (scope, pr, kind, job),
        )
        if not previous and reuse:
            previous = self.s.one(
                "SELECT f.*,p.state,p.cursor,p.reason FROM fetch_collections f JOIN collection_progress p ON p.fetch_collection_id=f.fetch_collection_id WHERE f.resume_scope_id=? AND f.change_request_id IS ? AND f.kind=? AND p.state='complete' ORDER BY f.observed_at_us DESC,f.fetch_collection_id DESC LIMIT 1",
                (scope, pr, kind),
            )
        if previous:
            if previous["state"] != "complete":
                self.s.execute(
                    "UPDATE collection_progress SET attempt=?,state='running',reason=NULL WHERE fetch_collection_id=?",
                    (self.fence(job), previous["fetch_collection_id"]),
                )
            return dict(previous)
        ident = str(uuid.uuid4())
        self.s.execute(
            "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,source_id,kind,resume_scope_id,observed_at_us) VALUES(?,?,?,?,?,?,?)",
            (
                ident,
                repo["repository_uuidv4"],
                pr,
                repo["source_id"],
                kind,
                scope,
                now_us(),
            ),
        )
        self.s.execute(
            "INSERT INTO collection_progress(fetch_collection_id,job_id,attempt,state,cursor,reason) VALUES(?,?,?,'running',NULL,NULL)",
            (ident, job, self.fence(job)),
        )
        return {
            "fetch_collection_id": ident,
            "resume_scope_id": scope,
            "state": "running",
            "cursor": None,
            "change_request_id": pr,
            "kind": kind,
        }

    def payload(self, raw):
        digest = hashlib.sha256(raw).digest()
        row = self.s.one(
            "SELECT payload_id FROM payloads WHERE sha256=? AND body=?", (digest, raw)
        )
        if row:
            return row[0]
        return self.s.execute(
            "INSERT INTO payloads(sha256,body,byte_length,representation) VALUES(?,?,?,'decoded_api')",
            (digest, raw, len(raw)),
        ).lastrowid

    def page(self, collection, response, request, next_cursor, *, advance=True):
        ordinal = self.s.one(
            "SELECT coalesce(max(ordinal),-1)+1 FROM fetch_occurrences WHERE fetch_collection_id=?",
            (collection["fetch_collection_id"],),
        )[0]
        timestamp = now_us()
        ident = self.s.execute(
            "INSERT INTO fetch_occurrences(fetch_collection_id,ordinal,payload_id,request,next_cursor,observed_at_us,parsed_at_us) VALUES(?,?,?,?,?,?,?)",
            (
                collection["fetch_collection_id"],
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
                "UPDATE collection_progress SET cursor=? WHERE fetch_collection_id=?",
                (next_cursor, collection["fetch_collection_id"]),
            )
        return ident, ordinal, timestamp

    def finish(self, collection, *, evidence=None, observed_at_us=None):
        if observed_at_us is None:
            observed_at_us = self.observed_at_us(collection)
        self.s.execute(
            "UPDATE collection_progress SET state='complete',cursor=NULL,reason=NULL WHERE fetch_collection_id=?",
            (collection["fetch_collection_id"],),
        )
        self.s.execute(
            "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,?,'complete',?,?)",
            (
                collection["resume_scope_id"],
                collection["fetch_collection_id"],
                canonical(evidence or {"parser": PARSER, "terminal": True}),
                observed_at_us,
            ),
        )

    def observed_at_us(self, collection):
        """Latest actual saved response; starting or replaying a scan adds no time."""
        return self.s.one(
            "SELECT MAX(observed_at_us) FROM fetch_occurrences WHERE fetch_collection_id=? AND coalesce(json_extract(request,'$.operational_only'),0)=0",
            (collection["fetch_collection_id"],),
        )[0]

    def thread_observed_at_us(self, collection):
        """Include every child associated with this root, including earlier resumes."""
        return self.s.one(
            """SELECT MAX(o.observed_at_us)
               FROM fetch_collections root
               JOIN fetch_collections member
                 ON member.repository_uuidv4=root.repository_uuidv4
                AND member.change_request_id IS root.change_request_id
                AND member.source_id IS root.source_id
               JOIN resume_scopes scope ON scope.resume_scope_id=member.resume_scope_id
               JOIN fetch_occurrences o ON o.fetch_collection_id=member.fetch_collection_id
               WHERE root.fetch_collection_id=?
                 AND coalesce(json_extract(o.request,'$.operational_only'),0)=0
                 AND (member.fetch_collection_id=root.fetch_collection_id
                      OR (member.kind='thread-comments'
                          AND json_extract(scope.request_context,'$.parent_fetch_collection_id')
                              =root.fetch_collection_id))""",
            (collection["fetch_collection_id"],),
        )[0]

    def pending_response(self, collection):
        """Whether acquisition still requires a response, not just local completion."""
        page = self.s.one(
            "SELECT next_cursor FROM fetch_occurrences WHERE fetch_collection_id=? ORDER BY ordinal DESC,fetch_occurrence_id DESC LIMIT 1",
            (collection["fetch_collection_id"],),
        )
        return page is None or page["next_cursor"] is not None

    def partial(self, collection, reason):
        self.s.execute(
            "UPDATE collection_progress SET state='partial',reason=? WHERE fetch_collection_id=?",
            (reason, collection["fetch_collection_id"]),
        )

    def origin(self, collection, occurrence, position):
        return f"api:{collection['fetch_collection_id']}:{occurrence}:{position}"

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
        observed_at_us,
        *,
        thread=None,
    ):
        if not isinstance(body, str):
            raise CatalogError("API_SCHEMA", "Expected document text")
        key = DocumentKey(pr, kind, str(provider))
        predicate = (
            "change_request_id=? AND kind=? AND provider_change_request_document_id=?"
        )
        found = self.s.one("SELECT * FROM documents WHERE " + predicate, key)
        origin = self.origin(collection, occurrence, position)
        if found and self.s.one(
            "SELECT 1 FROM document_observations WHERE "
            + predicate
            + " AND origin_key=?",
            (*key, origin),
        ):
            # Parsing the same admitted response again is not a new observation
            # and cannot overwrite a later current projection.
            return key
        author = value.get("user") or value.get("author") or {}
        metadata = {
            field: item
            for field, item in value.items()
            if field not in ("body", "title", "user", "author")
        }
        if thread:
            metadata["review_thread_provider_resource_id"] = thread
        projection = (
            author.get("login"),
            value.get("html_url") or value.get("url"),
            canonical(metadata),
        )
        if found:
            self.s.execute(
                "UPDATE documents SET author=?,url=?,metadata=?,deleted=0 WHERE "
                + predicate,
                (*projection, *key),
            )
        else:
            self.s.execute(
                "INSERT INTO documents(change_request_id,kind,provider_change_request_document_id,current_document_observation_id,deleted,author,url,metadata) VALUES(?,?,?,NULL,0,?,?,?)",
                (*key, *projection),
            )
        digest = intern_text_body(self.s.connection, body)
        owner_occurrence = (
            occurrence if collection.get("change_request_id") == pr else None
        )
        observation = self.s.execute(
            "INSERT INTO document_observations(change_request_id,kind,provider_change_request_document_id,text_body_sha256,observed_at_us,parsed_at_us,origin_key,fetch_occurrence_id,metadata) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                *key,
                digest,
                observed_at_us,
                now_us(),
                origin,
                owner_occurrence,
                canonical(metadata),
            ),
        ).lastrowid
        self.s.execute(
            "UPDATE documents SET current_document_observation_id=? WHERE " + predicate,
            (observation, *key),
        )
        if collection.get("change_request_id") == pr and not self.s.one(
            "SELECT 1 FROM collection_memberships WHERE fetch_collection_id=? AND "
            + predicate,
            (collection["fetch_collection_id"], *key),
        ):
            self.s.execute(
                "INSERT INTO collection_memberships(fetch_collection_id,change_request_id,kind,provider_change_request_document_id,ordinal) VALUES(?,?,?,?,?)",
                (collection["fetch_collection_id"], *key, position),
            )
        if kind == "review":
            if self.s.one("SELECT 1 FROM reviews WHERE " + predicate, key):
                self.s.execute(
                    "UPDATE reviews SET payload=? WHERE " + predicate,
                    (canonical(value), *key),
                )
            else:
                self.s.execute(
                    "INSERT INTO reviews(change_request_id,kind,provider_change_request_document_id,payload) VALUES(?,?,?,?)",
                    (*key, canonical(value)),
                )
        if kind == "review-comment":
            if self.s.one("SELECT 1 FROM review_comments WHERE " + predicate, key):
                self.s.execute(
                    "UPDATE review_comments SET review_thread_provider_resource_id=coalesce(?,review_thread_provider_resource_id),payload=? WHERE "
                    + predicate,
                    (thread, canonical(value), *key),
                )
            else:
                self.s.execute(
                    "INSERT INTO review_comments(change_request_id,kind,provider_change_request_document_id,review_thread_provider_resource_id,payload) VALUES(?,?,?,?,?)",
                    (*key, thread, canonical(value)),
                )
        return key
