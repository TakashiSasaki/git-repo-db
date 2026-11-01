"""Recovery budget dimensions meter actual decoding and nominal domain work."""

from __future__ import annotations

import base64
import json
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite import core_recovery as recovery
from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.p1_core import CoreFailure
from repo_catalog.domain.recovery import RecoveryBudget


def usage(catalog):
    return json.loads((catalog / "p1-recovery-request-default.json").read_text())[
        "cumulative_usage"
    ]


@pytest.mark.parametrize("table", ["git_objects", "repositories"])
@pytest.mark.parametrize("replay", [False, True])
def test_nominal_metadata_cannot_bypass_single_unit_ceiling(
    synthetic_catalog, tmp_path, repo_uuid, table, replay
):
    import sqlite3

    with sqlite3.connect(synthetic_catalog / "core.sqlite3") as conn:
        if table == "git_objects":
            oid = (
                conn.execute("SELECT object_oid FROM git_objects LIMIT 1").fetchone()[0]
                if replay
                else "9" * 40
            )
            first = {"object_format": "sha1", "object_oid": oid}
            second = {"object_format": "sha1", "object_oid": "2" * 40}
        elif table == "repositories":
            first = {"repository_uuidv4": repo_uuid if replay else str(uuid4())}
            second = {"repository_uuidv4": str(uuid4())}
    salvage = tmp_path / "nominal.jsonl"
    rows = [
        {
            "candidate_type": "git_metadata",
            "extraction_provenance": {"table": table},
            "payload": payload,
        }
        for payload in (first, second)
    ]
    salvage.write_text("".join(json.dumps(row) + "\n" for row in rows))
    result = RecoveryService().merge_salvage(
        synthetic_catalog,
        salvage,
        budget=RecoveryBudget(max_work_units={"metadata_units": 1}),
    )
    assert result.admitted_units == (0 if replay else 1)
    assert result.replayed_units == (1 if replay else 0)
    assert result.unprocessed_units == 1
    assert result.rejected_units == 0
    assert usage(synthetic_catalog)["metadata_units"] == 1
    assert not result.input_complete


@pytest.mark.parametrize("size", [1, 2, 3, 1000])
def test_base64_exact_decoded_allowance_settles_padding(size):
    body = b"x" * size
    work = recovery.RecoveryWorkBudget(work_limits={"input_bytes": size})
    assert (
        recovery._decode_bounded_base64(base64.b64encode(body).decode(), size, work)
        == body
    )
    assert work.usage["input_bytes"] == size


def test_base64_budget_refusal_precedes_decoder(monkeypatch):
    def forbidden_decoder(*args, **kwargs):
        pytest.fail("unreserved base64 allocation")

    monkeypatch.setattr(recovery.base64, "b64decode", forbidden_decoder)
    work = recovery.RecoveryWorkBudget(work_limits={"input_bytes": 1})
    with pytest.raises(CoreFailure, match="budget"):
        recovery._decode_bounded_base64("A" * 1336, 2000, work)
    assert work.usage["input_bytes"] == 0


def test_invalid_base64_retains_decode_expenditure():
    work = recovery.RecoveryWorkBudget(work_limits={"input_bytes": 3})
    with pytest.raises(ValueError):
        recovery._decode_bounded_base64("!!!!", 10, work)
    assert work.usage["input_bytes"] == 3


def test_context_encoding_reserves_decoded_input_before_allocation():
    class ForbiddenText(str):
        def encode(self, *args, **kwargs):
            pytest.fail("unreserved Context UTF-8 allocation")

    work = recovery.RecoveryWorkBudget(work_limits={"input_bytes": 1})
    with pytest.raises(CoreFailure, match="budget"):
        recovery._bounded_utf8(ForbiddenText("xx"), 10, work)
    assert work.usage["input_bytes"] == 0


@pytest.mark.parametrize("ceiling", [1, 1000])
def test_digest_rejection_still_meters_decoded_input(
    synthetic_catalog, tmp_path, ceiling
):
    body = b"x" * 1000
    salvage = tmp_path / "digest-rejected.jsonl"
    salvage.write_text(
        json.dumps(
            {
                "candidate_type": "retained_body",
                "payload": {
                    "object_format": "sha1",
                    "object_oid": "1" * 40,
                    "native_type": "commit",
                    "size": len(body),
                    "physical_copy_uuidv4": str(uuid4()),
                    "body_base64": base64.b64encode(body).decode(),
                    "digest_sha256": "0" * 64,
                },
            }
        )
        + "\n"
    )
    result = RecoveryService().merge_salvage(
        synthetic_catalog,
        salvage,
        budget=RecoveryBudget(max_work_units={"input_bytes": ceiling}),
    )
    assert result.admitted_units == 0
    assert result.unprocessed_units == (1 if ceiling == 1 else 0)
    assert result.rejected_units == (0 if ceiling == 1 else 1)
    assert usage(synthetic_catalog)["input_bytes"] == (0 if ceiling == 1 else len(body))


def test_rejected_nominal_candidate_still_consumes_metadata_work(
    synthetic_catalog, tmp_path
):
    salvage = tmp_path / "bad-nominal.jsonl"
    rows = [
        {
            "candidate_type": "git_metadata",
            "extraction_provenance": {"table": "git_objects"},
            "payload": {"object_format": "sha1", "object_oid": oid},
        }
        for oid in ("bad", "a" * 40)
    ]
    salvage.write_text("".join(json.dumps(row) + "\n" for row in rows))
    receipt = RecoveryService().merge_salvage(
        synthetic_catalog,
        salvage,
        budget=RecoveryBudget(max_work_units={"metadata_units": 1}),
    )
    assert receipt.rejected_units == 1
    assert receipt.unprocessed_units == 1
    assert receipt.admitted_units == 0
    assert usage(synthetic_catalog)["metadata_units"] == 1
