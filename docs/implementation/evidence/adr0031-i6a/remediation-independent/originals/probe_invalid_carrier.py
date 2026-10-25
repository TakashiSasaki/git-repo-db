"""Reproduce R09 invalid original declaration laundering at the store boundary.

Expected safety result: INCOMPLETE_ORIGINAL_REPORT before writes/duplicate.
The script exits 1 when that safety predicate is violated, retaining the actual
insert/duplicate, pure-validator control and normal product-fence observations.
"""

import json
import sys
from dataclasses import replace
from pathlib import Path

from probe_originals import E, admit, boundary, report, rows

from repo_catalog.domain.context_admission import AdmissionRefused, validate_originals
from repo_catalog.domain.resource_stage import (
    TRANSFER_FENCE_DEFINITIONS,
    UnsupportedResourceStage,
)


def invalid_report(value):
    value_report = report()
    object.__setattr__(value_report.endpoint_declaration, "from_endpoint", value)
    return value_report


def run():
    results = []
    for missing in (None, "invalid-original-state"):
        for replay in (False, True):
            with boundary() as (db, store, service, _):
                if replay:
                    assert admit(store, service, report()) == "insert"
                value = invalid_report(missing)
                before = rows(db)
                controls = {}
                for label, operation in (
                    ("pure_validate_originals", lambda: validate_originals(value)),
                    ("dataclasses_replace", lambda: replace(value)),
                ):
                    try:
                        operation()
                    except AdmissionRefused as error:
                        controls[label] = error.code
                    else:
                        controls[label] = "UNEXPECTED_ACCEPT"
                assert set(controls.values()) == {"INCOMPLETE_ORIGINAL_REPORT"}
                trace = []
                db.set_trace_callback(trace.append)
                try:
                    outcome = admit(store, service, value)
                    code = None
                except AdmissionRefused as error:
                    outcome, code = "refused", error.code
                db.set_trace_callback(None)
                restored = store.transfer_event_reports(E)
                results.append(
                    {
                        "id": f"invalid-original-{missing!r}-{'replay' if replay else 'initial'}",
                        "supplied_from_endpoint": missing,
                        "stage": "isolated-approved-test-fixture",
                        "replay": replay,
                        "expected_code": "INCOMPLETE_ORIGINAL_REPORT",
                        "actual_outcome": outcome,
                        "actual_code": code,
                        "safety_predicate_passed": code == "INCOMPLETE_ORIGINAL_REPORT"
                        and rows(db) == before,
                        "controls": controls,
                        "stored_from_endpoint": restored[
                            0
                        ].endpoint_declaration.from_endpoint
                        if restored
                        else None,
                        "stored_report_equals_supplied_original": restored[0] == value
                        if restored
                        else None,
                        "before_rowsets": before,
                        "after_rowsets": rows(db),
                        "transaction_open": db.in_transaction,
                        "sql_trace": trace,
                    }
                )
        with boundary() as (db, store, service, _):
            # Restore the exact production fences; no attempt to enable any route.
            for _, _, _, sql in TRANSFER_FENCE_DEFINITIONS:
                db.execute(sql)
            before = rows(db)
            try:
                admit(store, service, invalid_report(missing))
            except UnsupportedResourceStage as error:
                assert error.code == "I2_TRANSFER_UNSUPPORTED"
                assert rows(db) == before and not db.in_transaction
                results.append(
                    {
                        "id": f"normal-fence-{missing!r}",
                        "actual_code": error.code,
                        "safety_predicate_passed": True,
                        "rowsets_unchanged": True,
                    }
                )
            else:
                raise AssertionError("normal production fence opened")
    output = {
        "invalid_original_cases": 4,
        "invalid_original_refusals": sum(
            row.get("actual_code") == "INCOMPLETE_ORIGINAL_REPORT" for row in results
        ),
        "normal_fence_controls": 2,
        "observations": results,
    }
    Path(sys.argv[1]).write_text(json.dumps(output, indent=2) + "\n")
    print(
        json.dumps(
            {key: value for key, value in output.items() if key != "observations"}
        )
    )
    return int(any(not row["safety_predicate_passed"] for row in results))


if __name__ == "__main__":
    raise SystemExit(run())
