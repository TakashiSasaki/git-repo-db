"""Finite Access registry values, with no filesystem or network resolution."""

from uuid import UUID

import pytest

from repo_catalog.domain.access_registry import (
    INT64_MAX,
    MAX_LABEL_BYTES,
    MAX_URI_BYTES,
    AccessRegistryError,
    AccessScope,
    ScopeLocatorRegistration,
    display_label,
    page_size,
    registration_time,
    scope_locator,
    scope_uuid,
)

SCOPE = "550e8400-e29b-41d4-a716-446655440000"


@pytest.mark.parametrize("value", [None, 1, UUID(SCOPE), SCOPE.upper(), SCOPE + " ", "x", SCOPE.replace("41d4", "11d4")])
def test_reject_noncanonical_scope(value):
    with pytest.raises(AccessRegistryError, match="IDENTITY"):
        scope_uuid(value)


def test_scope_has_independent_mutable_label_value():
    assert AccessScope(SCOPE, "host").scope_uuidv4 == SCOPE
    assert AccessScope(SCOPE, "ホスト").display_name == "ホスト"
    assert AccessScope(SCOPE).display_name == ""


@pytest.mark.parametrize("value", [None, True, False, 0, -1, 1.0, "1", INT64_MAX + 1])
def test_invalid_registration_times(value):
    with pytest.raises(AccessRegistryError, match="TIME"):
        registration_time(value)


@pytest.mark.parametrize("value", [1, INT64_MAX])
def test_valid_registration_times(value):
    assert registration_time(value) == value


@pytest.mark.parametrize("value", [None, 1, "a\n", "\ud800", "x" * (MAX_LABEL_BYTES + 1)])
def test_bad_labels(value):
    with pytest.raises(AccessRegistryError, match="LABEL"):
        display_label(value)


@pytest.mark.parametrize("value", [0, -1, 1001, True, "2", 2.5])
def test_invalid_page_bound(value):
    with pytest.raises(AccessRegistryError, match="LIMIT"):
        page_size(value)


@pytest.mark.parametrize("value", [
    "https://Runner.example.org/environments/build",
    "HTTPS://runner.example.org/env",
    "https://runner.example.org:8443/env.git/",
    "https://[2001:db8::1]:8443/env",
    "ssh://git@host.example:2222/srv/environment",
    "file:///srv/environment",
    "file://localhost/srv/environment",
    "https://host.example/env%2Fname",
    "https://host.example/%E6%97%A5",
])
def test_preserve_valid_uri_exactly(value):
    assert scope_locator(value) == value
    assert ScopeLocatorRegistration(SCOPE, 1, value).key == (SCOPE, 1, value)


@pytest.mark.parametrize("value", [
    None, "", "http://host.example/env", "urn:uuid:" + SCOPE,
    "git@server:repo.git", "/srv/env", "../env", "ext::sh -c cmd",
    "https://host.example/env?", "https://host.example/env#",
    "https://host.example/env?token=PRIVATE", "https://u:PRIVATE@host.example/env",
    "https://u@host.example/env", "ssh://u:PRIVATE@host.example/env",
    "https://host.example/a\\b", "https://host.example/%", "https://host.example/%GG",
    "https://host.example/%00", "https://host.example/%0A", "https://host.example/%7f",
    "https://host.example/日本", "https://host.example/a b", "https://host.example/\n",
    "https://host.example:0/env", "https://host.example:65536/env",
    "https://host.example:/env", "https://[2001:db8::1]garbage/env",
    "https://bad_host.example/env", "https://-bad.example/env", "https:///env",
    "file://remote.example/srv/env", "file:relative", "file:////remote/env",
    "ssh://user@host.example", "https://host.example/" + "x" * MAX_URI_BYTES,
])
def test_reject_unsupported_or_unsafe_uri_without_echo(value):
    with pytest.raises(AccessRegistryError, match="LOCATOR") as error:
        scope_locator(value)
    assert "PRIVATE" not in str(error.value)


def test_timestamp_is_part_of_registration_not_scope_identity():
    first = ScopeLocatorRegistration(SCOPE, 1, "file:///srv/a")
    again = ScopeLocatorRegistration(SCOPE, 3, "file:///srv/a")
    assert first.key != again.key
    assert first.scope_uuidv4 == again.scope_uuidv4
