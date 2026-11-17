"""Real typed Exchange preserves unresolved fields and their actual producers."""

import json
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.exchange import (
    ExchangeSelectionScope,
    decode_package,
    encode_package,
)
from repo_catalog.domain.p1_context import (
    FieldCandidate,
    FieldClock,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.p1_coordination import RequestIdentity
from repo_catalog.domain.resource_identification import ResourceIdentification as RI
from tests.integration.p5.conftest import init_catalog_stores
from tests.support.context_admission import AuthorizedExchangeService as ExchangeService
from tests.support.context_admission import fixture_transaction

REPOSITORY = "9ebbe38a-f937-40e6-a99c-701835ebcf10"
SERVICE = "aad25448-03eb-4f83-a578-ceec84375b5a"
PARENT = ResourceKey.from_native(SERVICE, "pull_request", "parent")


def resource_case(family):
    if family == "issue":
        keys = tuple(
            ResourceKey.from_native(SERVICE, "issue", value) for value in ("7", "8")
        )
        return keys, tuple(RI.unscoped(key) for key in keys)
    kind, subtype = {
        "issue-comment": ("comment", "comment"),
        "review": ("review", "review"),
        "review-comment": ("comment", "review_comment"),
    }[family]
    keys = tuple(
        ResourceKey.document(PARENT, kind, subtype, value) for value in ("7", "8")
    )
    return keys, tuple(
        RI.scoped(key, PARENT, subtype, value)
        for key, value in zip(keys, ("7", "8"), strict=True)
    )


def provenance(event, module="tests.fixture.body-parser", version="9"):
    return canonical(
        {"source": module, "evidence": {"event": event, "parser_version": version}}
    )


def initialize(directory):
    init_catalog_stores(
        directory,
        repository_uuidv4=REPOSITORY,
        stores=("core", "context", "operational"),
    )


def receive(directory, package, *, first=True):
    return ExchangeService(directory).import_package(
        package,
        request=RequestIdentity(
            package.sender_catalog_instance_uuidv4, package.package_id
        ),
        new_request=first,
        permitted_repository_uuidv4s=(REPOSITORY,),
    )


def snapshot(directory, keys):
    with Context.snapshot(directory) as context:
        return {
            resource: (
                context.candidates(resource, "text_body_sha256"),
                context.candidates(resource, "author"),
            )
            for resource in keys
        }


@pytest.mark.parametrize(
    "family", ["issue", "issue-comment", "review", "review-comment"]
)
def test_competing_fields_and_inherited_body_producers_survive_repeat_reopen_and_onward(
    tmp_path,
    family,
):
    keys, declarations = resource_case(family)
    key, other = keys
    grants = DependencySet(
        resources={PARENT, *keys},
        repositories={REPOSITORY},
        provider_registrations={SERVICE},
    )
    source, target, onward = (
        tmp_path / name for name in ("source", "target", "onward")
    )
    for directory in (source, target, onward):
        initialize(directory)
    with fixture_transaction(source, grants) as context:
        context.provider(SERVICE, "github")
        context.repository(REPOSITORY)
        context.resource(PARENT)
        for declaration in declarations:
            context.resource(declaration.resource, identification=declaration)
        for index, text in enumerate(
            ("incumbent", "alternative B", "alternative C", "alternative D")
        ):
            context.admit_text(
                key,
                text,
                FieldClock("provider.updated_at", None),
                provenance(f"original-{index}"),
                index + 1,
            )
        context.admit_text(
            other,
            "independent",
            FieldClock("provider.updated_at", 10),
            provenance("independent"),
            10,
        )
        context.admit_field(
            FieldCandidate(
                key,
                "author",
                canonical("new author"),
                FieldClock("provider.updated_at", 20),
                provenance("sparse-author", "tests.fixture.author-parser", "0"),
                20,
            )
        )
        expected_bodies = context.candidates(key, "text_body_sha256")
        expected_author = context.candidates(key, "author")
        assert len(expected_bodies) == 4
    package = ExchangeService(source).export_package(
        selection=ExchangeSelectionScope(all_selected=True), exported_at_us=100
    )
    assert package.context is not None
    # This newly authored package first delivers each section in reverse row
    # order; onward export below uses the normal order without changing facts.
    package = replace(
        package,
        package_id=str(uuid4()),
        context={name: list(reversed(rows)) for name, rows in package.context.items()},
        digest_sha256=None,
    )
    package = decode_package(encode_package(package))
    receive(target, package)
    first = snapshot(target, keys)
    assert first[key] == (expected_bodies, expected_author)
    assert len(first[other][0]) == 1
    assert receive(target, package, first=False).idempotent_replay
    assert snapshot(target, keys) == first
    forward_package = ExchangeService(target).export_package(
        selection=ExchangeSelectionScope(all_selected=True), exported_at_us=101
    )
    receive(onward, decode_package(encode_package(forward_package)))
    assert snapshot(onward, keys) == first
    with Context.snapshot(onward) as context:
        bodies = {
            context.read_text(json.loads(candidate.value_json))
            for candidate in context.candidates(key, "text_body_sha256")
        }
        assert bodies == {
            "incumbent",
            "alternative B",
            "alternative C",
            "alternative D",
        }
        assert {
            json.loads(candidate.provenance_json)["source"]
            for candidate in context.candidates(key, "text_body_sha256")
        } == {"tests.fixture.body-parser"}
        assert (
            json.loads(context.candidates(key, "author")[0].provenance_json)["source"]
            == "tests.fixture.author-parser"
        )
