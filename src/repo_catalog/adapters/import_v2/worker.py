"""Fresh-process entry point; guards stay installed for its entire lifetime."""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from . import engine, guards
from .common import ConversionError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--source-cache", type=Path, action="append", default=[])
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-batches", type=int)
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    protected = [args.source, *args.source_cache]
    seal = args.state_dir / "import-v2/sealed.json"
    if os.path.lexists(seal):
        if seal.is_symlink() or not seal.is_file():
            raise ConversionError("SEAL_NOT_REGULAR")
        saved = json.loads(seal.read_bytes())
        protected.extend(
            [
                seal,
                args.state_dir / "import-v2/source.sqlite3",
                saved["original"]["path"],
                *(c["path"] for c in saved["caches"]),
            ]
        )
    policy = guards.install(args.state_dir, protected)
    return engine.run(
        policy,
        args.state_dir,
        source_path=args.source,
        source_caches=args.source_cache,
        batch_size=args.batch_size,
        max_batches=args.max_batches,
    )


if __name__ == "__main__":
    try:
        print(json.dumps({"ok": True, "result": main()}, sort_keys=True))
    except KeyboardInterrupt:
        print(
            json.dumps(
                {"ok": False, "code": "IMPORT_INTERRUPTED", "severity": "partial"}
            )
        )
        raise SystemExit(130) from None
    except (ConversionError, OSError, sqlite3.Error, ValueError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": exc.code
                    if isinstance(exc, ConversionError)
                    else "IMPORT_STORAGE_OR_INPUT_FAILURE",
                    "severity": "blocking",
                }
            )
        )
        raise SystemExit(2) from None
