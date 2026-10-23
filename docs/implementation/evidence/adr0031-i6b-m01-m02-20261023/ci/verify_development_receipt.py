"""Read-only, offline verification of actual timestamped Development CI evidence.

Supply GitHub API snapshots of the run, feature commit and actual checkout commit.
This helper never fetches, dispatches, pushes, downloads an artifact or runs payloads.
"""

import argparse
import base64
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path, PurePosixPath

MARKER = re.compile(
    r"^\d{4}-\d\d-\d\dT[^ ]+Z (CI_RECEIPTS_(?:BEGIN|DATA|END)_V1) (.*)$"
)
MAX_RECEIPT_BYTES = 16 * 1024 * 1024


def check(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def unique_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            check(key not in result, "duplicate JSON object key")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=pairs)


def log_views(paths):
    for path in paths:
        raw = path.read_bytes()
        if zipfile.is_zipfile(io.BytesIO(raw)):
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                check(
                    len(archive.namelist()) == len(set(archive.namelist())),
                    "duplicate log member",
                )
                for member in archive.infolist():
                    if not member.is_dir():
                        yield (
                            f"{path.name}:{member.filename}",
                            archive.read(member).decode("utf-8"),
                        )
        else:
            yield path.name, raw.decode("utf-8")


def recover_receipt(views):
    candidates = []
    for name, text in views:
        events = [m.groups() for line in text.splitlines() if (m := MARKER.match(line))]
        if not events:
            continue
        check(events[0][0] == "CI_RECEIPTS_BEGIN_V1", "missing BEGIN")
        check(events[-1][0] == "CI_RECEIPTS_END_V1", "missing END")
        check(
            all(k == "CI_RECEIPTS_DATA_V1" for k, _ in events[1:-1]),
            "duplicate/out-of-order marker",
        )
        claimed, length = events[0][1].split()
        check(0 < int(length) <= MAX_RECEIPT_BYTES, "receipt size bound")
        encoded = "".join(value for _, value in events[1:-1])
        check(
            len(encoded) <= 4 * ((MAX_RECEIPT_BYTES + 2) // 3), "encoded receipt bound"
        )
        blob = base64.b64decode(encoded, validate=True)
        check(len(blob) == int(length), "receipt length mismatch")
        check(digest(blob) == claimed == events[-1][1], "receipt hash mismatch")
        candidates.append((name, blob))
    check(bool(candidates), "no actual timestamped receipt")
    check(
        len({digest(blob) for _, blob in candidates}) == 1,
        "conflicting actual receipts",
    )
    return candidates[0][1], [name for name, _ in candidates]


def indexed_payloads(receipt, *, flat=True):
    with zipfile.ZipFile(io.BytesIO(receipt)) as archive:
        names = archive.namelist()
        check(len(names) == len(set(names)), "duplicate receipt member")
        for name in names:
            path = PurePosixPath(name)
            check(
                bool(name)
                and not path.is_absolute()
                and path.as_posix() == name
                and all(part not in (".", "..") for part in path.parts)
                and "\\" not in name
                and (not flat or Path(name).name == name),
                "unsafe or non-flat receipt member",
            )
        check(
            sum(member.file_size for member in archive.infolist()) <= 128 * 1024 * 1024,
            "expanded receipt bound",
        )
        files = {name: archive.read(name) for name in names}
    index = unique_json(files["receipt-index.json"])
    check(
        set(index) == set(files) - {"receipt-index.json"},
        "receipt index/member mismatch",
    )
    for name, metadata in index.items():
        check(metadata["bytes"] == len(files[name]), f"indexed length mismatch: {name}")
        check(
            metadata["sha256"] == digest(files[name]), f"indexed hash mismatch: {name}"
        )
    return files, index


def commit_identity(data):
    """Accept the ordinary commit or git/commits API shape, never inferred parents."""
    tree = data.get("tree", data.get("commit", {}).get("tree"))
    return data["sha"], tree["sha"], [parent["sha"] for parent in data["parents"]]


def verify(receipt, run, feature_commit, checkout_commit, base, expected_pr=None):
    files, index = indexed_payloads(receipt)
    binding = unique_json(files["receipt-binding.json"])
    manifest = unique_json(files["validation-manifest.json"])
    feature, feature_tree, _ = commit_identity(feature_commit)
    checkout, tree, parents = commit_identity(checkout_commit)
    check(run["head_sha"] == feature, "run feature mismatch")
    check(run["event"] == "pull_request", "not automatic PR validation")
    check(
        run["status"] == "completed" and run["conclusion"] == "success",
        "Development CI not completed successfully",
    )
    if expected_pr is not None:
        check(
            expected_pr in [pr["number"] for pr in run["pull_requests"]],
            "run PR mismatch",
        )
    check(binding["feature_sha"] == feature, "receipt feature mismatch")
    check(str(binding["run_id"]) == str(run["id"]), "receipt run mismatch")
    check(
        str(binding["run_attempt"]) == str(run["run_attempt"]),
        "receipt attempt mismatch",
    )
    check(binding["head"] == checkout, "actual checkout mismatch")
    check(parents == [base, feature], "actual ordered merge parents mismatch")
    check(
        tree == binding["tree"] == feature_tree == manifest["tree_sha"],
        "actual effective tree mismatch",
    )
    context = manifest["context"]
    check(
        context["feature_sha"] == feature
        and context["base_sha"] == base
        and context["tested_sha"] == checkout,
        "manifest commit binding mismatch",
    )
    check(
        str(context["run_id"]) == str(run["id"])
        and str(context["run_attempt"]) == str(run["run_attempt"]),
        "manifest run binding mismatch",
    )
    check(manifest["validation_mode"] == "development", "not Development validation")
    check(
        manifest["acceptance_status"] == "development_checks_passed",
        "Development checks not passed",
    )
    check(manifest["full_acceptance"] is False, "unexpected Release claim")
    check(
        manifest["coverage"]["executed"] == 0 and manifest["test_ids"] == [],
        "unexpected hosted product-test scope",
    )
    check(len(index) == 21, "Development payload set changed: review actual scope")
    return files, {
        "run_id": run["id"],
        "status": run["status"],
        "conclusion": run["conclusion"],
        "run_url": run["html_url"],
        "receipt_bytes": len(receipt),
        "receipt_sha256": digest(receipt),
        "indexed_payloads_verified": len(index),
        "feature": feature,
        "base": base,
        "checkout": checkout,
        "ordered_parents": parents,
        "effective_tree": tree,
        "acceptance_status": manifest["acceptance_status"],
        "full_acceptance": False,
        "hosted_product_test_cases": 0,
        "runtime": manifest["runtime"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", type=Path, nargs="+", required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--feature-commit", type=Path, required=True)
    parser.add_argument("--checkout-commit", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--pr", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    check(not args.output.exists(), "use a new output directory")
    receipt, views = recover_receipt(log_views(args.logs))
    files, result = verify(
        receipt,
        unique_json(args.run.read_bytes()),
        unique_json(args.feature_commit.read_bytes()),
        unique_json(args.checkout_commit.read_bytes()),
        args.base,
        args.pr,
    )
    args.output.mkdir(parents=True)
    for name, raw in files.items():
        (args.output / name).write_bytes(raw)
    (args.output / "receipt.zip").write_bytes(receipt)
    result["actual_marker_views"] = views
    result["inputs"] = {
        str(path): {"bytes": path.stat().st_size, "sha256": digest(path.read_bytes())}
        for path in [*args.logs, args.run, args.feature_commit, args.checkout_commit]
    }
    (args.output / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
