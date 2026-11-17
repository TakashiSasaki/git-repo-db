"""Provider native coordinates retain exact IDs without Node-ID aliasing."""

from uuid import uuid4

import pytest

from repo_catalog.adapters.github.identity import database_resource_id
from repo_catalog.domain.p1_context import ResourceKey


@pytest.mark.parametrize(
    "value,expected",
    [(123, "123"), ("00123", "00123"), ("9223372036854775808", "9223372036854775808")],
)
def test_database_resource_id_preserves_reported_decimal_spelling(value, expected):
    assert database_resource_id(value) == expected


@pytest.mark.parametrize(
    "value",
    [None, True, False, 0, -1, 1.0, "", " 1", "0", "１２３", "NODE_only", [], {}],
)
def test_database_resource_id_rejects_node_ids_and_invalid_scalars(value):
    with pytest.raises(ValueError):
        database_resource_id(value)


def test_full_service_parent_and_native_id_coordinates_do_not_alias():
    first, second = str(uuid4()), str(uuid4())
    a = ResourceKey.from_native(first, "repository", "00123")
    b = ResourceKey.from_native(first, "repository", "123")
    c = ResourceKey.from_native(second, "repository", "00123")
    assert len({a, b, c}) == 3
    left = ResourceKey.from_native(first, "pull_request", "left")
    right = ResourceKey.from_native(first, "pull_request", "right")
    thread_a = ResourceKey.document(
        left, "thread", "review_thread", "same-native-thread"
    )
    thread_b = ResourceKey.document(
        right, "thread", "review_thread", "same-native-thread"
    )
    assert thread_a != thread_b
    assert (
        ResourceKey.document(left, "thread", "review_thread", "same-native-thread")
        == thread_a
    )
