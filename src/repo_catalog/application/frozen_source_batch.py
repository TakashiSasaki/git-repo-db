"""Execute an immutable ordered Source plan using one cumulative request budget."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.adapters.sqlite.catalog_runtime import catalog_completion
from repo_catalog.application.frozen_acquisition_plan import FrozenAcquisitionPlan
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.p1_coordination import NotesLimits, RequestIdentity
from repo_catalog.domain.shared_values import OID, RepositoryFailure, uuid4_value

_SCOPE = ["frozen-source-batch", 1]
_GITHUB = {"github_inventory", "github"}
_NATIVE = {"git", "local_git", "manual_git"}
_REMOTE = {"remote_git", "git_remote"}
_HTTP_SETTINGS = {
    "operation",
    "service_instance_uuidv4",
    "owner",
    "repository",
    "rest_base_url",
    "graphql_url",
    "max_pages",
    "response_bytes",
    "sections",
    "include_repositories",
}


@dataclass(frozen=True)
class BatchAcquisitionReport:
    request_identity: RequestIdentity
    attempt_uuidv4: str
    status: str
    source_results: tuple[dict, ...]
    usage: dict[str, int]


def _list(value, name):
    if type(value) is not list:
        raise ValueError(f"{name} requires an explicit array")
    return value


def _oids(value):
    return tuple(
        OID(*_list(item, "object coordinate"))
        for item in _list(value, "object coordinates")
    )


def _native_settings(settings):
    if set(settings) - {"path_hex", "metadata_bytes", "request"}:
        raise ValueError("Unknown native Source setting")
    path = settings.get("path_hex")
    if type(path) is not str:
        raise ValueError("Native Source requires a lossless path_hex")
    raw = bytes.fromhex(path)
    if not raw or b"\0" in raw or raw.hex() != path:
        raise ValueError("Canonical nonempty native Source path required")
    limit = settings.get("metadata_bytes", 64 * 1024 * 1024)
    if type(limit) is not int or not 0 < limit < 2**63:
        raise ValueError("Positive finite native metadata bound required")
    return Path(os.fsdecode(raw)), limit, _native_request(settings.get("request"))


def _native_request(values):
    from repo_catalog.domain.git_acquisition import (
        GitNativeAcquisitionRequest,
        NotesAcquisitionSpec,
    )

    if type(values) is not dict or set(values) - {
        "repository_uuidv4",
        "capture_origin_uuidv4",
        "capture_uuidv4",
        "source_attribution",
        "observed_at_us",
        "select_object_oids",
        "retain_bytes",
        "retain_object_oids",
        "include_refs",
        "ref_prefixes",
        "nominated_ref_names_hex",
        "traverse_structural_targets",
        "nominal_missing_object_oids",
        "notes",
    }:
        raise ValueError("Exact native Source request settings required")
    values = dict(values)
    for name in ("select_object_oids", "nominal_missing_object_oids"):
        if name in values:
            values[name] = _oids(values[name])
    if values.get("retain_object_oids") is not None:
        values["retain_object_oids"] = frozenset(_oids(values["retain_object_oids"]))
    if "ref_prefixes" in values:
        prefixes = _list(values["ref_prefixes"], "ref prefixes")
        if any(type(item) is not str for item in prefixes):
            raise ValueError("Text ref prefixes required")
        values["ref_prefixes"] = tuple(prefixes)
    if "nominated_ref_names_hex" in values:
        values["nominated_ref_names"] = tuple(
            bytes.fromhex(item)
            for item in _list(values.pop("nominated_ref_names_hex"), "ref names")
        )
    for name in ("retain_bytes", "include_refs", "traverse_structural_targets"):
        if name in values and type(values[name]) is not bool:
            raise ValueError("Explicit native selection boolean required")
    if values.get("notes") is not None:
        notes = values["notes"]
        if type(notes) is not dict or set(notes) - {
            "discover_notes",
            "nominated_refs",
            "discovery_observation_uuidv4",
            "acquire_inventories",
            "target_object_oids",
            "retain_note_bodies",
        }:
            raise ValueError("Exact native Notes selection required")
        notes = dict(notes)
        for name in ("discover_notes", "acquire_inventories", "retain_note_bodies"):
            if name in notes and type(notes[name]) is not bool:
                raise ValueError("Explicit Notes selection boolean required")
        if "nominated_refs" in notes:
            refs = _list(notes["nominated_refs"], "Notes refs")
            if any(type(item) is not str for item in refs):
                raise ValueError("Text Notes refs required")
            notes["nominated_refs"] = tuple(refs)
        if "target_object_oids" in notes:
            notes["target_object_oids"] = _oids(notes["target_object_oids"])
        values["notes"] = NotesAcquisitionSpec(**notes)
    return GitNativeAcquisitionRequest(**values)


def _remote_settings(settings, reference):
    from repo_catalog.adapters.git.remote import _location

    if set(settings) - {
        "request",
        "locator",
        "object_format",
        "transfer_bytes",
        "disk_bytes",
        "timeout_seconds",
        "metadata_bytes",
        "username",
        "ssh_username",
        "ssh_known_hosts_file",
        "refspecs",
    }:
        raise ValueError("Unknown or credential-bearing remote Git Source setting")
    if reference is not None and reference["kind"] != "environment":
        raise ValueError(
            "Remote Git Source requires an environment reference or default SSH agent"
        )
    _location(settings.get("locator"))
    if settings.get("object_format") not in {"sha1", "sha256"}:
        raise ValueError("Explicit remote Git object format required")
    return {**settings, "request": _native_request(settings.get("request"))}


def _validate_sources(plan):
    for source in plan["sources"]:
        kind, settings = source["kind"], source["settings"]
        reference = plan["credential_refs"].get(source["source_registration_uuidv4"])
        if kind in _GITHUB:
            if set(settings) - _HTTP_SETTINGS:
                raise ValueError("Unknown or credential-bearing GitHub Source setting")
            if reference is None or reference["kind"] != "environment":
                raise ValueError(
                    "GitHub Source requires an explicit environment credential reference"
                )
            if settings.get("operation", "discover") not in {"discover", "sync"}:
                raise ValueError("GitHub Source requires discover or sync")
            uuid4_value(settings.get("service_instance_uuidv4"))
            if type(settings.get("owner")) is not str or not settings["owner"]:
                raise ValueError("Explicit GitHub owner required")
        elif kind in _NATIVE:
            if reference is not None:
                raise ValueError(
                    "Local native Source does not consume transport credentials"
                )
            _native_settings(settings)
        elif kind in _REMOTE:
            _remote_settings(settings, reference)
        else:
            raise ValueError(f"Unsupported batch Source kind: {kind}")


def _credential_available(source, reference, credentials):
    if source["kind"] not in _GITHUB and reference is None:
        return True
    if reference is None:
        return False
    return bool(
        credentials.get()
        if credentials is not None
        else os.environ.get(reference["name"])
    )


def _execute(
    catalog,
    source,
    reference,
    *,
    request,
    ledger,
    work,
    progress,
    authorization,
    admission,
    client,
    credentials,
    cancelled,
    clock_us,
):
    if not _credential_available(source, reference, credentials):
        raise CatalogError(
            "SOURCE_CREDENTIAL_UNAVAILABLE",
            "Frozen Source credential reference is unavailable",
        )
    if source["kind"] in _GITHUB:
        from repo_catalog.application.provider_fetch import acquire_github_with_budget

        document = {
            "operation": "discover",
            **source["settings"],
            "source_registration_uuidv4": source["source_registration_uuidv4"],
            "request_identity": list(request.values()),
            "new_request": False,
            "token_env_var": reference["name"],
        }
        return acquire_github_with_budget(
            catalog,
            document,
            authorization=authorization,
            admission=admission,
            ledger=ledger,
            work=work,
            progress=progress,
            client=client,
            credentials=credentials,
            cancelled=cancelled,
            clock_us=clock_us,
        )
    if source["kind"] in _REMOTE:
        from repo_catalog.application.remote_git_acquisition import (
            acquire_remote_git_with_budget,
        )

        document = _remote_settings(source["settings"], reference)
        document.update(request_identity=list(request.values()), new_request=False)
        if reference is not None:
            document["token_env_var"] = reference["name"]
        return acquire_remote_git_with_budget(
            catalog,
            document,
            source_registration_uuidv4=source["source_registration_uuidv4"],
            ledger=ledger,
            work=work,
            progress=progress,
            request_identity=request,
            credentials=credentials,
            cancelled=cancelled,
        )
    from repo_catalog.adapters.git.native import GitNativeSource
    from repo_catalog.application.git_acquisition import GitAcquisition

    path, limit, native_request = _native_settings(source["settings"])
    # Parent continuation is checked before even the constructor's finite Git
    # format probe. Native acquisition meters its subsequent reads normally.
    ledger.work_ledger.validate_continuation(request, work.attempt_uuidv4)
    work.require("metadata_units", 1)
    try:
        native = GitNativeSource(path, metadata_bytes=limit)
    except BaseException:
        work.abandon("metadata_units")
        raise
    work.charge("metadata_units", 1)
    return GitAcquisition(catalog, operational=ledger).acquire_from_native_with_budget(
        native,
        native_request,
        source_registration_uuidv4=source["source_registration_uuidv4"],
        ledger=ledger,
        work=work,
        progress=progress,
        request_identity=request,
    )


def acquire_batch(
    catalog,
    document,
    *,
    authorization=None,
    admission=None,
    client=None,
    credentials=None,
    cancelled=lambda: False,
    clock_us=None,
):
    """Run genuine source services; resume uses the original frozen ordered plan.

    Successful sources are checkpointed and skipped on resume. Partial sources
    retain their owning service's continuation. One parent attempt/work/progress
    capability is shared by every dispatcher call, with no child requests.
    """
    if type(document) is not dict or set(document) - {
        "request_identity",
        "new_request",
        "sources",
        "credential_refs",
        "work_limits",
    }:
        raise ValueError("Exact batch acquisition document required")
    request = RequestIdentity(*document["request_identity"])
    new_request = document.get("new_request", False)
    limits = document.get("work_limits", {})
    if (
        type(new_request) is not bool
        or type(limits) is not dict
        or set(limits) - set(NotesLimits.work_limits())
        or any(
            type(value) is not int or not 0 <= value < 2**63
            for value in limits.values()
        )
    ):
        raise ValueError(
            "Explicit new-request and finite known cumulative work limits required"
        )
    catalog = Path(catalog)
    if (catalog / "p1-recovery-stop.json").exists():
        raise CatalogError("RECOVERY_REQUIRED", "Catalog is stopped")
    if not (catalog / "operational.sqlite3").is_file():
        raise CatalogError(
            "CONTINUATION_UNAVAILABLE", "Durable Operational store required"
        )
    with OperationalAcquisitionLedger(catalog) as ledger:
        plans = FrozenAcquisitionPlan(ledger)
        # Invalid new plans never create request/progress rows. Existing requests
        # load the original instead of consulting changed registration/settings.
        existing = ledger.db.execute(
            "SELECT 1 FROM acquisition_requests WHERE request_origin_uuidv4=? AND request_uuidv4=?",
            request.values(),
        ).fetchone()
        if existing is None:
            raw = plans._validate(
                document["sources"], document.get("credential_refs", {})
            )
            plan = json.loads(raw)
            _validate_sources(plan)
        else:
            ledger.ensure_request(request, scope=_SCOPE)
            plan = plans.load(request)
            _validate_sources(plan)
        if any(source["kind"] in _GITHUB for source in plan["sources"]):
            if authorization is None:
                raise ValueError("Provider batch requires current Context authority")
            authorization.validate_context(admission)
        if existing is None and not any(
            _credential_available(
                source,
                plan["credential_refs"].get(source["source_registration_uuidv4"]),
                credentials,
            )
            for source in plan["sources"]
        ):
            raise CatalogError(
                "SOURCE_CREDENTIAL_UNAVAILABLE",
                "No selected Source has available credentials",
            )
        _, attempt, work, progress = ledger.create_budget(
            scope=_SCOPE,
            request=request,
            new_request=new_request,
            work_limits=limits,
        )
        plan = plans.freeze(request, plan["sources"], plan["credential_refs"])
        # A concurrent creator may have won the first-plan pin. Recheck that
        # actual frozen plan's dispatch requirements before any source work.
        _validate_sources(plan)
        if any(source["kind"] in _GITHUB for source in plan["sources"]):
            if authorization is None:
                raise ValueError("Provider batch requires current Context authority")
            authorization.validate_context(admission)
        results, halted = [], False
        for source in plan["sources"]:
            ident = source["source_registration_uuidv4"]
            key = ["frozen-source-batch-complete", 1, ident]
            summary = ledger.load_continuation(request, key)
            if summary is not None:
                if summary != {
                    "source_registration_uuidv4": ident,
                    "kind": source["kind"],
                    "status": "complete",
                }:
                    raise CatalogError(
                        "CONTINUATION_UNAVAILABLE",
                        "Invalid completed Source checkpoint",
                    )
                results.append(
                    {**summary, "failure_code": None, "replayed": True, "result": None}
                )
                continue
            result, failure = None, None
            was_cancelled = cancelled()
            if halted or was_cancelled:
                halted = True
                state, failure = (
                    "not_started",
                    "CANCELLED" if was_cancelled else "BATCH_HALTED",
                )
            else:
                try:
                    result = _execute(
                        catalog,
                        source,
                        plan["credential_refs"].get(ident),
                        request=request,
                        ledger=ledger,
                        work=work,
                        progress=progress,
                        authorization=authorization,
                        admission=admission,
                        client=client,
                        credentials=credentials,
                        cancelled=cancelled,
                        clock_us=clock_us,
                    )
                    outcome = getattr(result, "git_report", result)
                    failure = outcome.failure_code
                    state = (
                        "complete"
                        if outcome.status in {"complete", "known_empty"}
                        else "partial"
                    )
                except (RepositoryFailure, CatalogError) as error:
                    if error.code in {
                        "AUTHORITATIVE_CORRUPTION",
                        "RECOVERY_STOP",
                        "RECOVERY_REQUIRED",
                        "CORRUPT",
                        "INTEGRITY",
                    }:
                        raise
                    state, failure = "partial", error.code
                halted = failure in {"BUDGET", "QUERY_BUDGET", "CANCELLED"}
            summary = {
                "source_registration_uuidv4": ident,
                "kind": source["kind"],
                "status": state,
            }
            if state == "complete":
                ledger.save_continuation(request, key, summary)
            results.append(
                {
                    **summary,
                    "failure_code": failure,
                    "replayed": False,
                    "result": result,
                }
            )
        usage = ledger.work_ledger.usage(request)
        with catalog_completion(catalog):
            if (catalog / "p1-recovery-stop.json").exists():
                raise CatalogError("RECOVERY_REQUIRED", "Catalog is stopped")
            return BatchAcquisitionReport(
                request,
                attempt,
                "complete"
                if all(row["status"] == "complete" for row in results)
                else "partial",
                tuple(results),
                usage,
            )
