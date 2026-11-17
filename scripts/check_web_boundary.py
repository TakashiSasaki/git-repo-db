"""Reject reintroduced editable website sources on the product branch."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

FRONTEND = {"index.html", "package.json", "package-lock.json", "vite.config.mjs"}


def check(root: Path) -> list[str]:
    paths = (
        subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
        .decode()
        .split("\0")
    )
    return [p for p in paths if p.startswith("website/") or p in FRONTEND]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args()
    failures = check(args.root)
    if failures:
        print("Website sources belong on branch web: " + ", ".join(failures[:10]))
        return 1
    print("Product tree contains no tracked website/frontend sources.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
