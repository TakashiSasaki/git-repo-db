"""Opt-in approved local Git -> Core acquisition with original Operational intent.

No initializer, network transport, automatic approval or default CLI activation.
The caller supplies an already configured/approved Access selection, an existing
catalog, and an explicit expected Git object format. Every invocation needs fresh
local executor activation, including retries of a durably budgeted request.
"""

from __future__ import annotations

import copy
from contextlib import ExitStack, closing
from dataclasses import replace
from pathlib import Path

from repo_catalog.adapters.filesystem.access_executor import (
    LocalDirectoryExecutor,
    _path,
)
from repo_catalog.adapters.git.access_native import AccessGitSource
from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.application.access_workflow import AccessWorkflow, Reviewer
from repo_catalog.application.acquisition import GitAcquisition
from repo_catalog.domain.access_registry import AccessRegistryError
from repo_catalog.domain.access_workflow import AccessSelection, review_document
from repo_catalog.domain.acquisition import (
    GitAcquisitionReport,
    GitNativeAcquisitionRequest,
)
from repo_catalog.domain.native_acquisition import (
    native_request_intent,
    ref_input_processing,
    without_ref_inputs,
)
from repo_catalog.domain.p1_coordination import (
    CoordinationError,
    NotesLimits,
    RequestIdentity,
)
from repo_catalog.domain.p1_core import CoreFailure, Provenance, RepositoryClaim, encode
from repo_catalog.domain.ports.access_connections import AccessConfiguration
from repo_catalog.domain.ports.notes import request_scope


class AccessGitAcquisition:
    """One explicitly approved local operation. Application-owned adapters only."""

    def __init__(self, store: AccessConfiguration, catalog: str | Path):
        self.store = store
        self.catalog = Path(catalog)

    def acquire(
        self,
        selection: AccessSelection,
        request: GitNativeAcquisitionRequest,
        *,
        object_format: str,
        reviewer: Reviewer,
        new_request: bool = False,
        request_identity: RequestIdentity | None = None,
        work_limits: dict[str, int] | None = None,
        note_limits: NotesLimits | None = None,
        metadata_bytes: int = 64 * 1024 * 1024,
        cancelled=lambda: False,
    ) -> GitAcquisitionReport:
        selection = AccessWorkflow._selection(selection)
        native_request_intent(without_ref_inputs(request))
        has_ref_inputs = request.notes is not None and bool(request.notes.ref_inputs)
        if not has_ref_inputs:
            request = copy.deepcopy(request)
            intent = native_request_intent(request)
        if type(metadata_bytes) is not int or not 0 < metadata_bytes < 2**63:
            raise AccessRegistryError(
                "LIMIT", "positive finite metadata byte bound required"
            )
        if selection.repository_uuidv4 != request.repository_uuidv4:
            raise AccessRegistryError(
                "REPOSITORY_SCOPE", "request differs from reviewed repository"
            )
        if object_format not in ("sha1", "sha256"):
            raise AccessRegistryError("NATIVE_FORMAT", "expected sha1/sha256 required")
        if type(new_request) is not bool:
            raise AccessRegistryError("TYPE", "explicit new-request boolean required")
        req = request_identity or RequestIdentity(
            request.capture_origin_uuidv4, request.capture_uuidv4
        )
        req = RequestIdentity(*req.values())
        if not (self.catalog / "operational.sqlite3").is_file():
            raise CoordinationError(
                "CONTINUATION_UNAVAILABLE",
                "request",
                "durable Operational store required",
            )
        with (
            closing(GitCore(self.catalog / "core.sqlite3")) as core,
            ExitStack() as preparation,
        ):

            def catalog_guard():
                core.ensure_available()
                if cancelled():
                    raise CoreFailure(
                        "CANCELLED", "access-git", "local request cancelled"
                    )

            catalog_guard()
            catalog_seed, instance = core.catalog_identity()
            early = None
            if has_ref_inputs:
                # Existing approval must exist before spending request work. Only
                # settings are read here; executor activation still requires review.
                approved = self.store.current_grant(
                    selection.repository_uuidv4,
                    selection.scope_uuidv4,
                    **selection.options,
                )
                source_path = _path(approved.plan.assignment.locator_text)
                source_scope = encode(
                    ["local-git", source_path.encode().hex(), object_format]
                )
                scope = request_scope(
                    request.repository_uuidv4,
                    instance,
                    request.source_attribution,
                    source_scope,
                )
                ledger = preparation.enter_context(
                    closing(
                        OperationalAcquisitionLedger(
                            self.catalog / "operational.sqlite3",
                            repository_uuidv4=catalog_seed,
                            catalog_instance_uuidv4=instance,
                        )
                    )
                )
                _, _, early_work, early_progress = ledger.create_budget(
                    scope=scope,
                    request=req,
                    new_request=new_request,
                    work_limits=work_limits,
                    limits=note_limits,
                )
                with ref_input_processing(request.notes.ref_inputs, early_work):
                    request = copy.deepcopy(request)
                intent = native_request_intent(request, early_work)
                early = (approved.plan, early_work, early_progress)
            with AccessWorkflow(self.store) as workflow:

                def confirm(document):
                    # The caller sees the acquisition intent as well as the exact
                    # Access route. Its mutable display copy cannot alter intent.
                    with ref_input_processing(
                        request.notes.ref_inputs if has_ref_inputs else (),
                        early[1] if early is not None else None,
                    ):
                        return reviewer(
                            copy.deepcopy(
                                {
                                    **document,
                                    "operation": "acquire-local-git",
                                    "catalog": str(self.catalog),
                                    "catalog_seed": catalog_seed,
                                    "catalog_instance_uuidv4": instance,
                                    "request": intent,
                                    "expected_object_format": object_format,
                                    "request_identity": list(req.values()),
                                    "new_request": new_request,
                                }
                            )
                        )

                token = workflow.activate(selection, LocalDirectoryExecutor(), confirm)

                def acquire_reviewed(descriptor, plan, check_binding):
                    grant = self.store.current_grant(
                        plan.repository_uuidv4,
                        plan.assignment.scope_uuidv4,
                        assignment=plan.assignment,
                        registration=plan.registration,
                    )
                    if grant.plan != plan:
                        raise AccessRegistryError(
                            "GRANT_CHANGED", "activated plan changed"
                        )

                    def guard():
                        catalog_guard()
                        check_binding()
                        current = self.store.current_grant(
                            plan.repository_uuidv4,
                            plan.assignment.scope_uuidv4,
                            assignment=plan.assignment,
                            registration=plan.registration,
                        )
                        if current != grant:
                            raise AccessRegistryError(
                                "GRANT_CHANGED", "local consent changed"
                            )
                        catalog_guard()

                    guard()
                    source_path = _path(plan.assignment.locator_text)
                    source_scope = encode(
                        ["local-git", source_path.encode().hex(), object_format]
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
                        self.catalog / "operational.sqlite3",
                        repository_uuidv4=catalog_seed,
                        catalog_instance_uuidv4=instance,
                    ) as ledger:
                        if early is None:
                            _, _, work, progress = ledger.create_budget(
                                scope=scope,
                                request=req,
                                new_request=new_request,
                                work_limits=work_limits,
                                limits=note_limits,
                            )
                        else:
                            if early[0] != plan:
                                raise AccessRegistryError(
                                    "GRANT_CHANGED", "preparation plan changed"
                                )
                            _, work, progress = early
                        frozen = {
                            "plan": review_document(plan),
                            "object_format": object_format,
                            "request": intent,
                        }
                        coordinate = encode(
                            [
                                "a4-access-plan",
                                request.capture_origin_uuidv4,
                                request.capture_uuidv4,
                            ]
                        )
                        with ref_input_processing(
                            request.notes.ref_inputs if has_ref_inputs else (), work
                        ):
                            if progress.save_once(coordinate, frozen) != frozen:
                                raise CoreFailure(
                                    "INCOMPATIBLE_REPLAY",
                                    "access-plan",
                                    "original request cannot change its route or intent",
                                )

                        def bind_identity(identity):
                            coordinate = encode(
                                [
                                    "a4-access-source",
                                    request.capture_origin_uuidv4,
                                    request.capture_uuidv4,
                                ]
                            )
                            if progress.save_once(coordinate, identity) != identity:
                                raise CoreFailure(
                                    "INCOMPATIBLE_REPLAY",
                                    "access-source",
                                    "original physical source changed; explicit new request required",
                                )

                        with closing(
                            AccessGitSource(
                                descriptor,
                                source_path,
                                object_format=object_format,
                                work=work,
                                guard=guard,
                                bind_identity=bind_identity,
                                metadata_bytes=metadata_bytes,
                            )
                        ) as source:
                            observed_path = RepositoryClaim(
                                request.repository_uuidv4,
                                "git_path",
                                source_path,
                                Provenance(
                                    request.source_attribution,
                                    encode(
                                        [
                                            request.capture_origin_uuidv4,
                                            request.capture_uuidv4,
                                        ]
                                    ),
                                    "actual-local-git-path",
                                    "access-local-git",
                                    "1",
                                ),
                            )
                            local_request = replace(
                                request,
                                repository_claims=(
                                    *request.repository_claims,
                                    observed_path,
                                ),
                            )
                            report = GitAcquisition(core).acquire_from_native(
                                source,
                                local_request,
                                work=work,
                                progress=progress,
                            )
                        # Committed prefixes remain durable on later stop/revocation.
                        # Never report a completed result after a detected stop.
                        guard()
                        return report

                return workflow.dispatch_reviewed_once(
                    token, acquire_reviewed, guard=catalog_guard
                )
