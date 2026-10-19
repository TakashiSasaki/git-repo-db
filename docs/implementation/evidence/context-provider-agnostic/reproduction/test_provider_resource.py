"""Audit probes only: synthetic inputs, packaged product DDL and typed APIs.

Provider-derived counterexamples use documented semantics with invented IDs;
none is a captured live Provider response. Run with supported SQLite >=3.51.3.
"""

import sqlite3

import pytest

from repo_catalog.adapters.github.production_intake import github_repository_id
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.p1_context import (
    FieldCandidate,
    FieldClock,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.p1_core import OID
from repo_catalog.domain.production_context import CoreReference, ResourceRelation

SERVICE = "11111111-1111-4111-8111-111111111111"
SECOND = "22222222-2222-4222-8222-222222222222"
REPO = "33333333-3333-4333-8333-333333333333"
INSTANCE = "44444444-4444-4444-8444-444444444444"
PROVENANCE = canonical({"source": "synthetic-audit", "evidence": "observation-1"})


@pytest.fixture
def store(tmp_path):
    assert sqlite3.sqlite_version_info >= (3, 51, 3)
    initialize(tmp_path / "context.sqlite3", "context", REPO, INSTANCE)
    with Context.transaction(tmp_path) as ctx:
        ctx.provider(SERVICE, "gitlab")
        yield ctx


def field(resource, value, *, source="synthetic-audit", stamp=10):
    return FieldCandidate(
        resource,
        "evaluation",
        canonical(value),
        FieldClock("provider", 5),
        canonical({"source": source, "evidence": "evaluation-1"}),
        stamp,
    )


@pytest.mark.parametrize("second_kind", ["github", "gitlab"])
def test_pr01_service_namespace_separates_equal_ids(store, second_kind):
    store.provider(SECOND, second_kind)
    keys = (ResourceKey(SERVICE, "issue", "7"), ResourceKey(SECOND, "issue", "7"))
    for key in keys:
        store.resource(key)
    assert set(store.resources()) == set(keys)


def test_pr02_bare_project_iid_collides_but_qualified_coordinate_survives(store):
    # GitLab documents iid as project-local: project 42 / iid 5 != project 43 / iid 5.
    bare = ResourceKey(SERVICE, "issue", "5")
    store.resource(bare)
    store.resource(bare)
    assert store.resources() == (
        bare,
    )  # Adapter omission cannot be detected from this key.
    qualified = tuple(
        ResourceKey(SERVICE, "issue", canonical(["project_iid", p, "5"]))
        for p in ("42", "43")
    )
    for key in qualified:
        store.resource(key)
    assert set(store.resources()) == {bare, *qualified}


@pytest.mark.parametrize(
    "parent_kind,child_kind",
    [
        ("repository", "document"),
        ("issue", "document"),
        ("issue", "thread"),
        ("annotation", "review"),
        ("repository", "review"),
    ],
)
def test_pr03_document_parent_limits_reject_broader_use(store, parent_kind, child_kind):
    parent = ResourceKey(SERVICE, parent_kind, "parent-1")
    store.resource(parent)
    child = ResourceKey.document(parent, child_kind, "provider-native-kind", "child-1")
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        store.resource(child)
    assert child not in store.resources()


def test_pr04_supported_pr_document_positive_control(store):
    parent = ResourceKey(SERVICE, "pull_request", "change-1")
    child = ResourceKey.document(parent, "document", "provider-specification", "doc-1")
    store.resource(parent)
    store.resource(child)
    assert set(store.resources()) == {parent, child}


@pytest.mark.parametrize("kind", ["discussion", "event", "commit", "analysis_result"])
def test_pr05_unknown_resource_kind_is_rejected_at_ddl(store, kind):
    key = ResourceKey(SERVICE, kind, "1")  # Domain key itself permits nonempty strings.
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        store.resource(key)
    assert key not in store.resources()


def test_pr06_repository_annotation_has_identity_text_and_typed_relations(store):
    repository = ResourceKey(SERVICE, "repository", "project-42")
    annotation = ResourceKey(SERVICE, "annotation", "published-annotation-1")
    for key in (repository, annotation):
        store.resource(key)
    relation = ResourceRelation(
        annotation,
        "annotates",
        (repository,),
        PROVENANCE,
        canonical({"target_meaning": "repository"}),
        10,
    )
    assert store.relation(relation) == "insert"
    assert store.relations(annotation, "annotates") == (relation,)
    store.admit_text(
        annotation,
        "Repository evaluation",
        clock=FieldClock("provider", 5),
        provenance_json=PROVENANCE,
        observed_at_us=10,
    )
    digest = __import__("json").loads(
        store.candidates(annotation, "text_body_sha256")[0].value_json
    )
    assert store.read_text(digest) == "Repository evaluation"
    assert store.relation(relation) == "duplicate"


def test_pr07_commit_assessment_unavailable_oid_remains_report(store):
    assessment = ResourceKey(SERVICE, "assessment", "scanner-run-1")
    store.resource(assessment)
    ref = CoreReference(
        assessment, "analyzed_commit", OID("sha1", "a" * 40), PROVENANCE
    )
    store.report_core_reference(ref, clock=FieldClock("scanner", 5), observed_at_us=10)
    deps = store.core_dependencies(assessment, validate=lambda *_: False)
    assert len(deps) == 1
    assert deps[0].reference == ref and not deps[0].required and not deps[0].available
    with pytest.raises(ValueError, match="Required portable Core identity is absent"):
        store.link_core(
            assessment, ref.role, *ref.oid.key, PROVENANCE, lambda *_: False
        )
    assert store.db.execute("SELECT count(*) FROM core_references").fetchone()[0] == 0


def test_pr08_independent_assessment_reports_and_missing_null_preserved(store):
    key = ResourceKey(SERVICE, "assessment", "scanner-run-1")
    store.resource(key)
    assert store.candidates(key, "evaluation") == ()
    for value, source in (
        (None, "provider-a"),
        ("pass", "provider-b"),
        ("fail", "provider-c"),
    ):
        store.admit_field(field(key, value, source=source))
    candidates = store.candidates(key, "evaluation")
    assert {c.value_json for c in candidates} == {"null", '"pass"', '"fail"'}
    assert store.admit_field(field(key, "pass", source="provider-b")) == "duplicate"
    assert len(store.candidates(key, "evaluation")) == 3


def test_pr09_reparenting_document_changes_identity_by_current_contract(store):
    # Hypothetical provider with independent document ID and movable association.
    parents = [
        ResourceKey(SERVICE, "pull_request", name) for name in ("change-a", "change-b")
    ]
    children = [
        ResourceKey.document(p, "document", "independent-document", "doc-1")
        for p in parents
    ]
    for parent, child in zip(parents, children):
        store.resource(parent)
        store.resource(child)
    assert children[0] != children[1]
    assert len(store.resources(kind="document")) == 2


def test_pr10_github_repository_api_namespaces_are_preserved():
    assert github_repository_id({"id": 42}, graphql=False) == "42"
    assert github_repository_id(
        {"id": "opaque-node", "databaseId": 42}, graphql=True
    ) == canonical(["github:node_id", "opaque-node"])
