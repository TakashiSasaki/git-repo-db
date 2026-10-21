"""Audit-only synthetic counterexamples against the unchanged production facade.

Provider names are labels for synthetic normalized input, not live API acceptance.
Run with the checkout's supported interpreter and ``pytest -c pyproject.toml``.
"""

import sqlite3
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.acquisition import ProviderAcquisition
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.acquisition import ProviderIntakeBatch, ProviderRegistration
from repo_catalog.domain.exchange import ExchangeSelectionScope
from repo_catalog.domain.p1_context import (
    CoverageScope,
    FieldCandidate,
    FieldClock,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.production_context import (
    CollectionObservation,
    ContextError,
    ResourceRelation,
)


def catalog(path):
    path.mkdir()
    repository, instance = str(uuid4()), str(uuid4())
    for role in ("core", "context", "operational"):
        initialize(path / f"{role}.sqlite3", role, repository, instance)
    return repository


def observation(owner, members=(), *, provenance=None, state="complete", stamp=100):
    return CollectionObservation(
        owner,
        "analysis_results",
        provenance or canonical({"source": "synthetic-provider", "evidence": "run-1"}),
        canonical({"coverage_kind": "analysis_results", "visibility": "credential-A"}),
        stamp,
        state,
        members,
    )


def claim(obs, state=None):
    return CoverageClaim(
        CoverageScope.collection(
            obs.resource, obs.collection_kind, obs.provenance_json, obs.collection_kind
        ),
        obs.observed_at_us,
        state or obs.state,
    )


def seed(path, *, provider="gitlab", state="complete", members=True):
    catalog(path)
    service = str(uuid4())
    owner = ResourceKey(service, "repository", "42")
    member = ResourceKey(service, "assessment", "job:17")
    obs = observation(owner, (member,) if members else (), state=state)
    # Generic normalized intake exists; this deliberately does not invoke the
    # GitHub raw-payload normalizers for a different Provider.
    ProviderAcquisition(path).admit_batch(
        ProviderIntakeBatch(
            service_instance_uuidv4=service,
            providers=(ProviderRegistration(service, provider),),
            collection_proofs=((claim(obs), obs, obs.scope_json),),
        )
    )
    return owner, member, obs


@pytest.mark.parametrize("provider", ["github", "gitlab", "gerrit", "forgejo"])
def test_generic_normalized_collection_typed_exchange_replay(tmp_path, provider):
    source, target = tmp_path / "source", tmp_path / "target"
    owner, member, obs = seed(source, provider=provider)
    catalog(target)
    annotation = ResourceKey(
        owner.service_instance_uuidv4, "annotation", "local-note:9"
    )
    provenance = canonical({"source": "synthetic-local-author", "evidence": "note-9"})
    candidate = FieldCandidate(
        member,
        "external_result",
        canonical({"status": "warning", "rule": "A-1"}),
        FieldClock("synthetic-analyzer", 97),
        provenance,
        100,
    )
    relation = ResourceRelation(
        annotation, "annotates", (owner, member), provenance, "{}", 100
    )
    with Context.transaction(source) as ctx:
        ctx.resource(annotation)
        ctx.admit_field(candidate)
        ctx.admit_text(
            annotation,
            "Synthetic independent analysis note",
            FieldClock("local-author", 98),
            provenance,
            100,
        )
        ctx.relation(relation)
    source_view = ProductionQueryService(source).get_context_resource(owner)
    assert source_view.collections == (obs,)
    package = ExchangeService(source).export_package(
        selection=ExchangeSelectionScope(all_selected=True, include_core=False)
    )
    receiver = ExchangeService(target)
    receiver.import_package(package, new_request=True)
    received = ProductionQueryService(target).get_context_resource(owner)
    assert received.collections == source_view.collections
    with Context.snapshot(target) as ctx:
        assert ctx.coverage(claim(obs).scope).state == "complete"
        assert member in ctx.resources()
        before = ctx.db.execute("SELECT * FROM collection_terminals").fetchall()
        assert ctx.candidates(member, "external_result") == (candidate,)
        assert ctx.relations(annotation, "annotates") == (relation,)
    note = ProductionQueryService(target).get_context_resource(annotation)
    assert "Synthetic independent analysis note" in note.resolved_texts.values()
    assert note.relations == (relation,)
    assert receiver.import_package(package, new_request=True).idempotent_replay
    with Context.snapshot(target) as ctx:
        assert ctx.db.execute("SELECT * FROM collection_terminals").fetchall() == before
        assert ctx.coverage(claim(obs).scope).observed_at_us == 100


def test_empty_is_evidenced_and_missing_is_unknown(tmp_path):
    path = tmp_path / "catalog"
    owner, _, obs = seed(path, members=False)
    with Context.snapshot(path) as ctx:
        empty = ctx.coverage(claim(obs).scope)
        missing = ctx.coverage(CoverageScope.resource(owner, "never_requested"))
        assert empty.state == "complete" and empty.known_empty
        assert missing.state == "unknown" and not missing.known_empty
        assert missing.observed_at_us is None
        assert (
            len(ctx.db.execute("PRAGMA table_xinfo(coverage_claims)").fetchall()) == 5
        )


def test_partial_members_cannot_prove_complete(tmp_path):
    path = tmp_path / "catalog"
    _, _, obs = seed(path, state="partial")
    with Context.transaction(path) as ctx:
        with pytest.raises(sqlite3.IntegrityError):
            ctx.prove_collection(
                claim(obs, "complete"), obs, required_scope_json=obs.scope_json
            )
        assert ctx.coverage(claim(obs).scope).state == "partial"


def test_newer_unknown_terminal_invalidates_old_complete_without_rewrite(tmp_path):
    path = tmp_path / "catalog"
    _, _, obs = seed(path)
    with Context.transaction(path) as ctx:
        ctx.collection(replace(obs, observed_at_us=101, state="unknown", members=()))
        current = ctx.coverage(claim(obs).scope)
        assert current.state == "unknown" and not current.known_empty
        assert current.claims == (claim(obs),)
        assert current.observed_at_us == 100


def test_permission_and_clock_domains_use_distinct_provenance_scopes(tmp_path):
    path = tmp_path / "catalog"
    _, _, obs = seed(path)
    other = replace(
        obs,
        provenance_json=canonical(
            {"source": "synthetic-provider", "evidence": "clock-B/credential-B"}
        ),
        scope_json=canonical(
            {
                "coverage_kind": "analysis_results",
                "visibility": "credential-B",
                "clock_domain": "B",
            }
        ),
        observed_at_us=1,
        state="partial",
    )
    with Context.transaction(path) as ctx:
        ctx.collection(other)
        ctx.prove_collection(claim(other), other, required_scope_json=other.scope_json)
        assert ctx.coverage(claim(obs).scope).state == "complete"
        assert ctx.coverage(claim(other).scope).state == "partial"
        with pytest.raises(ContextError, match="EVIDENCE_REBIND"):
            ctx.collection(replace(obs, scope_json=other.scope_json))


def test_missing_collection_member_withholds_completeness(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    owner, member, obs = seed(source)
    catalog(target)
    package = ExchangeService(source).export_package(
        selection=ExchangeSelectionScope(all_selected=True, include_core=False)
    )
    # Deliberately incomplete, digest-recomputed synthetic delivery; original
    # terminal/proof is not edited to claim an apparently smaller complete set.
    package.context["resources"] = [
        row
        for row in package.context["resources"]
        if row["provider_resource_id"] != member.provider_resource_id
    ]
    report = ExchangeService(target).import_package(
        replace(package, digest_sha256=None), new_request=True
    )
    assert report.omissions
    with Context.snapshot(target) as ctx:
        assert owner in ctx.resources()
        assert member not in ctx.resources()
        assert ctx.coverage(claim(obs).scope).state == "unknown"
        assert not ctx.coverage(claim(obs).scope).known_empty
        assert not ctx.db.execute("SELECT * FROM collection_terminals").fetchall()


def test_unpartitioned_resource_coverage_compares_numeric_times_only(tmp_path):
    """Characterize required adapter scoping; passing does not approve clock mixing."""
    path = tmp_path / "catalog"
    owner, _, _ = seed(path)
    scope = CoverageScope.resource(owner, "synthetic_unpartitioned_analysis")
    with Context.transaction(path) as ctx:
        ctx.scope(scope)
        first = CoverageClaim(scope, 900, "partial")
        # These synthetic clocks have no declared common comparison domain.
        # CoverageClaim cannot express that fact: same owner means numeric order.
        second = CoverageClaim(scope, 100, "unknown")
        assert ctx.admit_coverage(first) == "insert"
        assert ctx.admit_coverage(second) == "stale"
        assert ctx.coverage(scope).claims == (first,)
        assert ctx.coverage(scope).observed_at_us == 900
