"""Independent stdlib audit of freshly retrieved hosted logs and receipt payloads.

Run in the frozen checkout; no GitHub writes, test execution or extraction.
"""
import base64
import collections
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = Path.cwd()
PIN = "08fbb956c2e470e245146b0dbae747ed0690ea40"


def sanitize_email_fields(value, parent=None):
    if isinstance(value, dict):
        return {k: ("[REDACTED_PERSONAL_EMAIL]" if k == "email" and isinstance(v, str) and "@" in v else "[REDACTED_PERSONAL_NAME]" if k == "name" and parent in ("author", "committer") and isinstance(v, str) else sanitize_email_fields(v, k)) for k, v in value.items() if not (parent == "verification" and k in ("signature", "payload"))}
    if isinstance(value, list):
        return [sanitize_email_fields(v, parent) for v in value]
    return value


def digest(b):
    return hashlib.sha256(b).hexdigest()


def audit_lane(z, prefix, installed=False):
    suffix = "-selected.txt" if installed else ".selected.txt"
    selected = z.read(prefix + suffix).decode().splitlines()
    counts = collections.Counter(selected)
    assert selected and max(counts.values()) == 1
    expected = collections.Counter()
    for node in selected:
        head, bracket, param = node.partition("[")
        parts = head.split("::")
        expected[(".".join([parts[0][:-3].replace("/", "."), *parts[1:-1]]), parts[-1] + bracket + param)] += 1
    cases = ET.fromstring(z.read(prefix + ".xml")).findall(".//testcase")
    actual = collections.Counter((c.get("classname"), c.get("name")) for c in cases)
    assert expected == actual
    outcomes = collections.Counter()
    failures = []
    for c in cases:
        outcome = "failed" if c.find("failure") is not None else "error" if c.find("error") is not None else "skipped" if c.find("skipped") is not None else "passed"
        outcomes[outcome] += 1
        if outcome != "passed":
            failures.append({"classname": c.get("classname"), "name": c.get("name"), "outcome": outcome})
    journal = [json.loads(l) for l in z.read(prefix + ".jsonl").decode().splitlines()]
    starts = collections.Counter(e["nodeid"] for e in journal if e["event"] == "start")
    assert starts == counts
    phases = collections.Counter((e["nodeid"], e["phase"]) for e in journal if e["event"] == "phase")
    setup = {e["nodeid"]: e["outcome"] for e in journal if e["event"] == "phase" and e["phase"] == "setup"}
    assert {n for n, _ in phases} == set(selected)
    assert all(phases[(n, p)] == 1 for n in selected for p in ("setup", "teardown"))
    assert all(phases[(n, "call")] == (setup[n] == "passed") for n in selected)
    finish = [e for e in journal if e["event"] == "finish"]
    assert len(finish) == 1 and finish[0]["status"] in ("completed", "failed")
    suffix = "-execution.json" if installed else ".execution.json"
    execution = json.loads(z.read(prefix + suffix))
    assert finish[0]["exitstatus"] == execution["exit_code"]
    for key in ("passed", "failed", "error", "skipped"):
        assert execution[key] == outcomes[key]
    return {"selected": len(selected), "outcomes": dict(outcomes), "process_exit": execution["exit_code"], "finish": finish[0], "exact_id_and_phase_checks": True, "nonpasses": failures}


def main():
    reports = []
    for path in sorted(HERE.glob("[0-9]*-[0-9]*.log.gz")):
        run_id, job_id = map(int, path.name.removesuffix(".log.gz").split("-"))
        log_bytes = gzip.decompress(path.read_bytes())
        log = log_bytes.decode("utf-8-sig")
        begin = re.findall(r"Z CI_RECEIPTS_BEGIN_V1 ([0-9a-f]{64}) (\d+)", log)
        if not begin:
            continue
        end = re.findall(r"Z CI_RECEIPTS_END_V1 ([0-9a-f]{64})", log)
        assert len(begin) == len(end) == 1
        raw = base64.b64decode("".join(re.findall(r"Z CI_RECEIPTS_DATA_V1 ([A-Za-z0-9+/=]+)", log)), validate=True)
        assert len(raw) == int(begin[0][1])
        assert digest(raw) == begin[0][0] == end[0]
        z = zipfile.ZipFile(io.BytesIO(raw))
        assert len(z.namelist()) == len(set(z.namelist()))
        idx = json.loads(z.read("receipt-index.json"))
        assert set(z.namelist()) == set(idx) | {"receipt-index.json"}
        for name, entry in idx.items():
            b = z.read(name)
            assert len(b) == entry["bytes"] and digest(b) == entry["sha256"]
        (HERE / f"{run_id}-receipts.zip").write_bytes(raw)
        run = json.loads((HERE / f"{run_id}-run.json").read_text())
        bind = json.loads(z.read("receipt-binding.json"))
        assert str(run_id) == bind["run_id"] and str(run["run_attempt"]) == bind["run_attempt"]
        # GitHub run.head_sha is the PR feature; receipt head is the actual test merge.
        commit = json.loads(subprocess.check_output(["gh", "api", f"repos/TakashiSasaki/git-repo-db/git/commits/{bind['head']}"]))
        (HERE / f"{run_id}-tested-commit.json").write_text(json.dumps(sanitize_email_fields(commit), indent=2) + "\n")
        assert commit["tree"]["sha"] == bind["tree"]
        assert run["head_sha"] in [p["sha"] for p in commit["parents"]]
        result = {"run_id": run_id, "job_id": job_id, "status": run["status"], "conclusion": run["conclusion"], "feature_sha": run["head_sha"], "binding": bind, "tested_commit_parents": [p["sha"] for p in commit["parents"]], "receipt_bytes": len(raw), "receipt_sha256": digest(raw), "verified_index_payloads": len(idx), "log_sha256": digest(log_bytes), "stored_log_sha256": digest(path.read_bytes())}
        if "validation-manifest.json" in z.namelist():
            m = json.loads(z.read("validation-manifest.json"))
            assert m["context"]["feature_sha"] == PIN == run["head_sha"]
            assert m["context"]["tested_sha"] == bind["head"] and m["tree_sha"] == bind["tree"]
            assert m["coverage"]["executed"] == 0 and m["test_ids"] == []
            result["development"] = {"runtime_pytest_nodes": 0, "required_unexecuted_files": len(m["coverage"]["required_files"]), "full_acceptance": m["full_acceptance"], "acceptance_status": m["acceptance_status"], "acceptance_input_hash": m["acceptance_input_hash"]}
        else:
            pref = "artifacts/access-registry/"
            inp = json.loads(z.read(pref + "i5/input-binding.json"))
            assert inp["head"] == bind["head"] and inp["tree"] == bind["tree"]
            mismatches = [n for n, h in inp["inputs"].items() if digest((ROOT / n).read_bytes()) != h]
            assert not mismatches
            result["executable_inputs"] = {"files": len(inp["inputs"]), "mismatches_against_frozen_checkout": mismatches}
            result["broad"] = audit_lane(z, pref + "i5/regressions")
            result["I4_source"] = audit_lane(z, pref + "i5/transfer-sql")
            result["I5_source"] = audit_lane(z, pref + "i5/transfer-admission")
            ordinary = z.read(pref + "i5/ordinary-collection.nodes.txt").decode().splitlines()
            selected = z.read(pref + "i5/regressions.selected.txt").decode().splitlines()
            notrun = z.read(pref + "i5/ordinary-not-executed.txt").decode().splitlines()
            assert collections.Counter(ordinary) == collections.Counter(selected + notrun)
            result["ordinary_inventory"] = {"collected": len(ordinary), "unexecuted": len(notrun)}
            product = {str(p.relative_to(ROOT / "src/repo_catalog")): digest(p.read_bytes()) for p in (ROOT / "src/repo_catalog").rglob("*") if p.is_file() and p.suffix in (".py", ".sql", ".json")}
            result["installed"] = {}
            for artifact in ("direct", "sdist"):
                for stage in (4, 5):
                    prefix = pref + f"i5-distribution/{artifact}-i{stage}"
                    lane = audit_lane(z, prefix, True)
                    imports = json.loads(z.read(prefix + "-imports.json"))
                    assert [i["phase"] for i in imports] == ["sessionstart", "sessionfinish"] * 2
                    for item in imports:
                        assert item["installed_files"] == product
                        assert item["origin"].startswith(item["prefix"] + "/") and "/site-packages/repo_catalog" in item["origin"]
                        assert all(v.startswith(item["origin"] + "/") for v in item["product_modules"].values())
                    lane["installed_modules_and_file_hashes_verified"] = len(product)
                    result["installed"][f"{artifact}-I{stage}"] = lane
                smoke = z.read(pref + f"i5-distribution/{artifact}-access.log").decode()
                assert "PERMISSION_DENIED" in smoke and "exchange.py" in smoke
                result["installed"][artifact + "-access-smoke"] = {"failed": True, "PERMISSION_DENIED": True, "exchange_guard_line_397": 'line 397' in smoke}
            result["runtime"] = json.loads(z.read("artifacts/runtime/selected.json"))
        reports.append(result)
    (HERE / "audit-results.json").write_text(json.dumps(reports, indent=2) + "\n")
    print(json.dumps([{k: v for k, v in r.items() if k in ("run_id", "conclusion", "receipt_bytes", "verified_index_payloads", "development", "executable_inputs", "ordinary_inventory")} for r in reports], indent=2))


if __name__ == "__main__":
    main()
