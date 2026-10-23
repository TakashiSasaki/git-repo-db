"""M02: received selection bytes must bind before typed set canonicalization."""

import copy
import hashlib
import json

import pytest

from repo_catalog.domain.exchange import (
    ExchangeError,
    ExchangePackage,
    ExchangeSelectionScope,
    decode_package,
    encode_package,
)
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.p1_core import OID

SERVICE = "11111111-1111-4111-8111-111111111111"
REPOSITORY = "22222222-2222-4222-8222-222222222222"
PACKAGE = "33333333-3333-4333-8333-333333333333"
SOURCE = "44444444-4444-4444-8444-444444444444"
FIELDS = (
    "repository_uuidv4s",
    "source_uuidv4s",
    "notes_refs",
    "object_oids",
    "resource_keys",
)


def received_digest(data):
    """Independent R03 oracle: only the top-level digest field is excluded."""
    return hashlib.sha256(
        json.dumps(
            {key: value for key, value in data.items() if key != "digest_sha256"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def package():
    scope = ExchangeSelectionScope(
        all_selected=True,
        repository_uuidv4s=(REPOSITORY, SOURCE),
        source_uuidv4s=(REPOSITORY, SOURCE),
        notes_refs=("refs/notes/a", "refs/notes/é"),
        object_oids=(OID("sha1", "1" * 40), OID("sha256", "2" * 64)),
        resource_keys=(
            ResourceKey.from_native(SERVICE, "opaque", "é"),
            ResourceKey.from_native(SERVICE, "opaque", ["", []]),
        ),
    )
    return ExchangePackage(PACKAGE, 97, SERVICE, REPOSITORY, scope)


def carrier(data, kind):
    if kind == "dict":
        return data
    text = json.dumps(data, ensure_ascii=False)
    return text if kind == "str" else text.encode("utf-8")


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("mutation", ("duplicate", "permutation"))
@pytest.mark.parametrize("kind", ("dict", "str", "bytes"))
def test_rehashed_noncanonical_selection_is_refused_without_repair(
    field, mutation, kind
):
    data = package().to_dict()
    values = data["selection_scope"][field]
    if mutation == "duplicate":
        values.append(copy.deepcopy(values[0]))
    else:
        values.reverse()
    data["digest_sha256"] = received_digest(data)
    before = copy.deepcopy(data)
    with pytest.raises(ExchangeError) as error:
        decode_package(carrier(data, kind))
    assert error.value.code == "INVALID_SELECTION"
    assert data == before


@pytest.mark.parametrize("kind", ("dict", "str", "bytes"))
def test_valid_canonical_selection_and_exact_unicode_roundtrip(kind):
    original = package()
    data = original.to_dict()
    assert data["digest_sha256"] == received_digest(data)
    before = copy.deepcopy(data)
    decoded = decode_package(carrier(data, kind))
    assert decoded.to_dict() == data == before
    assert encode_package(decoded) == encode_package(original)
    assert (
        decoded.selection_scope.resource_keys == original.selection_scope.resource_keys
    )


def test_stale_digest_refuses_before_selection_domain_conversion(monkeypatch):
    data = package().to_dict()
    data["selection_scope"]["notes_refs"].append("refs/notes/a")

    def conversion_forbidden(_data):
        raise AssertionError("unbound selection reached domain conversion")

    monkeypatch.setattr(ExchangeSelectionScope, "from_dict", conversion_forbidden)
    with pytest.raises(ExchangeError) as error:
        decode_package(data)
    assert error.value.code == "DIGEST_MISMATCH"


def test_changed_canonical_selection_requires_new_matching_digest():
    data = package().to_dict()
    data["selection_scope"]["notes_refs"].append("refs/notes/終")
    with pytest.raises(ExchangeError) as error:
        decode_package(data)
    assert error.value.code == "DIGEST_MISMATCH"
    data["digest_sha256"] = received_digest(data)
    decoded = decode_package(data)
    assert decoded.to_dict() == data
    assert decoded.selection_scope.notes_refs[-1] == "refs/notes/終"


@pytest.mark.parametrize("field", FIELDS)
def test_selection_decoder_itself_refuses_duplicate_set_entries(field):
    data = package().selection_scope.to_dict()
    data[field].append(copy.deepcopy(data[field][0]))
    with pytest.raises(ExchangeError) as error:
        ExchangeSelectionScope.from_dict(data)
    assert error.value.code == "INVALID_SELECTION"
