"""The real remote transport policy is available before any intake side effect."""

import pytest

from repo_catalog.application import remote_git_acquisition as owner
from repo_catalog.domain.p1_core import CoreFailure


def test_remote_settings_preflight_is_pure_and_retains_only_injected_reference_inputs(
    monkeypatch,
):
    def forbidden(*args, **kwargs):
        raise AssertionError("preflight must not fetch or resolve a credential value")

    monkeypatch.setattr(owner, "fetch_remote", forbidden)
    monkeypatch.setattr(owner, "_EnvironmentCredential", forbidden)
    settings = {
        "locator": "https://example.test/repo.git",
        "object_format": "sha1",
        "token_env_var": "LOCAL_CREDENTIAL_REFERENCE",
        "timeout_seconds": 30,
        "transfer_bytes": 1024,
        "disk_bytes": 2048,
        "metadata_bytes": 512,
        "refspecs": ["+refs/heads/main:refs/heads/main"],
    }
    assert owner.validate_remote_git_settings(settings) == settings


@pytest.mark.parametrize(
    "changes",
    [
        {"locator": "https://user:secret@example.test/repo.git"},
        {"locator": "https://example.test/repo.git?token=secret"},
        {"password": "secret"},
        {"headers": {"Authorization": "secret"}},
        {"work_limits": {"input_bytes": 999}},
        {"request_identity": ["new", "parent"]},
        {"source_handler": "untrusted-wire-callable"},
        {"refspecs": "unbounded-text"},
        {"transfer_bytes": True},
        {"timeout_seconds": float("nan")},
        {"ssh_username": "option injection"},
        {"ssh_identity_file": {"inline": "secret"}},
    ],
)
def test_invalid_remote_execution_settings_refuse_before_transport_or_accounting(
    changes, monkeypatch
):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid settings cannot perform a fetch")

    monkeypatch.setattr(owner, "fetch_remote", forbidden)
    with pytest.raises(CoreFailure):
        owner.validate_remote_git_settings(
            {
                "locator": "https://example.test/repo.git",
                "object_format": "sha1",
                **changes,
            }
        )
