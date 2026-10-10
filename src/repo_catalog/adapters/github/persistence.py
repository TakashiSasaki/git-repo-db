"""Typed live admission and scoped enumeration, without retained API messages."""

from __future__ import annotations

import hashlib
import json
import uuid

from repo_catalog.adapters.github import current_parser
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.time import now_us, validate_epoch_us

PARSER = "catalog3-github/3"


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def oid_context(value):
    from repo_catalog.domain.models import GitOid

    oids = [(value.get(role) or {}).get("sha") for role in ("head", "base")]
    present = [oid for oid in oids if oid is not None]
    if not present:
        return None, None, None
    algorithm = "sha256" if len(present[0]) == 64 else "sha1"
    return algorithm, *(
        GitOid.parse(algorithm + ":" + oid).value if oid is not None else None
        for oid in oids
    )


class ApiFacts:
    def __init__(self, store, config):
        self.s, self.cfg = store, config
        self.principal = None
        self.permissions = None

    def current_context(self, repo, pr, endpoint, kind=None):
        binding = self.s.one(
            "SELECT b.repository_binding_id,b.service_instance_uuidv4,s.source_registration_uuidv4 FROM repository_bindings b JOIN sources s ON s.service_instance_uuidv4=b.service_instance_uuidv4 WHERE b.repository_uuidv4=? AND s.source_id=? AND b.provider_repository_id=?",
            (
                repo["repository_uuidv4"],
                repo["source_id"],
                repo["provider_repository_id"],
            ),
        )
        if binding is None:
            raise CatalogError("SCOPE_MISMATCH", "Current resource binding is missing")
        scope = {
            "repository_uuidv4": repo["repository_uuidv4"],
            "repository_binding_id": binding["repository_binding_id"],
            "service_instance_uuidv4": binding["service_instance_uuidv4"],
            "endpoint": endpoint,
            "source_registration_uuidv4": binding["source_registration_uuidv4"],
            "principal_ref": self.principal,
            "observed_permissions": self.permissions,
            "api_version": self.cfg["rest_api_version"],
            "preservation_profile": self.s.config["preservation"]["profile"],
            **({"change_request_id": pr} if pr is not None else {}),
        }
        return {
            **{
                key: scope[key]
                for key in (
                    "repository_uuidv4",
                    "repository_binding_id",
                    "service_instance_uuidv4",
                )
            },
            **({"change_request_id": pr} if pr is not None else {}),
            "acquisition_scope": scope,
        }

    def admit_current(self, candidate, base_revision):
        candidate = {**candidate, "parsed_at_us": now_us()}
        if candidate["kind"] in (
            "issue",
            "issue-comment",
            "review",
            "review-comment",
        ) and not (
            candidate["kind"] == "issue-comment" and "change_request_id" in candidate
        ):
            from repo_catalog.adapters.sqlite.current_resources import CurrentResources

            resources = CurrentResources(self.s)
            result = resources.admit(
                candidate,
                source="live",
                base_revision=base_revision,
                scope_context=candidate["acquisition_scope"],
            )
            resources.promote_staging()
            return result
        from repo_catalog.adapters.sqlite.current_api import CurrentApiState

        table = (
            "change_request_state"
            if candidate["kind"] == "change-request"
            else "review_thread_state"
            if candidate["kind"] == "review-thread"
            else "document_state"
        )
        return CurrentApiState(self.s).admit(
            table,
            candidate,
            source="live",
            base_revision=base_revision,
            scope_context=candidate["acquisition_scope"],
        )

    def advance_revision(self):
        self.s.advance_local_revision()

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
            raise CatalogError("STALE_ATTEMPT", "Refusing obsolete API acquisition")
        return row["current_attempt"]

    def scope(self, repo, endpoint, context=None):
        capture = self.current_context(repo, None, endpoint)["acquisition_scope"]
        request_context = {
            "provider_repository_id": repo["provider_repository_id"],
            "rest_page_size": self.cfg["rest_page_size"],
            "graphql_page_size": self.cfg["graphql_page_size"],
            **(context or {}),
        }
        if self.permissions is not None:
            request_context["permissions"] = self.permissions
        scope = {
            **capture,
            "request_context": request_context,
            "parser_module": current_parser.PARSER_MODULE,
            "parser_version": current_parser.PARSER_VERSION,
        }
        ident = "api:" + hashlib.sha256(canonical(scope).encode()).hexdigest()
        if not self.s.one(
            "SELECT 1 FROM resume_scopes WHERE resume_scope_id=?", (ident,)
        ):
            self.s.execute(
                "INSERT INTO resume_scopes(resume_scope_id,repository_uuidv4,repository_binding_id,source_id,principal_ref,api_version,endpoint,request_context,parser_version,confidence) VALUES(?,?,?,?,?,?,?,?,?,'proven')",
                (
                    ident,
                    repo["repository_uuidv4"],
                    capture["repository_binding_id"],
                    repo["source_id"],
                    self.principal,
                    self.cfg["rest_api_version"],
                    endpoint,
                    canonical(request_context),
                    PARSER,
                ),
            )
        return ident, scope

    def begin(self, repo, pr, kind, job, endpoint, context=None, *, reuse=False):
        scope_id, scope = self.scope(repo, endpoint, context)
        if pr is not None:
            scope["change_request_id"] = pr
        scope_json = canonical(scope)
        previous = self.s.one(
            "SELECT f.*,p.state,p.cursor,p.reason FROM fetch_collections f JOIN collection_progress p USING(fetch_collection_id) WHERE f.scope_json=? AND f.change_request_id IS ? AND f.kind=? AND p.job_id=? ORDER BY f.observed_at_us DESC LIMIT 1",
            (scope_json, pr, kind, job),
        )
        if previous is None and reuse:
            previous = self.s.one(
                "SELECT f.*,p.state,p.cursor,p.reason FROM fetch_collections f JOIN collection_progress p USING(fetch_collection_id) WHERE f.scope_json=? AND f.change_request_id IS ? AND f.kind=? AND p.state='complete' ORDER BY f.observed_at_us DESC LIMIT 1",
                (scope_json, pr, kind),
            )
        if (
            previous
            and kind == "threads"
            and previous["reason"] in ("GRAPHQL_ROOT_PARTIAL", "RESUME_UNAVAILABLE")
        ):
            previous = None
        if previous:
            if previous["state"] != "complete":
                self.s.execute(
                    "UPDATE collection_progress SET attempt=?,state='running',reason=NULL WHERE fetch_collection_id=?",
                    (self.fence(job), previous["fetch_collection_id"]),
                )
            return dict(previous)
        ident = str(uuid.uuid4())
        self.s.execute(
            "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,source_id,kind,resume_scope_id,scope_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)",
            (
                ident,
                repo["repository_uuidv4"],
                pr,
                repo["source_id"],
                kind,
                scope_id,
                scope_json,
                now_us(),
            ),
        )
        self.s.execute(
            "INSERT INTO collection_progress(fetch_collection_id,job_id,attempt,state,cursor,reason) VALUES(?,?,?,'running',NULL,NULL)",
            (ident, job, self.fence(job)),
        )
        return {
            "fetch_collection_id": ident,
            "resume_scope_id": scope_id,
            "scope_json": scope_json,
            "state": "running",
            "cursor": None,
            "change_request_id": pr,
            "kind": kind,
        }

    @staticmethod
    def response_time(response):
        try:
            return validate_epoch_us(
                response.extensions.setdefault("catalog_observed_at_us", now_us())
            )
        except (TypeError, ValueError):
            raise CatalogError(
                "API_SCHEMA", "Invalid live response observation timestamp"
            ) from None

    def page(self, collection, timestamp, next_cursor, members, *, status=200):
        from repo_catalog.adapters.sqlite.current_collections import (
            CurrentCollectionProof,
        )

        ordinal = self.s.one(
            "SELECT coalesce(max(ordinal),-1)+1 FROM current_collection_pages WHERE fetch_collection_id=?",
            (collection["fetch_collection_id"],),
        )[0]
        CurrentCollectionProof(self.s.connection).page(
            collection["fetch_collection_id"],
            ordinal,
            timestamp,
            next_cursor,
            members,
            status=status,
            parser_module=current_parser.PARSER_MODULE,
            parser_version=current_parser.PARSER_VERSION,
        )
        self.s.execute(
            "UPDATE collection_progress SET cursor=? WHERE fetch_collection_id=?",
            (next_cursor, collection["fetch_collection_id"]),
        )
        return ordinal

    def finish(self, collection, *, evidence=None, observed_at_us=None):
        from repo_catalog.adapters.sqlite.current_collections import (
            CurrentCollectionProof,
        )

        ident = collection["fetch_collection_id"]
        proof = CurrentCollectionProof(self.s.connection)
        expected = proof.evidence(ident)
        if expected is None:
            raise CatalogError(
                "INVALID_PROVENANCE", "Collection lacks a terminal enumeration"
            )
        evidence = dict(evidence or expected)
        if evidence.get("kind") == "current-resource-pages-v1" and evidence != expected:
            raise CatalogError(
                "INVALID_PROVENANCE",
                "Collection terminal evidence does not match its pages",
            )
        if collection.get("kind") == "threads":
            root = self.s.one(
                "SELECT repository_uuidv4,change_request_id FROM fetch_collections WHERE fetch_collection_id=?",
                (ident,),
            )
            requirements = self.s.all(
                "SELECT r.*,c.repository_uuidv4,c.change_request_id,c.scope_json FROM thread_collection_requirements r LEFT JOIN fetch_collections c ON c.fetch_collection_id=r.child_fetch_collection_id WHERE r.fetch_collection_id=?",
                (ident,),
            )
            for requirement in requirements:
                child_id = requirement["child_fetch_collection_id"]
                if (
                    not child_id
                    or requirement["repository_uuidv4"] != root[0]
                    or requirement["change_request_id"] != root[1]
                ):
                    raise CatalogError(
                        "INVALID_PROVENANCE",
                        "Thread child has wrong owner or is unavailable",
                    )
                context = json.loads(requirement["scope_json"]).get(
                    "request_context", {}
                )
                if (
                    context.get("parent_fetch_collection_id") != ident
                    or context.get("provider_resource_id")
                    != requirement["provider_resource_id"]
                    or context.get("parent_observed_at_us")
                    != requirement["required_observed_at_us"]
                    or proof.evidence(child_id) is None
                ):
                    raise CatalogError(
                        "INVALID_PROVENANCE",
                        "Thread child does not discharge its exact captured requirement",
                    )
                marker = self.s.one(
                    "SELECT 1 FROM completion_markers WHERE fetch_collection_id=? AND asserted_state='complete'",
                    (child_id,),
                )
                if marker is None:
                    raise CatalogError(
                        "INVALID_PROVENANCE", "Required thread child is incomplete"
                    )
            evidence = {
                **expected,
                "kind": "current-resource-tree-v1",
                "fetch_collection_ids": [
                    row["child_fetch_collection_id"] for row in requirements
                ],
            }
        if observed_at_us is None:
            observed_at_us = (
                self.thread_observed_at_us(collection, include_partial=False)
                if collection.get("kind") == "threads"
                else self.observed_at_us(collection, include_partial=False)
            )
        self.s.execute(
            "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,?,'complete',?,?)",
            (
                collection.get("resume_scope_id"),
                ident,
                canonical(evidence),
                observed_at_us,
            ),
        )
        self.s.execute(
            "UPDATE collection_progress SET state='complete',cursor=NULL,reason=NULL WHERE fetch_collection_id=?",
            (ident,),
        )

    def observed_at_us(self, collection, *, include_partial=True):
        return self.s.one(
            "SELECT MAX(observed_at_us) FROM (SELECT observed_at_us FROM current_collection_pages WHERE fetch_collection_id=? UNION ALL SELECT observed_at_us FROM completion_markers WHERE fetch_collection_id=? AND asserted_state='partial' AND ?)",
            (
                collection["fetch_collection_id"],
                collection["fetch_collection_id"],
                include_partial,
            ),
        )[0]

    def thread_observed_at_us(self, collection, *, include_partial=True):
        return self.s.one(
            "SELECT MAX(observed_at_us) FROM (SELECT observed_at_us FROM current_collection_pages WHERE fetch_collection_id=? OR fetch_collection_id IN (SELECT child_fetch_collection_id FROM thread_collection_requirements WHERE fetch_collection_id=?) UNION ALL SELECT observed_at_us FROM completion_markers WHERE (fetch_collection_id=? OR fetch_collection_id IN (SELECT child_fetch_collection_id FROM thread_collection_requirements WHERE fetch_collection_id=?)) AND asserted_state='partial' AND ?)",
            (collection["fetch_collection_id"],) * 4 + (include_partial,),
        )[0]

    def pending_response(self, collection):
        row = self.s.one(
            "SELECT has_next FROM current_collection_pages WHERE fetch_collection_id=? ORDER BY ordinal DESC LIMIT 1",
            (collection["fetch_collection_id"],),
        )
        return row is None or bool(row["has_next"])

    def partial(self, collection, reason, *, observed_at_us=None):
        self.s.execute(
            "UPDATE collection_progress SET state='partial',reason=? WHERE fetch_collection_id=?",
            (reason, collection["fetch_collection_id"]),
        )
        if observed_at_us is not None:
            self.s.execute(
                "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,?,'partial',?,?)",
                (
                    collection.get("resume_scope_id"),
                    collection["fetch_collection_id"],
                    canonical({"reason": reason}),
                    observed_at_us,
                ),
            )
