"""Explicit remote Git acquisition with one durable cumulative request budget."""

from __future__ import annotations

import copy
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from repo_catalog.adapters.git.remote import (
    _location,
    fetch_remote,
    validate_remote_transport,
)
from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.application.git_acquisition import GitAcquisition, _open_core
from repo_catalog.domain.git_acquisition import GitNativeAcquisitionRequest
from repo_catalog.domain.native_acquisition import (
    native_request_intent,
    ref_input_processing,
    without_ref_inputs,
)
from repo_catalog.domain.p1_coordination import CoordinationError, RequestIdentity
from repo_catalog.domain.p1_core import CoreFailure, encode
from repo_catalog.domain.ports.notes import request_scope

_DOCUMENT_FIELDS = {
    "request",
    "locator",
    "object_format",
    "request_identity",
    "new_request",
    "work_limits",
    "transfer_bytes",
    "disk_bytes",
    "timeout_seconds",
    "metadata_bytes",
    "token_env_var",
    "username",
    "ssh_username",
    "ssh_identity_file",
    "ssh_known_hosts_file",
    "refspecs",
}
_TRANSPORT_OPTIONS = (
    "transfer_bytes",
    "disk_bytes",
    "timeout_seconds",
    "metadata_bytes",
    "username",
    "ssh_username",
    "ssh_identity_file",
    "ssh_known_hosts_file",
    "refspecs",
)


class _EnvironmentCredential:
    def __init__(self, name):
        self.name = name

    def get(self):
        return os.environ.get(self.name)


@dataclass(frozen=True)
class RemoteGitAcquisitionReport:
    git_report: object
    transfer_body_bytes: int
    request_identity: RequestIdentity


def validate_remote_git_settings(settings):
    """Pure bounded injected transport preflight, before any HTTP or work state."""
    allowed = {"locator", "object_format", "token_env_var", *_TRANSPORT_OPTIONS}
    if type(settings) is not dict or set(settings) - allowed:
        raise CoreFailure(
            "REQUEST", "remote-git", "known injected transport settings required"
        )
    name = settings.get("token_env_var")
    if name is not None and (type(name) is not str or not name or len(name) > 256):
        raise CoreFailure(
            "REMOTE_CREDENTIAL", "git", "credential environment reference required"
        )
    location, _ = validate_remote_transport(
        settings.get("locator"),
        object_format=settings.get("object_format"),
        **{key: settings[key] for key in _TRANSPORT_OPTIONS if key in settings},
    )
    if location.scheme == "ssh" and name is not None:
        raise CoreFailure(
            "REMOTE_CREDENTIAL", "git", "HTTP credential reference cannot authorize SSH"
        )
    return dict(settings)


def acquire_remote_git(catalog, document, *, credentials=None, cancelled=lambda: False):
    """Acquire an explicit HTTPS/SSH source into canonical Git Core.

    Input is a dictionary with ``request`` (GitNativeAcquisitionRequest),
    ``locator`` (credential-free https:// or ssh:// URL), ``object_format``;
    optional request_identity/new_request, finite limits, refspecs, and local
    HTTP/SSH credential references. No Access git-read grant authorizes HTTP
    Provider API work. This directly injected transport is separate from Access.
    """
    if type(document) is not dict or set(document) - _DOCUMENT_FIELDS:
        raise CoreFailure(
            "REQUEST", "remote-git", "explicit bounded request fields required"
        )
    request = document.get("request")
    if type(request) is not GitNativeAcquisitionRequest:
        raise CoreFailure("REQUEST", "remote-git", "typed native request required")
    # Original ref reports need the durable work permit even during copying and
    # intent validation. Preflight only the non-ref portion before opening it.
    native_request_intent(without_ref_inputs(request))
    location = _location(document.get("locator"))
    object_format = document.get("object_format")
    if object_format not in {"sha1", "sha256"}:
        raise CoreFailure("NATIVE_FORMAT", "remote-git", "explicit format required")
    original_request = document.get("request_identity")
    req = (
        original_request
        if type(original_request) is RequestIdentity
        else (
            RequestIdentity(*original_request)
            if original_request is not None
            else RequestIdentity(request.capture_origin_uuidv4, request.capture_uuidv4)
        )
    )
    if type(document.get("new_request", False)) is not bool:
        raise CoreFailure(
            "REQUEST", "remote-git", "explicit new-request boolean required"
        )
    name = document.get("token_env_var")
    if name is not None and (type(name) is not str or not name or len(name) > 256):
        raise CoreFailure(
            "REMOTE_CREDENTIAL", "git", "credential environment reference required"
        )
    if credentials is None and name is not None:
        credentials = _EnvironmentCredential(name)
    catalog = Path(catalog)
    if not (catalog / "operational.sqlite3").is_file():
        raise CoordinationError(
            "CONTINUATION_UNAVAILABLE", "request", "Operational store required"
        )
    with _open_core(catalog) as core:
        seed, instance = core.catalog_identity()

        def guard():
            core.ensure_available()
            if cancelled():
                raise CoreFailure("CANCELLED", "remote-git", "request cancelled")

        guard()
        source_scope = encode(
            [
                "remote-git",
                location.scheme,
                location.hostname,
                location.port,
                location.path,
                object_format,
            ]
        )
        scope = (
            request_scope(
                request.repository_uuidv4,
                instance,
                request.source_attribution,
                source_scope,
            )
            if request.notes is not None
            else [
                "p5-git-native",
                request.repository_uuidv4,
                request.capture_origin_uuidv4,
                request.capture_uuidv4,
            ]
        )
        with OperationalAcquisitionLedger(
            catalog, repository_uuidv4=seed, catalog_instance_uuidv4=instance
        ) as ledger:
            _, _, work, progress = ledger.create_budget(
                scope=scope,
                request=req,
                new_request=document.get("new_request", False),
                work_limits=document.get("work_limits"),
            )
            with ref_input_processing(
                request.notes.ref_inputs if request.notes is not None else (), work
            ):
                request = copy.deepcopy(request)
            intent = native_request_intent(request, work)
            # Local execution options belong only to Operational replay binding.
            # Persist a digest, never secret material or an executable config in Context.
            local_intent = {
                k: v
                for k, v in document.items()
                if k
                not in {
                    "request",
                    "request_identity",
                    "new_request",
                    "work_limits",
                    "transfer_bytes",
                    "disk_bytes",
                    "timeout_seconds",
                    "metadata_bytes",
                }
            }
            frozen = {
                "native": intent,
                "local_transport_sha256": hashlib.sha256(
                    encode(local_intent).encode("ascii")
                ).hexdigest(),
            }
            coordinate = encode(
                [
                    "remote-git-original-intent",
                    request.capture_origin_uuidv4,
                    request.capture_uuidv4,
                ]
            )
            if progress.save_once(coordinate, frozen) != frozen:
                raise CoreFailure(
                    "INCOMPATIBLE_REPLAY", "remote-git", "original request changed"
                )
            options = {
                k: document[k]
                for k in (
                    "transfer_bytes",
                    "disk_bytes",
                    "timeout_seconds",
                    "metadata_bytes",
                    "username",
                    "ssh_username",
                    "ssh_identity_file",
                    "ssh_known_hosts_file",
                    "refspecs",
                )
                if k in document
            }
            with fetch_remote(
                document["locator"],
                object_format=object_format,
                work=work,
                guard=guard,
                credentials=credentials,
                **options,
            ) as source:
                report = GitAcquisition(core).acquire_from_native(
                    source, request, work=work, progress=progress, request_identity=req
                )
                guard()
                return RemoteGitAcquisitionReport(
                    report, source.transfer_body_bytes, req
                )


def acquire_remote_git_with_budget(
    catalog,
    document,
    *,
    source_registration_uuidv4,
    ledger,
    work,
    progress,
    request_identity,
    credentials=None,
    cancelled=lambda: False,
    unit_scope=(),
    source_handler=None,
):
    """Fetch one original Source under an existing cumulative parent request.

    The trusted batch owner supplies the real parent capabilities and explicit
    Source UUID. The document contains the original typed native request and
    injected transport options; it cannot create/reset accounting or select a
    different parent request. Original capture provenance remains caller supplied.
    """
    if source_handler is not None and not callable(source_handler):
        raise CoreFailure(
            "REQUEST", "remote-git", "trusted application source handler required"
        )
    if (
        type(document) is not dict
        or set(document) - _DOCUMENT_FIELDS
        or "work_limits" in document
        or "new_request" in document
        and document["new_request"] is not False
    ):
        raise CoreFailure(
            "REQUEST",
            "remote-git",
            "Source transport inputs without child accounting required",
        )
    request = document.get("request")
    if (
        type(request) is not GitNativeAcquisitionRequest
        or type(request_identity) is not RequestIdentity
    ):
        raise CoreFailure(
            "REQUEST", "remote-git", "typed native request and parent identity required"
        )
    supplied = document.get("request_identity", request_identity)
    try:
        supplied = (
            supplied
            if type(supplied) is RequestIdentity
            else RequestIdentity(*supplied)
        )
    except (ValueError, TypeError):
        raise CoreFailure(
            "REQUEST", "remote-git", "exact parent request identity required"
        ) from None
    if supplied != request_identity:
        raise CoordinationError(
            "REQUEST_SCOPE", "remote-git", "Source cannot replace its parent request"
        )
    native_request_intent(without_ref_inputs(request))
    _location(document.get("locator"))
    object_format = document.get("object_format")
    if object_format not in {"sha1", "sha256"}:
        raise CoreFailure("NATIVE_FORMAT", "remote-git", "explicit format required")
    name = document.get("token_env_var")
    if name is not None and (type(name) is not str or not name or len(name) > 256):
        raise CoreFailure(
            "REMOTE_CREDENTIAL", "git", "credential environment reference required"
        )
    if credentials is None and name is not None:
        credentials = _EnvironmentCredential(name)
    catalog = Path(catalog)
    with _open_core(catalog) as core:
        # This performs real ledger identity, inode/checkpoint, catalog path,
        # request/attempt and Source UUID validation before opening any socket.
        GitAcquisition._validate_native_accounting(
            core,
            work,
            progress,
            None,
            request_identity,
            shared=(source_registration_uuidv4, ledger, unit_scope),
        )

        def guard():
            core.ensure_available()
            ledger.work_ledger.validate_continuation(
                request_identity, work.attempt_uuidv4
            )
            if cancelled():
                raise CoreFailure("CANCELLED", "remote-git", "request cancelled")

        guard()
        with ref_input_processing(
            request.notes.ref_inputs if request.notes is not None else (), work
        ):
            request = copy.deepcopy(request)
        intent = native_request_intent(request, work)
        local_intent = {
            key: value
            for key, value in document.items()
            if key not in {"request", "request_identity", "new_request"}
        }
        frozen = {
            "native": intent,
            "local_transport_sha256": hashlib.sha256(
                encode(local_intent).encode("ascii")
            ).hexdigest(),
        }
        transport_coordinate = encode(
            ["remote-git-source-transport", source_registration_uuidv4]
        )
        transport_intent = {"local_transport_sha256": frozen["local_transport_sha256"]}
        if (
            progress.save_once(transport_coordinate, transport_intent)
            != transport_intent
        ):
            raise CoreFailure(
                "INCOMPATIBLE_REPLAY", "remote-git", "original Source transport changed"
            )
        coordinate = encode(
            ["remote-git-source-intent", source_registration_uuidv4]
            + (["operation", list(unit_scope)] if unit_scope else [])
        )
        if progress.save_once(coordinate, frozen) != frozen:
            raise CoreFailure(
                "INCOMPATIBLE_REPLAY", "remote-git", "original Source intent changed"
            )
        options = {key: document[key] for key in _TRANSPORT_OPTIONS if key in document}
        with fetch_remote(
            document["locator"],
            object_format=object_format,
            work=work,
            guard=guard,
            credentials=credentials,
            **options,
        ) as source:
            if source_handler is not None:
                # The callable is supplied by trusted composition, never by
                # the wire document. All follow-up reads/admission must use
                # the same already validated parent capabilities.
                report = source_handler(source)
            else:
                report = GitAcquisition(
                    core, operational=ledger
                ).acquire_from_native_with_budget(
                    source,
                    request,
                    source_registration_uuidv4=source_registration_uuidv4,
                    ledger=ledger,
                    work=work,
                    progress=progress,
                    request_identity=request_identity,
                    unit_scope=unit_scope,
                )
            guard()
            return RemoteGitAcquisitionReport(
                report, source.transfer_body_bytes, request_identity
            )
