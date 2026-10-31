"""Explicit local Git acquisition using stored Access approval, never auto-fetch.

python -m repo_catalog.cli.access_acquisition ... --new-request
Reuse the original capture/time/request inputs without --new-request for a retry.
The operator must first approve the Access plan using cli.access_workflow approve.
"""

from __future__ import annotations

import argparse
import json
import sys

from repo_catalog.adapters.sqlite.access_connections import AccessConnections
from repo_catalog.application.access_acquisition import AccessGitAcquisition
from repo_catalog.cli.access_workflow import _confirm
from repo_catalog.domain.access_connections import AssignmentKey
from repo_catalog.domain.access_registry import (
    AccessRegistryError,
    ScopeLocatorRegistration,
)
from repo_catalog.domain.access_workflow import AccessSelection
from repo_catalog.domain.acquisition import (
    AcquisitionError,
    GitNativeAcquisitionRequest,
    NotesAcquisitionSpec,
)
from repo_catalog.domain.p1_coordination import (
    CoordinationError,
    NotesLimits,
    RequestIdentity,
)
from repo_catalog.domain.p1_core import OID, CoreFailure


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    for name in (
        "access-db",
        "catalog",
        "repository",
        "scope",
        "capture-origin",
        "capture",
        "source-attribution",
    ):
        result.add_argument("--" + name, required=True)
    result.add_argument("--observed-at-us", type=int, required=True)
    result.add_argument("--object-format", choices=("sha1", "sha256"), required=True)
    result.add_argument("--object-oid", action="append", default=[])
    result.add_argument("--metadata-only", action="store_true")
    result.add_argument("--no-refs", action="store_true")
    result.add_argument("--notes", action="store_true")
    result.add_argument("--note-target", action="append", default=[])
    result.add_argument("--new-request", action="store_true")
    result.add_argument("--request-origin")
    result.add_argument("--request")
    result.add_argument("--locator")
    result.add_argument("--profile")
    result.add_argument("--scope-uri")
    result.add_argument("--registered-at-us", type=int)
    result.add_argument("--max-object-bytes", type=int, default=64 * 1024 * 1024)
    for unit, default in NotesLimits.work_limits().items():
        result.add_argument(
            "--max-" + unit.replace("_", "-"), type=int, default=default
        )
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser()
    args = arguments.parse_args(argv)
    for left, right in (
        (args.locator, args.profile),
        (args.scope_uri, args.registered_at_us),
        (args.request_origin, args.request),
    ):
        if (left is None) != (right is None):
            arguments.error(
                "paired explicit selection/request arguments are required together"
            )
    try:
        if not sys.stdin.isatty() or not sys.stderr.isatty():
            raise AccessRegistryError(
                "LOCAL_TTY_REQUIRED", "interactive local terminal required"
            )
        selection = AccessSelection(
            args.repository,
            args.scope,
            None
            if args.locator is None
            else AssignmentKey(args.scope, args.locator, args.profile),
            None
            if args.scope_uri is None
            else ScopeLocatorRegistration(
                args.scope, args.registered_at_us, args.scope_uri
            ),
        )
        notes = None
        if args.notes or args.note_target:
            notes = NotesAcquisitionSpec(
                discover_notes=True,
                acquire_inventories=True,
                target_object_oids=tuple(
                    OID(args.object_format, object_oid)
                    for object_oid in args.note_target
                ),
                retain_note_bodies=not args.metadata_only,
            )
        request = GitNativeAcquisitionRequest(
            args.repository,
            args.capture_origin,
            args.capture,
            args.source_attribution,
            args.observed_at_us,
            select_object_oids=tuple(
                OID(args.object_format, object_oid) for object_oid in args.object_oid
            ),
            include_refs=not args.no_refs,
            retain_bytes=not args.metadata_only,
            notes=notes,
        )
        with AccessConnections(args.access_db) as store:
            report = AccessGitAcquisition(store, args.catalog).acquire(
                selection,
                request,
                object_format=args.object_format,
                reviewer=_confirm,
                new_request=args.new_request,
                request_identity=None
                if args.request is None
                else RequestIdentity(args.request_origin, args.request),
                metadata_bytes=args.max_object_bytes,
                work_limits={
                    unit: getattr(args, "max_" + unit)
                    for unit in NotesLimits.work_limits()
                },
            )
        print(
            json.dumps(
                {
                    "status": report.status,
                    "git_acquired": True,
                    "repository_uuidv4": report.repository_uuidv4,
                    "capture_origin_uuidv4": report.capture_origin_uuidv4,
                    "capture_uuidv4": report.capture_uuidv4,
                    "retained_objects": [
                        list(object_oid.key) for object_oid in report.retained_objects
                    ],
                    "nominal_missing_objects": [
                        list(object_oid.key)
                        for object_oid in report.nominal_missing_objects
                    ],
                    "retained_notes_count": len(
                        {
                            item.note
                            for item in report.ref_note_acquisitions
                            if item.body_retained and item.note is not None
                        }
                    ),
                    "failure_code": report.failure_code,
                },
                sort_keys=True,
            )
        )
        return 0
    except (
        AccessRegistryError,
        CoreFailure,
        CoordinationError,
        AcquisitionError,
    ) as error:
        print(json.dumps({"status": "error", "code": error.code}), file=sys.stderr)
        return 2
    except (OSError, EOFError, KeyboardInterrupt):
        print('{"status":"error","code":"LOCAL_OPERATION_FAILED"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
