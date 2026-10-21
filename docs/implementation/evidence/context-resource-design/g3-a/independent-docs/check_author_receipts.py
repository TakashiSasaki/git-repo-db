import gzip
import hashlib
import json
from pathlib import Path

p = Path(
    "/workspace/g3-a/docs/implementation/evidence/context-resource-design/g3-a/author"
)
s = json.loads((p / "summary.json").read_text())
checks = []
for runtime in s["runtimes"]:
    for name, r in runtime["files"].items():
        data = (p / name).read_bytes()
        if name.endswith(".gz"):
            assert (
                len(data) == r["gzip_bytes"]
                and hashlib.sha256(data).hexdigest() == r["gzip_sha256"]
            ), name
            raw = gzip.decompress(data)
            assert (
                len(raw) == r["raw_bytes"]
                and hashlib.sha256(raw).hexdigest() == r["raw_sha256"]
            ), name
        else:
            assert (
                len(data) == r["bytes"]
                and hashlib.sha256(data).hexdigest() == r["sha256"]
            ), name
    result = json.loads(
        gzip.decompress((p / (runtime["label"] + "-results.json.gz")).read_bytes())
    )
    assert (
        result["execution_git_head"] == s["freeze_commit"]
        and result["execution_git_tree"] == s["freeze_tree"]
    )
    assert result["candidate_sql_sha256"] == runtime["candidate_sql_sha256"]
    assert (
        result["passed"] == 11
        and result["failed"] == 0
        and result["collection_execution_equal"]
    )
    assert sum(len(c["steps"]) for c in result["cases"]) == 292
    r = [
        step
        for c in result["cases"]
        for step in c["steps"]
        if step["label"] == "direct SQL I8 support fails typed native-I7 FK"
    ][0]
    assert (
        r["sqlite_errorname"] == "SQLITE_CONSTRAINT_FOREIGNKEY"
        and r["sqlite_errorcode"] == 787
    )
    assert (
        r["rowsets_before"] == r["rowsets_after"]
        and r["transaction_before"]
        and r["transaction_after"]
    )
    assert r["sql"] and any("INSERT INTO resource_relations" in q for q in r["sql"])
    checks.append(
        {
            "runtime": runtime["runtime"]["sqlite_version"],
            "source_id": runtime["runtime"]["sqlite_source_id"],
            "freeze_head": result["execution_git_head"],
            "freeze_tree": result["execution_git_tree"],
            "passed_groups": 11,
            "steps": 292,
            "I8_sql_error": "SQLITE_CONSTRAINT_FOREIGNKEY/787",
            "actual_statement_rowsets_unchanged": True,
            "hashes_verified": True,
        }
    )
out = {
    "scope": "independent inspection of newly generated author receipts, not an independent rerun",
    "author_summary_sha256": hashlib.sha256(
        (p / "summary.json").read_bytes()
    ).hexdigest(),
    "results": checks,
}
Path("/tmp/g3-doc-review/author-receipt-checks.json").write_text(
    json.dumps(out, indent=2) + "\n"
)
print(json.dumps(out, indent=2))
