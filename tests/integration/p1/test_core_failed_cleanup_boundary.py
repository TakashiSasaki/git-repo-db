"""Failed savepoint cleanup discards the real Runtime-owned connection."""

import sqlite3
from contextlib import closing

import pytest

from repo_catalog.adapters.sqlite.admission_transaction import AdmissionTransaction
from repo_catalog.adapters.sqlite.p1_core import Core
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.domain.p1_core import CoreFailure, RelationGroup, RelationMember
from tests.integration.p1.test_core import core, oid, provenance

__all__ = ["core"]


@pytest.mark.parametrize(
    "statement",
    ["ROLLBACK TO p1_core_unit", "RELEASE p1_core_unit"],
    ids=["rollback-to", "release-after-rollback"],
)
def test_failed_cleanup_closes_runtime_transaction_guard_before_caller_can_commit(
    core, statement
):
    _owner, path, _repository = core
    original_error = ValueError("original domain evidence failure")

    class RefusingCleanup(AdmissionTransaction):
        armed = False

        def execute(self, sql, *args, **kwargs):
            if self.armed and sql == statement:
                assert self.in_transaction
                raise sqlite3.OperationalError("injected Runtime cleanup refusal")
            return super().execute(sql, *args, **kwargs)

    raw = connect(path, "core")
    raw.execute("BEGIN IMMEDIATE")
    transaction = RefusingCleanup(raw)

    def fail():
        raise original_error

    group = RelationGroup(
        oid("c"),
        "commit_parents",
        "original-complete-group",
        "complete",
        (RelationMember(0, oid("d")),),
        provenance(),
    )
    try:
        with pytest.raises(ValueError) as failure:
            with Core.for_transaction(transaction) as capability:
                capability.admit_object(oid("a"))
                transaction.armed = True
                capability.admit_group(group, before_commit=fail)
        assert failure.value is original_error
        assert any("OperationalError" in note for note in original_error.__notes__)
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            raw.execute("COMMIT")
        with pytest.raises(CoreFailure, match="expired"):
            capability.admit_object(oid("b"))
    finally:
        raw.close()
    with closing(Core(path)) as reopened:
        assert reopened.sql("SELECT * FROM git_objects") == []
        assert reopened.sql("SELECT * FROM relation_groups") == []
    assert not (path.parent / "p1-recovery-stop.json").exists()
