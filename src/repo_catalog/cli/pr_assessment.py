"""Exact captured PR code and document completeness with bounded read-only work."""

import argparse

from repo_catalog.cli.query_limits import add_limits, read_limits
from repo_catalog.cli.separated_io import emit, failure, read_document


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("pr-code", "pr-code-capture", "pr-documents", "pr-list")
    )
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--service-instance", required=True)
    parser.add_argument(
        "--provider-resource-id",
        required=True,
        help="Canonical Provider Resource ID JSON TEXT",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "core_only", "context_only", "paired"),
        default="auto",
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--cursor")
    parser.add_argument("--expected-token")
    parser.add_argument("--max-work", type=int, default=100_000)
    parser.add_argument("--max-bytes", type=int, default=16 * 1024 * 1024)
    parser.add_argument(
        "--require-git", action=argparse.BooleanOptionalAction, default=None
    )
    parser.add_argument(
        "--require-text", action=argparse.BooleanOptionalAction, default=None
    )
    parser.add_argument(
        "--kind",
        action="append",
        choices=(
            "reviews",
            "review_comments",
            "review_threads",
            "issue_comments",
            "pr_commits",
            "pr_files",
        ),
    )
    parser.add_argument(
        "--listing-kind", action="append", choices=("pr_commits", "pr_files")
    )
    parser.add_argument(
        "--provenance-file",
        help="Original collection provenance JSON string; an object selects its canonical encoding",
    )
    parser.add_argument(
        "--thread-id", help="Actual Provider thread ID within the selected PR"
    )
    parser.add_argument("--path", help="Exact Provider-reported path selector")
    parser.add_argument("--commit", help="Exact full native commit OID selector")
    parser.add_argument("--object-format", choices=("sha1", "sha256"), default="sha1")
    parser.add_argument("--assessment", choices=("code", "documents"))
    parser.add_argument(
        "--parent-id",
        action="append",
        help="Explicit canonical PR ID; omit to assess the actual full repository roster",
    )
    parser.add_argument("--state")
    parser.add_argument("--draft", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--author")
    parser.add_argument("--text-literal")
    parser.add_argument("--document-state")
    parser.add_argument("--document-author")
    parser.add_argument(
        "--resolved", action=argparse.BooleanOptionalAction, default=None
    )
    parser.add_argument(
        "--outdated", action=argparse.BooleanOptionalAction, default=None
    )
    parser.add_argument(
        "--document-filters",
        help="Bounded JSON object of document state/author/resolved/outdated filters, including explicit null",
    )
    add_limits(parser)
    args = parser.parse_args(argv)
    if args.command != "pr-list" and args.assessment is not None:
        parser.error("--assessment selects repository pr-list behavior only")
    assessment = args.assessment or "documents"
    if args.command == "pr-code-capture":
        if (
            args.kind is None
            or len(args.kind) != 1
            or args.kind[0] not in ("pr_commits", "pr_files")
            or args.provenance_file is None
        ):
            parser.error(
                "pr-code-capture requires one code --kind and --provenance-file"
            )
        if args.listing_kind:
            parser.error("captured listing uses its one exact --kind")
    elif args.provenance_file is not None:
        parser.error("--provenance-file selects pr-code-capture only")
    if args.listing_kind and not (
        args.command == "pr-code" or args.command == "pr-list" and assessment == "code"
    ):
        parser.error("--listing-kind selects a current code assessment")
    if (
        args.command in ("pr-documents", "pr-list")
        and (args.command != "pr-list" or assessment == "documents")
        and args.kind
        and any(kind in ("pr_commits", "pr_files") for kind in args.kind)
    ):
        parser.error("document assessments require document --kind values")
    document_filters_supplied = any(
        value is not None
        for value in (
            args.document_state,
            args.document_author,
            args.resolved,
            args.outdated,
            args.document_filters,
        )
    )
    if document_filters_supplied and (
        args.command in ("pr-code", "pr-code-capture")
        or args.command == "pr-list"
        and assessment == "code"
    ):
        parser.error("document metadata filters require a documents assessment")
    if args.command == "pr-code" and (
        args.kind
        or args.thread_id is not None
        or args.path is not None
        or args.commit is not None
        or args.require_text is not None
    ):
        parser.error(
            "document kind/thread/path/commit/text options require pr-documents"
        )
    if args.command == "pr-code-capture" and (
        args.thread_id is not None
        or args.path is not None
        or args.commit is not None
        or args.require_text is not None
    ):
        parser.error("captured code listing does not accept document selectors")
    if args.command == "pr-documents" and args.require_git is not None:
        parser.error("--require-git selects PR code metadata assessment only")
    if args.command != "pr-list" and any(
        value is not None
        for value in (
            args.parent_id,
            args.state,
            args.draft,
            args.author,
            args.text_literal,
        )
    ):
        parser.error("parent/metadata filters require repository pr-list")
    if args.command == "pr-list" and args.thread_id is not None:
        parser.error("--thread-id selects one PR through pr-documents")
    if (
        args.command == "pr-list"
        and assessment == "documents"
        and args.require_git is not None
    ):
        parser.error("--require-git selects code assessment only")
    if (
        args.command == "pr-list"
        and assessment == "code"
        and (
            args.kind
            or args.require_text is not None
            or args.path is not None
            or args.commit is not None
        )
    ):
        parser.error("document kinds/text options select documents assessment only")
    try:
        from repo_catalog.application.pr_assessment import PRQueryService
        from repo_catalog.domain.p1_context import ResourceKey, canonical
        from repo_catalog.domain.query_contracts import PageRequest
        from repo_catalog.domain.shared_values import OID

        metadata_filters = (
            {}
            if args.document_filters is None
            else read_document(args.document_filters)
        )
        if type(metadata_filters) is not dict:
            raise ValueError("document filters require an object")
        for field, value in (
            ("state", args.document_state),
            ("author", args.document_author),
            ("resolved", args.resolved),
            ("outdated", args.outdated),
        ):
            if value is not None:
                if field in metadata_filters and metadata_filters[field] != value:
                    raise ValueError("conflicting document filter options")
                metadata_filters[field] = value

        service = PRQueryService(
            args.catalog, mode=args.mode, read_limits=read_limits(args)
        )
        resource = ResourceKey(
            args.service_instance,
            "repository" if args.command == "pr-list" else "pull_request",
            args.provider_resource_id,
        )
        kwargs = {
            "page": PageRequest(
                limit=args.limit, cursor=args.cursor, expected_token=args.expected_token
            ),
            "max_work": args.max_work,
            "max_bytes": args.max_bytes,
        }
        if args.command == "pr-code-capture":
            original = read_document(args.provenance_file)
            if type(original) is dict:
                original = canonical(original)
            if type(original) is not str:
                raise ValueError(
                    "original collection provenance requires a JSON string or object"
                )
            result = service.get_pr_code_capture(
                resource,
                args.kind[0],
                original,
                require_git=False if args.require_git is None else args.require_git,
                **kwargs,
            )
        elif args.command == "pr-code":
            if args.listing_kind is not None:
                kwargs["listing_kinds"] = tuple(args.listing_kind)
            result = service.get_pr_code(
                resource,
                require_git=True if args.require_git is None else args.require_git,
                **kwargs,
            )
        elif args.command == "pr-documents":
            if args.kind is not None:
                kwargs["kinds"] = tuple(args.kind)
            result = service.get_pr_documents(
                resource,
                require_text=True if args.require_text is None else args.require_text,
                thread_id=args.thread_id,
                path=args.path,
                commit=None
                if args.commit is None
                else OID(args.object_format, args.commit),
                metadata_filters=metadata_filters or None,
                **kwargs,
            )
        else:
            if args.listing_kind is not None:
                kwargs["listing_kinds"] = tuple(args.listing_kind)
            if args.kind is not None:
                kwargs["kinds"] = tuple(args.kind)
            result = service.list_pr_assessments(
                resource,
                parents=None
                if args.parent_id is None
                else tuple(
                    ResourceKey(args.service_instance, "pull_request", value)
                    for value in args.parent_id
                ),
                assessment=assessment,
                require_git=True if args.require_git is None else args.require_git,
                require_text=True if args.require_text is None else args.require_text,
                state=args.state,
                draft=args.draft,
                author=args.author,
                text_literal=args.text_literal,
                path=args.path,
                commit=None
                if args.commit is None
                else OID(args.object_format, args.commit),
                metadata_filters=metadata_filters or None,
                **kwargs,
            )
        emit(result.to_dict())
        return 0
    except Exception as error:
        if not isinstance(
            error, (ValueError, OSError, KeyError, TypeError)
        ) and not hasattr(error, "code"):
            raise
        return failure(error)


if __name__ == "__main__":
    raise SystemExit(main())
