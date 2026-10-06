"""Create synthetic operational v2 evidence for the offline integrated demo.

This command only builds a fresh disposable source fixture. It does not read
user data, run Git, contact a forge, convert a target or activate a catalog.
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from tests.support.integrated_fixture import make_integrated_source  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-dir",
        type=Path,
        help="New disposable fixture directory; defaults to a temporary directory",
    )
    parser.add_argument(
        "--derived", action="store_true", help="Include app-built FTS and ANALYZE"
    )
    parser.add_argument(
        "--malformed", action="store_true", help="Include saved semantic defects"
    )
    parser.add_argument(
        "--scale", type=int, default=1, help="Positive synthetic document count"
    )
    args = parser.parse_args()
    if args.scale < 1:
        parser.error("--scale must be a positive integer")
    state_dir = (
        args.state_dir
        or Path(tempfile.mkdtemp(prefix="repo-catalog-integrated-")) / "source"
    )
    state_dir = state_dir.absolute()
    if state_dir.exists() or state_dir.is_symlink():
        parser.error("--state-dir must identify a new directory")
    database, cache = make_integrated_source(
        state_dir, derived=args.derived, malformed=args.malformed, scale=args.scale
    )
    print(
        json.dumps(
            {
                "fixture": "synthetic-operational-v2-integrated",
                "database": str(database),
                "cache": str(cache),
                "derived": args.derived,
                "malformed": args.malformed,
                "scale": args.scale,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
