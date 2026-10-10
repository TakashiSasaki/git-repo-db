"""Shared field captures keep every scalar and live dependency check."""

import copy
import json

import pytest

from repo_catalog.adapters.sqlite import json_contracts
from tests.support.domain_facts import candidate, fresh_domain_db


def field_evidence(value):
    fields = (
        "provider_updated_at_us",
        "provider_clock_scope",
        "observed_at_us",
        "parsed_at_us",
        "parser_module",
        "parser_version",
        "acquisition_scope",
    )
    return {
        json.dumps([field], separators=(",", ":")): {
            name: copy.deepcopy(value[name]) for name in fields
        }
        for field in ("state", "draft", "metadata")
    }


def test_equal_field_captures_share_shape_check_with_distinct_capture_checks(
    monkeypatch,
):
    db = fresh_domain_db()
    value = candidate(state="open", draft=False, metadata={})
    evidence = field_evidence(value)
    evidence['["draft"]']["acquisition_scope"]["endpoint"] = "other-capture"
    shapes, dependencies = [], []
    shape = json_contracts._acquisition_shape
    dependency = json_contracts._acquisition_dependencies

    def check_shape(scope, service):
        shapes.append(scope["endpoint"])
        return shape(scope, service)

    def check_dependencies(connection, scope, **options):
        dependencies.append(scope["endpoint"])
        return dependency(connection, scope, **options)

    monkeypatch.setattr(json_contracts, "_acquisition_shape", check_shape)
    monkeypatch.setattr(json_contracts, "_acquisition_dependencies", check_dependencies)
    try:
        assert json_contracts.validate_field_evidence(db, evidence, value) == []
        assert shapes == dependencies == ["synthetic-current", "other-capture"]
        # A second admission checks shapes and current identities again.
        assert json_contracts.validate_field_evidence(db, evidence, value) == []
        assert shapes == dependencies == ["synthetic-current", "other-capture"] * 2
    finally:
        db.close()


@pytest.mark.parametrize(
    "bad",
    [
        "time",
        "producer",
        "owner",
        "boolean-count",
        "integer-subclass",
        "numeric-key",
        "tuple",
        "tuple-numeric-key",
    ],
)
def test_shared_capture_cannot_mask_invalid_field_or_different_capture(bad):
    db = fresh_domain_db()
    value = candidate(state="open", draft=False, metadata={})
    value["acquisition_scope"]["request_context"] = {"number": 1}
    if bad in {"tuple", "tuple-numeric-key"}:
        value["acquisition_scope"]["request_context"]["permissions"] = []
    evidence = field_evidence(value)
    valid = copy.deepcopy(evidence)
    altered = evidence['["draft"]']
    if bad == "time":
        altered["provider_updated_at_us"] = True
    elif bad == "producer":
        altered["parser_version"] = ""
    elif bad == "owner":
        altered["acquisition_scope"]["change_request_id"] = "other-pr"
    elif bad == "boolean-count":
        altered["acquisition_scope"]["request_context"]["number"] = True
    elif bad == "integer-subclass":

        class OtherInteger(int):
            pass

        altered["acquisition_scope"]["request_context"]["number"] = OtherInteger(1)
    elif bad == "numeric-key":
        altered["acquisition_scope"]["request_context"][1] = 1
    elif bad == "tuple":
        altered["acquisition_scope"]["request_context"]["permissions"] = ()
    else:
        altered["acquisition_scope"]["request_context"]["permissions"] = ({1: "head"},)
    try:
        assert json_contracts.validate_field_evidence(db, valid, value) == []
        with pytest.raises(json_contracts.JsonContractError):
            json_contracts.validate_field_evidence(db, evidence, value)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        db.close()
