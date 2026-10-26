"""Comprehensive tests for log filtering, receipt extraction, fail-closed reconciliation,
and resource reservation (ADR 0034 Work Packages A through F).
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import sys
import zipfile
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from scripts import ci_execute, ci_profile, ci_query, resource_scheduler


def _create_signed_bundle(
    files: dict[str, bytes],
    indexed: bool = True,
    corrupt_index_hash: bool = False,
    extra_unindexed: bool = False,
    path_traversal: bool = False,
) -> tuple[bytes, str, int]:
    """Helper to create a validated or intentionally mutated receipt zip archive."""
    buf = io.BytesIO()
    index_map = {}
    for name, data in files.items():
        index_map[name] = {
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }

    if corrupt_index_hash:
        for name in index_map:
            index_map[name]["sha256"] = "0" * 64

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
        if indexed:
            zf.writestr(
                "receipt-index.json", json.dumps(index_map, indent=2).encode("utf-8")
            )
        if extra_unindexed:
            zf.writestr("unindexed-file.txt", b"surprise payload\n")
        if path_traversal:
            zf.writestr("../traversal.txt", b"escape\n")

    raw = buf.getvalue()
    digest = hashlib.sha256(raw).hexdigest()
    return raw, digest, len(raw)


def _format_log(
    raw: bytes,
    digest: str,
    length: int,
    timestamp_prefix: str = "2026-10-25T17:24:40.4275369Z ",
    bom: bool = False,
    omit_end: bool = False,
    corrupt_end_digest: bool = False,
    corrupt_b64: bool = False,
    omit_data: bool = False,
) -> str:
    """Format log text containing CI_RECEIPTS records."""
    prefix = timestamp_prefix
    bom_str = "\ufeff" if bom else ""
    lines = [f"{prefix}info: job initialization started"]
    lines.append(f"{bom_str}{prefix}CI_RECEIPTS_BEGIN_V1 {digest} {length}")

    if not omit_data:
        b64 = base64.b64encode(raw).decode("ascii")
        if corrupt_b64:
            b64 = b64[:20] + "???!!!" + b64[20:]
        chunk_size = 120
        for i in range(0, len(b64), chunk_size):
            lines.append(f"{prefix}CI_RECEIPTS_DATA_V1 {b64[i : i + chunk_size]}")

    if not omit_end:
        end_d = "f" * 64 if corrupt_end_digest else digest
        lines.append(f"{prefix}CI_RECEIPTS_END_V1 {end_d}")

    lines.append(f"{prefix}info: job complete")
    return "\n".join(lines) + "\n"


# =========================================================================
# Work Package A: Log Filtering
# =========================================================================


def test_filter_log_timestamp_and_raw_prefixes(tmp_path):
    """Verify filtering removes DATA records with timestamps or raw prefixes, but preserves commands."""
    raw, digest, length = _create_signed_bundle({"a.txt": b"payload"})
    log_content = (
        "2026-10-25T17:24:40.4275369Z info: step 1\n"
        f"2026-10-25T17:24:40.4275369Z CI_RECEIPTS_BEGIN_V1 {digest} {length}\n"
        "2026-10-25T17:24:40.4275369Z CI_RECEIPTS_DATA_V1 aW52YWxpZDE=\n"
        "CI_RECEIPTS_DATA_V1 dW5wcmVmaXhlZDI=\n"
        "\ufeff2026-10-25T17:24:40.4275369Z CI_RECEIPTS_DATA_V1 Ym9tcHJlZml4\n"
        '2026-10-25T17:24:40.4275369Z + echo "CI_RECEIPTS_DATA_V1 in command should stay"\n'
        "2026-10-25T17:24:40.4275369Z python -c \"print('CI_RECEIPTS_DATA_V1')\"\n"
        f"2026-10-25T17:24:41.4275369Z CI_RECEIPTS_END_V1 {digest}\n"
        "2026-10-25T17:24:41.4275369Z info: completed\n"
    )

    in_file = tmp_path / "raw.log"
    out_file = tmp_path / "filtered.log"
    in_file.write_text(log_content, encoding="utf-8")

    ret = ci_query.main(["filter-log", str(in_file), "-o", str(out_file)])
    assert ret == 0
    assert out_file.is_file()

    filtered = out_file.read_text(encoding="utf-8")
    assert "info: step 1" in filtered
    assert f"CI_RECEIPTS_BEGIN_V1 {digest} {length}" in filtered
    assert f"CI_RECEIPTS_END_V1 {digest}" in filtered
    assert "info: completed" in filtered
    assert '+ echo "CI_RECEIPTS_DATA_V1 in command should stay"' in filtered
    assert "python -c \"print('CI_RECEIPTS_DATA_V1')\"" in filtered

    # Verified: none of the actual DATA payload lines leaked into filtered output
    assert "aW52YWxpZDE=" not in filtered
    assert "dW5wcmVmaXhlZDI=" not in filtered
    assert "Ym9tcHJlZml4" not in filtered


def test_filter_log_missing_file_fails_closed(tmp_path):
    """Verify filter-log returns code 2 when input file does not exist."""
    missing = tmp_path / "nonexistent.log"
    ret = ci_query.main(["filter-log", str(missing)])
    assert ret == 2


def test_filter_log_real_access_job_fixture(tmp_path):
    """Verify filtering against the real Access workflow run 40215888079 log if present on host."""
    scratch_log = Path(
        "/home/ubuntu/.gemini/antigravity-cli/brain/624a97cb-9f93-4c7f-a5b1-797d6c39a9df/scratch/0_registry-runtime.txt"
    )
    if not scratch_log.is_file():
        return

    out_file = tmp_path / "filtered_real.log"
    ret = ci_query.main(["filter-log", str(scratch_log), "-o", str(out_file)])
    assert ret == 0
    assert out_file.is_file()

    raw_len = len(scratch_log.read_text(encoding="utf-8"))
    filt_len = len(out_file.read_text(encoding="utf-8"))
    assert raw_len == 2899527
    assert filt_len == 75886  # exactly ~76 KB (74.11 KB)
    assert filt_len < 80 * 1024


# =========================================================================
# Work Package B: Receipt Extraction & Security Validation
# =========================================================================


def test_extract_receipt_valid_timestamped(tmp_path):
    """Verify extraction of real-format timestamp-prefixed receipt."""
    files = {
        "summary.json": b'{"status": "PASSED"}\n',
        "tests.xml": b'<testsuite name="unit"/>\n',
    }
    raw, digest, length = _create_signed_bundle(files)
    log_text = _format_log(raw, digest, length)

    log_file = tmp_path / "job.log"
    log_file.write_text(log_text, encoding="utf-8")
    dest_dir = tmp_path / "extracted"

    ret = ci_query.main(["extract-receipt", str(log_file), "-o", str(dest_dir)])
    assert ret == 0
    assert (dest_dir / "summary.json").is_file()
    assert (dest_dir / "tests.xml").is_file()
    assert (dest_dir / "receipt-index.json").is_file()
    assert json.loads((dest_dir / "summary.json").read_text())["status"] == "PASSED"


def test_extract_receipt_missing_end_marker_fails_closed(tmp_path):
    """Verify extraction fails closed when log terminates before END marker."""
    raw, digest, length = _create_signed_bundle({"a.txt": b"123"})
    log_text = _format_log(raw, digest, length, omit_end=True)

    log_file = tmp_path / "truncated.log"
    log_file.write_text(log_text, encoding="utf-8")
    dest_dir = tmp_path / "extracted_truncated"

    ret = ci_query.main(["extract-receipt", str(log_file), "--dest", str(dest_dir)])
    assert ret == 2
    # Safe: no partial files published
    assert not dest_dir.exists() or len(list(dest_dir.iterdir())) == 0


def test_extract_receipt_digest_mismatch_fails_closed(tmp_path):
    """Verify extraction fails closed when outer SHA-256 does not match BEGIN/END."""
    raw, digest, length = _create_signed_bundle({"a.txt": b"123"})
    corrupt_digest = "e" * 64
    log_text = _format_log(raw, corrupt_digest, length)

    log_file = tmp_path / "corrupt_digest.log"
    log_file.write_text(log_text, encoding="utf-8")
    dest_dir = tmp_path / "extracted_corrupt"

    ret = ci_query.main(["extract-receipt", str(log_file), "-o", str(dest_dir)])
    assert ret == 2
    assert not dest_dir.exists() or len(list(dest_dir.iterdir())) == 0


def test_extract_receipt_invalid_base64_fails_closed(tmp_path):
    """Verify extraction fails closed on invalid Base64 chunks."""
    raw, digest, length = _create_signed_bundle({"a.txt": b"123"})
    log_text = _format_log(raw, digest, length, corrupt_b64=True)

    log_file = tmp_path / "bad_b64.log"
    log_file.write_text(log_text, encoding="utf-8")
    dest_dir = tmp_path / "extracted_bad_b64"

    ret = ci_query.main(["extract-receipt", str(log_file), "-o", str(dest_dir)])
    assert ret == 2
    assert not dest_dir.exists() or len(list(dest_dir.iterdir())) == 0


def test_extract_receipt_member_hash_mismatch_fails_closed(tmp_path):
    """Verify extraction fails closed when an archived member digest contradicts receipt-index.json."""
    raw, digest, length = _create_signed_bundle(
        {"valid.txt": b"content"}, corrupt_index_hash=True
    )
    log_text = _format_log(raw, digest, length)

    log_file = tmp_path / "index_mismatch.log"
    log_file.write_text(log_text, encoding="utf-8")
    dest_dir = tmp_path / "extracted_mismatch"

    ret = ci_query.main(["extract-receipt", str(log_file), "-o", str(dest_dir)])
    assert ret == 2
    assert not dest_dir.exists() or len(list(dest_dir.iterdir())) == 0


def test_extract_receipt_path_traversal_rejected(tmp_path):
    """Verify ZipSlip path traversal members are rejected and do not escape."""
    raw, digest, length = _create_signed_bundle(
        {"normal.txt": b"ok"}, path_traversal=True
    )
    log_text = _format_log(raw, digest, length)

    log_file = tmp_path / "traversal.log"
    log_file.write_text(log_text, encoding="utf-8")
    dest_dir = tmp_path / "extracted_traversal"

    ret = ci_query.main(["extract-receipt", str(log_file), "-o", str(dest_dir)])
    assert ret == 2
    assert not (tmp_path / "traversal.txt").exists()


def test_extract_receipt_unexpected_unindexed_member_rejected(tmp_path):
    """Verify unindexed unexpected members in zip are rejected."""
    raw, digest, length = _create_signed_bundle(
        {"declared.txt": b"ok"}, extra_unindexed=True
    )
    log_text = _format_log(raw, digest, length)

    log_file = tmp_path / "unindexed.log"
    log_file.write_text(log_text, encoding="utf-8")
    dest_dir = tmp_path / "extracted_unindexed"

    ret = ci_query.main(["extract-receipt", str(log_file), "-o", str(dest_dir)])
    assert ret == 2
    assert not dest_dir.exists() or len(list(dest_dir.iterdir())) == 0


def test_extract_receipt_oversized_compressed_fails_budget(tmp_path):
    """Verify compressed payloads exceeding 2 MiB fail closed."""
    # Enforce budget in parse_log_receipt_bundle
    fake_len = ci_execute.MAX_COMPRESSED_RECEIPT_BYTES + 1024
    log_text = (
        f"CI_RECEIPTS_BEGIN_V1 {'a' * 64} {fake_len}\n"
        "CI_RECEIPTS_DATA_V1 aW52YWxpZA==\n"
        f"CI_RECEIPTS_END_V1 {'a' * 64}\n"
    )
    log_file = tmp_path / "oversized.log"
    log_file.write_text(log_text, encoding="utf-8")
    dest_dir = tmp_path / "extracted_oversized"

    ret = ci_query.main(["extract-receipt", str(log_file), "-o", str(dest_dir)])
    assert ret == 2


def test_extract_receipt_multiple_ambiguous_bundles(tmp_path):
    """Verify multiple bundles in log fail without explicit digest selection, and succeed with it."""
    raw1, digest1, len1 = _create_signed_bundle({"bundle1.txt": b"first"})
    raw2, digest2, len2 = _create_signed_bundle({"bundle2.txt": b"second"})

    log_text = (
        _format_log(raw1, digest1, len1) + "\n" + _format_log(raw2, digest2, len2)
    )
    log_file = tmp_path / "multi.log"
    log_file.write_text(log_text, encoding="utf-8")

    # Without --digest: fails closed as ambiguous
    dest_ambig = tmp_path / "out_ambig"
    ret = ci_query.main(["extract-receipt", str(log_file), "-o", str(dest_ambig)])
    assert ret == 2

    # With explicit --digest: succeeds
    dest_target = tmp_path / "out_target"
    ret = ci_query.main(
        [
            "extract-receipt",
            str(log_file),
            "-o",
            str(dest_target),
            "--digest",
            digest2,
        ]
    )
    assert ret == 0
    assert (dest_target / "bundle2.txt").is_file()
    assert not (dest_target / "bundle1.txt").exists()


def test_extract_receipt_single_bundle_requested_digest_must_match(tmp_path):
    """An explicit SHA-256 selector applies even to one valid receipt."""
    raw, digest, length = _create_signed_bundle({"a.txt": b"payload"})
    logfile = tmp_path / "job.log"
    logfile.write_text(_format_log(raw, digest, length), encoding="utf-8")
    dest = tmp_path / "receipt"
    assert (
        ci_query.main(
            ["extract-receipt", str(logfile), "-o", str(dest), "--digest", "f" * 64]
        )
        == 2
    )
    assert not dest.exists()


def test_extract_receipt_supports_existing_empty_directory(tmp_path):
    """Preserve the existing CLI contract for an empty destination directory."""
    raw, digest, length = _create_signed_bundle({"a.txt": b"payload"})
    logfile = tmp_path / "job.log"
    logfile.write_text(_format_log(raw, digest, length), encoding="utf-8")
    dest = tmp_path / "receipt"
    dest.mkdir()
    assert ci_query.main(["extract-receipt", str(logfile), "-o", str(dest)]) == 0
    assert (dest / "a.txt").read_bytes() == b"payload"


def test_extract_receipt_refuses_existing_evidence_without_modification(tmp_path):
    """Do not combine independently verified and untrusted prior evidence."""
    raw, digest, length = _create_signed_bundle({"a.txt": b"payload"})
    logfile = tmp_path / "job.log"
    logfile.write_text(_format_log(raw, digest, length), encoding="utf-8")
    dest = tmp_path / "receipt"
    dest.mkdir()
    (dest / "existing.txt").write_text("keep")
    assert ci_query.main(["extract-receipt", str(logfile), "-o", str(dest)]) == 2
    assert sorted(p.name for p in dest.iterdir()) == ["existing.txt"]
    assert (dest / "existing.txt").read_text() == "keep"


def test_extract_receipt_failed_atomic_rename_leaves_destination_empty(tmp_path):
    """A failed final publication must not expose partial receipt contents."""
    raw, digest, length = _create_signed_bundle({"a.txt": b"first", "b.txt": b"second"})
    logfile = tmp_path / "job.log"
    logfile.write_text(_format_log(raw, digest, length), encoding="utf-8")
    dest = tmp_path / "receipt"
    dest.mkdir()
    with patch.object(ci_execute.os, "replace", side_effect=OSError("rename failed")):
        assert ci_query.main(["extract-receipt", str(logfile), "-o", str(dest)]) == 2
    assert list(dest.iterdir()) == []


# =========================================================================
# Work Package C: Fail-Closed Execution Status & Duplicate Node Handling
# =========================================================================


def test_reconciliation_rejects_duplicate_nodes():
    """Verify multiset equality with duplicate node IDs fails closed and cannot claim EXACT_ONCE_MATCH."""
    record = {
        "name": "unit",
        "exit_code": 0,
        "selection": {
            "test_ids": ["tests/test_dup.py::test_a", "tests/test_dup.py::test_a"]
        },
        "junit": {
            "tests": [
                {"nodeid": "tests/test_dup.py::test_a", "status": "passed"},
                {"nodeid": "tests/test_dup.py::test_a", "status": "passed"},
            ]
        },
    }

    summary = ci_profile.build_execution_summary(record)
    reconcil = summary["reconciliation"]
    assert reconcil["consistent"] is False
    assert "NODE_MISMATCH" in reconcil["status"]
    assert "duplicates=1" in reconcil["status"]
    assert reconcil["duplicate_count"] == 1
    assert "tests/test_dup.py::test_a" in reconcil["duplicate_nodes"]


def test_reconciliation_rejects_node_mismatch_when_pytest_exited_zero():
    """Verify equal counts with mismatched nodes fail closed."""
    record = {
        "name": "unit",
        "exit_code": 0,
        "selection": {"test_ids": ["tests/test_one.py::test_a"]},
        "junit": {
            "tests": [
                {"nodeid": "tests/test_other.py::test_b", "status": "passed"},
            ]
        },
    }

    summary = ci_profile.build_execution_summary(record)
    reconcil = summary["reconciliation"]
    assert reconcil["consistent"] is False
    assert "NODE_MISMATCH" in reconcil["status"]
    assert reconcil["missing_count"] == 1
    assert reconcil["unexpected_count"] == 1


def test_ci_profile_run_returns_nonzero_on_reconciliation_mismatch(tmp_path):
    """Runner must return nonzero when pytest child process exits 0 but reconciliation fails."""
    xml_path = tmp_path / "junit.xml"
    xml_content = (
        '<testsuite name="unit" tests="1" errors="0" failures="0" skipped="0">\n'
        '  <testcase classname="tests.test_mock" name="test_mock_1" time="0.01"/>\n'
        "</testsuite>\n"
    )

    # Command simulates a tool that exits 0 and writes unexpected/different JUnit
    script = f"import pathlib; pathlib.Path({repr(str(xml_path))}).write_text({repr(xml_content)})"

    args = Namespace(
        name="test_lane",
        command=[sys.executable, "-c", script],
        output=tmp_path,
        junit=xml_path,
        journal=None,
        mode="sequential",
        workers=1,
        series="test",
        reference=None,
        quiet=True,
        selection={"test_ids": ["tests/test_expected.py::test_req"]},
    )

    exit_code = ci_profile.run(args)
    # Child exited 0, but reconciliation was NODE_MISMATCH -> must fail closed with exit code 1
    assert exit_code == 1

    summary_file = tmp_path / "execution-summary.json"
    assert summary_file.is_file()
    summary = json.loads(summary_file.read_text())
    assert summary["reconciliation"]["consistent"] is False
    assert "NODE_MISMATCH" in summary["reconciliation"]["status"]
    assert summary["child_exit_code"] == 0
    assert summary["verification_exit_code"] == 1
    assert summary["exit_code"] == 1
    profile = json.loads((tmp_path / "test_lane.json").read_text())
    assert profile["exit_code"] == 1
    assert profile["child_exit_code"] == 0
    assert profile["verification_exit_code"] == 1
    assert profile["verified"] is False
    assert ci_query.main(["status", str(tmp_path)]) == 1


def test_ci_profile_run_returns_nonzero_on_missing_junit(tmp_path):
    """Fault-injection: pytest exits 0 but JUnit XML was not generated -> returns nonzero (2)."""
    missing_xml = tmp_path / "missing.xml"
    args = Namespace(
        name="test_lane",
        command=[sys.executable, "-c", "import sys; sys.exit(0)"],
        output=tmp_path,
        junit=missing_xml,
        journal=None,
        mode="sequential",
        workers=1,
        series="test",
        reference=None,
        quiet=True,
    )

    exit_code = ci_profile.run(args)
    assert exit_code == 2
    profile = json.loads((tmp_path / "test_lane.json").read_text())
    summary = json.loads((tmp_path / "execution-summary.json").read_text())
    assert profile["exit_code"] == summary["exit_code"] == 2
    assert profile["child_exit_code"] == summary["child_exit_code"] == 0
    assert profile["verification_exit_code"] == 2


# =========================================================================
# Work Package D: Inherited-Failure Reconciliation Validation
# =========================================================================


def test_unreconciled_failures_remain_unclassified():
    """Failures without authoritative reconciliation evidence must be UNCLASSIFIED_FAILURE."""
    record = {
        "name": "unit",
        "exit_code": 1,
        "junit": {
            "tests": [
                {
                    "nodeid": "tests/integration/test_transfer.py::test_fence",
                    "status": "failure",
                    "details": {"message": "failed", "type": "AssertionError"},
                }
            ]
        },
    }

    index = ci_profile.build_failure_index(record["junit"], reconciliation=None)
    assert len(index["failures"]) == 1
    f = index["failures"][0]
    assert f["classification"] == "UNCLASSIFIED_FAILURE"
    assert f["is_inherited"] is False


def test_rejected_comparator_verdict_cannot_produce_reconciled():
    """A rejected comparator verdict (acceptance_verdict=REJECTED) cannot produce RECONCILED_WITH_INHERITED_FAILURES."""
    record = {
        "name": "regressions",
        "exit_code": 1,
        "selection": {"test_ids": ["tests/t1.py::test_inherited"]},
        "junit": {
            "tests": [
                {
                    "nodeid": "tests/t1.py::test_inherited",
                    "status": "failure",
                    "details": {"message": "failed", "type": "AssertionError"},
                }
            ]
        },
    }

    reconciliation = {
        "acceptance_verdict": "REJECTED",
        "new_regressions_count": 0,
        "changed_failures_count": 0,
        "node_details": [
            {
                "node_id": "tests/t1.py::test_inherited",
                "classification": "STAGE_TRANSFER",
                "is_inherited": True,
            }
        ],
    }

    failure_index = ci_profile.build_failure_index(
        record["junit"], reconciliation=reconciliation
    )
    summary = ci_profile.build_execution_summary(
        record, failure_index=failure_index, reconciliation=reconciliation
    )

    reconcil = summary["reconciliation"]
    assert reconcil["consistent"] is False
    assert "RECONCILIATION_REJECTED" in reconcil["status"]
    assert reconcil["status"] != "RECONCILED_WITH_INHERITED_FAILURES"


def test_new_only_failures_retains_unclassified_and_changed(tmp_path):
    """ci_query failures --new-only excludes ONLY verified inherited failures."""
    index = {
        "failures": [
            {
                "nodeid": "tests/t1.py::test_inherited",
                "classification": "STAGE_TRANSFER",
                "is_inherited": True,
            },
            {
                "nodeid": "tests/t2.py::test_unclassified",
                "classification": "UNCLASSIFIED_FAILURE",
                "is_inherited": False,
            },
            {
                "nodeid": "tests/t3.py::test_changed",
                "classification": "CHANGED_FAILURE",
                "is_inherited": False,
            },
            {
                "nodeid": "tests/t4.py::test_new",
                "classification": "NEW_REGRESSION",
                "is_inherited": False,
            },
        ]
    }

    (tmp_path / "failure-index.json").write_text(json.dumps(index), encoding="utf-8")

    out = io.StringIO()
    with patch("sys.stdout", out):
        ret = ci_query.main(["failures", str(tmp_path), "--new-only", "--json"])
    assert ret == 1

    res = json.loads(out.getvalue())
    remaining = [f["nodeid"] for f in res["failures"]]
    assert "tests/t1.py::test_inherited" not in remaining
    assert "tests/t2.py::test_unclassified" in remaining
    assert "tests/t3.py::test_changed" in remaining
    assert "tests/t4.py::test_new" in remaining


# =========================================================================
# Work Package E: Scoped Resource Scheduler
# =========================================================================


def test_scoped_host_cpu_reservation_default_path(tmp_path):
    """Verify scoped_host_cpu_reservation defaults to user temp or CI_RESOURCE_LOCK env var."""
    custom_lock = tmp_path / "custom.lock"
    with patch.dict(os.environ, {"CI_RESOURCE_LOCK": str(custom_lock)}):
        with resource_scheduler.scoped_host_cpu_reservation(2) as granted:
            assert granted >= 1
            assert custom_lock.is_file()
