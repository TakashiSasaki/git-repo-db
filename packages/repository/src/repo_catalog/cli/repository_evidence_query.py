"""Explicit bounded typed Repository evidence, coverage and notes queries."""

import argparse

from repo_catalog.cli.query_limits import add_limits, read_limits
from repo_catalog.cli.separated_io import emit, failure, invocation

METHODS = {
    "coverage": "get_repository_coverage",
    "ref-observation": "get_ref_observation",
    "ref-enumeration": "get_ref_enumeration",
    "notes-mapping": "get_notes_mapping",
    "notes-inventories": "list_ref_notes_inventories",
    "note-bytes": "read_ref_note_bytes",
}


class ReadWork:
    def __init__(self, limit, note_bytes):
        from repo_catalog.domain.p1_coordination import NotesLimits

        self.limit, self.used = limit, {}
        self.limits = NotesLimits(note_bytes)

    def require(self, unit, amount=1):
        if (
            type(amount) is not int
            or amount < 0
            or self.used.get(unit, 0) + amount > self.limit
        ):
            raise ValueError("QUERY_BUDGET")

    def charge(self, unit, amount):
        self.require(unit, amount)
        self.used[unit] = self.used.get(unit, 0) + amount

    def abandon(self, unit):
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=tuple(METHODS))
    parser.add_argument("--catalog", required=True)
    parser.add_argument(
        "--input", required=True, help='JSON {"args": [tagged DTOs], "kwargs": {...}}'
    )
    parser.add_argument("--max-work", type=int, default=10_000_000)
    parser.add_argument("--max-note-bytes", type=int, default=16 * 1024 * 1024)
    add_limits(parser)
    args = parser.parse_args(argv)
    if (
        not 0 < args.max_work <= 100_000_000
        or not 0 < args.max_note_bytes <= 64 * 1024 * 1024
    ):
        parser.error("finite read limits are required")
    try:
        from repo_catalog.application.repository_query import RepositoryQueryService

        positional, keywords = invocation(args.input)
        kwargs = dict(keywords)
        kwargs["work"] = ReadWork(args.max_work, args.max_note_bytes)
        emit(
            getattr(
                RepositoryQueryService(
                    args.catalog, mode="repository_only", read_limits=read_limits(args)
                ),
                METHODS[args.command],
            )(*positional, **kwargs)
        )
        return 0
    except Exception as error:
        if not isinstance(
            error, (ValueError, OSError, TypeError, KeyError)
        ) and not hasattr(error, "code"):
            raise
        return failure(error)


if __name__ == "__main__":
    raise SystemExit(main())
