"""Checkout convenience wrapper for the single packaged offline v2 importer."""

import argparse
import json

from repo_catalog.application.import_service import import_catalog
from repo_catalog.domain.models import CatalogError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--source-cache", action="append", default=[])
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-batches", type=int)
    args = parser.parse_args()
    return import_catalog(
        args.source,
        args.state_dir,
        source_caches=args.source_cache,
        batch_size=args.batch_size,
        max_batches=args.max_batches,
    )


if __name__ == "__main__":
    try:
        print(json.dumps(main(), sort_keys=True))
    except CatalogError as exc:
        print(json.dumps({"code": exc.code, "severity": "blocking"}))
        raise SystemExit(2) from None
