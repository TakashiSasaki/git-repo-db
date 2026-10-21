import gzip
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path("/workspace/g3-review-docs-final")
EVIDENCE = ROOT / "docs/implementation/evidence/context-resource-design/g3-a"
OUT = Path("/tmp/g3-doc-post-review")
FROZEN = "4c07cb8ecc4d744ddfb8c3908deb91d8ad72f6f9"
FINAL = "6bc9525ab853344fba309b28aee343250f575738"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def blob(rev, path):
    return subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", rev + ":" + path]
    )


manifest = json.loads((EVIDENCE / "input-freeze.json").read_text())
for path in list(manifest["inputs"]) + [
    "docs/implementation/evidence/context-resource-design/g3-a/input-freeze.json"
]:
    assert blob(FROZEN, path) == blob(FINAL, path), path
assert blob(FROZEN, "src") == blob(FINAL, "src")

old_author = json.loads(
    (EVIDENCE / "author/summary-before-log-compression.json").read_text()
)
new_author = json.loads((EVIDENCE / "author/summary.json").read_text())
for key, value in old_author.items():
    if key != "runtimes":
        assert new_author[key] == value, key
for before, after in zip(old_author["runtimes"], new_author["runtimes"], strict=True):
    for key, value in before.items():
        if key != "files":
            assert after[key] == value, key
    for name, record in before["files"].items():
        if name.endswith(".log"):
            raw = gzip.decompress((EVIDENCE / "author" / (name + ".gz")).read_bytes())
            assert len(raw) == record["bytes"] and digest(raw) == record["sha256"]
        else:
            assert after["files"][name] == record, name

review_path = EVIDENCE / "independent-review"
old_manifest = json.loads(
    (review_path / "manifest-before-log-compression.json").read_text()
)
new_manifest = json.loads((review_path / "manifest.json").read_text())
for key, value in old_manifest.items():
    if key != "files":
        assert new_manifest[key] == value, key
for name, record in new_manifest["files"].items():
    stored = (review_path / name).read_bytes()
    assert (
        len(stored) == record["stored_bytes"]
        and digest(stored) == record["stored_sha256"]
    ), name
    raw = gzip.decompress(stored) if name.endswith(".gz") else stored
    assert len(raw) == record["raw_bytes"] and digest(raw) == record["raw_sha256"], name
for name, record in old_manifest["files"].items():
    if name.endswith(".log"):
        raw = gzip.decompress((review_path / (name + ".gz")).read_bytes())
        assert (
            len(raw) == record["raw_bytes"] and digest(raw) == record["raw_sha256"]
        ), name
    elif name == "final-review.md":
        raw = (review_path / name).read_bytes()
        prefix = raw[: record["raw_bytes"]]
        assert digest(prefix) == record["raw_sha256"]
        assert (
            b"Publication losslessly compresses stdout logs"
            in raw[record["raw_bytes"] :]
        )
    else:
        assert new_manifest["files"][name] == record, name

reviewer_counts = []
for name in ("minimum.json.gz", "newer.json.gz"):
    data = json.loads(gzip.decompress((review_path / name).read_bytes()))
    assert data["passed"] and data["failures"] == []
    assert data["observation_count"] == 99 and len(data["observations"]) == 99
    assert data["reviewed_commit"] == FROZEN
    assert data["composed_sql_sha256"] == manifest["candidate_sql_sha256"]
    reviewer_counts.append(
        {"runtime": data["sqlite_version"], "own_observations": 99, "passed": True}
    )

original_docs_receipt = json.loads(
    (EVIDENCE / "independent-docs/author-receipt-checks.json").read_text()
)
assert original_docs_receipt["author_summary_sha256"] == digest(
    (EVIDENCE / "author/summary-before-log-compression.json").read_bytes()
)
current_author_checks = json.loads(
    Path("/tmp/g3-doc-review/author-receipt-checks.json").read_text()
)
assert current_author_checks["author_summary_sha256"] == digest(
    (EVIDENCE / "author/summary.json").read_bytes()
)

result = {
    "reviewed_final_commit": FINAL,
    "reviewed_final_tree": "97efebce12fcf1ff45ddd336e60d59c14d5e8dfb",
    "initial_reviewed_freeze": FROZEN,
    "scope": "post-freeze documentation, status, links and receipt transport; no SQLite rerun",
    "frozen_executable_inputs_and_manifest_unchanged": True,
    "product_src_unchanged": True,
    "author_transport_only_metadata_and_lossless_logs": True,
    "independent_review_transport_only_metadata_and_lossless_logs": True,
    "original_doc_receipt_matches_retained_precompression_author_summary": True,
    "current_author_summary_sha256": current_author_checks["author_summary_sha256"],
    "final_review_transport_note_is_factual_postfreeze_appendix": True,
    "four_manifest_final_review_hash_fields_match_current_report": True,
    "independent_execution_receipts_verified": reviewer_counts,
    "material_semantic_or_executable_change": False,
    "verdict": "READY FOR OWNER DESIGN ACCEPTANCE",
    "findings": [],
}
(OUT / "transport-checks.json").write_text(json.dumps(result, indent=2) + "\n")
(OUT / "post-freeze-author-receipt-checks.json").write_text(
    json.dumps(current_author_checks, indent=2) + "\n"
)
print(json.dumps(result, indent=2))
