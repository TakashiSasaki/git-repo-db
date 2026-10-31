"""Build/check isolated target schema fingerprints, without opening user catalogs."""

import argparse
import json
from pathlib import Path

from repo_catalog.adapters.sqlite.p1_schema import expected_ddl_manifest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT / "packages/core/src/repo_catalog/adapters/sqlite/p1_ddl/fingerprints.json"
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = json.dumps(expected_ddl_manifest(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text() != result:
            raise SystemExit(
                "P1 fingerprints stale; run uv run python scripts/build_p1_schema.py"
            )
        print("P1 composed DDL and physical schema fingerprints match all four stores")
    else:
        OUTPUT.write_text(result)
        print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
