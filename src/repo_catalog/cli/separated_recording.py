"""Inspect optional local HTTP recordings without parsing or replaying them."""

import argparse
from pathlib import Path

from repo_catalog.cli.separated_io import emit, failure


def parser():
    result = argparse.ArgumentParser(prog="repo-catalog recording", description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect-message")
    inspect.add_argument("archive_reference")
    inspect.add_argument("--archive-root", type=Path, required=True)
    inspect.add_argument("--max-bytes", type=int, default=1024 * 1024)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        from repo_catalog.application.recording_inspection import inspect_message

        emit(
            inspect_message(
                args.archive_root, args.archive_reference, max_bytes=args.max_bytes
            )
        )
        return 0
    except Exception as error:
        return failure(error)


if __name__ == "__main__":
    raise SystemExit(main())
