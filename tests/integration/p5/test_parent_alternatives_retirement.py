"""Competing real Parent originals survive actual current Exchange end to end."""

from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.application.context_query import ContextQueryService
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.exchange import (
    ExchangeSelectionScope,
    decode_package,
    encode_package,
)
from repo_catalog.domain.p1_context import FieldClock, ResourceKey, canonical
from repo_catalog.domain.production_context import ResourceRelation
from repo_catalog.domain.resource_identification import ResourceIdentification
from tests.integration.p5.test_context_retirement_exchange import (
    SERVICE,
    ExchangeService,
    initialize,
    provenance,
    receive,
)
from tests.support.context_admission import fixture_transaction


@pytest.mark.parametrize("reverse", [False, True], ids=["normal", "reverse"])
def test_actual_parent_alternatives_survive_repeat_reopen_and_onward_exchange(
    tmp_path, reverse
):
    parents = tuple(
        ResourceKey.from_native(SERVICE, "issue", value) for value in ("12", "13")
    )
    child = ResourceKey.document(parents[0], "comment", "comment", "23")
    declaration = ResourceIdentification.scoped(child, parents[0], "comment", "23")
    originals = tuple(
        ResourceRelation(
            child,
            "parent",
            (parent,),
            provenance(f"parent-original-{index}"),
            canonical(
                {
                    "clock": {
                        "domain": "github:issue-comment:updated_at",
                        "at_us": 10 if index == 0 else None,
                    },
                    "document_kind": "comment",
                    "state": "complete",
                }
            ),
            11 + index,
        )
        for index, parent in enumerate(parents)
    )
    source, target, onward = (
        tmp_path / name for name in ("source", "target", "onward")
    )
    for directory in (source, target, onward):
        initialize(directory)
    grants = DependencySet(
        resources={child, *parents}, provider_registrations={SERVICE}
    )
    with fixture_transaction(source, grants) as context:
        context.provider(SERVICE, "github")
        for parent in parents:
            context.resource(parent)
        context.resource(child, identification=declaration)
        context.admit_text(
            child,
            "independently valid body",
            FieldClock("provider", 10),
            provenance("body"),
            10,
        )
        for original in originals:
            assert context.relation(original) == "insert"

    def read(directory):
        view = ContextQueryService(directory, mode="context_only").get_context_resource(
            child, include_text=True
        )
        reports = tuple(
            item for item in view.relations if item.relation_kind == "parent"
        )
        assert set(reports) == set(originals)
        assert {item.members[0] for item in reports} == set(parents)
        # A naming namespace is retained as such; it cannot choose one of the
        # contrary semantic Parent originals as an authoritative winner.
        assert view.identifier_namespace == parents[0]
        assert view.identification == declaration
        assert list(view.resolved_texts.values()) == ["independently valid body"]
        return view.fields, set(reports)

    before = read(source)
    selection = ExchangeSelectionScope(all_selected=True, include_core=False)
    package = ExchangeService(source).export_package(
        selection=selection, exported_at_us=100
    )
    assert package.context is not None
    if reverse:
        package = replace(
            package,
            package_id=str(uuid4()),
            context={
                name: list(reversed(rows)) for name, rows in package.context.items()
            },
            digest_sha256=None,
        )
    package = decode_package(encode_package(package))
    receive(target, package)
    assert read(target) == before
    assert receive(target, package, first=False).idempotent_replay
    assert read(target) == before
    forwarded = ExchangeService(target).export_package(
        selection=selection, exported_at_us=101
    )
    receive(onward, decode_package(encode_package(forwarded)))
    assert read(onward) == before
