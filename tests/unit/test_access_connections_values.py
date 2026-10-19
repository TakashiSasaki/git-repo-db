"""Pure finite configuration grammar; no network or credential probes."""

import pytest

from repo_catalog.domain.access_connections import (
    canonical,
    execution_context,
    profile_options,
    repository_locator,
)
from repo_catalog.domain.access_registry import AccessRegistryError


@pytest.mark.parametrize(
    "value,expected",
    [
        ("/repos/app.git", "file"),
        ("file:///repos/app.git", "file"),
        ("https://git.example.org/a.git", "https"),
        ("git@host.example:team/a.git", "ssh"),
        ("ssh://git@host.example:2222/srv/a.git", "ssh"),
        ("host:relative/a.git", "ssh"),
    ],
)
def test_repository_grammar(value, expected):
    assert repository_locator(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        1,
        "",
        "../repo",
        "~/repo",
        "//server/share",
        "C:/repo",
        "C:\\repo",
        "ext::sh -c true",
        "-option",
        "https://user:secret@host/repo",
        "https://host/repo?token=secret",
        "git@host:-option",
        "http://host/repo",
        "/repo\x00",
        "/repo name",
        "ssh://host/%00",
        "/r\\evil",
        "https://host/repo#fragment",
    ],
)
def test_unsupported_repository_grammar(value):
    with pytest.raises(AccessRegistryError):
        repository_locator(value)


@pytest.mark.parametrize(
    "value",
    [
        {"version": 1, "transport": "file", "path_dialect": "posix"},
        {"version": 1, "transport": "https"},
        {
            "version": 1,
            "transport": "https",
            "credential_ref": {"kind": "credential-helper", "name": "private"},
        },
        {
            "version": 1,
            "transport": "ssh",
            "credential_ref": {"kind": "ssh-agent", "name": "work"},
            "ssh_profile_ref": "approved-alias",
        },
    ],
)
def test_typed_options(value):
    encoded = canonical(value)
    assert profile_options(encoded) == encoded


@pytest.mark.parametrize(
    "value",
    [
        {},
        [],
        None,
        {"version": True, "transport": "https"},
        {"version": 1, "transport": "https", "token": "secret"},
        {"version": 1, "transport": "https", "verify_tls": False},
        {"version": 1, "transport": "ssh", "ProxyCommand": "sh"},
        {
            "version": 1,
            "transport": "ssh",
            "credential_ref": {"kind": "ssh-key", "name": "/home/key"},
        },
        {
            "version": 1,
            "transport": "https",
            "credential_ref": {"kind": "ssh-key", "name": "other"},
        },
        {"version": 1, "transport": "ssh", "ssh_profile_ref": "-oCommand=x"},
        {"version": 1, "transport": "file", "path_dialect": "windows"},
        {
            "version": 1,
            "transport": "https",
            "credential_ref": {
                "kind": "credential-helper",
                "name": "foo",
                "token": "secret",
            },
        },
        {"version": 1, "transport": ["https"]},
    ],
)
def test_unsafe_or_unsupported_options(value):
    with pytest.raises(AccessRegistryError):
        profile_options(canonical(value))


@pytest.mark.parametrize(
    "value",
    [
        ' {"version":1,"transport":"https"}',
        '{"transport":"https","version":1,"version":1}',
        "NaN",
        '"hello"',
        "[" * 10000,
        "x" * 20000,
    ],
)
def test_noncanonical_and_bounded_json(value):
    with pytest.raises(AccessRegistryError):
        profile_options(value)


def test_scope_context_is_typed_declaration_not_opaque_payload():
    value = {
        "version": 1,
        "executor_kind": "container",
        "executor_ref": "build",
        "identity_view": "owner",
        "path_dialect": "posix",
    }
    assert execution_context(canonical(value)) == canonical(value)
    for key, bad in (
        ("path_dialect", "windows"),
        ("executor_kind", "shell"),
        ("executor_ref", "/arbitrary/path"),
        ("version", True),
    ):
        with pytest.raises(AccessRegistryError):
            execution_context(canonical({**value, key: bad}))
