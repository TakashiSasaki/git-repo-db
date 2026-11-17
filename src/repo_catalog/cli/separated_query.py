"""Responsibility-oriented composition of authoritative queries."""

import sys


def main(argv=None):
    values = list(sys.argv[1:] if argv is None else argv)
    if values and values[0] in (
        "pr-code",
        "pr-code-capture",
        "pr-documents",
        "pr-list",
    ):
        from repo_catalog.cli.pr_assessment import main as pr

        return pr(values)
    if values and values[0] in (
        "log",
        "tree",
        "path",
        "diff",
        "repository",
        "compare",
        "path-history",
        "digest",
    ):
        from repo_catalog.cli.git_history import main as history

        return history(values)
    if values and values[0] in (
        "coverage",
        "ref-observation",
        "ref-enumeration",
        "notes-mapping",
        "notes-inventories",
        "note-bytes",
    ):
        from repo_catalog.cli.core_evidence_query import main as evidence

        return evidence(values)
    if values and values[0] in (
        "providers",
        "sources",
        "resource",
        "resources",
        "text",
        "context-coverage",
    ):
        from repo_catalog.cli.context_browse import main as context

        return context(values)
    if values and values[0] in ("-h", "--help"):
        print(
            "Additional Core commands: repository log tree path path-history diff compare digest coverage ref-observation ref-enumeration notes-mapping notes-inventories note-bytes"
        )
        print(
            "Additional Context commands: providers sources resource resources text context-coverage"
        )
        print("PR completeness commands: pr-code pr-documents pr-list")
    from repo_catalog.cli.production_query import main as query

    return query(values)


if __name__ == "__main__":
    raise SystemExit(main())
