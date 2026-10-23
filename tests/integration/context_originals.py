"""Explicit synthetic original observations for integration fixtures only."""

from repo_catalog.domain.p1_context import canonical
from repo_catalog.domain.parent_report import ParentObservation, ParentReportKey


def synthetic_parent(event, issue):
    """Declare a separate fixture Parent observation, never derive it from Event data."""
    return ParentObservation(
        ParentReportKey(
            event,
            canonical([list(issue.coordinates())]),
            canonical({"source": "integration-parent-fixture", "evidence": "P"}),
            canonical(
                {
                    "clock": {"domain": "fixture-parent", "at_us": 50},
                    "document_kind": "timeline_event",
                    "state": "complete",
                }
            ),
        ),
        51,
    )
