"""Explicit identity evidence routed to its independent owning authority.

Callers supply Repository and/or already scoped Context capabilities. This service
opens no stores, creates no registrations, and never turns provenance into
sender authentication or rewrites either nominal endpoint.
"""

from __future__ import annotations

from repo_catalog.domain.identity_assertions import (
    identity_record,
    identity_status,
    identity_values,
)
from repo_catalog.domain.shared_values import Provenance, RepositoryFailure


class IdentityAssertions:
    def __init__(self, repository_store=None, context=None):
        if repository_store is None and context is None:
            raise ValueError("at least one identity authority is required")
        self.repository_store, self.context = repository_store, context

    def admit(self, kind, record, provenance: Provenance, *, entity_kind=None):
        """Admit a portable original; cancellations require their owning kind.

        Return accepted, duplicate or conflict. An accepted unresolved claim is
        retained evidence, not an active equivalence. A cancellation can precede
        its assertion without a mutable staging record or a fabricated endpoint.
        """
        raw = identity_record(kind, record)
        if kind == "relation":
            actual = record["entity_kind"]
            if entity_kind is not None and entity_kind != actual:
                raise RepositoryFailure(
                    "IDENTITY_RECORD", kind, "identity authority differs"
                )
            entity_kind = actual
        identity_values(kind, entity_kind, raw, provenance)
        authority = (
            self.repository_store if entity_kind == "repository" else self.context
        )
        if authority is None:
            raise RepositoryFailure(
                "IDENTITY_AUTHORITY_UNAVAILABLE",
                entity_kind,
                "owning authority required",
            )
        original = provenance if entity_kind == "repository" else provenance.encoded
        return authority.admit_identity_evidence(kind, raw, original)

    def status(
        self,
        *,
        max_evidence=10000,
        max_bytes=16 * 1024 * 1024,
        max_closure_pairs=100000,
    ):
        """Combine explicitly supplied, independently pinned authority snapshots.

        No shared cross-database snapshot or pairing is claimed. Repository-only use
        cannot touch Context; Context-only use cannot touch Repository. Service links
        resolve solely against the supplied Context capability's Providers.
        """
        combined = None
        authorities = []
        for kind, authority in (
            ("repository", self.repository_store),
            ("service", self.context),
        ):
            if authority is None:
                continue
            snapshot = authority.identity_evidence_snapshot(
                max_evidence=max_evidence, max_bytes=max_bytes
            )
            projected = identity_status(
                snapshot["relations"],
                snapshot["cancellations"],
                repository_uuids=snapshot.get("repository_uuids", ()),
                service_uuids=snapshot.get("service_uuids", ()),
                max_evidence=max_evidence,
                max_closure_pairs=max_closure_pairs,
            )
            for item in (
                projected["identity_conflicts"] + projected["identity_unresolved"]
            ):
                item["entity_kind"] = kind
            if combined is None:
                combined = projected
            else:
                for name, records in projected.items():
                    combined[name].extend(records)
            authorities.append("repository" if kind == "repository" else "context")
        combined["authorities"] = authorities
        return combined
