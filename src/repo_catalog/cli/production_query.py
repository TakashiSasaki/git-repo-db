"""Opt-in P6 production query and Search CLI (`python -m repo_catalog.cli.production_query`).

Isolated from `repo_catalog.cli.main` (which remains the unchanged Schema 21 CLI).
Outputs deterministic canonical JSON to stdout and structured JSON error
diagnostics to stderr with non-zero exit codes.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.p1_core import OID, CoreFailure
from repo_catalog.domain.production_context import ContextError
from repo_catalog.domain.production_query import (
    SEARCH_PROJECTION_KINDS,
    PageRequest,
    QueryError,
    SearchQuery,
    canonical_json,
)


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--catalog",
        required=True,
        type=Path,
        help="Path to the catalog directory",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "core_only", "context_only", "paired"),
        default="auto",
        help="Catalog topology mode (default: auto)",
    )


def _add_page_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--limit", type=int, default=50, help="Page size limit")
    parser.add_argument("--cursor", default=None, help="Pagination cursor")
    parser.add_argument(
        "--expected-token",
        default=None,
        help="Expected snapshot fence token",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repo_catalog.cli.production_query",
        description="Opt-in P6 production authoritative query and Search CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # status
    p_status = sub.add_parser("status", help="Inspect catalog mode and snapshot token")
    _add_common_args(p_status)

    # git-object
    p_gobj = sub.add_parser("git-object", help="Query a single Git object by OID")
    _add_common_args(p_gobj)
    p_gobj.add_argument("--format", required=True, choices=("sha1", "sha256"))
    p_gobj.add_argument("--oid", required=True)
    p_gobj.add_argument("--include-bytes", action="store_true")

    # git-objects
    p_gobjs = sub.add_parser("git-objects", help="List Git objects with pagination")
    _add_common_args(p_gobjs)
    p_gobjs.add_argument("--format", default=None, choices=("sha1", "sha256"))
    p_gobjs.add_argument("--native-type", default=None)
    _add_page_args(p_gobjs)

    # git-observations
    p_gobs = sub.add_parser(
        "git-observations", help="List Git observations with pagination"
    )
    _add_common_args(p_gobs)
    p_gobs.add_argument("--kind", default=None)
    p_gobs.add_argument("--ref-prefix", default=None)
    _add_page_args(p_gobs)

    # notes
    p_notes = sub.add_parser("notes", help="List Notes captures with pagination")
    _add_common_args(p_notes)
    p_notes.add_argument("--notes-ref", default=None)
    _add_page_args(p_notes)

    # context-resource
    p_cres = sub.add_parser(
        "context-resource", help="Query a single Context resource by ResourceKey"
    )
    _add_common_args(p_cres)
    p_cres.add_argument("--service", required=True)
    p_cres.add_argument("--kind", required=True)
    p_cres.add_argument("--id", required=True)

    # context-resources
    p_cress = sub.add_parser(
        "context-resources", help="List Context resources with pagination"
    )
    _add_common_args(p_cress)
    p_cress.add_argument("--service", default=None)
    p_cress.add_argument("--kind", default=None)
    p_cress.add_argument("--repository", default=None)
    _add_page_args(p_cress)

    # paired-resource
    p_pres = sub.add_parser(
        "paired-resource",
        help="Query a paired Context resource with Core OID resolution",
    )
    _add_common_args(p_pres)
    p_pres.add_argument("--service", required=True)
    p_pres.add_argument("--kind", required=True)
    p_pres.add_argument("--id", required=True)
    p_pres.add_argument("--include-core-bytes", action="store_true")

    # paired-resources
    p_press = sub.add_parser(
        "paired-resources",
        help="List paired Context resources with Core OID resolution",
    )
    _add_common_args(p_press)
    p_press.add_argument("--kind", default=None)
    p_press.add_argument("--repository", default=None)
    _add_page_args(p_press)

    # search-rebuild
    p_sreb = sub.add_parser(
        "search-rebuild",
        help="Rebuild derivative search.sqlite3 projections from pinned authority",
    )
    _add_common_args(p_sreb)
    p_sreb.add_argument(
        "--kinds",
        default=",".join(SEARCH_PROJECTION_KINDS),
        help="Comma-separated projection kinds",
    )

    # search
    p_search = sub.add_parser(
        "search",
        help="Search across projection kinds with automatic authority_scan fallback",
    )
    _add_common_args(p_search)
    p_search.add_argument("--query", required=True)
    p_search.add_argument(
        "--kinds",
        default=",".join(SEARCH_PROJECTION_KINDS),
        help="Comma-separated projection kinds",
    )
    _add_page_args(p_search)

    return parser


def _page_from_args(args: argparse.Namespace) -> PageRequest:
    return PageRequest(
        limit=args.limit,
        cursor=args.cursor,
        expected_token=args.expected_token,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        service = ProductionQueryService(args.catalog, mode=args.mode)
        cmd = args.command

        if cmd == "status":
            mode = service.detect_mode()
            token = service.snapshot_token()
            payload = {
                "catalog_instance_uuidv4": token.catalog_instance_uuidv4,
                "context_sha256": token.context_sha256,
                "core_sha256": token.core_sha256,
                "mode": mode,
                "repository_uuidv4": token.repository_uuidv4,
                "snapshot_token": token.encode(),
            }
        elif cmd == "git-object":
            oid = OID(args.format, args.oid)
            view = service.get_git_object(oid, include_bytes=args.include_bytes)
            payload = view.to_dict()
        elif cmd == "git-objects":
            page = service.list_git_objects(
                _page_from_args(args),
                object_format=args.format,
                native_type=args.native_type,
            )
            payload = {
                "has_more": page.has_more,
                "items": [item.to_dict() for item in page.items],
                "next_cursor": page.next_cursor,
                "snapshot_token": page.snapshot_token,
                "total_count": page.total_count,
            }
        elif cmd == "git-observations":
            page = service.list_git_observations(
                _page_from_args(args),
                observation_kind=args.kind,
                ref_prefix=args.ref_prefix,
            )
            payload = {
                "has_more": page.has_more,
                "items": [item.to_dict() for item in page.items],
                "next_cursor": page.next_cursor,
                "snapshot_token": page.snapshot_token,
                "total_count": page.total_count,
            }
        elif cmd == "notes":
            page = service.list_notes_captures(
                _page_from_args(args),
                notes_ref=args.notes_ref,
            )
            payload = {
                "has_more": page.has_more,
                "items": [item.to_dict() for item in page.items],
                "next_cursor": page.next_cursor,
                "snapshot_token": page.snapshot_token,
                "total_count": page.total_count,
            }
        elif cmd == "context-resource":
            rkey = ResourceKey(args.service, args.kind, args.id)
            view = service.get_context_resource(rkey, include_text=True)
            payload = view.to_dict()
        elif cmd == "context-resources":
            page = service.list_context_resources(
                _page_from_args(args),
                service_instance_uuidv4=args.service,
                resource_kind=args.kind,
                repository_uuidv4=args.repository,
            )
            payload = {
                "has_more": page.has_more,
                "items": [item.to_dict() for item in page.items],
                "next_cursor": page.next_cursor,
                "snapshot_token": page.snapshot_token,
                "total_count": page.total_count,
            }
        elif cmd == "paired-resource":
            rkey = ResourceKey(args.service, args.kind, args.id)
            view = service.get_paired_resource(
                rkey,
                include_text=True,
                include_core_bytes=args.include_core_bytes,
            )
            payload = view.to_dict()
        elif cmd == "paired-resources":
            page = service.list_paired_resources(
                _page_from_args(args),
                resource_kind=args.kind,
                repository_uuidv4=args.repository,
            )
            payload = {
                "has_more": page.has_more,
                "items": [item.to_dict() for item in page.items],
                "next_cursor": page.next_cursor,
                "snapshot_token": page.snapshot_token,
                "total_count": page.total_count,
            }
        elif cmd == "search-rebuild":
            kinds = tuple(k.strip() for k in args.kinds.split(",") if k.strip())
            counts = service.rebuild_search(kinds)
            token = service.snapshot_token()
            payload = {
                "indexed_counts": counts,
                "snapshot_token": token.encode(),
            }
        elif cmd == "search":
            kinds = tuple(k.strip() for k in args.kinds.split(",") if k.strip())
            resp = service.search(
                SearchQuery(
                    query_text=args.query,
                    projection_kinds=kinds,
                    limit=args.limit,
                    cursor=args.cursor,
                    expected_token=args.expected_token,
                )
            )
            payload = resp.to_dict()
        else:
            raise QueryError("UNKNOWN_COMMAND", "cli", str(cmd))

        sys.stdout.write(canonical_json(payload) + "\n")
        return 0
    except (QueryError, CoreFailure, ContextError, CoordinationError) as error:
        err_payload = {
            "code": getattr(error, "code", "ERROR"),
            "error_type": type(error).__name__,
            "message": str(error),
            "scope": str(getattr(error, "scope", "unknown")),
        }
        sys.stderr.write(canonical_json(err_payload) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
