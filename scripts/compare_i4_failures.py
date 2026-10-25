"""Compare all inherited I3 non-successes with I4, retaining first trace locations."""

import argparse
import hashlib
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
            message = event.get("message") or ""
            actual_phase = (
                "teardown"
                if tag == "error" and "failed on teardown" in message
                else phase
            )
            refusal = re.search(
                r"I2_(?:TRANSFER|IDENTIFICATION_WIRE)_UNSUPPORTED(?:: [^\n\\]*)?",
                message or trace,
            )
            key = (case.get("classname"), case.get("name"))
            if key in result:
                raise ValueError(f"duplicate non-success node: {key}")
            frames = [
                {"path": p, "line": int(n), "function": fn}
                for p, n, fn in re.findall(
                    r"^(tests/[^\n:]+\.py|src/[^\n:]+\.py):(\d+):(?: in (\w+))?",
                    trace,
                    re.M,
                )
            ]
            result[(case.get("classname"), case.get("name"))] = {
                "phase": actual_phase,
                "message": event.get("message"),
                "stage_refusal": refusal.group() if refusal else None,
                "frames": frames,
            }
    return result


def compare(baseline, current):
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
                    new
                    and old["stage_refusal"]
                    and new["stage_refusal"] == old["stage_refusal"]
                ),
                "same_trace_paths_functions": bool(
                    new
                    and [(f["path"], f["function"]) for f in new["frames"]]
                    == [(f["path"], f["function"]) for f in old["frames"]]
                ),
            }
        )
    return {
        "baseline_non_successes": len(baseline),
        "current_non_successes": len(current),
        "same_nodes": set(baseline) == set(current),
        "resolved": len(set(baseline) - set(current)),
        "additional": len(set(current) - set(baseline)),
        "additional_nodes": [
            {"class": key[0], "name": key[1], **current[key]}
            for key in sorted(set(current) - set(baseline))
        ],
        "comparison": comparison,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--current",
        type=Path,
        required=True,
        help="Current invocation's regressions.xml",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--baseline-archive",
        type=Path,
        default=ROOT / "docs/implementation/evidence/adr0031-i3/author-evidence.zip",
    )
    parser.add_argument(
        "--baseline-entry",
        required=True,
        help="Explicit historical XML member, e.g. final-*/regressions.xml where available; no runtime selection",
    )
    args = parser.parse_args()
    with zipfile.ZipFile(args.baseline_archive) as archive:
        baseline = index(archive.read(args.baseline_entry))
    current = index(args.current.read_bytes())
    result = compare(baseline, current)
    result.update(
        baseline_archive=str(args.baseline_archive.resolve()),
        baseline_archive_sha256=hashlib.sha256(
            args.baseline_archive.read_bytes()
        ).hexdigest(),
        baseline_entry=args.baseline_entry,
        current=str(args.current.resolve()),
        current_sha256=hashlib.sha256(args.current.read_bytes()).hexdigest(),
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    # The frozen final I3 baseline has 79 failures/errors. Historical labels
    # select evidence bytes, never a required current SQLite release.
    valid = (
        result["baseline_non_successes"] == 79
        and result["same_nodes"]
        and all(
            c["same_phase"]
            and c["same_stage_refusal"]
            and c["same_trace_paths_functions"]
            for c in result["comparison"]
        )
    )
    if not valid:
        raise SystemExit(
            "non-success comparison differs; see explicit first-failure differences"
        )


if __name__ == "__main__":
    main()
