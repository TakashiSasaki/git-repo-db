"""Independent bounded review vectors; no Author fixture or product replacement.

Run with PYTHONPATH=src python probe_contract.py OUTPUT.json from frozen checkout.
The expected canonical profiles are literal stdlib encoders from accepted R03.
This script touches no database and does not grant operational authority.
"""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

from repo_catalog.domain.context_admission import (
    AdmissionBudget, AdmissionRefused, AdmissionSelection, AuthenticatedPrincipal,
    ContextAdmissionService, DependencySet,
)
from repo_catalog.domain.context_wire import decode_context_v5, encode_context_v5
from repo_catalog.domain.exchange import decode_package
from repo_catalog.domain.p1_context import ResourceKey

SERVICE = "fd75221e-32e7-4c7c-8fdd-dd66e55a91fe"
REPOSITORY = "2cd726cf-9f1c-4d9d-acfe-11e7145df18c"
PACKAGE = "27d409ba-3663-40fb-aebd-2617cd3d4e5a"
SECTIONS = (
    "providers repositories resource_repository_relations repository_mapping_dispositions "
    "sources source_repositories source_inventories resources resource_relations "
    "collections text_bodies field_candidates core_references coverage_scopes "
    "coverage_claims coverage_proofs"
).split()
CASES = []


def j(value, *, ascii=True):
    return json.dumps(value, ensure_ascii=ascii, sort_keys=True, separators=(",", ":"), allow_nan=False)


def record(name, check):
    try:
        details = check()
    except Exception as error:
        CASES.append({"name": name, "result": "FAIL", "exception": type(error).__name__, "message": str(error)})
    else:
        CASES.append({"name": name, "result": "PASS", "details": details})


def expect_refusal(fn, expected=None):
    try:
        fn()
    except (ValueError, TypeError) as error:
        code = getattr(error, "code", type(error).__name__)
        assert expected is None or code == expected, (code, expected)
        return {"refusal": code}
    raise AssertionError("accepted invalid input")


def resource(native, kind="x-review"):
    return dict(service_instance_uuidv4=SERVICE, resource_kind=kind,
                provider_resource_id=j(native), identifier_namespace_kind=None,
                identifier_namespace_id=None, document_kind=None,
                provider_document_id=j(native) if kind == "document" else None)


def context(*rows):
    data = {section: [] for section in SECTIONS}
    data["providers"] = [dict(service_instance_uuidv4=SERVICE, provider_kind="review", configuration_json="{}")]
    data["resources"] = list(rows)
    return data


def envelope(ctx=None):
    return dict(format="git-repo-db/adr0031-exchange-v5", package_id=PACKAGE,
                exported_at_us=731, sender_catalog_instance_uuidv4=SERVICE,
                repository_uuidv4=REPOSITORY, selection_scope=dict(
                    include_core=True, include_context=True, include_retained_bytes=True,
                    repository_uuidv4s=None, all_selected=True, max_depth=8,
                    max_units=10000, max_bytes=16777216, max_work=10000000,
                    object_oids=None, notes_refs=None, resource_keys=None, source_uuidv4s=None),
                selection_report={}, core=None, context=ctx, digest_sha256="")


def checksum(data):
    data["digest_sha256"] = hashlib.sha256(j({k:v for k,v in data.items() if k != "digest_sha256"}, ascii=False).encode()).hexdigest()
    return data


def roundtrip(data):
    before = deepcopy(data)
    assert decode_context_v5(encode_context_v5(data)) == before
    assert data == before
    return {"rows": len(data["resources"]), "input_unchanged": True}


def trace_selection(data, expected):
    reached = []
    def observe(frame, event, arg):
        if event == "call" and frame.f_code.co_name == "from_dict" and frame.f_globals.get("__name__") == "repo_catalog.domain.exchange":
            reached.append(frame.f_code.co_firstlineno)
    original = deepcopy(data)
    prior = sys.getprofile()
    sys.setprofile(observe)
    try:
        result = expect_refusal(lambda: decode_package(data), expected)
    finally:
        sys.setprofile(prior)
    assert data == original
    if expected == "DIGEST_MISMATCH":
        assert reached == [], reached
    else:
        assert len(reached) == 1, reached
    return {**result, "actual_selection_constructor_calls": len(reached), "input_unchanged": True}


class Policy:
    """Finite local authority limited to exactly one declared dependency set."""
    def __init__(self, principal, grants):
        self.principal, self.grants, self.calls, self.active, self.epoch = principal, grants, 0, 0, 0

    @contextmanager
    def lease(self, principal, operation, needed):
        self.calls += 1
        if principal is not self.principal or operation != "provider_intake" or not needed.issubset(self.grants):
            raise AdmissionRefused("PERMISSION_DENIED")
        epoch = self.epoch
        policy = self
        class Lease:
            def check_current(self):
                if epoch != policy.epoch or not needed.issubset(policy.grants):
                    raise AdmissionRefused("PERMISSION_DENIED")
        self.active += 1
        try:
            yield Lease()
        finally:
            self.active -= 1


def admission_vectors():
    principal = AuthenticatedPrincipal("independent-review", "single-local-session")
    key = ResourceKey(SERVICE, "x-review", j(["one", []]))
    needed = DependencySet(resources={key}, provider_registrations={SERVICE})
    policy = Policy(principal, needed)
    service = ContextAdmissionService(policy, lambda credential: principal if credential == "local-token" else None)
    foreign = ContextAdmissionService(policy, lambda _: principal)
    selection = AdmissionSelection(resource_keys={key}, repository_uuidv4s=(), source_uuidv4s=(), object_oids=())
    def issue(issuer=service):
        return issuer.context("local-token", "provider_intake", selection, AdmissionBudget(work_limit=64))
    def authorize(handle):
        with service.authorize(handle, needed):
            pass
    genuine = issue()
    for name, bad in (("foreign-service-identical-principal-policy", issue(foreign)), ("copied-issued-handle", replace(genuine))):
        before = policy.calls
        result = expect_refusal(lambda: authorize(bad), "PERMISSION_DENIED")
        assert policy.calls == before and policy.active == 0
        CASES.append({"name": name, "result": "PASS", "details": {**result,"policy_calls":0}})
    authorize(genuine)
    policy.grants = DependencySet()
    before = genuine.budget.used_work
    result = expect_refusal(lambda: authorize(genuine), "PERMISSION_DENIED")
    assert genuine.budget.used_work > before and policy.active == 0
    CASES.append({"name":"same-issued-handle-revoked-replay", "result":"PASS", "details":{**result,"charged_again":True}})
    policy.grants = needed
    empty = service.context("local-token", "provider_intake", AdmissionSelection(resource_keys=(), repository_uuidv4s=(), source_uuidv4s=(), object_oids=()), AdmissionBudget())
    result = expect_refusal(lambda: authorize(empty), "OMITTED_BY_SELECTION")
    CASES.append({"name":"finite-selection-rejects-unselected-resource", "result":"PASS", "details":result})
    before = policy.calls
    object.__setattr__(genuine, "selection", AdmissionSelection(all_selected=True))
    result = expect_refusal(lambda: authorize(genuine), "PERMISSION_DENIED")
    assert policy.calls == before
    CASES.append({"name":"mutated-issued-selection-rejected-before-policy", "result":"PASS", "details":result})


def main():
    for index, native in enumerate(("", [], [""], [[]], ["e\u0301", "é", ["😀", []]])):
        record(f"canonical-unknown-and-global-document-{index}", lambda native=native: roundtrip(context(resource(native), resource(native,"document"))))
    row = resource(["issue", j(["native", []]), "timeline_event", ["E", []]], "comment")
    row.update(identifier_namespace_kind="issue", identifier_namespace_id=j(["native", []]), document_kind="timeline_event", provider_document_id=j(["E", []]))
    record("scoped-child-without-namespace-resource-or-parent", lambda: roundtrip(context(row)))
    for field in tuple(row):
        malformed = deepcopy(row); malformed.pop(field)
        record("missing-named-resource-field-"+field, lambda malformed=malformed: expect_refusal(lambda:decode_context_v5(context(malformed))))
    for field, value in (("provider_resource_id", j(["issue", ["native", []], "timeline_event", ["E", []]])), ("identifier_namespace_id", j("different")), ("provider_document_id", None), ("document_kind", "")):
        malformed = deepcopy(row); malformed[field]=value
        record("scoped-mismatch-"+field, lambda malformed=malformed:expect_refusal(lambda:decode_context_v5(context(malformed))))
    for index, raw in enumerate((' "D" ', '"\\u0044"', '"é"', '7', 'true', 'null', '{}', '[1]')):
        malformed=resource("D");malformed["provider_resource_id"]=raw
        record(f"noncanonical-identity-{index}",lambda malformed=malformed:expect_refusal(lambda:decode_context_v5(context(malformed))))
    for version in (None,"git-repo-db/adr0031-exchange-v4","git-repo-db/adr0031-exchange-v6"):
        data=checksum(envelope());data["format"]=version
        record("unsupported-version-"+str(version),lambda data=data:expect_refusal(lambda:decode_package(data),"UNSUPPORTED_WIRE_VERSION"))
    for dimension, canonical in (("notes_refs",["refs/notes/a","refs/notes/z"]),("repository_uuidv4s",[REPOSITORY,SERVICE]),("source_uuidv4s",[REPOSITORY,SERVICE]),("resource_keys",[[SERVICE,"x-review",j("a")],[SERVICE,"x-review",j("z")]]),("object_oids",[["sha1","1"*40],["sha1","f"*40]])):
        for variant, changed in (("duplicate",[canonical[0],canonical[0]]),("permuted",list(reversed(canonical)))):
            data=envelope();data["selection_scope"][dimension]=canonical;checksum(data)
            data["selection_scope"][dimension]=changed
            record(dimension+"-"+variant+"-stale-digest",lambda data=deepcopy(data):trace_selection(data,"DIGEST_MISMATCH"))
            checksum(data)
            record(dimension+"-"+variant+"-rehashed",lambda data=deepcopy(data):trace_selection(data,"INVALID_SELECTION"))
    for changed in (True, 1.0, "1", -1):
        data=envelope();data["selection_scope"]["max_work"]=changed;checksum(data)
        record("strict-work-type-"+repr(changed),lambda data=data:expect_refusal(lambda:decode_package(data),"INVALID_SELECTION"))
    record("admission-independent-finite-vectors",admission_vectors)
    output = {"reviewed_commit":"fee364c6d61a5feebf08dbdd830a5a57ee2d872b", "sqlite_version":sqlite3.sqlite_version,"python":sys.version,"executable":sys.executable,"cases":CASES,"passed":sum(c["result"]=="PASS" for c in CASES),"failed":sum(c["result"]!="PASS" for c in CASES)}
    Path(sys.argv[1]).write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:output[k] for k in ("passed","failed","sqlite_version")}))
    return bool(output["failed"])


if __name__ == "__main__":
    raise SystemExit(main())
