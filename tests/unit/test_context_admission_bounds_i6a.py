"""Current mapping lookup stops before exhausting a small request budget."""

import pytest

from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import (
    AdmissionBudget,
    AdmissionRefused,
    DependencySet,
)
from repo_catalog.domain.p1_context import FieldClock, MappingClaimKey, canonical
from tests.integration.p3.test_transfer_admission import (
    KEY_PROV_REPO_1,
    REPO_1,
    _setup_base_records,
    fixture_grants,
    make_transfer_report,
)
from tests.support.context_admission import fixture_context, fixture_service
from tests.support.i6a import isolated_context_db


@pytest.mark.parametrize("adapter", ["store", "facade"])
def test_t11_current_claim_scan_charges_and_stops_before_full_materialization(
    tmp_path, adapter
):
    claims = tuple(
        MappingClaimKey(
            KEY_PROV_REPO_1,
            clock=FieldClock("distinct-original", index + 1),
            target_json=canonical(REPO_1),
            provenance_json=canonical({"source": "synthetic", "evidence": index}),
        )
        for index in range(50)
    )
    service, policy = fixture_service(
        fixture_grants() | DependencySet(mapping_claims=claims)
    )
    budget = AdmissionBudget(dependency_limit=25)
    admission = fixture_context(service, budget=budget)
    fetched = []

    class CountingCursor:
        def __init__(self, cursor):
            self.cursor = cursor

        def fetchone(self):
            row = self.cursor.fetchone()
            fetched.append(row)
            return row

        def fetchall(self):
            pytest.fail("bounded current-claim lookup used fetchall")

        def close(self):
            self.cursor.close()

    class CountingConnection:
        def __init__(self, connection):
            self._connection = connection

        @property
        def in_transaction(self):
            return self._connection.in_transaction

        def execute(self, sql, parameters=()):
            cursor = self._connection.execute(sql, parameters)
            if sql.startswith("SELECT clock_json,target_json,provenance_json "):
                return CountingCursor(cursor)
            return cursor

    with isolated_context_db() as db:
        _setup_base_records(db)
        for claim in claims:
            db.execute(
                "INSERT INTO resource_repository_relations("
                "service_instance_uuidv4,resource_kind,provider_resource_id,"
                "relation_kind,clock_json,target_json,provenance_json,observed_at_us) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (*claim.coordinates(), 50),
            )
        before = tuple(
            db.execute(f"SELECT * FROM {table}").fetchall()
            for table in ("resource_relations", "resource_repository_relations")
        )
        tracked = CountingConnection(db)
        with pytest.raises(AdmissionRefused) as stopped:
            if adapter == "facade":
                with Context.owned_transaction(
                    tracked, tmp_path, authorization=service, admission=admission
                ) as facade:
                    facade.admit_transfer_event(make_transfer_report())
            else:
                store = ContextStore(tracked, authorization=service)
                with store.admission_transaction(admission=admission):
                    store.admit_transfer_event(make_transfer_report())
        assert stopped.value.code == "INPUT_LIMIT"
        assert 0 < len(fetched) <= budget.dependency_limit + 1 < len(claims)
        assert budget.used_dependencies > budget.dependency_limit
        assert budget.used_work > 0 and budget.used_bytes > 0
        assert not db.in_transaction
        assert policy.active == 0
        after = tuple(
            db.execute(f"SELECT * FROM {table}").fetchall()
            for table in ("resource_relations", "resource_repository_relations")
        )
        assert after == before
