"""Opt-in Core Query CLI, extended by installed Context/Search capabilities (`python -m repo_catalog.cli.production_query`).

Isolated from `repo_catalog.cli.main` (which remains the unchanged Schema 21 CLI).
Outputs deterministic canonical JSON to stdout and structured JSON error
diagnostics to stderr with non-zero exit codes.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Sequence
from pathlib import Path

from repo_catalog.application.core_query import CoreQueryService
from repo_catalog.domain.core_query import ref_projection_json
from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.p1_core import OID, CoreFailure
from repo_catalog.domain.query_contracts import (
    PageRequest,
    QueryError,
    canonical_json,
)


def _features():
    """Load the explicit optional composition only when its code is installed."""
    name = "repo_catalog.cli.query_features"
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as error:
        if error.name != name:
            raise
        return None


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
        description="Opt-in authoritative Core Query CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # status
    p_status = sub.add_parser("status", help="Inspect catalog mode and snapshot token")
    _add_common_args(p_status)

    # git-object
    p_gobj = sub.add_parser("git-object", help="Query a single Git object by OID")
    _add_common_args(p_gobj)
    p_gobj.add_argument("--format", required=True, choices=("sha1", "sha256"))
    p_gobj.add_argument("--object-oid", required=True)
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

    p_refobs = sub.add_parser(
        "ref-observations", help="Page original ref observations and all result Claims"
    )
    _add_common_args(p_refobs)
    _add_page_args(p_refobs)

    features = _features()
    if features is not None:
        features.add_commands(sub, _add_common_args, _add_page_args)

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
        features = _features()
        service = (
            CoreQueryService(args.catalog, mode=args.mode)
            if features is None
            else features.query_service(args.catalog, mode=args.mode)
        )
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
        elif cmd == "ref-observations":
            page = service.list_ref_observations(_page_from_args(args))
            payload = {
                "items": [ref_projection_json(item) for item in page.items],
                "has_more": page.has_more,
                "next_cursor": page.next_cursor,
                "snapshot_token": page.snapshot_token,
            }
        elif cmd == "git-object":
            object_oid = OID(args.format, args.object_oid)
            view = service.get_git_object(object_oid, include_bytes=args.include_bytes)
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
        else:
            features = _features()
            if features is None:
                raise QueryError("UNKNOWN_COMMAND", "cli", str(cmd))
            payload = features.query_payload(service, args, _page_from_args)

        sys.stdout.write(canonical_json(payload) + "\n")
        return 0
    except Exception as error:
        context_module = sys.modules.get("repo_catalog.domain.production_context")
        context_error = getattr(context_module, "ContextError", ())
        if not isinstance(error, (QueryError, CoreFailure, CoordinationError)) and not (
            context_error and isinstance(error, context_error)
        ):
            raise
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
