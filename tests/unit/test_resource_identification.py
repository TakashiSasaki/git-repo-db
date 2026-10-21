"""Declarations cannot be recovered from key shape or used as a fourth key."""

from dataclasses import asdict, replace

import pytest

from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.production_context import ResourceObservation
from repo_catalog.domain.resource_identification import ResourceIdentification as RI
from repo_catalog.domain.resource_identity import encode_identity

SERVICE = "22222222-2222-4222-8222-222222222222"


@pytest.mark.parametrize("native", ["", [], [""], [[]], ["x", ["y", []]], "é😀"])
def test_explicit_global_declaration_roundtrip(native):
    key = ResourceKey.global_document(SERVICE, native)
    declaration = RI.global_document(key)
    bare = ResourceKey(**asdict(key))
    assert replace(key) == bare == declaration.resource
    assert RI.from_storage(bare, declaration.columns) == declaration
    with pytest.raises((TypeError, ValueError)):
        ResourceObservation(bare)
    assert (
        ResourceObservation(bare, identification=declaration).identification
        == declaration
    )


@pytest.mark.parametrize("native", ["", [], ["local", ["", []]]])
def test_scoped_native_local_is_serialized_once(native):
    namespace = ResourceKey.from_native(SERVICE, "pull_request", ["project", "7"])
    key = ResourceKey.document(namespace, "document", "body", native)
    declaration = RI.scoped(key, namespace, "body", native)
    assert declaration.columns == (
        "pull_request",
        namespace.provider_resource_id,
        "body",
        encode_identity(native),
    )
    assert (
        RI.from_storage(ResourceKey(*key.coordinates()), declaration.columns)
        == declaration
    )
    with pytest.raises(ValueError):
        RI.scoped(key, namespace, "body", encode_identity(native))


def test_same_key_has_two_possible_declarations_without_shape_dispatch():
    namespace = ResourceKey.from_native(SERVICE, "pull_request", "7")
    key = ResourceKey.document(namespace, "document", "body", "D")
    global_declaration = RI.global_document(ResourceKey(*key.coordinates()))
    scoped_declaration = RI.scoped(key, namespace, "body", "D")
    assert global_declaration.resource == scoped_declaration.resource
    assert global_declaration.columns != scoped_declaration.columns


@pytest.mark.parametrize(
    "kind,parent",
    [
        ("document", "issue"),
        ("review", "issue"),
        ("thread", "issue"),
        ("comment", "repository"),
    ],
)
def test_known_kind_cannot_fall_back_to_opaque(kind, parent):
    namespace = ResourceKey.from_native(SERVICE, parent, "7")
    key = ResourceKey.document(namespace, kind, "body", "D")
    with pytest.raises(ValueError):
        RI.scoped(key, namespace, "body", "D")
    with pytest.raises(ValueError):
        RI.unscoped(key)
