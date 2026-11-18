"""History and raw-path metadata queries; no ordinary file bodies are read."""

import argparse
import base64

from repo_catalog.cli.query_limits import add_limits, read_limits
from repo_catalog.cli.separated_io import emit, failure


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "log",
            "tree",
            "path",
            "diff",
            "repository",
            "compare",
            "path-history",
            "digest",
        ),
    )
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--format", choices=("sha1", "sha256"), default="sha1")
    parser.add_argument("--object-oid")
    parser.add_argument("--algorithm", choices=("raw-md5", "raw-sha1", "raw-sha256"))
    parser.add_argument("--digest")
    parser.add_argument("--byte-length", type=int)
    parser.add_argument("--left")
    parser.add_argument("--right")
    parser.add_argument("--path-b64")
    parser.add_argument(
        "--set",
        choices=("left-only", "right-only", "common", "symmetric"),
        default="symmetric",
    )
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--first-parent", action="store_true")
    parser.add_argument("--recursive", action="store_true")
    add_limits(parser)
    args = parser.parse_args(argv)
    for field in (
        ("left", "right")
        if args.command in ("diff", "compare")
        else ()
        if args.command in ("repository", "digest")
        else ("object_oid",)
    ):
        if not getattr(args, field):
            parser.error("--" + field.replace("_", "-") + " is required")
    if args.command == "digest" and (args.algorithm is None or args.digest is None):
        parser.error("digest requires --algorithm and --digest")
    if args.command in ("path", "path-history") and args.path_b64 is None:
        parser.error("path requires --path-b64")
    try:
        from repo_catalog.application.git_history_query import GitHistoryQuery
        from repo_catalog.domain.p1_repository import OID

        service = GitHistoryQuery(args.catalog, read_limits=read_limits(args))
        if args.command == "digest":
            result = service.digest(
                args.algorithm,
                args.digest,
                byte_length=args.byte_length,
                limit=args.limit,
            )
        elif args.command == "repository":
            result = service.get_repository_view()
        elif args.command == "compare":
            result = service.compare(
                OID(args.format, args.left),
                OID(args.format, args.right),
                selection=args.set,
                limit=args.limit,
            )
        elif args.command == "path-history":
            result = service.path_history(
                OID(args.format, args.object_oid),
                base64.b64decode(args.path_b64, validate=True),
                limit=args.limit,
            )
        elif args.command == "diff":
            result = service.diff(
                OID(args.format, args.left),
                OID(args.format, args.right),
                max_entries=args.limit,
            )
        elif args.command == "log":
            result = service.history(
                OID(args.format, args.object_oid),
                limit=args.limit,
                first_parent=args.first_parent,
            )
        else:
            result = service.tree(
                OID(args.format, args.object_oid),
                max_entries=args.limit,
                recursive=args.recursive,
                path=None
                if args.path_b64 is None
                else base64.b64decode(args.path_b64, validate=True),
            )
        emit(result)
        return 0
    except (ValueError, OSError) as error:
        return failure(error)


if __name__ == "__main__":
    raise SystemExit(main())
