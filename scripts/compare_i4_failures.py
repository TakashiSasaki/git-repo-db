"""Compare all inherited I3 non-successes with I4, retaining first trace locations."""

import argparse
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def index(raw):
    result = {}
    for case in ET.fromstring(raw).findall(".//testcase"):
        for tag, phase in [("failure", "call"), ("error", "setup")]:
            event = case.find(tag)
            if event is None:
                continue
            trace = event.text or ""
            frames = [
                {"path": p, "line": int(n), "function": fn}
                for p, n, fn in re.findall(
                    r"^(tests/[^\n:]+\.py|src/[^\n:]+\.py):(\d+):(?: in (\w+))?",
                    trace,
                    re.M,
                )
            ]
            result[(case.get("classname"), case.get("name"))] = {
                "phase": phase,
                "message": event.get("message"),
                "stage_refusal": re.search(
                    r"I2_(?:TRANSFER|IDENTIFICATION_WIRE)_UNSUPPORTED(?:: [^\n\\]*)?",
                    event.get("message") or trace,
                ).group(),
                "frames": frames,
            }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = {}
    with zipfile.ZipFile(
        ROOT / "docs/implementation/evidence/adr0031-i3/author-evidence.zip"
    ) as z:
        for version in ("3.51.3", "3.53.1"):
            baseline = index(z.read(f"final-{version}/regressions.xml"))
            current = index(
                (args.evidence / f"author-{version}/regressions.xml").read_bytes()
            )
            comparison = []
            for key, old in sorted(baseline.items()):
                new = current.get(key)
                comparison.append(
                    {
                        "class": key[0],
                        "name": key[1],
                        "baseline": old,
                        "current": new,
                        "same_phase": bool(new and new["phase"] == old["phase"]),
                        "same_message": bool(new and new["message"] == old["message"]),
                        "same_stage_refusal": bool(
                            new and new["stage_refusal"] == old["stage_refusal"]
                        ),
                        "same_trace_paths_functions": bool(
                            new
                            and [(f["path"], f["function"]) for f in new["frames"]]
                            == [(f["path"], f["function"]) for f in old["frames"]]
                        ),
                    }
                )
            results[version] = {
                "baseline_non_successes": len(baseline),
                "current_non_successes": len(current),
                "same_nodes": set(baseline) == set(current),
                "resolved": len(set(baseline) - set(current)),
                "additional": len(set(current) - set(baseline)),
                "comparison": comparison,
            }
    args.output.write_text(json.dumps(results, indent=2) + "\n")
    assert all(
        r["baseline_non_successes"] == 79
        and r["same_nodes"]
        and all(
            c["same_phase"]
            and c["same_stage_refusal"]
            and c["same_trace_paths_functions"]
            for c in r["comparison"]
        )
        for r in results.values()
    ), "see explicit first-failure differences"


if __name__ == "__main__":
    main()
