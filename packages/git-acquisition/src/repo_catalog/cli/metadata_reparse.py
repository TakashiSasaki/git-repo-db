"""Append decoder claims for already retained commit/tree/tag representations."""

import argparse

from repo_catalog.cli.separated_io import decode, emit, failure, read_document


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True)
    parser.add_argument(
        "--input",
        required=True,
        help="Object with unit (tagged GitMetadataInput), objects (tagged OIDs), notes (claim/mapping pairs)",
    )
    parser.add_argument("--request-origin", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--new-request", action="store_true")
    parser.add_argument("--text-encoding", default="utf-8")
    parser.add_argument(
        "--metadata-encoding", choices=("utf-8", "latin-1"), default="utf-8"
    )
    parser.add_argument(
        "--metadata-errors",
        choices=("strict", "surrogateescape", "backslashreplace", "replace"),
        default="backslashreplace",
    )
    parser.add_argument(
        "--errors",
        choices=("strict", "surrogateescape", "backslashreplace", "replace"),
        default="surrogateescape",
    )
    parser.add_argument("--max-object-bytes", type=int, default=64 * 1024 * 1024)
    args = parser.parse_args(argv)
    try:
        from repo_catalog.application.metadata_reparse import reparse
        from repo_catalog.domain.p1_coordination import RequestIdentity

        document = decode(read_document(args.input))
        emit(
            reparse(
                args.catalog,
                document["unit"],
                tuple(document.get("objects", ())),
                request=RequestIdentity(args.request_origin, args.request),
                new_request=args.new_request,
                text_encoding=args.text_encoding,
                errors=args.errors,
                metadata_encoding=args.metadata_encoding,
                metadata_errors=args.metadata_errors,
                max_object_bytes=args.max_object_bytes,
                notes=tuple(tuple(pair) for pair in document.get("notes", ())),
            )
        )
        return 0
    except Exception as error:
        if not isinstance(error, (ValueError, OSError, LookupError)) and not hasattr(
            error, "code"
        ):
            raise
        return failure(error)


if __name__ == "__main__":
    raise SystemExit(main())
