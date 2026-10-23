"""Independent original-evidence adversarial probes; synthetic in-memory state only.

Run from the reviewed checkout with PYTHONPATH=src:. <venv>/bin/python this.py.
The existing isolated-schema helper is infrastructure only: all report vectors,
failure expectations and assertions below were independently designed for review.
No Provider adapter, live catalog or product source is changed.
"""

import json
import sqlite3
import sys
import traceback
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.domain.context_admission import AdmissionRefused, DependencySet
from repo_catalog.domain.p1_context import (
    EventReportKey,
    FieldClock,
    ProviderEndpointDeclaration,
    ResourceKey,
    ResourceRepositoryRelation,
    TransferEventReport,
    canonical,
)
from repo_catalog.domain.parent_report import ParentObservation, ParentReportKey
from repo_catalog.domain.resource_identification import ResourceIdentification as RI
from tests.support.context_admission import fixture_context, fixture_service
from tests.support.i6a import isolated_context_db

SERVICE = "aad25448-03eb-4f83-a75e-cb7055fd33be"
ISSUE = ResourceKey.from_native(SERVICE, "issue", "review-I")
PR = ResourceKey.from_native(SERVICE, "pull_request", "review-PR")
ALT = ResourceKey.from_native(SERVICE, "issue", "review-alternative")
E = ResourceKey.document(ISSUE, "comment", "timeline_event", "review-E")
P = ResourceKey.from_native(SERVICE, "repository", "review-provider-R")
GLOBAL = ResourceKey.from_native(SERVICE, "document", ["review", []])
SCOPED = ResourceKey.document(PR, "document", "review-body", "D")
EP = canonical({"source": "review-event-original", "evidence": ["E", 900]})
PP = canonical({"source": "review-parent-original", "evidence": ["P", 21]})
EVENT_CLOCK = FieldClock("review-event-clock", 900)
PARENT_CLOCK = FieldClock("review-parent-clock", 21)
ROLES = ("transfer_from_repository", "transfer_to_repository")


def parent(issue=ISSUE, *, time=22, clock=PARENT_CLOCK, provenance=PP):
    return ParentObservation(
        ParentReportKey(
            E,
            canonical([list(issue.coordinates())]),
            provenance,
            canonical(
                {
                    "clock": json.loads(clock.encode()),
                    "document_kind": "timeline_event",
                    "state": "complete",
                }
            ),
        ),
        time,
    )


def report(
    *, original=None, from_state="explicit_null", to_state="explicit_null", targets=None
):
    declaration = ProviderEndpointDeclaration(from_state, to_state)
    if targets is None:
        targets = tuple(
            (role, "null")
            for role in ROLES
            if declaration.state_for(role) == "explicit_null"
        )
    relations = tuple(
        ResourceRepositoryRelation(E, role, EVENT_CLOCK, target, EP, 901)
        for role, target in targets
    )
    return TransferEventReport(
        EventReportKey(E, EVENT_CLOCK, EP),
        parent() if original is None else original,
        declaration,
        targets,
        901,
        tuple(r for r in relations if r.relation_kind == ROLES[0]),
        tuple(r for r in relations if r.relation_kind == ROLES[1]),
    )


def rows(db):
    return tuple(
        db.execute(
            "SELECT relation_kind,members_json,provenance_json,scope_json,observed_at_us FROM resource_relations ORDER BY relation_kind,members_json,provenance_json,scope_json"
        )
    ), tuple(
        db.execute(
            "SELECT relation_kind,target_json,event_report_members_json,event_report_scope_json FROM resource_repository_relations ORDER BY relation_kind,target_json"
        )
    )


def seed_parent(db, value):
    db.execute(
        "INSERT INTO resource_relations(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,members_json,provenance_json,scope_json,observed_at_us) VALUES(?,?,?,'parent',?,?,?,?)",
        (
            *E.coordinates(),
            value.members_json,
            value.provenance_json,
            value.scope_json,
            value.observed_at_us,
        ),
    )


@contextmanager
def boundary(*, original=None, parent_present=True):
    # Finite fixed identity grants, declared independently of mutation arguments.
    service, policy = fixture_service(
        DependencySet(
            resources={ISSUE, ALT, E, P, GLOBAL, SCOPED},
            provider_registrations={SERVICE},
        )
    )
    with isolated_context_db() as db:
        db.execute(
            "INSERT INTO providers VALUES(?,?,?)", (SERVICE, "review-synthetic", "{}")
        )
        store = ContextStore(db, authorization=service)
        for key, identity in (
            (ISSUE, RI.unscoped(ISSUE)),
            (ALT, RI.unscoped(ALT)),
            (E, RI.scoped(E, ISSUE, "timeline_event", "review-E")),
            (P, RI.unscoped(P)),
        ):
            context = fixture_context(service)
            with store.transaction(admission=context):
                store.resource(key, identification=identity, admission=context)
        if parent_present:
            seed_parent(db, parent() if original is None else original)
        yield db, store, service, policy


def admit(store, service, value):
    context = fixture_context(service)
    with store.transaction(admission=context):
        return store.admit_transfer_event(value, admission=context)


def refused(code, action):
    try:
        action()
    except AdmissionRefused as error:
        assert error.code == code, (code, error.code)
        return error.code
    raise AssertionError("expected refusal: " + code)


def case_constructor_missing_parent():
    value = report()
    refused("INCOMPLETE_ORIGINAL_REPORT", lambda: replace(value, parent_report=None))


def case_constructor_missing_declaration():
    refused(
        "INCOMPLETE_ORIGINAL_REPORT",
        lambda: replace(report(), endpoint_declaration=None),
    )


def case_constructor_missing_endpoints():
    refused("INCOMPLETE_ORIGINAL_REPORT", lambda: replace(report(), endpoints=None))


def case_missing_parent_time_is_not_null():
    try:
        ParentObservation(parent().report_key)
    except TypeError:
        return
    raise AssertionError("omitted original observation accepted")


def case_both_unreported_is_no_report():
    refused(
        "INCOMPLETE_ORIGINAL_REPORT",
        lambda: ProviderEndpointDeclaration("not_reported", "not_reported"),
    )


def case_constructor_truncated_two_sided():
    value = report()
    refused("INCOMPLETE_ENDPOINT_SET", lambda: replace(value, from_relations=()))


def case_selection_truncated_is_not_one_sided():
    refused("OMITTED_BY_SELECTION", lambda: replace(report(), selection_truncated=True))
    refused(
        "OMITTED_BY_SELECTION",
        lambda: replace(report(), omitted_roles=frozenset({ROLES[0]})),
    )


def case_one_sided_and_explicit_null_distinct():
    with boundary() as (db, store, service, _):
        value = report(from_state="not_reported")
        assert admit(store, service, value) == "insert"
        (restored,) = store.transfer_event_reports(E)
        assert restored == value
        assert restored.endpoint_declaration.from_endpoint == "not_reported"
        assert restored.endpoint_declaration.to_endpoint == "explicit_null"
        assert db.execute(
            "SELECT count(*) FROM resource_repository_relations"
        ).fetchone() == (1,)


def case_two_sided_null_and_replay_preserve_originals():
    with boundary() as (db, store, service, _):
        value = report()
        assert admit(store, service, value) == "insert"
        before = rows(db)
        assert admit(store, service, value) == "duplicate"
        assert rows(db) == before
        (restored,) = store.transfer_event_reports(E)
        assert restored == value
        assert restored.parent_report.observed_at_us == 22
        assert restored.observed_at_us == 901
        assert json.loads(restored.parent_scope_json)["clock"] == {
            "at_us": 21,
            "domain": "review-parent-clock",
        }
        assert restored.parent_provenance_json == PP != EP


def case_provider_only_unresolved_is_not_null():
    with boundary() as (db, store, service, _):
        value = report(from_state="not_reported", to_state=P, targets=())
        assert admit(store, service, value) == "insert"
        (restored,) = store.transfer_event_reports(E)
        assert restored == value
        assert restored.to_provider_repository == P
        assert restored.endpoints == ()
        assert db.execute(
            "SELECT count(*) FROM resource_repository_relations"
        ).fetchone() == (0,)


def case_parent_explicit_null_stays_null():
    original = parent(time=None)
    with boundary(original=original) as (_, store, service, _):
        value = report(original=original)
        assert admit(store, service, value) == "insert"
        (restored,) = store.transfer_event_reports(E)
        assert restored.parent_report.observed_at_us is None
        assert restored.observed_at_us == 901


def case_changed_parent_payload_refuses_even_replay():
    with boundary() as (db, store, service, _):
        assert admit(store, service, report()) == "insert"
        before = rows(db)
        refused(
            "IMMUTABLE_REPLAY_CONFLICT",
            lambda: admit(store, service, report(original=parent(time=23))),
        )
        assert rows(db) == before and not db.in_transaction


def case_event_coordinates_cannot_substitute_parent():
    with boundary() as (db, store, service, _):
        before = rows(db)
        synthesized = parent(clock=EVENT_CLOCK, provenance=EP, time=901)
        refused(
            "MISSING_DEPENDENCY",
            lambda: admit(store, service, report(original=synthesized)),
        )
        assert rows(db) == before and not db.in_transaction


def case_missing_exact_parent_is_not_recovered_from_native_id():
    with boundary(parent_present=False) as (db, store, service, _):
        before = rows(db)
        refused("MISSING_DEPENDENCY", lambda: admit(store, service, report()))
        assert rows(db) == before
        seed_parent(db, parent())
        assert db.execute(
            "SELECT count(*) FROM resource_relations WHERE relation_kind='transfer_event_report'"
        ).fetchone() == (0,)
        assert admit(store, service, report()) == "insert"


def case_multiple_parents_retained_without_winner():
    with boundary() as (db, store, service, _):
        alternate = parent(
            ALT,
            clock=FieldClock("review-alternative", 30),
            provenance=canonical({"source": "review-other", "evidence": "other"}),
            time=31,
        )
        seed_parent(db, alternate)
        before = rows(db)
        refused(
            "QS10_PARENT_INELIGIBLE",
            lambda: admit(store, service, report(original=alternate)),
        )
        assert rows(db) == before
        assert admit(store, service, report()) == "insert"
        assert db.execute(
            "SELECT count(*) FROM resource_relations WHERE relation_kind='parent'"
        ).fetchone() == (2,)
        (restored,) = store.transfer_event_reports(E)
        assert restored.parent_report == parent()


def case_replay_cannot_rewrite_two_sided_as_one_sided():
    with boundary() as (db, store, service, _):
        assert admit(store, service, report()) == "insert"
        before = rows(db)
        refused(
            "IMMUTABLE_REPLAY_CONFLICT",
            lambda: admit(store, service, report(from_state="not_reported")),
        )
        assert rows(db) == before


def case_stored_rows_cannot_rescue_truncated_delivery():
    with boundary() as (db, store, service, _):
        value = report()
        assert admit(store, service, value) == "insert"
        before = rows(db)
        refused(
            "INCOMPLETE_ENDPOINT_SET",
            lambda: TransferEventReport.from_stored_scope(
                value.report_key,
                value.to_relations,
                value.scope_json,
                value.members_json,
                901,
                parent_report=parent(),
            ),
        )
        assert rows(db) == before


def case_decoder_requires_all_original_parent_coordinates():
    value = report()
    for key in ("parent_members_json", "parent_provenance_json", "parent_scope_json"):
        for mode in ("omit", "null"):
            scope = json.loads(value.scope_json)
            if mode == "omit":
                del scope[key]
            else:
                scope[key] = None
            refused(
                "INCOMPLETE_ORIGINAL_REPORT",
                lambda: TransferEventReport.from_stored_scope(
                    value.report_key,
                    (*value.from_relations, *value.to_relations),
                    canonical(scope),
                    value.members_json,
                    901,
                    parent_report=parent(),
                ),
            )


def case_child_global_scoped_first_no_semantic_parent():
    service, _ = fixture_service(
        DependencySet(resources={GLOBAL, SCOPED}, provider_registrations={SERVICE})
    )
    with isolated_context_db() as db:
        db.execute(
            "INSERT INTO providers VALUES(?,?,?)", (SERVICE, "review-synthetic", "{}")
        )
        store = ContextStore(db, authorization=service)
        for key, identity in (
            (GLOBAL, RI.global_document(GLOBAL)),
            (SCOPED, RI.scoped(SCOPED, PR, "review-body", "D")),
        ):
            context = fixture_context(service)
            with store.transaction(admission=context):
                store.resource(key, identification=identity, admission=context)
        assert db.execute("SELECT count(*) FROM resources").fetchone() == (2,)
        assert db.execute("SELECT count(*) FROM resource_relations").fetchone() == (0,)
        assert store.identification(GLOBAL) == RI.global_document(GLOBAL)
        assert store.identification(SCOPED) == RI.scoped(SCOPED, PR, "review-body", "D")
        context = fixture_context(service)
        before = rows(db)
        try:
            with store.transaction(admission=context):
                store.resource(SCOPED, admission=context)
        except ValueError as error:
            assert (
                str(error)
                == "known document kind requires explicit ResourceIdentification"
            )
        else:
            raise AssertionError("replay omitted required identification")
        assert rows(db) == before


def main():
    result = {"python": sys.version, "sqlite": sqlite3.sqlite_version, "cases": []}
    for name, operation in sorted(globals().items()):
        if name.startswith("case_"):
            try:
                operation()
                result["cases"].append({"id": name, "result": "PASS"})
            except Exception as error:
                result["cases"].append(
                    {
                        "id": name,
                        "result": "FAIL",
                        "exception": type(error).__name__,
                        "message": str(error),
                        "traceback": traceback.format_exc(),
                    }
                )
    result["passed"] = sum(item["result"] == "PASS" for item in result["cases"])
    result["failed"] = len(result["cases"]) - result["passed"]
    destination = Path(sys.argv[1])
    destination.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({key: result[key] for key in ("passed", "failed")}))
    return int(bool(result["failed"]))


if __name__ == "__main__":
    raise SystemExit(main())
