"""Attributed decoder interpretations survive Exchange without becoming authority."""

import json
from contextlib import closing
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.p1_repository import RepositoryStore
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.exchange import (
    ExchangeSelectionScope,
    decode_package,
    encode_package,
)
from repo_catalog.domain.p1_repository import Provenance, ScalarClaim
from tests.integration.p1.test_repository import Budget, native, oid
from tests.integration.p2.test_native import entry
from tests.integration.p5.conftest import init_catalog_stores


@pytest.mark.parametrize("family", ["author", "name"])
def test_uninstalled_sender_decoder_and_exact_settings_survive_reverse_repeat_and_onward(
    tmp_path, family
):
    source, middle, target = (
        tmp_path / name for name in ("source", "middle", "target")
    )
    repository, _ = init_catalog_stores(source, stores=("repository", "operational"))
    raw = (
        b"genuine caf\xc3\xa9"
        if family == "name"
        else b"genuine caf\xc3\xa9 <a@invalid> 1 +0000"
    )
    target_oid = oid("a")
    body = (
        entry(b"100644", raw, target_oid)
        if family == "name"
        else (
            b"tree "
            + target_oid.object_oid.encode()
            + b"\nauthor "
            + raw
            + b"\ncommitter C <c@invalid> 2 +0000\n\nactual message"
        )
    )
    incoming = native("tree" if family == "name" else "commit", body)
    settings = json.dumps(
        {"metadata_encoding": "latin-1", "metadata_errors": "strict"},
        sort_keys=True,
        separators=(",", ":"),
    )
    producer = Provenance(
        "actual external decoder",
        "original capture",
        family + ":" + raw.hex() + ":" + settings,
        "uninstalled.sender.decoder",
        "999-unranked",
    )
    field = "decoded_name" if family == "name" else "author"
    reported = raw.decode("latin-1")
    with closing(RepositoryStore(source / "repository.sqlite3")) as repository_store:
        repository_store.admit_metadata(incoming, str(uuid4()), Budget())
        repository_store.admit_claim(
            ScalarClaim(incoming.object_oid, field, reported, producer)
        )
        repository_store.admit_claim(
            ScalarClaim(incoming.object_oid, "decoder_settings", settings, producer)
        )
        # A receiver may verify rich scalar fields from actual bytes; an
        # attributed external decoder cannot choose those checked values.
    selection = ExchangeSelectionScope(all_selected=True, include_context=False)
    package = ExchangeService(source).export_package(selection=selection)
    package = replace(
        package,
        package_id=str(uuid4()),
        repository_store={
            key: list(reversed(rows)) for key, rows in package.repository_store.items()
        },
        digest_sha256=None,
    )
    package = decode_package(encode_package(package))
    for directory in (middle, target):
        init_catalog_stores(
            directory,
            repository_uuidv4=repository,
            stores=("repository", "operational"),
        )
        exchange = ExchangeService(directory)
        exchange.import_package(
            package, new_request=True, permitted_repository_uuidv4s=(repository,)
        )
        assert exchange.import_package(
            package, permitted_repository_uuidv4s=(repository,)
        ).idempotent_replay
        with closing(
            RepositoryStore(directory / "repository.sqlite3")
        ) as repository_store:
            candidates = [
                c
                for c in repository_store.scalar(
                    incoming.object_oid, field
                ).alternatives
                if c["provenance"] == list(producer.key)
            ]
            assert len(candidates) == 1 and candidates[0]["checked"] is False
            assert candidates[0]["value"] == ["known", reported]
            settings_candidates = [
                c
                for c in repository_store.scalar(
                    incoming.object_oid, "decoder_settings"
                ).alternatives
                if c["provenance"] == list(producer.key)
            ]
            assert len(settings_candidates) == 1
            assert settings_candidates[0]["value"] == ["known", settings]
            assert settings_candidates[0]["checked"] is False
            expected_canonical = (
                None if family == "name" else ["known", raw.decode("utf-8")]
            )
            assert (
                repository_store.scalar(incoming.object_oid, field).canonical
                == expected_canonical
            )
            if family == "author":
                assert any(
                    c["checked"] and c["value"] == expected_canonical
                    for c in repository_store.scalar(
                        incoming.object_oid, field
                    ).alternatives
                )
            assert repository_store.read_metadata(incoming.object_oid) == body
        package = decode_package(
            encode_package(exchange.export_package(selection=selection))
        )
