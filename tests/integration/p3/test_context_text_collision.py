"""A same-digest incoming value never overwrites exact retained Context text."""

import hashlib
from types import SimpleNamespace

import pytest

from repo_catalog.domain.p1_context import FieldClock
from tests.integration.p3.test_production_context import (
    KEY,
    PROVENANCE,
    SERVICE,
    directory,
    production_grants,
)
from tests.support.context_admission import fixture_transaction

__all__ = ["directory"]


def test_incoming_digest_collision_preserves_original_body_field_and_producer(
    directory, monkeypatch
):
    with fixture_transaction(directory, production_grants()) as context:
        context.provider(SERVICE, "github")
        context.resource(KEY)
        context.admit_text(KEY, "A", FieldClock("provider", 1), PROVENANCE, 1)
        original = context.candidates(KEY, "text_body_sha256")
        digest = context.text("A")
        sha256 = hashlib.sha256

        def colliding(data=b"", *args, **kwargs):
            if data == b"B":
                return SimpleNamespace(hexdigest=lambda: digest)
            return sha256(data, *args, **kwargs)

        with monkeypatch.context() as fault:
            fault.setattr(hashlib, "sha256", colliding)
            with pytest.raises(ValueError, match="collision"):
                context.admit_text(KEY, "B", FieldClock("provider", 2), PROVENANCE, 2)
        assert context.candidates(KEY, "text_body_sha256") == original
        assert context.read_text(digest) == "A"
        assert context.db.execute("SELECT count(*) FROM text_bodies").fetchone()[0] == 1
    assert not (directory / "p1-recovery-stop.json").exists()
