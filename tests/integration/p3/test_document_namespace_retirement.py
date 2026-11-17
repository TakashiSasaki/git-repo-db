"""Natural documents and Service namespaces share bytes without sharing identity."""

import json

from repo_catalog.application.context_query import ContextQueryService
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.p1_context import FieldClock, ResourceKey, canonical
from repo_catalog.domain.resource_identification import ResourceIdentification
from tests.integration.p3.test_production_context import (
    OTHER_SERVICE,
    SERVICE,
    directory,
)
from tests.support.context_admission import fixture_transaction

__all__ = ["directory"]


def test_natural_document_kind_parent_spelling_and_service_remain_distinct_with_shared_text(
    directory,
):
    parents = tuple(
        ResourceKey.from_native(SERVICE, "pull_request", value)
        for value in ("first", "second")
    )
    declarations = tuple(
        ResourceIdentification.scoped(
            ResourceKey.document(parent, "document", kind, local), parent, kind, local
        )
        for parent, kind, local in (
            (parents[0], "pr_title", "00123"),
            (parents[0], "pr_body", "00123"),
            (parents[0], "pr_body", "123"),
            (parents[1], "pr_body", "123"),
        )
    )
    repositories = {
        ResourceKey.from_native(service, "repository", native)
        for service, native in (
            (SERVICE, "00123"),
            (SERVICE, "123"),
            (OTHER_SERVICE, "00123"),
        )
    }
    grants = DependencySet(
        resources={*parents, *repositories, *(item.resource for item in declarations)},
        provider_registrations={SERVICE, OTHER_SERVICE},
    )
    producer = canonical(
        {"source": "identified-document-provider", "evidence": "shared-exact-text"}
    )
    with fixture_transaction(directory, grants) as context:
        for service in (SERVICE, OTHER_SERVICE):
            context.provider(
                service,
                "gitlab",
                canonical(
                    {"description": "same public endpoint https://synthetic.invalid"}
                ),
            )
        for key in (*parents, *repositories):
            context.resource(key)
        for declaration in declarations:
            context.resource(declaration.resource, identification=declaration)
            context.admit_text(
                declaration.resource,
                "shared exact text",
                FieldClock("provider", 1),
                producer,
                1,
            )
        assert len({item.resource for item in declarations}) == 4
        assert len(repositories) == 3
        assert context.db.execute("SELECT count(*) FROM text_bodies").fetchone()[0] == 1
        assert (
            context.db.execute("SELECT count(*) FROM field_candidates").fetchone()[0]
            == 4
        )
        assert {
            tuple(row)
            for row in context.db.execute(
                "SELECT service_instance_uuidv4,provider_resource_id FROM resources WHERE resource_kind='repository'"
            )
        } == {
            (key.service_instance_uuidv4, key.provider_resource_id)
            for key in repositories
        }
        assert not context.db.execute("PRAGMA foreign_key_check").fetchall()
    query = ContextQueryService(directory, mode="context_only")
    for declaration in declarations:
        result = query.get_context_resource(declaration.resource, include_text=True)
        assert result.resource == declaration.resource
        assert result.document_kind == declaration.document_kind
        assert list(result.resolved_texts.values()) == ["shared exact text"]
        assert json.loads(
            result.fields["text_body_sha256"][0].provenance_json
        ) == json.loads(producer)
    assert not (directory / "core.sqlite3").exists()
