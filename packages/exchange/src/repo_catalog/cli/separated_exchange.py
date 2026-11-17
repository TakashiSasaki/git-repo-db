"""Explicit bounded selections for separated Exchange; transport does not grant authority."""

import argparse
from pathlib import Path

from repo_catalog.cli.separated_io import (
    authority,
    decode,
    emit,
    failure,
    read_document,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("export", "import"))
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--authority")
    parser.add_argument("--input")
    parser.add_argument("--output")
    parser.add_argument("--new-request", action="store_true")
    parser.add_argument("--request-origin")
    parser.add_argument("--request")
    parser.add_argument("--permit-repository", action="append", default=[])
    args = parser.parse_args(argv)
    if (args.request is None) != (args.request_origin is None):
        parser.error("--request and --request-origin must be supplied together")
    if not getattr(args, "output" if args.command == "export" else "input"):
        parser.error("export requires --output; import requires --input")
    try:
        from repo_catalog.application.exchange import ExchangeService
        from repo_catalog.domain.exchange import ExchangeSelectionScope, encode_package
        from repo_catalog.domain.p1_coordination import RequestIdentity

        selection = decode(read_document(args.selection))
        if type(selection) is not ExchangeSelectionScope:
            raise ValueError("selection requires tagged ExchangeSelectionScope")
        kwargs = {}
        if selection.include_context and (args.command == "import" or args.authority):
            if args.command == "import" and not args.authority:
                parser.error("Context import requires --authority")
            auth, admission, _ = authority(
                args.authority, "exchange_" + args.command, selection
            )
            kwargs = {"authorization": auth, "admission": admission}
        service = ExchangeService(args.catalog, operational=args.catalog, **kwargs)
        if args.command == "export":
            package = service.export_package(selection=selection)
            with Path(args.output).open("x", encoding="utf-8") as stream:
                stream.write(encode_package(package) + "\n")
            result = {"output": args.output, "package_id": package.package_id}
        else:
            result = service.import_package(
                read_document(args.input),
                selection=selection,
                permitted_repository_uuidv4s=tuple(args.permit_repository),
                new_request=args.new_request,
                request=None
                if args.request is None
                else RequestIdentity(args.request_origin, args.request),
            )
        emit(result)
        return 0
    except (ValueError, OSError) as error:
        return failure(error)


if __name__ == "__main__":
    raise SystemExit(main())
