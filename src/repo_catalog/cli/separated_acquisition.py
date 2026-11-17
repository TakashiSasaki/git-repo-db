"""Explicit native Git, normalized Provider, paired and remote Provider acquisition."""

import argparse
import sys

from repo_catalog.cli.separated_io import (
    authority,
    decode,
    emit,
    failure,
    read_document,
)


def main(argv=None):
    values = list(sys.argv[1:] if argv is None else argv)
    if values and values[0] == "git":
        from repo_catalog.cli.access_acquisition import main as acquire_git

        return acquire_git(values[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "git",
            "provider",
            "paired",
            "github",
            "git-metadata",
            "git-remote",
            "batch",
        ),
    )
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--authority")
    parser.add_argument("--new-request", action="store_true")
    parser.add_argument("--request-origin")
    parser.add_argument("--request")
    args = parser.parse_args(values)
    if (args.request is None) != (args.request_origin is None):
        parser.error("--request and --request-origin must be supplied together")
    if args.command in ("provider", "paired", "github") and not args.authority:
        parser.error("Context acquisition requires --authority")
    try:
        from repo_catalog.domain.p1_coordination import RequestIdentity

        document = decode(read_document(args.input))
        request = (
            None
            if args.request is None
            else RequestIdentity(args.request_origin, args.request)
        )
        kwargs = {"new_request": args.new_request, "request_identity": request}
        if args.command in ("provider", "paired", "github") or (
            args.command == "batch" and args.authority
        ):
            auth, admission, _ = authority(args.authority, "provider_intake")
        elif args.command == "batch":
            auth, admission = None, None
        if args.command in ("github", "git-remote", "batch"):
            if type(document) is not dict:
                raise ValueError("network request must be a JSON object")
            if request is not None:
                supplied = document.get("request_identity")
                supplied = (
                    list(supplied.values())
                    if isinstance(supplied, RequestIdentity)
                    else supplied
                )
                if supplied is not None and supplied != list(request.values()):
                    raise ValueError(
                        "request identity differs between document and CLI"
                    )
                document["request_identity"] = list(request.values())
            if args.new_request:
                document["new_request"] = True
        if args.command == "batch":
            from repo_catalog.application.frozen_source_batch import acquire_batch

            result = acquire_batch(
                args.catalog, document, authorization=auth, admission=admission
            )
        elif args.command == "provider":
            from repo_catalog.domain.provider_acquisition import ProviderIntakeBatch

            if type(document) is not ProviderIntakeBatch:
                raise ValueError("provider input requires tagged ProviderIntakeBatch")
            if args.new_request or request is not None:
                parser.error(
                    "normalized Provider intake uses its explicit admission budget; request flags apply to Git/paired/network acquisition"
                )
            from repo_catalog.application.provider_acquisition import (
                ProviderAcquisition,
            )

            result = ProviderAcquisition(
                args.catalog,
                operational=args.catalog,
                authorization=auth,
                admission=admission,
            ).admit_batch(document)
        elif args.command == "paired":
            from repo_catalog.application.paired_acquisition import (
                PairedAcquisitionCoordinator,
            )

            if type(document) is not dict or set(document) - {
                "git_input",
                "provider_batch",
            }:
                raise ValueError(
                    "paired input accepts git_input and provider_batch only"
                )
            if not document.get("git_input") and not document.get("provider_batch"):
                raise ValueError("paired input requires actual Git or Provider work")
            result = PairedAcquisitionCoordinator(
                args.catalog, authorization=auth, admission=admission
            ).admit_paired(
                git_input=document.get("git_input"),
                provider_batch=document.get("provider_batch"),
                **kwargs,
            )
        elif args.command == "github":
            from repo_catalog.application.provider_fetch import acquire_github

            result = acquire_github(
                args.catalog, document, authorization=auth, admission=admission
            )
        elif args.command == "git-remote":
            from repo_catalog.application.remote_git_acquisition import (
                acquire_remote_git,
            )

            result = acquire_remote_git(args.catalog, document)
        else:
            from repo_catalog.application.git_acquisition import GitAcquisition
            from repo_catalog.domain.git_acquisition import GitMetadataInput

            if type(document) is not GitMetadataInput:
                raise ValueError("metadata input requires tagged GitMetadataInput")
            result = GitAcquisition(
                args.catalog, operational=args.catalog
            ).acquire_metadata_only(document, **kwargs)
        emit(result)
        return 0
    except Exception as error:
        if not isinstance(
            error, (ValueError, OSError, TypeError, KeyError)
        ) and not hasattr(error, "code"):
            raise
        return failure(error)


if __name__ == "__main__":
    raise SystemExit(main())
