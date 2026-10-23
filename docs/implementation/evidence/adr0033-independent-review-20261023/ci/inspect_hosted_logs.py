"""Verify actual timestamped hosted receipt blocks and every indexed member."""
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
result = {}
for tag in ("tests", "access", "pages"):
    source = Path(f"/tmp/adr0033-{tag}-logs.zip")
    raw = source.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as logs:
        texts = {name: logs.read(name).decode("utf-8") for name in logs.namelist() if name.endswith(".txt")}
    # One aggregate job log per job: avoid duplicate per-step copies in ZIP.
    aggregate = {name: value for name, value in texts.items() if "/" not in name}
    record = {"run_log_zip_bytes": len(raw), "run_log_zip_sha256": hashlib.sha256(raw).hexdigest(), "zip_members": list(texts), "receipts": []}
    for name, log in aggregate.items():
        (out / f"{tag}-{Path(name).stem}-without-receipt-data.log").write_text("\n".join(line for line in log.splitlines() if "CI_RECEIPTS_DATA_V1" not in line) + "\n")
        starts = list(re.finditer(r"^.*?CI_RECEIPTS_BEGIN_V1 ([0-9a-f]{64}) (\d+)\s*$", log, re.MULTILINE))
        for start in starts:
            digest, length = start.group(1), int(start.group(2))
            end = re.search(r"^.*?CI_RECEIPTS_END_V1 ([0-9a-f]{64})\s*$", log[start.end():], re.MULTILINE)
            assert end is not None and end.group(1) == digest
            body = log[start.end():start.end()+end.start()]
            data = base64.b64decode("".join(re.findall(r"CI_RECEIPTS_DATA_V1 ([A-Za-z0-9+/=]+)", body)), validate=True)
            assert len(data) == length
            assert hashlib.sha256(data).hexdigest() == digest
            with zipfile.ZipFile(io.BytesIO(data)) as receipts:
                names = receipts.namelist()
                assert len(names) == len(set(names))
                index = json.loads(receipts.read("receipt-index.json"))
                for path, entry in index.items():
                    member = receipts.read(path)
                    assert len(member) == entry["bytes"]
                    assert hashlib.sha256(member).hexdigest() == entry["sha256"]
                binding = json.loads(receipts.read("receipt-binding.json"))
                assert binding["head"] == "18f1a890c18a8aee5b4b52238b520d7444c5776f"
                assert binding["tree"] == "0f42e9d0e498e249bc2cc02f6b96df9ef87106a0"
                selected = {p: json.loads(receipts.read(p)) for p in names if p in {"plan.json", "validation-manifest.json", "sdist-members.json", "receipt-binding.json"}}
                for path, member in selected.items():
                    (out / f"{tag}-{path}").write_text(json.dumps(member, indent=2)+"\n")
                record["receipts"].append({"sha256": digest, "bytes": length, "indexed_members_verified": len(index), "binding": binding, "members": names})
            (out / f"{tag}-receipts.zip").write_bytes(data)
    result[tag] = record
(out / "hosted-log-verification.json").write_text(json.dumps(result, indent=2)+"\n")
print(json.dumps({tag:{"log_bytes":r["run_log_zip_bytes"],"receipts":[{"sha256":p["sha256"],"bytes":p["bytes"],"indexed_members_verified":p["indexed_members_verified"]} for p in r["receipts"]]} for tag,r in result.items()}, indent=2))
