"""Shared typed codecs charge Core work and optional Exchange independently."""

from uuid import uuid4

import pytest

from repo_catalog.domain.exchange import (
    _WIRE_WORK,
    ExchangeError,
    ExchangePackage,
    ExchangeSelectionScope,
    _ref_input_work,
    decode_package,
    empty_core_section,
    encode_package,
)
from repo_catalog.domain.p1_core import Provenance, account_verification
from repo_catalog.domain.query_work import UnlimitedWorkBudget
from repo_catalog.domain.ref_exchange import (
    _hex,
    _provenance,
    account_ref_input,
    observation_to_wire,
)
from repo_catalog.domain.ref_observation import (
    RefObservation,
    RefObservationKey,
    new_uuid7,
)


def test_shared_codec_charges_repeated_core_work_without_exchange_meter():
    work = UnlimitedWorkBudget()
    value = Provenance("reported", "original", "ref", "decoder", "1", "reported")
    with account_verification(work):
        assert _provenance(value.encoded) == value
        first = work.usage["input_bytes"]
        assert first == 2 * len(value.encoded)
        assert _provenance(value.encoded) == value
    assert work.usage["input_bytes"] == 2 * first


def test_exchange_envelope_counts_repeated_shared_decode_and_core_work():
    repository = str(uuid4())
    observation = RefObservation(
        RefObservationKey(str(uuid4()), new_uuid7()),
        repository,
        b"refs/heads/main",
        "local-git",
        "visible-refs",
        1,
    )
    section = empty_core_section()
    section["ref_observations"].append(observation_to_wire(observation))
    package = ExchangePackage(
        package_id=str(uuid4()),
        exported_at_us=1,
        sender_catalog_instance_uuidv4=str(uuid4()),
        repository_uuidv4=repository,
        selection_scope=ExchangeSelectionScope(
            all_selected=True, include_context=False
        ),
        core=section,
    )
    measurement = {
        "metadata_units": 0,
        "verification_bytes": 0,
        "ref_decode_input_bytes": 0,
    }
    work = UnlimitedWorkBudget()
    token = _WIRE_WORK.set(measurement)
    try:
        with account_verification(work):
            encoded = encode_package(package)
            first = measurement["ref_decode_input_bytes"]
            assert first == 4 * len(observation.ref_name_bytes)
            decode_package(encoded)
            assert measurement["ref_decode_input_bytes"] == 2 * first
            assert work.usage["input_bytes"] == 2 * first
    finally:
        _WIRE_WORK.reset(token)


def test_failed_shared_decode_keeps_work_and_resets_observer():
    work = UnlimitedWorkBudget()
    measurement = {"ref_decode_input_bytes": 0}
    token = _WIRE_WORK.set(measurement)
    try:
        with account_verification(work):
            with pytest.raises(ValueError):
                with account_ref_input(_ref_input_work):
                    _hex("zz")
            assert measurement["ref_decode_input_bytes"] == 2
            assert work.usage["input_bytes"] == 2
            # The failed optional scope does not retain its meter for Core use.
            assert _hex("00") == b"\0"
            assert measurement["ref_decode_input_bytes"] == 2
            assert work.usage["input_bytes"] == 6
    finally:
        _WIRE_WORK.reset(token)


def test_exchange_codec_ceiling_refuses_before_decode_and_keeps_prior_work(monkeypatch):
    from repo_catalog.domain import exchange

    monkeypatch.setattr(exchange, "MAX_PACKAGE_BYTES", 1)
    measurement = {"ref_decode_input_bytes": 1}
    work = UnlimitedWorkBudget()
    token = _WIRE_WORK.set(measurement)
    try:
        with account_verification(work), account_ref_input(_ref_input_work):
            with pytest.raises(ExchangeError) as failure:
                _hex("0000")
        assert failure.value.code == "INPUT_LIMIT"
        assert measurement["ref_decode_input_bytes"] == 1
        assert work.usage["input_bytes"] == 0
    finally:
        _WIRE_WORK.reset(token)
