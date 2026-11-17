"""Inspect, stop/resume and deliberately increase finite durable request budgets."""

import argparse

from repo_catalog.cli.separated_io import emit, failure


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "show",
            "list",
            "cache-status",
            "cancel",
            "resume",
            "increase-limit",
            "complete",
            "cache-gc",
            "cache-register",
            "cache-touch",
            "cache-reuse",
            "cache-reserve",
            "cache-monitor",
            "cache-release",
        ),
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--request-origin")
    parser.add_argument("--request")
    parser.add_argument(
        "--unit",
        choices=("input_bytes", "verification_bytes", "metadata_units", "proof_steps"),
    )
    parser.add_argument("--finite-limit", type=int)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-cache-bytes", type=int)
    parser.add_argument("--cache-ttl-seconds", type=int)
    parser.add_argument("--min-free-bytes", type=int, default=0)
    parser.add_argument("--max-cache-entries", type=int, default=10_000)
    parser.add_argument("--attempt")
    parser.add_argument(
        "--cache-path-hex",
        help="Lossless relative managed Git directory bytes in hexadecimal",
    )
    parser.add_argument("--last-used-us", type=int)
    parser.add_argument("--reservation-bytes", type=int)
    args = parser.parse_args(argv)
    if args.command not in ("list", "cache-status", "cache-gc", "cache-reuse") and (
        not args.request or not args.request_origin
    ):
        parser.error("--request and --request-origin are required")
    if args.command == "increase-limit" and (
        args.unit is None or args.finite_limit is None
    ):
        parser.error("--unit and --finite-limit are required")
    cache = args.command.startswith("cache-")
    if cache and (args.max_cache_bytes is None or args.cache_ttl_seconds is None):
        parser.error(
            "cache operations require --max-cache-bytes and --cache-ttl-seconds"
        )
    if (
        cache
        and args.command not in ("cache-status", "cache-gc", "cache-reuse")
        and args.attempt is None
    ):
        parser.error("managed cache mutation requires the exact --attempt UUID")
    if (
        args.command in ("cache-register", "cache-touch", "cache-reuse")
        and args.cache_path_hex is None
    ):
        parser.error("--cache-path-hex is required")
    if args.command in ("cache-register", "cache-touch") and args.last_used_us is None:
        parser.error("--last-used-us is required")
    if args.command == "cache-reserve" and args.reservation_bytes is None:
        parser.error("--reservation-bytes is required")
    try:
        from repo_catalog.adapters.sqlite.operations_admin import OperationsAdmin
        from repo_catalog.domain.p1_coordination import RequestIdentity

        if cache:
            from repo_catalog.adapters.sqlite.managed_git_cache import ManagedGitCache

            app = ManagedGitCache(
                args.catalog,
                max_bytes=args.max_cache_bytes,
                min_free_bytes=args.min_free_bytes,
                ttl_seconds=args.cache_ttl_seconds,
                max_entries=args.max_cache_entries,
            )
            if args.command == "cache-status":
                result = app.status()
            elif args.command == "cache-gc":
                result = app.collect(apply=args.apply)
            elif args.command == "cache-reuse":
                result = app.reuse(bytes.fromhex(args.cache_path_hex))
            else:
                request = RequestIdentity(args.request_origin, args.request)
                if args.command in ("cache-register", "cache-touch"):
                    result = getattr(app, args.command.removeprefix("cache-"))(
                        request,
                        args.attempt,
                        bytes.fromhex(args.cache_path_hex),
                        args.last_used_us,
                    )
                elif args.command == "cache-reserve":
                    result = app.reserve(request, args.attempt, args.reservation_bytes)
                else:
                    result = getattr(app, args.command.removeprefix("cache-"))(
                        request, args.attempt
                    )
        elif args.command == "list":
            app = OperationsAdmin(args.catalog)
            result = app.inspect(limit=args.limit)
        else:
            app = OperationsAdmin(args.catalog)
            request = RequestIdentity(args.request_origin, args.request)
            if args.command == "show":
                result = app.show(request)
            elif args.command == "increase-limit":
                result = app.increase(request, args.unit, args.finite_limit)
            else:
                result = app.transition(
                    request,
                    resume=args.command == "resume",
                    complete=args.command == "complete",
                )
        emit(result)
        return 0
    except Exception as error:
        if not isinstance(error, (ValueError, OSError)) and not hasattr(error, "code"):
            raise
        return failure(error)


if __name__ == "__main__":
    raise SystemExit(main())
