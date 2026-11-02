"""Bounded Context Resource/exact-text reader without concrete Core or paired code."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass

from repo_catalog.adapters.sqlite.catalog_runtime import catalog_completion
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.query_runtime import QueryReader, _stored_view
from repo_catalog.domain.context_query import ContextResourceView
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.production_context import ResourceRelation
from repo_catalog.domain.query_contracts import (
    ByteReadResult,
    QueryError,
    SnapshotFenceToken,
)


@dataclass
class PinnedContextSnapshot:
    mode: str
    token: SnapshotFenceToken
    context: Context
    core: object = None


class ContextResourceReader:
    def get_context_resource(
        self,
        resource_key: ResourceKey,
        *,
        include_text: bool = True,
    ) -> ContextResourceView:
        with self.open_snapshot(required_store="context") as snap:
            assert snap.context is not None
            validate_core = None
            if snap.core is not None:
                core_ref = snap.core

                def _check_core(fmt: str, oid_hex: str) -> bool:
                    return bool(
                        core_ref.sql(
                            "SELECT 1 FROM git_objects WHERE object_format=? AND object_oid=?",
                            (fmt, oid_hex),
                        )
                    )

                validate_core = _check_core
            return self._context_resource_in_snapshot(
                snap.context,
                resource_key,
                include_text=include_text,
                validate_core=validate_core,
            )

    @_stored_view
    def _context_resource_in_snapshot(
        self,
        context: Context,
        resource_key: ResourceKey,
        *,
        include_text: bool = True,
        validate_core: Callable[[str, str], bool] | None = None,
    ) -> ContextResourceView:
        from repo_catalog.domain.p1_context import ResourceKey
        from repo_catalog.domain.production_context import CollectionObservation

        row = context.db.execute(
            "SELECT identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id "
            "FROM resources WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
            resource_key.coordinates(),
        ).fetchone()
        if row is None:
            raise QueryError(
                "RESOURCE_NOT_FOUND",
                resource_key,
                f"Context resource {resource_key} not found",
            )
        identification = context.identification(resource_key)
        identifier_namespace = (
            self._stored(
                ResourceKey,
                resource_key.service_instance_uuidv4,
                identification.identifier_namespace_kind,
                identification.identifier_namespace_id,
            )
            if identification.identifier_namespace_kind is not None
            else None
        )
        document_kind = identification.document_kind
        provider_document_id = identification.provider_document_id

        field_names = [
            r[0]
            for r in context.db.execute(
                "SELECT DISTINCT field_name FROM field_candidates "
                "WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? "
                "ORDER BY field_name",
                resource_key.coordinates(),
            ).fetchall()
        ]
        fields: dict[str, tuple] = {}
        for fname in field_names:
            fields[fname] = context.candidates(resource_key, fname)

        repo_roles = context.provider_repository_roles(
            resource_key, evidence=self.mapping_evidence
        )
        repo_relations = context.repository_relations(
            resource_key, evidence=self.mapping_evidence
        )
        primary_kind = {
            "issue": "owning_repository",
            "pull_request": "base_repository",
        }.get(resource_key.resource_kind)
        primary = tuple(r for r in repo_roles if r.scope.relation_kind == primary_kind)
        # Convenience projection only when every current report agrees on one
        # undisputed Mapping candidate. Full qualified alternatives remain below.
        targets = {
            target
            for role in primary
            if role.mapping is not None
            for target in role.mapping.active_repository_uuidv4s
        }
        repo_uuid = (
            next(iter(targets))
            if len(targets) == 1
            and primary
            and all(r.state == "single_candidate" for r in primary)
            else None
        )

        resolved_texts: dict[str, str | None] = {}
        if include_text and "text_body_sha256" in fields:
            for cand in fields["text_body_sha256"]:
                digest = json.loads(cand.value_json)
                if digest is None:
                    resolved_texts[cand.provenance_json] = None
                elif isinstance(digest, str):
                    resolved_texts[digest] = context.read_text(digest)

        rel_kinds = [
            r[0]
            for r in context.db.execute(
                "SELECT DISTINCT relation_kind FROM resource_relations "
                "WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? "
                "ORDER BY relation_kind",
                resource_key.coordinates(),
            ).fetchall()
        ]
        all_relations: list[ResourceRelation] = []
        for rkind in rel_kinds:
            all_relations.extend(context.relations(resource_key, rkind))

        col_rows = context.db.execute(
            "SELECT c.collection_kind,c.provenance_json,c.scope_json,"
            "t.observed_at_us,t.terminal_state,t.members_json "
            "FROM collections c JOIN collection_terminals t "
            "ON c.service_instance_uuidv4=t.service_instance_uuidv4 "
            "AND c.resource_kind=t.resource_kind "
            "AND c.provider_resource_id=t.provider_resource_id "
            "AND c.collection_kind=t.collection_kind "
            "AND c.provenance_json=t.provenance_json "
            "WHERE c.service_instance_uuidv4=? AND c.resource_kind=? AND c.provider_resource_id=? "
            "ORDER BY c.collection_kind,t.observed_at_us,c.provenance_json",
            resource_key.coordinates(),
        ).fetchall()
        collections = tuple(
            self._stored(
                CollectionObservation,
                resource=resource_key,
                collection_kind=cr[0],
                provenance_json=cr[1],
                scope_json=cr[2],
                observed_at_us=cr[3],
                state=cr[4],
                members=tuple(self._stored(ResourceKey, *m) for m in json.loads(cr[5])),
            )
            for cr in col_rows
        )

        core_deps = context.core_dependencies(resource_key, validate=validate_core)

        return ContextResourceView(
            resource=resource_key,
            repository_uuidv4=repo_uuid,
            repository_roles=repo_roles,
            repository_relations=repo_relations,
            identification=identification,
            identifier_namespace=identifier_namespace,
            document_kind=document_kind,
            provider_document_id=provider_document_id,
            fields=fields,
            resolved_texts=resolved_texts,
            relations=tuple(all_relations),
            collections=collections,
            core_dependencies=core_deps,
        )

    def read_context_text(self, text_sha256: str) -> ByteReadResult:
        from repo_catalog.domain.production_context import ContextError

        with self.open_snapshot(required_store="context") as snap:
            assert snap.context is not None
            try:
                text_val = snap.context.read_text(text_sha256)
            except ContextError as error:
                if error.code == "TEXT_UNAVAILABLE":
                    return ByteReadResult(available=False, verified=False)
                raise
            raw = text_val.encode("utf-8")
            return ByteReadResult(
                available=True,
                verified=True,
                body_bytes=raw,
                text_value=text_val,
                declared_size=len(raw),
                digest_sha256=text_sha256,
            )


class ContextQueryService(ContextResourceReader, QueryReader):
    """Pilot: Context Resource/text reads only; paired/Core/Search APIs are absent."""

    def __init__(self, *args, mapping_evidence=None, **kwargs):
        if mapping_evidence is not None:
            from repo_catalog.domain.p1_context import MappingOperationEvidence

            if not isinstance(mapping_evidence, MappingOperationEvidence):
                raise ValueError("MappingOperationEvidence required")
        self.mapping_evidence = mapping_evidence
        super().__init__(*args, **kwargs)

    def detect_mode(self):
        self._check_stop()
        if self._requested_mode in ("paired", "core_only") or (
            self._requested_mode == "auto"
            and (self.directory / "core.sqlite3").is_file()
        ):
            raise QueryError(
                "MISSING_CAPABILITY",
                "query",
                "Core/paired Query capability is not installed; select context_only explicitly",
            )
        if not (self.directory / "context.sqlite3").is_file():
            raise QueryError(
                "STORE_UNAVAILABLE", "context_only", "context.sqlite3 is required"
            )
        return "context_only"

    @contextmanager
    def _open_snapshot(self, *, required_store="any"):
        self.detect_mode()
        if required_store not in ("any", "context"):
            raise QueryError(
                "MISSING_CAPABILITY", required_store, "Context reader capability only"
            )
        with Context.snapshot(self.directory, read_limits=self.read_limits) as context:
            identity_started = time.perf_counter_ns()
            repo_id, inst_id = context.snapshot_identity()
            self.last_costs_ns["authority_identity_validation"] = (
                time.perf_counter_ns() - identity_started
            )
            token_started = time.perf_counter_ns()
            ctx_hash = context.snapshot_fingerprint()
            self.last_costs_ns["snapshot_token_generation"] = (
                time.perf_counter_ns() - token_started
            )
            token = SnapshotFenceToken(
                mode="context_only",
                repository_uuidv4=repo_id,
                catalog_instance_uuidv4=inst_id,
                core_sha256=None,
                context_sha256=ctx_hash,
            )
            yield PinnedContextSnapshot(
                mode="context_only",
                token=token,
                context=context,
            )
            with catalog_completion(self.directory):
                self._check_stop()
