"""Catalog3 API facts and restart boundaries, shared by REST and GraphQL."""

from __future__ import annotations

import hashlib
import json
import uuid

from repo_catalog.adapters.sqlite.json_contracts import validate_record
from repo_catalog.adapters.sqlite.parser_model import ParserModel
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.adapters.sqlite.text_bodies import intern_text_body
from repo_catalog.domain.document import DocumentKey
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.time import now_us, validate_epoch_us

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
        self.model = ParserModel(store.connection)
        self.profile_uuid = None
        self.results = {}
        self.pending_results = {}
        self.select_results = True
        self.response_identities = {}
        self.unselected_results = set()

    def current_context(self, repo, pr, endpoint, kind=None):
        """Typed provider owner and acquisition scope, without retained HTTP input."""
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
        from repo_catalog.adapters.sqlite.current_resources import CurrentResources

        candidate = {**candidate, "parsed_at_us": now_us()}
        resources = CurrentResources(self.s)
        result = resources.admit(
            candidate,
            source="live",
            base_revision=base_revision,
            scope_context=candidate["acquisition_scope"],
        )
        resources.promote_staging()
        return result

    def profile(self):
        if self.profile_uuid is None or not self.s.one(
            "SELECT 1 FROM parser_profiles WHERE parser_profile_uuidv4=?",
            (self.profile_uuid,),
        ):
            self.profile_uuid = self.model.ensure_builtin_profile()
        return self.profile_uuid

    def result(self, occurrence):
        """One local parsing execution, separate from the immutable remote fetch."""
        cached = self.results.get(occurrence)
        if cached and self.s.one(
            "SELECT 1 FROM parsed_results WHERE parsed_result_uuidv4=?", (cached,)
        ):
            return cached
        row = self.s.one(
            "SELECT fetch_occurrence_uuidv4,repository_uuidv4 FROM fetch_occurrences WHERE fetch_occurrence_id=?",
            (occurrence,),
        )
        if row is None:
            raise CatalogError("PARSER_INPUT_MISSING", "Saved acquisition is required")
        ident = self.model.create_result(
            self.profile(),
            repository_uuidv4=row["repository_uuidv4"],
            inputs=[{"fetch_occurrence_uuidv4": row["fetch_occurrence_uuidv4"]}],
            derivation={"parser": PARSER},
        )
        self.results[occurrence] = ident
        self.pending_results[ident] = {}
        return ident

    def ownership(self, occurrence):
        row = self.s.one(
            "SELECT repository_uuidv4 FROM fetch_occurrences WHERE fetch_occurrence_id=?",
            (occurrence,),
        )
        return row[0], self.result(occurrence)

    def choose_page(self, collection, occurrence):
        fact_kind = {
            "timeline": "events",
            "pr-commits": "code",
            "pr-files": "code",
        }.get(collection.get("kind"))
        if fact_kind:
            fetch_uuid = self.s.one(
                "SELECT fetch_occurrence_uuidv4 FROM fetch_occurrences WHERE fetch_occurrence_id=?",
                (occurrence,),
            )[0]
            self.choose(
                self.result(occurrence),
                fact_kind=fact_kind,
                change_request_id=collection["change_request_id"],
                fetch_occurrence_uuidv4=fetch_uuid,
            )

    def choose(self, result, **scope):
        choices = self.pending_results.setdefault(result, {})
        choices.setdefault(tuple(sorted(scope.items())), scope)

    def publish(self):
        """Seal each complete parsing transaction before publishing selections."""
        for result, scopes in list(self.pending_results.items()):
            owner = self.s.one(
                "SELECT repository_uuidv4,source_registration_uuidv4 FROM parsed_results WHERE parsed_result_uuidv4=?",
                (result,),
            )
            if owner is None:  # A rejected page rolled back this execution.
                del self.pending_results[result]
                continue
            self.model.publish_result(result)
            if self.select_results:
                for scope in scopes.values():
                    selected = self.model.ensure_scope_profile(
                        self.profile(),
                        repository_uuidv4=owner[0],
                        source_registration_uuidv4=owner[1],
                        fact_kind=scope["fact_kind"],
                    )
                    if selected is None:
                        self.unselected_results.add(result)
                        continue
                    if scope.get("change_request_id") and not self.s.one(
                        "SELECT 1 FROM effective_change_request_parser_profiles WHERE change_request_id=? AND fact_kind=? AND parser_profile_uuidv4=?",
                        (
                            scope["change_request_id"],
                            scope["fact_kind"],
                            self.profile(),
                        ),
                    ):
                        self.unselected_results.add(result)
                        continue
                    try:
                        self.model.select_fact(result, **scope)
                    except CatalogError as error:
                        if error.code != "SELECTION_UNRESOLVED":
                            raise
                        self.unselected_results.add(result)
            del self.pending_results[result]
        self.s.publish()
        self.response_identities.clear()

    def source_input(self, source_registration_uuidv4, response, context):
        ident = str(uuid.uuid4())
        timestamp = self.response_time(response)
        payload = self.payload(response.content)
        self.s.execute(
            "INSERT INTO source_input_observations(source_input_uuidv4,source_registration_uuidv4,payload_representation,payload_sha256,request_context_json,observed_at_us) VALUES(?,?,?,?,?,?)",
            (
                ident,
                source_registration_uuidv4,
                *payload.parameters(),
                canonical(context),
                timestamp,
            ),
        )
        return ident, timestamp, payload

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

    def require_payload(self, digest):
        from repo_catalog.adapters.sqlite.cas_integrity import is_quarantined

        if is_quarantined(self.s.connection, digest):
            raise CatalogError(
                "PAYLOAD_CORRUPTION", "Quarantined payload requires explicit repair"
            )

    def payload(self, raw):
        return intern_payload(self.s.connection, raw, representation="decoded_api")

    @staticmethod
    def response_time(response):
        """Reuse the actual live response clock even if its transaction failed."""
        try:
            return validate_epoch_us(
                response.extensions.setdefault("catalog_observed_at_us", now_us())
            )
        except (TypeError, ValueError):
            raise CatalogError(
                "API_SCHEMA", "Invalid live response observation timestamp"
            ) from None

    @staticmethod
    def response_metadata(response):
        """Preserve whitelisted historical evidence, independently of validators."""
        etag = response.headers.get("etag")
        return {
            "status": response.status_code,
            "headers": {"etag": etag} if etag is not None else {},
        }

    def page(self, collection, response, request, next_cursor, *, advance=True):
        request = {**request, "response": self.response_metadata(response)}
        ordinal = self.s.one(
            "SELECT coalesce(max(ordinal),-1)+1 FROM fetch_occurrences WHERE fetch_collection_id=?",
            (collection["fetch_collection_id"],),
        )[0]
        response_identity = self.response_identities.get(id(response))
        if response_identity is None or response_identity[0] is not response:
            response_identity = (
                response,
                str(uuid.uuid4()),
                self.response_time(response),
            )
            self.response_identities[id(response)] = response_identity
        fetch_uuid, timestamp = response_identity[1:]
        repository = self.s.one(
            "SELECT repository_uuidv4 FROM fetch_collections WHERE fetch_collection_id=?",
            (collection["fetch_collection_id"],),
        )[0]
        payload = self.payload(response.content)
        ident = self.s.execute(
            "INSERT INTO fetch_occurrences(fetch_occurrence_uuidv4,repository_uuidv4,fetch_collection_id,ordinal,payload_representation,payload_sha256,request,next_cursor,observed_at_us,parsed_at_us) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                fetch_uuid,
                repository,
                collection["fetch_collection_id"],
                ordinal,
                *payload.parameters(),
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
            observed_at_us = self.observed_at_us(collection, include_partial=False)
        self.s.execute(
            "UPDATE collection_progress SET state='complete',cursor=NULL,reason=NULL WHERE fetch_collection_id=?",
            (collection["fetch_collection_id"],),
        )
        evidence = dict(evidence or {"parser": PARSER, "terminal": True})
        if evidence.get("kind") == "current-resource-pages-v1":
            from repo_catalog.adapters.sqlite.current_collections import (
                CurrentCollectionProof,
            )

            proof = CurrentCollectionProof(self.s.connection).evidence(
                collection["fetch_collection_id"]
            )
            if proof != evidence:
                raise CatalogError(
                    "INVALID_PROVENANCE",
                    "Current collection has no valid terminal proof",
                )
            self.s.execute(
                "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,?,'complete',?,?)",
                (
                    collection["resume_scope_id"],
                    collection["fetch_collection_id"],
                    canonical(evidence),
                    observed_at_us,
                ),
            )
            return
        if (
            collection.get("kind") in {"pr-detail", "pr-code-check"}
            and "change_request_observation_uuidv4" not in evidence
        ):
            observations = self.s.all(
                "SELECT o.change_request_observation_uuidv4,o.parsed_result_uuidv4,f.fetch_occurrence_uuidv4 FROM change_request_observations o JOIN fetch_occurrences f ON f.fetch_occurrence_id=o.origin_fetch_occurrence_id WHERE f.fetch_collection_id=?",
                (collection["fetch_collection_id"],),
            )
            if len(observations) == 1:
                evidence.update(dict(observations[0]))
        if evidence.get("change_request_observation_uuidv4"):
            anchor = self.s.one(
                "SELECT o.change_request_observation_uuidv4,o.parsed_result_uuidv4,f.fetch_occurrence_uuidv4,f.payload_representation,f.payload_sha256 FROM change_request_observations o JOIN fetch_occurrences f ON f.fetch_occurrence_id=o.origin_fetch_occurrence_id JOIN fetch_collections c ON c.fetch_collection_id=? WHERE o.change_request_observation_uuidv4=? AND o.change_request_id=c.change_request_id AND o.repository_uuidv4=c.repository_uuidv4",
                (
                    collection["fetch_collection_id"],
                    evidence["change_request_observation_uuidv4"],
                ),
            )
            if anchor is None:
                raise CatalogError(
                    "INVALID_PROVENANCE",
                    "Completion observation has a different owner or is unavailable",
                )
            from repo_catalog.domain.payload import PayloadRef

            if (
                "payload" in evidence
                and evidence["payload"]
                != PayloadRef(
                    anchor["payload_representation"], anchor["payload_sha256"]
                ).as_json()
            ):
                raise CatalogError(
                    "INVALID_PROVENANCE",
                    "Completion payload differs from its original acquisition",
                )
            for field in ("parsed_result_uuidv4", "fetch_occurrence_uuidv4"):
                if field in evidence and evidence[field] != anchor[field]:
                    raise CatalogError(
                        "INVALID_PROVENANCE",
                        "Completion origin disagrees with its observation",
                    )
                evidence[field] = anchor[field]
        collection_ids = evidence.get(
            "fetch_collection_ids", [collection["fetch_collection_id"]]
        )
        if (
            not isinstance(collection_ids, list)
            or not collection_ids
            or collection["fetch_collection_id"] not in collection_ids
        ):
            raise CatalogError(
                "INVALID_PROVENANCE", "Completion must name its root collection"
            )
        root = self.s.one(
            "SELECT repository_uuidv4,change_request_id FROM fetch_collections WHERE fetch_collection_id=?",
            (collection["fetch_collection_id"],),
        )
        for selected in collection_ids:
            child = self.s.one(
                "SELECT c.repository_uuidv4,c.change_request_id,scope.request_context FROM fetch_collections c JOIN resume_scopes scope USING(resume_scope_id) WHERE c.fetch_collection_id=?",
                (selected,),
            )
            if (
                child is None
                or child[0:2] != root[0:2]
                or (
                    selected != collection["fetch_collection_id"]
                    and json.loads(child[2]).get("parent_fetch_collection_id")
                    != collection["fetch_collection_id"]
                )
            ):
                raise CatalogError(
                    "INVALID_PROVENANCE",
                    "Completion child collection has wrong parent or owner",
                )
        evidence["fetch_occurrence_uuidv4s"] = sorted(
            {
                row[0]
                for selected in collection_ids
                for row in self.s.all(
                    "SELECT fetch_occurrence_uuidv4 FROM fetch_occurrences WHERE fetch_collection_id=?",
                    (selected,),
                )
            }
        )
        from repo_catalog.adapters.sqlite.current_collections import (
            CurrentCollectionProof,
        )

        current_pages = []
        for selected in collection_ids:
            proof = CurrentCollectionProof(self.s.connection)
            if proof.pages(selected):
                metadata = proof.evidence(selected)
                if metadata is None:
                    raise CatalogError(
                        "INVALID_PROVENANCE", "Current child collection is not terminal"
                    )
                current_pages.append(
                    {
                        "fetch_collection_id": selected,
                        "page_ordinals": metadata["page_ordinals"],
                    }
                )
        if current_pages:
            evidence["current_page_collections"] = current_pages
        validate_record(
            self.s.connection,
            "completion_markers",
            {
                "fetch_collection_id": collection["fetch_collection_id"],
                "evidence": canonical(evidence),
            },
        )
        self.s.execute(
            "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,?,'complete',?,?)",
            (
                collection["resume_scope_id"],
                collection["fetch_collection_id"],
                canonical(evidence),
                observed_at_us,
            ),
        )

    def observed_at_us(self, collection, *, include_partial=True):
        """Latest observation, with accepted receipts alone proving completion."""
        return self.s.one(
            "SELECT MAX(observed_at_us) FROM (SELECT observed_at_us FROM fetch_occurrences WHERE fetch_collection_id=? UNION ALL SELECT observed_at_us FROM current_collection_pages WHERE fetch_collection_id=? UNION ALL SELECT observed_at_us FROM completion_markers WHERE fetch_collection_id=? AND asserted_state='partial' AND ?)",
            (collection["fetch_collection_id"],) * 3 + (include_partial,),
        )[0]

    def thread_observed_at_us(self, collection, *, include_partial=True):
        """Include every child associated with this root, including earlier resumes."""
        return self.s.one(
            """SELECT MAX(o.observed_at_us)
               FROM fetch_collections root
               JOIN fetch_collections member
                 ON member.repository_uuidv4=root.repository_uuidv4
                AND member.change_request_id IS root.change_request_id
                AND member.source_id IS root.source_id
               JOIN resume_scopes scope ON scope.resume_scope_id=member.resume_scope_id
               JOIN (SELECT fetch_collection_id,observed_at_us FROM fetch_occurrences
                     UNION ALL SELECT fetch_collection_id,observed_at_us FROM current_collection_pages
                     UNION ALL SELECT fetch_collection_id,observed_at_us FROM completion_markers WHERE asserted_state='partial' AND ?) o
                 ON o.fetch_collection_id=member.fetch_collection_id
               WHERE root.fetch_collection_id=?
                 AND (member.fetch_collection_id=root.fetch_collection_id
                      OR (member.kind='thread-comments'
                          AND json_extract(scope.request_context,'$.parent_fetch_collection_id')
                              =root.fetch_collection_id))""",
            (include_partial, collection["fetch_collection_id"]),
        )[0]

    def pending_response(self, collection):
        """Whether acquisition still requires a response, not just local completion."""
        page = self.s.one(
            "SELECT next_cursor FROM (SELECT ordinal,next_cursor FROM fetch_occurrences WHERE fetch_collection_id=? UNION ALL SELECT ordinal,next_cursor FROM current_collection_pages WHERE fetch_collection_id=?) ORDER BY ordinal DESC LIMIT 1",
            (collection["fetch_collection_id"], collection["fetch_collection_id"]),
        )
        return page is None or page["next_cursor"] is not None

    def partial(self, collection, reason, *, observed_at_us=None):
        self.s.execute(
            "UPDATE collection_progress SET state='partial',reason=? WHERE fetch_collection_id=?",
            (reason, collection["fetch_collection_id"]),
        )
        if observed_at_us is not None:
            # An observed rejected page establishes only an incomplete boundary.
            # No original, member/terminal claim or fictitious fetch is retained.
            self.s.execute(
                "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,?,'partial',?,?)",
                (
                    collection["resume_scope_id"],
                    collection["fetch_collection_id"],
                    canonical({"reason": reason}),
                    observed_at_us,
                ),
            )

    def origin(self, collection, occurrence, position):
        return f"parse:{self.result(occurrence)}:{position}"

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
    ):
        if kind in ("review", "review-comment"):
            raise CatalogError(
                "MUTABLE_RESOURCE",
                "Review resources use the shared current-state store",
            )
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
        if not found:
            self.s.execute(
                "INSERT INTO documents(change_request_id,kind,provider_change_request_document_id) VALUES(?,?,?)",
                key,
            )
        digest = intern_text_body(self.s.connection, body)
        owner_occurrence = (
            occurrence if collection.get("change_request_id") == pr else None
        )
        repository, result = self.ownership(occurrence)
        self.s.execute(
            "INSERT INTO document_observations(document_observation_uuidv4,repository_uuidv4,parsed_result_uuidv4,change_request_id,kind,provider_change_request_document_id,text_body_sha256,observed_at_us,parsed_at_us,origin_key,fetch_occurrence_id,metadata,author,url,deleted) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                repository,
                result,
                *key,
                digest,
                observed_at_us,
                now_us(),
                origin,
                owner_occurrence,
                canonical(metadata),
                author.get("login"),
                value.get("html_url") or value.get("url"),
                0,
            ),
        )
        self.choose(
            result,
            fact_kind=kind,
            change_request_id=pr,
            kind=kind,
            provider_change_request_document_id=str(provider),
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
        return key
