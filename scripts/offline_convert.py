"""Guarded offline archive, phase handoff and identity conversion."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.conversion import engine, guards  # noqa: E402
from scripts.conversion.common import ConversionError  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "seal",
            "archive",
            "verify",
            "handoff",
            "verify-phase",
            "identity-init",
            "identity",
            "verify-identity",
            "integrated",
            "stored",
            "verify-stored",
        ),
    )
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--source-cache", type=Path, action="append", default=[])
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--representative-repositories", action="store_true")
    args = parser.parse_args()
    if args.action == "seal" and not args.source:
        parser.error("seal requires --source")
    protected = []
    if args.source:
        protected.append(args.source)
    protected.extend(args.source_cache)
    if args.action != "seal":
        descriptor = json.loads((args.work_dir / "sealed.json").read_bytes())
        protected += [
            args.work_dir / "source.sqlite3",
            args.work_dir / "sealed.json",
            descriptor["original"]["path"],
            *(c["path"] for c in descriptor["caches"]),
        ]
    policy = guards.install(args.work_dir, protected)
    if args.action == "seal":
        engine.run(
            policy,
            "seal",
            args.work_dir,
            source_path=args.source,
            caches=args.source_cache,
        )
        return {"sealed": True}
    if args.action in {
        "verify",
        "handoff",
        "verify-phase",
        "verify-identity",
        "verify-stored",
    }:
        return engine.run(policy, args.action, args.work_dir)
    if args.action == "identity-init":
        return engine.run(
            policy, args.action, args.work_dir, batch_size=args.batch_size
        )
    if args.action in {"identity", "integrated", "stored"}:
        return engine.run(
            policy,
            args.action,
            args.work_dir,
            batch_size=args.batch_size,
            max_batches=args.max_batches,
        )
    return engine.run(
        policy,
        "archive",
        args.work_dir,
        batch_size=args.batch_size,
        map_repositories=args.representative_repositories,
        max_batches=args.max_batches,
    )


if __name__ == "__main__":
    try:
        print(json.dumps(main(), sort_keys=True))
    except KeyboardInterrupt:
        print(
            json.dumps({"code": "CONVERSION_INTERRUPTED", "severity": "partial"}),
            file=sys.stderr,
        )
        raise SystemExit(130) from None
    except (ConversionError, OSError, sqlite3.Error, ValueError) as exc:
        code = (
            exc.code if isinstance(exc, ConversionError) else "STORAGE_OR_INPUT_FAILURE"
        )
        result = {"code": code, "severity": "blocking"}
        if hasattr(exc, "report"):
            result["admission"] = {
                "unsupported": sum(
                    item["classification"] == "unsupported"
                    for item in exc.report["preservation_dispositions"]
                ),
                "admission_version": exc.report.get("admission_version"),
                "diagnostic_codes": sorted(
                    {item["code"] for item in exc.report["diagnostics"]}
                ),
            }
        print(json.dumps(result), file=sys.stderr)
        raise SystemExit(2) from None
