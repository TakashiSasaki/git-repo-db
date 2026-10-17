"""Finite domain-only registration contract and safe, non-executing diagnostics."""

import json
from dataclasses import asdict

import pytest

from repo_catalog.domain.context_registration import (
    ACCESS_FIELDS,
    EXECUTION_FIELDS,
    FIELD_TYPES,
    MAX_BYTES,
    SECRET_FIELDS,
    RegistrationError,
    classify_registration,
    registration_json,
)
from repo_catalog.domain.p1_context import canonical


@pytest.mark.parametrize("kind", FIELD_TYPES)
def test_empty_registration_is_not_access_configuration(kind):
    assert registration_json(kind, "{}") == {}


@pytest.mark.parametrize("kind", FIELD_TYPES)
@pytest.mark.parametrize(
    "key", sorted(ACCESS_FIELDS | EXECUTION_FIELDS | SECRET_FIELDS)
)
def test_execution_and_secret_fields_cannot_enter_registration(kind, key):
    # Source 'owner' etc. are descriptive and deliberately not in the block list.
    value = canonical({key: "SECRET-CANARY-DO-NOT-PRINT"})
    with pytest.raises(RegistrationError) as failure:
        registration_json(kind, value)
    assert "SECRET-CANARY" not in str(failure.value)
    assert failure.value.kind == kind


@pytest.mark.parametrize("kind", FIELD_TYPES)
def test_unknown_and_nested_buckets_fail_without_echoing_keys_or_values(kind):
    for value in ({"metadata": {"password": "SECRET"}}, {"SECRET-AS-KEY": "x"}):
        with pytest.raises(
            RegistrationError, match="REGISTRATION_UNKNOWN_FIELD"
        ) as error:
            registration_json(kind, canonical(value))
        assert "SECRET" not in str(error.value)


@pytest.mark.parametrize("value", [True, 1.0, "1", 0, -1, 2**63])
def test_registration_times_reject_invalid_classified_input(value):
    with pytest.raises(RegistrationError, match="FIELD_TYPE"):
        registration_json("provider", canonical({"created_at_us": value}))


@pytest.mark.parametrize("value", [None, 1, 2**63 - 1])
def test_unknown_or_positive_registration_time(value):
    data = {"created_at_us": value}
    assert registration_json("provider", canonical(data)) == data


@pytest.mark.parametrize("value", [1, "false", {}, []])
def test_boolean_does_not_coerce(value):
    with pytest.raises(RegistrationError, match="FIELD_TYPE"):
        registration_json("repository", canonical({"private": value}))


def test_null_and_unicode_descriptions_are_preserved_not_converted_to_urls():
    data = {
        "name": "実験用",
        "description": "see https://example.test/docs",
        "private": None,
    }
    assert registration_json("repository", canonical(data)) == data


@pytest.mark.parametrize(
    "encoded",
    [
        "[]",
        "null",
        "1",
        "{} ",
        '{"name":"one","name":"two"}',
        '{"name":NaN}',
        '{"name":Infinity}',
        '{"name":1e999}',
        '{"name":"\\ud800"}',
        "[[" * 30 + "]]" * 30,
        "x" * (MAX_BYTES + 1),
        canonical({"evidence": [0] * 3000}),
    ],
)
def test_malformed_oversized_duplicate_noncanonical_json(encoded):
    with pytest.raises(RegistrationError):
        registration_json("provider", encoded)


def test_membership_attribution_keeps_original_structured_coordinates():
    data = {"source": "provider.rest", "evidence": ["event", 9, {"page": 3}]}
    assert registration_json("membership", canonical(data)) == data
    for broken in ({"source": "provider"}, {"source": None, "evidence": 9}):
        with pytest.raises(RegistrationError, match="PROVENANCE"):
            registration_json("membership", canonical(broken))


def test_routing_dry_run_is_bounded_safe_and_does_not_extract_credentials():
    data = {
        "tier": "enterprise",
        "api_url": "https://private.example",
        "token": "SECRET",
        "poll_interval_s": 60,
        "SECRET-KEY": 1,
    }
    result = classify_registration("provider", canonical(data))
    assert result.context_fields == ("tier",)
    assert result.access_fields == ("api_url",)
    assert result.execution_fields == ("poll_interval_s",)
    assert result.secret_count == result.unknown_count == 1
    assert not result.valid_domain
    report = json.dumps(asdict(result))
    assert "SECRET" not in report and "private.example" not in report
    assert classify_registration("provider", "{}").valid_domain


@pytest.mark.parametrize("kind", [None, [], {}, 1, True, "invalid"])
def test_invalid_registration_kind_has_a_typed_safe_error(kind):
    with pytest.raises(RegistrationError, match="REGISTRATION_KIND"):
        registration_json(kind, "{}")
