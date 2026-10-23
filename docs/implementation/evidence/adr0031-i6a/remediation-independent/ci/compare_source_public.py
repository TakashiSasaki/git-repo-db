"""Compare fresh source/public broad JUnit failures without trusting summary claims."""
from pathlib import Path
import json
import re
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent


def failures(run):
    z = zipfile.ZipFile(HERE / f"{run}-receipts.zip")
    root = ET.fromstring(z.read("artifacts/access-registry/i5/regressions.xml"))
    result = {}
    for case in root.findall(".//testcase"):
        child = case.find("failure")
        phase = "call"
        if child is None:
            child = case.find("error")
            phase = "setup"
        if child is None:
            continue
        text = child.text or ""
        frames = re.findall(r'(?:^|\n)([^\n]+\.py):([0-9]+): ([^\n]+)', text)
        frames += re.findall(r'File "([^"\n]+\.py)", line ([0-9]+), in ([^\n]+)', text)
        normalized = []
        for file, line, function in frames:
            if "/repo_catalog/" in file:
                file = "repo_catalog/" + file.split("/repo_catalog/")[-1]
            elif "/tests/" in file:
                file = "tests/" + file.split("/tests/")[-1]
            normalized.append([file, int(line), function])
        assert normalized
        key = case.get("classname") + "::" + case.get("name")
        result[key] = {
            "phase": phase,
            "type": child.get("type"),
            "message": child.get("message"),
            "frames": normalized,
            "refusals": sorted(set(re.findall(r'\b(?:PERMISSION_DENIED|I2_TRANSFER_UNSUPPORTED|I2_IDENTIFICATION_WIRE_UNSUPPORTED|UNSUPPORTED_UNTIL_I[0-9]+)\b', text))),
        }
    return result


source = failures(39902230351)
public = failures(39903868666)
assert set(source) == set(public) and len(source) == 299
rows = []
for node in sorted(source):
    a, b = source[node], public[node]
    rows.append({
        "node": node,
        "same_phase": a["phase"] == b["phase"],
        "same_exception_type": a["type"] == b["type"],
        "same_refusals": a["refusals"] == b["refusals"],
        "same_full_frame_projection": a["frames"] == b["frames"],
        "source": a,
        "public": b,
    })
fields = ("same_phase", "same_exception_type", "same_refusals", "same_full_frame_projection")
result = {"source_run": 39902230351, "public_run": 39903868666, "count": len(rows), "counts": {k: sum(r[k] for r in rows) for k in fields}, "nodes": rows}
(HERE / "source-public-failure-comparison.json").write_text(json.dumps(result, indent=2) + "\n")
print(result["counts"])
